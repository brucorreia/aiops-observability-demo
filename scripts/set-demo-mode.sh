#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$ROOT/.kube/config}"

MODE="${1:?mode required (good|crashloop|oom|http500)}"
STALE="${2:-}"
NS="${DEMO_NS:-aiops-demo}"
DEPLOY="${DEPLOY_NAME:-demo-app}"
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
if [[ -n "$STALE" ]]; then
  DEPLOYED_AT="$STALE"
else
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi
IMAGE="$(kubectl get deploy/"$DEPLOY" -n "$NS" -o jsonpath='{.spec.template.spec.containers[0].image}')"

kubectl patch deployment "$DEPLOY" -n "$NS" --type=strategic -p "$(cat <<EOF
{
  "metadata": {
    "annotations": {
      "aiops.demo/git-sha": "$SHA",
      "aiops.demo/deployed-at": "$DEPLOYED_AT",
      "aiops.demo/image": "$IMAGE",
      "kubernetes.io/change-cause": "DEMO_MODE=$MODE sha=$SHA at $DEPLOYED_AT"
    }
  },
  "spec": {
    "template": {
      "metadata": {
        "annotations": {
          "aiops.demo/git-sha": "$SHA",
          "aiops.demo/deployed-at": "$DEPLOYED_AT",
          "aiops.demo/image": "$IMAGE"
        }
      },
      "spec": {
        "containers": [
          {
            "name": "demo-app",
            "env": [
              {"name": "DEMO_MODE", "value": "$MODE"}
            ]
          }
        ]
      }
    }
  }
}
EOF
)"

echo "Patched $DEPLOY DEMO_MODE=$MODE deployed-at=$DEPLOYED_AT sha=$SHA"
if [[ "$MODE" != "crashloop" ]]; then
  kubectl rollout status deployment/"$DEPLOY" -n "$NS" --timeout=120s
fi
