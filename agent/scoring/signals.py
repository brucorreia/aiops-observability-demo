from __future__ import annotations

from typing import Any


def derive_signals(incident_type: str, context: dict[str, Any]) -> dict[str, bool]:
    recent = context.get("recent_deployment")
    ready = context.get("pods_ready")
    ratio = context.get("memory_usage_ratio")
    replicas = context.get("replicas") or 1
    missing = context.get("missing_evidence") or []
    missing_names = {item.get("evidence") for item in missing}

    signals = {
        "recent_deployment": recent is True,
        "no_recent_deployment": recent is False,
        "previous_revision_healthy": context.get("previous_revision_healthy") is True,
        "failures_started_after_deployment": context.get("failures_started_after_deployment") is True,
        "memory_limit_reached": bool(
            incident_type == "oom"
            and (
                context.get("last_termination_reason") == "OOMKilled"
                or (ratio is not None and ratio >= 0.9)
            )
        ),
        "sustained_memory_growth": context.get("sustained_memory_growth") is True,
        "traffic_growth": context.get("traffic_growth") is True,
        "multiple_replicas_affected": (context.get("affected_pods") or 0) > 1 and replicas > 1,
        "external_dependency_errors": context.get("external_dependency_errors") is True,
        "crashloop_after_deployment": incident_type == "crashloop" and recent is True,
        "crashloop_without_recent_deployment": incident_type == "crashloop" and recent is False,
        "http_500_after_deployment": incident_type == "http500" and recent is True,
        "http_500_without_recent_deployment": incident_type == "http500" and recent is False,
        "oom_without_recent_deployment": incident_type == "oom" and recent is False,
        "pods_ready_with_http_500": incident_type == "http500" and (ready or 0) > 0,
        "cpu_saturation_with_traffic": bool(
            context.get("cpu_saturation") and context.get("traffic_growth")
        ),
        "single_process_memory_failure": incident_type == "oom" and replicas <= 1,
        "weak_evidence": len(missing_names) >= 3 or recent is None,
    }
    return signals
