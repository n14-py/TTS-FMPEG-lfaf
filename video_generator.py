import os
import time
import requests 
import subprocess 
import gc 
import sys
import asyncio 
import random
import edge_tts 
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# --- CARGAR VARIABLES ---
load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
FRONTEND_BASE_URL = "https://noticias.lat" 

# --- RUTAS DE ARCHIVOS (USAMOS /tmp PARA AWS/LINUX) ---
# Usamos carpetas temporales relativas para evitar permisos
TEMP_DIR = "temp_processing"
os.makedirs(TEMP_DIR, exist_ok=True)

AUDIO_PATH = os.path.join(TEMP_DIR, "news_audio.mp3")
FINAL_VIDEO_PATH = os.path.join(TEMP_DIR, "final_news_video.mp4")
ASSETS_DIR = "assets_video" 

# --- CONFIGURACIÓN DE VOZ (PLAN A y PLAN B) ---
VOICE_PLAN_A = "es-MX-JorgeNeural"  # Principal (Hombre)
VOICE_PLAN_B = "es-MX-DaliaNeural"  # Respaldo (Mujer)

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# --- CUENTAS DE YOUTUBE ---
ACCOUNTS = [
    {"id": 0, "name": "Principal",    "secret": "client_secret_0.json", "token": "token_0.json"},
    {"id": 1, "name": "NoticiasLat1", "secret": "client_secret_1.json", "token": "token_1.json"},
    {"id": 2, "name": "NoticiasLat2", "secret": "client_secret_2.json", "token": "token_2.json"},
    {"id": 3, "name": "NoticiasLat3", "secret": "client_secret_3.json", "token": "token_3.json"},
    {"id": 4, "name": "NoticiasLat4", "secret": "client_secret_4.json", "token": "token_4.json"},
    {"id": 5, "name": "NoticiasLat5", "secret": "client_secret_5.json", "token": "token_5.json"}
]

LAST_ACCOUNT_FILE = "last_account_used.txt"

print(f"✅ CARGADO: Sistema ULTRA ROBUSTO (Edge-TTS + Curl Download + FFmpeg)")

# --- UTILIDADES DE LOG Y API ---

def _print_flush(message):
    print(message)
    sys.stdout.flush()

def _report_status_to_api(endpoint, article_id, data={}):
    """Reporta éxito o fallo al backend principal."""
    if not MAIN_API_URL or not ADMIN_API_KEY:
        return
    url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    payload = {"articleId": article_id, **data}
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        _print_flush(f"⚠️ Alerta: No se pudo reportar a la API: {e}")

# --- GESTIÓN DE CUENTAS YOUTUBE ---

def get_next_account_index(current_index):
    return (current_index + 1) % len(ACCOUNTS)

def save_last_account(index):
    try:
        with open(LAST_ACCOUNT_FILE, "w") as f: f.write(str(index))
    except: pass

def load_last_account():
    try:
        if os.path.exists(LAST_ACCOUNT_FILE):
            with open(LAST_ACCOUNT_FILE, "r") as f: return int(f.read().strip())
    except: pass
    return 0

def get_authenticated_service(account_idx):
    account = ACCOUNTS[account_idx]
    if not os.path.exists(account['token']): return None
    try:
        creds = Credentials.from_authorized_user_file(account['token'], SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(requests.Request()) 
                with open(account['token'], 'w') as token: token.write(creds.to_json())
            else: return None
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds, cache_discovery=False)
    except Exception: return None

# --- MÓDULO 1: DESCARGA MILITAR DE IMÁGENES (SI O SI) ---

def validar_archivo_imagen(ruta):
    """Verifica si el archivo descargado es realmente una imagen válida."""
    if not os.path.exists(ruta): return False
    if os.path.getsize(ruta) < 500: return False # Muy pequeña = error
    
    # Leemos los primeros bytes para ver si es HTML (error común 403)
    try:
        with open(ruta, 'rb') as f:
            header = f.read(20)
            if b'<html' in header or b'<!DOCTYPE' in header or b'{' in header:
                return False # Es un HTML o JSON de error
    except:
        return False
    return True

