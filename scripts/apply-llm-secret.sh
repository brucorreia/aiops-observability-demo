#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS="${AGENT_NAMESPACE:-monitoring}"
ENV_FILE="${ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is empty; ai-agent will record llm_unavailable until a key is set."
  exit 0
fi

kubectl create secret generic ai-agent-llm \
  --namespace "${NS}" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --from-literal=OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}" \
  --from-literal=OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}" \
  --from-literal=GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

if kubectl get deploy ai-agent -n "${NS}" >/dev/null 2>&1; then
  kubectl rollout restart deployment/ai-agent -n "${NS}"
  kubectl rollout status deployment/ai-agent -n "${NS}" --timeout=180s
fi

echo "LLM secret applied in ${NS}/ai-agent-llm"
