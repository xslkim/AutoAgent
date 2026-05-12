# 09 - Orchestration（自动化调度架构）

> AutoAgent 框架本身的"自动化开发流程"如何运作。
> 这一层是元层（meta），不是产品功能——它是用 AI Agent 来开发 AutoAgent 框架自身的方式。

---

## 一、架构总览

两层 agent 设计：

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: 顶层调度（用户 Claude Code 客户端会话 + /loop 模式）   │
│  ─ 读 state/ 目录                                                 │
│  ─ 算依赖图，找 ready 任务                                        │
│  ─ spawn Python agent                                             │
│  ─ 收集 result，转移状态                                          │
│  ─ 汇报给用户（fire-and-forget，不阻塞下一轮）                    │
│  ─ ScheduleWakeup 自唤醒                                          │
└──────────────────────────────────────────────────────────────────┘
              │ Bash spawn                ▲ 读 result.json
              ▼                           │
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: Python agent（scripts/agent/run_task.py，单任务）       │
│  ─ 读 task YAML                                                   │
│  ─ 创建 git worktree                                              │
│  ─ subprocess.Popen("claude -p ...", env=独立 API key)            │
│  ─ claude CLI 跑完 → 拿 stdout/exitcode                           │
│  ─ 检查产出（git diff / PR 创建 / 验证脚本）                      │
│  ─ 写 result.json                                                 │
│  ─ 退出（成功 / 失败 / needs_human）                              │
└──────────────────────────────────────────────────────────────────┘
              │ 通过 git push 触发
              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: GitHub Actions CI                                       │
│  ─ 路径白名单 / 源码审计 / 编译 / 单元测试 / e2e / 视觉回归       │
│  ─ 结果通过 PR check status 反映                                  │
└──────────────────────────────────────────────────────────────────┘
```

**关键约束**：
- 顶层 Claude **不写业务代码**，只调度。
- Python agent **只跑一个任务**，跑完即退出。
- 两层之间**只通过状态文件交互**，不共享内存、不开 socket。

---

## 二、状态文件目录结构

```
<REPO_ROOT>\state\         # Windows 示例: D:\AutoAgent\state\；Linux/macOS: /path/to/AutoAgent/state/
├─ queue\                  # 待执行任务（文件名 = TASK-NNNN.json）
├─ ready\                  # 依赖已满足，可立即 spawn 的任务
├─ in_progress\            # Python agent 正在跑（含 PID + 启动时间 + worktree 路径）
├─ awaiting_ci\            # Python agent 已退出，PR 已开，等 CI 结果
├─ done\                   # 已完成（含 PR URL + commit SHA + CI 状态）
├─ failed\                 # 永久失败（重试耗尽 / 全局停止）
├─ needs_human\            # 等用户裁决（路径违规 / 同错连续 3 次 / 其他）
├─ blocked\                # 被上游 needs_human/failed 任务阻塞的下游
├─ events.jsonl            # 全局事件日志（append-only，时间戳 + 事件类型）
├─ budget.json             # 预算状态（今日累计 $ / session 累计 $ / 任务计数）
└─ stop_signal             # 紧急停机文件（存在即全局停）
```

**状态转移图**：

```
         ┌──── queue ────┐
         │               │
         │ (deps done)   │ (deps failed/needs_human)
         ▼               ▼
       ready          blocked ◄────┐
         │               │         │
         │ (spawn)       │         │ (上游恢复)
         ▼               │         │
    in_progress          └─────────┘
         │
         │ (Python agent 退出 + PR 已开)
         ▼
    awaiting_ci
         │
   ┌─────┼─────┬──────────┐
   ▼     ▼     ▼          ▼
  done  failed retry   needs_human
                │         │
                └────►ready│
                           │ (用户裁决)
                           └────►ready / failed / done
