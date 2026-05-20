"""Screenshot and wait tools: take_screenshot, wait_for.

TASK-0124 extends ``take_screenshot`` with two optional baseline-integration
parameters:

* ``save_as_baseline`` — after capturing, copy the screenshot to the named
  baseline (calls :func:`~autoagent_mcp.vision.baseline.save_baseline`).
* ``compare_baseline`` — after capturing, run an SSIM comparison against the
  named baseline and embed the result in the return dict.

Both parameters are independent: you can save-only, compare-only, both, or
neither (the pre-0124 behaviour).
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
    """Register take_screenshot and wait_for on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def take_screenshot(
        save_path: str,
        scope: Literal["fullscreen", "node", "rect"] = "fullscreen",
        node_id: str | None = None,
        rect: list[float] | None = None,
        save_as_baseline: str | None = None,
        compare_baseline: str | None = None,
        baseline_threshold: float = 0.95,
        diff_path: str | None = None,
    ) -> dict[str, Any]:
        """Capture a screenshot and optionally integrate with the baseline workflow.

        Args:
            save_path:         Absolute path where the screenshot PNG is written.
            scope:             Capture region — ``"fullscreen"`` (default),
                               ``"node"`` (widget bounding box), or ``"rect"``
                               (explicit ``[x, y, w, h]``).
            node_id:           Required when ``scope="node"``.
            rect:              ``[x, y, w, h]`` required when ``scope="rect"``.
            save_as_baseline:  When set, the screenshot is also saved as a
                               named baseline (calls ``save_baseline``).  Pass
                               the same name you will later pass to
                               ``compare_to_baseline``.
            compare_baseline:  When set, the screenshot is compared against the
                               named baseline using SSIM.  The result is
                               embedded under ``"baseline_comparison"`` in the
                               return dict.
            baseline_threshold: SSIM threshold for ``identical`` when
                               *compare_baseline* is set (default ``0.95``).
            diff_path:         When *compare_baseline* is set and this is
                               provided, the diff image is saved here.

        Returns:
            Base fields (always)::

                {"saved_path": "...", "scope": "..."}

            With ``save_as_baseline``::

                {..., "baseline_saved": true, "baseline_name": "...",
                 "baseline_path": "..."}

            With ``compare_baseline``::

                {..., "baseline_comparison": {
                    "score": 0.987, "identical": true,
                    "changed_regions": [...], "diff_path": null
                }}
        """
        # -----------------------------------------------------------------
        # Build wire params
        # -----------------------------------------------------------------
        params: dict[str, Any] = {"path": save_path, "mode": scope}

        if scope == "node":
            if not node_id:
                raise ValueError("node_id is required when scope='node'")
            params["id"] = node_id

        elif scope == "rect":
            if not rect or len(rect) < 4:
                raise ValueError("rect must be [x, y, w, h] when scope='rect'")
            params["x"] = int(rect[0])
            params["y"] = int(rect[1])
            params["w"] = int(rect[2])
            params["h"] = int(rect[3])

        # -----------------------------------------------------------------
        # Call adapter
        # -----------------------------------------------------------------
        result = await get_client().call("take_screenshot", params)
        captured_path = (result or {}).get("path", save_path)

        response: dict[str, Any] = {
            "saved_path": captured_path,
            "scope": scope,
        }

        # -----------------------------------------------------------------
        # Optionally save as baseline
        # -----------------------------------------------------------------
        if save_as_baseline is not None:
            try:
                dest = save_baseline(save_as_baseline, captured_path, overwrite=True)
                response["baseline_saved"] = True
                response["baseline_name"] = save_as_baseline
                response["baseline_path"] = str(dest)
            except Exception as exc:
                response["baseline_saved"] = False
                response["baseline_error"] = str(exc)

        # -----------------------------------------------------------------
        # Optionally compare to baseline
        # -----------------------------------------------------------------
        if compare_baseline is not None:
            try:
                bl_path = load_baseline_path(compare_baseline)
                cmp = compare_images(
                    bl_path,
                    captured_path,
                    threshold=baseline_threshold,
                    save_diff=diff_path or None,
                    return_diff=False,
                )
                response["baseline_comparison"] = {
                    "score": round(cmp.score, 6),
                    "identical": cmp.identical,
                    "changed_regions": [
                        {"x": r.x, "y": r.y, "width": r.width, "height": r.height}
                        for r in cmp.changed_regions
                    ],
                    "diff_path": str(diff_path) if diff_path else None,
                    "baseline_name": compare_baseline,
                    "baseline_path": str(bl_path),
                }
            except FileNotFoundError as exc:
                response["baseline_comparison"] = {
                    "error": str(exc),
                    "baseline_name": compare_baseline,
                }
            except Exception as exc:
                response["baseline_comparison"] = {
                    "error": str(exc),
                    "baseline_name": compare_baseline,
                }

        return response

    @mcp.tool()
    @handle_tool_errors
    async def wait_for(
        condition: Literal[
            "widget_appeared",
            "widget_disappeared",
            "widget_visible",
            "text_changed",
        ],
        id: str,
        expected_value: str | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Block until a UI condition is met or the timeout expires.

        Conditions:

        * ``widget_appeared``    — the widget exists in the active scene.
        * ``widget_disappeared`` — the widget is absent from the active scene.
        * ``widget_visible``     — the widget is present **and** visible.
        * ``text_changed``       — the widget's text equals *expected_value*.

        Returns ``{"success": True, "elapsed_ms": N}`` on success; raises
        ``AdapterError(-32005)`` on timeout.
        """
        params: dict[str, Any] = {
            "condition": condition,
            "id": id,
            "timeout_ms": timeout_ms,
        }
        if expected_value is not None:
            params["expected_value"] = expected_value

        result = await get_client().call("wait_for", params)
        return result or {"success": True, "elapsed_ms": 0}
