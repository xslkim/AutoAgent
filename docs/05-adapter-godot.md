# 05 - Godot Adapter

> Godot 引擎 adapter 设计。GDScript 主路径，性能热点用 GDExtension（C++），Godot 4.6。

## 一、范围

- **支持版本**：Godot 4.6+
- **支持 UI 系统**：Control 节点（CanvasLayer / Control / Container 树）
- **支持 Build**：Editor / Debug Export / Release Export
- **支持平台**：Windows / Linux / macOS

## 二、Plugin 结构

Godot addon 格式（`adapters/godot/addons/autoagent/`）：

```
adapters/godot/
└─ addons/
   └─ autoagent/
      ├─ plugin.cfg
      ├─ plugin.gd                    # EditorPlugin 入口
      ├─ runtime/
      │  ├─ autoagent.gd              # autoload singleton
      │  ├─ server/
      │  │  ├─ websocket_server.gd
      │  │  └─ protocol_handler.gd
      │  ├─ reflection/
      │  │  ├─ control_reflector.gd
      │  │  ├─ class_db_cache.gd      # release export 反射缺口对策
      │  │  └─ node_serializer.gd
      │  ├─ input/
      │  │  └─ engine_input_driver.gd
      │  ├─ meta/
      │  │  ├─ stable_id.gd            # Resource 类型，attach 到 Control.set_meta
      │  │  └─ id_allocator.gd
      │  └─ screenshot/
      │     └─ capturer.gd
      ├─ editor/
      │  ├─ stable_id_inspector.gd
      │  └─ icons/
      └─ tests/
         ├─ unit/
         └─ scenes/
```

## 三、UI 树反射

> **前提（与 [00 §四 程序员搭建边界](00-product-overview.md) / [01 §三](01-protocol-spec.md) 对齐）**：fixture `.tscn` 里**只放视觉骨架**——`Control` / `TextureRect` / `ColorRect` / `Label` / `Container` / `VBoxContainer` / `HBoxContainer` 等纯显示节点。**不放任何交互 Control 子类**（`Button` / `LineEdit` / `HSlider` / `VSlider` / `CheckBox` / `CheckButton` / `OptionButton` / `ScrollContainer` / `ItemList` / `Tree`）。
>
> **Godot 模型特殊性**：Godot 的节点 class 是静态的，无法像 Unity 那样 AddComponent，也不能像 UE 那样直接 SetContent 包裹。AI 必须走"**替换 + 视觉迁移**"路径（§六-A）：在 `_ready()` 里 free 原 TextureRect 节点，instantiate Button，把 TextureRect 的 texture 通过 `add_theme_stylebox_override("normal", StyleBoxTexture)` 转给 Button，让视觉保持一致。
>
> 因此反射的 `type` 字段在 fixture 阶段是 `TextureRect` / `ColorRect` / `Label`；AI `_ready()` 后变成 `Button` / `LineEdit` / `ScrollContainer`（节点 class 已变更）。

### 入口
所有 `CanvasLayer` 下的 `Control` 节点。

```gdscript
extends Node
class_name ControlReflector

func dump_all() -> Array:
    var result: Array = []
    var roots = get_tree().get_nodes_in_group("autoagent_ui_root")
    if roots.is_empty():
        # fallback: 全部 Viewport 下的 CanvasLayer
        roots = _find_canvas_layers(get_tree().root)
    for root in roots:
        _walk(root, "", result)
    return result

func _walk(node: Node, parent_id: String, out: Array) -> void:
    if node is Control:
        var nd = _build_node_data(node, parent_id)
        out.append(nd)
        for child in node.get_children():
            _walk(child, nd.id, out)
```

### 节点字段映射

| Schema 字段 | Godot 来源 |
|---|---|
| `id` | `node.get_meta("autoagent_pinned_id")` or hash |
| `type` | `node.get_class()` 简名（fixture 阶段：`TextureRect` / `ColorRect` / `Label` 等；AI `_ready()` 替换后：`Button` / `LineEdit` / ...） |
| `engine_type` | `node.get_class()` |
| `parent_id` | parent control id |
| `visual.position` | `node.global_position` |
| `visual.size` | `node.size` |
| `visual.world_bounds` | `node.get_global_rect()` |
| `visual.visible` | `node.visible && node.is_visible_in_tree()` |
| `visual.alpha` | `node.modulate.a * node_path_alpha_chain()` |
| `visual.color` | `node.modulate` 或 `theme_color` |
| `behavior.interactable` | `node.mouse_filter != MOUSE_FILTER_IGNORE && !node.disabled` |
| `behavior.raycast_target` | `node.mouse_filter != Control.MOUSE_FILTER_IGNORE` |
| `behavior.attached_components` | Godot 没有"组件挂载"。dump 时序列化"AI 替换后的节点 class"（`Button` / `LineEdit` / ...），与 `type` 一致。便于 CI 校验 logical_role |
| `behavior.event_handlers` | 反射 `node.get_signal_connection_list("pressed")` 等 |
| `behavior.custom_scripts` | `node.get_script().resource_path` |
| `meta.logical_role` | `node.get_meta("autoagent_logical_role")` |
| `meta.state_sprites` | `node.get_meta("autoagent_state_sprites")` — Dictionary 形式 `{ normal: Texture2D, hover: Texture2D, ... }` |

