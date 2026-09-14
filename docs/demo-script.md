# Demo script

Keep three terminals: `make agent-logs`, `make app-logs`, and commands.

Do not commit files created under `docs/incidents/` during the talk.

## Setup

```bash
make setup
make run
source .kube/env
make status
```

## 1. CrashLoopBackOff after a deploy

```bash
make demo-crashloop
kubectl get pods -n aiops-demo -w
make analyze
```

Expected: `CrashLoopBackOff` from kube-state-metrics, recent `aiops.demo/deployed-at`, rollback `recommendation_score` very high.

Human approval:

```bash
make approve-rollback
```

## 2. OOM after a recent deploy

```bash
make demo-good
make demo-oom
make analyze
```

Expected: memory climbs in stdout, then `OOMKilled`. Rollback outranks vertical scale. Horizontal scale stays low because the leak is per process.

## 3. OOM without a recent deploy

```bash
make demo-oom-stale
make analyze
```

The workload still OOMs, but `aiops.demo/deployed-at` is old. Vertical scale / investigate should outrank rollback. This is the slide that shows the agent is not a lookup table.

## 4. HTTP 500 from logs

```bash
make demo-good
make demo-500
make analyze
```

`/health` stays `200`. `/api` writes JSON `status: 500` to stdout. `HighHttp5xxFromLogs` is LogsQL (`type: vlogs`), not PromQL. Rollback should lead while pods remain Ready.

## Lecture output

`make analyze` prints and saves:

```text
INCIDENTE: OOMKilled
WORKLOAD: demo-app
...
AÇÃO RECOMENDADA: rollback
EXECUÇÃO AUTOMÁTICA: desabilitada
```

JSON and Markdown land in `docs/incidents/<timestamp>-<incident-type>-<workload>.*`.
