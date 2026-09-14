#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAY="${1:?overlay required (local|homelab)}"
OWNER="${IMAGE_OWNER:?IMAGE_OWNER is required}"
TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
APP_IMAGE="ghcr.io/${OWNER}/aiops-demo-app:${TAG}"
AGENT_IMAGE="ghcr.io/${OWNER}/aiops-agent:${TAG}"
DEST="${ROOT}/.kube/kustomize-${OVERLAY}"

mkdir -p "${DEST}"
cat > "${DEST}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../deploy/overlays/${OVERLAY}
images:
  - name: aiops-demo-app
    newName: ghcr.io/${OWNER}/aiops-demo-app
    newTag: "${TAG}"
  - name: aiops-agent
    newName: ghcr.io/${OWNER}/aiops-agent
    newTag: "${TAG}"
patches:
  - target:
      kind: Deployment
      name: demo-app
    patch: |-
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: demo-app
        annotations:
          aiops.demo/git-sha: "${TAG}"
          aiops.demo/image: "${APP_IMAGE}"
      spec:
        template:
          metadata:
            annotations:
              aiops.demo/git-sha: "${TAG}"
              aiops.demo/image: "${APP_IMAGE}"
EOF
