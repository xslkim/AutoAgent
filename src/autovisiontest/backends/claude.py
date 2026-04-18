"""Claude API chat backend."""

from __future__ import annotations

import base64
import logging
import time
from typing import Literal

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]


class ClaudeChatBackend:
    """Chat backend using the Anthropic Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=self._api_key)
            except ImportError as exc:
                raise ChatBackendError(
                    "anthropic package not installed",
                    context={"hint": "pip install anthropic"},
                    retryable=False,
                ) from exc
        return self._client

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        """Send a chat request to Claude.

        Args:
            messages: Conversation history.
            images: Optional images to include.
            response_format: "json" for JSON output, "text" for plain text.

        Returns:
            ChatResponse with the model's reply.

        Raises:
            ChatBackendError: On API errors (retryable or not).
        """
        client = self._get_client()

        # Build Anthropic-format messages
        system_content = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                content_blocks = []
                # Add text content
                content_blocks.append({"type": "text", "text": msg.content})

                # Add images attached to this message
                if msg.images:
                    for img_bytes in msg.images:
                        b64 = base64.b64encode(img_bytes).decode("utf-8")
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        })

                # Also add any extra images passed directly
                api_messages.append({
                    "role": msg.role,
                    "content": content_blocks,
                })

        # Add extra images to the last user message if provided separately
        if images and api_messages:
            last = api_messages[-1]
            if last["role"] == "user":
                for img_bytes in images:
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    last["content"].append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    })

        # Append JSON instruction to system prompt if needed
        if response_format == "json" and system_content:
            system_content += "\n\nRespond with a single JSON object. No markdown fences."
        elif response_format == "json" and not system_content:
            system_content = "Respond with a single JSON object. No markdown fences."

        # Retry loop with exponential backoff
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    system=system_content or "",
                    messages=api_messages,
                )

                content = response.content[0].text if response.content else ""
                usage = {
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                }

                return ChatResponse(
                    content=content,
                    raw=response.model_dump() if hasattr(response, "model_dump") else {},
                    usage=usage,
                )

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "status_code", None)

                # 4xx errors are not retryable (except 429)
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    raise ChatBackendError(
                        f"Claude API error: {exc}",
                        context={"status_code": status_code},
                        retryable=False,
                    ) from exc

                # 5xx / network errors are retryable
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "Claude API error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    raise ChatBackendError(
                        f"Claude API error after {_MAX_RETRIES} retries: {exc}",
                        context={"status_code": status_code},
                        retryable=True,
                    ) from exc

        # Should not reach here, but just in case
        raise ChatBackendError(
            f"Claude API error: {last_exc}",
            retryable=True,
        )