```

**原子性保证**：状态转移 = `os.rename` 文件移动（Windows 同盘原子）。绝不"先删后写"。

---

## 三、任务文件 schema

`state/queue/TASK-NNNN.json`：

```json
{
  "id": "TASK-0007",
  "title": "Unity adapter PoC + unit tests",
  "phase": 0,
  "engine": "unity",
  "depends_on": ["TASK-0001", "TASK-0002"],
  "spec_path": "docs/tasks.md#task-0007",
  "mode": "auto-with-review",
  "effort_estimate": "5d",
  "risk": "medium",

  "created_at": "2026-05-10T14:23:00Z",
  "ready_at": null,
  "started_at": null,
  "finished_at": null,

  "retries": 0,
  "max_retries": 5,

  "spawn": {
    "pid": null,
    "worktree_path": null,
    "branch": null,
    "log_path": null
  },

  "result": null,

  "history": []
}
```

任务进入 `in_progress/` 时填 `spawn.pid` / `spawn.worktree_path` / `spawn.branch` / `started_at`。

完成后写 `result`：

```json
{
  "status": "success | failed | needs_human",
  "pr_url": "https://github.com/.../pull/42",
  "commit_sha": "abc123",
  "ci_status": "green | red | pending",
  "claude_session_id": "...",
  "tokens_used": { "input": 12000, "output": 3500 },
  "cost_usd": 0.42,
  "duration_seconds": 178,
  "error": null,
  "needs_human_reason": null,
  "agent_self_assessment": "Implemented WalkChildren recursion, all 12 unit tests pass, PR opened."
}
```

`history[]` 记录每次重试的 result 摘要（保留全部历史，方便事后复盘）。

### budget.json schema

`state/budget.json`（顶层 poll + Python agent 共用，原子写入用 temp file + `os.replace`）：

```json
{
  "today": "2026-05-12",
  "daily": {
    "cost_usd": 14.32,
    "task_count": 5,
    "pr_count": 5,
    "path_violations": 0
  },
  "session": {
    "started_at": "2026-05-12T09:00:00Z",
    "cost_usd": 14.32,
    "task_count": 5,
    "ci_triggers": 8
  },
  "global": {
    "consecutive_path_violations": 0,
    "consecutive_ci_failures": 0
  }
}
```

**更新规则**：
- `daily` 字段每次 CI 完成时累加（顶层 poll 第 6 步）；跨日自动归零（`today != now.date()` 时重置）
- `session` 字段每次 spawn agent 时累加；顶层重启时从 `events.jsonl` 重算
- `global.consecutive_path_violations`：连续 +1，任意成功归零；触达 3 → 写 `stop_signal`
- 原子写：先写 `.budget.tmp`，`os.replace` 到 `budget.json`（同盘原子操作）

**上限阈值（对应 [07 §2.2-2.3](07-agent-operations.md)）**：

| 字段 | 上限 | 触发行为 |
|---|---|---|
| `session.cost_usd` | ≥ $50 | session 停 |
| `daily.cost_usd` | ≥ $200 | 全局停（写 stop_signal） |
| `daily.task_count` | ≥ 50 | 全局停 |
| `session.task_count` | ≥ 20 | session 停 |
| `session.ci_triggers` | ≥ 50 | session 停 |
| `global.consecutive_path_violations` | ≥ 3 | 全局停 |

---

## 四、调度算法（依赖图）

### 4.1 Ready 集合计算

每轮 polling 时：

```python
def compute_ready():
    done_ids = set(os.listdir("state/done")) - {"."}
    failed_ids = set(os.listdir("state/failed"))
    needs_human_ids = set(os.listdir("state/needs_human"))
    blocked_ids = set(os.listdir("state/blocked"))

    for task_file in os.listdir("state/queue"):
        task = load(task_file)
        deps = task["depends_on"]

        # 上游有任何 failed/needs_human → 自己进 blocked
        if any(d in failed_ids | needs_human_ids for d in deps):
            move(task_file, "state/blocked")
            continue

        # 上游全 done → 进 ready
        if all(d in done_ids for d in deps):
            move(task_file, "state/ready")
```

### 4.2 Blocked 解除

每轮 polling 时也扫 `blocked/`：

```python
for task_file in os.listdir("state/blocked"):
    task = load(task_file)
    deps = task["depends_on"]
    # 所有阻塞源都已恢复（done） → 重新进 ready
    if all(d in done_ids for d in deps):
        move(task_file, "state/ready")
```

### 4.3 Spawn 调度

`ready/` 里的任务按 phase 升序、然后按 ID 升序，**严格串行执行**（MAX_CONCURRENT = 1）。

```python
MAX_CONCURRENT = 1  # 永久值，MVP 不放并发，验证完也不放（不需要）
running = len(os.listdir("state/in_progress"))
if running == 0 and ready_tasks:
    spawn_python_agent(ready_tasks[0])  # 一次只 spawn 一个
