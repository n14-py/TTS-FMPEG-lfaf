# -*- coding: utf-8 -*-
"""Pruebas de estabilidad. No fabrican videos ni llaman a la API externa."""

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import app
import config
import main_orchestrator
import process_guard
import service_guard
import tts_engine
import youtube_uploader

def _fail_tts(message):
    def _run(coro):
        coro.close()
        raise RuntimeError(message)
    return _run


KEY = os.getenv("ADMIN_API_KEY", "secreto123456")
AUTH = {"x-api-key": KEY, "Content-Type": "application/json"}


def _wait_unlock(timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app.processing_lock.locked():
            return True
        time.sleep(0.05)
    return not app.processing_lock.locked()


class ResourceAndContractTests(unittest.TestCase):
    def test_video_constants_unchanged(self):
        self.assertEqual(config.RESOLUTION_W, 1280)
        self.assertEqual(config.RESOLUTION_H, 720)
        self.assertEqual(config.FPS, 15)
        self.assertEqual(config.VIDEO_PRESET, "ultrafast")
        self.assertEqual(config.CHROMA_COLOR, "0x00FF00")
        self.assertEqual(config.CHROMA_SIMILARITY, "0.30")
        self.assertEqual(config.CHROMA_BLEND, "0.10")
        self.assertEqual(config.VOICES["mujer_1"], "es-MX-DaliaNeural")
        self.assertEqual(config.VOICES["mujer_2"], "es-ES-ElviraNeural")
        self.assertEqual(config.VOICES["hombre_1"], "es-AR-TomasNeural")
        self.assertEqual(config.VOICES["hombre_2"], "es-CO-TomasNeural")
        self.assertEqual(app.LISTEN_VOICE, "es-MX-JorgeNeural")
        self.assertEqual(app.LISTEN_RATE, "+10%")

    def test_scene_templates_keep_encoding_parameters(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        universal = open(os.path.join(root, "scene_templates", "ffmpeg_universal.py"), encoding="utf-8").read()
        intro = open(os.path.join(root, "scene_templates", "ffmpeg_intro.py"), encoding="utf-8").read()
        self.assertIn("chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}", universal)
        self.assertIn('"-preset", "superfast"', universal)
        self.assertIn('"-threads", "2"', universal)
        self.assertIn('"-c:v", "libx264"', universal)
        self.assertIn('"-c:a", "aac"', intro)
        self.assertIn('"-b:a", "128k"', intro)
        self.assertIn('"-shortest"', intro)

    def test_concat_keeps_original_ffmpeg_arguments(self):
        captured = {}

        def fake_run(cmd, timeout, check=False, capture_output=False, log_label="subprocess"):
            captured["cmd"] = list(cmd)
            captured["timeout"] = timeout
            raise subprocess.CalledProcessError(1, cmd)

        with patch("main_orchestrator.process_guard.run", side_effect=fake_run):
            ok = main_orchestrator.concatenar_escenas(["/tmp/escena_a.mp4"], "/tmp/final.mp4", "abc")
        self.assertFalse(ok)
        cmd = captured["cmd"]
        rendered = " ".join(cmd)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("libx264", cmd)
        self.assertIn("superfast", cmd)
        self.assertIn("aac", cmd)
        self.assertIn("48000", cmd)
        self.assertIn("128k", cmd)
        self.assertIn("scale=1280:720", rendered)
        self.assertIn("fps=15", rendered)
        self.assertEqual(captured["timeout"], 600)

    def test_streamed_download_keeps_the_same_bytes(self):
        import background_fetcher

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def iter_content(self, chunk_size=1024):
                for offset in range(0, len(self.payload), chunk_size):
                    yield self.payload[offset:offset + chunk_size]

        payload = b"\xff\xd8" + (b"noticia-lat" * 300)
        path = "/tmp/img-bytes-5236.bin"
        try:
            self.assertTrue(background_fetcher._guardar_respuesta(FakeResponse(payload), path, 1024 * 1024))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), payload)
            self.assertFalse(background_fetcher._guardar_respuesta(FakeResponse(payload), path, 100))
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_article_id_rejects_path_escape_and_keeps_normal_ids(self):
        self.assertEqual(service_guard.validate_article_id(12345), "12345")
        self.assertEqual(service_guard.validate_article_id("noticia-01"), "noticia-01")
        self.assertIsNone(service_guard.validate_article_id("../etc/passwd"))
        self.assertIsNone(service_guard.validate_article_id("a/b"))
        self.assertIsNone(service_guard.validate_article_id(".."))
        self.assertIsNone(service_guard.validate_article_id(""))


