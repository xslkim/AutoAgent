# 04 - Unreal Adapter

> Unreal 引擎 adapter 设计。**业务逻辑纯 C++**（不在 Blueprint event graph 里写逻辑），UE 5.7。
>
> **"不用蓝图"的精确语义**（与 [00 §四 / §硬约束](00-product-overview.md) 对齐）：
> - ✅ **允许** `WBP_LoginScreen.uasset` 等 Widget Blueprint asset 作为**纯数据的视觉骨架容器**——里头声明 UI 树 + 图片 + StableId/LogicalRole/StateSprites meta，**没有 Event Graph / Function Graph 节点**。
> - ✅ **允许** WBP 继承自 C++ `UUserWidget` 子类（如 `ULoginUserWidget`），BindWidget 把 WBP 里的 UImage 反映回 C++ 字段。
> - ❌ **禁止** 在 WBP 里用 Blueprint Visual Scripting 写任何 OnClicked / Tick / Custom Event 逻辑——所有逻辑必须在对应 C++ class 里。
> - ❌ **禁止** 用 Blueprint-only widget class（无 C++ parent），调度 / 反射 / 跨 PIE 稳定性都会出问题。
>
> 这条约束既保证 UE fixture 可以可视化预览（程序员对齐美术稿的关键工具），又保证逻辑由文本代码承载（git diff / 源码审计 / IDE refactor 全部可工作）。

## 一、范围

- **支持版本**：UE 5.7
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

