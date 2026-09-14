#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("empty analysis payload", file=sys.stderr)
        return 1
    analysis = json.loads(raw)
    ident = analysis.get("id") or "unknown-incident"
    out_dir = Path("docs/incidents")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{ident}.json").write_text(json.dumps(analysis, indent=2) + "\n")
    markdown = analysis.get("markdown") or f"# {ident}\n"
    (out_dir / f"{ident}.md").write_text(markdown if markdown.endswith("\n") else markdown + "\n")
    print(analysis.get("lecture_text") or ident)
    print(f"\nSaved docs/incidents/{ident}.json and docs/incidents/{ident}.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