class ProcessGuardTests(unittest.TestCase):
    def test_rejects_shell_string(self):
        with self.assertRaises(ValueError):
            process_guard.run("sleep 1", timeout=1)

    def test_timeout_kills_process_and_child(self):
        script = "import subprocess, time; subprocess.Popen(['sleep', '30']); time.sleep(30)"
        started = time.time()
        result = process_guard.run([sys.executable, "-c", script], timeout=1, log_label="test-kill")
        self.assertTrue(result.timed_out)
        self.assertLess(time.time() - started, 8)
        listing = subprocess.check_output(["ps", "-eo", "args"], text=True)
        self.assertNotIn("\nsleep 30\n", "\n" + listing + "\n")
        self.assertFalse(any(line.strip() == "sleep 30" for line in listing.splitlines()))


class FfmpegRunnerTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg no está instalado en este entorno")

    def test_invalid_input_returns_false(self):
        from ffmpeg_core import execute_ffmpeg_command
        ok = execute_ffmpeg_command(
            ["ffmpeg", "-y", "-i", "/tmp/no-existe-5236.mp4", "-f", "null", "-"],
            timeout=20,
        )
        self.assertFalse(ok)

    def test_timeout_kills_ffmpeg(self):
        marker = "ffkill-marker-5236"
        result = process_guard.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-f", "null", marker],
            timeout=1,
            log_label="test-ffmpeg-timeout",
        )
        self.assertTrue(result.timed_out)
        self.assertEqual(process_guard._active_pids, set())
        listing = subprocess.check_output(["ps", "-eo", "args"], text=True)
        self.assertNotIn(marker, listing)


class TtsFailureTests(unittest.TestCase):
    def test_transient_tts_failure_stops_after_three_attempts(self):
        with patch("tts_engine.asyncio.run", side_effect=_fail_tts("network down")) as run_async, \
                patch("tts_engine.time.sleep"):
            path = tts_engine.generate_audio_clip("Hola, esto es una prueba.", "hombre_1", "unit_tts.mp3")
        self.assertIsNone(path)
        self.assertEqual(run_async.call_count, 3)

    def test_invalid_voice_is_not_retried(self):
        with patch("tts_engine.asyncio.run", side_effect=_fail_tts("Invalid voice name")) as run_async, \
                patch("tts_engine.time.sleep"):
            path = tts_engine.generate_audio_clip("Hola, esto es una prueba.", "hombre_1", "unit_tts_perm.mp3")
        self.assertIsNone(path)
        self.assertEqual(run_async.call_count, 1)


class ApiStabilityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.patches = [
            patch("app.service_guard.tool_on_path", return_value=True),
            patch("app.service_guard.disk_allows_new_task", return_value=(True, 10000)),
            patch("app.service_guard.memory_allows_new_task", return_value=(True, 10000)),
            patch("app._notificar_webhook_node"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        _wait_unlock()
        if app.processing_lock.locked():
            try:
                app.processing_lock.release()
            except RuntimeError:
                pass
            with app._state_lock:
                app._task["held"] = False
                app._task["started"] = None
        for item in self.patches:
            item.stop()

    def _post(self, payload, headers=None):
        return self.client.post("/generate_video", json=payload, headers=headers or AUTH)

    def test_health_stays_available(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["server"], "Noticias.lat Video Factory V4")
        self.assertIn("accepting_video_tasks", body)
        self.assertIn("disk_free_mb", body)

    def test_invalid_json_and_auth_do_not_lock(self):
        denied = self.client.post("/generate_video", json={"article_id": "x", "scenes": [{}]}, headers={"Content-Type": "application/json"})
        self.assertEqual(denied.status_code, 403)
        invalid = self.client.post(
            "/generate_video",
            data="esto no es json",
            headers={"x-api-key": KEY, "Content-Type": "application/json"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json()["error"], "No se envió un cuerpo JSON válido.")
        missing = self._post({"article_id": "solo-id"})
        self.assertEqual(missing.status_code, 400)
        escaped = self._post({"article_id": "../secrets", "scenes": [{"type": "body"}]})
        self.assertEqual(escaped.status_code, 400)
        self.assertFalse(app.processing_lock.locked())

    def test_oversized_body_returns_413_without_lock(self):
        raw = b'{"article_id":"big","scenes":["' + (b"a" * (3 * 1024 * 1024)) + b'"]}'
        response = self.client.post("/generate_video", data=raw, headers=AUTH)
        self.assertEqual(response.status_code, 413)
        self.assertFalse(app.processing_lock.locked())

    def test_too_many_scenes_rejected(self):
        payload = {"article_id": "muchas-escenas", "scenes": [{"type": "body", "text": "a"}] * 101}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(app.processing_lock.locked())

    def test_task_failure_releases_lock_and_next_task_is_accepted(self):
        with patch("app.main_orchestrator.process_video_payload", side_effect=RuntimeError("ffmpeg explotó")):
            first = self._post({"article_id": "fallo-1", "scenes": [{"type": "body", "text": "hola"}]})
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.get_json()["status"], "processing")
        self.assertTrue(_wait_unlock())
        self.assertFalse(app.processing_lock.locked())

        with patch("app.main_orchestrator.process_video_payload", return_value=None):
            second = self._post({"article_id": "fallo-2", "scenes": [{"type": "body", "text": "hola"}]})
        self.assertEqual(second.status_code, 202)
        self.assertTrue(_wait_unlock())

    def test_busy_server_rejects_second_task_and_health_stays_up(self):
        started = threading.Event()
        release = threading.Event()

        def slow(payload):
            started.set()
            release.wait(5)
            return None

        with patch("app.main_orchestrator.process_video_payload", side_effect=slow):
            accepted = self._post({"article_id": "lento-1", "scenes": [{"type": "body", "text": "hola"}]})
            self.assertEqual(accepted.status_code, 202)
            self.assertTrue(started.wait(2))
            busy = self._post({"article_id": "lento-2", "scenes": [{"type": "body", "text": "hola"}]})
            self.assertEqual(busy.status_code, 503)
            self.assertEqual(busy.get_json()["error"], "El servidor está procesando otro video. Reintente en unos minutos.")
            health = self.client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.get_json()["status"], "healthy")
            self.assertFalse(health.get_json()["accepting_video_tasks"])
            release.set()
        self.assertTrue(_wait_unlock())

    def test_low_disk_does_not_take_the_lock(self):
        with patch("app.service_guard.disk_allows_new_task", return_value=(False, 10)), \
                patch("app.main_orchestrator.process_video_payload") as render:
            response = self._post({"article_id": "sin-disco", "scenes": [{"type": "body", "text": "hola"}]})
        self.assertEqual(response.status_code, 503)
        render.assert_not_called()
        self.assertFalse(app.processing_lock.locked())

    def test_internal_error_hides_traceback(self):
        with patch("app._check_auth", side_effect=RuntimeError("secreto interno")):
            response = self._post({"article_id": "x", "scenes": [{"type": "body"}]})
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertEqual(body["error"], "Error interno del servidor.")
        self.assertNotIn("secreto interno", response.get_data(as_text=True))
        self.assertNotIn("Traceback", response.get_data(as_text=True))

    def test_listen_audio_uses_argv_and_same_voice(self):
        command = app.build_listen_audio_command("hola $(touch /tmp/tts_pwned_5236)", "/tmp/out.mp3")
        self.assertEqual(command[:4], ["edge-tts", "--voice", "es-MX-JorgeNeural", "--rate"])
        self.assertEqual(command[4], "+10%")
        self.assertIsInstance(command, list)
        self.assertFalse(app.processing_lock.locked())
        app._audio_sem.acquire()
        try:
            with patch("app.process_guard.run") as run_cmd, patch("app.cloudflare_r2.upload_media_to_r2", return_value=None):
                run_cmd.return_value = process_guard.CommandResult(command, 0)
                app.background_audio_task("audio-1", "audio-1", "hola $(touch /tmp/tts_pwned_5236)")
            used = run_cmd.call_args[0][0]
            self.assertIsInstance(used, list)
            self.assertEqual(used[0], "edge-tts")
            self.assertEqual(used[6], "hola $(touch /tmp/tts_pwned_5236)")
            self.assertNotIn("touch", used[:6])
            self.assertFalse(os.path.exists("/tmp/tts_pwned_5236"))
        finally:
            if os.path.exists("/tmp/tts_pwned_5236"):
                os.remove("/tmp/tts_pwned_5236")


class GunicornInvalidRequestTests(unittest.TestCase):
    def test_http2_preface_does_not_stop_the_worker(self):
        port = 18765
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["PYTHONUNBUFFERED"] = "1"
        env["R2_CLEANUP_ENABLED"] = "0"
        proc = subprocess.Popen(
            [sys.executable, "-m", "gunicorn", "-c", "gunicorn.conf.py", "--bind", "127.0.0.1:%s" % port, "app:app"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        logs = []

        def _read():
            for line in proc.stdout:
                logs.append(line)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        try:
            self.assertTrue(_wait_http(port, proc), "Gunicorn no llegó a responder /health. Logs: %s" % "".join(logs[-30:]))
            _send_raw(port, b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")
            _send_raw(port, b"esto no es HTTP\r\n\r\n")
            status, body = _get(port, "/health")
            self.assertEqual(status, 200)
            self.assertIn(b"Noticias.lat Video Factory V4", body)
            status_home, _home = _get(port, "/")
            self.assertEqual(status_home, 200)
            deadline = time.time() + 3
            while time.time() < deadline and not any("Invalid request" in line for line in logs):
                time.sleep(0.1)
            self.assertTrue(any("PRI * HTTP/2.0" in line or "Invalid request" in line for line in logs), "".join(logs[-40:]))
            self.assertIsNone(proc.poll(), "El proceso de Gunicorn terminó después de la petición inválida.")
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), 15)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), 9)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)


