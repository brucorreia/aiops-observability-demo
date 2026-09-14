from __future__ import annotations

import json
from typing import Any

from collectors.http import HttpError, request
from config import ACTIONS


PROMPT = """You are an AIOps analyst. You receive collected evidence and deterministic recommendation_score values.
These scores are a prioritization from available evidence, not mathematical certainty.
You may adjust each action by at most {max_adjustment} points.
You must not invent metrics, deploys, logs, revisions, or termination reasons.
If evidence is marked unavailable, leave it unavailable.
Return JSON only:
{{"adjustments": {{"rollback": 0, "vertical_scale": 0, "horizontal_scale": 0, "investigate": 0, "none": 0}}, "notes": []}}
"""


def interpret(
    analysis: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    if not settings.get("openai_api_key"):
        return {"used": False, "adjustments": {}, "notes": ["LLM layer skipped: no API key"]}

    body = json.dumps(
        {
            "model": settings["openai_model"],
            "temperature": 0,
            "messages": [
                {"role": "system", "content": PROMPT.format(max_adjustment=settings["llm_max_adjustment"])},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "incident_type": analysis.get("incident_type"),
                            "evidence": analysis.get("evidence"),
                            "missing_evidence": analysis.get("missing_evidence"),
                            "signals": analysis.get("signals"),
                            "deterministic_scores": {
                                item["action"]: item["recommendation_score"]
                                for item in analysis.get("recommendations", [])
                            },
                        }
                    ),
                },
            ],
        }
    ).encode()
    try:
        _, raw = request(
            f"{settings['openai_base_url']}/chat/completions",
            method="POST",
            body=body,
            headers={
                "Authorization": f"Bearer {settings['openai_api_key']}",
                "Content-Type": "application/json",
            },
            timeout=20.0,
        )
    except HttpError as exc:
        return {"used": False, "adjustments": {}, "notes": [f"LLM unavailable: {exc}"]}

    try:
        payload = json.loads(raw.decode())
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        return {"used": False, "adjustments": {}, "notes": ["LLM returned unusable JSON"]}

    adjustments = parsed.get("adjustments") or {}
    clean = {action: int(adjustments.get(action, 0) or 0) for action in ACTIONS}
    return {"used": True, "adjustments": clean, "notes": parsed.get("notes") or []}
