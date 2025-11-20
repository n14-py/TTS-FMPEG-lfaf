import os
import time
import requests 
import subprocess 
import gc # IMPORTANTE: Traemos de vuelta el recolector de basura
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
from google.oauth2.credentials import Credentials

load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

FRONTEND_BASE_URL = "https://noticias.lat" # Sin slash al final para evitar dobles

AUDIO_PATH = "temp_audio/news_audio.mp3"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

# --- MODELO PIPER ---
PIPER_MODEL_NAME = "es_ES-carlfm-x_low"
PIPER_MODEL_DIR = "/app/models/piper" 

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secrets.json' 

print("Cargando motor TTS: Piper (Ultraligero)")

# --- Funciones Auxiliares ---

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

# --- PASO 1: Generar Audio ---
def generar_audio(text):
    print(f"Iniciando Paso 1: Generando audio con Piper...")
    start_time = time.time()
    
    command = [
        "piper",
        "--model", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx"),
        "--config", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx.json"),
        "--output_file", AUDIO_PATH
    ]
    
    try:
        # Ejecutamos Piper. Al ser subprocess, la RAM se libera al terminar el proceso externo.
        subprocess.run(command, input=text.encode('utf-8'), capture_output=True, check=True)
        
        if not os.path.exists(AUDIO_PATH):
             raise Exception("Piper no generó el archivo de audio.")
             
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error al ejecutar Piper: {e.stderr.decode('utf-8')}")
    except Exception as e:
        raise Exception(f"Error al iniciar Piper: {e}")

    end_time = time.time()
    print(f"Audio guardado ({end_time - start_time:.2f}s).")
    return AUDIO_PATH

# --- PASO 2: Generar Video ---
def generar_video_ia(audio_path, imagen_path):
    print("Iniciando Paso 2: Generando video HORIZONTAL (1080p)...")
    
    # Optimizaciones para memoria:
    # -threads 1: Usa menos CPU/RAM concurrente
    # -preset ultrafast: Codifica rápido para liberar RAM antes
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

# --- PASO 3: Subir a YouTube ---
def subir_a_youtube(video_path, title, full_text, article_id):
    print("Iniciando Paso 3: Subiendo a YouTube...")
    
    credentials = None
    if os.path.exists('token.json'):
        credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refrescando token...")
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
    
    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        
        # --- TÍTULO SEGURO (Máx 100 chars) ---
        suffix = " // Noticias.lat"
        max_title_length = 98 - len(suffix) 
        clean_title = title.strip()
        if len(clean_title) > max_title_length:
            clean_title = clean_title[:max_title_length - 3].strip() + "..."
        final_title = f"{clean_title}{suffix}"
        
        # --- DESCRIPCIÓN OPTIMIZADA ---
        # Estructura pedida:
        # 1. Link noticia
        # 2. Texto noticia
        # 3. Link Home
        
        article_link = f"{FRONTEND_BASE_URL}/articulo/{article_id}"
        home_link = "https://www.noticias.lat/"
        
        intro_line = f"Lee la noticia completa aquí: {article_link}"
        outro_line = f"Visita nuestra web: {home_link}"
        
        # YouTube permite 5000 caracteres. Calculamos cuánto espacio queda para el texto.
        # Reservamos unos 100 caracteres de buffer por seguridad.
        reserved_chars = len(intro_line) + len(outro_line) + 100 
        max_text_chars = 5000 - reserved_chars
        
        safe_text = full_text.strip()
        if len(safe_text) > max_text_chars:
            safe_text = safe_text[:max_text_chars].strip() + "..."

        final_description = (
            f"{intro_line}\n\n"
            f"{safe_text}\n\n"
            f"{outro_line}"
        )
        
        print(f"Longitud Descripción: {len(final_description)} caracteres.")
        
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
        
        video_id = response_upload.get('id')
        print(f"Video subido con éxito. ID: {video_id}")
        return video_id

    except Exception as e:
        print(f"Error al subir a YouTube: {e}")
        raise e 

def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    try:
        # 1. Audio
        audio_file = generar_audio(text_content)
        if not audio_file: raise Exception("Falló audio")
        
        # Limpieza post-audio
        gc.collect()

        # 2. Video
        video_file = generar_video_ia(audio_file, anchor_image_path)
        if not video_file: raise Exception("Falló video")
        
        # Limpieza post-video (importante antes de subir para tener RAM libre para requests)
        gc.collect()

        # 3. Subida
        youtube_id = subir_a_youtube(video_file, title, text_content, article_id)
        if not youtube_id: raise Exception("Falló subida")

        print(f"✅ FINALIZADO CON ÉXITO: {article_id}")
        _report_status_to_api("video_complete", article_id, {"youtubeId": youtube_id})

    except Exception as e:
        print(f"❌ FALLO: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
    
    finally:
        print("🧹 LIMPIEZA FINAL DE ARCHIVOS Y RAM...")
        # Eliminar archivos
        if os.path.exists(AUDIO_PATH): 
            try: os.remove(AUDIO_PATH)
            except: pass
        if os.path.exists(FINAL_VIDEO_PATH): 
            try: os.remove(FINAL_VIDEO_PATH)
            except: pass
        
        # Forzar limpieza de memoria de Python
        del text_content
        del title
        gc.collect()