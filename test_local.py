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
    "youtube_title": "Rocha Moya: Extradición, Protección y Análisis Legal en México",
    "youtube_description": "Últimas noticias sobre Rubén Rocha Moya, la solicitud de extradición de Estados Unidos, la protección de la Guardia Nacional y las implicaciones legales de este caso. Análisis completo y actualizado.",
    "youtube_tags": [
        "Rubén Rocha Moya",
        "Extradición",
        "Guardia Nacional",
        "México",
        "Estados Unidos",
        "Crimen Organizado",
        "Luisa María Alcalde",
        "Sheinbaum"
    ],
    "scenes": [
        {
            "type": "intro",
            "text": "Rocha Moya enfrenta acusaciones y medidas de seguridad, mientras se analiza su posible extradición a Estados Unidos.",
            "voice": "hombre_1",
            "bgm_mood": "urgencia",
            "sfx_type": "impactos"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "Rubén Rocha Moya solicitó licencia como gobernador de Sinaloa para no entorpecer las investigaciones de la FGR, lo que ha generado un debate sobre su situación legal y la necesidad de garantizar un proceso transparente y justo. La colaboración entre México y Estados Unidos es crucial.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "mujer",
            "text": "La presidenta Sheinbaum informó que Rocha Moya cuenta con elementos de la Guardia Nacional para su seguridad, tras una evaluación de riesgo estándar. Este protocolo se aplica a cualquier ciudadano que requiera protección, sin importar su cargo o posición social.",
            "voice": "mujer_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "pexels",
            "termino_busqueda": "security forces mexico",
            "layout_category": "sin_presentador",
            "text": "La Guardia Nacional evalúa constantemente los niveles de riesgo para ofrecer protección adecuada, considerando factores como amenazas directas, vulnerabilidad y la naturaleza de las investigaciones en curso. La seguridad es una prioridad para el gobierno.",
            "voice": "hombre_1",
            "bgm_mood": "tension",
            "sfx_type": "alertas"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "La solicitud de licencia de Rocha Moya se produjo tras acusaciones de Estados Unidos sobre presuntos nexos con Los Chapitos y el crimen organizado en Sinaloa. Estas acusaciones han generado una fuerte controversia y un escrutinio público intenso.",
            "voice": "hombre_1",
            "bgm_mood": "urgencia",
            "sfx_type": "impactos"
        },
        {
            "type": "mapa",
            "ubicacion": "Sinaloa, Mexico",
            "layout_category": "sin_presentador",
            "text": "Sinaloa, un estado clave en la lucha contra el narcotráfico, se encuentra en el centro de esta controversia. La situación requiere una estrategia integral que involucre a las autoridades federales y estatales para garantizar la seguridad y el estado de derecho.",
            "voice": "mujer_1",
            "bgm_mood": "tension",
            "sfx_type": "alertas"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "mujer",
            "text": "Yeraldine Bonilla fue nombrada gobernadora interina de Sinaloa tras la licencia de Rocha Moya. Su administración enfrenta el desafío de mantener la estabilidad política y social en un momento de incertidumbre y tensión.",
            "voice": "mujer_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "Sheinbaum defendió su gira por Palenque y desmintió especulaciones sobre una reunión con López Obrador, calificando las acusaciones de misoginia y falta de reconocimiento a su capacidad de toma de decisiones. La transparencia es fundamental.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "pexels",
            "termino_busqueda": "political debate mexico",
            "layout_category": "sin_presentador",
            "text": "La presidenta Sheinbaum enfatizó la importancia de evitar la desinformación y los ataques basados en prejuicios de género. La discusión política debe centrarse en los hechos y las propuestas, no en ataques personales.",
            "voice": "mujer_1",
            "bgm_mood": "tension",
            "sfx_type": "alertas"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "Luisa María Alcalde, consejera Jurídica de la Presidencia, analizará la posibilidad de retrasar la elección Judicial al año 2028. El análisis busca determinar si una reforma que la posponga sería conveniente para el sistema judicial.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "mujer",
            "text": "Alcalde aclaró la diferencia entre una solicitud de extradición y una solicitud de detención provisional con fines de extradición en el caso de Rocha Moya. La solicitud actual es de detención provisional, un paso previo a la extradición formal.",
            "voice": "mujer_1",
            "bgm_mood": "urgencia",
            "sfx_type": "impactos"
        },
        {
            "type": "pexels",
            "termino_busqueda": "legal process mexico",
            "layout_category": "sin_presentador",
            "text": "El Tratado de Extradición entre México y Estados Unidos establece los requisitos y procedimientos para la entrega de personas acusadas de delitos. La solicitud formal debe presentarse por vía diplomática con pruebas detalladas.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "La solicitud de detención provisional permite a las autoridades mexicanas detener a Rocha Moya mientras Estados Unidos prepara la solicitud formal de extradición. Este proceso busca evitar la fuga y garantizar la comparecencia ante la justicia.",
            "voice": "hombre_1",
            "bgm_mood": "tension",
            "sfx_type": "alertas"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "mujer",
            "text": "Profeco informó que el litro de diésel se venderá a un precio máximo de 27 pesos esta semana, mientras que la gasolina Magna tiene un promedio de 23.67 pesos por litro. Se publicaron listas de gasolineras con precios más bajos.",
            "voice": "mujer_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "hombre",
            "text": "Leticia Ramírez, nueva secretaria del Bienestar, dio a conocer el calendario de pagos de la Pensión Bienestar para Adultos Mayores y otros programas sociales, comenzando el 4 de mayo con la letra A en orden alfabético.",
            "voice": "hombre_1",
            "bgm_mood": "analisis",
            "sfx_type": "transiciones"
        },
        {
            "type": "body",
            "image_url": "https://www.elfinanciero.com.mx/resizer/v2/BVLRGKWUCZAK5KQQI574NNPCWM.jpg?smart=true&auth=da160f5b33d3101bcf32028457ec9e5cc06b41c1ede1220bea5b502cb4ea547b&width=1200&height=630",
            "layout_category": "mujer",
            "text": "La situación de Rubén Rocha Moya sigue siendo un tema central en la agenda política nacional, con implicaciones significativas para la seguridad y la cooperación entre México y Estados Unidos. El análisis legal es crucial.",
            "voice": "mujer_1",
            "bgm_mood": "urgencia",
            "sfx_type": "impactos"
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