## 四、输入注入

> **前置约束**：`click` / `send_text` / `scroll` 都要求 AI 已经走"替换 + 视觉迁移"把 fixture 的 TextureRect 替换成 Button / LineEdit / ScrollContainer。fixture 阶段直接对 TextureRect 发 `click` → `node.button_index` / `node.text` 等属性不存在 → adapter 返回 `-32002 WidgetNotInteractable`，错误信息明确提示"节点 class 仍是 TextureRect，需要先替换为 Button/LineEdit/..."。

### 引擎事件层（默认）

```gdscript
func click(node: Control, button: int = MOUSE_BUTTON_LEFT) -> bool:
    if node.mouse_filter == Control.MOUSE_FILTER_IGNORE:
        push_error("Widget MOUSE_FILTER_IGNORE")
        return false

    var center = node.global_position + node.size * 0.5

    var ev_down = InputEventMouseButton.new()
    ev_down.button_index = button
    ev_down.pressed = true
    ev_down.position = center
    ev_down.global_position = center
    Input.parse_input_event(ev_down)

    var ev_up = InputEventMouseButton.new()
    ev_up.button_index = button
    ev_up.pressed = false
    ev_up.position = center
    ev_up.global_position = center
    Input.parse_input_event(ev_up)
    return true

func send_text(node: LineEdit, text: String, clear_first: bool) -> bool:
    if not node is LineEdit:
        return false
    if clear_first:
        node.text = ""
        node.text_changed.emit("")
    node.text = node.text + text
    node.text_changed.emit(node.text)
    node.text_submitted.emit(node.text)  # 可选
    return true

func drag(from_node: Control, to_node: Control, duration_ms: int) -> bool:
    # OnGUI drag 逻辑：start at from center, multi-frame moves, release at to center
    ...
```

### OS 级（Phase 4）
通过 GDExtension 调 `SendInput` / `XTest`。

## 五、WebSocket Server

Godot 4 已弃用 `WebSocketServer` 类，需要 `TCPServer + WebSocketPeer.accept_stream`：

```gdscript
extends Node
class_name WebSocketServer

var _tcp := TCPServer.new()
var _peers: Array[WebSocketPeer] = []

func start(port: int) -> int:
    return _tcp.listen(port, "127.0.0.1")

func _process(_delta: float) -> void:
    # accept new
    while _tcp.is_connection_available():
        var conn = _tcp.take_connection()
        var peer := WebSocketPeer.new()
        # 强制 client 必须请求 autoagent.v1 subprotocol
        peer.supported_protocols = PackedStringArray(["autoagent.v1"])
        peer.accept_stream(conn)
        _peers.append(peer)

    # poll all
    for peer in _peers:
        peer.poll()
        var state = peer.get_ready_state()
        # 在 OPEN 之后立即校验 selected_protocol
        if state == WebSocketPeer.STATE_OPEN \
                and peer.get_selected_protocol() != "autoagent.v1":
            peer.close(1002, "subprotocol mismatch: require autoagent.v1")
            continue
        
        # 握手成功后启动 negotiate_version 5s watchdog（与 01 §七 一致）
        if state == WebSocketPeer.STATE_OPEN and not _negotiate_watchdog_running.has(peer):
            _start_negotiate_timeout(peer)
        
        while peer.get_available_packet_count() > 0:
            var pkt = peer.get_packet().get_string_from_utf8()
            _on_message(peer, pkt)

func _start_negotiate_timeout(peer: WebSocketPeer) -> void:
    _negotiate_watchdog_running[peer] = true
    await get_tree().create_timer(5.0).timeout
    if not _negotiate_done.has(peer):
        peer.close(1008, "negotiate_version timeout: no response in 5s")
        _remove_peer(peer)

func _on_negotiate_received(peer: WebSocketPeer) -> void:
    _negotiate_done[peer] = true
```

样板代码比 Unity / UE 多但稳定。

## 六、Meta 注入

### Stable ID 存储
Godot 节点的 `Object.set_meta(key, value)` 持久化到 .tscn。框架支持三种来源：

