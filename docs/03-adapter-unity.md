# 03 - Unity Adapter

> Unity 引擎 adapter 设计。纯 C# 实现（不用预制件），Unity 2023.x LTS。

## 一、范围

- **支持版本**：Unity 2023.x LTS（2023.2.20f1+）；Unity 6 LTS 兼容（Phase 4 验证）
- **支持 UI 系统**：UGUI（uGUI / Canvas / RectTransform）— 第一优先级；UI Toolkit（VisualElement）— Phase 1 末加入
- **支持 Build Target**：Editor / Standalone Windows-Linux-Mac / IL2CPP
- **不支持**：NGUI / FairyGUI（Phase 4 评估）

## 二、Plugin 包结构

Unity Package Manager 格式（`adapters/unity/`）：

```
adapters/unity/
├─ package.json
├─ Runtime/
│  ├─ AutoAgent.Runtime.asmdef
│  ├─ Server/
│  │  ├─ WebSocketServer.cs        # 第三方库 websocket-sharp 封装
│  │  ├─ JsonRpcDispatcher.cs
│  │  └─ ProtocolHandler.cs
│  ├─ Reflection/
│  │  ├─ UGuiReflector.cs          # UGUI 树遍历
│  │  ├─ UIToolkitReflector.cs     # UI Toolkit 树遍历（Phase 1 末）
│  │  └─ NodeSerializer.cs
│  ├─ Input/
│  │  ├─ EngineInputDriver.cs      # EventSystem 派发
│  │  └─ OsInputDriver.cs          # SendInput（Phase 4）
│  ├─ Meta/
│  │  ├─ StableIdComponent.cs      # 挂到 GameObject 上的 MonoBehaviour
│  │  ├─ IdAllocator.cs
│  │  └─ OrphanTracker.cs
│  ├─ Screenshot/
│  │  └─ ScreenshotCapturer.cs
│  └─ AutoAgentBootstrap.cs        # 启动入口（[RuntimeInitializeOnLoadMethod]）
├─ Editor/
│  ├─ AutoAgent.Editor.asmdef
│  └─ StableIdInspector.cs         # Inspector UI for pin ID
└─ Tests/
   ├─ Runtime/
   └─ Editor/
```

## 三、UI 树反射

### UGUI（主路径）

**入口**：所有 `Canvas` 组件 → 遍历其下 `RectTransform` 子树。

```csharp
// 伪代码
foreach (var canvas in GameObject.FindObjectsOfType<Canvas>(includeInactive: true)) {
    yield return WalkRectTransform(canvas.transform);
}

IEnumerable<NodeData> WalkRectTransform(Transform t) {
    var rt = t as RectTransform;
    if (rt == null) yield break;
    yield return BuildNodeData(rt);
    foreach (Transform child in t) {
        foreach (var n in WalkRectTransform(child)) yield return n;
    }
}
```

### 节点字段映射

| Schema 字段 | Unity 来源 |
|---|---|
| `id` | `StableIdComponent.Id`（pinned）or `Hash(transformPath + name + type)` |
| `type` | 主组件类型简名（`Button` / `Image` / `Text` / `InputField` ...） |
| `engine_type` | `component.GetType().FullName` |
| `parent_id` | 父节点的 id |
| `children_ids` | 子节点 id 列表 |
| `visual.position` | `rectTransform.anchoredPosition` |
| `visual.size` | `rectTransform.rect.size` |
| `visual.anchor` | `rectTransform.anchorMin` |
| `visual.world_bounds` | RectTransformUtility.PixelAdjustRect → screen rect |
| `visual.visible` | `gameObject.activeInHierarchy && canvasRenderer.GetAlpha() > 0` |
| `visual.alpha` | `CanvasRenderer.GetAlpha()` × 父链 CanvasGroup.alpha |
| `visual.color` | `Image.color` / `Text.color` |
| `visual.sprite_ref` | `Image.sprite` 的 `AssetDatabase.GetAssetPath`（Editor）/ `sprite.name`（Runtime） |
| `behavior.interactable` | `Selectable.interactable` |
| `behavior.event_handlers` | 反射 `Button.onClick` / `Toggle.onValueChanged` 的 listener 列表 |
| `behavior.custom_scripts` | `GetComponents<MonoBehaviour>()` 排除 Unity 内置 |
| `meta.role` / `meta.intent` | `StableIdComponent.Meta` 字段 |

### UI Toolkit（Phase 1 末加入）

