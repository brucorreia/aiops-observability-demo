from __future__ import annotations

from typing import Any

from collectors import k8s


def _container_patch(name: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": name, **fields},
                    ]
                }
            }
        }
    }


def rollback(namespace: str, name: str, previous_revision: int | None) -> str:
    replicasets = k8s.list_replicasets(namespace, name)
    previous = None
    for item in replicasets:
        annotations = (item.get("metadata") or {}).get("annotations") or {}
        if annotations.get("deployment.kubernetes.io/revision") == str(previous_revision):
            previous = item
            break
    if previous is None:
        ranked = sorted(
            replicasets,
            key=lambda item: int(
                ((item.get("metadata") or {}).get("annotations") or {}).get(
                    "deployment.kubernetes.io/revision", "0"
                )
            ),
            reverse=True,
        )
        if len(ranked) < 2:
            raise RuntimeError("no previous ReplicaSet to roll back to")
        previous = ranked[1]
    template = (previous.get("spec") or {}).get("template") or {}
    k8s.patch_json(
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        {"spec": {"template": template}},
    )
    return f"rolled back toward revision {previous_revision}"


def vertical_scale(namespace: str, name: str, memory: str = "128Mi") -> str:
    k8s.patch_json(
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        _container_patch(name, {"resources": {"limits": {"memory": memory}, "requests": {"memory": "32Mi"}}}),
    )
    return f"patched memory limit to {memory}"


def horizontal_scale(namespace: str, name: str, replicas: int) -> str:
    k8s.patch_json(
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        {"spec": {"replicas": replicas}},
    )
    return f"patched replicas to {replicas}"


def execute(decision: str, analysis: dict[str, Any]) -> tuple[bool, str]:
    evidence = analysis.get("evidence") or {}
    namespace = evidence.get("namespace") or "aiops-demo"
    name = evidence.get("deployment") or "demo-app"
    if decision == "approve_rollback":
        return True, rollback(namespace, name, evidence.get("previous_revision"))
    if decision == "approve_vertical_scale":
        return True, vertical_scale(namespace, name)
    if decision == "approve_horizontal_scale":
        replicas = int(evidence.get("replicas") or 1) + 1
        return True, horizontal_scale(namespace, name, replicas)
    if decision in {"reject", "investigate_more"}:
        return False, "no cluster change"
    raise ValueError(f"unknown decision {decision}")
