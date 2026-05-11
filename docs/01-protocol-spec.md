# 01 - Wire Protocol Specification v0.1

> 框架（MCP Server）与引擎 Adapter 之间的通信协议。所有三引擎 adapter 必须实现这份协议。
> Phase 0 PoC 完成后会出 v0.2，schema 锁定。

## 一、传输层

- **传输**：WebSocket over TCP
- **默认端口**：`27842`（可配置，避开常见占用）
- **绑定地址**：默认 `127.0.0.1`（本地通信）
- **握手**：标准 WebSocket 升级握手 + 自定义 `Sec-WebSocket-Protocol: autoagent.v1`
- **编码**：UTF-8 JSON
- **每条消息**：单独一帧（一次 send，不分片）

## 二、消息格式

基于 JSON-RPC 2.0，三种消息类型：**Request / Response / Notification（事件）**。

### Request（MCP Server → Adapter）

```json
{
  "jsonrpc": "2.0",
  "id": "uuid-string",
  "method": "dump_tree",
  "params": { "root_id": null, "include_invisible": false }
}
```

### Response（Adapter → MCP Server）

成功：
```json
{
  "jsonrpc": "2.0",
  "id": "uuid-string",
  "result": { ... }
}
```

错误：
```json
{
  "jsonrpc": "2.0",
  "id": "uuid-string",
  "error": { "code": -32001, "message": "WidgetNotFound", "data": { "id": "missing_id" } }
}
```

### Notification（Adapter → MCP Server，事件流）

```json
{
  "jsonrpc": "2.0",
  "method": "event.scene_changed",
  "params": { "scene_name": "MainMenu", "timestamp": 1715234567.123 }
}
```

## 三、节点 Schema（核心数据结构）

每个 UI 节点统一 schema，**属性强制分三组**。

> ⚠️ **重要约定（与 [00 §四 程序员搭建边界](00-product-overview.md) 强一致）**：程序员手搭 fixture 时**只放视觉骨架**（Image / Text / 容器），`type` 字段反映的是**引擎 raw 类型**（不会出现 `Button` / `InputField`）。"逻辑控件角色"由 `meta.logical_role` 声明，AI 在源码里按引擎模型实现对应控件能力：Unity `AddComponent`，UE 包裹 / 替换为 UMG widget，Godot 替换节点并迁移视觉。也就是说：
> - **fixture 加载完直接 dump**：`type=Image`、`meta.logical_role=button`、`behavior.event_handlers=[]`、`behavior.custom_scripts=[]`
> - **AI 代码运行之后 dump**：Unity 通常 `type=Image` 不变且 `behavior.attached_components=[Button]`；UE/Godot 可能因包裹 / 替换出现新 widget class，但同一 pinned ID 必须保留，且 `behavior.attached_components` 反映已实现的控件能力
> - **任务 DSL 引用按 `meta.logical_role`**，不再按 `type`

```json
{
  "id": "login_button_bg",
  "type": "Image",
  "engine_type": "UnityEngine.UI.Image",
  "parent_id": "login_panel",
  "children_ids": ["login_button_label"],
  "stable_id_source": "pinned" | "hash" | "auto",

  "visual": {
    "position": [100.0, 200.0],
    "size": [200.0, 60.0],
    "anchor": [0.5, 0.5],
    "world_bounds": [50.0, 170.0, 250.0, 230.0],
    "visible": true,
    "alpha": 1.0,
    "color": "#FFFFFFFF",
    "sprite_ref": "Assets/UI/btn_login_normal.png",
    "z_order": 5
  },

  "behavior": {
    "interactable": true,
    "raycast_target": true,
    "event_handlers": ["OnClick"],
    "custom_scripts": ["LoginController"],
    "attached_components": ["UnityEngine.UI.Button"]
  },

  "meta": {
    "logical_role": "button",
    "role": "submit_button",
    "intent": "trigger_login",
    "tags": ["primary", "form"],
    "task_refs": ["TASK-042"],
    "state_sprites": {
      "normal":   "Assets/UI/btn_login_normal.png",
      "hover":    "Assets/UI/btn_login_hover.png",
      "pressed":  "Assets/UI/btn_login_pressed.png",
      "disabled": "Assets/UI/btn_login_disabled.png"
    }
  }
}
```

