---
task_id: T B.5
title: 窗口管理
agent: dev
status: ready_for_test
pr: 11
iteration: 1
---

# T B.5: 窗口管理

## 交付物
- `src/autovisiontest/control/window.py` — WindowInfo, list/find/focus/wait_window
- `tests/unit/control/test_window.py` — 8 项测试

## 验收 Checklist
- [x] 8/8 测试通过
- [x] list_windows 返回 WindowInfo 列表
- [x] find_window_by_title 支持子串匹配
- [x] wait_window 超时抛 AppLaunchError
