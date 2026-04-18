---
task_id: T B.7
title: 动作执行器
agent: dev
status: ready_for_test
pr: 13
iteration: 1
---

# T B.7: 动作执行器

## 交付物
- `src/autovisiontest/control/actions.py` — Action/ActionResult Pydantic 模型
- `src/autovisiontest/control/executor.py` — ActionExecutor 分派到 mouse/keyboard
- `tests/unit/control/test_executor.py` — 10 项测试

## 验收 Checklist
- [x] 10/10 测试通过
- [x] execute click 正确分派
- [x] type 不需要 coords
- [x] click 不传 coords 抛 ActionExecutionError
- [x] 未知 action type 抛 ActionExecutionError