### 三类属性的语义

| 类别 | 含义 | AI 权限 |
|---|---|---|
| `visual` | 视觉表达：位置 / 尺寸 / 颜色 / `sprite_ref` 当前值 / 透明度 / Z 序 | **只读**（防美术稿被破坏） |
| `behavior` | 交互行为：是否响应 / 绑定脚本 / 事件回调 / `raycast_target` / 运行时附加的控件组件 | 读写 |
| `meta` | 语义标签：`logical_role` / role / intent / tags / 任务引用 / `state_sprites` 映射 | 读写（fixture 初始化时由程序员声明 `logical_role` / `state_sprites`；AI 可补充其他 meta） |

#### `meta.logical_role` 取值表（normative，跨引擎统一）

| 值 | 程序员手放的节点 type | AI 在代码里实现的控件能力 |
|---|---|---|
| `button` | Image / RawImage / TextureRect / UImage | Unity: `Button` ; UE: `UButton` ; Godot: `Button` |
| `input` | Image（背景框）+ 子 Text 节点（占位/输入回显） | Unity: `TMP_InputField` / `InputField` ; UE: `UEditableTextBox` ; Godot: `LineEdit` |
| `slider` | Image（轨道）+ Image（handle）+ 可选 Image（fill） | Unity: `Slider` ; UE: `USlider` ; Godot: `HSlider` / `VSlider` |
| `toggle` / `checkbox` | Image（背景）+ Image（勾选标记） | Unity: `Toggle` ; UE: `UCheckBox` ; Godot: `CheckButton` / `CheckBox` |
| `dropdown` / `combobox` | Image（背景）+ Text（当前值）+ Image（箭头） | Unity: `TMP_Dropdown` ; UE: `UComboBoxString` ; Godot: `OptionButton` |
| `scroll_container` | Image（视口容器）+ Image（content 容器）+ 可选 Image（滚动条） | Unity: `ScrollRect` + `RectMask2D` ; UE: `UScrollBox` ; Godot: `ScrollContainer` |
| `list_view` | Image（容器）+ Image（item 模板） | AI 自定义渲染（Instantiate 模板 + 数据绑定） |
| `text_display` | Text / TextMeshPro / UTextBlock / Label | （不需要 AddComponent，纯显示） |
| `image_only` | Image / Sprite / RawImage / TextureRect | （不需要 AddComponent，装饰） |

**约定**：
- fixture 阶段，每个**有交互**的节点必须 pin ID **并**声明 `meta.logical_role`；纯装饰节点可省略（默认 `image_only`）。
- 任务 DSL 引用节点的 `logical_role` 与 fixture 声明的不匹配 → MCP server 加载任务时拒绝。
- AI 实际实现的控件能力必须与 `logical_role` 对应表一致；adapter 在 dump 时把实际挂载 / 包裹 / 替换后的控件写入 `behavior.attached_components`，CI 校验一致性（防 AI 偷换控件）。

### 必填字段

`id` / `type` / `engine_type` / `parent_id` / `children_ids` / `stable_id_source` / `visual.position` / `visual.size` / `visual.visible`

`meta.logical_role` 在**有交互的节点**（任务 DSL 引用的节点）上必填。

### 节点 ID 稳定性约定（normative）

`stable_id_source` 三种来源对任务可靠性的承诺**不同**：

| 来源 | 来源详情 | 跨美术迭代/hot reload/PIE 稳定 | 任务 DSL 可引用 |
|---|---|---|---|
| `pinned` | 美术 / 程序员手动 pin（持久化到引擎组件 / 元数据） | ✅ | ✅ |
| `auto` | 框架在源码 / 节点声明里自动收集（如 UPROPERTY meta=AutoAgentId / SerializeField StableId） | ✅ | ✅ |
| `hash` | 框架基于 hierarchy_path + name + type 计算的回退值 | ❌ | ❌ **任务 DSL 禁止引用** |

