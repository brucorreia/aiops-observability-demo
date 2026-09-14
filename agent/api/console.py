from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from collectors import github, k8s, logs, metrics
from collectors.http import HttpError, request
from config import settings as load_settings
from recommendations import execute as execute_mod
from recommendations import store
from recommendations.format import ACTION_LABELS, INCIDENT_LABELS

CONSOLE_DIR = Path(os.getenv("CONSOLE_DIR", "/app/console"))
DEMO_APP_URL = os.getenv("DEMO_APP_URL", "http://demo-app.aiops-demo.svc").rstrip("/")
ARGO_HEALTH_URL = os.getenv("ARGO_HEALTH_URL", "http://argocd-server.argocd.svc/healthz")
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "k3d-aiops")
MODE_FILE = "apps/demo-app/demo_mode"
APP_YAML = "deploy/demo-app/demo-app.yaml"
WORKFLOW_FILE = "demo-app.yaml"
MIME = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
}
INCIDENT_MESSAGES = {
    "good": "fix(demo-app): restore healthy mode",
    "crashloop": "fix(demo-app): fail startup (CrashLoopBackOff)",
    "oom": "fix(demo-app): leak memory (OOMKilled)",
    "http500": "fix(demo-app): return HTTP 500 on /api",
    "oom-stale": "fix(demo-app): leak memory with a stale deploy timestamp",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _probe(url: str) -> bool:
    try:
        request(url, timeout=2.0)
        return True
    except HttpError:
        return False


def _series_values(result: list[dict[str, Any]], limit: int = 24) -> list[float]:
    if not result:
        return []
    points = result[0].get("values") or []
    values: list[float] = []
    for point in points[-limit:]:
        if len(point) < 2:
            continue
        try:
            values.append(round(float(point[1]), 4))
        except (TypeError, ValueError):
            continue
    return values


def _pod_status(pod: dict[str, Any]) -> dict[str, Any]:
    meta = pod.get("metadata") or {}
    status = pod.get("status") or {}
    spec = pod.get("spec") or {}
    phase = status.get("phase") or "Unknown"
    reason = None
    restarts = 0
    ready = False
    image = None
    container_name = None
    for condition in status.get("conditions") or []:
        if condition.get("type") == "Ready":
            ready = condition.get("status") == "True"
    for item in status.get("containerStatuses") or []:
        container_name = item.get("name") or container_name
        restarts += int(item.get("restartCount") or 0)
        image = item.get("image") or image
        waiting = ((item.get("state") or {}).get("waiting") or {})
        terminated = ((item.get("state") or {}).get("terminated") or {})
        last = ((item.get("lastState") or {}).get("terminated") or {})
        reason = waiting.get("reason") or terminated.get("reason") or last.get("reason") or reason
    if reason == "CrashLoopBackOff":
        badge = "CrashLoopBackOff"
    elif reason == "OOMKilled":
        badge = "OOMKilled"
    elif phase == "Pending":
        badge = "Pending"
    elif ready:
        badge = "Running"
    else:
        badge = phase
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "node": spec.get("nodeName"),
        "app": ((meta.get("labels") or {}).get("app")),
        "phase": phase,
        "ready": ready,
        "status": badge,
        "reason": reason,
        "restarts": restarts,
        "image": image,
        "container": container_name,
        "created_at": meta.get("creationTimestamp"),
        "age": meta.get("creationTimestamp"),
    }


def _workload_resources(pod: dict[str, Any]) -> dict[str, Any]:
    containers = ((pod.get("spec") or {}).get("containers") or [])
    container = containers[0] if containers else {}
    resources = container.get("resources") or {}
    return {
        "requests": resources.get("requests") or {},
        "limits": resources.get("limits") or {},
    }