**入口**：所有 `UIDocument` → `rootVisualElement.Query<VisualElement>().ToList()`

字段映射差异（无 RectTransform，用 `worldBound`）。两套 UI 系统的节点共存于同一棵树（`engine_extras.unity.ui_system: "ugui" | "uitk"`）。

## 四、输入注入

### 引擎事件层（默认）

```csharp
public class EngineInputDriver {
    public bool Click(NodeData node, PointerButton button) {
        if (!IsInteractable(node)) throw new WidgetNotInteractable();

        var pointerData = new PointerEventData(EventSystem.current) {
            position = node.WorldCenterScreen,
            button = MapButton(button)
        };

        // 模拟完整 down → up 序列以触发 IPointerClickHandler
        ExecuteEvents.Execute<IPointerDownHandler>(node.GameObject, pointerData, ExecuteEvents.pointerDownHandler);
        ExecuteEvents.Execute<IPointerUpHandler>(node.GameObject, pointerData, ExecuteEvents.pointerUpHandler);
        ExecuteEvents.Execute<IPointerClickHandler>(node.GameObject, pointerData, ExecuteEvents.pointerClickHandler);
        return true;
    }

    public bool SendText(NodeData node, string text, bool clearFirst) {
        var input = node.GameObject.GetComponent<TMP_InputField>()
                 ?? (Component)node.GameObject.GetComponent<InputField>();
        if (input == null) throw new WidgetNotInteractable("not an input field");
        if (clearFirst) SetInputText(input, "");
        AppendInputText(input, text);
        // 触发 onValueChanged + onEndEdit
        return true;
    }

    public bool Drag(NodeData from, NodeData to, int durationMs) {
        // OnBeginDrag → 多帧 OnDrag（按 durationMs 分帧）→ OnEndDrag → OnDrop
        ...
    }
}
```

### OS 级输入（Phase 4）

Windows: P/Invoke `SendInput`；Mac: 调用 `CGEventCreateMouseEvent`（through native plugin）。

## 五、WebSocket 服务

第三方库 **`websocket-sharp`**（MIT, IL2CPP 兼容已验证）。

```csharp
public class AutoAgentBootstrap {
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Init() {
        if (!ShouldEnable()) return; // 配置 / 编译宏控制
        var server = new WebSocketServer("ws://127.0.0.1:27842");
        server.AddWebSocketService<ProtocolHandler>("/");
        server.Start();
    }
}

public class ProtocolHandler : WebSocketBehavior {
    // 在 OnHandshake 阶段校验 Sec-WebSocket-Protocol，必须包含 autoagent.v1
    protected override void OnHandshake() {
        var requested = Context.Headers["Sec-WebSocket-Protocol"];
        if (string.IsNullOrEmpty(requested) ||
            !requested.Split(',').Select(s => s.Trim()).Contains("autoagent.v1")) {
            // websocket-sharp: 在 OnHandshake 抛错 → 自动 close with 1002 ProtocolError
            throw new InvalidOperationException("subprotocol mismatch: require autoagent.v1");
        }
        // websocket-sharp 自动在 response Header 回写选定 subprotocol（首个匹配项）
    }

    protected override void OnOpen() {
        // 握手成功后，等待 server 发起 negotiate_version；
        // 5 秒未收到则关闭（close code 1008 PolicyViolation）
        StartNegotiationTimeoutWatchdog(TimeSpan.FromSeconds(5));
    }
}
```

**线程模型**：
- WebSocket 库在自己线程接收消息
- 引擎 API 调用必须切回主线程（用 `MainThreadDispatcher` queue）
- 响应通过 queue 推回 WebSocket 线程发出

## 六、Meta 注入机制

### StableIdComponent
挂到任意 GameObject 的 MonoBehaviour：

```csharp
public class StableIdComponent : MonoBehaviour {
    [SerializeField] public string PinnedId;        // 美术/程序员手动 pin
    [SerializeField] public string AutoHashId;      // 框架自动生成
    [SerializeField] public string Role;
    [SerializeField] public string Intent;
    [SerializeField] public List<string> Tags;

    public string Id => !string.IsNullOrEmpty(PinnedId) ? PinnedId : AutoHashId;
    public string Source => !string.IsNullOrEmpty(PinnedId) ? "pinned" : "hash";
}
```

### IdAllocator
框架启动时遍历所有 RectTransform，给每个节点：
1. 已有 `StableIdComponent.PinnedId` → 直接用
2. 否则 → 计算 `Hash(transformPath + gameObject.name + 主组件类型)` → 写入 `AutoHashId`
3. 检测冲突 → 在重复节点上加序号后缀

