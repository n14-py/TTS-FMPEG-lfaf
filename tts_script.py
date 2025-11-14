import sys
import os
from TTS.api import TTS

# --- CONFIGURACIÓN ---
# Modelo VITS en español: Rápido y de alta calidad para CPU.
# XTTS es de mayor calidad pero MUY lento sin GPU.
MODEL_NAME = "tts_models/es/css10/vits"
LANGUAGE = "es"

# Asegura que el path al modelo exista (para descargas)
try:
    if not os.path.exists(os.path.join(os.path.expanduser('~'), '.local/share/tts')):
        os.makedirs(os.path.join(os.path.expanduser('~'), '.local/share/tts'), exist_ok=True)
except Exception:
    # Esto puede fallar en Render, pero está bien, TTS lo manejará
    pass

# 1. Recibir argumentos de Node.js
text_to_speak = sys.argv[1]
output_audio_path = sys.argv[2]

try:
    print(f"[CoquiTTS] Iniciando (Modelo: {MODEL_NAME})...")
    
    # 2. Cargar el modelo.
    # gpu=False es crucial para tu plan de CPU.
    tts = TTS(MODEL_NAME, gpu=False)

    print(f"[CoquiTTS] Modelo cargado. Generando audio...")
    
    # 3. Generar el audio y guardarlo en el path de salida
    tts.tts_to_file(
        text=text_to_speak,
        file_path=output_audio_path,
        language=LANGUAGE
    )
    
    print(f"[CoquiTTS] Audio guardado: {output_audio_path}")
    # Devuelve el path al script de Node.js para confirmar
    sys.stdout.write(output_audio_path)
    sys.exit(0)

except Exception as e:
    print(f"[CoquiTTS] Error fatal: {e}")
    sys.stderr.write(str(e))
    sys.exit(1)