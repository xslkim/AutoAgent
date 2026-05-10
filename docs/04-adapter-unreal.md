# 04 - Unreal Adapter

> Unreal 引擎 adapter 设计。纯 C++ 实现（不用蓝图），UE 5.6。

## 一、范围

- **支持版本**：UE 5.6
- **支持 UI 系统**：UMG（UUserWidget / UWidget 树）— 第一优先级；Slate 原生 SWidget — Phase 2 末加入
- **支持 Build Type**：Editor / Development / Shipping（Shipping 需编译期开关）
- **支持平台**：Windows Editor + Standalone；Linux Server（CI 用）

## 二、Plugin 结构

```
adapters/unreal/
├─ AutoAgent.uplugin
├─ Source/
│  ├─ AutoAgent/                # Runtime module
│  │  ├─ AutoAgent.Build.cs
│  │  ├─ Public/
│  │  │  ├─ AutoAgentSubsystem.h         # UGameInstanceSubsystem 入口
│  │  │  ├─ StableIdInterface.h          # UInterface for IDs
│  │  │  ├─ Server/
│  │  │  │  └─ WebSocketServer.h
│  │  │  ├─ Reflection/
│  │  │  │  ├─ UmgReflector.h
│  │  │  │  └─ NodeSerializer.h
│  │  │  ├─ Input/
│  │  │  │  └─ SlateInputDriver.h
│  │  │  └─ Meta/
│  │  │     └─ StableIdComponent.h       # UWidget 上的辅助 component
│  │  └─ Private/
│  │     └─ ... (corresponding .cpp)
│  └─ AutoAgentEditor/          # Editor module（pin ID UI）
│     └─ ...
├─ Resources/
│  └─ Icon128.png
└─ Tests/
   └─ ...
```

`AutoAgent.Build.cs` 依赖：`Core`, `CoreUObject`, `Engine`, `UMG`, `Slate`, `SlateCore`, `Json`, `JsonUtilities`, `Sockets`, `Networking`, `WebSockets`（UE 内置 LibWebSockets 封装）

## 三、UI 树反射

### UMG 主路径

**入口**：所有当前激活的 `UUserWidget`（通过 `UWidgetBlueprintLibrary::GetAllWidgetsOfClass`）→ 各自的 `WidgetTree` → 递归。

```cpp
void UUmgReflector::DumpAllWidgets(TArray<FNodeData>& OutNodes) {
    UWorld* World = GetWorld();
    TArray<UUserWidget*> Widgets;
    UWidgetBlueprintLibrary::GetAllWidgetsOfClass(
        World, Widgets, UUserWidget::StaticClass(), /*TopLevelOnly=*/false);

    for (UUserWidget* UserWidget : Widgets) {
        if (!UserWidget || !UserWidget->IsInViewport()) continue;
        WalkWidgetTree(UserWidget->WidgetTree, OutNodes, /*ParentId=*/TEXT(""));
    }
}

void UUmgReflector::WalkWidgetTree(UWidgetTree* Tree, TArray<FNodeData>& Out, FString ParentId) {
    if (!Tree) return;
    Tree->ForEachWidget([&](UWidget* W) {
        FNodeData Node = BuildNode(W, ParentId);
        Out.Add(Node);
        if (UPanelWidget* Panel = Cast<UPanelWidget>(W)) {
            for (int32 i = 0; i < Panel->GetChildrenCount(); ++i) {
                WalkChildren(Panel->GetChildAt(i), Out, Node.Id);
            }
        }
    });
}
```

### 节点字段映射

| Schema 字段 | UE 来源 |
|---|---|
| `id` | `IStableIdInterface::GetPinnedId(W)` or hash(`W->GetPathName()`) |
| `type` | Widget class 简名（`UButton` → `Button`） |
| `engine_type` | `W->GetClass()->GetPathName()` |
| `parent_id` | parent UWidget id |
| `children_ids` | UPanelWidget 子节点 id |
| `visual.position` | `W->GetCachedGeometry().Position` |
| `visual.size` | `W->GetCachedGeometry().Size` |
| `visual.world_bounds` | `W->GetCachedGeometry().GetAbsolutePositionAtCoordinates(...)` |
| `visual.visible` | `W->GetVisibility() != ESlateVisibility::Hidden && IsInViewport` |
| `visual.alpha` | `W->GetRenderOpacity()` |
| `visual.color` | `Image->GetColorAndOpacity()` 等组件特定 |
| `visual.sprite_ref` | `Image->Brush.GetResourceObject()->GetPathName()` |
| `behavior.interactable` | `W->GetIsEnabled()` && Visibility 接受输入 |
| `behavior.event_handlers` | `OnClicked.IsBound() ? ["OnClicked"] : []`（运行时反射） |

