# AutoVisionTest — 双 Agent 开发流程文档 v1.0

文档日期：2026-04-18
配套文档：`docs/product_document.md` v2.1、`docs/task_document.md` v2.0

---

## 0. 本文档是什么

本文档定义 **Dev Agent** 和 **Test Agent** 两个 AI 协作完成 AutoVisionTest 项目的工作流。两个 Agent 独立运行（两个 Claude Code / Cursor 实例），通过 **Git + 共享文件** 通信，**不直接对话**。人类只在明确的升级点介入。

**读者**：Dev Agent、Test Agent、以及负责启动两者的人类。

**非目标**：本文档不重复产品/任务文档内容，只定义"两个 Agent 怎么合作"。

---

## 1. 核心原则

| 原则 | 含义 |
|------|------|
| **任务原子** | 一次一个任务，不跨任务批量操作 |
| **契约至上** | `task_document.md` 的"交付物"和"验收 checklist" 是不可谈判的 SSOT（Single Source of Truth） |
| **职责分离** | Dev 写生产代码，Test 写验收代码。两者不互相"帮忙"越界 |
| **异步协作** | Dev 和 Test 不要求同时在线。一方完成自己的部分写入共享文件，另一方下次启动时消费 |
| **可追溯** | 所有决定（领取、交付、验收、打回、升级）都落盘为文件 + Git commit，不留口头约定 |
| **人类托底** | 连续 3 轮来回不收敛 → 立即升级，不硬磕 |

---

## 2. 两个 Agent 的角色

### 2.1 Dev Agent

**唯一使命**：把一个任务从 `pending` 实现到"所有验收 checklist 通过"。

**权限**：
- ✅ 修改 `src/autovisiontest/**`
- ✅ 修改 `tests/**`（编写任务"测试项"中要求的测试）
- ✅ 修改 `scripts/**`、`config/**`（如果任务范围涉及）
- ✅ 创建新分支、commit、push
- ❌ 修改 `docs/product_document.md`
- ❌ 修改 `docs/task_document.md`（除非人类明确授权修订任务定义）
- ❌ 修改 `docs/dev_workflow.md`
- ❌ 合并 PR 到 `main`
- ❌ 跨越当前任务的"范围"白名单，改动无关文件
- ❌ 领取有未完成依赖的任务

**核心行为**：
1. 按任务"范围"列表动手，不越界
2. 严格实现任务的"交付物"（函数签名、文件路径、返回类型必须一致）
3. 写任务"测试项"中列出的 pytest 用例
4. 本地 `pytest` 必须全绿才交付
5. 交付物的文档字符串、类型注解必须齐备
6. 不得跳过任何"验收 checklist"条目

### 2.2 Test Agent

**唯一使命**：判定一个任务是否"真的完成"；不放行任何虚假完成。

**权限**：
- ✅ 只读 `src/**`（不改生产代码）
- ✅ 修改 `tests/**`（**补充** edge case、integration 测试，不删除 Dev 写的测试）
- ✅ 在 PR 上评论、approve、request-changes
- ✅ 合并 PR 到 `main`（在验收通过后）
- ✅ 升级给人类（写入 `.agent/escalations/`）
- ❌ 修改 `src/**` 生产代码（即使发现 bug，也要打回给 Dev）
- ❌ 修改任何 `docs/**`
- ❌ 删除或重写 Dev 写的测试
- ❌ 放行验收 checklist 未全部打钩的任务
- ❌ 跳过里程碑验收

**核心行为**：
1. 逐条对照任务"验收 checklist" 独立验证（不信 Dev 的口头声明）
2. 重新执行 `pytest`，不依赖 Dev 的 CI 结果
3. 检查交付物清单完整性（每个文件路径、每个函数签名都要存在）
4. 检查越界修改（`git diff main..task-branch -- $files_outside_scope`）
5. 补充被 Dev 漏写的 edge case 测试
6. 检查代码质量（命名、结构、是否违反产品文档的硬约束）
7. 阶段结束时跑"阶段里程碑验收"

### 2.3 角色不重叠矩阵

| 事项 | Dev | Test |
|------|-----|------|
| 写 `src/` 生产代码 | ✅ 唯一 | ❌ |
| 写任务要求的基础单元测试 | ✅ 主责 | ❌ |
| 补充 edge case / integration 测试 | 可选 | ✅ 主责 |
| 修代码 bug | ✅ 唯一 | ❌ |
| 修自己补充的测试 | ❌ | ✅ |
| 决定"这个任务过了没" | ❌ | ✅ 唯一 |
| 合并到 main | ❌ | ✅ 唯一 |
| 触发人类介入 | ✅ 可以 | ✅ 可以 |

---

## 3. 工作流总览

### 3.1 任务状态机

```
              ┌─────────┐
              │ pending │ (task_document.md 未被领取)
              └────┬────┘
                   │ Dev 领取
                   ▼
            ┌─────────────┐
            │ in_progress │ (Dev 正在实现)
            └──────┬──────┘
                   │ Dev 完成,写 handoff
                   ▼
            ┌─────────────┐      review_requested_changes (≤ 3 轮)
            │  review     │◄─────────────────────────┐
            └──────┬──────┘                          │
                   │                                 │
          ┌────────┼────────┐                       │
          │        │        │                       │
   approve│        │escalate│                       │
          ▼        ▼        ▼                       │
     ┌─────┐  ┌─────────┐  ┌────────┐              │
     │ done│  │escalated│  │rejected├──────────────┘
     └─────┘  └─────────┘  └────────┘
```

