# -*- coding: utf-8 -*-
"""
=============================================================================
 SISTEMA DE GENERACIÓN DE VIDEO IA - LFAF TECH (VERSIÓN MAESTRA PRO)
=============================================================================
 Autor: LFAF Bot
 Versión: 4.5.0 (Horizontal Stable)
 Descripción: 
   Genera videos de noticias automatizados para YouTube usando:
   - Imágenes dinámicas (sin deformación)
   - Presentador Virtual (Bucle Ping-Pong + Chroma Key Sólido)
   - Narración IA (Edge-TTS)
   - Rotación de Cuentas de YouTube (Anti-Límite)
   - Sistema de Archivos de Bloqueo (Anti-Duplicados)
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

# Configuración de Logs (Muestra todo lo que pasa en la terminal)
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
LOCKS_DIR = os.path.join(BASE_DIR, "locks_history") # Nueva carpeta para evitar duplicados

# --- ARCHIVOS DE ACTIVOS ---
# El video del presentador debe estar en assets_video/presenter.mp4
PRESENTER_FILENAME = "presenter.mp4"

# --- AJUSTES DE CHROMA KEY (PANTALLA VERDE) ---
# Color exacto de tu video verde
CHROMA_COLOR = "0x00bf63" 
# Similarity: Cuánto se parece al verde (0.1 es estricto, 0.3 es tolerante)
CHROMA_SIMILARITY = "0.15" 
# Blend: Suavizado de bordes. 
# ¡IMPORTANTE!: Mantener bajo (0.05) para evitar transparencia en la persona.
CHROMA_BLEND = "0.05"

# --- AJUSTES DE YOUTUBE ---
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
MAX_ACCOUNTS = 6  # Del 0 al 5

# Inicialización de directorios
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR, LOCKS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
        logger.info(f"📁 Directorio creado: {d}")

# ==========================================
# 2. SISTEMA ANTI-DUPLICADOS
# ==========================================

def is_already_processed(article_id):
    """
    Verifica si este ID ya fue procesado exitosamente.
    Evita que el bot suba el mismo video 2 veces si la API lo pide de nuevo.
    """
    lock_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
    if os.path.exists(lock_file):
        return True
    return False

def mark_as_processed(article_id, video_id):
    """
    Crea una marca de seguridad indicando que este articulo ya es video.
    """
    lock_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
    try:
        with open(lock_file, 'w') as f:
            f.write(f"Processed at {datetime.now()} - YouTube ID: {video_id}")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar bloqueo para {article_id}: {e}")

# ==========================================
# 3. UTILIDADES DE TEXTO Y ARCHIVOS
# ==========================================

def sanitize_filename(filename):
    """Limpia nombres de archivo para Windows/Linux."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def prepare_text_for_video(text):
    """
    Formatea el título para que se vea bonito en el video.
    - Elimina caracteres basura.
    - Divide en líneas (Word Wrap) para que no se salga de la pantalla.
    """
    # 1. Limpieza de caracteres prohibidos en FFmpeg
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")

    # 2. Algoritmo de ajuste de línea (Wrap)
    # Corta cada 45 caracteres aprox sin romper palabras
    wrapper = textwrap.TextWrapper(width=45) 
    word_list = wrapper.wrap(text=text)
    
    # 3. Unir máximo 3 líneas (para no tapar la cara del presentador)
    if len(word_list) > 3:
        logger.info("ℹ️ Texto muy largo, recortando a 3 líneas.")
        final_text = "\n".join(word_list[:3]) + "..."
    else:
        final_text = "\n".join(word_list)
    
    return final_text

# ==========================================
# 4. GESTOR DE DESCARGAS (PLAN B MILITAR)
# ==========================================

