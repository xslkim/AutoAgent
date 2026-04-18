"""Unit tests for engine core data models (T F.1)."""

from __future__ import annotations

import json

from autovisiontest.control.actions import Action
from autovisiontest.engine.models import (
    Assertion,
    AssertionResult,
    BugHint,
    SessionContext,
    StepRecord,
    TerminationReason,
)


class TestTerminationReason:
    def test_enum_values(self) -> None:
        assert TerminationReason.CRASH == "CRASH"
        assert TerminationReason.UNSAFE == "UNSAFE"
        assert TerminationReason.PASS == "PASS"
        assert TerminationReason.ERROR_DIALOG == "ERROR_DIALOG"
        assert TerminationReason.MAX_STEPS == "MAX_STEPS"
        assert TerminationReason.STUCK == "STUCK"
        assert TerminationReason.NO_PROGRESS == "NO_PROGRESS"
        assert TerminationReason.USER == "USER"
        assert TerminationReason.TARGET_NOT_FOUND == "TARGET_NOT_FOUND"
        assert TerminationReason.ASSERTION_FAILED == "ASSERTION_FAILED"

    def test_enum_from_string(self) -> None:
        assert TerminationReason("CRASH") is TerminationReason.CRASH
        assert TerminationReason("PASS") is TerminationReason.PASS


class TestStepRecord:
    def test_step_record_creation(self) -> None:
        action = Action(type="click", params={"x": 100, "y": 200})
        step = StepRecord(
            idx=0,
            planner_intent="click save button",
            actor_target_desc="save button",
            action=action,
            grounding_confidence=0.85,
        )
        assert step.idx == 0
        assert step.action is not None
        assert step.action.type == "click"

    def test_step_record_timestamp(self) -> None:
        step = StepRecord(idx=0)
        assert step.timestamp  # non-empty
        # Should be valid ISO 8601
        from datetime import datetime
        datetime.fromisoformat(step.timestamp)


class TestBugHint:
    def test_bug_hint_creation(self) -> None:
        hint = BugHint(
            description="Save button not responding",
            confidence=0.8,
            evidence="Click at (100,200) had no effect",
        )
        assert hint.confidence == 0.8

    def test_bug_hint_confidence_range(self) -> None:
        # Valid range
        BugHint(description="test", confidence=0.0)
        BugHint(description="test", confidence=1.0)
        # Invalid range
        try:
            BugHint(description="test", confidence=1.5)
            assert False, "Should have raised ValidationError"
        except Exception:
            pass


class TestModelsSerializeRoundtrip:
    def test_step_record_roundtrip(self) -> None:
        action = Action(type="type", params={"text": "hello"})
        step = StepRecord(
            idx=1,
            planner_intent="type text",
            action=action,
            grounding_confidence=0.9,
        )
        data = step.model_dump()
        restored = StepRecord.model_validate(data)
        assert restored.idx == 1
        assert restored.action is not None
        assert restored.action.type == "type"

    def test_session_context_roundtrip(self) -> None:
        ctx = SessionContext(
            goal="open notepad",
            mode="exploratory",
            steps=[
                StepRecord(idx=0, planner_intent="open app"),
                StepRecord(idx=1, planner_intent="type text"),
            ],
            bug_hints=[
                BugHint(description="crash on save", confidence=0.7)
            ],
        )
        data = ctx.model_dump()
        restored = SessionContext.model_validate(data)
        assert restored.goal == "open notepad"
        assert len(restored.steps) == 2
        assert len(restored.bug_hints) == 1

    def test_session_context_json_roundtrip(self) -> None:
        ctx = SessionContext(
            goal="test goal",
            mode="regression",
            termination_reason=TerminationReason.PASS,
        )
        json_str = ctx.model_dump_json()
        restored = SessionContext.model_validate_json(json_str)
        assert restored.goal == "test goal"
        assert restored.termination_reason == TerminationReason.PASS

    def test_assertion_roundtrip(self) -> None:
        assertion = Assertion(type="ocr_contains", params={"text": "hello"})
        data = assertion.model_dump()
        restored = Assertion.model_validate(data)
        assert restored.type == "ocr_contains"
        assert restored.params["text"] == "hello"

    def test_assertion_result_roundtrip(self) -> None:
        result = AssertionResult(type="ocr_contains", passed=True, detail="found")
        data = result.model_dump()
        restored = AssertionResult.model_validate(data)
        assert restored.passed is True


class TestSessionContextDefaults:
    def test_default_session_id(self) -> None:
        ctx = SessionContext()
        assert len(ctx.session_id) == 12

    def test_default_mode(self) -> None:
        ctx = SessionContext()
        assert ctx.mode == "exploratory"

    def test_default_empty_lists(self) -> None:
        ctx = SessionContext()
        assert ctx.steps == []
        assert ctx.assertions == []
        assert ctx.bug_hints == []
