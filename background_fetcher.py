# -*- coding: utf-8 -*-
"""
==============================================================================
BACKGROUND FETCHER (Los Recolectores de Fondos)
==============================================================================
Este módulo se conecta a APIs externas (Mapbox, Pexels, Pixabay) y a la web
para descargar la "materia prima" visual. Ahora incluye memoria anti-duplicación.
"""

import os
import time
import random
import logging
import requests
import subprocess
import urllib.parse
from config import *

logger = logging.getLogger(__name__)

# ==============================================================================
# CLAVES DE APIS (Deben estar en tu archivo .env)
# ==============================================================================
MAPBOX_API_KEY = os.getenv("MAPBOX_API_KEY", "TU_CLAVE_MAPBOX_AQUI")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "TU_CLAVE_PEXELS_AQUI")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "TU_CLAVE_PIXABAY_AQUI")

# Historial global para no repetir videos de Pexels
_historial_pexels = []


# ==============================================================================
# 1. RECOLECTOR DE LA FOTO REAL DE LA NOTICIA (MODO STEALTH BROWSER)
# ==============================================================================

# Pon aquí la URL directa a tu logo para el 1% de casos que fallen
URL_LOGO_FALLBACK = "https://noticias.lat/favicon.png" 

def sanitizar_imagen(ruta_archivo):
    """Verifica silenciosamente si es una imagen real sin ensuciar la consola"""
    clean_path = ruta_archivo + "_clean.jpg"
    cmd_sanitize = [
        "ffmpeg", "-y", "-v", "fatal", # 'fatal' oculta todos los errores feos de la consola
        "-i", ruta_archivo,
        "-vf", "scale='min(1920,iw)':-2",
        "-frames:v", "1",
        clean_path
    ]
    try:
        # Silenciamos la salida completamente
        subprocess.run(cmd_sanitize, timeout=10, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(clean_path, ruta_archivo) 
        return True
    except:
        if os.path.exists(ruta_archivo): os.remove(ruta_archivo)
        if os.path.exists(clean_path): os.remove(clean_path)
        return False

def obtener_imagen_noticia(url, save_path, retries=3):
    if not url or url == "":
        url = URL_LOGO_FALLBACK
        
    logger.info(f"  [Fetcher] Descargando imagen (Modo Browser): {url[:50]}...")
    
    # CABECERAS EXTREMAS: Engañamos a Cloudflare y Firewalls haciéndonos pasar por Chrome
    headers_humanos = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site'
    }

    for attempt in range(retries):
        # INTENTO 1: Requests con camuflaje total
        try:
            r = requests.get(url, headers=headers_humanos, verify=False, timeout=15)
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(r.content)
                if os.path.getsize(save_path) > 1024 and sanitizar_imagen(save_path):
                    return save_path
        except Exception:
            pass

        # INTENTO 2: Curl con camuflaje total
        try:
            cmd = [
                "curl", "-L", "-k", "--retry", "2", "-s",
                "-A", headers_humanos['User-Agent'],
                "-H", f"Accept: {headers_humanos['Accept']}",
                "-H", f"Referer: {headers_humanos['Referer']}",
                "-o", save_path, url
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1024 and sanitizar_imagen(save_path):
                return save_path
        except Exception:
            pass
            
        time.sleep(1)

    # =========================================================================
    # EL 1% DE FALLO: SALVAVIDAS ACTIVADO (LOGO NOTICIAS.LAT)
    # =========================================================================
    logger.warning(f"  [Fetcher] Bloqueo extremo detectado. Usando LOGO DE RESPALDO...")
    try:
        r_logo = requests.get(URL_LOGO_FALLBACK, verify=False, timeout=10)
        if r_logo.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(r_logo.content)
            if sanitizar_imagen(save_path):
                return save_path
    except Exception as e:
        logger.error(f"  [Fetcher] Falló hasta el logo de respaldo: {e}")
        
    return None


# ==============================================================================
# 2. RECOLECTOR DE MAPAS (MAPBOX)
# ==============================================================================
def obtener_mapa_mapbox(ubicacion_texto, save_path):
    logger.info(f"  [Fetcher] Generando mapa para: '{ubicacion_texto}'")
    
    if MAPBOX_API_KEY == "TU_CLAVE_MAPBOX_AQUI":
        logger.error("  [Fetcher] ERROR: Falta MAPBOX_API_KEY en el entorno.")
        return None

    try:
        query = urllib.parse.quote(ubicacion_texto)
        geo_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json?access_token={MAPBOX_API_KEY}&limit=1"
        
        geo_res = requests.get(geo_url, timeout=10)
        geo_data = geo_res.json()
        
        if not geo_data.get('features'):
            logger.warning(f"  [Fetcher] Mapbox no reconoció el lugar '{ubicacion_texto}'.")
            return None
            
        lon, lat = geo_data['features'][0]['center']
        
        estilo = "dark-v10"
        zoom = "13"
        ancho, alto = RESOLUTION_W, RESOLUTION_H
        
        mapa_url = f"https://api.mapbox.com/styles/v1/mapbox/{estilo}/static/pin-s-marker+ff0000({lon},{lat})/{lon},{lat},{zoom},0,0/{ancho}x{alto}?access_token={MAPBOX_API_KEY}"
        
        mapa_res = requests.get(mapa_url, stream=True, timeout=15)
        if mapa_res.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in mapa_res.iter_content(8192):
                    f.write(chunk)
            return save_path
        else:
            logger.error(f"  [Fetcher] Error Mapbox: HTTP {mapa_res.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"  [Fetcher] Error fatal en Mapbox: {e}")
        return None

# ==============================================================================
# 3. RECOLECTOR DE B-ROLL (PEXELS CON MEMORIA ANTI-DUPLICACIÓN)
# ==============================================================================
def obtener_video_stock(termino_busqueda, save_path):
    global _historial_pexels
    logger.info(f"  [Fetcher] Buscando video B-Roll sobre: '{termino_busqueda}'")
    
    if PEXELS_API_KEY == "TU_CLAVE_PEXELS_AQUI":
        logger.error("  [Fetcher] ERROR: Falta PEXELS_API_KEY.")
        return None

    try:
        query = urllib.parse.quote(termino_busqueda)
        # Pedimos hasta 15 resultados para tener de dónde elegir al azar
        url = f"https://api.pexels.com/videos/search?query={query}&orientation=landscape&per_page=15"
        headers = {'Authorization': PEXELS_API_KEY}
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if not data.get('videos') or len(data['videos']) == 0:
            logger.warning(f"  [Fetcher] Cero resultados en Pexels para '{termino_busqueda}'.")
            return None
            
        # Filtramos los videos que NO hemos usado recientemente
        videos_disponibles = [v for v in data['videos'] if v['id'] not in _historial_pexels]
        
        # Si ya usamos todos, reseteamos la lista y agarramos uno al azar igual
        if not videos_disponibles:
            logger.warning("  [Pexels] Ya se usaron todos los resultados, repitiendo...")
            videos_disponibles = data['videos']

        # Elegimos al azar para garantizar variedad
        video_elegido = random.choice(videos_disponibles)
        
        # Guardamos en la memoria y limpiamos si hay más de 50 (para no ahogar la RAM en AWS)
        _historial_pexels.append(video_elegido['id'])
        if len(_historial_pexels) > 50:
            _historial_pexels.pop(0)

        video_link = None
        video_files = video_elegido.get('video_files', [])
        
        # Ordenamos buscando HD sin llegar a 4K que destruya tu t3.micro
        video_files.sort(key=lambda x: x.get('width', 0), reverse=True)
        
        for file in video_files:
            if file.get('link') and file.get('quality') == 'hd' and file.get('width', 0) >= 1280:
                video_link = file['link']
                break
                
        if not video_link and video_files:
            video_link = video_files[0].get('link')
            
        if not video_link:
            return None
            
        logger.info(f"  [Pexels] Descargando ID: {video_elegido['id']}")
        
        r = requests.get(video_link, stream=True, timeout=30)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk: f.write(chunk)
            
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                return save_path
        
        logger.error(f"  [Fetcher] Error descargando MP4: HTTP {r.status_code}")
        return None

    except Exception as e:
        logger.error(f"  [Fetcher] Error fatal en la API de Pexels: {e}")
        return None