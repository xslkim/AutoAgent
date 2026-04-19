"""CLI command implementations — bridges click commands to the scheduler.

This module contains the business logic for each CLI sub-command,
keeping ``cli.py`` focused on argument parsing and presentation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import click

from autovisiontest.scheduler.session_store import SessionStatus


# ── Exit codes ──────────────────────────────────────────────────────────

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ABORT = 2
EXIT_INTERNAL_ERROR = 3


# ── Scheduler factory ──────────────────────────────────────────────────


def _create_scheduler(config_path: str | None, data_dir: Path | None = None):
    """Create a :class:`SessionScheduler` from config.

    Builds the single UI-TARS agent backend from ``config.agent`` and
    wires it into the scheduler.  Returns ``None`` on any failure
    (with an error printed).
    """
    config = _load_config(config_path)
    if config is None:
        return None

    if config.agent is None:
        click.echo(
            "Error: config is missing an `agent:` section — the UI-TARS "
            "migration removed the legacy planner/actor pair.",
            err=True,
        )
        return None

    actual_data_dir = data_dir or Path(config.runtime.data_dir)
    actual_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        from autovisiontest.backends.factory import create_agent_backend

        agent_backend = create_agent_backend(config.agent)
    except Exception as exc:
        click.echo(f"Error creating agent backend: {exc}", err=True)
        return None

    from autovisiontest.scheduler.session_scheduler import SessionScheduler

    return SessionScheduler(
        agent_backend=agent_backend,
        data_dir=actual_data_dir,
        max_steps=config.runtime.max_steps,
    )


def _load_config(config_path: str | None):
    """Load configuration, returning None on failure."""
    try:
        from autovisiontest.config.loader import load_config

        path = Path(config_path) if config_path else None
        return load_config(path=path)
    except ImportError:
        click.echo("Error: Configuration module not available.", err=True)
        return None
    except Exception as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        return None


# ── Command implementations ────────────────────────────────────────────


def cmd_run(
    goal: str | None,
    app_path: str | None,
    app_args: str | None,
    timeout: int | None,
    case_path: str | None,
    config_path: str | None,
    launch: bool = True,
) -> int:
    """Execute the ``run`` command.

    Args:
        launch: When True the runner kills/launches/closes the app.  When
            False (attach mode) none of that happens — ``app_path`` becomes
            optional and the Planner drives the UI from the current desktop.

    Returns exit code.
    """
    scheduler = _create_scheduler(config_path)
    if scheduler is None:
        return EXIT_INTERNAL_ERROR

    if case_path is not None:
        click.echo(f"Running from case file: {case_path}")
        try:
            from autovisiontest.cases.schema import TestCase

            case = TestCase.model_validate_json(
                Path(case_path).read_text(encoding="utf-8")
            )
            goal = case.goal
            app_path = case.app_config.path
            app_args_list = case.app_config.args
        except Exception as exc:
            click.echo(f"Error loading case file: {exc}", err=True)
            return EXIT_INTERNAL_ERROR
    else:
        app_args_list = app_args.split() if app_args else None

    if not goal:
        click.echo("Error: --goal is required.", err=True)
        return EXIT_INTERNAL_ERROR
    if launch and not app_path:
        click.echo("Error: --app is required unless --no-launch is set.", err=True)
        return EXIT_INTERNAL_ERROR

    session_id = scheduler.start_session(
        goal=goal,
        app_path=app_path,
        app_args=app_args_list,
        timeout_ms=timeout,
        launch=launch,
    )
    click.echo(f"Session started: {session_id}")

    # Block until completion
    try:
        while True:
            status = scheduler.get_status(session_id)
            if status is None:
                click.echo("Error: Session not found.", err=True)
                return EXIT_INTERNAL_ERROR
            if status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        click.echo("\nStopping session...")
        scheduler.stop(session_id)
        scheduler.shutdown()
        return EXIT_ABORT

    # Final status
    final_status = scheduler.get_status(session_id)
    click.echo(f"Status: {final_status.value}")

    # Print report path
    report = scheduler.get_report(session_id)
    if report:
        click.echo(f"Report available for session {session_id}")

    scheduler.shutdown()

    if final_status == SessionStatus.COMPLETED:
        return EXIT_PASS
    elif final_status == SessionStatus.STOPPED:
        return EXIT_ABORT
    else:
        return EXIT_FAIL


def cmd_status(session_id: str, config_path: str | None) -> int:
    """Execute the ``status`` command."""
    config = _load_config(config_path)
    if config is None:
        return EXIT_INTERNAL_ERROR

    data_dir = Path(config.runtime.data_dir)

    from autovisiontest.scheduler.session_store import SessionStore

    store = SessionStore(data_dir=data_dir)
    record = store.load(session_id)

    if record is None:
        click.echo(f"Session not found: {session_id}", err=True)
        return EXIT_INTERNAL_ERROR

    click.echo(f"Session:   {record.session_id}")
    click.echo(f"Goal:      {record.goal}")
    click.echo(f"App:       {record.app_path}")
    click.echo(f"Mode:      {record.mode}")
    click.echo(f"Status:    {record.status.value}")
    click.echo(f"Created:   {record.created_at}")
    click.echo(f"Updated:   {record.updated_at}")
    if record.termination_reason:
        click.echo(f"Reason:    {record.termination_reason}")
    if record.fingerprint:
        click.echo(f"Recording: {record.fingerprint}")

    return EXIT_PASS


def cmd_report(session_id: str, fmt: str, config_path: str | None) -> int:
    """Execute the ``report`` command."""
    config = _load_config(config_path)
    if config is None:
        return EXIT_INTERNAL_ERROR

    data_dir = Path(config.runtime.data_dir)

    from autovisiontest.scheduler.session_store import SessionStore

    store = SessionStore(data_dir=data_dir)
    record = store.load(session_id)

    if record is None:
        click.echo(f"Session not found: {session_id}", err=True)
        return EXIT_INTERNAL_ERROR

    if record.report_path and Path(record.report_path).exists():
        report_text = Path(record.report_path).read_text(encoding="utf-8")
        if fmt == "json":
            click.echo(report_text)
        else:
            # Try to render as HTML
            try:
                from autovisiontest.report.schema import Report
                from autovisiontest.report.builder import ReportBuilder

                report = Report.model_validate_json(report_text)
                builder = ReportBuilder()
                click.echo(builder.to_html(report))
            except Exception:
                click.echo(report_text)
        return EXIT_PASS

    # Try to build report from session context
    ctx_path = data_dir / "sessions" / session_id / "context.json"
    if ctx_path.exists():
        try:
            from autovisiontest.engine.models import SessionContext
            from autovisiontest.report.builder import ReportBuilder

            ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
            session_ctx = SessionContext.model_validate(ctx_data)
            evidence_dir = data_dir / "evidence" / session_id

            builder = ReportBuilder()
            report = builder.build(
                session=session_ctx,
                evidence_dir=evidence_dir if evidence_dir.exists() else None,
                include_base64=(fmt == "json"),
            )

            if fmt == "json":
                click.echo(builder.to_json(report))
            else:
                click.echo(builder.to_html(report))
            return EXIT_PASS
        except Exception as exc:
            click.echo(f"Error building report: {exc}", err=True)
            return EXIT_INTERNAL_ERROR

    click.echo(f"No report data found for session: {session_id}", err=True)
    return EXIT_INTERNAL_ERROR


def cmd_list_recordings(config_path: str | None) -> int:
    """Execute the ``list-recordings`` command."""
    config = _load_config(config_path)
    if config is None:
        return EXIT_INTERNAL_ERROR

    data_dir = Path(config.runtime.data_dir)

    try:
        from autovisiontest.cases.store import RecordingStore

        store = RecordingStore(data_dir=data_dir)
        cases = store.list_all()
    except Exception as exc:
        click.echo(f"Error listing recordings: {exc}", err=True)
        return EXIT_INTERNAL_ERROR

    if not cases:
        click.echo("No recordings found.")
        return EXIT_PASS

    # Print table
    click.echo(f"{'Fingerprint':<20} {'Goal':<40} {'App':<30} {'Steps':<8}")
    click.echo("-" * 100)
    for case in cases:
        fp = case.metadata.fingerprint[:18]
        goal = case.goal[:38] + ".." if len(case.goal) > 40 else case.goal
        app = case.app_config.app_path[:28] + ".." if len(case.app_config.app_path) > 30 else case.app_config.app_path
        steps = str(len(case.steps))
        click.echo(f"{fp:<20} {goal:<40} {app:<30} {steps:<8}")

    click.echo(f"\nTotal: {len(cases)} recording(s)")
    return EXIT_PASS
