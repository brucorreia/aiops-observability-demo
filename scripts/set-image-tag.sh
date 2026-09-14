#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${IMAGE_OWNER:?IMAGE_OWNER is required}"
TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
NAME="${IMAGE_NAME:?IMAGE_NAME is required}"
FILE="${KUSTOMIZATION:-}"

if [[ -z "${FILE}" ]]; then
  case "${NAME}" in
    aiops-demo-app) FILE="${ROOT}/infra/apps/demo-app/kustomization.yaml" ;;
    aiops-agent) FILE="${ROOT}/infra/apps/ai-agent/kustomization.yaml" ;;
    *)
      echo "Unknown IMAGE_NAME=${NAME}; set KUSTOMIZATION" >&2
      exit 1
      ;;
  esac
fi

python3 - "${FILE}" "${OWNER}" "${TAG}" "${NAME}" <<'PY'
from pathlib import Path
import re
import sys

path, owner, tag, name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
text = Path(path).read_text()
pattern = re.compile(
    rf"(  - name: {re.escape(name)}\n    newName: )[^\n]+(\n    newTag: )[^\n]+"
)
updated, count = pattern.subn(rf'\1ghcr.io/{owner}/{name}\2"{tag}"', text, count=1)
if count != 1:
    raise SystemExit(f"Could not update image {name} in {path}")
Path(path).write_text(updated)
print(f"Updated {path} image={name} tag={tag} owner={owner}")
PY
