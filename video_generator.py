# -*- coding: utf-8 -*-
"""
Generador de Video Automatizado para Noticias.lat
-------------------------------------------------
Este script se encarga de:
1. Descargar la imagen de la noticia.
2. Generar el audio usando Microsoft Edge TTS.
3. Renderizar el video con FFmpeg (Chroma Key para el presentador).
4. Subir el video a YouTube rotando entre 4 cuentas.
"""

import os
import time
import logging
import asyncio
import re
import subprocess
import uuid
import textwrap
import shutil
import glob
from datetime import datetime
import requests

# --- LIBRERÍAS DE GOOGLE Y YOUTUBE ---
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# --- LIBRERÍA DE TTS ---
import edge_tts

# ==============================================================================
# 1. CONFIGURACIÓN GENERAL DEL SISTEMA
# ==============================================================================

# Configuración de Logs para ver todo en la consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

# Directorios de trabajo
BASE_DIR = os.getcwd()
TEMP_AUDIO = os.path.join(BASE_DIR, "temp_audio")
TEMP_VIDEO = os.path.join(BASE_DIR, "temp_video")
TEMP_IMG = os.path.join(BASE_DIR, "temp_processing")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ASSETS_DIR = os.path.join(BASE_DIR, "assets_video")
LOCKS_DIR = os.path.join(BASE_DIR, "locks_history") 

# Nombre del archivo del presentador con pantalla verde
PRESENTER_FILENAME = "presenter.mp4"

# Ajustes Avanzados para FFmpeg (Chroma Key / Pantalla Verde)
CHROMA_COLOR = "0x00bf63" 
CHROMA_SIMILARITY = "0.15" 
CHROMA_BLEND = "0.05"

# Ajustes de YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# IMPORTANTE: Límite de cuentas para la rotación (0, 1, 2, 3)
MAX_ACCOUNTS = 4 


# ==============================================================================
# 2. LIMPIEZA INICIAL DEL SERVIDOR
# ==============================================================================

def initial_cleanup():
    """
    Función que limpia basura vieja si el servidor se reinició por un error previo.
    Evita que el disco duro se llene con el tiempo.
    """
    logger.info("🧹 Ejecutando limpieza inicial de directorios temporales...")
    folders = [TEMP_AUDIO, TEMP_VIDEO, TEMP_IMG, OUTPUT_DIR]
    
    for folder in folders:
        # Si la carpeta no existe, la creamos
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
                logger.info(f"📁 Carpeta creada: {folder}")
            except Exception as e:
                logger.error(f"❌ Error creando carpeta {folder}: {e}")
        else:
            # Si existe, borramos los archivos dentro de ella
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo borrar {file_path}: {e}")

# Ejecutamos la limpieza inmediatamente al arrancar el script
initial_cleanup()


# ==============================================================================
# 3. FUNCIONES AUXILIARES Y DE CONTROL (ROTACIÓN Y BLOQUEOS)
# ==============================================================================

def get_next_account_index():
    """
    Calcula qué cuenta de YouTube toca usar hoy (0->1->2->3->0...)
    Guarda el estado en un archivo de texto para no perder la cuenta si se reinicia.
    """
    rotator_file = os.path.join(LOCKS_DIR, "account_rotator.txt")
    
    # Asegurar que existe el directorio de bloqueos
    if not os.path.exists(LOCKS_DIR):
        os.makedirs(LOCKS_DIR, exist_ok=True)

    current_index = 0
    
    # Leemos cuál fue el último canal que usamos
    if os.path.exists(rotator_file):
        try:
            with open(rotator_file, 'r') as f:
                current_index = int(f.read().strip())
        except Exception as e:
            logger.warning(f"⚠️ Error leyendo archivo de rotación, asumiendo 0: {e}")
            current_index = 0
    
    # Calculamos el siguiente canal a usar
    next_index = (current_index + 1) % MAX_ACCOUNTS
    
    # Guardamos el nuevo canal para el futuro
    try:
        with open(rotator_file, 'w') as f:
            f.write(str(next_index))
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar el archivo de rotación: {e}")

    logger.info(f"🔄 ROTACIÓN DE CANALES: Toca usar Cuenta {next_index} (La anterior fue {current_index})")
    return next_index

