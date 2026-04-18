"""Custom exception hierarchy for AutoVisionTest.

All exceptions inherit from AutoVTError and support serialization
via the ``to_dict`` method producing ``{"type": ..., "message": ..., "context": ...}``.
"""

from __future__ import annotations


class AutoVTError(Exception):
    """Base exception for all AutoVisionTest errors."""

    def __init__(self, message: str = "", *, context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def to_dict(self) -> dict:
        return {
            "type": type(self).__name__,
            "message": self.message,
            "context": self.context,
        }


# ── Config ──────────────────────────────────────────────────────────────


class ConfigError(AutoVTError):
    """Configuration loading or validation error."""


# ── Control ─────────────────────────────────────────────────────────────


class ControlError(AutoVTError):
    """Desktop control layer error."""


class AppLaunchError(ControlError):
    """Failed to launch the target application."""


class AppCrashedError(ControlError):
    """Target application crashed during execution."""


class ActionExecutionError(ControlError):
    """Failed to execute a mouse/keyboard action."""


# ── Perception ──────────────────────────────────────────────────────────


class PerceptionError(AutoVTError):
    """Visual perception layer error."""


class ScreenshotError(PerceptionError):
    """Failed to capture screenshot."""


class OCRError(PerceptionError):
    """OCR engine error."""


# ── Backend ─────────────────────────────────────────────────────────────


class BackendError(AutoVTError):
    """Model backend error."""

    def __init__(
        self,
        message: str = "",
        *,
        retryable: bool = False,
        context: dict | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.retryable = retryable

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["retryable"] = self.retryable
        return d


class ChatBackendError(BackendError):
    """Chat model backend error."""


class GroundingBackendError(BackendError):
    """Grounding model backend error."""


# ── Safety ──────────────────────────────────────────────────────────────


class SafetyError(AutoVTError):
    """Safety system error."""


class UnsafeActionError(SafetyError):
    """An action was blocked as unsafe."""


# ── Session ─────────────────────────────────────────────────────────────


class SessionError(AutoVTError):
    """Session management error."""


class SessionNotFoundError(SessionError):
    """Requested session does not exist."""


class SessionTimeoutError(SessionError):
    """Session exceeded maximum allowed duration."""


# ── Case ────────────────────────────────────────────────────────────────


class CaseError(AutoVTError):
    """Test case / recording error."""


class RecordingInvalidError(CaseError):
    """Recording is invalid or corrupted."""
