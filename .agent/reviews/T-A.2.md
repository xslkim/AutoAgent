---
task_id: T A.2
reviewer: test-agent (gaobiedongtian)
decision: request_changes
iteration: 2
reviewed_at: "2026-04-18T08:50:00Z"
---

## Summary

T A.2 配置系统的核心交付物（schema、loader、yaml）质量合格，17 项测试全部通过。但验收 checklist 第二项仍未满足：`autovisiontest --config config/model.yaml validate` 不可用。

## Checklist Verification (独立验证)

- [x] `pytest tests/unit/config/` 全通过 (17/17)
- [ ] `autovisiontest --config config/model.yaml validate` 能打印解析后的配置 — **未实现**

## Deliverables Completeness

| 交付物 | 状态 | 验证 |
|--------|------|------|
| `src/autovisiontest/config/__init__.py` | ✅ | 模块导出正确 |
| `src/autovisiontest/config/schema.py` | ✅ | 4 个 Pydantic 模型，validator 齐全 |
| `src/autovisiontest/config/loader.py` | ✅ | 优先级链 + 环境变量覆盖 + API key warning |
| `config/model.yaml` | ✅ | 示例配置对齐产品文档 |
| `tests/unit/config/test_loader.py` | ✅ | 17 个测试全通过 |

## Required Changes (必须修复)

### R1: 缺少 `validate` 子命令和 `--config` 全局选项

任务验收 checklist 明确要求：`autovisiontest --config config/model.yaml validate` 能打印解析后的配置。

任务文档原文（括号说明）："可先桩实现 validate 子命令"。

**最小实现**（在 `cli.py` 中）：
1. `main` 组添加 `--config` 选项（`click.option('--config', 'config_path', type=click.Path())`）
2. 添加 `validate` 子命令：加载配置 → `print(config.model_dump_json(indent=2))`

注意：虽然 `cli.py` 不在 T A.2 范围列表中，但验收 checklist 明确要求此功能，且标注"可先桩实现"。这属于范围灰色地带，但遵循"契约至上"原则（task_document 是 SSOT），以验收 checklist 为准。

## Suggestions (建议，非阻塞)

- S1: `load_config` 中的 `_DEFAULT_CONFIG_PATHS` 第二项使用 `__file__` 相对路径，在 `pip install -e .` 模式下可能指向源码目录（可接受），但 wheel 安装模式下可能不正确。建议在 docstring 中注明此限制。

## Independent Verification

```
$ git checkout task/ta2-config-system
$ pip install -e ".[dev]"

$ pytest tests/unit/config/test_loader.py -v
  17 passed in 0.20s

$ autovisiontest --config config/model.yaml validate
  Error: No such command 'validate'
  → 验收 checklist 第二项未通过
```

## Next Step

Dev Agent 请在 `cli.py` 中添加最小 `validate` 子命令和 `--config` 选项。修复后更新 handoff 进入 iteration 2。