### 3.2 每个任务的生命周期

```
Dev                                         Test
 │                                           │
 │ 1. 从 task_document.md 选下一个无依赖阻塞的任务
 │ 2. 创建分支 task/T-X.Y-<slug>
 │ 3. 写入 .agent/state/current_task.json
 │ 4. 实现代码 + 测试
 │ 5. pytest 本地全绿
 │ 6. 写 .agent/handoffs/T-X.Y.md
 │ 7. git push + gh pr create
 │ 8. 在 handoff 里写明 "ready_for_review"
 │ ───────────────────────────────────────►  │
 │                                           │ 9. 发现 handoff
 │                                           │ 10. 拉分支
 │                                           │ 11. 对照 checklist 验收
 │                                           │ 12. 重跑 pytest
 │                                           │ 13. 审代码和越界检查
 │                                           │ 14. (可选) 补测试
 │                                           │ 15. 写 .agent/reviews/T-X.Y.md
 │                                           │
 │                                           │ 若通过:
 │                                           │   16a. gh pr merge --squash
 │                                           │   17a. 更新 .agent/state/task_status.jsonl
 │                                           │   → 任务结束
 │                                           │
 │  若不通过:                                 │   16b. request_changes + 具体问题清单
 │                                           │ ◄─────
 │ 17. Dev 读 review                         │
 │ 18. 修复,push                             │
 │ 19. 更新 handoff "iteration: 2"           │
 │ ───────────────────────────────────────►  │ 回到 11
 │                                           │
 │  (最多 3 轮,超过 → escalate 到人类)         │
```

---

## 4. 共享状态与目录约定

### 4.1 `.agent/` 目录结构

```
.agent/
├── state/
│   ├── current_task.json          # Dev 正在做什么 (单条记录)
│   └── task_status.jsonl          # 所有任务状态历史 (append-only)
├── handoffs/
│   └── T-X.Y.md                   # Dev → Test 的交接文件
├── reviews/
│   └── T-X.Y.md                   # Test → Dev 的审查结果
├── escalations/
│   └── T-X.Y-<timestamp>.md       # 升级给人类的事项
└── locks/
    └── dispatcher.lock            # 领任务时的互斥锁 (见 §5.1)
```

**Git 追踪策略**：
- `.agent/handoffs/`, `.agent/reviews/`, `.agent/escalations/`, `.agent/state/task_status.jsonl` → **提交到 Git**（决策历史不能丢）
- `.agent/state/current_task.json`, `.agent/locks/` → **不提交**（短生命周期状态）

在 `.gitignore` 中添加：
```
.agent/locks/
.agent/state/current_task.json
```

### 4.2 文件格式

见 §6 详细规范。

---

## 5. Dev Agent 工作流

### 5.1 领取任务

**启动提示（由人类给出）**：
> "你是 Dev Agent。阅读 `docs/dev_workflow.md` 和 `docs/task_document.md`。按流程领取下一个任务并实现。"

**步骤**：

1. **加锁**（防止两个 Dev 实例同时起）
   - 检查 `.agent/locks/dispatcher.lock` 是否存在
   - 若存在且 mtime < 10 分钟前 → 等待或退出
   - 若不存在或过期 → 写入当前时间戳和 agent 标识

2. **扫描可用任务**
   - 读取 `docs/task_document.md` 的任务列表
   - 读取 `.agent/state/task_status.jsonl` 确定已完成/进行中的任务
   - 过滤出：`status == pending` 且 `所有依赖 ∈ done`
   - 按任务 ID 升序取第一个

3. **写入状态**
   - `.agent/state/current_task.json`：
     ```json
     {
       "task_id": "T B.3",
       "title": "鼠标控制原语",
       "branch": "task/tb3-mouse-primitives",
       "agent": "dev",
       "started_at": "2026-04-18T10:00:00Z",
       "iteration": 1
     }
     ```
   - `.agent/state/task_status.jsonl` 追加一行：
     ```json
     {"task_id": "T B.3", "status": "in_progress", "at": "2026-04-18T10:00:00Z"}
     ```

4. **Git 准备**
   ```bash
   git fetch origin
   git checkout main
   git pull
   git checkout -b task/tb3-mouse-primitives
   ```

5. **释放锁**

### 5.2 实现任务

**硬约束**：

- 只修改任务"范围"列表中明确列出的文件；如需修改其他文件，**立即停止并升级**（§8.1）
- 每个交付函数必须有类型注解和至少一行 docstring
- 每实现一个交付物，立即写对应测试；不攒到最后
- 每次 commit message 格式：`T B.3: <简短描述>`；第一个 commit 可以 `T B.3: scaffold`
- commit 粒度建议：scaffold / implementation / tests / polish，不要一个巨型 commit

**自测循环**：

```bash
pytest tests/unit/control/test_mouse.py -v      # 本任务相关测试
pytest                                           # 全部测试（不允许让别的任务测试变红）
mypy src/autovisiontest/control/mouse.py       # 若项目启用 mypy
ruff check src/autovisiontest/control/mouse.py  # 若项目启用 ruff
```

**所有检查必须全绿才能进入交付。**

### 5.3 交付

1. **写 handoff 文件** `.agent/handoffs/T-B.3.md`（格式见 §6.1）

2. **Push**
   ```bash
   git push -u origin task/tb3-mouse-primitives
   ```

3. **创建 PR**
   ```bash
   gh pr create \
     --title "T B.3: 鼠标控制原语" \
     --body "$(cat .agent/handoffs/T-B.3.md)" \
     --base main
   ```

