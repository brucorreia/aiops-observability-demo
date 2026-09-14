from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from config import load_scoring_config, settings as load_settings
from enrichment.context import enrich
from pipeline import analyze_alert, analyze_payload
from recommendations import execute as execute_mod
from recommendations import store

CFG = load_settings(load_scoring_config())
LAST_ALERT: dict[str, Any] | None = None


def infer_live_alert() -> dict[str, Any]:
    probe = {
        "alert_name": "LiveInspection",
        "incident_type": "unknown",
        "namespace": CFG["demo_namespace"],
        "pod": "",
        "container": "demo-app",
        "severity": "critical",
        "signal": "kubernetes",
        "starts_at": "",
    }
    context = enrich(probe, CFG)
    reason = context.get("last_termination_reason")
    http_500 = context.get("http_500_count") or 0
    if reason == "OOMKilled" or (context.get("memory_usage_ratio") or 0) >= 0.9:
        probe["alert_name"] = "ContainerOOMKilled"
        probe["incident_type"] = "oom"
    elif reason in {"CrashLoopBackOff", "Error"} or (context.get("restarts") or 0) >= 3 and (context.get("pods_ready") or 0) == 0:
        probe["alert_name"] = "ContainerCrashLoopBackOff"
        probe["incident_type"] = "crashloop"
    elif http_500 >= 5:
        probe["alert_name"] = "HighHttp5xxFromLogs"
        probe["incident_type"] = "http500"
        probe["signal"] = "logs"
    return probe


def run_analysis(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global LAST_ALERT
    if payload and payload.get("alerts"):
        results = analyze_payload(payload, CFG)
        if results:
            LAST_ALERT = results[0].get("alert")
            return results[0]
    alert = payload if payload and payload.get("alert_name") else LAST_ALERT or infer_live_alert()
    LAST_ALERT = alert
    return analyze_alert(alert, CFG)


class Handler(BaseHTTPRequestHandler):
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

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            self._send(200, {"status": "healthy"})
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
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            payload = self._read_json()
        except ValueError as exc:
            print(json.dumps({"event": "invalid_payload", "raw": str(exc)}), flush=True)
            self._send(400, {"error": "invalid json"})
            return
        if path == "/alerts":
            print(json.dumps({"event": "alert_received", "payload": payload}), flush=True)
            results = analyze_payload(payload, CFG)
            if results:
                global LAST_ALERT
                LAST_ALERT = results[0].get("alert")
                print(results[0].get("lecture_text"), flush=True)
            self._send(200, {"status": "received", "analyses": [item["id"] for item in results]})
            return
        if path == "/analyze":
            analysis = run_analysis(payload or None)
            print(analysis.get("lecture_text"), flush=True)
            self._send(200, analysis)
            return
        if path == "/approvals":
            latest = store.latest()
            ident = payload.get("analysis_id") or (latest or {}).get("id")
            if not ident or not store.get(ident):
                self._send(404, {"error": "no analysis to approve"})
                return
            decision = payload.get("decision")
            analysis = store.get(ident)
            try:
                executed, detail = execute_mod.execute(decision, analysis)
            except Exception as exc:  # noqa: BLE001 - surface execution errors to the operator
                self._send(400, {"error": str(exc)})
                return
            updated = store.record_decision(ident, decision, executed, detail)
            self._send(200, {"status": "recorded", "executed": executed, "detail": detail, "analysis": updated})
            return
        self._send(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    print(json.dumps({"event": "started", "automatic_execution_allowed": CFG["automatic_execution_allowed"]}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
