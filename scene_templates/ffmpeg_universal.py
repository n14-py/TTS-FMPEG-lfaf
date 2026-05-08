# -*- coding: utf-8 -*-
"""
==============================================================================
SÚPER MÓDULO FFMPEG UNIVERSAL: MOTOR DINÁMICO ALEATORIO
==============================================================================
Este es el ensamblador definitivo. No solo une capas, sino que inyecta
aleatoriedad matemática en cada renderizado. Aplica movimientos de cámara
(Ken Burns) aleatorios a las imágenes y corrección de color dinámica a los 
videos de B-Roll para que NINGUNA ESCENA SEA IDÉNTICA A OTRA.
"""

import os
import random
import logging
import subprocess
import textwrap
from config import *

logger = logging.getLogger(__name__)

def obtener_duracion_audio(audio_path):
    """Mide los segundos exactos del MP3"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    try:
        resultado = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
        return float(resultado.stdout.strip()) + 0.4
    except Exception:
        return 25.0

# ==============================================================================
# FUNCIONES DE TEXTO
# ==============================================================================
def formatear_texto(texto, max_chars):
    """Corta el texto dinámicamente para que encaje en los zócalos de Canva."""
    if not texto:
        return ""
        
    # 1. EXTERMINIO DE LA "n" Y LIMPIEZA EXTREMA
    texto = texto.replace("\\n", " ").replace("\n", " ") # Adiós saltos ocultos
    texto = " ".join(texto.split()) # Quita espacios dobles
    texto = texto.replace("'", "\u2019").replace(":", "\:") # Protege comillas
    
    # 2. CORTAR TEXTO
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=texto)
    
    if len(word_list) > 3:
        return "\n".join(word_list[:3]) + "..."
    return "\n".join(word_list)

# ==============================================================================
# MOTORES DE ALEATORIEDAD VISUAL
# ==============================================================================
def generar_movimiento_camara_imagen():
    """
    Motor Ken Burns Optimizado: Menos resolución de entrada y frames ajustados.
    """
    # Bajamos la velocidad para que se vea suave a 20fps
    velocidad = "0.001" 
    
    efectos = [
        # 1. ZOOM IN (Escalamos solo a 1.5x en lugar de 2x para ahorrar CPU)
        f"[0:v]scale={RESOLUTION_W*1.5}:-2,zoompan=z='min(zoom+{velocidad},1.3)':d=200:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={RESOLUTION_W}x{RESOLUTION_H}:fps={FPS}[bg];",
        
        # 2. PANEO DERECHA
        f"[0:v]scale=-2:{RESOLUTION_H*1.5},zoompan=z=1.1:d=200:x='x+2':y='ih/2-(ih/zoom/2)':s={RESOLUTION_W}x{RESOLUTION_H}:fps={FPS}[bg];",
        
        # 3. PANEO IZQUIERDA
        f"[0:v]scale=-2:{RESOLUTION_H*1.5},zoompan=z=1.1:d=200:x='if(eq(on,1),iw-iw/zoom,x-2)':y='ih/2-(ih/zoom/2)':s={RESOLUTION_W}x{RESOLUTION_H}:fps={FPS}[bg];",
        
        # 4. PANEO ABAJO
        f"[0:v]scale={RESOLUTION_W*1.5}:-2,zoompan=z=1.1:d=200:x='iw/2-(iw/zoom/2)':y='y+2':s={RESOLUTION_W}x{RESOLUTION_H}:fps={FPS}[bg];"
    ]
    
    efecto_elegido = random.choice(efectos)
    logger.info(f"    [FX Motor] Aplicando movimiento optimizado ({FPS}fps): {efectos.index(efecto_elegido) + 1}")
    return efecto_elegido


def generar_color_grading_video():
    """
    Aplica Color Grading. El bucle normal se maneja desde el input (-stream_loop -1).
    """
    filtros_color = [
        "eq=contrast=1.05:saturation=1.1",     
        "eq=contrast=1.1:brightness=-0.02",    
        "eq=saturation=0.9:gamma=1.05",        
        "colorbalance=rs=.05:gs=.02:bs=-.02",  
        "colorbalance=rs=-.05:gs=.02:bs=.05",  
        "eq=contrast=1.0"                      
    ]
    
    filtro_elegido = random.choice(filtros_color)
    logger.info(f"    [FX Motor] Color Grading: {filtro_elegido}")
    
    # Filtro limpio, sin reverse ni concat
    filtro_completo = (
        f"[0:v]format=yuv420p,"
        f"{filtro_elegido},"
        f"scale={RESOLUTION_W}:{RESOLUTION_H}:force_original_aspect_ratio=increase,"
        f"crop={RESOLUTION_W}:{RESOLUTION_H}:(iw-ow)/2:(ih-oh)/2[bg];"
    )
    return filtro_completo


# ==============================================================================
# EL ENSAMBLADOR MAESTRO
# ==============================================================================
# ==============================================================================
# EL ENSAMBLADOR MAESTRO
# ==============================================================================
def ensamblar_escena(fondo_path, overlay_path, audio_tts_path, bgm_path, sfx_path, texto, output_path):
    """
    La bestia que une todo.
    """
    duracion_exacta = obtener_duracion_audio(audio_tts_path)
    logger.info(f"  [FFmpeg Universal] Ensamblando escena de alta complejidad (Duración: {duracion_exacta}s)...")
    logger.info(f"  --> Fondo: {os.path.basename(fondo_path)}")
    logger.info(f"  --> Overlay: {os.path.basename(overlay_path)}")

    # 1. VALIDACIONES DE SEGURIDAD
    if not os.path.exists(fondo_path) or not os.path.exists(overlay_path) or not os.path.exists(audio_tts_path):
        logger.error("  [FFmpeg Universal] Faltan archivos clave para ensamblar la escena.")
        return False

    # 2. OBTENER COORDENADAS DEL DICCIONARIO (config.py)
    filename = os.path.basename(overlay_path)
    config = get_layout_config(filename)
    
    clean_text = formatear_texto(texto, config["max_letras_por_linea"])
    x, y = config["texto_x"], config["texto_y"]
    color, size = config["color"], config["font_size"]
    
    # --- AQUÍ ESTÁ EL CONTORNO (BORDER) ---
    shadow = "bordercolor=black:borderw=2" 

    # Escribimos el texto en un archivo temporal para FFmpeg
    import uuid
    texto_path = os.path.join(TEMP_VIDEO_DIR, f"txt_{uuid.uuid4().hex[:6]}.txt").replace('\\', '/')
    if clean_text:
        with open(texto_path, "wb") as f:
            f.write(clean_text.encode("utf-8"))

    # 3. DETECTAR TIPO DE FONDO Y APLICAR MOTORES ALEATORIOS
    es_video_fondo = fondo_path.lower().endswith(('.mp4', '.mov', '.avi'))
    cmd = ["ffmpeg", "-y"]

    if es_video_fondo:
        # Bucle infinito normal, quitamos el "-t 6"
        cmd.extend(["-stream_loop", "-1", "-i", fondo_path])
        fondo_filtro_complex = generar_color_grading_video()
    else:
        # Es una imagen (Foto de la noticia o Mapa)
        cmd.extend(["-loop", "1", "-framerate", str(FPS), "-i", fondo_path])
        fondo_filtro_complex = generar_movimiento_camara_imagen()

    # --- ENTRADA 1: EL OVERLAY (PANTALLA VERDE) ---
    cmd.extend(["-stream_loop", "-1", "-i", overlay_path])

    # --- ENTRADA 2: EL AUDIO PRINCIPAL (Voz TTS) ---
    cmd.extend(["-i", audio_tts_path])

    # 4. CONSTRUCCIÓN DEL CHROMA KEY Y OVERLAY FINAL
# 4. CONSTRUCCIÓN DEL CHROMA KEY Y OVERLAY FINAL
    filter_complex = fondo_filtro_complex + (
        f"[1:v]format=yuv420p,scale={RESOLUTION_W}:{RESOLUTION_H}[v_scaled];"
        f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
        f"[bg][v_keyed]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
    )

    # 5. INYECCIÓN DEL ZÓCALO DE TEXTO (Usando el archivo temporal .txt)
# 5. INYECCIÓN DEL ZÓCALO DE TEXTO (Blindaje Windows)
    if clean_text:
        # Escapamos los dos puntos y barras para que FFmpeg en Windows no explote
        font_safe = str(FONT_PATH).replace('\\', '/').replace(':', '\\:')
        txt_safe = str(texto_path).replace('\\', '/').replace(':', '\\:')
        
        filter_complex += f"[comp]drawtext=fontfile='{font_safe}':textfile='{txt_safe}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    else:
        filter_complex += f"[comp]copy[vout];"

    # 6. MEZCLADOR MATRICIAL DE AUDIO PROFESIONAL
    audio_inputs = "[2:a]"
    input_count = 1

    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-i", bgm_path])  # Entrada 3
        audio_inputs += "[3:a]"
        input_count += 1
        
    if sfx_path and os.path.exists(sfx_path):
        cmd.extend(["-i", sfx_path])  # Entrada 4
        audio_inputs += "[4:a]"
        input_count += 1

    if input_count > 1:
        # Mezcla música y SFX por debajo de la voz, con un fadeout natural
        filter_complex += f"{audio_inputs}amix=inputs={input_count}:duration=first:dropout_transition=2:weights=1 0.1 0.2[aout]"
        audio_map = "-map [aout]"
    else:
        filter_complex = filter_complex.rstrip(';')
        audio_map = "-map 2:a"

# 7. COMPILACIÓN DEL COMANDO Y RENDERIZADO
# 7. COMPILACIÓN DEL COMANDO Y RENDERIZADO
    cmd.extend([
        "-filter_threads", "2",  
        "-filter_complex", filter_complex,
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", 
        "-preset", "superfast", 
        "-threads", "2",         
        "-r", str(FPS),
        "-c:a", "aac", 
        "-b:a", "128k", 
        "-t", str(duracion_exacta), 
        output_path
    ])

    try:
        logger.info(f"    [FFmpeg] Ejecutando renderizado de la escena...")
        proceso = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proceso.communicate(timeout=200) 
        
        if proceso.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            logger.info(f"  [FFmpeg Universal] ¡ÉXITO! Escena lista: {os.path.basename(output_path)}")
            return True
        else:
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("  [FFmpeg Universal] TIMEOUT: Matando proceso Zombi...")
        proceso.kill() 
        proceso.communicate() 
        return False
    except Exception as e:
        logger.error(f"  [FFmpeg Universal] Error inesperado en el sistema: {e}")
        if 'proceso' in locals():
            proceso.kill()
            proceso.communicate()
        return False
            
    except subprocess.TimeoutExpired:
        logger.error("  [FFmpeg Universal] TIMEOUT: La escena tardó demasiado. Abortando hilo.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"  [FFmpeg Universal] FFmpeg se estrelló procesando los filtros complejos. Código de error: {e.returncode}")
        return False
    except Exception as e:
        logger.error(f"  [FFmpeg Universal] Error inesperado en el sistema: {e}")
        return False 
    finally:
        # Borramos el txt temporal para mantener el servidor limpio
        if 'texto_path' in locals() and os.path.exists(texto_path):
            try:
                os.remove(texto_path)
            except:
                pass