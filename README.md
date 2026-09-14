# AIOps Rollback Demo

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/brucorreia/aiops-observability-demo)](https://github.com/brucorreia/aiops-observability-demo/releases)
[![demo-app](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/demo-app.yaml/badge.svg)](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/demo-app.yaml)
[![ai-agent](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/ai-agent.yaml/badge.svg)](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/ai-agent.yaml)
[![load-generator](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/load-generator.yaml/badge.svg)](https://github.com/brucorreia/aiops-observability-demo/actions/workflows/load-generator.yaml)

A reproducible Kubernetes demo where firing alerts go to an agent that scores OOMKilled and HTTP 500 logs (CrashLoopBackOff remains available via `make`). The console Execute button applies rollback or scale; automatic remediation stays off until `AUTOMATIC_EXECUTION_ALLOWED=true`. The scores are a prioritization from collected evidence, not mathematical certainty.

HTTP 500 is detected only from application stdout. There is no `demo_http_requests_total` metric and no PromQL 5xx rule.

More detail: [docs/architecture.md](docs/architecture.md), [docs/scoring.md](docs/scoring.md), [docs/demo-script.md](docs/demo-script.md).

## What you will run

| Mode | Console / command | Signal |
| --- | --- | --- |
| `crashloop` | CrashLoop on the console (cause is hidden) | kube-state-metrics `CrashLoopBackOff` or `OOMKilled` |
| `oom` | `make demo-oom` | kube-state-metrics `OOMKilled` + cAdvisor memory |
| `http500` | `make demo-500` | VictoriaLogs LogsQL on stdout JSON |

`make run` deletes and recreates the k3d cluster named `aiops`, installs Argo CD and VictoriaMetrics/VictoriaLogs `0.85.0`, and lets Argo CD sync **three Applications** (`demo-app`, `ai-agent`, `load-generator`) from GitHub. Each app has its own GitHub Actions pipeline and image tag.

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
- Python 3.12+ (`python3` on PATH) for `make test`
- An OpenAI-compatible API key for the agent to score incidents (`OPENAI_API_KEY`)

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

The cluster boots without a `.env`, but the agent **cannot score** until `OPENAI_API_KEY` is in Secret `ai-agent-llm`. Copy the example and load it:

```bash
cp .env.example .env
```

Useful keys in `.env.example`:

- `RECENT_DEPLOYMENT_WINDOW_MINUTES=15` — what counts as a recent Deployment revision
- `AUTOMATIC_EXECUTION_ALLOWED=false` — keep remediation manual (console Execute). Set `true` to auto-apply rollback/scale after a scored firing alert
- `OPENAI_API_KEY` — required for scoring; without it the agent returns `llm_unavailable`
- `OPENAI_MODEL` — default `gpt-4o-mini`
- `GITHUB_TOKEN` — optional if GitHub rate-limits anonymous commit lookups

Load the key into the cluster without committing it:

```bash
cp .env.example .env
# edit OPENAI_API_KEY
make llm-secret
```

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
make deploy        # Argo CD Applications for demo-app, ai-agent, load-generator
```

Expect several minutes. Helm `--wait` for the monitoring stack can take up to 10 minutes on the first run.

If `make cluster` fails because `aiops` already exists:

```bash
make clean
make run
```

### What each step does

**cluster.** Deletes any existing k3d cluster named `aiops`, creates 1 server + 1 agent from `cluster/k3d.yaml`, publishes `localhost:8080` → the k3d load balancer, and writes `.kube/config` with a single context `k3d-aiops`. Every `make run` starts this cluster from scratch so Argo CD cannot keep a stale local Application.

**argocd.** Installs Argo CD in namespace `argocd`. Three Applications auto-sync independent Git paths: `infra/apps/demo-app`, `infra/apps/ai-agent`, and `infra/apps/load-generator`. `make argocd-ui` port-forwards http://localhost:8088 (user `admin`).

**monitoring.** Adds the VictoriaMetrics Helm repo and installs release `vmks` in namespace `monitoring` with `monitoring/values-common.yaml` + `monitoring/values-local.yaml` (`local-path` PVCs, 1 Gi, 1 day retention, no Grafana).

**deploy.** Applies the Argo CD AppProject and the three Applications, then waits until each is Synced/Healthy. Incidents are git commits of `apps/demo-app/demo_mode`, then Argo CD rolls the new image.

This is a monorepo with isolated pipelines:

| Change in | Workflow | Argo Application | Rolls |
| --- | --- | --- | --- |
| `apps/demo-app/**` | `demo-app.yaml` | `demo-app` | only `demo-app` image tag |
| `agent/**` or `config/scoring.yaml` | `ai-agent.yaml` | `ai-agent` | only `ai-agent` image tag |
| `load-generator/**` | `load-generator.yaml` (validate) | `load-generator` | only the curl generator |

Each image workflow publishes `linux/amd64` and `linux/arm64` to `ghcr.io/<owner>/<image>:<sha>` (no `latest`) and commits **only that app's** `infra/apps/<app>/kustomization.yaml`. Until the matching pipeline has succeeded, that app may stay `ImagePullBackOff`.

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

`demo-app` starts in `DEMO_MODE=good` (`/health` and `/api` return 200). `/api` returns a new `pedido`, `produto`, and `valor` (R$ 1.00–350.00) on every request so the console checkout feed stays live.

## 9. Run the incidents

Use three terminals if you want live output: commands, `make agent-logs`, `make app-logs`.

Wait until pods are Ready before switching modes. Open `make console` (http://localhost:8082) for the operator UI: **CrashLoop** and **Saudável**. CrashLoop randomly bakes either a silent startup exit or an OOM leak; the console does not say which. The AI column appears after the alert and names the cause with a scored action. Remediation is manual unless `AUTOMATIC_EXECUTION_ALLOWED` is true.

```bash
source .kube/env
make console      # operator UI; CrashLoop commits a surprise GitOps incident
make agent-logs   # scores; execution stays skipped while the flag is false
```

`make demo-oom`, `make demo-crashloop`, and `make demo-500` still exist for an explicit talk, but they are not on the console.

## 10. Inspect telemetry

Each port-forward occupies a terminal until you stop it with Ctrl+C.

```bash
source .kube/env

make vmalert          # http://localhost:8081/vmalert/alerts
make alertmanager     # http://localhost:9093
make victorialogs     # http://localhost:9428
make console          # http://localhost:8082 operator UI (Kube Sentinel)
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

`monitoring/values-homelab.yaml` uses Longhorn instead of `local-path`. Image tags on GitHub are already set by the per-app workflows; a homelab that also runs Argo CD will pick them up from `infra/apps/<app>`.

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
.github/workflows/   One pipeline per app (demo-app, ai-agent, load-generator)
apps/demo-app/       Demo API
agent/               Collectors, enrichment, LLM scoring, API
cluster/             k3d
infra/argocd/        Three Argo CD Applications
infra/apps/<app>/    Image tags Argo syncs per app
deploy/demo-app/     demo-app manifests
deploy/ai-agent/     ai-agent manifests + scoring ConfigMap
load-generator/      Traffic for log-based HTTP 500
monitoring/          VictoriaMetrics k8s-stack 0.85.0 values
config/scoring.yaml  Playbook hints for the LLM (not live scores)
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
| Images `ImagePullBackOff` | Wait for the matching app workflow and for that Argo CD Application to be Synced. Make the GHCR packages public (or add a pull secret). |
| Argo CD cannot fetch the repo | The GitHub remote must exist. A private repo needs an Argo CD repository credential |
| `make argocd-ui` | http://localhost:8088 — user `admin`, password from `argocd-initial-admin-secret` |
| `demo-crashloop` rollout never Ready | Expected for that make target; it is not on the console |
| HTTP 500 alert does not fire | Confirm load-generator is running and wait 15–40 s; `/health` stays 200 on purpose |
| Agent log shows `llm_unavailable` | Set `OPENAI_API_KEY` in `.env` and run `make llm-secret` |

`make help` lists every target.

## License

This project is licensed under the [MIT License](LICENSE).
