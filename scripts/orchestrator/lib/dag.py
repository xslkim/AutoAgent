"""Dependency-graph computations for the task scheduler.

Pure functions over (queue, done, failed, needs_human) sets — no I/O.
See docs/09-orchestration.md §四 for semantics.
"""

from __future__ import annotations

from dataclasses import dataclass


class DependencyError(Exception):
    """Raised when the task graph has a cycle or other structural issue."""


@dataclass(frozen=True)
class ReadyDecision:
    task_id: str
    target: str  # "ready" | "blocked" | "queue"
    reason: str  # human-readable explanation


def _deps(task: dict) -> list[str]:
    return list(task.get("depends_on") or [])


def compute_ready_and_blocked(
    queue: dict[str, dict],
    blocked: dict[str, dict],
    *,
    done_ids: set[str],
    failed_ids: set[str],
    needs_human_ids: set[str],
) -> list[ReadyDecision]:
    """Decide what to do with every task currently sitting in queue/ or blocked/.

    Rules (docs/09 §4.1 + §4.2):
      - any dep ∈ failed ∪ needs_human → blocked
      - all deps ∈ done                → ready
      - else                            → keep where it is

    Returns the *changes* — tasks whose target bucket differs from their current
    one. Callers apply moves via StateRoot.move_task.
    """
    decisions: list[ReadyDecision] = []
    fail_or_block = failed_ids | needs_human_ids

    # queue → ready / blocked
    for tid, task in queue.items():
        deps = _deps(task)
        if any(d in fail_or_block for d in deps):
            blockers = [d for d in deps if d in fail_or_block]
            decisions.append(ReadyDecision(tid, "blocked", f"upstream blocked: {blockers}"))
            continue
        if deps and all(d in done_ids for d in deps):
            decisions.append(ReadyDecision(tid, "ready", "all deps done"))
            continue
        if not deps:
            decisions.append(ReadyDecision(tid, "ready", "no deps"))
            continue
        # Some deps still pending elsewhere: stay in queue.

    # blocked → ready (recovery)
    for tid, task in blocked.items():
        deps = _deps(task)
        if any(d in fail_or_block for d in deps):
            continue  # still blocked
        if all(d in done_ids for d in deps):
            decisions.append(ReadyDecision(tid, "ready", "blockers recovered"))

    return decisions


def find_cycles(tasks: dict[str, dict]) -> list[list[str]]:
    """Detect cycles in the dependency graph. Returns one cycle per SCC > 1."""
    # Tarjan's algorithm, iterative.
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[list[str]] = []

    def strongconnect(v: str) -> None:
        work = [(v, iter(_deps(tasks[v]) if v in tasks else []))]
        call_stack: list[str] = [v]
        indices[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        while work:
            node, deps_iter = work[-1]
            try:
                w = next(deps_iter)
                if w not in tasks:
                    continue
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(_deps(tasks[w]))))
                    call_stack.append(w)
                elif w in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[w])
            except StopIteration:
                if lowlinks[node] == indices[node]:
                    comp: list[str] = []
                    while True:
                        x = stack.pop()
                        on_stack.discard(x)
                        comp.append(x)
                        if x == node:
                            break
                    if len(comp) > 1 or (len(comp) == 1 and node in _deps(tasks[node])):
                        cycles.append(sorted(comp))
                work.pop()
                if call_stack:
                    call_stack.pop()
                if work:
                    parent_node = work[-1][0]
                    lowlinks[parent_node] = min(lowlinks[parent_node], lowlinks[node])

    for v in tasks:
        if v not in indices:
            strongconnect(v)

    return cycles
