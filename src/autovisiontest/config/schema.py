"""Pydantic configuration models for AutoVisionTest."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PlannerConfig(BaseModel):
    """Configuration for the Planner agent (large VLM)."""

    backend: Literal["claude_api", "openai_api", "dashscope_api", "vllm_local"] = "vllm_local"
    model: str = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
    api_key_env: Optional[str] = Field(
        default=None,
        description="Environment variable name holding the API key (cloud backends only).",
    )
    max_tokens: int = 1024
    temperature: float = 0.3
    endpoint: Optional[str] = Field(
        default=None,
        description="Custom API endpoint URL (for vllm_local or self-hosted).",
    )

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {v}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def _validate_max_tokens(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"max_tokens must be >= 1, got {v}")
        return v


class ActorConfig(BaseModel):
    """Configuration for the Actor agent (small grounding VLM)."""

    backend: Literal["showui_local", "osatlas_local", "vllm_local"] = "showui_local"
    model: str = "showlab/ShowUI-2B"
    endpoint: Optional[str] = Field(
        default=None,
        description="Inference endpoint URL for the grounding model.",
    )
    confidence_threshold: float = Field(
        default=0.5,
        description="Minimum grounding confidence to accept a prediction.",
    )

    @field_validator("confidence_threshold")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence_threshold must be between 0.0 and 1.0, got {v}")
        return v


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
    """Top-level configuration model combining all sub-configs."""

    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    actor: ActorConfig = Field(default_factory=ActorConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
