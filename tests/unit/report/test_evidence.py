"""Tests for EvidenceWriter — screenshot and report file storage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from autovisiontest.report.evidence import EvidenceWriter


# A minimal model for testing write_report
class FakeReport(BaseModel):
    status: str = "PASS"
    summary: str = ""


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path


@pytest.fixture
def writer(tmp_data_dir: Path) -> EvidenceWriter:
    """Create an EvidenceWriter with a temp directory."""
    return EvidenceWriter(session_id="test-session-001", data_dir=tmp_data_dir)


class TestEvidenceWriter:
    """Tests for EvidenceWriter file operations."""

    def test_write_step_creates_files(
        self, writer: EvidenceWriter, tmp_data_dir: Path
    ) -> None:
        """write_step creates before/after screenshot files."""
        before_png = b"\x89PNG\r\n\x1a\n" + b"before_data"
        after_png = b"\x89PNG\r\n\x1a\n" + b"after_data"

        paths = writer.write_step(idx=0, before=before_png, after=after_png)

        assert "before" in paths
        assert "after" in paths
        assert paths["before"].exists()
        assert paths["after"].exists()
        assert paths["before"].read_bytes() == before_png
        assert paths["after"].read_bytes() == after_png

        # Verify directory structure
        evidence_dir = tmp_data_dir / "evidence" / "test-session-001"
        assert evidence_dir.exists()
        assert (evidence_dir / "step_0_before.png").exists()
        assert (evidence_dir / "step_0_after.png").exists()

    def test_write_step_with_ocr(
        self, writer: EvidenceWriter
    ) -> None:
        """write_step creates OCR JSON when ocr is provided."""
        ocr_data = {"items": [{"text": "hello", "confidence": 0.9}]}

        paths = writer.write_step(
            idx=1,
            before=b"before",
            after=b"after",
            ocr=ocr_data,
        )

        assert "ocr" in paths
        assert paths["ocr"].exists()

        loaded = json.loads(paths["ocr"].read_text(encoding="utf-8"))
        assert loaded["items"][0]["text"] == "hello"

    def test_write_step_with_pydantic_ocr(
        self, writer: EvidenceWriter
    ) -> None:
        """write_step handles Pydantic model OCR results."""
        ocr_model = FakeReport(status="DONE", summary="ocr result")

        paths = writer.write_step(
            idx=2, before=b"b", after=b"a", ocr=ocr_model
        )

        loaded = json.loads(paths["ocr"].read_text(encoding="utf-8"))
        assert loaded["status"] == "DONE"

    def test_write_step_multiple_indices(
        self, writer: EvidenceWriter
    ) -> None:
        """Multiple steps can be written with different indices."""
        for i in range(3):
            writer.write_step(
                idx=i,
                before=f"before_{i}".encode(),
                after=f"after_{i}".encode(),
            )

        for i in range(3):
            before_path = writer.evidence_dir / f"step_{i}_before.png"
            after_path = writer.evidence_dir / f"step_{i}_after.png"
            assert before_path.exists()
            assert after_path.exists()

    def test_write_report_json(
        self, writer: EvidenceWriter
    ) -> None:
        """write_report creates a valid JSON file."""
        report = FakeReport(status="FAIL", summary="Something went wrong")

        report_path = writer.write_report(report)

        assert report_path.exists()
        assert report_path.name == "report.json"

        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["status"] == "FAIL"
        assert data["summary"] == "Something went wrong"

    def test_write_report_overwrites(
        self, writer: EvidenceWriter
    ) -> None:
        """Calling write_report twice overwrites the previous file."""
        report1 = FakeReport(status="RUNNING")
        report2 = FakeReport(status="PASS")

        writer.write_report(report1)
        path = writer.write_report(report2)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "PASS"  # Second write wins

    def test_get_step_paths(
        self, writer: EvidenceWriter
    ) -> None:
        """get_step_paths returns expected path structure."""
        paths = writer.get_step_paths(idx=5)

        assert paths["before"].name == "step_5_before.png"
        assert paths["after"].name == "step_5_after.png"
        assert paths["ocr"].name == "ocr_5.json"

    def test_evidence_dir_property(
        self, writer: EvidenceWriter, tmp_data_dir: Path
    ) -> None:
        """evidence_dir returns the correct path."""
        expected = tmp_data_dir / "evidence" / "test-session-001"
        assert writer.evidence_dir == expected
