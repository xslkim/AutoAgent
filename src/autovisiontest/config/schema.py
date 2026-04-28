"""Pydantic configuration models for AutoVisionTest."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for the single-model GUI agent.

    Supported backends — both speak the UI-TARS ``Thought + Action(...)``
    dialect but differ in coordinate convention, so the factory picks the
    right parser transform for each:

    * ``uitars_local`` — UI-TARS-1.5-7B-(AWQ) served by vLLM; coordinates
      are in sent-image-pixel space (requires image pre-resize).
    * ``maiui_local`` — MAI-UI (Tongyi-MAI, Qwen3-VL based); coordinates
      are in the Qwen-VL ``[0, 1000]`` normalised canvas.
    """

    backend: Literal["uitars_local", "maiui_local"] = "uitars_local"
    model: str = Field(
        default="ui-tars-1.5-7b",
        description="Served-model-name registered with the vLLM server.",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible endpoint (e.g. http://localhost:8000/v1).",
    )
    max_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    language: Literal["Chinese", "English"] = Field(
        default="Chinese",
        description="Language used inside the Thought section (must match the model's training distribution).",
    )
    history_images: int = Field(
        default=3,
        ge=0,
        description="How many of the most recent past screenshots to re-send back to the model.",
    )
    timeout_s: float = Field(default=60.0, gt=0.0)


class RuntimeConfig(BaseModel):
    """Runtime limits and paths for test execution."""

    max_steps: int = Field(default=30, description="Maximum steps per session.")
    max_session_duration_s: int = Field(
        default=600, description="Maximum session duration in seconds."
    )
    step_wait_ms: int = Field(
        default=500, description="Wait time in ms between steps."
    )
    data_dir: Path = Field(
        default=Path("./data"),
        description="Root directory for runtime data (sessions, recordings, evidence).",
    )


class AppConfig(BaseModel):
    """Top-level configuration model.

    After the UI-TARS migration, all model configuration lives under the
    ``agent`` section.  Legacy ``planner`` / ``actor`` sections, if
    present in older YAML files, are ignored by :func:`load_config`.
    """

    agent: AgentConfig = Field(default_factory=AgentConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    model_config = {"extra": "ignore"}
