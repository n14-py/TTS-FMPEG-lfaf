# Usar una imagen base de Python
FROM python:3.10-slim

# Instalar FFmpeg Y utilidades de descarga (curl)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requisitos e instalar librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- ¡NUEVO! DESCARGAR Y CONFIGURAR VOZ PIPER ---
# 1. Crear carpeta para el modelo
RUN mkdir -p /app/models/piper

# 2. Descargar los dos archivos esenciales (modelo ONNX y archivo de configuración JSON)
# Usamos el modelo más estable y ligero en español: es_ES-carlfm-x_low
RUN curl -L -o /app/models/piper/es_ES-carlfm-x_low.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx \
    && curl -L -o /app/models/piper/es_ES-carlfm-x_low.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json

# Copiar el resto de la aplicación (app.py, video_generator.py, etc.)
COPY . .

# Comando para correr la aplicación
CMD gunicorn --bind "0.0.0.0:$PORT" app:app