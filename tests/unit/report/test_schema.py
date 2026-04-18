"""Tests for report schema — protocol v2.0 Pydantic models."""

from __future__ import annotations

import json

import pytest

from autovisiontest.report.schema import (
    PROTOCOL_VERSION,
    EvidenceScreenshot,
    KeyEvidence,
    Report,
    ReportApp,
    ReportAssertion,
    ReportBugHint,
    ReportResult,
    ReportSession,
    ReportStep,
)


class TestReportSchema:
    """Tests for Report schema roundtrip and validation."""

    def test_report_schema_roundtrip(self) -> None:
        """Report serializes to JSON and deserializes back correctly."""
        report = Report(
            session=ReportSession(
                id="ts-001",
                trigger="cli",
                mode="exploratory",
                start_time="2026-04-18T10:00:00Z",
                end_time="2026-04-18T10:02:30Z",
                duration_ms=150000,
            ),
            goal="Open notepad and type hello",
            app=ReportApp(
                path="C:\\Windows\\notepad.exe",
                pid=12345,
                final_state="exited_normally",
            ),
            result=ReportResult(
                status="PASS",
                termination_reason="PASS",
                summary="Goal achieved successfully",
            ),
            steps=[
                ReportStep(
                    idx=1,
                    timestamp="2026-04-18T10:00:05Z",
                    planner_intent="Click File menu",
                    actor_target_desc="File menu",
                    action={"type": "click", "x": 32, "y": 45},
                    grounding_confidence=0.92,
                    before_screenshot="evidence/step1_before.png",
                    after_screenshot="evidence/step1_after.png",
                    reflection="Menu opened",
                ),
            ],
            assertions=[
                ReportAssertion(
                    type="file_exists",
                    params={"path": "C:\\test.txt"},
                    result="PASS",
                    detail="File exists",
                ),
            ],
            key_evidence=KeyEvidence(
                failed_step_screenshot=None,
                error_context_screenshots=[],
            ),
            bug_hints=[
                ReportBugHint(
                    description="Possible timing issue",
                    confidence=0.6,
                    related_hypothesis=["slow response", "race condition"],
                ),
            ],
        )

        # Serialize to JSON
        json_str = report.model_dump_json(indent=2)

        # Deserialize back
        parsed = Report.model_validate_json(json_str)

        assert parsed.protocol_version == report.protocol_version
        assert parsed.session.id == "ts-001"
        assert parsed.goal == "Open notepad and type hello"
        assert parsed.app.path == "C:\\Windows\\notepad.exe"
        assert parsed.result.status == "PASS"
        assert len(parsed.steps) == 1
        assert parsed.steps[0].grounding_confidence == 0.92
        assert len(parsed.assertions) == 1
        assert len(parsed.bug_hints) == 1
        assert parsed.bug_hints[0].related_hypothesis == [
            "slow response",
            "race condition",
        ]

    def test_report_protocol_version_stable(self) -> None:
        """Protocol version is always '2.0'."""
        assert PROTOCOL_VERSION == "2.0"

        report = Report()
        assert report.protocol_version == "2.0"

        # After serialization
        data = json.loads(report.model_dump_json())
        assert data["protocol_version"] == "2.0"

    def test_report_default_values(self) -> None:
        """Report has sensible defaults."""
        report = Report()
        assert report.session.id == ""
        assert report.session.trigger == "cli"
        assert report.session.mode == "exploratory"
        assert report.result.status == "FAIL"
        assert report.goal == ""
        assert report.steps == []
        assert report.assertions == []
        assert report.key_evidence.failed_step_screenshot is None
        assert report.bug_hints == []

    def test_evidence_screenshot_fields(self) -> None:
        """EvidenceScreenshot has all expected fields."""
        ev = EvidenceScreenshot(
            step_idx=5,
            description="Failed step screenshot",
            image_base64="base64data",
            image_path="evidence/step5_after.png",
        )
        assert ev.step_idx == 5
        assert ev.image_base64 == "base64data"

        # Roundtrip
        parsed = EvidenceScreenshot.model_validate_json(ev.model_dump_json())
        assert parsed.step_idx == ev.step_idx

    def test_report_assertion_result_validation(self) -> None:
        """ReportAssertion validates correctly."""
        assertion = ReportAssertion(
            type="ocr_contains",
            params={"text": "hello"},
            result="PASS",
        )
        assert assertion.type == "ocr_contains"

    def test_report_bug_hint_confidence_range(self) -> None:
        """BugHint confidence is clamped to [0, 1]."""
        # Valid range
        hint = ReportBugHint(description="test", confidence=0.5)
        assert hint.confidence == 0.5

        # Edge cases
        hint_low = ReportBugHint(description="test", confidence=0.0)
        assert hint_low.confidence == 0.0

        hint_high = ReportBugHint(description="test", confidence=1.0)
        assert hint_high.confidence == 1.0

        # Out of range
        with pytest.raises(Exception):
            ReportBugHint(description="test", confidence=1.5)

        with pytest.raises(Exception):
            ReportBugHint(description="test", confidence=-0.1)
