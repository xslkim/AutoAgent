# -*- coding: utf-8 -*-
"""Notepad hello-world exploratory test case.

Open Notepad, type a string, save to C:\\TestSandbox\\hello.txt, verify the file exists.

Usage::
    python -m autovisiontest --config config/model.yaml run --case examples/cases/notepad_hello.py --debug-trace
"""

from __future__ import annotations

from autovisiontest.cases.schema import AppConfig, TestCase


def build_case() -> TestCase:
    return TestCase(
        goal=(
            "Notepad has been launched and is in the foreground. Please complete these steps:\n"
            "1. Click in the text area and type exactly: Hello, AutoVisionTest!\n"
            "2. Open File -> Save As, navigate to C:\\TestSandbox\\ (create the folder if it does not exist), "
            "save the file as hello.txt.\n"
            "3. After the file is confirmed saved, call finished(content='hello.txt saved').\n"
            "Do NOT call finished before the file is actually saved to disk."
        ),
        app_config=AppConfig(
            app_path="C:\\Windows\\System32\\notepad.exe",
            app_args=[],
        ),
        steps=[],
        assertions=[
            {"type": "file_exists", "params": {"path": "C:\\TestSandbox\\hello.txt"}},
        ],
    )
