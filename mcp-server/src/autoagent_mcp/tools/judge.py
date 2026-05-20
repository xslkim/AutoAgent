"""Claude Vision judge tool: judge_visual_diff.

Wraps :func:`~autoagent_mcp.vision.claude_judge.judge_diff` as an MCP tool.
The tool is a "second-opinion" complement to :func:`audit_visual_changes`:
use ``audit_visual_changes`` to detect *where* pixels changed (fast, free),
then call ``judge_visual_diff`` when you need Claude to explain *what* changed
in plain language (slower, costs API tokens).

No engine connection is required — both images must already be on disk.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.vision.claude_judge import DEFAULT_MODEL, judge_diff


def register(mcp: FastMCP) -> None:
    """Register judge_visual_diff on *mcp*."""

    @mcp.tool()
    async def judge_visual_diff(
        baseline_path: str,
        current_path: str,
        diff_path: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Use Claude Vision to describe what changed between two screenshots.

        This tool is a "second opinion" on top of SSIM: SSIM tells you *where*
        pixels changed; Claude Vision tells you *what* the change means
        (e.g. "the Submit button label changed from 'OK' to 'Confirm'").

        Requires the ``ANTHROPIC_API_KEY`` environment variable to be set.

        Args:
            baseline_path: Absolute path to the reference (before) screenshot.
            current_path:  Absolute path to the candidate (after) screenshot.
            diff_path:     Optional path to an SSIM diff heat-map image.
                           When provided it is included as a third image to
                           help Claude focus on the changed areas.
            model:         Anthropic model to use (default ``claude-opus-4-5``).
            max_tokens:    Maximum response tokens (default 512).

        Returns:
            On success::

                {
                  "changed": true,
                  "severity": "minor",
                  "description": "The OK button was renamed to Confirm.",
                  "details": ["Button label changed from 'OK' to 'Confirm'"],
                  "model": "claude-opus-4-5"
                }

            On error::

                {"success": false, "error": "..."}
        """
        try:
            result = judge_diff(
                baseline_path,
                current_path,
                diff_path=diff_path or None,
                model=model,
                max_tokens=max_tokens,
            )
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            # Covers anthropic.APIError, auth errors, network failures, …
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

        return {
            "changed": result.changed,
            "severity": result.severity,
            "description": result.description,
            "details": result.details,
            "model": result.model,
        }
