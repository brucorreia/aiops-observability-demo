from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ALERT_TYPES = {
    "ContainerOOMKilled": "oom",
    "ContainerMemoryUsageHigh": "oom",
    "ContainerCrashLoopBackOff": "crashloop",
    "HighHttp5xxFromLogs": "http500",
}

SIGNAL_BY_TYPE = {
    "oom": "kubernetes",
    "crashloop": "kubernetes",
    "http500": "logs",
}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def incident_type_for(alert_name: str, last_termination_reason: str | None = None) -> str:
    mapped = ALERT_TYPES.get(alert_name, "unknown")
    if mapped == "crashloop" and last_termination_reason == "OOMKilled":
        return "oom"
    return mapped


def normalize_alertmanager(payload: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for item in payload.get("alerts") or []:
        if item.get("status") == "resolved":
            continue
        labels = item.get("labels") or {}
        alert_name = labels.get("alertname") or "Unknown"
        incident_type = incident_type_for(alert_name)
        alerts.append(
            {
                "alert_name": alert_name,
                "incident_type": incident_type,
                "namespace": labels.get("namespace") or "aiops-demo",
                "pod": labels.get("pod") or labels.get("kubernetes_pod_name") or "",
                "container": labels.get("container") or "demo-app",
                "severity": labels.get("severity") or "critical",
                "signal": SIGNAL_BY_TYPE.get(incident_type, "kubernetes"),
                "starts_at": item.get("startsAt") or "",
                "raw_labels": labels,
                "raw_annotations": item.get("annotations") or {},
            }
        )
    return alerts