**强制约束**：任何被 task DSL 引用的节点必须 `stable_id_source ∈ {pinned, auto}`。MCP server 在加载任务时校验 → 引用了 hash ID 直接拒绝并要求 pin。

**hash ID 的合法用途**：
- AI 临时探索 UI 树（`dump_tree` 返回里包含）
- 给程序员提示"这些节点未 pin"
- `list_orphan_ids` 检测对照

## 四、命令集（Methods）

### 4.1 树查询

#### `dump_tree`
拉取整棵 UI 树或子树。

```json
// Request
{ "method": "dump_tree", "params": {
  "root_id": null,        // null = 全部，或指定子树根
  "include_invisible": false,
  "max_depth": -1,         // -1 = 不限
  "fields": ["visual", "behavior", "meta"]  // 可选过滤减少 token
}}

// Result
{ "nodes": [ {...}, {...} ], "captured_at": 1715234567.123 }
```

#### `find_widget`
按条件找节点（支持 ID / logical_role / role / type / 文本）。

```json
{ "method": "find_widget", "params": {
  "by": "id" | "logical_role" | "role" | "type" | "text",
  "value": "button",
  "first_only": true
}}

// Result: { "nodes": [...] }
```

> 任务 DSL 推荐用 `by=logical_role` 而非 `by=type`，因为 fixture 里所有交互节点的 `type` 都是 `Image`，无区分度。

#### `get_widget`
按 ID 拿单个节点的最新状态。

```json
{ "method": "get_widget", "params": { "id": "login_button" }}
// Result: { "node": {...} }
```

### 4.2 输入操作

> **前置条件（normative）**：所有输入操作走**引擎事件层**（Q4=A）。目标节点必须已经被 AI 在源码里实现对应控件能力（Unity `AddComponent`；UE 包裹 / 替换为交互 widget；Godot 替换为交互 Control），否则引擎事件分发不到任何 handler，adapter 返回 `-32002 WidgetNotInteractable`。
>
> 也就是说：**fixture 加载完直接对 `logical_role=button` 的节点发 `click` 会失败**，AI 必须先让自己写的代码 `Awake()` / `NativeConstruct()` / `_ready()` 完成控件实现才能成功。CI e2e 流程必须保证这个时序。

#### `click`
模拟点击。**前置**：目标节点的 `behavior.attached_components` 包含 `Button` / `Toggle` / 其他实现了引擎 click 接口的组件，且 `behavior.raycast_target == true`。

```json
{ "method": "click", "params": {
  "id": "login_button_bg",
  "button": "left" | "right" | "middle",
  "modifiers": ["ctrl", "shift", "alt"],
  "input_layer": "engine" | "os"   // 默认 engine
}}
// Result: { "success": true, "captured_at": ... }
```

#### `send_text`
向输入框发送文本。**前置**：目标节点的 `behavior.attached_components` 包含 `TMP_InputField` / `InputField` / `UEditableTextBox` / `LineEdit`。

```json
{ "method": "send_text", "params": {
  "id": "account_input_bg",
  "text": "alice@example.com",
  "clear_first": true
}}
```

#### `drag`
从一个节点拖到另一个节点（或坐标）。**前置**：from / to 节点的 `behavior.attached_components` 实现引擎拖拽接口（Unity `IBeginDragHandler` 等 / UE `OnDragDetected` / Godot `_get_drag_data`）。

```json
{ "method": "drag", "params": {
  "from_id": "item_001",
  "to_id": "slot_005",
  "duration_ms": 200,
  "input_layer": "engine"
}}
```

#### `scroll`
滚动容器。**前置**：目标节点的 `behavior.attached_components` 包含 `ScrollRect` / `UScrollBox` / `ScrollContainer`。

```json
{ "method": "scroll", "params": {
  "id": "inventory_scroll_container",
  "direction": "down" | "up" | "left" | "right",
  "amount": 100.0
}}
```

#### `key_press`
按键。

