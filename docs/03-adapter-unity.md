# 03 - Unity Adapter

> Unity 引擎 adapter 设计。**业务逻辑纯 C#**，Unity 2023.x LTS。
>
> **"不用预制件 / 纯 C#"的精确语义**（与 [00 §四 / §硬约束](00-product-overview.md) 对齐）：
> - ✅ **允许** `.unity` scene / `.prefab` 作为**纯数据的视觉骨架容器**——含 RectTransform / Image / TMP_Text / StableIdComponent (meta) 等。
> - ❌ **禁止** 在 prefab / scene 里序列化 UnityEvent 调用（如 Button.onClick 在 Inspector 里拖引用 LoginController.OnLogin）——所有事件绑定必须在 C# `Awake()` 里 `AddListener(...)` 完成。
> - ❌ **禁止** Visual Scripting / Bolt / Playmaker 节点图。
>
> 这条约束让 fixture .unity 文件 git-diff 可读（无 UnityEvent 序列化的 GUID 漂移），同时逻辑全部在 .cs 里被源码审计扫到。

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

> **前提（与 [00 §四 程序员搭建边界](00-product-overview.md) / [01 §三](01-protocol-spec.md) 对齐）**：fixture `.unity` 文件里**只放视觉骨架**——`Canvas` / `RectTransform` / `Image` / `RawImage` / `TMP_Text` / 容器节点。**不挂任何 Selectable 子类**（`Button` / `Toggle` / `Slider` / `InputField` 等）。这些控件由 AI 在源码 `Awake()` 里 `AddComponent` 添加。
>
> 因此反射的 `type` 字段绝大多数情况下是 `Image` / `TMP_Text` / `RectTransform`；`behavior.attached_components` 字段在 fixture 加载完是空的，AI 代码运行后才会包含 `Button` / `TMP_InputField` 等。

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
| `type` | **主图形组件类型简名**（fixture 阶段绝大多数是 `Image` / `RawImage` / `TMP_Text`；无图形组件的容器返回 `RectTransform`）。**不再使用 Selectable 子类作 type**——因为 fixture 不挂这些 |
| `engine_type` | 主图形组件的 `component.GetType().FullName` |
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
| `behavior.interactable` | 若有 `Selectable` 子类（AI AddComponent 后）：`Selectable.interactable`；否则 `false` |
| `behavior.raycast_target` | `Graphic.raycastTarget` |
| `behavior.attached_components` | 运行时枚举 `GetComponents<Component>()` 过滤出 `Selectable` 子类 / `ScrollRect` / `RectMask2D` 等"逻辑控件"组件（白名单，详见 §三末） |
| `behavior.event_handlers` | 反射已挂载的 `Button.onClick` / `Toggle.onValueChanged` 等 listener 列表（fixture 阶段为空） |
| `behavior.custom_scripts` | `GetComponents<MonoBehaviour>()` 排除 Unity 内置 |
| `meta.logical_role` | `StableIdComponent.LogicalRole` 字段（fixture 阶段由程序员填） |
| `meta.role` / `meta.intent` | `StableIdComponent.Meta` 字段 |
| `meta.state_sprites` | `StableIdComponent.StateSprites` 字段（`{ normal, hover, pressed, ... } → Sprite`，序列化时输出 AssetPath） |

### `attached_components` 白名单

为避免把所有 MonoBehaviour 都序列化，adapter 维护一份"逻辑控件组件白名单"，只这些组件出现在 `behavior.attached_components`：

```
UnityEngine.UI.Button / Toggle / Slider / Scrollbar / Dropdown / InputField
TMPro.TMP_InputField / TMP_Dropdown
UnityEngine.UI.ScrollRect / RectMask2D / Mask
（未来扩展：用户在 ~/.autoagent/config.toml 的 [unity.attached_components_whitelist] 加自定义）
```

CI 校验：若节点 `meta.logical_role == "button"` 但 `attached_components` 不含 `Button`（或等价），视为 AI 没正确实现 → e2e fail。

### UI Toolkit（Phase 1 末加入）

**入口**：所有 `UIDocument` → `rootVisualElement.Query<VisualElement>().ToList()`

字段映射差异（无 RectTransform，用 `worldBound`）。两套 UI 系统的节点共存于同一棵树（`engine_extras.unity.ui_system: "ugui" | "uitk"`）。

## 四、输入注入

### 引擎事件层（默认）

> **前置约束**：`Click` / `SendText` / `Drag` / `Scroll` 都要求 AI 已经在源码里给目标 GameObject `AddComponent` 对应的引擎控件（`Button` / `TMP_InputField` / 实现 `IDragHandler` 的脚本 / `ScrollRect`）。fixture 阶段直接调这些会抛 `-32002 WidgetNotInteractable`。错误信息明确提示"节点未挂 Button / InputField / ScrollRect 等"——这是 AI 自检的关键信号。

