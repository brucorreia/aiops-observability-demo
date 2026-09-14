# Scoring

`recommendation_score` is assigned **only by the LLM** from evidence that was actually collected (logs, commits, Kubernetes, metrics). It is not a probability and not mathematical certainty.

YAML in `config/scoring.yaml` is an optional playbook hint sent to the model. It is not applied as the live score.

Final scores are integers in `[0, 100]` and always sum to `100`.

## LLM only

The agent sends collected logs, Kubernetes evidence, and recent GitHub commits to an OpenAI-compatible chat API. The model assigns the five `recommendation_score` values. It must cite log events and commit SHAs and must not invent evidence.

If `OPENAI_API_KEY` is missing or the model call fails, the agent does **not** fall back to YAML weights. It records `scoring_source: llm_unavailable`, prefers `investigate`, and keeps rollback/scale at 0.

Put `OPENAI_API_KEY` in `.env` and run `make llm-secret` (also invoked by `make deploy`). The key lives in Secret `monitoring/ai-agent-llm`, not in Git. `OPENAI_MODEL` defaults to `gpt-4o-mini`; set `gpt-4o` if you want a stronger model.

## Temporal rule

The table below is the playbook the model receives as hints, not a lookup table executed in Python.

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
