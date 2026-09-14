# AIOps Rollback Demo

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/brucorreia/aiops-observability-demo)](https://github.com/brucorreia/aiops-observability-demo/releases)
[![Images](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/images.yaml/badge.svg)](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/images.yaml)

A reproducible Kubernetes demo where an agent investigates CrashLoopBackOff, OOMKilled, and HTTP 500 logs, then assigns a `recommendation_score` to each possible action. The scores are a prioritization from collected evidence, not mathematical certainty. Automatic execution stays off.

HTTP 500 is detected only from application stdout. There is no `demo_http_requests_total` metric and no PromQL 5xx rule.

More detail: [docs/architecture.md](docs/architecture.md), [docs/scoring.md](docs/scoring.md), [docs/demo-script.md](docs/demo-script.md).

## What you will run

| Mode | Command | Signal |
| --- | --- | --- |
| `crashloop` | `make demo-crashloop` | kube-state-metrics `CrashLoopBackOff` |
| `oom` | `make demo-oom` | kube-state-metrics `OOMKilled` + cAdvisor memory |
| `http500` | `make demo-500` | VictoriaLogs LogsQL on stdout JSON |

`make run` deletes and recreates the k3d cluster named `aiops`, installs Argo CD and VictoriaMetrics/VictoriaLogs `0.85.0`, and lets Argo CD sync the app, agent, and load generator from GitHub (`infra/apps`). Image tags are written by GitHub Actions after they publish to GHCR.

Quick start after cloning:

```bash
make setup
make run
source .kube/env
make status
```

## 1. Prerequisites

- macOS (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- A running Docker daemon (`docker info` must succeed). This repo does not start or stop Docker.
- Python 3.12+ (`python3` on PATH) for `make test` and `make analyze`
- Optional: an OpenAI-compatible API key if you want the second scoring layer

Install Homebrew if needed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Clone this repository and work from its root:

```bash
git clone git@github.com:brucorreia/aiops-observability-demo.git
cd aiops-observability-demo
```

## 2. Install and verify CLI tools

```bash
make setup
```

This installs the Brewfile (Docker CLI, kubectl, Helm, k3d) and runs `make tools` to confirm every binary is on PATH, including `python3`. It does not need Docker running. `make doctor` is the same CLI check plus a live Docker daemon.

## 3. Run the stack

With Docker already running, bring the k3d stack up:

```bash
make run
```

`make run` only requires `docker info` to succeed. First boot can take several minutes (Helm `--wait` up to 10 minutes). Make cannot export variables into your existing terminal, so when it finishes:

```bash
source .kube/env
make status
kubectl get nodes
```

## 4. Optional local config

The cluster demo does not need a `.env`. Copy the example only if you want to change windows, URLs, or enable the LLM layer:

```bash
cp .env.example .env
```

Useful keys in `.env.example`:

- `RECENT_DEPLOYMENT_WINDOW_MINUTES=15` — what counts as a recent Deployment revision
- `AUTOMATIC_EXECUTION_ALLOWED=false` — keep this false
- `OPENAI_API_KEY` — leave empty for deterministic scores only

Do not commit `.env`, tokens, or kubeconfigs.

## 5. Isolated kubeconfig

`make cluster` does **not** merge into `~/.kube/config`. It writes only the new cluster to `.kube/config` in this repo.

Every Makefile target exports:

```text
KUBECONFIG=$PWD/.kube/config
```

In a shell outside Make (kubectl, k9s, stern, and so on), source the file `make run` writes:

```bash
source .kube/env
kubectl config current-context   # must be k3d-aiops
kubectl config view --minify
```

`.kube/` is gitignored. `make clean` deletes the cluster and this file.

## 6. Validate Docker (optional)

`make run` already runs `make doctor`. To check without creating the cluster:

```bash
make doctor
```

Optional unit tests (no cluster):

```bash
make test
```

## 7. What `make run` does

`make setup-local` is the Kubernetes half of `make run` and is equivalent to:

```bash
make cluster       # delete+create k3d cluster aiops + isolated kubeconfig
make argocd        # Helm argo-cd 10.9.0
make monitoring    # Helm victoria-metrics-k8s-stack 0.85.0
make deploy        # Argo CD Application pointing at this GitHub repo
```

Expect several minutes. Helm `--wait` for the monitoring stack can take up to 10 minutes on the first run.

If `make cluster` fails because `aiops` already exists:

```bash
make clean
make run
```

### What each step does

**cluster.** Deletes any existing k3d cluster named `aiops`, creates 1 server + 1 agent from `cluster/k3d.yaml`, publishes `localhost:8080` → the k3d load balancer, and writes `.kube/config` with a single context `k3d-aiops`. Every `make run` starts this cluster from scratch so Argo CD cannot keep a stale local Application.

**argocd.** Installs Argo CD in namespace `argocd`. The application `aiops` auto-syncs `infra/apps` from `https://github.com/brucorreia/aiops-observability-demo.git`. `make argocd-ui` port-forwards http://localhost:8088 (user `admin`).

**monitoring.** Adds the VictoriaMetrics Helm repo and installs release `vmks` in namespace `monitoring` with `monitoring/values-common.yaml` + `monitoring/values-local.yaml` (`local-path` PVCs, 1 Gi, 1 day retention, no Grafana).

**deploy.** Applies the Argo CD Application/AppProject and waits until the cluster matches `infra/apps` on GitHub. Incident commands (`make demo-crashloop` and the others) still patch `DEMO_MODE` in-cluster; Argo ignores those fields so it does not revert the demo.

A push to `main` that changes the app or agent runs `.github/workflows/images.yaml`: it publishes `linux/amd64` and `linux/arm64` images `ghcr.io/<owner>/aiops-demo-app:<sha>` and `ghcr.io/<owner>/aiops-agent:<sha>` (no `latest`), then commits the new tags into `infra/apps/kustomization.yaml`. Argo CD sees that commit and rolls the cluster. Until that pipeline has succeeded, pods may stay `ImagePullBackOff`.

## 8. Confirm the cluster

```bash
source .kube/env
make status
```

You should see:

- Namespace `monitoring`: VictoriaMetrics, VictoriaLogs, VMAgent, VLAgent, VMAlert, Alertmanager, kube-state-metrics, `ai-agent`
- Namespace `aiops-demo`: `demo-app` Running/Ready, `load-generator` Running
- PVCs for VMSingle and VLSingle Bound
- VMRules including `ContainerCrashLoopBackOff`, `ContainerOOMKilled`, `ContainerMemoryUsageHigh`, `HighHttp5xxFromLogs`

```bash
kubectl get pods -n monitoring
kubectl get pods -n aiops-demo
kubectl get pvc -n monitoring
kubectl get vmrule -n monitoring
```

`demo-app` starts in `DEMO_MODE=good` (`/health` and `/api` return 200).

## 9. Run the incidents

Use three terminals if you want live output: commands, `make agent-logs`, `make app-logs`.

Wait until pods are Ready before switching modes. After `demo-crashloop` the app will not become Ready; that is expected.

```bash
source .kube/env

# 1. CrashLoopBackOff after a recorded deploy
make demo-crashloop
kubectl get pods -n aiops-demo -w
make analyze
make approve-rollback          # or: make rollback

# 2. OOM after a recent deploy (rollback should outrank vertical scale)
make demo-good
make demo-oom
make analyze

# 3. Same OOM, old deploy annotation (vertical scale / investigate should lead)
make demo-oom-stale
make analyze

# 4. HTTP 500 from logs; /health stays 200
make demo-good
make demo-500
make analyze
make approve-rollback
```

`make analyze` talks to the in-cluster agent, prints the lecture text, and writes:

```text
docs/incidents/<timestamp>-<incident-type>-<workload>.json
docs/incidents/<timestamp>-<incident-type>-<workload>.md
```

Do not commit those files during a demo.

Alerts need a short window (about 30–60 seconds) after the fault is visible. If `make analyze` runs too early, wait and run it again.

## 10. Inspect telemetry

Each port-forward occupies a terminal until you stop it with Ctrl+C.

```bash
source .kube/env

make vmalert          # http://localhost:8081/vmalert/alerts
make alertmanager     # http://localhost:9093
make victorialogs     # http://localhost:9428
make recommendations  # latest lecture-style recommendation
make agent-logs
make app-logs
```

## 11. Tear down

```bash
make stop
```

This deletes the k3d cluster `aiops` and `.kube/config`. The Docker daemon is left running. To start the demo over:

```bash
make stop
make run
```

## Homelab

`monitoring/values-homelab.yaml` uses Longhorn instead of `local-path`. Image tags on GitHub are already set by the `images` workflow; a homelab that also runs Argo CD will pick them up from `infra/apps`.

To apply without Argo:

```bash
export KUBECONFIG=/path/to/homelab.kubeconfig
helm repo add vm https://victoriametrics.github.io/helm-charts/ --force-update
helm upgrade --install vmks vm/victoria-metrics-k8s-stack \
  --version 0.85.0 -n monitoring --create-namespace \
  -f monitoring/values-common.yaml \
  -f monitoring/values-homelab.yaml
make deploy-homelab
```

## Layout

```text
.github/workflows/   GHCR multi-arch builds + Argo image-tag commit
apps/demo-app/       Demo API
agent/               Collectors, enrichment, scoring, API
cluster/             k3d
infra/               Argo CD app + the image tags Argo syncs
deploy/              Kustomize base + local/homelab overlays
load-generator/      Traffic for log-based HTTP 500
monitoring/          VictoriaMetrics k8s-stack 0.85.0 values
config/scoring.yaml  Weights
docs/                Architecture, scoring, talk script, incident output
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `brew bundle` fails linking `etc/bash_completion.d/docker` | `make setup` unlinks `docker-completion` (it conflicts with formula `docker`) and retries `brew link --overwrite docker` |
| `make doctor`: `AIOps demo could not find a running Docker daemon.` | `docker info` failed; start Docker and retry |
| `k3d cluster create` / cluster exists | `make clean` then `make run` |
| `kubectl` talks to another cluster | `source .kube/env` and confirm context `k3d-aiops` |
| Helm timeout | `make status`; retry `make monitoring`. First install is slow. |
| Images `ImagePullBackOff` | Wait for the `images` Action to finish and for Argo CD `aiops` to be Synced. Make the GHCR packages public (or add a pull secret). |
| Argo CD cannot fetch the repo | The GitHub remote must exist. A private repo needs an Argo CD repository credential |
| `make argocd-ui` | http://localhost:8088 — user `admin`, password from `argocd-initial-admin-secret` |
| `demo-crashloop` rollout never Ready | Expected. Use `kubectl get pods -n aiops-demo` and `make analyze`. |
| HTTP 500 alert does not fire | Confirm load-generator is running and wait 30–60 s; `/health` stays 200 on purpose |
| `make analyze` with empty evidence | Wait for the alert and metrics/logs to arrive, then rerun |

`make help` lists every target.

## License

This project is licensed under the [MIT License](LICENSE).
