# ... (Líneas 1-4)
FROM python:3.10-slim

# Instalar FFmpeg SOLAMENTE. Eliminamos 'libsndfile1' y la descarga de TTS.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requisitos e instalar librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- ELIMINADO: Ya no necesitamos descargar el modelo grande de Coqui aquí ---
# ELIMINAR: RUN python -c "from TTS.api import TTS; TTS(model_name='tts_models/es/css10/vits', progress_bar=True, gpu=False)"

# Copiar el resto de la aplicación (app.py, video_generator.py, etc.)
COPY . .

# Comando para correr la aplicación (sin cambios)
CMD gunicorn --bind "0.0.0.0:$PORT" app:app