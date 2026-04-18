---
task_id: T B.4
title: 键盘控制原语
agent: dev
status: ready_for_test
pr: 10
iteration: 1
---

# T B.4: 键盘控制原语

## 交付物
- `src/autovisiontest/control/keyboard.py` — type_text, key_combo, press
- `tests/unit/control/test_keyboard.py` — 8 项测试

## 实现细节
- `type_text`: ASCII 文本用 typewrite，含非 ASCII（如中文）自动切换到 pyperclip.copy + Ctrl+V
- `key_combo`: 调用 pyautogui.hotkey
- `press`: 单键按下

## 验收 Checklist
- [x] 8/8 测试通过
- [x] ASCII 走 typewrite
- [x] 中文走 clipboard + hotkey("ctrl","v")
- [x] key_combo_ctrl_s 正确
