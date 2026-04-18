"""Unit tests for vLLM chat backend (mocked httpx)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from autovisiontest.backends.types import Message
from autovisiontest.backends.vllm_chat import VLLMChatBackend
from autovisiontest.exceptions import ChatBackendError


@pytest.fixture
def backend():
    return VLLMChatBackend(
        model="Qwen/Qwen2.5-VL-7B-Instruct-AWQ",
        endpoint="http://localhost:8000/v1",
    )


class TestVLLMChatBackend:
    @patch("autovisiontest.backends.vllm_chat.httpx.Client")
    def test_chat_basic(self, mock_client_cls) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_client.post.return_value = mock_response

        backend = VLLMChatBackend()
        messages = [Message(role="user", content="Say hi")]
        result = backend.chat(messages)

        assert result.content == "Hello!"
        assert result.usage is not None

    @patch("autovisiontest.backends.vllm_chat.httpx.Client")
    def test_chat_request_body(self, mock_client_cls) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
        }
        mock_client.post.return_value = mock_response

        backend = VLLMChatBackend()
        backend.chat(
            [Message(role="system", content="You are a planner."), Message(role="user", content="hi")],
            response_format="json",
        )

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["model"] == "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
        assert "response_format" in payload
        assert payload["response_format"]["type"] == "json_object"

    @patch("autovisiontest.backends.vllm_chat.httpx.Client")
    def test_chat_connection_error(self, mock_client_cls) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        backend = VLLMChatBackend()
        with pytest.raises(ChatBackendError, match="connection error") as exc_info:
            backend.chat([Message(role="user", content="hi")])

        assert exc_info.value.retryable is True

    @patch("autovisiontest.backends.vllm_chat.httpx.Client")
    def test_chat_http_5xx_retryable(self, mock_client_cls) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_client.post.return_value = mock_response

        backend = VLLMChatBackend()
        with pytest.raises(ChatBackendError) as exc_info:
            backend.chat([Message(role="user", content="hi")])

        assert exc_info.value.retryable is True
