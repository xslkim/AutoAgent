"""Unit tests for engine planner module (T F.3)."""

from __future__ import annotations

import json

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.control.actions import Action
from autovisiontest.engine.models import BugHint, SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.planner import Planner
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult
from autovisiontest.perception.facade import FrameSnapshot

import numpy as np


def _make_snapshot(texts: list[str] | None = None) -> FrameSnapshot:
    """Create a minimal FrameSnapshot for testing."""
    items = []
    if texts:
        for i, t in enumerate(texts):
            items.append(OCRItem(text=t, bbox=BoundingBox(x=10, y=10 + i * 30, w=50, h=20), confidence=0.9))
    ocr = OCRResult(items=items, image_size=(1920, 1080))
    return FrameSnapshot(
        screenshot=np.zeros((100, 100, 3), dtype=np.uint8),
        screenshot_png=b"\x89PNG" + b"\x00" * 10,
        ocr=ocr,
        timestamp=1.0,
    )


class _MockChatBackend:
    """Mock ChatBackend that returns a configurable Planner-compatible JSON."""

    def __init__(self, decision: dict | None = None) -> None:
        if decision is None:
            decision = {
                "reflection": "test",
                "done": False,
                "bug_hints": [],
                "next_intent": "click button",
                "target_desc": "the button",
                "action": {"type": "click", "params": {}},
            }
        self._response = json.dumps(decision)
        self.last_messages: list[Message] | None = None

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        self.last_messages = messages
        return ChatResponse(content=self._response, raw={}, usage=None)


class TestPlanner:
    def test_decide_happy_path(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        session = SessionContext(goal="open notepad", steps=[])
        snapshot = _make_snapshot()

        decision = planner.decide(session, snapshot)

        assert decision.next_intent == "click button"
        assert decision.action.type == "click"
        assert decision.done is False

    def test_decide_calls_backend_with_messages(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        session = SessionContext(goal="test goal", steps=[])
        snapshot = _make_snapshot()

        planner.decide(session, snapshot)

        assert backend.last_messages is not None
        assert len(backend.last_messages) == 2
        assert "test goal" in backend.last_messages[1].content

    def test_decide_history_truncation(self) -> None:
        """History with more than max_history steps should be truncated."""
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend, max_history_steps=5)

        # Create 10 steps
        steps = [
            StepRecord(idx=i, planner_intent=f"step {i}", action=Action(type="click", params={}))
            for i in range(10)
        ]
        session = SessionContext(goal="test", steps=steps)
        snapshot = _make_snapshot()

        planner.decide(session, snapshot)

        # Verify the backend was called (messages contain truncated history)
        assert backend.last_messages is not None
        # The user message should contain steps 0, 1, 6, 7, 8, 9
        user_content = backend.last_messages[1].content
        assert "step 0" in user_content
        assert "step 1" in user_content
        assert "step 9" in user_content
        # step 3 should be truncated out
        assert "step 3" not in user_content

    def test_decide_with_ocr(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        session = SessionContext(goal="test", steps=[])
        snapshot = _make_snapshot(texts=["File", "Edit", "View"])

        planner.decide(session, snapshot)

        user_content = backend.last_messages[1].content
        assert "File" in user_content

    def test_summarize_on_terminate_pass(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        session = SessionContext(goal="test", steps=[])

        hints = planner.summarize_on_terminate(session, TerminationReason.PASS)
        assert hints == []

    def test_summarize_on_terminate_with_existing_hints(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        existing = [BugHint(description="crash", confidence=0.8)]
        session = SessionContext(goal="test", steps=[], bug_hints=existing)

        hints = planner.summarize_on_terminate(session, TerminationReason.CRASH)
        assert len(hints) == 1
        assert hints[0].description == "crash"

    def test_summarize_on_terminate_failure_generates_hint(self) -> None:
        backend = _MockChatBackend()
        planner = Planner(chat_backend=backend)
        session = SessionContext(goal="open notepad", steps=[
            StepRecord(idx=0, planner_intent="try"),
        ])

        hints = planner.summarize_on_terminate(session, TerminationReason.CRASH)
        assert len(hints) == 1
        assert "CRASH" in hints[0].description
