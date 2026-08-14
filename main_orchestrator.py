# -*- coding: utf-8 -*-
"""
==============================================================================
MAIN ORCHESTRATOR (NÚCLEO BLINDADO ANTI-CORRUPCIÓN)
==============================================================================
"""

import os
import uuid
import time
import logging
import gc
import requests
import subprocess
from config import *

import media_manager
import background_fetcher
import tts_engine
import scene_templates.ffmpeg_intro as ffmpeg_intro
import scene_templates.ffmpeg_01_mapa as ffmpeg_mapa
import scene_templates.ffmpeg_02_pexels as ffmpeg_pexels
import scene_templates.ffmpeg_universal as ffmpeg_universal
import scene_templates.ffmpeg_ads as ffmpeg_ads

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNCIÓN AUXILIAR: CONCATENACIÓN NUCLEAR (A PRUEBA DE BALAS)
# ==============================================================================
def concatenar_escenas(lista_escenas, output_path, unique_id):
    """
    Toma todas las escenas y las pasa por un filtro complejo que FUERZA 
    la resolución, el formato de píxeles, los FPS y el audio (Stereo 48kHz).
    Es imposible que el video final se corrompa con este método.
    """
    if not lista_escenas:
        return False
        
    try:
        logger.info(f"  [Orchestrator] Ensamblando y normalizando {len(lista_escenas)} escenas (Modo Tanque)...")
        
        cmd = ["ffmpeg", "-y"]
        filter_complex = ""
        concat_inputs = ""
        
        # 1. Cargamos todos los inputs y construimos la normalización
        for i, escena in enumerate(lista_escenas):
            cmd.extend(["-i", escena])
            
            # Normalizar Video: Lo obligamos a tener el tamaño, FPS, ratio y pixeles exactos.
            filter_complex += f"[{i}:v]scale={RESOLUTION_W}:{RESOLUTION_H},setsar=1,fps={FPS},format=yuv420p[v{i}];"
            
            # Normalizar Audio: Lo obligamos a ser Estéreo y a 48000Hz pase lo que pase.
            filter_complex += f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
            
            # Preparamos la cadena del concat final
            concat_inputs += f"[v{i}][a{i}]"
            
        # 2. El comando concat que une todo lo normalizado
        filter_complex += f"{concat_inputs}concat=n={len(lista_escenas)}:v=1:a=1[outv][outa]"
        
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-preset", "superfast", # Compensamos velocidad aquí
            "-threads", "4",
            "-r", str(FPS),
            "-c:a", "aac",
            "-ar", "48000",
            "-ac", "2",
            "-b:a", "128k",
            output_path
        ])
        
        # Le damos tiempo suficiente porque está renderizando el master final
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        
    except subprocess.CalledProcessError as e:
        logger.error(f"  [Orchestrator] Error de FFmpeg al concatenar: {e}")
        return False
    except Exception as e:
        logger.error(f"  [Orchestrator] Error crítico al concatenar: {e}")
        return False

# ==============================================================================
# FUNCIÓN AUXILIAR: DESCARGAR MULTIMEDIA DE ANUNCIOS
# ==============================================================================
def descargar_recurso_ad(url, save_path):
    try:
        logger.info(f"  [Orchestrator] Descargando recurso publicitario: {url}")
        r = requests.get(url, stream=True, timeout=15)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return save_path
    except Exception as e:
        logger.error(f"  [Orchestrator] Error descargando anuncio: {e}")
    return None

