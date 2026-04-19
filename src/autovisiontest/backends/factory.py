"""Backend factory — creates the configured GUI agent backend from config."""

from __future__ import annotations

import logging

from autovisiontest.config.schema import AgentConfig

logger = logging.getLogger(__name__)


def create_agent_backend(config: AgentConfig):
    """Create a GUI agent backend from :class:`AgentConfig`.

    Supported ``config.backend`` values:

    * ``uitars_local`` → :class:`UITarsBackend` (default port 8000).
    * ``maiui_local``  → :class:`MAIUIBackend`  (default port 8001).

    Both expose the same ``decide(image_png, goal, history) -> UITarsDecision``
    surface, so callers (including :class:`UITarsAgent` and the live probe
    scripts) can swap between them without any other code changes.
    """
    if config.backend == "uitars_local":
        from autovisiontest.backends.uitars import UITarsBackend

        endpoint = config.endpoint or "http://localhost:8000/v1"
        logger.info(
            "Creating UI-TARS agent backend: endpoint=%s, model=%s",
            endpoint,
            config.model,
        )
        return UITarsBackend(
            model=config.model,
            endpoint=endpoint,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            language=config.language,
            history_images=config.history_images,
            timeout_s=config.timeout_s,
        )

    if config.backend == "maiui_local":
        from autovisiontest.backends.maiui import MAIUIBackend

        endpoint = config.endpoint or "http://localhost:8001/v1"
        logger.info(
            "Creating MAI-UI agent backend: endpoint=%s, model=%s",
            endpoint,
            config.model,
        )
        return MAIUIBackend(
            model=config.model,
            endpoint=endpoint,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            language=config.language,
            history_images=config.history_images,
            timeout_s=config.timeout_s,
        )

    raise ValueError(f"Unsupported agent backend: {config.backend!r}")
