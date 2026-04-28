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
import time
from pathlib import Path
from typing import Optional

from autovisiontest.backends.uitars import UITarsBackend
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.control.process import AppHandle, close_app, kill_processes_by_exe, launch_app
from autovisiontest.engine.agent import UITarsAgent
from autovisiontest.engine.models import SessionContext, TerminationReason
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
    ) -> None:
        try:
            self._disk.write_step(
                idx=step_idx,
                before=before_screenshot,
                after=after_screenshot or before_screenshot,
                ocr={"text": ocr_text} if ocr_text else None,
            )
        except Exception:  # pragma: no cover — evidence must never break a run
            logger.exception("evidence_write_failed", extra={"step_idx": step_idx})


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
    ) -> None:
        self._agent_backend = agent_backend
        self._max_steps = max_steps
        self._data_dir = Path(data_dir) if data_dir is not None else None

    def run(
        self,
        goal: str,
        app_path: str | None,
        app_args: list[str] | None = None,
        launch: bool = True,
        session_id: str | None = None,
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

        handle: AppHandle | None = None
        try:
            if launch:
                if not app_path:
                    raise ValueError("app_path is required when launch=True")
                exe_name = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
                kill_processes_by_exe(exe_name)
                handle = launch_app(app_path, app_args)
                logger.info("app_launched", extra={"app_path": app_path, "pid": handle.pid})
            else:
                logger.info("attach_mode", extra={"goal": goal})

            perception = Perception()
            agent = UITarsAgent(backend=self._agent_backend)
            terminator = Terminator(app_handle=handle, max_steps=self._max_steps)
            second_check = SecondCheck(chat_backend=_StubChatBackend())
            safety_guard = SafetyGuard(second_check=second_check)
            executor = ActionExecutor()

            evidence_writer: Optional[_StepLoopEvidenceAdapter] = None
            if self._data_dir is not None:
                disk_writer = DiskEvidenceWriter(
                    session_id=session.session_id,
                    data_dir=self._data_dir,
                )
                evidence_writer = _StepLoopEvidenceAdapter(disk_writer)

            loop = StepLoop(
                agent=agent,
                terminator=terminator,
                safety_guard=safety_guard,
                executor=executor,
                perception=perception,
                evidence_writer=evidence_writer,
            )

            reason = loop.run(session)
            logger.info("session_ended", extra={"reason": reason.value})

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
                        kill_processes_by_exe(handle.exe_name)
                    except Exception:
                        pass

        return session