# ==============================================================================
# EL CEREBRO PRINCIPAL
# ==============================================================================
def process_video_payload(payload):
    article_id = payload.get("article_id", "NO_ID")
    scenes = payload.get("scenes", [])
    
    if not scenes:
        return None

    unique_id = uuid.uuid4().hex[:8]
    final_output_path = os.path.join(OUTPUT_DIR, f"{article_id}.mp4")
    thumbnail_output_path = os.path.join(OUTPUT_DIR, f"{article_id}.jpg") 
    
    archivos_temporales = []
    escenas_renderizadas = []
    miniatura_creada = False
    
    logger.info(f"========== INICIANDO PRODUCCIÓN MATRICIAL: NOTICIA {article_id} ==========")
    
    try:
        for idx, scene in enumerate(scenes):
            logger.info(f"  --- Procesando Escena {idx + 1}/{len(scenes)} ---")
            
            scene_type = scene.get("type", "body") 
            texto_guion = scene.get("text", "")
            
            ad_media_url = scene.get("ad_media_url")
            ad_banner_url = scene.get("ad_banner_url")

            audio_path = None
            if scene_type != "ad_video":
                if not texto_guion:
                    logger.warning(f"  [Orchestrator] Escena {idx} sin texto. Poniendo un silencio para no romper nada.")
                    audio_filename = f"audio_{unique_id}_{idx}.mp3"
                    audio_path = os.path.join(TEMP_VIDEO_DIR, audio_filename)
                    # Generar un mp3 de silencio de 3 segundos por seguridad
                    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3", "-q:a", "9", "-acodec", "libmp3lame", audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    archivos_temporales.append(audio_path)
                else:
                    audio_filename = f"audio_{unique_id}_{idx}.mp3"
                    voz_elegida = scene.get("voice", "hombre_1")
                    audio_path = tts_engine.generate_audio_clip(texto_guion, voz_elegida, audio_filename)
                    if audio_path:
                        archivos_temporales.append(audio_path)
                    else:
                        continue

            bgm_mood = scene.get("bgm_mood")
            bgm_path = media_manager.get_random_bgm(bgm_mood) if bgm_mood else None
            sfx_type = scene.get("sfx_type")
            sfx_path = media_manager.get_random_sfx(sfx_type) if sfx_type else None
            
            local_ad_media = None
            if ad_media_url:
                ext = ".mp4" if ".mp4" in ad_media_url.lower() else ".jpg"
                temp_ad_path = os.path.join(TEMP_VIDEO_DIR, f"ad_media_{unique_id}_{idx}{ext}")
                local_ad_media = descargar_recurso_ad(ad_media_url, temp_ad_path)
                if local_ad_media: archivos_temporales.append(local_ad_media)

            local_ad_banner = None
            if ad_banner_url:
                ext_b = ".png" if ".png" in ad_banner_url.lower() else ".jpg"
                temp_banner_path = os.path.join(TEMP_IMG_DIR, f"ad_banner_{unique_id}_{idx}{ext_b}")
                local_ad_banner = descargar_recurso_ad(ad_banner_url, temp_banner_path)
                if local_ad_banner: archivos_temporales.append(local_ad_banner)

            escena_output = os.path.join(TEMP_VIDEO_DIR, f"escena_{unique_id}_{idx}.mp4")
            exito = False

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
                        termino, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output, unique_id, local_ad_banner
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
                            fondo_path, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output, local_ad_banner
                        )

            elif scene_type == "ad_video":
                if local_ad_media:
                    exito = ffmpeg_ads.renderizar_ad_video(local_ad_media, escena_output)
                else:
                    logger.error("  [Orchestrator] Falló la descarga del video publicitario.")

            elif scene_type == "ad_mencion":
                if local_ad_media and audio_path:
                    overlay_path = media_manager.get_random_template("sin_presentador")
                    exito = ffmpeg_ads.renderizar_mencion(
                        local_ad_media, overlay_path, audio_path, bgm_path, sfx_path, texto_guion, escena_output, unique_id
                    )

            if exito and os.path.exists(escena_output):
                escenas_renderizadas.append(escena_output)
                archivos_temporales.append(escena_output)
                
                if scene_type == "body" and not miniatura_creada:
                    try:
                        cmd_thumb = ["ffmpeg", "-y", "-ss", "00:00:02", "-i", escena_output, "-vframes", "1", "-q:v", "2", thumbnail_output_path]
                        subprocess.run(cmd_thumb, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.exists(thumbnail_output_path):
                            miniatura_creada = True 
                    except Exception:
                        pass
            else:
                logger.error(f"  [Orchestrator] Falló el ensamblaje de la escena {idx} ({scene_type}).")

        # CONCATENACIÓN FINAL CON EL MOTOR BLINDADO
        if len(escenas_renderizadas) > 0:
            exito_final = concatenar_escenas(escenas_renderizadas, final_output_path, unique_id)
            if exito_final:
                logger.info(f"========== ¡SISTEMA COMPLETADO EXITOSAMENTE! Video: {final_output_path} ==========")
                return final_output_path
            else:
                logger.error("  [Orchestrator] Error en la concatenación de las escenas.")
                return None
        else:
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