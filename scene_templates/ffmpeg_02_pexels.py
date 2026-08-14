# -*- coding: utf-8 -*-
"""
==============================================================================
PLANTILLA: ESCENAS CON VIDEOS DE STOCK (PEXELS) Y SOPORTE DE ADS
==============================================================================
"""
import os
import logging
import subprocess
import textwrap
import uuid
from config import *

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIONES DE TEXTO PARA PEXELS (Blindado Anti-\n)
# ==============================================================================
def formatear_texto(texto, max_chars):
    """Corta el texto dinámicamente para que encaje en los zócalos de Canva."""
    if not texto:
        return ""
        
    # 1. EXTERMINIO DE LA "\n" Y LIMPIEZA EXTREMA
    texto = texto.replace("\\n", " ").replace("\n", " ") # Adiós saltos ocultos
    texto = " ".join(texto.split()) # Quita espacios dobles
    texto = texto.replace("'", "\u2019").replace(":", "\\:") # Protege comillas
    
    # 2. CORTAR TEXTO
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=texto)
    
    if len(word_list) > 3:
        return "\n".join(word_list[:3]) + "..." # Máximo 3 líneas
    return "\n".join(word_list)

# ==============================================================================
# EL ENSAMBLADOR DE PEXELS
# ==============================================================================
def renderizar_escena_pexels(termino, overlay_path, audio_tts_path, bgm_path, sfx_path, texto, output_path, unique_id, local_ad_banner=None):
    import background_fetcher
    
    logger.info(f"  [Pexels] Buscando video para: '{termino}'...")
    
    # Intentar descargar el video de Pexels
    fondo_path = os.path.join(TEMP_VIDEO_DIR, f"pexels_bg_{unique_id}.mp4")
    fondo_path = background_fetcher.obtener_video_stock(termino, fondo_path)
    
    # Si falla, usamos un fondo por defecto
    if not fondo_path:
        fondo_path = os.path.join(ASSETS_DIR, "images", "default_news_bg.jpg")
        logger.warning(f"  [Pexels] Falló la descarga. Usando fondo por defecto.")

    # Validaciones de seguridad
    if not os.path.exists(fondo_path) or not os.path.exists(overlay_path) or not os.path.exists(audio_tts_path):
        logger.error("  [Pexels] Faltan archivos clave para ensamblar la escena.")
        return False

    # Configuración del diseño
    filename = os.path.basename(overlay_path)
    config = get_layout_config(filename)
    
    clean_text = formatear_texto(texto, config["max_letras_por_linea"])
    x, y = config["texto_x"], config["texto_y"]
    color, size = config["color"], config["font_size"]
    
    # --- AQUÍ ESTÁ EL CONTORNO (BORDER) NEGRO PARA PEXELS ---
    shadow = "bordercolor=black:borderw=2"

    # Escribimos el texto en un archivo temporal a prueba de balas
    texto_path = os.path.join(TEMP_VIDEO_DIR, f"txt_{uuid.uuid4().hex[:6]}.txt").replace('\\', '/')
    if clean_text:
        with open(texto_path, "wb") as f:
            f.write(clean_text.encode("utf-8"))

    # 3. DETECTAR TIPO DE FONDO Y APLICAR FILTROS
    es_video_fondo = fondo_path.lower().endswith(('.mp4', '.mov', '.avi'))
    cmd = ["ffmpeg", "-y"]

    if es_video_fondo:
        cmd.extend(["-stream_loop", "-1", "-i", fondo_path])
        # Bucle normal limpio para videos de Pexels, forzando a 12 FPS para máxima velocidad
        fondo_filtro_complex = (
            f"[0:v]format=yuv420p,"
            f"fps=12,"
            f"scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,"
            f"crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2[bg];"
        )
    else:
        cmd.extend(["-loop", "1", "-framerate", "12", "-i", fondo_path])
        # Zoom sutil optimizado: d=450 (quita el límite infinito) y fijado a 12 FPS
        fondo_filtro_complex = f"[0:v]scale={RESOLUTION_W*2}:-1,zoompan=z='min(zoom+0.0005,1.5)':d=450:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={RESOLUTION_W}x{RESOLUTION_H}:fps=12[bg];"

    # Entradas de FFmpeg
    cmd.extend(["-stream_loop", "-1", "-i", overlay_path])

    # --- ENTRADA EXTRA: BANNER PUBLICITARIO ---
    banner_idx = -1
    audio_idx = 2
    if local_ad_banner and os.path.exists(local_ad_banner):
        # Magia 1: Si es foto, le forzamos un loop infinito para que NO mate la escena al segundo 1
        if local_ad_banner.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            cmd.extend(["-loop", "1", "-framerate", str(FPS), "-i", local_ad_banner])
        else:
            cmd.extend(["-stream_loop", "-1", "-i", local_ad_banner])
            
        banner_idx = 2
        audio_idx = 3 # Desplazamos el audio una posición       
        logger.info("  [Pexels] 💰 Inyectando Banner Flotante de Anuncio.")

    # --- ENTRADA AUDIO TTS ---
    cmd.extend(["-i", audio_tts_path])

    filter_complex = fondo_filtro_complex + (
        f"[1:v]format=yuv420p,split=2[ov1][ov2];"
        f"[ov2]reverse[ov2r];"
        f"[ov1][ov2r]concat=n=2:v=1:a=0[pingpong_ov];"
        f"[pingpong_ov]scale={RESOLUTION_W}:{RESOLUTION_H}[v_scaled];"
        f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
        f"[bg][v_keyed]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
    )

    nodo_actual = "comp"

    # --- INYECCIÓN DEL BANNER FLOTANTE ---
