---
task_id: T A.3
title: 日志系统
agent: dev
status: ready_for_test
pr: 4
iteration: 1
---

# T A.3: 日志系统

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/logging_setup.py` | structlog 初始化，支持 console/JSON 双模式 |
| `tests/unit/test_logging_setup.py` | 7 项单元测试 |

## 实现细节

### setup_logging(level, json_output, log_file)

- **Console 模式** (`json_output=False`)：`structlog.dev.ConsoleRenderer`，输出到 stderr
- **JSON 模式** (`json_output=True`)：`structlog.processors.JSONRenderer`，每行一条 JSON
- **Context vars**：自动合并 `structlog.contextvars`，支持 `session_id`、`step_idx` 绑定
- **默认字段**：`timestamp`(ISO 8601)、`level`、`logger_name`、`module`
- **文件轮转**：`RotatingFileHandler`，10MB × 5 个备份
- **幂等重入**：清空已有 handler 后重建，避免重复输出

### 测试覆盖

- `TestSetupLoggingConsole`：console 格式输出 + 日志级别过滤
- `TestSetupLoggingJson`：JSON 可解析 + 包含 timestamp
- `TestContextBinding`：`session_id` 和 `step_idx` 通过 contextvars 传播
- `TestLogFileRotation`：文件创建验证

## 验收 Checklist

- [x] `pytest tests/unit/test_logging_setup.py` 全通过 (7/7)
- [x] console 模式输出到 stderr，包含预期字段
- [x] JSON 模式每行可被 `json.loads` 解析
- [x] `structlog.contextvars.bind_contextvars(session_id="x")` 后日志含 `session_id=x`
