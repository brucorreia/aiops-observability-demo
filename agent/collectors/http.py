from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def request(
    url: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
    cafile: str | None = None,
    insecure: bool = False,
) -> tuple[int, bytes]:
    ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context(cafile=cafile)
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read() if exc.fp else b""
        raise HttpError(f"HTTP {exc.code} for {url}: {payload[:300]!r}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"request failed for {url}: {exc.reason}") from exc


def get_json(url: str, **kwargs: Any) -> Any:
    _, raw = request(url, **kwargs)
    if not raw:
        return None
    return json.loads(raw.decode())


def post_form(url: str, fields: dict[str, str], **kwargs: Any) -> bytes:
    body = urllib.parse.urlencode(fields).encode()
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    _, raw = request(url, method="POST", body=body, headers=headers, **kwargs)
    return raw
