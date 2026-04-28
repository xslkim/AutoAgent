"""Regression runner — placeholder pending port to the :class:`Agent` protocol.

The previous implementation chained a :class:`ScriptPlanner` with the
legacy :class:`Actor` (grounding VLM) through the two-call step loop.
With the single-model UI-TARS refactor the legacy classes were removed,
so regression needs to be re-designed: recorded steps must replay with
their captured coordinates (the new step loop expects an :class:`Agent`
emitting :class:`AgentDecision` with ``coords`` already populated).

Until that work lands, calling :class:`RegressionRunner` raises a clear
error instead of silently misbehaving.  The exploratory path remains
fully functional in the meantime.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from autovisiontest.engine.models import SessionContext, TerminationReason

logger = logging.getLogger(__name__)


class RecordingStore(Protocol):
    """Protocol for loading recorded test sessions."""

    def load(self, fingerprint: str) -> dict[str, Any] | None: ...

    def find_for_goal(self, app_path: str, goal: str) -> dict[str, Any] | None: ...


class StubRecordingStore:
    """In-memory store for testing."""

    def __init__(self, recordings: dict[str, dict[str, Any]] | None = None) -> None:
        self._recordings = recordings or {}

    def load(self, fingerprint: str) -> dict[str, Any] | None:
        return self._recordings.get(fingerprint)

    def find_for_goal(self, app_path: str, goal: str) -> dict[str, Any] | None:  # noqa: ARG002
        for rec in self._recordings.values():
            if rec.get("goal") == goal:
                return rec
        return None


class RegressionRunner:
    """Placeholder regression runner.

    Instantiating the runner is allowed (so the scheduler does not need a
    special case), but :meth:`run` raises until regression is ported to
    the :class:`~autovisiontest.engine.agent.Agent` protocol.
    """

    def __init__(
        self,
        store: RecordingStore,
        max_steps: int = 30,
        **_legacy_kwargs: Any,  # tolerate stale callers during migration
    ) -> None:
        self._store = store
        self._max_steps = max_steps

    def run(self, recording_path: str) -> SessionContext:
        logger.warning(
            "regression_runner_not_ported",
            extra={"recording_path": recording_path},
        )
        raise NotImplementedError(
            "RegressionRunner has not been ported to the Agent protocol yet. "
            "The previous implementation depended on the legacy Planner+Actor "
            "pipeline, which was removed as part of the UI-TARS migration. "
            "Track this work on the migration plan (P3/P5 follow-up)."
        )
