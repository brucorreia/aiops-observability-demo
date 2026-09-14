from __future__ import annotations

from typing import Any

from config import ACTIONS

ACTION_LABELS = {
    "rollback": "Rollback",
    "vertical_scale": "Escala vertical",
    "horizontal_scale": "Escala horizontal",
    "investigate": "Investigar",
    "none": "Nenhuma ação automática",
}

INCIDENT_LABELS = {
    "oom": "OOMKilled",
    "crashloop": "CrashLoopBackOff",
    "http500": "HTTP 500",
    "unknown": "Unknown",
}

REASON_TEMPLATES = {
    "recent_deployment": "A recorded Deployment revision changed inside the configured window",
    "no_recent_deployment": "No recent Deployment revision was recorded; a new pod is not treated as a deploy",
    "previous_revision_healthy": "The previous revision did not show this failure mode",
    "failures_started_after_deployment": "Symptoms started after the recorded rollout",
    "memory_limit_reached": "The container reached or crossed the configured memory limit",
    "sustained_memory_growth": "Memory grew continuously inside the process, which looks like a leak",
    "traffic_growth": "Request volume increased",
    "multiple_replicas_affected": "More than one replica is affected",
    "external_dependency_errors": "Logs mention timeout, upstream, or connection failures",
    "crashloop_after_deployment": "CrashLoopBackOff started after the recorded rollout",
    "crashloop_without_recent_deployment": "CrashLoopBackOff is present without a recent recorded deploy",
    "http_500_after_deployment": "HTTP 500 logs started after the recorded rollout while probes can stay green",
    "http_500_without_recent_deployment": "HTTP 500 logs are present without a recent recorded deploy",
    "oom_without_recent_deployment": "OOM happened without a recent recorded application change",
    "pods_ready_with_http_500": "Pods remain Ready while /api logs show HTTP 500",
    "cpu_saturation_with_traffic": "CPU saturation arrived together with higher traffic",
    "single_process_memory_failure": "The memory failure is inside a single process; extra replicas may copy the leak",
    "weak_evidence": "Key metrics, logs, or deploy metadata are missing, so automatic change is risky",
}


def reasons_for(action: str, signals: dict[str, bool]) -> list[str]:
    selected = []
    for name, active in signals.items():
        if not active:
            continue
        template = REASON_TEMPLATES.get(name)
        if not template:
            continue
        if action == "rollback" and name in {
            "recent_deployment",
            "previous_revision_healthy",
            "failures_started_after_deployment",
            "crashloop_after_deployment",
            "http_500_after_deployment",
            "multiple_replicas_affected",
            "sustained_memory_growth",
            "pods_ready_with_http_500",
        }:
            selected.append(template)
        elif action == "vertical_scale" and name in {
            "memory_limit_reached",
            "oom_without_recent_deployment",
            "no_recent_deployment",
            "sustained_memory_growth",
        }:
            selected.append(template)
        elif action == "horizontal_scale" and name in {
            "traffic_growth",
            "cpu_saturation_with_traffic",
        }:
            selected.append(template)
        elif action == "horizontal_scale" and name == "single_process_memory_failure":
            selected.append(template)
        elif action == "investigate" and name in {
            "external_dependency_errors",
            "no_recent_deployment",
            "crashloop_without_recent_deployment",
            "http_500_without_recent_deployment",
            "oom_without_recent_deployment",
            "weak_evidence",
        }:
            selected.append(template)
        elif action == "none" and name in {"weak_evidence", "crashloop_without_recent_deployment"}:
            selected.append(template)
    return selected


def recommended_action(scores: dict[str, int], recent: bool | None) -> str:
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_score = ranked[0][1]
    tied = [action for action, score in ranked if score == top_score]
    if len(tied) == 1:
        return tied[0]
    if recent and "rollback" in tied:
        return "rollback"
    if "investigate" in tied:
        return "investigate"
    if "none" in tied:
        return "none"
    return tied[0]


def lecture_text(analysis: dict[str, Any]) -> str:
    evidence = analysis.get("evidence") or {}
    llm = analysis.get("llm") or {}
    lines = [
        f"INCIDENTE: {INCIDENT_LABELS.get(analysis.get('incident_type'), analysis.get('incident_type'))}",
        f"WORKLOAD: {evidence.get('deployment') or 'demo-app'}",
        f"VERSÃO ATUAL: {evidence.get('git_sha') or evidence.get('current_image') or 'unknown'}",
        f"DEPLOY REALIZADO HÁ: {evidence.get('minutes_since_deployment', 'unknown')} minutos",
        f"SCORE: {analysis.get('scoring_source') or 'llm'}",
        "",
        "EVIDÊNCIAS:",
    ]
    if llm.get("used") and llm.get("summary"):
        lines.append(f"- {llm['summary']}")
    for rec in analysis.get("recommendations") or []:
        if rec.get("action") != analysis.get("recommended_action"):
            continue
        for reason in rec.get("reasons") or []:
            lines.append(f"- {reason}")
    commits = evidence.get("recent_commits") or []
    if commits:
        lines.append("- Commits recentes:")
        for item in commits[:5]:
            lines.append(f"  - {item.get('sha')}: {item.get('message')}")
    compare = evidence.get("commit_compare") or {}
    if compare.get("status") == "ok" and compare.get("files"):
        files = ", ".join(str(item.get("filename")) for item in compare["files"][:8])
        lines.append(f"- Diff {compare.get('base')}...{compare.get('head')}: {files}")
    if analysis.get("missing_evidence"):
        for item in analysis["missing_evidence"]:
            lines.append(f"- Evidência indisponível: {item.get('evidence')}")
    lines.append("")
    lines.append("RECOMENDAÇÕES:")
    for index, rec in enumerate(analysis.get("recommendations") or [], start=1):
        label = ACTION_LABELS.get(rec["action"], rec["action"])
        lines.append(f"{index}. {label:<20} {rec['recommendation_score']}%")
    lines.append("")
    lines.append(f"AÇÃO RECOMENDADA: {analysis.get('recommended_action')}")
    allowed = analysis.get("automatic_execution_allowed")
    lines.append(f"EXECUÇÃO AUTOMÁTICA: {'habilitada' if allowed else 'desabilitada'}")
    lines.append("")
    lines.append(
        "Os valores são recommendation_score: uma priorização a partir das evidências disponíveis, não certeza matemática."
    )
    return "\n".join(lines)


def markdown(analysis: dict[str, Any]) -> str:
    return "# Incident analysis\n\n```text\n" + lecture_text(analysis) + "\n```\n"


def ordered_recommendations(
    scores: dict[str, int],
    signals: dict[str, bool],
    llm_reasons: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    items = []
    for action, value in sorted(scores.items(), key=lambda item: (-item[1], ACTIONS.index(item[0]))):
        cited = [str(item) for item in (llm_reasons or {}).get(action) or [] if str(item).strip()]
        items.append(
            {
                "action": action,
                "recommendation_score": value,
                "reasons": cited or reasons_for(action, signals),
            }
        )
    return items
