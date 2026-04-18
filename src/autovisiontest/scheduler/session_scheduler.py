"""Session scheduler — routes between exploratory and regression modes.

The SessionScheduler is the main entry point for starting test sessions.
It determines whether to run in exploratory mode (no existing recording)
or regression mode (recording exists for the given app+goal).

MVP uses a single background thread (``ThreadPoolExecutor(max_workers=1)``)
so sessions execute serially.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from autovisiontest.backends.protocol import ChatBackend, GroundingBackend
from autovisiontest.cases.consolidator import consolidate
from autovisiontest.cases.store import RecordingStore
from autovisiontest.engine.exploratory import ExploratoryRunner
from autovisiontest.engine.models import SessionContext, TerminationReason
from autovisiontest.engine.regression import RegressionRunner
from autovisiontest.scheduler.session_store import (
    SessionRecord,
    SessionStatus,
    SessionStore,
)

logger = logging.getLogger(__name__)


class SessionScheduler:
    """Routes test sessions between exploratory and regression modes.

    Args:
        chat_backend: Chat backend for Planner and SecondCheck.
        grounding_backend: Grounding backend for Actor.
        data_dir: Root data directory for recordings and sessions.
        max_steps: Maximum steps per session.
        confidence_threshold: Minimum grounding confidence.
    """

    def __init__(
        self,
        chat_backend: ChatBackend,
        grounding_backend: GroundingBackend,
        data_dir: Path,
        max_steps: int = 30,
        confidence_threshold: float = 0.6,
    ) -> None:
        self._chat_backend = chat_backend
        self._grounding_backend = grounding_backend
        self._data_dir = Path(data_dir)
        self._max_steps = max_steps
        self._confidence_threshold = confidence_threshold

        self._store = RecordingStore(data_dir=self._data_dir)
        self._session_store = SessionStore(data_dir=self._data_dir)
        self._executor = ThreadPoolExecutor(max_workers=1)

        # Track running futures for stop() support
        self._futures: dict[str, Future[None]] = {}
        # Track sessions that should be stopped
        self._stop_requested: set[str] = set()

    # -- Public API ----------------------------------------------------------

    def start_session(
        self,
        goal: str,
        app_path: str,
        app_args: list[str] | None = None,
        timeout_ms: int | None = None,
    ) -> str:
        """Start a test session.

        If a recording exists for the given app+goal, runs in regression mode.
        Otherwise, runs in exploratory mode and consolidates on success.

        Args:
            goal: Natural language goal for the test.
            app_path: Path to the application executable.
            app_args: Optional command-line arguments for the application.
            timeout_ms: Optional timeout in milliseconds (reserved for future use).

        Returns:
            session_id for tracking the session.
        """
        session_id = uuid.uuid4().hex[:12]

        # Check for existing recording → regression
        existing_case = self._store.find_for_goal(app_path, goal)
        mode = "regression" if existing_case else "exploratory"

        fingerprint = existing_case.metadata.fingerprint if existing_case else None

        # Create session record
        record = SessionRecord(
            session_id=session_id,
            goal=goal,
            app_path=app_path,
            app_args=app_args or [],
            mode=mode,
            status=SessionStatus.RUNNING,
            fingerprint=fingerprint,
        )
        self._session_store.save(record)

        logger.info(
            "session_starting",
            extra={"session_id": session_id, "mode": mode},
        )

        # Submit to background thread
        future = self._executor.submit(
            self._run_session,
            session_id=session_id,
            goal=goal,
            app_path=app_path,
            app_args=app_args,
            mode=mode,
            fingerprint=fingerprint,
        )
        self._futures[session_id] = future

        return session_id

    def get_status(self, session_id: str) -> SessionStatus | None:
        """Get the current status of a session.

        Args:
            session_id: The session identifier.

        Returns:
            SessionStatus, or None if the session does not exist.
        """
        record = self._session_store.load(session_id)
        if record is None:
            return None
        return record.status

    def get_report(self, session_id: str) -> dict[str, Any] | None:
        """Get the report for a completed session.

        Args:
            session_id: The session identifier.

        Returns:
            Report dict if available, None otherwise.
            Note: Full Report model will be available after H stage.
        """
        record = self._session_store.load(session_id)
        if record is None or record.report_path is None:
            return None
        try:
            report_path = Path(record.report_path)
            if report_path.exists():
                import json

                return json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("report_load_failed", extra={"session_id": session_id})
        return None

    def stop(self, session_id: str) -> bool:
        """Request a running session to stop.

        The session will be stopped at the next step boundary.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session was running and stop was requested.
        """
        record = self._session_store.load(session_id)
        if record is None:
            return False

        if record.status != SessionStatus.RUNNING:
            return False

        self._stop_requested.add(session_id)
        logger.info("session_stop_requested", extra={"session_id": session_id})
        return True

    def get_session_context(self, session_id: str) -> SessionContext | None:
        """Get the full SessionContext for a completed session.

        This is a convenience method for accessing the raw session data
        stored during execution.

        Args:
            session_id: The session identifier.

        Returns:
            SessionContext if available, None otherwise.
        """
        session_dir = self._session_store._sessions_dir / session_id
        ctx_path = session_dir / "context.json"
        if not ctx_path.exists():
            return None
        try:
            import json

            data = json.loads(ctx_path.read_text(encoding="utf-8"))
            return SessionContext.model_validate(data)
        except Exception:
            logger.exception(
                "context_load_failed", extra={"session_id": session_id}
            )
            return None

    def shutdown(self) -> None:
        """Shut down the executor and clean up resources."""
        self._executor.shutdown(wait=True)

    # -- Internal ------------------------------------------------------------

    def _run_session(
        self,
        session_id: str,
        goal: str,
        app_path: str,
        app_args: list[str] | None,
        mode: str,
        fingerprint: str | None,
    ) -> None:
        """Execute a session in the background thread.

        Args:
            session_id: Session identifier.
            goal: Test goal.
            app_path: Application path.
            app_args: Application arguments.
            mode: "exploratory" or "regression".
            fingerprint: Recording fingerprint (for regression).
        """
        try:
            if mode == "regression" and fingerprint:
                session = self._run_regression(fingerprint)
            else:
                session = self._run_exploratory(goal, app_path, app_args)

            # Check if stop was requested during execution
            if session_id in self._stop_requested:
                self._stop_requested.discard(session_id)
                session.termination_reason = TerminationReason.USER

            # Save session context
            self._save_context(session_id, session)

            # Update session record
            record = self._session_store.load(session_id)
            if record is not None:
                record.termination_reason = (
                    session.termination_reason.value
                    if session.termination_reason
                    else None
                )
                if session.termination_reason == TerminationReason.PASS:
                    record.status = SessionStatus.COMPLETED
                elif session.termination_reason == TerminationReason.USER:
                    record.status = SessionStatus.STOPPED
                else:
                    record.status = SessionStatus.FAILED
                self._session_store.save(record)

            # Post-exploration consolidation
            if (
                mode == "exploratory"
                and session.termination_reason == TerminationReason.PASS
            ):
                try:
                    consolidate(session, self._store)
                    logger.info(
                        "consolidation_done",
                        extra={"session_id": session_id},
                    )
                except Exception:
                    logger.exception(
                        "consolidation_failed",
                        extra={"session_id": session_id},
                    )

            logger.info(
                "session_completed",
                extra={
                    "session_id": session_id,
                    "status": record.status.value if record else "UNKNOWN",
                    "reason": (
                        session.termination_reason.value
                        if session.termination_reason
                        else None
                    ),
                },
            )

        except Exception:
            logger.exception(
                "session_run_failed", extra={"session_id": session_id}
            )
            # Update record to failed
            record = self._session_store.load(session_id)
            if record is not None:
                record.status = SessionStatus.FAILED
                record.termination_reason = "INTERNAL_ERROR"
                self._session_store.save(record)

    def _run_exploratory(
        self,
        goal: str,
        app_path: str,
        app_args: list[str] | None,
    ) -> SessionContext:
        """Run an exploratory session."""
        runner = ExploratoryRunner(
            chat_backend=self._chat_backend,
            grounding_backend=self._grounding_backend,
            max_steps=self._max_steps,
            confidence_threshold=self._confidence_threshold,
        )
        return runner.run(goal=goal, app_path=app_path, app_args=app_args)

    def _run_regression(self, fingerprint: str) -> SessionContext:
        """Run a regression session."""
        runner = RegressionRunner(
            chat_backend=self._chat_backend,
            grounding_backend=self._grounding_backend,
            store=self._store,
            max_steps=self._max_steps,
            confidence_threshold=self._confidence_threshold,
        )
        return runner.run(recording_path=fingerprint)

    def _save_context(self, session_id: str, session: SessionContext) -> None:
        """Save the SessionContext to disk."""
        session_dir = self._session_store._sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = session_dir / "context.json"
        ctx_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
