# 07 - AI Agent Operating Contract

> AI Agent（Claude Code background mode）执行任务的边界与规则。设定权限、迭代上限、失败处理、secret 策略。
> **任何 autonomous loop 启动前必须读这份文档。**

## 一、设计原则

1. **能跑得起来 ≠ 能放心跑** —— 自动化越强，意外破坏的代价越大
2. **失败要停得快** —— 连续失败必须降级为人工
3. **改动要可逆** —— 一切操作通过 git，不直接修改 `origin/main`
4. **secret 不上下文** —— AI 永远看不到 API key、私钥、生产数据
5. **路径硬白名单** —— 不允许 AI 改非约定路径

## 二、Iteration & Stopping

### 2.1 单任务最大迭代次数

| 任务类型 | 最大尝试次数 | 失败后行为 |
|---|---|---|
| 普通编码任务（adapter 内部 / MCP tool） | 5 | 标 `needs-human-review`，发通知 |
| 涉及 e2e 的任务 | 3 | 同上 |
| 涉及视觉回归 baseline 的任务 | 1 | 立刻停，必须人工确认 |
| 修改 CI 配置 / 项目 manifest 的任务 | 1 | 立刻停 |
| 修改协议规范 / 跨 adapter 字段的任务 | 1 | 立刻停 |

迭代 = 一次"改代码 → 推 commit → CI 跑 → 看结果"循环。

### 2.2 Session-level 上限

| 项 | 上限 | 说明 |
|---|---|---|
| 单 session 任务数 | 20 | 一次连续运行最多处理 20 个任务 |
| 单 session CI 触发数 | 50 | 含重试 |
| 单 session API 成本 | $50 USD | Anthropic API 用量估算 |
| 单 session 时长 | 12 小时 | wall clock |

任意上限触达 → session 停 + 通知 + 等人手动恢复。

### 2.3 Global 上限（跨 session）

| 项 | 上限 |
|---|---|
| 单天 API 成本 | $200 USD |
| 单天 PR 数 | 50 |
| 连续路径违规 | 3 次 → 全局停 |

触达后自动暂停所有 background agent，开 GitHub Issue。

### 2.4 失败模式分类

| 失败类型 | 行为 |
|---|---|
| 单元测试 fail | 重试，diff + log 给 AI |
| e2e fail（引擎崩溃） | 重试 1 次，仍 fail → 停 |
| CI 配置错误 | 立即停（不重试） |
| **路径白名单违规（防护 0.1）** | **立即停，不重试**（说明 AI 越界了） |
| **源码 diff 审计失败（防护 0.2）** | **立即停，不重试** |
| dump 前后 diff 失败（防护 0.3） | 重试 1 次（可能测试不稳定），仍 fail → 停 |
| 视觉回归失败（防护 3） | 重试 1 次，仍 fail → 标 `needs-baseline-review` |
| 网络超时 / API rate limit | 退避重试，最多 3 次 |
| Claude API 返回 `stop_reason="refusal"` | 立即停，记录上下文给人工 |
| Token 上限触达 | 同上 |

## 三、路径权限

### 3.1 AI 可读路径
- 整个 repo 的所有文件（read-only）
- `~/.autoagent/config.toml`（不含 secret 字段）
- `~/.autoagent/sessions/<session_id>.jsonl`（自己的 trace）

### 3.2 AI 可写路径

✅ **允许写**：
```
adapters/{unity,unreal,godot}/Runtime/**/*.cs *.cpp *.h *.gd
adapters/{unity,unreal,godot}/Tests/**
mcp-server/src/**/*.py
mcp-server/tests/**/*.py
fixtures/*/Scripts/**/*.cs *.cpp *.h *.gd
docs/99-tasks.md  (仅状态字段更新允许；新任务/重排需人工)
```