> **前提（与 [00 §四 程序员搭建边界](00-product-overview.md) / [01 §三](01-protocol-spec.md) 对齐）**：fixture WBP（蓝图 widget）/ C++ UUserWidget 子类的 WidgetTree 里**只放视觉骨架**——`UImage` / `UTextBlock` / `UCanvasPanel` / `UVerticalBox` / `UHorizontalBox` / `UScaleBox` 等纯显示与布局 widget。**不放任何"交互 widget"**（`UButton` / `UEditableTextBox` / `USlider` / `UCheckBox` / `UComboBoxString` / `UScrollBox` / `UListView`）。这些控件由 AI 在源码 `NativeConstruct()` / `BeginPlay()` 里**运行时创建**并挂到树上（见 §四末"AI 添加控件的两条路径"）。
>
> 因此反射的 `type` 字段绝大多数情况下是 `UImage` / `UTextBlock` / `UCanvasPanel`；`behavior.attached_components` 在 fixture 加载完是空的，AI 代码运行后才会包含 `UButton` 等。

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
| `type` | **Widget class 简名**（fixture 阶段绝大多数是 `Image` / `TextBlock` / `CanvasPanel` 等纯视觉 widget）。AI 通过包裹节点实现交互后，包裹层会出现新 type（如 `Button`） |
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
| `behavior.raycast_target` | `W->GetVisibility() == ESlateVisibility::Visible`（HitTestInvisible / SelfHitTestInvisible 返回 false） |
| `behavior.attached_components` | UE 模型下没有"组件挂载"，但 AI 通过 [§三 AI 实现路径](#ue-特殊性fixture-不放交互-widget-的两条-ai-实现路径) "包裹节点"添加的 UButton / UEditableTextBox 自身就是 widget。这里序列化为 ["UButton"] 等，**当被包裹的子 widget 的视觉是它的 brush/content 时**，便于 CI 校验 logical_role |
| `behavior.event_handlers` | `OnClicked.IsBound() ? ["OnClicked"] : []`（运行时反射） |
| `meta.logical_role` | C++ UPROPERTY `meta=(AutoAgentLogicalRole="button")` 或 `Config/AutoAgentIds.ini` 里的 `AutoAgentLogicalRole` 字段 |
| `meta.state_sprites` | UPROPERTY `meta=(AutoAgentStateSprites="...")` 指向同 UClass 内多个 `UPROPERTY UTexture2D*` 字段，或在 ini 配置 |

### UE 特殊性：fixture 不放交互 widget 的两条 AI 实现路径

UE 的 UMG 模型下 `UButton` / `UEditableTextBox` 等是**节点本身**而非"组件"，无法像 Unity 那样 AddComponent。因此 fixture 只放视觉骨架时，AI 必须通过以下两条路径之一实现"赋予交互"：

**路径 A：包裹（推荐）** — UButton 包 UImage：

```cpp
void ULoginUserWidget::NativeConstruct() {
    Super::NativeConstruct();

    // 1. 找到 fixture 里的 UImage（程序员手放的视觉骨架）
    UImage* LoginButtonBg = Cast<UImage>(GetWidgetFromName(TEXT("LoginButtonBg")));
    UPanelWidget* Parent = Cast<UPanelWidget>(LoginButtonBg->GetParent());
    UPanelSlot* OldSlot = LoginButtonBg->Slot;

    // 2. CreateWidget<UButton>，把 UImage 移到 UButton 的 content slot
    UButton* Btn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("LoginButton_Wrapper"));
    Btn->SetContent(LoginButtonBg);   // UImage 作为 button 的视觉

    // 3. 替换原 panel slot（保留原 layout 参数）
    Parent->ReplaceChildAt(Parent->GetChildIndex(LoginButtonBg), Btn);
    CopySlotProperties(OldSlot, Btn->Slot);  // 保留 anchor / offset

    // 4. 绑 OnClicked
    Btn->OnClicked.AddDynamic(this, &ULoginUserWidget::OnLoginClicked);

    // 5. 把 logical_role / pinned_id 从原 UImage 转移到 UButton（adapter 配合）
    AutoAgentSubsystem->TransferStableId(LoginButtonBg, Btn);
}
```

**路径 B：替换 brush** — 适用于 UEditableTextBox 等自身有 background brush 的控件：

```cpp
// UImage 的 brush 提取后丢给 UEditableTextBox.WidgetStyle.BackgroundImageNormal
UImage* InputBg = Cast<UImage>(GetWidgetFromName(TEXT("AccountInputBg")));
FSlateBrush BgBrush = InputBg->GetBrush();
UEditableTextBox* Input = WidgetTree->ConstructWidget<UEditableTextBox>(...);
Input->WidgetStyle.BackgroundImageNormal = BgBrush;
Input->WidgetStyle.BackgroundImageHovered = BgBrush;
Input->WidgetStyle.BackgroundImageFocused = BgBrush;
// 把 UEditableTextBox 放回 UImage 原 slot，UImage 不再渲染（visible=false）或彻底从树移除
Parent->ReplaceChildAt(Parent->GetChildIndex(InputBg), Input);
```

**关键约束（写进 [06 §二 防护 0](06-visual-regression.md)）**：
- 这两条路径会**改变 WidgetTree 结构**，正常情况下属于"AI 不允许改结构"违规。需要在 [06 防护 0.3 dump 前后 diff](06-visual-regression.md#23-dump-前后-diff-gate运行时验证) 里明确豁免：**"AI 添加的包裹层 widget，只要其 logical_role 在 [01 协议 logical_role 取值表](01-protocol-spec.md) 内 + 视觉字段（包裹层 vs 原节点）一致，则不算结构破坏"**。
- adapter 提供 `AutoAgentSubsystem->TransferStableId(OldWidget, NewWidget)` 接口让 AI 显式转移 pinned ID，否则 dump 后原 ID 会成 orphan → CI fail。
- CI 校验：若 fixture 里某节点 `meta.logical_role == "button"`，运行时 dump 后该 ID 对应的 widget 必须是 `UButton` / 子类。

### Slate 原生（Phase 2 末加入）

`FSlateApplication::Get().GetAllVisibleWidgets()` 拿到 `TArray<TSharedRef<SWidget>>`，递归 `GetChildren()`。Schema 用相同字段，`engine_extras.unreal.is_slate = true` 区分。

## 四、输入注入

> **前置约束**：`Click` / `SendText` / `Drag` / `Scroll` 都要求 AI 已经走 §三末"路径 A/B"把 UImage 包裹/替换成对应交互 widget（`UButton` / `UEditableTextBox` / `UScrollBox` / ...）。fixture 阶段直接对纯 UImage 节点发 `click` → adapter 找不到 UButton 父级 → 返回 `-32002 WidgetNotInteractable`，错误信息明确提示"节点未被 UButton 包裹"。

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

> **与 [00 §四 程序员搭建边界](00-product-overview.md) 对齐**：fixture WBP 里 BindWidget 只绑到 `UImage` / `UTextBlock` 等视觉骨架节点。`UButton` / `UEditableTextBox` 不在 fixture 里出现，由 AI 在 NativeConstruct 通过路径 A/B 创建。

```cpp
UCLASS()
class ULoginUserWidget : public UUserWidget {
    GENERATED_BODY()
public:
    // BindWidget 绑到 fixture WBP 里的 UImage（视觉骨架）
    UPROPERTY(meta=(BindWidget,
                    AutoAgentId="login_button_bg",
                    AutoAgentLogicalRole="button",
                    AutoAgentRole="submit_button"))
    UImage* LoginButtonBg;

    UPROPERTY(meta=(BindWidget,
                    AutoAgentId="account_input_bg",
                    AutoAgentLogicalRole="input"))
    UImage* AccountInputBg;

    // AI 在 NativeConstruct 里 ConstructWidget 后填回这两个指针（非 BindWidget）
    UPROPERTY() UButton* LoginButton;
    UPROPERTY() UEditableTextBox* AccountInput;
};
```

Adapter 启动时反射所有 `UUserWidget` 子类的 UPROPERTY，扫描 meta map 里的 `AutoAgentId` / `AutoAgentLogicalRole` / `AutoAgentRole` / `AutoAgentIntent`，建立 `(OuterUserWidgetClass, BindWidgetName) → StableId` 映射。

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
- `WidgetTree->RootWidget` + `UPanelWidget::GetChildAt` 递归遍历 ✅（本 adapter 禁用 `ForEachWidget` 以避免重复节点）
- `GetAllWidgetsOfClass` ✅
- 反射 `OnClicked.IsBound()` ✅（FMulticastDelegate API 公开）

### Cooked 资源 reference
`Image->Brush.GetResourceObject()->GetPathName()` 在 cooked build 返回的是 cooked path（`/Game/UI/btn_login.uasset` → `/Game/UI/btn_login`）。schema 字段允许这种差异。

## 八、测试 Fixture（用户准备）

### `fixtures/unreal-test-project/`
最小 UE 5.7 项目（C++ project），**WidgetTree 只放视觉骨架**（[00 §四 程序员搭建边界](00-product-overview.md)）：

#### Map: `LoginMap.umap`
- GameMode 在 BeginPlay 时 `CreateWidget<ULoginUserWidget>` 加到 viewport
- `WBP_LoginScreen`（继承自 ULoginUserWidget C++ class）的 WidgetTree：
  - LoginPanel (UCanvasPanel) — `AutoAgentLogicalRole=image_only`（容器）
    - AccountInputBg (UImage)     — `AutoAgentLogicalRole=input`
    - PasswordInputBg (UImage)    — `AutoAgentLogicalRole=input`
    - LoginButtonBg (UImage)      — `AutoAgentLogicalRole=button`
      - LoginButtonLabel (UTextBlock "Login") — `AutoAgentLogicalRole=text_display`
    - ErrorLabel (UTextBlock, initially empty) — `AutoAgentLogicalRole=text_display`
  - WelcomePanel (UCanvasPanel, initially Hidden) — `AutoAgentLogicalRole=image_only`
    - WelcomeText (UTextBlock) — `AutoAgentLogicalRole=text_display`

每个节点的 PinId / LogicalRole 通过以下方式之一设置：
- C++ UPROPERTY `meta=(BindWidget, AutoAgentId="...", AutoAgentLogicalRole="...")`（推荐）
- 外部注册表 `Config/AutoAgentIds.ini`

**关键**：fixture 加载完，WidgetTree 内 **没有任何 UButton / UEditableTextBox**；AI 写的 `ULoginUserWidget::NativeConstruct()` 通过 §三末"路径 A/B"创建并替换/包裹。

#### Map: `PocPlaygroundMap.umap` (Phase 0)
4 动作视觉骨架覆盖（同 Unity 模式）：
- `click_target` (UImage, logical_role=button)
- `text_target` (UImage, logical_role=input)
- `drag_source` + `drag_target` (UImage)
- `scroll_container` (UImage + 30 个 UImage item, logical_role=scroll_container)

PoC 测试代码自行实现包裹路径。

## 九、已知坑（必读）

1. **GameThread 强制**：所有 Slate / UMG API 必须 GameThread 调。WebSocket 自己线程收消息后必须 marshal。
2. **Slate Widget 的 SharedPtr 不能跨线程**：`TakeWidget()` 返回的 `TSharedRef<SWidget>` 跨线程拷贝会崩。
3. **PIE vs Standalone Window 差异**：`GetActiveTopLevelWindow` 在编辑器 PIE 模式下可能返回错的 window；用 widget 自身的 `GetCachedWidget()->GetPaintSpaceGeometry()` 反查。
4. **uWebSockets 在 UE Build 系统集成有坑**：需要 disable RTTI 适配；最稳的做法是把 uWebSockets 作为 ThirdParty 静态库，独立编译。
5. **OnClicked.IsBound() 的限制**：仅显式 BindDynamic 的能反射出来，C++ lambda binding 反射不到。
6. **Hot Reload 后 WidgetClass 失效**：dev workflow 时 hot reload 会让 `GetAllWidgetsOfClass` 返回空；adapter 在 Subsystem `OnReinitialized` 时重启 server。
7. **WidgetTree::ForEachWidget vs RootWidget->GetChildAt 混用风险**：前者扁平遍历整棵树（含 panel children），后者递归层级。**混用会产生重复节点 + parent_id 错乱**。与 §三 "遍历策略约束" 一致：**全 codebase 禁用 `UWidgetTree::ForEachWidget`**，统一从 `WidgetTree->RootWidget` 单一递归 `WalkChildren` 并明确传递 `parent_id`。单元测试 `NoDuplicateNodes` + `ParentChildConsistent` 强制验证。
8. **EditableTextBox 的文本输入**：`SetText` 不触发 `OnTextChanged`；用 `OnTextChanged.Broadcast(...)` 或 `ProcessKeyCharEvent`。
9. **UE 5.7 升级风险**：Slate 内部 API（FPointerEvent constructor 等）跨小版本可能调整。Adapter 用 `#if ENGINE_MAJOR_VERSION == 5 && ENGINE_MINOR_VERSION >= 7` 隔离版本差异。
10. **Subsystem 生命周期**：`UGameInstanceSubsystem::Initialize` 早于第一个 World，但 WebSocket server 启动失败不能 abort 游戏 → 必须 try-catch。

## 十、Phase 2 出口标准

1. login MVP case 跨引擎一致通过（与 Unity 同一份 task DSL）
2. CI nightly 全绿（编译 + e2e）
3. 所有 tool 实现且与 Unity adapter 行为一致
4. Shipping build 验证（编译期开关关掉 → adapter 不包含到二进制）
5. UE 5.7 升级到 5.7.x 小版本时 adapter 不破

## 十一、性能目标

- `dump_tree`（200 节点）< 50ms（UMG 反射比 Unity 略慢）
- `click` 端到端 < 60ms
- 常驻 < 50MB
- Shipping build 验证 size 增量 < 5MB
