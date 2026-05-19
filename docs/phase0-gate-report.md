# Phase 0 出口 gate 检查报告

> TASK-0023 产出。Phase 0 的 10 个 go/no-go gate 逐项 review 结果。
> **任意一项 fail → Phase 1 不启动。**
>
> gate 定义见 [tasks-phase0.md §Phase 0 出口标准](tasks-phase0.md)。
> 维护人已于 2026-05-19 逐项 review 全部 10 个 gate 并签字放行（见文末「出口签字」）。

---

## 摘要

| # | Gate | 状态 |
|---|---|---|
| 1 | 三引擎 dump UI 树 parent/children 正确 | ☑ PASS |
| 2 | Unity / Godot screenshot 非空（非黑屏） | ☑ PASS |
| 3 | Self-hosted UE runner online + nightly 跑通 | ☑ PASS |
| 4 | 防护 0.1 + 0.2 拦下故意破坏 | ☑ PASS |
| 5 | Subprotocol 握手三引擎返回 `autoagent.v1` | ☑ PASS |
| 6 | `negotiate_version` JSON-RPC 握手符合规范 | ☑ PASS |
| 7 | Orchestration 跑通 1 个 echo 任务（TASK-0022） | ☑ PASS |
| 8 | agent 违反路径白名单 → 顶层捕获 needs_human | ☑ PASS |
| 9 | kill in_progress agent → 顶层 resume 恢复 | ☑ PASS |
| 10 | 写 stop_signal → 顶层停机 | ☑ PASS |

---

## Gate 1 — 三引擎 dump UI 树 parent/children 正确

**证据**
- e2e 冒烟 `scripts/e2e/login_smoke.py` 含 `dump_tree` + node schema 校验
  （`protocol/schema/node.json`）、pinned 节点覆盖检查。
- Unity / Godot / Unreal 三引擎各 8/8 项检查通过（同一脚本、同一协议）。

**人工核对**：☑　三引擎各跑一次 `login_smoke.py`，确认 dump_tree 检查项 PASS。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 2 — Unity / Godot screenshot 非空（非黑屏）

**证据**
- TASK-0014：三引擎 baseline 截图，6 张 PNG 在 `baselines/{unity,godot,unreal}/windows/`，
  每张配 `.meta.json`。
- `take_screenshot` 协议方法三引擎均实现，写出真实 PNG。

**人工核对**：☑　肉眼 review 6 张 baseline，确认非黑屏、内容正确。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 3 — Self-hosted UE runner online + nightly 跑通

**证据**
- self-hosted runner `F5090`（ID 21，标签 self-hosted/Windows/X64）online，
  见 `docs/runners-inventory.md`。
- `.github/workflows/unreal-nightly.yml`：`Build.bat` 编译 + `UnrealEditor-Cmd`
  跑 2 个 Automation 测试，已验证跑通。

**人工核对**：☑　GitHub Settings → Runners 显示 online；手动 workflow_dispatch 触发
unreal-nightly 跑一次确认绿。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 4 — 防护 0.1（路径白名单）+ 0.2（源码 diff）拦下故意破坏

**证据**
- 本地 integration 脚本验证拦截逻辑：
  `bash scripts/ci/tests/integration/test_path_violation.sh`、
  `bash scripts/ci/tests/integration/test_visual_audit.sh`。
- TASK-0015 / TASK-0016：在独立 sandbox repo `github.com/xslkim/AuteTest` 装入
  防护 0.1/0.2 + `source-audit.yml`，推 3 个故意破坏演示 PR，CI 结果与预期完全一致：

  | PR | 故意做的事 | CI 结果 | 日志证据 |
  |---|---|---|---|
  | AuteTest#1 | 改 `.unity` / `baselines/` / `.env` | **FAIL** ✓ | 防护 0.1 输出 3 条 DENY（`.env` / `baselines/**` / `fixtures/*/**.unity`） |
  | AuteTest#2 | C# 写 `errorIcon.color = Color.red` | **FAIL** ✓ | 防护 0.2 输出 `[color_write]` 违规行 |
  | AuteTest#3 | 同上 + `AUTOAGENT_ALLOW_VISUAL` 豁免注释 | **PASS** ✓ | 防护 0.2 跳过该文件（exempted） |
