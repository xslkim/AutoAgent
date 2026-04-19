"""Backend factory — creates backend instances from config.

Routes ``PlannerConfig`` / ``ActorConfig`` to the appropriate backend class.
"""

from __future__ import annotations

import logging

from autovisiontest.config.schema import ActorConfig, PlannerConfig

logger = logging.getLogger(__name__)


def create_chat_backend(config: PlannerConfig):
    """Create a ChatBackend from PlannerConfig.

    Supported backends:
        - ``vllm_local``: VLLMChatBackend (OpenAI-compatible API)
        - ``openai_api``: OpenAIChatBackend
        - ``claude_api``: ClaudeChatBackend
        - ``dashscope_api``: OpenAIChatBackend with DashScope endpoint
    """
    backend = config.backend

    if backend == "vllm_local":
        from autovisiontest.backends.vllm_chat import VLLMChatBackend

        endpoint = config.endpoint or "http://localhost:8000/v1"
        logger.info("Creating vLLM chat backend: endpoint=%s, model=%s", endpoint, config.model)
        return VLLMChatBackend(
            model=config.model,
            endpoint=endpoint,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    elif backend == "openai_api":
        from autovisiontest.backends.openai_backend import OpenAIChatBackend

        api_key = _resolve_api_key(config.api_key_env, "OPENAI_API_KEY")
        logger.info("Creating OpenAI chat backend: model=%s", config.model)
        return OpenAIChatBackend(
            model=config.model,
            api_key=api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    elif backend == "claude_api":
        from autovisiontest.backends.claude import ClaudeChatBackend

        api_key = _resolve_api_key(config.api_key_env, "ANTHROPIC_API_KEY")
        logger.info("Creating Claude chat backend: model=%s", config.model)
        return ClaudeChatBackend(
            model=config.model,
            api_key=api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    elif backend == "dashscope_api":
        from autovisiontest.backends.openai_backend import OpenAIChatBackend

        api_key = _resolve_api_key(config.api_key_env, "DASHSCOPE_API_KEY")
        endpoint = config.endpoint or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        logger.info("Creating DashScope chat backend: model=%s", config.model)
        return OpenAIChatBackend(
            model=config.model,
            api_key=api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    else:
        raise ValueError(f"Unsupported planner backend: {backend!r}")


def create_grounding_backend(config: ActorConfig):
    """Create a GroundingBackend from ActorConfig.

    Supported backends:
        - ``showui_local``: ShowUIGroundingBackend via vLLM
        - ``osatlas_local``: ShowUIGroundingBackend via vLLM (same protocol)
        - ``vllm_local``: ShowUIGroundingBackend via vLLM
    """
    backend = config.backend

    if backend in ("showui_local", "osatlas_local", "vllm_local"):
        from autovisiontest.backends.showui import ShowUIGroundingBackend

        endpoint = config.endpoint or "http://localhost:8001/v1"
        logger.info(
            "Creating grounding backend: type=%s, endpoint=%s, model=%s",
            backend, endpoint, config.model,
        )
        return ShowUIGroundingBackend(
            model=config.model,
            endpoint=endpoint,
            confidence_threshold=config.confidence_threshold,
        )

    else:
        raise ValueError(f"Unsupported actor backend: {backend!r}")


def _resolve_api_key(env_var: str | None, default_env_var: str) -> str:
    """Resolve API key from environment variable."""
    import os

    key_name = env_var or default_env_var
    api_key = os.environ.get(key_name, "")
    if not api_key:
        logger.warning(
            "API key env var '%s' is not set. API calls will likely fail.",
            key_name,
        )
    return api_key
