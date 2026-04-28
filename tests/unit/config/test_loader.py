"""Unit tests for configuration loader and schema (UI-TARS-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from autovisiontest.config.loader import load_config
from autovisiontest.config.schema import AgentConfig, AppConfig, RuntimeConfig


class TestLoadDefaultConfig:
    """Verify that a minimal YAML yields correct default values."""

    def test_minimal_yaml_loads(self, tmp_path: Path) -> None:
        """A nearly-empty YAML should fill in all defaults."""
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("agent:\n  backend: uitars_local\n", encoding="utf-8")

        config = load_config(path=cfg_file)

        assert isinstance(config, AppConfig)
        assert config.agent.backend == "uitars_local"
        assert config.agent.model == "ui-tars-1.5-7b"
        assert config.agent.max_tokens == 512
        assert config.agent.temperature == 0.0
        assert config.agent.language == "Chinese"
        assert config.agent.history_images == 3
        assert config.agent.timeout_s == 60.0
        assert config.runtime.max_steps == 30
        assert config.runtime.max_session_duration_s == 600
        assert config.runtime.step_wait_ms == 500
        assert config.runtime.data_dir == Path("./data")

    def test_empty_yaml_uses_built_in_defaults(self, tmp_path: Path) -> None:
        """An empty YAML file should produce a valid AppConfig with all defaults."""
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")

        config = load_config(path=cfg_file)

        assert config.agent.backend == "uitars_local"
        assert config.agent.model == "ui-tars-1.5-7b"
        assert config.runtime.max_steps == 30

    def test_full_yaml_overrides(self, tmp_path: Path) -> None:
        """All fields overridden in YAML should be reflected in the model."""
        data: dict[str, Any] = {
            "agent": {
                "backend": "uitars_local",
                "model": "ui-tars-1.5-7b-awq",
                "endpoint": "http://localhost:9000/v1",
                "max_tokens": 1024,
                "temperature": 0.1,
                "language": "English",
                "history_images": 5,
                "timeout_s": 30.0,
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

        assert config.agent.model == "ui-tars-1.5-7b-awq"
        assert config.agent.endpoint == "http://localhost:9000/v1"
        assert config.agent.max_tokens == 1024
        assert config.agent.temperature == 0.1
        assert config.agent.language == "English"
        assert config.agent.history_images == 5
        assert config.agent.timeout_s == 30.0
        assert config.runtime.max_steps == 50
        assert config.runtime.data_dir == Path("/tmp/avt")

    def test_legacy_planner_actor_sections_ignored(self, tmp_path: Path) -> None:
        """Old YAML files with planner/actor sections should load without error."""
        data: dict[str, Any] = {
            "planner": {"backend": "vllm_local", "model": "Qwen"},
            "actor": {"backend": "showui_local"},
            "agent": {"backend": "uitars_local"},
            "runtime": {"max_steps": 42},
        }
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(yaml.dump(data), encoding="utf-8")

        config = load_config(path=cfg_file)

        assert config.agent.backend == "uitars_local"
        assert config.runtime.max_steps == 42


class TestEnvVarOverride:
    """Environment variable overrides should take effect after file loading."""

    def test_data_dir_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_DATA_DIR", "/tmp/foo")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")
        config = load_config(path=cfg_file)

        assert config.runtime.data_dir == Path("/tmp/foo")

    def test_agent_endpoint_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOVT_AGENT_ENDPOINT", "http://host.docker.internal:8000/v1")

        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text("{}", encoding="utf-8")
        config = load_config(path=cfg_file)

        assert config.agent.endpoint == "http://host.docker.internal:8000/v1"

    def test_autovt_config_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOVT_CONFIG env var should point to the config file."""
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text(
            yaml.dump({"agent": {"backend": "uitars_local", "model": "custom-tars"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("AUTOVT_CONFIG", str(cfg_file))

        config = load_config()
        assert config.agent.model == "custom-tars"


class TestInvalidBackendRejected:
    """Invalid backend strings must be rejected by Pydantic validation."""

    def test_invalid_agent_backend(self) -> None:
        with pytest.raises(ValidationError, match="backend"):
            AgentConfig(backend="nonsense")  # type: ignore[arg-type]

    def test_invalid_agent_temperature(self) -> None:
        with pytest.raises(ValidationError, match="temperature"):
            AgentConfig(temperature=5.0)

    def test_invalid_yaml_backend_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "model.yaml"
        cfg_file.write_text(
            yaml.dump({"agent": {"backend": "nonsense"}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Invalid configuration"):
            load_config(path=cfg_file)


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


class TestRuntimeConfig:
    def test_defaults(self) -> None:
        rc = RuntimeConfig()
        assert rc.max_steps == 30
        assert rc.step_wait_ms == 500
        assert rc.data_dir == Path("./data")