❌ **禁止写**：
```
fixtures/*/*.unity *.uasset *.tscn *.umap          # 场景文件
fixtures/*/Assets/Sprites/** Resources/UI/** Content/UI/**   # 美术资源
fixtures/*/Assets/Fonts/**                          # 字体
fixtures/*/ProjectSettings/** Config/DefaultEngine.ini   # 引擎配置
baselines/**                                         # 视觉 baseline
.github/workflows/**                                # CI 配置（除非任务明确）
.env *.key *.pem secrets/**                         # secret
docs/00-08*.md                                      # 产品文档
.gitignore .git/**                                  # git 元
package.json package-lock.json pyproject.toml uv.lock pnpm-lock.yaml   # 依赖锁
```

CI 第一步 `scripts/ci/check_changed_paths.py` 强制执行。违反 → PR 立即关闭，agent 收到 `-32030 PathViolation`。

### 3.3 例外申请流程
确实需要改禁止路径时：
1. 任务 doc 必须明确声明 `path_exception: ["specific/path/here"]`
2. 任务必须标 `risk: high`，强制 human review
3. CI 仍跑路径白名单检查，但允许 exception list

## 四、Secret 管理

### 4.1 AI 永远看不到的 secret
- Anthropic API key（Claude Code 自己配，**不通过 prompt 传**）
- GitHub token（GitHub Actions secret，env var 注入）
- 任何生产数据库 URL / API key
- TLS 私钥
- 用户真实账号密码

### 4.2 AI 可以看到的"半 secret"
- 测试环境 mock API endpoint（已 sandbox）
- Test user 凭据（专为测试创建，仅 sandbox 有效）
- 公开的 license key（如 GameCI Unity personal license activation key，已 GitHub secret 化）

### 4.3 实现保护
- `.env` / `secrets/` 路径在 `.gitignore` + 路径白名单都禁
- CI 用 GitHub Actions secrets 注入到 env，不在日志输出（`::add-mask::`）
- AI 收到任何疑似 secret（regex 匹配 `[A-Za-z0-9_\-]{32,}` + 上下文有 `key` / `token` / `password` 字样）应该立即停且不入 prompt 历史
- agent log 输出前自动 redact secret pattern

## 五、Git 操作策略

### 5.1 允许的 git 操作
- `git checkout -b task/XXX-...`
- `git add <白名单内的路径>`
- `git commit -m "[TASK-XXX] ..."`
- `git push origin task/XXX-...`
- `gh pr create ...`
- `gh pr comment ...`（仅 reply 给 CI 失败 / human review feedback）

### 5.2 禁止的 git 操作
- `git push origin main`（任何方式）
- `git push --force` to **任何** branch
- `git rebase` / `git merge`（PR 通过 GitHub UI 或人 / auto-merge bot 完成）
- `git reset --hard`（AI 工作目录也禁，避免误丢工作）
- `git config` 改 user.email / user.name / remote
- 任何 `git tag`
- 任何 `--no-verify` / `-c commit.gpgsign=false`

### 5.3 Branch 命名
`task/<task-id>-<short-desc>`，例：`task/0042-implement-login-controller`

### 5.4 Commit message
```
[TASK-XXX] Title under 70 chars

详细说明：
- 改了什么
- 为什么
- 验证结果（CI link / 测试输出摘要）
```

### 5.5 单次 commit 原则
- 一个任务一个 commit（可能多次 push 到同一 branch，最后 squash by GitHub）
- 不允许 amend 已经 push 过的 commit

## 六、PR 工作流

### 6.1 PR Title
`[TASK-XXX] Title`

### 6.2 PR Body 模板
```markdown
## Task
TASK-XXX: <title>
Phase: <0/1/2/3/4>
Engine: <unity/unreal/godot/all>
Risk: <low/medium/high>

## Goal
<一句话目标，从任务 doc 拷过来>

## Changes
- File path: 简述改动

## Verification
- [ ] 路径白名单通过（CI step 1）
- [ ] 源码 diff 审计通过（CI step 2）
- [ ] 单元测试通过（CI step 3）
- [ ] e2e 通过（CI step 4，如适用）
- [ ] 视觉回归通过（CI step 5，如适用）
- [ ] dump 前后 diff 通过（防护 0.3）

## AI Agent Trace
- Session ID: <uuid>
- Iterations: <n>
- Cost: $<amount>
- Started: <iso8601>
- Completed: <iso8601>
```

