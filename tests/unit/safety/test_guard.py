"""Unit tests for safety guard module (T E.4)."""

from __future__ import annotations

import time

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.control.actions import Action
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult
from autovisiontest.safety.guard import SafetyGuard, SafetyVerdict
from autovisiontest.safety.second_check import SecondCheck


def _make_ocr_result(items: list[tuple[str, int, int]]) -> OCRResult:
    """Helper to create OCRResult from (text, x, y) tuples."""
    return OCRResult(
        items=[
            OCRItem(text=t, bbox=BoundingBox(x=x, y=y, w=50, h=20), confidence=0.95)
            for t, x, y in items
        ],
        image_size=(1920, 1080),
    )


class _MockChatBackend:
    """Mock ChatBackend with configurable verdict."""

    def __init__(self, verdict: str = "unsafe") -> None:
        self._verdict = verdict

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        import json
        content = json.dumps({"verdict": self._verdict, "reason": "mock"})
        return ChatResponse(content=content, raw={}, usage=None)


class TestSafetyGuard:
    def test_within_limits_passes(self) -> None:
        """Normal safe action within limits should pass."""
        backend = _MockChatBackend(verdict="unsafe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="click", params={})
        ocr = _make_ocr_result([("保存", 100, 100)])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=(100, 110), ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "pass"

    def test_max_actions_blocks(self) -> None:
        """Exceeding max actions should block."""
        backend = _MockChatBackend()
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="click", params={})
        ocr = _make_ocr_result([("保存", 100, 100)])
        ctx = {"step_count": 30, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=(100, 110), ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "blocked"
        assert result.reason == "MAX_ACTIONS"

    def test_max_duration_timeout(self) -> None:
        """Exceeding max duration should timeout."""
        backend = _MockChatBackend()
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=1)
        action = Action(type="click", params={})
        ocr = _make_ocr_result([("保存", 100, 100)])
        ctx = {"step_count": 5, "start_time": time.time() - 10, "safety_overrides": 0}

        result = guard.check(action, coords=(100, 110), ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "timeout"
        assert result.reason == "MAX_DURATION"

    def test_click_dangerous_then_unsafe_blocks(self) -> None:
        """Clicking near a dangerous keyword with VLM saying unsafe should block."""
        backend = _MockChatBackend(verdict="unsafe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="click", params={})
        # "删除" at (100, 100) — clicking near it
        ocr = _make_ocr_result([("删除", 80, 90)])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=(100, 100), ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "blocked"
        assert "删除" in result.reason or "Delete" in result.reason

    def test_click_dangerous_then_safe_passes(self) -> None:
        """Clicking near a dangerous keyword with VLM saying safe should pass."""
        backend = _MockChatBackend(verdict="safe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="click", params={})
        # "删除" at (80, 90), center at (105, 100), click at (100, 100) — within 30px
        ocr = _make_ocr_result([("删除", 80, 90)])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=(100, 100), ocr=ocr, goal="clean up files", session_ctx=ctx)

        assert result.decision == "pass"

    def test_type_dangerous_blocks(self) -> None:
        """Typing a dangerous command should block."""
        backend = _MockChatBackend(verdict="unsafe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="type", params={"text": "rm -rf /"})
        ocr = _make_ocr_result([])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=None, ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "blocked"

    def test_key_combo_dangerous_blocks(self) -> None:
        """Blacklisted key combo should block."""
        backend = _MockChatBackend(verdict="unsafe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="key_combo", params={"keys": ["alt", "f4"]})
        ocr = _make_ocr_result([])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=None, ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "blocked"

    def test_safe_type_passes(self) -> None:
        """Normal typing should pass."""
        backend = _MockChatBackend(verdict="unsafe")
        second = SecondCheck(chat_backend=backend, max_overrides_per_session=3)
        guard = SafetyGuard(second_check=second, max_session_actions=30, max_session_duration_s=600)
        action = Action(type="type", params={"text": "hello world"})
        ocr = _make_ocr_result([])
        ctx = {"step_count": 5, "start_time": time.time(), "safety_overrides": 0}

        result = guard.check(action, coords=None, ocr=ocr, goal="test", session_ctx=ctx)

        assert result.decision == "pass"
