# -*- coding: utf-8 -*-
"""
==============================================================================
APP.PY (Servidor Flask y Controlador de Tareas)
==============================================================================
Este es el punto de entrada de la aplicación. Levanta un servidor web que
escucha las peticiones de Node.js, ejecuta el orquestador en segundo plano
y maneja los bloqueos (Locks) para no saturar el servidor.

La fabricación del video sigue en main_orchestrator y en las plantillas.
Este módulo solo decide si la tarea puede empezar, la aísla de las demás
y garantiza que el lock se libere.
"""

import os
import signal
import threading
import time
import random
import gc
import logging
import requests
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException

import main_orchestrator
import youtube_uploader
import cloudflare_r2
import process_guard
import service_guard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "secreto123456")
MAIN_API_URL = os.getenv("MAIN_API_URL", "https://lfaftechapi.onrender.com")
PORT = int(os.getenv("PORT", 3001))

if os.getenv("ADMIN_API_KEY") is None:
    logger.warning("ADMIN_API_KEY no está definida. Se está usando la clave por defecto embebida.")

app = Flask(__name__)
try:
    app.config["MAX_CONTENT_LENGTH"] = max(64 * 1024, int(os.getenv("MAX_CONTENT_LENGTH_BYTES", str(2 * 1024 * 1024))))
except ValueError:
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

# Un video a la vez en este proceso. El lock no se comparte entre workers.
processing_lock = threading.Lock()
_state_lock = threading.Lock()
_services_lock = threading.Lock()
try:
    _audio_slots = max(1, int(os.getenv("MAX_AUDIO_CONCURRENCY", "1")))
except ValueError:
    _audio_slots = 1
_audio_sem = threading.BoundedSemaphore(_audio_slots)
_task = {
    "held": False,
    "generation": 0,
    "article_id": None,
    "started": None,
    "phase": "idle",
    "stuck": False,
}
_boot_time = time.time()
_allow_self_restart = False
_supervision_started = False
_watchdog_started = False

# Voz del botón "Escuchar". No forma parte del noticiero y no se cambia.
LISTEN_VOICE = "es-MX-JorgeNeural"
LISTEN_RATE = "+10%"


def _check_auth():
    """Verifica que la petición venga de tu API en Node.js (Seguridad)."""
    api_key = request.headers.get('x-api-key')
    return api_key == ADMIN_API_KEY


def _max_scenes():
    try:
        return max(1, int(os.getenv("MAX_SCENES", "100")))
    except ValueError:
        return 100


def _hard_timeout():
    try:
        return max(600, int(os.getenv("TASK_HARD_TIMEOUT_SECONDS", "10800")))
    except ValueError:
        return 10800


def _public_error(exc):
    text = "%s: %s" % (type(exc).__name__, exc)
    return text.replace("\n", " ")[:300]


def _set_phase(generation, phase):
    with _state_lock:
        if _task["generation"] == generation and _task["held"]:
            _task["phase"] = phase


def _still_owner(generation):
    with _state_lock:
        owns = _task["held"] and _task["generation"] == generation
    return owns and not process_guard.cancellation_requested()


def _acquire_video_lock(article_id):
    if not processing_lock.acquire(blocking=False):
        return None
    with _state_lock:
        _task["generation"] += 1
        _task["held"] = True
        _task["article_id"] = article_id
        _task["started"] = time.time()
        _task["phase"] = "starting"
        _task["stuck"] = False
        generation = _task["generation"]
    process_guard.clear_cancel()
    return generation


def _release_video_lock(generation):
    with _state_lock:
        if _task["generation"] != generation or not _task["held"]:
            return
        _task["held"] = False
        _task["phase"] = "idle"
        _task["article_id"] = None
        _task["started"] = None
        _task["stuck"] = False
    process_guard.clear_cancel()
    try:
        processing_lock.release()
    except RuntimeError:
        logger.exception("  [API] El lock de video ya estaba libre.")


def _marker_path(article_id):
    return os.path.join(youtube_uploader.LOCKS_DIR, "%s.processing" % article_id)


def _write_marker(article_id):
    try:
        os.makedirs(youtube_uploader.LOCKS_DIR, exist_ok=True)
        with open(_marker_path(article_id), "w", encoding="utf-8") as handle:
            handle.write("pid=%s started=%s\n" % (os.getpid(), int(time.time())))
    except OSError as exc:
        logger.warning("  [API] No se pudo escribir el marcador de tarea: %s", exc)


