from __future__ import annotations

from typing import Any


ACTION_DECISIONS = {
    "rollback": "approve_rollback",
    "vertical_scale": "approve_vertical_scale",
    "horizontal_scale": "approve_horizontal_scale",
}


def automatic_decision(analysis: dict[str, Any]) -> str | None:
    if not analysis.get("automatic_execution_allowed"):
        return None
    if analysis.get("scoring_source") != "llm":
        return None
    return ACTION_DECISIONS.get(analysis.get("recommended_action"))


def execute(decision: str, analysis: dict[str, Any], cfg: dict[str, Any] | None = None) -> tuple[bool, str]:
    if not cfg:
        raise RuntimeError("GitOps config required; cluster patches are disabled")
    from api.console import apply_remediation

    return apply_remediation(cfg, decision, analysis)