| 来源 | Meta key | 设置方式 |
|---|---|---|
| `pinned` | `autoagent_pinned_id` | 程序员在 Inspector / Editor Plugin 手动填写 |
| `auto` | `autoagent_declared_id` | 框架扫描 GDScript 中的 `@export var autoagent_id: String` 或脚本级注解自动收集 |
| `hash` | `autoagent_hash_id` | 框架基于 `node.get_path() + node.name + node.get_class()` 自动计算 |

**`auto` 来源的收集机制**：框架在启动时扫描所有挂载脚本的 `@export` 变量，查找命名符合 `autoagent_id` 或 `auto_agent_id` 约定的字符串字段。这与 UE 的 `UPROPERTY(meta=(AutoAgentId="..."))` 和 Unity 的 `[AutoAgentId("...")]` 特性等价——程序员在源码中声明，框架自动收集。

```gdscript
# 写（程序员搭 fixture 时设置）
node.set_meta("autoagent_pinned_id", "login_button_bg")
node.set_meta("autoagent_logical_role", "button")
node.set_meta("autoagent_role", "submit_button")
node.set_meta("autoagent_state_sprites", {
    "normal":   preload("res://assets/ui/btn_login_normal.png"),
    "hover":    preload("res://assets/ui/btn_login_hover.png"),
    "pressed":  preload("res://assets/ui/btn_login_pressed.png"),
    "disabled": preload("res://assets/ui/btn_login_disabled.png"),
})

# 框架自动收集来源 2 (auto)：扫描 @export var autoagent_id
# 业务代码中声明:
# @export var autoagent_id: String = "dynamic_item_001"
# → 框架在 dump 时将该值写入 autoagent_declared_id

# 读（优先级: pinned > auto > hash）
func _resolve_stable_id(node: Node) -> Dictionary:
    if node.has_meta("autoagent_pinned_id"):
        return {"id": node.get_meta("autoagent_pinned_id"), "source": "pinned"}
    if node.has_meta("autoagent_declared_id"):
        return {"id": node.get_meta("autoagent_declared_id"), "source": "auto"}
    return {"id": _compute_hash_id(node), "source": "hash"}
```

Editor Plugin 提供 Inspector 扩展：选中 Control → "AutoAgent ID / LogicalRole / StateSprites" 字段编辑（LogicalRole 限制为 [01 §三 logical_role 取值表](01-protocol-spec.md) 合法值）。

### A. AI 替换节点的视觉迁移路径

```gdscript
# AI 在 _ready() 里实现（业务代码，不是 adapter 代码）
func _replace_with_button(bg_node: TextureRect, on_pressed: Callable) -> Button:
    var parent := bg_node.get_parent()
    var pos := bg_node.position
    var sz  := bg_node.size
    var anc_l := bg_node.anchor_left
    var anc_t := bg_node.anchor_top
    var anc_r := bg_node.anchor_right
    var anc_b := bg_node.anchor_bottom

    # 从 state_sprites meta 取多状态视觉
    var ss: Dictionary = bg_node.get_meta("autoagent_state_sprites")

    var btn := Button.new()
    btn.name = bg_node.name
    btn.flat = true  # 关掉 Button 默认背景
    btn.add_theme_stylebox_override("normal",   _styleboxify(ss.normal))
    btn.add_theme_stylebox_override("hover",    _styleboxify(ss.hover))
    btn.add_theme_stylebox_override("pressed",  _styleboxify(ss.pressed))
    btn.add_theme_stylebox_override("disabled", _styleboxify(ss.disabled))

    # 转移 meta（pinned_id / logical_role）
    btn.set_meta("autoagent_pinned_id", bg_node.get_meta("autoagent_pinned_id"))
    btn.set_meta("autoagent_logical_role", "button")

    # 替换
    var idx := bg_node.get_index()
    parent.remove_child(bg_node)
    bg_node.queue_free()
    parent.add_child(btn)
    parent.move_child(btn, idx)
    btn.position = pos; btn.size = sz
    btn.anchor_left = anc_l; btn.anchor_top = anc_t
    btn.anchor_right = anc_r; btn.anchor_bottom = anc_b

    btn.pressed.connect(on_pressed)
    return btn

func _styleboxify(tex: Texture2D) -> StyleBoxTexture:
    var sb := StyleBoxTexture.new()
    sb.texture = tex
    return sb
```

**关键约束（写进 [06 §二 防护 0](06-visual-regression.md)）**：
- 这条路径修改 `.tscn` 节点树结构，正常情况下属于"AI 不允许改结构"违规。豁免规则与 UE 的"包裹"路径同：**新节点的 type 必须能在 logical_role 取值表里匹配 + state_sprites 完整迁移 + position/size/anchor 一致 → 不算结构破坏**（dump 前后 diff gate 校验）。
- pinned_id 必须显式转移到新节点（如上 `btn.set_meta("autoagent_pinned_id", ...)`），否则 orphan tracker 报警。

