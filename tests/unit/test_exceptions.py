"""Tests for the AutoVisionTest exception hierarchy."""

from __future__ import annotations

import pytest

from autovisiontest.exceptions import (
    ActionExecutionError,
    AppCrashedError,
    AppLaunchError,
    AutoVTError,
    BackendError,
    CaseError,
    ChatBackendError,
    ConfigError,
    ControlError,
    GroundingBackendError,
    OCRError,
    PerceptionError,
    RecordingInvalidError,
    SafetyError,
    ScreenshotError,
    SessionError,
    SessionNotFoundError,
    SessionTimeoutError,
    UnsafeActionError,
)


# ── Hierarchy tests ─────────────────────────────────────────────────────

HIERARCHY = {
    ConfigError: AutoVTError,
    ControlError: AutoVTError,
    AppLaunchError: ControlError,
    AppCrashedError: ControlError,
    ActionExecutionError: ControlError,
    PerceptionError: AutoVTError,
    ScreenshotError: PerceptionError,
    OCRError: PerceptionError,
    BackendError: AutoVTError,
    ChatBackendError: BackendError,
    GroundingBackendError: BackendError,
    SafetyError: AutoVTError,
    UnsafeActionError: SafetyError,
    SessionError: AutoVTError,
    SessionNotFoundError: SessionError,
    SessionTimeoutError: SessionError,
    CaseError: AutoVTError,
    RecordingInvalidError: CaseError,
}


@pytest.mark.parametrize("child,parent", list(HIERARCHY.items()), ids=lambda c: c.__name__)
def test_exception_hierarchy(child: type, parent: type) -> None:
    assert issubclass(child, parent)
    assert issubclass(child, AutoVTError)


def test_all_exceptions_inherit_from_autovterror() -> None:
    """Every exception class defined in the module must inherit from AutoVTError."""
    import autovisiontest.exceptions as exc_mod

    for name in dir(exc_mod):
        obj = getattr(exc_mod, name)
        if isinstance(obj, type) and issubclass(obj, BaseException) and obj is not AutoVTError:
            assert issubclass(obj, AutoVTError), f"{name} does not inherit from AutoVTError"


# ── to_dict tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "exc_cls",
    [AutoVTError, ConfigError, ControlError, AppLaunchError, AppCrashedError,
     ActionExecutionError, PerceptionError, ScreenshotError, OCRError,
     SafetyError, UnsafeActionError, SessionError, SessionNotFoundError,
     SessionTimeoutError, CaseError, RecordingInvalidError],
    ids=lambda c: c.__name__,
)
def test_to_dict_basic(exc_cls: type) -> None:
    exc = exc_cls("test message", context={"key": "value"})
    d = exc.to_dict()
    assert d["type"] == exc_cls.__name__
    assert d["message"] == "test message"
    assert d["context"] == {"key": "value"}


def test_to_dict_default_context_empty() -> None:
    exc = AutoVTError("msg")
    d = exc.to_dict()
    assert d["context"] == {}


def test_to_dict_backend_error_retryable() -> None:
    exc = BackendError("fail", retryable=True)
    d = exc.to_dict()
    assert d["retryable"] is True

    exc2 = BackendError("fail", retryable=False)
    d2 = exc2.to_dict()
    assert d2["retryable"] is False


def test_to_dict_chat_backend_error() -> None:
    exc = ChatBackendError("4xx", retryable=False, context={"status": 400})
    d = exc.to_dict()
    assert d["type"] == "ChatBackendError"
    assert d["retryable"] is False
    assert d["context"]["status"] == 400


def test_to_dict_grounding_backend_error() -> None:
    exc = GroundingBackendError("timeout", retryable=True)
    d = exc.to_dict()
    assert d["type"] == "GroundingBackendError"
    assert d["retryable"] is True
