# -*- coding: utf-8 -*-
"""
==============================================================================
TEST LOCAL (Simulador de Node.js) - EDICIÓN DOCUMENTAL LARGO FORMATO
==============================================================================
Noticia: Feriado Laboral Revitaliza el Turismo Ecuatoriano
Este payload masivo generará un video largo, con cortes dinámicos cada ~15 seg.
"""

import logging
from main_orchestrator import process_video_payload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

def ejecutar_prueba_ecuador():
    print("\n" + "="*70)
    print("🚀 INICIANDO PRODUCCIÓN: BOOM TURÍSTICO EN ECUADOR (FORMATO LARGO) 🚀")
    print("="*70 + "\n")

    # La imagen original de la noticia que me pasaste
    img_noticia = "https://img.eldiario.ec/upload/2026/05/17161D524C43416D15120F54584945711F121818534B42711416-1024x576.jpg"

    payload = {
    "youtube_title": "Rocha Moya: Guardia Nacional y Acusaciones de EE.UU.",
    "youtube_description": "🔔 ¡Suscríbete al canal para no perderte ninguna noticia!\n👉 Lee la noticia completa aquí: https://www.noticias.lat/articulo/id_articulo_prueba\n\nTras solicitar licencia como gobernador de Sinaloa para no obstaculizar las investigaciones de la Fiscalía General de la República (FGR), Rubén Rocha Moya cuenta con elementos de la Guardia Nacional que resguardan su seguridad, según informó la presidenta Claudia Sheinbaum. La decisión se tomó tras una evaluación de riesgo realizada por el Gabinete de Seguridad, un protocolo que se aplica a cualquier ciudadano que solicite apoyo en su seguridad, ya sea un gobernador, legislador o un ciudadano común.\n        Sheinbaum enfatizó que la protección se ofrece a cualquier persona que sea considerada en riesgo, tras un análisis exhaustivo de la situación. En estos casos como en cualquier otro, sea para un gobernador o gobernador con licencia de cualquier estado, un diputado, senador, ciudadano que tenga consideración de riesgo de su persona solicita a la Guardia Nacional apoyo en su seguridad y se hace un análisis de riesgo.\n        La solicitud de licencia de Rocha Moya se produjo después de que el gobierno de Estados Unidos lo acusara de presuntos nexos con Los Chapitos y el crimen organizado en Sinaloa. Ante este escenario, el Congreso estatal nombró a Yeraldine Bonilla como gobernadora interina.",
    "youtube_tags": [
        "Rocha Moya",
        "Sinaloa",
        "Guardia Nacional",
        "FGR",
        "Noticias México"
    ],
    "scenes": [
        {
            "type": "intro",
            "text": "Rubén Rocha Moya recibe protección de la Guardia Nacional tras solicitar licencia en Sinaloa.",
            "layout_category": "sin_presentador",
            "voice": "hombre_1",
            "bgm_mood": "urgencia",
            "sfx_type": "impactos"
        },


        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true",
            "layout_category": "hombre",
            "text": "El protocolo de seguridad se aplica a cualquier ciudadano que solicite apoyo, independientemente de si es gobernador, legislador o ciudadano común.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "ad_video",
            "layout_category": "sin_presentador",
            "ad_media_url": "https://pub-32bf4851ff77488ebe727d3dad5fbb4d.r2.dev/anuncios/ad_1786665259795_671169041.mp4"
        },

      
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true",
            "layout_category": "hombre",
            "text": "Se espera que en los próximos días se revelen más detalles sobre el proceso de extradición y las investigaciones de FGR.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        }
    ]
}

    resultado = process_video_payload(payload)

    print("\n" + "="*70)
    if resultado:
        print(f"✅ ¡NOTICIERO ECUATORIANO CREADO EXITOSAMENTE!\n👉 Archivo guardado en: {resultado}")
    else:
        print("❌ LA PRUEBA HA FALLADO. Revisa los logs arriba para ver el error.")
    print("="*70 + "\n")

if __name__ == "__main__":
    ejecutar_prueba_ecuador()