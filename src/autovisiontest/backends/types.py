"""Shared data types for model backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Message:
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str
    images: list[bytes] = field(default_factory=list)


@dataclass(frozen=True)
class ChatResponse:
    """Response from a chat backend."""

    content: str
    raw: dict
    usage: dict | None = None


@dataclass(frozen=True)
class GroundingResponse:
    """Response from a grounding backend."""

    x: int
    y: int
    confidence: float
    raw: dict
