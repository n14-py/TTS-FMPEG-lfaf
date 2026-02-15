# -*- coding: utf-8 -*-
"""
=============================================================================
 SISTEMA DE GENERACIÓN DE VIDEO IA - LFAF TECH (VERSIÓN DEFINITIVA 5.5)
=============================================================================
 Autor: LFAF Bot
 Descripción: 
   Genera videos de noticias automatizados para YouTube:
   - Formato 16:9 (1280x720) Horizontal.
   - Texto alineado a la izquierda (Estilo TV Lower Third).
   - Descripción con noticia completa + URL.
   - Presentador Sólido (Chroma Key ajustado).
   - Sistema de Bloqueo Anti-Duplicados y Reintentos.
   - Rotación de Cuentas de YouTube (Anti-Límite).
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

# Configuración de Logs (Detallada para depuración)
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
# El video del presentador debe estar en assets_video/presenter.mp4
PRESENTER_FILENAME = "presenter.mp4"

# --- AJUSTES DE CHROMA KEY (SOLIDEZ) ---
CHROMA_COLOR = "0x00bf63" 
CHROMA_SIMILARITY = "0.15" 
CHROMA_BLEND = "0.05" # Bajo para evitar transparencia en la persona

# --- AJUSTES DE YOUTUBE ---
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
MAX_ACCOUNTS = 6  # Del 0 al 5

# Inicialización de directorios (Crea las carpetas si no existen)
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR, LOCKS_DIR]:
    if not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
            logger.info(f"📁 Directorio verificado: {d}")
        except Exception as e:
            logger.error(f"❌ Error creando directorio {d}: {e}")

# ==========================================
# 2. SISTEMA ANTI-DUPLICADOS
# ==========================================

def is_already_processed(article_id):
    """
    Verifica si este ID ya fue procesado exitosamente.
    Evita que el bot suba el mismo video 2 veces si la API lo pide de nuevo.
    """
    if not article_id:
        return False
    lock_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
    return os.path.exists(lock_file)

def mark_as_processed(article_id, video_id):
    """
    Crea una marca de seguridad indicando que este articulo ya es video.
    """
    if not article_id:
        return
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
    """Limpia nombres de archivo para evitar errores en el sistema de archivos."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def prepare_text_for_video(text):
    """
    Formatea el título para la pantalla (Lower Third).
    Usa 'wrapper' para cortar líneas.
    """
    # 1. Limpieza de caracteres extraños
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")

    # 2. WRAP: 45 caracteres por línea (para dejar espacio al presentador a la derecha)
    wrapper = textwrap.TextWrapper(width=45) 
    word_list = wrapper.wrap(text=text)
    
    # 3. Máximo 3 líneas para no tapar demasiado la pantalla
    if len(word_list) > 3:
        final_text = "\n".join(word_list[:3]) + "..."
    else:
        final_text = "\n".join(word_list)
    
    return final_text

# ==========================================
# 4. GESTOR DE DESCARGAS (PLAN B MILITAR)
# ==========================================

