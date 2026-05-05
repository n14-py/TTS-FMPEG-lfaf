# -*- coding: utf-8 -*-
"""
==============================================================================
MÓDULO FFMPEG: ENSAMBLADOR DE INTROS
==============================================================================
Este script se encarga exclusivamente de las intros.
A diferencia del ensamblador universal, aquí NO HAY CHROMA KEY (pantalla verde)
ni videos de fondo superpuestos. Es video directo + texto gigante + audio mezclado.
"""

import os
import logging
import subprocess
import textwrap
from config import *

logger = logging.getLogger(__name__)

def formatear_texto_intro(texto, max_chars):
    """Corta el titular para que encaje perfecto y se vea gigante y agresivo."""
    if not texto:
        return ""
    # Escapar comillas simples
    texto = texto.replace("'", "\u2019").replace(":", "\\:")
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=texto)
    # Las intros suelen tener 1 o 2 líneas máximo para mayor impacto
    if len(word_list) > 2:
        return "\\n".join(word_list[:2]) + "..."
    return "\\n".join(word_list)

def ensamblar_intro(intro_path, audio_tts_path, bgm_path, sfx_path, texto, output_path):
    """
    Toma el video de intro base y le incrusta el título, la voz y la música.
    """
    logger.info(f"  [FFmpeg Intro] Ensamblando escena de Introducción...")
    logger.info(f"  --> Intro Base: {os.path.basename(intro_path)}")

    # 1. VALIDACIONES
    if not os.path.exists(intro_path) or not os.path.exists(audio_tts_path):
        logger.error("  [FFmpeg Intro] Faltan archivos clave (Intro o Audio) para ensamblar.")
        return False

    # 2. OBTENER COORDENADAS (Desde config.py)
    filename = os.path.basename(intro_path)
    config = get_layout_config(filename)
    
    clean_text = formatear_texto_intro(texto, config["max_letras_por_linea"])
    
    # Variables visuales
    x, y = config["texto_x"], config["texto_y"]
    color, size = config["color"], config["font_size"]
    shadow = "shadowcolor=black@0.8:shadowx=0:shadowy=0" # Sombra más fuerte para intros

    # 3. CONSTRUIR COMANDO BASE
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", intro_path, # [0:v] Video de Intro en loop por si la voz dura más
        "-i", audio_tts_path                    # [1:a] Voz TTS principal
    ]

    # 4. TUBERÍA VISUAL (Solo escala y texto, nada de verde)
    filter_complex = (
        f"[0:v]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,"
        f"crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2[bg];"
    )

    if clean_text:
        filter_complex += f"[bg]drawtext=fontfile='{FONT_PATH}':text='{clean_text}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    else:
        filter_complex += f"[bg]copy[vout];"

    # 5. MEZCLADOR DE AUDIO
    audio_inputs = "[1:a]"
    input_count = 1

    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-i", bgm_path])  # Entrada 2
        audio_inputs += "[2:a]"
        input_count += 1
        
    if sfx_path and os.path.exists(sfx_path):
        cmd.extend(["-i", sfx_path])  # Entrada 3
        audio_inputs += "[3:a]"
        input_count += 1

    # Mezclamos los audios
    if input_count > 1:
        # La música en la intro puede estar un poquitito más fuerte (0.15) para dar impacto
        filter_complex += f"{audio_inputs}amix=inputs={input_count}:duration=first:dropout_transition=2:weights=1 0.15 0.3[aout]"
        audio_map = "-map [aout]"
    else:
        filter_complex = filter_complex.rstrip(';')
        audio_map = "-map 1:a"

    # 6. EMPAQUETADO FINAL
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", 
        "-preset", VIDEO_PRESET, 
        "-r", str(FPS),
        "-c:a", "aac", 
        "-b:a", "128k", 
        "-shortest", # Corta la intro cuando la IA termina de leer el titular
        output_path
    ])

    # 7. EJECUCIÓN
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=200)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            logger.info("  [FFmpeg Intro] Intro renderizada con éxito.")
            return True
        else:
            logger.error("  [FFmpeg Intro] El archivo de intro resultante está vacío.")
            return False
            
    except Exception as e:
        logger.error(f"  [FFmpeg Intro] Error crítico: {e}")
        return False