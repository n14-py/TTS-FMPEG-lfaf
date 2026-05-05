# -*- coding: utf-8 -*-
"""
==============================================================================
MAIN ORCHESTRATOR (El Director de Orquesta de Noticias.lat)
==============================================================================
Este archivo recibe el payload JSON estructurado, coordina a los recolectores
de fondos, al motor de voz, y a los diferentes módulos de FFmpeg.
Al final, concatena todas las escenas sin pérdida de calidad y limpia el servidor.
"""

import os
import uuid
import time
import logging
import gc
import subprocess
from config import *

# Importamos nuestros submódulos especializados
import media_manager
import background_fetcher
import tts_engine
import scene_templates.ffmpeg_intro as ffmpeg_intro
import scene_templates.ffmpeg_01_mapa as ffmpeg_mapa
import scene_templates.ffmpeg_02_pexels as ffmpeg_pexels
import scene_templates.ffmpeg_universal as ffmpeg_universal

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIÓN AUXILIAR: CONCATENACIÓN RÁPIDA
# ==============================================================================
def concatenar_escenas(lista_escenas, output_path, unique_id):
    """Pega múltiples videos .mp4 en uno solo usando 'concat' de FFmpeg."""
    if not lista_escenas:
        logger.error("  [Orchestrator] Lista de escenas vacía. No hay nada que concatenar.")
        return False
        
    archivo_lista = os.path.join(TEMP_VIDEO_DIR, f"concat_list_{unique_id}.txt")
    
    try:
        logger.info(f"  [Orchestrator] Ensamblando {len(lista_escenas)} escenas...")
        with open(archivo_lista, 'w', encoding='utf-8') as f:
            for escena in lista_escenas:
                safe_path = escena.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
                
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", archivo_lista,
            "-c", "copy",
            output_path
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        
    except Exception as e:
        logger.error(f"  [Orchestrator] Error crítico al concatenar: {e}")
        return False
    finally:
        if os.path.exists(archivo_lista):
            os.remove(archivo_lista)

