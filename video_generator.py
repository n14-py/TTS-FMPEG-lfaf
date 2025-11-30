import os
import time
import requests 
import subprocess 
import gc 
import json
import sys # <-- NECESARIO para _print_flush
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request 
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

FRONTEND_BASE_URL = "https://noticias.lat" 

AUDIO_PATH = "temp_audio/news_audio.mp3"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"
ASSETS_DIR = "assets_video" # Directorio de las imágenes estáticas

# --- MODELO PIPER ---
PIPER_MODEL_NAME = "es_ES-carlfm-x_low"
PIPER_MODEL_DIR = "/app/models/piper" 

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# --- CONFIGURACIÓN DE LAS 4 CUENTAS ---
ACCOUNTS = [
    {"id": 0, "name": "Principal",    "secret": "client_secret_0.json", "token": "token_0.json"},
    {"id": 1, "name": "NoticiasLat1", "secret": "client_secret_1.json", "token": "token_1.json"},
    {"id": 2, "name": "NoticiasLat2", "secret": "client_secret_2.json", "token": "token_2.json"},
    {"id": 3, "name": "NoticiasLat3", "secret": "client_secret_3.json", "token": "token_3.json"}
]

LAST_ACCOUNT_FILE = "last_account_used.txt"

print("Cargando motor TTS: Piper (Ultraligero) y Sistema Multi-Cuenta")

# --- Funciones Auxiliares ---

def _print_flush(message):
    print(message)
    sys.stdout.flush()

def _report_status_to_api(endpoint, article_id, data={}):
    if not MAIN_API_URL or not ADMIN_API_KEY:
        return
    url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    payload = {"articleId": article_id, **data}
    try:
        requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e:
        _print_flush(f"ERROR CALLBACK: {e}")

# --- GESTIÓN DE ROTACIÓN DE CUENTAS ---
def get_next_account_index(current_index):
    return (current_index + 1) % len(ACCOUNTS)

def save_last_account(index):
    try:
        with open(LAST_ACCOUNT_FILE, "w") as f:
            f.write(str(index))
    except:
        pass

def load_last_account():
    try:
        if os.path.exists(LAST_ACCOUNT_FILE):
            with open(LAST_ACCOUNT_FILE, "r") as f:
                return int(f.read().strip())
    except:
        pass
    return 0

def get_authenticated_service(account_idx):
    account = ACCOUNTS[account_idx]
    _print_flush(f"🔑 [Auth] Probando cuenta {account['id']} ({account['name']})...")
    
    if not os.path.exists(account['token']):
        _print_flush(f"⚠️ [Auth] Falta el archivo {account['token']}. Saltando cuenta.")
        return None

    try:
        creds = Credentials.from_authorized_user_file(account['token'], SCOPES)
        
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                _print_flush(f"🔄 [Auth] Refrescando token para {account['name']}...")
                creds.refresh(Request())
                with open(account['token'], 'w') as token:
                    token.write(creds.to_json())
            else:
                _print_flush(f"❌ [Auth] Token inválido e irrecuperable para {account['name']}.")
                return None
                
        # cache_discovery=False para ahorrar RAM y evitar problemas de inicialización
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds, cache_discovery=False) 
    except Exception as e:
        _print_flush(f"❌ [Auth] Error en cuenta {account['id']}: {e}")
        return None

def get_audio_duration(file_path):
    """Obtiene la duración del audio usando ffprobe."""
    try:
        command = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        _print_flush(f"⚠️ Error duración audio: {e}. Default 0.")
        return 0