4. **更新状态**
   - `.agent/state/task_status.jsonl` 追加：
     ```json
     {"task_id": "T B.3", "status": "review", "at": "...", "pr": 42}
     ```
   - 清空 `.agent/state/current_task.json`

5. **退出会话**（等 Test 的 review）

### 5.4 处理 review 反馈（iteration 2+）

**启动提示**：
> "你是 Dev Agent。读 `.agent/reviews/T-B.3.md` 和原 handoff，按 review 的 required_changes 修复。"

**步骤**：

1. `git checkout task/tb3-mouse-primitives && git pull`
2. 读 `.agent/reviews/T-B.3.md` 中的 `required_changes`
3. 只修 required_changes 列出的项；不附带改其他
4. 每条 required_change 对应一个 commit，message 格式：`T B.3 iter-2: fix <issue>`
5. 本地 pytest 全绿
6. 更新 handoff 文件：
   - 添加 `## Iteration 2` 节，回应每条 required_change
   - 底部 `iteration: 2`
7. `git push`（同分支）
8. 在 PR 上 `gh pr comment <n> --body "Addressed in latest push. See updated handoff."`
9. 更新 task_status.jsonl

### 5.5 Dev 的红线（任一命中立即停止并升级）

- 任务依赖还没完成
- 任务"范围"列表不足以完成任务（真实需要改 scope 外的文件）
- 任务的"交付物"与产品文档冲突
- 第 3 轮迭代仍被 request_changes
- pytest 出现无法理解的环境问题（模型下载失败、API key 无效等）
- 发现产品文档矛盾或缺漏

---

## 6. Test Agent 工作流

### 6.1 触发与扫描

**启动提示**：
> "你是 Test Agent。读 `docs/dev_workflow.md`。扫 `.agent/handoffs/` 里 status=ready_for_review 的 handoff，按优先级 review。"

**步骤**：

1. 扫描 `.agent/handoffs/*.md`，读每个 frontmatter 的 `status`
2. 过滤 `status == ready_for_review` 的
3. 按任务 ID 升序处理（保证不跨越依赖链 review）

### 6.2 单任务 review 流程

对一个任务 `T B.3`：

1. **拉分支**
   ```bash
   git fetch origin
   git checkout task/tb3-mouse-primitives
   git pull
   ```

2. **对照 checklist** — 打开 `task_document.md` 的 T B.3，逐条验证"验收"列出的 checklist：
   - 每条必须**独立验证**。Dev 说"通过"不算通过
   - 例：`[ ] pytest tests/unit/control/test_mouse.py 全通过` → Test Agent 真的执行这条命令
   - 例：`[ ] 手动验证：...` → 若可自动化，自动化；若必须人类操作，记为"待人工"并在 review 里标出

3. **交付物完整性**
   - 任务"交付物"列的每个文件路径是否存在？
   - 每个导出函数签名是否与任务描述一致？（用 Python AST 或简单 grep 验证）

4. **范围检查**（越界）
   ```bash
   git diff main...HEAD --name-only > /tmp/changed.txt
   # 对比任务"范围"列表；超出的文件列为越界
   ```

5. **全局测试**
   ```bash
   pytest  # 全部测试；不允许此任务让其他测试变红
   ```

6. **代码 review**（简要，不深究风格）
   - 类型注解齐全
   - 无明显未处理异常路径
   - 无直接 `print()` 等遗留调试代码
   - 无硬编码绝对路径
   - 导出函数有 docstring
   - 没有引入产品文档非目标的内容（如偷偷调 UIA、偷偷绕过 DPI 归一化）

7. **补充测试**（可选）
   - 若发现 edge case 未覆盖且任务"测试项"本应覆盖 → 补一个测试
   - 若发现覆盖率不足且核心模块 < 80% → 补测试
   - 补充的测试也必须通过；若因补充测试发现 bug → request_changes

8. **判定**
   - 全过 → approve → merge
   - 不全过 → request_changes → 写 review 文件

### 6.3 Approve 流程

```bash
# 1. 写 review 文件（结果: approved）
vi .agent/reviews/T-B.3.md

# 2. 提交 review 文件和可能新增的测试
git add .agent/reviews/T-B.3.md tests/
git commit -m "T B.3 review: approved"
git push

# 3. gh PR approve + merge
gh pr review <n> --approve --body "Approved. See .agent/reviews/T-B.3.md"
gh pr merge <n> --squash --delete-branch

# 4. 更新 task_status.jsonl
echo '{"task_id": "T B.3", "status": "done", "at": "...", "approved_by": "test-agent"}' \
  >> .agent/state/task_status.jsonl

# 5. 提交状态更新
git checkout main && git pull
git add .agent/state/task_status.jsonl
git commit -m "T B.3: mark done"
git push
```

### 6.4 Request-changes 流程

```bash
# 1. 写 review 文件（结果: request_changes + required_changes 清单）
vi .agent/reviews/T-B.3.md

# 2. commit 到 task 分支
git add .agent/reviews/T-B.3.md
git commit -m "T B.3 review iter-1: request changes"
git push

# 3. PR 反馈
gh pr review <n> --request-changes --body "See .agent/reviews/T-B.3.md"

# 4. 更新 task_status.jsonl
echo '{"task_id": "T B.3", "status": "review_requested_changes", "at": "...", "iteration": 1}' \
  >> .agent/state/task_status.jsonl
```

### 6.5 阶段里程碑验收

