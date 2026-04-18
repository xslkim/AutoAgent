"""Unit tests for backend factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.backends.claude import ClaudeChatBackend
from autovisiontest.backends.factory import create_chat_backend, create_grounding_backend
from autovisiontest.backends.openai_backend import OpenAIChatBackend
from autovisiontest.backends.showui import ShowUIGroundingBackend
from autovisiontest.backends.vllm_chat import VLLMChatBackend
from autovisiontest.exceptions import ConfigError


def _make_planner_config(backend: str, **kwargs):
    """Create a mock PlannerConfig."""
    config = MagicMock()
    config.backend = backend
    config.model = kwargs.get("model", None)
    config.api_key_env = kwargs.get("api_key_env", None)
    config.max_tokens = kwargs.get("max_tokens", 2048)
    config.temperature = kwargs.get("temperature", 0.2)
    config.endpoint = kwargs.get("endpoint", None)
    return config


def _make_actor_config(backend: str, **kwargs):
    """Create a mock ActorConfig."""
    config = MagicMock()
    config.backend = backend
    config.model = kwargs.get("model", None)
    config.endpoint = kwargs.get("endpoint", None)
    config.confidence_threshold = kwargs.get("confidence_threshold", 0.6)
    return config


class TestCreateChatBackend:
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_create_claude_backend(self) -> None:
        config = _make_planner_config("claude_api")
        backend = create_chat_backend(config)
        assert isinstance(backend, ClaudeChatBackend)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_create_openai_backend(self) -> None:
        config = _make_planner_config("openai_api")
        backend = create_chat_backend(config)
        assert isinstance(backend, OpenAIChatBackend)

    def test_create_vllm_backend(self) -> None:
        config = _make_planner_config("vllm")
        backend = create_chat_backend(config)
        assert isinstance(backend, VLLMChatBackend)

    def test_unknown_backend_raises(self) -> None:
        config = _make_planner_config("nonexistent")
        with pytest.raises(ConfigError, match="Unknown chat backend"):
            create_chat_backend(config)


class TestCreateGroundingBackend:
    def test_create_showui_backend(self) -> None:
        config = _make_actor_config("showui")
        backend = create_grounding_backend(config)
        assert isinstance(backend, ShowUIGroundingBackend)

    def test_unknown_grounding_backend_raises(self) -> None:
        config = _make_actor_config("nonexistent")
        with pytest.raises(ConfigError, match="Unknown grounding backend"):
            create_grounding_backend(config)
