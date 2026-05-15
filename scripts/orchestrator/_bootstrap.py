"""Make `from lib import ...` work when the script is run directly.

Adds this file's parent dir (scripts/orchestrator/) to sys.path so each
top-level helper can simply `from lib import ...`.

Also reconfigures stdout/stderr to UTF-8 with replace on encode errors so
that Chinese / emoji / Unicode glyphs don't crash on Windows GBK consoles.
"""

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

# Best-effort UTF-8 reconfigure — only Python 3.7+ TextIOWrapper exposes this.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
