"""Evidence writer — stores screenshots, OCR results, and reports to disk.

Evidence for each session is stored under ``{data_dir}/evidence/{session_id}/``:
- ``step_{idx}_before.png`` — screenshot before action execution
- ``step_{idx}_after.png`` — screenshot after action execution
- ``ocr_{idx}.json`` — OCR result cache per step
- ``report.json`` — final structured report
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EvidenceWriter:
    """Write evidence files (screenshots, OCR, reports) to disk.

    Args:
        session_id: The session identifier.
        data_dir: Root data directory. Evidence is stored under
            ``{data_dir}/evidence/{session_id}/``.
    """

    def __init__(self, session_id: str, data_dir: Path) -> None:
        self._session_id = session_id
        self._evidence_dir = data_dir / "evidence" / session_id
        self._evidence_dir.mkdir(parents=True, exist_ok=True)

    @property
    def evidence_dir(self) -> Path:
        """Return the evidence directory path."""
        return self._evidence_dir

    def write_step(
        self,
        idx: int,
        before: bytes,
        after: bytes,
        ocr: Any | None = None,
    ) -> dict[str, Path]:
        """Write evidence files for a single step.

        Args:
            idx: Step index (0-based).
            before: Before-action screenshot as PNG bytes.
            after: After-action screenshot as PNG bytes.
            ocr: Optional OCR result. If it has a ``model_dump`` method
                (Pydantic model) it will be serialized. Otherwise, it
                should be JSON-serializable.

        Returns:
            Dict with keys ``before``, ``after``, and optionally ``ocr``,
            mapping to the Path of each written file.
        """
        paths: dict[str, Path] = {}

        # Write before screenshot
        before_path = self._evidence_dir / f"step_{idx}_before.png"
        before_path.write_bytes(before)
        paths["before"] = before_path

        # Write after screenshot
        after_path = self._evidence_dir / f"step_{idx}_after.png"
        after_path.write_bytes(after)
        paths["after"] = after_path

        # Write OCR result if provided
        if ocr is not None:
            ocr_path = self._evidence_dir / f"ocr_{idx}.json"
            if hasattr(ocr, "model_dump"):
                # Pydantic model
                ocr_data = ocr.model_dump()
            elif isinstance(ocr, dict):
                ocr_data = ocr
            else:
                # dataclass or other — try to serialize fields
                ocr_data = str(ocr)

            ocr_path.write_text(
                json.dumps(ocr_data, indent=2, default=str),
                encoding="utf-8",
            )
            paths["ocr"] = ocr_path

        logger.debug(
            "evidence_step_written",
            extra={"session_id": self._session_id, "step_idx": idx},
        )

        return paths

    def write_report(self, report: BaseModel) -> Path:
        """Write the final report to disk.

        Args:
            report: The Report model instance (Pydantic BaseModel).

        Returns:
            Path to the written report JSON file.
        """
        report_path = self._evidence_dir / "report.json"
        report_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(
            "evidence_report_written",
            extra={
                "session_id": self._session_id,
                "path": str(report_path),
            },
        )
        return report_path

    def get_step_paths(self, idx: int) -> dict[str, Path]:
        """Get the expected paths for a step's evidence files.

        Does not check if the files exist.

        Args:
            idx: Step index.

        Returns:
            Dict with keys ``before``, ``after``, ``ocr``.
        """
        return {
            "before": self._evidence_dir / f"step_{idx}_before.png",
            "after": self._evidence_dir / f"step_{idx}_after.png",
            "ocr": self._evidence_dir / f"ocr_{idx}.json",
        }
