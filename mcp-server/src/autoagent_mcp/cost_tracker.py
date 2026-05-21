"""Anthropic API cost tracker — 防护 budget (docs/07 §2.2 / §7.1).

Records every API usage event, accumulates session and daily totals, and
triggers the STOP sentinel when limits are exceeded.

Two persistence targets:

1. ``~/.autoagent/cost-daily.csv`` — append-only event log; one row per
   API call.  Used for EOD reports and audit.

2. ``state/budget.json`` (repo-root) — mutable counters used by the
   orchestrator and status commands.  Keys: ``today``, ``session``,
   ``limits``, ``consecutive_path_violations``.

Path constants are module-level so tests can monkeypatch them.

Usage::

    from autoagent_mcp.cost_tracker import record_usage

    entry = record_usage(
        model="claude-opus-4-5",
        input_tokens=1000,
        output_tokens=500,
        session_id="session-abc",
        task_id="TASK-0042",
    )
    print(f"This call cost ${entry.cost_usd:.4f}")
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Path constants — monkeypatched in tests
# ---------------------------------------------------------------------------

AUTOAGENT_DIR: Path = Path.home() / ".autoagent"
DEFAULT_CSV: Path = AUTOAGENT_DIR / "cost-daily.csv"

# Repo root is four levels above this file:
# mcp-server/src/autoagent_mcp/cost_tracker.py  →  repo-root/state/budget.json
_MODULE_DIR = Path(__file__).resolve().parent
BUDGET_JSON: Path = _MODULE_DIR.parent.parent.parent.parent / "state" / "budget.json"

# ---------------------------------------------------------------------------
# Limits (docs/07 §2.2 / §2.3)
# ---------------------------------------------------------------------------

SESSION_COST_LIMIT_USD: float = 50.0
DAILY_COST_LIMIT_USD: float = 200.0

# ---------------------------------------------------------------------------
# Model pricing  (per 1 M tokens, USD)
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude 4 family
    "claude-opus-4-5":               {"input": 15.00, "output": 75.00},
    "claude-opus-4":                 {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5":             {"input":  3.00, "output": 15.00},
    "claude-sonnet-4":               {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":              {"input":  0.80, "output":  4.00},
    # Claude 3.x family
    "claude-3-5-sonnet-20241022":    {"input":  3.00, "output": 15.00},
    "claude-3-5-haiku-20241022":     {"input":  0.80, "output":  4.00},
    "claude-3-haiku-20240307":       {"input":  0.25, "output":  1.25},
    "claude-3-opus-20240229":        {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229":      {"input":  3.00, "output": 15.00},
    # Default: use Opus pricing (most conservative / expensive)
    "default":                       {"input": 15.00, "output": 75.00},
}

CSV_FIELDNAMES = [
    "timestamp",
    "date",
    "session_id",
    "task_id",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
]


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class CostEntry:
    """One API usage event."""

    timestamp: str   # ISO-8601 UTC, e.g. "2026-05-21T09:15:23.123456+00:00"
    date: str        # YYYY-MM-DD
    session_id: str
    task_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


# ---------------------------------------------------------------------------
# Pure calculation
# ---------------------------------------------------------------------------


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost for a single API call.

    Args:
        model:         Anthropic model identifier (e.g. ``"claude-opus-4-5"``).
        input_tokens:  Number of input (prompt) tokens.
        output_tokens: Number of output (completion) tokens.

    Returns:
        Cost in USD, rounded to 6 decimal places.
    """
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING["default"]
    cost = (
        input_tokens  * pricing["input"]
        + output_tokens * pricing["output"]
    ) / 1_000_000
    return round(cost, 6)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _ensure_csv(csv_path: Path) -> None:
    """Create the CSV with headers if it does not exist."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.is_file():
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()


def _append_csv(csv_path: Path, entry: CostEntry) -> None:
    """Append one row to the CSV (create + write header if needed)."""
    _ensure_csv(csv_path)
    row = asdict(entry)
    # Always write cost_usd as fixed-point decimal to avoid scientific notation
    # (e.g. 9e-05 → "0.000090") so CSV is human-readable and round-trip safe.
    row["cost_usd"] = f"{entry.cost_usd:.8f}"
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writerow(row)


def _read_csv(csv_path: Path) -> list[dict[str, str]]:
    """Return all rows from the CSV as dicts (empty list if file absent)."""
    if not csv_path.is_file():
        return []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def get_daily_total(date: str | None = None, csv_path: Path | None = None) -> float:
    """Sum ``cost_usd`` for the given date (default: today UTC).

    Args:
        date:     ``YYYY-MM-DD`` string.  Defaults to today's UTC date.
        csv_path: Path to the cost CSV.  Defaults to :data:`DEFAULT_CSV`.

    Returns:
        Total cost in USD for that date.
    """
    if date is None:
        date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows = _read_csv(csv_path or DEFAULT_CSV)
    return round(sum(float(r["cost_usd"]) for r in rows if r.get("date") == date), 6)


def get_session_total(session_id: str, csv_path: Path | None = None) -> float:
    """Sum ``cost_usd`` for the given session.

    Args:
        session_id: Session identifier string.
        csv_path:   Path to the cost CSV.  Defaults to :data:`DEFAULT_CSV`.

    Returns:
        Total cost in USD for that session.
    """
    rows = _read_csv(csv_path or DEFAULT_CSV)
    return round(
        sum(float(r["cost_usd"]) for r in rows if r.get("session_id") == session_id),
        6,
    )


# ---------------------------------------------------------------------------
# budget.json helpers
# ---------------------------------------------------------------------------


def read_budget(budget_path: Path | None = None) -> dict[str, Any]:
    """Read and return the budget JSON dict.

    Returns a fresh default dict if the file is absent or unreadable.
    """
    path = budget_path or BUDGET_JSON
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    # Return the canonical default structure
    return {
        "schema_version": 1,
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
            "session_usd": SESSION_COST_LIMIT_USD,
            "session_task_count": 20,
            "session_ci_run_count": 50,
            "session_duration_hours": 12,
            "daily_usd": DAILY_COST_LIMIT_USD,
            "daily_pr_count": 50,
            "consecutive_path_violations": 3,
        },
        "consecutive_path_violations": 0,
        "updated_at": None,
    }


def write_budget(doc: dict[str, Any], budget_path: Path | None = None) -> None:
    """Write the budget dict back to JSON (pretty-printed)."""
    path = budget_path or BUDGET_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def update_budget(
    entry: CostEntry,
    budget_path: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Add *entry*'s cost to the budget accumulators and persist.

    Handles daily rollover (resets ``today`` when the date changes).
    Initialises ``session.started_at`` on first call.

    Args:
        entry:       The :class:`CostEntry` just recorded.
        budget_path: Override :data:`BUDGET_JSON` (for tests).

    Returns:
        ``(updated_budget_dict, triggered_limits)`` where
        ``triggered_limits`` is a list of human-readable strings for
        each limit that was **newly exceeded** by this call.
    """
    doc = read_budget(budget_path)
    today_section = doc.setdefault("today", {})
    session_section = doc.setdefault("session", {})
    limits = doc.get("limits", {})

    # Daily rollover
    if today_section.get("date") != entry.date:
        today_section["date"] = entry.date
        today_section["usd"] = 0.0
        today_section["task_count"] = 0
        today_section["ci_run_count"] = 0
        today_section["pr_count"] = 0

    # Session initialisation
    if not session_section.get("started_at"):
        session_section["started_at"] = entry.timestamp

    # Accumulate
    today_section["usd"] = round(today_section.get("usd", 0.0) + entry.cost_usd, 6)
    session_section["usd"] = round(session_section.get("usd", 0.0) + entry.cost_usd, 6)

    doc["updated_at"] = entry.timestamp

    # Check limits
    triggered: list[str] = []
    session_limit = float(limits.get("session_usd", SESSION_COST_LIMIT_USD))
    daily_limit = float(limits.get("daily_usd", DAILY_COST_LIMIT_USD))

    if session_section["usd"] >= session_limit:
        triggered.append(
            f"session cost limit ${session_limit:.2f} exceeded "
            f"(current: ${session_section['usd']:.4f})"
        )
    if today_section["usd"] >= daily_limit:
        triggered.append(
            f"daily cost limit ${daily_limit:.2f} exceeded "
            f"(current: ${today_section['usd']:.4f})"
        )

    write_budget(doc, budget_path)
    return doc, triggered


