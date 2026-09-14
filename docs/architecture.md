# Architecture

The demo is a small Kubernetes AIOps loop: three synthetic incidents, one telemetry path, and an agent that scores remediation options instead of binding each alert to a fixed action.

```text
CrashLoopBackOff / OOMKilled / resource pressure
    → kube-state-metrics + cAdvisor
    → VMAgent
    → VictoriaMetrics
    → VMAlert

HTTP 500 and exceptions
    → stdout JSON
    → VLAgent (aiops-demo only)
    → VictoriaLogs
    → VMAlert with LogsQL (group type: vlogs)

VMAlert
    → Alertmanager
    → ai-agent
    → collect context
    → score alternatives
    → recommend
    → automatic rollback or scale
```

## Workloads

- `apps/demo-app` exposes `/health` and `/api`. `DEMO_MODE` selects `good`, `crashloop`, `oom`, or `http500`. There is no custom HTTP Prometheus metric.
- `load-generator` calls `/api` once per second so log-based HTTP 500 alerts have volume.
- `agent` receives Alertmanager webhooks, enriches from Kubernetes, VictoriaMetrics, VictoriaLogs, and GitHub commits, then scores **only with the LLM**. Without an API key it records `llm_unavailable` and does not recommend rollback or scale.

## Deploy identity

A new pod is not treated as a deploy. Pipelines and `scripts/set-demo-mode.sh` write:

- `aiops.demo/git-sha`
- `aiops.demo/deployed-at`
- `aiops.demo/image`
- `kubernetes.io/change-cause`

The agent also reads ReplicaSet `deployment.kubernetes.io/revision`, current and previous images, and `DEMO_MODE` on those revisions.

## GitOps

Each image workflow builds one GHCR image and commits **only that app's** tag under `infra/apps/<app>/kustomization.yaml`. Argo CD Applications `demo-app`, `ai-agent`, and `load-generator` watch those paths independently. `DEMO_MODE` patches from the demo scripts are ignored on `demo-app` so a talk incident is not reverted.

Local and GHCR images carry OCI labels:

- `org.opencontainers.image.source`
- `org.opencontainers.image.revision`
- `org.opencontainers.image.created`
- `org.opencontainers.image.version`

## Agent pipeline

1. **Receive** Alertmanager JSON and normalize `incident_type`.
2. **Enrich** Deployment, ReplicaSets, pods, events, metrics, application logs, and recent GitHub commits (compare current vs previous image SHA). Missing data is marked `status: unavailable`.
3. **Hypothesize** regression, leak, low limit, load, dependency, config, or infrastructure.
4. **Score** only with the LLM (logs + commits + cluster evidence). YAML weights are hints, not the score. If the LLM is unavailable, the agent recommends investigate and does not roll back or scale.
5. **Recommend** actions whose `recommendation_score` values sum to 100.
6. **Execute** the recommended rollback or scale automatically when the LLM scored a firing Alertmanager alert. `investigate` and `none` do not change the cluster. If the LLM is unavailable, nothing is applied.

## Storage

VictoriaMetrics and VictoriaLogs run as single-node CRs from `victoria-metrics-k8s-stack` `0.85.0`: 1 day retention, `1Gi` PVCs, `local-path` on k3d, `longhorn` on the homelab, no Grafana.