def _clear_marker(article_id):
    try:
        os.remove(_marker_path(article_id))
    except OSError:
        pass


def _clear_stale_markers():
    directory = youtube_uploader.LOCKS_DIR
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        if name.endswith(".processing"):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass


def _string_or_default(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _tag_list(value):
    if isinstance(value, list):
        return value
    return ['noticias', 'actualidad']


@app.route('/health', methods=['GET'])
def health_check():
    """
    Liveness para el orquestador. Responde 200 mientras el proceso atiende,
    aunque esté fabricando un video. 503 solo si el supervisor ya declaró
    el worker irrecuperable y está pidiendo reinicio.
    """
    with _state_lock:
        held = _task["held"]
        stuck = _task["stuck"]
        started = _task["started"]
        phase = _task["phase"]
    free_disk = service_guard.disk_free_mb()
    free_ram = service_guard.memory_available_mb()
    ffmpeg_ok = service_guard.tool_on_path("ffmpeg")
    ffprobe_ok = service_guard.tool_on_path("ffprobe")
    disk_ok, _free = service_guard.disk_allows_new_task()
    ram_ok, _ram = service_guard.memory_allows_new_task()
    accepting = (not held) and (not stuck) and disk_ok and ram_ok and ffmpeg_ok and ffprobe_ok
    if stuck:
        state = "stuck"
    elif held:
        state = "busy"
    elif not accepting:
        state = "degraded"
    else:
        state = "idle"
    body = {
        "status": "unhealthy" if stuck else "healthy",
        "server": "Noticias.lat Video Factory V4",
        "service_state": state,
        "accepting_video_tasks": accepting,
        "video_phase": phase if held else "idle",
        "active_task_seconds": int(time.time() - started) if started else None,
        "disk_free_mb": free_disk,
        "memory_available_mb": free_ram,
        "ffmpeg": ffmpeg_ok,
        "ffprobe": ffprobe_ok,
        "uptime_seconds": int(time.time() - _boot_time),
    }
    return jsonify(body), (503 if stuck else 200)


@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    """Recibe el JSON con las escenas, las valida y encola el trabajo."""

    if not _check_auth():
        logger.warning("  [API] Intento de acceso no autorizado desde %s", request.remote_addr)
        return jsonify({"error": "No autorizado. API Key inválida."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "No se envió un cuerpo JSON válido."}), 400

    raw_article_id = payload.get('article_id')
    scenes = payload.get('scenes')
    article_id = service_guard.validate_article_id(raw_article_id)
    if not article_id or not scenes or not isinstance(scenes, list):
        if raw_article_id not in (None, "") and article_id is None:
            return jsonify({"error": "article_id inválido."}), 400
        return jsonify({"error": "Faltan datos obligatorios: article_id o scenes."}), 400
    if len(scenes) > _max_scenes():
        return jsonify({"error": "El payload excede el máximo de escenas admitidas."}), 400

    payload["article_id"] = article_id
    youtube_title = _string_or_default(payload.get('youtube_title'), 'Noticia de Última Hora')
    youtube_desc = _string_or_default(payload.get('youtube_description'), 'Mira la noticia completa en Noticias.lat')
    youtube_tags = _tag_list(payload.get('youtube_tags'))

    if youtube_uploader.is_already_processed(article_id):
        logger.info("  [API] Tarea %s ignorada. Ya existe en el historial.", article_id)
        return jsonify({
            "message": "El video ya fue generado y subido anteriormente.",
            "status": "completed",
            "article_id": raw_article_id
        }), 200

    if not service_guard.tool_on_path("ffmpeg") or not service_guard.tool_on_path("ffprobe"):
        logger.error("  [API] FFmpeg o ffprobe no están en el PATH.")
        return jsonify({"error": "El motor de video no está disponible. Reintente más tarde."}), 503

    disk_ok, free_disk = service_guard.disk_allows_new_task()
    if not disk_ok:
        logger.error("  [API] Disco insuficiente (%s MiB libres).", free_disk)
        return jsonify({"error": "Espacio en disco insuficiente para renderizar. Reintente más tarde."}), 503

    ram_ok, free_ram = service_guard.memory_allows_new_task()
    if not ram_ok:
        logger.error("  [API] RAM insuficiente (%s MiB disponibles).", free_ram)
        return jsonify({"error": "Memoria insuficiente para renderizar. Reintente más tarde."}), 503

    generation = _acquire_video_lock(article_id)
    if generation is None:
        logger.warning("  [API] Servidor ocupado. Rechazando ID: %s", article_id)
        return jsonify({
            "error": "El servidor está procesando otro video. Reintente en unos minutos."
        }), 503

    logger.info("  [API] [Lock Adquirido] Iniciando producción para ID: %s", article_id)
    _write_marker(article_id)

    def background_task():
        try:
            _set_phase(generation, "render")
            video_path = main_orchestrator.process_video_payload(payload)

            if not _still_owner(generation):
                logger.error("  [Background] TASK_CANCELLED article=%s", article_id)
                _notificar_webhook_node("video_failed", raw_article_id, error="task_timeout")
                return

            if video_path and os.path.exists(video_path):
                logger.info("  [Background] Video listo. Iniciando subidas...")
                _set_phase(generation, "upload")

                nombre_video_r2 = f"video_{article_id}.mp4"
                url_r2 = cloudflare_r2.upload_media_to_r2(video_path, nombre_video_r2)

                if not _still_owner(generation):
                    logger.error("  [Background] TASK_CANCELLED article=%s durante la subida", article_id)
                    _notificar_webhook_node("video_failed", raw_article_id, error="task_timeout")
                    return

                youtube_id = youtube_uploader.upload_video(
                    file_path=video_path,
                    title=youtube_title,
                    description=youtube_desc,
                    tags=youtube_tags
                )

                if youtube_id or url_r2:
                    if youtube_id:
                        youtube_uploader.mark_as_processed(article_id, youtube_id)

                    _notificar_webhook_node("video_complete", raw_article_id, youtube_id=youtube_id, video_url=url_r2)

                    try:
                        os.remove(video_path)
                        logger.info("  [Limpieza] Video borrado del disco: %s", video_path)
                        posible_jpg = video_path.rsplit('.', 1)[0] + '.jpg'
                        if os.path.exists(posible_jpg):
                            os.remove(posible_jpg)
                    except Exception as exc:
                        logger.warning("  [Limpieza] No se pudo borrar el video: %s", exc)
                else:
                    logger.error("  [Background] Falló la subida a YouTube.")
                    _notificar_webhook_node("video_failed", raw_article_id, error="YouTube Upload Failed")
            else:
                logger.error("  [Background] El orquestador no devolvió un video válido.")
                _notificar_webhook_node("video_failed", raw_article_id, error="Video Generation Failed")

        except Exception as exc:
            logger.exception("  [Background] TASK_FAILED article=%s", article_id)
            _notificar_webhook_node("video_failed", raw_article_id, error=_public_error(exc))

        finally:
            _clear_marker(article_id)
            _release_video_lock(generation)
            logger.info("  [API] [Lock Liberado] Servidor listo para nueva tarea.")
            gc.collect()

    worker = threading.Thread(target=background_task, name="video-%s" % article_id, daemon=True)
    try:
        worker.start()
    except Exception:
        logger.exception("  [API] No se pudo lanzar la tarea %s", article_id)
        _clear_marker(article_id)
        _release_video_lock(generation)
        return jsonify({"error": "No se pudo iniciar la tarea."}), 500

    return jsonify({
        "message": "Tarea matricial aceptada. Fabricando en segundo plano.",
        "status": "processing",
        "article_id": raw_article_id
    }), 202


def _notificar_webhook_node(endpoint, article_id, youtube_id=None, video_url=None, audio_url=None, error=None):
    """
    Se comunica de vuelta con tu API de Node.js para avisarle cómo terminó todo.
    El cuerpo y la ruta son los de siempre. Solo se reintenta si la falla es transitoria.
    """
    webhook_url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}

    payload = {"articleId": article_id}
    if youtube_id:
        payload["youtubeId"] = youtube_id
    if video_url:
        payload["videoUrl"] = video_url
    if audio_url:
        payload["audioUrl"] = audio_url
    if error:
        payload["error"] = str(error).replace("\n", " ")[:300]

    for attempt in range(3):
        try:
            response = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                logger.info("  [Webhook] API de Node.js notificada con éxito (%s).", endpoint)
                return
            body = (response.text or "").replace("\n", " ")[:200]
            logger.warning("  [Webhook] La API de Node.js respondió con error %s: %s", response.status_code, body)
            if response.status_code not in (429, 500, 502, 503, 504):
                return
        except Exception as exc:
            logger.error("  [Webhook] Error de conexión al notificar a Node.js: %s", exc)
        if attempt < 2:
            time.sleep((2 ** attempt) + random.uniform(0, 0.3))