# --- INYECCIÓN DEL BANNER FLOTANTE ---
# --- INYECCIÓN DEL BANNER FLOTANTE ---
    if banner_idx != -1:
        # Magia 2: scale=400:-2 asegura alturas pares siempre, y QUITAMOS el shortest=1
        filter_complex += (
            f"[{banner_idx}:v]scale=400:-2,setsar=1[banner_scaled];"
            f"[{nodo_actual}][banner_scaled]overlay=x='if(lte(t,1),W-(w+40)*t,W-w-40)':y=40[comp_ad];"
        )
        nodo_actual = "comp_ad"

    # 5. INYECCIÓN DEL ZÓCALO DE TEXTO (Blindaje Windows)
    if clean_text:
        # Escapamos los dos puntos y barras para que FFmpeg en Windows no explote
        font_safe = str(FONT_PATH).replace('\\', '/').replace(':', '\\:')
        txt_safe = str(texto_path).replace('\\', '/').replace(':', '\\:')
        
        filter_complex += f"[{nodo_actual}]drawtext=fontfile='{font_safe}':textfile='{txt_safe}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    else:
        filter_complex += f"[{nodo_actual}]copy[vout];"

    # Mezclador de Audio
    audio_inputs = f"[{audio_idx}:a]"
    input_count = 1
    current_in_idx = audio_idx + 1

    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-i", bgm_path])
        audio_inputs += f"[{current_in_idx}:a]"
        current_in_idx += 1
        input_count += 1
        
    if sfx_path and os.path.exists(sfx_path):
        cmd.extend(["-i", sfx_path])
        audio_inputs += f"[{current_in_idx}:a]"
        current_in_idx += 1
        input_count += 1

    if input_count > 1:
        filter_complex += f"{audio_inputs}amix=inputs={input_count}:duration=first:dropout_transition=2:weights=1 0.1 0.2[aout]"
        audio_map = "-map [aout]"
    else:
        filter_complex = filter_complex.rstrip(';')
        audio_map = f"-map {audio_idx}:a"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", 
        "-preset", VIDEO_PRESET, 
        "-r", str(FPS),
        "-c:a", "aac", 
        "-b:a", "128k", 
        "-shortest", 
        output_path
    ])

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return True
        return False
        
    except Exception as e:
        logger.error(f"  [FFmpeg Pexels] Error: {e}")
        return False

    finally:
        # 1. Borrar el archivo de texto temporal para mantener limpio el disco
        if 'texto_path' in locals() and os.path.exists(texto_path):
            try:
                os.remove(texto_path)
            except:
                pass
        
        # 2. Borrar el video descargado de Pexels para que AWS no colapse
        if 'fondo_path' in locals() and os.path.exists(fondo_path):
            # ¡IMPORTANTE! Validamos que NO sea la imagen por defecto de tus assets
            if "default_news_bg" not in fondo_path:
                try:
                    os.remove(fondo_path)
                except Exception as e:
                    logger.warning(f"  [Limpieza] No se pudo borrar el video de Pexels: {e}")