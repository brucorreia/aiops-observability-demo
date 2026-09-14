SHELL := /bin/bash
.DEFAULT_GOAL := help

CLUSTER := aiops
KUBECONFIG_FILE := $(CURDIR)/.kube/config
KUBE_ENV_FILE := $(CURDIR)/.kube/env
export KUBECONFIG := $(KUBECONFIG_FILE)
VM_CHART_VERSION := 0.85.0
VM_RELEASE := vmks
MONITORING_NS := monitoring
DEMO_NS := aiops-demo
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_URL := $(shell git remote get-url origin 2>/dev/null || echo "")
IMAGE_OWNER ?= $(shell git remote get-url origin 2>/dev/null | awk -F'[:/]' '{print $$(NF-1)}')
IMAGE_TAG ?= $(GIT_SHA)
APP_IMAGE := ghcr.io/$(IMAGE_OWNER)/aiops-demo-app:$(IMAGE_TAG)
AGENT_IMAGE := ghcr.io/$(IMAGE_OWNER)/aiops-agent:$(IMAGE_TAG)
KUSTOMIZE_HOMELAB := $(CURDIR)/.kube/kustomize-homelab
ARGO_CHART_VERSION := 10.9.0
ARGO_RELEASE := argocd
ARGO_NS := argocd
STALE_DEPLOY ?= 2026-01-01T00:00:00Z

.PHONY: help tools doctor setup bootstrap run stop kube-env cluster argocd argocd-ui build monitoring deploy deploy-homelab setup-local \
	demo-good demo-crashloop demo-oom demo-oom-stale demo-500 \
	recommendations rollback status \
	app-logs agent-logs victorialogs vmalert alertmanager llm-secret test clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

tools: ## Verify CLI prerequisites and print versions (no Docker daemon required)
	@failed=0; \
	for cmd in docker kubectl helm k3d python3; do \
	  if ! command -v $$cmd >/dev/null; then echo "Missing: $$cmd"; failed=1; fi; \
	done; \
	if [ $$failed -ne 0 ]; then exit 1; fi
	@echo "docker    $$(docker --version)"
	@echo "kubectl   $$(kubectl version --client --short 2>/dev/null || kubectl version --client | head -n 1)"
	@echo "helm      $$(helm version --short)"
	@echo "k3d       $$(k3d version | head -n 1)"
	@echo "python3   $$(python3 --version)"
	@echo "CLI tools OK"

doctor: tools ## Verify CLI tools and that the Docker daemon is reachable
	@docker info >/dev/null 2>&1 || { \
	  echo "AIOps demo could not find a running Docker daemon."; \
	  exit 1; \
	}
	@echo "Docker context: $$(docker context show)"

setup: ## Install CLI tools and verify they are on PATH
	@command -v brew >/dev/null || { echo "Missing: brew. Install Homebrew from https://brew.sh"; exit 1; }
	@if brew list --formula docker-completion >/dev/null 2>&1; then \
	  echo "Unlinking docker-completion (it conflicts with formula docker)"; \
	  brew unlink docker-completion; \
	fi
	brew bundle || { \
	  echo "Retrying docker link after completion conflict"; \
	  brew link --overwrite docker; \
	  brew bundle; \
	}
	$(MAKE) tools

bootstrap: setup

run: doctor ## Recreate the k3d stack; Argo CD syncs images from GitHub
	$(MAKE) setup-local
	@$(MAKE) --no-print-directory kube-env
	@echo
	@echo "Make cannot export KUBECONFIG into this terminal. Run:"
	@echo "  source .kube/env"
	@echo "Then kubectl talks to context k3d-$(CLUSTER)."

stop: ## Delete the k3d demo cluster; does not stop the Docker daemon
	@docker info >/dev/null 2>&1 || { \
	  echo "AIOps demo could not find a running Docker daemon."; \
	  exit 1; \
	}
	-k3d cluster delete $(CLUSTER)
	rm -f "$(KUBECONFIG_FILE)" "$(KUBE_ENV_FILE)"
	@echo "k3d cluster $(CLUSTER) removed."

setup-local: cluster argocd monitoring deploy

kube-env: ## Write .kube/env so this terminal can source KUBECONFIG
	@mkdir -p "$(dir $(KUBECONFIG_FILE))"
	@printf 'export KUBECONFIG=%q\n' "$(KUBECONFIG_FILE)" > "$(KUBE_ENV_FILE)"

cluster: doctor ## Recreate the k3d cluster with an isolated kubeconfig
	-k3d cluster delete $(CLUSTER)
	mkdir -p "$(dir $(KUBECONFIG_FILE))"
	k3d cluster create --config cluster/k3d.yaml
	k3d kubeconfig get $(CLUSTER) > "$(KUBECONFIG_FILE)"
	@test "$$(kubectl config view --kubeconfig "$(KUBECONFIG_FILE)" -o jsonpath='{.contexts[*].name}')" = "k3d-$(CLUSTER)"
	@$(MAKE) --no-print-directory kube-env
	@echo "KUBECONFIG=$(KUBECONFIG_FILE) context=$$(kubectl config current-context)"

argocd: ## Install Argo CD and wait until the API is ready
	helm repo add argo https://argoproj.github.io/argo-helm --force-update
	helm upgrade --install $(ARGO_RELEASE) argo/argo-cd \
	  --version $(ARGO_CHART_VERSION) \
	  --namespace $(ARGO_NS) --create-namespace \
	  -f infra/argocd/values.yaml \
	  --wait --timeout 10m
	kubectl wait --for=condition=Established crd/applications.argoproj.io --timeout=120s