def cluster_status(cfg: dict[str, Any]) -> dict[str, Any]:
    namespace = cfg.get("demo_namespace") or "aiops-demo"
    now = time.time()
    k8s_ok = False
    nodes: list[dict[str, Any]] = []
    demo_pods: list[dict[str, Any]] = []
    agent_pods: list[dict[str, Any]] = []
    deployment: dict[str, Any] = {}
    error = None
    try:
        nodes = [
            {
                "name": (item.get("metadata") or {}).get("name"),
                "ready": any(
                    cond.get("type") == "Ready" and cond.get("status") == "True"
                    for cond in ((item.get("status") or {}).get("conditions") or [])
                ),
            }
            for item in k8s.list_nodes()
        ]
        demo_pods = k8s.list_namespace_pods(namespace)
        agent_pods = k8s.list_pods("monitoring", "ai-agent")
        deployment = k8s.get_deployment(namespace, "demo-app")
        k8s_ok = True
    except (HttpError, k8s.KubernetesUnavailable, TypeError, KeyError) as exc:
        error = str(exc)

    workloads = [_pod_status(item) for item in demo_pods + agent_pods]
    demo_app = [item for item in workloads if item.get("app") == "demo-app"]
    ready_demo = sum(1 for item in demo_app if item.get("ready"))
    crashing = any(item.get("status") in {"CrashLoopBackOff", "OOMKilled"} for item in demo_app)
    annotations = (deployment.get("metadata") or {}).get("annotations") or {}
    image = None
    if demo_app:
        image = demo_app[0].get("image")
    if not image:
        containers = (
            ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
        ).get("containers") or []
        if containers:
            image = containers[0].get("image")

    cpu = metrics.query(
        cfg["victoriametrics_url"],
        f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[1m]))',
    )
    mem = metrics.query(
        cfg["victoriametrics_url"],
        f'sum(container_memory_working_set_bytes{{namespace="{namespace}"}})',
    )
    restarts = metrics.query(
        cfg["victoriametrics_url"],
        f'sum(kube_pod_container_status_restarts_total{{namespace="{namespace}"}})',
    )
    cpu_range = metrics.query_range(
        cfg["victoriametrics_url"],
        f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[1m]))',
        now - 900,
        now,
        step="30s",
    )
    mem_range = metrics.query_range(
        cfg["victoriametrics_url"],
        f'sum(container_memory_working_set_bytes{{namespace="{namespace}"}})',
        now - 900,
        now,
        step="30s",
    )

    app_health = None
    app_api = None
    try:
        _, health_raw = request(DEMO_APP_URL + "/health", timeout=2.0)
        app_health = json.loads(health_raw.decode()) if health_raw else {"status": "ok"}
    except (HttpError, ValueError, json.JSONDecodeError):
        app_health = None
    try:
        _, api_raw = request(DEMO_APP_URL + "/api", timeout=2.0, raise_http_error=False)
        app_api = json.loads(api_raw.decode()) if api_raw else None
    except (HttpError, ValueError, json.JSONDecodeError):
        app_api = None

    analysis = store.latest()
    http_failing = bool(app_api and app_api.get("status") == 500)
    health = "Healthy"
    if not k8s_ok or crashing or ready_demo == 0 or http_failing:
        health = "Degraded"

    rollout = store.rollout() or {}
    if rollout.get("sha"):
        rollout["workflow"] = github.workflow_run_for_sha(
            cfg.get("github_repository") or "",
            rollout.get("sha") or "",
            WORKFLOW_FILE,
            cfg.get("github_token") or None,
            cfg.get("github_api_url") or "https://api.github.com",
        )
        short = (rollout.get("short_sha") or "")[:7]
        image_tag = (image or "").rsplit(":", 1)[-1] if image else ""
        rollout["image_synced"] = bool(short and image_tag.startswith(short))
        store.set_rollout(rollout)

    return {
        "cluster": CLUSTER_NAME,
        "environment": "Demo",
        "updated_at": utc_now(),
        "health": health,
        "error": error,
        "connections": {
            "kubernetes": k8s_ok,
            "argocd": _probe(ARGO_HEALTH_URL),
            "llm": bool(cfg.get("openai_api_key")),
            "github": bool(cfg.get("github_token")),
        },
        "nodes": {
            "ready": sum(1 for item in nodes if item.get("ready")),
            "total": len(nodes),
            "items": nodes,
        },
        "pods": {
            "running": sum(1 for item in workloads if item.get("status") == "Running"),
            "total": len(workloads),
        },
        "cpu": {
            "cores": metrics.first_value(cpu.get("result") or []),
            "sparkline": _series_values(cpu_range.get("result") or []),
        },
        "memory": {
            "bytes": metrics.first_value(mem.get("result") or []),
            "sparkline": _series_values(mem_range.get("result") or []),
        },
        "restarts": metrics.first_value(restarts.get("result") or []) or sum(
            item.get("restarts") or 0 for item in workloads
        ),
        "demo_app": {
            "ready": ready_demo,
            "total": max(len(demo_app), 1),
            "image": image,
            "git_sha": annotations.get("aiops.demo/git-sha") or github.sha_from_image(image),
            "deployed_at": annotations.get("aiops.demo/deployed-at"),
            "mode": (app_api or {}).get("version"),
            "health": app_health,
            "api": app_api,
        },
        "workloads": workloads,
        "topology": {
            "nodes": [
                {
                    **node,
                    "pods": [item for item in workloads if item.get("node") == node.get("name")],
                }
                for node in nodes
            ],
            "unscheduled": [item for item in workloads if not item.get("node")],
        },
        "rollout": rollout,
        "analysis": analysis,
        "timeline": build_timeline(rollout, analysis, health, crashing, http_failing),
    }


