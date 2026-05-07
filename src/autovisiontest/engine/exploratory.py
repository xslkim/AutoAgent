"""Exploratory runner — runs a test session in exploratory mode.

The runner wires up a single :class:`~autovisiontest.engine.agent.UITarsAgent`,
a step loop, a safety guard, and an evidence writer, then drives
everything to termination.

* ``launch=True``  — kill leftover app instances, launch the app, close
  it on exit.
* ``launch=False`` — **attach mode**; the agent drives the whole UI flow
  starting from whatever is already on screen (no kill, no launch, no
  close).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from autovisiontest.backends.uitars import UITarsBackend
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.control.process import (
    AppHandle,
    close_app,
    kill_related_processes,
    kill_stale_instances_for_app,
    launch_app,
    pick_calculator_monitor_pid,
)
from autovisiontest.engine.agent import UITarsAgent
from autovisiontest.engine.assertions import run_assertions
from autovisiontest.engine.models import Assertion, SessionContext, TerminationReason
from autovisiontest.engine.step_loop import StepLoop
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import Perception
from autovisiontest.report.evidence import EvidenceWriter as DiskEvidenceWriter
from autovisiontest.safety.guard import SafetyGuard
from autovisiontest.safety.second_check import SecondCheck

logger = logging.getLogger(__name__)


class _StepLoopEvidenceAdapter:
    """Bridge :class:`~autovisiontest.report.evidence.EvidenceWriter` to the
    :class:`~autovisiontest.engine.step_loop.EvidenceWriter` protocol.

    The disk writer expects ``write_step(idx, before, after, ocr=...)``;
    the step loop calls ``write_step_evidence(session_id, step_idx,
    before, after, ocr_text)``.  When ``after`` is ``None`` we fall back
    to the before-screenshot so two PNGs always land on disk.
    """

    def __init__(self, disk_writer: DiskEvidenceWriter) -> None:
        self._disk = disk_writer

    def write_step_evidence(
        self,
        session_id: str,  # noqa: ARG002
        step_idx: int,
        before_screenshot: bytes,
        after_screenshot: bytes | None,
        ocr_text: str,
    ) -> dict[str, str]:
        try:
            paths = self._disk.write_step(
                idx=step_idx,
                before=before_screenshot,
                after=after_screenshot or before_screenshot,
                ocr={"text": ocr_text} if ocr_text else None,
            )
            return {
                "before": str(paths["before"]),
                "after": str(paths["after"]),
            }
        except Exception:  # pragma: no cover — evidence must never break a run
            logger.exception("evidence_write_failed", extra={"step_idx": step_idx})
            return {}


class _StubChatBackend:
    """No-op :class:`ChatBackend` used to keep :class:`SecondCheck` wirable.

    SecondCheck is only consulted when the blacklist matcher flags an
    action — which never happens for benign goals.  If it *is* invoked,
    returning an empty reply causes SecondCheck to fall back to its
    ``"unsafe"`` safe default, so this stub is both cheap and correct.

    A proper, UI-TARS–driven safety arbitration path can replace this
    later once we decide whether UI-TARS itself, a second small VLM, or a
    rules-only guard should own that responsibility.
    """

    def chat(self, messages, images=None, response_format: str = "text"):  # noqa: ARG002
        from autovisiontest.backends.types import ChatResponse

        return ChatResponse(content="")


class ExploratoryRunner:
    """Run a test session in exploratory mode, end-to-end."""

    def __init__(
        self,
        agent_backend: UITarsBackend,
        max_steps: int = 30,
        data_dir: Path | None = None,
        stop_event: "threading.Event | None" = None,
        debug_tracer: "object | None" = None,
    ) -> None:
        self._agent_backend = agent_backend
        self._max_steps = max_steps
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._stop_event = stop_event
        self._debug_tracer = debug_tracer

    def run(
        self,
        goal: str,
        app_path: str | None,
        app_args: list[str] | None = None,
        launch: bool = True,
        session_id: str | None = None,
        assertions: list[Assertion] | None = None,
    ) -> SessionContext:
        session = SessionContext(
            goal=goal,
            mode="exploratory",
            app_path=app_path or "",
            app_args=app_args or [],
            start_time=time.time(),
        )
        if session_id is not None:
            session.session_id = session_id

        # T-1.4: implicitly prepend no_error_dialog assertion
        _ensure_implicit_assertions(session, assertions)

        handle: AppHandle | None = None
        disk_writer: DiskEvidenceWriter | None = None
        try:
            if launch:
                if not app_path:
                    raise ValueError("app_path is required when launch=True")
                kill_stale_instances_for_app(app_path)
                handle = launch_app(app_path, app_args)
                logger.info("app_launched", extra={"app_path": app_path, "pid": handle.pid})
                session.app_pid = handle.pid
                # Wait for main window to appear; raises AppLaunchError on timeout.
                from autovisiontest.control.window import wait_for_app_main_window

                wait_for_app_main_window(app_path, handle.pid, timeout_s=20.0)
                logger.info("app_window_ready", extra={"app_path": app_path, "pid": handle.pid})
                time.sleep(1.0)  # extra buffer for app initialization after window appears

                if handle.exe_name.lower() == "calc.exe":
                    try:
                        mp = pick_calculator_monitor_pid()
                        if mp is not None:
                            handle.monitor_pid = mp
                            logger.info(
                                "calc_monitor_pid_attached",
                                extra={"monitor_pid": mp},
                            )
                        else:
                            logger.warning(
                                "calc_monitor_pid_unresolved",
                                extra={"hint": "is_alive uses window/PowerShell fallbacks"},
                            )
                    except Exception:
                        logger.debug("calc_monitor_pid_skipped", extra={"app_path": app_path})
            else:
                logger.info("attach_mode", extra={"goal": goal})

            perception = Perception()
            agent = UITarsAgent(backend=self._agent_backend)
            terminator = Terminator(app_handle=handle, max_steps=self._max_steps)
            second_check = SecondCheck(chat_backend=_StubChatBackend())
            safety_guard = SafetyGuard(second_check=second_check)
            executor = ActionExecutor()

            evidence_writer: Optional[_StepLoopEvidenceAdapter] = None
            on_step_complete = None
            if self._data_dir is not None:
                disk_writer = DiskEvidenceWriter(
                    session_id=session.session_id,
                    data_dir=self._data_dir,
                )
                evidence_writer = _StepLoopEvidenceAdapter(disk_writer)
                _ctx_path = disk_writer.evidence_dir / "context.json"

                def on_step_complete(ctx: SessionContext, _p: Path = _ctx_path) -> None:
                    _p.write_text(ctx.model_dump_json(indent=2), encoding="utf-8")

            loop = StepLoop(
                agent=agent,
                terminator=terminator,
                safety_guard=safety_guard,
                executor=executor,
                perception=perception,
                evidence_writer=evidence_writer,
                stop_requested=self._stop_event,
                debug_tracer=self._debug_tracer,
                on_step_complete=on_step_complete,
            )

            reason = loop.run(session)
            logger.info("session_ended", extra={"reason": reason.value})

            # T-1.5 / T-1.3: assertion gate — finished only counts if
            # all assertions pass.  Run assertions on any terminal state
            # so the report is always populated.
            self._run_assertions(session, perception, disk_writer)

        except Exception:
            logger.exception("exploratory_run_failed")
            session.termination_reason = TerminationReason.CRASH

        finally:
            if handle is not None:
                try:
                    close_app(handle)
                    logger.info("app_closed", extra={"pid": handle.pid})
                except Exception:
                    logger.exception("app_close_failed")
                    try:
                        kill_related_processes(handle)
                    except Exception:
                        pass

        return session

    def _run_assertions(
        self,
        session: SessionContext,
        perception: Perception,
        disk_writer: DiskEvidenceWriter | None,
    ) -> None:
        """Run all assertions against the current session state.

        If the session was PASS but assertions fail, demote to
        ASSERTION_FAILED.  Assertion results are always written to
        ``session.assertion_results`` regardless of outcome.
        """
        if not session.assertions:
            return

        try:
            snapshot = perception.capture_snapshot()
        except Exception:
            logger.exception("assertion_snapshot_failed")
            return

        ctx: dict = {
            "ocr": snapshot.ocr,
            "screenshot_png": snapshot.screenshot_png,
            "chat_backend": _StubChatBackend(),
        }

        results = run_assertions(session.assertions, ctx)
        session.assertion_results = results

        all_passed = all(r.passed for r in results)
        if not all_passed and session.termination_reason == TerminationReason.PASS:
            logger.warning("assertion_failed_demoting_pass")
            session.termination_reason = TerminationReason.ASSERTION_FAILED
        elif not all_passed and session.termination_reason not in (
            TerminationReason.CRASH,
            TerminationReason.UNSAFE,
            TerminationReason.USER,
        ):
            session.termination_reason = TerminationReason.ASSERTION_FAILED


def _ensure_implicit_assertions(
    session: SessionContext,
    explicit: list[Assertion] | None = None,
) -> None:
    """Add implicit assertions and merge user-supplied ones.

    Always prepends a ``no_error_dialog`` assertion (unless the caller
    already supplied one).
    """
    if explicit:
        session.assertions = list(explicit)

    has_no_error = any(a.type == "no_error_dialog" for a in session.assertions)
    if not has_no_error:
        session.assertions.insert(0, Assertion(type="no_error_dialog"))
