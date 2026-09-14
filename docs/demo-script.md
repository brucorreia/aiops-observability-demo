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

Open http://localhost:8082. The console has **CrashLoop** and **Saudável**. The AI column stays hidden until a cluster problem is identified.

Click **CrashLoop**. That commit does not say whether the image will die on startup (`os._exit(1)`, no app log) or leak until the 32Mi cgroup kills it (`OOMKilled`). The operator sees CrashLoopBackOff. After the alert, the agent classifies the termination reason and scores rollback vs vertical scale vs investigate.

Watch `make agent-logs`. Each incident **commits and pushes** `apps/demo-app/demo_mode`, waits for the `demo-app` image workflow, then Argo CD rolls the new image. Alerts fire on their own (about 15–40 seconds after that roll). The agent scores the webhook and **does not** apply rollback or scale while `AUTOMATIC_EXECUTION_ALLOWED=false`. Use Execute on the console if you want to apply the recommendation.

The checkout card polls `/api` every second. The amount grows R$ 7.00 per second from process start, then goes blank when the pod cannot stay Ready.

The working tree must be clean. First run takes about a minute (GHCR build).

## Lecture output

The agent prints on stdout when the alert arrives. Expect either `INCIDENTE: OOMKilled` (memory) or `INCIDENTE: CrashLoopBackOff` (startup Error), with scores that follow the evidence:

```text
{"event": "recommendation_score", "recommended_action": "rollback", "scores": {"rollback": 80, ...}}
INCIDENTE: OOMKilled
...
AÇÃO RECOMENDADA: rollback
{"event": "automatic_execution_skipped", "reason": "automatic_execution_disabled"}
```

Flip `AUTOMATIC_EXECUTION_ALLOWED` to `true` (Deployment env + scoring YAML) to demonstrate automatic rollback/scale instead of the skipped event.

`make demo-oom`, `make demo-crashloop`, and `make demo-500` remain for an explicit walkthrough off the console.
