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
    tini \
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
ENV PYTHONFAULTHANDLER=1
ENV MALLOC_ARENA_MAX=2
ENV PORT=3001

# tini es PID 1: reenvía señales y recoge procesos zombi de FFmpeg.
# La política de reinicio no cabe en la imagen: hay que pasar
# --restart unless-stopped al crear el contenedor, o usar docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["tini", "-g", "--"]
# workers 1: un video FFmpeg a la vez. El detalle vive en gunicorn.conf.py.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]