argocd-ui: ## Port-forward the Argo CD UI to localhost:8088
	@echo "URL: http://localhost:8088  user: admin"
	@echo "Password: $$(kubectl -n $(ARGO_NS) get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
	kubectl port-forward -n $(ARGO_NS) svc/$(ARGO_RELEASE)-server 8088:80

build: ## Optional: build images locally and import them into k3d
	@test -n "$(IMAGE_OWNER)" || { echo "Could not derive GitHub owner from origin. Set IMAGE_OWNER."; exit 1; }
	docker build \
	  --build-arg GIT_SHA=$(GIT_SHA) \
	  --build-arg SOURCE_URL=$(SOURCE_URL) \
	  --build-arg BUILD_DATE=$(BUILD_DATE) \
	  --build-arg VERSION=$(GIT_SHA) \
	  -t $(APP_IMAGE) apps/demo-app
	docker build \
	  --build-arg GIT_SHA=$(GIT_SHA) \
	  --build-arg SOURCE_URL=$(SOURCE_URL) \
	  --build-arg BUILD_DATE=$(BUILD_DATE) \
	  --build-arg VERSION=$(GIT_SHA) \
	  -f agent/Dockerfile -t $(AGENT_IMAGE) .
	k3d image import -c $(CLUSTER) $(APP_IMAGE) $(AGENT_IMAGE)

monitoring: ## Install the pinned VictoriaMetrics/VictoriaLogs stack
	helm repo add vm https://victoriametrics.github.io/helm-charts/ --force-update
	helm upgrade --install $(VM_RELEASE) vm/victoria-metrics-k8s-stack \
	  --version $(VM_CHART_VERSION) \
	  --namespace $(MONITORING_NS) --create-namespace \
	  -f monitoring/values-common.yaml \
	  -f monitoring/values-local.yaml \
	  --wait --timeout 10m

deploy: ## Point Argo CD at GitHub and wait until it has synced
	-kubectl delete application aiops -n $(ARGO_NS) --ignore-not-found
	kubectl apply -k infra/argocd
	./scripts/apply-llm-secret.sh
	./scripts/wait-argocd-sync.sh
	kubectl rollout status deployment/ai-agent -n $(MONITORING_NS) --timeout=180s
	kubectl rollout status deployment/demo-app -n $(DEMO_NS) --timeout=180s

llm-secret: ## Create/update the optional OpenAI secret from .env and restart ai-agent
	./scripts/apply-llm-secret.sh

deploy-homelab: ## Apply the three GitOps apps with the tags already on GitHub
	kubectl apply -k infra/apps/demo-app
	kubectl apply -k infra/apps/ai-agent
	kubectl apply -k infra/apps/load-generator
	kubectl rollout status deployment/ai-agent -n $(MONITORING_NS) --timeout=180s
	kubectl rollout status deployment/demo-app -n $(DEMO_NS) --timeout=180s

demo-good: ## Commit+push healthy demo-app and wait for Argo CD
	./scripts/set-demo-mode.sh good

demo-crashloop: ## Commit+push CrashLoopBackOff and wait for the GitOps roll
	./scripts/set-demo-mode.sh crashloop

demo-oom: ## Commit+push OOMKilled with a recent deploy timestamp
	./scripts/set-demo-mode.sh oom

demo-oom-stale: ## Commit+push OOMKilled with an old deploy timestamp
	./scripts/set-demo-mode.sh oom $(STALE_DEPLOY)

demo-500: ## Commit+push HTTP 500 logs while /health stays green
	./scripts/set-demo-mode.sh http500

recommendations: ## Print the latest lecture-friendly recommendation from a firing alert
	kubectl exec -n $(MONITORING_NS) deploy/ai-agent -- python -m api.cli recommendations --format text

rollback: ## Undo the last demo-app rollout
	kubectl rollout undo deployment/demo-app -n $(DEMO_NS)
	kubectl rollout status deployment/demo-app -n $(DEMO_NS) --timeout=120s

status: ## Show core demo, monitoring, and Argo CD resources
	kubectl get application -n $(ARGO_NS)
	kubectl get pods,pvc -n $(MONITORING_NS)
	kubectl get pods,deploy,rs -n $(DEMO_NS)
	kubectl get vmrule -n $(MONITORING_NS)

app-logs: ## Follow demo-app stdout JSON
	kubectl logs -n $(DEMO_NS) deployment/demo-app -f

agent-logs: ## Follow agent analyses
	kubectl logs -n $(MONITORING_NS) deployment/ai-agent -f

victorialogs: ## Port-forward VictoriaLogs to localhost:9428
	kubectl port-forward -n $(MONITORING_NS) svc/vlsingle-vmks 9428:9428

vmalert: ## Port-forward VMAlert to localhost:8081
	kubectl port-forward -n $(MONITORING_NS) svc/vmalert-vmks 8081:8080

alertmanager: ## Port-forward Alertmanager to localhost:9093
	kubectl port-forward -n $(MONITORING_NS) svc/vmalertmanager-vmks 9093:9093

test: ## Run scoring and normalization unit tests
	python3 -m venv .venv
	.venv/bin/pip install -q -r agent/requirements.txt
	PYTHONPATH=agent .venv/bin/python -m unittest discover -s agent/tests -v

clean: ## Delete the local k3d cluster and its kubeconfig
	-k3d cluster delete $(CLUSTER)
	rm -f "$(KUBECONFIG_FILE)" "$(KUBE_ENV_FILE)"
