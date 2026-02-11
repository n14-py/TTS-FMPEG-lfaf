import os
import threading
import gc
import sys
import logging
from flask import Flask, request, jsonify

# Importamos la función robusta del archivo que acabamos de crear
from video_generator import process_video_task

# --- CONFIGURACIÓN DE LOGS (Para CloudWatch en AWS) ---
# En AWS, todo lo que imprimas en consola se guarda en los logs.
# Configuramos para que se vea claro.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables (aunque video_generator ya las carga, aquí validamos el puerto)
from dotenv import load_dotenv
load_dotenv()

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

app = Flask(__name__)

# --- SEMÁFORO DE PROCESAMIENTO (CRÍTICO PARA T3.MICRO) ---
# Un t3.micro solo tiene 2 vCPU. Si intentas renderizar 2 videos a la vez,
# el servidor se congelará. Este Lock asegura que sea 1 a la vez.
processing_lock = threading.Lock()

def _check_auth():
    """Verifica la API Key en los headers."""
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        return False
    return True

# --- RUTA 1: HEALTHCHECK (OBLIGATORIO PARA AWS) ---
@app.route('/health', methods=['GET'])
def health_check():
    """
    AWS llama a esto cada 30 segundos.
    Si no responde 200, AWS mata el contenedor y crea uno nuevo.
    """
    return jsonify({"status": "healthy", "server": "TTS-Worker-V2"}), 200

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

    article_id = data.get('article_id')
    image_url = data.get('image_url')
    text_content = data.get('text')
    title = data.get('title')

    # Validamos que llegue TODO lo necesario
    if not all([article_id, image_url, text_content, title]):
        missing = [k for k in ['article_id', 'image_url', 'text', 'title'] if not data.get(k)]
        return jsonify({"error": f"Faltan datos: {', '.join(missing)}"}), 400

    # 3. Control de Concurrencia (El Portero)
    # acquire(blocking=False) intenta tomar el turno. Si está ocupado, devuelve False inmediatamente.
    if processing_lock.acquire(blocking=False):
        try:
            logger.info(f"🔒 [Lock Adquirido] Iniciando tarea para ID: {article_id}")
            
            # Definimos la tarea que correrá en background
            def background_task():
                try:
                    # Llamamos a la función maestra en video_generator.py
                    process_video_task(text_content, title, image_url, article_id)
                except Exception as e:
                    logger.error(f"❌ Error no capturado en hilo: {e}")
                finally:
                    # IMPORTANTE: Liberar el Lock pase lo que pase
                    processing_lock.release()
                    logger.info(f"🔓 [Lock Liberado] Tarea {article_id} finalizada.")
                    # Limpieza forzada de memoria RAM
                    gc.collect()

            # Lanzamos el hilo
            thread = threading.Thread(target=background_task)
            thread.daemon = True # Si el servidor se apaga, el hilo muere (seguridad)
            thread.start()

            # Respondemos RÁPIDO al cliente (Backend Principal)
            return jsonify({
                "message": "Tarea aceptada. El video se está procesando en segundo plano.",
                "status": "processing",
                "article_id": article_id
            }), 202

        except Exception as e:
            # Si algo falla al intentar lanzar el hilo, liberamos el lock
            processing_lock.release()
            logger.error(f"❌ Error al lanzar hilo: {e}")
            return jsonify({"error": "Error interno del servidor al iniciar tarea"}), 500
    else:
        # 4. Manejo de Saturación
        logger.warning(f"⚠️ Servidor ocupado. Rechazando tarea ID: {article_id}")
        return jsonify({
            "error": "El servidor está procesando otro video actualmente. Intente de nuevo en 2 minutos."
        }), 503

@app.route('/', methods=['GET'])
def index():
    return "<h1>Noticias.lat Video Worker</h1><p>Sistema Operativo. Use POST /generate_video</p>"

if __name__ == '__main__':
    # En producción (Docker), gunicorn controla esto, pero por si acaso:
    port = int(os.getenv("PORT", 3001))
    app.run(host='0.0.0.0', port=port)