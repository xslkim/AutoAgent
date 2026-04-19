"""HTTP API server — FastAPI-based REST interface.

Routes follow the product document §10.2 specification:
- POST   /v1/sessions                — create and start a test session
- GET    /v1/sessions/{id}/status     — get session status
- GET    /v1/sessions/{id}/report     — get session report
- POST   /v1/sessions/{id}/stop       — stop a running session
- GET    /v1/recordings              — list all recordings
- DELETE /v1/recordings/{fingerprint} — delete a recording
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Request / Response models ───────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """Request body for creating a session."""

    goal: str
    app_path: str
    app_args: list[str] = Field(default_factory=list)
    timeout_ms: int | None = None


class CreateSessionResponse(BaseModel):
    """Response for session creation."""

    session_id: str


class SessionStatusResponse(BaseModel):
    """Response for session status."""

    session_id: str
    status: str
    goal: str
    mode: str
    termination_reason: str | None = None
    created_at: str
    updated_at: str


class StopSessionResponse(BaseModel):
    """Response for stop session."""

    stopped: bool


class RecordingInfo(BaseModel):
    """Recording info for listing."""

    fingerprint: str
    goal: str
    app_path: str
    steps: int


class DeleteRecordingResponse(BaseModel):
    """Response for deleting a recording."""

    deleted: bool


# ── App factory ─────────────────────────────────────────────────────────

# Module-level scheduler reference (set by create_app)
_scheduler: Any = None


def create_app(config_path: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config_path: Path to config YAML file.

    Returns:
        Configured FastAPI app.
    """
    global _scheduler

    app = FastAPI(
        title="AutoVisionTest API",
        version="0.1.0",
        description="AI-vision-driven desktop application automated testing framework",
    )

    # Try to initialise scheduler
    _scheduler = _init_scheduler(config_path)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/sessions", response_model=CreateSessionResponse)
    async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        session_id = _scheduler.start_session(
            goal=req.goal,
            app_path=req.app_path,
            app_args=req.app_args or None,
            timeout_ms=req.timeout_ms,
        )
        return CreateSessionResponse(session_id=session_id)

    @app.get("/v1/sessions/{session_id}/status", response_model=SessionStatusResponse)
    async def get_session_status(session_id: str) -> SessionStatusResponse:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        from autovisiontest.scheduler.session_store import SessionStore

        data_dir = Path(_scheduler._data_dir)
        store = SessionStore(data_dir=data_dir)
        record = store.load(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionStatusResponse(
            session_id=record.session_id,
            status=record.status.value,
            goal=record.goal,
            mode=record.mode,
            termination_reason=record.termination_reason,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @app.get("/v1/sessions/{session_id}/report")
    async def get_session_report(session_id: str) -> dict[str, Any]:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        report = _scheduler.get_report(session_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @app.post("/v1/sessions/{session_id}/stop", response_model=StopSessionResponse)
    async def stop_session(session_id: str) -> StopSessionResponse:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        stopped = _scheduler.stop(session_id)
        if not stopped:
            raise HTTPException(
                status_code=404, detail="Session not found or not running"
            )
        return StopSessionResponse(stopped=True)

    @app.get("/v1/recordings", response_model=list[RecordingInfo])
    async def list_recordings() -> list[RecordingInfo]:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        cases = _scheduler._store.list_all()
        return [
            RecordingInfo(
                fingerprint=c.metadata.fingerprint,
                goal=c.goal,
                app_path=c.app_config.app_path,
                steps=len(c.steps),
            )
            for c in cases
        ]

    @app.delete(
        "/v1/recordings/{fingerprint}", response_model=DeleteRecordingResponse
    )
    async def delete_recording(fingerprint: str) -> DeleteRecordingResponse:
        if _scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")

        deleted = _scheduler.invalidate_recording(fingerprint)
        if not deleted:
            raise HTTPException(status_code=404, detail="Recording not found")
        return DeleteRecordingResponse(deleted=True)

    return app


def _init_scheduler(config_path: str | None):
    """Initialise the SessionScheduler from config."""
    try:
        from autovisiontest.interfaces.cli_commands import _create_scheduler

        return _create_scheduler(config_path)
    except Exception:
        logger.exception("scheduler_init_failed")
        return None
