# Self-hosted runner 清单

> TASK-0013 产出。记录 AutoAgent CI 用的 GitHub Actions self-hosted runner。
> 换机器 / 加 runner / 换维护人时**手动更新本文件**（运维专属，需人工 review）。

---

## 1. runner 清单

| 字段 | 值 |
|---|---|
| runner ID | `21` |
| name / hostname | `F5090` |
| OS | Windows 11 |
| 架构 | X64 |
| labels | `self-hosted` / `Windows` / `X64` |
| 安装目录 | `D:\actions-runner` |
| 注册范围 | repo 级（`xslkim/AutoAgent`） |
| 维护负责人 | xiangsilian@gmail.com |
| 状态 | online |

查在线状态：GitHub 仓库 → **Settings → Actions → Runners**，或

```
gh api repos/xslkim/AutoAgent/actions/runners --jq '.runners[] | {id,name,status}'
```

---

## 2. 为什么要 self-hosted

GitHub 云端 runner 没装游戏引擎、没 GPU、磁盘小，跑不了 Unity / Godot / Unreal 的
编译和测试。self-hosted = CI 任务在用户这台装齐三引擎的机器上跑。

机器要求（TASK-0013 spec）：Windows 11 + VS 2022 + UE + GPU + 32GB RAM + 200GB SSD。

---

## 3. 引擎可执行文件路径

CI workflow 里**写死**了引擎路径 —— 换机器 / 换引擎版本必须同步改对应 workflow：

| 引擎 | 路径 | 用到的 workflow |
|---|---|---|
| Unity 2023.2.20f1 | `C:\Program Files\Unity 2023.2.20f1\Editor\Unity.exe` | `unity-pr.yml` |
| Godot 4.6 (dev/mono) | `D:\test\godot\bin\godot.windows.editor.dev.x86_64.mono.exe` | `godot-pr.yml` |
| Unreal 5.7 | `C:\Program Files\Epic Games\UE_5.7` | `unreal-nightly.yml` |

---

## 4. 常驻 / 维护

- **目前**：`D:\actions-runner\run.cmd` 前台运行（关窗口即停）。
- **建议**：用管理员 PowerShell 装成 Windows 服务常驻：
  ```
  cd D:\actions-runner
  ./svc install
  ./svc start
  ```
- runner 跑 CI 时尽量别在编辑器里开着同一个 fixture 项目（CI 用独立 checkout 目录，
  一般不冲突，但 Unity 项目锁要注意）。

---

## 5. 关联 workflow

| workflow | 触发 | 在 runner 上做什么 |
|---|---|---|
| `unity-pr.yml` | PR 改 `adapters/unity/**` 等，或手动 | Unity batch 模式跑 8 个 PlayMode 测试 |
| `godot-pr.yml` | PR 改 `adapters/godot/**` 等，或手动 | Godot headless 跑 `headless_input_test`（9 项） |
| `unreal-nightly.yml` | 每晚 02:00 UTC，或手动 | `Build.bat` 编译 + `UnrealEditor-Cmd` 跑 Automation 测试 |

每个 workflow 另有一个 `lint` job 跑在 GitHub 云端（fixture 静态检查，免费、快）。

详见 [engine-adapters-and-ci.md §6](engine-adapters-and-ci.md)。
