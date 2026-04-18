"""OpenAI API chat backend."""

from __future__ import annotations

import base64
import logging
import time

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]


class OpenAIChatBackend:
    """Chat backend using the OpenAI API (GPT-4o / GPT-4o-mini)."""

    def __init__(
        self,
        model: str = "gpt-4o",
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
        """Lazy-initialize the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key)
            except ImportError as exc:
                raise ChatBackendError(
                    "openai package not installed",
                    context={"hint": "pip install openai"},
                    retryable=False,
                ) from exc
        return self._client

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        """Send a chat request to OpenAI.

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

        # Build OpenAI-format messages
        api_messages = []
        for msg in messages:
            if msg.role == "system":
                content = msg.content
                if response_format == "json":
                    content += "\n\nRespond with a single JSON object. No markdown fences."
                api_messages.append({"role": "system", "content": content})
            else:
                content_parts: list[dict] = []
                content_parts.append({"type": "text", "text": msg.content})

                # Add images from Message
                for img_bytes in msg.images:
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        },
                    })

                # Add extra images passed separately
                if images:
                    for img_bytes in images:
                        b64 = base64.b64encode(img_bytes).decode("utf-8")
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "low",
                            },
                        })

                api_messages.append({"role": msg.role, "content": content_parts})

        # Build kwargs
        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        # Retry loop
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.chat.completions.create(**kwargs)

                content = response.choices[0].message.content or ""
                usage = None
                if response.usage:
                    usage = {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                    }

                return ChatResponse(
                    content=content,
                    raw=response.model_dump() if hasattr(response, "model_dump") else {},
                    usage=usage,
                )

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "status_code", None)

                if status_code and 400 <= status_code < 500 and status_code != 429:
                    raise ChatBackendError(
                        f"OpenAI API error: {exc}",
                        context={"status_code": status_code},
                        retryable=False,
                    ) from exc

                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "OpenAI API error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    raise ChatBackendError(
                        f"OpenAI API error after {_MAX_RETRIES} retries: {exc}",
                        context={"status_code": status_code},
                        retryable=True,
                    ) from exc

        raise ChatBackendError(f"OpenAI API error: {last_exc}", retryable=True)
