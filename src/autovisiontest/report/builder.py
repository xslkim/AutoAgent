"""Report builder — constructs structured reports from session data.

The builder converts a ``SessionContext`` (engine output) into a ``Report``
(report schema), applying screenshot delivery strategies:
- **Success**: only first and last step screenshots
- **Failure**: failed step ± 2 steps (up to 5 screenshots)
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autovisiontest.engine.models import (
    AssertionResult,
    SessionContext,
    StepRecord,
    TerminationReason,
)
from autovisiontest.report.schema import (
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

logger = logging.getLogger(__name__)


class ReportBuilder:
    """Build structured reports from session context.

    The builder transforms engine data into the protocol v2.0 report
    format, selecting key evidence screenshots according to the
    delivery strategy.
    """

    def build(
        self,
        session: SessionContext,
        evidence_dir: Path | None = None,
        include_base64: bool = True,
    ) -> Report:
        """Build a Report from a SessionContext.

        Args:
            session: The completed session data.
            evidence_dir: Directory containing evidence screenshots.
                Used to read screenshot files for base64 embedding.
            include_base64: If True, embed screenshots as base64 in
                key_evidence. If False, only include file paths.

        Returns:
            Complete Report model.
        """
        is_pass = session.termination_reason == TerminationReason.PASS

        # Build session metadata
        report_session = self._build_session(session)

        # Build app info
        report_app = ReportApp(path=session.app_path)

        # Build result
        report_result = self._build_result(session)

        # Build steps
        report_steps = self._build_steps(session)

        # Build assertions
        report_assertions = self._build_assertions(session)

        # Build key evidence
        key_evidence = self._build_key_evidence(
            session=session,
            evidence_dir=evidence_dir,
            include_base64=include_base64,
        )

        # Build bug hints
        bug_hints = self._build_bug_hints(session)

        return Report(
            session=report_session,
            goal=session.goal,
            app=report_app,
            result=report_result,
            steps=report_steps,
            assertions=report_assertions,
            key_evidence=key_evidence,
            bug_hints=bug_hints,
        )

    def to_json(self, report: Report, pretty: bool = True) -> str:
        """Serialize a Report to JSON string.

        Args:
            report: The Report to serialize.
            pretty: If True, format with indentation.

        Returns:
            JSON string.
        """
        indent = 2 if pretty else None
        return report.model_dump_json(indent=indent)

    def to_html(self, report: Report) -> str:
        """Generate a simple HTML summary of the report.

        This is a minimal implementation for MVP. A full HTML report
        can be added in a later phase.

        Args:
            report: The Report to render.

        Returns:
            HTML string.
        """
        status_color = "green" if report.result.status == "PASS" else "red"
        html = f"""<!DOCTYPE html>
