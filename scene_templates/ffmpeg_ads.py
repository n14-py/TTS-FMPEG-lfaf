# -*- coding: utf-8 -*-
import os
import logging
import subprocess
import textwrap
import uuid
from config import *

logger = logging.getLogger(__name__)

def obtener_duracion_audio(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    try:
        resultado = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
        return float(resultado.stdout.strip()) + 0.4
    except Exception:
        return 25.0

def tiene_audio(filepath):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", filepath]
    try:
        resultado = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return len(resultado.stdout.strip()) > 0
    except Exception:
        return False

def formatear_texto(texto, max_chars):
    if not texto: return ""
    texto = texto.replace("\\n", " ").replace("\n", " ")
    texto = " ".join(texto.split())
    texto = texto.replace("'", "\u2019").replace(":", "\\:")
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=texto)
    if len(word_list) > 3:
        return "\n".join(word_list[:3]) + "..."  # Usamos \n real
    return "\n".join(word_list)  # Usamos \n real

# ==============================================================================
# MOTOR 1: PAUSA COMERCIAL 
# ==============================================================================
def renderizar_ad_video(ad_media_path, output_path):
    logger.info(f"  [FFmpeg Ads] 🎬 Dando formato militar al video comercial...")
    
    if not os.path.exists(ad_media_path):
        return False

    has_audio = tiene_audio(ad_media_path)

    # Blur adaptativo para cualquier resolución, forzando YUV420P y el FPS de nuestro noticiero
    filter_complex = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2,boxblur=25:25,setsar=1,fps={FPS}[bg_blur];"
        f"[fg]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=decrease,setsar=1,fps={FPS}[fg_scale];"
        f"[bg_blur][fg_scale]overlay=(W-w)/2:(H-h)/2,format=yuv420p,setsar=1[vout]"
    )

    cmd = ["ffmpeg", "-y", "-i", ad_media_path]

    # Inyectamos o re-sampleamos el audio a la fuerza para que NO ROMPA el orquestador
    if not has_audio:
        logger.info("  [FFmpeg Ads] 🔇 Video mudo detectado. Inyectando silencio de sistema...")
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        audio_map = ["-map", "1:a"]
        shortest_flag = ["-shortest"]
    else:
        # Pasa su audio por la licuadora a 48000Hz Stereo
        filter_complex += ";[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[aout]"
        audio_map = ["-map", "[aout]"]
        shortest_flag = []

    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]"])
    cmd.extend(audio_map)
    
    cmd.extend([
        "-c:v", "libx264", 
        "-preset", VIDEO_PRESET if 'VIDEO_PRESET' in globals() else "superfast", 
        "-r", str(FPS),
        "-c:a", "aac", 
        "-ar", "48000",
        "-ac", "2",
        "-b:a", "128k"
    ])
    
    cmd.extend(shortest_flag)
    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"  [FFmpeg Ads] ❌ Error: {e}")
        return False

# ==============================================================================
# MOTOR 2: MENCIÓN PATROCINADA 
# ==============================================================================
def renderizar_mencion(ad_media_path, overlay_path, audio_tts_path, bgm_path, sfx_path, texto, output_path, unique_id):
    logger.info(f"  [FFmpeg Ads] 🎙️ Renderizando Mención Patrocinada IA...")

    if not os.path.exists(ad_media_path) or not os.path.exists(overlay_path) or not os.path.exists(audio_tts_path):
        return False

    duracion_exacta = obtener_duracion_audio(audio_tts_path)

    filename = os.path.basename(overlay_path)
    config = get_layout_config(filename) if 'get_layout_config' in globals() else LAYOUT_CONFIG.get(filename, DEFAULT_LAYOUT)

    clean_text = formatear_texto(texto, config["max_letras_por_linea"])
    x, y = config["texto_x"], config["texto_y"]
    color, size = config["color"], config["font_size"]
    shadow = "bordercolor=black:borderw=2"

    texto_path = os.path.join(TEMP_VIDEO_DIR, f"txt_ad_{uuid.uuid4().hex[:6]}.txt").replace('\\', '/')
    if clean_text:
        with open(texto_path, "wb") as f:
            f.write(clean_text.encode("utf-8"))

    es_video = ad_media_path.lower().endswith(('.mp4', '.mov', '.avi'))
    cmd = ["ffmpeg", "-y"]
    
    if es_video:
        cmd.extend(["-stream_loop", "-1", "-i", ad_media_path])
    else:
        cmd.extend(["-loop", "1", "-framerate", str(FPS), "-i", ad_media_path])

    cmd.extend(["-stream_loop", "-1", "-i", overlay_path])
    cmd.extend(["-i", audio_tts_path])

    filter_complex = (
        f"[0:v]split=2[bg_raw][fg_raw];"
        f"[bg_raw]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2,boxblur=20:20,fps={FPS},setsar=1[bg_blur];"
        f"[fg_raw]scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=decrease,fps={FPS},setsar=1[fg_scale];"
        f"[bg_blur][fg_scale]overlay=(W-w)/2:(H-h)/2,format=yuv420p,setsar=1[bg];"
        f"[1:v]format=yuv420p,scale={RESOLUTION_W}:{RESOLUTION_H},setsar=1[v_scaled];"
        f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
        f"[bg][v_keyed]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p,setsar=1[comp];"
    )

    if clean_text:
        font_safe = str(FONT_PATH).replace('\\', '/').replace(':', '\\:')
        txt_safe = str(texto_path).replace('\\', '/').replace(':', '\\:')
        filter_complex += f"[comp]drawtext=fontfile='{font_safe}':textfile='{txt_safe}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    else:
        filter_complex += f"[comp]copy[vout];"

    audio_inputs = "[2:a]"
    input_count = 1

    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-i", bgm_path])
        audio_inputs += "[3:a]"
        input_count += 1
        
    if sfx_path and os.path.exists(sfx_path):
        cmd.extend(["-i", sfx_path])
        audio_inputs += "[4:a]"
        input_count += 1

    if input_count > 1:
        filter_complex += f"{audio_inputs}amix=inputs={input_count}:duration=first:dropout_transition=2:weights=1 0.1 0.2[aout]"
        audio_map = "-map [aout]"
    else:
        filter_complex = filter_complex.rstrip(';')
        audio_map = "-map 2:a"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", *audio_map.split(),
        "-c:v", "libx264", "-preset", VIDEO_PRESET if 'VIDEO_PRESET' in globals() else "superfast",
        "-threads", "2", "-r", str(FPS),
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        "-t", str(duracion_exacta),
        output_path
    ])

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"  [FFmpeg Ads] ❌ Error: {e}")
        return False
    finally:
        if 'texto_path' in locals() and os.path.exists(texto_path):
            try: os.remove(texto_path)
            except: pass