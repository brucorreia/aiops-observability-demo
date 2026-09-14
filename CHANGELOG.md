# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-09-14

### Fixed

- `make run` recreates the k3d cluster so Argo CD always syncs image tags from GitHub

## [0.1.0] - 2026-09-14

### Added

- Reproducible k3d demo for CrashLoopBackOff, OOMKilled, and log-based HTTP 500
- Agent that scores rollback, scale, and investigate options from collected evidence, without automatic execution
- Argo CD GitOps path whose image tags are published to GHCR by GitHub Actions

[0.1.1]: https://github.com/brucorreia/aiops-observability-demo/releases/tag/v0.1.1
[0.1.0]: https://github.com/brucorreia/aiops-observability-demo/releases/tag/v0.1.0
