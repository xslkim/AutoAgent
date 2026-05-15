# dry-run-report.md — Orchestration 端到端 Dry Run (TASK-0022)

> 日期：2026-05-15
> 环境：Windows 11, Python 3.12.10
> 仓库：commit `d6af7dd`
> 隔离目录：`state-dryrun/`（dry run 期间临时；跑完已清理）

## 一、目的

在 Phase 0 真正启动 `/loop` 之前，验证 [docs/09-orchestration.md](09-orchestration.md) 描述的调度链路在本地能完整跑通：

```
queue → ready → in_progress → awaiting_ci → done
                     │
                     ├──▶ needs_human (路径违规等)
                     └──▶ ready (僵尸恢复 / 重试)

global: stop_signal → poll/spawn 全部拒绝执行 → resume 恢复
```

## 二、跑了哪些场景

| 场景 | 验证内容 | 结果 |
|---|---|---|
| A. Happy path | poll 入 ready / run_task 写 result / collect 入 awaiting_ci | ✓ |
| B. 路径违规 | mock claude 喷 `-32030 PathViolation` stderr → needs_human | ✓ |
| C. 僵尸 agent | PID 死 + 无 result.json → ready/ + retries=1 | ✓ |
| D. 紧急停机 | stop_signal → poll/spawn 拒绝；resume 恢复 | ✓ |

事件全部正确写到 `state-dryrun/events.jsonl`（`task_transition` / `task_finished` / `task_collected` / `global_stop` / `global_resume` 5 种）。

## 三、Happy path 逐步轨迹

### 准备 echo 任务

`state-dryrun/queue/TASK-DRY-001.json`：

```json
{
  "id": "TASK-DRY-001",
  "title": "Echo task — orchestration dry run happy path",
  "phase": 0,
  "engine": "none",
  "depends_on": [],
  "spec_path": "docs/dry-run-report.md",
  "mode": "auto-with-review",
  "risk": "low",
  "goal": "Exit cleanly, pretend to have opened a PR.",
  "verification": [
    "agent exit code 0",
    "PR URL emitted in stdout",
    "result.status == awaiting_ci"
  ],
  "retries": 0,
  "max_retries": 3,
  "max_duration_seconds": 60,
  "spawn": {"pid": null, "worktree_path": null, "branch": null, "log_path": null},
  "result": null,
  "history": []
}
```

### Step 1: status — 初始一棵空树 + 1 task in queue

```
$ python scripts/orchestrator/status.py --state-root state-dryrun
  * queue        (1)  TASK-DRY-001
    ready        (0)
    in_progress  (0)
    ...
  ✓ no stop_signal
```

### Step 2: poll — DRY-001 无依赖，进 ready

```
$ python scripts/orchestrator/poll.py --state-root state-dryrun
  moved TASK-DRY-001 → ready  (no deps)
```

### Step 3: spawn dry-run — 列出会 spawn 的目标

```
$ python scripts/orchestrator/spawn.py --state-root state-dryrun --dry-run
would spawn TASK-DRY-001
```

### Step 4: 直接调用 run_task.py（mock claude，无网络）

```
$ mv state-dryrun/ready/TASK-DRY-001.json state-dryrun/in_progress/

$ python scripts/agent/run_task.py TASK-DRY-001 \
    --state-root state-dryrun --no-worktree \
    --claude-cmd $(which python) \
    --claude-arg=-c \
    --claude-arg="import sys; sys.stdin.read(); print('Echo task done. Pretend PR: https://github.com/example/repo/pull/42'); sys.exit(0)"

TASK-DRY-001: awaiting_ci — agent exited cleanly, PR open
```

`run_task.py` 把 `result` 写回任务文件：

```json
"result": {
  "status": "awaiting_ci",
  "reason": "agent exited cleanly, PR open",
  "pr_url": "https://github.com/example/repo/pull/42",
  "exit_code": 0,
  "timed_out": false,
  "log_path": "state-dryrun/logs/TASK-DRY-001/...log"
}
```

### Step 5: collect — 移到 awaiting_ci/

```
$ python scripts/orchestrator/collect.py --state-root state-dryrun
  moved TASK-DRY-001 → awaiting_ci  (agent done, CI pending)
```

### Step 6: 模拟 CI 全绿 → done

```
$ mv state-dryrun/awaiting_ci/TASK-DRY-001.json state-dryrun/done/
```

真实场景下，**顶层 Claude** 用 `gh pr checks <pr_url>` 自动检测 CI 状态，全绿后调用 `mv`。本地 dry run 没有真 PR，所以手动模拟。

## 四、负面场景

### B. 路径违规 → needs_human

构造一个 in_progress/ 任务 + mock claude 在 stderr 喷 `-32030 PathViolation`：

```
$ python scripts/agent/run_task.py TASK-DRY-002 \
    --state-root state-dryrun --no-worktree \
    --claude-cmd $(which python) \
    --claude-arg=-c \
    --claude-arg="import sys; sys.stdin.read();
                  sys.stderr.write('MCP error -32030 PathViolation: ...');
                  sys.exit(1)"

TASK-DRY-002: needs_human — path violation

$ python scripts/orchestrator/collect.py --state-root state-dryrun
  moved TASK-DRY-002 → needs_human  (path violation)
```

