# -*- coding: utf-8 -*-
"""
=============================================================================
 SISTEMA DE GENERACIÓN DE VIDEO IA - LFAF TECH (VERSIÓN FINAL PRO)
=============================================================================
 Autor: LFAF Bot
 Versión: 5.0.0 (Horizontal Left-Align + Full Description)
 Descripción: 
   Genera videos de noticias automatizados para YouTube:
   - Formato 16:9 (1280x720) Horizontal.
   - Texto alineado a la izquierda (Estilo TV).
   - Descripción con noticia completa + URL.
   - Presentador Sólido (Chroma Key ajustado).
   - Sistema de Bloqueo Anti-Duplicados y Reintentos.
=============================================================================
"""

import os
import time
import random
import logging
import json
import asyncio
import re
import subprocess
import uuid
import textwrap
import shutil
from datetime import datetime
import requests

# --- LIBRERÍAS DE GOOGLE/YOUTUBE ---
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# --- LIBRERÍA DE VOZ NEURAL ---
import edge_tts

# ==========================================
# 1. CONFIGURACIÓN DEL SISTEMA
# ==========================================

# Configuración de Logs (Detallada)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- RUTAS DE DIRECTORIOS ---
BASE_DIR = os.getcwd()
TEMP_AUDIO = os.path.join(BASE_DIR, "temp_audio")
TEMP_VIDEO = os.path.join(BASE_DIR, "temp_video")
TEMP_IMG = os.path.join(BASE_DIR, "temp_processing")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ASSETS_DIR = os.path.join(BASE_DIR, "assets_video")
LOCKS_DIR = os.path.join(BASE_DIR, "locks_history") 

# --- ARCHIVOS DE ACTIVOS ---
PRESENTER_FILENAME = "presenter.mp4"

# --- AJUSTES DE CHROMA KEY (SOLIDEZ) ---
CHROMA_COLOR = "0x00bf63" 
CHROMA_SIMILARITY = "0.15" 
CHROMA_BLEND = "0.05" # Bajo para evitar transparencia en la persona

# --- AJUSTES DE YOUTUBE ---
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
MAX_ACCOUNTS = 6  # Del 0 al 5

# Inicialización de directorios
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR, LOCKS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# ==========================================
# 2. SISTEMA ANTI-DUPLICADOS
# ==========================================

def is_already_processed(article_id):
    """Verifica si el video ya se hizo para no repetirlo."""
    lock_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
    return os.path.exists(lock_file)

def mark_as_processed(article_id, video_id):
    """Marca la tarea como completada."""
    lock_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
    try:
        with open(lock_file, 'w') as f:
            f.write(f"Processed at {datetime.now()} - YouTube ID: {video_id}")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar bloqueo para {article_id}: {e}")

# ==========================================
# 3. PROCESAMIENTO DE TEXTO (ALINEACIÓN IZQUIERDA)
# ==========================================

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def prepare_text_for_video(text):
    """
    Formatea el título para la pantalla.
    Usa 'wrapper' para cortar líneas.
    """
    # Limpieza
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")

    # WRAP: 40 caracteres por línea (para dejar espacio al presentador)
    wrapper = textwrap.TextWrapper(width=40) 
    word_list = wrapper.wrap(text=text)
    
    # Máximo 3 líneas para no tapar demasiado
    if len(word_list) > 3:
        final_text = "\n".join(word_list[:3]) + "..."
    else:
        final_text = "\n".join(word_list)
    
    return final_text

# ==========================================
# 4. GESTOR DE DESCARGAS (PLAN B MILITAR)
# ==========================================

