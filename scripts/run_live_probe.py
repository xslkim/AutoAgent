"""Live single-agent smoke run with verbose per-step logging.

Separate from :mod:`run_notepad_test` — this script bypasses the scheduler
and uses :class:`UITarsBackend` + :class:`ActionExecutor` directly so:

* every step prints Thought + Action to stdout IN REAL TIME (no buffering);
* per-step evidence (before.png / after.png / decision.json) is saved under
  ``data/probes/<timestamp>/step_NN/`` so you can post-mortem without the
  scheduler's context.json;
* ``Ctrl+C`` writes a ``summary.json`` and exits cleanly — no matter where
  in the loop you interrupt.

Usage::

    # Simple notepad-open probe (default 8 steps, 20s Win+D delay).
    python scripts/run_live_probe.py

    # Custom goal + fewer steps.
    python scripts/run_live_probe.py \\
        --goal "打开计算器" \\
        --max-steps 5

    # Dry-run: decide but do not execute (safe for eyeballing).
    python scripts/run_live_probe.py --dry-run

Exit codes:
    0 — agent emitted ``finished()`` or dry-run reached max_steps cleanly.
    1 — internal error (network / parser / executor crash).
    2 — agent stopped without finishing (max_steps hit).
    130 — Ctrl+C.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---- sys.path so we can run from repo root without install -----------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Force UTF-8 on Windows consoles so Chinese thoughts render.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover — older Pythons / odd terminals
    pass

from autovisiontest.backends.maiui import MAIUIBackend  # noqa: E402
from autovisiontest.backends.uitars import (  # noqa: E402
    HistoryStep,
    UITarsBackend,
    UITarsDecision,
)
from autovisiontest.control.actions import NEED_TARGET, Action  # noqa: E402
from autovisiontest.control.executor import ActionExecutor  # noqa: E402
from autovisiontest.control.screenshot import capture_primary_screen  # noqa: E402
from autovisiontest.engine.agent import _uitars_to_action  # noqa: E402


# Per-backend defaults — these match the WSL deployment docs
# (docs/uitars_wsl2_deploy.md :8000  and  docs/maiui_wsl2_deploy.md :8001).
_BACKEND_DEFAULTS: dict[str, dict[str, str]] = {
    "uitars": {
        "endpoint": "http://localhost:8000/v1",
        "model": "ui-tars-1.5-7b",
    },
    "maiui": {
        "endpoint": "http://localhost:8001/v1",
        "model": "mai-ui-2b",
    },
}


DEFAULT_GOAL = (
    "请从当前 Windows 桌面开始，通过点击 UI 元素打开记事本（Notepad）。"
    "在记事本中输入文字「今天天气真好」。"
    "输入完成后调用 finished 结束任务。"
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _log(msg: str = "", *, end: str = "\n") -> None:
    """Print and flush — print() alone is block-buffered on some terminals."""
    sys.stdout.write(msg + end)
    sys.stdout.flush()


def _countdown(seconds: int) -> None:
    _log(f"=== 倒计时 {seconds}s，请立刻 Win+D 把前台窗口全压下去 ===")
    for i in range(seconds, 0, -1):
        _log(f"  T-{i}", end="\r" if i > 1 else "\n")
        time.sleep(1)
    _log("=== GO ===")


def _save_decision_json(
    out_path: Path,
    *,
    step_idx: int,
    goal: str,
    raw_response: str,
    ui_decision: UITarsDecision,
    action: Action,
    coords: tuple[int, int] | None,
    executed: bool,
    execute_error: str | None,
    latency_ms: float,
) -> None:
    """Dump everything we know about this step to disk."""
    payload: dict[str, Any] = {
        "step_idx": step_idx,
        "goal": goal,
        "latency_ms": round(latency_ms, 1),
        "model": {
            "raw_response": raw_response,
            "thought": ui_decision.thought,
            "action_type": ui_decision.action_type,
            "action_params": ui_decision.action_params,
            "point_xy": ui_decision.point_xy,
            "end_point_xy": ui_decision.end_point_xy,
            "finished": ui_decision.finished,
            "finished_content": ui_decision.finished_content,
            "parse_error": ui_decision.parse_error,
        },
        "projected_action": action.model_dump(),
        "executed": executed,
        "executed_coords": list(coords) if coords is not None else None,
        "execute_error": execute_error,
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_summary(
    session_dir: Path,
    *,
    goal: str,
    steps: list[dict[str, Any]],
    stop_reason: str,
) -> None:
    payload = {
        "goal": goal,
        "stop_reason": stop_reason,
        "n_steps": len(steps),
        "steps": steps,
    }
    (session_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Live UI-TARS probe with verbose logging")
    ap.add_argument("--goal", default=DEFAULT_GOAL, help="Natural-language instruction.")
    ap.add_argument("--max-steps", type=int, default=8, help="Hard cap on loop iterations.")
    ap.add_argument("--delay", type=int, default=20, help="Countdown seconds before first screenshot.")
    ap.add_argument("--step-wait-ms", type=int, default=800, help="Pause after executing each action.")
    ap.add_argument(
        "--backend",
        default="uitars",
        choices=list(_BACKEND_DEFAULTS),
        help="Which GUI-VLA backend to drive.  Changes the default endpoint + model.",
    )
    ap.add_argument(
        "--endpoint",
        default=None,
        help="Override backend's default endpoint (e.g. http://localhost:8001/v1).",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="Override backend's default served-model-name.",
    )
    ap.add_argument("--language", default="Chinese", choices=["Chinese", "English"])
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--history-images", type=int, default=3)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Decide but do not execute — safe for eyeballing.",
    )
    ap.add_argument("--out", default="data/probes", help="Base output directory.")
    args = ap.parse_args()

    # Resolve backend-specific endpoint/model defaults; explicit CLI flags
    # still win over the table.
    defaults = _BACKEND_DEFAULTS[args.backend]
    resolved_endpoint = args.endpoint or defaults["endpoint"]
    resolved_model = args.model or defaults["model"]

    # Prepare session dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = Path(args.out) / stamp
    session_dir.mkdir(parents=True, exist_ok=True)

    _log(f"goal       : {args.goal[:100]}{'…' if len(args.goal) > 100 else ''}")
    _log(f"backend    : {args.backend}")
    _log(f"endpoint   : {resolved_endpoint}")
    _log(f"model      : {resolved_model}")
    _log(f"max_steps  : {args.max_steps}")
    _log(f"dry_run    : {args.dry_run}")
    _log(f"session    : {session_dir}")
    _log("")

    # Flip a flag on SIGINT so the loop can exit cleanly after persisting
    # the current step — simpler than fighting with KeyboardInterrupt in
    # the middle of an httpx call.
    interrupted = {"v": False}

    def _on_sigint(signum, frame):  # noqa: ARG001
        interrupted["v"] = True
        _log("\n[!] Ctrl+C received — will exit after current step saves.")

    signal.signal(signal.SIGINT, _on_sigint)

    if args.delay > 0:
        _countdown(args.delay)

    backend_cls = UITarsBackend if args.backend == "uitars" else MAIUIBackend
    backend = backend_cls(
        model=resolved_model,
        endpoint=resolved_endpoint,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        language=args.language,
        history_images=args.history_images,
    )
    executor = ActionExecutor()

    history: list[HistoryStep] = []
    steps_summary: list[dict[str, Any]] = []
    stop_reason = "max_steps"
    final_exit = 2

    for step_idx in range(args.max_steps):
        if interrupted["v"]:
            stop_reason = "sigint"
            final_exit = 130
            break

        step_dir = session_dir / f"step_{step_idx:02d}"
        step_dir.mkdir(exist_ok=True)

        # ---- 1. Capture ----
        try:
            before_png = capture_primary_screen()
        except Exception as exc:
            _log(f"[step {step_idx}] capture failed: {exc}")
            stop_reason = f"capture_error: {exc}"
            final_exit = 1
            break
        (step_dir / "before.png").write_bytes(before_png)

        _log(f"--- step {step_idx} ---")
        _log(f"  captured {len(before_png)} bytes")

        # ---- 2. Decide ----
        t0 = time.monotonic()
        try:
            ui_decision = backend.decide(before_png, goal=args.goal, history=history)
        except Exception as exc:
            _log(f"[step {step_idx}] decide failed: {exc}")
            stop_reason = f"decide_error: {exc}"
            final_exit = 1
            break
        latency_ms = (time.monotonic() - t0) * 1000.0

        _log(f"  latency   : {latency_ms:.0f} ms")
        _log(f"  thought   : {ui_decision.thought[:160]}")
        _log(f"  action    : {ui_decision.action_type}  point={ui_decision.point_xy}  params={ui_decision.action_params}")
        if ui_decision.parse_error:
            _log(f"  [!] parse_error: {ui_decision.parse_error}")
        if ui_decision.raw_response:
            # Show the action line verbatim so we can sanity-check the dialect.
            for line in ui_decision.raw_response.splitlines():
                if line.strip().startswith("Action:"):
                    _log(f"  raw-action: {line.strip()}")
                    break

        action = _uitars_to_action(ui_decision)
        coords = ui_decision.point_xy

        # ---- 3. Early-exit conditions ----
        if ui_decision.finished:
            _save_decision_json(
                step_dir / "decision.json",
                step_idx=step_idx, goal=args.goal,
                raw_response=ui_decision.raw_response,
                ui_decision=ui_decision,
                action=action, coords=coords,
                executed=False, execute_error=None,
                latency_ms=latency_ms,
            )
            steps_summary.append({
                "idx": step_idx,
                "action_type": ui_decision.action_type,
                "coords": coords,
                "finished": True,
                "parse_error": ui_decision.parse_error,
                "thought_preview": ui_decision.thought[:80],
            })
            _log(f"  => finished: {ui_decision.finished_content!r}")
            stop_reason = "finished"
            final_exit = 0
            break

        if action.type in NEED_TARGET and coords is None:
            _log("  [!] action needs coords but parser produced none — skipping execute")
            _save_decision_json(
                step_dir / "decision.json",
                step_idx=step_idx, goal=args.goal,
                raw_response=ui_decision.raw_response,
                ui_decision=ui_decision,
                action=action, coords=coords,
                executed=False, execute_error="needs_target_no_coords",
                latency_ms=latency_ms,
            )
            steps_summary.append({
                "idx": step_idx,
                "action_type": action.type,
                "coords": None,
                "finished": False,
                "parse_error": ui_decision.parse_error or "needs_target_no_coords",
                "thought_preview": ui_decision.thought[:80],
            })
            # Keep going — maybe next frame gives a better answer.
            continue

        # ---- 4. Execute (unless dry-run) ----
        executed = False
        execute_error: str | None = None
        if args.dry_run:
            _log("  (dry-run — skipping execute)")
        else:
            try:
                executor.execute(action, coords=coords)
                executed = True
                _log("  executed.")
            except Exception as exc:
                execute_error = str(exc)
                _log(f"  [!] execute failed: {exc}")

        # ---- 5. Settle + after ----
        time.sleep(args.step_wait_ms / 1000.0)
        try:
            after_png = capture_primary_screen()
            (step_dir / "after.png").write_bytes(after_png)
        except Exception as exc:
            _log(f"  [!] after-capture failed: {exc}")

        # ---- 6. Persist decision + update history ----
        _save_decision_json(
            step_dir / "decision.json",
            step_idx=step_idx, goal=args.goal,
            raw_response=ui_decision.raw_response,
            ui_decision=ui_decision,
            action=action, coords=coords,
            executed=executed, execute_error=execute_error,
            latency_ms=latency_ms,
        )

        # UI-TARS history needs the assistant's Thought + Action as text;
        # screenshot is attached so the model can compare before/after.
        action_summary = ui_decision.raw_response.splitlines()
        summary_line = next(
            (ln for ln in action_summary if ln.strip().startswith("Action:")),
            ui_decision.action_type,
        )
        history.append(HistoryStep(
            thought=ui_decision.thought,
            action_summary=summary_line.replace("Action:", "").strip() or ui_decision.action_type,
            screenshot_png=before_png,
        ))

        steps_summary.append({
            "idx": step_idx,
            "action_type": ui_decision.action_type,
            "coords": coords,
            "finished": False,
            "parse_error": ui_decision.parse_error,
            "thought_preview": ui_decision.thought[:80],
        })

    # ---- Summary ----
    _write_summary(session_dir, goal=args.goal, steps=steps_summary, stop_reason=stop_reason)
    _log("")
    _log(f"stop_reason : {stop_reason}")
    _log(f"n_steps     : {len(steps_summary)}")
    _log(f"session_dir : {session_dir}")
    _log(f"summary     : {session_dir / 'summary.json'}")
    return final_exit


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Signal handler should catch it first, but just in case.
        sys.exit(130)
