from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from api import console
from config import load_scoring_config, settings as load_settings
from pipeline import analyze_payload
from recommendations import execute as execute_mod
from recommendations import store

CFG = load_settings(load_scoring_config())
LAST_EXECUTION_AT: dict[str, float] = {}
EXECUTION_COOLDOWN_SECONDS = 600


def apply_recommendation(analysis: dict[str, Any]) -> dict[str, Any]:
    ident = analysis.get("id") or ""
    incident = analysis.get("incident_type") or "unknown"
    if not analysis.get("automatic_execution_allowed"):
        payload = {
            "event": "automatic_execution_skipped",
            "id": ident,
            "recommended_action": analysis.get("recommended_action"),
            "reason": "automatic_execution_disabled",
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        store.emit(**payload)
        return analysis
    decision = execute_mod.automatic_decision(analysis)
    if not decision:
        reason = "investigate_or_none" if analysis.get("scoring_source") == "llm" else "llm_unavailable"
        payload = {
            "event": "automatic_execution_skipped",
            "id": ident,
            "recommended_action": analysis.get("recommended_action"),
            "reason": reason,
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        store.emit(**payload)
        return analysis
    last = LAST_EXECUTION_AT.get(incident, 0.0)
    if time.monotonic() - last < EXECUTION_COOLDOWN_SECONDS:
        payload = {
            "event": "automatic_execution_skipped",
            "id": ident,
            "recommended_action": analysis.get("recommended_action"),
            "reason": "cooldown",
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        store.emit(**payload)
        return analysis
    try:
        executed, detail = execute_mod.execute(decision, analysis)
    except Exception as exc:  # noqa: BLE001 - log and keep the webhook 200
        payload = {
            "event": "automatic_execution_failed",
            "id": ident,
            "decision": decision,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        store.emit(**payload)
        return analysis
    LAST_EXECUTION_AT[incident] = time.monotonic()
    updated = store.record_decision(ident, decision, executed, detail)
    payload = {
        "event": "automatic_execution",
        "id": ident,
        "decision": decision,
        "executed": executed,
        "detail": detail,
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    store.emit(**payload)
    return updated


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload).encode()
        elif isinstance(payload, str):
            body = payload.encode()
        else:
            body = payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size) if size else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(raw.decode(errors="replace"))
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        return data

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            self._send(200, {"status": "healthy"})
            return
        if self.path.startswith("/live/demo"):
            status, body, content_type = console.proxy_demo(self.path)
            self._send(status, body, content_type)
            return
        handled = console.handle_get(self.path, CFG)
        if handled:
            self._send(*handled)
            return
        if path == "/recommendations":
            latest = store.latest()
            if not latest:
                self._send(404, {"error": "no analysis yet"})
                return
            self._send(200, latest)
            return
        if path == "/recommendations.txt":
            latest = store.latest()
            if not latest:
                self._send(404, "no analysis yet", "text/plain; charset=utf-8")
                return
            self._send(200, latest.get("lecture_text") or "", "text/plain; charset=utf-8")
            return
        if path == "/analyses":
            self._send(200, {"ids": list(store.STORE.keys()), "latest": store.LATEST})
            return
        if path.startswith("/analyses/"):
            ident = path.split("/", 2)[-1]
            item = store.get(ident)
            if not item:
                self._send(404, {"error": "not found"})
                return
            self._send(200, item)
            return
        static = console.static_file(self.path)
        if static:
            self._send(*static)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            payload = self._read_json()
        except ValueError as exc:
            print(json.dumps({"event": "invalid_payload", "raw": str(exc)}), flush=True)
            self._send(400, {"error": "invalid json"})
            return
        handled = console.handle_post(self.path, payload, CFG)
        if handled:
            self._send(*handled)
            return
        if path == "/alerts":
            print(json.dumps({"event": "alert_received"}), flush=True)
            store.emit("alert_received")
            results = analyze_payload(payload, CFG)
            applied = [apply_recommendation(item) for item in results]
            for item in applied:
                store.emit(
                    "recommendation_score",
                    id=item.get("id"),
                    recommended_action=item.get("recommended_action"),
                    scoring_source=item.get("scoring_source"),
                )
            self._send(
                200,
                {"status": "received", "analyses": [item.get("id") for item in applied]},
            )
            return
        self._send(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "event": "started",
                "automatic_execution_allowed": CFG["automatic_execution_allowed"],
            }
        ),
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Handler).serve_forever()
