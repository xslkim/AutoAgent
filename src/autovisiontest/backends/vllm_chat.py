"""vLLM local chat backend (OpenAI-compatible API)."""

from __future__ import annotations

import base64
import logging

import httpx

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "http://localhost:8000/v1"
_DEFAULT_TIMEOUT = 60.0


class VLLMChatBackend:
    """Chat backend using a local vLLM server with OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ",
        endpoint: str = _DEFAULT_ENDPOINT,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        """Send a chat request to vLLM.

        Args:
            messages: Conversation history.
            images: Optional images to include.
            response_format: "json" for JSON output, "text" for plain text.

        Returns:
            ChatResponse with the model's reply.

        Raises:
            ChatBackendError: On connection or API errors.
        """
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

                for img_bytes in (msg.images or []) + (images or []):
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                        },
                    })

                api_messages.append({"role": msg.role, "content": content_parts})

        payload = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }

        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = self._client.post(
                f"{self._endpoint}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage")

            return ChatResponse(
                content=content,
                raw=data,
                usage=usage,
            )

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            retryable = status_code >= 500 or status_code == 429
            raise ChatBackendError(
                f"vLLM API error: {exc}",
                context={"status_code": status_code},
                retryable=retryable,
            ) from exc
        except httpx.ConnectError as exc:
            raise ChatBackendError(
                f"vLLM connection error: {exc}",
                context={"endpoint": self._endpoint},
                retryable=True,
            ) from exc
        except Exception as exc:
            raise ChatBackendError(
                f"vLLM error: {exc}",
                retryable=True,
            ) from exc
