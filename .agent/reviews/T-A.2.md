---
task_id: T A.2
reviewer: test-agent (gaobiedongtian)
decision: request_changes
iteration: 1
reviewed_at: "2026-04-18T14:45:00Z"
---

## Summary

T A.2 配置系统 检出 1 个必须修复的问题。代码实现质量整体良好，schema 和 loader 逻辑正确，17 项测试全通过，但验收 checklist 有一条未满足。

## Required Changes (必须修复)

### R1: 缺少 `validate` CLI 子命令和 `--config` 全局选项

任务验收 checklist 要求：
> `autovisiontest --config config/model.yaml validate` 能打印解析后的配置（可先桩实现 validate 子命令）

当前 `cli.py` 只有 `click.group` + `--version`，没有 `validate` 子命令，也没有 `--config` 全局选项。

- 文件: `src/autovisiontest/cli.py`
- 期望: 添加 `validate` 子命令（桩实现即可），加载配置并以可读格式打印；添加 `--config` 全局选项传入配置路径
- 对应 checklist 条目: "autovisiontest --config config/model.yaml validate 能打印解析后的配置"

**建议实现**：

```python
@click.group()
@click.version_option(version=__version__, prog_name="autovisiontest")
@click.option("--config", "config_path", type=click.Path(), default=None, help="Path to config YAML file.")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> int:
    """AutoVisionTest — ..."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    return 0

@main.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Load and print the current configuration."""
    from autovisiontest.config.loader import load_config
    from pathlib import Path
    config_path = ctx.obj.get("config_path")
    config = load_config(path=Path(config_path) if config_path else None)
    click.echo(config.model_dump_json(indent=2))
```

## Checklist Verification (独立验证)

- [x] `pytest tests/unit/config/` 全通过 (17/17)
- [ ] `autovisiontest --config config/model.yaml validate` 能打印解析后的配置 ❌ (No such command 'validate')

## Deliverables Completeness

| 交付物 | 状态 | 验证 |
|--------|------|------|
| `src/autovisiontest/config/__init__.py` | ✅ | 导出核心类和 load_config |
| `src/autovisiontest/config/schema.py` | ✅ | 4 个 Pydantic 模型 + validators |
| `src/autovisiontest/config/loader.py` | ✅ | 优先级链 + 环境变量覆盖 + API key warning |
| `config/model.yaml` | ✅ | 对齐产品文档 §8.4 |
| `tests/unit/config/test_loader.py` | ✅ | 17 项测试全通过 |

## Scope Check (范围检查)

T A.2 任务范围：
- `src/autovisiontest/config/__init__.py` ✅
- `src/autovisiontest/config/schema.py` ✅
- `src/autovisiontest/config/loader.py` ✅
- `config/model.yaml` ✅
- `tests/unit/config/test_loader.py` ✅

额外文件：`cli.py` 修改（16行加入），但内容仍是 T A.1 的桩——未添加 validate 子命令，这恰好是需要修复的点。

`.agent/handoffs/T-A.1.md` — T A.1 的 handoff 文件，在该分支上出现合理（分支基于 T A.1 merge 前）。

**越界文件：无。**

## Code Review

- ✅ 类型注解齐全
- ✅ 所有导出函数有 docstring
- ✅ 无遗留 `print()`
- ✅ 无硬编码绝对路径
- ✅ 无 UIA 依赖
- ✅ Pydantic validators 正确
- ✅ 优先级链实现正确
- ✅ 环境变量覆盖逻辑正确
- ✅ API key warning 行为正确（warning 而非 exception）
- ✅ `config/model.yaml` 内容完整

## Independent Verification

```
$ git checkout task/ta2-config-system
$ pytest tests/unit/config/test_loader.py -v
  17 passed in 0.21s

$ pytest -v
  20 passed in 0.30s

$ python -m autovisiontest.cli validate --config config/model.yaml
  Error: No such command 'validate'.

$ git diff main...HEAD --name-only
  (17 files, all within scope)
```

## Next Step

Dev Agent 请修复 R1：在 `cli.py` 中添加 `--config` 全局选项和 `validate` 子命令。修复后更新 handoff 进入 iteration 2。