```

**为什么不并发**：
- 单机资源有限，三引擎各自有 CI 跑就够并行了（CI 在 GitHub 那边并发）
- 串行调试容易，状态文件无锁竞争
- tasks.md 里大部分任务有依赖串联，并发收益有限
- `awaiting_ci/` 里的任务**不算占用** spawn slot（它已经退出，只是等 CI），所以同时可能有多个 awaiting_ci 任务在等

### 4.4 关键不变量

- **任意时刻一个 task 只在一个目录里** —— 移动用 `os.rename`，绝不 copy
- **依赖图必须无环** —— 加载时拓扑排序失败 → 全局停 + 报错
- **下游 blocked 不会消耗 spawn slot** —— blocked 任务不在 ready 集合里
- **旁支独立任务永远能跑** —— 一个分支 needs_human 不影响其他分支

---

## 五、Failure routing

### 5.1 错误分类表

| 错误类别 | 来源 | 处理 |
|---|---|---|
| 编译错误 / 单元测试 fail / lint fail | claude CLI 退出码非 0，且能读到错误信息 | 自动重试 ≤5 次（task.max_retries） |
| 路径白名单违规（防护 0.1） | CI source-audit job fail | **不重试**，立即 needs_human |
| 源码审计违规（防护 0.2） | CI source-audit job fail | **不重试**，立即 needs_human |
| 视觉回归 fail | CI visual job fail | 自动重试 ≤2 次（更保守，因为可能是 baseline 问题） |
| API 超时 / 网络错误 | Python agent 抓 subprocess 异常 | 指数退避重试（30s/2min/10min），≤3 次 |
| Claude CLI 内部 OOM / panic | exitcode 137/139 | 重试 ≤2 次，再 fail 进 needs_human |
| 同一错误指纹连续 3 次 | history 里最近 3 次 result.error 相同 | needs_human |
| 单任务成本 > $5 | budget.json 单任务累计 | needs_human + 全局暂停（等用户裁决） |
| 单天总成本 > $200 | budget.json 单天累计 | 全局停（写 stop_signal） |
| 12h session 上限 | 顶层 /loop 启动时间 | 全局停 |
| 路径违规连续 3 次（跨任务） | events.jsonl 扫描 | 全局停 |
| Claude CLI 执行超时 | Python agent wait timeout | failed，重试 ≤2 次 |
| CI 等待超时 | 顶层 poll awaiting_ci 时检查 | failed（按引擎超时阈值，见 5.2） |

**错误指纹**：从 stderr 提取关键 substring（去除时间戳、随机 ID、绝对路径），SHA-1 截断。

### 5.2 CI 超时阈值（按引擎区分）

顶层在 awaiting_ci 状态下等待 PR check 完成。超时后视为 failed。

| Task 类型 | 超时阈值 | 理由 |
|---|---|---|
| 仅 source-audit job（无 engine 字段） | 3 min | 跑 path/regex 检查，应在秒级完成 |
| Unity PR（每 PR 跑） | 10 min | windows-latest 编译 + e2e ~5 min，留 2x 余量 |
| Godot PR（每 PR 跑） | 5 min | ubuntu-latest 编译 + Xvfb e2e ~2 min |
| UE PR lint（每 PR 跑） | 10 min | self-hosted lint，不编译 |
| UE nightly（仅 nightly） | 60 min | self-hosted clean build 可达 45 min |
| MCP server PR | 5 min | 纯 Python 测试 |

**判断方式**：从 task YAML 的 `engine` + `tags`（含 `nightly`）字段决定。任务无 engine 字段 → 走 source-audit 阈值（3 min）。

**超时后**：杀 PR check（`gh run cancel`），关 PR，状态 → failed，重试。

---

## 六、Worktree 隔离

### 6.1 命名约定

```
D:\AutoAgent.worktrees\
├─ TASK-0007\         # branch: agent/TASK-0007, path: <REPO_ROOT>.worktrees\TASK-0007
├─ TASK-0009\         # branch: agent/TASK-0009
└─ TASK-0011\         # branch: agent/TASK-0011
```

worktree 根目录在主 repo 外（`<REPO_ROOT>.worktrees\`），避免污染主 repo。在 Windows 上形如 `D:\AutoAgent.worktrees\`，Linux/macOS 上形如 `/home/user/AutoAgent.worktrees/`。

### 6.2 生命周期

```bash
# spawn 时
git worktree add ../<REPO_ROOT>.worktrees/TASK-0007 -b agent/TASK-0007 origin/main

