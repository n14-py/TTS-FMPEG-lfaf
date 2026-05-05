# -*- coding: utf-8 -*-
"""
==============================================================================
SCENE BUILDER (El Constructor de Escenas)
==============================================================================
Este módulo toma los recursos (audio, video base, imagen) y crea comandos
de FFmpeg complejos para generar una escena individual.
"""

import os
import textwrap
import logging
from config import *
from ffmpeg_core import execute_ffmpeg_command

logger = logging.getLogger(__name__)

# ==============================================================================
# FORMATEO DE TEXTO MULTILÍNEA
# ==============================================================================
def wrap_text_for_ffmpeg(text, max_chars):
    """
    Toma un texto largo y le inserta saltos de línea (\n) para que
    encaje perfectamente en las cajas de tus overlays de Canva sin salirse.
    """
    if not text:
        return ""
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=text)
    # Limitamos a 3 líneas máximo en pantalla para no saturar
    if len(word_list) > 3:
        return "\\n".join(word_list[:3]) + "..."
    return "\\n".join(word_list)

# ==============================================================================
# CONSTRUCTOR DE INTROS
# ==============================================================================
def build_intro_scene(template_path, audio_path, bgm_path, title_text, output_path):
    """
    Construye los primeros segundos del video.
    No requiere chroma key. Mezcla música, voz, overlay y texto.
    """
    logger.info("  [Scene Builder] Construyendo Escena Intro...")
    
    # 1. Obtener la configuración matemática para este diseño específico
    filename = os.path.basename(template_path)
    config = get_layout_config(filename)
    
    clean_title = wrap_text_for_ffmpeg(title_text, config["max_letras_por_linea"])
    
    # 2. Variables de texto
    x = config["texto_x"]
    y = config["texto_y"]
    color = config["color"]
    size = config["font_size"]
    shadow = "shadowcolor=black@0.8:shadowx=0:shadowy=0"
    
    # 3. Construir el comando (Manejo dinámico de audio)
    # Si tenemos música (bgm) y voz, los mezclamos. Si no, solo usamos la voz.
    audio_filter = ""
    audio_map = "-map 1:a" # Por defecto, mapeamos solo el TTS (entrada 1)
    
    if bgm_path:
        # amix=inputs=2: Mezcla el audio del video base/TTS con la música
        audio_filter = f"[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2:weights=1 0.1[aout];"
        audio_map = "-map [aout]"

    filter_complex = (
        f"[0:v]drawtext=fontfile='{FONT_PATH}':text='{clean_title}':"
        f"fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
        f"{audio_filter}"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", template_path, # [0:v] El video de intro de Canva
        "-i", audio_path     # [1:a] La voz TTS
    ]
    
    if bgm_path:
        cmd.extend(["-i", bgm_path]) # [2:a] La música de fondo
        
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path
    ])
    
    return execute_ffmpeg_command(cmd)

# ==============================================================================
# CONSTRUCTOR DE CUERPO DE NOTICIA (CHROMA KEY)
# ==============================================================================
def build_body_scene(image_path, template_path, audio_path, bgm_path, sfx_path, overlay_text, output_path):
    """
    El corazón del noticiero.
    Toma la foto de fondo, le pone encima el video verde (template_path),
    perfora el verde, escribe el texto e inyecta audio, música y efectos.
    """
    logger.info("  [Scene Builder] Construyendo Escena de Cuerpo (Chroma)...")
    
    # 1. Configuración de texto
    filename = os.path.basename(template_path)
    config = get_layout_config(filename)
    clean_text = wrap_text_for_ffmpeg(overlay_text, config["max_letras_por_linea"])
    
    x = config["texto_x"]
    y = config["texto_y"]
    color = config["color"]
    size = config["font_size"]
    shadow = "shadowcolor=black@0.8:shadowx=0:shadowy=0"
    
    # 2. Construcción del filtro complejo (La tubería visual de FFmpeg)
    # [bg]: Escala la foto de la noticia para que llene 1280x720 sin estirarse
    # [v_scaled]: Asegura que el MP4 verde de Canva esté en 720p
    # [v_keyed]: Borra el color verde del MP4
    # [comp]: Superpone el MP4 transparente sobre la foto de fondo
    # [vout]: Escribe el texto sobre la composición
    
    filter_complex = (
        f"[0:v]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,"
        f"crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2[bg];"
        f"[1:v]scale=-1:{RESOLUTION_H}[v_scaled];"
        f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
        f"[bg][v_keyed]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
        f"[comp]drawtext=fontfile='{FONT_PATH}':text='{clean_text}':"
        f"fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    )
    
    # 3. Mezclador Dinámico de Audio
    # Siempre tenemos la voz (TTS) como entrada [2:a]
    audio_inputs = "[2:a]"
    input_count = 1
    
    # Construcción base del comando de terminal
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", "60", "-i", image_path, # [0:v] Imagen real (Forzada a durar máximo 60s si falla el -shortest)
        "-stream_loop", "-1", "-i", template_path,  # [1:v] Video Verde en bucle infinito
        "-i", audio_path                            # [2:a] Voz TTS
    ]
    
    # ¿Tenemos Música de Fondo?
    if bgm_path:
        cmd.extend(["-i", bgm_path])                # [3:a]
        audio_inputs += "[3:a]"
        input_count += 1
        
    # ¿Tenemos Efectos de Sonido? (Ej: "swoosh" al entrar la imagen)
    if sfx_path:
        cmd.extend(["-i", sfx_path])                # [4:a]
        audio_inputs += "[4:a]"
        input_count += 1

    # Si hay más de 1 fuente de audio, las mezclamos. Si no, pasamos la voz directo.
    if input_count > 1:
        # El volumen de la música/efecto (0.1) evita tapar la voz
        filter_complex += f"{audio_inputs}amix=inputs={input_count}:duration=first:dropout_transition=2:weights=1 0.1 0.3[aout]"
        audio_map = "-map [aout]"
    else:
        # filter_complex no necesita terminar con ; si no hay audios extra
        filter_complex = filter_complex.rstrip(';')
        audio_map = "-map 2:a"
        
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path
    ])
    
    return execute_ffmpeg_command(cmd)