---
task_id: T B.3
title: 鼠标控制原语
agent: dev
status: ready_for_test
pr: 9
iteration: 1
---

# T B.3: 鼠标控制原语

## 交付物
- `src/autovisiontest/control/mouse.py` — move, click, double_click, right_click, drag, scroll
- `tests/unit/control/test_mouse.py` — 8 项测试（全部 mock pyautogui）

## 验收 Checklist
- [x] 8/8 测试通过
- [x] click 正确传递 button 参数
- [x] drag 调用 moveTo→mouseDown→moveTo→mouseUp 序列
- [x] scroll 正负方向正确
