"""Offline smoke test for backends.uitars parser (no service needed)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from autovisiontest.backends.uitars import (  # noqa: E402
    _unescape,
    parse_action_response,
    parse_uitars_response,
)

W, H = 1920, 1080

CASES: list[tuple[str, str]] = [
    # --- primary dialect: start_box='(x,y)' (what AWQ checkpoint emits) ---
    (
        "click_startbox_zh",
        "Thought: 我需要点击搜索按钮。\nAction: click(start_box='(512,720)')",
    ),
    (
        "left_double_startbox",
        "Thought: double click.\nAction: left_double(start_box='(100,200)')",
    ),
    (
        "right_single_startbox",
        "Thought: context menu.\nAction: right_single(start_box='(50,60)')",
    ),
    (
        "drag_startbox",
        "Thought: drag it.\nAction: drag(start_box='(10,20)', end_box='(300,400)')",
    ),
    (
        "scroll_startbox",
        "Thought: scroll down.\nAction: scroll(start_box='(960,540)', direction='down')",
    ),
    # --- back-compat: <point>x y</point> dialect (official 1.5 weights) ---
    (
        "click_point_zh",
        "Thought: 我需要点击搜索按钮。\nAction: click(point='<point>512 720</point>')",
    ),
    (
        "drag_point",
        "Thought: drag it.\nAction: drag(start_point='<point>10 20</point>', end_point='<point>300 400</point>')",
    ),
    # --- non-coordinate actions ---
    (
        "type_chinese",
        "Thought: 输入文字。\nAction: type(content='今天天气真好')",
    ),
    (
        "type_escaped_newline",
        "Thought: submit.\nAction: type(content='hello\\nworld')",
    ),
    (
        "hotkey",
        "Thought: save.\nAction: hotkey(key='ctrl s')",
    ),
    (
        "wait",
        "Thought: wait.\nAction: wait()",
    ),
    (
        "finished",
        "Thought: all done.\nAction: finished(content='saved to desktop')",
    ),
    # --- tolerance edge cases ---
    (
        "no_thought",
        "Action: click(start_box='(1,2)')",
    ),
    (
        "backticks",
        "Thought: test.\nAction: ```click(start_box='(5,6)')```",
    ),
    # AWQ-checkpoint drift: stop sequence fires mid-arg, so the closing
    # quote and paren never arrive.  Parser should still recover the coord.
    (
        "truncated_startbox",
        "Thought: fix it.\nAction: click(start_box='(560,362)",
    ),
    (
        "truncated_bbox",
        "Thought: oops.\nAction: click(start_box='[100,200,300,400",
    ),
]


def main() -> int:
    print("=== parser smoke test ===")
    fails: list[str] = []
    for name, raw in CASES:
        d = parse_uitars_response(raw, W, H, W, H)
        ok = d.parse_error is None
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {name:22s} type={d.action_type:13s} "
            f"point={d.point_xy} end={d.end_point_xy} "
            f"params={d.action_params} finished={d.finished} "
            f"err={d.parse_error}"
        )
        if not ok:
            fails.append(name)

    # Scaling: orig 1920x1080, sent 1344x756.  Model emits (672, 378) — half of sent.
    for label, raw in (
        ("scale_check_startbox", "Thought: x.\nAction: click(start_box='(672,378)')"),
        ("scale_check_point", "Thought: x.\nAction: click(point='<point>672 378</point>')"),
    ):
        d = parse_uitars_response(raw, 1920, 1080, 1344, 756)
        expected = (960, 540)
        if d.point_xy != expected:
            print(f"[FAIL] {label} got {d.point_xy}, expected {expected}")
            fails.append(label)
        else:
            print(f"[OK ] {label:22s} got {d.point_xy}")

    # MAI-UI norm1000 coord transform: model emits [0, 1000] per axis,
    # we scale back to 1920x1080 screen pixels.  Ground truth from the
    # 2026-04-20 calculator matrix probe: (725, 587) → (1392, 634) for
    # the × button; (314, 592) → (603, 639) for the 8 button.
    def _norm1000(w: int, h: int):
        def _t(x: float, y: float) -> tuple[int, int]:
            return (
                max(0, min(w - 1, int(round(x * w / 1000.0)))),
                max(0, min(h - 1, int(round(y * h / 1000.0)))),
            )
        return _t

    maiui_cases = [
        ("maiui_multiply_x", "Thought: 点 ×.\nAction: click(start_box='(725,587)')", (1392, 634)),
        ("maiui_digit_8",    "Thought: 点 8.\nAction: click(start_box='(314,592)')", (603, 639)),
        ("maiui_edge_max",   "Thought: edge.\nAction: click(start_box='(1000,1000)')", (1919, 1079)),
    ]
    for label, raw, expected in maiui_cases:
        d = parse_action_response(raw, _norm1000(1920, 1080))
        if d.point_xy != expected:
            print(f"[FAIL] {label} got {d.point_xy}, expected {expected}")
            fails.append(label)
        else:
            print(f"[OK ] {label:22s} got {d.point_xy}")

    print(f"\nunescape('hello\\\\nworld') = {_unescape('hello\\nworld')!r}")
    print(f"unescape(chinese)          = {_unescape('今天\\\\ntest')!r}")

    if fails:
        print(f"\nFAILED: {fails}")
        return 1
    print("\nALL GOOD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
