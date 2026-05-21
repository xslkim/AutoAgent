"""TASK-0130: Tests for cost_tracker.py.

All tests redirect path constants to tmp_path so they never touch
the real ~/.autoagent/ or state/budget.json.

Coverage:
- calculate_cost: accuracy per model, default pricing for unknowns
- record_usage: CSV creation, row values, budget update, stop trigger
- get_daily_total / get_session_total: aggregation over multiple rows
- update_budget: daily rollover, session init, limit detection
- read_budget / write_budget: round-trip JSON, missing file default
- Session limit trigger: stop_fn called when session cost ≥ $50
- Daily limit trigger: stop_fn called when daily cost ≥ $200
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import autoagent_mcp.cost_tracker as ct
from autoagent_mcp.cost_tracker import (
    CostEntry,
    calculate_cost,
    get_daily_total,
    get_session_total,
    read_budget,
    record_usage,
    update_budget,
    write_budget,
)


# ---------------------------------------------------------------------------
# Fixtures: redirect path constants to tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Redirect CSV and budget.json paths to tmp_path sandbox."""
    aa_dir = tmp_path / ".autoagent"
    aa_dir.mkdir()
    csv_path = aa_dir / "cost-daily.csv"
    budget_path = tmp_path / "state" / "budget.json"
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(ct, "AUTOAGENT_DIR", aa_dir)
    monkeypatch.setattr(ct, "DEFAULT_CSV", csv_path)
    monkeypatch.setattr(ct, "BUDGET_JSON", budget_path)
    return {"csv": csv_path, "budget": budget_path, "aa_dir": aa_dir}


def _no_stop(reason: str) -> None:
    """Replacement stop function that does nothing (avoids writing real STOP)."""


# ---------------------------------------------------------------------------
# calculate_cost
# ---------------------------------------------------------------------------


class TestCalculateCost:
    def test_claude_opus_pricing(self):
        # $15/M input + $75/M output
        # 1000 input + 500 output = 15*1000/1M + 75*500/1M = 0.015 + 0.0375 = 0.0525
        cost = calculate_cost("claude-opus-4-5", 1000, 500)
        assert abs(cost - 0.0525) < 1e-9

    def test_claude_sonnet_pricing(self):
        # $3/M + $15/M
        cost = calculate_cost("claude-3-5-sonnet-20241022", 1_000_000, 0)
        assert abs(cost - 3.0) < 1e-9

    def test_claude_haiku_pricing(self):
        # $0.80/M + $4/M
        cost = calculate_cost("claude-3-5-haiku-20241022", 0, 1_000_000)
        assert abs(cost - 4.0) < 1e-9

    def test_claude_3_haiku_cheaper(self):
        # $0.25/M + $1.25/M
        cost = calculate_cost("claude-3-haiku-20240307", 1_000_000, 1_000_000)
        assert abs(cost - 1.5) < 1e-9

    def test_zero_tokens(self):
        assert calculate_cost("claude-opus-4-5", 0, 0) == 0.0

    def test_unknown_model_uses_default_pricing(self):
        # Default = Opus pricing ($15/M + $75/M)
        cost_unknown = calculate_cost("unknown-model-xyz", 1_000_000, 0)
        cost_opus = calculate_cost("claude-opus-4-5", 1_000_000, 0)
        assert abs(cost_unknown - cost_opus) < 1e-9

    def test_all_known_models_have_pricing(self):
        for model in ct.MODEL_PRICING:
            if model == "default":
                continue
            cost = calculate_cost(model, 1000, 1000)
            assert cost > 0, f"Model {model!r} returned zero cost"

    def test_returns_float(self):
        assert isinstance(calculate_cost("claude-opus-4-5", 100, 100), float)

    def test_large_token_counts(self):
        cost = calculate_cost("claude-opus-4-5", 10_000_000, 5_000_000)
        # 10M * $15 + 5M * $75 = $150 + $375 = $525
        assert abs(cost - 525.0) < 1e-6


# ---------------------------------------------------------------------------
# record_usage — CSV
# ---------------------------------------------------------------------------


