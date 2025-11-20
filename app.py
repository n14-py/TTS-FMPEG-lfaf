import os
import threading
import requests 
import gc # Importamos Garbage Collector
from flask import Flask, request, jsonify
from video_generator import process_video_task 
from dotenv import load_dotenv

load_dotenv()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
TEMP_IMAGE_DIR = 'temp_images'

# Asegurar carpetas
os.makedirs('temp_audio', exist_ok=True)
os.makedirs('temp_video', exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

app = Flask(__name__)

# Semáforo: Solo permite 1 hilo a la vez. 
# Si llega otra petición, se rechaza hasta que termine la actual.
processing_lock = threading.Lock()

@app.before_request
def check_api_key():
    api_key = request.headers.get('x-api-key')
    if not api_key or api_key != ADMIN_API_KEY:
        return jsonify({"error": "Acceso no autorizado"}), 403

def task_wrapper(text, title, image_path, article_id):
    try:
        process_video_task(text, title, image_path, article_id)
    except Exception as e:
        print(f"Error no controlado en task_wrapper: {e}")
    finally:
        print(f"🔓 [Bot] Trabajo terminado para {article_id}. Liberando recursos.")
        
        # 1. Eliminar imagen descargada
        if os.path.exists(image_path) and "temp_images" in image_path:
            try:
                os.remove(image_path)
            except:
                pass
        
        # 2. Liberar el candado para que pueda entrar otro trabajo
        processing_lock.release()
        
        # 3. LIMPIEZA PROFUNDA DE RAM
        # Esto le dice al sistema: "Ya terminé, borra todo lo que no sirva ahora mismo"
        gc.collect() 
        print("✨ Memoria RAM purgada y lista para el siguiente trabajo.")

@app.route('/generate_video', methods=['POST'])
def handle_generate_video():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Faltan datos JSON"}), 400

    text_content = data.get('text')
    title = data.get('title')
    image_url = data.get('image_url') 
    article_id = data.get('article_id')

    if not all([text_content, title, image_url, article_id]):
        return jsonify({"error": "Faltan datos obligatorios"}), 400

    # Intentamos adquirir el candado SIN bloquear.
    # Si está ocupado, devuelve False inmediatamente.
    if processing_lock.acquire(blocking=False):
        print(f"🔒 [Bot] Candado adquirido para {article_id}. Iniciando descarga...")
        
        # Descargamos la imagen DENTRO del bloqueo para no gastar RAM si no vamos a procesar
        downloaded_image_path = ""
        try:
            response = requests.get(image_url, timeout=15)
            if response.status_code == 200:
                downloaded_image_path = os.path.join(TEMP_IMAGE_DIR, f"{article_id}.jpg")
                with open(downloaded_image_path, 'wb') as f:
                    f.write(response.content)
            else:
                processing_lock.release()
                return jsonify({"error": "No se pudo descargar la imagen"}), 400
        except Exception as e:
            processing_lock.release()
            return jsonify({"error": f"Error descargando imagen: {str(e)}"}), 500

        # Lanzamos el hilo de trabajo
        thread = threading.Thread(
            target=task_wrapper,
            args=(text_content, title, downloaded_image_path, article_id)
        )
        thread.start()

        return jsonify({"message": "¡Orden aceptada! Procesando video secuencialmente."}), 202
    else:
        # Si el bot está ocupado, rechazamos para no explotar la RAM
        print(f"⛔ [Bot] RECHAZADO {article_id}: Memoria/Bot ocupado.")
        # Forzamos una limpieza por si acaso quedó basura de un proceso anterior zombie
        gc.collect() 
        return jsonify({
            "error": "El bot está ocupado procesando un video. Espera a que termine."
        }), 503

if __name__ == '__main__':
    # Usamos debug=False en producción para ahorrar overhead
    app.run(debug=False, port=int(os.getenv("PORT", 5001)))