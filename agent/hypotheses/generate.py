from __future__ import annotations

from typing import Any

HYPOTHESES = {
    "regression_current_version": "Regression introduced by the current version",
    "memory_leak": "Memory leak inside the process",
    "inadequate_memory_limit": "Memory limit is too low for a legitimate workload",
    "legitimate_load_increase": "Legitimate traffic increase",
    "external_dependency_failure": "External dependency failure",
    "invalid_configuration": "Invalid configuration",
    "infrastructure_issue": "Infrastructure or node problem",
}


def generate(incident_type: str, context: dict[str, Any], signals: dict[str, bool]) -> list[dict[str, Any]]:
    supported = {
        "regression_current_version": bool(
            signals.get("recent_deployment")
            and (
                signals.get("failures_started_after_deployment")
                or signals.get("crashloop_after_deployment")
                or signals.get("http_500_after_deployment")
            )
        ),
        "memory_leak": bool(
            incident_type == "oom" and signals.get("sustained_memory_growth")
        ),
        "inadequate_memory_limit": bool(
            incident_type == "oom"
            and signals.get("memory_limit_reached")
            and not signals.get("recent_deployment")
            and not signals.get("sustained_memory_growth")
        ),
        "legitimate_load_increase": bool(
            signals.get("traffic_growth") and not signals.get("sustained_memory_growth")
        ),
        "external_dependency_failure": bool(signals.get("external_dependency_errors")),
        "invalid_configuration": bool(
            incident_type == "crashloop" and not signals.get("recent_deployment")
        ),
        "infrastructure_issue": bool(
            not signals.get("recent_deployment")
            and incident_type == "crashloop"
            and not context.get("related_log_messages")
        ),
    }
    hypotheses = []
    for key, title in HYPOTHESES.items():
        reasons = []
        if key == "regression_current_version" and supported[key]:
            reasons.append("Failures line up with a recorded Deployment revision, not just a new pod")
        if key == "memory_leak" and supported[key]:
            reasons.append("Memory grew continuously inside the same process")
        if key == "inadequate_memory_limit" and supported[key]:
            reasons.append("The container reached its configured limit without a recent application change")
        if key == "legitimate_load_increase" and supported[key]:
            reasons.append("Request volume increased while per-process memory did not trend like a leak")
        if key == "external_dependency_failure" and supported[key]:
            reasons.append("Logs mention timeout, upstream, or connection errors")
        if key == "invalid_configuration" and supported[key]:
            reasons.append("The process exits during startup without a recent recorded deploy")
        if key == "infrastructure_issue" and supported[key]:
            reasons.append("No application-level evidence was available beyond Kubernetes restart state")
        hypotheses.append(
            {
                "id": key,
                "title": title,
                "supported": supported[key],
                "reasons": reasons,
            }
        )
    return hypotheses