# --- Función CRÍTICA de Optimización de RAM ---
def resize_input_image(input_path, max_dim=1280):
    """
    PRE-ESCALADO CRÍTICO: Reescala la imagen de fondo ANTES de que FFmpeg inicie
    el pipeline principal, previniendo el error "Ran out of memory" por imágenes 4K.
    """
    name, ext = os.path.splitext(input_path)
    resized_path = f"{name}_resized{ext}"
    
    if os.path.exists(resized_path): return resized_path

    _print_flush("🖼️ Revisando tamaño de imagen de fondo (RAM Fix)...")

    try:
        # 1. Usar ffprobe para obtener la resolución
        probe_command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", 
            "stream=width,height", "-of", "csv=p=0:s=x", input_path
        ]
        result = subprocess.run(probe_command, capture_output=True, text=True, check=True)
        width, height = map(int, result.stdout.strip().split('x'))
        
        if width <= max_dim and height <= max_dim:
            _print_flush("✅ Imagen ya optimizada (o pequeña).")
            return input_path
        
        _print_flush(f"⚠️ Imagen muy grande ({width}x{height}). Reescalando a max {max_dim}px...")
        
        # 2. Reescalar la imagen con FFmpeg (comando ligero)
        scale_command = [
            "ffmpeg", "-y", "-i", input_path, 
            "-vf", f"scale='min({max_dim},iw)':'min({max_dim},ih)'", 
            "-q:v", "5", resized_path # -q:v 5 es buena calidad/compresión
        ]
        subprocess.run(scale_command, check=True, stderr=subprocess.DEVNULL)
        
        if os.path.exists(resized_path):
            return resized_path
        else:
            raise Exception("No se pudo reescalar la imagen.")

    except Exception as e:
        _print_flush(f"❌ Error al pre-escalar imagen: {e}. Usando original (¡RIESGO DE RAM!).")
        return input_path 