def download_image_robust(url, save_path, retries=3):
    """Descarga imágenes asegurando que no fallen."""
    for attempt in range(retries):
        # INTENTO PYTHON
        try:
            response = requests.get(url, timeout=15, verify=False)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                if os.path.getsize(save_path) > 100:
                    return True
        except Exception as e:
            pass

        # INTENTO CURL (LINUX)
        try:
            cmd = [
                "curl", "-L", "-k",
                "--user-agent", "Mozilla/5.0",
                "--retry", "2",
                "-o", save_path, url
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                return True
        except Exception:
            pass
            
        time.sleep(1)

    logger.error("❌ ERROR: No se pudo descargar la imagen.")
    return False

# ==========================================
# 5. GENERADOR DE AUDIO (TTS)
# ==========================================

async def generate_audio_edge(text, output_file):
    """Voz de Hombre (Tomás Neural)."""
    try:
        voice = 'es-AR-TomasNeural' 
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        return True
    except Exception as e:
        logger.error(f"❌ Error TTS: {e}")
        return False

# ==========================================
# 6. MOTOR DE VIDEO (FFMPEG IZQUIERDA)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Genera video 1280x720 Horizontal.
    - ALINEACIÓN TEXTO: Izquierda (x=30).
    - FONDO: Ajustado sin deformar.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    if not os.path.exists(presenter_path):
        logger.error(f"❌ FALTA VIDEO PRESENTADOR: {presenter_path}")
        return False
    
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial"

    # Prepara el texto con saltos de línea
    clean_title = prepare_text_for_video(text_title)

    # --- COMANDO FFMPEG AJUSTADO ---
    # x=30 : Pegado a la izquierda (margen de 30 píxeles).
    # y=h-160 : En la parte inferior.
    # text_align=left : Fuerza alineación izquierda del bloque.
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       
        "-i", presenter_path,                 
        "-i", audio_path,                     
        "-filter_complex",
        (
            # 1. FONDO: Escalar y recortar centro
            f"[0:v]scale=1280:-2,crop=1280:720:(iw-ow)/2:(ih-oh)/2[bg];"
            
            # 2. PRESENTADOR: Escalar y Chroma Key
            f"[1:v]scale=-1:720[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
            
            # 3. BUCLE PING-PONG
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            
            # 4. COMPOSICIÓN (Presentador Centrado)
            f"[bg][presenter_loop]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
            
            # 5. TEXTO A LA IZQUIERDA
            # x=30 (Pegado izquierda), y=h-160 (Abajo)
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=40:line_spacing=12:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3:"
            f"x=30:y=h-160[outv]" 
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-r", "24",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path
    ]

    try:
        logger.info("🎬 Renderizando Video (Texto Izquierda)...")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error FFmpeg: {e}")
        return False

# ==========================================
# 7. GESTOR DE YOUTUBE (DESCRIPCIÓN COMPLETA)
# ==========================================

def get_authenticated_service(account_index):
    """Autenticación y rotación de tokens."""
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    if not os.path.exists(client_secrets_file):
        return None

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception:
                return None
        else:
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except Exception:
        return None

def upload_video(file_path, title, description, tags, category_id="25"):
    """Subida con rotación de cuentas."""
    
    for account_index in range(MAX_ACCOUNTS):
        logger.info(f"📡 Probando Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube: continue

        body = {
            'snippet': {
                'title': title[:99],
                'description': description[:4900], # Descripción larga permitida
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

            video_id = response.get('id')
            logger.info(f"✅ SUBIDO: https://youtu.be/{video_id}")
            return video_id

        except HttpError as e:
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"⚠️ Cuota llena Cuenta {account_index}.")
                continue
            else:
                logger.error(f"❌ Error HTTP {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error {account_index}: {e}")

    return None

# ==========================================
# 8. ORQUESTADOR PRINCIPAL
# ==========================================

# AÑADIMOS article_url=None para recibir la URL si la envían
def process_video_task(text_content, title, image_url, article_id, article_url=""):
    start_time = time.time()
    
    logger.info(f"⚡ TAREA {article_id}: Iniciando...")

    if is_already_processed(article_id):
        logger.warning(f"🛑 Tarea {article_id} ya realizada.")
        return "ALREADY_PROCESSED"

    unique_id = uuid.uuid4().hex[:8]
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    try:
        # 1. Descargar
        if not download_image_robust(image_url, raw_img_path): return None

        # 2. Audio
        if text_content:
            await generate_audio_edge(text_content, audio_path)
        else:
            await generate_audio_edge(title, audio_path)

        # 3. Renderizar (Texto Izquierda)
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success: return None

        # 4. Preparar Descripción COMPLETA
        # Cortamos a 4500 chars para dejar espacio a la URL y hashtags
        full_text_truncated = text_content[:4500] if text_content else title
        
        description_final = f"{title}\n\n"
        description_final += f"{full_text_truncated}\n\n"
        
        # Añadir URL si existe
        if article_url:
            description_final += f"📰 Leer nota completa: {article_url}\n\n"
            
        description_final += "#noticias #actualidad #mundo"

        # 5. Subir
        tags = ["noticias", "actualidad"]
        video_id = upload_video(final_video_path, title, description_final, tags)

        if video_id:
            mark_as_processed(article_id, video_id)
            
            # Limpieza
            if os.path.exists(raw_img_path): os.remove(raw_img_path)
            if os.path.exists(audio_path): os.remove(audio_path)
            if os.path.exists(final_video_path): os.remove(final_video_path)
            
            return video_id
        else:
            return None

    except Exception as e:
        logger.error(f"❌ Error Fatal: {e}")
        return None