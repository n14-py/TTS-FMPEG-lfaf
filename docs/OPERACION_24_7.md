# Operación continua de TTS-FFMPEG

Este documento describe cómo desplegar, comprobar y revertir las correcciones de estabilidad. No cambia el contrato con la API de noticias ni la fabricación audiovisual.

## Qué quedó protegido

- Gunicorn sigue en HTTP/1.1, un worker y ocho hilos. Una línea `PRI * HTTP/2.0` se rechaza y el worker sigue atendiendo.
- El lock de video se libera si la tarea falla, si FFmpeg agota su tiempo o si el hilo no llega a arrancar.
- FFmpeg, ffprobe y el `edge-tts` del botón Escuchar se ejecutan con tope de tiempo y, si se pasan, muere todo su grupo de procesos.
- Edge TTS del noticiero reintenta tres veces con espera creciente. La voz no cambia.
- YouTube y R2 tienen tiempos máximos de red para no dejar el servidor ocupado.
- `/health` responde 200 mientras el proceso vive, también durante un render. Pasa a 503 solo si el supervisor declara el worker atascado y pide reinicio.
- La limpieza de objetos R2 de más de 28 días no se activa sola. En Gunicorn nunca llegó a ejecutarse; ahora hace falta `R2_CLEANUP_ENABLED=1`.

## Variables nuevas

| Variable | Valor por defecto | Efecto |
| --- | --- | --- |
| `TTS_WEB_WORKERS` | `1` | No subirla en un servidor pequeño: el lock es por proceso. |
| `GUNICORN_THREADS` | `8` | Hilos HTTP. No fabrican videos en paralelo. |
| `GUNICORN_TIMEOUT` | `300` | Silencio del worker antes de que Gunicorn lo recicle. |
| `GUNICORN_GRACEFUL_TIMEOUT` | `45` | Espera tras SIGTERM antes del cierre forzado. |
| `TASK_HARD_TIMEOUT_SECONDS` | `10800` | Tope absoluto de una tarea. Mínimo interno: 600. |
| `TTS_ATTEMPT_TIMEOUT_SECONDS` | `90` | Cada intento de Edge TTS del noticiero. |
| `YOUTUBE_UPLOAD_TIMEOUT_SECONDS` | `900` | Tope de una subida a YouTube. |
| `YOUTUBE_SOCKET_TIMEOUT_SECONDS` | `120` | Tope de cada lectura de red de esa subida. |
| `MIN_FREE_DISK_MB` | `512` | Rechaza tareas nuevas por debajo de este espacio. |
| `MIN_FREE_RAM_MB` | `120` | Rechaza tareas nuevas por debajo de esta RAM disponible. |
| `MIN_RAM_FOR_AUDIO_DURING_VIDEO_MB` | `200` | Permite el MP3 de Escuchar mientras hay un video solo si hay esta RAM. |
| `MAX_AUDIO_CONCURRENCY` | `1` | Locuciones simultáneas del botón Escuchar. |
| `MAX_CONTENT_LENGTH_BYTES` | `2097152` | Tamaño máximo del JSON. |
| `MAX_SCENES` | `100` | Tope de escenas por tarea. |
| `MAX_AD_DOWNLOAD_BYTES` | `209715200` | Tope de descarga de un anuncio. |
| `MAX_IMAGE_DOWNLOAD_BYTES` | `26214400` | Tope de una imagen de noticia o mapa. |
| `MAX_PEXELS_DOWNLOAD_BYTES` | `314572800` | Tope de un clip de Pexels. |
| `R2_CLEANUP_ENABLED` | `0` | `1` borra en R2 objetos de más de 28 días, una vez al día. |
| `TEMP_FILE_MAX_AGE_SECONDS` | `10800` | Edad a partir de la cual el barrido borra temporales, si no hay un video en curso. |
| `OUTPUT_FILE_MAX_AGE_SECONDS` | `21600` | Edad de los mp4/jpg finales huérfanos. |

`ADMIN_API_KEY`, `MAIN_API_URL` y las credenciales de R2, YouTube, Mapbox y Pexels se usan igual que antes.

## Despliegue

Desde el directorio del proyecto, con el mismo `.env` o las mismas variables que ya usa el contenedor:

```bash
docker compose build
docker compose up -d
```

Si el contenedor no se crea con Compose:

```bash
docker build -t tts-ffmpeg .
docker stop tts-ffmpeg || true
docker rm tts-ffmpeg || true
docker run -d --name tts-ffmpeg \
  --restart unless-stopped \
  -p 3001:3001 \
  --env-file .env \
  -v tts_locks:/app/locks_history \
  tts-ffmpeg
```

El volumen `locks_history` conserva los archivos `.done`. Sin ese volumen, al recrear el contenedor el historial local se pierde y una noticia reenviada puede volver a subirse a YouTube.

Comprobación:

```bash
curl -fsS http://127.0.0.1:3001/health
docker ps --filter name=tts-ffmpeg
docker logs --tail 100 tts-ffmpeg
```

`/health` debe devolver HTTP 200 y `"status": "healthy"`. Durante un video, `service_state` pasa a `busy` y `accepting_video_tasks` a `false`, pero el código HTTP sigue siendo 200. No hay que marcar el contenedor como caído por eso.

## Reversión

```bash
git checkout <commit-anterior>
docker compose build
docker compose up -d
```

O, si la imagen anterior sigue en el daemon:

```bash
docker stop tts-ffmpeg
docker rm tts-ffmpeg
docker run -d --name tts-ffmpeg --restart unless-stopped -p 3001:3001 --env-file .env <imagen-anterior>
```

No borra `assets_video` ni el volumen de `locks_history`.

## Qué no hace este cambio

- No recupera una tarea a la que se le mató el proceso en mitad de FFmpeg o de la subida. No hay cola persistente. La API externa tiene que reenviar la noticia.
- Si YouTube aceptó el video y el proceso murió antes de escribir el `.done`, un reintento puede publicar un segundo video.
- No habla HTTP/2. Los clientes que envían el prefacio `PRI * HTTP/2.0` reciben un rechazo de Gunicorn y deben usar HTTP/1.1.