# claude 在 worktree 里跑，提交，开 PR
cd ../<REPO_ROOT>.worktrees/TASK-0007
claude -p "<task prompt>"
git push -u origin agent/TASK-0007
gh pr create ...

# done 时（PR merged，CI green）
git worktree remove ../<REPO_ROOT>.worktrees/TASK-0007
git branch -D agent/TASK-0007  # 本地清理；远端分支 GitHub 自动清

# failed/needs_human 时
# 保留 worktree 7 天，方便人工调试
# state/in_progress/TASK-0007.json.deleted_at = T+7d
# 清理脚本每天扫一次
```

### 6.3 冲突避免

- 不同任务在不同 worktree，**绝不**在同一 worktree 跑两个任务。
- worktree 之间的修改通过 PR + main merge 串行化，避免直接互相影响。
- 同一 task 重试时**销毁旧 worktree + 新建 fresh worktree**（见 §10.2），不复用——避免 `git reset --hard` 越过 [07 §5.2](07-agent-operations.md) 的 git 禁令。

### 6.4 与 [07 git 禁令](07-agent-operations.md) 的边界

[07 §5.2](07-agent-operations.md) 禁止 AI agent 用 `git reset --hard` / `git push --force` / `git rebase` 等破坏性操作。**orchestrator（顶层调度脚本）也必须遵守这条**——因为 orchestrator 写出来后 agent 调用 orchestrator helper 就等于间接执行这些操作。

**重试 / 故障恢复的正确做法**：
- ✅ `git worktree remove --force ../<REPO_ROOT>.worktrees/TASK-XXXX` + `git worktree add` 新建（fresh checkout）
- ✅ `git branch -D agent/TASK-XXXX` 删旧分支 + 新建同名分支（在 fresh worktree 内）
- ❌ `git reset --hard origin/main` 重置已有 worktree
- ❌ `git push --force` 覆盖远端分支历史

唯一例外：本地未推送的 worktree 在**销毁前**清理工作区，可以 `git clean -fdx` + `git checkout .`（不属于 reset），目的是释放磁盘 / 避免锁文件残留。这条仍要写进 `scripts/orchestrator/lib/git_ops.py` 的白名单 + 单元测试。

---

## 七、API key 与 secret 边界

### 7.1 Secret 分类

| Secret | 谁能看到 | 存储位置 |
|---|---|---|
| `ANTHROPIC_API_KEY`（Python agent 专用） | Python agent 进程 env | `.env`（gitignore） |
| `ANTHROPIC_API_KEY`（顶层 Claude Code 用的） | 顶层会话 | OS keyring / 不进 `.env` |
| `GITHUB_TOKEN` | Python agent 进程 env（用于 gh CLI 开 PR） | `.env`（gitignore，最小权限：仓库读写 + PR 创建） |
| 生产环境 secret | **谁都不行**，根本不应该出现在 repo 里 | N/A |

### 7.2 隔离机制

```python
# scripts/agent/run_task.py
import os
from dotenv import load_dotenv

load_dotenv(".env.agent")  # 只加载 agent 专用 env，不污染父进程

env = {
    "ANTHROPIC_API_KEY": os.environ["AGENT_ANTHROPIC_KEY"],
    "GITHUB_TOKEN": os.environ["AGENT_GITHUB_TOKEN"],
    "PATH": os.environ["PATH"],  # 允许找到 claude / git / gh
    # 不传 HOME / USERPROFILE 之外的任何 env
}

