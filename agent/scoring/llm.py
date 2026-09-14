from __future__ import annotations

import json
import re
from typing import Any

from collectors.http import HttpError, request
from config import ACTIONS
from scoring.engine import clip_and_normalize


PROMPT = """You are the only scorer in this AIOps loop. There is no deterministic score to adjust.
You receive collected evidence plus optional playbook_hints (SRE notes, not answers).
Assign recommendation_score values that sum to 100 for these actions:
- rollback: revert the current Deployment revision
- vertical_scale: raise memory/CPU limits
- horizontal_scale: add replicas
- investigate: gather more evidence before changing the workload
- none: do not change the cluster

Rules:
- You produce the scores. Do not copy playbook_hints as if they were already scored.
- Do not invent metrics, deploys, logs, commits, files, revisions, or termination reasons.
- If evidence is marked unavailable, treat it as unknown. Do not assume it exists.
- A new pod is not a deploy. Use recorded Deployment revision, image tag, git SHA, and commit compare.
- CrashLoopBackOff and OOMKilled are cluster facts (waiting/terminated reason, restart count, kube events, memory limit vs working set). Do not expect application logs for those incidents.
- HTTP 500 is a log signal: pods can stay Ready while /api stdout shows status 500.
- Prefer rollback when failures started after a commit/rollout that changed the failing app (especially apps/demo-app).
- Prefer vertical_scale for OOM without a recent app change, or when memory hits the limit without a leak-vs-traffic story that needs more replicas.
- Prefer horizontal_scale only when traffic/CPU evidence supports load, not a single-process leak or crash.
- Prefer investigate when logs point to upstream/timeout/DNS, when commits do not touch the failing app, or when evidence is weak.
- Cite Kubernetes reasons/events/restarts for crashloop and oom. Cite log lines for HTTP 500. Cite commit SHAs/files when a deploy is involved.
- Write summary and reasons in Portuguese.

Return JSON only:
{{
  "summary": "one sentence",
  "scores": {{"rollback": 0, "vertical_scale": 0, "horizontal_scale": 0, "investigate": 0, "none": 0}},
  "reasons": {{
    "rollback": ["..."],
    "vertical_scale": ["..."],
    "horizontal_scale": ["..."],
    "investigate": ["..."],
    "none": ["..."]
  }},
  "cited_commits": ["abc1234"],
  "cited_logs": ["optional log snippet for HTTP 500 only"],
  "notes": []
}}
"""


def interpret(
    analysis: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    if not settings.get("openai_api_key"):
        return {"used": False, "source": "skipped", "notes": ["LLM layer skipped: no API key"]}

    evidence = analysis.get("evidence") or {}
    payload = {
        "incident_type": analysis.get("incident_type"),
        "alert": analysis.get("alert"),
        "playbook_hints": settings.get("weights") or {},
        "kubernetes": {
            "deployment": evidence.get("deployment"),
            "namespace": evidence.get("namespace"),
            "current_revision": evidence.get("current_revision"),
            "previous_revision": evidence.get("previous_revision"),
            "current_image": evidence.get("current_image"),
            "previous_image": evidence.get("previous_image"),
            "git_sha": evidence.get("git_sha"),
            "recent_deployment": evidence.get("recent_deployment"),
            "minutes_since_deployment": evidence.get("minutes_since_deployment"),
            "last_termination_reason": evidence.get("last_termination_reason"),
            "restarts": evidence.get("restarts"),
            "pods_ready": evidence.get("pods_ready"),
            "replicas": evidence.get("replicas"),
            "affected_pods": evidence.get("affected_pods"),
            "memory_limit_bytes": evidence.get("memory_limit_bytes"),
            "memory_peak_bytes": evidence.get("memory_peak_bytes"),
            "memory_usage_ratio": evidence.get("memory_usage_ratio"),
            "sustained_memory_growth": evidence.get("sustained_memory_growth"),
            "cpu_saturation": evidence.get("cpu_saturation"),
            "events": evidence.get("events") or [],
        },
        "logs": {
            "http_500_count": evidence.get("http_500_count"),
            "event_counts": evidence.get("log_event_counts") or {},
            "external_dependency_errors": evidence.get("external_dependency_errors"),
            "entries": evidence.get("log_entries") or [],
        },
        "commits": {
            "recent_commits": evidence.get("recent_commits") or [],
            "compare": evidence.get("commit_compare"),
            "code_changed_in_demo_app": evidence.get("code_changed_in_demo_app"),
        },
        "missing_evidence": analysis.get("missing_evidence") or evidence.get("missing_evidence") or [],
        "signals": analysis.get("signals"),
        "hypotheses": [
            {"id": item.get("id"), "supported": item.get("supported")}
            for item in analysis.get("hypotheses") or []
        ],
    }
    body = json.dumps(
        {
            "model": settings["openai_model"],
            "temperature": 0,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": json.dumps(payload, default=str)},
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
            timeout=float(settings.get("llm_timeout_seconds") or 45),
        )
    except HttpError as exc:
        return {"used": False, "source": "error", "notes": [f"LLM unavailable: {exc}"]}

    try:
        envelope = json.loads(raw.decode())
        content = envelope["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError):
        return {"used": False, "source": "error", "notes": ["LLM returned unusable JSON"]}

    raw_scores = parsed.get("scores") or {}
    scores = {action: float(raw_scores.get(action, 0) or 0) for action in ACTIONS}
    if sum(scores.values()) <= 0:
        return {"used": False, "source": "error", "scores": {}, "notes": ["LLM returned empty scores"]}
    normalized = clip_and_normalize(scores)
    reasons = parsed.get("reasons") or {}
    clean_reasons = {
        action: [str(item) for item in (reasons.get(action) or []) if str(item).strip()][:5]
        for action in ACTIONS
    }
    return {
        "used": True,
        "source": "primary",
        "model": settings["openai_model"],
        "scores": normalized,
        "reasons": clean_reasons,
        "summary": parsed.get("summary") or "",
        "cited_commits": parsed.get("cited_commits") or [],
        "cited_logs": parsed.get("cited_logs") or [],
        "notes": parsed.get("notes") or [],
    }


def _extract_json(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in LLM content")
    return json.loads(stripped[start : end + 1])
