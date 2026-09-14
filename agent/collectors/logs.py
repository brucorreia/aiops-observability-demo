from __future__ import annotations

import json
from typing import Any

from collectors.http import HttpError, post_form, request


def query_logs(base_url: str, expr: str, limit: int = 50) -> dict[str, Any]:
    url = f"{base_url}/select/logsql/query"
    try:
        raw = post_form(url, {"query": expr, "limit": str(limit)}, timeout=8.0)
    except HttpError as exc:
        return {"status": "unavailable", "error": str(exc), "logs": []}
    logs: list[dict[str, Any]] = []
    for line in raw.decode(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            logs.append({"_msg": line})
    return {"status": "ok", "logs": logs}


def stats_query(base_url: str, expr: str) -> dict[str, Any]:
    url = f"{base_url}/select/logsql/stats_query"
    try:
        _, raw = request(
            url,
            method="POST",
            body=f"query={expr}".encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=8.0,
        )
    except HttpError as exc:
        return {"status": "unavailable", "error": str(exc), "result": []}
    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError:
        return {"status": "unavailable", "error": "invalid stats_query payload", "result": []}
    if payload.get("status") != "success":
        return {
            "status": "unavailable",
            "error": payload.get("error", "victoriaLogs stats query failed"),
            "result": [],
        }
    return {"status": "ok", "result": ((payload.get("data") or {}).get("result") or [])}
