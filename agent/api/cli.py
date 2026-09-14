from __future__ import annotations

import argparse
import json
import sys

from collectors.http import HttpError, request


def _get_recommendations(fmt: str) -> int:
    path = "/recommendations.txt" if fmt == "text" else "/recommendations"
    try:
        _, raw = request(f"http://127.0.0.1:8080{path}", timeout=8.0)
    except HttpError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = raw.decode()
    if fmt == "text":
        print(text)
        return 0
    if fmt == "both":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print(text)
            return 0
        print(payload.get("lecture_text") or "", file=sys.stderr)
        print(text)
        return 0
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOps agent CLI")
    parser.add_argument("command", choices=["recommendations"])
    parser.add_argument("--format", choices=["json", "text", "both"], default="json")
    args = parser.parse_args()
    if args.command == "recommendations":
        return _get_recommendations(args.format)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
