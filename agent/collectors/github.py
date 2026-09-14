from __future__ import annotations

import re
from typing import Any

import base64
from collectors.http import HttpError, get_json, json_request

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def sha_from_image(image: str | None) -> str | None:
    if not image or ":" not in image:
        return None
    tag = image.rsplit(":", 1)[-1].strip()
    if tag in {"dev", "latest"} or not SHA_RE.match(tag):
        return None
    return tag


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "aiops-observability-demo",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _commit_summary(item: dict[str, Any]) -> dict[str, Any]:
    commit = item.get("commit") or {}
    author = commit.get("author") or {}
    return {
        "sha": (item.get("sha") or "")[:7],
        "message": ((commit.get("message") or "").splitlines() or [""])[0][:200],
        "author": author.get("name"),
        "date": author.get("date"),
        "html_url": item.get("html_url"),
    }


def _file_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": item.get("filename"),
        "status": item.get("status"),
        "additions": item.get("additions"),
        "deletions": item.get("deletions"),
    }


def _touches(files: list[dict[str, Any]], prefix: str) -> bool:
    return any(str(item.get("filename") or "").startswith(prefix) for item in files)


def collect_commit_evidence(
    repo: str,
    current_sha: str | None,
    previous_sha: str | None,
    token: str | None = None,
    api_url: str = "https://api.github.com",
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "status": "unavailable",
        "repository": repo,
        "current_sha": current_sha,
        "previous_sha": previous_sha,
        "recent_commits": [],
        "compare": None,
        "touches_demo_app": None,
        "touches_agent": None,
        "error": None,
    }
    if not repo:
        evidence["error"] = "GITHUB_REPOSITORY is empty"
        return evidence

    base = api_url.rstrip("/")
    headers = _headers(token)
    try:
        commits = get_json(
            f"{base}/repos/{repo}/commits?per_page=8",
            headers=headers,
            timeout=8.0,
        )
    except (HttpError, ValueError, TypeError) as exc:
        evidence["error"] = str(exc)
        return evidence

    if not isinstance(commits, list):
        evidence["error"] = "unexpected GitHub commits payload"
        return evidence

    evidence["recent_commits"] = [_commit_summary(item) for item in commits[:8]]
    evidence["status"] = "ok"

    if not current_sha or not previous_sha or current_sha == previous_sha:
        return evidence

    try:
        compare = get_json(
            f"{base}/repos/{repo}/compare/{previous_sha}...{current_sha}",
            headers=headers,
            timeout=8.0,
        )
    except (HttpError, ValueError, TypeError) as exc:
        evidence["compare"] = {"status": "unavailable", "error": str(exc)}
        return evidence

    files = [_file_summary(item) for item in (compare.get("files") or [])[:40]]
    evidence["compare"] = {
        "status": "ok",
        "base": previous_sha,
        "head": current_sha,
        "ahead_by": compare.get("ahead_by"),
        "behind_by": compare.get("behind_by"),
        "total_commits": compare.get("total_commits"),
        "commits": [_commit_summary(item) for item in (compare.get("commits") or [])[:12]],
        "files": files,
    }
    evidence["touches_demo_app"] = _touches(files, "apps/demo-app/")
    evidence["touches_agent"] = _touches(files, "agent/")
    return evidence


def read_file(
    repo: str,
    path: str,
    token: str,
    api_url: str = "https://api.github.com",
    ref: str = "main",
) -> str:
    base = api_url.rstrip("/")
    payload = get_json(
        f"{base}/repos/{repo}/contents/{path}?ref={ref}",
        headers=_headers(token),
        timeout=15.0,
    )
    encoded = (payload or {}).get("content") or ""
    return base64.b64decode(encoded.replace("\n", "")).decode()


def commit_files(
    repo: str,
    files: dict[str, str],
    message: str,
    token: str,
    api_url: str = "https://api.github.com",
    branch: str = "main",
) -> dict[str, Any]:
    if not token:
        raise HttpError("GITHUB_TOKEN is required to commit demo incidents", status=401)
    if not files:
        raise ValueError("no files to commit")
    base = api_url.rstrip("/")
    headers = _headers(token)
    ref = get_json(f"{base}/repos/{repo}/git/ref/heads/{branch}", headers=headers, timeout=15.0)
    head = ((ref or {}).get("object") or {}).get("sha")
    if not head:
        raise HttpError(f"could not resolve {branch}", status=404)
    commit = get_json(f"{base}/repos/{repo}/git/commits/{head}", headers=headers, timeout=15.0)
    base_tree = ((commit or {}).get("tree") or {}).get("sha")
    entries = []
    for path, content in files.items():
        blob = json_request(
            f"{base}/repos/{repo}/git/blobs",
            payload={"content": content, "encoding": "utf-8"},
            headers=headers,
            timeout=15.0,
        )
        entries.append(
            {"path": path, "mode": "100644", "type": "blob", "sha": (blob or {}).get("sha")}
        )
    tree = json_request(
        f"{base}/repos/{repo}/git/trees",
        payload={"base_tree": base_tree, "tree": entries},
        headers=headers,
        timeout=15.0,
    )
    created = json_request(
        f"{base}/repos/{repo}/git/commits",
        payload={
            "message": message,
            "tree": (tree or {}).get("sha"),
            "parents": [head],
        },
        headers=headers,
        timeout=15.0,
    )
    sha = (created or {}).get("sha") or ""
    json_request(
        f"{base}/repos/{repo}/git/refs/heads/{branch}",
        method="PATCH",
        payload={"sha": sha},
        headers=headers,
        timeout=15.0,
    )
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "html_url": (created or {}).get("html_url"),
        "message": message,
        "branch": branch,
    }


def workflow_run_for_sha(
    repo: str,
    sha: str,
    workflow_file: str,
    token: str | None,
    api_url: str = "https://api.github.com",
) -> dict[str, Any]:
    if not token or not sha:
        return {"status": "unavailable", "conclusion": None, "html_url": None}
    base = api_url.rstrip("/")
    try:
        payload = get_json(
            f"{base}/repos/{repo}/actions/workflows/{workflow_file}/runs?head_sha={sha}&per_page=1",
            headers=_headers(token),
            timeout=15.0,
        )
    except (HttpError, ValueError, TypeError) as exc:
        return {"status": "unavailable", "conclusion": None, "error": str(exc)}
    runs = (payload or {}).get("workflow_runs") or []
    if not runs:
        return {"status": "queued", "conclusion": None, "html_url": None}
    run = runs[0]
    return {
        "status": run.get("status") or "queued",
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
        "name": run.get("name"),
    }
