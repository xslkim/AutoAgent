"""Visual-audit tool: audit_visual_changes.

``audit_visual_changes`` is a high-level composite tool that:

1. Captures a screenshot of the current screen (wire call → engine adapter).
2. Compares it to a saved named baseline using SSIM.
3. Returns a structured result with a human-readable ``summary`` field and
   a boolean ``changed`` flag so the AI can branch on the outcome without
   having to interpret the raw SSIM score.

Compared to calling ``take_screenshot(compare_baseline=...)`` directly, this
tool is more ergonomic for audit loops: it owns the full screenshot + compare
lifecycle and surfaces ``changed`` / ``region_count`` / ``summary`` at the top
level.

Optional ``update_baseline`` flag: when ``True`` and changes are detected, the
freshly captured screenshot replaces the baseline, making the next audit treat
the current state as the new ground truth.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors
from autoagent_mcp.vision.baseline import (
    load_baseline_path,
    save_baseline,
)
from autoagent_mcp.vision.ssim import compare_images


def register(mcp: FastMCP) -> None:
    """Register audit_visual_changes on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def audit_visual_changes(
        baseline_name: str,
        screenshot_path: str,
        scope: Literal["fullscreen", "node", "rect"] = "fullscreen",
        node_id: str | None = None,
        rect: list[float] | None = None,
        threshold: float = 0.95,
        diff_path: str | None = None,
        update_baseline: bool = False,
    ) -> dict[str, Any]:
        """Capture a screenshot and compare it to a saved baseline in one step.

        This is the recommended tool for visual regression checks in test loops.
        It combines ``take_screenshot`` and ``compare_to_baseline`` into a
        single call and surfaces the result with semantic fields (``changed``,
        ``region_count``, ``summary``) that the AI can act on directly.

        Args:
            baseline_name:   Name of the baseline saved with ``save_baseline``.
            screenshot_path: Absolute path where the new screenshot is written.
            scope:           Capture region — ``"fullscreen"`` (default),
                             ``"node"`` (widget bounding box), or ``"rect"``.
            node_id:         Required when ``scope="node"``.
            rect:            ``[x, y, w, h]`` required when ``scope="rect"``.
            threshold:       SSIM score below which ``changed=True``
                             (default ``0.95``).
            diff_path:       When provided, a greyscale diff image is written
                             here (brighter pixel = larger change).
            update_baseline: When ``True`` and changes are detected, replace
                             the baseline with the freshly captured screenshot
                             so the next audit uses the new state as reference.

        Returns::

            {
              "changed": false,
              "score": 0.998,
              "region_count": 0,
              "changed_regions": [],
              "summary": "No visual changes detected (score: 0.998)",
              "screenshot_path": "/tmp/shot.png",
              "baseline_name": "login_screen",
              "baseline_path": "~/.autoagent/baselines/login_screen.png",
              "diff_path": null,
              "baseline_updated": false
            }

        On error (baseline missing, size mismatch, …)::

            {"success": false, "error": "..."}
        """
        # ------------------------------------------------------------------
        # 1. Load baseline (fail fast before making the wire call)
        # ------------------------------------------------------------------
        try:
            bl_path = load_baseline_path(baseline_name)
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        # ------------------------------------------------------------------
        # 2. Capture screenshot via engine adapter
        # ------------------------------------------------------------------
        params: dict[str, Any] = {"path": screenshot_path, "mode": scope}

        if scope == "node":
            if not node_id:
                return {"success": False, "error": "node_id is required when scope='node'"}
            params["id"] = node_id
        elif scope == "rect":
            if not rect or len(rect) < 4:
                return {"success": False, "error": "rect must be [x, y, w, h] when scope='rect'"}
            params["x"] = int(rect[0])
            params["y"] = int(rect[1])
            params["w"] = int(rect[2])
            params["h"] = int(rect[3])

        wire_result = await get_client().call("take_screenshot", params)
        captured_path = (wire_result or {}).get("path", screenshot_path)

        # ------------------------------------------------------------------
        # 3. SSIM comparison
        # ------------------------------------------------------------------
        try:
            cmp = compare_images(
                bl_path,
                captured_path,
                threshold=threshold,
                save_diff=diff_path or None,
                return_diff=False,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

        changed = not cmp.identical
        region_count = len(cmp.changed_regions)
        regions = [
            {"x": r.x, "y": r.y, "width": r.width, "height": r.height}
            for r in cmp.changed_regions
        ]

        if changed:
            summary = (
                f"{region_count} changed region(s) detected "
                f"(score: {cmp.score:.4f}, threshold: {threshold})"
            )
        else:
            summary = f"No visual changes detected (score: {cmp.score:.4f})"

        # ------------------------------------------------------------------
        # 4. Optionally update baseline
        # ------------------------------------------------------------------
        baseline_updated = False
        if update_baseline and changed:
            try:
                save_baseline(baseline_name, captured_path, overwrite=True)
                baseline_updated = True
            except Exception:
                pass  # non-fatal — result still contains the comparison

        return {
            "changed": changed,
            "score": round(cmp.score, 6),
            "region_count": region_count,
            "changed_regions": regions,
            "summary": summary,
            "screenshot_path": str(captured_path),
            "baseline_name": baseline_name,
            "baseline_path": str(bl_path),
            "diff_path": str(diff_path) if diff_path else None,
            "baseline_updated": baseline_updated,
        }
