import os
import time
import random
import logging
import json
import asyncio
import re
import subprocess
import uuid
from datetime import datetime
import requests

# --- LIBRERÍAS DE YOUTUBE ---
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# --- LIBRERÍA DE VOZ ---
import edge_tts

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directorios
TEMP_AUDIO = "temp_audio"
TEMP_VIDEO = "temp_video"
TEMP_IMG = "temp_processing"
OUTPUT_DIR = "output"
ASSETS_DIR = "assets_video"

# Archivo del Presentador (DEBE ESTAR EN assets_video/)
PRESENTER_FILENAME = "presenter.mp4"

# Color de la pantalla verde (Tu color exacto)
CHROMA_COLOR = "0x00bf63"

# Scopes de YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Asegurar directorios
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR]:
    os.makedirs(d, exist_ok=True)

# ==========================================
# 1. UTILIDADES Y DESCARGAS
# ==========================================

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def sanitize_text_for_ffmpeg(text):
    """Limpia texto para evitar errores en FFmpeg (comillas, emojis)."""
    text = re.sub(r'[^\w\s\.\,\!\?\-]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")
    # Cortar si es muy largo para el título
    if len(text) > 50:
        text = text[:47] + "..."
    return text

def download_image_robust(url, save_path):
    """Descarga 'Militar' usando Python y CURL como respaldo."""
    # Intento 1: Python
    try:
        response = requests.get(url, timeout=15, verify=False)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        logger.warning(f"⚠️ Python falló descargando imagen: {e}")

    # Intento 2: CURL (Linux System)
    try:
        cmd = [
            "curl", "-L", "-k",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "-o", save_path, url
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True
    except Exception as e:
        logger.error(f"❌ CURL falló también: {e}")
    
    return False

# ==========================================
# 2. GENERACIÓN DE AUDIO (EDGE-TTS)
# ==========================================

async def generate_audio_edge(text, output_file):
    """Genera audio realista con Edge-TTS."""
    # Voces: 'es-MX-DaliaNeural', 'es-AR-TomasNeural', 'es-ES-AlvaroNeural'
    voice = 'es-MX-DaliaNeural' 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# ==========================================
# 3. RENDERIZADO DE VIDEO (FFMPEG COMPLEJO)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Crea el video final con:
    - Fondo: Imagen de la noticia.
    - Presentador: Video con Chroma Key (#00bf63) en bucle "Ping-Pong".
    - Texto: Título superpuesto.
    - Audio: Narración TTS.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    # Verificación de archivos
    if not os.path.exists(presenter_path):
        logger.error(f"❌ FALTA EL VIDEO DEL PRESENTADOR: {presenter_path}")
        return False
    
    # Fuente para el texto (Linux path)
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial" # Fallback para Windows/Mac local

    clean_title = sanitize_text_for_ffmpeg(text_title)

    # --- COMANDO FFMPEG BLINDADO ---
    # Explicación rápida de filtros:
    # [0:v] -> Imagen de fondo (escalada a 1080x1920)
    # [1:v] -> Presentador (escalado + chroma key + split + reverse + concat + loop)
    # overlay -> Pone al presentador encima del fondo
    # drawtext -> Escribe el título
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       # Input 0: Imagen
        "-i", presenter_path,                 # Input 1: Presentador
        "-i", audio_path,                     # Input 2: Audio
        "-filter_complex",
        (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg];"
            f"[1:v]scale=1080:1920[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:0.1:0.2[v_keyed];"
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            f"[bg][presenter_loop]overlay=0:0:shortest=1[comp];"
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=60:box=1:boxcolor=black@0.6:"
            f"boxborderw=20:x=(w-text_w)/2:y=h-350[outv]"
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",  # ¡VITAL PARA T3.MICRO!
        "-r", "14",            # 14 FPS para ahorrar CPU
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",           # Cortar cuando acabe el audio
        output_path
    ]

    try:
        logger.info("🎬 Renderizando Video con Presentador Virtual...")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error en FFmpeg: {e}")
        return False

# ==========================================
# 4. GESTIÓN DE YOUTUBE (ROTACIÓN DE CUENTAS)
# ==========================================

def get_authenticated_service(account_index):
    """Autentica con la cuenta X (0-5)."""
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    # Verificar si existen los archivos
    if not os.path.exists(client_secrets_file):
        logger.error(f"❌ No existe {client_secrets_file}")
        return None

    # Cargar token si existe
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            logger.warning(f"⚠️ Token {account_index} corrupto.")

    # Refrescar token si es necesario
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"❌ Error refrescando token {account_index}: {e}")
                return None
        else:
            logger.error(f"❌ Token {account_index} inválido y sin refresh. Requiere re-autenticación manual.")
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except HttpError as e:
        logger.error(f"❌ Error conectando con YouTube API {account_index}: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="22"):
    """
    Intenta subir el video rotando cuentas (0 al 5).
    Si una falla por cuota, pasa a la siguiente.
    """
    max_accounts = 6
    
    for account_index in range(max_accounts):
        logger.info(f"🔄 Intentando subir con Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube:
            continue

        body = {
            'snippet': {
                'title': title[:99], # Máximo 100 chars
                'description': description[:4900],
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"🚀 Subiendo... {int(status.progress() * 100)}%")

            video_id = response.get('id')
            logger.info(f"✅ SUBIDA EXITOSA: {video_id} (Cuenta {account_index})")
            return video_id

        except HttpError as e:
            if e.resp.status in [403, 429]:
                reason = e.content.decode('utf-8')
                if "quotaExceeded" in reason:
                    logger.warning(f"⚠️ CUOTA EXCEDIDA en Cuenta {account_index}. Cambiando a la siguiente...")
                    continue # Pasa al siguiente loop (siguiente cuenta)
                else:
                    logger.error(f"❌ Error 403/429 no relacionado con cuota: {e}")
            else:
                logger.error(f"❌ Error HTTP desconocido en Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado subiendo con Cuenta {account_index}: {e}")

    logger.error("❌ ERROR CRÍTICO: Todas las cuentas fallaron o están sin cuota.")
    return None

# ==========================================
# 5. ORQUESTADOR PRINCIPAL
# ==========================================

def process_video_task(text_content, title, image_url, article_id):
    """
    Función Maestra:
    1. Descarga recursos.
    2. Genera audio.
    3. Renderiza video (Green Screen).
    4. Sube a YouTube.
    5. Limpia.
    """
    start_time = time.time()
    unique_id = uuid.uuid4().hex[:8]
    
    # Rutas de archivos temporales
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    logger.info(f"⚡ INICIO PROCESO ID: {article_id}")

    try:
        # 1. Descargar Imagen
        logger.info(f"⬇️ Iniciando descarga de imagen...")
        if not download_image_robust(image_url, raw_img_path):
            logger.error("❌ Abortando: No se pudo descargar imagen.")
            return None

        # 2. Generar Audio (Edge-TTS)
        logger.info(f"🎙️ Generando audio (Edge-TTS)...")
        try:
            asyncio.run(generate_audio_edge(text_content, audio_path))
        except Exception as e:
            logger.error(f"❌ Error en TTS: {e}")
            return None

        # 3. Renderizar Video
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success:
            logger.error("❌ Abortando: Falló renderizado de video.")
            return None

        # 4. Subir a YouTube
        logger.info("🚀 Iniciando protocolo de subida a YouTube...")
        tags = ["noticias", "actualidad", "video"]
        video_id = upload_video(final_video_path, title, text_content, tags)

        # 5. Limpieza
        logger.info("🧹 Limpiando archivos temporales...")
        if os.path.exists(raw_img_path): os.remove(raw_img_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        # Opcional: Borrar video final para ahorrar espacio
        if os.path.exists(final_video_path): os.remove(final_video_path)

        total_time = time.time() - start_time
        logger.info(f"🏁 Tarea finalizada en {total_time:.2f} segundos.")
        return video_id

    except Exception as e:
        logger.error(f"❌ Error fatal en process_video_task: {e}")
        return None