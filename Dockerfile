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

# Exponer el puerto que usa Flask (5001)
EXPOSE 5001

# Comando para correr la aplicación en producción
# Usamos Gunicorn en lugar de "python app.py"
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app"]