```csharp
public class EngineInputDriver {
    public bool Click(NodeData node, PointerButton button) {
        // IsInteractable 同时检查：节点存在 + raycastTarget + Selectable.interactable（若挂了）
        if (!IsInteractable(node)) throw new WidgetNotInteractable(
            "Node has no Selectable component attached — AI must AddComponent<Button>/Toggle/... first");

        var pointerData = new PointerEventData(EventSystem.current) {
            position = node.WorldCenterScreen,
            button = MapButton(button)
        };

        // 模拟完整 down → up 序列以触发 IPointerClickHandler
        // Button.OnPointerClick 是 IPointerClickHandler.OnPointerClick 的实现，所以 AI AddComponent<Button> 之后这套就工作
        ExecuteEvents.Execute<IPointerDownHandler>(node.GameObject, pointerData, ExecuteEvents.pointerDownHandler);
        ExecuteEvents.Execute<IPointerUpHandler>(node.GameObject, pointerData, ExecuteEvents.pointerUpHandler);
        ExecuteEvents.Execute<IPointerClickHandler>(node.GameObject, pointerData, ExecuteEvents.pointerClickHandler);
        return true;
    }

    public bool SendText(NodeData node, string text, bool clearFirst) {
        var input = node.GameObject.GetComponent<TMP_InputField>()
                 ?? (Component)node.GameObject.GetComponent<InputField>();
        if (input == null) throw new WidgetNotInteractable(
            "not an input field — AI must AddComponent<TMP_InputField> first");
        if (clearFirst) SetInputText(input, "");
        AppendInputText(input, text);
        // 触发 onValueChanged + onEndEdit
        return true;
    }

    public bool Drag(NodeData from, NodeData to, int durationMs) {
        // OnBeginDrag → 多帧 OnDrag（按 durationMs 分帧）→ OnEndDrag → OnDrop
        // 要求 from 节点挂了实现 IBeginDragHandler/IDragHandler/IEndDragHandler 的脚本
        ...
    }

    public bool Scroll(NodeData node, ScrollDirection dir, float amount) {
        var scrollRect = node.GameObject.GetComponent<ScrollRect>();
        if (scrollRect == null) throw new WidgetNotInteractable(
            "not a scroll container — AI must AddComponent<ScrollRect> first");
        // 修改 normalizedPosition 或 dispatch IScrollHandler
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
挂到任意 GameObject 的 MonoBehaviour（**注意**：这是 adapter 自己的 metadata 组件，**不是交互控件**，挂这个不违反"程序员不放控件"约束）：

```csharp
public class StableIdComponent : MonoBehaviour {
    [SerializeField] public string PinnedId;        // 美术/程序员手动 pin（来源 1: pinned）
    [SerializeField] public string AutoDeclaredId;  // 框架从代码注解自动收集（来源 2: auto）
    [SerializeField] public string AutoHashId;      // 框架自动 hash 计算（来源 3: hash，诊断用）
    [SerializeField] public string LogicalRole;     // button / input / slider / ... (见 01 协议 logical_role 取值表)
    [SerializeField] public string Role;
    [SerializeField] public string Intent;
    [SerializeField] public List<string> Tags;

    [Serializable] public class StateSpriteEntry { public string State; public Sprite Sprite; }
    [SerializeField] public List<StateSpriteEntry> StateSprites;  // normal/hover/pressed/disabled → Sprite

