# -*- coding: utf-8 -*-
"""
==============================================================================
FFMPEG CORE (El Motor de Renderizado)
==============================================================================
Este módulo maneja la ejecución segura de comandos de FFmpeg, evitando
que los procesos se cuelguen (Timeouts) y consuman toda la memoria del servidor.
"""

import os
import subprocess
import logging
from config import *

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIÓN DE EJECUCIÓN SEGURA
# ==============================================================================
def execute_ffmpeg_command(cmd, timeout=300):
    """
    Ejecuta un comando de FFmpeg de manera segura.
    Retorna True si fue exitoso, False si falló o hubo Timeout.
    """
    try:
        logger.info(f"  [FFmpeg Core] Ejecutando comando... (Timeout: {timeout}s)")
        
        # Ejecutar con subprocess.run para bloquear hasta que termine
        subprocess.run(
            cmd, 
            check=True, 
            stdout=subprocess.DEVNULL, # Oculta el log masivo de FFmpeg en consola
            stderr=subprocess.DEVNULL, 
            timeout=timeout
        )
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("  [FFmpeg Core] ERROR: El renderizado excedió el tiempo límite. Proceso abortado para proteger el servidor.")
        return False
    except subprocess.CalledProcessError as err:
        logger.error(f"  [FFmpeg Core] FALLO de FFmpeg: Posible falta de RAM o archivo de entrada corrupto.")
        return False
    except Exception as e:
        logger.error(f"  [FFmpeg Core] Error inesperado en FFmpeg: {e}")
        return False

# ==============================================================================
# AYUDANTES (HELPERS) PARA FILTROS FFMPEG
# ==============================================================================
def get_chroma_filter(video_index, out_name):
    """
    Devuelve la cadena de filtro para perforar la pantalla verde (Chroma Key).
    """
    return f"[{video_index}:v]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[{out_name}];"

def get_text_filter(text, config_dict, in_name, out_name):
    """
    Devuelve la cadena de filtro para dibujar el texto sobre el video, 
    usando las coordenadas de tu diccionario en config.py.
    """
    x = config_dict.get("texto_x", 50)
    y = config_dict.get("texto_y", 600)
    color = config_dict.get("color", "white")
    size = config_dict.get("font_size", 45)
    
    # Efecto de sombra profesional para que siempre se lea bien
    shadow = "shadowcolor=black@0.8:shadowx=0:shadowy=0"
    
    return f"[{in_name}]drawtext=fontfile='{FONT_PATH}':text='{text}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[{out_name}];"

def apply_background_music(video_in, bgm_path, out_name, volume="0.1"):
    """
    Devuelve la cadena de filtro para mezclar el audio principal con música de fondo.
    Asume que el audio de voz es la pista [0:a] y la BGM es [1:a].
    """
    if not bgm_path:
        return "" # Si no hay BGM, no hacemos nada
    
    # 'amix' mezcla las pistas. 'duration=first' hace que la música dure lo mismo que la voz.
    return f"[{video_in}a][1:a]amix=inputs=2:duration=first:dropout_transition=2:weights=1 {volume}[{out_name}];"

# ==============================================================================
# EL ENSAMBLADOR FINAL (CONCATENACIÓN HIPER-RÁPIDA)
# ==============================================================================
def concatenate_scenes(scene_files, final_output_path, unique_id):
    """
    Toma una lista de videos ya renderizados (escenas) y los pega en uno solo
    en menos de 2 segundos sin volver a codificar (re-encode).
    """
    if not scene_files:
        logger.error("  [FFmpeg Core] No hay escenas para concatenar.")
        return False
        
    list_file_path = os.path.join(TEMP_VIDEO_DIR, f"list_{unique_id}.txt")
    
    try:
        # 1. Crear el archivo de lista requerido por FFmpeg
        logger.info(f"  [FFmpeg Core] Ensamblando {len(scene_files)} escenas...")
        with open(list_file_path, 'w', encoding='utf-8') as f:
            for scene in scene_files:
                # FFmpeg requiere la ruta absoluta envuelta en comillas simples
                # y caracteres de escape para rutas en Windows/Linux
                safe_path = scene.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
                
        # 2. Comando de concatenación pura (Stream Copy)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy", # ¡ESTA ES LA MAGIA! No re-renderiza, solo pega
            final_output_path
        ]
        
        success = execute_ffmpeg_command(cmd, timeout=60) # Esto es rapidísimo
        
        return success and os.path.exists(final_output_path)
        
    except Exception as e:
        logger.error(f"  [FFmpeg Core] Fallo en la concatenación: {e}")
        return False
    finally:
        # Limpieza del archivo de texto
        if os.path.exists(list_file_path):
            os.remove(list_file_path)