"""Unit tests for OpenAI chat backend (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.backends.openai_backend import OpenAIChatBackend
from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.exceptions import ChatBackendError


@pytest.fixture
def mock_openai():
    """Patch the openai module and return mock client."""
    with patch.dict("sys.modules", {"openai": MagicMock()}):
        import openai

        mock_client = MagicMock()
        openai.OpenAI.return_value = mock_client
        yield mock_client


@pytest.fixture
def backend(mock_openai):
    return OpenAIChatBackend(model="gpt-4o", api_key="test-key")


def _make_mock_response(content: str = "Hello!", input_tokens: int = 10, output_tokens: int = 5):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = input_tokens
    resp.usage.completion_tokens = output_tokens
    resp.model_dump.return_value = {"id": "chatcmpl_123"}
    return resp


class TestOpenAIChatBackend:
    def test_chat_basic(self, backend: OpenAIChatBackend, mock_openai) -> None:
        mock_openai.chat.completions.create.return_value = _make_mock_response("Hi there!")

        messages = [Message(role="user", content="Say hi")]
        result = backend.chat(messages)

        assert isinstance(result, ChatResponse)
        assert result.content == "Hi there!"

    def test_chat_with_image(self, backend: OpenAIChatBackend, mock_openai) -> None:
        mock_openai.chat.completions.create.return_value = _make_mock_response("I see an image")

        messages = [Message(role="user", content="What is this?", images=[b"\x89PNG"])]
        result = backend.chat(messages)

        assert result.content == "I see an image"

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][0]
        assert len(user_msg["content"]) == 2  # text + image
        assert user_msg["content"][1]["type"] == "image_url"

    def test_chat_retries_on_5xx(self, backend: OpenAIChatBackend, mock_openai) -> None:
        error = Exception("Internal Server Error")
        error.status_code = 500  # type: ignore

        mock_openai.chat.completions.create.side_effect = [
            error,
            _make_mock_response("OK"),
        ]

        with patch("autovisiontest.backends.openai_backend.time.sleep"):
            result = backend.chat([Message(role="user", content="hi")])

        assert result.content == "OK"

    def test_chat_no_retry_on_4xx(self, backend: OpenAIChatBackend, mock_openai) -> None:
        error = Exception("Bad Request")
        error.status_code = 400  # type: ignore
        mock_openai.chat.completions.create.side_effect = error

        with pytest.raises(ChatBackendError, match="OpenAI API error") as exc_info:
            backend.chat([Message(role="user", content="hi")])

        assert exc_info.value.retryable is False

    def test_chat_json_format(self, backend: OpenAIChatBackend, mock_openai) -> None:
        mock_openai.chat.completions.create.return_value = _make_mock_response('{"action": "click"}')

        messages = [
            Message(role="system", content="You are a test planner."),
            Message(role="user", content="What next?"),
        ]
        backend.chat(messages, response_format="json")

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}
