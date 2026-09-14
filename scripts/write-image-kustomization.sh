#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${IMAGE_OWNER:?IMAGE_OWNER is required}"
TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
DEST="${ROOT}/.kube/kustomize-homelab"

mkdir -p "${DEST}"
cat > "${DEST}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../infra/apps/demo-app
  - ../../infra/apps/ai-agent
  - ../../infra/apps/load-generator
images:
  - name: ghcr.io/${OWNER}/aiops-demo-app
    newTag: "${TAG}"
  - name: ghcr.io/${OWNER}/aiops-agent
    newTag: "${TAG}"
EOF
echo "Wrote ${DEST}/kustomization.yaml"
