# -*- coding: utf-8 -*-
"""
Configuración de Gunicorn para el worker de video.

Un solo worker: cada video ya usa FFmpeg y el lock vive en el proceso.
Más workers multiplican la RAM y no comparten el lock.
HTTP/2 queda apagado: el contenedor habla HTTP/1.1 y el aviso
'PRI * HTTP/2.0' es un cliente que Gunicorn rechaza sin matar el worker.
"""

import os

bind = "0.0.0.0:%s" % os.environ.get("PORT", "3001")
workers = int(os.environ.get("TTS_WEB_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "45"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
# max_requests recicla el worker al azar y cortaría un video en curso.
max_requests = 0
limit_request_line = int(os.environ.get("GUNICORN_LIMIT_REQUEST_LINE", "4094"))
limit_request_fields = 100
limit_request_field_size = 8190
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True
preload_app = False

# Gunicorn antiguo ignora claves que no conoce. En 25+ fija HTTP/1.1.
http_protocols = "h1"
http2_cleartext = "off"


def post_worker_init(worker):
    worker.log.info("Worker %s listo. Activando supervision de estabilidad.", worker.pid)
    try:
        import app as app_module
        app_module.enable_production_supervision()
    except Exception:
        worker.log.exception("No se pudo activar la supervision de estabilidad")


def worker_abort(worker):
    worker.log.warning(
        "WORKER_ABORT pid=%s. Gunicorn recicla el worker por silencio del heartbeat. Se cancelan los FFmpeg hijos.",
        worker.pid,
    )
    _stop_children()


def worker_exit(server, worker):
    _stop_children()
    server.log.info("WORKER_EXIT pid=%s", worker.pid)


def on_exit(server):
    server.log.info("Gunicorn master en cierre.")


def _stop_children():
    try:
        import process_guard
        process_guard.request_cancel()
        process_guard.kill_all()
    except Exception:
        pass
