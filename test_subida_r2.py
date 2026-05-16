# -*- coding: utf-8 -*-
import os
import time
from dotenv import load_dotenv

# Importar tus propios módulos del proyecto
from tts_engine import generate_audio_clip
from cloudflare_r2 import upload_media_to_r2

load_dotenv()

# =====================================================================
# ⚙️ CONFIGURACIÓN DE LA PRUEBA (MODIFICA ESTO)
# =====================================================================
# 1. El texto real de la noticia para generar el audio
TEXTO_NOTICIA = "En un operativo realizado en el departamento de Santa Ana, efectivos de la Policía Nacional lograron la captura de varios sujetos luego de que fueran sorprendidos transportando sustancias ilícitas a bordo de un vehículo. El hecho se produjo en el marco de las labores de vigilancia y control que las autoridades mantienen en la zona, orientadas a combatir el tráfico de estupefacientes y reducir los índices de criminalidad en la región occidental del país. El procedimiento policial se centró en la interceptación de un automóvil, el cual, tras ser revisado por los agentes, resultó contener droga en su interior. La acción de las autoridades permitió la detención inmediata de los individuos que se encontraban en el vehículo al momento del hallazgo. Según la información disponible, los sujetos fueron sorprendidos en flagrancia, lo que facilitó la intervención policial y la posterior aseguración tanto de la sustancia prohibida como del medio de transporte utilizado para su traslado. Desde una perspectiva analítica, este tipo de capturas pone de manifiesto la importancia de los operativos de control en las vías de comunicación de Santa Ana. El uso de vehículos para el transporte de droga es una modalidad recurrente en el crimen organizado, ya que permite el desplazamiento de sustancias entre diferentes puntos geográficos intentando evadir los controles estatales. En este caso particular, la capacidad de respuesta de los agentes permitió neutralizar el traslado de la droga, evitando que esta llegara a su destino final. La captura de estos sujetos representa un paso más en la estrategia de seguridad implementada en la zona. El hallazgo de drogas a bordo de un vehículo sugiere una logística de distribución que las autoridades buscan desmantelar. Cuando los agentes logran sorprender a los implicados, no solo se retira el producto ilícito del mercado, sino que se inicia un proceso judicial contra quienes participaban activamente en el transporte de estas sustancias. En cuanto al proceso legal posterior a la captura, los sujetos detenidos deben ser puestos a disposición de las autoridades judiciales competentes. El protocolo establece que, una vez realizada la detención y asegurada la evidencia, se proceda con la lectura de sus derechos y el traslado a las instalaciones correspondientes para el registro formal de la captura. La droga incautada es procesada siguiendo los protocolos de cadena de custodia para que sirva como prueba material en el proceso penal que se abrirá contra los implicados. El departamento de Santa Ana, por su ubicación estratégica, es un punto clave para las operaciones de seguridad. La presencia policial constante y la ejecución de operativos sorpresa son herramientas fundamentales para inhibir el movimiento de sustancias prohibidas. Este evento particular refuerza la tesis de que la vigilancia activa es la vía más efectiva para detectar actividades irregulares en el transporte terrestre. La lucha contra el tráfico de drogas es una prioridad para las instituciones de seguridad, ya que el consumo y la distribución de estas sustancias suelen estar vinculados a otros delitos menores y mayores que afectan la paz social. Al interceptar un vehículo con droga, la policía no solo realiza una detención administrativa, sino que interrumpe una cadena de suministro que alimenta la economía ilegal. Finalmente, es importante destacar que la operatividad de la policía en Santa Ana continúa enfocada en la prevención y la reacción inmediata. La captura de estos sujetos y el decomiso de la droga encontrada en el vehículo son el resultado de la aplicación de la ley y el cumplimiento de los deberes de seguridad pública. Las autoridades mantienen su compromiso de seguir vigilando las rutas y los desplazamientos en la zona para garantizar que el territorio esté libre de actividades relacionadas con el narcotráfico."

# 2. El nombre exacto de tu video de YouTube descargado en esta misma carpeta
NOMBRE_VIDEO_LOCAL = "video1.mp4" 
# =====================================================================

def generar_y_subir():
    print("\n" + "="*50)
    print("🚀 INICIANDO GENERACIÓN Y SUBIDA EN TTS-FMPEG")
    print("="*50)

    # 1. Verificar que el video local existe
    ruta_video = os.path.join(os.getcwd(), NOMBRE_VIDEO_LOCAL)
    if not os.path.exists(ruta_video):
        print(f"❌ Error: No se encuentra el archivo de video '{NOMBRE_VIDEO_LOCAL}'.")
        return

    # 2. Generar el AUDIO usando tu motor TTS
    print("\n🎙️ Generando audio desde el texto...")
    nombre_audio_temp = f"audio_temp_{int(time.time())}.mp3"
    ruta_audio = generate_audio_clip(TEXTO_NOTICIA, "hombre_1", nombre_audio_temp)

    if not ruta_audio or not os.path.exists(ruta_audio):
        print("❌ Error: El motor TTS falló al generar el audio.")
        return
    print("✅ Audio generado exitosamente.")

    # 3. Subir VIDEO y AUDIO a Cloudflare R2
    print("\n☁️ Subiendo Video a Cloudflare R2...")
    clave_video_r2 = f"videos/real_vid_{int(time.time())}.mp4"
    url_video_final = upload_media_to_r2(ruta_video, clave_video_r2)

    print("☁️ Subiendo Audio a Cloudflare R2...")
    clave_audio_r2 = f"audios/real_aud_{int(time.time())}.mp3"
    url_audio_final = upload_media_to_r2(ruta_audio, clave_audio_r2)

    if not url_video_final or not url_audio_final:
        print("❌ Error: Falló la subida a Cloudflare R2.")
        return

    print("\n🎉 ¡PROCESO COMPLETADO EN TTS-FMPEG!")
    print("👇 COPIA ESTAS DOS URLs PARA USARLAS EN NODE.JS 👇\n")
    print(f"const URL_VIDEO = '{url_video_final}';")
    print(f"const URL_AUDIO = '{url_audio_final}';\n")

    # Limpieza del audio temporal
    try:
        os.remove(ruta_audio)
    except:
        pass

if __name__ == "__main__":
    generar_y_subir()