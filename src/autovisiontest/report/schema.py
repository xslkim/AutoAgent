"""Report schema — Pydantic models for protocol v2.0 JSON output.

The report is the primary output of the framework, designed to be consumed
by AI programming agents.  Protocol version ``2.0`` includes:
- Session metadata (id, mode, trigger, timing)
- Goal and app information
- Result status with termination reason
- Per-step action traces with coordinates and grounding confidence
- Assertion results
- Key evidence screenshots (base64 or path)
- AI-generated bug hints with confidence scores
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Constant protocol version for all v2.0 reports
PROTOCOL_VERSION = "2.0"


# -- Sub-models -------------------------------------------------------------


class ReportSession(BaseModel):
    """Session metadata in a report."""

    id: str = ""
    trigger: str = "cli"  # "cli" | "http" | "mcp"
    mode: str = "exploratory"  # "exploratory" | "regression"
    recording_fingerprint: str | None = None
    start_time: str = ""  # ISO 8601
    end_time: str = ""  # ISO 8601
    duration_ms: int = 0


class ReportApp(BaseModel):
    """Application information in a report."""

    path: str = ""
    pid: int = 0
    final_state: str = ""  # "exited_normally" | "crashed" | "killed"


class ReportResult(BaseModel):
    """Result status and termination information."""

    status: str = "FAIL"  # "PASS" | "FAIL" | "ABORT"
    termination_reason: str = ""
    summary: str = ""
    failed_step_idx: int | None = None


class ReportStep(BaseModel):
    """Per-step action trace in a report."""

    idx: int
    timestamp: str = ""
    planner_intent: str = ""
    actor_target_desc: str = ""
    action: dict[str, Any] | None = None
    grounding_confidence: float | None = None
    before_screenshot: str = ""
    after_screenshot: str = ""
    reflection: str = ""


class ReportAssertion(BaseModel):
    """Assertion result in a report."""

    type: str
    params: dict[str, Any] = {}
    result: str = ""  # "PASS" | "FAIL"
    detail: str = ""


class EvidenceScreenshot(BaseModel):
    """A key evidence screenshot."""

    step_idx: int
    description: str = ""
    image_base64: str = ""
    image_path: str = ""


class KeyEvidence(BaseModel):
    """Key screenshots selected for the report."""

    failed_step_screenshot: EvidenceScreenshot | None = None
    error_context_screenshots: list[EvidenceScreenshot] = []


class ReportBugHint(BaseModel):
    """AI-generated bug hypothesis."""

    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    related_hypothesis: list[str] = []


# -- Top-level Report -------------------------------------------------------


class Report(BaseModel):
    """Top-level report model (protocol v2.0).

    This is the complete structured output of a test session, designed
    for consumption by AI programming agents.
    """

    protocol_version: str = PROTOCOL_VERSION
    session: ReportSession = Field(default_factory=ReportSession)
    goal: str = ""
    app: ReportApp = Field(default_factory=ReportApp)
    result: ReportResult = Field(default_factory=ReportResult)
    steps: list[ReportStep] = Field(default_factory=list)
    assertions: list[ReportAssertion] = Field(default_factory=list)
    key_evidence: KeyEvidence = Field(default_factory=KeyEvidence)
    bug_hints: list[ReportBugHint] = Field(default_factory=list)
