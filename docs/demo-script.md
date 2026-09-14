# Demo script

Keep three terminals: `make console`, `make agent-logs`, and commands.

Do not commit files created under `docs/incidents/` during the talk.

## Setup

```bash
make setup
make run
source .kube/env
make status
make console
```

Open http://localhost:8082. The console has OOM recente, OOM antigo, HTTP 500, and Saudável. The AI column stays hidden until a cluster problem is identified.

Watch `make agent-logs`. Each incident **commits and pushes** a change to `apps/demo-app/demo_mode`, waits for the `demo-app` image workflow, then Argo CD rolls the new image. Alerts fire on their own (about 15–40 seconds after that roll). The agent scores the webhook and **does not** apply rollback or scale while `AUTOMATIC_EXECUTION_ALLOWED=false`. Use Execute on the console if you want to apply the recommendation.

The checkout card polls `/api` every second. The amount grows R$ 7.00 per second from process start.

The working tree must be clean. First run takes about a minute (GHCR build).

## 1. OOM after a recent deploy

```bash
make demo-oom
```

Or click **OOM recente** on the console.

Expected: memory climbs, then `OOMKilled`, `/health` stops responding, the AI panel appears after the alert, and stdout on `ai-agent` shows `recommendation_score` plus `automatic_execution_skipped` with `reason: automatic_execution_disabled`.

## 2. OOM without a recent deploy

```bash
make demo-oom-stale
```

Or click **OOM antigo**. The workload still OOMs, but `aiops.demo/deployed-at` is old. Vertical scale / investigate should outrank rollback.

## 3. HTTP 500 from logs

```bash
make demo-good
make demo-500
```

Or click **HTTP 500**. `/health` stays `200`. `/api` writes JSON `status: 500` to stdout and still increments `checkout_reais`. `HighHttp5xxFromLogs` is LogsQL (`type: vlogs`), not PromQL.

## Lecture output

The agent prints on stdout when the alert arrives:

```text
{"event": "recommendation_score", "recommended_action": "rollback", "scores": {"rollback": 80, ...}}
INCIDENTE: OOMKilled
...
AÇÃO RECOMENDADA: rollback
{"event": "automatic_execution_skipped", "reason": "automatic_execution_disabled"}
```

Flip `AUTOMATIC_EXECUTION_ALLOWED` to `true` (Deployment env + scoring YAML) to demonstrate automatic rollback/scale instead of the skipped event.
