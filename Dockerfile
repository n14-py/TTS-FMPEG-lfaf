# Usar una imagen base de Python
FROM python:3.10-slim

# Instalar FFmpeg Y las nuevas dependencias para TTS
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requisitos e instalar librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- ¡NUEVO! Descargar el modelo de voz ---
# Esto descarga el modelo español que elegimos (css10/vits)
# Se ejecuta UNA VEZ durante el deploy, para que el bot inicie rápido.
RUN python -c "from TTS.api import TTS; TTS(model_name='tts_models/es/css10/vits', progress_bar=True, gpu=False)"
# Copiar el resto de la aplicación (app.py, video_generator.py, etc.)
COPY . .

# Comando para correr la aplicación (corregido con $PORT)
CMD gunicorn --bind "0.0.0.0:$PORT" app:app