@app.route('/', methods=['GET'])
def index():
    return "<h1>Noticias.lat - Motor Matricial Activo</h1>", 200


def build_listen_audio_command(texto_completo, ruta_audio):
    """Mismos voz, ritmo y limpieza de comillas. Sin shell."""
    texto_limpio = texto_completo.replace('"', '').replace("'", "")
    return [
        "edge-tts",
        "--voice", LISTEN_VOICE,
        "--rate", LISTEN_RATE,
        "--text", texto_limpio,
        "--write-media", ruta_audio,
    ]


def _audio_timeout():
    try:
        return max(30, int(os.getenv("AUDIO_TTS_TIMEOUT_SECONDS", "180")))
    except ValueError:
        return 180


def background_audio_task(raw_article_id, safe_article_id, texto_completo):
    logger.info("  [Audio] Iniciando locución completa para %s", safe_article_id)
    ruta_audio = None
    try:
        nombre_archivo = f"audio_{safe_article_id}.mp3"
        os.makedirs("temp", exist_ok=True)
        ruta_audio = os.path.join("temp", nombre_archivo)
        comando = build_listen_audio_command(texto_completo, ruta_audio)
        process_guard.run(comando, timeout=_audio_timeout(), check=True, log_label="Audio edge-tts")

        url_r2 = cloudflare_r2.upload_media_to_r2(ruta_audio, nombre_archivo)
        if url_r2:
            _notificar_webhook_node("audio_complete", raw_article_id, video_url=None, audio_url=url_r2)
    except Exception as exc:
        logger.exception("  [Audio] Error generando MP3 para %s: %s", safe_article_id, exc)
    finally:
        if ruta_audio and os.path.exists(ruta_audio):
            try:
                os.remove(ruta_audio)
                logger.info("  [Limpieza] Audio borrado del disco: %s", ruta_audio)
            except Exception as exc:
                logger.warning("  [Limpieza] No se pudo borrar el audio local: %s", exc)
        _audio_sem.release()