def is_already_processed(article_id):
    """Verifica si la noticia ya se procesó anteriormente buscando su archivo .done"""
    if not article_id: return False
    return os.path.exists(os.path.join(LOCKS_DIR, f"{article_id}.done"))

def mark_as_processed(article_id, video_id):
    """Crea un archivo .done para que esta noticia no se vuelva a hacer en el futuro"""
    if not article_id: return
    try:
        if not os.path.exists(LOCKS_DIR):
            os.makedirs(LOCKS_DIR, exist_ok=True)
            
        done_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
        with open(done_file, 'w') as f:
            f.write(f"Processed at {datetime.now()} - YouTube ID: {video_id}")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar el archivo de bloqueo para {article_id}: {e}")

def prepare_text_for_video(text):
    """Limpia el título para que FFmpeg lo pueda renderizar sin errores de caracteres raros"""
    # Quitamos caracteres que puedan romper FFmpeg
    text = re.sub(r'[^\w\s\.\,\!\?\-áéíóúÁÉÍÓÚñÑ]', '', text)
    text = text.replace("'", "").replace('"', "").replace(":", "")
    
    # Ajustamos el ancho del texto para que no se salga de la pantalla
    wrapper = textwrap.TextWrapper(width=45) 
    word_list = wrapper.wrap(text=text)
    
    # Limitamos a 3 líneas máximo en la pantalla
    if len(word_list) > 3:
        return "\n".join(word_list[:3]) + "..."
    return "\n".join(word_list)

def download_image_robust(url, save_path, retries=3):
    """Descarga la imagen de la noticia con alta tolerancia a fallos"""
    logger.info(f"⬇️ Iniciando descarga de imagen: {url}")
    
    for attempt in range(retries):
        try:
            # INTENTO 1: Usamos CURL porque es más rápido y estable en Linux
            cmd = ["curl", "-L", "-k", "--retry", "2", "-o", save_path, url]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Verificamos que la imagen realmente pesa algo (no está vacía)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                return True
                
        except Exception as e:
            logger.warning(f"⚠️ Intento {attempt+1} fallido con curl. Usando método alternativo.")
            try:
                # INTENTO 2: Fallback usando Python Requests
                time.sleep(1)
                r = requests.get(url, verify=False, timeout=15)
                if r.status_code == 200:
                    with open(save_path, 'wb') as f: 
                        f.write(r.content)
                    return True
            except Exception as e2:
                logger.error(f"❌ Error también en Requests: {e2}")
                pass
                
    logger.error("❌ No se pudo descargar la imagen después de todos los intentos.")
    return False


# ==============================================================================
# 4. GENERADORES DE AUDIO (TTS) Y VIDEO (FFMPEG)
# ==============================================================================

async def generate_audio_edge(text, output_file):
    """Genera la voz en off utilizando Microsoft Edge TTS"""
    try:
        logger.info("🎙️ Generando audio TTS...")
        communicate = edge_tts.Communicate(text, 'es-AR-TomasNeural')
        await communicate.save(output_file)
        
        # Validar que el audio se creó correctamente
        return os.path.exists(output_file) and os.path.getsize(output_file) > 100
    except Exception as e:
        logger.error(f"❌ Error fatal en generación TTS: {e}")
        return False

