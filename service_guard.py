# -*- coding: utf-8 -*-
"""
Comprobaciones de disco, memoria y limpieza de temporales.

No decide cómo se ve un video. Solo evita que una tarea deje el proceso
sin recursos o que un reinicio acumule archivos huérfanos.
"""

import os
import shutil
import time
import logging

logger = logging.getLogger(__name__)


def memory_available_mb():
    """Memoria que el kernel puede entregar sin swap, en MiB. None si no se puede leer."""
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                info[key.strip()] = int(value.strip().split()[0])
        kib = info.get("MemAvailable", info.get("MemFree"))
        if kib is None:
            return None
        return kib // 1024
    except (OSError, ValueError, IndexError):
        return None


def disk_free_mb(path=None):
    target = path or os.getcwd()
    try:
        return shutil.disk_usage(target).free // (1024 * 1024)
    except OSError:
        return None


def disk_allows_new_task():
    free = disk_free_mb()
    if free is None:
        return True, None
    try:
        minimum = int(os.getenv("MIN_FREE_DISK_MB", "512"))
    except ValueError:
        minimum = 512
    return free >= max(0, minimum), free


def memory_allows_new_task():
    free = memory_available_mb()
    if free is None:
        return True, None
    try:
        minimum = int(os.getenv("MIN_FREE_RAM_MB", "120"))
    except ValueError:
        minimum = 120
    return free >= max(0, minimum), free


def tool_on_path(name):
    return shutil.which(name) is not None


def validate_article_id(value):
    """
    Acepta el mismo identificador que ya usa la API y rechaza solo valores
    que puedan salir del directorio de trabajo (separadores, nulos, '..').
    """
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    if not text or len(text) > 200:
        return None
    if "/" in text or "\\" in text or "\x00" in text:
        return None
    if text in (".", "..") or ".." in text:
        return None
    return text


def cleanup_stale_workdir(startup=False):
    """
    Borra temporales huérfanos. En arranque limpia temp de inmediato porque
    no hay una tarea viva. Los videos de output se conservan unas horas por
    si hace falta recuperarlos a mano. Nunca toca assets ni locks_history.
    """
    from config import OUTPUT_DIR, TEMP_AUDIO_DIR, TEMP_IMG_DIR, TEMP_VIDEO_DIR

    now = time.time()
    temp_age = 0 if startup else _env_int("TEMP_FILE_MAX_AGE_SECONDS", 10800, minimum=600)
    output_age = _env_int("OUTPUT_FILE_MAX_AGE_SECONDS", 21600, minimum=3600)
    removed = 0
    for directory in (
        TEMP_AUDIO_DIR,
        TEMP_VIDEO_DIR,
        TEMP_IMG_DIR,
        os.path.join(os.getcwd(), "temp"),
    ):
        removed += _purge_old_files(directory, temp_age, now)
    removed += _purge_old_files(OUTPUT_DIR, output_age, now)
    if removed:
        logger.info("  [Limpieza] Archivos temporales eliminados: %s (startup=%s).", removed, startup)
    return removed


def _env_int(name, default, minimum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def _purge_old_files(directory, max_age, now):
    if not directory or not os.path.isdir(directory):
        return 0
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError as exc:
        logger.warning("  [Limpieza] No se pudo listar %s: %s", directory, exc)
        return 0
    for name in names:
        path = os.path.join(directory, name)
        try:
            if os.path.islink(path):
                continue
            if os.path.isfile(path):
                if now - os.path.getmtime(path) >= max_age:
                    os.remove(path)
                    removed += 1
            elif os.path.isdir(path):
                for sub in os.listdir(path):
                    sub_path = os.path.join(path, sub)
                    if os.path.isfile(sub_path) and not os.path.islink(sub_path):
                        if now - os.path.getmtime(sub_path) >= max_age:
                            os.remove(sub_path)
                            removed += 1
        except OSError as exc:
            logger.warning("  [Limpieza] No se pudo borrar %s: %s", path, exc)
    return removed
