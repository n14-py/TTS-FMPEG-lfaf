# -*- coding: utf-8 -*-
"""
==============================================================================
TTS ENGINE (Motor de Texto a Voz)
==============================================================================
Este módulo se encarga de convertir el texto del guion en archivos de audio MP3
usando Microsoft Edge TTS. Soporta múltiples voces y limpia el texto para
evitar bloqueos del sintetizador.
"""

import os
import re
import asyncio
import logging
import random
import time
import edge_tts
from config import TEMP_AUDIO_DIR, VOICES

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIONES DE LIMPIEZA DE TEXTO
# ==============================================================================
def sanitize_text_for_tts(text):
    """
    Limpia el texto de caracteres especiales, emojis o comillas que puedan
    hacer que Edge TTS lance un error o lea código en voz alta.
    """
    if not text:
        return "Sin texto disponible."
    
    # Quitar URLs si las hay por error
    text = re.sub(r'http[s]?://\S+', '', text)
    # Quitar hashtags
    text = re.sub(r'#\w+', '', text)
    # Reemplazar comillas y otros símbolos problemáticos
    text = text.replace('"', '').replace('*', '').replace('_', '')
    # Reducir múltiples espacios a uno solo
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# ==============================================================================
# GENERADOR ASÍNCRONO DE AUDIO
# ==============================================================================
def _tts_attempt_timeout():
    try:
        return max(15, int(os.getenv("TTS_ATTEMPT_TIMEOUT_SECONDS", "90")))
    except ValueError:
        return 90


async def _async_generate_audio(text, voice_code, output_path):
    """
    Función interna asíncrona que se comunica con Edge TTS.
    El texto, la voz y el códec de salida no cambian: solo hay un tope de tiempo.
    """
    try:
        communicate = edge_tts.Communicate(text, voice_code)
        await asyncio.wait_for(communicate.save(output_path), timeout=_tts_attempt_timeout())
        return True
    except asyncio.TimeoutError:
        logger.error("  [TTS Engine] Edge TTS superó el tiempo de espera.")
        return False
    except Exception as e:
        logger.error(f"  [TTS Engine] Fallo interno en Edge TTS: {e}")
        return False


def _tts_error_is_permanent(exc):
    message = str(exc).lower()
    permanent_markers = (
        "invalid voice",
        "voice not found",
        "is not a valid voice",
    )
    return any(marker in message for marker in permanent_markers)

# ==============================================================================
# CONTROLADOR PRINCIPAL DEL MOTOR TTS
# ==============================================================================
def generate_audio_clip(text, voice_key, filename):
    """
    Genera un archivo MP3 a partir de texto.
    
    Parámetros:
    - text: El texto a leer.
    - voice_key: Clave del diccionario VOICES (ej: 'mujer_1', 'hombre_1').
    - filename: Nombre del archivo de salida (ej: 'escena_1.mp3').
    
    Retorna:
    - La ruta absoluta del archivo generado o None si falla.
    """
    logger.info(f"  [TTS Engine] Preparando locución para: {filename}")
    
    # 1. Limpieza y validación
    clean_text = sanitize_text_for_tts(text)
    
    # 2. Asignación de voz segura (Fallback a Tomás si no encuentra la voz)
    voice_code = VOICES.get(voice_key, VOICES["hombre_1"])
    
    # 3. Ruta de salida
    output_path = os.path.join(TEMP_AUDIO_DIR, filename)
    
    # Si el archivo ya existe (por alguna ejecución trabada anterior), lo borramos
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            logger.warning(f"  [TTS Engine] No se pudo sobrescribir {output_path}")
    
    # 4. Generación con reintentos acotados y espera creciente.
    # La voz y el texto limpio son los mismos de siempre.
    max_retries = 3
    for attempt in range(max_retries):
        try:
            success = asyncio.run(_async_generate_audio(clean_text, voice_code, output_path))

            if success and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                logger.info(f"  [TTS Engine] Éxito: {filename} generado correctamente.")
                return output_path
            else:
                logger.warning(f"  [TTS Engine] Archivo vacío o no generado. Intento {attempt + 1}/{max_retries}")

        except Exception as e:
            logger.warning(f"  [TTS Engine] Error en intento {attempt + 1}: {e}")
            if _tts_error_is_permanent(e):
                logger.error("  [TTS Engine] Error permanente de voz. No se reintenta.")
                break

        if attempt < max_retries - 1:
            delay = min(8, 2 ** attempt) + random.uniform(0, 0.4)
            time.sleep(delay)

    logger.error(f"  [TTS Engine] ERROR FATAL: No se pudo generar audio para {filename} tras {max_retries} intentos.")
    return None

# ==============================================================================
# PROCESAMIENTO POR LOTES PARA ESCENAS
# ==============================================================================
def process_scene_audios(scenes_data, unique_id):
    """
    Recibe una lista de escenas (del JSON de Node.js) y genera todos los audios de golpe.
    Retorna un diccionario con las rutas de los audios generados.
    """
    audio_paths = {}
    
    for i, scene in enumerate(scenes_data):
        text = scene.get("text", "")
        voice = scene.get("voice", "hombre_1")
        filename = f"audio_{unique_id}_scene_{i}.mp3"
        
        # Solo generamos si hay texto
        if text.strip():
            path = generate_audio_clip(text, voice, filename)
            if path:
                audio_paths[i] = path
            else:
                logger.error(f"  [TTS Engine] Falló la escena {i}, saltando audio.")
                audio_paths[i] = None
        else:
            audio_paths[i] = None
            
    return audio_paths