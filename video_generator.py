import os
import time
import requests # Para llamar de vuelta a la API
from dotenv import load_dotenv # Para leer el .env

# --- Importamos la librería de Coqui TTS ---
from TTS.api import TTS

# --- Importaciones de YouTube ---
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- Cargar variables de entorno ---
load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# --- CONSTANTES ---
AUDIO_PATH = "temp_audio/news_audio.mp3"
IA_VIDEO_PATH = "temp_video/ia_video.mp4"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

# --- Configuración de YouTube API ---
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secrets.json' 

# --- Cargar el modelo de voz UNA SOLA VEZ (Global) ---
print("Cargando modelo de TTS (Coqui/VITS)...")
try:
    # Modelo: tts_models/es/css10/vits
    tts_model = TTS(model_name="tts_models/es/css10/vits", progress_bar=False, gpu=False)
    print("¡Modelo de TTS cargado con éxito!")
except Exception as e:
    print(f"ERROR FATAL: No se pudo cargar el modelo de TTS. {e}")
    tts_model = None

# --- FUNCIÓN DE "LLAMADA DE VUELTA" (CALLBACK) ---
def _report_status_to_api(endpoint, article_id, data={}):
    """Función interna para llamar de vuelta a la API principal."""
    if not MAIN_API_URL or not ADMIN_API_KEY:
        print("ERROR DE CALLBACK: MAIN_API_URL o ADMIN_API_KEY no están en .env")
        return

    # Construimos la URL de la API
    url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    # Enviamos articleId + los datos extra (youtubeId o error)
    payload = {"articleId": article_id, **data}
    
    try:
        print(f"Haciendo callback a API: {url} para articleId: {article_id}")
        requests.post(url, json=payload, headers=headers, timeout=15)
        print("Callback enviado con éxito.")
    except Exception as e:
        print(f"ERROR FATAL DE CALLBACK: No se pudo reportar a la API. {e}")


# --- PASO 1: Generar Audio ---
def generar_audio(text):
    """Paso 1: Convierte texto a voz usando Coqui TTS (Modelo VITS)."""
    if not tts_model:
        raise Exception("El modelo TTS no está cargado. No se puede generar audio.")
        
    print("Iniciando Paso 1: Generando audio (Coqui TTS)...")
    
    start_time = time.time()
    
    # Usamos el modelo cargado globalmente
    # IMPORTANTE: Sin language='es' porque el modelo es monolingüe
    tts_model.tts_to_file(
        text=text,
        file_path=AUDIO_PATH
    )
    
    end_time = time.time()
    print(f"Audio guardado en {AUDIO_PATH} (Tardó {end_time - start_time:.2f} segundos)")
    return AUDIO_PATH

# --- PASO 2: Generar Video (SÚPER OPTIMIZADO) ---
def generar_video_ia(audio_path, imagen_path):
    """
    Paso 2: Genera el video (MODO SÚPER SEGURO).
    - 1 Hilo: Imposible que sature la RAM.
    - 1 FPS: Mínimo trabajo posible para el procesador.
    - 720p: Resolución HD pero ligera.
    """
    print("Iniciando Paso 2: Generando video (Modo 1 Hilo / 1 FPS)...")
    
    # EXPLICACIÓN DE LA OPTIMIZACIÓN:
    # -threads 1: Seguridad máxima de memoria.
    # -r 1: Solo 1 cuadro por segundo. ¡Video de 1 min = solo 60 cuadros!
    # -preset ultrafast: Lo más rápido posible.
    # scale=720:1280: 720p Vertical (HD Ligero).
    # -crf 32: Compresión alta para archivo liviano.
    
    ffmpeg_command = (
        f"ffmpeg -y -loop 1 -i \"{imagen_path}\" -i \"{audio_path}\" "
        f"-threads 1 "
        f"-r 1 "
        f"-c:v libx264 -preset ultrafast -tune stillimage -crf 32 "
        f"-c:a aac -b:a 64k -ac 1 "
        f"-pix_fmt yuv420p -shortest "
        f"-vf \"scale=720:1280,setsar=1\" "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    try:
        os.system(ffmpeg_command)
        print(f"Video guardado en {FINAL_VIDEO_PATH}")
        return FINAL_VIDEO_PATH
    except Exception as e:
        print(f"Error en ffmpeg: {e}")
        return None

# --- PASO 3: Subir a YouTube ---
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
                'categoryId': '25' # Noticias y Política
            },
            'status': {
                'privacyStatus': 'unlisted', # 'unlisted' = Oculto
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

# --- FUNCIÓN PRINCIPAL (WORKER) ---
def process_video_task(text_content, title, anchor_image_path, article_id):
    """
    Orquesta todo el proceso EN SEGUNDO PLANO.
    Reporta éxito o fallo a la API principal.
    """
    youtube_id = None
    try:
        # 1. Generar Audio
        audio_file = generar_audio(text_content)
        if not audio_file:
            raise Exception("Falló la generación de audio con Coqui TTS")

        # 2. Generar Video
        video_file = generar_video_ia(audio_file, anchor_image_path)
        if not video_file:
            raise Exception("Falló la generación de video con FFmpeg")

        # 3. Subir a YouTube
        # Descripción cortada para no exceder límites si fuera necesario
        description = f"Video generado por IA. Contenido: {text_content[:300]}..."
        youtube_id = subir_a_youtube(video_file, title, description)
        
        if not youtube_id:
            raise Exception("Falló la subida a YouTube")

        # 4. ¡ÉXITO! Reportar a la API
        print(f"¡TRABAJO COMPLETO para {article_id}! Reportando a la API...")
        _report_status_to_api(
            endpoint="video_complete",
            article_id=article_id,
            data={"youtubeId": youtube_id}
        )

    except Exception as e:
        print(f"ERROR en 'process_video_task' para {article_id}: {e}")
        # 5. ¡FALLO! Reportar a la API
        _report_status_to_api(
            endpoint="video_failed",
            article_id=article_id,
            data={"error": str(e)}
        )
    
    finally:
        # 6. Limpiar archivos temporales
        print(f"Limpiando archivos temporales para {article_id}...")
        try:
            if os.path.exists(AUDIO_PATH): os.remove(AUDIO_PATH)
            if os.path.exists(FINAL_VIDEO_PATH): os.remove(FINAL_VIDEO_PATH)
            print("Limpieza completa.")
        except Exception as e:
            print(f"Error limpiando archivos temporales: {e}")