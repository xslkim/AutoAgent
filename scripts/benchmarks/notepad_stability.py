#!/usr/bin/env python3
"""Notepad stability benchmark (§T J.4).

Runs the AutoVisionTest regression mode against Notepad 20 times and
reports success rate, latency statistics, and failure screenshots.

Usage:
    python scripts/benchmarks/notepad_stability.py

    # Custom iterations
    python scripts/benchmarks/notepad_stability.py --iterations 10

    # Custom endpoint
    python scripts/benchmarks/notepad_stability.py --endpoint http://gpu:8001/v1

Acceptance: success rate >= 90%, results recorded in notepad_stability.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULTS_MD = _ROOT / "tests" / "benchmarks" / "notepad_stability.md"
SANDBOX_DIR = Path(r"C:\TestSandbox")
OUTPUT_FILE = SANDBOX_DIR / "out.txt"
NOTEPAD_PATH = r"C:\Windows\System32\notepad.exe"
GOAL = "打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt"
DEFAULT_ITERATIONS = 20


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Result of a single stability run."""

    iteration: int
    session_id: str
    success: bool
    elapsed_s: float
    mode: str
    termination_reason: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_scheduler(config_path: Path | None = None):
    """Create SessionScheduler from config."""
    from autovisiontest.backends.showui import ShowUIGroundingBackend
    from autovisiontest.config.loader import load_config
    from autovisiontest.scheduler.session_scheduler import SessionScheduler

    config = load_config(config_path)
    planner_backend = config.planner.backend

    if planner_backend == "vllm_local":
        from autovisiontest.backends.vllm_chat import VLLMChatBackend

        chat = VLLMChatBackend(
            model=config.planner.model,
            endpoint=config.planner.endpoint or "http://localhost:8000/v1",
            max_tokens=config.planner.max_tokens,
            temperature=config.planner.temperature,
        )
    elif planner_backend == "openai_api":
        from autovisiontest.backends.openai_backend import OpenAIChatBackend

        chat = OpenAIChatBackend(
            model=config.planner.model,
            api_key=os.environ.get(config.planner.api_key_env or "", ""),
        )
    elif planner_backend == "claude_api":
        from autovisiontest.backends.claude import ClaudeChatBackend

        chat = ClaudeChatBackend(
            model=config.planner.model,
            api_key=os.environ.get(config.planner.api_key_env or "", ""),
        )
    else:
        raise ValueError(f"Unsupported planner backend: {planner_backend}")

    grounding = ShowUIGroundingBackend(
        model=config.actor.model,
        endpoint=config.actor.endpoint or "http://localhost:8001/v1",
        confidence_threshold=config.actor.confidence_threshold,
    )

    data_dir = config.runtime.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    return (
        SessionScheduler(
            chat_backend=chat,
            grounding_backend=grounding,
            data_dir=data_dir,
            max_steps=config.runtime.max_steps,
            confidence_threshold=config.actor.confidence_threshold,
        ),
        config,
    )


