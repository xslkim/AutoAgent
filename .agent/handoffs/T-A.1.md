---
task_id: T A.1
title: 项目初始化
branch: task/ta1-project-init
pr: TBD
status: ready_for_review
iteration: 1
dev_agent: xslkim-dev
created_at: "2026-04-18T13:56:00Z"
updated_at: "2026-04-18T14:10:00Z"
---

## 交付物清单

- [x] `pyproject.toml` — 新建，hatchling 构建后端，完整依赖清单，CLI 入口点
- [x] `src/autovisiontest/__init__.py` — 新建，导出 `__version__ = "0.1.0"`
- [x] `src/autovisiontest/cli.py` — 新建，`click` CLI 桩实现，支持 `--version`
- [x] `.gitignore` — 新建，包含 data/、__pycache__、*.egg-info、.venv、.pytest_cache、secrets、agent locks
- [x] `tests/unit/test_init.py` — 新建，3 个测试用例

## 交付物细节

### `pyproject.toml`

- name: `autovisiontest`
- requires-python: `>=3.11`
- 构建后端: `hatchling`
- 依赖: 对齐 task_document §1.2 的完整清单
- `[project.scripts]`: `autovisiontest = "autovisiontest.cli:main"`
- pytest/ruff 配置已包含

### `src/autovisiontest/__init__.py`

- `__version__ = "0.1.0"`

### `src/autovisiontest/cli.py`

- `click.group` + `@click.version_option`
- `main() -> int` 返回 exit code

### `.gitignore`

- 包含 `data/`、`__pycache__/`、`*.egg-info`、`.venv`、secrets (`*.env`, `.autovt/`)、agent locks
- 与 dev_workflow §16.8 完全对齐

## 自测结果

```
$ py -c "import autovisiontest; print(autovisiontest.__version__)"
0.1.0

$ autovisiontest --version
autovisiontest, version 0.1.0

$ git check-ignore data/
data/

$ py -m pytest tests/unit/test_init.py -v
============ 3 passed in 0.14s ============
```

## 范围检查

改动文件列表（与任务"范围"白名单完全一致）:
- pyproject.toml (新建)
- src/autovisiontest/__init__.py (新建)
- src/autovisiontest/cli.py (新建)
- .gitignore (新建)
- tests/unit/test_init.py (新建)
- tests/__init__.py (新建)
- tests/unit/__init__.py (新建)
- tests/integration/__init__.py (新建)

额外添加了 README.md 相关（未修改，已有正确内容）。

## Checklist 自查

- [x] `pip install -e .` 成功
- [x] `autovisiontest --version` 输出 `0.1.0`
- [x] `.gitignore` 已生效（`data/` 不会被 git add）