### Slate 原生（Phase 2 末加入）

`FSlateApplication::Get().GetAllVisibleWidgets()` 拿到 `TArray<TSharedRef<SWidget>>`，递归 `GetChildren()`。Schema 用相同字段，`engine_extras.unreal.is_slate = true` 区分。

## 四、输入注入

### Slate 引擎事件层

**关键**：`FSlateApplication::ProcessMouseButtonDownEvent` 必须在 GameThread 调。

```cpp
bool USlateInputDriver::Click(UWidget* Widget, EMouseButton Button) {
    if (!IsInGameThread()) {
        // Marshal 到 GameThread
        bool Result = false;
        FFunctionGraphTask::CreateAndDispatchWhenReady([&]() {
            Result = ClickInternal(Widget, Button);
        }, TStatId(), nullptr, ENamedThreads::GameThread)->Wait();
        return Result;
    }
    return ClickInternal(Widget, Button);
}

bool USlateInputDriver::ClickInternal(UWidget* Widget, EMouseButton Button) {
    auto SlateWidget = Widget->TakeWidget();
    auto Geometry = Widget->GetCachedGeometry();
    FVector2D Center = Geometry.GetAbsolutePosition() + Geometry.GetAbsoluteSize() * 0.5f;

    FPointerEvent Down(
        /*PointerIndex=*/0,
        /*ScreenSpacePosition=*/Center,
        /*LastScreenSpacePosition=*/Center,
        /*PressedButtons=*/TSet<FKey>{ MapButton(Button) },
        /*EffectingButton=*/MapButton(Button),
        /*WheelDelta=*/0.f,
        /*ModifierKeys=*/FModifierKeysState()
    );

    auto Reply = FSlateApplication::Get().ProcessMouseButtonDownEvent(
        FSlateApplication::Get().GetActiveTopLevelWindow(), Down);
    FSlateApplication::Get().ProcessMouseButtonUpEvent(Down);
    return Reply.IsEventHandled();
}
```

### 输入注入注意

- **Modal Widget**：弹窗等 modal 会拦截事件，必须先 `SetUserFocus`
- **Window 选择**：`GetActiveTopLevelWindow` 在 PIE 多 viewport 时可能错；用 `Widget->GetCachedWidget()->GetPaintSpaceGeometry()` 拿到正确 window
- **EditableTextBox 输入**：通过 `ProcessKeyCharEvent` 逐字符送入

### OS 级（Phase 4）

Windows `SendInput`；通过 native module 加载（不依赖 UE platform abstraction，独立 PInvoke）。

## 五、WebSocket Server

UE 内置 `IWebSocketsModule` 偏 client，server 用第三方：

**选型**：`uWebSockets`（MIT，header-only，性能好），或 `Beast`（Boost）。Phase 1 用 `uWebSockets` 简单嵌入。

```cpp
class FWebSocketServer {
public:
    bool Start(int32 Port);
    void Stop();
    DECLARE_DELEGATE_OneParam(FOnMessage, const FString&);
    FOnMessage OnMessage;
private:
    TUniquePtr<uWS::App> App;
    TFuture<void> ServerThread;
};
```

**线程**：WebSocket 自己线程；接收的消息 enqueue 到 `TQueue<FString, EQueueMode::Mpsc>`，GameThread 在 `Tick` 里 dequeue 处理。

## 六、Meta 注入

### IStableIdInterface（UInterface）
```cpp
UINTERFACE(MinimalAPI, meta=(CannotImplementInterfaceInBlueprint))
class UStableIdInterface : public UInterface { GENERATED_BODY() };

class IStableIdInterface {
    GENERATED_BODY()
public:
    virtual FString GetPinnedId() const = 0;
    virtual FString GetRole() const { return TEXT(""); }
    virtual FString GetIntent() const { return TEXT(""); }
};
```

### UAutoAgentMeta（UWidget 上的辅助）

由于 UWidget 是 UCLASS，最好不让用户改基类。改用**附加组件**模式：每个 UWidget 关联一个 `UAutoAgentMeta` UObject（key by `WeakObjectPtr<UWidget>`），存在 `UAutoAgentSubsystem` 的 map 里，序列化到 SaveGame。

Editor 里加自定义 Detail Panel：选中任意 UWidget → 显示 "AutoAgent" 折叠面板 → Pin ID / Role / Intent / Tags 输入。

### Hash ID 算法
`MD5(WidgetTreePath + WidgetName + ClassName).Left(12)` → 12 字符 hex。

