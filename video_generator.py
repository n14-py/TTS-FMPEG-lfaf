import os
import time
import requests 
import subprocess 
import gc 
import json
import sys
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
ASSETS_DIR = "assets_video" 

# --- MODELO PIPER ---
PIPER_MODEL_NAME = "es_ES-carlfm-x_low"
PIPER_MODEL_DIR = "/app/models/piper" 

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# --- CONFIGURACIÓN DE CUENTAS ---
ACCOUNTS = [
    {"id": 0, "name": "Principal",    "secret": "client_secret_0.json", "token": "token_0.json"},
    {"id": 1, "name": "NoticiasLat1", "secret": "client_secret_1.json", "token": "token_1.json"},
    {"id": 2, "name": "NoticiasLat2", "secret": "client_secret_2.json", "token": "token_2.json"},
    {"id": 3, "name": "NoticiasLat3", "secret": "client_secret_3.json", "token": "token_3.json"},
    {"id": 4, "name": "NoticiasLat4", "secret": "client_secret_4.json", "token": "token_4.json"},
    {"id": 5, "name": "NoticiasLat5", "secret": "client_secret_5.json", "token": "token_5.json"}
]

LAST_ACCOUNT_FILE = "last_account_used.txt"

print("Cargando motor TTS: Piper (Ultraligero) y Sistema Multi-Cuenta Optimizado (Modo 480p/10fps)")

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
        requests.post(url, json=payload, headers=headers, timeout=10)
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
                
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds, cache_discovery=False) 
    except Exception as e:
        _print_flush(f"❌ [Auth] Error en cuenta {account['id']}: {e}")
        return None

# --- Optimización de RAM para Imagen ---
def resize_input_image(input_path, max_dim=854): # Bajamos a 854px (480p ancho)
    """
    Reescala agresivamente para evitar OOM en plan Free.
    """
    name, ext = os.path.splitext(input_path)
    resized_path = f"{name}_resized{ext}"
    
    if os.path.exists(resized_path): return resized_path

    try:
        # Medimos primero
        probe_command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", 
            "stream=width,height", "-of", "csv=p=0:s=x", input_path
        ]
        result = subprocess.run(probe_command, capture_output=True, text=True, check=True)
        width, height = map(int, result.stdout.strip().split('x'))
        
        # Si es pequeña, la dejamos
        if width <= max_dim and height <= max_dim:
            return input_path
        
        _print_flush(f"⚠️ Reescalando imagen grande ({width}x{height}) a 480p para proteger RAM...")
        
        # Escalado rápido
        scale_command = [
            "ffmpeg", "-y", "-i", input_path, 
            "-vf", f"scale='min({max_dim},iw)':'min({max_dim},ih)'", 
            "-q:v", "10", # Calidad media-baja para el temp, ahorra espacio
            resized_path 
        ]
        subprocess.run(scale_command, check=True, stderr=subprocess.DEVNULL)
        
        return resized_path if os.path.exists(resized_path) else input_path

    except Exception as e:
        _print_flush(f"Aviso imagen: {e}. Usando original.")
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
    
    return AUDIO_PATH


