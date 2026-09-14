#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

OWNER="${IMAGE_OWNER:?IMAGE_OWNER is required}"
TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
NAME="${IMAGE_NAME:?IMAGE_NAME is required}"
SLUG="${APP_SLUG:?APP_SLUG is required}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

attempt=1
while (( attempt <= 5 )); do
  git fetch origin main
  git checkout -B main origin/main
  IMAGE_OWNER="${OWNER}" IMAGE_TAG="${TAG}" IMAGE_NAME="${NAME}" "${ROOT}/scripts/set-image-tag.sh"
  FILE="$(
    case "${NAME}" in
      aiops-demo-app) echo infra/apps/demo-app/kustomization.yaml ;;
      aiops-agent) echo infra/apps/ai-agent/kustomization.yaml ;;
      *) echo "" ;;
    esac
  )"
  if [[ -z "${FILE}" ]]; then
    echo "Unknown IMAGE_NAME=${NAME}" >&2
    exit 1
  fi
  git add "${FILE}"
  if git diff --cached --quiet; then
    echo "Argo image tag for ${NAME} already matches ${TAG}"
    exit 0
  fi
  git commit -m "chore(${SLUG}): set image tag to ${TAG}"
  if git push origin HEAD:main; then
    exit 0
  fi
  echo "Push collided; retrying (${attempt}/5)"
  git reset --hard HEAD~1
  attempt=$((attempt + 1))
  sleep $((attempt * 2))
done

echo "Failed to push GitOps tag update for ${NAME}" >&2
exit 1
