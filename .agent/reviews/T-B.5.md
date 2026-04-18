# Review: T B.5 — 窗口管理

**任务**: window.py — 窗口管理 (pygetwindow + pywin32)
**分支**: task/tb5-window-management
**PR**: #11
**Reviewer**: test-agent (gaobiedongtian)
**日期**: 2026-04-18
**轮次**: 1

## 验收 Checklist

| # | 项目 | 结果 |
|---|------|------|
| 1 | `pytest tests/unit/control/test_window.py` 全通过 | ✅ 8/8 passed |
| 2 | list_windows / find_by_title / find_by_pid / focus / wait_window | ✅ 全部实现 |
| 3 | wait_window 超时抛出 AppLaunchError | ✅ 已验证 |
| 4 | find_window_by_title 含 substring fallback | ✅ 已验证 |

## 代码质量

- WindowInfo dataclass 设计清晰
- find_window_by_title 含 substring fallback — 容错性好
- wait_window 超时抛 AppLaunchError — 符合异常体系设计
- 所有函数调用 enable_dpi_awareness() — 符合 D6 约束
- 测试 MockWindow 设计完善

## 结论

**APPROVED** — 无修改要求。
