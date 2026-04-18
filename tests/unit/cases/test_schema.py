"""Unit tests for cases/schema.py."""

from __future__ import annotations

import json

import pytest

from autovisiontest.cases.schema import AppConfig, CaseMetadata, Expect, Step, TestCase


class TestAppConfig:
    """Tests for AppConfig model."""

    def test_defaults(self) -> None:
        config = AppConfig(app_path="notepad.exe")
        assert config.app_path == "notepad.exe"
        assert config.app_args == []

    def test_with_args(self) -> None:
        config = AppConfig(app_path="test.exe", app_args=["--flag", "value"])
        assert len(config.app_args) == 2


class TestExpect:
    """Tests for Expect model."""

    def test_defaults(self) -> None:
        expect = Expect()
        assert expect.ssim_hash == ""
        assert expect.ocr_keywords == []

    def test_with_values(self) -> None:
        expect = Expect(ssim_hash="abc123", ocr_keywords=["OK", "保存"])
        assert expect.ssim_hash == "abc123"
        assert len(expect.ocr_keywords) == 2


class TestStep:
    """Tests for Step model."""

    def test_defaults(self) -> None:
        step = Step(idx=0)
        assert step.idx == 0
        assert step.action == {}
        assert step.expect == Expect()

    def test_with_action(self) -> None:
        step = Step(
            idx=1,
            planner_intent="click button",
            target_desc="the OK button",
            action={"type": "click", "params": {"button": "left"}},
            expect=Expect(ocr_keywords=["OK"]),
        )
        assert step.action["type"] == "click"


class TestCaseMetadata:
    """Tests for CaseMetadata model."""

    def test_defaults(self) -> None:
        meta = CaseMetadata()
        assert meta.fingerprint == ""
        assert meta.created_at != ""
        assert meta.version == 1

    def test_with_fingerprint(self) -> None:
        meta = CaseMetadata(fingerprint="abc123def456")
        assert meta.fingerprint == "abc123def456"


class TestTestCase:
    """Tests for TestCase model."""

    def test_minimal(self) -> None:
        case = TestCase(
            goal="open notepad",
            app_config=AppConfig(app_path="notepad.exe"),
        )
        assert case.goal == "open notepad"
        assert case.steps == []

    def test_with_steps(self) -> None:
        case = TestCase(
            goal="type hello",
            app_config=AppConfig(app_path="notepad.exe"),
            steps=[
                Step(idx=0, action={"type": "click", "params": {}}),
                Step(idx=1, action={"type": "type", "params": {"text": "hello"}}),
            ],
            metadata=CaseMetadata(fingerprint="fp1", step_count=2),
        )
        assert len(case.steps) == 2

    def test_schema_roundtrip_json(self) -> None:
        """TestCase can be serialized to JSON and back."""
        case = TestCase(
            goal="test roundtrip",
            app_config=AppConfig(app_path="test.exe", app_args=["--flag"]),
            steps=[
                Step(
                    idx=0,
                    planner_intent="click",
                    target_desc="button",
                    action={"type": "click", "params": {"button": "left"}},
                    expect=Expect(ssim_hash="hash1", ocr_keywords=["OK"]),
                ),
            ],
            metadata=CaseMetadata(fingerprint="fp1", step_count=1),
        )
        json_str = case.model_dump_json()
        restored = TestCase.model_validate_json(json_str)
        assert restored.goal == case.goal
        assert restored.app_config.app_path == case.app_config.app_path
        assert len(restored.steps) == 1
        assert restored.steps[0].expect.ocr_keywords == ["OK"]

    def test_schema_roundtrip_dict(self) -> None:
        """TestCase can be converted to dict and back."""
        case = TestCase(
            goal="test dict",
            app_config=AppConfig(app_path="test.exe"),
        )
        d = case.model_dump()
        restored = TestCase.model_validate(d)
        assert restored.goal == case.goal

    def test_schema_validation_errors(self) -> None:
        """Invalid data should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TestCase(goal=123, app_config="not a model")  # type: ignore

        with pytest.raises(ValidationError):
            TestCase(goal="test", app_config=AppConfig(app_path="test.exe"), steps="not a list")  # type: ignore
