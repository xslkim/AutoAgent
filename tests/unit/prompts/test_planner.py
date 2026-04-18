"""Unit tests for planner prompt module (T F.2)."""

from __future__ import annotations

import json

import pytest

from autovisiontest.control.actions import Action
from autovisiontest.engine.models import StepRecord
from autovisiontest.exceptions import ChatBackendError
from autovisiontest.prompts.planner import (
    PlannerDecision,
    build_planner_messages,
    parse_planner_response,
)


class TestBuildMessages:
    def test_build_messages_includes_goal(self) -> None:
        messages = build_planner_messages(goal="open notepad", history=[])
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert "open notepad" in messages[1].content

    def test_build_messages_includes_history(self) -> None:
        steps = [
            StepRecord(idx=0, planner_intent="click start", action=Action(type="click", params={})),
            StepRecord(idx=1, planner_intent="type text", action=Action(type="type", params={"text": "hello"})),
        ]
        messages = build_planner_messages(goal="test", history=steps)
        user_content = messages[1].content
        assert "click start" in user_content
        assert "type text" in user_content

    def test_build_messages_includes_ocr_summary(self) -> None:
        messages = build_planner_messages(
            goal="test", history=[], ocr_summary="File Edit View"
        )
        assert "File Edit View" in messages[1].content

    def test_build_messages_includes_reflection(self) -> None:
        messages = build_planner_messages(
            goal="test", history=[], last_reflection="Button not found"
        )
        assert "Button not found" in messages[1].content

    def test_system_prompt_loaded(self) -> None:
        messages = build_planner_messages(goal="test", history=[])
        assert len(messages[0].content) > 100  # Non-trivial system prompt


class TestParseResponse:
    def test_parse_valid_response(self) -> None:
        raw = json.dumps({
            "reflection": "Clicked save button",
            "done": False,
            "bug_hints": [],
            "next_intent": "Type filename",
            "target_desc": "filename input",
            "action": {"type": "type", "params": {"text": "test.txt"}},
        })
        decision = parse_planner_response(raw)

        assert decision.reflection == "Clicked save button"
        assert decision.done is False
        assert decision.next_intent == "Type filename"
        assert decision.target_desc == "filename input"
        assert decision.action.type == "type"
        assert decision.action.params["text"] == "test.txt"
        assert decision.bug_hints == []

    def test_parse_with_markdown_fence(self) -> None:
        raw = '```json\n{"reflection": "", "done": true, "bug_hints": [], "next_intent": "", "target_desc": "", "action": {"type": "wait", "params": {}}}\n```'
        decision = parse_planner_response(raw)
        assert decision.done is True

    def test_parse_with_bug_hints(self) -> None:
        raw = json.dumps({
            "reflection": "Save dialog did not appear",
            "done": False,
            "bug_hints": [
                {"description": "Save button unresponsive", "confidence": 0.8, "evidence": "No dialog after click"}
            ],
            "next_intent": "Try again",
            "target_desc": "save button",
            "action": {"type": "click", "params": {}},
        })
        decision = parse_planner_response(raw)
        assert len(decision.bug_hints) == 1
        assert decision.bug_hints[0].description == "Save button unresponsive"
        assert decision.bug_hints[0].confidence == 0.8

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ChatBackendError):
            parse_planner_response("this is not json at all, no braces")

    def test_parse_missing_optional_fields(self) -> None:
        raw = json.dumps({
            "action": {"type": "wait", "params": {}},
        })
        decision = parse_planner_response(raw)
        assert decision.reflection == ""
        assert decision.done is False
        assert decision.bug_hints == []
        assert decision.next_intent == ""
        assert decision.target_desc == ""

    def test_parse_with_trailing_text(self) -> None:
        raw = json.dumps({
            "reflection": "",
            "done": False,
            "bug_hints": [],
            "next_intent": "test",
            "target_desc": "",
            "action": {"type": "wait", "params": {}},
        }) + " some trailing text here"
        decision = parse_planner_response(raw)
        assert decision.next_intent == "test"

    def test_parse_no_json_object_raises(self) -> None:
        with pytest.raises(ChatBackendError, match="no JSON object"):
            parse_planner_response("plain text without any braces")
