import os
import threading
from flask import Flask, request, jsonify
from video_generator import process_video_task 
from dotenv import load_dotenv

load_dotenv()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
REPORTER_IMAGES_DIR = 'reporter_images'

# Asegurar carpetas
os.makedirs('temp_audio', exist_ok=True)
os.makedirs('temp_video', exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs(REPORTER_IMAGES_DIR, exist_ok=True)

app = Flask(__name__)

# --- ¡NUEVO! EL SEMÁFORO ---
# Este candado asegura que solo haya 1 video generándose a la vez.
processing_lock = threading.Lock()

@app.before_request
def check_api_key():
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        return jsonify({"error": "Acceso no autorizado"}), 403

# --- Función Envoltorio (Wrapper) ---
# Esta función ejecuta la tarea y LIBERA el candado cuando termina (éxito o error).
def task_wrapper(text, title, image_path, article_id):
    try:
        process_video_task(text, title, image_path, article_id)
    finally:
        # ¡IMPORTANTE! Liberamos el candado pase lo que pase
        print(f"🔓 [Bot] Trabajo terminado para {article_id}. Liberando candado.")
        processing_lock.release()

@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Faltan datos JSON"}), 400

    text_content = data.get('text')
    title = data.get('title')
    image_name = data.get('image_name')
    article_id = data.get('article_id')

    if not all([text_content, title, image_name, article_id]):
        return jsonify({"error": "Faltan datos obligatorios"}), 400

    anchor_image_path = os.path.join(REPORTER_IMAGES_DIR, image_name)
    if not os.path.exists(anchor_image_path):
        return jsonify({"error": f"Imagen '{image_name}' no encontrada."}), 404
    
    # --- LÓGICA DEL CANDÁDO ---
    # Intentamos adquirir el candado SIN esperar (blocking=False).
    # Si está ocupado, devuelve False inmediatamente.
    if processing_lock.acquire(blocking=False):
        print(f"🔒 [Bot] Candado adquirido para {article_id}. Iniciando...")
        
        # Iniciamos el hilo usando el 'wrapper' en lugar de la función directa
        thread = threading.Thread(
            target=task_wrapper,
            args=(text_content, title, anchor_image_path, article_id)
        )
        thread.start()

        return jsonify({"message": "¡Orden aceptada! Procesando."}), 202
    else:
        # Si el candado estaba cerrado (alguien más está trabajando)
        print(f"⛔ [Bot] RECHAZADO {article_id}: El bot está ocupado.")
        return jsonify({
            "error": "El bot está ocupado procesando otro video. Intenta más tarde."
        }), 503 # 503 = Service Unavailable (Ocupado)

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", 5001)))