def build_timeline(
    rollout: dict[str, Any],
    analysis: dict[str, Any] | None,
    health: str,
    crashing: bool,
    http_failing: bool,
) -> list[dict[str, Any]]:
    workflow = (rollout or {}).get("workflow") or {}
    approvals = (analysis or {}).get("approvals") or []
    executed = any(item.get("executed") for item in approvals)
    recommended = (analysis or {}).get("recommended_action")
    steps = [
        {
            "id": "commit",
            "label": "Commit em main",
            "detail": (rollout or {}).get("short_sha") or (rollout or {}).get("message"),
            "done": bool((rollout or {}).get("sha")),
        },
        {
            "id": "build",
            "label": "Build da imagem",
            "detail": workflow.get("status"),
            "done": workflow.get("status") == "completed" and workflow.get("conclusion") == "success",
            "active": workflow.get("status") in {"queued", "in_progress"},
        },
        {
            "id": "sync",
            "label": "Argo CD sync",
            "detail": "imagem publicada no Deployment",
            "done": bool((rollout or {}).get("image_synced")),
        },
        {
            "id": "symptom",
            "label": "Sintoma no cluster",
            "detail": "CrashLoop / OOM / HTTP 500",
            "done": crashing or http_failing,
        },
        {
            "id": "score",
            "label": "Análise da IA",
            "detail": recommended,
            "done": bool(analysis and analysis.get("scoring_source") == "llm"),
        },
        {
            "id": "action",
            "label": "Ação aplicada",
            "detail": (approvals[-1].get("decision") if approvals else None),
            "done": executed,
        },
        {
            "id": "recovered",
            "label": "Serviço recuperado",
            "detail": health,
            "done": health == "Healthy" and executed,
        },
    ]
    found_active = False
    for step in steps:
        if step.get("active"):
            found_active = True
            continue
        if not step["done"] and not found_active:
            step["active"] = True
            found_active = True
        else:
            step.setdefault("active", False)
    return steps


