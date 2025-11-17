import os
import time
from gtts import gTTS
# --- Importaciones de YouTube (requieren configuración) ---
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- CONSTANTES ---
AUDIO_PATH = "temp_audio/news_audio.mp3"
IA_VIDEO_PATH = "temp_video/ia_video.mp4" # Video de la IA
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

# --- Configuración de YouTube API ---
# ¡AQUÍ ESTABA EL ERROR! Faltaba una comilla (")
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secrets.json' 

def generar_audio(text):
    """Paso 1: Convierte texto a voz usando Google Text-to-Speech (gTTS)."""
    print("Iniciando Paso 1: Generando audio (TTS)...")
    try:
        tts = gTTS(text=text, lang='es')
        tts.save(AUDIO_PATH)
        print(f"Audio guardado en {AUDIO_PATH}")
        return AUDIO_PATH
    except Exception as e:
        print(f"Error en gTTS: {e}")
        return None

def generar_video_ia(audio_path, imagen_path):
    """
    Paso 2: Genera el video con IA (Lip-Sync).
    Usamos la simulación de ffmpeg por ahora.
    """
    print("Iniciando Paso 2: Generando video (Simulación FFmpeg)...")
    
    # --- SIMULACIÓN (mientras no tengamos la IA) ---
    # Vamos a usar ffmpeg para poner la imagen sobre el audio (sin animación).
    print("¡ADVERTENCIA! Usando simulación de ffmpeg. ¡IA no configurada!")
    
    # -y (sobrescribe el video si ya existe)
    # -loop 1 (repite la imagen)
    # -i '{imagen_path}' (input 1: la imagen)
    # -i '{audio_path}' (input 2: el audio)
    # -c:v libx264 (codec de video)
    # -tune stillimage (optimiza para imagen quieta)
    # -c:a aac -b:a 192k (codec de audio)
    # -pix_fmt yuv420p (formato de pixel para compatibilidad)
    # -shortest (hace que el video dure lo mismo que el audio)
    # -vf "scale=1080:1920,setsar=1" (escala el video a 1080x1920 vertical)
    ffmpeg_command = f"ffmpeg -y -loop 1 -i \"{imagen_path}\" -i \"{audio_path}\" -c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p -shortest -vf \"scale=1080:1920,setsar=1\" \"{FINAL_VIDEO_PATH}\""
    
    try:
        os.system(ffmpeg_command)
        print(f"Video (simulado) guardado en {FINAL_VIDEO_PATH}")
        return FINAL_VIDEO_PATH
    except Exception as e:
        print(f"Error en ffmpeg (simulación): {e}")
        return None

def subir_a_youtube(video_path, title, description):
    """Paso 3: Sube el video a YouTube y devuelve el ID."""
    print("Iniciando Paso 3: Subiendo a YouTube...")
    
    credentials = None
    if os.path.exists('token.json'):
        credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
    
    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        
        request_body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': ['noticias', 'noticiaslat', 'ia'],
                'categoryId': '25' # 25 es la categoría de "Noticias y Política"
            },
            'status': {
                'privacyStatus': 'unlisted', # 'private', 'public' o 'unlisted'
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

def process_video_task(text_content, title, anchor_image_path):
    """
    Función principal que orquesta todo el proceso.
    """
    # 1. Generar Audio
    audio_file = generar_audio(text_content)
    if not audio_file:
        raise Exception("Falló la generación de audio")

    # 2. Generar Video (Con la IA o la simulación)
    video_file = generar_video_ia(audio_file, anchor_image_path)
    if not video_file:
        raise Exception("Falló la generación de video IA")

    # 3. Subir a YouTube
    description = f"Video generado por IA. Contenido: {text_content[:100]}..."
    youtube_id = subir_a_youtube(video_file, title, description)
    if not youtube_id:
        raise Exception("Falló la subida a YouTube")

    # (Opcional) Limpiar archivos temporales
    # os.remove(audio_file)
    # os.remove(video_file)

    return youtube_id