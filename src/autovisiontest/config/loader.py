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
    """Apply environment variable overrides to the loaded config.

    Since Pydantic model_copy(update=...) replaces nested models with dicts,
    we must reconstruct each nested model individually.
    """
    # Build updated sub-models
    planner_updates: dict = {}
    planner_backend = os.environ.get("AUTOVT_PLANNER_BACKEND")
    if planner_backend:
        planner_updates["backend"] = planner_backend

    actor_updates: dict = {}
    actor_backend = os.environ.get("AUTOVT_ACTOR_BACKEND")
    if actor_backend:
        actor_updates["backend"] = actor_backend

    runtime_updates: dict = {}
    data_dir = os.environ.get("AUTOVT_DATA_DIR")
    if data_dir:
        runtime_updates["data_dir"] = Path(data_dir)

    if not (planner_updates or actor_updates or runtime_updates):
        return config

    new_planner = config.planner.model_copy(update=planner_updates) if planner_updates else config.planner
    new_actor = config.actor.model_copy(update=actor_updates) if actor_updates else config.actor
    new_runtime = config.runtime.model_copy(update=runtime_updates) if runtime_updates else config.runtime

    return config.model_copy(update={
        "planner": new_planner,
        "actor": new_actor,
        "runtime": new_runtime,
    })


def _check_api_key_warnings(config: AppConfig) -> list[str]:
    """Check for missing API keys and return warning messages."""
    warnings: list[str] = []

    cloud_backends = {"claude_api", "openai_api", "dashscope_api"}
    if config.planner.backend in cloud_backends and config.planner.api_key_env:
        key_value = os.environ.get(config.planner.api_key_env)
        if not key_value:
            warnings.append(
                f"Planner backend is '{config.planner.backend}' but environment variable "
                f"'{config.planner.api_key_env}' (api_key_env) is not set. "
                f"API calls will fail until this is configured."
            )

    return warnings


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Load configuration from YAML file with env var overrides.

    Priority chain:
        1. Explicit path argument
        2. AUTOVT_CONFIG environment variable
        3. ./config/model.yaml
        4. Package-relative default
        5. Built-in defaults (no file)

    Environment variable overrides:
        - AUTOVT_DATA_DIR: Override runtime.data_dir
        - AUTOVT_PLANNER_BACKEND: Override planner.backend
        - AUTOVT_ACTOR_BACKEND: Override actor.backend
    """
    config_path = _resolve_config_path(path)

    if config_path is not None:
        logger.info("Loading config", path=str(config_path))
        with open(config_path, "r", encoding="utf-8") as f:
            raw: dict = yaml.safe_load(f) or {}
    else:
        logger.info("No config file found, using built-in defaults")
        raw = {}

    try:
        config = AppConfig(**raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc

    config = _apply_env_overrides(config)

    warnings = _check_api_key_warnings(config)
    for w in warnings:
        logger.warning(w)

    return config