# ---------------------------------------------------------------------------
# Default stop action
# ---------------------------------------------------------------------------


def _default_stop(reason: str) -> None:
    """Write the STOP sentinel (delegates to agent_ctl)."""
    from autoagent_mcp.agent_ctl import write_stop  # lazy import
    write_stop(reason)


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------


def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    session_id: str = "",
    task_id: str = "",
    csv_path: Path | None = None,
    budget_path: Path | None = None,
    _stop_fn: Callable[[str], None] | None = None,
) -> CostEntry:
    """Record one API call, update counters, and enforce limits.

    Args:
        model:         Anthropic model identifier.
        input_tokens:  Prompt token count.
        output_tokens: Completion token count.
        session_id:    Current session identifier (empty string = unknown).
        task_id:       Current task identifier (empty string = unknown).
        csv_path:      Override :data:`DEFAULT_CSV` (for tests).
        budget_path:   Override :data:`BUDGET_JSON` (for tests).
        _stop_fn:      Override the stop action (for tests).  Receives a
                       human-readable reason string.  When ``None``,
                       defaults to writing the STOP sentinel via
                       :func:`autoagent_mcp.agent_ctl.write_stop`.

    Returns:
        The recorded :class:`CostEntry`.

    Side-effects:
        1. Appends a row to the daily CSV.
        2. Updates ``state/budget.json`` (today + session accumulators).
        3. Calls *_stop_fn* (or the default) for each exceeded limit.
    """
    now = datetime.now(tz=timezone.utc)
    cost = calculate_cost(model, input_tokens, output_tokens)

    entry = CostEntry(
        timestamp=now.isoformat(),
        date=now.strftime("%Y-%m-%d"),
        session_id=session_id,
        task_id=task_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )

    _append_csv(csv_path or DEFAULT_CSV, entry)

    _, triggered = update_budget(entry, budget_path)

    stop = _stop_fn if _stop_fn is not None else _default_stop
    for reason in triggered:
        stop(reason)

    return entry