def render_video_ffmpeg(image_path, audio_path, text_title, output_path):
    """Renderiza el video final uniendo la imagen de fondo, el presentador y el audio"""
    presenter_path = os.path.join(ASSETS_DIR, PRESENTER_FILENAME)
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    clean_title = prepare_text_for_video(text_title)

    if not os.path.exists(presenter_path):
        logger.error(f"❌ No se encontró el video del presentador en la ruta: {presenter_path}")
        return False

    # Comando ultra complejo de FFmpeg para lograr el efecto profesional
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", presenter_path,
        "-i", audio_path,
        "-filter_complex",
        (
            f"[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720:(iw-ow)/2:(ih-oh)/2[bg];"
            f"[1:v]scale=-1:720[v_scaled];"
            f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
            f"[v_keyed]split[main][reverse_copy];"
            f"[reverse_copy]reverse[v_reversed];"
            f"[main][v_reversed]concat=n=2:v=1:a=0[boomerang];"
            f"[boomerang]loop=-1:size=32767:start=0[presenter_loop];"
            f"[bg][presenter_loop]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
            f"[comp]drawtext=fontfile='{font_path}':text='{clean_title}':"
            f"fontcolor=white:fontsize=40:line_spacing=12:"
            f"shadowcolor=black@1.0:shadowx=4:shadowy=4:"
            f"x=30:y=h-145[outv]"
        ),
        "-map", "[outv]", "-map", "2:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-r", "24",
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path
    ]

    try:
        # TIMEOUT CONFIGURADO EN 600s (10 minutos) PARA EVITAR BLOQUEOS DEL SERVIDOR
        logger.info("🎬 Iniciando renderizado de Video en FFmpeg (Timeout: 600s)...")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        
        # Validamos que el video final se creó correctamente
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        
    except subprocess.TimeoutExpired:
        logger.error("❌ ERROR CRÍTICO: El renderizado superó los 10 minutos (Timeout). Cancelando proceso para no saturar el servidor.")
        return False
    except subprocess.CalledProcessError as err:
        logger.error(f"❌ Fallo interno en FFmpeg (Posible falta de RAM o archivo corrupto).")
        return False


# ==============================================================================
# 5. GESTIÓN Y SUBIDA A YOUTUBE (CON ROTACIÓN)
# ==============================================================================

