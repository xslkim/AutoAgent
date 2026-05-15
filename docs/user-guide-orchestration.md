# user-guide-orchestration.md — 用户日常操作指南

> 给项目维护者看的"怎么启动自动化、怎么读汇报、怎么裁决、怎么停机"。
> 顶层 Claude 怎么工作的细节见 [docs/orchestrator-prompt.md](orchestrator-prompt.md)
> 和 [docs/09-orchestration.md](09-orchestration.md)。

## 一、第一次准备（一次性，5 分钟）

### 1.1 创建 `.env.agent`

```bash
cp .env.agent.example .env.agent
```

打开 `.env.agent` 填两个值：

```
AGENT_ANTHROPIC_KEY=sk-ant-...    # 一个独立账户，单独计费追踪
AGENT_GITHUB_TOKEN=ghp_...        # repo:write + pull-requests:write，只给本仓库
```

`.env.agent` 已在 `.gitignore` — 永远不会被 commit。

### 1.2 确认 state/ 已就位

```bash
ls state/
# 应该看到: queue/ ready/ in_progress/ awaiting_ci/ done/ failed/ needs_human/ blocked/ logs/ budget.json events.jsonl
```

不在？跑：

```bash
python scripts/orchestrator/status.py
```

会列缺什么。手工 `mkdir` 补齐即可。

### 1.3 Python 依赖

```bash
pip install pyyaml jsonschema referencing
pip install -e mcp-server   # 让 autoagent-mcp 命令可用（可选）
```

## 二、加任务

把任务 JSON 文件丢进 `state/queue/`：

```bash
cat > state/queue/TASK-0007.json <<'EOF'
{
  "id": "TASK-0007",
  "title": "Unity adapter PoC",
  "phase": 0,
  "engine": "unity",
  "depends_on": ["TASK-0001", "TASK-0008a"],
  "spec_path": "docs/tasks-phase0.md#task-0007",
  "goal": "Unity adapter 最小可行版",
  "verification": [
    "Unity Test Runner 通过",
    "wscat 握手成功"
  ],
  "mode": "auto-with-review",
  "risk": "medium",
  "retries": 0,
  "max_retries": 5,
  "max_duration_seconds": 3600
}
EOF
```

依赖项里写其他 task 的 id。`scripts/orchestrator/poll.py` 会自动算依赖。

## 三、启动 /loop

打开 Claude Code，新建一个会话，**先粘贴整篇 [orchestrator-prompt.md](orchestrator-prompt.md)**，再敲：

```
/loop 5m
```

5 分钟一次的 polling 循环开始了。也可以让 Claude 自己定步长：

```
/loop
```

之后第一轮就会输出"启动话术" + 状态摘要。

## 四、看汇报

每一轮 Claude 输出形如：

```
## Polling tick @ 2026-05-16 14:23 UTC

**正在跑** (1)：
- TASK-0007 Unity adapter PoC  [12 min, $0.34]

**本轮变化**：
- ✓ TASK-0001 Protocol schema → done [PR #12 merged]
- ⚠ TASK-0011 UE adapter PoC → needs_human
   原因：源码审计违规，agent 试图修改 .uasset 文件
   PR：https://github.com/xslkim/AutoAgent/pull/15
- ⊘ TASK-0012 UE fixture → blocked（依赖 TASK-0011）

**预算**：今日 $14.32 / $200
**下一轮**：300 秒后唤醒（in_progress 非空，等 agent 跑完）
```

图标速记：

| 图标 | 含义 |
|---|---|
| ✓ | 进入 done/ |
| ⚠ | 进入 needs_human/（你要裁决） |
| ⊘ | 进入 blocked/（等上游恢复） |
| ⟳ | 重试（回 ready/） |
| ⛔ | 进入 failed/（重试耗尽） |

## 五、做裁决

看到 ⚠ needs_human 时，直接在对话里用**自然语言**回复：

```
TASK-0011 我看了 PR，是误判，重新跑一遍。
```

```
TASK-0011 是真违规，标 failed。
```

```
0011 我手动改完 PR 了，标 done。
```

```
TASK-0011 先跳过。
```

```
把 0011 阻塞的下游全 cancel。
```

Claude 会识别意图，下一轮 polling 应用裁决（详见 [orchestrator-prompt.md §自然语言识别表](orchestrator-prompt.md)）。识别错了？再说一遍，纠正即可。

**多个 needs_human 同时存在**：一次说一个，或者一段说几个：

```
0011 重试，0013 跳过，0015 标 failed。
```

## 六、紧急停机

### 6.1 立刻停（推荐）

在另一个终端：

```bash
python scripts/orchestrator/stop.py --reason "需要中断手动调整"
```

或者直接在 Claude 对话里说"全部停了"。

