# 99 - 任务清单（Tasks）索引

> 所有任务由 AI Agent（Claude Code background mode）执行，规则见 [07-agent-operations.md](07-agent-operations.md)。
> 每个任务 = 1 个 PR。任务之间有 `depends_on` 关系，agent 按拓扑顺序执行。

## 一、文档使用说明

### 任务字段

每个任务用 YAML 描述，字段含义：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✅ | 简短标题（PR title 用） |
| `phase` | int | ✅ | 0 / 1 / 2 / 3 / 4 |
| `engine` | enum | ✅ | `none` / `unity` / `unreal` / `godot` / `all` |
| `depends_on` | list | ✅ | 必须先完成的 task ID 列表 |
| `goal` | string | ✅ | 一句话目标 |
| `output` | list | ✅ | 要创建/修改的文件路径 + 简述 |
| `verification` | list | ✅ | 完成验收方式（unit/e2e/acceptance） |
| `mode` | enum | ✅ | `manual` / `auto-with-review` / `auto-merge-safe` |
| `risk` | enum | ✅ | `low` / `medium` / `high` |
| `max_iterations` | int | ⬜ | 默认见 [07 §2.1](07-agent-operations.md#21-单任务最大迭代次数) |
| `path_exception` | list | ⬜ | 突破路径白名单的明确豁免（[07 §3.3](07-agent-operations.md#33-例外申请流程)） |
| `negative_test` | bool | ⬜ | 故意破坏 / 违规验证类任务。CI fail 是预期 verification |
| `sandbox_only` | bool | ⬜ | 任务 commit 推到独立 sandbox repo |

### 任务状态

- `pending`：未开始
- `in-progress`：AI agent 正在执行
- `pr-open`：已开 PR 等 review
- `merged`：已合并
- `blocked`：依赖未完成 / 等人工干预
- `anchor`：占位任务，待该 phase 启动前细化

状态字段不在 YAML 里手动维护，由 agent + GitHub status check 自动更新（写在 PR body 里，详见 07）。

## 二、任务总表

| Phase | 任务数 | 产出 |
|---|---|---|
| Phase 0 | 25 | 协议 schema + 三引擎 PoC + CI gate + 故意破坏验证 + orchestration scaffolding |
| Phase 1 | 35 | Unity adapter 完整 + MCP server + 视觉回归 + login MVP |
| Phase 2 | 12 (anchor) | UE adapter 完整 + 跨引擎 MVP 一致 |
| Phase 3 | 10 (anchor) | Godot adapter 完整 + 三引擎一致 |
| Phase 4 | 11 (anchor) | OS 输入 / LPIPS / 性能优化 / v1.0 release |
| **合计** | **93** | |

## 三、分 Phase 任务文件

| Phase | 文件 |
|---|---|
| Phase 0 | [tasks-phase0.md](tasks-phase0.md) |
| Phase 1 | [tasks-phase1.md](tasks-phase1.md) |
| Phase 2 | [tasks-phase2.md](tasks-phase2.md) |
| Phase 3 | [tasks-phase3.md](tasks-phase3.md) |
| Phase 4 | [tasks-phase4.md](tasks-phase4.md) |

## 四、Go/No-Go Gates 汇总

> 每个 phase 出口必须人工 review 全部 gate 通过才能进下个 phase。详见各 phase 文件末尾。

### Phase 0 出口 (TASK-0023 验证)
1. ☐ 三引擎 dump UI 树 parent/children 正确
2. ☐ Unity / Godot 在 PR runner 上 take_screenshot 拿到非黑屏
3. ☐ Self-hosted UE runner online + nightly 通过
4. ☐ 防护 0.1 + 0.2 能拦下故意破坏
5. ☐ Subprotocol 握手在三引擎都正确返回 `autoagent.v1`
6. ☐ `negotiate_version` JSON-RPC 握手符合规范
7. ☐ Orchestration scaffolding 跑通 1 个 echo 任务
8. ☐ 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human
9. ☐ 故意 kill 掉一个 in_progress agent → 顶层 resume 时正确恢复
10. ☐ 写 stop_signal → 顶层正确停机

### Phase 1 出口 (TASK-0135 验证)
1. ☐ AI Agent 完整 autonomous loop 跑通 login MVP
2. ☐ 防护 0.2 拦下 AI 在 .cs 写 visual 字段
3. ☐ 防护 0.1 拦下 AI 改 .unity 文件
4. ☐ 防护 0.3 dump 前后 visual diff 拦下故意写入
5. ☐ SSIM 视觉回归通过 login + welcome
6. ☐ 全程无人工敲键盘（除 review/approve PR）
7. ☐ AI 单任务平均迭代数 < 3
8. ☐ Cost tracking 正常工作

### Phase 2 出口 (TASK-0211 验证)
1. ☐ login MVP 跨 Unity / UE 一致（同一份 task DSL）
2. ☐ 5 道防护在 UE 全部生效
3. ☐ Self-hosted runner 稳定（连续 7 天 nightly 无超时 / OOM）
4. ☐ UE shipping build 验证 adapter 不包含到二进制

### Phase 3 出口 (TASK-0309 验证)
1. ☐ 三引擎完成 login MVP，同任务 DSL 行为一致
2. ☐ 三引擎视觉回归通过
3. ☐ Godot release export 反射 self-check 通过
4. ☐ 5 道防护在 Godot 全部生效

### Phase 4 出口 (TASK-0408 / TASK-0409)
1. ☐ OS 输入双轨可用（三平台）
2. ☐ LPIPS 子进程化 + 内存隔离生效
3. ☐ 大场景（1000+ 节点）性能达标
4. ☐ v1.0 changelog + migration guide 完成
5. ☐ 文档与实际实现 sync 完成

## 五、修订历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-05-10 | 0.1 | 初版（Phase 0/1 详写，Phase 2-4 anchor） |
| 2026-05-10 | 0.2 | Phase 0 加 5 个 orchestration task (TASK-0018~0022) |
| 2026-05-12 | 0.3 | 按 Phase 拆分为独立文件；TASK-0115 移至 Phase 4 |
