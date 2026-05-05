# -*- coding: utf-8 -*-
"""
==============================================================================
YOUTUBE UPLOADER (Rotador Automático de Cuentas)
==============================================================================
Este módulo maneja exclusivamente la conexión con la API de YouTube.
Utiliza un sistema de rotación matemática para alternar entre las 6 cuentas
disponibles y evitar el error 403 (Quota Exceeded).
"""

import os
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURACIÓN DE YOUTUBE
# ==============================================================================
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
MAX_ACCOUNTS = 4  # Tienes configurados del token_0 al token_5
BASE_DIR = os.getcwd()
LOCKS_DIR = os.path.join(BASE_DIR, "locks_history")

# Nos aseguramos de que la carpeta de historial de bloqueos exista
if not os.path.exists(LOCKS_DIR):
    os.makedirs(LOCKS_DIR, exist_ok=True)

# ==============================================================================
# FUNCIONES DE ROTACIÓN Y ESTADO
# ==============================================================================
def get_next_account_index():
    """
    Calcula qué cuenta de YouTube toca usar hoy (0->1->2->3->4->5->0...)
    Guarda el estado en un archivo de texto para no perder la cuenta tras reinicios.
    """
    rotator_file = os.path.join(LOCKS_DIR, "account_rotator.txt")
    current_index = 0
    
    # Leemos cuál fue el último canal que usamos
    if os.path.exists(rotator_file):
        try:
            with open(rotator_file, 'r') as f:
                content = f.read().strip()
                if content.isdigit():
                    current_index = int(content)
        except Exception as e:
            logger.warning(f"  [YouTube Uploader] Error leyendo archivo de rotación: {e}")
            current_index = 0
            
    # Calculamos el siguiente canal a usar
    next_index = (current_index + 1) % MAX_ACCOUNTS
    
    # Guardamos el nuevo canal para el futuro
    try:
        with open(rotator_file, 'w') as f:
            f.write(str(next_index))
    except Exception as e:
        logger.warning(f"  [YouTube Uploader] No se pudo guardar rotación: {e}")
        
    logger.info(f"  [YouTube Uploader] Toca usar Cuenta {next_index} (La anterior fue {current_index})")
    return next_index

def is_already_processed(article_id):
    """Evita subidas duplicadas buscando si ya existe un registro de esta noticia."""
    if not article_id or article_id == "NO_ID": 
        return False
    return os.path.exists(os.path.join(LOCKS_DIR, f"{article_id}.done"))

def mark_as_processed(article_id, video_id):
    """Crea un archivo imborrable para marcar que esta noticia ya se subió a YouTube."""
    if not article_id or article_id == "NO_ID": 
        return
    try:
        done_file = os.path.join(LOCKS_DIR, f"{article_id}.done")
        with open(done_file, 'w') as f:
            f.write(f"Processed at {datetime.now()} - YouTube ID: {video_id}")
    except Exception as e:
        logger.warning(f"  [YouTube Uploader] No se pudo guardar historial para {article_id}: {e}")

# ==============================================================================
# AUTENTICACIÓN Y SUBIDA
# ==============================================================================
def get_authenticated_service(account_index):
    """Carga los tokens JSON y obtiene acceso a la API para la cuenta específica."""
    creds = None
    token_file = os.path.join(BASE_DIR, f'token_{account_index}.json')
    
    if not os.path.exists(token_file):
        logger.warning(f"  [YouTube Uploader] Falta el archivo de token: {token_file}")
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    except Exception as e:
        logger.error(f"  [YouTube Uploader] Token {account_index} corrupto: {e}")
        return None

    # Refresco automático de tokens caducados
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info(f"  [YouTube Uploader] Refrescando token expirado de cuenta {account_index}...")
                creds.refresh(Request())
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"  [YouTube Uploader] Error refrescando token {account_index}: {e}")
                return None
        else:
            logger.error(f"  [YouTube Uploader] El token {account_index} requiere re-autorización manual.")
            return None
            
    try:
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"  [YouTube Uploader] Error construyendo el servicio YouTube: {e}")
        return None

def upload_video(file_path, title, description, tags, category_id="25"):
    """
    Intenta subir el video. Si la cuenta actual se quedó sin cuota (403),
    salta automáticamente a la siguiente cuenta en el loop.
    """
    if not os.path.exists(file_path):
        logger.error("  [YouTube Uploader] Archivo de video no encontrado para subir.")
        return None

    start_index = get_next_account_index()
    
    for i in range(MAX_ACCOUNTS):
        account_index = (start_index + i) % MAX_ACCOUNTS
        logger.info(f"  [YouTube Uploader] Intentando subida con la Cuenta {account_index}...")
        
        youtube = get_authenticated_service(account_index)
        if not youtube:
            continue
            
        body = {
            'snippet': {
                'title': title[:99],
                'description': description[:4900],
                'tags': tags[:15], # Límite prudente de tags
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
            logger.info("  [YouTube Uploader] Transfiriendo bytes a YouTube...")
            
            while response is None:
                status, response = request.next_chunk()
                
            video_id = response.get('id')
            logger.info(f"  [YouTube Uploader] ¡ÉXITO! Video publicado: https://youtu.be/{video_id}")
            return video_id
            
        except HttpError as e:
            if e.resp.status in [403, 429] and "quotaExceeded" in e.content.decode('utf-8'):
                logger.warning(f"  [YouTube Uploader] CUOTA LLENA en Cuenta {account_index}. Cambiando a la siguiente...")
                continue # Pasa a la siguiente cuenta del ciclo
            else:
                logger.error(f"  [YouTube Uploader] Error de red en YouTube: {e}")
                
        except Exception as e:
            logger.error(f"  [YouTube Uploader] Error inesperado durante la subida: {e}")
            
    logger.error("  [YouTube Uploader] FALLO CRÍTICO: Todas las cuentas fallaron o no tienen cuota.")
    return None