每个阶段（如阶段 B）的所有任务都 done 后，Test 触发里程碑验收：

1. 读 `task_document.md` 的"阶段 X 里程碑验收"
2. 逐条验证
3. 通过 → 写 `.agent/reviews/milestone-B.md`（格式类似 review 文件），merge 到 main
4. 不通过 → 为缺失的项创建 followup 任务（与人类商量后追加到 task_document.md）

### 6.6 Test 的红线（立即停止并升级）

- 同一任务连续 3 轮 request_changes 仍不达标
- Dev 交付的代码通过了 checklist 但明显违反产品文档硬约束（如绕过 DPI 归一化）
- 发现产品文档与任务文档矛盾
- 测试基础设施问题（pytest 无法运行、环境依赖缺失）
- Dev 在 review 后 push 的改动**扩大了范围**（修了 review 没要求的内容）

---

## 7. 通信文件规范

### 7.1 handoff 文件（Dev → Test）

`.agent/handoffs/T-B.3.md`：

```markdown
---
task_id: T B.3
title: 鼠标控制原语
branch: task/tb3-mouse-primitives
pr: 42
status: ready_for_review
iteration: 1
dev_agent: claude-code-session-abc
created_at: 2026-04-18T10:00:00Z
updated_at: 2026-04-18T11:30:00Z
---

## 交付物清单

- [x] `src/autovisiontest/control/mouse.py` — 新建,导出 6 个函数
- [x] `tests/unit/control/test_mouse.py` — 新建,7 个测试用例
- [x] 所有 checklist 本地已自测通过

## 交付物细节

### `src/autovisiontest/control/mouse.py`

导出函数:
- `move(x: int, y: int, duration_ms: int = 100) -> None`
- `click(x: int, y: int, button: Literal["left", "right", "middle"] = "left") -> None`
- `double_click(x: int, y: int) -> None`
- `right_click(x: int, y: int) -> None`
- `drag(from_xy, to_xy, duration_ms: int = 300) -> None`
- `scroll(x: int, y: int, dy: int) -> None`

实现要点:
- 所有入口调用 `enable_dpi_awareness()`(幂等)
- `pyautogui.FAILSAFE = True` 保留

## 自测结果

```
$ pytest tests/unit/control/test_mouse.py -v
============ 7 passed in 0.8s ============

$ pytest
============ 42 passed in 4.2s ============
```

## 范围检查

改动文件列表(与任务"范围"白名单完全一致):
- src/autovisiontest/control/mouse.py   (新建)
- tests/unit/control/test_mouse.py      (新建)

## 已知限制 / 待 Test 关注

- drag 的 `duration_ms` 极小值(< 50ms) 在我的机器上不稳定,但 pyautogui 底层行为决定,已在 docstring 注明
- 未验证多显示器场景(任务明确 MVP 单屏)

## Checklist 自查

- [x] 文件创建并包含所有导出函数
- [x] 单元测试通过 (pytest tests/unit/control/test_mouse.py -v)
- [x] 手动验证已做: scripts/smoke_mouse.py 能点开记事本文件菜单(截图附 commit 123abc)
```

**字段规范**：

| 字段 | 值 |
|------|----|
| `status` | `ready_for_review` / `in_progress` / `iteration_2_ready` / `withdrawn` |
| `iteration` | 1 / 2 / 3 |

### 7.2 review 文件（Test → Dev）

`.agent/reviews/T-B.3.md`：

```markdown
---
task_id: T B.3
reviewer: test-agent
decision: request_changes      # approved | request_changes
iteration: 1
reviewed_at: 2026-04-18T12:00:00Z
---

## Summary

检出 2 个必须修复的问题,1 个建议(非阻塞)。

## Required Changes (必须修复)

### R1: `drag` 缺少 `ActionExecutionError` 抛出

任务要求所有控制函数失败时抛 `ActionExecutionError`,当前 `drag` 在 `from_xy == to_xy` 时会被 pyautogui 吞掉异常返回 None,未抛错。

- 文件: `src/autovisiontest/control/mouse.py`
- 行号: 48
- 期望: `if from_xy == to_xy: raise ActionExecutionError("drag from == to")`
- 对应 checklist 条目: 交付物中"失败时抛 ActionExecutionError"

### R2: 测试 `test_click_default_button_is_left` 未断言 button 参数

测试只验证了 pyautogui.click 被调用,没验证 button="left"。

- 文件: `tests/unit/control/test_mouse.py`
- 行号: 15
- 期望: `mock_click.assert_called_once_with(x=100, y=200, button="left")`

## Suggestions (建议)

### S1: 文档字符串可更具体

`move` 的 docstring "move the mouse" 过于简略,建议补充"duration_ms is the cursor animation duration, not a wait before moving"。

## Independent Verification

我跑的命令:
```
$ git checkout task/tb3-mouse-primitives
$ pytest tests/unit/control/test_mouse.py -v   # 7 passed,符合 handoff
$ pytest                                        # 42 passed
$ git diff main...HEAD --name-only
  src/autovisiontest/control/mouse.py
  tests/unit/control/test_mouse.py             # 范围合规
```

## Next Step

Dev Agent 请修复 R1 和 R2,S1 可选。修复后更新 handoff 进入 iteration 2。
```

### 7.3 escalation 文件（任一 Agent → 人类）

`.agent/escalations/T-B.3-20260418T130000Z.md`：