def download_image_robust(url, save_path, retries=3):
    """
    Descarga imágenes asegurando que no fallen.
    Si requests falla, usa CURL del sistema.
    """
    logger.info(f"⬇️ Iniciando descarga de imagen: {url}")
    
    for attempt in range(retries):
        # INTENTO PYTHON (REQUESTS)
        try:
            response = requests.get(url, timeout=15, verify=False)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                if os.path.getsize(save_path) > 100:
                    return True
        except Exception as e:
            logger.warning(f"⚠️ Intento {attempt+1} fallido (Requests): {e}")

        # INTENTO CURL (LINUX SYSTEM)
        try:
            cmd = [
                "curl", "-L", "-k",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "--retry", "2",
                "-o", save_path, url
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                return True
        except Exception as e:
            logger.warning(f"⚠️ Intento {attempt+1} fallido (CURL): {e}")
            
        time.sleep(1) # Esperar un poco antes de reintentar

    logger.error("❌ ERROR FATAL: No se pudo descargar la imagen tras todos los intentos.")
    return False

# ==========================================
# 5. GENERADOR DE AUDIO (TTS ASÍNCRONO)
# ==========================================

async def generate_audio_edge(text, output_file):
    """
    Genera audio con voz de locutor hombre usando Edge-TTS.
    Voz: es-AR-TomasNeural.
    """
    try:
        voice = 'es-AR-TomasNeural' 
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        
        # Verificar que el archivo se creó correctamente
        if os.path.exists(output_file) and os.path.getsize(output_file) > 100:
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error generando TTS: {e}")
        return False

# ==========================================
# 6. MOTOR DE VIDEO (FFMPEG IZQUIERDA)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Genera video 1280x720 Horizontal.
    - ALINEACIÓN TEXTO: Izquierda (x=50).
    - FONDO: Ajustado sin deformar.
    - PRESENTADOR: Solidez mejorada.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    # Validar existencia del presentador
    if not os.path.exists(presenter_path):
        logger.error(f"❌ FALTA VIDEO PRESENTADOR: {presenter_path}")
        return False
    
    # Fuente (Linux) o Fallback
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial"

    # Prepara el texto con saltos de línea
    clean_title = prepare_text_for_video(text_title)

    # --- COMANDO FFMPEG COMPLEJO AJUSTADO ---
    # x=50 : Pegado a la izquierda (margen de 50 píxeles).
    # y=h-180 : En la parte inferior.
    # text_align=left : Fuerza alineación izquierda del bloque.
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       # 0: Imagen
        "-i", presenter_path,                 # 1: Presentador
        "-i", audio_path,                     # 2: Audio
        "-filter_complex",
        (
            # 1. FONDO: Escalar ancho a 1280 y recortar altura a 720 (Centrado)
            f"[0:v]scale=1280:-2,crop=1280:720:(iw-ow)/2:(ih-oh)/2[bg];"
            
            # 2. PRESENTADOR: Escalar altura a 720 (ancho auto) y Chroma Key
            f"[1:v]scale=-1:720[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
            
            # 3. BUCLE PING-PONG (Efecto espejo para continuidad)
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            
            # 4. COMPOSICIÓN (Presentador Centrado sobre fondo)
            f"[bg][presenter_loop]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
            
            # 5. TEXTO A LA IZQUIERDA (Lower Third style)
            # x=50 (Pegado izquierda), y=h-160 (Abajo)
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=40:line_spacing=12:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3:"
            f"box=1:boxcolor=black@0.5:boxborderw=10:" # Caja semitransparente para leer mejor
            f"x=50:y=h-180[outv]" 
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast", # Optimizado para t3.micro
        "-r", "24",           # 24 FPS Standard
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path
    ]

    try:
        logger.info("🎬 Renderizando Video (Texto Izquierda)...")
        subprocess.run(cmd, check=True)
        # Validar que el archivo resultante exista y tenga peso
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error Crítico FFmpeg: {e}")
        return False

# ==========================================
# 7. GESTOR DE YOUTUBE (DESCRIPCIÓN COMPLETA + ROTACIÓN)
# ==========================================

def get_authenticated_service(account_index):
    """Autenticación y rotación de tokens."""
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    # Verificar existencia de secretos
    if not os.path.exists(client_secrets_file):
        # logger.warning(f"⚠️ Falta archivo secreto para cuenta {account_index}")
        return None

    # Cargar token existente
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            pass

    # Refrescar token si es necesario
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

def upload_video(file_path, title, description, tags, category_id="25"): # 25 = News & Politics
    """Subida con rotación de cuentas automática."""
    
    for account_index in range(MAX_ACCOUNTS):
        logger.info(f"📡 Probando subida con Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube: 
            continue # Si falla auth, prueba la siguiente

        body = {
            'snippet': {
                'title': title[:99], # Límite de YouTube 100 chars
                'description': description[:4900], # Límite 5000 chars
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'public', # CAMBIAR A 'private' PARA PRUEBAS
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            response = None
            logger.info("🚀 Subiendo video...")
            while response is None:
                status, response = request.next_chunk()
                if status:
                    # Progreso en consola (opcional)
                    pass

            video_id = response.get('id')
            logger.info(f"✅ SUBIDA EXITOSA: https://youtu.be/{video_id}")
            return video_id

        except HttpError as e:
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"⚠️ Cuota llena en Cuenta {account_index}. Cambiando...")
                continue
            else:
                logger.error(f"❌ Error HTTP Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado Cuenta {account_index}: {e}")

    logger.error("❌ ERROR CRÍTICO: Todas las cuentas fallaron.")
    return None

# ==========================================
# 8. ORQUESTADOR PRINCIPAL
# ==========================================

def process_video_task(text_content, title, image_url, article_id, article_url=""):
    """
    Función Principal (Entry Point).
    """
    start_time = time.time()
    
    logger.info(f"⚡ TAREA RECIBIDA: {article_id}")

    # 1. Verificar si ya se hizo (Anti-Duplicados)
    if is_already_processed(article_id):
        logger.warning(f"🛑 Tarea {article_id} ignorada (Ya procesada).")
        return "ALREADY_PROCESSED"

    unique_id = uuid.uuid4().hex[:8]
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    try:
        # PASO 1: Descargar Imagen
        if not download_image_robust(image_url, raw_img_path): 
            return None

        # PASO 2: Generar Audio (CORRECCIÓN APLICADA: asyncio.run)
        logger.info("🎙️ Generando audio...")
        try:
            # Seleccionar texto a leer (Contenido o Título)
            text_to_read = text_content if text_content and len(text_content) > 10 else title
            
            # --- AQUÍ ESTABA EL ERROR, AHORA ESTÁ CORREGIDO ---
            asyncio.run(generate_audio_edge(text_to_read, audio_path))
            
        except Exception as e:
            logger.error(f"❌ Error TTS: {e}")
            return None

        # PASO 3: Renderizar Video (Texto Izquierda)
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success: 
            return None

        # PASO 4: Preparar Descripción COMPLETA
        # Cortamos a 4500 chars para dejar espacio a la URL
        full_text_truncated = text_content[:4000] if text_content else title
        
        description_final = f"{title}\n\n"
        description_final += "------------------------------------------------\n"
        description_final += f"{full_text_truncated}\n\n"
        
        # Añadir URL si existe
        if article_url:
            description_final += f"📰 Leer nota completa aquí: {article_url}\n\n"
            
        description_final += "------------------------------------------------\n"
        description_final += "#noticias #actualidad #internacional #ia"

        # PASO 5: Subir a YouTube
        tags = ["noticias", "actualidad", "ultimahora"]
        video_id = upload_video(final_video_path, title, description_final, tags)

        if video_id:
            mark_as_processed(article_id, video_id)
            
            # Limpieza de archivos temporales
            try:
                if os.path.exists(raw_img_path): os.remove(raw_img_path)
                if os.path.exists(audio_path): os.remove(audio_path)
                if os.path.exists(final_video_path): os.remove(final_video_path)
            except Exception:
                pass
            
            total_time = time.time() - start_time
            logger.info(f"🏁 Tarea completada en {total_time:.2f} segundos.")
            return video_id
        else:
            return None

    except Exception as e:
        logger.error(f"❌ Error Fatal en Proceso: {e}")
        return None