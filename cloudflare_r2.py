import boto3
from botocore.config import Config
import logging
import os
from dotenv import load_dotenv
import datetime


# Cargar las variables del archivo .env automáticamente
load_dotenv()

# =====================================================================
# 📊 CONFIGURACIÓN DE REGISTROS (LOGS)
# =====================================================================
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =====================================================================
# ⚙️ CREDENCIALES DE CLOUDFLARE R2 (VÍA VARIABLES DE ENTORNO)
# =====================================================================
ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
SECRET_KEY = os.getenv("R2_SECRET_KEY")
BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN")

def upload_media_to_r2(file_path, file_name):
    """
    Sube un archivo multimedia (Video o Audio) a Cloudflare R2.
    Detecta automáticamente el tipo de archivo para que la App móvil (Flutter) 
    o la Web puedan reproducirlo directamente sin tener que descargarlo.
    
    Args:
        file_path (str): La ruta local del archivo en tu servidor.
        file_name (str): El nombre final que tendrá el archivo en la nube.
        
    Returns:
        str: La URL pública completa del archivo subido, o None si falla.
    """
    
    # 1. Verificación de seguridad local
    if not os.path.exists(file_path):
        logger.error(f"  [Cloudflare R2] ❌ Error: El archivo local a subir NO EXISTE: {file_path}")
        return None

    # Verificación de credenciales
    if not all([ACCOUNT_ID, ACCESS_KEY, SECRET_KEY, BUCKET_NAME]):
        logger.error("  [Cloudflare R2] ❌ Error: Faltan credenciales de R2 en el archivo .env")
        return None

    try:
        # 2. Autenticación y Conexión Segura con Cloudflare (Vía S3 API)
        s3 = boto3.client(
            's3',
            endpoint_url=f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        
        logger.info(f"  [Cloudflare R2] 🚀 Iniciando subida a la nube: {file_name} ...")
        
        # 3. Detección Inteligente del Tipo de Contenido (MIME Type)
        # Esto es CRÍTICO para que los navegadores y Flutter sepan cómo reproducirlo
        tipo_contenido = 'application/octet-stream' # Valor por defecto seguro
        
        if file_name.lower().endswith('.mp3'):
            tipo_contenido = 'audio/mpeg'
            logger.info("  [Cloudflare R2] 🎵 Archivo detectado como AUDIO (.mp3)")
        elif file_name.lower().endswith('.mp4'):
            tipo_contenido = 'video/mp4'
            logger.info("  [Cloudflare R2] 🎥 Archivo detectado como VIDEO (.mp4)")
        else:
            logger.warning(f"  [Cloudflare R2] ⚠️ Extensión desconocida, usando fallback: {tipo_contenido}")
        
        # 4. Subida oficial del archivo al Bucket
        s3.upload_file(
            Filename=file_path, 
            Bucket=BUCKET_NAME, 
            Key=file_name,
            ExtraArgs={
                'ContentType': tipo_contenido,
                # Opcional: si la app carga lento en el futuro, activamos la caché aquí
                'CacheControl': 'max-age=31536000' 
            }
        )
        
        # 5. Generación de la URL Pública Final para enviar a Node.js
        domain = PUBLIC_DOMAIN.rstrip('/')
        url_final = f"{domain}/{file_name}"
        
        logger.info(f"  [Cloudflare R2] ✅ ¡Subida exitosa confirmada!")
        logger.info(f"  [Cloudflare R2] 🔗 Link directo: {url_final}")
        
        return url_final
        
    except Exception as e:
        # Captura cualquier error de red, de credenciales o de permisos en Cloudflare
        logger.error(f"  [Cloudflare R2] ❌ Error CRÍTICO durante la subida: {str(e)}")
        return None

# =====================================================================
# 🛠️ MODO DE PRUEBA MANUAL (OPCIONAL)
# =====================================================================
# Si ejecutas este archivo directamente (python cloudflare_r2.py), 
# hará una prueba rápida de conexión creando y subiendo un archivo de texto.
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🔧 Iniciando Diagnóstico de Cloudflare R2...")
    print("="*50)
    
    test_file = "test_cloudflare.txt"
    with open(test_file, "w") as f:
        f.write("Prueba de conexión exitosa desde tu servidor Python a Cloudflare R2")
        
    print("⏳ Subiendo archivo de prueba...")
    resultado = upload_media_to_r2(test_file, "prueba_conexion.txt")
    
    if resultado:
        print(f"\n🎉 ¡TODO PERFECTO! Tus credenciales funcionan.")
        print(f"👉 Puedes ver el archivo subido aquí: {resultado}")
    else:
        print("\n💀 FALLÓ LA PRUEBA.")
        print("Por favor, revisa tus variables R2_ACCOUNT_ID, R2_ACCESS_KEY y R2_SECRET_KEY en el archivo .env.")
        
    # Limpieza del archivo de prueba local
    if os.path.exists(test_file):
        os.remove(test_file)





        # =====================================================================
# 🧹 SISTEMA DE LIMPIEZA AUTOMÁTICA (28 DÍAS)
# =====================================================================

def delete_old_files_from_r2(days_old=28):
    """
    Busca y elimina audios y videos en Cloudflare R2 que tengan más de 'days_old' días
    para evitar acumular costos de almacenamiento.
    """
    if not all([ACCOUNT_ID, ACCESS_KEY, SECRET_KEY, BUCKET_NAME]):
        logger.error("  [Cloudflare Limpieza] ❌ Error: Faltan credenciales de R2.")
        return False

    try:
        s3 = boto3.client(
            's3',
            endpoint_url=f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        
        logger.info(f"  [Cloudflare Limpieza] 🕒 Buscando archivos con más de {days_old} días de antigüedad...")
        
        # Calcular la fecha exacta de hace 28 días
        fecha_limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
        
        # Obtener la lista de archivos en el bucket
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        
        if 'Contents' not in response:
            logger.info("  [Cloudflare Limpieza] 📭 El bucket está vacío, no hay nada que borrar.")
            return True

        archivos_borrados = 0
        for obj in response['Contents']:
            # Comparar la fecha de modificación del archivo con nuestra fecha límite
            if obj['LastModified'] < fecha_limite:
                logger.info(f"  [Cloudflare Limpieza] 🗑️ Borrando archivo antiguo: {obj['Key']}")
                s3.delete_object(Bucket=BUCKET_NAME, Key=obj['Key'])
                archivos_borrados += 1
                
        if archivos_borrados > 0:
            logger.info(f"  [Cloudflare Limpieza] ✅ Limpieza terminada. Se borraron {archivos_borrados} archivos.")
        else:
            logger.info("  [Cloudflare Limpieza] ✨ No se encontraron archivos tan viejos para borrar hoy.")
            
        return True

    except Exception as e:
        logger.error(f"  [Cloudflare Limpieza] ❌ Error durante la limpieza: {str(e)}")
        return False