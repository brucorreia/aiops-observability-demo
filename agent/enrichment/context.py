from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from collectors import github, k8s, logs, metrics
from collectors.http import HttpError
from enrichment.normalize import incident_type_for, parse_time

EXTERNAL_HINTS = (
    "timeout",
    "timed out",
    "connection refused",
    "upstream",
    "dns",
    "i/o timeout",
    "dial tcp",
)


def _unavailable(name: str, error: str | None = None) -> dict[str, str]:
    item = {"evidence": name, "status": "unavailable"}
    if error:
        item["error"] = error
    return item


def _annotation(obj: dict[str, Any], key: str) -> str | None:
    annotations = (obj.get("metadata") or {}).get("annotations") or {}
    return annotations.get(key)


def _container(pod_or_rs: dict[str, Any], name: str = "demo-app") -> dict[str, Any]:
    containers = ((pod_or_rs.get("spec") or {}).get("template") or {}).get("spec", {}).get("containers")
    if containers is None:
        containers = (pod_or_rs.get("spec") or {}).get("containers") or []
    for item in containers or []:
        if item.get("name") == name:
            return item
    return (containers or [None])[0] or {}


def _env_value(container: dict[str, Any], key: str) -> str | None:
    for item in container.get("env") or []:
        if item.get("name") == key:
            return item.get("value")
    return None


def _revision(obj: dict[str, Any]) -> int | None:
    raw = _annotation(obj, "deployment.kubernetes.io/revision")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    try:
        if text.endswith("Ki"):
            return int(float(text[:-2]) * 1024)
        if text.endswith("Mi"):
            return int(float(text[:-2]) * 1024 * 1024)
        if text.endswith("Gi"):
            return int(float(text[:-2]) * 1024 * 1024 * 1024)
        return int(float(text))
    except ValueError:
        return None


def _memory_slope(points: list[list[Any]]) -> float | None:
    values = []
    for point in points:
        if len(point) < 2:
            continue
        try:
            values.append(float(point[1]))
        except (TypeError, ValueError):
            continue
    if len(values) < 4:
        return None
    increases = sum(1 for prev, cur in zip(values, values[1:]) if cur > prev)
    return increases / max(1, len(values) - 1)