## 七、Packaged Build 兼容

### 编译期开关
`AutoAgent.Build.cs`：
```csharp
PublicDefinitions.Add("AUTOAGENT_ENABLED=" + (Target.Configuration != UnrealTargetConfiguration.Shipping ? "1" : "0"));
```

Shipping build 默认禁用；用户可在 `Target.cs` 里强制开启。

### Slate API 在 Shipping 的可用性
- `FSlateApplication::ProcessMouseButtonDownEvent` ✅ 可调用（无 WITH_EDITOR 守卫）
- `UWidgetTree::ForEachWidget` ✅
- `GetAllWidgetsOfClass` ✅
- 反射 `OnClicked.IsBound()` ✅（FMulticastDelegate API 公开）

### Cooked 资源 reference
`Image->Brush.GetResourceObject()->GetPathName()` 在 cooked build 返回的是 cooked path（`/Game/UI/btn_login.uasset` → `/Game/UI/btn_login`）。schema 字段允许这种差异。

## 八、测试 Fixture（用户准备）

### `fixtures/unreal-test-project/`
最小 UE 5.6 项目（C++ project）：

#### Map: `LoginMap.umap`
- GameMode 在 BeginPlay 时 `CreateWidget<ULoginUserWidget>` 加到 viewport
- `ULoginUserWidget`（C++ class，不是蓝图）：
  - LoginPanel (UCanvasPanel)
    - AccountInput (UEditableTextBox)
    - PasswordInput (UEditableTextBox)
    - LoginButton (UButton + UTextBlock child)
    - ErrorLabel (UTextBlock)
  - WelcomePanel (initially Hidden)
    - WelcomeText (UTextBlock)

每个交互元素的 PinId 通过 EditorUtility 设置（也可以代码硬编码 `meta=(AutoAgentId="login_button")`）。

#### Map: `PocPlaygroundMap.umap` (Phase 0)
4 动作覆盖（同 Unity）。

## 九、已知坑（必读）

1. **GameThread 强制**：所有 Slate / UMG API 必须 GameThread 调。WebSocket 自己线程收消息后必须 marshal。
2. **Slate Widget 的 SharedPtr 不能跨线程**：`TakeWidget()` 返回的 `TSharedRef<SWidget>` 跨线程拷贝会崩。
3. **PIE vs Standalone Window 差异**：`GetActiveTopLevelWindow` 在编辑器 PIE 模式下可能返回错的 window；用 widget 自身的 `GetCachedWidget()->GetPaintSpaceGeometry()` 反查。
4. **uWebSockets 在 UE Build 系统集成有坑**：需要 disable RTTI 适配；最稳的做法是把 uWebSockets 作为 ThirdParty 静态库，独立编译。
5. **OnClicked.IsBound() 的限制**：仅显式 BindDynamic 的能反射出来，C++ lambda binding 反射不到。
6. **Hot Reload 后 WidgetClass 失效**：dev workflow 时 hot reload 会让 `GetAllWidgetsOfClass` 返回空；adapter 在 Subsystem `OnReinitialized` 时重启 server。
7. **WidgetTree::ForEachWidget vs RootWidget->GetChildAt**：前者扁平，后者递归层级。深度遍历时混用易漏。建议统一用 ForEachWidget。
8. **EditableTextBox 的文本输入**：`SetText` 不触发 `OnTextChanged`；用 `OnTextChanged.Broadcast(...)` 或 `ProcessKeyCharEvent`。
9. **UE 5.6 升级风险**：Slate 内部 API（FPointerEvent constructor 等）跨小版本可能调整。Adapter 用 `#if ENGINE_MAJOR_VERSION == 5 && ENGINE_MINOR_VERSION >= 6` 隔离版本差异。
10. **Subsystem 生命周期**：`UGameInstanceSubsystem::Initialize` 早于第一个 World，但 WebSocket server 启动失败不能 abort 游戏 → 必须 try-catch。

## 十、Phase 2 出口标准

1. login MVP case 跨引擎一致通过（与 Unity 同一份 task DSL）
2. CI nightly 全绿（编译 + e2e）
3. 所有 tool 实现且与 Unity adapter 行为一致
4. Shipping build 验证（编译期开关关掉 → adapter 不包含到二进制）
5. UE 5.6 升级到 5.6.x 小版本时 adapter 不破

## 十一、性能目标

- `dump_tree`（200 节点）< 50ms（UMG 反射比 Unity 略慢）
- `click` 端到端 < 60ms
- 常驻 < 50MB
- Shipping build 验证 size 增量 < 5MB
