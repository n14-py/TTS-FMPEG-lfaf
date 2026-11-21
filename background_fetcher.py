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
import process_guard

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

def _max_image_bytes():
    try:
        return max(1024, int(os.getenv("MAX_IMAGE_DOWNLOAD_BYTES", str(25 * 1024 * 1024))))
    except ValueError:
        return 25 * 1024 * 1024


def _guardar_respuesta(response, save_path, max_bytes):
    """Escribe el cuerpo tal cual, y aborta si supera el tope para no agotar la RAM."""
    total = 0
    try:
        with open(save_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    break
                handle.write(chunk)
    except Exception:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        return False
    if total > max_bytes or total <= 0:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        return False
    return True


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
        process_guard.run(cmd_sanitize, timeout=10, check=True, log_label="Fetcher imagen")
        os.replace(clean_path, ruta_archivo) 
        return True
    except:
        if os.path.exists(ruta_archivo): os.remove(ruta_archivo)
        if os.path.exists(clean_path): os.remove(clean_path)
        return False

def obtener_imagen_noticia(url, save_path, retries=3):
    if not url or url == "":
        url = URL_LOGO_FALLBACK
        
    logger.info(f"  [Fetcher] Descargando imagen: {url[:50]}...")
    
    # 🎭 EL DISFRAZ PERFECTO QUE FUNCIONÓ EN TUS PRUEBAS
    cabeceras_falsas = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/"
    }

    for attempt in range(retries):
        # ==========================================
        # INTENTO 1: Descarga Directa Disfrazada
        # ==========================================
        try:
            r = requests.get(url, headers=cabeceras_falsas, timeout=10, stream=True)
            try:
                if r.status_code == 200 and _guardar_respuesta(r, save_path, _max_image_bytes()):
                    if os.path.getsize(save_path) > 1024 and sanitizar_imagen(save_path):
                        return save_path
            finally:
                r.close()
        except Exception:
            pass

        # ==========================================
        # INTENTO 2: El Puente de Google (Alternativa)
        # ==========================================
        try:
            url_magica = f"https://images10-focus-opensocial.googleusercontent.com/gadgets/proxy?container=focus&refresh=2592000&url={url}"
            r_proxy = requests.get(url_magica, timeout=10, stream=True)
            try:
                if r_proxy.status_code == 200 and _guardar_respuesta(r_proxy, save_path, _max_image_bytes()):
                    if os.path.getsize(save_path) > 1024 and sanitizar_imagen(save_path):
                        logger.info("  [Fetcher] Imagen obtenida exitosamente usando el Puente de Google.")
                        return save_path
            finally:
                r_proxy.close()
        except Exception:
            pass
            
        time.sleep(1)

    # =========================================================================
    # EL 1% DE FALLO: SALVAVIDAS ACTIVADO (LOGO NOTICIAS.LAT)
    # =========================================================================
    logger.warning(f"  [Fetcher] Bloqueo extremo detectado. Usando LOGO DE RESPALDO...")
    try:
        r_logo = requests.get(URL_LOGO_FALLBACK, verify=False, timeout=10, stream=True)
        try:
            if r_logo.status_code == 200 and _guardar_respuesta(r_logo, save_path, _max_image_bytes()):
                if sanitizar_imagen(save_path):
                    return save_path
        finally:
            r_logo.close()
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
        try:
            if mapa_res.status_code == 200:
                if _guardar_respuesta(mapa_res, save_path, _max_image_bytes()):
                    return save_path
                logger.error("  [Fetcher] El mapa de Mapbox no se pudo guardar.")
                return None
            logger.error(f"  [Fetcher] Error Mapbox: HTTP {mapa_res.status_code}")
            return None
        finally:
            mapa_res.close()
            
    except Exception as e:
        logger.error(f"  [Fetcher] Error fatal en Mapbox: {e}")
        return None

# ==============================================================================
# 3. RECOLECTOR DE B-ROLL (PEXELS CON MEMORIA ANTI-DUPLICACIÓN Y BLINDAJE)
# ==============================================================================

def _parece_mp4(ruta_archivo):
    try:
        with open(ruta_archivo, "rb") as handle:
            cabecera = handle.read(32)
    except OSError:
        return False
    return b"ftyp" in cabecera


def sanitizar_video(ruta_archivo):
    """Verifica silenciosamente que el archivo bajado de Pexels sea un video real"""
    cmd_check = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=nw=1:nk=1",
        ruta_archivo
    ]
    try:
        resultado = process_guard.run(cmd_check, timeout=20, capture_output=True, log_label="Fetcher ffprobe")
        # Si ffprobe responde "video", entonces es un MP4 válido
        if "video" in (resultado.stdout or "").lower():
            return True
    except Exception:
        pass
    # Un MP4 real empieza con ftyp. Si ffprobe no alcanzó a leerlo, no lo tiramos.
    return _parece_mp4(ruta_archivo)


def _termino_pexels(termino):
    """La API a veces manda null o una lista. quote() revienta con eso y no se baja nada."""
    if isinstance(termino, (list, tuple)):
        partes = [str(parte).strip() for parte in termino if str(parte).strip() and str(parte).strip().lower() != "none"]
        termino = " ".join(partes)
    elif not isinstance(termino, str):
        termino = ""
    texto = " ".join(termino.replace("\n", " ").split())
    if texto.lower() == "none":
        texto = ""
    return texto[:80] or "news"


