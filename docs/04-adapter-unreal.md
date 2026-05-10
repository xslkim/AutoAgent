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
// ⚠️ 注意：UWidgetTree::ForEachWidget 已经遍历整棵树（含 panel children）。
// 如果再对 UPanelWidget 递归调 GetChildAt，会重复访问节点 + parent_id 错乱。
// 正确做法：只用一种遍历方式。这里采用从 RootWidget 单一递归，明确传递 parent_id。

void UUmgReflector::DumpAllWidgets(TArray<FNodeData>& OutNodes) {
    UWorld* World = GetWorld();
    TArray<UUserWidget*> Widgets;
    UWidgetBlueprintLibrary::GetAllWidgetsOfClass(
        World, Widgets, UUserWidget::StaticClass(), /*TopLevelOnly=*/false);

    for (UUserWidget* UserWidget : Widgets) {
        if (!UserWidget || !UserWidget->IsInViewport()) continue;
        if (!UserWidget->WidgetTree) continue;

        // UserWidget 自身作为根节点，先入树
        FString UserWidgetId = StableIdResolver.Resolve(UserWidget).Id;
        OutNodes.Add(BuildNode(UserWidget, /*ParentId=*/TEXT("")));

        // 从 WidgetTree.RootWidget 单一递归，traverse 整棵树
        if (UWidget* Root = UserWidget->WidgetTree->RootWidget) {
            WalkChildren(Root, OutNodes, /*ParentId=*/UserWidgetId);
        }
    }
}

void UUmgReflector::WalkChildren(UWidget* W, TArray<FNodeData>& Out, const FString& ParentId) {
    if (!W) return;
    FNodeData Node = BuildNode(W, ParentId);
    Out.Add(Node);

    // 仅 UPanelWidget 有 children；其他 widget（Button / Image / TextBlock）是叶子
    if (UPanelWidget* Panel = Cast<UPanelWidget>(W)) {
        for (int32 i = 0; i < Panel->GetChildrenCount(); ++i) {
            WalkChildren(Panel->GetChildAt(i), Out, /*ParentId=*/Node.Id);
        }
    }
    // NamedSlot 等特殊容器：在 BuildNode 里单独处理（如果需要）
}
```

**遍历策略约束**：
- 全 codebase 内**禁止使用** `UWidgetTree::ForEachWidget`（容易和 RootWidget 递归混用造成重复）
- 单元测试 `UmgReflectorTest.NoDuplicateNodes` 验证：dump 输出的 id 集合无重复
- 单元测试 `UmgReflectorTest.ParentChildConsistent` 验证：每个 child 的 parent_id 都在 nodes 列表里且对应节点的 children_ids 包含 child id

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

**Subprotocol 校验（uWS 配置）**：

```cpp
App->ws<UserData>("/*", {
    .upgrade = [](auto* res, auto* req, auto* /*context*/) {
        std::string_view subProtocols = req->getHeader("sec-websocket-protocol");
        if (subProtocols.find("autoagent.v1") == std::string_view::npos) {
            res->writeStatus("400 Bad Request")
               ->end("subprotocol mismatch: require autoagent.v1");
            return;
        }
        // upgrade 时回写选定的 subprotocol
        res->upgrade<UserData>(
            UserData{},
            req->getHeader("sec-websocket-key"),
            "autoagent.v1",   // selected subprotocol
            req->getHeader("sec-websocket-extensions"),
            /*context*/ nullptr
        );
    },
    .open = [](auto* ws) { /* 启动 negotiation 5s watchdog */ },
    .message = [](auto* ws, std::string_view msg, uWS::OpCode) { /* enqueue to GameThread */ },
});
```

**线程**：WebSocket 自己线程；接收的消息 enqueue 到 `TQueue<FString, EQueueMode::Mpsc>`，GameThread 在 `Tick` 里 dequeue 处理。

## 六、Meta 注入（Stable ID 持久化）

> ⚠️ **UE 不能照搬 Unity 的 MonoBehaviour 模式**。UWidget 实例在 PIE 启动 / hot reload / WidgetTree rebuild 后会被重新 New，`WeakObjectPtr<UWidget>` 失效，SaveGame key 也对不上。
> UE 侧 stable ID **不靠运行时挂载**，靠**设计期源码声明 + 编辑期注册表**。

### Stable ID 来源（优先级从高到低）

#### 来源 1：`UPROPERTY` meta tag（C++ 类成员，最稳）

```cpp
UCLASS()
class ULoginUserWidget : public UUserWidget {
    GENERATED_BODY()
public:
    UPROPERTY(meta=(BindWidget, AutoAgentId="login_button", AutoAgentRole="submit_button"))
    UButton* LoginButton;

