"""SSIM-based visual comparison for UI screenshots.

Entry point: :func:`compare_images`.  It takes two image paths, computes the
Structural Similarity Index Measure (SSIM) via scikit-image, and returns a
:class:`CompareResult` with:

* ``score``           — scalar SSIM (0.0 = totally different, 1.0 = identical).
* ``identical``       — ``True`` when ``score >= threshold``.
* ``changed_regions`` — bounding boxes of areas whose local SSIM fell below
                        ``pixel_threshold``.
* ``diff_array``      — ``uint8`` NumPy array visualising per-pixel difference
                        (bright = changed); ``None`` when *return_diff* is
                        ``False``.

Images are loaded via ``skimage.io`` (backed by imageio).  Both images must
have the same spatial dimensions; :class:`ValueError` is raised otherwise.
RGBA images have their alpha channel dropped before comparison; grayscale
images are broadcast to 3-channel.

Usage::

    from autoagent_mcp.vision.ssim import compare_images

    result = compare_images("baseline.png", "current.png", save_diff="diff.png")
    print(result.score)            # e.g. 0.97
    print(result.identical)       # True / False
    print(result.changed_regions) # list of Region(x, y, width, height)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from skimage import io as skio
from skimage.color import rgb2gray
from skimage.measure import label, regionprops
from skimage.metrics import structural_similarity

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """Axis-aligned bounding box of a changed image region (pixel coordinates).

    The coordinate system matches image array indexing: ``(x, y)`` is the
    top-left corner; ``x`` increases right, ``y`` increases down.
    """

    x: int        # left edge (column index)
    y: int        # top edge (row index)
    width: int
    height: int


@dataclass
class CompareResult:
    """Result returned by :func:`compare_images`.

    Attributes:
        score:           Overall SSIM in ``[0.0, 1.0]``.  ``1.0`` means the
                         images are pixel-identical (up to floating-point).
        identical:       ``True`` when *score* >= the *threshold* passed to
                         :func:`compare_images`.
        changed_regions: Bounding boxes of areas where the local SSIM value
                         fell below *pixel_threshold*.  Small specks below
                         *min_region_area* pixels are omitted.
        diff_array:      ``uint8`` NumPy array of shape ``(H, W)`` where
                         brighter pixels represent larger local differences,
                         or ``None`` when *return_diff* was ``False``.
    """

    score: float
    identical: bool
    changed_regions: list[Region]
    diff_array: np.ndarray | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_images(
    path_a: str | os.PathLike,
    path_b: str | os.PathLike,
    *,
    threshold: float = 0.95,
    pixel_threshold: float = 0.80,
    min_region_area: int = 50,
    save_diff: str | os.PathLike | None = None,
    return_diff: bool = True,
) -> CompareResult:
    """Compare two screenshots using the Structural Similarity Index (SSIM).

    Args:
        path_a:           Reference (baseline) image path.
        path_b:           Candidate (current) image path.
        threshold:        Overall SSIM threshold for ``identical``.  Images
                          with ``score >= threshold`` are considered unchanged
                          (default ``0.95``).
        pixel_threshold:  Per-pixel SSIM below which a pixel is labelled
                          "changed" when detecting :attr:`~CompareResult.changed_regions`
                          (default ``0.80``).
        min_region_area:  Minimum area in pixels a connected changed-region must
                          have to appear in
                          :attr:`~CompareResult.changed_regions` (default ``50``).
        save_diff:        When not ``None``, the diff image is written to this
                          path as a PNG before returning.  Parent directories are
                          created automatically.
        return_diff:      When ``False``, ``CompareResult.diff_array`` is
                          ``None`` (saves memory for callers that only need
                          the score / regions).  When *save_diff* is set this
                          parameter is ignored — the array is always computed.

    Returns:
        :class:`CompareResult`.

    Raises:
        FileNotFoundError: Either *path_a* or *path_b* does not exist.
        ValueError:        The images have different spatial dimensions.
    """
    img_a = _load_rgb(path_a)
    img_b = _load_rgb(path_b)

    if img_a.shape != img_b.shape:
        raise ValueError(
            f"Image size mismatch: "
            f"{Path(path_a).name} is {img_a.shape[1]}×{img_a.shape[0]} "
            f"but {Path(path_b).name} is {img_b.shape[1]}×{img_b.shape[0]}"
        )

    gray_a = _to_grayscale_float(img_a)
    gray_b = _to_grayscale_float(img_b)

    # win_size must be odd, <= min image dimension, and >= 3.
    h, w = gray_a.shape
    win = min(7, h, w)
    if win % 2 == 0:
        win -= 1
    win = max(win, 3)

    score, ssim_map = structural_similarity(
        gray_a,
        gray_b,
        data_range=1.0,
        full=True,
        win_size=win,
    )

    # diff image: brighter pixel = larger difference
    diff_f = np.clip(1.0 - ssim_map, 0.0, 1.0)
    need_diff = return_diff or (save_diff is not None)
    diff_uint8 = (diff_f * 255).astype(np.uint8) if need_diff else None

    if save_diff is not None and diff_uint8 is not None:
        save_path = Path(save_diff)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        skio.imsave(str(save_path), diff_uint8, check_contrast=False)

    # Detect changed regions via connected-component labelling.
    changed_mask = ssim_map < pixel_threshold
    labeled = label(changed_mask)
    regions: list[Region] = []
    for prop in regionprops(labeled):
        if prop.area < min_region_area:
            continue
        min_row, min_col, max_row, max_col = prop.bbox
        regions.append(
            Region(
                x=int(min_col),
                y=int(min_row),
                width=int(max_col - min_col),
                height=int(max_row - min_row),
            )
        )

    return CompareResult(
        score=float(score),
        identical=float(score) >= threshold,
        changed_regions=regions,
        diff_array=diff_uint8 if return_diff else None,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_rgb(path: str | os.PathLike) -> np.ndarray:
    """Load *path* as an ``(H, W, 3)`` ``uint8`` RGB array.

    Handles: RGB, RGBA (alpha dropped), grayscale (broadcast to 3-channel),
    float images (rescaled to uint8).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p}")

    img = skio.imread(str(p))

    # RGBA → RGB
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    # Grayscale → RGB
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=2)

    # Float → uint8
    if img.dtype != np.uint8:
        img = (np.clip(img.astype(float), 0.0, 1.0) * 255).astype(np.uint8)

    return img


def _to_grayscale_float(img: np.ndarray) -> np.ndarray:
    """Convert ``(H, W, 3)`` ``uint8`` to ``(H, W)`` ``float64`` in ``[0, 1]``."""
    return rgb2gray(img.astype(np.float64) / 255.0)
