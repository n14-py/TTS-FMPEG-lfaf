# -*- coding: utf-8 -*-
"""
==============================================================================
APP.PY (Servidor Flask y Controlador de Tareas)
==============================================================================
Este es el punto de entrada de la aplicación. Levanta un servidor web que
escucha las peticiones de Node.js, ejecuta el orquestador en segundo plano
y maneja los bloqueos (Locks) para no saturar el servidor.
"""

import os
import threading
import gc
import logging
import requests
from flask import Flask, request, jsonify

# Importamos nuestros módulos maestros
import main_orchestrator
import youtube_uploader
import cloudflare_r2
import subprocess

# ==============================================================================
# CONFIGURACIÓN INICIAL
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

# Variables de entorno (Las mismas que tenías en tu .env original)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "secreto123456")
MAIN_API_URL = os.getenv("MAIN_API_URL", "https://lfaftechapi.onrender.com")
PORT = int(os.getenv("PORT", 3001))

app = Flask(__name__)

# ==============================================================================
# SEMÁFORO DE PROCESAMIENTO (ANTI-COLAPSO)
# ==============================================================================
# Este "Lock" asegura que solo se procese 1 video a la vez en todo el servidor.
processing_lock = threading.Lock()

def _check_auth():
    """Verifica que la petición venga de tu API en Node.js (Seguridad)."""
    api_key = request.headers.get('x-api-key')
    return api_key == ADMIN_API_KEY

# ==============================================================================
# RUTAS DE LA API
# ==============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Ruta para que Render sepa que el servidor está vivo."""
    return jsonify({"status": "healthy", "server": "Noticias.lat Video Factory V4"}), 200

@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    """Recibe el JSON con las escenas, las valida y encola el trabajo."""
    
    # 1. Seguridad básica
    if not _check_auth():
        logger.warning(f"  [API] Intento de acceso no autorizado desde {request.remote_addr}")
        return jsonify({"error": "No autorizado. API Key inválida."}), 403

    # 2. Obtener y validar el JSON
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No se envió un cuerpo JSON válido."}), 400

    article_id = payload.get('article_id')
    scenes = payload.get('scenes')
    youtube_title = payload.get('youtube_title', 'Noticia de Última Hora')
    youtube_desc = payload.get('youtube_description', 'Mira la noticia completa en Noticias.lat')
    youtube_tags = payload.get('youtube_tags', ['noticias', 'actualidad'])

    if not article_id or not scenes:
        return jsonify({"error": "Faltan datos obligatorios: article_id o scenes."}), 400

    # 3. Filtro Anti-Bucle (Revisar si ya se subió a YouTube)
    if youtube_uploader.is_already_processed(article_id):
        logger.info(f"  [API] Tarea {article_id} ignorada. Ya existe en el historial.")
        return jsonify({
            "message": "El video ya fue generado y subido anteriormente.",
            "status": "completed",
            "article_id": article_id
        }), 200

    # 4. Intentar adquirir el control del servidor (Lock)
    if processing_lock.acquire(blocking=False):
        logger.info(f"  [API] [Lock Adquirido] Iniciando producción para ID: {article_id}")
        
        # ----------------------------------------------------------------------
        # HILO EN SEGUNDO PLANO (Background Task)
        # ----------------------------------------------------------------------
        def background_task():
            try:
                # Paso A: Fabricar el video (Llama al orquestador)
                video_path = main_orchestrator.process_video_payload(payload)
                
                # Paso B: Subir a YouTube si se fabricó bien
# Paso B: Subir a Cloudflare y YouTube
                if video_path and os.path.exists(video_path):
                    logger.info("  [Background] Video listo. Iniciando subidas...")
                    
                    # 1. Subir a Cloudflare R2
                    nombre_video_r2 = f"video_{article_id}.mp4"
                    url_r2 = cloudflare_r2.upload_media_to_r2(video_path, nombre_video_r2)
                    
                    # 2. Subir a YouTube
                    youtube_id = youtube_uploader.upload_video(
                        file_path=video_path,
                        title=youtube_title,
                        description=youtube_desc,
                        tags=youtube_tags
                    )
                    
                    # 3. Notificar a Node.js (Solo si se subió a R2 o a YouTube)
                    if youtube_id or url_r2:
                        if youtube_id:
                            youtube_uploader.mark_as_processed(article_id, youtube_id)
                            
                        # Pasamos youtube_id Y url_r2 al webhook
                        _notificar_webhook_node("video_complete", article_id, youtube_id=youtube_id, video_url=url_r2)
                        
                        # --- AUTODESTRUCCIÓN PARA LIBERAR ESPACIO ---
                        try:
                            os.remove(video_path)
                            logger.info(f"  [Limpieza] Video borrado del disco: {video_path}")
                            # Borrar también la miniatura si existe
                            posible_jpg = video_path.rsplit('.', 1)[0] + '.jpg'
                            if os.path.exists(posible_jpg):
                                os.remove(posible_jpg)
                        except Exception as e:
                            logger.warning(f"  [Limpieza] No se pudo borrar el video: {e}")
                        # --------------------------------------------
                        
                    else:
                        logger.error("  [Background] Falló la subida a YouTube.")
                        _notificar_webhook_node("video_failed", article_id, error="YouTube Upload Failed")
                else:
                    logger.error("  [Background] El orquestador no devolvió un video válido.")
                    _notificar_webhook_node("video_failed", article_id, error="Video Generation Failed")

            except Exception as e:
                logger.error(f"  [Background] Error fatal en hilo de procesamiento: {e}")
                _notificar_webhook_node("video_failed", article_id, error=str(e))
                
            finally:
                # ¡CRÍTICO! Liberar el servidor para la siguiente noticia
                processing_lock.release()
                logger.info(f"  [API] [Lock Liberado] Servidor listo para nueva tarea.")
                gc.collect()

        # Lanzar el hilo
        thread = threading.Thread(target=background_task)
        thread.daemon = True
        thread.start()

        # 5. Respuesta inmediata a Node.js
        return jsonify({
            "message": "Tarea matricial aceptada. Fabricando en segundo plano.",
            "status": "processing",
            "article_id": article_id
        }), 202

    else:
        # Si el servidor ya está haciendo un video, rechaza la petición
        logger.warning(f"  [API] Servidor ocupado. Rechazando ID: {article_id}")
        return jsonify({
            "error": "El servidor está procesando otro video. Reintente en unos minutos."
        }), 503

