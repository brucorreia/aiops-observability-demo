#!/usr/bin/env bash
set -euo pipefail

NS="${ARGO_NS:-argocd}"
TIMEOUT="${ARGO_WAIT_SECONDS:-600}"
APPS="${ARGO_APPS:-demo-app ai-agent load-generator}"

wait_one() {
  local app="$1"
  kubectl annotate application "${app}" -n "${NS}" argocd.argoproj.io/refresh=hard --overwrite >/dev/null
  local start="${SECONDS}"
  local sync="" health=""
  while (( SECONDS - start < TIMEOUT )); do
    sync="$(kubectl get application "${app}" -n "${NS}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)"
    health="$(kubectl get application "${app}" -n "${NS}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)"
    if [[ "${sync}" == "Synced" && "${health}" == "Healthy" ]]; then
      echo "Argo CD application ${app} is Synced/Healthy"
      return 0
    fi
    sleep 3
  done
  echo "Timed out waiting for Argo CD application ${app} (sync=${sync:-unknown} health=${health:-unknown})"
  kubectl get application "${app}" -n "${NS}" -o yaml | sed -n '/^status:/,$p' | head -n 80
  return 1
}

failed=0
for app in ${APPS}; do
  wait_one "${app}" || failed=1
done
exit "${failed}"
