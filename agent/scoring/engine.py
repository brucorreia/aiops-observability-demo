from __future__ import annotations

from typing import Any

from config import ACTIONS


def apply_weights(signals: dict[str, bool], weights: dict[str, dict[str, float]]) -> dict[str, float]:
    scores = {action: 0.0 for action in ACTIONS}
    for name, active in signals.items():
        if not active:
            continue
        for action, delta in (weights.get(name) or {}).items():
            if action in scores:
                scores[action] += float(delta)
    return scores


def clip_and_normalize(scores: dict[str, float]) -> dict[str, int]:
    clipped = {action: max(0.0, float(scores.get(action, 0.0))) for action in ACTIONS}
    total = sum(clipped.values())
    if total <= 0:
        clipped = {action: 0.0 for action in ACTIONS}
        clipped["investigate"] = 50.0
        clipped["none"] = 50.0
        total = 100.0
    scaled = {action: value / total * 100.0 for action, value in clipped.items()}
    ints = {action: int(value) for action, value in scaled.items()}
    remainder = 100 - sum(ints.values())
    for action in sorted(scaled, key=lambda key: (-scaled[key], key)):
        if remainder == 0:
            break
        ints[action] += 1
        remainder -= 1
    return ints


def apply_llm_delta(
    scores: dict[str, int],
    adjustments: dict[str, int] | None,
    max_adjustment: int,
) -> dict[str, float]:
    updated = {action: float(scores.get(action, 0)) for action in ACTIONS}
    if not adjustments:
        return updated
    for action, delta in adjustments.items():
        if action not in updated:
            continue
        bounded = max(-max_adjustment, min(max_adjustment, int(delta)))
        updated[action] = max(0.0, updated[action] + bounded)
    return updated


def score_quality(missing: list[dict[str, Any]], conflicting: list[str]) -> str:
    names = {item.get("evidence") for item in missing}
    if len(names) >= 3 or conflicting and len(names) >= 2:
        return "low"
    if names or conflicting:
        return "medium"
    return "high"


def conflicting_from_signals(signals: dict[str, bool]) -> list[str]:
    conflicts = []
    if signals.get("recent_deployment") and signals.get("external_dependency_errors"):
        conflicts.append("recent_deploy_vs_external_errors")
    if signals.get("sustained_memory_growth") and signals.get("traffic_growth"):
        conflicts.append("memory_leak_vs_traffic_growth")
    if signals.get("crashloop_after_deployment") and signals.get("memory_limit_reached"):
        conflicts.append("crashloop_vs_oom")
    return conflicts
