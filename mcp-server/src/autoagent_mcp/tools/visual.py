"""Visual-comparison tools: save_baseline, compare_to_baseline.

``save_baseline`` stores a reference PNG under ``~/.autoagent/baselines/``.
``compare_to_baseline`` runs an SSIM comparison between a saved baseline and a
current screenshot and returns the score, changed regions, and an optional diff
image path.

Both tools are pure filesystem operations — they do **not** communicate with
the engine adapter and therefore do not use :func:`get_client` or
``@handle_tool_errors``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.vision.baseline import (
    delete_baseline,
    list_baselines,
    load_baseline_path,
    save_baseline as _save_baseline,
)
from autoagent_mcp.vision.ssim import compare_images
from autoagent_mcp.vision.lpips_subprocess import (
    LpipsNotAvailable,
    compare_lpips,
)


def register(mcp: FastMCP) -> None:
    """Register save_baseline and compare_to_baseline on *mcp*."""

    @mcp.tool()
    async def save_baseline(name: str, path: str) -> dict[str, Any]:
        """Save a screenshot as a named visual baseline.

        The image at *path* is copied to ``~/.autoagent/baselines/<name>.png``
        so it can later be referenced by ``compare_to_baseline``.  An existing
        baseline with the same name is silently overwritten.

        Args:
            name: Logical identifier for the baseline (e.g. ``"login_screen"``).
                  Must not be empty.  Slashes and backslashes are replaced with
                  underscores.
            path: Absolute path to the PNG screenshot to use as the baseline.

        Returns:
            ``{"saved": true, "baseline_path": "...", "name": "..."}``
        """
        try:
            dest = _save_baseline(name, path, overwrite=True)
            return {
                "saved": True,
                "name": name,
                "baseline_path": str(dest),
            }
        except FileNotFoundError as exc:
            return {"saved": False, "error": str(exc)}
        except ValueError as exc:
            return {"saved": False, "error": str(exc)}

    @mcp.tool()
    async def compare_to_baseline(
        name: str,
        current_path: str,
        threshold: float = 0.95,
        save_diff: str | None = None,
    ) -> dict[str, Any]:
        """Compare a screenshot to a saved baseline using SSIM.

        Args:
            name:         Baseline name (must have been saved with
                          ``save_baseline`` first).
            current_path: Absolute path to the PNG screenshot to compare.
            threshold:    SSIM score below which ``identical`` is ``False``
                          (default ``0.95``; range ``0.0``–``1.0``).
            save_diff:    When provided, a greyscale diff image highlighting
                          pixel-level changes is written to this path.

        Returns:
            On success::

                {
                  "score": 0.987,
                  "identical": true,
                  "changed_regions": [{"x": 10, "y": 20, "width": 50, "height": 30}],
                  "diff_path": "/path/to/diff.png" | null,
                  "baseline_path": "/path/to/baseline.png",
                  "current_path": "/path/to/current.png"
                }

            On error::

                {"success": false, "error": "..."}
        """
        try:
            baseline = load_baseline_path(name)
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        try:
            result = compare_images(
                baseline,
                current_path,
                threshold=threshold,
                save_diff=save_diff or None,
                return_diff=False,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        regions = [
            {"x": r.x, "y": r.y, "width": r.width, "height": r.height}
            for r in result.changed_regions
        ]

        return {
            "score": round(result.score, 6),
            "identical": result.identical,
            "changed_regions": regions,
            "diff_path": str(save_diff) if save_diff else None,
            "baseline_path": str(baseline),
            "current_path": str(current_path),
        }

    @mcp.tool()
    async def compare_lpips_to_baseline(
        name: str,
        current_path: str,
        threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Compare a screenshot to a saved baseline using LPIPS perceptual distance.

        LPIPS (Learned Perceptual Image Patch Similarity) uses a neural network
        to measure perceptual similarity.  It correlates better with human
        perception than pixel-based metrics like SSIM — small colour tweaks or
        anti-aliasing artefacts that fool SSIM are handled more gracefully.

        **Score semantics differ from SSIM**: LPIPS is a *distance* — lower is
        more similar.  ``score=0.0`` means perceptually identical; typical UI
        screenshots that look the same to the human eye score below ``0.05``.
        The ``identical`` flag is ``True`` when ``score < threshold``.

        Requires the ``[lpips]`` extras::

            pip install "autoagent-mcp[lpips]"

        Args:
            name:         Baseline name (saved with ``save_baseline`` first).
            current_path: Absolute path to the PNG screenshot to compare.
            threshold:    LPIPS distance above which ``identical`` is ``False``
                          (default ``0.1``; range ``0.0``–``1.0+``).

        Returns:
            On success::

                {
                  "score": 0.023,
                  "identical": true,
                  "threshold": 0.1,
                  "baseline_path": "/path/to/baseline.png",
                  "current_path": "/path/to/current.png"
                }

            On error::

                {"success": false, "error": "...", "hint": "..."}
        """
        try:
            baseline = load_baseline_path(name)
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        try:
            result = compare_lpips(baseline, current_path, threshold=threshold)
        except LpipsNotAvailable as exc:
            return {
                "success": False,
                "error": str(exc),
                "hint": "pip install 'autoagent-mcp[lpips]'",
            }
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        return {
            "score": round(result.score, 6),
            "identical": result.identical,
            "threshold": threshold,
            "baseline_path": str(baseline),
            "current_path": str(current_path),
        }

    @mcp.tool()
    async def list_baselines_tool() -> dict[str, Any]:
        """List the names of all saved visual baselines.

        Returns ``{"baselines": ["name1", "name2", ...]}``.
        """
        return {"baselines": list_baselines()}

    @mcp.tool()
    async def delete_baseline_tool(name: str) -> dict[str, Any]:
        """Delete a saved visual baseline by name.

        Returns ``{"deleted": true}`` if the baseline existed,
        ``{"deleted": false}`` if it was not found.
        """
        removed = delete_baseline(name)
        return {"deleted": removed, "name": name}
