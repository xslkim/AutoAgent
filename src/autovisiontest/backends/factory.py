"""Backend factory — create backends from configuration."""

from __future__ import annotations

from autovisiontest.backends.claude import ClaudeChatBackend
from autovisiontest.backends.openai_backend import OpenAIChatBackend
from autovisiontest.backends.protocol import ChatBackend, GroundingBackend
from autovisiontest.backends.showui import ShowUIGroundingBackend
from autovisiontest.backends.vllm_chat import VLLMChatBackend
from autovisiontest.exceptions import ConfigError


def create_chat_backend(config) -> ChatBackend:
    """Create a ChatBackend from a PlannerConfig.

    Args:
        config: PlannerConfig with backend, model, api_key_env, etc.

    Returns:
        A ChatBackend instance.

    Raises:
        ConfigError: If the backend type is unknown.
    """
    backend_type = config.backend.lower() if config.backend else ""

    if backend_type == "claude_api":
        api_key = _resolve_env(config.api_key_env, "ANTHROPIC_API_KEY")
        return ClaudeChatBackend(
            model=config.model or "claude-sonnet-4-20250514",
            api_key=api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    elif backend_type == "openai_api":
        api_key = _resolve_env(config.api_key_env, "OPENAI_API_KEY")
        return OpenAIChatBackend(
            model=config.model or "gpt-4o",
            api_key=api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    elif backend_type == "vllm":
        return VLLMChatBackend(
            model=config.model or "Qwen/Qwen2.5-VL-7B-Instruct-AWQ",
            endpoint=config.endpoint or "http://localhost:8000/v1",
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    else:
        raise ConfigError(
            f"Unknown chat backend: {config.backend}",
            context={"backend": config.backend},
        )


def create_grounding_backend(config) -> GroundingBackend:
    """Create a GroundingBackend from an ActorConfig.

    Args:
        config: ActorConfig with backend, model, endpoint, etc.

    Returns:
        A GroundingBackend instance.

    Raises:
        ConfigError: If the backend type is unknown.
    """
    backend_type = config.backend.lower() if config.backend else ""

    if backend_type == "showui":
        return ShowUIGroundingBackend(
            model=config.model or "showlab/ShowUI-2B",
            endpoint=config.endpoint or "http://localhost:8001/v1",
            confidence_threshold=config.confidence_threshold,
        )
    else:
        raise ConfigError(
            f"Unknown grounding backend: {config.backend}",
            context={"backend": config.backend},
        )


def _resolve_env(env_var: str | None, default: str) -> str:
    """Resolve an environment variable, falling back to *default* var name."""
    import os

    var_name = env_var or default
    value = os.environ.get(var_name, "")
    return value
