# Usamos una imagen base ligera de Python 3.10
# "slim" es perfecta para AWS porque pesa poco y despliega rápido.
FROM python:3.10-slim

# --- INSTALACIÓN DE PAQUETES DEL SISTEMA ---
# 1. ffmpeg: El motor para crear el video.
# 2. curl: HERRAMIENTA CLAVE para tu descarga de imágenes "Nivel Militar".
# 3. ca-certificates: Para que curl no falle con errores SSL.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configuración del directorio de trabajo
WORKDIR /app

# --- INSTALACIÓN DE LIBRERÍAS PYTHON ---
# Copiamos primero requirements.txt para aprovechar la caché de Docker
# (Si cambias el código pero no las librerías, este paso se salta y el build es veloz)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- COPIAR CÓDIGO FUENTE ---
COPY . .

# --- VARIABLES DE ENTORNO ---
# Evita que Python genere archivos .pyc (basura en contenedores)
ENV PYTHONDONTWRITEBYTECODE=1
# Obliga a Python a imprimir los logs al instante (Vital para ver errores en AWS CloudWatch)
ENV PYTHONUNBUFFERED=1

# Puerto por defecto (AWS suele sobrescribir esto con su propia variable PORT)
ENV PORT=3001

# --- COMANDO DE INICIO (OPTIMIZADO PARA T3.MICRO) ---
# --workers 1: OBLIGATORIO. Mantiene el control de memoria y respeta el 'lock' de app.py.
# --threads 8: Permite concurrencia para peticiones ligeras (como /health) mientras el worker trabaja.
# --timeout 300: Damos 5 minutos de margen antes de dar error (renderizar video toma tiempo).
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 app:app