def descargar_imagen_agresiva(url_original, destino_local):
    """
    Intenta descargar la imagen usando 3 métodos de fuerza creciente.
    """
    _print_flush(f"⬇️ Iniciando protocolo de descarga para: {url_original}")
    
    # --- MÉTODO 1: Requests con Headers de Navegador (Estándar) ---
    headers_normal = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    }
    try:
        resp = requests.get(url_original, headers=headers_normal, stream=True, timeout=10)
        if resp.status_code == 200:
            with open(destino_local, 'wb') as f:
                for chunk in resp.iter_content(1024): f.write(chunk)
            if validar_archivo_imagen(destino_local):
                _print_flush("✅ Descarga exitosa (Método 1)")
                return True
    except Exception as e:
        _print_flush(f"⚠️ Falló Método 1: {e}")

    # --- MÉTODO 2: Requests simulando Google Referer (Anti-Hotlink) ---
    _print_flush("🔄 Intentando Método 2 (Referer Spoofing)...")
    headers_google = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
        "Referer": "https://www.google.com/",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors"
    }
    try:
        resp = requests.get(url_original, headers=headers_google, stream=True, timeout=10)
        if resp.status_code == 200:
            with open(destino_local, 'wb') as f:
                for chunk in resp.iter_content(1024): f.write(chunk)
            if validar_archivo_imagen(destino_local):
                _print_flush("✅ Descarga exitosa (Método 2)")
                return True
    except: pass

    # --- MÉTODO 3: CURL de Sistema (Fuerza Bruta) ---
    # Esto salta bloqueos de librerías de Python. Es el "SI O SI".
    _print_flush("🔥 Intentando Método 3 (CURL System)...")
    try:
        # -L sigue redirecciones, -A cambia user agent, --retry reintenta
        cmd = [
            "curl", "-L", "-A", "Mozilla/5.0 (X11; Linux x86_64) Firefox/100.0",
            "--retry", "2", "--connect-timeout", "10",
            "-o", destino_local, url_original
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if validar_archivo_imagen(destino_local):
             _print_flush("✅ Descarga exitosa (Método 3 - CURL)")
             return True
    except Exception as e:
        _print_flush(f"❌ Falló Método 3: {e}")

    # Si llegamos aquí, la URL es imposible o está muerta.
    # El "SI O SI" requiere que devolvamos False para que el sistema use una imagen generada localmente si es necesario
    # (aunque aquí fallaremos la tarea si es vital, o usamos placeholder si así se desea en un futuro)
    _print_flush("❌ FATAL: La imagen es inaccesible por métodos humanos o bots.")
    return False

def sanitizar_imagen(input_path):
    """
    Convierte CUALQUIER cosa que haya bajado (WebP, AVIF, JPG corrupto)
    a un PNG limpio y escalado para HD.
    """
    _print_flush(f"🧼 Sanitizando y Normalizando imagen: {input_path}")
    clean_path = os.path.join(TEMP_DIR, "clean_image.png")
    
    # Comando FFmpeg para forzar lectura y conversión a PNG RGBA
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2", # Escala inteligente y Relleno negro si es necesario
        "-pix_fmt", "rgba", 
        clean_path
    ]
    try:
        subprocess.run(cmd, check=True)
        return clean_path
    except subprocess.CalledProcessError:
        raise Exception("FFmpeg no pudo entender el archivo de imagen. Probablemente corrupto.")

# --- MÓDULO 2: AUDIO EDGE-TTS (CON RESPALDO AUTOMÁTICO) ---

async def _edge_tts_generate(text, voice, output):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output)

def generar_audio(text):
    _print_flush(f"🎙️ Generando audio...")
    if os.path.exists(AUDIO_PATH): os.remove(AUDIO_PATH)
    
    # Pausa humana aleatoria (Seguridad anti-bloqueo)
    time.sleep(random.uniform(1.0, 2.5))
    
    # PLAN A: Voz Principal
    try:
        _print_flush(f"   👉 Intento Plan A: {VOICE_PLAN_A}")
        asyncio.run(_edge_tts_generate(text, VOICE_PLAN_A, AUDIO_PATH))
        if os.path.exists(AUDIO_PATH) and os.path.getsize(AUDIO_PATH) > 100:
            return AUDIO_PATH
    except Exception as e:
        _print_flush(f"⚠️ Falló Plan A ({e}).")

    # Si falla A, esperamos y probamos B
    _print_flush("   ⏱️ Esperando 3s antes de Plan B...")
    time.sleep(3)
    
    # PLAN B: Voz Respaldo
    try:
        _print_flush(f"   👉 Intento Plan B: {VOICE_PLAN_B}")
        asyncio.run(_edge_tts_generate(text, VOICE_PLAN_B, AUDIO_PATH))
        if os.path.exists(AUDIO_PATH):
            return AUDIO_PATH
    except Exception as e2:
         raise Exception(f"❌ FALLO TOTAL DE AUDIO (Ni A ni B funcionaron): {e2}")
    
    raise Exception("Audio generado pero archivo vacío.")

# --- MÓDULO 3: GENERACIÓN DE VIDEO IA (FFMPEG OPTIMIZADO) ---