def _audio_capacity_ok():
    if not processing_lock.locked():
        return True
    free = service_guard.memory_available_mb()
    try:
        needed = int(os.getenv("MIN_RAM_FOR_AUDIO_DURING_VIDEO_MB", "200"))
    except ValueError:
        needed = 200
    if free is None or free < needed:
        return False
    return True


@app.route('/api/tasks/audio', methods=['POST'])
def task_audio():
    """Ruta que Node.js llamará para pedir un MP3 completo."""
    data = request.get_json(silent=True)
    api_key = request.headers.get("x-api-key")

    if api_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    if not isinstance(data, dict):
        return jsonify({"error": "Faltan datos"}), 400

    raw_article_id = data.get("articleId")
    texto_completo = data.get("texto")
    article_id = service_guard.validate_article_id(raw_article_id)

    if not article_id or not isinstance(texto_completo, str) or not texto_completo.strip():
        return jsonify({"error": "Faltan datos"}), 400
    try:
        max_audio_chars = int(os.getenv("MAX_AUDIO_CHARS", "30000"))
    except ValueError:
        max_audio_chars = 30000
    if len(texto_completo) > max_audio_chars:
        return jsonify({"error": "Faltan datos"}), 400

    if not _audio_capacity_ok() or not _audio_sem.acquire(blocking=False):
        logger.warning("  [Audio] Rechazado por capacidad. article=%s", article_id)
        return jsonify({"error": "El servidor está ocupado generando audio. Reintente en unos minutos."}), 503

    worker = threading.Thread(
        target=background_audio_task,
        args=(raw_article_id, article_id, texto_completo),
        name="audio-%s" % article_id,
        daemon=True,
    )
    try:
        worker.start()
    except Exception:
        _audio_sem.release()
        logger.exception("  [Audio] No se pudo lanzar la locución %s", article_id)
        return jsonify({"error": "No se pudo iniciar la tarea."}), 500

    return jsonify({"message": "Generación de audio iniciada", "articleId": raw_article_id}), 202