class TestRecordUsageCsv:
    def test_creates_csv_on_first_call(self, sandbox):
        record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        assert sandbox["csv"].is_file()

    def test_csv_has_header(self, sandbox):
        record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        with open(sandbox["csv"], newline="") as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames or []) == set(ct.CSV_FIELDNAMES)

    def test_csv_row_values(self, sandbox):
        record_usage(
            "claude-opus-4-5", 1000, 500,
            session_id="ses-1", task_id="TASK-0001",
            _stop_fn=_no_stop,
        )
        with open(sandbox["csv"], newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        r = rows[0]
        assert r["model"] == "claude-opus-4-5"
        assert r["session_id"] == "ses-1"
        assert r["task_id"] == "TASK-0001"
        assert int(r["input_tokens"]) == 1000
        assert int(r["output_tokens"]) == 500
        assert abs(float(r["cost_usd"]) - 0.0525) < 1e-6

    def test_multiple_calls_append_rows(self, sandbox):
        for i in range(5):
            record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        with open(sandbox["csv"], newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5

    def test_returns_cost_entry(self, sandbox):
        entry = record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        assert isinstance(entry, CostEntry)
        assert entry.model == "claude-opus-4-5"
        assert entry.input_tokens == 100
        assert entry.output_tokens == 50

    def test_cost_calculated_correctly_in_entry(self, sandbox):
        entry = record_usage("claude-opus-4-5", 1000, 500, _stop_fn=_no_stop)
        assert abs(entry.cost_usd - 0.0525) < 1e-9

    def test_date_and_timestamp_set(self, sandbox):
        entry = record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        assert len(entry.date) == 10  # YYYY-MM-DD
        assert "T" in entry.timestamp

    def test_empty_session_task_id(self, sandbox):
        entry = record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop)
        assert entry.session_id == ""
        assert entry.task_id == ""


# ---------------------------------------------------------------------------
# get_daily_total
# ---------------------------------------------------------------------------


class TestGetDailyTotal:
    def test_zero_when_no_csv(self, sandbox):
        total = get_daily_total(csv_path=sandbox["csv"])
        assert total == 0.0

    def test_sums_today(self, sandbox):
        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        for _ in range(3):
            record_usage("claude-opus-4-5", 1000, 500, _stop_fn=_no_stop,
                         csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        total = get_daily_total(date=today, csv_path=sandbox["csv"])
        assert abs(total - 0.0525 * 3) < 1e-6

    def test_does_not_include_other_dates(self, sandbox):
        """Manually insert a row with a different date."""
        ct._ensure_csv(sandbox["csv"])
        with open(sandbox["csv"], "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ct.CSV_FIELDNAMES)
            w.writerow({
                "timestamp": "2020-01-01T00:00:00+00:00",
                "date": "2020-01-01",
                "session_id": "", "task_id": "",
                "model": "claude-opus-4-5",
                "input_tokens": 1000, "output_tokens": 500,
                "cost_usd": 0.0525,
            })
        total = get_daily_total(date="2026-05-21", csv_path=sandbox["csv"])
        assert total == 0.0

    def test_specific_date_argument(self, sandbox):
        ct._ensure_csv(sandbox["csv"])
        with open(sandbox["csv"], "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ct.CSV_FIELDNAMES)
            w.writerow({
                "timestamp": "2026-01-15T12:00:00+00:00",
                "date": "2026-01-15",
                "session_id": "", "task_id": "",
                "model": "claude-opus-4-5",
                "input_tokens": 1000000, "output_tokens": 0,
                "cost_usd": 15.0,
            })
        assert abs(get_daily_total("2026-01-15", sandbox["csv"]) - 15.0) < 1e-6
        assert get_daily_total("2026-01-16", sandbox["csv"]) == 0.0


# ---------------------------------------------------------------------------
# get_session_total
# ---------------------------------------------------------------------------


class TestGetSessionTotal:
    def test_zero_when_no_csv(self, sandbox):
        assert get_session_total("ses-1", sandbox["csv"]) == 0.0

    def test_sums_session(self, sandbox):
        for _ in range(4):
            record_usage("claude-opus-4-5", 1000, 500,
                         session_id="ses-A", _stop_fn=_no_stop,
                         csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        total = get_session_total("ses-A", sandbox["csv"])
        assert abs(total - 0.0525 * 4) < 1e-6

    def test_isolates_sessions(self, sandbox):
        record_usage("claude-opus-4-5", 1000, 500,
                     session_id="ses-A", _stop_fn=_no_stop,
                     csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        record_usage("claude-opus-4-5", 1000, 500,
                     session_id="ses-B", _stop_fn=_no_stop,
                     csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        assert abs(get_session_total("ses-A", sandbox["csv"]) - 0.0525) < 1e-6
        assert abs(get_session_total("ses-B", sandbox["csv"]) - 0.0525) < 1e-6

    def test_empty_session_id_grouped(self, sandbox):
        record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop,
                     csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop,
                     csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        total = get_session_total("", sandbox["csv"])
        assert total > 0


# ---------------------------------------------------------------------------
# read_budget / write_budget
# ---------------------------------------------------------------------------


class TestBudgetIO:
    def test_read_missing_file_returns_defaults(self, sandbox):
        doc = read_budget(sandbox["budget"])
        assert doc["schema_version"] == 1
        assert "today" in doc
        assert "session" in doc
        assert "limits" in doc

    def test_write_then_read_round_trip(self, sandbox):
        doc = read_budget(sandbox["budget"])
        doc["today"]["usd"] = 42.5
        write_budget(doc, sandbox["budget"])
        loaded = read_budget(sandbox["budget"])
        assert loaded["today"]["usd"] == 42.5

    def test_malformed_budget_returns_defaults(self, sandbox):
        sandbox["budget"].write_text("not json", encoding="utf-8")
        doc = read_budget(sandbox["budget"])
        assert doc["today"]["usd"] == 0.0

    def test_write_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep_path = tmp_path / "a" / "b" / "c" / "budget.json"
        doc = {"schema_version": 1, "today": {"usd": 0}}
        write_budget(doc, deep_path)
        assert deep_path.is_file()


# ---------------------------------------------------------------------------
# update_budget
# ---------------------------------------------------------------------------


class TestUpdateBudget:
    def _make_entry(self, cost: float, session_id: str = "ses") -> CostEntry:
        import datetime as dt
        now = dt.datetime.now(tz=dt.timezone.utc)
        return CostEntry(
            timestamp=now.isoformat(),
            date=now.strftime("%Y-%m-%d"),
            session_id=session_id,
            task_id="",
            model="claude-opus-4-5",
            input_tokens=0,
            output_tokens=0,
            cost_usd=cost,
        )

    def test_accumulates_session_usd(self, sandbox):
        update_budget(self._make_entry(5.0), sandbox["budget"])
        update_budget(self._make_entry(3.0), sandbox["budget"])
        doc = read_budget(sandbox["budget"])
        assert abs(doc["session"]["usd"] - 8.0) < 1e-9

    def test_accumulates_daily_usd(self, sandbox):
        update_budget(self._make_entry(10.0), sandbox["budget"])
        update_budget(self._make_entry(7.5), sandbox["budget"])
        doc = read_budget(sandbox["budget"])
        assert abs(doc["today"]["usd"] - 17.5) < 1e-9

    def test_daily_rollover(self, sandbox):
        # Seed a budget with yesterday's date
        doc = read_budget(sandbox["budget"])
        doc["today"]["date"] = "2000-01-01"
        doc["today"]["usd"] = 99.0
        doc["today"]["task_count"] = 10
        write_budget(doc, sandbox["budget"])

        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        entry = self._make_entry(1.0)
        updated, _ = update_budget(entry, sandbox["budget"])
        assert updated["today"]["date"] == today
        # Reset to just the current entry's cost
        assert abs(updated["today"]["usd"] - 1.0) < 1e-9
        assert updated["today"]["task_count"] == 0

    def test_session_started_at_initialized(self, sandbox):
        entry = self._make_entry(1.0)
        updated, _ = update_budget(entry, sandbox["budget"])
        assert updated["session"]["started_at"] is not None

    def test_no_limit_triggered_under_threshold(self, sandbox):
        _, triggered = update_budget(self._make_entry(1.0), sandbox["budget"])
        assert triggered == []

    def test_session_limit_triggered(self, sandbox):
        # Set session usd to just below limit
        doc = read_budget(sandbox["budget"])
        doc["session"]["usd"] = 49.9
        write_budget(doc, sandbox["budget"])
        _, triggered = update_budget(self._make_entry(0.2), sandbox["budget"])
        assert any("session" in t for t in triggered)

    def test_daily_limit_triggered(self, sandbox):
        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        doc = read_budget(sandbox["budget"])
        doc["today"]["date"] = today
        doc["today"]["usd"] = 199.9
        write_budget(doc, sandbox["budget"])
        _, triggered = update_budget(self._make_entry(0.2), sandbox["budget"])
        assert any("daily" in t for t in triggered)

    def test_both_limits_triggered(self, sandbox):
        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        doc = read_budget(sandbox["budget"])
        doc["today"]["date"] = today
        doc["today"]["usd"] = 199.9
        doc["session"]["usd"] = 49.9
        write_budget(doc, sandbox["budget"])
        _, triggered = update_budget(self._make_entry(0.2), sandbox["budget"])
        assert len(triggered) == 2

    def test_returns_updated_doc(self, sandbox):
        entry = self._make_entry(5.0)
        doc, _ = update_budget(entry, sandbox["budget"])
        assert isinstance(doc, dict)
        assert "today" in doc


# ---------------------------------------------------------------------------
# record_usage — stop trigger (session limit)
# ---------------------------------------------------------------------------


class TestSessionLimitTrigger:
    """Verification: session cost limit ≥ $50 → stop_fn called."""

    def test_stop_fn_not_called_below_limit(self, sandbox):
        stop_mock = MagicMock()
        record_usage(
            "claude-opus-4-5", 100, 50,
            session_id="ses-X",
            _stop_fn=stop_mock,
            csv_path=sandbox["csv"],
            budget_path=sandbox["budget"],
        )
        stop_mock.assert_not_called()

    def test_stop_fn_called_when_session_limit_reached(self, sandbox):
        """Accumulate session cost to exactly breach the $50 limit."""
        stop_mock = MagicMock()
        # Pre-fill session budget close to limit
        doc = read_budget(sandbox["budget"])
        doc["session"]["usd"] = 49.9
        write_budget(doc, sandbox["budget"])

        record_usage(
            "claude-opus-4-5", 1_000_000, 0,   # $15 input → session total ≥ $50
            session_id="ses-Y",
            _stop_fn=stop_mock,
            csv_path=sandbox["csv"],
            budget_path=sandbox["budget"],
        )
        stop_mock.assert_called_once()
        reason = stop_mock.call_args[0][0]
        assert "session" in reason.lower()

    def test_stop_fn_called_multiple_times_if_multiple_limits(self, sandbox):
        """When both session and daily limits are breached, stop_fn fires twice."""
        stop_mock = MagicMock()
        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        doc = read_budget(sandbox["budget"])
        doc["today"]["date"] = today
        doc["today"]["usd"] = 199.9
        doc["session"]["usd"] = 49.9
        write_budget(doc, sandbox["budget"])

        record_usage(
            "claude-opus-4-5", 1_000_000, 0,
            _stop_fn=stop_mock,
            csv_path=sandbox["csv"],
            budget_path=sandbox["budget"],
        )
        assert stop_mock.call_count == 2

    def test_stop_reason_mentions_dollar_amount(self, sandbox):
        doc = read_budget(sandbox["budget"])
        doc["session"]["usd"] = 49.9
        write_budget(doc, sandbox["budget"])
        stop_mock = MagicMock()
        record_usage(
            "claude-opus-4-5", 1_000_000, 0,
            _stop_fn=stop_mock,
            csv_path=sandbox["csv"],
            budget_path=sandbox["budget"],
        )
        reason = stop_mock.call_args[0][0]
        assert "$" in reason


# ---------------------------------------------------------------------------
# record_usage — daily limit trigger
# ---------------------------------------------------------------------------


class TestDailyLimitTrigger:
    def test_stop_fn_called_when_daily_limit_reached(self, sandbox):
        import datetime as dt
        today = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")
        doc = read_budget(sandbox["budget"])
        doc["today"]["date"] = today
        doc["today"]["usd"] = 199.0
        write_budget(doc, sandbox["budget"])

        stop_mock = MagicMock()
        record_usage(
            "claude-opus-4-5", 10_000_000, 0,   # $150 → daily total ≥ $200
            _stop_fn=stop_mock,
            csv_path=sandbox["csv"],
            budget_path=sandbox["budget"],
        )
        stop_mock.assert_called()
        reason = stop_mock.call_args[0][0]
        assert "daily" in reason.lower()


# ---------------------------------------------------------------------------
# CSV integrity
# ---------------------------------------------------------------------------


class TestCsvIntegrity:
    def test_csv_idempotent_header(self, sandbox):
        """Calling record_usage twice should only have one header row."""
        for _ in range(3):
            record_usage("claude-opus-4-5", 100, 50, _stop_fn=_no_stop,
                         csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        with open(sandbox["csv"], newline="") as f:
            lines = f.readlines()
        header_lines = [l for l in lines if "timestamp" in l]
        assert len(header_lines) == 1

    def test_csv_cost_usd_precision(self, sandbox):
        record_usage("claude-opus-4-5", 1, 1, _stop_fn=_no_stop,
                     csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        with open(sandbox["csv"], newline="") as f:
            rows = list(csv.DictReader(f))
        assert "." in rows[0]["cost_usd"]

    def test_csv_readable_after_many_records(self, sandbox):
        for i in range(50):
            record_usage("claude-haiku-4-5", i * 10, i * 5, _stop_fn=_no_stop,
                         csv_path=sandbox["csv"], budget_path=sandbox["budget"])
        with open(sandbox["csv"], newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 50