def enrich(alert: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    namespace = alert.get("namespace") or settings["demo_namespace"]
    workload = "demo-app"
    window = settings["recent_deployment_window_minutes"]
    now = datetime.now(timezone.utc)

    context: dict[str, Any] = {
        "deployment": workload,
        "namespace": namespace,
        "current_revision": None,
        "previous_revision": None,
        "current_image": None,
        "previous_image": None,
        "current_mode": None,
        "previous_mode": None,
        "last_deployment_at": None,
        "minutes_since_deployment": None,
        "recent_deployment": None,
        "restarts": 0,
        "last_termination_reason": None,
        "memory_limit_bytes": None,
        "memory_peak_bytes": None,
        "memory_usage_ratio": None,
        "http_500_count": None,
        "related_log_messages": [],
        "log_entries": [],
        "log_event_counts": {},
        "recent_commits": [],
        "commit_compare": None,
        "code_changed_in_demo_app": None,
        "pods_ready": None,
        "replicas": None,
        "affected_pods": 0,
        "deployment_conditions": [],
        "events": [],
        "git_sha": None,
        "previous_revision_healthy": None,
        "failures_started_after_deployment": None,
        "sustained_memory_growth": None,
        "traffic_growth": None,
        "cpu_saturation": None,
        "external_dependency_errors": False,
        "missing_evidence": missing,
    }

    try:
        deployment = k8s.get_deployment(namespace, workload)
        replicasets = k8s.list_replicasets(namespace, workload)
        pods = k8s.list_pods(namespace, workload)
        events = k8s.list_events(namespace, workload)
    except (k8s.KubernetesUnavailable, HttpError, json.JSONDecodeError) as exc:
        missing.append(_unavailable("kubernetes_api", str(exc)))
        deployment, replicasets, pods, events = {}, [], [], []

    if deployment:
        context["current_revision"] = _revision(deployment)
        current_container = _container(deployment)
        context["current_image"] = current_container.get("image")
        context["current_mode"] = _env_value(current_container, "DEMO_MODE")
        context["git_sha"] = _annotation(deployment, "aiops.demo/git-sha")
        context["replicas"] = (deployment.get("spec") or {}).get("replicas")
        context["deployment_conditions"] = (deployment.get("status") or {}).get("conditions") or []
        limits = ((current_container.get("resources") or {}).get("limits") or {})
        context["memory_limit_bytes"] = _parse_bytes(limits.get("memory"))
        deployed_at = parse_time(_annotation(deployment, "aiops.demo/deployed-at"))
        if deployed_at is None:
            missing.append(_unavailable("last_deployment_at"))
        else:
            context["last_deployment_at"] = deployed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            minutes = max(0, int((now - deployed_at).total_seconds() // 60))
            context["minutes_since_deployment"] = minutes
            context["recent_deployment"] = minutes <= window

    ranked = sorted(
        (item for item in replicasets if _revision(item) is not None),
        key=lambda item: _revision(item) or 0,
        reverse=True,
    )
    if ranked:
        current_rs = ranked[0]
        context["current_revision"] = context["current_revision"] or _revision(current_rs)
        context["current_image"] = context["current_image"] or _container(current_rs).get("image")
        if len(ranked) > 1:
            previous = ranked[1]
            context["previous_revision"] = _revision(previous)
            prev_container = _container(previous)
            context["previous_image"] = prev_container.get("image")
            context["previous_mode"] = _env_value(prev_container, "DEMO_MODE")
            prev_replicas = (previous.get("status") or {}).get("readyReplicas")
            context["previous_revision_healthy"] = (prev_replicas or 0) > 0 or context["previous_mode"] == "good"
        else:
            missing.append(_unavailable("previous_revision"))
    else:
        missing.append(_unavailable("replicasets"))

    ready = 0
    restarts = 0
    last_reason = None
    affected = 0
    for pod in pods:
        status = pod.get("status") or {}
        pod_ready = False
        for cond in status.get("conditions") or []:
            if cond.get("type") == "Ready" and cond.get("status") == "True":
                pod_ready = True
                ready += 1
        for container_status in status.get("containerStatuses") or []:
            restarts += int(container_status.get("restartCount") or 0)
            terminated = ((container_status.get("lastState") or {}).get("terminated")) or {}
            waiting = ((container_status.get("state") or {}).get("waiting")) or {}
            reason = terminated.get("reason") or waiting.get("reason")
            if reason:
                last_reason = reason
            if reason in {"OOMKilled", "CrashLoopBackOff", "Error"}:
                affected += 1
        if not pod_ready:
            affected += 1
    context["pods_ready"] = ready
    context["restarts"] = restarts
    context["last_termination_reason"] = last_reason
    context["affected_pods"] = max(affected, 1 if last_reason else 0)
    if last_reason:
        alert["incident_type"] = incident_type_for(alert.get("alert_name", ""), last_reason)

    context["events"] = [
        {
            "type": item.get("type"),
            "reason": item.get("reason"),
            "message": item.get("message"),
            "count": item.get("count"),
        }
        for item in events[:15]
    ]

    mem_limit = metrics.query(
        settings["victoriametrics_url"],
        f'kube_pod_container_resource_limits{{namespace="{namespace}",container="demo-app",resource="memory"}}',
    )
    mem_peak = metrics.query(
        settings["victoriametrics_url"],
        f'max_over_time(container_memory_working_set_bytes{{namespace="{namespace}",container="demo-app"}}[15m])',
    )
    mem_now = metrics.query(
        settings["victoriametrics_url"],
        f'container_memory_working_set_bytes{{namespace="{namespace}",container="demo-app"}}',
    )
    cpu = metrics.query(
        settings["victoriametrics_url"],
        f'avg_over_time(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",container="demo-app"}}[2m])[10m:])',
    )
    if mem_limit["status"] != "ok":
        missing.append(_unavailable("memory_limit_bytes", mem_limit.get("error")))
    else:
        value = metrics.first_value(mem_limit["result"])
        if value is not None:
            context["memory_limit_bytes"] = int(value)
    if mem_peak["status"] != "ok":
        missing.append(_unavailable("memory_peak_bytes", mem_peak.get("error")))
        if mem_now["status"] == "ok":
            value = metrics.first_value(mem_now["result"])
            if value is not None:
                context["memory_peak_bytes"] = int(value)
    else:
        value = metrics.first_value(mem_peak["result"])
        if value is not None:
            context["memory_peak_bytes"] = int(value)
    if context["memory_limit_bytes"] and context["memory_peak_bytes"]:
        context["memory_usage_ratio"] = round(
            context["memory_peak_bytes"] / context["memory_limit_bytes"], 3
        )
    if cpu["status"] != "ok":
        missing.append(_unavailable("cpu_usage", cpu.get("error")))
    else:
        value = metrics.first_value(cpu["result"])
        context["cpu_saturation"] = bool(value is not None and value > 0.7)

    if context["last_deployment_at"]:
        deployed_at = parse_time(context["last_deployment_at"])
        if deployed_at:
            start = deployed_at.timestamp() - 600
            end = now.timestamp()
            series = metrics.query_range(
                settings["victoriametrics_url"],
                f'container_memory_working_set_bytes{{namespace="{namespace}",container="demo-app"}}',
                start,
                end,
            )
            if series["status"] != "ok" or not series["result"]:
                missing.append(_unavailable("previous_version_memory", series.get("error")))
            else:
                points = series["result"][0].get("values") or []
                slope = _memory_slope(points)
                context["sustained_memory_growth"] = bool(slope is not None and slope >= 0.7)
                before = [float(p[1]) for p in points if float(p[0]) < deployed_at.timestamp()]
                after = [float(p[1]) for p in points if float(p[0]) >= deployed_at.timestamp()]
                if before and after:
                    context["failures_started_after_deployment"] = max(after) > max(before) * 1.2
                else:
                    missing.append(_unavailable("memory_before_after_deploy"))
    else:
        missing.append(_unavailable("previous_version_memory"))

    log_filter = (
        f'kubernetes.pod_namespace:="{namespace}" kubernetes.container_name:="demo-app" '
        "| unpack_json"
    )
    log_result = logs.query_logs(settings["victorialogs_url"], log_filter, limit=60)
    if log_result["status"] != "ok":
        missing.append(_unavailable("application_logs", log_result.get("error")))
        if pods:
            try:
                fallback = k8s.pod_logs(namespace, (pods[0].get("metadata") or {}).get("name", ""), "demo-app")
                context["related_log_messages"] = fallback.splitlines()[-20:]
                context["log_entries"] = _entries_from_raw_lines(context["related_log_messages"])
                missing.append({"evidence": "application_logs", "status": "fallback_kube_logs"})
            except (HttpError, k8s.KubernetesUnavailable, KeyError):
                pass
    else:
        _apply_log_evidence(context, log_result["logs"], missing)

    stats = logs.stats_query(
        settings["victorialogs_url"],
        f'{log_filter} | path:="/api" | stats count() as total, count() if (status:500) as http_500',
    )
    if stats["status"] == "ok" and stats["result"]:
        metric = stats["result"][0]
        values = {item.get("metric", {}).get("stats_result"): item.get("value", [None, None])[1] for item in stats["result"]}
        try:
            total = float(values.get("total") or metric.get("value", [None, 0])[1] or 0)
            err = float(values.get("http_500") or 0)
            if total > 0:
                context["traffic_growth"] = total > 20
        except (TypeError, ValueError):
            missing.append(_unavailable("http_500_count"))
    elif context["http_500_count"] is None:
        missing.append(_unavailable("http_500_count", stats.get("error")))

    if context["failures_started_after_deployment"] is None and context["recent_deployment"] and last_reason:
        context["failures_started_after_deployment"] = True

    current_sha = context.get("git_sha") if context.get("git_sha") not in {None, "dev"} else github.sha_from_image(
        context.get("current_image")
    )
    previous_sha = github.sha_from_image(context.get("previous_image"))
    if current_sha:
        context["git_sha"] = current_sha
    commit_evidence = github.collect_commit_evidence(
        settings.get("github_repository") or "",
        current_sha,
        previous_sha,
        token=settings.get("github_token") or None,
        api_url=settings.get("github_api_url") or "https://api.github.com",
    )
    if commit_evidence.get("status") != "ok":
        missing.append(_unavailable("github_commits", commit_evidence.get("error")))
    context["recent_commits"] = commit_evidence.get("recent_commits") or []
    context["commit_compare"] = commit_evidence.get("compare")
    context["code_changed_in_demo_app"] = commit_evidence.get("touches_demo_app")

    return context


def _parse_log_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("_msg")
    payload = item
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = {**item, **decoded}
        except json.JSONDecodeError:
            pass
    status = payload.get("status")
    try:
        status_i = int(status) if status is not None else None
    except (TypeError, ValueError):
        status_i = None
    message = str(payload.get("message") or raw or json.dumps(item))[:400]
    return {
        "timestamp": payload.get("timestamp") or payload.get("_time"),
        "level": payload.get("level"),
        "event": payload.get("event"),
        "path": payload.get("path"),
        "status": status_i,
        "message": message,
    }


def _entries_from_raw_lines(lines: list[str]) -> list[dict[str, Any]]:
    entries = []
    for line in lines:
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                entries.append(_parse_log_item(parsed))
                continue
        except json.JSONDecodeError:
            pass
        entries.append({"message": line[:400], "level": None, "event": None, "status": None, "path": None})
    return entries[-30:]


def _apply_log_evidence(context: dict[str, Any], raw_logs: list[dict[str, Any]], missing: list[dict[str, str]]) -> None:
    entries = []
    event_counts: dict[str, int] = {}
    http_500 = 0
    external = False
    after_deploy = 0
    deployed_at = parse_time(context.get("last_deployment_at"))
    for item in raw_logs:
        entry = _parse_log_item(item)
        entries.append(entry)
        event = entry.get("event") or "unknown"
        event_counts[event] = event_counts.get(event, 0) + 1
        if entry.get("status") == 500:
            http_500 += 1
            if deployed_at:
                log_time = parse_time(entry.get("timestamp"))
                if log_time and log_time >= deployed_at:
                    after_deploy += 1
        text = (entry.get("message") or "").lower()
        if any(hint in text for hint in EXTERNAL_HINTS):
            external = True
    entries.sort(
        key=lambda item: (
            0 if item.get("status") == 500 or (item.get("level") or "").lower() == "error" else 1,
            item.get("timestamp") or "",
        )
    )
    context["related_log_messages"] = [item["message"] for item in entries[:30]]
    context["log_entries"] = entries[:30]
    context["log_event_counts"] = event_counts
    context["http_500_count"] = http_500
    context["external_dependency_errors"] = external
    if context.get("failures_started_after_deployment") is None and deployed_at:
        context["failures_started_after_deployment"] = after_deploy > 0 and http_500 > 0
    if not entries:
        missing.append(_unavailable("application_logs"))