def collect_logs(cfg: dict[str, Any], source: str = "demo-app") -> dict[str, Any]:
    namespace = cfg.get("demo_namespace") or "aiops-demo"
    if source == "ai-agent":
        try:
            pods = k8s.list_pods("monitoring", "ai-agent")
            name = ((pods[0].get("metadata") or {}).get("name") if pods else "")
            raw = k8s.pod_logs("monitoring", name, "webhook", tail=80) if name else ""
            entries = []
            for line in raw.splitlines()[-80:]:
                try:
                    payload = json.loads(line)
                    entries.append(
                        {
                            "timestamp": payload.get("at") or utc_now(),
                            "level": "error" if "fail" in str(payload.get("event")) else "info",
                            "pod": name,
                            "message": line[:400],
                            "event": payload.get("event"),
                        }
                    )
                except json.JSONDecodeError:
                    entries.append(
                        {
                            "timestamp": utc_now(),
                            "level": "info",
                            "pod": name,
                            "message": line[:400],
                        }
                    )
            return {"status": "ok", "source": source, "logs": entries[-80:]}
        except (HttpError, k8s.KubernetesUnavailable, IndexError) as exc:
            return {"status": "unavailable", "source": source, "logs": [], "error": str(exc)}

    query = (
        f'kubernetes.pod_namespace:="{namespace}" kubernetes.container_name:="demo-app" | unpack_json'
    )
    result = logs.query_logs(cfg["victorialogs_url"], query, limit=80)
    entries = []
    for item in result.get("logs") or []:
        raw = item.get("_msg")
        payload = item
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    payload = {**item, **decoded}
            except json.JSONDecodeError:
                pass
        level = str(payload.get("level") or "info").lower()
        status = payload.get("status")
        message = str(payload.get("message") or raw or "")[:400]
        if status == 500:
            level = "error"
        entries.append(
            {
                "timestamp": payload.get("timestamp") or payload.get("_time"),
                "level": level,
                "pod": item.get("kubernetes.pod_name") or "demo-app",
                "message": message,
                "status": status,
                "event": payload.get("event"),
            }
        )
    if result.get("status") != "ok" or not entries:
        try:
            pods = k8s.list_pods(namespace, "demo-app")
            name = ((pods[0].get("metadata") or {}).get("name") if pods else "")
            raw = k8s.pod_logs(namespace, name, "demo-app", tail=80) if name else ""
            for line in raw.splitlines()[-80:]:
                try:
                    payload = json.loads(line)
                    entries.append(
                        {
                            "timestamp": payload.get("timestamp"),
                            "level": payload.get("level") or "info",
                            "pod": name,
                            "message": payload.get("message") or line[:400],
                            "status": payload.get("status"),
                            "event": payload.get("event"),
                        }
                    )
                except json.JSONDecodeError:
                    entries.append(
                        {
                            "timestamp": utc_now(),
                            "level": "info",
                            "pod": name,
                            "message": line[:400],
                        }
                    )
        except (HttpError, k8s.KubernetesUnavailable, IndexError):
            pass
    return {"status": "ok" if entries else result.get("status") or "ok", "source": source, "logs": entries[-80:]}


def _mode_files(mode: str, deployed_at: str, yaml_text: str) -> dict[str, str]:
    updated = re.sub(
        r'(aiops\.demo/deployed-at: )"[^"]*"',
        rf'\1"{deployed_at}"',
        yaml_text,
    )
    if updated == yaml_text:
        raise ValueError("could not update deployed-at")
    file_mode = "oom" if mode == "oom-stale" else mode
    return {MODE_FILE: f"{file_mode}\n", APP_YAML: updated}


