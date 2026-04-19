"""Test case schema — Pydantic models for test case definition and storage.

Models correspond to the product document §4.3:
- TestCase: Top-level test case with metadata, steps, and expectations
- AppConfig: Application configuration for the test
- Step: A single recorded step
- Expect: Expected state after a step
- CaseMetadata: Metadata about the test case (fingerprints, timestamps, etc.)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Application configuration for a test case."""

    app_path: str
    app_args: list[str] = Field(default_factory=list)


class Expect(BaseModel):
    """Expected state after a step.

    Used for regression verification:
    - ssim_hash: Perceptual hash or SSIM score of the expected screenshot
    - ocr_keywords: Key OCR text that should be present
    """

    ssim_hash: str = ""
    ocr_keywords: list[str] = Field(default_factory=list)


class Step(BaseModel):
    """A single recorded step in a test case.

    Captures the action taken, the target description, and
    the expected state after the step.
    """

    idx: int
    planner_intent: str = ""
    target_desc: str = ""
    action: dict[str, Any] = {}  # Serialized Action model
    expect: Expect = Field(default_factory=Expect)


class CaseMetadata(BaseModel):
    """Metadata about a test case.

    Includes fingerprint, creation/update timestamps, and statistics.
    """

    fingerprint: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_session_id: str = ""
    step_count: int = 0
    version: int = 1


class TestCase(BaseModel):
    """Top-level test case definition.

    A TestCase represents a recorded (or manually defined) test that can
    be replayed in regression mode.  It captures the goal, application
    configuration, steps, expectations, and metadata.
    """

    __test__ = False  # Prevent pytest from trying to collect this class

    goal: str
    app_config: AppConfig
    steps: list[Step] = Field(default_factory=list)
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)
