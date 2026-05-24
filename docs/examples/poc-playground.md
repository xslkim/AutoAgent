# AutoAgent 端到端教程 — poc_playground 三引擎同步开发

> 本教程演示如何使用 AutoAgent 框架，在 Unity / Unreal / Godot 三个引擎上
> 同步开发同一个 UI 交互功能。从手动操控到 AI 全自动，逐步深入。

**预计时间**: 60-90 分钟（含引擎启动时间）
**前置条件**: Unity 2023.2+, Unreal 5.x, Godot 4.x, Python 3.12+

---

## 目录

1. [场景概览](#1-场景概览)
2. [环境准备](#2-环境准备)
3. [手动探索](#3-手动探索)
4. [手动操控](#4-手动操控)
5. [OS 级输入对比](#5-os-级输入对比)
6. [三引擎跨引擎对比](#6-三引擎跨引擎对比)
7. [任务 DSL](#7-任务-dsl)
8. [AI 自治循环](#8-ai-自治循环)
9. [视觉回归验证](#9-视觉回归验证)
10. [参考代码](#10-参考代码)

---

## 1. 场景概览

`poc_playground` 是三引擎共享的静态视觉骨架场景。它只包含图片和文字占位节点，
**没有任何交互逻辑** — 这正是 AI 要添加的部分。

### 节点清单（三引擎 ID 完全一致）

```
PocPlaygroundScene (CanvasLayer / Canvas / CanvasPanel)
├─ click_target              ← 按钮（5 个变体）
├─ click_target_variant_1
├─ click_target_variant_2
├─ click_target_variant_3
├─ click_target_variant_4
├─ click_target_variant_5
├─ text_target               ← 输入框背景（混动窗口）
│  └─ text_target_text       ← 文字标签
├─ drag_source               ← 拖拽起点
├─ drag_target               ← 拖拽终点
└─ scroll_container           ← 滚动容器
   └─ scroll_content          ← 滚动内容区
      ├─ scroll_item_001
      ├─ ...
      └─ scroll_item_030     ← 30 个滚动项
```

### 三引擎节点类型对照

| Pinned ID | Unity | Unreal | Godot | Logical Role |
|-----------|-------|--------|-------|-------------|
| click_target | GameObject (Image) | UImage | TextureRect | button |
| text_target | GameObject (Image) | UImage | TextureRect | input |
| text_target_text | TextMeshProUGUI | UTextBlock | Label | text_display |
| drag_source | GameObject (Image) | UImage | TextureRect | drag_source |
| scroll_container | GameObject (Image) | UImage | TextureRect | scroll_container |
| scroll_item_NNN | GameObject (Image) | UImage (Blueprint) | TextureRect | image_only |

> **关键概念**: 这些节点是"纯视觉骨架"——只有位置、大小、图片。Button 组件、
> InputField、拖拽逻辑等都是 AI 后续添加的。框架的防护系统会确保 AI 不会
> 意外修改视觉字段（颜色、位置、Sprite 等）。

---

## 2. 环境准备

### 2.1 安装 MCP Server

```bash
cd mcp-server
pip install -e ".[dev]"

# 验证
python -c "from autoagent_mcp.server import build_server; print('OK')"
```

### 2.2 启动引擎

**Unity** (任选其一):
```bash
# 方式 A: 手动打开
#   Unity Hub → 打开 fixtures/unity-test-project → Play Mode

# 方式 B: 命令行
"C:\Program Files\Unity 2023.2.20f1\Editor\Unity.exe" \
  -projectPath fixtures/unity-test-project \
  -executeMethod AutoAgent.CIBuild.EnterPlayMode -batchmode
```

**Unreal** (任选其一):
```bash
# 方式 A: 手动打开
#   Unreal Editor → 打开 fixtures/unreal-test-project/PocPlaygroundMap → PIE (Alt+P)

# 方式 B: 命令行 (需要 Unreal Engine 路径)
# UE 编辑器启动后手动 PIE
```

**Godot** (任选其一):
```bash
# 方式 A: 手动打开
#   Godot → 导入 fixtures/godot-test-project/project.godot → 运行 (F5)

# 方式 B: headless（仅用于自动化测试，无法验证 OS 光标）
godot --path fixtures/godot-test-project scenes/poc_playground.tscn
```

### 2.3 启动 MCP Server

```bash
cd mcp-server
python -m autoagent_mcp.server
```

输出应显示:
```
MCP Server started
Connected to engine at ws://127.0.0.1:27842
```

### 2.4 验证连接

用 Claude Code 或其他 MCP 客户端连接 server，然后:

```
>>> dump_tree
{
  "nodes": [
    {"id": "click_target", "type": "Image", "meta": {"logical_role": "button"}, ...},
    {"id": "text_target", "type": "Image", "meta": {"logical_role": "input"}, ...},
    ...
  ],
  "captured_at": 1716000000.0
}
```

如果返回节点列表，说明引擎连接成功。

---

## 3. 手动探索

### 3.1 dump_tree — 查看完整节点树

```
>>> dump_tree()
```

返回 40+ 个节点的完整树。每个节点包含:

```json
{
  "id": "click_target",
  "type": "Image",
  "engine_type": "UnityEngine.UI.Image",
  "parent_id": null,
  "children_ids": [],
  "stable_id_source": "pinned",
  "visual": {
    "position": [100, 100],
    "size": [120, 80],
    "anchor": [0, 0],
    "visible": true,
    "alpha": 1.0,
    "color": "#FFFFFFFF",
    "sprite_ref": "slot_bg"
  },
  "behavior": {
    "interactable": false,
    "raycast_target": false,
    "event_handlers": [],
    "custom_scripts": [],
    "attached_components": ["Image"]
  },
  "meta": {
    "logical_role": "button",
    "intent": null,
    "tags": [],
    "state_sprites": null
  }
}
```

### 3.2 dump_tree_delta — 增量查询

```
>>> r1 = dump_tree_delta()
>>> r1["snapshot_id"]
"a1b2c3d4"

# 场景未变化时:
>>> r2 = dump_tree_delta(since="a1b2c3d4")
>>> r2["full_snapshot"]    # False — 无变化
>>> r2["unchanged_count"]  # 40 — 全部未变
>>> r2["changed"]          # [] — 无变化
```

### 3.3 find_widget — 按角色搜索

```
>>> find_widget(logical_role="button")
["click_target", "click_target_variant_1", "click_target_variant_2",
 "click_target_variant_3", "click_target_variant_4", "click_target_variant_5"]

>>> find_widget(logical_role="input")
["text_target"]
```

### 3.4 get_widget — 查看单个节点

```
>>> get_widget(id="text_target")
{
  "id": "text_target",
  "type": "Image",
  "visual": {"size": [360, 56], "visible": true, ...},
  "meta": {
    "state_sprites": {"normal": "input_bg_normal", "focused": "input_bg_focused"}
  }
}
```

> **发现**: text_target 有 `state_sprites` — 正常和聚焦两种状态的图片。后面可以
> 用它来实现输入框视觉反馈。

---

## 4. 手动操控

以下操作在 **Unity** 引擎上演示。切换到 UE/Godot 时操作完全相同。

### 4.1 click — 点击按钮

**engine 层**（默认，通过 EventSystem 注入，光标不移动）:

```
>>> click(id="click_target")
{"success": true}
```

点击后:
- `dump_tree()` 查看 `click_target.behavior.event_handlers` — 仍然为空（没有 AI 添加的 onClick 处理器）
- 因为框架只做输入注入，不会自动添加交互逻辑

### 4.2 send_text — 输入文字

```
>>> send_text(id="text_target", text="Hello AutoAgent")
```

> 注意: 需要 AI 先给 `text_target` 添加 `TMP_InputField` 组件后才能接收文字输入。
> 在纯视觉骨架上直接 send_text 会返回错误。

### 4.3 drag — 拖拽

```
>>> drag(from_id="drag_source", to_id="drag_target", duration_ms=500)
{"success": true}
```

### 4.4 scroll — 滚动

```
>>> scroll(id="scroll_container", direction="down", amount=200)
{"success": true}
```

### 4.5 key_press — 按键

```
>>> key_press(id="text_target", key="Enter")
{"success": true}

>>> key_press(id="text_target", key="Shift+Tab")
{"success": true}
```

> 支持的按键: `Enter` / `Return` / `Submit`, `Escape` / `Esc` / `Cancel`,
> `Tab`, `Shift+Tab`

---

## 5. OS 级输入对比

OS 层 (`input_layer="os"`) 直接操控系统光标，绕开引擎事件系统。

### 5.1 对比演示

```
# Engine 层 — 光标不移动，引擎内部处理
>>> click(id="click_target", input_layer="engine")

# OS 层 — 可以看到鼠标光标跳到 click_target 的位置然后点击
>>> click(id="click_target", input_layer="os")
```

### 5.2 三平台 OS 层支持

| 平台 | Unity | Unreal | Godot |
|------|-------|--------|-------|
| Windows | Win32 SendInput | Win32 SendInput | DisplayServer 光标位移 |
| macOS | CGEventPost | CGEventPost | DisplayServer 光标位移 |
| Linux | X11 XTest | X11 XTest | DisplayServer 光标位移 |

### 5.3 验证 OS 层

```bash
# Windows — 可见光标跳到节点位置
>>> click(id="drag_source", input_layer="os")

# macOS — 需要辅助功能权限（系统设置 → 隐私 → 辅助功能）
>>> click(id="drag_source", input_layer="os")

# Linux — 需要 X11 会话
>>> click(id="drag_source", input_layer="os")
```

### 5.4 带右/中键的点击

```
>>> click(id="click_target", button="right", input_layer="os")
>>> click(id="click_target", button="middle", input_layer="os")
```

---

## 6. 三引擎跨引擎对比

### 6.1 同一操作在不同引擎的 dump_tree 输出

**Unity**:
```json
{"id": "click_target", "type": "Image", "engine_type": "UnityEngine.UI.Image"}
```

**Unreal**:
```json
{"id": "click_target", "type": "UImage", "engine_type": "UImage"}
```

**Godot**:
```json
{"id": "click_target", "type": "TextureRect", "engine_type": "TextureRect"}
```

### 6.2 节点坐标差异

| 引擎 | 坐标原点 | Y 轴方向 |
|------|---------|---------|
| Unity | 左下 | 上 + |
| Unreal | 左上 | 下 + |
| Godot | 左上 | 下 + |

> OS 层已经处理了坐标转换（Y-flip + DPI），手动对比时注意坐标系差异。

### 6.3 视觉基线对比

```bash
# 采集三引擎基线
python scripts/e2e/capture_baseline.py --engine unity  --scene poc_playground
python scripts/e2e/capture_baseline.py --engine unreal --scene poc_playground
python scripts/e2e/capture_baseline.py --engine godot  --scene poc_playground

# 验证
python scripts/ci/check_visual_baseline.py --baseline baselines/unity/windows/poc_playground.png
```

---

## 7. 任务 DSL

任务 DSL 是 AI 理解需求的标准化格式。放在 `docs/canonical-tasks/poc_playground.yaml`。

已随本教程提供：`docs/canonical-tasks/poc_playground.yaml`

### DSL 内容概要

任务定义了一个简单的交互面板：

1. **点击高亮**: 点击 `click_target` 或其变体 → 该按钮显示"选中"状态
2. **文字过滤**: 向 `text_target` 输入文字 → 过滤可见的按钮
3. **拖拽交换**: 从 `drag_source` 拖拽到 `drag_target` → 触发重排
4. **滚动加载**: 滚动到 `scroll_container` 底部 → 显示更多项

### 关键约束

```yaml
constraints:
  max_iterations: 5
  cost_limit_usd: 2.0
  visual_diff_ssim_min: 0.95
  path_whitelist: true
  visual_write_block: true
```

---

## 8. AI 自治循环

### 8.1 配置 AI Agent

```bash
# 复制配置模板
cp .env.agent.example .env.agent

# 编辑（填入你的 API key）
# AGENT_RUNNER=opencode
# DEEPSEEK_API_KEY=sk-...
# MCP_SERVER_URL=http://localhost:8000
```

### 8.2 启动 Agent

**Unity**:
```bash
python scripts/agent/runner.py \
  --task docs/canonical-tasks/poc_playground.yaml \
  --engine unity
```

**Unreal**:
```bash
python scripts/agent/runner.py \
  --task docs/canonical-tasks/poc_playground.yaml \
  --engine unreal
```

**Godot**:
```bash
python scripts/agent/runner.py \
  --task docs/canonical-tasks/poc_playground.yaml \
  --engine godot
```

### 8.3 Agent 工作流程

```
迭代 1:
  AI: dump_tree() → 获取场景结构
  AI: 发现 5 个 click_target, text_target, drag_source/target, scroll_container
  AI: 在 PocPlaygroundController.cs 中添加 OnClick 高亮逻辑
  AI: 提交 PR → CI 自动运行测试 → 截图对比
  CI: SSIM=0.98 PASS, Visual Audit PASS
  AI: 检查截图 → 按钮被点击后正常高亮

迭代 2:
  AI: 添加文字过滤逻辑
  AI: send_text("card") → assert 只有匹配的按钮可见
  CI: SSIM=0.97 PASS

... (继续迭代直到所有步骤通过)
```

### 8.4 Agent 输出

Agent 会生成以下文件（路径受 path_whitelist 约束）:

| 文件 | 说明 |
|------|------|
| `fixtures/unity-test-project/Assets/Scripts/PocPlaygroundController.cs` | Unity 交互逻辑 |
| `fixtures/unreal-test-project/Source/AutoAgentTest/PocPlaygroundController.h` | UE 头文件 |
| `fixtures/unreal-test-project/Source/AutoAgentTest/PocPlaygroundController.cpp` | UE 实现 |
| `fixtures/godot-test-project/scripts/PocPlaygroundController.gd` | Godot 脚本 |

### 8.5 验证 Agent 结果

```bash
# 运行全部测试
pytest scripts/ci/tests/ mcp-server/tests/

# 运行特定引擎 e2e 测试
python scripts/e2e/unity_login.sh      # Unity
python scripts/e2e/ue_run_login.py     # UE
# Godot: godot --headless --path fixtures/godot-test-project res://addons/autoagent/tests/headless_input_test.tscn
```

---

## 9. 视觉回归验证

### 9.1 采集基线

```bash
# 三引擎各自采集（AI 开发后）
python scripts/e2e/capture_baseline.py --engine unity  --scene poc_playground
python scripts/e2e/capture_baseline.py --engine unreal --scene poc_playground
python scripts/e2e/capture_baseline.py --engine godot  --scene poc_playground
```

基线图片保存在:
```
baselines/unity/windows/poc_playground.png
baselines/unreal/windows/poc_playground.png
baselines/godot/windows/poc_playground.png
```

### 9.2 SSIM 对比

```python
# MCP 工具调用
>>> compare_to_baseline(id="poc_playground")
{
  "ssim": 0.98,
  "passed": true,
  "threshold": 0.95
}
```

### 9.3 LPIPS 感知对比

```python
>>> compare_lpips_to_baseline(id="poc_playground")
{
  "lpips": 0.03,
  "passed": true,
  "threshold": 0.1
}
```

### 9.4 Claude Vision 裁决

```python
>>> claude_judge_screenshot(
      id="poc_playground",
      question="Are all 5 buttons visible and properly aligned? Is the text input field showing the correct background?"
    )
{
  "answer": "Yes",
  "confidence": 0.95,
  "details": "All 5 buttons are visible in a horizontal row. The text input field shows the normal state background."
}
```

---

## 10. 参考代码

以下是 AI 完成开发后产出的参考实现，供对比学习。

> 这些代码由 AI Agent（Claude Code）在自治循环中自动编写。你可以在
> `docs/examples/poc-playground/` 目录下找到完整文件。

### 10.1 Unity — PocPlaygroundController.cs

位置: `docs/examples/poc-playground/unity/PocPlaygroundController.cs`

核心逻辑:
- `Start()`: 遍历所有 `click_target*` 节点，给 `Image` 添加 `Button` 组件
- `OnClickTarget(buttonId)`: 高亮被点击的按钮（修改 Image.color 为选中色），取消其他高亮
- `AttachInputField()`: 给 `text_target` 添加 `TMP_InputField`，监听 `onValueChanged`
- `OnFilterTextChanged(text)`: 根据输入过滤可见按钮
- 拖拽和滚动由引擎事件系统原生处理（Button/ScrollRect）

### 10.2 Unreal — PocPlaygroundController.h / .cpp

位置: `docs/examples/poc-playground/unreal/`

核心逻辑:
- `BeginPlay()`: 使用 BindWidget 属性找到 UI 控件，添加 `OnClicked` 动态委托
- `OnClickTarget(int32 Index)`: 设置 Widget 的 `ColorAndOpacity` 为高亮色
- `OnFilterTextChanged(FText)`: 根据 `TextTargetText->GetText()` 过滤
- 使用 `ESlateVisibility` 控制可见性

### 10.3 Godot — PocPlaygroundController.gd

位置: `docs/examples/poc-playground/godot/PocPlaygroundController.gd`

核心逻辑:
- `_ready()`: 通过 `get_node()` 按路径找到 `click_target*` 节点
- 给 TextureRect 动态包装一个 Button 父节点实现点击
- `_on_filter_text_changed(text)`: 过滤可见按钮
- 使用 `visible` 属性控制显隐

---

## 附录 A: 故障排除

### MCP Server 连不上引擎

```bash
# 检查引擎是否在 Play Mode / PIE / 运行状态
# 检查端口 27842 是否被占用
netstat -an | grep 27842
```

### OS 输入无效

- Windows: 确保 Unity/UE 以管理员身份运行（SendInput 需要）
- macOS: 系统设置 → 隐私与安全性 → 辅助功能 → 添加 Unity/UE/Godot
- Linux: 确保在 X11 会话下运行（Wayland 不支持 XTest）

### dump_tree 返回空

- 检查引擎场景是否正确加载（PocPlaygroundScene / WBP_PocPlayground / poc_playground.tscn）
- 检查 Canvas/CanvasLayer 是否激活
- 检查节点是否有 RectTransform / RenderTransform

---

## 附录 B: 命令速查

```bash
# 启动 MCP Server
cd mcp-server && python -m autoagent_mcp.server

# 运行测试
pytest scripts/ci/tests/ mcp-server/tests/

# 视觉基线
python scripts/e2e/capture_baseline.py --engine <unity|unreal|godot> --scene poc_playground

# Agent 自治
python scripts/agent/run_task.py --task docs/canonical-tasks/poc_playground.yaml --engine <unity|unreal|godot>

# 发布
bash scripts/release.sh patch
```
