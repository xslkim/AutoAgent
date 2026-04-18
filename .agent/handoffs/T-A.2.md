---
task_id: T A.2
title: 配置系统
agent: dev
status: ready_for_test
pr: 3
iteration: 1
---

# T A.2: 配置系统

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/config/__init__.py` | 模块入口，导出核心类和 `load_config` |
| `src/autovisiontest/config/schema.py` | Pydantic 模型：`PlannerConfig`, `ActorConfig`, `RuntimeConfig`, `AppConfig` |
| `src/autovisiontest/config/loader.py` | 配置加载器：YAML + 环境变量覆盖 + 优先级链 |
| `config/model.yaml` | 示例配置文件，对齐产品文档 §8.4 |
| `tests/unit/config/test_loader.py` | 17 项单元测试 |

## 实现细节

### Schema (schema.py)
- `PlannerConfig`：`backend` (Literal 4 选 1), `model`, `api_key_env`, `max_tokens`, `temperature`, `endpoint` — 含 validator
- `ActorConfig`：`backend` (Literal 3 选 1), `model`, `endpoint`, `confidence_threshold` — 含 validator
- `RuntimeConfig`：`max_steps=30`, `max_session_duration_s=600`, `step_wait_ms=500`, `data_dir=Path("./data")`
- `AppConfig`：组合以上三个子模型

### Loader (loader.py)
- `load_config(path=None) -> AppConfig`：优先级链：显式路径 > `AUTOVT_CONFIG` > `./config/model.yaml` > 包内默认 > 内置默认
- 环境变量覆盖：`AUTOVT_DATA_DIR`, `AUTOVT_PLANNER_BACKEND`, `AUTOVT_ACTOR_BACKEND`
- 云端 backend + `api_key_env` 指向未设置的环境变量时：打印 warning，不抛异常（延迟到调用时检查）
- 无效 backend 通过 Pydantic `Literal` 类型拒绝，抛 `ValidationError`

### 测试覆盖
- `TestLoadDefaultConfig`：最小/空/完整 YAML 加载
- `TestEnvVarOverride`：3 个环境变量覆盖 + `AUTOVT_CONFIG` 路径
- `TestInvalidBackendRejected`：非法 backend/temperature/confidence
- `TestMissingApiKeyWarning`：缺 API key 的 warning 行为
- `TestFileNotFound`：显式/环境变量路径不存在时抛 `FileNotFoundError`

## 验收 Checklist

- [x] `pytest tests/unit/config/` 全通过 (17/17)
- [x] 配置加载优先级链正确
- [x] 环境变量覆盖生效
- [x] 无效 backend 被 Pydantic 拒绝
- [x] 云端 backend 缺 API key 时发出 warning 而非异常