### OrphanTracker
持久化"上次扫描看到的 ID 列表"到 `Library/AutoAgent/last_scan.json`。每次新扫描比对，找不到的 ID 标 orphan。

### Editor Inspector
`StableIdInspector.cs`：在 GameObject Inspector 下显示一个 "Pin AutoAgent ID" 按钮，输入框 + apply。

## 七、IL2CPP 兼容

### link.xml
模板放在 `Runtime/Resources/AutoAgent.link.xml`：

```xml
<linker>
  <assembly fullname="UnityEngine.UI">
    <type fullname="UnityEngine.EventSystems.*" preserve="all"/>
  </assembly>
  <assembly fullname="Assembly-CSharp">
    <type fullname="*" preserve="methods" required="false"/>
  </assembly>
</linker>
```

用户业务代码的 MonoBehaviour 反射调用需要用户自己加 preserve（文档说明）。

### AOT 警告
泛型方法 + 值类型参数避免使用。`Newtonsoft.Json` 替代 `System.Text.Json`（IL2CPP 更稳）。

## 八、测试 Fixture（用户准备）

### `fixtures/unity-test-project/`
最小 Unity 项目，包含：

#### Scene: `LoginScene.unity`
- Main Camera
- Canvas (Screen Space - Overlay)
  - LoginPanel (Image, RectTransform)
    - AccountInput (TMP_InputField)
    - PasswordInput (TMP_InputField)
    - LoginButton (Button + Image + Text)
    - ErrorLabel (TMP_Text, initially empty)
  - WelcomePanel (initially inactive)
    - WelcomeText (TMP_Text)

每个交互元素挂 `StableIdComponent`，PinnedId 分别为：
`login_panel / account_input / password_input / login_button / error_label / welcome_panel / welcome_text`

#### Scene: `PocPlaygroundScene.unity` (Phase 0)
覆盖 4 动作：
- `click_target` (Button) — click 验证
- `text_target` (TMP_InputField) — send_text 验证
- `drag_source` + `drag_target` (RawImage 实现 IBeginDragHandler/IDragHandler/IEndDragHandler/IDropHandler) — drag 验证
- `scroll_view` (ScrollView with 30 items) — scroll 验证

#### `Packages/manifest.json`
依赖 `com.autoagent.unity`（local file path 或 git URL）。

## 九、已知坑（必读）

1. **EventSystem 必须存在**：场景里没有 EventSystem 时模拟点击会静默失败。adapter 启动时检查 + 缺失时告警。
2. **PointerEventData.position 用 screen 坐标**，不是 world / local。Camera 渲染模式要正确转换。
3. **TMP_InputField 的 text 直接赋值不触发 onValueChanged**。必须用 `ProcessEvent` 或 `text + onEndEdit?.Invoke()` 配合。
4. **Drag 序列必须分帧**：单帧内 OnBeginDrag → OnDrag → OnEndDrag 部分 IDragHandler 实现会出问题（如 Slider）。用 coroutine。
5. **Canvas 的 sortingOrder 影响射线**。多 Canvas 时 RaycastAll 优先返回最高 sortingOrder。
6. **CanvasGroup 链条上的 alpha=0 或 interactable=false 让节点 visible 但不可点**。`interactable` 字段要遍历父链 CanvasGroup 计算。
7. **StableIdComponent 不能挂到 prefab 实例的根**（用户原始约束："不用预制件"），但子物体上 OK。
8. **IL2CPP 下 websocket-sharp 偶发卡顿**：keep-alive 频率调到 10s（非默认 30s）。
9. **Scene 切换时**：必须 `[RuntimeInitializeOnLoadMethod]` 重新 attach；老的 WebSocket 在 `OnApplicationQuit` 关掉。

## 十、性能目标

- `dump_tree`（200 节点）< 30ms
- `click` 端到端（含 WebSocket 往返）< 50ms
- 常驻内存 < 30MB
- 帧率影响 < 1FPS（不调用时）

## 十一、Phase 1 出口标准

1. login MVP case 通过（手动跑一次成功）
2. CI 全绿（unit + integration + e2e in Unity headless）
3. `dump_tree` / `click` / `send_text` / `drag` / `scroll` / `take_screenshot` / `wait_for` / `pin_id` 全部 tool 实现
4. IL2CPP build 验证通过
5. 三类属性分离权限校验通过（写 visual 被拒绝）
