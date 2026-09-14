import os
from pathlib import Path

import yaml

ACTIONS = (
    "rollback",
    "vertical_scale",
    "horizontal_scale",
    "investigate",
    "none",
)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_scoring_config(path: str | None = None) -> dict:
    config_path = Path(path or os.getenv("SCORING_CONFIG", "/app/config/scoring.yaml"))
    if not config_path.exists():
        local = Path(__file__).resolve().parents[1] / "config" / "scoring.yaml"
        if not local.exists():
            local = Path(__file__).resolve().parent.parent.parent / "config" / "scoring.yaml"
        config_path = local
    with config_path.open() as handle:
        return yaml.safe_load(handle) or {}


def settings(config: dict | None = None) -> dict:
    cfg = config if config is not None else load_scoring_config()
    return {
        "recent_deployment_window_minutes": int(
            os.getenv(
                "RECENT_DEPLOYMENT_WINDOW_MINUTES",
                cfg.get("recent_deployment_window_minutes", 15),
            )
        ),
        "automatic_execution_allowed": env_bool(
            "AUTOMATIC_EXECUTION_ALLOWED",
            bool(cfg.get("automatic_execution_allowed", False)),
        ),
        "victoriametrics_url": os.getenv(
            "VICTORIAMETRICS_URL",
            "http://vmsingle-vmks.monitoring.svc:8428",
        ).rstrip("/"),
        "victorialogs_url": os.getenv(
            "VICTORIALOGS_URL",
            "http://vlsingle-vmks.monitoring.svc:9428",
        ).rstrip("/"),
        "demo_namespace": os.getenv("KUBERNETES_NAMESPACE", "aiops-demo"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "llm_max_adjustment": int((cfg.get("llm") or {}).get("max_adjustment", 10)),
        "weights": cfg.get("scoring") or {},
    }
