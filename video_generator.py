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

# Configuración de Logs para ver todo en la terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Definición de carpetas de trabajo
TEMP_AUDIO = "temp_audio"
TEMP_VIDEO = "temp_video"
TEMP_IMG = "temp_processing"
OUTPUT_DIR = "output"
ASSETS_DIR = "assets_video"

# Nombre del archivo del presentador (Debe existir en assets_video/)
PRESENTER_FILENAME = "presenter.mp4"

# Color de la pantalla verde a eliminar (Hexadecimal)
CHROMA_COLOR = "0x00bf63"

# Permisos requeridos para YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Crear carpetas si no existen
for d in [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR, ASSETS_DIR]:
    os.makedirs(d, exist_ok=True)

# ==========================================
# 1. UTILIDADES Y LIMPIEZA
# ==========================================

def sanitize_filename(filename):
    """Elimina caracteres ilegales para nombres de archivo."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def sanitize_text_for_ffmpeg(text):
    """
    Limpia el texto para evitar que FFmpeg falle al escribir el título.
    - Elimina emojis y caracteres raros.
    - Elimina comillas simples y dobles.
    - Recorta el texto si es demasiado largo para la pantalla.
    """
    # Permitir letras, números, puntuación básica y tildes
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    # Quitar comillas que rompen el comando
    text = text.replace("'", "").replace('"', "").replace(":", "")
    
    # Recortar si supera los 65 caracteres (aprox 2 líneas en 720p)
    if len(text) > 65:
        text = text[:62] + "..."
    return text

def download_image_robust(url, save_path):
    """
    Sistema de descarga de imágenes 'blindado'.
    Intenta primero con Python, y si falla, usa CURL del sistema Linux.
    """
    # INTENTO 1: Python Requests (Más rápido)
    try:
        response = requests.get(url, timeout=15, verify=False)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        logger.warning(f"⚠️ Python falló descargando imagen, intentando Plan B: {e}")

    # INTENTO 2: CURL (Fuerza bruta del sistema operativo)
    try:
        cmd = [
            "curl", "-L", "-k",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "-o", save_path, url
        ]
        # Ejecutar comando silenciosamente
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Verificar que el archivo se creó y no está vacío
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True
    except Exception as e:
        logger.error(f"❌ CURL falló también. La imagen no se puede descargar: {e}")
    
    return False

# ==========================================
# 2. GENERACIÓN DE AUDIO (EDGE-TTS)
# ==========================================

async def generate_audio_edge(text, output_file):
    """
    Genera el audio de la noticia usando Microsoft Edge TTS.
    Voz configurada: Hombre (Tomás Neural).
    """
    voice = 'es-AR-TomasNeural' 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# ==========================================
# 3. RENDERIZADO DE VIDEO (FFMPEG)
# ==========================================

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """
    Construye el video final usando FFmpeg con filtros complejos.
    
    ESTRUCTURA DEL VIDEO (720x1280):
    1. Fondo: Imagen de la noticia escalada y recortada al centro.
    2. Presentador: Video con fondo verde eliminado (Chroma Key).
    3. Efecto: El presentador hace 'ping-pong' (bucle normal-reversa).
    4. Texto: Título superpuesto con sombra en la parte inferior.
    """
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    
    # Verificar que exista el video del presentador
    if not os.path.exists(presenter_path):
        logger.error(f"❌ ERROR CRÍTICO: No se encuentra '{presenter_path}'")
        return False
    
    # Intentar usar fuente del sistema (Linux), fallback a Arial generica
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "Arial" 

    clean_title = sanitize_text_for_ffmpeg(text_title)

    # --- COMANDO FFMPEG ---
    # Corrección aplicada: crop=720:1280:(iw-ow)/2:(ih-oh)/2
    # Esto calcula el centro matemáticamente: (AnchoEntrada - AnchoSalida) / 2
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,       # Entrada 0: Imagen estática
        "-i", presenter_path,                 # Entrada 1: Video Presentador
        "-i", audio_path,                     # Entrada 2: Audio TTS
        "-filter_complex",
        (
            # 1. PROCESAMIENTO DEL FONDO (Imagen)
            # Escala la imagen para que la altura sea 1280px (scale=-1:1280)
            # Luego recorta un rectángulo de 720x1280 justo en el centro matemático
            f"[0:v]scale=-1:1280,crop=720:1280:(iw-ow)/2:(ih-oh)/2[bg];"
            
            # 2. PROCESAMIENTO DEL PRESENTADOR
            # Escala el video del presentador a 720x1280
            f"[1:v]scale=720:1280[v_scaled];"
            # Aplica Chroma Key (quita el verde)
            f"[v_scaled]chromakey={CHROMA_COLOR}:0.1:0.2[v_keyed];"
            # Divide el video en 2 copias
            f"[v_keyed]split[main][reverse_copy];"
            # Invierte la segunda copia (Efecto Reversa)
            f"[reverse_copy]reverse[v_reversed];"
            # Une Normal + Reversa para hacer un bucle suave
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            # Repite el bucle infinitamente
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            
            # 3. COMPOSICIÓN (Capas)
            # Pone al presentador sobre el fondo. 'shortest=1' corta al final del audio.
            f"[bg][presenter_loop]overlay=0:0:shortest=1[comp];"
            
            # 4. TEXTO (TÍTULO)
            # Escribe el título blanco con sombra negra.
            # x=(w-text_w)/2 : Centrado horizontal
            # y=h-250 : Posición vertical (cerca del fondo)
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=42:shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"x=(w-text_w)/2:y=h-250[outv]"
        ),
        "-map", "[outv]",     # Usar el video resultante del filtro
        "-map", "2:a",        # Usar el audio TTS
        "-c:v", "libx264",    # Codec de video H.264
        "-preset", "ultrafast", # ¡CRÍTICO! Máxima velocidad para servidor pequeño
        "-r", "14",           # 14 FPS para renderizado rápido
        "-c:a", "aac",        # Codec de audio AAC
        "-b:a", "128k",       # Calidad de audio
        "-shortest",          # Asegura que el video termine cuando termine el audio
        output_path
    ]

    try:
        logger.info("🎬 Iniciando Renderizado FFmpeg (720p - Fórmula Centro)...")
        # Ejecuta el comando y espera a que termine. Si falla, lanza error.
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error fatal en FFmpeg: {e}")
        return False

# ==========================================
# 4. GESTIÓN DE YOUTUBE (ROTACIÓN DE CUENTAS)
# ==========================================

def get_authenticated_service(account_index):
    """
    Obtiene las credenciales para la cuenta especificada (0 a 5).
    Maneja el refresco de tokens automáticamente.
    """
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    # Verificar existencia de secretos
    if not os.path.exists(client_secrets_file):
        logger.error(f"❌ No existe el archivo de secretos: {client_secrets_file}")
        return None

    # Cargar token existente
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            logger.warning(f"⚠️ El token {account_index} parece estar corrupto.")

    # Validar o Refrescar Token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Guardar el token refrescado
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"❌ Error refrescando token {account_index}: {e}")
                return None
        else:
            logger.error(f"❌ Token {account_index} inválido y no se puede refrescar.")
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except HttpError as e:
        logger.error(f"❌ Error conectando con API YouTube (Cuenta {account_index}): {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="22"):
    """
    Sube el video intentando con la cuenta 0.
    Si se acaba la cuota, salta automáticamente a la cuenta 1, luego a la 2, etc.
    """
    max_accounts = 6
    
    for account_index in range(max_accounts):
        logger.info(f"🔄 Intentando subir video con Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube:
            continue

        body = {
            'snippet': {
                'title': title[:99], # Límite de YouTube: 100 caracteres
                'description': description[:4900], # Límite aprox 5000
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'public', # Cambiar a 'private' para pruebas si deseas
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            # Preparar la subida
            media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            # Ejecutar subida por partes (chunked upload)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"🚀 Subiendo... {int(status.progress() * 100)}%")

            # ÉXITO
            video_id = response.get('id')
            logger.info(f"✅ SUBIDA EXITOSA: https://youtu.be/{video_id} (Usando Cuenta {account_index})")
            return video_id

        except HttpError as e:
            # Manejo de errores específicos
            if e.resp.status in [403, 429]:
                error_content = e.content.decode('utf-8')
                if "quotaExceeded" in error_content:
                    logger.warning(f"⚠️ CUOTA EXCEDIDA en Cuenta {account_index}. Cambiando a la siguiente...")
                    continue # Salta al siguiente ciclo del loop (siguiente cuenta)
                else:
                    logger.error(f"❌ Error HTTP 403/429 (No es cuota) en Cuenta {account_index}: {e}")
            else:
                logger.error(f"❌ Error HTTP desconocido en Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado subiendo con Cuenta {account_index}: {e}")

    # Si termina el loop y no subió nada
    logger.error("❌ ERROR CRÍTICO: Todas las cuentas fallaron o están sin cuota diaria.")
    return None

# ==========================================
# 5. ORQUESTADOR PRINCIPAL (TASK PROCESSOR)
# ==========================================

def process_video_task(text_content, title, image_url, article_id):
    """
    Función principal llamada por app.py.
    Coordina todo el flujo: Descarga -> Audio -> Video -> YouTube.
    """
    start_time = time.time()
    unique_id = uuid.uuid4().hex[:8]
    
    # Rutas temporales para este proceso
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")

    logger.info(f"⚡ INICIO PROCESO ID: {article_id} (Modo 720p FIXED)")

    try:
        # PASO 1: Descargar Imagen
        logger.info(f"⬇️ Iniciando descarga de imagen...")
        if not download_image_robust(image_url, raw_img_path):
            logger.error("❌ Abortando: No se pudo descargar imagen.")
            return None

        # PASO 2: Generar Audio
        logger.info(f"🎙️ Generando audio (Voz Tomás)...")
        try:
            asyncio.run(generate_audio_edge(text_content, audio_path))
        except Exception as e:
            logger.error(f"❌ Error generando TTS: {e}")
            return None

        # PASO 3: Renderizar Video
        success = render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path)
        if not success:
            logger.error("❌ Abortando: Falló renderizado de video.")
            return None

        # PASO 4: Subir a YouTube
        logger.info("🚀 Iniciando protocolo de subida a YouTube...")
        tags = ["noticias", "actualidad", "video", "shorts", "news"]
        # Usamos el título también como descripción
        video_id = upload_video(final_video_path, title, title + "\n\n#noticias", tags)

        # PASO 5: Limpieza de archivos temporales
        logger.info("🧹 Limpiando archivos temporales...")
        if os.path.exists(raw_img_path): os.remove(raw_img_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        # Opcional: Borrar video final
        if os.path.exists(final_video_path): os.remove(final_video_path)

        total_time = time.time() - start_time
        logger.info(f"🏁 Tarea finalizada en {total_time:.2f} segundos.")
        
        return video_id

    except Exception as e:
        logger.error(f"❌ Error fatal en process_video_task: {e}")
        return None