def get_authenticated_service(account_index):
    """Obtiene el servicio autenticado de YouTube para una cuenta específica"""
    creds = None
    token_file = f'token_{account_index}.json'
    client_secrets_file = f'client_secret_{account_index}.json'

    # Verificamos si los archivos de Google existen
    if not os.path.exists(client_secrets_file) and not os.path.exists(token_file):
        logger.error(f"❌ Faltan archivos de autenticación para la cuenta {account_index}")
        return None

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            logger.warning(f"⚠️ Error leyendo {token_file}: {e}")
            pass

    # Si el token expiró, intentamos refrescarlo automáticamente
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
            return None

    try:
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ Error construyendo el servicio de YouTube: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="25"):
    """
    Sube el video aplicando el sistema de Rotación Inteligente.
    """
    
    # 1. Obtenemos qué cuenta nos toca usar en este turno
    start_index = get_next_account_index()

    # 2. Bucle de subida (Si la cuenta asignada falla, intenta con las siguientes)
    for i in range(MAX_ACCOUNTS):
        # Fórmula matemática para rotar: 0,1,2,3 y volver a 0
        account_index = (start_index + i) % MAX_ACCOUNTS
        
        logger.info(f"📡 Intentando subida con Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube: 
            logger.warning(f"⚠️ Cuenta {account_index} no disponible o no configurada. Saltando.")
            continue 

        # Cuerpo de la petición a YouTube
        body = {
            'snippet': {
                'title': title[:99],
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
            logger.info("🚀 Enviando paquete de video a los servidores de YouTube...")
            
            while response is None:
                status, response = request.next_chunk()
            
            video_id = response.get('id')
            logger.info(f"✅ ¡SUBIDA EXITOSA! El video está en la Cuenta {account_index}: https://youtu.be/{video_id}")
            return video_id

        except HttpError as e:
            # Si nos da error 403 (Cuota llena), logueamos y pasamos a la siguiente cuenta
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"⚠️ CUOTA LLENA en Cuenta {account_index}. Pasando al siguiente canal de emergencia.")
                continue
            else:
                logger.error(f"❌ Error HTTP en subida de Cuenta {account_index}: {e}")
        except Exception as e:
            logger.error(f"❌ Error general inesperado en Cuenta {account_index}: {e}")

    logger.error("❌ ERROR CRÍTICO EN SUBIDA: Se agotaron todas las cuentas disponibles.")
    return None


# ==============================================================================
# 6. ORQUESTADOR PRINCIPAL (LA FUNCIÓN MAESTRA)
# ==============================================================================

def process_video_task(text_content, title, image_url, article_id, article_url=""):
    """
    Esta es la función que manda a llamar app.py. Controla todo el ciclo de vida de la noticia.
    """
    logger.info(f"⚡ INICIANDO TAREA MAESTRA PARA ID: {article_id}")

    # Filtro de seguridad inicial
    if is_already_processed(article_id):
        logger.info("⏭️ Esta noticia ya fue procesada anteriormente.")
        return "ALREADY_PROCESSED"

    # Definimos rutas únicas para los archivos temporales de esta tarea
    unique_id = uuid.uuid4().hex[:8]
    raw_img_path = os.path.join(TEMP_IMG, f"{unique_id}_raw.jpg")
    audio_path = os.path.join(TEMP_AUDIO, f"{unique_id}.mp3")
    final_video_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")
    
    # LISTA DE BASURA A BORRAR AL FINALIZAR
    files_to_clean = [raw_img_path, audio_path, final_video_path]

    try: 
        # ---------------------------------------------------------
        # PASO 1: IMAGEN
        # ---------------------------------------------------------
        if not download_image_robust(image_url, raw_img_path): 
            logger.error("Fallo al descargar la imagen. Abortando tarea.")
            return None

        # ---------------------------------------------------------
        # PASO 2: AUDIO
        # ---------------------------------------------------------
        text_to_read = text_content if text_content and len(text_content) > 10 else title
        try:
            asyncio.run(generate_audio_edge(text_to_read, audio_path))
        except Exception as e_tts:
            logger.error(f"Error en bloque de TTS asyncio: {e_tts}")
            return None

        # ---------------------------------------------------------
        # PASO 3: RENDERIZADO DE VIDEO (FFMPEG)
        # ---------------------------------------------------------
        if not render_video_ffmpeg(raw_img_path, audio_path, title, final_video_path): 
            logger.error("Fallo durante el renderizado del video.")
            return None

        # ---------------------------------------------------------
        # PASO 4: CONSTRUCCIÓN DE LA DESCRIPCIÓN 
        # ---------------------------------------------------------
        logger.info("✍️ Construyendo descripción para YouTube...")
        
        # 4.1. LÓGICA DE LA URL (Debe ir ARRIBA y usar /articulo/)
        if article_url and "http" in str(article_url):
            final_link = article_url
        else:
            # Si no hay URL de la API, la forzamos con la estructura correcta
            final_link = f"https://www.noticias.lat/articulo/{article_id}"
            
        desc = f"🔗 LEER NOTA COMPLETA AQUÍ:\n{final_link}\n\n"
        
        # 4.2. TÍTULO Y CUERPO (Limitado a 4000 caracteres por reglas de YouTube)
        full_text_truncated = text_content[:4000] if text_content else title
        desc += f"{title}\n\n"
        desc += "------------------------------------------------\n"
        desc += f"{full_text_truncated}\n\n"

        # 4.3. PUBLICIDAD (Relax Station)
        desc += "🧘 ¿Estás estresado y quieres relajarte?\n"
        desc += "👉 https://www.youtube.com/@DesdeRelaxStation/streams\n\n"

        # 4.4. HASHTAGS GLOBALES
        desc += "#noticias #actualidad #internacional"
        
        # ---------------------------------------------------------
        # PASO 5: SUBIDA A YOUTUBE
        # ---------------------------------------------------------
        video_id = upload_video(final_video_path, title, desc, ["noticias"])

        if video_id:
            # Marcamos como completado para que no se repita
            mark_as_processed(article_id, video_id)
            logger.info(f"🏁 TAREA FINALIZADA CON ÉXITO: {video_id}")
            return video_id
            
        return None

    except Exception as general_error:
        logger.error(f"❌ Error Fatal no capturado en proceso general: {general_error}")
        return None
    
    finally:
        # =======================================================================
        # 🧹 ZONA DE LIMPIEZA OBLIGATORIA (SE EJECUTA TENGA ÉXITO O FALLE)
        # =======================================================================
        logger.info("🧹 Iniciando proceso de limpieza para liberar memoria del servidor...")
        for f in files_to_clean:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    logger.debug(f"Archivo eliminado: {f}")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ No se pudo borrar el archivo temporal {f}: {cleanup_error}")
        
        # Invocamos al recolector de basura de Python para vaciar la RAM
        import gc
        gc.collect()
        logger.info("✨ Limpieza completada.")