def _elegir_enlace_pexels(video_files):
    """Elige un MP4 cercano a 1280 px. El más ancho tarda y se corta por timeout."""
    candidatos = []
    for archivo in video_files or []:
        if not isinstance(archivo, dict):
            continue
        enlace = archivo.get("link")
        if not enlace:
            continue
        tipo = str(archivo.get("file_type") or "").lower()
        ruta = str(enlace).split("?", 1)[0].lower()
        if tipo and "mp4" not in tipo and not ruta.endswith(".mp4"):
            continue
        try:
            ancho = int(archivo.get("width") or 0)
        except (TypeError, ValueError):
            ancho = 0
        candidatos.append((ancho, str(archivo.get("quality") or ""), enlace))
    hd = [item for item in candidatos if item[1] == "hd" and item[0] >= 1280]
    pool = hd or candidatos
    if not pool:
        return None
    pool.sort(key=lambda item: (abs((item[0] or 1280) - 1280), item[0] or 99999))
    return pool[0][2]


def _buscar_videos_pexels(termino):
    query = urllib.parse.quote(_termino_pexels(termino))
    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": "NoticiasLAT-VideoBot/1.0",
    }
    endpoints = [
        "https://api.pexels.com/videos/search?query=%s&orientation=landscape&per_page=15" % query,
        "https://api.pexels.com/v1/videos/search?query=%s&orientation=landscape&per_page=15" % query,
    ]
    for url in endpoints:
        try:
            response = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as exc:
            logger.warning("  [Fetcher] Pexels no respondió: %s", exc)
            continue
        try:
            data = response.json()
        except ValueError:
            logger.warning("  [Fetcher] Pexels no devolvió JSON (HTTP %s).", response.status_code)
            continue
        videos = data.get("videos") if isinstance(data, dict) else None
        if response.status_code == 200 and videos:
            return videos
        detalle = ""
        if isinstance(data, dict):
            detalle = str(data.get("error") or data.get("status") or "")[:160]
        logger.warning("  [Fetcher] Búsqueda Pexels HTTP %s. %s", response.status_code, detalle)
    return []


def obtener_video_stock(termino_busqueda, save_path):
    global _historial_pexels
    termino = _termino_pexels(termino_busqueda)
    logger.info(f"  [Fetcher] Buscando video B-Roll sobre: '{termino}'")
    
    if PEXELS_API_KEY == "TU_CLAVE_PEXELS_AQUI":
        logger.error("  [Fetcher] ERROR: Falta PEXELS_API_KEY.")
        return None

    try:
        carpeta = os.path.dirname(save_path)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)

        videos = _buscar_videos_pexels(termino)
        if not videos:
            logger.warning(f"  [Fetcher] Cero resultados en Pexels para '{termino}'.")
            return None
            
        videos_disponibles = [v for v in videos if isinstance(v, dict) and v.get("id") not in _historial_pexels]
        if not videos_disponibles:
            videos_disponibles = [v for v in videos if isinstance(v, dict)]
        random.shuffle(videos_disponibles)

        for video_elegido in videos_disponibles[:4]:
            video_link = _elegir_enlace_pexels(video_elegido.get("video_files"))
            if not video_link:
                continue
            video_id = video_elegido.get("id")
            logger.info(f"  [Pexels] Descargando ID: {video_id}")
            try:
                r = requests.get(
                    video_link,
                    stream=True,
                    timeout=(10, 90),
                    headers={"User-Agent": "NoticiasLAT-VideoBot/1.0"},
                )
            except requests.RequestException as exc:
                logger.warning("  [Fetcher] No se pudo bajar el video %s: %s", video_id, exc)
                continue
            try:
                guardado = _guardar_video_pexels(r, save_path)
            finally:
                r.close()
            if guardado:
                _historial_pexels.append(video_id)
                if len(_historial_pexels) > 50:
                    _historial_pexels.pop(0)
                return guardado
        return None

    except Exception as e:
        logger.error(f"  [Fetcher] Error fatal en la API de Pexels: {e}")
        return None


def _guardar_video_pexels(r, save_path):
    if r.status_code == 200:
        try:
            max_video = max(1024, int(os.getenv("MAX_PEXELS_DOWNLOAD_BYTES", str(300 * 1024 * 1024))))
        except ValueError:
            max_video = 300 * 1024 * 1024
        total = 0
        demasiado = False
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_video:
                    demasiado = True
                    break
                f.write(chunk)
        if demasiado:
            logger.warning("  [Fetcher] El video de Pexels supera el tamaño máximo. Se descarta.")
            if os.path.exists(save_path):
                os.remove(save_path)
            return None

        if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
            if sanitizar_video(save_path):
                return save_path
            logger.warning("  [Fetcher] ¡Video falso/corrupto de Pexels detectado! Abortando escena de forma segura.")
            os.remove(save_path)
            return None
        logger.error("  [Fetcher] El MP4 de Pexels llegó vacío.")
        return None

    logger.error(f"  [Fetcher] Error descargando MP4: HTTP {r.status_code}")
    return None