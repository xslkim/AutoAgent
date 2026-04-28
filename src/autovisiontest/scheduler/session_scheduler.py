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

from autovisiontest.backends.uitars import UITarsBackend
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
    """Routes test sessions through the exploratory (UI-TARS) runner.

    Regression mode is gated behind :class:`RegressionRunner`, which
    currently raises pending a port to the :class:`Agent` protocol.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        agent_backend: UITarsBackend,
        max_steps: int = 30,
    ) -> None:
        if agent_backend is None:
            raise ValueError("SessionScheduler requires an agent_backend (UI-TARS)")
        self._agent_backend = agent_backend
        self._data_dir = Path(data_dir)
        self._max_steps = max_steps

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
        app_path: str | None,
        app_args: list[str] | None = None,
        timeout_ms: int | None = None,
        launch: bool = True,
    ) -> str:
        """Start a test session.

        If a recording exists for the given app+goal, runs in regression mode.
        Otherwise, runs in exploratory mode and consolidates on success.

        Args:
            goal: Natural language goal for the test.
            app_path: Path to the application executable.  Optional when
                ``launch`` is False (attach mode).
            app_args: Optional command-line arguments for the application.
            timeout_ms: Optional timeout in milliseconds (reserved for future use).
            launch: When True (default) the runner kills and launches the app.
                When False, attach mode — the Planner drives the UI from the
                current desktop state and the runner neither starts nor stops
                any process.

        Returns:
            session_id for tracking the session.
        """
        session_id = uuid.uuid4().hex[:12]

        # Regression mode requires a recording keyed on app_path + goal.
        # In attach mode we skip this lookup (no meaningful app_path).
        if launch and app_path:
            existing_case = self._store.find_for_goal(app_path, goal)
            mode = "regression" if existing_case else "exploratory"
            fingerprint = existing_case.metadata.fingerprint if existing_case else None
        else:
            mode = "exploratory"
            fingerprint = None

        # Create session record
        record = SessionRecord(
            session_id=session_id,
            goal=goal,
            app_path=app_path or "",
            app_args=app_args or [],
            mode=mode,
            status=SessionStatus.RUNNING,
            fingerprint=fingerprint,
        )
        self._session_store.save(record)

        logger.info(
            "session_starting",
            extra={"session_id": session_id, "mode": mode, "launch": launch},
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
            launch=launch,
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

    def invalidate_recording(self, fingerprint: str) -> bool:
        """Delete a recording by fingerprint.

        This can be called externally (e.g., via API) or internally
        when a regression session detects UI drift.

        Args:
            fingerprint: The recording fingerprint to delete.

        Returns:
            True if the recording was deleted, False if not found.
        """
        result = self._store.delete(fingerprint)
        if result:
            logger.info(
                "recording_invalidated", extra={"fingerprint": fingerprint}
            )
        return result

    def shutdown(self) -> None:
        """Shut down the executor and clean up resources."""
        self._executor.shutdown(wait=True)

    # -- Internal ------------------------------------------------------------

    def _run_session(
        self,
        session_id: str,
        goal: str,
        app_path: str | None,
        app_args: list[str] | None,
        mode: str,
        fingerprint: str | None,
        launch: bool = True,
    ) -> None:
        """Execute a session in the background thread.

        If a regression session finishes with ``recording_invalid=True``,
        automatically launches a compensatory exploratory session.

        Args:
            session_id: Session identifier.
            goal: Test goal.
            app_path: Application path.
            app_args: Application arguments.
            mode: "exploratory" or "regression".
            fingerprint: Recording fingerprint (for regression).
            launch: Whether to launch/close the app (see ``start_session``).
        """
        try:
            if mode == "regression" and fingerprint:
                session = self._run_regression(fingerprint)
            else:
                session = self._run_exploratory(
                    goal, app_path, app_args, launch=launch, session_id=session_id
                )

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

            # Post-exploration consolidation — only in launch mode, since
            # recordings are keyed on app_path + goal.
            if (
                mode == "exploratory"
                and launch
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

            # Regression invalidation → fallback to exploration
            if (
                mode == "regression"
                and session.recording_invalid
                and fingerprint
            ):
                logger.info(
                    "regression_invalid_fallback",
                    extra={
                        "session_id": session_id,
                        "fingerprint": fingerprint,
                    },
                )
                self._invalidate_and_reexplore(
                    fingerprint=fingerprint,
                    goal=goal,
                    app_path=app_path,
                    app_args=app_args,
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
        app_path: str | None,
        app_args: list[str] | None,
        launch: bool = True,
        session_id: str | None = None,
    ) -> SessionContext:
        """Run an exploratory session via UI-TARS."""
        runner = ExploratoryRunner(
            agent_backend=self._agent_backend,
            max_steps=self._max_steps,
            data_dir=self._data_dir,
        )
        return runner.run(
            goal=goal,
            app_path=app_path,
            app_args=app_args,
            launch=launch,
            session_id=session_id,
        )

    def _run_regression(self, fingerprint: str) -> SessionContext:
        """Regression mode — currently raises pending Agent port."""
        runner = RegressionRunner(store=self._store, max_steps=self._max_steps)
        return runner.run(recording_path=fingerprint)

    def _save_context(self, session_id: str, session: SessionContext) -> None:
        """Save the SessionContext to disk."""
        session_dir = self._session_store._sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = session_dir / "context.json"
        ctx_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def _invalidate_and_reexplore(
        self,
        fingerprint: str,
        goal: str,
        app_path: str,
        app_args: list[str] | None,
    ) -> None:
        """Delete invalid recording and run a compensatory exploratory session.

        If the exploratory session succeeds, it will automatically be
        consolidated into a new recording (replacing the old one).

        Args:
            fingerprint: The invalid recording's fingerprint.
            goal: Test goal.
            app_path: Application path.
            app_args: Application arguments.
        """
        # Delete the invalid recording
        self.invalidate_recording(fingerprint)

        # Run exploratory session
        logger.info(
            "fallback_exploration_starting",
            extra={"goal": goal, "app_path": app_path},
        )

        try:
            session = self._run_exploratory(goal, app_path, app_args)

            if session.termination_reason == TerminationReason.PASS:
                # Consolidate the new successful exploration
                new_case = consolidate(session, self._store)
                if new_case:
                    logger.info(
                        "fallback_exploration_consolidated",
                        extra={
                            "new_fingerprint": new_case.metadata.fingerprint,
                            "old_fingerprint": fingerprint,
                        },
                    )
                else:
                    logger.warning("fallback_exploration_consolidation_skipped")
            else:
                logger.warning(
                    "fallback_exploration_failed",
                    extra={"reason": session.termination_reason.value if session.termination_reason else None},
                )
        except Exception:
            logger.exception("fallback_exploration_error")