```markdown
---
task_id: T B.3
raised_by: dev-agent         # 或 test-agent
raised_at: 2026-04-18T13:00:00Z
iteration: 3
category: deadlock           # deadlock | scope_conflict | doc_conflict | env_issue | unclear_requirement
---

## Context

任务 T B.3 "鼠标控制原语" 进入第 3 轮迭代仍未通过 review。

## Iteration History

- Iteration 1: Dev 交付 → Test 打回 R1, R2
- Iteration 2: Dev 修复 R1, R2 → Test 打回 R3 (`drag` 在多显示器上坐标不正确)
- Iteration 3: Dev 修复 R3 → Test 打回 R4 (R3 的修复破坏了 R1 的行为)

## 问题根因分析(raiser 视角)

`drag` 在多显示器场景的期望行为在任务文档和产品文档里都不明确。
任务只说"物理像素主屏坐标",产品文档 §6.2 说"MVP 不支持多显示器"。
但 R3 要求处理多显示器的副屏拖拽,与产品文档冲突。

## 请求人类裁决

请选择:
- A) 维持"MVP 单屏"边界,撤销 R3。
- B) 扩大 MVP 范围到多屏,同步更新 task/product 文档和本任务范围。
- C) 其他方案。

## 当前状态

- 分支: task/tb3-mouse-primitives
- PR: #42
- 分支相对 main: 5 commits ahead
- 任务暂停(两个 Agent 都停止工作,等待裁决)
```

### 7.4 task_status.jsonl

Append-only。每行一个事件：

```json
{"task_id": "T B.3", "status": "in_progress", "at": "2026-04-18T10:00:00Z", "agent": "dev"}
{"task_id": "T B.3", "status": "review", "at": "2026-04-18T11:30:00Z", "pr": 42, "iteration": 1}
{"task_id": "T B.3", "status": "review_requested_changes", "at": "2026-04-18T12:00:00Z", "iteration": 1}
{"task_id": "T B.3", "status": "in_progress", "at": "2026-04-18T12:10:00Z", "iteration": 2}
{"task_id": "T B.3", "status": "review", "at": "2026-04-18T13:00:00Z", "iteration": 2}
{"task_id": "T B.3", "status": "done", "at": "2026-04-18T13:45:00Z", "approved_by": "test-agent"}
```

状态值：`in_progress` / `review` / `review_requested_changes` / `done` / `escalated` / `rejected`。

---

## 8. 升级与人类介入

### 8.1 何时升级

| Trigger | 谁升级 | 处理时效 |
|---------|--------|---------|
| Iteration == 3 仍被 request_changes | Test | 同步阻塞,立即升级 |
| 任务范围不足以完成任务 | Dev | 同步阻塞 |
| 发现产品/任务文档矛盾或空白 | 任一 | 同步阻塞 |
| 依赖的任务未完成却没标 pending | 任一 | 不阻塞,继续领下一个 |
| 环境问题(模型下载、API 限流) | 任一 | 先尝试 30 分钟自救,仍不行则升级 |
| 对抗性:Test 总是打回 / Dev 总是绕过 | 任一 | 立即升级 |

### 8.2 升级流程

1. 触发方写 `.agent/escalations/T-X.Y-<timestamp>.md`
2. commit + push
3. 所有 Agent 停止触碰该任务（task_status 追加 `escalated`）
4. 创建 GitHub issue 或在 PR 上 @人类
5. **人类介入后**：
   - 人类可改 `task_document.md` / `product_document.md`
   - 人类在 escalation 文件底部写 resolution
   - 人类决定是重启哪个 Agent 从哪步继续
   - task_status 追加 `resolved`

### 8.3 人类不处理的事

人类**不**应该被用来：
- 拆解任务细节（应该 Agent 自己读 task_document 解决）
- 决定代码风格（交给 ruff / formatter）
- 检查 pytest 是否通过（Agent 自己跑）
- 在两个 Agent 之间传话（它们靠文件通信）

---

## 9. 分支与 PR 约定

### 9.1 分支命名

```
task/<task-id-slug>-<short-title-slug>
```

例：
- `task/ta1-project-init`
- `task/tb3-mouse-primitives`
- `task/tf7-step-loop`

任务 ID 里的空格和点去掉。

### 9.2 PR 模板

PR body 直接使用 handoff 文件的内容（见 §5.3 step 3）。

### 9.3 Commit 信息

```
T B.3: <短描述>

<可选正文,解释非平凡的实现决定>
```

第 iter-2+ 的 commit：
```
T B.3 iter-2: fix R1 drag error handling
```

### 9.4 合并策略

**一律 squash merge**，保持 main 线性。

合并信息：
```
T B.3: 鼠标控制原语 (#42)
```

---

## 10. 并行执行规则

### 10.1 何时允许并行（多个 Dev Agent）

允许，但须遵守：

- 不同任务分支，不会同时触到同一文件
- 每个 Dev 独占 `.agent/locks/dispatcher.lock` 领取任务
- `.agent/state/current_task.json` 改为目录：`.agent/state/current/<agent_id>.json`
- Test Agent 可以有多个（并行 review 不同任务），但同一任务只能被一个 Test review

### 10.2 何时强制串行

- 跨阶段的依赖任务（如 F 阶段任务依赖 B/C/D 完成）
- 里程碑验收

### 10.3 并行冲突处理

- 两个 Dev 领到有隐含冲突的任务（task_document 依赖表未写全）：
  - 第二个检出冲突的 Dev 停下，写 escalation，让人类修复依赖表

---

## 11. 质量红线（两个 Agent 都要守）

任何时候命中以下任一项 → 立即停，写 escalation：