subprocess.Popen(
    ["claude", "-p", prompt],
    env=env,  # ← 关键：清空父进程其他 env
    cwd=worktree_path,
    stdin=subprocess.PIPE,
    stdout=open(log_path, "w"),
)
```

### 7.3 .env.agent 模板

```bash
# .env.agent.example （commit 到 repo，含占位符）
AGENT_ANTHROPIC_KEY=sk-ant-...   # 独立账户独立计费
AGENT_GITHUB_TOKEN=ghp_...        # repo:write + pull-requests:write，仅本 repo（<REPO_ROOT>）
```

**严禁**：
- `.env.agent` 进 git（添加到 `.gitignore`）
- 任何 task prompt 里出现 secret 字符串
- agent log 里 echo `$ANTHROPIC_API_KEY`（log 重定向时主动 mask）

---

## 八、顶层 Claude polling 循环职责

每个 turn（被 ScheduleWakeup 唤醒后）做完整一轮：

```
1. 读 state/stop_signal → 存在则停
2. 读 state/budget.json → 超限则停 + 写 stop_signal
3. 处理用户裁决（如果用户上轮回复中包含裁决指令）:
     - 解析自然语言（见 §12.3）
     - 把 needs_human/TASK-NNNN.json 移到对应目录
4. 健康检查 in_progress/（Python agent 还在跑的）：
     - 对每个 PID：os.kill(pid, 0) 检查存活
     - 僵尸（PID 死了但 result.json 没写）→ 移回 ready/，retries++
     - 超时（started_at + max_claude_duration < now）→ 杀进程 + 移回 ready/
5. 收集 Python agent 已退出的：扫 in_progress/ 找有 result.json 的
     - result.status="awaiting_ci" → 移到 awaiting_ci/
     - result.status="failed" → 看 retries，<max 移回 ready/，>=max 移到 failed/
     - result.status="needs_human" → 移到 needs_human/
6. 检查 awaiting_ci/ 的 CI 状态：
     - 对每个：gh pr checks <pr_url> --json
     - all green → 移到 done/，更新 budget.json
     - any red → 按 §5.1 分类（路径违规 → needs_human / 其他 → 重试或 failed）
     - pending 且未超时（按 §5.2 引擎阈值） → 保持
     - pending 且超时 → 杀 CI run + 关 PR，移到 failed/，重试
7. 算依赖图：
     - queue/ → ready/ 或 blocked/
     - blocked/ → ready/（如果上游恢复）
8. spawn 新任务（如果 in_progress 为空）：
     - ready/ 取第一个，bash spawn python scripts/agent/run_task.py TASK-NNNN
     - 移到 in_progress/，记 PID
9. 汇报本轮变化（给用户看的文本，见 §12.2）
10. ScheduleWakeup：
     - 有 in_progress/ → 5 分钟后再来（agent 跑 claude 需要时间）
     - 仅有 awaiting_ci/ → 3 分钟后再来（CI 跑得快）
     - 全空 + queue 还有未 ready 的 → 30 分钟后再来
     - queue 全空 + in_progress 全空 + awaiting_ci 全空 → 报告"全部完成"，不再唤醒
