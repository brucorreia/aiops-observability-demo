#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="${ROOT}/infra/apps/kustomization.yaml"
OWNER="${IMAGE_OWNER:?IMAGE_OWNER is required}"
TAG="${IMAGE_TAG:?IMAGE_TAG is required}"

python3 - "${FILE}" "${OWNER}" "${TAG}" <<'PY'
from pathlib import Path
import sys

path, owner, tag = sys.argv[1], sys.argv[2], sys.argv[3]
lines = Path(path).read_text().splitlines(keepends=True)
out = []
current = None
for line in lines:
    stripped = line.strip()
    if stripped.startswith("name:"):
        current = stripped.split(":", 1)[1].strip()
    if stripped.startswith("newName:") and current == "aiops-demo-app":
        indent = line[: len(line) - len(line.lstrip())]
        line = f'{indent}newName: ghcr.io/{owner}/aiops-demo-app\n'
    elif stripped.startswith("newName:") and current == "aiops-agent":
        indent = line[: len(line) - len(line.lstrip())]
        line = f'{indent}newName: ghcr.io/{owner}/aiops-agent\n'
    elif stripped.startswith("newTag:"):
        indent = line[: len(line) - len(line.lstrip())]
        line = f'{indent}newTag: "{tag}"\n'
    out.append(line)
Path(path).write_text("".join(out))
print(f"Updated {path} tag={tag} owner={owner}")
PY