    UPROPERTY(meta=(BindWidget, AutoAgentId="account_input"))
    UEditableTextBox* AccountInput;
};
```

Adapter 启动时反射所有 `UUserWidget` 子类的 UPROPERTY，扫描 meta map 里的 `AutoAgentId` / `AutoAgentRole` / `AutoAgentIntent`，建立 `(OuterUserWidgetClass, BindWidgetName) → StableId` 映射。

**关键**：key 是 *widget 名字 + outer class*，不是 instance pointer。PIE / hot reload / rebuild 后仍然有效。

#### 来源 2：运行时显式注册（业务代码声明）

适用于 BindWidget 不方便的场景（动态创建的列表项、运行时 spawn 的 widget）：

```cpp
void ULoginUserWidget::NativeConstruct() {
    Super::NativeConstruct();
    if (auto* Subsystem = GetGameInstance()->GetSubsystem<UAutoAgentSubsystem>()) {
        Subsystem->RegisterStableId(SomeRuntimeWidget, TEXT("dynamic_item_001"));
    }
}
```

注册表 key 用 `widget->GetFName().ToString() + "@" + widget->GetOuter()->GetFullName()`，不依赖指针。dump 时按 key 反查。

#### 来源 3：Fixture 项目里的显式注册表（外部 .ini）

业务代码不便修改时，fixture 项目可以提供 `Config/AutoAgentIds.ini`：

```ini
[/Game/UI/WBP_LoginScreen.WBP_LoginScreen_C:LoginButton]
AutoAgentId=login_button
AutoAgentRole=submit_button

[/Game/UI/WBP_LoginScreen.WBP_LoginScreen_C:AccountInput]
AutoAgentId=account_input
```

Adapter 启动时加载这份 ini，建立映射。优先级低于来源 1/2。

#### 来源 4（仅诊断）：Path Hash

```
PathHash = MD5(OwningUserWidgetClass + "." + WidgetFName).Left(12)
```

`stable_id_source = "hash"`。**任务 DSL 不允许引用**（与 [01 协议规范](01-protocol-spec.md) 一致）。

### Editor 工具（`AutoAgentEditor` module）

1. **BindWidget Property Detail Customization**：选中 UUserWidget 类的 BindWidget 属性时，Inspector 显示 "AutoAgent ID / Role / Intent" 字段，编辑后自动写到对应 .h 的 UPROPERTY meta。
2. **AutoAgentIds.ini Editor**：可视化编辑外部注册表。
3. **未 pin 节点检测**：扫描 fixture project 的所有 UUserWidget，列出"还在用 hash ID"的 widget，提示 pin。

### `FStableIdResolver` 接口

```cpp
class FStableIdResolver {
public:
    enum class ESource { Pinned, Auto, Hash };
    struct FResolved { FString Id; ESource Source; };

    FResolved Resolve(UWidget* W) const;

    void LoadFromPropertyMeta();        // 来源 1：UClass UPROPERTY meta 扫描
    void LoadFromIniRegistry();          // 来源 3：解析 AutoAgentIds.ini
    void RegisterRuntime(UWidget* W, const FString& Id);  // 来源 2：业务代码注册

private:
    // key: OuterUserWidgetClass + "." + WidgetFName
    TMap<FString, FString> NameToPinnedId;
};
```

**实现禁忌**：
- ❌ 不要用 `WeakObjectPtr<UWidget>` 作 map key
- ❌ 不要用 SaveGame 持久化 widget 引用
- ❌ 不要承诺 "Inspector 上挂个组件就行" 的 Unity 体验
- ✅ 一切映射基于 widget 名字 + outer class，跨 lifecycle 稳定

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