def run_cleanup_loop():
    time.sleep(10)
    while True:
        try:
            cloudflare_r2.delete_old_files_from_r2(days_old=28)
        except Exception as exc:
            logger.error("Error en el bucle de limpieza automática de R2: %s", exc)
        time.sleep(86400)


def _janitor_loop():
    while True:
        time.sleep(1800)
        try:
            if not processing_lock.locked():
                service_guard.cleanup_stale_workdir(startup=False)
        except Exception:
            logger.exception("  [Limpieza] Falló el barrido de temporales.")


def _watchdog_loop():
    while True:
        time.sleep(15)
        try:
            _watchdog_once()
        except Exception:
            logger.exception("  [Watchdog] Error en el supervisor.")


def _watchdog_once():
    with _state_lock:
        held = _task["held"]
        started = _task["started"]
        generation = _task["generation"]
        article_id = _task["article_id"]
        phase = _task["phase"]
    if not held or not started:
        return
    elapsed = time.time() - started
    if elapsed < _hard_timeout():
        return
    logger.critical(
        "WATCHDOG task_stuck article=%s elapsed=%.0f phase=%s",
        article_id, elapsed, phase,
    )
    process_guard.request_cancel()
    process_guard.kill_all()
    deadline = time.time() + 90
    while time.time() < deadline:
        with _state_lock:
            if (not _task["held"]) or _task["generation"] != generation:
                logger.critical("WATCHDOG task_released article=%s", article_id)
                return
        time.sleep(1)
    with _state_lock:
        _task["stuck"] = True
    logger.critical(
        "WATCHDOG_RESTART reason=task_stuck_after_cancel article=%s elapsed=%.0f",
        article_id, elapsed,
    )
    if _allow_self_restart:
        try:
            if article_id:
                _notificar_webhook_node("video_failed", article_id, error="task_timeout")
        except Exception:
            logger.exception("  [Watchdog] No se pudo notificar el timeout.")
        os.kill(os.getpid(), signal.SIGTERM)


def _start_watchdog():
    global _watchdog_started
    with _services_lock:
        if _watchdog_started:
            return
        _watchdog_started = True
    threading.Thread(target=_watchdog_loop, name="stability-watchdog", daemon=True).start()


def enable_production_supervision():
    """Arranque de limpieza y reinicio automático. Lo llama Gunicorn al crear el worker."""
    global _supervision_started, _allow_self_restart
    with _services_lock:
        if _supervision_started:
            return
        _supervision_started = True
        _allow_self_restart = True
    _start_watchdog()
    _clear_stale_markers()
    try:
        service_guard.cleanup_stale_workdir(startup=True)
    except Exception:
        logger.exception("  [Limpieza] Falló la limpieza de arranque.")
    if os.getenv("R2_CLEANUP_ENABLED", "0") == "1":
        threading.Thread(target=run_cleanup_loop, name="r2-cleanup", daemon=True).start()
        logger.info("Limpieza de R2 activada cada 24 horas.")
    else:
        logger.info("Limpieza de R2 apagada. Definir R2_CLEANUP_ENABLED=1 para borrados de más de 28 días.")
    threading.Thread(target=_janitor_loop, name="temp-janitor", daemon=True).start()
    logger.info(
        "SERVICE_READY ffmpeg=%s ffprobe=%s disk_free_mb=%s ram_available_mb=%s",
        service_guard.tool_on_path("ffmpeg"),
        service_guard.tool_on_path("ffprobe"),
        service_guard.disk_free_mb(),
        service_guard.memory_available_mb(),
    )


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return jsonify({"error": exc.name, "status": exc.code}), exc.code


@app.errorhandler(Exception)
def handle_unexpected_exception(exc):
    logger.exception("Error no controlado en una petición HTTP.")
    return jsonify({"error": "Error interno del servidor."}), 500


_start_watchdog()


if __name__ == '__main__':
    enable_production_supervision()
    app.run(host='0.0.0.0', port=PORT, threaded=True, use_reloader=False)
