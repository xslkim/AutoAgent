"""dag.py: ready computation, blocked propagation, cycle detection."""

from __future__ import annotations

from lib.dag import compute_ready_and_blocked, find_cycles


def t(tid: str, *deps: str) -> dict:
    return {"id": tid, "depends_on": list(deps)}


# --- compute_ready_and_blocked --------------------------------------------

def test_no_deps_goes_ready():
    decisions = compute_ready_and_blocked(
        queue={"A": t("A")},
        blocked={},
        done_ids=set(),
        failed_ids=set(),
        needs_human_ids=set(),
    )
    assert len(decisions) == 1
    assert decisions[0].task_id == "A"
    assert decisions[0].target == "ready"


def test_all_deps_done_goes_ready():
    decisions = compute_ready_and_blocked(
        queue={"B": t("B", "A")},
        blocked={},
        done_ids={"A"},
        failed_ids=set(),
        needs_human_ids=set(),
    )
    assert decisions[0].target == "ready"


def test_failed_dep_blocks():
    decisions = compute_ready_and_blocked(
        queue={"B": t("B", "A")},
        blocked={},
        done_ids=set(),
        failed_ids={"A"},
        needs_human_ids=set(),
    )
    assert decisions[0].target == "blocked"
    assert "A" in decisions[0].reason


def test_needs_human_dep_blocks():
    decisions = compute_ready_and_blocked(
        queue={"B": t("B", "A")},
        blocked={},
        done_ids=set(),
        failed_ids=set(),
        needs_human_ids={"A"},
    )
    assert decisions[0].target == "blocked"


def test_pending_dep_stays_in_queue():
    """Deps not yet done/failed → task stays in queue (no transition emitted)."""
    decisions = compute_ready_and_blocked(
        queue={"B": t("B", "A")},  # A is still in queue/ready
        blocked={},
        done_ids=set(),
        failed_ids=set(),
        needs_human_ids=set(),
    )
    assert decisions == []


def test_blocked_recovers_to_ready_when_blockers_done():
    decisions = compute_ready_and_blocked(
        queue={},
        blocked={"B": t("B", "A")},
        done_ids={"A"},
        failed_ids=set(),
        needs_human_ids=set(),
    )
    assert len(decisions) == 1
    assert decisions[0].task_id == "B"
    assert decisions[0].target == "ready"
    assert "recover" in decisions[0].reason


def test_blocked_stays_blocked_if_blocker_still_failed():
    decisions = compute_ready_and_blocked(
        queue={},
        blocked={"B": t("B", "A")},
        done_ids=set(),
        failed_ids={"A"},
        needs_human_ids=set(),
    )
    assert decisions == []


def test_multiple_deps_one_failed_blocks():
    decisions = compute_ready_and_blocked(
        queue={"C": t("C", "A", "B")},
        blocked={},
        done_ids={"A"},
        failed_ids={"B"},
        needs_human_ids=set(),
    )
    assert decisions[0].target == "blocked"


def test_diamond_dag():
    """A → B, A → C, (B, C) → D — D goes ready only after both B and C done."""
    queue = {
        "B": t("B", "A"),
        "C": t("C", "A"),
        "D": t("D", "B", "C"),
    }
    # A done, B/C pending — D still in queue (because deps pending)
    decisions = compute_ready_and_blocked(
        queue=queue,
        blocked={},
        done_ids={"A"},
        failed_ids=set(),
        needs_human_ids=set(),
    )
    targets = {d.task_id: d.target for d in decisions}
    assert targets.get("B") == "ready"
    assert targets.get("C") == "ready"
    assert "D" not in targets  # stays in queue


# --- find_cycles ----------------------------------------------------------

def test_no_cycle_in_simple_chain():
    tasks = {"A": t("A"), "B": t("B", "A"), "C": t("C", "B")}
    assert find_cycles(tasks) == []


def test_self_cycle_detected():
    tasks = {"A": t("A", "A")}
    cycles = find_cycles(tasks)
    assert cycles == [["A"]]


def test_two_node_cycle_detected():
    tasks = {"A": t("A", "B"), "B": t("B", "A")}
    cycles = find_cycles(tasks)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"A", "B"}


def test_external_dep_not_in_task_set_is_ignored():
    tasks = {"A": t("A", "NONEXISTENT")}
    assert find_cycles(tasks) == []
