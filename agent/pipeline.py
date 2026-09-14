from __future__ import annotations

import json
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
    conflicting_from_signals,
    llm_unavailable_scores,
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
    missing = context.get("missing_evidence") or []
    conflicting = conflicting_from_signals(signals)
    hypotheses = generate_hypotheses(incident_type, context, signals)
    analysis = {
        "id": analysis_id(incident_type, context.get("deployment") or "demo-app"),
        "incident_type": incident_type,
        "alert": alert,
        "summary": _summary(incident_type, context),
        "evidence": context,
        "signals": signals,
        "hypotheses": hypotheses,
        "recommendations": [],
        "recommended_action": "investigate",
        "automatic_execution_allowed": settings.get("automatic_execution_allowed", True),
        "score_quality": score_quality(missing, conflicting),
        "missing_evidence": missing,
        "conflicting_evidence": conflicting,
        "llm": {"used": False},
        "scoring_source": "llm",
        "note": "recommendation_score is produced only by the LLM from collected evidence, not by YAML weights.",
    }
    llm = interpret(analysis, settings)
    analysis["llm"] = llm
    if llm.get("used") and llm.get("scores"):
        scores = llm["scores"]
        analysis["scoring_source"] = "llm"
        if llm.get("summary"):
            analysis["summary"] = llm["summary"]
        analysis["recommendations"] = ordered_recommendations(
            scores, signals, llm.get("reasons")
        )
        analysis["recommended_action"] = recommended_action(scores, context.get("recent_deployment"))
    else:
        scores = llm_unavailable_scores()
        note = "; ".join(llm.get("notes") or ["LLM unavailable"])
        analysis["scoring_source"] = "llm_unavailable"
        analysis["summary"] = "IA indisponível; nenhuma mudança de cluster foi pontuada"
        analysis["recommendations"] = ordered_recommendations(
            scores,
            signals,
            {
                "investigate": [note, "O score deste agente é gerado somente por IA."],
                "none": ["Sem análise de IA, não há rollback nem escala automáticos."],
            },
        )
        analysis["recommended_action"] = "investigate"
        analysis["score_quality"] = "low"
    analysis["lecture_text"] = lecture_text(analysis)
    analysis["markdown"] = markdown(analysis)
    saved = save(analysis)
    log_score(saved)
    return saved


def analyze_payload(payload: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = normalize_alertmanager(payload)
    return [analyze_alert(alert, settings) for alert in alerts]


def log_score(analysis: dict[str, Any]) -> None:
    scores = {
        item["action"]: item["recommendation_score"]
        for item in analysis.get("recommendations") or []
    }
    print(
        json.dumps(
            {
                "event": "recommendation_score",
                "id": analysis.get("id"),
                "incident_type": analysis.get("incident_type"),
                "scoring_source": analysis.get("scoring_source"),
                "recommended_action": analysis.get("recommended_action"),
                "scores": scores,
                "summary": analysis.get("summary"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    text = analysis.get("lecture_text")
    if text:
        print(text, flush=True)


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
