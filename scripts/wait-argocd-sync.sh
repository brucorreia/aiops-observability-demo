#!/usr/bin/env bash
set -euo pipefail

NS="${ARGO_NS:-argocd}"
APP="${ARGO_APP:-aiops}"
TIMEOUT="${ARGO_WAIT_SECONDS:-600}"

kubectl annotate application "${APP}" -n "${NS}" argocd.argoproj.io/refresh=hard --overwrite >/dev/null

deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  sync="$(kubectl get application "${APP}" -n "${NS}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)"
  health="$(kubectl get application "${APP}" -n "${NS}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)"
  if [[ "${sync}" == "Synced" && "${health}" == "Healthy" ]]; then
    echo "Argo CD application ${APP} is Synced/Healthy"
    exit 0
  fi
  sleep 3
done

echo "Timed out waiting for Argo CD application ${APP} (sync=${sync:-unknown} health=${health:-unknown})"
kubectl get application "${APP}" -n "${NS}" -o yaml | sed -n '/^status:/,$p' | head -n 80
exit 1
