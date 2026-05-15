"""budget.json atomic read / write + limit checks.

Schema documented at docs/09-orchestration.md §三 (budget.json schema).
All writes are atomic via temp file + os.replace on the same filesystem.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1


def default_budget() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "today": {
            "date": None,
            "usd": 0.0,
            "task_count": 0,
            "ci_run_count": 0,
            "pr_count": 0,
        },
        "session": {
            "started_at": None,
            "usd": 0.0,
            "task_count": 0,
            "ci_run_count": 0,
        },
        "limits": {
            "single_task_usd": 5.0,
            "session_usd": 50.0,
            "session_task_count": 20,
            "session_ci_run_count": 50,
            "session_duration_hours": 12,
            "daily_usd": 200.0,
            "daily_pr_count": 50,
            "consecutive_path_violations": 3,
        },
        "consecutive_path_violations": 0,
        "updated_at": None,
    }


def load_budget(path: Path) -> dict:
    if not path.is_file():
        return default_budget()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"budget.json schema_version={data.get('schema_version')!r}, "
            f"expected {SCHEMA_VERSION}"
        )
    return data


def save_budget(path: Path, data: dict) -> None:
    data = dict(data)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def maybe_rollover_today(budget: dict, now: date | None = None) -> dict:
    """Reset the `today` block if a date boundary has crossed. Returns a new dict."""
    now = now or datetime.now(timezone.utc).date()
    today_date = budget.get("today", {}).get("date")
    if today_date == now.isoformat():
        return budget
    out = dict(budget)
    out["today"] = {
        "date": now.isoformat(),
        "usd": 0.0,
        "task_count": 0,
        "ci_run_count": 0,
        "pr_count": 0,
    }
    return out


def check_limits(budget: dict) -> list[str]:
    """Return a list of limit names that are currently breached.

    Limit semantics from docs/09-orchestration.md §三:
      - session_usd / session_task_count / session_ci_run_count → session stop
      - daily_usd / daily_pr_count → global stop (write stop_signal)
      - consecutive_path_violations → global stop
    """
    limits = budget.get("limits") or {}
    today = budget.get("today") or {}
    session = budget.get("session") or {}

    breaches: list[str] = []
    if session.get("usd", 0) >= limits.get("session_usd", float("inf")):
        breaches.append("session_usd")
    if session.get("task_count", 0) >= limits.get("session_task_count", float("inf")):
        breaches.append("session_task_count")
    if session.get("ci_run_count", 0) >= limits.get("session_ci_run_count", float("inf")):
        breaches.append("session_ci_run_count")
    if today.get("usd", 0) >= limits.get("daily_usd", float("inf")):
        breaches.append("daily_usd")
    if today.get("pr_count", 0) >= limits.get("daily_pr_count", float("inf")):
        breaches.append("daily_pr_count")
    if budget.get("consecutive_path_violations", 0) >= limits.get(
        "consecutive_path_violations", float("inf")
    ):
        breaches.append("consecutive_path_violations")
    return breaches


def add_cost(
    budget: dict,
    usd: float,
    *,
    today: bool = True,
    session: bool = True,
) -> dict:
    out = dict(budget)
    out["today"] = dict(budget["today"])
    out["session"] = dict(budget["session"])
    if today:
        out["today"]["usd"] = round(out["today"]["usd"] + usd, 6)
    if session:
        out["session"]["usd"] = round(out["session"]["usd"] + usd, 6)
    return out


def bump_counter(budget: dict, field: str, *, where: str, by: int = 1) -> dict:
    """Bump session.<field> or today.<field> by `by` (default +1)."""
    if where not in ("today", "session"):
        raise ValueError(f"where must be 'today' or 'session', got {where!r}")
    out = dict(budget)
    out[where] = dict(budget[where])
    out[where][field] = out[where].get(field, 0) + by
    return out
