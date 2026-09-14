# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- LLM-only `recommendation_score` from logs, commits, and cluster evidence (YAML weights are hints, not the live score)
- Optional Secret `ai-agent-llm` from `.env` via `make llm-secret`
- Isolated GitHub Actions + Argo CD Applications for `demo-app`, `ai-agent`, and `load-generator`
- Automatic scoring and rollback/scale when Alertmanager delivers a firing alert (no on-demand `make analyze`)
- Demo incidents are git commits of `apps/demo-app/demo_mode` followed by a real GitOps image roll
- Operator console at `make console` (http://localhost:8082): live demo-app, GitOps incident buttons, scores, and execute
- CrashLoopBackOff exits the process with no app log; OOMKilled fills RSS against a 32Mi cgroup limit; HTTP 500 remains a stdout signal
- `demo-app` `/api` returns a new checkout order each request (product + R$ 1.00–350.00)
- Console CrashLoop button hides the cause (OOM or startup Error); the LLM classifies from Kubernetes evidence and scores the action
- The AI column opens only after clicking a problematic workload
- Remediation stays manual (`AUTOMATIC_EXECUTION_ALLOWED=false`) until that flag is flipped

## [0.1.2] - 2026-09-14

### Fixed

- GHCR short tags match Argo CD (`bc84c53` instead of `sha-bc84c53`) so k3d can pull the published image

## [0.1.1] - 2026-09-14

### Fixed

- `make run` recreates the k3d cluster so Argo CD always syncs image tags from GitHub

## [0.1.0] - 2026-09-14

### Added

- Reproducible k3d demo for CrashLoopBackOff, OOMKilled, and log-based HTTP 500
- Agent that scores rollback, scale, and investigate options from collected evidence, without automatic execution
- Argo CD GitOps path whose image tags are published to GHCR by GitHub Actions

[0.1.2]: https://github.com/brucorreia/aiops-observability-demo/releases/tag/v0.1.2
[0.1.1]: https://github.com/brucorreia/aiops-observability-demo/releases/tag/v0.1.1
[0.1.0]: https://github.com/brucorreia/aiops-observability-demo/releases/tag/v0.1.0
