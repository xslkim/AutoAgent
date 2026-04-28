"""Attach-mode notepad session.

Runs AutoVisionTest in attach mode: the framework does NOT launch or close
any process — UI-TARS drives the whole UI flow from the current desktop.

The goal is kept intentionally short: a few-sentence skeleton describing
what success looks like, not a step-by-step script.  UI-TARS is a GUI
agent trained for exactly this kind of open-ended instruction, and
over-prescriptive prompts hurt more than they help.
"""
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from autovisiontest.logging_setup import setup_logging
setup_logging(level="INFO")

from autovisiontest.interfaces.cli_commands import _create_scheduler
from autovisiontest.scheduler.session_store import SessionStatus

GOAL = (
    "请从当前 Windows 桌面开始，通过点击 UI 元素打开记事本（Notepad）。"
    "在记事本中输入文字「今天天气真好」。"
    "输入完成后调用 finished 结束任务。"
)


def main() -> int:
    scheduler = _create_scheduler(config_path="config/model.yaml")
    if scheduler is None:
        print("ERROR: Failed to create scheduler")
        return 1

    print(f"Goal: {GOAL[:80]}...")
    print("Starting attach-mode session (no launch / no close by framework)")

    session_id = scheduler.start_session(
        goal=GOAL,
        app_path=None,
        launch=False,
    )
    print(f"Session ID: {session_id}")
    print("Waiting for completion...\n")

    last_step = -1
    try:
        while True:
            status = scheduler.get_status(session_id)
            if status is None:
                print("ERROR: Session not found")
                return 1
            ctx = scheduler.get_session_context(session_id)
            step = ctx.step_count if ctx else 0
            if step != last_step:
                print(f"  [{status.value}] step={step}", flush=True)
                last_step = step
            if status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
                break
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nInterrupted, stopping session...")
        scheduler.stop(session_id)

    final = scheduler.get_status(session_id)
    print(f"\nFinal status: {final.value}")

    ctx = scheduler.get_session_context(session_id)
    if ctx:
        print(f"Steps executed: {ctx.step_count}")
        print(f"Termination reason: {ctx.termination_reason}")
        for s in ctx.steps:
            act = s.action
            act_desc = f"{act.type}({act.params})" if act else "None"
            print(f"  step {s.idx}: intent={s.planner_intent!r}")
            print(f"          action={act_desc} target={s.actor_target_desc!r} conf={s.grounding_confidence}")
            print(f"          reflection={s.reflection!r}")
        if ctx.bug_hints:
            print("Bug hints:")
            for h in ctx.bug_hints:
                print(f"  - {h.description} (conf={h.confidence})")

    scheduler.shutdown()
    return 0 if final == SessionStatus.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
