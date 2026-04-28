"""Configuration loader with priority chain and env var overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import structlog
import yaml
from pydantic import ValidationError

from autovisiontest.config.schema import AppConfig

logger = structlog.get_logger(__name__)

_DEFAULT_CONFIG_PATHS: list[Path] = [
    Path("./config/model.yaml"),
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "model.yaml",
]


def _resolve_config_path(explicit_path: Optional[Path] = None) -> Optional[Path]:
    """Resolve config file path by priority: explicit > env var > defaults."""
    if explicit_path is not None:
        p = Path(explicit_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p

    env_path = os.environ.get("AUTOVT_CONFIG")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Config file from AUTOVT_CONFIG not found: {p}"
            )
        return p

    for candidate in _DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return candidate

    return None


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    """Apply environment variable overrides to the loaded config."""
    runtime_updates: dict = {}
    data_dir = os.environ.get("AUTOVT_DATA_DIR")
    if data_dir:
        runtime_updates["data_dir"] = Path(data_dir)

    agent_updates: dict = {}
    agent_endpoint = os.environ.get("AUTOVT_AGENT_ENDPOINT")
    if agent_endpoint:
        agent_updates["endpoint"] = agent_endpoint

    if not (runtime_updates or agent_updates):
        return config

    new_runtime = config.runtime.model_copy(update=runtime_updates) if runtime_updates else config.runtime
    new_agent = config.agent.model_copy(update=agent_updates) if agent_updates else config.agent
    return config.model_copy(update={"runtime": new_runtime, "agent": new_agent})


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Load configuration from YAML file with env var overrides.

    Priority chain:
        1. Explicit path argument
        2. ``AUTOVT_CONFIG`` environment variable
        3. ``./config/model.yaml``
        4. Package-relative default
        5. Built-in defaults (no file)

    Environment variable overrides:
        - ``AUTOVT_DATA_DIR``     — override ``runtime.data_dir``
        - ``AUTOVT_AGENT_ENDPOINT`` — override ``agent.endpoint``
    """
    config_path = _resolve_config_path(path)

    if config_path is not None:
        logger.info("Loading config", path=str(config_path))
        with open(config_path, "r", encoding="utf-8") as f:
            raw: dict = yaml.safe_load(f) or {}
    else:
        logger.info("No config file found, using built-in defaults")
        raw = {}

    # Legacy ``planner`` / ``actor`` sections are silently dropped by
    # ``AppConfig.model_config = {"extra": "ignore"}`` — no need to pop
    # them explicitly.  This lets old model.yaml files keep loading
    # cleanly until operators migrate them.

    try:
        config = AppConfig(**raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc

    return _apply_env_overrides(config)