```

**关键不变量**：
- 顶层每 turn 时间 < 1 分钟（不阻塞用户回复）
- 顶层不直接读源码、不写代码
- 所有汇报都不带"问题"——单向通知，用户想回复就回复

---

## 九、Python agent 单任务执行流程

`scripts/agent/run_task.py TASK-NNNN`：

```python
def main(task_id):
    task = load_task(task_id)
    state_path = f"state/in_progress/{task_id}.json"

    # 1. 创建 / 重用 worktree
    worktree = setup_worktree(task_id)

    # 2. 拼 prompt
    prompt = build_prompt(task)
    # = task spec from tasks.md + 相关上下文文件路径
    # + 强制约束："你只能修改路径白名单内的文件"
    # + 退出条件："完成后必须 git commit + git push + gh pr create"

    # 3. spawn claude CLI
    log_path = f"state/logs/{task_id}/{timestamp}.log"
    proc = subprocess.Popen(
        ["claude", "-p", "--permission-mode", "acceptEdits"],
        env=isolated_env(),
        cwd=worktree,
        stdin=subprocess.PIPE,
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
    )
    proc.stdin.write(prompt.encode("utf-8"))
    proc.stdin.close()

    # 4. 等待退出（含超时）
    try:
        exit_code = proc.wait(timeout=task.max_duration_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        write_result(task_id, status="failed", error="timeout")
        return

    # 5. 验证产出（不等 CI，CI 由顶层 poll）
    pr_url = extract_pr_url_from_log(log_path)
    commit_sha = git_rev_parse_head(worktree)

    # 6. 决定状态
    if exit_code != 0:
        # claude CLI 退出码非 0
        status = classify_failure(log_path)  # failed / needs_human
        write_result(task_id, status=status, exit_code=exit_code,
                     commit_sha=commit_sha, pr_url=pr_url, error=...)
        return

    if not pr_url:
        # claude 跑成功但没开 PR
        write_result(task_id, status="failed",
                     error="agent did not create PR")
        return

    # 7. 写 result.json，状态 = awaiting_ci，由顶层 poll CI
    write_result(task_id, status="awaiting_ci",
                 pr_url=pr_url, commit_sha=commit_sha,
                 tokens_used=..., cost_usd=...)
    # 退出。顶层 polling 会扫到 result.json 并把任务移到 awaiting_ci/
```

**Python agent 不等 CI 的好处**：
- agent 进程不长期占用（claude CLI 跑完就退）
- CI 等待逻辑集中在顶层，便于全局超时管理
- 顶层可以同时监控多个 awaiting_ci 任务的 CI 状态（即使 spawn 串行）

### 9.1 Prompt 模板（精简示例）

```
你是 AutoAgent 框架开发任务的执行 agent。当前任务：

# TASK-0007: Unity adapter PoC + unit tests

[完整任务规格从 docs/tasks.md 嵌入]

## 你必须遵守的约束

1. 你工作在 git worktree {{worktree_path}}（branch: agent/TASK-0007）
2. 你只能修改以下路径：
   - adapters/unity/Runtime/**
   - mcp-server/src/**
   - fixtures/unity-test-project/Scripts/**
3. 你**禁止**修改：
   - 任何 .unity / .uasset / .tscn / Sprites/ / baselines/ / .github/
   - 任何 ProjectSettings/
4. 完成后必须执行：
   - git add <修改的文件>
   - git commit -m "<符合规范的消息>"
   - git push -u origin agent/TASK-0007
   - gh pr create --title "..." --body "..."
5. 失败时**不要**强行清理或 reset，留下现场让人工调试。

## 验证标准

[从任务 YAML 的 verification 字段嵌入]

## 完成后

直接退出。不要继续等待 CI 结果——那由顶层调度处理。
```

### 9.2 不支持的事

- agent **不能**唤起子 agent（嵌套 spawn）
- agent **不能**修改 state/ 目录（顶层独占）
- agent **不能**直接 merge PR（顶层判断 CI 后由人或自动 merge bot 做）
- agent **不能**读其他 task 的 worktree（隔离边界）

---

## 十、Resume 与崩溃恢复

### 10.1 顶层会话重启

用户关掉 Claude Code 再打开，第一轮 polling：

```
1. 读 state/in_progress/ 所有任务
   - 检查 spawn.pid 是否还活着（os.kill(pid, 0)）
   - 死了：
     - 有 result.json → 按 result.status 处理（awaiting_ci/failed/needs_human）
     - 无 result.json → 移回 ready/，retries++，记 events.jsonl
   - 活着：保持 in_progress/，下一轮再看
2. 读 state/awaiting_ci/ 所有任务
   - 顶层重启不影响 awaiting_ci 任务（CI 在 GitHub 那边继续跑）
   - 直接进入正常 poll 流程查 PR 状态
```

### 10.2 Python agent 自身崩溃

agent 在 worktree 里 `git commit` 后但 `gh pr create` 前崩溃：
- worktree 有未推的 commit → 顶层重试时检测到
- **当前实现**（与 [07 §5.2](07-agent-operations.md) git 禁令一致）：
  1. `git worktree remove --force ../<REPO_ROOT>.worktrees/TASK-XXXX`（销毁旧 worktree，未推 commit 一并丢弃）
  2. `git branch -D agent/TASK-XXXX`（删旧分支）
  3. `git worktree add` + 新建同名分支（fresh checkout）
  4. 在新 worktree 里重跑 agent
- **不**用 `git reset --hard`——orchestrator 必须遵守 agent contract，所有破坏性操作通过销毁 / 重建 worktree 隔离

### 10.3 GitHub Actions CI 自身故障

- CI 卡住 > 10min → Python agent 超时退出，status=failed
- CI 因 GitHub 故障 fail → 顶层不区分（视为普通 ci red），由 retry 机制处理
- CI quota 耗尽 → 全局停（写 stop_signal）

---

## 十一、停机条件

### 11.1 紧急停机

```bash
# 用户在另一个终端写 stop signal（路径相对 repo root）
# Windows PowerShell:  ni <REPO_ROOT>\state\stop_signal -Force
# Linux/macOS:         touch <REPO_ROOT>/state/stop_signal

# 或 CLI helper
python scripts/orchestrator/stop.py
```

stop_signal 存在时：
- 顶层每轮 polling 第一步检查，存在即停（不 spawn 新任务，不杀正在跑的）
- 等 in_progress/ 全部自然结束后退出 /loop

### 11.2 自动停机

| 触发 | 行为 |
|---|---|
| 单天总成本 > $200 | 写 stop_signal + 通知用户 |
| 单 session > 12h | 写 stop_signal |
| 路径违规连续 3 次（跨任务） | 写 stop_signal + needs_human |
| 全局错误率 > 50%（最近 10 个任务） | 写 stop_signal |
| stop_signal 文件存在 | （已停机状态，直接 exit /loop） |

### 11.3 恢复

```bash
# Windows: del <REPO_ROOT>\state\stop_signal
# Linux/macOS: rm <REPO_ROOT>/state/stop_signal
# 用户在 Claude Code 重新启动 /loop
```

---

## 十二、监控与可观测性

### 12.1 events.jsonl 事件类型

```jsonl
{"ts": "2026-05-10T14:23:00Z", "type": "task_spawned", "task_id": "TASK-0007", "pid": 12345}
{"ts": "...", "type": "task_done", "task_id": "TASK-0007", "duration_s": 178, "cost_usd": 0.42}
{"ts": "...", "type": "task_failed", "task_id": "TASK-0007", "error_fingerprint": "abc123", "retries": 2}
{"ts": "...", "type": "needs_human", "task_id": "TASK-0007", "reason": "path_violation"}
{"ts": "...", "type": "global_stop", "reason": "daily_budget_exceeded"}
{"ts": "...", "type": "polling_tick", "in_progress": 2, "ready": 5, "blocked": 3}
```

### 12.2 顶层每轮汇报格式（给用户看）

```markdown
## Polling tick @ 2026-05-10 14:23

**正在跑** (2)：
- TASK-0007 Unity adapter PoC  [12 min, $0.34]
- TASK-0009 Godot adapter PoC  [8 min, $0.21]

**本轮变化**：
- ✓ TASK-0001 Protocol schema → done [PR #12 merged]
- ✓ TASK-0003 Path whitelist CI → done [PR #14 merged]
- ⚠ TASK-0011 UE adapter PoC → needs_human
   原因：源码审计违规，agent 试图修改 .uasset 文件
   PR：https://github.com/.../pull/15
- ⊘ TASK-0012 UE fixture → blocked（依赖 TASK-0011）

**预算**：今日 $14.32 / $200 上限
**下一轮**：5 分钟后唤醒
```

### 12.3 用户裁决 needs_human 的方式（自然语言）

用户在 Claude Code 对话里直接说，顶层 agent **用自然语言识别**意图，不要求严格语法。例：

| 用户说的话 | 顶层识别为 | 动作 |
|---|---|---|
| "TASK-0011 我看了 PR 是误判，approve 重试" | approve_retry | needs_human/ → ready/，retries 不变 |
| "0011 误判，重新跑" | approve_retry | 同上 |
| "11 是真违规，标 failed 关掉" | reject_failed | needs_human/ → failed/，关 PR |
| "TASK-0011 我手动改完了 PR，标 done" | approve_done | needs_human/ → done/，记 manual_intervention=true |
| "0011 跳过先不处理" | defer | 维持 needs_human/，下次 polling 不重新询问 |
| "把 TASK-0011 阻塞的下游全部 cancel 掉" | cascade_cancel | 找所有依赖 0011 的任务，blocked/ → failed/ |
| "全部停了" | global_stop | 写 stop_signal |
| "继续" / "ok" | （无指令，仅推进 polling） | 不做裁决动作 |

**识别规则**（顶层每轮 polling 第 3 步）：
1. 扫上一轮 user message 文本
2. 提取所有形如 `TASK-NNNN` / `0NNN` / `NNNN` 的 ID（与 needs_human/ 里的 ID 比对，模糊匹配）
3. 对每个匹配到的 ID，识别动词关键词：approve/重试/redo/retry → approve_retry；fail/失败/关闭/reject → reject_failed；done/完成/已处理/通过 → approve_done；defer/跳过/晚点 → defer；cancel/取消 → cascade_cancel
4. 识别失败（歧义、找不到 ID）→ 在汇报里反问"你说的 TASK-XXXX 是指 ...?"，但**不阻塞**继续 polling

**关键原则**：
- 顶层的"识别"是"best effort"——识别错了把 needs_human 误移走，下一轮用户说"我没说重试 TASK-0011" 顶层应能撤回（移回 needs_human/）
- 永远在 events.jsonl 里记 `decision_parsed` 事件含原始用户文本 + 解析结果，便于事后追责
- 如果 needs_human/ 里有任务但用户**没提任何 ID**，顶层不做任何动作，只是在汇报里再次列出 needs_human 提醒

---

## 十三、目录与脚本清单

```
<REPO_ROOT>\
├─ scripts/
│  ├─ orchestrator/        # 顶层 Claude 调用的 helper
│  │  ├─ poll.py           # 一轮 polling（read state + compute ready + report）
│  │  ├─ spawn.py          # spawn 单个 Python agent
│  │  ├─ collect.py        # 扫 in_progress/ 收集完成的
│  │  ├─ stop.py           # 写 stop_signal
│  │  ├─ resume.py         # 删 stop_signal
│  │  └─ status.py         # 打印当前状态摘要
│  ├─ agent/
│  │  └─ run_task.py       # Python agent 入口
│  └─ ci/                  # 已存在的 CI 脚本（不变）
│     ├─ check_changed_paths.py
│     ├─ audit_visual_writes.py
│     └─ ...
├─ state/                  # gitignore 整个目录
│  ├─ queue/  ready/  in_progress/  awaiting_ci/  done/  failed/  needs_human/  blocked/
│  ├─ logs/<TASK-NNNN>/<timestamp>.log
│  ├─ events.jsonl
│  ├─ budget.json
│  └─ stop_signal
├─ .env.agent.example      # commit
├─ .env.agent              # gitignore
└─ docs/
   └─ 09-orchestration.md  # 本文档
```

---

## 十四、新增任务（追加到 tasks.md）

orchestration scaffolding 本身要作为 Phase 0 一部分：

| ID | 标题 | mode | effort | risk |
|---|---|---|---|---|
| TASK-0018 | state/ 目录初始化 + .gitignore + 文件锁约定 | manual | 1h | low |
| TASK-0019 | scripts/orchestrator/{poll,spawn,collect,stop,resume,status}.py | auto-with-review | 2d | medium |
| TASK-0020 | scripts/agent/run_task.py + prompt 模板 | auto-with-review | 2d | high |
| TASK-0021 | 顶层 Claude /loop 启动 prompt 模板（doc + 用户操作指南） | manual | 4h | low |
| TASK-0022 | 端到端 dry run（1 个 echo 任务跑通整个 loop） | manual | 4h | high |

详细 YAML 加到 `docs/tasks.md` Phase 0 节末尾，依赖关系：
- TASK-0018 → TASK-0019 → TASK-0020 → TASK-0022
- TASK-0021 与 TASK-0019/0020 并行
- TASK-0022 是 orchestration 子链的最后一个验证任务，必须在 TASK-0023（Phase 0 出口 gate review）之前通过

---

## 十五、Go/no-go gate（追加到 Phase 0）

Phase 0 出口在原 6 项基础上加 4 项：

7. ☐ orchestration scaffolding 跑通 1 个 echo 任务（TASK-0022 通过）
8. ☐ 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human
9. ☐ 故意 kill 掉一个 in_progress agent → 顶层 resume 时正确恢复
10. ☐ 写 stop_signal → 顶层正确停机

任意一项 fail → Phase 0 不算完成。

---

## 十六、不做什么（明确边界）

- **不**做 web UI dashboard —— 状态全在文件里，需要时单独写
- **不**做 Slack/Discord 通知 —— 顶层会话里看就够
- **不**做多用户协作 —— 单用户单仓库
- **不**做跨机器分布式 —— 单机串行（MVP）
- **不**做任务热加载 —— 改 tasks.md 后需要重新生成 queue/
- **不**做 agent 之间通信 —— Python agent 互相不知道对方
- **不**让 Python agent 操作 GitHub merge —— merge 由人或独立 bot 做
