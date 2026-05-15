"""Make `agent.*` modules importable in tests."""

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

# Also expose the orchestrator lib (run_task depends on it).
ORCH_DIR = AGENT_DIR.parent / "orchestrator"
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))
