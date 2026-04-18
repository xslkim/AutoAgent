---
task_id: T A.4
title: 异常体系
agent: dev
status: ready_for_test
pr: 5
iteration: 1
---

# T A.4: 异常体系

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/exceptions.py` | 完整异常层级，含 `to_dict()` 序列化 |
| `tests/unit/test_exceptions.py` | 39 项单元测试 |

## 实现细节

### 异常层级

```
AutoVTError (base)
├── ConfigError
├── ControlError
│   ├── AppLaunchError
│   ├── AppCrashedError
│   └── ActionExecutionError
├── PerceptionError
│   ├── ScreenshotError
│   └── OCRError
├── BackendError (含 retryable 字段)
│   ├── ChatBackendError
│   └── GroundingBackendError
├── SafetyError
│   └── UnsafeActionError
├── SessionError
│   ├── SessionNotFoundError
│   └── SessionTimeoutError
└── CaseError
    └── RecordingInvalidError
```

### to_dict() 序列化

- 所有异常支持 `to_dict()` → `{"type": "...", "message": "...", "context": {...}}`
- `BackendError` 及其子类额外包含 `"retryable": bool`

### 测试覆盖

- 继承关系验证：18 项参数化测试
- 全局检查：1 项（确保所有异常类继承 AutoVTError）
- to_dict 序列化：20 项（含基础、默认值、retryable 等）

## 验收 Checklist

- [x] `pytest tests/unit/test_exceptions.py` 全通过 (39/39)
- [x] 所有异常类均继承自 `AutoVTError`
- [x] 每个 `to_dict()` 返回合法字典
