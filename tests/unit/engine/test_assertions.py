"""Unit tests for engine assertions module (T F.5)."""

from __future__ import annotations

import os
import tempfile

import numpy as np

from autovisiontest.backends.types import ChatResponse, Message
from autovisiontest.engine.assertions import (
    assert_file_contains,
    assert_file_exists,
    assert_no_error_dialog,
    assert_ocr_contains,
    assert_screenshot_similar,
    assert_vlm_element_exists,
    run_assertions,
)
from autovisiontest.engine.models import Assertion
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult


def _make_ocr(items: list[tuple[str, int, int]]) -> OCRResult:
    return OCRResult(
        items=[
            OCRItem(text=t, bbox=BoundingBox(x=x, y=y, w=50, h=20), confidence=0.95)
            for t, x, y in items
        ],
        image_size=(1920, 1080),
    )


class TestAssertOcrContains:
    def test_found(self) -> None:
        ocr = _make_ocr([("hello", 10, 10), ("world", 100, 10)])
        result = assert_ocr_contains(ocr, "hello")
        assert result.passed is True

    def test_not_found(self) -> None:
        ocr = _make_ocr([("hello", 10, 10)])
        result = assert_ocr_contains(ocr, "goodbye")
        assert result.passed is False

    def test_fuzzy_match(self) -> None:
        ocr = _make_ocr([("helo", 10, 10)])
        result = assert_ocr_contains(ocr, "hello")  # edit distance 1
        assert result.passed is True


class TestAssertNoErrorDialog:
    def test_no_error(self) -> None:
        ocr = _make_ocr([("File", 10, 10), ("Save", 100, 10)])
        result = assert_no_error_dialog(ocr)
        assert result.passed is True

    def test_error_keyword(self) -> None:
        ocr = _make_ocr([("Error", 10, 10)])
        result = assert_no_error_dialog(ocr)
        assert result.passed is False


class TestAssertFileExists:
    def test_exists(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            result = assert_file_exists(path)
            assert result.passed is True
        finally:
            os.unlink(path)

    def test_not_exists(self) -> None:
        result = assert_file_exists("/nonexistent/path/file.txt")
        assert result.passed is False


class TestAssertFileContains:
    def test_contains(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            path = f.name
        try:
            result = assert_file_contains(path, "hello")
            assert result.passed is True
        finally:
            os.unlink(path)

    def test_not_contains(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            path = f.name
        try:
            result = assert_file_contains(path, "goodbye")
            assert result.passed is False
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        result = assert_file_contains("/nonexistent/path/file.txt", "test")
        assert result.passed is False


class TestAssertScreenshotSimilar:
    def test_identical_images(self) -> None:
        img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        result = assert_screenshot_similar(img, img, threshold=0.9)
        assert result.passed is True

    def test_different_images(self) -> None:
        img1 = np.zeros((100, 100, 3), dtype=np.uint8)
        img2 = np.ones((100, 100, 3), dtype=np.uint8) * 255
        result = assert_screenshot_similar(img1, img2, threshold=0.9)
        assert result.passed is False


class TestAssertVlmElementExists:
    def test_element_found(self) -> None:
        class _MockBackend:
            def chat(self, messages, images=None, response_format="json"):
                return ChatResponse(content="yes, the button is visible", raw={}, usage=None)

        result = assert_vlm_element_exists(_MockBackend(), b"img", "save button")
        assert result.passed is True

    def test_element_not_found(self) -> None:
        class _MockBackend:
            def chat(self, messages, images=None, response_format="json"):
                return ChatResponse(content="no, not visible", raw={}, usage=None)

        result = assert_vlm_element_exists(_MockBackend(), b"img", "save button")
        assert result.passed is False

    def test_backend_error(self) -> None:
        class _FailingBackend:
            def chat(self, messages, images=None, response_format="json"):
                raise RuntimeError("backend down")

        result = assert_vlm_element_exists(_FailingBackend(), b"img", "button")
        assert result.passed is False


class TestRunAssertions:
    def test_run_ocr_assertion(self) -> None:
        ocr = _make_ocr([("hello", 10, 10)])
        assertions = [Assertion(type="ocr_contains", params={"text": "hello"})]
        results = run_assertions(assertions, ctx={"ocr": ocr})
        assert len(results) == 1
        assert results[0].passed is True

    def test_run_unknown_type(self) -> None:
        assertions = [Assertion(type="custom_unknown", params={})]
        results = run_assertions(assertions, ctx={})
        assert len(results) == 1
        assert results[0].passed is False
        assert "Unknown" in results[0].detail

    def test_run_multiple(self) -> None:
        ocr = _make_ocr([("hello", 10, 10)])
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            assertions = [
                Assertion(type="ocr_contains", params={"text": "hello"}),
                Assertion(type="file_exists", params={"path": path}),
            ]
            results = run_assertions(assertions, ctx={"ocr": ocr})
            assert len(results) == 2
            assert results[0].passed is True
            assert results[1].passed is True
        finally:
            os.unlink(path)
