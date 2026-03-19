import os
import threading
import gc
import logging
import requests
import json
from flask import Flask, request, jsonify

# Importamos la función maestra y el chequeo de duplicados
from video_generator import process_video_task, is_already_processed

# --- CONFIGURACIÓN DE LOGS ---
# Formato detallado para CloudWatch / Docker logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
# URL de tu API principal (Backend en Render) para los Webhooks
MAIN_API_URL = os.getenv("MAIN_API_URL", "https://lfaftechapi.onrender.com")

app = Flask(__name__)

# --- SEMÁFORO DE PROCESAMIENTO ---
# Evita que el t3.micro explote procesando 2 videos a la vez.
processing_lock = threading.Lock()

def _check_auth():
    """Verifica que la petición venga de tu API Admin."""
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        return False
    return True

# --- RUTA 1: HEALTHCHECK (AWS lo usa para saber si estás vivo) ---
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "server": "TTS-Worker-V3-Promo"}), 200

# --- RUTA 2: GENERACIÓN DE VIDEO ---
@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    # 1. Seguridad
    if not _check_auth():
        logger.warning(f"⛔ Intento de acceso no autorizado desde {request.remote_addr}")
        return jsonify({"error": "No autorizado"}), 403

    # 2. Validación de Datos
    data = request.get_json()
    if not data:
        return jsonify({"error": "Sin cuerpo JSON"}), 400

    # Extraemos datos
    article_id = data.get('article_id')
    image_url = data.get('image_url')
    text_content = data.get('text')
    title = data.get('title')
    
    # IMPORTANTE: Intentamos obtener la URL de varias formas por si cambia el nombre en la API
    article_url = data.get('url') or data.get('article_url') or data.get('link') or ""

    # Validamos lo mínimo indispensable
    if not all([article_id, image_url, text_content, title]):
        missing = [k for k in ['article_id', 'image_url', 'text', 'title'] if not data.get(k)]
        return jsonify({"error": f"Faltan datos: {', '.join(missing)}"}), 400

    # 3. FILTRO ANTI-BUCLE (Si ya existe, respondemos 200 OK para que la API pare)
    if is_already_processed(article_id):
        logger.info(f"⏭️ Tarea {article_id} ya existe en historial. Respondiendo OK.")
        return jsonify({
            "message": "El video ya fue generado anteriormente.",
            "status": "completed",
            "article_id": article_id
        }), 200

    # 4. INTENTO DE PROCESAMIENTO (Lock)
    if processing_lock.acquire(blocking=False):
        try:
            logger.info(f"🔒 [Lock Adquirido] Iniciando tarea para ID: {article_id}")
            
            # Definimos la tarea en segundo plano
            def background_task():
                try:
                    # --- LLAMADA AL GENERADOR ---
                    # Pasamos la URL explícita aquí
                    video_id = process_video_task(text_content, title, image_url, article_id, article_url)
                    
                    # --- MANEJO DE RESULTADOS ---
                    
                    # CASO A: ÉXITO (Tenemos ID de YouTube)
                    if video_id and video_id != "ALREADY_PROCESSED":
                        logger.info(f"📞 ÉXITO. Notificando a API Principal: {video_id}")
                        try:
                            # Webhook de éxito
                            webhook_url = f"{MAIN_API_URL}/api/articles/video_complete"
                            payload = {
                                "articleId": article_id,
                                "youtubeId": video_id
                            }
                            headers = {"x-api-key": ADMIN_API_KEY}
                            
                            r = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
                            if r.status_code == 200:
                                logger.info("✅ API Principal confirmó recepción.")
                            else:
                                logger.warning(f"⚠️ API respondió {r.status_code}: {r.text}")
                                
                        except Exception as e:
                            logger.error(f"❌ Error de conexión al notificar éxito: {e}")

                    # CASO B: FALLO (Timeout, Error de Render, etc.)
                    elif video_id is None:
                        logger.warning(f"⚠️ FALLO CRÍTICO en tarea {article_id}. Notificando error para cancelar reintentos.")
                        try:
                            # Webhook de fallo (ROMPE EL BUCLE INFINITO)
                            webhook_url = f"{MAIN_API_URL}/api/articles/video_failed"
                            payload = {
                                "articleId": article_id, 
                                "error": "Worker Error: Render Failed or Timeout"
                            }
                            headers = {"x-api-key": ADMIN_API_KEY}
                            requests.post(webhook_url, json=payload, headers=headers, timeout=10)
                            logger.info("✅ API avisada del fallo.")
                        except Exception as e:
                            logger.error(f"❌ Error al notificar fallo: {e}")

                except Exception as e:
                    logger.error(f"❌ Error fatal no capturado en hilo: {e}")
                finally:
                    # IMPORTANTE: Liberar el Lock siempre
                    processing_lock.release()
                    logger.info(f"🔓 [Lock Liberado] Tarea finalizada.")
                    # Limpieza agresiva de memoria RAM
                    gc.collect()

            # Lanzamos el hilo
            thread = threading.Thread(target=background_task)
            thread.daemon = True 
            thread.start()

            # Respondemos RÁPIDO que aceptamos el trabajo
            return jsonify({
                "message": "Tarea aceptada. Procesando en background.",
                "status": "processing",
                "article_id": article_id
            }), 202

        except Exception as e:
            processing_lock.release()
            logger.error(f"❌ Error al lanzar hilo: {e}")
            return jsonify({"error": "Error interno del servidor"}), 500
    else:
        # 5. Servidor Ocupado
        logger.warning(f"⚠️ Servidor ocupado. Rechazando tarea ID: {article_id}")
        return jsonify({
            "error": "El servidor está procesando otro video. Intente en 5 minutos."
        }), 503

@app.route('/', methods=['GET'])
def index():
    return "<h1>Noticias.lat Video Worker V3</h1><p>Sistema Operativo con Promo y Fix de URL.</p>"

if __name__ == '__main__':
    port = int(os.getenv("PORT", 3001))
    app.run(host='0.0.0.0', port=port)