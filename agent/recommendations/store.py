from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE: dict[str, dict[str, Any]] = {}
LATEST: str | None = None
EVENTS: list[dict[str, Any]] = []
ROLLOUT: dict[str, Any] | None = None
DATA_DIR = Path("/tmp/aiops-incidents")
MAX_EVENTS = 80
_HYDRATED = False


def analysis_id(incident_type: str, workload: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{incident_type}-{workload}"


def save(analysis: dict[str, Any]) -> dict[str, Any]:
    global LATEST
    ident = analysis.get("id") or analysis_id(
        analysis.get("incident_type") or "unknown",
        ((analysis.get("evidence") or {}).get("deployment") or "demo-app"),
    )
    analysis["id"] = ident
    STORE[ident] = analysis
    LATEST = ident
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{ident}.json").write_text(json.dumps(analysis, indent=2))
    return analysis


def latest() -> dict[str, Any] | None:
    if not LATEST:
        _hydrate()
    if LATEST:
        return STORE.get(LATEST)
    return None


def get(ident: str) -> dict[str, Any] | None:
    if ident not in STORE:
        _hydrate()
    return STORE.get(ident)


def _hydrate() -> None:
    global LATEST, _HYDRATED
    if _HYDRATED:
        return
    _HYDRATED = True
    if LATEST or not DATA_DIR.exists():
        return
    files = sorted(DATA_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime)
    for path in files:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        ident = str(data.get("id") or path.stem)
        data["id"] = ident
        STORE[ident] = data
        LATEST = ident


def emit(event: str, **fields: Any) -> dict[str, Any]:
    item = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        **fields,
    }
    EVENTS.append(item)
    if len(EVENTS) > MAX_EVENTS:
        del EVENTS[: len(EVENTS) - MAX_EVENTS]
    return item


def events(limit: int = 40) -> list[dict[str, Any]]:
    return EVENTS[-limit:]


def set_rollout(payload: dict[str, Any]) -> dict[str, Any]:
    global ROLLOUT
    ROLLOUT = payload
    return payload


def rollout() -> dict[str, Any] | None:
    return ROLLOUT


def record_decision(ident: str, decision: str, executed: bool, detail: str) -> dict[str, Any]:
    analysis = STORE.get(ident)
    if not analysis:
        raise KeyError(ident)
    analysis.setdefault("approvals", []).append(
        {
            "decision": decision,
            "executed": executed,
            "detail": detail,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    save(analysis)
    return analysis
