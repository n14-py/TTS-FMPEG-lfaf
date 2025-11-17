# Usar una imagen base de Python
FROM python:3.10-slim

# Instalar FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requisitos e instalar librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la aplicación (app.py, video_generator.py, etc.)
COPY . .

# --- ¡ESTA ES LA LÍNEA CORREGIDA! ---
# En lugar de usar corchetes [], usamos un string.
# Esto obliga a Docker a ejecutar el comando en un shell (/bin/sh -c "...")
# El shell SÍ sabe cómo reemplazar $PORT por el valor 3001 que le da Render.
CMD gunicorn --bind "0.0.0.0:$PORT" app:app