def _run_single(i: int, config_path: Path | None = None) -> RunResult:
    """Run a single regression iteration."""
    from autovisiontest.scheduler.session_store import SessionStore, SessionStatus

    # Clean output
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    scheduler, config = _create_scheduler(config_path)
    data_dir = config.runtime.data_dir

    try:
        session_id = scheduler.start_session(
            goal=GOAL,
            app_path=NOTEPAD_PATH,
        )

        session_store = SessionStore(data_dir)
        record = session_store.load(session_id)

        start = time.time()
        max_wait = 120
        while time.time() - start < max_wait:
            status = scheduler.get_status(session_id)
            if status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
                break
            time.sleep(0.5)
        else:
            scheduler.stop(session_id)
            return RunResult(
                iteration=i,
                session_id=session_id,
                success=False,
                elapsed_s=time.time() - start,
                mode=record.mode if record else "unknown",
                error="timeout",
            )

        elapsed = time.time() - start
        final_record = session_store.load(session_id)

        success = final_record.status == SessionStatus.COMPLETED if final_record else False
        mode = final_record.mode if final_record else "unknown"
        term_reason = final_record.termination_reason if final_record else None

        return RunResult(
            iteration=i,
            session_id=session_id,
            success=success,
            elapsed_s=elapsed,
            mode=mode,
            termination_reason=term_reason,
        )

    except Exception as exc:
        return RunResult(
            iteration=i,
            session_id="",
            success=False,
            elapsed_s=0.0,
            mode="error",
            error=str(exc),
        )
    finally:
        scheduler.shutdown()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _write_results_md(
    results: list[RunResult],
    output_path: Path,
) -> None:
    """Write results to Markdown file."""
    total = len(results)
    successes = sum(1 for r in results if r.success)
    success_rate = successes / total if total > 0 else 0.0

    latencies = [r.elapsed_s for r in results if r.success]
    avg_lat = statistics.mean(latencies) if latencies else 0
    med_lat = statistics.median(latencies) if latencies else 0
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else 0)

    status = "PASS" if success_rate >= 0.9 else "FAIL"

    lines = [
        "# Notepad Stability Benchmark Results (§T J.4)",
        "",
        f"**Status**: {status}",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Success rate**: {success_rate:.1%} ({successes}/{total})",
        f"**Threshold**: 90%",
        "",
        "## Latency Statistics (successful runs only)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Average | {avg_lat:.1f}s |",
        f"| Median | {med_lat:.1f}s |",
        f"| P95 | {p95_lat:.1f}s |",
        f"| Min | {min(latencies):.1f}s |" if latencies else "",
        f"| Max | {max(latencies):.1f}s |" if latencies else "",
        "",
        "## Detailed Results",
        "",
        "| # | Session ID | Mode | Success | Elapsed | Termination | Error |",
        "|---|------------|------|---------|---------|-------------|-------|",
    ]

    for r in results:
        ok_str = "YES" if r.success else "NO"
        term_str = r.termination_reason or "-"
        err_str = r.error or ""
        lines.append(
            f"| {r.iteration} | {r.session_id} | {r.mode} | {ok_str} | "
            f"{r.elapsed_s:.1f}s | {term_str} | {err_str} |"
        )

    # Failures summary
    failures = [r for r in results if not r.success]
    if failures:
        lines.extend([
            "",
            "## Failure Summary",
            "",
        ])
        for r in failures:
            lines.append(f"- Run #{r.iteration}: {r.error or r.termination_reason or 'unknown'}")

    lines.extend(["", "---", "*Generated by notepad_stability.py*"])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Notepad stability benchmark (§T J.4)")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path, default=_RESULTS_MD)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    print(f"Notepad Stability Benchmark — {args.iterations} iterations")
    print("=" * 60)

    # Verify recording exists
    from autovisiontest.cases.store import RecordingStore
    from autovisiontest.config.loader import load_config

    config = load_config(args.config)
    store = RecordingStore(config.runtime.data_dir)
    recording = store.find_for_goal(NOTEPAD_PATH, GOAL)

    if recording is None:
        print("ERROR: No recording found. Run T J.1 first to create one.")
        return 1

    print(f"Recording fingerprint: {recording.metadata.fingerprint}")
    print()

    results: list[RunResult] = []

    for i in range(1, args.iterations + 1):
        print(f"  [{i}/{args.iterations}] Running...", end=" ", flush=True)
        result = _run_single(i, args.config)
        results.append(result)

        status_str = "PASS" if result.success else "FAIL"
        print(f"{status_str}  {result.elapsed_s:.1f}s  mode={result.mode}", end="")
        if result.error:
            print(f"  err={result.error}", end="")
        print()

    # Summary
    successes = sum(1 for r in results if r.success)
    success_rate = successes / len(results)

    print()
    print("=" * 60)
    print(f"  Success rate: {success_rate:.1%} ({successes}/{len(results)})")
    latencies = [r.elapsed_s for r in results if r.success]
    if latencies:
        print(f"  Avg latency:  {statistics.mean(latencies):.1f}s")
        print(f"  Med latency:  {statistics.median(latencies):.1f}s")
    print(f"  Status:       {'PASS' if success_rate >= 0.9 else 'FAIL'}")
    print("=" * 60)

    # Write results
    _write_results_md(results, args.output)

    # Optional JSON
    if args.json:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps([
            {
                "iteration": r.iteration,
                "session_id": r.session_id,
                "success": r.success,
                "elapsed_s": round(r.elapsed_s, 2),
                "mode": r.mode,
                "termination_reason": r.termination_reason,
                "error": r.error,
            }
            for r in results
        ], indent=2))

    return 0 if success_rate >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