# ==============================================================================
# EL CEREBRO PRINCIPAL
# ==============================================================================
def process_video_payload(payload):
    """Función principal que procesa el JSON enviado por Node.js o el test local."""
    article_id = payload.get("article_id", "NO_ID")
    scenes = payload.get("scenes", [])
    
    if not scenes:
        logger.error(f"  [Orchestrator] El payload {article_id} no contiene escenas válidas.")
        return None

    unique_id = uuid.uuid4().hex[:8]
    final_output_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")
    thumbnail_output_path = os.path.join(OUTPUT_DIR, f"{article_id}.jpg") # <--- El path del JPG
    
    archivos_temporales = []
    escenas_renderizadas = []
    miniatura_creada = False
    
    logger.info(f"========== INICIANDO PRODUCCIÓN MATRICIAL: NOTICIA {article_id} ==========")
    
    try:
        for idx, scene in enumerate(scenes):
            logger.info(f"  --- Procesando Escena {idx + 1}/{len(scenes)} ---")
            
            scene_type = scene.get("type", "body") # intro, mapa, pexels, body
            texto_guion = scene.get("text", "")
            
            # 1. GENERAR EL AUDIO TTS
            audio_filename = f"audio_{unique_id}_{idx}.mp3"
            voz_elegida = scene.get("voice", "hombre_1")
            audio_path = tts_engine.generate_audio_clip(texto_guion, voz_elegida, audio_filename)
            
            if audio_path:
                archivos_temporales.append(audio_path)
            else:
                logger.error(f"  [Orchestrator] Falló el audio en escena {idx}. Saltando.")
                continue

            # 2. OBTENER BGM Y SFX COMUNES
            bgm_mood = scene.get("bgm_mood")
            bgm_path = media_manager.get_random_bgm(bgm_mood) if bgm_mood else None
            sfx_type = scene.get("sfx_type")
            sfx_path = media_manager.get_random_sfx(sfx_type) if sfx_type else None
            
            escena_output = os.path.join(TEMP_VIDEO_DIR, f"escena_{unique_id}_{idx}.mp4")
            exito = False

            # ==========================================================
            # RUTEO DE ESCENAS A SUS MÓDULOS ESPECÍFICOS
            # ==========================================================
            
            if scene_type == "intro":
                intro_path = media_manager.get_random_template("intros")
                if intro_path:
                    exito = ffmpeg_intro.ensamblar_intro(
                        intro_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output
                    )
            
            elif scene_type == "mapa":
                ubicacion = scene.get("ubicacion", "Paraguay")
                overlay_path = media_manager.get_random_template("sin_presentador")
                if overlay_path:
                    exito = ffmpeg_mapa.renderizar_escena_mapa(
                        ubicacion, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output, unique_id
                    )
                    
            elif scene_type == "pexels":
                termino = scene.get("termino_busqueda", "news")
                overlay_path = media_manager.get_random_template(scene.get("layout_category", "sin_presentador"))
                if overlay_path:
                    exito = ffmpeg_pexels.renderizar_escena_pexels(
                        termino, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output, unique_id
                    )
                    
            elif scene_type == "body":
                img_url = scene.get("image_url", "")
                fondo_path = os.path.join(TEMP_IMG_DIR, f"bg_img_{unique_id}_{idx}.jpg")
                fondo_path = background_fetcher.obtener_imagen_noticia(img_url, fondo_path)
                
                if fondo_path:
                    archivos_temporales.append(fondo_path)
                    overlay_path = media_manager.get_random_template(scene.get("layout_category", "hombre"))
                    if overlay_path:
                        exito = ffmpeg_universal.ensamblar_escena(
                            fondo_path, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output
                        )

            # ==========================================================
            # GUARDAR SI FUE EXITOSO
            # ==========================================================
            # ==========================================================
            # GUARDAR SI FUE EXITOSO
            # ==========================================================
            if exito and os.path.exists(escena_output):
                escenas_renderizadas.append(escena_output)
                archivos_temporales.append(escena_output)
                
                # --- 📸 MAGIA DE LA MINIATURA ---
                # Si es una escena "body" (que tiene la imagen original) y aún no sacamos foto
                if scene_type == "body" and not miniatura_creada:
                    try:
                        # Extraemos un fotograma exacto en el segundo 2 (Alta calidad)
                        cmd_thumb = [
                            "ffmpeg", "-y",
                            "-ss", "00:00:02", 
                            "-i", escena_output,
                            "-vframes", "1",
                            "-q:v", "2", 
                            thumbnail_output_path
                        ]
                        subprocess.run(cmd_thumb, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        if os.path.exists(thumbnail_output_path):
                            logger.info(f"  [Orchestrator] 📸 Miniatura capturada y guardada exitosamente.")
                            miniatura_creada = True # Cerramos el candado
                    except Exception as e:
                        logger.warning(f"  [Orchestrator] ⚠️ No se pudo crear la miniatura: {e}")
                # -----------------------------
            else:
                logger.error(f"  [Orchestrator] Falló el ensamblaje de la escena {idx} ({scene_type}).")

        # 5. CONCATENACIÓN FINAL
        if len(escenas_renderizadas) > 0:
            exito_final = concatenar_escenas(escenas_renderizadas, final_output_path, unique_id)
            if exito_final:
                logger.info(f"========== ¡SISTEMA COMPLETADO EXITOSAMENTE! Video: {final_output_path} ==========")
                return final_output_path
            else:
                logger.error("  [Orchestrator] Error en la concatenación de las escenas.")
                return None
        else:
            logger.error("  [Orchestrator] Ninguna escena se generó correctamente. Operación abortada.")
            return None

    except Exception as e:
        logger.error(f"  [Orchestrator] ERROR FATAL EN EL PROCESO: {e}")
        return None
        
    finally:
        logger.info("  [Orchestrator] Activando recolección de basura...")
        for archivo in archivos_temporales:
            try:
                if archivo and os.path.exists(archivo):
                    os.remove(archivo)
            except Exception:
                pass
        gc.collect()
        logger.info("  [Orchestrator] Limpieza finalizada. Servidor libre.")