import os
from flask import Flask, request, jsonify
from video_generator import process_video_task

# --- ¡NUEVO! ---
# Definimos la carpeta donde guardarás las fotos de tus reporteros
REPORTER_IMAGES_DIR = 'reporter_images'

# Asegúrate de que existan todas las carpetas necesarias
os.makedirs('temp_audio', exist_ok=True)
os.makedirs('temp_video', exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs(REPORTER_IMAGES_DIR, exist_ok=True) # Creamos la carpeta de reporteros

app = Flask(__name__)

@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    """
    Este endpoint ahora espera:
    {
        "text": "El contenido de la noticia...",
        "title": "El título para YouTube",
        "image_name": "reportero_juan.jpg" 
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Faltan datos JSON"}), 400

    # --- ¡MODIFICADO! ---
    # Ahora revisamos que los 3 campos existan
    text_content = data.get('text')
    title = data.get('title')
    image_name = data.get('image_name') # Ej: "reportera_maria.jpg"

    if not all([text_content, title, image_name]):
        return jsonify({"error": "Faltan datos 'text', 'title' o 'image_name'"}), 400

    # --- ¡NUEVA LÓGICA! ---
    # 1. Construimos la ruta completa a la imagen
    anchor_image_path = os.path.join(REPORTER_IMAGES_DIR, image_name)
    
    # 2. Verificamos si esa imagen existe en la carpeta
    if not os.path.exists(anchor_image_path):
        print(f"Error: No se encontró la imagen solicitada: {anchor_image_path}")
        return jsonify({"error": f"Imagen '{image_name}' no encontrada en el servidor del bot."}), 404
    
    # 3. Si existe, continuamos como antes
    try:
        # Pasamos la ruta de la imagen verificada a nuestra función
        youtube_id = process_video_task(text_content, title, anchor_image_path)
        
        if youtube_id:
            return jsonify({"youtubeId": youtube_id})
        else:
            return jsonify({"error": "No se pudo generar el video o subir a YouTube"}), 500

    except Exception as e:
        print(f"Error catastrófico en la generación de video: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)