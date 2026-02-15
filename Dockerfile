# Usamos una imagen base ligera de Python
FROM python:3.10-slim

# --- INSTALACIÓN DE SISTEMA BLINDADA ---
# 1. ffmpeg: El motor de video.
# 2. curl: Para descargas potentes.
# 3. fonts-liberation: ¡CRÍTICO! Instala fuentes (letras) para que el texto del video no falle.
# 4. fontconfig: Para que Linux reconozca las fuentes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    fonts-liberation \
    fontconfig \
    ca-certificates \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

# Configuración del directorio de trabajo
WORKDIR /app

# --- INSTALACIÓN DE LIBRERÍAS PYTHON ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- COPIAR CÓDIGO FUENTE ---
COPY . .

# --- VARIABLES DE ENTORNO ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=3001

# --- COMANDO DE INICIO (OPTIMIZADO T3.MICRO) ---
# workers 1: Vital para respetar la memoria de tu servidor pequeño.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 app:app