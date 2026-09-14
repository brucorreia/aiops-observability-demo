import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = 4096
CHUNK = 8 * 1024 * 1024
PRODUCTS = (
    "Fone Bluetooth",
    "Camiseta Preta",
    "Garrafa Térmica",
    "Mouse Sem Fio",
    "Caderno A5",
    "Mochila Urbana",
    "Carregador USB-C",
    "Caneca Cerâmica",
    "Teclado Compacto",
    "Luminária LED",
    "Cabo HDMI",
    "Squeeze 750ml",
)


def load_mode() -> str:
    path = Path(__file__).with_name("demo_mode")
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or "good"
    return (os.getenv("DEMO_MODE") or "").strip() or "good"


MODE = load_mode()
PUBLIC_MODE = "crashloop" if MODE in {"crashloop", "oom"} else MODE
PORT = int(os.getenv("PORT", "8080"))
SERVICE = os.getenv("SERVICE_NAME", "demo-app")
HELD: list[bytearray] = []
ORDER_LOCK = threading.Lock()
ORDER_SEQ = 4800


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_event(**fields) -> None:
    payload = {
        "timestamp": utc_now(),
        "service": SERVICE,
        "logger": "demo-app",
        "version": PUBLIC_MODE,
        **fields,
    }
    print(json.dumps(payload), flush=True)


if MODE == "crashloop":
    os._exit(1)


def exhaust_memory() -> None:
    while True:
        block = bytearray(CHUNK)
        for offset in range(0, CHUNK, PAGE):
            block[offset] = 1
        HELD.append(block)


def next_order() -> dict:
    global ORDER_SEQ
    with ORDER_LOCK:
        ORDER_SEQ += 1
        number = ORDER_SEQ
    valor = round(random.uniform(1.0, 350.0), 2)
    return {
        "pedido": number,
        "produto": random.choice(PRODUCTS),
        "valor": valor,
        "currency": "BRL",
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, body: str) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, '{"status":"healthy"}')
            return

        if self.path == "/api":
            started = time.monotonic()
            status = 500 if MODE == "http500" else 200
            order = next_order()
            duration_ms = max(1, int((time.monotonic() - started) * 1000)) or 12
            event = {
                "level": "error" if status == 500 else "info",
                "method": "GET",
                "path": "/api",
                "status": status,
                "duration_ms": duration_ms if duration_ms > 1 else 12,
                "pedido": order["pedido"],
                "produto": order["produto"],
                "valor": order["valor"],
                "message": "internal error serving /api" if status == 500 else "request completed",
            }
            log_event(**event)
            self.send_json(
                status,
                json.dumps(
                    {
                        "status": status,
                        "version": PUBLIC_MODE,
                        **order,
                    }
                ),
            )
            return

        self.send_json(404, '{"status":404}')

    def log_message(self, *_args) -> None:
        return


if MODE == "oom":
    threading.Thread(target=exhaust_memory, daemon=True).start()

if __name__ == "__main__":
    log_event(level="info", event="started", port=PORT, message="demo-app listening")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
