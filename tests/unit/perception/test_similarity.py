"""Unit tests for SSIM similarity calculation."""

from __future__ import annotations

import numpy as np
import pytest

from autovisiontest.perception.similarity import ssim, ssim_bytes


class TestSSIM:
    def test_identical_images_returns_one(self) -> None:
        img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        result = ssim(img, img)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_different_images_below_threshold(self) -> None:
        a = np.zeros((100, 100, 3), dtype=np.uint8)
        b = np.full((100, 100, 3), 255, dtype=np.uint8)
        result = ssim(a, b)
        assert result < 0.3

    def test_different_sizes_handled(self) -> None:
        a = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        b = np.random.randint(0, 255, (80, 80, 3), dtype=np.uint8)
        # Should not raise
        result = ssim(a, b)
        assert 0.0 <= result <= 1.0

    def test_grayscale_input(self) -> None:
        img = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        result = ssim(img, img)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_slightly_modified_image_high_ssim(self) -> None:
        """A small amount of noise should still have high SSIM."""
        a = np.full((100, 100, 3), 128, dtype=np.uint8)
        b = a.copy()
        # Add a tiny amount of noise
        noise = np.random.randint(0, 5, (100, 100, 3), dtype=np.uint8)
        b = np.clip(a.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        result = ssim(a, b)
        assert result > 0.9

    def test_ssim_bytes(self) -> None:
        """Test SSIM with PNG bytes input."""
        import cv2

        a = np.full((100, 100, 3), 128, dtype=np.uint8)
        _, encoded = cv2.imencode(".png", a)
        png_bytes = encoded.tobytes()

        result = ssim_bytes(png_bytes, png_bytes)
        assert result == pytest.approx(1.0, abs=1e-6)
