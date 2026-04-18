"""Tests for ReportBuilder — report construction from session data."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from autovisiontest.control.actions import Action
from autovisiontest.engine.models import (
    AssertionResult,
    BugHint,
    SessionContext,
    StepRecord,
    TerminationReason,
)
from autovisiontest.report.builder import ReportBuilder


@pytest.fixture
def builder() -> ReportBuilder:
    """Create a ReportBuilder."""
    return ReportBuilder()


def _make_session(
    status: TerminationReason = TerminationReason.PASS,
    step_count: int = 3,
    app_path: str = "C:\\Windows\\notepad.exe",
    goal: str = "Open notepad and type hello",
) -> SessionContext:
    """Create a test SessionContext with steps."""
    steps = []
    for i in range(step_count):
        steps.append(
            StepRecord(
                idx=i,
                planner_intent=f"Step {i}",
                actor_target_desc=f"Target {i}",
                action=Action(type="click", params={"x": 100, "y": 100}),
                grounding_confidence=0.9,
                before_screenshot_path=f"evidence/step_{i}_before.png",
                after_screenshot_path=f"evidence/step_{i}_after.png",
                reflection=f"Reflection {i}",
            )
        )

    session = SessionContext(
        session_id=uuid.uuid4().hex[:12],
        goal=goal,
        mode="exploratory",
        app_path=app_path,
        steps=steps,
        start_time=1000000.0,
        termination_reason=status,
    )
    return session


class TestReportBuilder:
    """Tests for ReportBuilder."""

    def test_build_success_report_minimal_evidence(
        self, builder: ReportBuilder
    ) -> None:
        """Success report only includes first and last step screenshots."""
        session = _make_session(status=TerminationReason.PASS, step_count=5)
        report = builder.build(session, evidence_dir=None, include_base64=False)

        assert report.result.status == "PASS"
        assert report.result.termination_reason == "PASS"
        assert len(report.steps) == 5

        # Key evidence: first + last only
        evidence = report.key_evidence
        assert evidence.failed_step_screenshot is None
        assert len(evidence.error_context_screenshots) == 2
        assert evidence.error_context_screenshots[0].step_idx == 0
        assert evidence.error_context_screenshots[1].step_idx == 4

    def test_build_failure_report_context_screenshots(
        self, builder: ReportBuilder
    ) -> None:
        """Failure report includes failed step ± 2 screenshots."""
        session = _make_session(status=TerminationReason.MAX_STEPS, step_count=10)
        report = builder.build(session, evidence_dir=None, include_base64=False)

        assert report.result.status == "FAIL"
        assert report.result.termination_reason == "MAX_STEPS"

        # Key evidence: up to 5 screenshots around failure
        evidence = report.key_evidence
        assert evidence.failed_step_screenshot is not None
        assert evidence.failed_step_screenshot.step_idx == 9  # last step

        # ± 2 from step 9 = steps 7,8,9 (start capped at 7)
        assert len(evidence.error_context_screenshots) == 3
        indices = [s.step_idx for s in evidence.error_context_screenshots]
        assert 7 in indices
        assert 8 in indices
        assert 9 in indices

    def test_build_failure_report_small_session(
        self, builder: ReportBuilder
    ) -> None:
        """Failure report with fewer than 5 steps includes all."""
        session = _make_session(status=TerminationReason.CRASH, step_count=2)
        report = builder.build(session, evidence_dir=None, include_base64=False)

        assert report.result.status == "FAIL"
        evidence = report.key_evidence
        assert len(evidence.error_context_screenshots) == 2

    def test_to_json_roundtrip(self, builder: ReportBuilder) -> None:
        """Report can be serialized to JSON and back."""
        session = _make_session(step_count=2)
        report = builder.build(session)

        json_str = builder.to_json(report)
        assert isinstance(json_str, str)

        # Parse and verify
        data = json.loads(json_str)
        assert data["protocol_version"] == "2.0"
        assert data["result"]["status"] == "PASS"
        assert len(data["steps"]) == 2

    def test_to_html(self, builder: ReportBuilder) -> None:
        """to_html produces valid HTML."""
        session = _make_session()
        report = builder.build(session)
        html = builder.to_html(report)

        assert "<html>" in html
        assert "PASS" in html
        assert session.goal in html

    def test_build_with_bug_hints(self, builder: ReportBuilder) -> None:
        """Bug hints are included in the report."""
        session = _make_session(status=TerminationReason.ASSERTION_FAILED)
        session.bug_hints = [
            BugHint(
                description="Possible timing issue",
                confidence=0.7,
                evidence="Screenshot shows blank screen",
            ),
        ]

        report = builder.build(session)
        assert len(report.bug_hints) == 1
        assert report.bug_hints[0].description == "Possible timing issue"
        assert report.bug_hints[0].confidence == 0.7

    def test_build_with_assertion_results(self, builder: ReportBuilder) -> None:
        """Assertion results are included in the report."""
        from autovisiontest.engine.models import Assertion

        session = _make_session()
        session.assertions = [
            Assertion(type="file_exists", params={"path": "test.txt"}),
        ]
        session.assertion_results = [
            AssertionResult(type="file_exists", passed=True, detail="File exists"),
        ]

        report = builder.build(session)
        assert len(report.assertions) == 1
        assert report.assertions[0].type == "file_exists"
        assert report.assertions[0].result == "PASS"

    def test_build_empty_session(self, builder: ReportBuilder) -> None:
        """Builder handles empty session (no steps)."""
        session = SessionContext(
            goal="empty test",
            app_path="test.exe",
            termination_reason=TerminationReason.PASS,
        )
        report = builder.build(session)

        assert report.result.status == "PASS"
        assert report.steps == []
        assert report.key_evidence.failed_step_screenshot is None
        assert report.key_evidence.error_context_screenshots == []

    def test_build_session_metadata(self, builder: ReportBuilder) -> None:
        """Session metadata is correctly populated."""
        session = _make_session()
        report = builder.build(session)

        assert report.session.id == session.session_id
        assert report.session.mode == "exploratory"
        assert report.session.duration_ms > 0