```json
{ "method": "key_press", "params": {
  "keys": ["Enter"],
  "input_layer": "engine"
}}
```

### 4.3 截图与等待

#### `take_screenshot`
截图（整屏 / 指定节点 / 指定矩形）。

```json
{ "method": "take_screenshot", "params": {
  "scope": "fullscreen" | "node" | "rect",
  "node_id": "login_panel",     // scope=node 时必填
  "rect": [x, y, w, h],          // scope=rect 时必填
  "format": "png" | "jpg",
  "save_path": "screenshots/login.png"   // 可选；不填返回 base64
}}
// Result: { "saved_path": "...", "base64": "...", "size": [w, h] }
```

#### `wait_for`
等待条件满足。

```json
{ "method": "wait_for", "params": {
  "condition": "widget_appeared" | "widget_disappeared" | "widget_visible" | "text_changed",
  "id": "welcome_text",
  "expected_value": "Welcome alice",   // text_changed 时用
  "timeout_ms": 5000,
  "poll_interval_ms": 100
}}
// Result: { "success": true, "elapsed_ms": 1234 }
```

### 4.4 反射调用（高级）

#### `invoke_method`
调用节点上挂载脚本的方法（用于测试自定义逻辑）。

```json
{ "method": "invoke_method", "params": {
  "id": "login_panel",
  "script": "LoginController",
  "method_name": "ResetForm",
  "args": []
}}
// Result: { "return_value": null }
```

#### `get_property` / `set_property`
读写脚本字段（仅 behavior / meta，禁止 visual）。

```json
{ "method": "set_property", "params": {
  "id": "login_panel",
  "script": "LoginController",
  "property": "errorMessage",
  "value": "Invalid credentials",
  "category": "behavior"   // 服务端校验，visual 拒绝
}}
```

### 4.5 ID 管理

#### `pin_id`
钉死一个 ID 到节点（持久化到引擎组件字段）。

```json
{ "method": "pin_id", "params": {
  "current_id": "auto_hash_abc123",
  "new_id": "login_button"
}}
```

#### `list_orphan_ids`
列出"上次见过这次找不到"的 ID。

```json
{ "method": "list_orphan_ids", "params": {} }
// Result: { "orphans": [{"id": "old_button", "last_seen_path": "..."}] }
```

### 4.6 Session 管理

#### `ping` / `pong`
存活检测，30s 心跳。

#### `get_engine_info`
拿引擎元信息。

```json
{ "method": "get_engine_info", "params": {} }
// Result: {
//   "engine": "Unity" | "Unreal" | "Godot",
//   "engine_version": "2023.2.20f1",
//   "adapter_version": "0.1.0",
//   "protocol_version": "0.1",
//   "platform": "Windows" | "Linux" | "Mac",
//   "build_type": "Editor" | "Development" | "Shipping"
// }
```

## 五、事件流（Notifications）

Adapter 主动推送给 MCP Server，无需 ack。

| 事件 | 触发时机 | params |
|---|---|---|
| `event.scene_changed` | 场景 / Level 切换 | `{scene_name, timestamp}` |
| `event.widget_appeared` | 新节点出现 | `{id, type, parent_id, timestamp}` |
| `event.widget_disappeared` | 节点销毁 / 隐藏 | `{id, timestamp}` |
| `event.widget_clicked` | 用户/AI 点击 | `{id, button, timestamp, source: "user"|"automation"}` |
| `event.text_changed` | 输入框文本变化 | `{id, old_text, new_text, timestamp}` |
| `event.error` | adapter 内部错误 | `{level: "warn"|"error", message, stack}` |

## 六、错误码

JSON-RPC 标准错误码 + 框架自定义：

