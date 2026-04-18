---
task_id: T B.6
title: 进程管理
agent: dev
status: ready_for_test
pr: 12
iteration: 1
---

# T B.6: 进程管理

## 交付物
- `src/autovisiontest/control/process.py` — AppHandle, launch/kill/close/is_alive
- `tests/unit/control/test_process.py` — 8 项测试

## 验收 Checklist
- [x] 8/8 测试通过
- [x] kill_processes_by_exe 忽略"进程不存在"
- [x] launch_app 找不到时抛 AppLaunchError
- [x] is_alive 进程退出后返回 False
- [x] close_app 先优雅关闭再强制kill
