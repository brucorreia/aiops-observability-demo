# Scoring

`recommendation_score` is a prioritization from the evidence that was actually collected. It is not a probability and not mathematical certainty.

Final scores are integers in `[0, 100]` and always sum to `100`. Negative weights exist only in `config/scoring.yaml`; they are clipped before normalization.

## Two layers

1. **Deterministic.** `agent/scoring/signals.py` turns enrichment into booleans. `agent/scoring/engine.py` applies the YAML weights.
2. **LLM (optional).** If `OPENAI_API_KEY` is set, the model may shift each action by at most `llm.max_adjustment` points. It receives only collected evidence and must not invent metrics, deploys, or logs. With no key, this layer is skipped.

## Temporal rule

`RECENT_DEPLOYMENT_WINDOW_MINUTES` (default `15`) uses `aiops.demo/deployed-at` and ReplicaSet revision metadata. Pod start time is ignored because restarts and reschedules also create new pods.

| Incident | Recent recorded deploy | Preference |
| --- | --- | --- |
| OOM | yes | rollback |
| OOM | no | vertical scale / investigate |
| OOM + traffic + stable per-request memory | either | horizontal scale can rise |
| OOM + rising memory per process | either | horizontal scale stays low |
| CrashLoop | yes | rollback very high |
| CrashLoop | no | investigate |
| HTTP 500 + Ready pods | yes | rollback |
| HTTP 500 + timeout/upstream logs | no | investigate |
| HTTP 500 + CPU saturation + traffic | either | horizontal scale can rise |

## Quality

Each analysis includes:

```json
{
  "score_quality": "high | medium | low",
  "missing_evidence": [{"evidence": "previous_version_memory", "status": "unavailable"}],
  "conflicting_evidence": []
}
```

Missing evidence lowers score quality and raises `investigate` / `none`. The agent never fills gaps with invented values.