| Code | 名称 | 说明 |
|---|---|---|
| -32700 | ParseError | JSON 解析失败 |
| -32600 | InvalidRequest | 不符合 JSON-RPC 2.0 |
| -32601 | MethodNotFound | 未知 method |
| -32602 | InvalidParams | 参数错误 |
| -32603 | InternalError | adapter 内部错误 |
| -32001 | WidgetNotFound | 找不到指定 ID 的节点 |
| -32002 | WidgetNotInteractable | 节点存在但不可交互（如 disabled） |
| -32003 | VisualPropertyWrite | 试图写 visual 属性（被拒） |
| -32004 | StructuralChange | 试图修改 hierarchy（被拒） |
| -32005 | TimeoutError | wait_for 超时 |
| -32006 | InputInjectionFailed | 输入注入失败（焦点丢失等） |
| -32007 | EngineThreadViolation | 跨线程调用引擎 API |
| -32008 | ScreenshotFailed | 截图失败 |
| -32010 | VersionMismatch | 协议版本不兼容 |
| -32011 | NegotiationTimeout | 握手 5 秒超时 |
| -32012 | SubprotocolMismatch | WebSocket subprotocol 错误 |
| -32013 | NotNegotiated | 握手前调用了其他 method |
| -32030 | PathViolation | AI 试图修改非白名单路径（CI 层） |

## 七、版本协商（强制握手）

WebSocket subprotocol 协商成功后，**Server 必须在 100ms 内**发起 `negotiate_version` JSON-RPC request。Adapter **必须在 5 秒内**回复，超时或不兼容立即断开。

```json
// 1. Server → Adapter (Request)
{
  "jsonrpc": "2.0",
  "id": "negotiate-1",
  "method": "negotiate_version",
  "params": {
    "supported": ["0.1"],
    "client": "autoagent-mcp/0.1.0"
  }
}

// 2a. Adapter → Server (Response, success)
{
  "jsonrpc": "2.0",
  "id": "negotiate-1",
  "result": {
    "agreed": "0.1",
    "adapter_supported": ["0.1"],
    "adapter_name": "autoagent-unity/0.1.0",
    "engine": "Unity",
    "engine_version": "2023.2.20f1"
  }
}

// 2b. Adapter → Server (Response, version mismatch)
{
  "jsonrpc": "2.0",
  "id": "negotiate-1",
  "error": {
    "code": -32010,
    "message": "VersionMismatch",
    "data": { "supported": ["0.2"] }
  }
}
```

**握手层错误码**：
- `-32010 VersionMismatch`：双方版本无交集 → adapter 立即关闭连接（WebSocket close code 1002）
- `-32011 NegotiationTimeout`：5 秒未收到回复 → server 端关闭连接（close code 1008）
- `-32012 SubprotocolMismatch`：WebSocket subprotocol 不是 `autoagent.v1` → 在 WebSocket upgrade 阶段就拒绝（HTTP 400），不进入 JSON-RPC

握手成功后才允许其他 method 调用；握手前发送其他 method → adapter 返回 `-32013 NotNegotiated` 并关闭。

## 八、扩展机制

### 自定义节点 attribute

引擎特定的属性放在 `engine_extras`：

```json
{
  "id": "...",
  "engine_extras": {
    "unity": { "canvas_render_mode": "ScreenSpaceOverlay", "attached_runtime_components": ["UnityEngine.UI.Button"], ... },
    "unreal": { "widget_class": "UImage", "attached_runtime_components": ["UButton"], ... },
    "godot": { "control_flags": [...], "attached_runtime_components": ["Button"], ... }
  }
}
```

不同引擎特有字段不污染主 schema，AI 通常无视，需要时按需读取。

### 自定义命令

引擎特有命令前缀 `engine.`：

```json
{ "method": "engine.unity.set_canvas_scaler", "params": {...}}
```

跨引擎统一任务 DSL **不应该使用** `engine.*` 命令。

## 九、性能约定

- `dump_tree` 在 500 节点内 < 50ms
- 节点 dump 增量更新（v0.2 引入）：每次只发 diff
- WebSocket 帧大小硬上限 1MB（超过 chunk）
- 一个 session 同时最多 100 个 in-flight request

## 十、安全

- 默认仅监听 `127.0.0.1`
- 启动时打印随机生成的 session token（可选 `--require-token` 开启鉴权）
- shipping 包默认禁用 adapter（编译期 `AUTOAGENT_ENABLED` 宏）
