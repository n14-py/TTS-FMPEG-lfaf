# -*- coding: utf-8 -*-
"""
==============================================================================
MEDIA MANAGER (Gestor de Recursos Visuales y Sonoros)
==============================================================================
Este módulo se encarga de escanear los directorios locales para seleccionar
aleatoriamente músicas, efectos, intros y layouts sin causar errores.
También maneja la descarga de imágenes dinámicas enviadas por Node.js.
"""

import os
import random
import logging
import requests
from config import *

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIONES DE SELECCIÓN ALEATORIA LOCAL
# ==============================================================================
def get_random_file_from_dir(directory):
    """
    Busca en un directorio dado y devuelve la ruta absoluta de un archivo al azar.
    Si la carpeta está vacía o no existe, devuelve None.
    """
    if not os.path.exists(directory):
        logger.warning(f"  [MediaManager] Directorio no encontrado: {directory}")
        return None
        
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    
    # Ignorar archivos ocultos o de sistema (como .DS_Store)
    files = [f for f in files if not f.startswith('.')]
    
    if not files:
        logger.warning(f"  [MediaManager] Directorio vacío: {directory}")
        return None
        
    chosen_file = random.choice(files)
    return os.path.join(directory, chosen_file)

def get_random_bgm(mood):
    """
    Busca una música de fondo según el mood ('urgencia', 'analisis', 'tension').
    """
    mood_dir = os.path.join(BGM_DIR, mood)
    bgm_path = get_random_file_from_dir(mood_dir)
    
    # Fallback de seguridad si no hay música en esa carpeta
    if not bgm_path:
        logger.warning(f"  [MediaManager] Fallback a primera música disponible.")
        # Intenta buscar en cualquier carpeta de BGM
        for d in os.listdir(BGM_DIR):
            fallback_dir = os.path.join(BGM_DIR, d)
            if os.path.isdir(fallback_dir):
                bgm_path = get_random_file_from_dir(fallback_dir)
                if bgm_path: break
                
    return bgm_path

def get_random_sfx(sfx_type):
    """
    Busca un efecto de sonido ('transiciones', 'impactos', 'alertas', 'tecnologia').
    """
    sfx_dir = os.path.join(SFX_DIR, sfx_type)
    return get_random_file_from_dir(sfx_dir)

def get_random_template(template_type):
    """
    Busca un video base según el tipo ('intros', 'hombre', 'mujer', 'sin_presentador').
    Devuelve la ruta absoluta.
    """
    template_dir = os.path.join(TEMPLATES_DIR, template_type)
    return get_random_file_from_dir(template_dir)

# ==============================================================================
# FUNCIONES DE DESCARGA (FOTOS Y VIDEOS DINÁMICOS)
# ==============================================================================
def download_media(url, save_path, retries=2):
    """
    Descarga una imagen o video desde una URL y la guarda en save_path.
    Tiene tolerancia a fallos.
    """
    if not url:
        return None
        
    logger.info(f"  [MediaManager] Descargando recurso: {url[:50]}...")
    
    for attempt in range(retries):
        try:
            # Usar un User-Agent realista para evitar bloqueos
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, stream=True, timeout=15)
            
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                        
                # Verificar tamaño mínimo (evitar imágenes corruptas de 1kb)
                if os.path.getsize(save_path) > 1024:
                    return save_path
            
            logger.warning(f"  [MediaManager] Servidor devolvió status {response.status_code}")
            
        except Exception as e:
            logger.warning(f"  [MediaManager] Fallo intento {attempt+1}: {e}")
            
    logger.error("  [MediaManager] Fallo definitivo al descargar medio.")
    return None

def download_flag(country_code, unique_id):
    """
    Descarga la bandera usando FlagCDN según el código ISO de dos letras.
    """
    if not country_code or country_code.lower() == "un":
        return None
        
    flag_url = f"https://flagcdn.com/w320/{country_code.lower()}.png"
    save_path = os.path.join(TEMP_IMG_DIR, f"flag_{unique_id}.png")
    
    return download_media(flag_url, save_path)