def download_image_robust(url, save_path, retries=3):
    """
    Descarga imágenes con reintentos y múltiples métodos.
    Si falla Python, usa CURL (comando de sistema).
    """
    for attempt in range(retries):
        try:
            # MÉTODO A: Python Requests (Rápido)
            logger.info(f"⬇️ Descargando imagen (Intento {attempt+1})...")
            response = requests.get(url, timeout=15, verify=False)
            
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                # Verificar que no esté vacío
                if os.path.getsize(save_path) > 100:
                    return True
                else:
                    logger.warning("⚠️ Imagen descargada vacía.")
            
        except Exception as e:
            logger.warning(f"⚠️ Fallo Python Requests: {e}")

        # MÉTODO B: CURL (Fuerza Bruta)
        try:
            logger.info("👉 Activando Protocolo CURL...")
            cmd = [
                "curl", "-L", "-k",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "--retry", "2",
                "-o", save_path,
                url
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                logger.info("✅ Imagen recuperada con CURL.")
                return True
                
        except Exception as e:
            logger.error(f"❌ CURL falló también: {e}")
            
        time.sleep(2) # Esperar antes de reintentar

    logger.error("❌ ERROR FATAL: No se pudo descargar la imagen tras varios intentos.")
    return False

# ==========================================
# 5. GENERADOR DE AUDIO (TTS NEURAL)
# ==========================================

async def generate_audio_edge(text, output_file):
    """
    Genera la voz del noticiero.
    Voz: Hombre (Tomás Neural) - Serio y profesional.
    """
    try:
        # Selección de Voz
        voice = 'es-AR-TomasNeural' 
        
        # Generación
        logger.info(f"🎙️ Sintetizando voz con {voice}...")
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        
        # Verificación
        if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
            return True
        else:
            raise Exception("Archivo de audio generado muy pequeño o vacío.")
            
    except Exception as e:
        logger.error(f"❌ Error en TTS: {e}")
        return False

# ==========================================
# 6. MOTOR DE RENDERIZADO (FFMPEG PRO)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Construye el video final en ALTA CALIDAD HORIZONTAL (1280x720).
    Corrige transparencia y deformaciones.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    # 1. Validación de Activos
    if not os.path.exists(presenter_path):
        logger.error(f"❌ NO EXISTE EL VIDEO DEL PRESENTADOR: {presenter_path}")
        logger.error("👉 Sube un archivo llamado 'presenter.mp4' a la carpeta 'assets_video'.")
        return False
    
    # 2. Selección de Fuente
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial" # Fallback para pruebas locales

    # 3. Preparación del Texto
    clean_title = prepare_text_for_video(text_title)

    # 4. CONSTRUCCIÓN DEL COMANDO COMPLEJO
    # ---------------------------------------------------------
    # Filtros Explicados:
    # [0:v] -> FONDO: 
    #     scale=1280:-2  -> Ancho 1280, Alto proporcional (par).
    #     crop=1280:720  -> Recorta el centro exacto. CERO DEFORMACIÓN.
    # [1:v] -> PRESENTADOR:
    #     scale=-1:720   -> Altura 720, Ancho proporcional. CERO DEFORMACIÓN.
    #     chromakey      -> Quita el verde con parámetros ajustados (SOLIDIDAD).
    #     split+reverse  -> Crea efecto Ping-Pong (Adelante-Atrás).
    #     loop           -> Repite infinitamente.
    # overlay -> Pone al presentador sobre el fondo.
    # drawtext -> Escribe el título centrado abajo.
    # ---------------------------------------------------------
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       # Input 0: Imagen
        "-i", presenter_path,                 # Input 1: Video
        "-i", audio_path,                     # Input 2: Audio
        "-filter_complex",
        (
            # FONDO
            f"[0:v]scale=1280:-2,crop=1280:720:(iw-ow)/2:(ih-oh)/2[bg];"
            
            # PRESENTADOR (Chroma Key Corregido)
            f"[1:v]scale=-1:720[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
            
            # EFECTO BUCLE PING-PONG
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            
            # COMPOSICIÓN (Overlay centrado)
            f"[bg][presenter_loop]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
            
            # TEXTO (Título Profesional con Sombra y Fondo)
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=38:line_spacing=15:"
            f"shadowcolor=black@0.9:shadowx=4:shadowy=4:"  # Sombra fuerte para legibilidad
            f"x=(w-text_w)/2:y=h-150[outv]"                # Posición inferior centrada
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",  # Prioridad: VELOCIDAD
        "-r", "24",            # 24 FPS (Cinemático y ligero)
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",           # Cortar cuando acabe el audio
        output_path
    ]

    try:
        logger.info("🎬 Renderizando Video 16:9 (Corrección Solidez)...")
        # subprocess.run ejecuta el comando y espera. check=True lanza error si falla.
        subprocess.run(cmd, check=True)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        return False
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error Crítico en FFmpeg: {e}")
        return False

# ==========================================
# 7. GESTOR DE YOUTUBE (ROTACIÓN DE CUENTAS)
# ==========================================

def get_authenticated_service(account_index):
    """
    Obtiene el servicio de YouTube para la cuenta N.
    Si el token venció, intenta refrescarlo automáticamente.
    """
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    # Validación básica
    if not os.path.exists(client_secrets_file):
        logger.error(f"❌ [Cuenta {account_index}] Falta archivo client_secret.")
        return None

    # Cargar credenciales
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            logger.warning(f"⚠️ [Cuenta {account_index}] Token corrupto, ignorando.")

    # Refresco de Token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info(f"🔄 [Cuenta {account_index}] Refrescando token vencido...")
                creds.refresh(Request())
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"❌ [Cuenta {account_index}] Falló refresco: {e}")
                return None
        else:
            logger.error(f"❌ [Cuenta {account_index}] Token inválido irreversible.")
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ [Cuenta {account_index}] Error de conexión API: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="25"): # 25=News
    """
    Sube el video probando cuentas en orden (0 -> 1 -> 2...).
    Si una cuenta da error de cuota, salta automáticamente a la siguiente.
    """
    
    for account_index in range(MAX_ACCOUNTS):
        logger.info(f"📡 Iniciando intento de subida con CUENTA {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube:
            continue # Si falla la auth, prueba la siguiente

        body = {
            'snippet': {
                'title': title[:99], # YouTube corta a 100 chars
                'description': description[:4900],
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'public', # 'public', 'private', 'unlisted'
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            response = None
            logger.info("🚀 Subiendo bits a la nube...")
            
            while response is None:
                status, response = request.next_chunk()
                if status:
                    # Barra de progreso simple
                    print(f"   Subiendo: {int(status.progress() * 100)}%", end='\r')

            print("") # Salto de línea al terminar
            video_id = response.get('id')
            logger.info(f"✅ ¡ÉXITO! Video subido con Cuenta {account_index}")
            logger.info(f"🔗 URL: https://youtu.be/{video_id}")
            
            return video_id # Retorna ID y ROMPE el bucle (no sigue subiendo)

        except HttpError as e:
            error_msg = e.content.decode('utf-8')
            
            if e.resp.status in [403, 429] and "quotaExceeded" in error_msg:
                logger.warning(f"⚠️ CUOTA EXCEDIDA en Cuenta {account_index}. Cambiando de cuenta...")
                continue # Pasa al siguiente ciclo del for (siguiente cuenta)
            
            elif "uploadLimitExceeded" in error_msg:
                logger.warning(f"⚠️ Límite de subida diario alcanzado en Cuenta {account_index}.")
                continue
                
            else:
                logger.error(f"❌ Error HTTP desconocido en Cuenta {account_index}: {e}")
                
        except Exception as e:
            logger.error(f"❌ Error inesperado en Cuenta {account_index}: {e}")

    # Si llega aquí, es que fallaron las 6 cuentas
    logger.error("❌ ERROR CRÍTICO: Se han probado todas las cuentas y ninguna funcionó.")
    return None

# ==========================================
# 8. ORQUESTADOR PRINCIPAL (CEREBRO)
# ==========================================

def process_video_task(text_content, title, image_url, article_id):
    """
    Función Maestra llamada por la API.
    Coordina paso a paso la creación del noticiero.
    """
    start_time = time.time()
    
    logger.info("="*60)
    logger.info(f"⚡ NUEVA TAREA RECIBIDA: ID {article_id}")
    logger.info("="*60)

    # 1. Verificar Duplicados (Seguridad Anti-Repetición)
    if is_already_processed(article_id):
        logger.warning(f"🛑 Tarea {article_id} IGNORADA: Ya fue procesada anteriormente.")
        return "ALREADY_PROCESSED"

    # Generar ID único para archivos temporales
    unique_id = uuid.uuid4().hex[:8]
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    try:
        # PASO 2: Descargar Recursos
        logger.info("1️⃣  Descargando Imagen...")
        if not download_image_robust(image_url, raw_img_path):
            return None

        # PASO 3: Generar Audio
        logger.info("2️⃣  Generando Narración IA...")
        try:
            asyncio.run(generate_audio_edge(text_content, audio_path))
        except Exception as e:
            logger.error(f"❌ Falló TTS: {e}")
            return None

        # PASO 4: Renderizar Video
        logger.info("3️⃣  Renderizando Video (FFmpeg)...")
        render_success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        
        if not render_success:
            logger.error("❌ Falló Renderizado. Abortando tarea.")
            return None

        # PASO 5: Subir a YouTube
        logger.info("4️⃣  Subiendo a YouTube...")
        tags = ["noticias", "actualidad", "mundo", "ia"]
        description = f"{title}\n\nResumen de noticias generado por IA.\nSuscríbete para más.\n\n#noticias #actualidad"
        
        video_id = upload_video(final_video_path, title, description, tags)

        if video_id:
            # Marcar como procesado para que no se repita nunca más
            mark_as_processed(article_id, video_id)
            
            total_time = time.time() - start_time
            logger.info(f"🏁 TAREA COMPLETADA EN {total_time:.2f} SEGUNDOS")
            
            # Limpieza final
            logger.info("🧹 Limpiando basura temporal...")
            if os.path.exists(raw_img_path): os.remove(raw_img_path)
            if os.path.exists(audio_path): os.remove(audio_path)
            if os.path.exists(final_video_path): os.remove(final_video_path)
            
            return video_id
        else:
            logger.error("❌ Falló la subida a YouTube (todas las cuentas).")
            return None

    except Exception as e:
        logger.error(f"❌ EXCEPCIÓN NO CONTROLADA EN PROCESO: {e}")
        return None