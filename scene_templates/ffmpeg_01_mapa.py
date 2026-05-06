# -*- coding: utf-8 -*-
"""
==============================================================================
MÓDULO FFMPEG 01: ESCENA DE MAPA (UBICACIÓN EXACTA)
==============================================================================
Este script se encarga exclusivamente de las escenas donde se debe mostrar
la ubicación de la noticia. Utiliza Mapbox para geocodificar y obtener la imagen.
"""

import os
import logging
import requests
import subprocess
import textwrap
import urllib.parse
import uuid
from config import *

logger = logging.getLogger(__name__)

# Necesitas agregar tu API KEY de Mapbox en tu archivo .env y cargarla en config.py,
# o ponerla directamente aquí si estás en fase de pruebas:
MAPBOX_API_KEY = os.getenv("MAPBOX_API_KEY", "TU_CLAVE_MAPBOX_AQUI")

def obtener_imagen_mapa(ubicacion_texto, save_path):
    """
    Paso 1: Convierte el texto (ej: "Capiatá, Paraguay") en coordenadas.
    Paso 2: Descarga la imagen del mapa estático con un pin rojo.
    """
    logger.info(f"  [FFmpeg 01 Mapa] Buscando coordenadas para: {ubicacion_texto}")
    
    try:
        # Geocodificación: Buscar Latitud y Longitud
        query_codificada = urllib.parse.quote(ubicacion_texto)
        geo_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query_codificada}.json?access_token={MAPBOX_API_KEY}&limit=1"
        
        geo_response = requests.get(geo_url, timeout=10)
        geo_data = geo_response.json()
        
        if not geo_data.get('features'):
            logger.warning("  [FFmpeg 01 Mapa] No se encontró la ubicación. Usando mapa por defecto.")
            lon, lat = -57.4333, -25.3500 # Coordenadas base (ej. Capiatá)
        else:
            lon, lat = geo_data['features'][0]['center']
            
        # Descargar mapa estático (Estilo Dark, zoom 13, 1280x720)
        # pin-s-marker+ff0000 es un pin rojo
        mapa_url = f"https://api.mapbox.com/styles/v1/mapbox/dark-v10/static/pin-s-marker+ff0000({lon},{lat})/{lon},{lat},13,0,0/1280x720?access_token={MAPBOX_API_KEY}"
        
        mapa_response = requests.get(mapa_url, stream=True, timeout=15)
        if mapa_response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in mapa_response.iter_content(8192):
                    f.write(chunk)
            return save_path
        else:
            logger.error(f"  [FFmpeg 01 Mapa] Error al descargar mapa: {mapa_response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"  [FFmpeg 01 Mapa] Error en la API de Mapbox: {e}")
        return None

def formatear_texto_mapa(texto, max_chars):
    """Corta el texto dinámicamente y limpia la basura de Windows"""
    if not texto:
        return ""
    
    # 1. EXTERMINIO DE LA "n" Y RETORNOS DE CARRO FANTASMAS
    texto = texto.replace("\\n", " ").replace("\n", " ").replace("\r", "")
    texto = " ".join(texto.split()) # Quita espacios dobles
    texto = texto.replace("'", "\u2019").replace(":", "\:") # Protege comillas y dos puntos
    
    # 2. CORTAR TEXTO
    wrapper = textwrap.TextWrapper(width=max_chars)
    word_list = wrapper.wrap(text=texto)
    
    if len(word_list) > 3:
        return "\n".join(word_list[:3]) + "..."
    return "\n".join(word_list)

def renderizar_escena_mapa(ubicacion_texto, overlay_mp4_path, audio_tts_path, bgm_path, sfx_path, texto_zocalo, output_path, unique_id):
    """
    Ensambla la imagen del mapa con un zoom lento, perfora el chroma del overlay,
    agrega los textos, la voz y la música.
    """
    logger.info("  [FFmpeg 01 Mapa] Iniciando renderizado de la escena...")
    
    # 1. Obtener la foto del mapa
    mapa_img_path = os.path.join(TEMP_IMG_DIR, f"mapa_{unique_id}.jpg")
    if not obtener_imagen_mapa(ubicacion_texto, mapa_img_path):
        return False # Si falla el mapa, abortamos esta escena específica
        
    # 2. Configuración del diseño (Zócalo sin presentador)
    filename = os.path.basename(overlay_mp4_path)
    # Reemplazamos la función de búsqueda para que sea universal
    config = get_layout_config(filename) if 'get_layout_config' in globals() else LAYOUT_CONFIG.get(filename, DEFAULT_LAYOUT)
    
    clean_text = formatear_texto_mapa(texto_zocalo, config["max_letras_por_linea"])
    x, y = config["texto_x"], config["texto_y"]
    color, size = config["color"], config["font_size"]
    
    # --- AQUÍ ESTÁ EL CONTORNO MÁS FINO ---
    shadow = "bordercolor=black:borderw=2" 

    # Escribimos el archivo en MODO BINARIO ("wb") para matar el cuadradito de Windows
    texto_path = os.path.join(TEMP_VIDEO_DIR, f"txt_map_{uuid.uuid4().hex[:6]}.txt").replace('\\', '/')
    if clean_text:
        with open(texto_path, "wb") as f:
            f.write(clean_text.encode("utf-8"))
    
    # 3. Construir el filtro complejo de FFmpeg
    # [bg]: Efecto de ZOOM lento al mapa (zoompan) para que parezca un dron
    # [v_scaled]: Overlay verde
    # [v_keyed]: Perforación del verde
# 3. Construir el filtro complejo de FFmpeg
    filter_complex = (
        f"[0:v]scale={RESOLUTION_W*2}:-2,zoompan=z='min(zoom+0.002,1.5)':d=450:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={RESOLUTION_W}x{RESOLUTION_H}:fps=15[bg];"
        f"[1:v]scale=-1:{RESOLUTION_H}[v_scaled];"
        f"[v_scaled]chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[v_keyed];"
        f"[bg][v_keyed]overlay=(W-w)/2:(H-h)/2:shortest=1[comp];"
    )
    
    # INYECCIÓN DEL ZÓCALO DE TEXTO (Blindaje Windows)
    if clean_text:
        font_safe = str(FONT_PATH).replace('\\', '/').replace(':', '\\:')
        txt_safe = str(texto_path).replace('\\', '/').replace(':', '\\:')
        filter_complex += f"[comp]drawtext=fontfile='{font_safe}':textfile='{txt_safe}':fontcolor={color}:fontsize={size}:{shadow}:x={x}:y={y}[vout];"
    else:
        filter_complex += f"[comp]copy[vout];"
    
    # 4. Gestión dinámica de audio
    audio_inputs = "[2:a]"
    input_count = 1
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", mapa_img_path,         # [0:v] Foto del mapa
        "-stream_loop", "-1", "-i", overlay_mp4_path, # [1:v] Video verde sin presentador
        "-i", audio_tts_path                       # [2:a] Voz TTS
    ]
    
    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(["-i", bgm_path])               # [3:a] Música
        audio_inputs += "[3:a]"
        input_count += 1
        
    if sfx_path and os.path.exists(sfx_path):
        cmd.extend(["-i", sfx_path])               # [4:a] Sonido (Ej. Teclado procesando datos)
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
        "-map", "[vout]", 
        *audio_map.split(),
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path
    ])
    
    # 5. Ejecutar el subproceso
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"  [FFmpeg 01 Mapa] Fallo crítico renderizando: {e}")
        return False
    finally:
        # 1. Borrar el archivo de texto temporal
        if 'texto_path' in locals() and os.path.exists(texto_path):
            try:
                os.remove(texto_path)
            except:
                pass
                
        # 2. Borrar la imagen JPG del mapa descargada
        if 'mapa_img_path' in locals() and os.path.exists(mapa_img_path):
            try:
                os.remove(mapa_img_path)
            except:
                pass