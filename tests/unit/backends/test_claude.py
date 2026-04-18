"""Unit tests for Claude chat backend (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.backends.claude import ClaudeChatBackend
from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.exceptions import ChatBackendError


@pytest.fixture
def mock_anthropic():
    """Patch the anthropic module and return mock client."""
    with patch.dict("sys.modules", {"anthropic": MagicMock()}):
        import anthropic

        mock_client = MagicMock()
        anthropic.Anthropic.return_value = mock_client
        yield mock_client


@pytest.fixture
def backend(mock_anthropic):
    """Return a ClaudeChatBackend with mocked client."""
    return ClaudeChatBackend(model="claude-sonnet-4-20250514", api_key="test-key")


class TestClaudeChatBackend:
    def test_chat_basic(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test basic chat request construction."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello!")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model_dump.return_value = {"id": "msg_123"}
        mock_anthropic.messages.create.return_value = mock_response

        messages = [Message(role="user", content="Say hi")]
        result = backend.chat(messages)

        assert isinstance(result, ChatResponse)
        assert result.content == "Hello!"
        assert result.usage is not None
        assert result.usage["input_tokens"] == 10

        # Verify request was constructed correctly
        call_kwargs = mock_anthropic.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert len(call_kwargs["messages"]) == 1

    def test_chat_with_image(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test that images are correctly attached to messages."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I see an image")]
        mock_response.usage = MagicMock(input_tokens=20, output_tokens=5)
        mock_response.model_dump.return_value = {}
        mock_anthropic.messages.create.return_value = mock_response

        messages = [Message(role="user", content="What is this?", images=[b"\x89PNG"])]
        result = backend.chat(messages)

        assert result.content == "I see an image"

        # Verify image was included in the message content
        call_kwargs = mock_anthropic.messages.create.call_args[1]
        user_msg = call_kwargs["messages"][0]
        assert len(user_msg["content"]) == 2  # text + image
        assert user_msg["content"][1]["type"] == "image"

    def test_chat_retries_on_5xx(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test that 5xx errors trigger retries."""
        error = Exception("Internal Server Error")
        error.status_code = 500  # type: ignore

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="OK")]
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=2)
        mock_response.model_dump.return_value = {}

        mock_anthropic.messages.create.side_effect = [error, mock_response]

        with patch("autovisiontest.backends.claude.time.sleep"):
            result = backend.chat([Message(role="user", content="hi")])

        assert result.content == "OK"
        assert mock_anthropic.messages.create.call_count == 2

    def test_chat_no_retry_on_4xx(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test that 4xx errors (except 429) are not retried."""
        error = Exception("Bad Request")
        error.status_code = 400  # type: ignore
        mock_anthropic.messages.create.side_effect = error

        with pytest.raises(ChatBackendError, match="Claude API error") as exc_info:
            backend.chat([Message(role="user", content="hi")])

        assert exc_info.value.retryable is False

    def test_chat_retryable_on_max_retries_exceeded(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test that after max retries, error is marked retryable."""
        error = Exception("Service Unavailable")
        error.status_code = 503  # type: ignore
        mock_anthropic.messages.create.side_effect = error

        with patch("autovisiontest.backends.claude.time.sleep"):
            with pytest.raises(ChatBackendError, match="after 3 retries") as exc_info:
                backend.chat([Message(role="user", content="hi")])

        assert exc_info.value.retryable is True

    def test_chat_json_format_adds_instruction(self, backend: ClaudeChatBackend, mock_anthropic) -> None:
        """Test that response_format=json adds JSON instruction to system prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"action": "click"}')]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model_dump.return_value = {}
        mock_anthropic.messages.create.return_value = mock_response

        messages = [
            Message(role="system", content="You are a test planner."),
            Message(role="user", content="What next?"),
        ]
        backend.chat(messages, response_format="json")

        call_kwargs = mock_anthropic.messages.create.call_args[1]
        assert "JSON object" in call_kwargs["system"]
