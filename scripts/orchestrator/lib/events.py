"""events.jsonl append-only log helpers.

Single-writer model (顶层 poll only). For multi-writer scenarios we'd need
flock — out of scope for Phase 0.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def append_event(events_path: Path, event_type: str, **fields) -> None:
    """Append one JSON line to events.jsonl with ts + type + fields."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
    }
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def iter_events(events_path: Path) -> Iterator[dict]:
    """Yield each line of events.jsonl as a parsed dict. Skips blank lines."""
    if not events_path.is_file():
        return
    with events_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Tolerate partial writes on crash — single corrupted line shouldn't block reads.
                continue