    public string Id => !string.IsNullOrEmpty(PinnedId) ? PinnedId
                      : !string.IsNullOrEmpty(AutoDeclaredId) ? AutoDeclaredId
                      : AutoHashId;
    public string Source => !string.IsNullOrEmpty(PinnedId) ? "pinned"
                          : !string.IsNullOrEmpty(AutoDeclaredId) ? "auto"
                          : "hash";
}
```

Inspector 自定义：`StableIdInspector.cs` 显示 LogicalRole 下拉（限制为 [01 §三 logical_role 取值表](01-protocol-spec.md) 的合法值）+ StateSprites 数组编辑器。

### IdAllocator
框架启动时遍历所有 RectTransform，给每个节点：
1. 已有 `StableIdComponent.PinnedId` → `stable_id_source = "pinned"`
2. 已有 `StableIdComponent.AutoDeclaredId`（由框架从代码注解 `[AutoAgentId("...")]` 或命名约定自动填充）→ `stable_id_source = "auto"`
3. 否则 → 计算 `Hash(transformPath + gameObject.name + 主组件类型)` → 写入 `AutoHashId`，`stable_id_source = "hash"`
4. 检测冲突 → 在重复节点上加序号后缀

**`auto` 来源的收集机制**：框架扫描 GameObject 上挂载的 MonoBehaviour 脚本，查找标有 `[AutoAgentId("id_string")]` 特性的字段或类，自动将其声明的 ID 填入 `AutoDeclaredId`。这与 UE 的 `UPROPERTY(meta=(AutoAgentId="..."))` 等价——程序员在源码中声明，框架自动收集，不需要 Inspector 手动 pin。

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
最小 Unity 项目，**只包含视觉骨架**（[00 §四 程序员搭建边界](00-product-overview.md)）：

#### Scene: `LoginScene.unity`
- Main Camera
- Canvas (Screen Space - Overlay) ← 容器组件 OK
  - LoginPanel (Image, RectTransform) — `logical_role=image_only`
    - AccountInputBg (Image)        — `logical_role=input`（不挂 InputField，AI 加）
      - AccountInputText (TMP_Text) — `logical_role=text_display`（占位字段，AI 写入用户输入）
    - PasswordInputBg (Image)       — `logical_role=input`
      - PasswordInputText (TMP_Text)— `logical_role=text_display`
    - LoginButtonBg (Image)         — `logical_role=button`（不挂 Button，AI 加）
      - LoginButtonLabel (TMP_Text "Login") — `logical_role=text_display`
    - ErrorLabel (TMP_Text, initially empty) — `logical_role=text_display`
  - WelcomePanel (Image, initially inactive) — `logical_role=image_only`
    - WelcomeText (TMP_Text)        — `logical_role=text_display`

每个节点挂 `StableIdComponent`，PinnedId / LogicalRole / StateSprites 分别为：

| PinnedId | LogicalRole | StateSprites（如适用） |
|---|---|---|
| `login_panel` | image_only | — |
| `account_input_bg` | input | { normal, focused } |
| `password_input_bg` | input | { normal, focused } |
| `login_button_bg` | button | { normal, hover, pressed, disabled } |
| `error_label` | text_display | — |
| `welcome_panel` | image_only | — |
| `welcome_text` | text_display | — |

**关键**：fixture 加载完，整棵树 **没有任何 `Selectable` 子类组件**；AI 写的 `LoginController.cs` 在 `Awake()` 里给 `account_input_bg` / `password_input_bg` `AddComponent<TMP_InputField>()`，给 `login_button_bg` `AddComponent<Button>()`，并设置 `raycastTarget=true`。

#### Scene: `PocPlaygroundScene.unity` (Phase 0)
4 动作的视觉骨架（同样不放控件，PoC 测试代码自行 AddComponent）：
- `click_target` (Image, logical_role=button) — click 验证（PoC 测试代码 AddComponent<Button>）
- `text_target` (Image + 子 TMP_Text, logical_role=input) — send_text 验证（PoC AddComponent<TMP_InputField>）
- `drag_source` + `drag_target` (RawImage, logical_role=drag_source/drop_target) — drag 验证（PoC 挂自实现 IBeginDragHandler/IDragHandler/IEndDragHandler/IDropHandler 脚本）
- `scroll_container` (Image 容器 + 30 个 Image item, logical_role=scroll_container) — scroll 验证（PoC AddComponent<ScrollRect> + AddComponent<RectMask2D>）

#### `Packages/manifest.json`
依赖 `com.autoagent.unity`（local file path 或 git URL）。

## 九、已知坑（必读）

1. **EventSystem 必须存在**：场景里没有 EventSystem 时模拟点击会静默失败。adapter 启动时检查 + 缺失时告警。
2. **PointerEventData.position 用 screen 坐标**，不是 world / local。Camera 渲染模式要正确转换。
3. **TMP_InputField 的 text 直接赋值不触发 onValueChanged**。必须用 `ProcessEvent` 或 `text + onEndEdit?.Invoke()` 配合。
4. **Drag 序列必须分帧**：单帧内 OnBeginDrag → OnDrag → OnEndDrag 部分 IDragHandler 实现会出问题（如 Slider）。用 coroutine。
5. **Canvas 的 sortingOrder 影响射线**。多 Canvas 时 RaycastAll 优先返回最高 sortingOrder。
6. **CanvasGroup 链条上的 alpha=0 或 interactable=false 让节点 visible 但不可点**。`interactable` 字段要遍历父链 CanvasGroup 计算。
7. **StableIdComponent 可以挂到任意 GameObject**（包括 prefab 子节点）。prefab 根节点也支持，但建议优先挂到具体 UI 元素上以获得更精确的 ID 绑定。
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
