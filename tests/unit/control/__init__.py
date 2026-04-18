"""Tests for DPI awareness utilities."""

from __future__ import annotations

import ctypes
from unittest.mock import patch

import pytest

from autovisiontest.control.dpi import (
    _DPI_AWARENESS_ENABLED,
    enable_dpi_awareness,
    get_dpi_scale,
    get_primary_screen_size,
)


class TestEnableDpiAwareness:
    def test_enable_dpi_awareness_idempotent(self) -> None:
        """Calling twice should not raise."""
        enable_dpi_awareness()
        enable_dpi_awareness()
        # If we got here without error, idempotency holds

    def test_enable_dpi_awareness_sets_flag(self) -> None:
        """After calling, the module-level flag should be True."""
        import autovisiontest.control.dpi as dpi_mod

        dpi_mod._DPI_AWARENESS_ENABLED = False  # reset for test
        dpi_mod.enable_dpi_awareness()
        assert dpi_mod._DPI_AWARENESS_ENABLED is True

    def test_enable_dpi_awareness_fallback(self) -> None:
        """If SetProcessDpiAwareness fails, fallback to SetProcessDPIAware."""
        import autovisiontest.control.dpi as dpi_mod

        dpi_mod._DPI_AWARENESS_ENABLED = False

        # Make shcore fail but user32 succeed
        original_shcore = ctypes.windll.shcore.SetProcessDpiAwareness
        ctypes.windll.shcore.SetProcessDpiAwareness = MockRaise(OSError)
        try:
            dpi_mod.enable_dpi_awareness()
            assert dpi_mod._DPI_AWARENESS_ENABLED is True
        finally:
            ctypes.windll.shcore.SetProcessDpiAwareness = original_shcore


class MockRaise:
    """A callable that always raises the given exception."""

    def __init__(self, exc: type) -> None:
        self._exc = exc

    def __call__(self, *args: object, **kwargs: object) -> None:
        raise self._exc("mock")


class TestGetPrimaryScreenSize:
    def test_get_primary_screen_size_returns_tuple(self) -> None:
        """Return value should be (int, int) with both > 0."""
        w, h = get_primary_screen_size()
        assert isinstance(w, int)
        assert isinstance(h, int)
        assert w > 0
        assert h > 0


class TestGetDpiScale:
    def test_get_dpi_scale_returns_float(self) -> None:
        """Return value should be a positive float."""
        scale = get_dpi_scale()
        assert isinstance(scale, float)
        assert scale > 0

    def test_get_dpi_scale_reasonable_range(self) -> None:
        """Scale should be between 0.5 and 3.0 for any real display."""
        scale = get_dpi_scale()
        assert 0.5 <= scale <= 3.0
