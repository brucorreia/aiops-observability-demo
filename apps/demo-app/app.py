import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def load_mode() -> str:
    env = (os.getenv("DEMO_MODE") or "").strip()
    if env:
        return env
    path = Path(__file__).with_name("demo_mode")
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or "good"
    return "good"


MODE = load_mode()
PORT = int(os.getenv("PORT", "8080"))
SERVICE = os.getenv("SERVICE_NAME", "demo-app")
CHUNKS: list[bytearray] = []
ALLOCATED_BYTES = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_event(**fields) -> None:
    payload = {
        "timestamp": utc_now(),
        "service": SERVICE,
        "logger": "demo-app",
        "version": MODE,
        **fields,
    }
    print(json.dumps(payload), flush=True)


if MODE == "crashloop":
    log_event(level="error", event="startup_failed", message="simulated crash during startup")
    sys.exit(1)


def grow_memory() -> None:
    global ALLOCATED_BYTES
    while True:
        CHUNKS.append(bytearray(2 * 1024 * 1024))
        ALLOCATED_BYTES += 2 * 1024 * 1024
        log_event(
            level="info",
            event="memory_allocated",
            allocated_bytes=ALLOCATED_BYTES,
            message="progressive memory allocation for OOM demo",
        )
        time.sleep(0.3)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, body: str) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, '{"status":"healthy"}')
            return

        if self.path == "/api":
            started = time.monotonic()
            status = 500 if MODE == "http500" else 200
            duration_ms = max(1, int((time.monotonic() - started) * 1000)) or 12
            event = {
                "level": "error" if status == 500 else "info",
                "method": "GET",
                "path": "/api",
                "status": status,
                "duration_ms": duration_ms if duration_ms > 1 else 12,
                "message": "simulated upstream failure" if status == 500 else "request completed",
            }
            log_event(**event)
            self.send_json(status, json.dumps({"status": status, "version": MODE}))
            return

        self.send_json(404, '{"status":404}')

    def log_message(self, *_args) -> None:
        return


if MODE == "oom":
    threading.Thread(target=grow_memory, daemon=True).start()

log_event(level="info", event="started", port=PORT, message="demo-app listening")
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
