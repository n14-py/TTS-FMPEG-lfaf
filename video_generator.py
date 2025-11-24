import os
import time
import requests 
import subprocess 
import gc # IMPORTANTE: Traemos de vuelta el recolector de basura
import json
from dotenv import load_dotenv

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

load_dotenv()
MAIN_API_URL = os.getenv("MAIN_API_URL")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

FRONTEND_BASE_URL = "https://noticias.lat" # Sin slash al final para evitar dobles

AUDIO_PATH = "temp_audio/news_audio.mp3"
FINAL_VIDEO_PATH = "output/final_news_video.mp4"

# --- MODELO PIPER ---
PIPER_MODEL_NAME = "es_ES-carlfm-x_low"
PIPER_MODEL_DIR = "/app/models/piper" 

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# --- ¡NUEVO! CONFIGURACIÓN DE LAS 4 CUENTAS ---
ACCOUNTS = [
    {"id": 0, "name": "Principal",    "secret": "client_secret_0.json", "token": "token_0.json"},
    {"id": 1, "name": "NoticiasLat1", "secret": "client_secret_1.json", "token": "token_1.json"},
    {"id": 2, "name": "NoticiasLat2", "secret": "client_secret_2.json", "token": "token_2.json"},
    {"id": 3, "name": "NoticiasLat3", "secret": "client_secret_3.json", "token": "token_3.json"}
]

LAST_ACCOUNT_FILE = "last_account_used.txt"

print("Cargando motor TTS: Piper (Ultraligero) y Sistema Multi-Cuenta")

# --- Funciones Auxiliares ---

def _report_status_to_api(endpoint, article_id, data={}):
    if not MAIN_API_URL or not ADMIN_API_KEY:
        return
    url = f"{MAIN_API_URL}/api/articles/{endpoint}"
    headers = {"x-api-key": ADMIN_API_KEY}
    payload = {"articleId": article_id, **data}
    try:
        requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e:
        print(f"ERROR CALLBACK: {e}")

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
    print(f"🔑 [Auth] Probando cuenta {account['id']} ({account['name']})...")
    
    if not os.path.exists(account['token']):
        print(f"⚠️ [Auth] Falta el archivo {account['token']}. Saltando cuenta.")
        return None

    try:
        creds = Credentials.from_authorized_user_file(account['token'], SCOPES)
        
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                print(f"🔄 [Auth] Refrescando token para {account['name']}...")
                creds.refresh(Request())
                with open(account['token'], 'w') as token:
                    token.write(creds.to_json())
            else:
                print(f"❌ [Auth] Token inválido e irrecuperable para {account['name']}.")
                return None
                
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds)
    except Exception as e:
        print(f"❌ [Auth] Error en cuenta {account['id']}: {e}")
        return None

# --- PASO 1: Generar Audio (Original) ---
def generar_audio(text):
    print(f"Iniciando Paso 1: Generando audio con Piper...")
    start_time = time.time()
    
    command = [
        "piper",
        "--model", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx"),
        "--config", os.path.join(PIPER_MODEL_DIR, f"{PIPER_MODEL_NAME}.onnx.json"),
        "--output_file", AUDIO_PATH
    ]
    
    try:
        # Ejecutamos Piper. Al ser subprocess, la RAM se libera al terminar el proceso externo.
        subprocess.run(command, input=text.encode('utf-8'), capture_output=True, check=True)
        
        if not os.path.exists(AUDIO_PATH):
             raise Exception("Piper no generó el archivo de audio.")
             
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error al ejecutar Piper: {e.stderr.decode('utf-8')}")
    except Exception as e:
        raise Exception(f"Error al iniciar Piper: {e}")

    end_time = time.time()
    print(f"Audio guardado ({end_time - start_time:.2f}s).")
    return AUDIO_PATH

