"""计算器 5×7 探索用例（Python 定义，与 calculator_5x7.json 等价）。

运行::
    python -m autovisiontest --config config/model.yaml run --case examples/cases/calculator_5x7.py
"""

from __future__ import annotations

from autovisiontest.cases.schema import AppConfig, TestCase


def build_case() -> TestCase:
    return TestCase(
        goal=(
            "计算器已由测试框架启动并置于前台。请在标准模式下用按钮或键盘完成乘法 "
            "5×7（也可按 5 * 7），确认界面上的结果显示为 35。确认无误后必须调用 "
            "finished(content='已验证 5×7=35') 结束任务，不要在未看到 35 前结束。"
        ),
        app_config=AppConfig(
            app_path=r"C:\Windows\System32\calc.exe",
            app_args=[],
        ),
        steps=[],
        assertions=[
            {"type": "ocr_contains", "params": {"text": "35"}},
        ],
    )