### 6.3 PR Auto-merge
- **默认禁用 auto-merge**
- 例外：标 `auto-merge-safe` label 的任务（low-risk + human pre-approved）+ 全 CI 绿 → 允许 auto-merge
- Phase 0/1 期间所有任务都不允许 auto-merge

### 6.4 Review 强度

| Risk | Phase 0/1 | Phase 2/3/4 |
|---|---|---|
| Low | Human review required | CI green 可 merge |
| Medium | Human review required | Human review required |
| High | Human review required + 协议变更 review | Human review required |

## 七、通知与可观测

### 7.1 通知渠道
- 任务完成（PR 提）→ GitHub PR 通知 + （可选）Slack webhook
- 任务失败 → 同上 + 标 `needs-human-review` label
- 上限触达 → 高优通知（GitHub Issue + email）
- Cost 报告 → 每天 EOD 汇总到 `~/.autoagent/cost-daily.csv`

### 7.2 日志
- 所有 AI session 完整 trace 落 `~/.autoagent/sessions/<session_id>.jsonl`
- 包含：每次 prompt / tool call / response / cost / iteration / git op
- 保留 90 天，超期自动 archive 到 `sessions-archive/`

### 7.3 可观测指标
- 每日 PR 数 / merge 率 / 平均迭代数 / 平均成本
- CI 失败率分布（按 防护 0.1 / 0.2 / 0.3 / 编译 / 测试分类）
- 路径违规次数 趋势

## 八、紧急停机

### 8.1 用户主动停
- `autoagent-stop` CLI 命令
- 写入 `~/.autoagent/STOP` 文件
- 所有 background agent 在下一次轮询（≤ 10s）检测到 → 停止
- 当前正在跑的 CI job 保留（不主动 cancel，避免半完成状态）

### 8.2 自动停机条件
- 任意 global 上限触达
- 连续 3 个任务路径白名单违规（说明 AI 在尝试越界）
- 连续 5 个任务 CI 失败
- 检测到 secret 写入风险（自动 fail-stop）
- Claude API 连续 5 次 refusal

### 8.3 停机后状态
- 所有未完成任务标 `paused`
- 已开 PR 不关，等人工 review
- 写入 `~/.autoagent/last_stop.log` 记录原因

## 九、人工恢复流程

1. 检查停机原因（`~/.autoagent/last_stop.log`）
2. 修复根因（可能是任务 doc 不清楚、CI 配置错、AI prompt 缺约束）
3. 重置 counter：`autoagent-reset --session` 或 `--global`
4. 启动：`autoagent-start --task TASK-XXX` 或 `autoagent-start --resume`

## 十、与 99-tasks.md 的关系

任务清单（`99-tasks.md`）的每个任务必须显式声明：

```yaml
TASK-0042:
  title: Implement LoginController in Unity
  phase: 1
  engine: unity
  depends_on: [TASK-0035, TASK-0040]
  goal: ...
  output: [paths]
  verification: ...
  effort: 4h
  execution_mode: auto-with-review     # manual | auto-with-review | auto-merge-safe
  risk: low                             # low | medium | high
  max_iterations: 5                     # 覆盖 §2.1 默认值
  path_exception: []                    # §3.3 例外申请
```

风险等级影响 PR review 强度（见 §6.4）。`execution_mode` 决定 AI 是否可以 auto-merge。

## 十一、初始 bootstrap（Phase 0 配置）

第一次启动 background agent 前必须做：

1. ☐ 安装 GitHub CLI 并 `gh auth login`（用 fine-grained token，仅 repo scope）
2. ☐ 安装 Claude Code 并配置 Anthropic API key（环境变量，不在 prompt）
3. ☐ 配置 `~/.autoagent/config.toml`（含 vision / claude_vision / source_audit 段）
4. ☐ 确认 GitHub repo branch protection（main: 必须 PR + CI green + review）
5. ☐ 确认 GitHub Actions secrets（UNITY_LICENSE / 等）
6. ☐ 配置 `.autoagent/STOP` 监视目录权限
7. ☐ Self-hosted UE runner online（[08-ci-runners.md](08-ci-runners.md)）

任何一项不到位 → 不启动 autonomous loop。