def start_incident(cfg: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode not in INCIDENT_MESSAGES:
        raise ValueError("unknown mode")
    token = (cfg.get("github_token") or "").strip()
    repo = cfg.get("github_repository") or ""
    if not token:
        raise HttpError("GITHUB_TOKEN ausente no Secret ai-agent-llm", status=409)
    if mode == "oom-stale":
        deployed_at = "2026-01-01T00:00:00Z"
    else:
        deployed_at = utc_now()
    yaml_text = github.read_file(
        repo, APP_YAML, token, cfg.get("github_api_url") or "https://api.github.com"
    )
    files = _mode_files(mode, deployed_at, yaml_text)
    commit = github.commit_files(
        repo,
        files,
        INCIDENT_MESSAGES[mode],
        token,
        cfg.get("github_api_url") or "https://api.github.com",
    )
    payload = {
        "mode": mode,
        "deployed_at": deployed_at,
        "started_at": utc_now(),
        **commit,
        "workflow": {"status": "queued", "conclusion": None},
        "image_synced": False,
    }
    store.set_rollout(payload)
    store.emit("demo_incident_committed", mode=mode, sha=commit.get("short_sha"))
    return payload


def execute_latest(analysis: dict[str, Any] | None) -> dict[str, Any]:
    if not analysis:
        raise KeyError("no analysis yet")
    ident = analysis.get("id") or ""
    if any(item.get("executed") for item in analysis.get("approvals") or []):
        return analysis
    decision = execute_mod.ACTION_DECISIONS.get(analysis.get("recommended_action") or "")
    if not decision:
        raise PermissionError("investigate_or_none")
    if analysis.get("scoring_source") != "llm":
        raise PermissionError("llm_unavailable")
    executed, detail = execute_mod.execute(decision, analysis)
    updated = store.record_decision(ident, decision, executed, detail)
    store.emit(
        "human_execution",
        id=ident,
        decision=decision,
        executed=executed,
        detail=detail,
    )
    return updated


def pod_detail(cfg: dict[str, Any], namespace: str, name: str) -> dict[str, Any]:
    pods = k8s.list_namespace_pods(namespace)
    match = next(
        (item for item in pods if (item.get("metadata") or {}).get("name") == name),
        None,
    )
    if not match:
        raise KeyError(name)
    summary = _pod_status(match)
    resources = _workload_resources(match)
    events = []
    try:
        events = k8s.list_events(namespace, name)[:12]
    except (HttpError, k8s.KubernetesUnavailable):
        events = []
    recent_logs = []
    try:
        container = summary.get("container") or summary.get("app") or "demo-app"
        raw = k8s.pod_logs(namespace, name, container, tail=30)
        recent_logs = raw.splitlines()[-20:]
    except (HttpError, k8s.KubernetesUnavailable, TypeError):
        recent_logs = []
    return {
        **summary,
        **resources,
        "events": [
            {
                "type": item.get("type"),
                "reason": item.get("reason"),
                "message": item.get("message"),
                "count": item.get("count"),
            }
            for item in events
        ],
        "logs": recent_logs,
    }


def recommendation_view(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    if not analysis:
        return None
    evidence = analysis.get("evidence") or {}
    approvals = analysis.get("approvals") or []
    action = analysis.get("recommended_action")
    executable = action in execute_mod.ACTION_DECISIONS and analysis.get("scoring_source") == "llm"
    return {
        "id": analysis.get("id"),
        "incident_type": analysis.get("incident_type"),
        "incident_label": INCIDENT_LABELS.get(
            analysis.get("incident_type"), analysis.get("incident_type")
        ),
        "summary": analysis.get("summary"),
        "lecture_text": analysis.get("lecture_text"),
        "recommended_action": action,
        "recommended_label": ACTION_LABELS.get(action, action),
        "scoring_source": analysis.get("scoring_source"),
        "automatic_execution_allowed": analysis.get("automatic_execution_allowed"),
        "executable": executable,
        "executed": any(item.get("executed") for item in approvals),
        "approvals": approvals,
        "recommendations": analysis.get("recommendations") or [],
        "evidence": {
            "deployment": evidence.get("deployment"),
            "namespace": evidence.get("namespace"),
            "git_sha": evidence.get("git_sha"),
            "current_image": evidence.get("current_image"),
            "minutes_since_deployment": evidence.get("minutes_since_deployment"),
            "recent_deployment": evidence.get("recent_deployment"),
            "restarts": evidence.get("restarts"),
            "last_termination_reason": evidence.get("last_termination_reason"),
            "recent_commits": evidence.get("recent_commits") or [],
            "log_entries": (evidence.get("log_entries") or [])[:8],
        },
    }


def static_file(request_path: str) -> tuple[int, bytes, str] | None:
    if not CONSOLE_DIR.exists():
        return None
    parsed = urlparse(request_path).path
    relative = parsed.lstrip("/") or "index.html"
    if parsed in {"/", ""}:
        relative = "index.html"
    target = (CONSOLE_DIR / relative).resolve()
    try:
        target.relative_to(CONSOLE_DIR.resolve())
    except ValueError:
        return 403, b"forbidden", "text/plain"
    if target.is_dir():
        target = target / "index.html"
    if not target.exists() or not target.is_file():
        index = CONSOLE_DIR / "index.html"
        if index.exists() and "." not in Path(relative).name:
            return 200, index.read_bytes(), MIME[".html"]
        return None
    return 200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream")


def parse_query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    return {key: values[-1] for key, values in parse_qs(parsed.query).items()}


def handle_get(path: str, cfg: dict[str, Any]) -> tuple[int, Any, str] | None:
    route = urlparse(path).path.rstrip("/") or "/"
    query = parse_query(path)
    if route == "/api/status":
        return 200, cluster_status(cfg), "application/json"
    if route == "/api/logs":
        return 200, collect_logs(cfg, query.get("source") or "demo-app"), "application/json"
    if route == "/api/events":
        return 200, {"events": store.events()}, "application/json"
    if route == "/api/recommendations":
        latest = recommendation_view(store.latest())
        if not latest:
            return 404, {"error": "no analysis yet"}, "application/json"
        return 200, latest, "application/json"
    if route == "/api/rollout":
        return 200, store.rollout() or {}, "application/json"
    if route.startswith("/api/pods/"):
        parts = [item for item in route.split("/") if item]
        if len(parts) < 4:
            return 400, {"error": "namespace and name required"}, "application/json"
        try:
            return 200, pod_detail(cfg, parts[2], parts[3]), "application/json"
        except KeyError:
            return 404, {"error": "not found"}, "application/json"
        except (HttpError, k8s.KubernetesUnavailable) as exc:
            return 503, {"error": str(exc)}, "application/json"
    return None


def handle_post(path: str, payload: dict[str, Any], cfg: dict[str, Any]) -> tuple[int, Any] | None:
    route = urlparse(path).path.rstrip("/") or "/"
    if route == "/api/demo/incidents":
        mode = str(payload.get("mode") or "").strip()
        try:
            return 202, start_incident(cfg, mode)
        except ValueError:
            return 400, {"error": "unknown mode"}
        except HttpError as exc:
            status = exc.status or 502
            return status, {"error": str(exc)}
    if route == "/api/execute":
        ident = str(payload.get("id") or "").strip()
        analysis = store.get(ident) if ident else store.latest()
        try:
            return 200, recommendation_view(execute_latest(analysis))
        except KeyError:
            return 404, {"error": "no analysis yet"}
        except PermissionError as exc:
            return 409, {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface cluster errors to the console
            return 502, {"error": str(exc)}
    return None


def proxy_demo(request_path: str) -> tuple[int, bytes, str]:
    parsed = urlparse(request_path)
    suffix = parsed.path[len("/live/demo") :] or "/"
    if parsed.query:
        suffix = suffix + "?" + parsed.query
    try:
        status, raw = request(DEMO_APP_URL + suffix, timeout=3.0, raise_http_error=False)
    except HttpError as exc:
        body = json.dumps({"status": "unavailable", "error": str(exc)}).encode()
        return exc.status or 502, body, "application/json"
    content_type = "application/json"
    return status, raw, content_type
