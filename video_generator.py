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
# NOTA: Si cambias al presentador mujer, cambia este nombre aquí.
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
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")
    # Cortar si es muy largo para el título (aprox 2 líneas)
    if len(text) > 65:
        text = text[:62] + "..."
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
    # CAMBIO DE VOZ: Usamos 'es-AR-TomasNeural' para voz masculina de noticias.
    # Si usas la presentadora mujer, cambia esto a 'es-MX-DaliaNeural'.
    voice = 'es-AR-TomasNeural' 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# ==========================================
# 3. RENDERIZADO DE VIDEO (FFMPEG OPTIMIZADO 720p)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Crea el video final en 720x1280 (Optimizado).
    - Fondo: Imagen sin deformar (recortada al centro).
    - Presentador: Chroma Key + Bucle Ping-Pong.
    - Texto: Título con sombra (sin caja negra).
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    if not os.path.exists(presenter_path):
        logger.error(f"❌ FALTA EL VIDEO DEL PRESENTADOR: {presenter_path}")
        return False
    
    # Fuente para el texto (Linux path)
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial" # Fallback local

    clean_title = sanitize_text_for_ffmpeg(text_title)

    # --- COMANDO FFMPEG OPTIMIZADO (720p) ---
    # CAMBIOS CLAVE:
    # 1. Resoluciones: Todo pasa de 1080:1920 a 720:1280.
    # 2. Escala de imagen [0:v]: Se usa scale=-1:1280 (mantiene aspecto) y luego crop=720:1280:center:center (corta lo que sobra). ¡ADIÓS DEFORMACIÓN!
    # 3. drawtext: Se elimina 'box=1' y 'boxcolor'. Se añade shadowcolor y shadowx/y para sombra elegante.
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       # Input 0: Imagen
        "-i", presenter_path,                 # Input 1: Presentador
        "-i", audio_path,                     # Input 2: Audio
        "-filter_complex",
        (
            # 1. Fondo (Imagen): Escalar proporcionalmente a 1280 de alto y cortar el centro a 720 de ancho
            f"[0:v]scale=-1:1280,crop=720:1280:center:center[bg];"
            
            # 2. Presentador: Escalar a 720p, quitar verde, efecto boomerang
            f"[1:v]scale=720:1280[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:0.1:0.2[v_keyed];"
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            
            # 3. Superponer Presentador sobre Fondo
            f"[bg][presenter_loop]overlay=0:0:shortest=1[comp];"
            
            # 4. Dibujar Texto (SIN CAJA NEGRA, CON SOMBRA)
            #    fontsize=42 (más pequeño para 720p), y=h-250 (posición)
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=42:shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"x=(w-text_w)/2:y=h-250[outv]"
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",  # VITAL PARA VELOCIDAD
        "-r", "14",            # 14 FPS para velocidad máxima
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path
    ]

    try:
        logger.info("🎬 Renderizando Video 720p OPTIMIZADO...")
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

    if not os.path.exists(client_secrets_file):
        logger.error(f"❌ No existe {client_secrets_file}")
        return None

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            logger.warning(f"⚠️ Token {account_index} corrupto.")

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
            logger.error(f"❌ Token {account_index} inválido. Requiere re-autenticación.")
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except HttpError as e:
        logger.error(f"❌ Error conectando con YouTube API {account_index}: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="22"):
    """Sube el video rotando cuentas si hay error de cuota."""
    max_accounts = 6
    
    for account_index in range(max_accounts):
        logger.info(f"🔄 Intentando subir con Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube:
            continue

        body = {
            'snippet': {
                'title': title[:99],
                'description': description[:4900],
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'public', # CAMBIA A 'private' PARA PRUEBAS
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
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"⚠️ CUOTA EXCEDIDA en Cuenta {account_index}. Probando siguiente...")
                continue
            else:
                logger.error(f"❌ Error HTTP en Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado en Cuenta {account_index}: {e}")

    logger.error("❌ ERROR CRÍTICO: Todas las cuentas fallaron.")
    return None

# ==========================================
# 5. ORQUESTADOR PRINCIPAL
# ==========================================

def process_video_task(text_content, title, image_url, article_id):
    """Función Maestra que coordina todo."""
    start_time = time.time()
    unique_id = uuid.uuid4().hex[:8]
    
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    logger.info(f"⚡ INICIO PROCESO ID: {article_id} (Modo 720p Optimizado)")

    try:
        # 1. Descargar Imagen
        logger.info(f"⬇️ Descargando imagen...")
        if not download_image_robust(image_url, raw_img_path):
            return None

        # 2. Generar Audio (Voz Hombre)
        logger.info(f"🎙️ Generando audio (Voz Tomás)...")
        asyncio.run(generate_audio_edge(text_content, audio_path))

        # 3. Renderizar Video (720p, sin deformar, sin caja negra)
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success:
            return None

        # 4. Subir a YouTube
        logger.info("🚀 Iniciando subida a YouTube...")
        tags = ["noticias", "actualidad", "video", "shorts"]
        # NOTA: Se usa el título como descripción también para este formato corto
        video_id = upload_video(final_video_path, title, title + "\n\n#noticias", tags)

        # 5. Limpieza
        logger.info("🧹 Limpiando...")
        if os.path.exists(raw_img_path): os.remove(raw_img_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(final_video_path): os.remove(final_video_path)

        total_time = time.time() - start_time
        logger.info(f"🏁 Tarea finalizada en {total_time:.2f}s.")
        return video_id

    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        return None