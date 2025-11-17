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

# --- ¡CAMBIO IMPORTANTE! ---
# Ya no exponemos el 5001, dejaremos que Render elija.
# EXPOSE 5001 <--- (Línea eliminada)

# --- ¡ESTA ES LA LÍNEA CORREGIDA! ---
# En lugar de "5001", usamos "$PORT".
# Gunicorn leerá la variable de entorno de Render (que será 3001)
# y se iniciará en el puerto correcto.
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"]