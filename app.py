import os
import threading
import requests # Necesario para descargar la imagen
from flask import Flask, request, jsonify
from video_generator import process_video_task 
from dotenv import load_dotenv

load_dotenv()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
# Carpeta para guardar la imagen descargada temporalmente
TEMP_IMAGE_DIR = 'temp_images'

# Asegurar carpetas
os.makedirs('temp_audio', exist_ok=True)
os.makedirs('temp_video', exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

app = Flask(__name__)

# Semáforo para evitar crash por memoria
processing_lock = threading.Lock()

@app.before_request
def check_api_key():
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        return jsonify({"error": "Acceso no autorizado"}), 403

def task_wrapper(text, title, image_path, article_id):
    try:
        process_video_task(text, title, image_path, article_id)
    finally:
        print(f"🔓 [Bot] Trabajo terminado para {article_id}. Liberando candado.")
        processing_lock.release()
        # Opcional: Borrar la imagen descargada para ahorrar espacio
        if os.path.exists(image_path) and "temp_images" in image_path:
            try:
                os.remove(image_path)
            except:
                pass

@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Faltan datos JSON"}), 400

    text_content = data.get('text')
    title = data.get('title')
    image_url = data.get('image_url') # Ahora esperamos una URL
    article_id = data.get('article_id')

    if not all([text_content, title, image_url, article_id]):
        return jsonify({"error": "Faltan datos obligatorios (text, title, image_url, article_id)"}), 400

    # --- NUEVO: DESCARGAR LA IMAGEN ---
    try:
        print(f"Descargando imagen desde: {image_url}")
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            # Guardamos la imagen con el nombre del article_id para evitar conflictos
            # Asumimos jpg por defecto, ffmpeg es inteligente y lo detectará igual
            downloaded_image_path = os.path.join(TEMP_IMAGE_DIR, f"{article_id}.jpg")
            with open(downloaded_image_path, 'wb') as f:
                f.write(response.content)
            print(f"Imagen descargada en: {downloaded_image_path}")
        else:
            return jsonify({"error": "No se pudo descargar la imagen de la noticia"}), 400
    except Exception as e:
        print(f"Error descargando imagen: {e}")
        return jsonify({"error": f"Error descargando imagen: {str(e)}"}), 500
    
    # --- LÓGICA DEL SEMÁFORO ---
    if processing_lock.acquire(blocking=False):
        print(f"🔒 [Bot] Candado adquirido para {article_id}. Iniciando...")
        
        thread = threading.Thread(
            target=task_wrapper,
            args=(text_content, title, downloaded_image_path, article_id)
        )
        thread.start()

        return jsonify({"message": "¡Orden aceptada! Procesando video horizontal."}), 202
    else:
        print(f"⛔ [Bot] RECHAZADO {article_id}: El bot está ocupado.")
        return jsonify({
            "error": "El bot está ocupado procesando otro video. Intenta más tarde."
        }), 503

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", 5001)))