# --- PASO 1: Generar Audio (PIPER) ---
def generar_audio(text):
    _print_flush("🎙️ Generando audio (Piper)...")
    if os.path.exists(AUDIO_PATH): os.remove(AUDIO_PATH)
    
    command = [
        "piper",
        "--model", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx"),
        "--config", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx.json"),
        "--output_file", AUDIO_PATH
    ]
    try:
        subprocess.run(command, input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
        if not os.path.exists(AUDIO_PATH): raise Exception("No se generó audio")
    except Exception as e:
        raise Exception(f"Piper Error: {e}")
    
    _print_flush("✅ Audio guardado.")
    return AUDIO_PATH


# --- PASO 2: Generar Video (FFMPEG EXTREMADAMENTE OPTIMIZADO + Overlays + Crop) ---
def generar_video_ia(audio_path, imagen_path):
    _print_flush("🎬 Generando video (FFmpeg, 720p, 1 FPS, Cropping)...")
    
    # Limpieza de RAM antes de llamar a FFmpeg (CRÍTICO)
    gc.collect() 

    audio_duration = get_audio_duration(audio_path)
    # El Outro aparece 5 segundos antes del final
    outro_start_time = max(0, audio_duration - 5) 

    # --- RUTAS DE ASSETS (Definidas localmente) ---
    IMAGE_OUTRO_PATH = os.path.join(ASSETS_DIR, "outro_final.png") 
    
    ASSETS_TIMING = [
        {'path': os.path.join(ASSETS_DIR, "overlay_subscribe_like.png"), 'start': 1, 'end': 2}, 
        {'path': os.path.join(ASSETS_DIR, "overlay_like.png"), 'start': 2, 'end': 3},      
        {'path': os.path.join(ASSETS_DIR, "overlay_bell.png"), 'start': 3, 'end': 4},      
        {'path': os.path.join(ASSETS_DIR, "overlay_comment.png"), 'start': 4, 'end': 5},   
    ]

    # --- CONSTRUCCIÓN DINÁMICA DE INPUTS ---
    inputs = []
    # Input 0: Fondo de Noticia (Imagen pre-escalada)
    inputs.append(f"-loop 1 -i \"{imagen_path}\"")       
    # Input 1: Audio
    inputs.append(f"-i \"{audio_path}\"")                
    
    overlay_assets = []
    next_idx = 2
    
    # 2. Agregar Overlays Temporales
    for asset in ASSETS_TIMING:
        if os.path.exists(asset['path']):
            inputs.append(f"-loop 1 -i \"{asset['path']}\"")
            overlay_assets.append({'idx': next_idx, 'start': asset['start'], 'end': asset['end']})
            next_idx += 1
            
    # 3. Agregar Outro Final
    has_outro = os.path.exists(IMAGE_OUTRO_PATH) 
    if has_outro:
        inputs.append(f"-loop 1 -i \"{IMAGE_OUTRO_PATH}\"") 
        outro_idx = next_idx

    # --- CADENA DE FILTROS ---
    
    # 1. Filtro Base (Escalar y CROP para ELIMINAR BARRAS NEGRAS)
    # scale=...increase -> FUERZA a que la imagen llene el cuadro 1280x720, cortando los bordes
    # crop=1280:720 -> Se asegura que la imagen de fondo siempre sea exactamente 1280x720
    filter_chain = "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1[bg];"
    last_stream = "[bg]"
    stream_counter = 1

    # 2. Aplicar los Overlays Temporales
    for asset in overlay_assets:
        next_stream_name = f"[v{stream_counter}]"
        # Posición: (W-w)/2:100 (centrado horizontal, a 100px del borde superior)
        filter_chain += (
            f"{last_stream}[{asset['idx']}:v]overlay=(W-w)/2:100:enable='between(t,{asset['start']},{asset['end']})'{next_stream_name};"
        )
        last_stream = next_stream_name
        stream_counter += 1

    # 3. Aplicar el Outro Final
    if has_outro:
        filter_chain += (
            f"{last_stream}[{outro_idx}:v]overlay=0:0:enable='gte(t,{outro_start_time})'[outv]"
        )
        final_map_stream = "[outv]"
    else:
        final_map_stream = last_stream


    # COMANDO FINAL (Optimización Extrema de Render: ultrafast, crf 28, 1 FPS, 1 Hilo)
    cmd = (
        f"ffmpeg -y -hide_banner -loglevel error "
        f"{' '.join(inputs)} "
        f"-filter_complex \"{filter_chain}\" "
        f"-map \"{final_map_stream}\" -map 1:a "
        f"-c:v libx264 -preset ultrafast -tune animation -crf 28 -r 1 -threads 1 " 
        f"-c:a aac -b:a 64k -ac 1 " 
        f"-pix_fmt yuv420p -shortest "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    subprocess.run(cmd, shell=True, check=True)
    _print_flush("✅ Video guardado.")
    return FINAL_VIDEO_PATH

# --- PASO 3: Subir a YouTube (Original) ---
def subir_a_youtube_rotativo(video_path, title, full_text, article_id):
    _print_flush("Iniciando Paso 3: Subiendo a YouTube con Rotación de Cuentas...")
    
    gc.collect()

    start_index = load_last_account()
    _print_flush(f"🚀 Cuenta inicial sugerida: {start_index}")
    
    attempts = 0
    max_attempts = len(ACCOUNTS)
    current_idx = start_index

    while attempts < max_attempts:
        youtube = get_authenticated_service(current_idx)
        
        if youtube:
            try:
                # --- LÓGICA DE TÍTULO Y DESCRIPCIÓN (Original Restaurada) ---
                suffix = " // Noticias.lat"
                max_title_length = 98 - len(suffix) 
                clean_title = title.strip()
                if len(clean_title) > max_title_length:
                    clean_title = clean_title[:max_title_length - 3].strip() + "..."
                final_title = f"{clean_title}{suffix}"
                
                article_link = f"{FRONTEND_BASE_URL}/articulo/{article_id}"
                home_link = "https://www.noticias.lat/"
                
                intro_line = f"Lee la noticia completa aquí: {article_link}"
                outro_line = f"Visita nuestra web: {home_link}"
                
                reserved_chars = len(intro_line) + len(outro_line) + 100 
                max_text_chars = 5000 - reserved_chars
                
                safe_text = full_text.strip()
                if len(safe_text) > max_text_chars:
                    safe_text = safe_text[:max_text_chars].strip() + "..."

                final_description = (
                    f"{intro_line}\n\n"
                    f"{safe_text}\n\n"
                    f"{outro_line}"
                )
                
                _print_flush(f"Longitud Descripción: {len(final_description)} caracteres.")
                
                request_body = {
                    'snippet': {
                        'title': final_title,
                        'description': final_description,
                        'tags': ['noticias', 'noticiaslat', 'actualidad'],
                        'categoryId': '25' 
                    },
                    'status': {
                        'privacyStatus': 'public',
                        'selfDeclaredMadeForKids': False
                    }
                }

                # Usamos chunksize=1MB para uploads más estables
                media_file = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)

                _print_flush(f"📤 Intentando subir a Cuenta {current_idx}...")
                response_upload = youtube.videos().insert(
                    part='snippet,status',
                    body=request_body,
                    media_body=media_file
                ).execute()
                
                video_id = response_upload.get('id')
                _print_flush(f"✅ ¡SUBIDA EXITOSA! ID: {video_id} en Cuenta {current_idx}")
                
                save_last_account(current_idx)
                return video_id

            except HttpError as e:
                error_content = e.content.decode('utf-8')
                if e.resp.status in [403, 429] and ("quotaExceeded" in error_content or "daily limit" in error_content):
                    _print_flush(f"⛔ CUOTA AGOTADA en Cuenta {current_idx}. Cambiando a la siguiente...")
                else:
                    _print_flush(f"❌ Error HTTP no relacionado con cuota: {e}")
            except Exception as e:
                _print_flush(f"❌ Error desconocido al subir: {e}")
                
        
        current_idx = get_next_account_index(current_idx)
        attempts += 1
        _print_flush(f"🔄 Rotando a Cuenta {current_idx}...")
        time.sleep(2) 

    raise Exception("❌ TODAS las cuentas han fallado o están sin cuota.")

# --- PROCESO PRINCIPAL (Modificado para usar resize_input_image y limpiar) ---
def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    audio_file = None
    video_file = None
    optimized_img_path = anchor_image_path # Inicializamos al original

    try:
        _print_flush("--------------------------------------------------")
        _print_flush("INICIO DE TRABAJO. Forzando limpieza inicial.")
        gc.collect()

        # 1. Audio
        audio_file = generar_audio(text_content)
        if not audio_file: raise Exception("Falló audio")
        
        _print_flush("1/3 Completado. Forzando limpieza de Piper.")
        gc.collect()

        # 1.5. OPTIMIZACIÓN DE IMAGEN (NUEVO PASO CRÍTICO DE RAM)
        optimized_img_path = resize_input_image(anchor_image_path)
        
        # 2. Video
        # Usamos la imagen ya optimizada
        video_file = generar_video_ia(audio_file, optimized_img_path) 
        if not video_file: raise Exception("Falló video")
        
        _print_flush("2/3 Completado. Forzando limpieza de FFmpeg.")
        gc.collect()

        # 3. Subida (USANDO EL NUEVO SISTEMA ROTATIVO)
        youtube_id = subir_a_youtube_rotativo(video_file, title, text_content, article_id)
        if not youtube_id: raise Exception("Falló subida")

        _print_flush(f"✅ FINALIZADO CON ÉXITO: {article_id}")
        _report_status_to_api("video_complete", article_id, {"youtubeId": youtube_id})

    except Exception as e:
        _print_flush(f"❌ FALLO: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
    
    finally:
        _print_flush("🧹 LIMPIEZA FINAL DE ARCHIVOS Y RAM...")
        
        # Eliminar audio
        if audio_file and os.path.exists(audio_file): 
            try: os.remove(audio_file)
            except: pass
            
        # Eliminar video
        if video_file and os.path.exists(video_file): 
            try: os.remove(video_file)
            except: pass
            
        # Eliminar imagen reescalada (si se creó y es diferente a la original)
        if optimized_img_path != anchor_image_path and os.path.exists(optimized_img_path):
            try: os.remove(optimized_img_path)
            except: pass
            
        # La imagen ORIGINAL (anchor_image_path) la elimina el app.py
        
        _print_flush("✨ Limpieza de RAM completa. Sistema listo.")
        gc.collect()