1. 产品文档 §1.3 的"非目标"被偷偷实现了（如引入 UIA）
2. 产品文档的"决策 D1-D12"被偷偷违反
3. 发现安全黑名单（§9）被绕过或弱化
4. 有 secret（API key、token）进入代码或 commit
5. 测试被标 `@pytest.mark.skip` 或 `xfail` 但没有书面理由和 issue
6. 向 `main` push（只能通过 PR merge）
7. `git push --force` 到 `main`

---

## 12. 冷启动：第一个任务怎么开

项目初始状态（当前）：只有 docs/ 三份文档，没有任何代码。

**步骤**：

1. 人类初始化 `.agent/` 目录结构（见 §4.1）

2. 人类在 `.agent/state/task_status.jsonl` 写一行：
   ```json
   {"event": "project_init", "at": "2026-04-18T00:00:00Z"}
   ```

3. 人类启动 **Dev Agent**（一个 Claude Code 会话）：
   > "你是 Dev Agent。先读 `docs/product_document.md` 和 `docs/task_document.md` 和 `docs/dev_workflow.md`。然后按 dev_workflow 的 §5 领取下一个任务（应为 T A.1）并实现。"

4. Dev Agent 完成 T A.1 → 创建 PR → 更新 handoff

5. 人类启动 **Test Agent**（另一个 Claude Code 会话）：
   > "你是 Test Agent。先读 `docs/dev_workflow.md`(其他两份自行按需读)。按 §6 扫描 handoff,review 等待的任务。"

6. Test Agent review T A.1 → approve 或 request_changes

7. 之后两个 Agent 可以各自按自己节奏运行。人类只在 escalation 来时介入。

---

## 13. 运行监控（可选）

人类可每日跑一个简短脚本看进度：

```bash
# 看状态分布
cat .agent/state/task_status.jsonl | jq -r '.status' | sort | uniq -c

# 看当前有谁在做什么
ls .agent/state/current/
cat .agent/state/current/*.json

# 看未解决的 escalation
ls .agent/escalations/

# 看 main 上已完成的任务
git log --oneline main | grep -E '^[a-f0-9]+ T [A-J]\.[0-9]+:' | wc -l
```

项目 MVP 共 56 个任务。正常节奏下（假设人类可用于 escalation），一个 Dev + 一个 Test 预计 3-6 周跑完。

---

## 14. 常见陷阱

| 陷阱 | 解法 |
|------|------|
| Dev 想"顺便"重构邻近代码 | 禁止。写 `.agent/escalations/refactor-suggestion-<topic>.md` 等人类裁决 |
| Test 发现 bug 手痒想修 | 禁止。一律 request_changes 由 Dev 修 |
| Dev 第 3 轮濒临超限，想"再塞一版" | 停下,升级。不要拖延升级时机 |
| Test 验收时跑 pytest 失败但"看起来是环境问题" | 必须排查到根因或升级,不能放行 |
| 两个 Agent 偷偷直接改 docs | 红线,立即升级,人类回滚 |
| 任务范围其实需要 5 个文件但只列了 3 个 | Dev 升级,人类改任务文档,**不要**自行扩大范围 |
| 任务 checklist 的"手动验证"项 | 截图+文字记录写进 handoff,Test 接受这些作为证据 |

---

## 15. 文档版本与修订

- v1.0（2026-04-18）：初版
- v1.1（2026-04-18）：新增 §16 GitHub 使用规范
- 本文档与产品/任务文档同属"契约级"。修订需人类签字（commit 作者 = 人类）
- Agent 发现本文档与实际需求矛盾 → 走 escalation,不得自行修改

---

## 16. GitHub 使用规范

### 16.1 仓库与账号

| 项 | 值 |
|---|---|
| 仓库 URL | `https://github.com/xslkim/AutoAgent.git` |
| 可见性 | public |
| 默认分支 | `main`（已开 branch protection） |
| 人类维护者 | `xslkim`（仓库所有者） |
| Dev bot 账号 | `<DEV_BOT_USER>` — 已接受 collaborator 邀请 |
| Test bot 账号 | `<TEST_BOT_USER>` — 已接受 collaborator 邀请 |

**认证方式**：每个 bot 账号各持一个 Classic PAT（`ghp_...`），仅人类本地持有。**禁止**将 PAT 写入任何被 Git 追踪的文件。

### 16.2 两份独立 checkout（推荐）

两个 Agent 使用**各自独立的本地 working copy**，避免共用一份 checkout 时身份切换出错。

```
D:\
├── AutoAgent\            ← 人类维护目录(只改 docs,不领任务)
├── AutoAgent-dev\        ← Dev Agent 工作目录
└── AutoAgent-test\       ← Test Agent 工作目录
```

初始化命令（人类执行一次）：

```bash
# 在 E:\ 下
cd /e/

# Dev 工作副本
git clone https://github.com/xslkim/AutoAgent.git AutoAgent-dev
cd AutoAgent-dev
git config user.name "<DEV_BOT_USER>"
git config user.email "<dev_bot_email>"
cd ..

# Test 工作副本
git clone https://github.com/xslkim/AutoAgent.git AutoAgent-test

cd AutoAgent-test
git config user.name "<TEST_BOT_USER>"
git config user.email "<test_bot_email>"
cd ..
```

`.agent/` 目录**跨两份 checkout 共享决策历史**，靠 Git 同步（handoff/review 文件都 commit+push）。一方写入、另一方 `git pull` 即可看到。

### 16.3 PAT 存储（绝对不能进 Git）

