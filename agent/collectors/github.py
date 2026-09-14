from __future__ import annotations

import re
from typing import Any

from collectors.http import HttpError, get_json

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
