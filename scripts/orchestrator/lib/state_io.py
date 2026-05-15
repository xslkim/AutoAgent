"""state/ directory I/O.

Atomic file moves and JSON read/write. All operations use `os.replace` which
is atomic on the same filesystem (POSIX rename / Win32 ReplaceFile).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BUCKETS: tuple[str, ...] = (
    "queue",
    "ready",
    "in_progress",
    "awaiting_ci",
    "done",
    "failed",
    "needs_human",
    "blocked",
    "logs",
)
"""All task-bucket subdirectories under state/. Order matches docs/09 §二."""

TASK_BUCKETS: tuple[str, ...] = tuple(b for b in BUCKETS if b != "logs")
"""Buckets that hold TASK-NNNN.json files (excludes 'logs/')."""


@dataclass(frozen=True)
class StateRoot:
    """Convenience wrapper around the state/ directory layout.

    All methods are stateless — fresh disk reads each call. No caching.
    """

    root: Path

    # --- bucket paths ------------------------------------------------------

    def bucket(self, name: str) -> Path:
        if name not in BUCKETS:
            raise ValueError(f"unknown bucket: {name}")
        return self.root / name

    @property
    def budget_path(self) -> Path:
        return self.root / "budget.json"

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def stop_signal_path(self) -> Path:
        return self.root / "stop_signal"

    # --- listing -----------------------------------------------------------

    def list_task_files(self, bucket: str) -> list[Path]:
        """List TASK-NNNN.json files in a bucket. Sorted, deterministic."""
        d = self.bucket(bucket)
        if not d.is_dir():
            return []
        return sorted(p for p in d.glob("TASK-*.json") if p.is_file())

    def list_task_ids(self, bucket: str) -> list[str]:
        return [p.stem for p in self.list_task_files(bucket)]

    def find(self, task_id: str) -> tuple[str, Path] | None:
        """Locate a task by id. Returns (bucket_name, path) or None."""
        for bucket in TASK_BUCKETS:
            p = self.bucket(bucket) / f"{task_id}.json"
            if p.is_file():
                return bucket, p
        return None

    # --- I/O ---------------------------------------------------------------

    @staticmethod
    def load_task(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_task(path: Path, data: dict) -> None:
        """Atomic write via temp file + os.replace (same dir, same fs)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def move_task(self, task_id: str, target_bucket: str) -> Path:
        """Move a task to a new bucket. Returns the new path. Raises if not found."""
        location = self.find(task_id)
        if location is None:
            raise FileNotFoundError(f"task {task_id} not found in any bucket")
        _, src = location
        dst = self.bucket(target_bucket) / src.name
        if dst == src:
            return src
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return dst

    # --- stop_signal -------------------------------------------------------

    def is_stopped(self) -> bool:
        return self.stop_signal_path.is_file()

    def touch_stop_signal(self, reason: str = "") -> None:
        self.stop_signal_path.write_text(reason or "stop", encoding="utf-8")

    def clear_stop_signal(self) -> None:
        try:
            self.stop_signal_path.unlink()
        except FileNotFoundError:
            pass


def load_all_tasks(root: StateRoot, buckets: Iterable[str] | None = None) -> dict[str, tuple[str, dict]]:
    """Load every task across the given buckets. Returns {task_id: (bucket, data)}."""
    use = buckets if buckets is not None else TASK_BUCKETS
    out: dict[str, tuple[str, dict]] = {}
    for b in use:
        for p in root.list_task_files(b):
            out[p.stem] = (b, root.load_task(p))
    return out
