"""T J.1 — Notepad exploration E2E test.

Runs the full AutoVisionTest pipeline against Windows Notepad in exploratory mode:
1. Clean C:\\TestSandbox\\
2. Start session with goal: "打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt"
3. Wait for completion (max 5 minutes)
4. Verify result.status == "PASS"
5. Verify C:\\TestSandbox\\out.txt exists and contains "hello world"
6. Verify recordings/ has a new fingerprint file

Prerequisites:
- VLM Planner service running (e.g., Qwen2.5-VL-7B on port 8000)
- VLM Actor service running (e.g., ShowUI-2B on port 8001)
- Windows desktop with Notepad available
- C:\\TestSandbox\\ directory writable

Usage:
    pytest tests/e2e/test_notepad_exploration.py -v --run-e2e
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# E2E marker — must opt-in with --run-e2e flag
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
MAX_WAIT_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_sandbox() -> None:
    """Remove and recreate the sandbox directory."""
    if SANDBOX_DIR.exists():
        shutil.rmtree(SANDBOX_DIR)
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


def _create_scheduler():
    """Create a SessionScheduler from default config."""
    from autovisiontest.backends.showui import ShowUIGroundingBackend
    from autovisiontest.config.loader import load_config
    from autovisiontest.scheduler.session_scheduler import SessionScheduler

    # Try to use vLLM for chat backend
    config = load_config()

    # Import the appropriate chat backend
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


def test_notepad_exploration_end_to_end():
    """T J.1: Notepad exploratory E2E test.

    Steps:
        1. Clean sandbox
        2. Record existing recordings count
        3. Start exploratory session
        4. Poll until completion (max 5 min)
        5. Assert PASS status
        6. Assert output file exists with expected content
        7. Assert new recording was created
    """
    from autovisiontest.cases.store import RecordingStore
    from autovisiontest.config.loader import load_config
    from autovisiontest.scheduler.session_store import SessionStatus

    # 1. Clean sandbox
    _clean_sandbox()
    assert not OUTPUT_FILE.exists(), "Sandbox should be clean"

    # 2. Record baseline recordings count
    config = load_config()
    data_dir = config.runtime.data_dir
    store = RecordingStore(data_dir)
    recordings_before = store.list_all()

    # 3. Create scheduler and start session
    scheduler = _create_scheduler()
    session_id = scheduler.start_session(
        goal=GOAL,
        app_path=NOTEPAD_PATH,
    )

    assert session_id, "start_session should return a session_id"

    # 4. Poll until completion
    start = time.time()
    while time.time() - start < MAX_WAIT_SECONDS:
        status = scheduler.get_status(session_id)
        if status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
            break
        time.sleep(1.0)
    else:
        scheduler.stop(session_id)
        scheduler.shutdown()
        pytest.fail(f"Session {session_id} did not complete within {MAX_WAIT_SECONDS}s")

    elapsed = time.time() - start

    # Get report before shutdown
    report = scheduler.get_report(session_id)
    record = scheduler.get_session_context(session_id)
    scheduler.shutdown()

    # 5. Assert status
    status = scheduler.get_status(session_id) if report else SessionStatus.FAILED
    # Re-read status from the store since scheduler is shut down
    from autovisiontest.scheduler.session_store import SessionStore

    session_store = SessionStore(data_dir)
    final_record = session_store.load(session_id)

    assert final_record is not None, f"Session record not found: {session_id}"
    assert final_record.status == SessionStatus.COMPLETED, (
        f"Expected COMPLETED, got {final_record.status}. "
        f"termination_reason={final_record.termination_reason}"
    )

    # 6. Assert output file
    assert OUTPUT_FILE.exists(), (
        f"Output file not found: {OUTPUT_FILE}. "
        f"Session took {elapsed:.1f}s, status={final_record.status}"
    )

    content = OUTPUT_FILE.read_text(encoding="utf-8", errors="replace")
    assert "hello world" in content.lower(), (
        f"Expected 'hello world' in file, got: {content[:200]}"
    )

    # 7. Assert new recording was created
    recordings_after = store.list_all()
    assert len(recordings_after) > len(recordings_before), (
        f"No new recording created. Before: {len(recordings_before)}, "
        f"After: {len(recordings_after)}"
    )

    # Log some stats for debugging
    print(f"\n{'='*60}")
    print(f"  Session: {session_id}")
    print(f"  Status: {final_record.status}")
    print(f"  Termination: {final_record.termination_reason}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Output file: {OUTPUT_FILE}")
    print(f"  Content: {content[:100]}")
    print(f"  Recordings: {len(recordings_before)} -> {len(recordings_after)}")
    print(f"{'='*60}")
