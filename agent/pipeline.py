from __future__ import annotations

from typing import Any

from enrichment.context import enrich
from enrichment.normalize import incident_type_for, normalize_alertmanager
from hypotheses.generate import generate as generate_hypotheses
from recommendations.format import (
    lecture_text,
    markdown,
    ordered_recommendations,
    recommended_action,
)
from recommendations.store import analysis_id, save
from scoring.engine import (
    apply_llm_delta,
    apply_weights,
    clip_and_normalize,
    conflicting_from_signals,
    score_quality,
)
from scoring.llm import interpret
from scoring.signals import derive_signals


def analyze_alert(alert: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    context = enrich(alert, settings)
    incident_type = incident_type_for(
        alert.get("alert_name", ""),
        context.get("last_termination_reason"),
    )
    if incident_type == "unknown":
        incident_type = alert.get("incident_type") or "unknown"
    signals = derive_signals(incident_type, context)
    raw_scores = apply_weights(signals, settings["weights"])
    scores = clip_and_normalize(raw_scores)
    missing = context.get("missing_evidence") or []
    conflicting = conflicting_from_signals(signals)
    hypotheses = generate_hypotheses(incident_type, context, signals)
    recommendations = ordered_recommendations(scores, signals)
    analysis = {
        "id": analysis_id(incident_type, context.get("deployment") or "demo-app"),
        "incident_type": incident_type,
        "alert": alert,
        "summary": _summary(incident_type, context),
        "evidence": context,
        "signals": signals,
        "hypotheses": hypotheses,
        "recommendations": recommendations,
        "recommended_action": recommended_action(scores, context.get("recent_deployment")),
        "automatic_execution_allowed": False,
        "score_quality": score_quality(missing, conflicting),
        "missing_evidence": missing,
        "conflicting_evidence": conflicting,
        "llm": {"used": False},
        "note": "recommendation_score values are a prioritization based on available evidence, not mathematical certainty.",
    }
    llm = interpret(analysis, settings)
    analysis["llm"] = llm
    if llm.get("used"):
        adjusted = apply_llm_delta(scores, llm.get("adjustments"), settings["llm_max_adjustment"])
        scores = clip_and_normalize(adjusted)
        analysis["recommendations"] = ordered_recommendations(scores, signals)
        analysis["recommended_action"] = recommended_action(scores, context.get("recent_deployment"))
    analysis["lecture_text"] = lecture_text(analysis)
    analysis["markdown"] = markdown(analysis)
    return save(analysis)


def analyze_payload(payload: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = normalize_alertmanager(payload)
    return [analyze_alert(alert, settings) for alert in alerts]


def _summary(incident_type: str, context: dict[str, Any]) -> str:
    minutes = context.get("minutes_since_deployment")
    if incident_type == "oom" and context.get("recent_deployment"):
        return f"Container finished by memory after a recorded rollout {minutes} minutes ago"
    if incident_type == "oom":
        return "Container finished by memory without a recent recorded application change"
    if incident_type == "crashloop" and context.get("recent_deployment"):
        return f"CrashLoopBackOff started after a recorded rollout {minutes} minutes ago"
    if incident_type == "crashloop":
        return "CrashLoopBackOff without a recent recorded deploy"
    if incident_type == "http500" and context.get("recent_deployment"):
        return "HTTP 500 logs after a recorded rollout while health probes can stay green"
    if incident_type == "http500":
        return "HTTP 500 logs without a recent recorded deploy"
    return "Incident received with limited classified evidence"
