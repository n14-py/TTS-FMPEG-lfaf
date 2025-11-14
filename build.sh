#!/usr/bin/env bash
# Salir si cualquier comando falla
set -e

echo "--- Iniciando script de build personalizado ---"

# 1. Instalar dependencias del sistema (Python, pip, FFmpeg)
echo "Actualizando e instalando apt-get..."
apt-get update
apt-get install -y python3 python3-pip ffmpeg

# 2. Instalar CoquiTTS
echo "Instalando CoquiTTS (esto puede tardar)..."
# Usamos 'pip3' y lo actualizamos primero
pip3 install --upgrade pip
pip3 install TTS

# 3. Instalar dependencias de Node.js (lo que haría Render)
echo "Instalando dependencias de npm..."
npm install

echo "--- Build completado ---"