"""Tests for DPI awareness utilities."""

from __future__ import annotations

import ctypes

import pytest

from autovisiontest.control.dpi import (
    enable_dpi_awareness,
    get_dpi_scale,
    get_primary_screen_size,
)


class TestEnableDpiAwareness:
    def test_enable_dpi_awareness_idempotent(self) -> None:
        """Calling twice should not raise."""
        enable_dpi_awareness()
        enable_dpi_awareness()

    def test_enable_dpi_awareness_sets_flag(self) -> None:
        """After calling, the module-level flag should be True."""
        import autovisiontest.control.dpi as dpi_mod

        dpi_mod._DPI_AWARENESS_ENABLED = False
        dpi_mod.enable_dpi_awareness()
        assert dpi_mod._DPI_AWARENESS_ENABLED is True


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