`state/stop_signal` 会被写进去。当前在跑的 Python agent **不会被杀**（让它跑完），但不再 spawn 新任务。等 in_progress/ 自然清空，Claude 输出"全部完成 / 已停机"后 /loop 自动退出。

### 6.2 恢复

```bash
python scripts/orchestrator/resume.py
```

或在 Claude 里 `/loop 5m` 重新启动。

## 七、典型日常操作

### 7.1 早上看看

```bash
python scripts/orchestrator/status.py
```

一眼看完：哪些 done、哪些 needs_human、预算还剩多少。

### 7.2 重启 Claude Code 会话

Claude Code 关掉再打开**不会丢状态**——状态全在 `state/` 文件里。重新打开后粘贴 [orchestrator-prompt.md](orchestrator-prompt.md) + `/loop 5m` 即可继续。

崩溃恢复细节见 [docs/09-orchestration.md §十](09-orchestration.md)。

### 7.3 看事件日志

```bash
tail -30 state/events.jsonl
```

每个状态转移、spawn、决策都会记一行。事后复盘用。

### 7.4 看任务详情

```bash
cat state/awaiting_ci/TASK-0007.json | python -m json.tool
```

或扫某个 bucket：

```bash
ls state/needs_human/
```

### 7.5 看 agent log（任务跑了什么）

```bash
ls state/logs/TASK-0007/
cat state/logs/TASK-0007/<latest>.log
```

Log 里 ANTHROPIC_API_KEY / GITHUB_TOKEN 等已被 scrub 替换为 `***REDACTED***`（见 `scripts/agent/run_task.py:scrub_secrets`）。

## 八、Troubleshooting

| 现象 | 通常原因 | 修法 |
|---|---|---|
| 顶层 Claude 不 ScheduleWakeup 了 | queue/in_progress/awaiting_ci 全空 → 正常完成 | 加新任务即可，再 `/loop` |
| `python scripts/orchestrator/poll.py` 报 `dependency cycle detected` | 你新加的 task 与已有 task 形成环 | 改 `depends_on` 字段或删任务 |
| agent 跑了但没开 PR | claude CLI 写代码失败 / git push 失败 | 看 `state/logs/<TASK>/<latest>.log`，按 `result.error` 排错 |
| `consecutive_path_violations` 触达上限自动停机 | AI 连续 3 次试图改禁止路径 | 看最近 3 个 needs_human 的 PR，决定 reject_failed 或修任务 spec |
| budget.json 显示 `usd` 一直 0 | Python agent 没把 claude CLI 的 cost 写回（Phase 0 stub） | 暂忽略，Phase 1 接 claude SDK 后才有真实 cost tracking |
| 看到一堆 worktree 残留 `<repo>.worktrees/TASK-XXXX/` | Agent 跑完没清理（needs_human / failed 故意保留 7 天） | 手工 `git worktree remove --force` 清；或等 [自动清理脚本](09-orchestration.md) |
| events.jsonl 越来越大 | 正常，归档暂未实现 | 手工 `mv state/events.jsonl state/events.<date>.jsonl` 启新一个 |

## 九、Phase 0 当前能力 / 不能力

✅ 能：
- 接受任务 JSON、算依赖、spawn Python agent、收集 result、移转状态
- 真 git worktree 隔离 + 自然语言裁决 + stop/resume
- 路径白名单（防护 0.1）+ 源码审计（防护 0.2）+ dump 前后 diff（防护 0.3）三个 CI 脚本就位
- 7 个 GitHub Actions workflow 注册（实际触发需推 PR）

⚠️ Phase 0 暂未实现，**Phase 1 之前需要人工**：
- 真实成本追踪（claude CLI 退出后的 token / cost 提取）
- 视觉回归（SSIM 比较 baseline）
- 三引擎 adapter（Unity / UE / Godot 跑 dump_tree + 4 动作）—— 那是 TASK-0007/0009/0011 的活

❌ Phase 1 才上：
- 并发（始终 MAX_CONCURRENT=1，docs/09 §4.3）
- 跨 session 状态恢复（基本能，但极端 crash 路径未完整覆盖）

## 十、相关文档

- [docs/09-orchestration.md](09-orchestration.md) — 调度架构（顶层 + Python agent + CI 三层、状态机、budget、决策识别完整规范）
- [docs/07-agent-operations.md](07-agent-operations.md) — agent 自治边界（迭代上限 / 路径白名单 / secret / git 禁令）
- [docs/orchestrator-prompt.md](orchestrator-prompt.md) — 给顶层 Claude 看的 prompt 模板
- `scripts/orchestrator/` — helper 脚本源码（poll/spawn/collect/stop/resume/status）
- `scripts/agent/run_task.py` — Python agent 单任务入口
