import os
import threading # ¡NUEVO! Para tareas en segundo plano
from flask import Flask, request, jsonify
from video_generator import process_video_task # Importamos la función principal

# --- ¡NUEVO! Cargamos la clave secreta desde el .env ---
from dotenv import load_dotenv
load_dotenv()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# --- ¡NUEVO! ---
# Definimos la carpeta donde guardarás las fotos de tus reporteros
REPORTER_IMAGES_DIR = 'reporter_images'

# Asegúrate de que existan todas las carpetas necesarias
os.makedirs('temp_audio', exist_ok=True)
os.makedirs('temp_video', exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs(REPORTER_IMAGES_DIR, exist_ok=True) # Creamos la carpeta de reporteros

app = Flask(__name__)

# --- ¡NUEVO! Middleware de seguridad ---
@app.before_request
def check_api_key():
    # Verificamos que la clave 'x-api-key' enviada por la API sea correcta
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        print(f"ALERTA: Intento de acceso denegado. Clave: {api_key}")
        return jsonify({"error": "Acceso no autorizado"}), 403

# --- ¡Ruta MODIFICADA! ---
@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    """
    Este endpoint ahora espera:
    {
        "text": "El contenido de la noticia...",
        "title": "El título para YouTube",
        "image_name": "reportero_juan.jpg",
        "article_id": "60a...f3b"
    }
    Y responde INMEDIATAMENTE.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Faltan datos JSON"}), 400

    # --- ¡MODIFICADO! ---
    # Ahora revisamos que los 4 campos existan
    text_content = data.get('text')
    title = data.get('title')
    image_name = data.get('image_name') # Ej: "reportera_maria.jpg"
    article_id = data.get('article_id') # ¡El ID para el callback!

    if not all([text_content, title, image_name, article_id]):
        return jsonify({"error": "Faltan datos 'text', 'title', 'image_name' o 'article_id'"}), 400

    # --- ¡NUEVA LÓGICA! ---
    # 1. Construimos la ruta completa a la imagen
    anchor_image_path = os.path.join(REPORTER_IMAGES_DIR, image_name)
    
    # 2. Verificamos si esa imagen existe en la carpeta
    if not os.path.exists(anchor_image_path):
        print(f"Error: No se encontró la imagen solicitada: {anchor_image_path}")
        return jsonify({"error": f"Imagen '{image_name}' no encontrada en el servidor del bot."}), 404
    
    # 3. ¡LA MAGIA! Iniciar el trabajo en segundo plano
    try:
        print(f"¡Orden recibida para articleId: {article_id}! Iniciando trabajo en 2do plano...")
        
        # Creamos un hilo (thread) que ejecutará la tarea lenta
        thread = threading.Thread(
            target=process_video_task,
            args=(text_content, title, anchor_image_path, article_id)
        )
        thread.start() # Inicia el hilo

        # 4. Respondemos INMEDIATAMENTE a la API
        return jsonify({"message": "¡Orden recibida! Procesando en segundo plano."}), 202
        
    except Exception as e:
        print(f"Error catastrófico al iniciar el hilo: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Esto no se usa en Gunicorn, pero es útil para pruebas locales
    app.run(debug=True, port=int(os.getenv("PORT", 5001)))