- main repo（AutoAgent）全局违规计数不受影响 —— 破坏全发生在 sandbox repo。

**人工核对**：☑　打开 AuteTest#1/#2/#3，确认 CI 红/红/绿与上表一致。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 5 — Subprotocol 握手三引擎返回 `autoagent.v1`

**证据**
- e2e `login_smoke.py` 含「握手」+「错误 subprotocol 拒绝」两项检查。
- 三引擎均正确协商 `autoagent.v1`、拒绝错误 subprotocol。三引擎 8/8。

**人工核对**：☑　确认 login_smoke 握手 / 错误 subprotocol 拒绝两项 PASS。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 6 — `negotiate_version` JSON-RPC 握手符合规范

**证据**
- e2e `login_smoke.py` 含 `negotiate_version` 检查项，三引擎通过。
- 协议规范见 `docs/01-protocol-spec.md`。

**人工核对**：☑　确认 login_smoke 的 negotiate_version 检查项 PASS。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 7 — Orchestration 跑通 1 个 echo 任务（TASK-0022）

**证据**
- TASK-0022 端到端验证完成，见 `docs/dry-run-report.md` §十。
- 真 /loop：collect → CI → done → poll → spawn → opencode agent → collect → CI →
  done 全闭环。dry-run 任务 TASK-DRY-001 / TASK-DRY-002 各开 PR（#64 / #65）CI 全绿。
- agent runner 已从 claude CLI 换成 opencode + DeepSeek V4 Pro。

**人工核对**：☑　Review dry-run-report.md §十。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 8 — agent 违反路径白名单 → 顶层捕获 needs_human

**证据**
- TASK-0022 Stage 3：result `status=needs_human` 的任务经 `collect.py` 正确路由到
  `needs_human/`；模拟自然语言裁决 `approve_retry` 后回 `ready/`。
- `classify.py` 优先级：policy 违规模式即使 exit 0 也拦下（unit test
  `test_policy_violation_beats_clean_exit`）。

**人工核对**：☑　Review dry-run-report.md §十 Stage 3。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 9 — kill in_progress agent → 顶层 resume 恢复

**证据**
- TASK-0022 Stage 3：`in_progress/` 任务 `result=null` 且 `spawn.pid` 为死 pid →
  `collect.py` 检测 zombie → 退回 `ready/` 且 `retries` +1。

**人工核对**：☑　Review dry-run-report.md §十 Stage 3。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## Gate 10 — 写 stop_signal → 顶层停机

**证据**
- TASK-0022 Stage 3：`stop.py` 写 `state/stop_signal` → `poll.py` 和 `spawn.py`
  都拒绝调度。

**人工核对**：☑　Review dry-run-report.md §十 Stage 3。

**结论**：☑ PASS　（维护人 2026-05-19 review 通过）

---

## 出口签字

- [x] Gate 1–10 全部 PASS
- [x] 无 FAIL 项

| 项 | 内容 |
|---|---|
| 签发人 | xslkim（xiangsilian@gmail.com） |
| 日期 | 2026-05-19 |
| 结论 | ☑ **Phase 0 通过，Phase 1 启动** |

---

## 附：证据来源速查

| 来源 | 覆盖 gate |
|---|---|
| `scripts/e2e/login_smoke.py`（三引擎 8/8） | 1, 5, 6 |
| `baselines/` 6 张截图 + TASK-0014 | 2 |
| `docs/runners-inventory.md` + unreal-nightly workflow | 3 |
| `scripts/ci/tests/integration/*.sh` + TASK-0015/0016 | 4 |
| `docs/dry-run-report.md` §十（TASK-0022） | 7, 8, 9, 10 |
