import os
import time
import requests 
from dotenv import load_dotenv
from TTS.api import TTS
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
# --- ¡ESTA ES LA LÍNEA QUE FALTABA! ---
from google.auth.transport.requests import Request 

load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

AUDIO_PATH = "temp_audio/news_audio.mp3"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secrets.json' 

print("Cargando modelo de TTS (Coqui/VITS)...")
try:
    tts_model = TTS(model_name="tts_models/es/css10/vits", progress_bar=False, gpu=False)
    print("¡Modelo de TTS cargado con éxito!")
except Exception as e:
    print(f"ERROR FATAL: No se pudo cargar el modelo de TTS. {e}")
    tts_model = None

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

def generar_audio(text):
    if not tts_model:
        raise Exception("Modelo TTS no cargado.")
    print("Iniciando Paso 1: Generando audio...")
    # Quitamos language='es'
    tts_model.tts_to_file(text=text, file_path=AUDIO_PATH)
    return AUDIO_PATH

def generar_video_ia(audio_path, imagen_path):
    """
    Genera un VIDEO HORIZONTAL (Landscape) para YouTube.
    Resolución: 1280x720 (HD)
    FPS: 1 (Estático optimizado)
    """
    print("Iniciando Paso 2: Generando video HORIZONTAL (1280x720)...")
    
    ffmpeg_command = (
        f"ffmpeg -y -loop 1 -i \"{imagen_path}\" -i \"{audio_path}\" "
        f"-threads 1 -r 1 "
        f"-c:v libx264 -preset ultrafast -tune stillimage -crf 32 "
        f"-c:a aac -b:a 64k -ac 1 "
        f"-pix_fmt yuv420p -shortest "
        f"-vf \"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1\" "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    try:
        os.system(ffmpeg_command)
        print(f"Video guardado en {FINAL_VIDEO_PATH}")
        return FINAL_VIDEO_PATH
    except Exception as e:
        print(f"Error en ffmpeg: {e}")
        return None

def subir_a_youtube(video_path, title, full_text):
    """Subida con Título y Descripción personalizados"""
    print("Iniciando Paso 3: Subiendo a YouTube...")
    
    credentials = None
    if os.path.exists('token.json'):
        credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refrescando token de acceso...")
            credentials.refresh(Request()) # <--- Aquí daba el error antes
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
    
    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        
        # Título y Descripción
        final_title = f"{title} // Noticias.lat"
        safe_text = full_text[:4800] + "..." if len(full_text) > 4800 else full_text
        final_description = f"Más en: www.noticias.lat\n\n{safe_text}"

        print(f"Título: {final_title}")
        
        request_body = {
            'snippet': {
                'title': final_title,
                'description': final_description,
                'tags': ['noticias', 'noticiaslat', 'actualidad'],
                'categoryId': '25' 
            },
            'status': {
                'privacyStatus': 'public', # Video Público
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
        return None

def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    try:
        # 1. Audio
        audio_file = generar_audio(text_content)
        if not audio_file: raise Exception("Falló audio")

        # 2. Video
        video_file = generar_video_ia(audio_file, anchor_image_path)
        if not video_file: raise Exception("Falló video")

        # 3. YouTube
        youtube_id = subir_a_youtube(video_file, title, text_content)
        
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