---
task_id: T A.5
title: CLI 骨架
agent: dev
status: ready_for_test
pr: 6
iteration: 1
---

# T A.5: CLI 骨架

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/cli.py` | CLI 入口，5 个子命令 + 3 个全局选项 |
| `tests/unit/test_cli.py` | 13 项单元测试 |

## 实现细节

### 全局选项
- `--version`：显示版本号
- `--config <path>`：指定配置文件路径
- `--log-level <DEBUG|INFO|WARNING|ERROR>`：日志级别

### 子命令（桩实现）
- `run --goal <str> --app <path> [--app-args] [--timeout]` 或 `run --case <path>`
- `status <session_id>`
- `report <session_id> [--format json|html]`
- `list-recordings`
- `validate`（加载并打印配置，config 模块不可用时给出友好提示）

### 设计决策
- `--goal` 和 `--case` 互斥，缺少时报 UsageError
- `logging_setup` 和 `config.loader` 通过 try/except ImportError 容错，因 T A.2/A.3 可能尚未合并
- 当 T A.2/A.3 合并后，validate 和 log-level 功能自动激活

## 验收 Checklist

- [x] `pytest tests/unit/test_cli.py` 全通过 (13/13)
- [x] `autovisiontest --help` 列出所有子命令
- [x] `autovisiontest run` 不带参数退出码非 0
- [x] `autovisiontest --version` 输出 0.1.0
