"""Recording store — persistent storage for test case recordings.

Recordings are stored as JSON files under ``{data_dir}/recordings/``,
one file per fingerprint.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from autovisiontest.cases.fingerprint import compute_fingerprint
from autovisiontest.cases.schema import TestCase

logger = logging.getLogger(__name__)


class RecordingStore:
    """Persistent store for test case recordings.

    Args:
        data_dir: Root data directory. Recordings are stored under
            ``{data_dir}/recordings/``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._recordings_dir = data_dir / "recordings"
        self._recordings_dir.mkdir(parents=True, exist_ok=True)

    def save(self, case: TestCase) -> Path:
        """Save a test case recording to disk.

        Args:
            case: The TestCase to save.

        Returns:
            Path to the saved JSON file.
        """
        # Compute fingerprint if not set
        if not case.metadata.fingerprint:
            fp = compute_fingerprint(
                case.app_config.app_path,
                case.goal,
            )
            case.metadata.fingerprint = fp

        fp = case.metadata.fingerprint
        path = self._recordings_dir / f"{fp}.json"
        path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
        logger.info("recording_saved", extra={"fingerprint": fp, "path": str(path)})
        return path

    def load(self, fingerprint: str) -> TestCase | None:
        """Load a test case recording by fingerprint.

        Args:
            fingerprint: The fingerprint string.

        Returns:
            TestCase if found, None otherwise.
        """
        path = self._recordings_dir / f"{fingerprint}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TestCase.model_validate(data)
        except Exception:
            logger.exception("recording_load_failed", extra={"fingerprint": fingerprint})
            return None

    def list_all(self) -> list[TestCase]:
        """List all stored recordings.

        Returns:
            List of all TestCase objects in the store.
        """
        cases: list[TestCase] = []
        for path in sorted(self._recordings_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cases.append(TestCase.model_validate(data))
            except Exception:
                logger.warning("recording_skip_invalid", extra={"path": str(path)})
        return cases

    def delete(self, fingerprint: str) -> bool:
        """Delete a recording by fingerprint.

        Args:
            fingerprint: The fingerprint string.

        Returns:
            True if the recording was deleted, False if not found.
        """
        path = self._recordings_dir / f"{fingerprint}.json"
        if path.exists():
            path.unlink()
            logger.info("recording_deleted", extra={"fingerprint": fingerprint})
            return True
        return False

    def find_for_goal(self, app_path: str, goal: str) -> TestCase | None:
        """Find a recording matching the given app and goal.

        Searches through all recordings for one whose app_path and goal
        match the query.  Uses fingerprint for an O(1) lookup first.

        Args:
            app_path: Application path.
            goal: Test goal.

        Returns:
            Matching TestCase if found, None otherwise.
        """
        # Try fingerprint-based lookup first
        fp = compute_fingerprint(app_path, goal)
        case = self.load(fp)
        if case is not None:
            return case

        # Fallback: linear scan (for cases where fingerprint computation
        # might differ, e.g., app version changed)
        normalized_goal = goal.lower().strip()
        for case in self.list_all():
            if (
                case.app_config.app_path.lower() == app_path.lower()
                and case.goal.lower().strip() == normalized_goal
            ):
                return case

        return None
