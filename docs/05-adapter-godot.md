# 05 - Godot Adapter

> Godot 引擎 adapter 设计。GDScript 主路径，性能热点用 GDExtension（C++），Godot 4.3。

## 一、范围

- **支持版本**：Godot 4.3+
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
| `type` | `node.get_class()` 简名 |
| `engine_type` | `node.get_class()`（如 `Button` / `LineEdit`） |
| `parent_id` | parent control id |
| `visual.position` | `node.global_position` |
| `visual.size` | `node.size` |
| `visual.world_bounds` | `node.get_global_rect()` |
| `visual.visible` | `node.visible && node.is_visible_in_tree()` |
| `visual.alpha` | `node.modulate.a * node_path_alpha_chain()` |
| `visual.color` | `node.modulate` 或 `theme_color` |
| `behavior.interactable` | `node.mouse_filter != MOUSE_FILTER_IGNORE && !node.disabled` |
| `behavior.event_handlers` | 反射 `node.get_signal_connection_list("pressed")` 等 |
| `behavior.custom_scripts` | `node.get_script().resource_path` |

## 四、输入注入

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
        while peer.get_available_packet_count() > 0:
            var pkt = peer.get_packet().get_string_from_utf8()
            _on_message(peer, pkt)
```

样板代码比 Unity / UE 多但稳定。

## 六、Meta 注入

### Stable ID 存储
Godot 节点的 `Object.set_meta(key, value)` 持久化到 .tscn。

```gdscript
# 写
node.set_meta("autoagent_pinned_id", "login_button")
node.set_meta("autoagent_role", "submit_button")

# 读
if node.has_meta("autoagent_pinned_id"):
    return node.get_meta("autoagent_pinned_id")
```

Editor Plugin 提供 Inspector 扩展：选中 Control → "AutoAgent ID" 字段编辑。

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

#### Scene: `login.tscn`
- CanvasLayer
  - LoginPanel (Control + ColorRect background)
    - AccountInput (LineEdit)
    - PasswordInput (LineEdit, secret = true)
    - LoginButton (Button)
    - ErrorLabel (Label)
  - WelcomePanel (Control, visible = false)
    - WelcomeText (Label)

每个交互节点 set_meta autoagent_pinned_id（编辑器手动设或 .tscn 直接编辑）。

#### Scene: `poc_playground.tscn` (Phase 0)
4 动作覆盖。

## 九、已知坑（必读）

1. **`MOUSE_FILTER_IGNORE` 节点静默吞输入**：必须检查。
2. **`Input.parse_input_event` 全局生效**：所有 viewport 都收到。多窗口环境注意。
3. **GDScript 反射性能**：`get_property_list` / `get_method_list` 在大量节点上调用慢。1000 节点全 dump > 200ms。需缓存。
4. **WebSocketPeer 的 close code**：默认 1000；客户端意外断开返回 1006。adapter 都当作正常断开处理。
5. **Release export 反射裁剪**：上面已写。silent failure，必须自检。
6. **C# adapter 不行**：Godot 4.6 之前 C# 不支持 web export，且和 GDExtension 不能直接互调。Phase 1 选 GDScript 是对的。
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
