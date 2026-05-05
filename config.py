# -*- coding: utf-8 -*-
"""
==============================================================================
CONFIGURACIÓN MAESTRA DEL SISTEMA DE VIDEO
==============================================================================
Centraliza rutas, configuraciones de FFmpeg, coordenadas de 20 overlays y voces.
"""

import os
from dotenv import load_dotenv

# Cargar las variables del archivo .env automáticamente
load_dotenv()

# ==============================================================================
# 1. RUTAS DE DIRECTORIOS
# ==============================================================================
BASE_DIR = os.getcwd()

TEMP_AUDIO_DIR = os.path.join(BASE_DIR, "temp_audio")
TEMP_VIDEO_DIR = os.path.join(BASE_DIR, "temp_video")
TEMP_IMG_DIR = os.path.join(BASE_DIR, "temp_processing")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

ASSETS_DIR = os.path.join(BASE_DIR, "assets_video")

# --- TRUCO MAESTRO PARA FFMPEG EN WINDOWS ---
# Generamos la ruta absoluta y escapamos los dos puntos de la unidad C:
_raw_font = os.path.join(ASSETS_DIR, "fonts", "fuente.ttf")
FONT_PATH = "arial.ttf"

TEMPLATES_DIR = os.path.join(ASSETS_DIR, "templates")
BGM_DIR = os.path.join(ASSETS_DIR, "bgm")
SFX_DIR = os.path.join(ASSETS_DIR, "sfx")

# ==============================================================================
# 2. CONFIGURACIÓN DE PANTALLA Y RENDERIZADO
# ==============================================================================
RESOLUTION_W = 1280
RESOLUTION_H = 720
FPS = 20
VIDEO_PRESET = "ultrafast"
CHROMA_COLOR = "0x00FF00"
CHROMA_SIMILARITY = "0.30"
CHROMA_BLEND = "0.10"

# ==============================================================================
# 3. VOCES DEL TTS (Edge TTS)
# ==============================================================================
VOICES = {
    "mujer_1": "es-MX-DaliaNeural",
    "mujer_2": "es-ES-ElviraNeural",
    "hombre_1": "es-AR-TomasNeural",
    "hombre_2": "es-CO-TomasNeural"
}

# ==============================================================================
# 4. DICCIONARIO DE COORDENADAS PARA 20 LAYOUTS EXACTOS (1280x720)
# ==============================================================================
DEFAULT_LAYOUT = {
    "texto_x": 50, 
    "texto_y": 600, 
    "color": "white", 
    "font_size": 45, 
    "max_letras_por_linea": 40
}

LAYOUT_CONFIG = {
    # --- INTROS ---
    "intro_layout_01.mp4": {"texto_x": -1000, "texto_y": -1500, "color": "white", "font_size": 85, "max_letras_por_linea": 20},
    "intro_layout_02.mp4": {"texto_x": -1000,  "texto_y": -1500, "color": "yellow", "font_size": 70, "max_letras_por_linea": 30},
    "intro_layout_03.mp4": {"texto_x": -1000, "texto_y": -1500, "color": "white", "font_size": 75, "max_letras_por_linea": 20},
    "intro_layout_04.mp4": {"texto_x": -1000,  "texto_y": -1500, "color": "red", "font_size": 80, "max_letras_por_linea": 55},
    "intro_layout_05.mp4": {"texto_x": -1000, "texto_y": -1500, "color": "white", "font_size": 65, "max_letras_por_linea": 35},

    # --- HOMBRE ---
    "hombre_layout_01.mp4": {"texto_x": 9,  "texto_y": 572, "color": "white", "font_size": 27, "max_letras_por_linea": 60},
    "hombre_layout_02.mp4": {"texto_x": 333,  "texto_y": 557, "color": "white", "font_size": 30, "max_letras_por_linea": 58},
    "hombre_layout_03.mp4": {"texto_x": 15,  "texto_y": 566,  "color": "yellow", "font_size": 30, "max_letras_por_linea": 25},
    "hombre_layout_04.mp4": {"texto_x": 495,  "texto_y": 578, "color": "white", "font_size": 27, "max_letras_por_linea": 55},
    "hombre_layout_05.mp4": {"texto_x": 107, "texto_y": 551, "color": "white", "font_size": 28, "max_letras_por_linea": 55},

    # --- MUJER ---
    "mujer_layout_01.mp4": {"texto_x": 9,  "texto_y": 572, "color": "white", "font_size": 27, "max_letras_por_linea": 60},
    "mujer_layout_02.mp4": {"texto_x": 333,  "texto_y": 557, "color": "white", "font_size": 30, "max_letras_por_linea": 58},
    "mujer_layout_03.mp4": {"texto_x": 15,  "texto_y": 566,  "color": "yellow", "font_size": 30, "max_letras_por_linea": 25},
    "mujer_layout_04.mp4": {"texto_x": 495,  "texto_y": 578, "color": "white", "font_size": 27, "max_letras_por_linea": 55},
    "mujer_layout_05.mp4": {"texto_x": 107, "texto_y": 551, "color": "white", "font_size": 28, "max_letras_por_linea": 55},

    # --- GRÁFICOS (SIN PRESENTADOR) ---
    "grafico_layout_01.mp4": {"texto_x": 9,  "texto_y": 572, "color": "white", "font_size": 27, "max_letras_por_linea": 60},
    "grafico_layout_02.mp4": {"texto_x": 333,  "texto_y": 557,  "color": "white", "font_size": 30, "max_letras_por_linea": 58},
    "grafico_layout_03.mp4": {"texto_x": 15,  "texto_y": 566, "color": "yellow", "font_size": 30, "max_letras_por_linea": 55},
    "grafico_layout_04.mp4": {"texto_x": 495,  "texto_y": 578, "color": "white", "font_size": 27, "max_letras_por_linea": 40},
    "grafico_layout_05.mp4": {"texto_x": 107, "texto_y": 551, "color": "white", "font_size": 28, "max_letras_por_linea": 55},
}

def get_layout_config(filename):
    return LAYOUT_CONFIG.get(filename, DEFAULT_LAYOUT)
# ==============================================================================
# 5. CREACIÓN AUTOMÁTICA DE CARPETAS
# ==============================================================================
def init_directories():
    directories = [
        TEMP_AUDIO_DIR, TEMP_VIDEO_DIR, TEMP_IMG_DIR, OUTPUT_DIR,
        ASSETS_DIR, 
        os.path.join(ASSETS_DIR, "fonts"), # <-- ESTA ES LA LÍNEA CORREGIDA
        TEMPLATES_DIR, BGM_DIR, SFX_DIR,
        os.path.join(TEMPLATES_DIR, "intros"),
        os.path.join(TEMPLATES_DIR, "hombre"),
        os.path.join(TEMPLATES_DIR, "mujer"),
        os.path.join(TEMPLATES_DIR, "sin_presentador"),
        os.path.join(BGM_DIR, "urgencia"),
        os.path.join(BGM_DIR, "analisis"),
        os.path.join(BGM_DIR, "tension"),
        os.path.join(SFX_DIR, "transiciones"),
        os.path.join(SFX_DIR, "impactos"),
        os.path.join(SFX_DIR, "alertas"),
        os.path.join(SFX_DIR, "tecnologia")
    ]
    for directory in directories:
        # Solo creamos la carpeta si no es un string con la ruta "engañada" de FFmpeg
        if "C\:" not in directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

init_directories()