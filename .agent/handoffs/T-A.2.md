---
task_id: T A.2
title: 配置系统
branch: task/ta2-config-system
pr: 3
status: ready_for_review
iteration: 2
dev_agent: dev-agent (xslkim)
created_at: "2026-04-18T13:30:00Z"
updated_at: "2026-04-18T16:32:00Z"
---

## 交付物清单

- [x] `src/autovisiontest/config/__init__.py` — 新建,导出核心类和 load_config
- [x] `src/autovisiontest/config/schema.py` — 新建,4 个 Pydantic 模型
- [x] `src/autovisiontest/config/loader.py` — 新建,配置加载器 + 优先级链 + 环境变量覆盖
- [x] `config/model.yaml` — 新建,示例配置(对齐产品文档 §8.4)
- [x] `tests/unit/config/test_loader.py` — 新建,17 个测试用例
- [x] `src/autovisiontest/cli.py` — **修改**,添加 `--config` 全局选项 + `validate` 子命令

## Iteration 2 变更

### R1 修复：添加 validate CLI 子命令

Test Agent review iter-1 要求：
> `autovisiontest --config config/model.yaml validate` 能打印解析后的配置

**修复内容** (`src/autovisiontest/cli.py`)：

1. 添加 `--config` 全局选项到 `@click.group()` 装饰器（类型 `click.Path(exists=False)`，默认 None）
2. 添加 `@click.pass_context` 到 `main` 函数签名，将 `config_path` 存入 `ctx.obj`
3. 新增 `validate` 命令函数：
   - 从 `ctx.obj` 取 `config_path`
   - 调用 `load_config(path=Path(config_path) if config_path else None)`
   - 用 `click.echo(config.model_dump_json(indent=2))` 输出 JSON

## 自测结果

```
$ pytest tests/unit/config/ -v
============ 17 passed in 0.21s ============

$ pytest tests/unit/ -v
============ 20 passed in 0.30s ============

$ python -m autovisiontest.cli --config config/model.yaml validate
{
  "planner": {
    "backend": "vllm_local",
    ...
  },
  ...
}
```

## 验收 Checklist

- [x] `pytest tests/unit/config/` 全通过 (17/17)
- [x] `autovisiontest --config config/model.yaml validate` 能打印解析后的配置 ✅ (iter-2 已修复)

## 范围检查

改动文件列表:
- src/autovisiontest/config/__init__.py   (新建, iter-1)
- src/autovisiontest/config/schema.py     (新建, iter-1)
- src/autovisiontest/config/loader.py     (新建, iter-1)
- config/model.yaml                       (新建, iter-1)
- tests/unit/config/test_loader.py        (新建, iter-1)
- src/autovisiontest/cli.py               (**修改**, iter-2: 添加 --config + validate)

所有改动在任务范围内。