class YouTubeUploadClientTests(unittest.TestCase):
    def test_service_uses_library_client(self):
        class _Creds:
            valid = True

        with patch("youtube_uploader.os.path.exists", return_value=True), \
             patch("youtube_uploader.Credentials.from_authorized_user_file", return_value=_Creds()), \
             patch("youtube_uploader.build") as build:
            build.return_value = object()
            service = youtube_uploader.get_authenticated_service(0)

        self.assertIs(service, build.return_value)
        args, kwargs = build.call_args
        self.assertEqual(args, ("youtube", "v3"))
        self.assertIsInstance(kwargs.get("credentials"), _Creds)
        self.assertNotIn("http", kwargs)

    def test_library_http_does_not_treat_308_as_redirect(self):
        import httplib2
        from googleapiclient.http import build_http

        raw = httplib2.Http()
        library = build_http()
        self.assertIn(308, set(raw.redirect_codes))
        self.assertNotIn(308, set(library.redirect_codes))


def _wait_http(port, proc, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            status, _body = _get(port, "/health")
            if status == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def _get(port, path):
    with urllib.request.urlopen("http://127.0.0.1:%s%s" % (port, path), timeout=3) as response:
        return response.status, response.read()


def _send_raw(port, payload):
    conn = socket.create_connection(("127.0.0.1", port), timeout=3)
    try:
        conn.sendall(payload)
        conn.settimeout(1)
        try:
            conn.recv(4096)
        except socket.timeout:
            pass
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
