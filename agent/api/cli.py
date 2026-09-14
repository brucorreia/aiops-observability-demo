from __future__ import annotations

import argparse
import json
import sys

from api.server import run_analysis
from recommendations import execute as execute_mod
from recommendations import store


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOps agent CLI")
    parser.add_argument("command", choices=["analyze", "recommendations", "approve"])
    parser.add_argument("--format", choices=["json", "text", "both"], default="json")
    parser.add_argument(
        "--decision",
        choices=[
            "approve_rollback",
            "approve_vertical_scale",
            "approve_horizontal_scale",
            "reject",
            "investigate_more",
        ],
    )
    args = parser.parse_args()

    if args.command == "analyze":
        analysis = run_analysis()
        _print(analysis, args.format)
        return 0

    if args.command == "recommendations":
        analysis = store.latest()
        if not analysis:
            analysis = run_analysis()
        _print(analysis, args.format)
        return 0

    if args.command == "approve":
        if not args.decision:
            print("decision is required", file=sys.stderr)
            return 2
        analysis = store.latest() or run_analysis()
        executed, detail = execute_mod.execute(args.decision, analysis)
        store.record_decision(analysis["id"], args.decision, executed, detail)
        print(json.dumps({"executed": executed, "detail": detail, "id": analysis["id"]}))
        return 0
    return 1


def _print(analysis: dict, fmt: str) -> None:
    if fmt == "text":
        print(analysis.get("lecture_text") or "")
        return
    if fmt == "both":
        print(analysis.get("lecture_text") or "", file=sys.stderr)
    print(json.dumps(analysis))


if __name__ == "__main__":
    raise SystemExit(main())