# --- PASO 2: Generar Video (OPTIMIZADO 720p Original) ---
def generar_video_ia(audio_path, imagen_path):
    print("Iniciando Paso 2: Generando video HORIZONTAL (720p HD)...")
    
    # CAMBIOS APLICADOS PARA VELOCIDAD EXTREMA:
    # 1. Escala bajada a 1280x720 (HD Estándar) -> Mucho más rápido de procesar.
    # 2. Mantenemos -preset ultrafast y -tune stillimage.
    # 3. Mantenemos -threads 1 por seguridad en el plan de $7 de Render.
    
    ffmpeg_command = (
        f"ffmpeg -y -loop 1 -i \"{imagen_path}\" -i \"{audio_path}\" "
        f"-threads 1 -r 1 "
        f"-c:v libx264 -preset ultrafast -tune stillimage -crf 32 "
        f"-c:a aac -b:a 64k -ac 1 "
        f"-pix_fmt yuv420p -shortest "
        f"-vf \"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1\" "
        f"\"{FINAL_VIDEO_PATH}\""
    )
    
    try:
        subprocess.run(ffmpeg_command, shell=True, check=True)
        print(f"Video guardado en {FINAL_VIDEO_PATH}")
        return FINAL_VIDEO_PATH
    except Exception as e:
        print(f"Error en ffmpeg: {e}")
        return None

# --- PASO 3: Subir a YouTube (NUEVO SISTEMA ROTATIVO) ---
def subir_a_youtube_rotativo(video_path, title, full_text, article_id):
    print("Iniciando Paso 3: Subiendo a YouTube con Rotación de Cuentas...")
    
    # Cargamos cuál fue la última cuenta usada para intentar distribuir la carga
    start_index = load_last_account()
    print(f"🚀 Cuenta inicial sugerida: {start_index}")
    
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
                
                print(f"Longitud Descripción: {len(final_description)} caracteres.")
                
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

                media_file = MediaFileUpload(video_path, chunksize=-1, resumable=True)

                print(f"📤 Intentando subir a Cuenta {current_idx}...")
                response_upload = youtube.videos().insert(
                    part='snippet,status',
                    body=request_body,
                    media_body=media_file
                ).execute()
                
                video_id = response_upload.get('id')
                print(f"✅ ¡SUBIDA EXITOSA! ID: {video_id} en Cuenta {current_idx}")
                
                # Guardamos esta cuenta como la última exitosa
                save_last_account(current_idx)
                return video_id

            except HttpError as e:
                # Chequeamos si es error de cuota (403 o 429 con mensaje especifico)
                error_content = e.content.decode('utf-8')
                if e.resp.status in [403, 429] and "quotaExceeded" in error_content:
                    print(f"⛔ CUOTA AGOTADA en Cuenta {current_idx}. Cambiando a la siguiente...")
                else:
                    print(f"❌ Error HTTP no relacionado con cuota: {e}")
                    # A veces Google da errores 403 raros, probamos siguiente cuenta por si acaso
            except Exception as e:
                print(f"❌ Error desconocido al subir: {e}")
                # Probamos siguiente cuenta
        
        # Si falló, pasamos a la siguiente cuenta en el anillo
        current_idx = get_next_account_index(current_idx)
        attempts += 1
        print(f"🔄 Rotando a Cuenta {current_idx}...")
        time.sleep(2) # Pequeña pausa para no saturar

    # Si salimos del while es que todas fallaron
    raise Exception("❌ TODAS las cuentas han fallado o están sin cuota.")

# --- PROCESO PRINCIPAL (Original con llamada nueva) ---
def process_video_task(text_content, title, anchor_image_path, article_id):
    youtube_id = None
    try:
        # 1. Audio
        audio_file = generar_audio(text_content)
        if not audio_file: raise Exception("Falló audio")
        
        # Limpieza post-audio
        gc.collect()

        # 2. Video
        video_file = generar_video_ia(audio_file, anchor_image_path)
        if not video_file: raise Exception("Falló video")
        
        # Limpieza post-video (importante antes de subir para tener RAM libre para requests)
        gc.collect()

        # 3. Subida (USANDO EL NUEVO SISTEMA ROTATIVO)
        youtube_id = subir_a_youtube_rotativo(video_file, title, text_content, article_id)
        if not youtube_id: raise Exception("Falló subida")

        print(f"✅ FINALIZADO CON ÉXITO: {article_id}")
        _report_status_to_api("video_complete", article_id, {"youtubeId": youtube_id})

    except Exception as e:
        print(f"❌ FALLO: {e}")
        _report_status_to_api("video_failed", article_id, {"error": str(e)})
    
    finally:
        print("🧹 LIMPIEZA FINAL DE ARCHIVOS Y RAM...")
        # Eliminar archivos
        if os.path.exists(AUDIO_PATH): 
            try: os.remove(AUDIO_PATH)
            except: pass
        if os.path.exists(FINAL_VIDEO_PATH): 
            try: os.remove(FINAL_VIDEO_PATH)
            except: pass
        
        # Forzar limpieza de memoria de Python
        del text_content
        del title
        gc.collect()