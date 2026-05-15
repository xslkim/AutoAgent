"""budget.py: schema validation, rollover, limits, atomic save."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from lib.budget import (
    SCHEMA_VERSION,
    add_cost,
    bump_counter,
    check_limits,
    default_budget,
    load_budget,
    maybe_rollover_today,
    save_budget,
)


def test_default_budget_has_schema_version():
    b = default_budget()
    assert b["schema_version"] == SCHEMA_VERSION


def test_load_missing_file_returns_default(tmp_path):
    b = load_budget(tmp_path / "nope.json")
    assert b["schema_version"] == SCHEMA_VERSION


def test_load_rejects_wrong_schema_version(tmp_path):
    p = tmp_path / "budget.json"
    p.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_budget(p)


def test_save_then_load_round_trip(tmp_path):
    p = tmp_path / "budget.json"
    b = default_budget()
    b["today"]["usd"] = 12.34
    save_budget(p, b)
    loaded = load_budget(p)
    assert loaded["today"]["usd"] == 12.34
    assert "updated_at" in loaded


def test_save_atomic_no_tmp_file_left(tmp_path):
    p = tmp_path / "budget.json"
    save_budget(p, default_budget())
    assert not (tmp_path / "budget.json.tmp").exists()


# --- rollover --------------------------------------------------------------

def test_rollover_same_day_is_noop():
    b = default_budget()
    b["today"]["date"] = "2026-05-15"
    b["today"]["usd"] = 12.34
    out = maybe_rollover_today(b, now=date(2026, 5, 15))
    assert out["today"]["usd"] == 12.34


def test_rollover_new_day_resets_today_only():
    b = default_budget()
    b["today"]["date"] = "2026-05-14"
    b["today"]["usd"] = 12.34
    b["today"]["pr_count"] = 7
    b["session"]["usd"] = 99.0  # session preserved
    out = maybe_rollover_today(b, now=date(2026, 5, 15))
    assert out["today"]["date"] == "2026-05-15"
    assert out["today"]["usd"] == 0
    assert out["today"]["pr_count"] == 0
    assert out["session"]["usd"] == 99.0


# --- check_limits ----------------------------------------------------------

def test_no_breaches_initially():
    assert check_limits(default_budget()) == []


def test_session_usd_breach():
    b = default_budget()
    b["session"]["usd"] = 60.0  # limit 50
    assert "session_usd" in check_limits(b)


def test_daily_usd_breach():
    b = default_budget()
    b["today"]["usd"] = 250.0
    assert "daily_usd" in check_limits(b)


def test_daily_pr_count_breach():
    b = default_budget()
    b["today"]["pr_count"] = 50
    assert "daily_pr_count" in check_limits(b)


def test_session_task_count_breach():
    b = default_budget()
    b["session"]["task_count"] = 21
    assert "session_task_count" in check_limits(b)


def test_consecutive_path_violations_breach():
    b = default_budget()
    b["consecutive_path_violations"] = 3
    assert "consecutive_path_violations" in check_limits(b)


def test_multiple_breaches_returned():
    b = default_budget()
    b["session"]["usd"] = 60.0
    b["today"]["usd"] = 250.0
    breaches = check_limits(b)
    assert "session_usd" in breaches and "daily_usd" in breaches


# --- add_cost / bump_counter -----------------------------------------------

def test_add_cost_updates_both_today_and_session():
    b = default_budget()
    b2 = add_cost(b, 1.50)
    assert b2["today"]["usd"] == 1.50
    assert b2["session"]["usd"] == 1.50
    # original untouched (pure function)
    assert b["today"]["usd"] == 0


def test_add_cost_session_only():
    b = default_budget()
    b2 = add_cost(b, 1.50, today=False, session=True)
    assert b2["today"]["usd"] == 0
    assert b2["session"]["usd"] == 1.50


def test_bump_counter():
    b = default_budget()
    b2 = bump_counter(b, "task_count", where="session", by=2)
    assert b2["session"]["task_count"] == 2
    assert b["session"]["task_count"] == 0  # original untouched
