from __future__ import annotations

import urllib.parse
from typing import Any

from collectors.http import HttpError, get_json


def query(base_url: str, expr: str) -> dict[str, Any]:
    url = f"{base_url}/api/v1/query?{urllib.parse.urlencode({'query': expr})}"
    try:
        payload = get_json(url, timeout=8.0)
    except HttpError as exc:
        return {"status": "unavailable", "error": str(exc), "result": []}
    if not payload or payload.get("status") != "success":
        return {
            "status": "unavailable",
            "error": (payload or {}).get("error", "victoriaMetrics query failed"),
            "result": [],
        }
    return {"status": "ok", "result": ((payload.get("data") or {}).get("result") or [])}


def query_range(base_url: str, expr: str, start: float, end: float, step: str = "15s") -> dict[str, Any]:
    params = {"query": expr, "start": start, "end": end, "step": step}
    url = f"{base_url}/api/v1/query_range?{urllib.parse.urlencode(params)}"
    try:
        payload = get_json(url, timeout=8.0)
    except HttpError as exc:
        return {"status": "unavailable", "error": str(exc), "result": []}
    if not payload or payload.get("status") != "success":
        return {
            "status": "unavailable",
            "error": (payload or {}).get("error", "victoriaMetrics range query failed"),
            "result": [],
        }
    return {"status": "ok", "result": ((payload.get("data") or {}).get("result") or [])}


def first_value(result: list[dict[str, Any]]) -> float | None:
    if not result:
        return None
    value = result[0].get("value")
    if not value or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None
