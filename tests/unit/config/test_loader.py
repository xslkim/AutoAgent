"""Unit tests for configuration loader and schema."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from autovisiontest.config.loader import load_config
from autovisiontest.config.schema import (
    ActorConfig,
    AppConfig,
    PlannerConfig,
    RuntimeConfig,
)


# ---------------------------------------------------------------------------
# test_load_default_config
# ---------------------------------------------------------------------------

class TestLoadDefaultConfig:
    """Verify that a minimal YAML yields correct default values."""

    def test_minimal_yaml_loads(self, tmp_path: Path) -> None:
        """A nearly-empty YAML should fill in all defaults."""
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("planner:\n  backend: vllm_local\n", encoding="utf-8")

        config = load_config(path=cfg_file)

        assert isinstance(config, AppConfig)
        # Planner defaults
        assert config.planner.backend == "vllm_local"
        assert config.planner.model == "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
        assert config.planner.max_tokens == 1024
        assert config.planner.temperature == 0.3
        assert config.planner.api_key_env is None
        assert config.planner.endpoint is None
        # Actor defaults
        assert config.actor.backend == "showui_local"
        assert config.actor.model == "showlab/ShowUI-2B"
        assert config.actor.confidence_threshold == 0.5
        # Runtime defaults
        assert config.runtime.max_steps == 30
        assert config.runtime.max_session_duration_s == 600
        assert config.runtime.step_wait_ms == 500
        assert config.runtime.data_dir == Path("./data")

    def test_empty_yaml_uses_built_in_defaults(self, tmp_path: Path) -> None:
        """An empty YAML file should produce a valid AppConfig with all defaults."""
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")

        config = load_config(path=cfg_file)

        assert config.planner.backend == "vllm_local"
        assert config.actor.backend == "showui_local"
        assert config.runtime.max_steps == 30

    def test_full_yaml_overrides(self, tmp_path: Path) -> None:
        """All fields overridden in YAML should be reflected in the model."""
        data: dict[str, Any] = {
            "planner": {
                "backend": "claude_api",
                "model": "claude-3-5-sonnet-20241022",
                "api_key_env": "ANTHROPIC_API_KEY",
                "max_tokens": 2048,
                "temperature": 0.1,
                "endpoint": "https://api.anthropic.com",
            },
            "actor": {
                "backend": "osatlas_local",
                "model": "OS-Atlas-2B",
                "endpoint": "http://localhost:8002/v1",
                "confidence_threshold": 0.8,
            },
            "runtime": {
                "max_steps": 50,
                "max_session_duration_s": 1200,
                "step_wait_ms": 1000,
                "data_dir": "/tmp/avt",
            },
        }
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(yaml.dump(data), encoding="utf-8")

        config = load_config(path=cfg_file)

        assert config.planner.backend == "claude_api"
        assert config.planner.model == "claude-3-5-sonnet-20241022"
        assert config.planner.api_key_env == "ANTHROPIC_API_KEY"
        assert config.planner.max_tokens == 2048
        assert config.planner.temperature == 0.1
        assert config.planner.endpoint == "https://api.anthropic.com"
        assert config.actor.backend == "osatlas_local"
        assert config.actor.model == "OS-Atlas-2B"
        assert config.actor.confidence_threshold == 0.8
        assert config.runtime.max_steps == 50
        assert config.runtime.data_dir == Path("/tmp/avt")


# ---------------------------------------------------------------------------
# test_env_var_override
# ---------------------------------------------------------------------------

class TestEnvVarOverride:
    """Environment variable overrides should take effect after file loading."""

    def test_data_dir_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_DATA_DIR", "/tmp/foo")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")
        config = load_config(path=cfg_file)

        assert config.runtime.data_dir == Path("/tmp/foo")

    def test_planner_backend_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_PLANNER_BACKEND", "claude_api")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")
        config = load_config(path=cfg_file)

        assert config.planner.backend == "claude_api"

    def test_actor_backend_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_ACTOR_BACKEND", "osatlas_local")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")
        config = load_config(path=cfg_file)

        assert config.actor.backend == "osatlas_local"

    def test_autovt_config_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOVT_CONFIG env var should point to the config file."""
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text(
            yaml.dump({"planner": {"backend": "openai_api"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("AUTOVT_CONFIG", str(cfg_file))

        config = load_config()
        assert config.planner.backend == "openai_api"


# ---------------------------------------------------------------------------
# test_invalid_backend_rejected
# ---------------------------------------------------------------------------

class TestInvalidBackendRejected:
    """Invalid backend strings must be rejected by Pydantic validation."""

    def test_invalid_planner_backend(self) -> None:
        with pytest.raises(ValidationError, match="backend"):
            PlannerConfig(backend="nonsense")

    def test_invalid_actor_backend(self) -> None:
        with pytest.raises(ValidationError, match="backend"):
            ActorConfig(backend="nonsense")

    def test_invalid_planner_temperature(self) -> None:
        with pytest.raises(ValidationError, match="temperature"):
            PlannerConfig(temperature=5.0)

    def test_invalid_actor_confidence(self) -> None:
        with pytest.raises(ValidationError, match="confidence_threshold"):
            ActorConfig(confidence_threshold=1.5)

    def test_invalid_yaml_backend_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(
            yaml.dump({"planner": {"backend": "nonsense"}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Invalid configuration"):
            load_config(path=cfg_file)


# ---------------------------------------------------------------------------
# test_missing_api_key_env_warning
# ---------------------------------------------------------------------------

class TestMissingApiKeyWarning:
    """Cloud backend with unset api_key_env should emit a warning, not raise."""

    def test_missing_api_key_produces_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Planner uses claude_api but ANTHROPIC_API_KEY is not set → warning."""
        # Ensure the key is NOT set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(
            yaml.dump({
                "planner": {
                    "backend": "claude_api",
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
            }),
            encoding="utf-8",
        )

        # Should NOT raise; config loads successfully
        config = load_config(path=cfg_file)
        assert config.planner.backend == "claude_api"
        assert config.planner.api_key_env == "ANTHROPIC_API_KEY"

    def test_api_key_present_no_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When api_key_env variable IS set, no warning should be emitted."""
        monkeypatch.setenv("MY_API_KEY", "sk-test-123")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(
            yaml.dump({
                "planner": {
                    "backend": "openai_api",
                    "api_key_env": "MY_API_KEY",
                }
            }),
            encoding="utf-8",
        )

        config = load_config(path=cfg_file)
        assert config.planner.backend == "openai_api"

    def test_local_backend_no_api_key_needed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vllm_local backend should not require api_key_env at all."""
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(
            yaml.dump({"planner": {"backend": "vllm_local"}}),
            encoding="utf-8",
        )

        config = load_config(path=cfg_file)
        assert config.planner.backend == "vllm_local"
        assert config.planner.api_key_env is None


# ---------------------------------------------------------------------------
# test_file_not_found
# ---------------------------------------------------------------------------

class TestFileNotFound:
    """Explicit path to non-existent file should raise FileNotFoundError."""

    def test_explicit_missing_path_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(path=Path("/nonexistent/model.yaml"))

    def test_env_missing_path_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_CONFIG", "/nonexistent/model.yaml")
        try:
            with pytest.raises(FileNotFoundError, match="AUTOVT_CONFIG"):
                load_config()
        finally:
            monkeypatch.delenv("AUTOVT_CONFIG")
