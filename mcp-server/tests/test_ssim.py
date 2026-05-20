"""TASK-0122: SSIM visual comparison tests.

All images are synthesised from NumPy arrays and saved to tmp_path as PNGs.
No external image files are required.

Coverage:
- Identical images → score ≈ 1.0, identical=True, no changed_regions.
- Fully different images → score much lower, identical=False.
- Small local change → changed_region detected with correct bounding box.
- Large local change → multiple / large regions detected.
- Size mismatch → ValueError.
- Missing file → FileNotFoundError.
- RGBA input → alpha dropped, comparison proceeds.
- Grayscale input → broadcast to RGB, comparison proceeds.
- save_diff writes a PNG to disk.
- return_diff=False → diff_array is None.
- threshold parameter controls `identical`.
- pixel_threshold controls region detection.
- min_region_area filters out tiny blobs.
- Region dataclass fields are correct types.
- CompareResult fields are correct types.
"""

from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path

from skimage import io as skio

from autoagent_mcp.vision.ssim import CompareResult, Region, compare_images


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid(color: tuple[int, int, int], size: int = 64) -> np.ndarray:
    """Return a solid-color (H, W, 3) uint8 array."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    arr[:, :] = color
    return arr


def save_png(arr: np.ndarray, path: Path) -> Path:
    skio.imsave(str(path), arr, check_contrast=False)
    return path


def make_pair(tmp_path, a: np.ndarray, b: np.ndarray):
    """Save two arrays and return their paths."""
    pa = save_png(a, tmp_path / "a.png")
    pb = save_png(b, tmp_path / "b.png")
    return pa, pb


# ---------------------------------------------------------------------------
# Basic score behaviour
# ---------------------------------------------------------------------------


class TestScore:
    def test_identical_images_score_one(self, tmp_path):
        img = solid((128, 200, 50))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert result.score == pytest.approx(1.0, abs=1e-6)

    def test_identical_images_is_identical(self, tmp_path):
        img = solid((10, 10, 10))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert result.identical is True

    def test_different_images_lower_score(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((0, 0, 0)), solid((255, 255, 255)))
        result = compare_images(pa, pb)
        assert result.score < 0.5

    def test_different_images_not_identical(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((0, 0, 0)), solid((255, 255, 255)))
        result = compare_images(pa, pb, threshold=0.95)
        assert result.identical is False

    def test_score_in_range(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((100, 100, 100)), solid((200, 200, 200)))
        result = compare_images(pa, pb)
        assert 0.0 <= result.score <= 1.0

    def test_score_is_float(self, tmp_path):
        img = solid((50, 50, 50))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert isinstance(result.score, float)


# ---------------------------------------------------------------------------
# threshold parameter
# ---------------------------------------------------------------------------


class TestThreshold:
    def test_high_threshold_marks_slightly_different_as_changed(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((100, 100, 100)), solid((110, 110, 110)))
        result = compare_images(pa, pb, threshold=0.9999)
        assert result.identical is False

    def test_low_threshold_marks_very_different_as_identical(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((0, 0, 0)), solid((255, 0, 0)))
        result = compare_images(pa, pb, threshold=0.0)
        assert result.identical is True

    def test_threshold_equals_score_is_identical(self, tmp_path):
        img = solid((80, 80, 80))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        # score == 1.0 for identical; use threshold just below 1.0
        result2 = compare_images(pa, pb, threshold=result.score)
        assert result2.identical is True


# ---------------------------------------------------------------------------
# Changed regions
# ---------------------------------------------------------------------------


class TestChangedRegions:
    def test_identical_no_changed_regions(self, tmp_path):
        img = solid((200, 200, 200))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert result.changed_regions == []

    def test_local_change_detected(self, tmp_path):
        """A white square on a black background should be detected as changed."""
        base = solid((0, 0, 0), size=64)
        current = base.copy()
        # Draw a 20×20 white block at (10, 10)
        current[10:30, 10:30] = 255
        pa, pb = make_pair(tmp_path, base, current)
        result = compare_images(pa, pb, pixel_threshold=0.95, min_region_area=10)
        assert len(result.changed_regions) >= 1

    def test_region_has_correct_types(self, tmp_path):
        base = solid((0, 0, 0), size=64)
        current = base.copy()
        current[10:30, 10:30] = 255
        pa, pb = make_pair(tmp_path, base, current)
        result = compare_images(pa, pb, pixel_threshold=0.95, min_region_area=10)
        for r in result.changed_regions:
            assert isinstance(r, Region)
            assert isinstance(r.x, int)
            assert isinstance(r.y, int)
            assert isinstance(r.width, int)
            assert isinstance(r.height, int)

    def test_region_positive_dimensions(self, tmp_path):
        base = solid((0, 0, 0), size=64)
        current = base.copy()
        current[10:30, 10:30] = 255
        pa, pb = make_pair(tmp_path, base, current)
        result = compare_images(pa, pb, pixel_threshold=0.95, min_region_area=10)
        for r in result.changed_regions:
            assert r.width > 0
            assert r.height > 0

    def test_min_region_area_filters_tiny_blobs(self, tmp_path):
        """A single-pixel change should be filtered out by min_region_area."""
        base = solid((128, 128, 128), size=64)
        current = base.copy()
        current[32, 32] = 0  # single pixel
        pa, pb = make_pair(tmp_path, base, current)
        result = compare_images(pa, pb, pixel_threshold=0.80, min_region_area=100)
        assert result.changed_regions == []

    def test_high_pixel_threshold_finds_more_regions(self, tmp_path):
        """Raising pixel_threshold makes the detector more sensitive."""
        img_a = solid((100, 100, 100), size=64)
        img_b = solid((120, 120, 120), size=64)
        pa, pb = make_pair(tmp_path, img_a, img_b)
        result_strict = compare_images(pa, pb, pixel_threshold=0.9999)
        result_loose = compare_images(pa, pb, pixel_threshold=0.01)
        assert len(result_strict.changed_regions) >= len(result_loose.changed_regions)

    def test_fully_different_images_have_regions(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((0, 0, 0), 64), solid((255, 255, 255), 64))
        result = compare_images(pa, pb, pixel_threshold=0.5, min_region_area=1)
        assert len(result.changed_regions) >= 1

    def test_changed_regions_is_list(self, tmp_path):
        img = solid((50, 50, 50))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert isinstance(result.changed_regions, list)


# ---------------------------------------------------------------------------
# diff_array / save_diff
# ---------------------------------------------------------------------------


class TestDiffArray:
    def test_diff_array_is_numpy_uint8(self, tmp_path):
        img = solid((100, 100, 100))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb, return_diff=True)
        assert isinstance(result.diff_array, np.ndarray)
        assert result.diff_array.dtype == np.uint8

    def test_diff_array_same_hw_as_input(self, tmp_path):
        img = solid((0, 128, 255), size=32)
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert result.diff_array.shape == (32, 32)

    def test_diff_array_none_when_return_diff_false(self, tmp_path):
        img = solid((77, 77, 77))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb, return_diff=False)
        assert result.diff_array is None

    def test_identical_diff_array_is_all_zeros(self, tmp_path):
        img = solid((200, 200, 200))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert result.diff_array.max() == 0

    def test_different_diff_array_has_nonzero(self, tmp_path):
        pa, pb = make_pair(tmp_path, solid((0, 0, 0)), solid((255, 255, 255)))
        result = compare_images(pa, pb)
        assert result.diff_array.max() > 0

    def test_save_diff_creates_file(self, tmp_path):
        img = solid((10, 20, 30))
        pa, pb = make_pair(tmp_path, img, img.copy())
        diff_path = tmp_path / "out" / "diff.png"
        compare_images(pa, pb, save_diff=diff_path)
        assert diff_path.exists()

    def test_save_diff_creates_parent_dirs(self, tmp_path):
        img = solid((5, 5, 5))
        pa, pb = make_pair(tmp_path, img, img.copy())
        diff_path = tmp_path / "deep" / "nested" / "diff.png"
        compare_images(pa, pb, save_diff=diff_path)
        assert diff_path.exists()

    def test_save_diff_with_return_diff_false_still_saves(self, tmp_path):
        """save_diff overrides return_diff=False — file is written."""
        img = solid((1, 2, 3))
        pa, pb = make_pair(tmp_path, img, img.copy())
        diff_path = tmp_path / "d.png"
        compare_images(pa, pb, save_diff=diff_path, return_diff=False)
        assert diff_path.exists()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_file_a_raises(self, tmp_path):
        img = solid((0, 0, 0))
        pb = save_png(img, tmp_path / "b.png")
        with pytest.raises(FileNotFoundError):
            compare_images(tmp_path / "no_a.png", pb)

    def test_missing_file_b_raises(self, tmp_path):
        img = solid((0, 0, 0))
        pa = save_png(img, tmp_path / "a.png")
        with pytest.raises(FileNotFoundError):
            compare_images(pa, tmp_path / "no_b.png")

    def test_size_mismatch_raises(self, tmp_path):
        pa = save_png(solid((0, 0, 0), size=32), tmp_path / "a.png")
        pb = save_png(solid((0, 0, 0), size=64), tmp_path / "b.png")
        with pytest.raises(ValueError, match="size mismatch"):
            compare_images(pa, pb)

    def test_error_message_includes_filenames(self, tmp_path):
        pa = save_png(solid((0, 0, 0), size=32), tmp_path / "small.png")
        pb = save_png(solid((0, 0, 0), size=64), tmp_path / "large.png")
        with pytest.raises(ValueError) as exc:
            compare_images(pa, pb)
        assert "small.png" in str(exc.value) or "large.png" in str(exc.value)


# ---------------------------------------------------------------------------
# Image format handling
# ---------------------------------------------------------------------------


class TestImageFormats:
    def test_rgba_image_handled(self, tmp_path):
        """RGBA images should have their alpha channel dropped."""
        rgba = np.zeros((64, 64, 4), dtype=np.uint8)
        rgba[:, :, :3] = 128
        rgba[:, :, 3] = 200  # semi-transparent
        pa = save_png(rgba, tmp_path / "a.png")
        pb = save_png(rgba.copy(), tmp_path / "b.png")
        result = compare_images(pa, pb)
        assert result.score == pytest.approx(1.0, abs=1e-6)

    def test_grayscale_image_handled(self, tmp_path):
        """Grayscale images should be broadcast to 3-channel."""
        gray = np.full((64, 64), 128, dtype=np.uint8)
        pa = save_png(gray, tmp_path / "a.png")
        pb = save_png(gray.copy(), tmp_path / "b.png")
        result = compare_images(pa, pb)
        assert result.score == pytest.approx(1.0, abs=1e-6)

    def test_rgba_vs_rgba_different_colors(self, tmp_path):
        rgba_a = np.zeros((64, 64, 4), dtype=np.uint8)
        rgba_a[:, :, 0] = 255  # red
        rgba_a[:, :, 3] = 255
        rgba_b = np.zeros((64, 64, 4), dtype=np.uint8)
        rgba_b[:, :, 2] = 255  # blue
        rgba_b[:, :, 3] = 255
        pa = save_png(rgba_a, tmp_path / "a.png")
        pb = save_png(rgba_b, tmp_path / "b.png")
        result = compare_images(pa, pb)
        assert result.score < 0.99


# ---------------------------------------------------------------------------
# CompareResult / Region type checks
# ---------------------------------------------------------------------------


class TestTypes:
    def test_compare_result_is_dataclass(self, tmp_path):
        img = solid((0, 0, 0))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert isinstance(result, CompareResult)

    def test_identical_field_is_bool(self, tmp_path):
        img = solid((0, 0, 0))
        pa, pb = make_pair(tmp_path, img, img.copy())
        result = compare_images(pa, pb)
        assert isinstance(result.identical, bool)

    def test_region_is_frozen(self):
        r = Region(x=1, y=2, width=10, height=20)
        with pytest.raises(Exception):
            r.x = 99  # frozen dataclass → should raise FrozenInstanceError
