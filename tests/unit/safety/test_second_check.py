"""Unit tests for safety second_check module (T E.3)."""

from __future__ import annotations

import json

import pytest

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.control.actions import Action
from autovisiontest.safety.second_check import SecondCheck


class _MockChatBackend:
    """Mock ChatBackend that returns a configurable response."""

    def __init__(self, response_content: str) -> None:
        self._response = response_content
        self.last_messages: list[Message] | None = None

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        self.last_messages = messages
        return ChatResponse(content=self._response, raw={}, usage=None)


class TestSecondCheck:
    def test_safe_response_parsed(self) -> None:
        backend = _MockChatBackend('{"verdict": "safe", "reason": "goal requires deletion"}')
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        action = Action(type="click", params={"x": 100, "y": 200})
        ctx: dict = {"safety_overrides": 0}

        result = check.confirm(action, "click near 'Delete'", "clean up temp files", ctx)

        assert result == "safe"
        assert ctx["safety_overrides"] == 1

    def test_unsafe_response_parsed(self) -> None:
        backend = _MockChatBackend('{"verdict": "unsafe", "reason": "dangerous operation"}')
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        action = Action(type="click", params={"x": 100, "y": 200})
        ctx: dict = {"safety_overrides": 0}

        result = check.confirm(action, "click near 'Format'", "open a document", ctx)

        assert result == "unsafe"
        assert ctx["safety_overrides"] == 1

    def test_exceeds_limit_auto_unsafe(self) -> None:
        """Once override limit is exceeded, always return unsafe without calling VLM."""
        backend = _MockChatBackend('{"verdict": "safe", "reason": "ok"}')
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=2)
        action = Action(type="click", params={})
        ctx: dict = {"safety_overrides": 2}

        result = check.confirm(action, "click near 'Delete'", "goal", ctx)

        assert result == "unsafe"
        # VLM should not have been called
        assert backend.last_messages is None
        # Override count still incremented
        assert ctx["safety_overrides"] == 3

    def test_malformed_response_defaults_unsafe(self) -> None:
        backend = _MockChatBackend("this is not json at all")
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        action = Action(type="click", params={})
        ctx: dict = {"safety_overrides": 0}

        result = check.confirm(action, "click near 'Reset'", "goal", ctx)

        assert result == "unsafe"

    def test_response_with_markdown_fence(self) -> None:
        """VLM may wrap JSON in markdown fences — should still parse."""
        content = '```json\n{"verdict": "safe", "reason": "ok"}\n```'
        backend = _MockChatBackend(content)
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        action = Action(type="type", params={"text": "del /s file"})
        ctx: dict = {"safety_overrides": 0}

        result = check.confirm(action, "type matches del pattern", "goal", ctx)

        assert result == "safe"

    def test_exception_in_backend_defaults_unsafe(self) -> None:
        """If the backend raises, default to unsafe."""

        class _FailingBackend:
            def chat(self, messages, images=None, response_format="json"):
                raise RuntimeError("backend down")

        check = SecondCheck(chat_backend=_FailingBackend(), max_overrides_per_session=3)
        action = Action(type="click", params={})
        ctx: dict = {"safety_overrides": 0}

        result = check.confirm(action, "click near 'Delete'", "goal", ctx)

        assert result == "unsafe"

    def test_missing_safety_overrides_key(self) -> None:
        """If session_ctx lacks 'safety_overrides', should default to 0."""
        backend = _MockChatBackend('{"verdict": "safe", "reason": "ok"}')
        check = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        action = Action(type="click", params={})
        ctx: dict = {}

        result = check.confirm(action, "hit", "goal", ctx)

        assert result == "safe"
        assert ctx["safety_overrides"] == 1
