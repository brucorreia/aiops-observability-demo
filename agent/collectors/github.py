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


WRITE_DENIED = (
    "GITHUB_TOKEN sem permissão de escrita em brucorreia/aiops-observability-demo. "
    "No fine-grained PAT, Contents deve ser Read and write; depois rode make llm-secret."
)


def _raise_github_write_error(exc: BaseException) -> None:
    text = str(exc)
    denied = (
        "Resource not accessible by personal access token" in text
        or "FORBIDDEN" in text
        or (isinstance(exc, HttpError) and exc.status in {401, 403})
    )
    if denied:
        raise HttpError(WRITE_DENIED, status=403) from exc
    if isinstance(exc, HttpError):
        raise exc
    raise HttpError(text, status=502) from exc


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
    try:
        head_payload = get_json(
            f"{base}/repos/{repo}/commits/{branch}",
            headers=headers,
            timeout=15.0,
        )
    except HttpError as exc:
        _raise_github_write_error(exc)
    head = (head_payload or {}).get("sha")
    if not head:
        raise HttpError(f"could not resolve {branch}", status=404)
    additions = [
        {
            "path": path,
            "contents": base64.b64encode(content.encode()).decode(),
        }
        for path, content in files.items()
    ]
    try:
        result = json_request(
            f"{base}/graphql",
            payload={
                "query": (
                    "mutation($input: CreateCommitOnBranchInput!) {"
                    " createCommitOnBranch(input: $input) {"
                    " commit { oid commitUrl }"
                    " }"
                    " }"
                ),
                "variables": {
                    "input": {
                        "branch": {
                            "repositoryNameWithOwner": repo,
                            "branchName": branch,
                        },
                        "message": {"headline": message.splitlines()[0][:256]},
                        "fileChanges": {"additions": additions},
                        "expectedHeadOid": head,
                    }
                },
            },
            headers=headers,
            timeout=20.0,
        )
    except HttpError as exc:
        _raise_github_write_error(exc)
    errors = (result or {}).get("errors") or []
    if errors:
        _raise_github_write_error(HttpError(str(errors[0]), status=403))
    commit = (((result or {}).get("data") or {}).get("createCommitOnBranch") or {}).get("commit") or {}
    sha = commit.get("oid") or ""
    if not sha:
        raise HttpError("GitHub did not return a commit SHA", status=502)
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "html_url": commit.get("commitUrl"),
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


ACTIVE_WORKFLOW_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})


def _workflow_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "name": run.get("name") or run.get("display_title"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
        "head_sha": (run.get("head_sha") or "")[:7],
        "path": run.get("path"),
    }


def active_workflow_runs(
    repo: str,
    token: str | None,
    api_url: str = "https://api.github.com",
    branch: str = "main",
) -> list[dict[str, Any]]:
    if not token or not repo:
        return []
    base = api_url.rstrip("/")
    try:
        payload = get_json(
            f"{base}/repos/{repo}/actions/runs?branch={branch}&per_page=20",
            headers=_headers(token),
            timeout=3.0,
        )
    except (HttpError, ValueError, TypeError):
        return []
    found: list[dict[str, Any]] = []
    for run in (payload or {}).get("workflow_runs") or []:
        if (run.get("status") or "") in ACTIVE_WORKFLOW_STATUSES:
            found.append(_workflow_run_summary(run))
    return found
