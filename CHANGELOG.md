# Changelog

## v1.0.0 (2026-05-23)

### Core — 多引擎 AI Agent UI 自动化框架

AutoAgent 是一个让 AI Agent（Claude Code 等）通过 MCP 协议驱动 Unity / Unreal /
Godot 游戏引擎，实现 UI 开发完整闭环的框架：

```
程序员放置静态 UI → 框架遍历 UI 树添加 ID/meta
  → AI 接收任务描述 → AI 写引擎代码
  → 框架自动运行并模拟操作 → 视觉对比回传 AI
  → AI 判断完成或继续迭代
```

### 三引擎 Adapter

- **Unity** — C# adapter，支持 UGUI 完整反射、输入注入、WebSocket JSON-RPC 服务端
- **Unreal** — C++ adapter，支持 UMG 反射、Slate 输入注入、editor 模块 pin 扫描
- **Godot** — GDScript adapter，支持 Control 节点反射、stable ID、visual regression

### 五道美术保真防护

0. **源码层审计** — PR diff 路径白名单 + visual-write AST/regex 扫描 + dump 前后 diff gate
1. **协议层 Schema 权限** — runtime setter 拒绝 visual/结构字段写入 (`-32003`/`-32004`)
2. **ID 稳定性** — pinned / auto declared，禁止 hash ID 用于任务 contract
3. **视觉回归** — SSIM ≥ 0.95 + Claude Vision 二次裁决 + LPIPS 子进程化 (Phase 4)
4. **资源 GUID 追踪** — 引擎自带 (.meta / AssetRegistry / .uid)

### OS 级输入（三平台双轨）

- **Windows** — `Win32InputDriver`：SendInput API，绝对坐标转换 (0-65535)，ClientToScreen 窗口偏移
- **macOS** — `MacInputDriver`：CGEventPost API，CGDisplayBounds 坐标转换
- **Linux** — `LinuxInputDriver`：X11 XTest 扩展，持久 Display 连接
- 引擎事件层（EventSystem / FSlateApplication / Input.parse_input_event）为主轨
- OS 层为 fallback，通过 `input_layer="os"` 切换

### MCP Server

- JSON-RPC over WebSocket wire protocol
- `click / drag / scroll / key_press` 输入工具（支持 `input_layer` 参数）
- `dump_tree / dump_tree_delta` 节点树查询（delta cache 增量推送）
- `take_screenshot / compare_to_baseline / compare_lpips_to_baseline` 视觉回归
- `invoke_method / get_property / set_property` 反射调用
- `claude_judge_screenshot` Claude Vision 二次裁决
- API cost tracking + STOP signal

### CI / Automation

- **CI runners**: Windows self-hosted (Unity + UE Editor), GitHub-hosted (MCP + Godot)
- **Source audit**: path whitelist + visual-write regex scan on every PR
- **E2E tests**: cross-engine login MVP verification scripts
- **Nightly**: UE stress test + visual regression suite
- **Orchestration**: AI agent autonomous loop with resume / stop / cost tracking
- **Agent runner**: opencode + DeepSeek backend

### Known Limitations

- macOS CGEventPost requires Accessibility permissions (macOS 10.14+)
- Linux XTest driver requires X11 session (no native Wayland support)
- OS-level input coordinate conversion assumes fullscreen/window-at-origin;
  multi-display precision needs per-platform window-offset queries (future)
- Batch-mode `Assume.That` inconclusive tests may cause non-zero exit;
  prefer `Assert.Ignore` for platform-gated test skipping
