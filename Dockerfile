# 1. Usar una imagen base de Node.js (versión 18, ligera)
FROM node:18-slim

# 2. Establecer el directorio de trabajo dentro del contenedor
WORKDIR /usr/src/app

# 3. ¡IMPORTANTE! Cambiar a usuario ROOT para instalar paquetes del sistema
USER root

# 4. Instalar Python, Pip, y FFmpeg
RUN apt-get update && \
    apt-get install -y python3 python3-pip ffmpeg && \
    # Limpiar el caché de apt para mantener la imagen ligera
    rm -rf /var/lib/apt/lists/*

# 5. Instalar CoquiTTS (globalmente)
#    ¡CAMBIO CLAVE! Añadimos --break-system-packages para saltar el error (PEP 668)
#    También unimos los dos comandos en una sola capa (más eficiente)
RUN pip3 install --upgrade pip --break-system-packages && \
    pip3 install TTS --break-system-packages

# 6. Copiar los archivos de la app
# Primero copiamos package.json para aprovechar el caché de Docker
COPY package*.json ./

# 7. Instalar dependencias de Node.js (cloudinary, express, etc.)
RUN npm install --omit=dev

# 8. Copiar el resto del código de la aplicación (index.js, tts_script.py, etc.)
COPY . .

# 9. Crear las carpetas que necesita tu app y dar permisos
# Cambiamos al usuario 'node' (que viene con la imagen) por seguridad
RUN mkdir -p temp avatars && \
    chown -R node:node temp avatars
USER node

# 10. Comando para iniciar el servidor cuando el contenedor arranque
CMD [ "node", "index.js" ]