#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
export KUBECONFIG="${KUBECONFIG:-$ROOT/.kube/config}"

KIND="${1:?kind required (vertical|horizontal)}"
NS="${DEMO_NS:-aiops-demo}"
DEPLOY="${DEPLOY_NAME:-demo-app}"
KUSTOMIZE="${ROOT}/infra/apps/demo-app/kustomization.yaml"

case "${KIND}" in
  vertical|horizontal) ;;
  *)
    echo "Unknown scale kind: ${KIND}" >&2
    exit 1
    ;;
esac

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "Demo scale must be committed on main so Argo CD can sync it." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash unrelated changes first." >&2
  git status --short >&2
  exit 1
fi

DETAIL="$(
  python3 - "${KUSTOMIZE}" "${KIND}" <<'PY'
from pathlib import Path
import re
import sys

path, kind = Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
max_replicas = 3
limits = ("32Mi", "128Mi", "256Mi")
requests = ("16Mi", "32Mi", "64Mi")
replicas_path = "/spec/replicas"
request_path = "/spec/template/spec/containers/0/resources/requests/memory"
limit_path = "/spec/template/spec/containers/0/resources/limits/memory"


def value_of(body: str, json_path: str) -> str | None:
    match = re.search(rf"path: {re.escape(json_path)}\n\s+value: (\S+)", body)
    return match.group(1) if match else None


def set_value(body: str, json_path: str, value: str) -> str:
    updated, count = re.subn(
        rf"(path: {re.escape(json_path)}\n\s+value: )\S+",
        rf"\g<1>{value}",
        body,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"could not set {json_path}")
    return updated


if kind == "vertical":
    current = value_of(text, limit_path)
    if current not in limits:
        raise SystemExit(f"unknown memory limit {current}")
    index = limits.index(current)
    if index >= len(limits) - 1:
        raise SystemExit("memory already at GitOps cap (256Mi)")
    next_limit = limits[index + 1]
    text = set_value(text, request_path, requests[index + 1])
    text = set_value(text, limit_path, next_limit)
    detail = f"GitOps memory {current} -> {next_limit}"
else:
    current = value_of(text, replicas_path)
    if current is None or not current.isdigit():
        raise SystemExit(f"unknown replica count {current}")
    replicas = int(current)
    if replicas >= max_replicas:
        raise SystemExit(f"replicas already at GitOps cap ({max_replicas})")
    nxt = replicas + 1
    text = set_value(text, replicas_path, str(nxt))
    detail = f"GitOps replicas {replicas} -> {nxt}"

path.write_text(text)
print(detail)
PY
)"

if [[ "${KIND}" == "vertical" ]]; then
  MSG="fix(demo-app): raise memory limit via GitOps"
else
  MSG="fix(demo-app): add replica via GitOps"
fi

git add "${KUSTOMIZE}"
if git diff --cached --quiet; then
  echo "demo-app scale is already at ${DETAIL}"
  exit 0
fi
git commit -m "${MSG}"
git push origin HEAD
SHA="$(git rev-parse --short HEAD)"
echo "Pushed ${SHA} ${DETAIL}"

echo "Waiting for Argo CD to apply ${DETAIL}..."
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
  kubectl annotate application demo-app -n argocd argocd.argoproj.io/refresh=hard --overwrite >/dev/null 2>&1 || true
  live_replicas="$(kubectl get deploy "${DEPLOY}" -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || true)"
  live_memory="$(kubectl get deploy "${DEPLOY}" -n "${NS}" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null || true)"
  if [[ "${KIND}" == "vertical" && "${DETAIL}" == *"-> ${live_memory}" ]]; then
    echo "demo-app memory is live from commit ${SHA} (${DETAIL})"
    exit 0
  fi
  if [[ "${KIND}" == "horizontal" && "${DETAIL}" == *"-> ${live_replicas}" ]]; then
    echo "demo-app replicas are live from commit ${SHA} (${DETAIL})"
    exit 0
  fi
  sleep 5
done

echo "Timed out waiting for Argo CD to apply ${DETAIL}" >&2
kubectl get deploy "${DEPLOY}" -n "${NS}" -o jsonpath='replicas={.spec.replicas} memory={.spec.template.spec.containers[0].resources.limits.memory}{"\n"}' >&2 || true
exit 1
