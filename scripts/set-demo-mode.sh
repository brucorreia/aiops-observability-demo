#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
export KUBECONFIG="${KUBECONFIG:-$ROOT/.kube/config}"

MODE="${1:?mode required (good|crashloop|oom|http500)}"
STALE="${2:-}"
NS="${DEMO_NS:-aiops-demo}"
DEPLOY="${DEPLOY_NAME:-demo-app}"
MODE_FILE="${ROOT}/apps/demo-app/demo_mode"
APP_YAML="${ROOT}/deploy/demo-app/demo-app.yaml"

case "${MODE}" in
  good|crashloop|oom|http500) ;;
  *)
    echo "Unknown mode: ${MODE}" >&2
    exit 1
    ;;
esac

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "Demo incidents must be committed on main so Argo CD can sync them." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash unrelated changes first." >&2
  git status --short >&2
  exit 1
fi

if [[ -n "${STALE}" ]]; then
  DEPLOYED_AT="${STALE}"
else
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

printf '%s\n' "${MODE}" > "${MODE_FILE}"
python3 - "${APP_YAML}" "${DEPLOYED_AT}" <<'PY'
from pathlib import Path
import re
import sys

path, deployed_at = Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
updated = re.sub(
    r'(aiops\.demo/deployed-at: )"[^"]*"',
    rf'\1"{deployed_at}"',
    text,
)
if updated == text:
    raise SystemExit(f"could not update deployed-at in {path}")
path.write_text(updated)
PY

if [[ -n "${STALE}" ]]; then
  MSG="fix(demo-app): leak memory with a stale deploy timestamp"
else
  case "${MODE}" in
    good) MSG="fix(demo-app): restore healthy mode" ;;
    crashloop) MSG="fix(demo-app): fail startup (CrashLoopBackOff)" ;;
    oom) MSG="fix(demo-app): leak memory (OOMKilled)" ;;
    http500) MSG="fix(demo-app): return HTTP 500 on /api" ;;
  esac
fi

git add "${MODE_FILE}" "${APP_YAML}"
if git diff --cached --quiet; then
  echo "demo-app is already in mode ${MODE}"
  exit 0
fi
git commit -m "${MSG}"
git push origin HEAD
SHA="$(git rev-parse --short HEAD)"
echo "Pushed ${SHA} DEMO_MODE=${MODE} deployed-at=${DEPLOYED_AT}"

if ! command -v gh >/dev/null; then
  echo "gh is not installed; wait for the demo-app workflow and Argo CD to sync ${SHA}" >&2
  exit 0
fi

echo "Waiting for the demo-app image workflow..."
sleep 3
RUN_ID="$(gh run list --workflow=demo-app.yaml --branch main --limit 1 --json databaseId --jq '.[0].databaseId')"
if [[ -z "${RUN_ID}" ]]; then
  echo "No demo-app workflow found" >&2
  exit 1
fi
gh run watch "${RUN_ID}" || true
CONCLUSION="$(gh run view "${RUN_ID}" --json conclusion --jq '.conclusion')"
if [[ "${CONCLUSION}" != "success" ]]; then
  echo "demo-app workflow ${RUN_ID} finished as ${CONCLUSION}" >&2
  exit 1
fi
git pull --ff-only origin main

echo "Waiting for Argo CD to roll ghcr.io/.../aiops-demo-app:${SHA}..."
deadline=$((SECONDS + 300))
while (( SECONDS < deadline )); do
  image="$(kubectl get deploy "${DEPLOY}" -n "${NS}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  if [[ "${image}" == *":${SHA}" ]]; then
    break
  fi
  kubectl annotate application demo-app -n argocd argocd.argoproj.io/refresh=hard --overwrite >/dev/null 2>&1 || true
  sleep 5
done
image="$(kubectl get deploy "${DEPLOY}" -n "${NS}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
if [[ "${image}" != *":${SHA}" ]]; then
  echo "Timed out waiting for demo-app image ${SHA} (saw ${image:-unknown})" >&2
  exit 1
fi

if [[ "${MODE}" == "crashloop" ]]; then
  echo "Waiting for CrashLoopBackOff..."
  deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    if kubectl get pods -n "${NS}" -l app=demo-app -o jsonpath='{range .items[*]}{.status.containerStatuses[0].state.waiting.reason}{"\n"}{end}' 2>/dev/null | grep -q CrashLoopBackOff; then
      echo "demo-app is CrashLoopBackOff after commit ${SHA}"
      exit 0
    fi
    sleep 3
  done
  echo "Image rolled but CrashLoopBackOff was not observed yet; check kubectl get pods -n ${NS}"
  exit 0
fi

kubectl rollout status deployment/"${DEPLOY}" -n "${NS}" --timeout=180s
echo "demo-app mode ${MODE} is live from commit ${SHA}"