# ==============================================================================
# SISTEMA DE NOTIFICACIONES (WEBHOOKS)
# ==============================================================================
def _notificar_webhook_node(endpoint, article_id, youtube_id=None, video_url=None, audio_url=None, error=None):
    """
    Se comunica de vuelta con tu API de Node.js para avisarle cómo terminó todo.
    """
    webhook_url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    
    payload = {"articleId": article_id}
    if youtube_id:
        payload["youtubeId"] = youtube_id
    if video_url:
        payload["videoUrl"] = video_url # <--- Link de Cloudflare para Video
    if audio_url:
        payload["audioUrl"] = audio_url # <--- Link de Cloudflare para Audio MP3
    if error:
        payload["error"] = error

    try:
        r = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            logger.info(f"  [Webhook] API de Node.js notificada con éxito ({endpoint}).")
        else:
            logger.warning(f"  [Webhook] La API de Node.js respondió con error {r.status_code}: {r.text}")
    except Exception as e:
        logger.error(f"  [Webhook] Error de conexión al notificar a Node.js: {e}")


@app.route('/', methods=['GET'])
def index():
    return "<h1>Noticias.lat - Motor Matricial Activo</h1>", 200



# =====================================================================
# 🎧 MICROSERVICIO DE AUDIO (Para el botón "Escuchar" de la App)
# =====================================================================
# =====================================================================
# 🎧 MICROSERVICIO DE AUDIO (Para el botón "Escuchar" de la App)
# =====================================================================
def background_audio_task(article_id, texto_completo):
    logger.info(f"  [Audio] 🎙️ Iniciando locución completa para {article_id}")
    try:
        nombre_archivo = f"audio_{article_id}.mp3"
        # Aseguramos que la carpeta temp exista antes de guardar el audio
        os.makedirs("temp", exist_ok=True)
        ruta_audio = f"temp/{nombre_archivo}" 
        
        # 1. Limpiamos comillas que puedan romper la consola
        texto_limpio = texto_completo.replace('"', '').replace("'", "")
        
        # 2. Generamos el audio de corrido con la mejor voz
        comando = f'edge-tts --voice "es-MX-JorgeNeural" --rate="+10%" --text "{texto_limpio}" --write-media {ruta_audio}'
        subprocess.run(comando, shell=True, check=True)
        
        # 3. Subimos el MP3 a Cloudflare R2
        url_r2 = cloudflare_r2.upload_media_to_r2(ruta_audio, nombre_archivo)
        
        # 4. Avisamos a Node.js que el AUDIO está listo
        if url_r2:
            _notificar_webhook_node("audio_complete", article_id, video_url=None, audio_url=url_r2)
            
        # 5. --- LIMPIEZA VITAL PARA NO LLENAR EL DISCO ---
        try:
            if os.path.exists(ruta_audio):
                os.remove(ruta_audio)
                logger.info(f"  [Limpieza] Audio borrado del disco: {ruta_audio}")
        except Exception as e:
            logger.warning(f"  [Limpieza] No se pudo borrar el audio local: {e}")
            
    except Exception as e:
        logger.error(f"  [Audio] ❌ Error generando MP3: {e}")

@app.route('/api/tasks/audio', methods=['POST'])
def task_audio():
    """Ruta que Node.js llamará para pedir un MP3 completo."""
    data = request.json
    api_key = request.headers.get("x-api-key")
    
    if api_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
        
    article_id = data.get("articleId")
    texto_completo = data.get("texto")
    
    if not article_id or not texto_completo:
        return jsonify({"error": "Faltan datos"}), 400

    # Lanzamos el proceso en segundo plano para no hacer esperar a Node.js
    thread = threading.Thread(target=background_audio_task, args=(article_id, texto_completo))
    thread.start()
    
    return jsonify({"message": "Generación de audio iniciada", "articleId": article_id}), 202

def run_cleanup_loop():
    import time
    # Espera 10 segundos después de arrancar el servidor antes de hacer la primera limpieza
    time.sleep(10)
    while True:
        try:
            cloudflare_r2.delete_old_files_from_r2(days_old=28)
        except Exception as e:
            logger.error(f"❌ Error en el bucle de limpieza automática de R2: {e}")
        # Esperar 86400 segundos (24 horas) para la siguiente revisión
        time.sleep(86400)

if __name__ == '__main__':
    # Lanzar el hilo de limpieza en segundo plano al arrancar
    cleanup_thread = threading.Thread(target=run_cleanup_loop, daemon=True)
    cleanup_thread.start()
    
    app.run(host='0.0.0.0', port=PORT)