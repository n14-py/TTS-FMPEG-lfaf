#!/usr/bin/env bash
# Salir si cualquier comando falla
set -e

echo "--- Iniciando script de build personalizado (v2 con sudo) ---"

# 1. Instalar dependencias del sistema (Python, pip, FFmpeg)
echo "Actualizando e instalando apt-get con sudo..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip ffmpeg

# 2. Instalar CoquiTTS
echo "Instalando CoquiTTS (esto puede tardar)..."
# Usamos 'pip3' y lo actualizamos primero
pip3 install --upgrade pip
pip3 install TTS

# 3. Instalar dependencias de Node.js
echo "Instalando dependencias de npm..."
npm install

echo "--- Build completado ---"