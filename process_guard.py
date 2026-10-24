# -*- coding: utf-8 -*-
"""
Ejecuta procesos hijos (FFmpeg, ffprobe, edge-tts) con tope de tiempo
y los mata junto con su grupo de procesos si se quedan colgados.

No modifica los argumentos del comando que recibe.
"""

import os
import signal
import subprocess
import threading
import logging

logger = logging.getLogger(__name__)

_registry_lock = threading.Lock()
_active_pids = set()
_cancel = threading.Event()

_STDERR_TAIL = 8192
_STDOUT_CAP = 1024 * 1024


class CommandResult:
    def __init__(self, args, returncode, stdout="", stderr="", timed_out=False):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.timed_out = timed_out

    @property
    def cancelled(self):
        return cancellation_requested() and self.returncode != 0


def cancellation_requested():
    return _cancel.is_set()


def request_cancel():
    _cancel.set()


def clear_cancel():
    _cancel.clear()


def kill_all():
    with _registry_lock:
        pids = list(_active_pids)
    for pid in pids:
        _kill_group(pid)


def run(cmd, timeout, check=False, capture_output=False, log_label="subprocess"):
    """
    Ejecuta `cmd` (lista de argumentos, nunca un shell) y espera como máximo
    `timeout` segundos. Si vence el plazo, mata el grupo de procesos.
    """
    if isinstance(cmd, (str, bytes)) or not cmd:
        raise ValueError("El comando debe ser una lista de argumentos, sin shell.")

    if cancellation_requested():
        logger.error("  [%s] Comando no iniciado: la tarea fue cancelada.", log_label)
        result = CommandResult(list(cmd), returncode=1, stderr="cancelled", timed_out=False)
        if check:
            raise subprocess.CalledProcessError(1, cmd, result.stdout, result.stderr)
        return result

    stdout_target = subprocess.PIPE if capture_output else subprocess.DEVNULL
    proc = subprocess.Popen(
        list(cmd),
        stdout=stdout_target,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    _register(proc.pid)
    stdout_box = []
    stderr_box = []
    readers = []
    if capture_output:
        readers.append(threading.Thread(
            target=_drain, args=(proc.stdout, stdout_box, _STDOUT_CAP), daemon=True
        ))
    readers.append(threading.Thread(
        target=_drain, args=(proc.stderr, stderr_box, _STDERR_TAIL), daemon=True
    ))
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            logger.error(
                "  [%s] TIMEOUT tras %ss. Matando el grupo de procesos pid=%s.",
                log_label, timeout, proc.pid,
            )
            _kill_group(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(proc.pid, sig=signal.SIGKILL)
                proc.wait(timeout=5)
    finally:
        for reader in readers:
            reader.join(timeout=2)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        _unregister(proc.pid)

    stdout = "".join(stdout_box)
    stderr = "".join(stderr_box)
    result = CommandResult(list(cmd), proc.returncode if proc.returncode is not None else -1, stdout, stderr, timed_out)

    if timed_out:
        _log_tail(log_label, "timeout", result.stderr)
        if check:
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
        return result

    if result.returncode != 0:
        _log_tail(log_label, "exit %s" % result.returncode, result.stderr)
        if check:
            raise subprocess.CalledProcessError(result.returncode, cmd, stdout, stderr)
    return result


def _register(pid):
    with _registry_lock:
        _active_pids.add(pid)


def _unregister(pid):
    with _registry_lock:
        _active_pids.discard(pid)


def _kill_group(pid, sig=signal.SIGTERM):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        logger.warning("  [process_guard] Sin permiso para señalar el grupo %s.", pid)
        return
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def _drain(stream, sink, limit):
    if stream is None:
        return
    try:
        while True:
            # FFmpeg escribe el progreso con retornos de carro, sin salto de línea.
            # Leer por bloques evita acumular toda la salida en una sola cadena.
            chunk = stream.read(4096)
            if not chunk:
                break
            sink.append(chunk)
            size = sum(len(part) for part in sink)
            while size > limit and len(sink) > 1:
                size -= len(sink.pop(0))
            if sink and len(sink[-1]) > limit:
                sink[-1] = sink[-1][-limit:]
    except Exception:
        return


def _log_tail(label, status, stderr):
    tail = (stderr or "").strip().replace("\n", " | ")
    if len(tail) > 700:
        tail = tail[-700:]
    if tail:
        logger.error("  [%s] Fallo (%s). stderr: %s", label, status, tail)
    else:
        logger.error("  [%s] Fallo (%s) sin stderr.", label, status)