# --- PASO 2: Generar Video (FFMPEG TURBO - MODO FREE TIER) ---
def generar_video_ia(audio_path, imagen_path):
    _print_flush("🎬 Generando video 480p @ 10fps (Modo Ahorro)...")
    
    # Overlays estáticos
    ASSETS_TIMING = [
        {'path': os.path.join(ASSETS_DIR, "overlay_subscribe_like.png"), 'start': 1, 'end': 4}, 
        {'path': os.path.join(ASSETS_DIR, "overlay_like.png"), 'start': 4, 'end': 7},      
        {'path': os.path.join(ASSETS_DIR, "overlay_bell.png"), 'start': 7, 'end': 10},      
        {'path': os.path.join(ASSETS_DIR, "overlay_comment.png"), 'start': 10, 'end': 13},   
    ]

    inputs = []
    inputs.append(f"-loop 1 -i \"{imagen_path}\"")       
    inputs.append(f"-i \"{audio_path}\"")                
    
    overlay_assets = []
    next_idx = 2
    
    for asset in ASSETS_TIMING:
        if os.path.exists(asset['path']):
            inputs.append(f"-loop 1 -i \"{asset['path']}\"")
            overlay_assets.append({'idx': next_idx, 'start': asset['start'], 'end': asset['end']})
            next_idx += 1
            
    # --- FILTRO OPTIMIZADO PARA 480p ---
    # 1. Bajamos la resolución base a 854x480 (480p)
    filter_chain = "[1:a]atempo=0.95[audio_out];"
    filter_chain += (
        "[0:v]scale=854:480:force_original_aspect_ratio=decrease,setsar=1,"
        "pad=854:480:(ow-iw)/2:(oh-ih)/2[bg];"
    )
    last_stream = "[bg]"
    stream_counter = 1

    for asset in overlay_assets:
        next_stream_name = f"[v{stream_counter}]"
        # Escalamos los overlays si son muy grandes, o los ponemos directos
        # (Para ahorrar CPU asumimos que encajan, si no, se verán grandes pero funcionará)
        filter_chain += (
            f"{last_stream}[{asset['idx']}:v]overlay=(W-w)/2:10:enable='between(t,{asset['start']},{asset['end']})'{next_stream_name};"
        )
        last_stream = next_stream_name
        stream_counter += 1

    filter_chain = filter_chain.rstrip(';')
    final_map_stream = last_stream

    # --- COMANDO EXTREMO PARA PLAN FREE ---
    cmd = (
        f"ffmpeg -y -hide_banner -loglevel error "
        f"{' '.join(inputs)} "
        f"-filter_complex \"{filter_chain}\" "
        f"-map \"{final_map_stream}\" -map [audio_out] "
        
        # OPCIONES DE CALIDAD / VELOCIDAD
        f"-r 10 "                    # FPS: Bajamos a 10 FPS (Mucho menos CPU)
        f"-ar 24000 "                # Audio: 24kHz (Suficiente para voz)
        f"-c:v libx264 "             # Codec Video
        f"-preset ultrafast "        # Velocidad máxima de encoding
        f"-tune stillimage "         # Optimización para imágenes estáticas
        f"-crf 35 "                  # Compresión alta (Archivos livianos, subida rápida)
        f"-c:a aac -b:a 48k -ac 1 "  # Audio mono bajo bitrate
        f"-pix_fmt yuv420p -shortest "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    subprocess.run(cmd, shell=True, check=True)
    return FINAL_VIDEO_PATH

# --- PASO 3: Subir a YouTube (Optimizado) ---
def subir_a_youtube_rotativo(video_path, title, full_text, article_id):
    _print_flush("🚀 Subiendo a YouTube...")
    
    start_index = load_last_account()
    attempts = 0
    max_attempts = len(ACCOUNTS)
    current_idx = start_index

    while attempts < max_attempts:
        youtube = get_authenticated_service(current_idx)
        
        if youtube:
            try:
                suffix = " // Noticias.lat"
                max_title_length = 98 - len(suffix) 
                clean_title = title.strip()[:max_title_length].strip()
                final_title = f"{clean_title}{suffix}"
                
                article_link = f"{FRONTEND_BASE_URL}/articulo/{article_id}"
                home_link = "https://www.noticias.lat/"
                
                intro_line = f"Lee la noticia completa aquí: {article_link}"
                outro_line = f"Visita nuestra web: {home_link}"
                
                final_description = (
                    f"{intro_line}\n\n"
                    f"{full_text.strip()[:4000]}...\n\n"
                    f"{outro_line}"
                )
                
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

                # Chunk pequeño para conexiones inestables o servidores lentos
                media_file = MediaFileUpload(video_path, chunksize=4*1024*1024, resumable=True)

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
                    _print_flush(f"⛔ CUOTA AGOTADA en Cuenta {current_idx}. Rotando...")
                else:
                    _print_flush(f"❌ Error HTTP: {e}")
            except Exception as e:
                _print_flush(f"❌ Error subida: {e}")
                
        current_idx = get_next_account_index(current_idx)
        attempts += 1
        time.sleep(1) 

    raise Exception("❌ TODAS las cuentas fallaron.")

# --- PROCESO PRINCIPAL ---
def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    audio_file = None
    video_file = None
    optimized_img_path = anchor_image_path 

    try:
        _print_flush(f"⚡ INICIO TAREA (Modo Free): {article_id}")
        gc.collect() # Limpieza inicial

        # 1. Audio
        audio_file = generar_audio(text_content)
        
        # 2. Reescalado de Imagen (Vital para RAM de 512MB)
        optimized_img_path = resize_input_image(anchor_image_path, max_dim=854)
        
        # 3. Video
        video_file = generar_video_ia(audio_file, optimized_img_path) 
        
        # 4. Subida
        youtube_id = subir_a_youtube_rotativo(video_file, title, text_content, article_id)
        if not youtube_id: raise Exception("Falló subida")

        _report_status_to_api("video_complete", article_id, {"youtubeId": youtube_id})

    except Exception as e:
        _print_flush(f"❌ FALLO GRAVE: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
    
    finally:
        # Limpieza de archivos
        for f in [audio_file, video_file]:
            if f and os.path.exists(f): 
                try: os.remove(f)
                except: pass
        
        if optimized_img_path != anchor_image_path and os.path.exists(optimized_img_path):
            try: os.remove(optimized_img_path)
            except: pass
            
        gc.collect() # Limpieza final agresiva
        _print_flush("✨ Tarea finalizada. Memoria purgada.")