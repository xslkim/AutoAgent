"""T J.2 — Notepad regression replay E2E test.

Runs the AutoVisionTest pipeline against Windows Notepad in regression mode:
1. Ensure J.1 has created a recording (consolidated)
2. Delete out.txt from previous run
3. Start session again with the same goal → regression mode
4. Verify regression mode is used (not exploratory)
5. Verify total time < 60 seconds
6. Verify result.status == "PASS"

Prerequisites:
- T J.1 must have been run successfully first (to create recording)
- VLM services running
- Windows desktop with Notepad available

Usage:
    pytest tests/e2e/test_notepad_regression.py -v --run-e2e
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# E2E marker
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.environ.get("AUTOVT_RUN_E2E"),
    reason="E2E test disabled. Set AUTOVT_RUN_E2E=1 to enable.",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SANDBOX_DIR = Path(r"C:\TestSandbox")
OUTPUT_FILE = SANDBOX_DIR / "out.txt"
NOTEPAD_PATH = r"C:\Windows\System32\notepad.exe"
GOAL = "打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt"
MAX_WAIT_SECONDS = 120  # 2 minutes (regression should be < 60s)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_scheduler():
    """Create a SessionScheduler from default config."""
    from autovisiontest.backends.showui import ShowUIGroundingBackend
    from autovisiontest.config.loader import load_config
    from autovisiontest.scheduler.session_scheduler import SessionScheduler

    config = load_config()
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
        raise ValueError(f"Unsupported planner backend for E2E: {planner_backend}")

    grounding = ShowUIGroundingBackend(
        model=config.actor.model,
        endpoint=config.actor.endpoint or "http://localhost:8001/v1",
        confidence_threshold=config.actor.confidence_threshold,
    )

    data_dir = config.runtime.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    return SessionScheduler(
        chat_backend=chat,
        grounding_backend=grounding,
        data_dir=data_dir,
        max_steps=config.runtime.max_steps,
        confidence_threshold=config.actor.confidence_threshold,
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_notepad_regression_fast_replay():
    """T J.2: Notepad regression replay E2E test.

    Steps:
        1. Verify recording exists (from J.1)
        2. Remove output file
        3. Start session (should use regression mode)
        4. Verify regression mode is used
        5. Poll until completion (max 2 min)
        6. Assert PASS
        7. Assert elapsed < 60s
    """
    from autovisiontest.cases.store import RecordingStore
    from autovisiontest.config.loader import load_config
    from autovisiontest.scheduler.session_store import SessionStore, SessionStatus

    # 1. Verify recording exists
    config = load_config()
    data_dir = config.runtime.data_dir
    store = RecordingStore(data_dir)
    recordings = store.list_all()

    assert len(recordings) > 0, (
        "No recordings found. Run T J.1 (test_notepad_exploration) first to create one."
    )

    # Find recording matching our goal
    recording = store.find_for_goal(NOTEPAD_PATH, GOAL)
    assert recording is not None, (
        f"No recording found for goal='{GOAL}' app='{NOTEPAD_PATH}'. "
        "Run T J.1 first."
    )

    # 2. Remove output file
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()
    assert not OUTPUT_FILE.exists(), "Failed to delete output file"

    # 3. Start session
    scheduler = _create_scheduler()
    session_id = scheduler.start_session(
        goal=GOAL,
        app_path=NOTEPAD_PATH,
    )
    assert session_id, "start_session should return a session_id"

    # 4. Verify regression mode
    session_store = SessionStore(data_dir)
    record = session_store.load(session_id)
    assert record is not None, f"Session record not found: {session_id}"
    assert record.mode == "regression", (
        f"Expected regression mode, got: {record.mode}"
    )

    # 5. Poll until completion
    start = time.time()
    while time.time() - start < MAX_WAIT_SECONDS:
        status = scheduler.get_status(session_id)
        if status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
            break
        time.sleep(0.5)
    else:
        scheduler.stop(session_id)
        scheduler.shutdown()
        pytest.fail(f"Session {session_id} did not complete within {MAX_WAIT_SECONDS}s")

    elapsed = time.time() - start
    report = scheduler.get_report(session_id)
    scheduler.shutdown()

    # 6. Assert PASS
    final_record = session_store.load(session_id)
    assert final_record is not None
    assert final_record.status == SessionStatus.COMPLETED, (
        f"Expected COMPLETED, got {final_record.status}. "
        f"termination_reason={final_record.termination_reason}"
    )

    # 7. Assert elapsed < 60s
    assert elapsed < 60.0, (
        f"Regression took {elapsed:.1f}s, expected < 60s"
    )

    # Verify output file
    assert OUTPUT_FILE.exists(), "Output file not created"
    content = OUTPUT_FILE.read_text(encoding="utf-8", errors="replace")
    assert "hello world" in content.lower(), (
        f"Expected 'hello world' in file, got: {content[:200]}"
    )

    print(f"\n{'='*60}")
    print(f"  Session: {session_id}")
    print(f"  Mode: {final_record.mode}")
    print(f"  Status: {final_record.status}")
    print(f"  Elapsed: {elapsed:.1f}s (< 60s required)")
    print(f"  Output: {content[:100]}")
    print(f"{'='*60}")
