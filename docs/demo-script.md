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

Watch `make agent-logs`. Each `make demo-*` **commits and pushes** a change to `apps/demo-app/demo_mode`, waits for the `demo-app` image workflow, then Argo CD rolls the new image. Alerts fire on their own (about 15–40 seconds after that roll). The agent scores the webhook and applies rollback or scale when the LLM recommends it.

The working tree must be clean. First run takes about a minute (GHCR build).

## 1. CrashLoopBackOff after a deploy

```bash
make demo-crashloop
kubectl get pods -n aiops-demo -w
```

Expected: `CrashLoopBackOff` from kube-state-metrics, then a firing alert, then stdout on `ai-agent` with `recommendation_score` and `automatic_execution`.

## 2. OOM after a recent deploy

```bash
make demo-good
make demo-oom
```

Expected: memory climbs in stdout, then `OOMKilled`, then the agent scores and acts.

## 3. OOM without a recent deploy

```bash
make demo-oom-stale
```

The workload still OOMs, but `aiops.demo/deployed-at` is old. Vertical scale / investigate should outrank rollback.

## 4. HTTP 500 from logs

```bash
make demo-good
make demo-500
```

`/health` stays `200`. `/api` writes JSON `status: 500` to stdout. `HighHttp5xxFromLogs` is LogsQL (`type: vlogs`), not PromQL.

## Lecture output

The agent prints on stdout when the alert arrives:

```text
{"event": "recommendation_score", "recommended_action": "rollback", "scores": {"rollback": 80, ...}}
INCIDENTE: OOMKilled
...
AÇÃO RECOMENDADA: rollback
{"event": "automatic_execution", "decision": "approve_rollback", "executed": true}
```
