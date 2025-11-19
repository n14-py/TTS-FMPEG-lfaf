import os
import time
import requests 
import subprocess # ¡NUEVO! Para llamar a Piper (tts)
from dotenv import load_dotenv
# ELIMINAMOS: from TTS.api import TTS
# ELIMINAMOS: import gc (Ya no hace falta la limpieza de memoria)

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
from google.oauth2.credentials import Credentials

load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

FRONTEND_BASE_URL = "https://noticias.lat"

AUDIO_PATH = "temp_audio/news_audio.mp3"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

# --- MODELO PIPER ---
# Este es el reemplazo ultraligero y de buena calidad para español
PIPER_MODEL = "es_ES-karlen-low" 

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secrets.json' 

print("Cargando motor TTS: Piper (Ultraligero)")

# --- Funciones Auxiliares (sin cambios) ---

def _report_status_to_api(endpoint, article_id, data={}):
    if not MAIN_API_URL or not ADMIN_API_KEY:
        return
    url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    payload = {"articleId": article_id, **data}
    try:
        requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e:
        print(f"ERROR CALLBACK: {e}")

# --- PASO 1: Generar Audio (CON PIPER) ---
def generar_audio(text):
    """Genera audio usando el motor ultraligero Piper."""
    print(f"Iniciando Paso 1: Generando audio con Piper ({PIPER_MODEL})...")
    
    start_time = time.time()
    
    # 1. Creamos el comando de Piper CLI
    command = [
        "piper",
        "--model", PIPER_MODEL,
        "--output_file", AUDIO_PATH,
        "--speaker", "default"
    ]
    
    # 2. Ejecutamos el comando y enviamos el texto a través de stdin
    try:
        process = subprocess.run(command, input=text.encode('utf-8'), capture_output=True, check=True)
        # Opcional: imprimir la salida de error de Piper para debug
        if process.stderr:
            print(f"Advertencia/Error de Piper: {process.stderr.decode('utf-8')}")
            
        if not os.path.exists(AUDIO_PATH):
             raise Exception("Piper no generó el archivo de audio. ¿El modelo fue descargado correctamente?")
             
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error al ejecutar Piper: {e.stderr.decode('utf-8')}")
    except Exception as e:
        raise Exception(f"Error al iniciar Piper: {e}")

    end_time = time.time()
    # Ya no hay que limpiar memoria, Piper es eficiente
    print(f"Audio guardado (Tardó {end_time - start_time:.2f}s). ¡RAM limpia!")
    
    return AUDIO_PATH

# --- PASO 2: Generar Video (1080p, 1 FPS) ---
# ... (El resto de las funciones son iguales, solo las pego para completar el archivo) ...

def generar_video_ia(audio_path, imagen_path):
    """
    Genera video Horizontal 1080p a 1 FPS y 1 Hilo (Máx. Estabilidad).
    """
    print("Iniciando Paso 2: Generando video HORIZONTAL (1920x1080)...")
    
    ffmpeg_command = (
        f"ffmpeg -y -loop 1 -i \"{imagen_path}\" -i \"{audio_path}\" "
        f"-threads 1 -r 1 "
        f"-c:v libx264 -preset ultrafast -tune stillimage -crf 32 "
        f"-c:a aac -b:a 64k -ac 1 "
        f"-pix_fmt yuv420p -shortest "
        f"-vf \"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1\" "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    try:
        subprocess.run(ffmpeg_command, shell=True, check=True)
        print(f"Video guardado en {FINAL_VIDEO_PATH}")
        return FINAL_VIDEO_PATH
    except Exception as e:
        print(f"Error en ffmpeg: {e}")
        return None

def subir_a_youtube(video_path, title, full_text, article_id):
    """Subida con Título ULTRA SEGURO (Máx 98 caracteres) y Público"""
    print("Iniciando Paso 3: Subiendo a YouTube...")
    
    credentials = None
    if os.path.exists('token.json'):
        credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refrescando token de acceso...")
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
    
    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        
        suffix = " // Noticias.lat"
        max_total_length = 98 
        max_title_length = max_total_length - len(suffix) 
        
        clean_title = title.strip()
        
        if len(clean_title) > max_title_length:
            clean_title = clean_title[:max_title_length - 3].strip() + "..."
            
        final_title = f"{clean_title}{suffix}"
        
        article_link = f"{FRONTEND_BASE_URL}/articulo/{article_id}"
        safe_text = full_text[:4700].strip()
        if len(full_text) > 4700:
            safe_text += "..."

        final_description = (
            f"Lee la noticia completa aquí: {article_link}\n"
            f"----------------------------------------\n"
            f"{safe_text}"
        )
        
        print(f"Título Final ({len(final_title)} chars): {final_title}")
        
        request_body = {
            'snippet': {
                'title': final_title,
                'description': final_description,
                'tags': ['noticias', 'noticiaslat', 'actualidad'],
                'categoryId': '25' 
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }

        media_file = MediaFileUpload(video_path, chunksize=-1, resumable=True)

        response_upload = youtube.videos().insert(
            part='snippet,status',
            body=request_body,
            media_body=media_file
        ).execute()
        
        print(f"Video subido con éxito. ID: {response_upload['id']}")
        return response_upload['id']

    except Exception as e:
        print(f"Error al subir a YouTube: {e}")
        raise e 

def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    try:
        # Ya no se necesita gc.collect() aquí
        
        # 1. Audio (Ahora con Piper)
        audio_file = generar_audio(text_content)
        if not audio_file: raise Exception("Falló audio")

        # 2. Video (Full HD 1080p)
        video_file = generar_video_ia(audio_file, anchor_image_path)
        if not video_file: raise Exception("Falló video")

        # 3. Subida
        youtube_id = subir_a_youtube(video_file, title, text_content, article_id)
        
        if not youtube_id: raise Exception("Falló subida")

        print(f"¡TRABAJO COMPLETO para {article_id}!")
        _report_status_to_api("video_complete", article_id, {"youtubeId": youtube_id})

    except Exception as e:
        print(f"ERROR en proceso: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
    
    finally:
        print("Limpiando archivos...")
        if os.path.exists(AUDIO_PATH): os.remove(AUDIO_PATH)
        if os.path.exists(FINAL_VIDEO_PATH): os.remove(FINAL_VIDEO_PATH)
        # Ya no se necesita gc.collect() aquí