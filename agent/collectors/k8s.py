from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from collectors.http import get_json, request

TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
NS_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


class KubernetesUnavailable(Exception):
    pass


def in_cluster() -> bool:
    return TOKEN_PATH.exists()


def _headers() -> dict[str, str]:
    if not TOKEN_PATH.exists():
        raise KubernetesUnavailable("service account token is not mounted")
    token = TOKEN_PATH.read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def api(path: str) -> Any:
    host = "https://kubernetes.default.svc"
    cafile = str(CA_PATH) if CA_PATH.exists() else None
    return get_json(host + path, headers=_headers(), cafile=cafile)


def patch_json(path: str, payload: dict[str, Any]) -> Any:
    host = "https://kubernetes.default.svc"
    cafile = str(CA_PATH) if CA_PATH.exists() else None
    body = json.dumps(payload).encode()
    _, raw = request(
        host + path,
        method="PATCH",
        body=body,
        headers={
            **_headers(),
            "Content-Type": "application/strategic-merge-patch+json",
        },
        cafile=cafile,
    )
    return json.loads(raw.decode()) if raw else None


def list_deployments(namespace: str) -> list[dict[str, Any]]:
    data = api(f"/apis/apps/v1/namespaces/{namespace}/deployments")
    return data.get("items") or []


def get_deployment(namespace: str, name: str) -> dict[str, Any]:
    return api(f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}")


def list_replicasets(namespace: str, name: str) -> list[dict[str, Any]]:
    data = api(
        f"/apis/apps/v1/namespaces/{namespace}/replicasets?labelSelector=app={name}"
    )
    return data.get("items") or []


def list_pods(namespace: str, name: str) -> list[dict[str, Any]]:
    data = api(f"/api/v1/namespaces/{namespace}/pods?labelSelector=app={name}")
    return data.get("items") or []


def list_events(namespace: str, name: str) -> list[dict[str, Any]]:
    data = api(f"/api/v1/namespaces/{namespace}/events")
    items = data.get("items") or []
    return [
        item
        for item in items
        if name in json.dumps(item.get("involvedObject") or {})
        or name in (item.get("metadata") or {}).get("name", "")
    ]


def pod_logs(namespace: str, pod: str, container: str, tail: int = 50) -> str:
    data = request(
        f"https://kubernetes.default.svc/api/v1/namespaces/{namespace}/pods/{pod}/log"
        f"?container={container}&tailLines={tail}",
        headers=_headers(),
        cafile=str(CA_PATH) if CA_PATH.exists() else None,
    )
    return data[1].decode(errors="replace")