### Hash ID
`(node.get_path() as String + node.name + node.get_class()).md5_text().substr(0, 12)`

## 七、Release Export 反射缺口（关键）

**Issue [godotengine#99722](https://github.com/godotengine/godot/issues/99722)**：`get_property_list()` 在 release export 中会丢失部分 metadata（自定义类继承链、脚本路径）。

### 对策：自维护 ClassDB 缓存

构建期扫描所有 .gd 脚本，生成 `class_db_cache.gd`：

```gdscript
# 自动生成
const CLASS_DB := {
    "LoginController": {
        "extends": "Control",
        "script_path": "res://scripts/login_controller.gd",
        "exported_properties": ["account", "password"],
        "methods": ["login", "reset_form"],
    },
    ...
}
```

运行时优先查 `CLASS_DB`，缺失时再 fallback `get_property_list()`。

### Release 自检脚本

adapter 启动时跑一次 self-check：尝试反射几个 known control，比对 dev / release 输出。失败立刻 push warning 到 MCP server。

## 八、测试 Fixture（用户准备）

### `fixtures/godot-test-project/`

#### Scene: `login.tscn`（**只放视觉骨架**，无任何 Button / LineEdit）
- CanvasLayer
  - LoginPanel (Control + ColorRect background) — `autoagent_logical_role=image_only`
    - AccountInputBg (TextureRect)               — `autoagent_logical_role=input`
    - PasswordInputBg (TextureRect)              — `autoagent_logical_role=input`
    - LoginButtonBg (TextureRect)                — `autoagent_logical_role=button` + state_sprites
      - LoginButtonLabel (Label "Login")         — `autoagent_logical_role=text_display`
    - ErrorLabel (Label, initially empty)        — `autoagent_logical_role=text_display`
  - WelcomePanel (Control, visible = false)      — `autoagent_logical_role=image_only`
    - WelcomeText (Label)                        — `autoagent_logical_role=text_display`

每个节点 set_meta `autoagent_pinned_id` + `autoagent_logical_role`（编辑器手动设或 .tscn 直接编辑）。state_sprites 在 button / input 节点上设。

**关键**：fixture 加载完，整棵树 **没有任何 Button / LineEdit / ScrollContainer**；AI 在 `_ready()` 里走 §六-A 路径替换节点 class。

#### Scene: `poc_playground.tscn` (Phase 0)
4 动作视觉骨架覆盖（同前两引擎模式）：
- `click_target` (TextureRect, logical_role=button)
- `text_target` (TextureRect, logical_role=input)
- `drag_source` + `drag_target` (TextureRect)
- `scroll_container` (TextureRect 容器 + 30 个 TextureRect item, logical_role=scroll_container)

PoC 测试代码自行实现节点替换路径。

## 九、已知坑（必读）

1. **`MOUSE_FILTER_IGNORE` 节点静默吞输入**：必须检查。
2. **`Input.parse_input_event` 全局生效**：所有 viewport 都收到。多窗口环境注意。
3. **GDScript 反射性能**：`get_property_list` / `get_method_list` 在大量节点上调用慢。1000 节点全 dump > 200ms。需缓存。
4. **WebSocketPeer 的 close code**：默认 1000；客户端意外断开返回 1006。adapter 都当作正常断开处理。
5. **Release export 反射裁剪**：上面已写。silent failure，必须自检。
6. **Godot C# 支持受限**：Godot 4.6 C# web export 支持仍有限，且和 GDExtension 不能直接互调。Phase 1 选 GDScript 是对的。
7. **theme_override vs theme**：`Button.add_theme_color_override("font_color", ...)` 和 `theme.get_color("font_color", "Button")` 不同。dump 时优先 override。
8. **Container 自动布局会覆盖 size 设置**：测试 fixture 里的固定布局用 anchor + offset，不要依赖 HBoxContainer 这种容器的自动 size。
9. **autoload singleton 的初始化时序**：`_ready` 比第一个 scene 早。`get_tree().root` 此时只有 root 没有用户场景。要等到 `tree_changed` 第一次触发再启动。
10. **跨场景持久化**：autoload singleton 跨场景存活；scene 切换时清理 cache。

## 十、Phase 3 出口标准

1. login MVP 跨三引擎一致通过
2. CI 全绿（GUT 单元测试 + e2e）
3. 所有 tool 实现
4. Release export 验证（自检脚本通过 + 4 动作 e2e 通过）
5. ClassDB cache 构建脚本可用

## 十一、性能目标

- `dump_tree`（200 节点）< 80ms（GDScript 慢）
- `click` 端到端 < 80ms
- 常驻 < 20MB
- 性能瓶颈节点 dump 用 GDExtension 重写（Phase 3 末）