人类在本机创建两个文件，**保存在仓库之外**：

```
C:\Users\xsl\.autovt\dev.env
  GH_TOKEN=ghp_<dev_bot_pat>
  GIT_AUTHOR_NAME=<DEV_BOT_USER>
  GIT_AUTHOR_EMAIL=<dev_bot_email>
  GIT_COMMITTER_NAME=<DEV_BOT_USER>
  GIT_COMMITTER_EMAIL=<dev_bot_email>

C:\Users\xsl\.autovt\test.env
  GH_TOKEN=ghp_<test_bot_pat>
  GIT_AUTHOR_NAME=<TEST_BOT_USER>
  GIT_AUTHOR_EMAIL=<test_bot_email>
  GIT_COMMITTER_NAME=<TEST_BOT_USER>
  GIT_COMMITTER_EMAIL=<test_bot_email>
```

`.autovt/` 目录**不在任何 git 仓库下**，永远不会被 commit。

建议同步为 Windows 系统环境变量或在 shell profile 里 source 对应 env 文件，按启动哪个 Agent 选对应的 env。

**PAT 的最小 scope**（Classic PAT）：`repo`（公开+私有仓库读写）。不要勾 `admin:*`、`delete_repo`、`workflow`（无 Actions 时不需要）。

### 16.4 启动 Agent 的标准方式

#### 启动 Dev Agent

人类在一个终端里：

```bash
# 1. 加载 Dev 身份
source /c/Users/xsl/.autovt/dev.env
export GH_TOKEN  # 确保 gh CLI 使用这个 token

# 2. 进入 Dev 工作目录
cd /e/AutoAgent-dev

# 3. 同步最新 main
git checkout main
git pull

# 4. 验证身份
gh auth status        # 应显示登录为 <DEV_BOT_USER>
git config user.name  # 应输出 <DEV_BOT_USER>

# 5. 在该终端启动 Claude Code
claude
```

Claude Code 启动后，人类在第一条消息中给出标准 Dev 启动 prompt（见 §12）。

#### 启动 Test Agent

**另一个终端**：

```bash
source /c/Users/xsl/.autovt/test.env
export GH_TOKEN

cd /e/AutoAgent-test
git checkout main
git pull

gh auth status        # 应显示登录为 <TEST_BOT_USER>
git config user.name  # 应输出 <TEST_BOT_USER>

claude
```

然后用 Test 启动 prompt（见 §12）。

**关键点**：两个终端的 `GH_TOKEN` 必须不同。Agent **不能**修改全局 `~/.gitconfig` 或 `~/.config/gh/` 中的认证——只使用环境变量和仓库级 `.git/config`。

### 16.5 分支与 PR 的 GitHub 层操作

#### Dev Agent 的标准命令序列

```bash
# 开始任务
git checkout main && git pull
git checkout -b task/tb3-mouse-primitives

# ... 编码 + 本地 pytest ...

git add src/autovisiontest/control/mouse.py tests/unit/control/test_mouse.py
git commit -m "T B.3: 鼠标控制原语"

# Push 到远程(需要 GH_TOKEN 生效)
git push -u origin task/tb3-mouse-primitives

# 创建 PR,正文使用 handoff 文件内容
gh pr create \
  --repo xslkim/AutoAgent \
  --base main \
  --head task/tb3-mouse-primitives \
  --title "T B.3: 鼠标控制原语" \
  --body-file .agent/handoffs/T-B.3.md

# 提交 handoff 和 task_status(在同一 task 分支上 commit)
git add .agent/handoffs/T-B.3.md .agent/state/task_status.jsonl
git commit -m "T B.3: handoff v1"
git push
```

#### Test Agent 的标准命令序列

```bash
# 同步最新(拿到 Dev 刚推的 handoff)
git checkout main && git pull

# 检出待 review 的分支
git fetch origin
git checkout task/tb3-mouse-primitives
git pull

# 执行验收(见 §6.2)
pytest
# ... 其他检查 ...

# 写 review 文件并 commit 到 task 分支
vi .agent/reviews/T-B.3.md
git add .agent/reviews/T-B.3.md
git commit -m "T B.3 review iter-1: approved"
git push

# --- 分支 A:通过 ---
gh pr review <PR_NUMBER> --approve \
  --body "See .agent/reviews/T-B.3.md"
gh pr merge <PR_NUMBER> --squash --delete-branch

# 更新 task_status 到 main
git checkout main && git pull
echo '{"task_id":"T B.3","status":"done","at":"...","approved_by":"test-agent"}' \
  >> .agent/state/task_status.jsonl
git add .agent/state/task_status.jsonl
git commit -m "T B.3: mark done"
git push

# --- 分支 B:打回 ---
gh pr review <PR_NUMBER> --request-changes \
  --body "See .agent/reviews/T-B.3.md"
# (不 merge,等 Dev iteration 2)
```

**查 PR 编号**：
```bash
gh pr list --repo xslkim/AutoAgent --state open --head task/tb3-mouse-primitives --json number -q '.[].number'
```

### 16.6 Branch Protection 与 Agent 的协同

`main` 分支保护（已由人类设置）应包含：

- ✅ Require a pull request before merging
- ✅ Require at least 1 approval
- ✅ Dismiss stale approvals when new commits are pushed（强烈建议）
- ⬜ Require review from Code Owners（不需要，MVP 无 CODEOWNERS）
- ⬜ Require status checks（MVP 暂无 CI；Phase 2 引入时再开）
- ✅ Do not allow bypassing the above settings, including administrators（防止任一 bot 绕过）

