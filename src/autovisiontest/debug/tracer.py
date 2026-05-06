"""DebugTracer — collects per-step debug data and saves an HTML report.

Data captured per step:
  * before / after full-resolution PNG screenshots
  * the JPEG actually sent to the model (after resize)
  * the instruction text (system prompt + goal)
  * number of history entries included in the prompt
  * the model's raw text response
  * the parsed thought, action type, params, and coordinates
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autovisiontest.engine.agent import AgentDecision


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BackendCallRecord:
    """Snapshot of one UITarsBackend.decide() invocation."""

    prompt_text: str
    history_count: int
    raw_response: str
    orig_size: tuple[int, int]   # (w, h) original screen resolution
    sent_size: tuple[int, int]   # (w, h) after resize for model
    sent_jpeg: bytes             # the JPEG bytes that were sent


@dataclass
class StepTrace:
    """Complete debug record for one fully-executed step."""

    step_idx: int
    timestamp: str
    before_png: bytes
    after_png: bytes | None
    backend_call: BackendCallRecord | None
    thought: str
    action_type: str
    action_params: dict
    coords: tuple[int, int] | None
    finished: bool = False
    parse_error: str | None = None


# ---------------------------------------------------------------------------
# DebugTracer
# ---------------------------------------------------------------------------


class DebugTracer:
    """Accumulates trace data throughout a session and writes an HTML report.

    Lifecycle
    ---------
    1. ``UITarsBackend.decide()`` calls ``on_backend_call()`` with the prompt
       text, raw response, and image sizing metadata.
    2. ``StepLoop.run()`` calls ``record_step()`` after each fully-executed
       step, passing the before/after screenshots and the parsed decision.
    3. After the session finishes, the caller sets ``session_*`` fields and
       calls ``save_html(path)`` to write the self-contained report.
    """

    def __init__(self) -> None:
        self._steps: list[StepTrace] = []
        self._pending_backend: BackendCallRecord | None = None

        # Filled in by the caller (cli_commands) after the session ends.
        self.session_id: str = ""
        self.session_goal: str = ""
        self.app_path: str = ""
        self.started_at: str = ""
        self.finished_at: str = ""
        self.final_status: str = ""

    # ------------------------------------------------------------------
    # Hooks called from the execution path
    # ------------------------------------------------------------------

    def on_backend_call(
        self,
        *,
        prompt_text: str,
        history_count: int,
        raw_response: str,
        orig_w: int,
        orig_h: int,
        sent_w: int,
        sent_h: int,
        sent_jpeg: bytes,
    ) -> None:
        """Called from UITarsBackend.decide() after each successful HTTP call."""
        self._pending_backend = BackendCallRecord(
            prompt_text=prompt_text,
            history_count=history_count,
            raw_response=raw_response,
            orig_size=(orig_w, orig_h),
            sent_size=(sent_w, sent_h),
            sent_jpeg=sent_jpeg,
        )

    def record_step(
        self,
        *,
        step_idx: int,
        before_png: bytes,
        after_png: bytes | None,
        decision: "AgentDecision",
    ) -> None:
        """Called from StepLoop.run() after each fully-executed step."""
        step = StepTrace(
            step_idx=step_idx,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            before_png=before_png,
            after_png=after_png,
            backend_call=self._pending_backend,
            thought=decision.thought,
            action_type=decision.action.type,
            action_params=dict(decision.action.params) if decision.action.params else {},
            coords=decision.coords,
            finished=decision.finished,
        )
        self._steps.append(step)
        self._pending_backend = None

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    @property
    def steps(self) -> list[StepTrace]:
        return self._steps

    def save_html(self, path: Path) -> None:
        """Generate and write the self-contained HTML debug report."""
        from autovisiontest.debug.html_report import generate_html

        html = generate_html(self)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers used by html_report
# ---------------------------------------------------------------------------


def png_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def jpeg_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