def generar_video_ia(audio_path, imagen_path):
    _print_flush("🎬 Renderizando video final...")
    
    # Assets (Suscríbete, Like, etc.)
    assets = [
        {'path': os.path.join(ASSETS_DIR, "overlay_subscribe_like.png"), 'start': 2, 'end': 5}, 
        {'path': os.path.join(ASSETS_DIR, "overlay_bell.png"), 'start': 8, 'end': 11},      
    ]
    
    # Construcción del comando FFmpeg
    # Input 0: Imagen de fondo (Loop)
    # Input 1: Audio
    inputs = [f"-loop 1 -i \"{imagen_path}\"", f"-i \"{audio_path}\""]
    
    filter_complex = ""
    # Escala base para la imagen de fondo (asegura 1280x720)
    filter_complex += "[0:v]scale=1280:720,setsar=1[bg];"
    last_layer = "[bg]"
    
    # Añadir Overlays si existen
    stream_idx = 1
    input_idx = 2 # 0 es imagen, 1 es audio
    
    for asset in assets:
        if os.path.exists(asset['path']):
            inputs.append(f"-loop 1 -i \"{asset['path']}\"")
            filter_complex += f"{last_layer}[{input_idx}:v]overlay=(W-w)/2:H-h-50:enable='between(t,{asset['start']},{asset['end']})'[v{stream_idx}];"
            last_layer = f"[v{stream_idx}]"
            stream_idx += 1
            input_idx += 1
            
    # Comando Final
    cmd = (
        f"ffmpeg -y -hide_banner -loglevel error "
        f"{' '.join(inputs)} "
        f"-filter_complex \"{filter_complex.rstrip(';')}\" "
        f"-map \"{last_layer}\" -map 1:a " # Mapear ultimo video layer y audio (input 1)
        f"-c:v libx264 -preset ultrafast -tune stillimage -crf 30 " # Video rápido
        f"-c:a aac -b:a 128k -ac 2 " # Audio estéreo estándar
        f"-pix_fmt yuv420p -shortest " # Cortar cuando acabe el audio
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    subprocess.run(cmd, shell=True, check=True)
    return FINAL_VIDEO_PATH

# --- MÓDULO 4: SUBIDA A YOUTUBE (ROTACIÓN INTELIGENTE) ---

def subir_a_youtube_rotativo(video_path, title, full_text, article_id):
    _print_flush("🚀 Subiendo a YouTube...")
    current_idx = load_last_account()
    attempts = 0
    
    while attempts < len(ACCOUNTS):
        youtube = get_authenticated_service(current_idx)
        if youtube:
            try:
                # SEO y Título
                final_title = f"{title.strip()[:95]} | Noticias"
                desc = (
                    f"📰 Noticia completa: {FRONTEND_BASE_URL}/articulo/{article_id}\n\n"
                    f"{full_text[:3500]}...\n\n"
                    f"⚠️ Este contenido es informativo."
                )
                
                body = {
                    'snippet': {
                        'title': final_title, 
                        'description': desc, 
                        'tags': ['noticias', 'actualidad', 'latinoamerica'], 
                        'categoryId': '25' # Noticias y Politica
                    },
                    'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
                }
                
                media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
                resp = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
                
                video_id = resp.get('id')
                _print_flush(f"✅ SUBIDA EXITOSA: {video_id} (Cuenta {current_idx})")
                
                # Rotar cuenta para la próxima
                save_last_account(get_next_account_index(current_idx))
                return video_id

            except HttpError as e:
                # Manejo específico de Cuota Excedida (403/429)
                if e.resp.status in [403, 429]:
                    _print_flush(f"⛔ CUOTA LLENA Cuenta {current_idx}. Probando siguiente...")
                else:
                    _print_flush(f"❌ Error API YouTube: {e}")
            except Exception as e:
                _print_flush(f"❌ Error Genérico Subida: {e}")
                
        # Si falló, pasamos a la siguiente cuenta
        current_idx = get_next_account_index(current_idx)
        attempts += 1
        time.sleep(2) # Pausa técnica

    raise Exception("❌ ERROR CRÍTICO: Todas las cuentas fallaron o están sin cuota.")

# --- PROCESO PRINCIPAL (ORQUESTADOR) ---

def process_video_task(text_content, title, image_url, article_id):
    try:
        _print_flush(f"⚡ INICIO PROCESO ID: {article_id}")
        gc.collect()
        
        # 1. Descarga "SI O SI" de la imagen
        local_img_raw = os.path.join(TEMP_DIR, "raw_image")
        success = descargar_imagen_agresiva(image_url, local_img_raw)
        
        if not success:
            raise Exception("No se pudo descargar la imagen ni con métodos agresivos.")
            
        # 2. Sanitización (Convertir a HD PNG)
        clean_img = sanitizar_imagen(local_img_raw)
        
        # 3. Audio (Plan A o B)
        audio_file = generar_audio(text_content)
        
        # 4. Video
        video_file = generar_video_ia(audio_file, clean_img)
        
        # 5. Subida
        yt_id = subir_a_youtube_rotativo(video_file, title, text_content, article_id)
        
        # Reportar Éxito
        _report_status_to_api("video_complete", article_id, {"youtubeId": yt_id})
        
    except Exception as e:
        _print_flush(f"❌ FALLO TAREA: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
        
    finally:
        # Limpieza obsesiva para servidores pequeños
        _print_flush("🧹 Limpiando archivos temporales...")
        try:
            shutil.rmtree(TEMP_DIR) # Borra todo el directorio temporal
            os.makedirs(TEMP_DIR, exist_ok=True) # Lo recrea vacío
        except: pass
        gc.collect()