**产生的行为约束**：

- Dev bot push 到 `main` → **被 GitHub 拒绝**（符合预期，防错机制）
- Dev bot 对自己的 PR approve → **无效**（GitHub 禁止 PR 作者 approve 自己）
- Test bot 必须 approve 后才能 merge → 强制双人制

### 16.7 Issue 与 Escalation 的 GitHub 对应关系

本项目的 "escalation" 文件是**决策权威**，但同时在 GitHub 创建 issue 便于人类看到：

```bash
# 任一 bot 发起升级时
gh issue create \
  --repo xslkim/AutoAgent \
  --title "Escalation: T B.3 iteration 3 deadlock" \
  --body-file .agent/escalations/T-B.3-20260418T130000Z.md \
  --label "escalation,needs-human" \
  --assignee xslkim
```

人类解决后：
```bash
gh issue close <issue_number> --comment "Resolved per .agent/escalations/xxx.md resolution section"
```

Label `escalation` 和 `needs-human` 需要人类在仓库 Settings → Labels 预先创建。

### 16.8 .gitignore 必须包含

```gitignore
# secrets
*.env
.env
.autovt/

# agent runtime state (non-tracked parts)
.agent/locks/
.agent/state/current_task.json
.agent/state/current/

# python
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
.venv/

# runtime data
data/
```

人类需在 T A.1 执行前把这段加入仓库的 `.gitignore`（T A.1 任务会建立 .gitignore，但可能不包含这些——**见 §16.11 的人类前置动作**）。

### 16.9 安全红线（GitHub 层）

Agent 必须严守：

| # | 红线 | 处理 |
|---|------|------|
| G1 | 不得把 PAT / `ghp_...` 字符串写入任何被 Git 追踪的文件 | 立即 escalate |
| G2 | 不得在 commit message / PR body / issue 里贴任何 token | 立即 escalate |
| G3 | 不得 `git push --force` 到 `main` | 红线,升级 |
| G4 | 不得修改仓库的 Settings / branch protection / collaborators | 无权限,也禁止尝试 |
| G5 | 不得 `gh auth login` 重新认证（会污染全局 gh 配置） | 只用 `GH_TOKEN` 环境变量 |
| G6 | 不得触碰 `.github/workflows/`（除非人类发任务） | 越界,禁止 |
| G7 | 若 pytest 日志中意外出现 token 字符串 → 清理证据、escalate | 泄露应急见 §16.10 |

### 16.10 PAT 泄露应急

若任一 Agent 怀疑 PAT 可能已泄露（进入 commit、log、截图等）：

1. **立即停止所有 Agent 操作**，写 `.agent/escalations/pat-leak-<timestamp>.md`
2. 在 escalation 中标注怀疑泄露的对象（commit SHA、文件、行）
3. **人类动作**：
   - 立刻去 GitHub Settings → Developer settings → Tokens → 吊销被泄露的 PAT
   - 生成新 PAT，更新 `C:\Users\xsl\.autovt\*.env`
   - 若已 push 到 public 仓库：`git filter-repo` 或 `git filter-branch` 清除历史（但 token 已应吊销，不一定需要重写历史）
   - 在 GitHub audit log 检查该 token 是否在吊销前被第三方使用
4. 事后补救完成后在 escalation 文件加 resolution 节，重启 Agent

### 16.11 人类前置动作 checklist

在启动任何 Agent 前，人类需完成：

- [ ] 两个 bot 账号已创建并接受仓库 collaborator 邀请
- [ ] 两个 PAT 已生成（Classic, scope: `repo`），各自保存到 `.autovt/*.env`
- [ ] main 分支保护已开启（§16.6）
- [ ] 两份 checkout 目录已 clone（`AutoAgent-dev`, `AutoAgent-test`）
- [ ] 每份 checkout 的 `.git/config` 已设置对应 bot 的 user.name/user.email
- [ ] 仓库 Labels 已创建：`escalation`、`needs-human`
- [ ] `.gitignore` 已包含 §16.8 条目
- [ ] `.agent/` 目录结构已初始化（§12）
- [ ] 本地验证：在 dev 终端 `gh auth status` 显示 `<DEV_BOT_USER>`；test 终端显示 `<TEST_BOT_USER>`
- [ ] 本地验证：各自终端 `git push`（空 commit 试 push 一个 test 分支再删除）可成功

全部打钩后，按 §12 冷启动流程启动 Dev Agent。

### 16.12 常见 GitHub 相关错误与排查

| 现象 | 原因 | 解法 |
|------|------|------|
| `git push` 提示 401 Unauthorized | `GH_TOKEN` 未 export 或过期 | `source .autovt/<role>.env && export GH_TOKEN` |
| `git push` 提示 403 protected branch | Agent 误对 `main` 直接 push | 切回 task 分支,走 PR |
| `gh pr merge` 提示 "Pull request is not mergeable" | review 未通过或有冲突 | Test 先 approve;Dev 先 rebase |
| `gh pr review --approve` 提示 422 | 同一账号不能 approve 自己的 PR | 确认当前身份是 Test,不是 Dev |
| PR 作者显示为 `xslkim` 而非 bot | Agent 启动时未切换身份 | 检查 `git config user.name` 和 `GH_TOKEN` |
| push 成功但 PR commit author 是 "unknown" | 未设置 `user.email` | `git config user.email <bot_email>` |

---

*流程文档结束。两位 Agent 请严格遵守。有疑问走 escalation,不要猜。*
