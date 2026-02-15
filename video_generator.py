import os
import time
import random
import logging
import json
import asyncio
import re
import subprocess
import uuid
import textwrap  # LIBRERÍA NUEVA PARA CORTAR EL TEXTO
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

# Directorios de trabajo
TEMP_AUDIO = "temp_audio"
TEMP_VIDEO = "temp_video"
TEMP_IMG = "temp_processing"
OUTPUT_DIR = "output"
ASSETS_DIR = "assets_video"

# ARCHIVO DEL PRESENTADOR (Debe estar en assets_video/)
PRESENTER_FILENAME = "presenter.mp4"

# Color verde a eliminar (Chroma Key)
CHROMA_COLOR = "0x00bf63"

# Permisos de YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Crear carpetas si no existen
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR]:
    os.makedirs(d, exist_ok=True)

# ==========================================
# 1. UTILIDADES Y PROCESAMIENTO DE TEXTO
# ==========================================

def sanitize_filename(filename):
    """Limpia nombres de archivo."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def prepare_text_for_video(text):
    """
    1. Limpia caracteres raros.
    2. Divide el texto en líneas (WRAP) para que no se salga de la pantalla.
    """
    # Limpieza básica
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")

    # WRAP: Cortar cada 50 caracteres para que haga salto de línea
    # Esto convierte "Noticia larga..." en "Noticia larga\nsegunda parte"
    wrapper = textwrap.TextWrapper(width=50) 
    word_list = wrapper.wrap(text=text)
    
    # Unir con saltos de línea y limitar a máximo 3 líneas para no tapar la cara
    final_text = "\n".join(word_list[:3]) 
    
    return final_text

def download_image_robust(url, save_path):
    """
    Descarga 'Militar': Intenta Python primero, si falla usa CURL de Linux.
    Esencial para evitar errores 403 de imágenes protegidas.
    """
    # INTENTO 1: Python Requests
    try:
        response = requests.get(url, timeout=15, verify=False)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        logger.warning(f"⚠️ Python falló descargando imagen, activando CURL: {e}")

    # INTENTO 2: CURL (Linux)
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
    """
    Genera audio con voz de locutor hombre.
    Voz: es-AR-TomasNeural (Clara y profesional).
    """
    voice = 'es-AR-TomasNeural' 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# ==========================================
# 3. RENDERIZADO DE VIDEO (FFMPEG HORIZONTAL)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Crea un video HORIZONTAL (1280x720).
    - Fondo: Imagen ajustada matemáticamente (sin estirar).
    - Presentador: Sin deformar, centrado.
    - Texto: Multilínea, más pequeño, centrado abajo.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    if not os.path.exists(presenter_path):
        logger.error(f"❌ FALTA VIDEO PRESENTADOR: {presenter_path}")
        return False
    
    # Fuente (Linux) o Fallback
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial" 

    # Preparar el título con saltos de línea (\n)
    wrapped_title = prepare_text_for_video(text_title)

    # --- COMANDO FFMPEG COMPLEJO ---
    # Explicación de Filtros:
    # 1. Fondo [0:v]: Escalar ancho a 1280 (alto auto), luego cortar el centro a 720 de alto.
    # 2. Presentador [1:v]: Escalar alto a 720 (ancho auto). NO SE DEFORMA.
    # 3. Chroma Key: Quita el verde.
    # 4. Boomerang: Normal -> Reversa -> Bucle.
    # 5. Overlay: Pone al presentador encima.
    # 6. Drawtext:
    #    - text='...': Usa el texto con saltos de línea.
    #    - fontsize=35: Más chico.
    #    - line_spacing=10: Espacio entre líneas.
    #    - y=h-140: Posición fija abajo.
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       
        "-i", presenter_path,                 
        "-i", audio_path,                     
        "-filter_complex",
        (
            f"[0:v]scale=1280:-1,crop=1280:720:(iw-ow)/2:(ih-oh)/2[bg];"
            f"[1:v]scale=-1:720[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:0.1:0.2[v_keyed];"
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            f"[bg][presenter_loop]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
            f"[comp]drawtext=fontfile='{font_path}':text='{wrapped_title}':"
            f"fontcolor=white:fontsize=35:line_spacing=10:"
            f"shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"x=(w-text_w)/2:y=h-140[outv]"
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast", # CLAVE para servidor barato
        "-r", "14",           # 14 FPS es suficiente y rápido
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path
    ]

    try:
        logger.info(f"🎬 Renderizando Video HORIZONTAL (Multi-línea)...")
        logger.info(f"📜 Título procesado: {wrapped_title.replace(chr(10), ' | ')}") # Log del título
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error FFmpeg: {e}")
        return False

# ==========================================
# 4. GESTIÓN DE YOUTUBE (ROTACIÓN DE CUENTAS)
# ==========================================

def get_authenticated_service(account_index):
    """
    Autentica y rota tokens automáticamente.
    Si el token venció, lo refresca y guarda.
    """
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    if not os.path.exists(client_secrets_file):
        logger.error(f"❌ Falta archivo secreto: {client_secrets_file}")
        return None

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            logger.warning(f"⚠️ Token {account_index} corrupto.")

    # Refrescar si es necesario
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
            logger.error(f"❌ Token {account_index} muerto. Requiere login manual.")
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except HttpError as e:
        logger.error(f"❌ Error API YouTube {account_index}: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="22"):
    """
    Sube el video. Si la Cuenta 0 falla por cuota, prueba la Cuenta 1, etc.
    """
    max_accounts = 6
    
    for account_index in range(max_accounts):
        logger.info(f"🔄 Intento de subida: Cuenta {account_index}...")
        
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
                'privacyStatus': 'public', # 'private' o 'public'
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
            logger.info(f"✅ SUBIDA EXITOSA: https://youtu.be/{video_id}")
            return video_id

        except HttpError as e:
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"⚠️ Cuota llena en Cuenta {account_index}. Pasando a siguiente...")
                continue
            else:
                logger.error(f"❌ Error HTTP en Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado Cuenta {account_index}: {e}")

    logger.error("❌ ERROR CRÍTICO: Todas las cuentas fallaron.")
    return None

# ==========================================
# 5. ORQUESTADOR PRINCIPAL (TASK PROCESSOR)
# ==========================================

def process_video_task(text_content, title, image_url, article_id):
    """
    Controlador principal. Llama a todo en orden.
    """
    start_time = time.time()
    unique_id = uuid.uuid4().hex[:8]
    
    # Rutas
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    logger.info(f"⚡ INICIO TAREA: {article_id} (Modo: Horizontal + Multi-line)")

    try:
        # 1. Descargar Imagen
        if not download_image_robust(image_url, raw_img_path): 
            logger.error("❌ Falló descarga imagen")
            return None

        # 2. Generar Audio
        logger.info("🎙️ Generando audio...")
        try:
            asyncio.run(generate_audio_edge(text_content, audio_path))
        except Exception as e:
            logger.error(f"❌ Error TTS: {e}")
            return None

        # 3. Renderizar Video
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success:
            logger.error("❌ Falló Renderizado")
            return None

        # 4. Subir a YouTube
        logger.info("🚀 Subiendo a YouTube...")
        tags = ["noticias", "actualidad", "internacional"]
        # Usamos el título como descripción también
        video_id = upload_video(final_video_path, title, f"{title}\n\nMás en nuestro canal.\n#noticias", tags)

        # 5. Limpieza
        logger.info("🧹 Limpiando...")
        if os.path.exists(raw_img_path): os.remove(raw_img_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(final_video_path): os.remove(final_video_path)

        total_time = time.time() - start_time
        logger.info(f"🏁 Tarea terminada en {total_time:.2f}s")
        return video_id

    except Exception as e:
        logger.error(f"❌ Error Fatal: {e}")
        return None