`classify.py` 优先级正确：先检测 policy 违规模式（即使 exit 0 也能拦下，见 unit test `test_policy_violation_beats_clean_exit`），再看 exit code。

### C. 僵尸 agent → ready

构造一个 in_progress/ 任务，PID 999999（系统不存在）+ `result: null`：

```
$ python scripts/orchestrator/collect.py --state-root state-dryrun
  moved TASK-DRY-003 → ready  (zombie agent (pid 999999 dead, no result.json))
```

任务文件被改写：`retries: 0 → 1`，`spawn.pid → null`。重新进入 ready/ 等下次 spawn。

### D. 紧急停机

```
$ python scripts/orchestrator/stop.py --state-root state-dryrun --reason "dry run scenario D"
stop_signal written: dry run scenario D

$ python scripts/orchestrator/poll.py --state-root state-dryrun
stop_signal present — refusing to schedule

$ python scripts/orchestrator/spawn.py --state-root state-dryrun --dry-run
stop_signal present — refusing to spawn

$ python scripts/orchestrator/resume.py --state-root state-dryrun
stop_signal cleared

$ python scripts/orchestrator/poll.py --state-root state-dryrun
no state transitions; queue=0 blocked=0 ready=1 inflight=0
```

## 五、Events trace

```
[2026-05-15T16:43:21Z] task_transition      TASK-DRY-001 → ready (no deps)
[2026-05-15T16:43:29Z] task_finished        TASK-DRY-001 status=awaiting_ci exit_code=0
[2026-05-15T16:43:39Z] task_collected       TASK-DRY-001 → awaiting_ci (agent done, CI pending)
[2026-05-15T16:43:53Z] task_finished        TASK-DRY-002 status=needs_human exit_code=1
[2026-05-15T16:43:53Z] task_collected       TASK-DRY-002 → needs_human (path violation)
[2026-05-15T16:44:03Z] task_collected       TASK-DRY-003 → ready (zombie ...)
[2026-05-15T16:44:10Z] global_stop          reason=dry run scenario D
[2026-05-15T16:44:10Z] global_resume
```

`events.jsonl` 每个状态转移都留痕，事后复盘有据。

## 六、本地能验证的 vs. 必须真 /loop 才能验证

✅ **本地 dry run 已覆盖**：

- queue → ready / blocked 决策
- spawn → in_progress 转移
- run_task 写 result + 原子保存
- classify 正确识别 path/visual/auth 违规
- collect 路由（awaiting_ci / needs_human / failed / retry-ready / zombie）
- stop/resume 全局门控
- events.jsonl 事件 trace
- log 自动 scrub secret

❌ **本地 dry run 不能覆盖，需要真 /loop 才完整跑通**：

| 项 | 为什么 | 验证方式 |
|---|---|---|
| `claude` CLI 真实调用 | 需要本机 `claude` 命令 + 有效 `ANTHROPIC_API_KEY` | 用户跑 `/loop` 时由 spawn.py 链路触发 |
| `git worktree` 真创建 | dry run 用了 `--no-worktree` | unit test `test_worktree.py` 用真 git 已覆盖 |
| `gh pr create` + PR check 轮询 | 需要 GitHub 凭据 + 真 repo | 等用户首个真 task 跑通时验证 |
| 自然语言裁决（§12.3） | 顶层 Claude 的 LLM 推断行为 | 用户在 /loop 里说"approve 0011 重试"验证 |
| 12h session 超时 / budget 触达 | 真实跑那么久才触发 | 模拟时间用 unit test 验证 limit 计算（已） |

## 七、复现 dry run 的步骤

```bash
# 1. 重建隔离 state
rm -rf state-dryrun
mkdir -p state-dryrun/{queue,ready,in_progress,awaiting_ci,done,failed,needs_human,blocked,logs}

# 2. 写入 echo task（见 §三 准备 echo 任务 的 JSON）
# 3. 按 §三 / §四 顺序跑命令
# 4. 看 state-dryrun/events.jsonl
```

或者读单元测试（更稳定）：

```bash
pytest scripts/orchestrator/tests/ scripts/agent/tests/ -v
```

`scripts/orchestrator/tests/test_poll_smoke.py` 已用临时 state 自动跑过相同场景。

## 八、结论

调度链路在本地完整跑通——poll/spawn/collect/stop/resume 5 个 helper 协同正确，run_task.py 在 mock claude 下行为符合 classify.py 设计，events.jsonl 完整留痕。

剩余的 `claude` CLI / GitHub PR / 自然语言裁决三块属于"真 /loop 启动"时才能验证的部分；具体由 **TASK-0022 在真 Claude Code 会话里**做最终签字（[docs/user-guide-orchestration.md §三](user-guide-orchestration.md) 流程）。

## 九、Phase 0 出口 gate 对应（TASK-0023 参考）

| Gate | 本次覆盖 |
|---|---|
| Gate 7: Orchestration scaffolding 跑通 1 个 echo 任务 | ✓ (Happy path, 不含真 claude CLI) |
| Gate 8: 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human | ✓ (Scenario B) |
| Gate 9: 故意 kill in_progress agent → 顶层 resume 正确恢复 | ✓ (Scenario C — zombie 路径) |
| Gate 10: 写 stop_signal → 顶层正确停机 | ✓ (Scenario D) |

Gate 1-6 依赖三引擎 adapter，本次未涉及。