<html><head><title>Test Report - {report.session.id}</title></head>
<body>
<h1>Test Report</h1>
<p><strong>Session:</strong> {report.session.id}</p>
<p><strong>Goal:</strong> {report.goal}</p>
<p><strong>Status:</strong> <span style="color:{status_color}">{report.result.status}</span></p>
<p><strong>Termination:</strong> {report.result.termination_reason}</p>
<p><strong>Steps:</strong> {len(report.steps)}</p>
<p><strong>Bug Hints:</strong> {len(report.bug_hints)}</p>
</body></html>"""
        return html

    # -- Internal helpers ----------------------------------------------------

    def _build_session(self, session: SessionContext) -> ReportSession:
        """Build ReportSession from SessionContext."""
        duration_ms = 0
        end_time = ""
        if session.start_time > 0:
            duration_ms = int(
                (datetime.now(timezone.utc).timestamp() - session.start_time)
                * 1000
            )
            end_time = datetime.now(timezone.utc).isoformat()

        start_time = ""
        if session.start_time > 0:
            start_time = datetime.fromtimestamp(
                session.start_time, tz=timezone.utc
            ).isoformat()

        return ReportSession(
            id=session.session_id,
            mode=session.mode,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
        )

    def _build_result(self, session: SessionContext) -> ReportResult:
        """Build ReportResult from SessionContext."""
        is_pass = session.termination_reason == TerminationReason.PASS

        # Find failed step index
        failed_step_idx = None
        if not is_pass and session.steps:
            # Last step is typically the failure point
            for step in reversed(session.steps):
                if step.action is not None:
                    failed_step_idx = step.idx
                    break

        return ReportResult(
            status="PASS" if is_pass else "FAIL",
            termination_reason=(
                session.termination_reason.value
                if session.termination_reason
                else ""
            ),
            summary=self._generate_summary(session),
            failed_step_idx=failed_step_idx,
        )

    def _generate_summary(self, session: SessionContext) -> str:
        """Generate a human-readable result summary."""
        if session.termination_reason == TerminationReason.PASS:
            return f"Goal achieved in {len(session.steps)} steps."
        elif session.termination_reason == TerminationReason.CRASH:
            return "Application crashed during execution."
        elif session.termination_reason == TerminationReason.UNSAFE:
            return "Session terminated due to unsafe action detection."
        elif session.termination_reason == TerminationReason.MAX_STEPS:
            return f"Maximum step limit ({session.step_count}) reached."
        else:
            reason = (
                session.termination_reason.value
                if session.termination_reason
                else "UNKNOWN"
            )
            return f"Session ended: {reason}"

    def _build_steps(self, session: SessionContext) -> list[ReportStep]:
        """Build ReportStep list from SessionContext."""
        report_steps: list[ReportStep] = []
        for step in session.steps:
            action_dict = step.action.model_dump() if step.action else None
            report_steps.append(
                ReportStep(
                    idx=step.idx,
                    timestamp=step.timestamp,
                    planner_intent=step.planner_intent,
                    actor_target_desc=step.actor_target_desc,
                    action=action_dict,
                    grounding_confidence=step.grounding_confidence,
                    before_screenshot=step.before_screenshot_path,
                    after_screenshot=step.after_screenshot_path,
                    reflection=step.reflection,
                )
            )
        return report_steps

    def _build_assertions(self, session: SessionContext) -> list[ReportAssertion]:
        """Build ReportAssertion list from SessionContext."""
        assertions: list[ReportAssertion] = []
        for i, assertion_result in enumerate(session.assertion_results):
            params = {}
            if i < len(session.assertions):
                params = session.assertions[i].params
            assertions.append(
                ReportAssertion(
                    type=assertion_result.type,
                    params=params,
                    result="PASS" if assertion_result.passed else "FAIL",
                    detail=assertion_result.detail,
                )
            )
        return assertions

    def _build_key_evidence(
        self,
        session: SessionContext,
        evidence_dir: Path | None,
        include_base64: bool,
    ) -> KeyEvidence:
        """Build KeyEvidence with screenshot selection strategy.

        - Success: first + last step screenshots
        - Failure: failed step ± 2 steps (max 5)
        """
        is_pass = session.termination_reason == TerminationReason.PASS
        steps = session.steps

        if not steps:
            return KeyEvidence()

        if is_pass:
            return self._select_success_evidence(
                steps, evidence_dir, include_base64
            )
        else:
            return self._select_failure_evidence(
                steps, evidence_dir, include_base64
            )

    def _select_success_evidence(
        self,
        steps: list[StepRecord],
        evidence_dir: Path | None,
        include_base64: bool,
    ) -> KeyEvidence:
        """Select first and last step screenshots for success reports."""
        context: list[EvidenceScreenshot] = []

        # First step
        if steps:
            context.append(
                self._make_evidence_screenshot(
                    steps[0], "First step", evidence_dir, include_base64
                )
            )

        # Last step (if different from first)
        if len(steps) > 1:
            context.append(
                self._make_evidence_screenshot(
                    steps[-1], "Last step", evidence_dir, include_base64
                )
            )

        return KeyEvidence(error_context_screenshots=context)

    def _select_failure_evidence(
        self,
        steps: list[StepRecord],
        evidence_dir: Path | None,
        include_base64: bool,
    ) -> KeyEvidence:
        """Select failed step ± 2 screenshots for failure reports."""
        # Find the failed step (last step with action)
        failed_idx = len(steps) - 1
        for step in reversed(steps):
            if step.action is not None:
                failed_idx = step.idx
                break

        # Select ± 2 steps around failure
        start_idx = max(0, failed_idx - 2)
        end_idx = min(len(steps), failed_idx + 3)  # +3 for exclusive range

        failed_screenshot: EvidenceScreenshot | None = None
        context: list[EvidenceScreenshot] = []

        for i in range(start_idx, end_idx):
            step = steps[i]
            ev = self._make_evidence_screenshot(
                step,
                f"Step {step.idx}",
                evidence_dir,
                include_base64,
            )
            context.append(ev)
            if step.idx == failed_idx:
                failed_screenshot = ev

        return KeyEvidence(
            failed_step_screenshot=failed_screenshot,
            error_context_screenshots=context,
        )

    def _make_evidence_screenshot(
        self,
        step: StepRecord,
        description: str,
        evidence_dir: Path | None,
        include_base64: bool,
    ) -> EvidenceScreenshot:
        """Create an EvidenceScreenshot from a StepRecord."""
        image_base64 = ""
        image_path = step.after_screenshot_path

        if include_base64 and evidence_dir and image_path:
            # Try to read the file and encode as base64
            try:
                full_path = Path(image_path)
                if not full_path.is_absolute() and evidence_dir:
                    full_path = evidence_dir / image_path
                if full_path.exists():
                    image_base64 = base64.b64encode(
                        full_path.read_bytes()
                    ).decode("ascii")
            except Exception:
                logger.debug(
                    "base64_encode_failed",
                    extra={"step_idx": step.idx, "path": image_path},
                )

        return EvidenceScreenshot(
            step_idx=step.idx,
            description=description,
            image_base64=image_base64,
            image_path=image_path,
        )

    def _build_bug_hints(self, session: SessionContext) -> list[ReportBugHint]:
        """Build ReportBugHint list from SessionContext."""
        hints: list[ReportBugHint] = []
        for hint in session.bug_hints:
            hints.append(
                ReportBugHint(
                    description=hint.description,
                    confidence=hint.confidence,
                    related_hypothesis=[],
                )
            )
        return hints
