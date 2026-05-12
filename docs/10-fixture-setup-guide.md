# 10 - 三引擎静态 Fixture 搭建指南

> 目标：手动搭建 Unity / Unreal / Godot 三个最小静态 UI 场景，作为 AutoAgent 后续全自动开发、协议 PoC、e2e、视觉回归的共同验证基线。
>
> 这份文档只覆盖**视觉骨架 fixture**。不要在这些场景里放任何交互控件或业务逻辑；交互能力后续由 AI 在源码里运行时实现。

## 一、最终产物

完成后 repo 里应有：

```text
fixtures/
├─ unity-test-project/
│  ├─ Packages/manifest.json
│  ├─ ProjectSettings/...
│  └─ Assets/
│     ├─ Scenes/PocPlaygroundScene.unity
│     ├─ Scenes/LoginScene.unity
│     ├─ Sprites/UI/*.png
│     └─ Fonts/{NotoSansCJK-Regular.otf,Roboto-Regular.ttf,RobotoMono-Regular.ttf}
├─ unreal-test-project/
│  ├─ AutoAgentTest.uproject
│  ├─ Source/AutoAgentTest/*
│  ├─ Config/AutoAgentIds.ini
│  └─ Content/
│     ├─ UI/WBP_LoginScreen.uasset
│     ├─ UI/WBP_PocPlayground.uasset
│     ├─ UI/Sprites/*.png
│     ├─ UI/Fonts/*
│     └─ Maps/{LoginMap.umap,PocPlaygroundMap.umap}
└─ godot-test-project/
   ├─ project.godot
   ├─ scenes/{login.tscn,poc_playground.tscn}
   └─ assets/
      ├─ ui/*.png
      └─ fonts/{NotoSansCJK-Regular.otf,Roboto-Regular.ttf,RobotoMono-Regular.ttf}
```

Phase 0 需要两个场景：

- `Login`：MVP canonical task 的静态登录界面。
- `PocPlayground`：验证 `click` / `send_text` / `drag` / `scroll` 四个动作的静态骨架。

## 二、硬规则

> **唯一权威定义见 [00 §四 程序员搭建边界](00-product-overview.md)**。本节为 fixture 搭建特定补充。
>
> 1. **只放视觉骨架**：图片、文字、容器、布局节点可以放；交互控件不放。
2. **节点命名等于 stable ID**：在 adapter 的 metadata Inspector 可用之前，先让节点名严格等于未来 `PinnedId`，例如 `login_button_bg`。
3. **后补 metadata**：adapter 的 `StableIdComponent` / UE meta / Godot Inspector 可用后，再给每个关键节点补 `PinnedId`、`LogicalRole`、`StateSprites`。
4. **不写业务逻辑**：Unity 不绑 UnityEvent；UE WBP 不写 Event Graph；Godot 不挂脚本做交互。
5. **不改视觉资源来修测试**：baseline 和美术资源走单独人工 PR。

禁止出现：

- Unity：`Button` / `TMP_InputField` / `InputField` / `Toggle` / `Slider` / `ScrollRect`。
- UE：`UButton` / `UEditableTextBox` / `USlider` / `UScrollBox` / `UCheckBox` / `UComboBoxString`。
- Godot：`Button` / `LineEdit` / `HSlider` / `VSlider` / `CheckBox` / `OptionButton` / `ScrollContainer` / `ItemList` / `Tree`。

## 三、先跑通目录和占位资源

在 repo 根目录执行：

```powershell
python scripts/fixtures/bootstrap_fixture_assets.py
```

脚本会创建三引擎 fixture 目录、baseline 目录，并生成可临时使用的占位 PNG：

- `btn_login_normal.png`
- `btn_login_hover.png`
- `btn_login_pressed.png`
- `btn_login_disabled.png`
- `input_bg_normal.png`
- `input_bg_focused.png`
- `panel_bg.png`
- `slot_bg.png`

这些 PNG 只用于先把场景搭起来。最终 baseline 前必须替换为真实 UI 切图和字体。

字体需要你手动放入三个目录：

```text
fixtures/unity-test-project/Assets/Fonts/
fixtures/unreal-test-project/Content/UI/Fonts/
fixtures/godot-test-project/assets/fonts/
```

必须包含：

- `NotoSansCJK-Regular.otf`
- `Roboto-Regular.ttf`
- `RobotoMono-Regular.ttf`

## 四、统一 UI 规格

建议所有 fixture 使用同一套布局，减少跨引擎视觉差异：

- 分辨率：`1920x1080`
- 主面板：宽 `640`，高 `480`，居中
- 输入框：宽 `360`，高 `56`
- 登录按钮：宽 `240`，高 `64`
- 字体：英文用 `Roboto-Regular.ttf`，中文/兜底用 `NotoSansCJK-Regular.otf`
- 初始状态：`WelcomePanel` 隐藏，`ErrorLabel` 为空

### Login 节点清单

所有引擎保持同一组 stable ID：

```text
login_panel                image_only
account_input_bg           input
account_input_text         text_display
password_input_bg          input
password_input_text        text_display
login_button_bg            button
login_button_label         text_display
error_label                text_display
welcome_panel              image_only
welcome_text               text_display
```

`state_sprites`：

```text
login_button_bg:
  normal   -> btn_login_normal.png
  hover    -> btn_login_hover.png
  pressed  -> btn_login_pressed.png
  disabled -> btn_login_disabled.png

account_input_bg / password_input_bg:
  normal  -> input_bg_normal.png
  focused -> input_bg_focused.png
```

### PocPlayground 节点清单

```text
click_target               button
click_target_variant_1     button
click_target_variant_2     button
click_target_variant_3     button
click_target_variant_4     button
click_target_variant_5     button
text_target                input
text_target_text           text_display
drag_source                draggable
drag_target                drop_zone
scroll_container           scroll_container
scroll_content             image_only
scroll_item_001..030       image_only
```

## 五、Unity 搭建步骤

### 5.1 创建项目

1. 用 Unity Hub 创建 `Unity 2023.2.20f1+` 2D 项目。
2. 项目路径选 `fixtures/unity-test-project`。
3. 安装 / 启用 TextMeshPro。
4. 把 `adapters/unity` 作为 local package 加到 `Packages/manifest.json`。adapter 还没实现时，可以先保留空 package 依赖，等 TASK-0007 后再修正。
5. Project Settings：
   - Resolution 默认 `1920x1080`
   - Color Space 设为 `Linear`
   - 不启用 Visual Scripting

### 5.2 创建 LoginScene

创建 `Assets/Scenes/LoginScene.unity`。

Scene 结构：

```text
Main Camera
EventSystem                 # 允许存在；它不是交互控件
Canvas (Screen Space Overlay, 1920x1080 reference)
└─ login_panel              Image
   ├─ account_input_bg      Image
   │  └─ account_input_text TMP_Text
   ├─ password_input_bg     Image
   │  └─ password_input_text TMP_Text
   ├─ login_button_bg       Image
   │  └─ login_button_label TMP_Text ("Login")
   └─ error_label           TMP_Text ("")
└─ welcome_panel            Image, inactive
   └─ welcome_text          TMP_Text ("Welcome")
```

注意：

- 所有 `Image` 可以保留 `raycastTarget=false`；AI 后续可按 behavior 打开。
- 不要添加 `Button`、`TMP_InputField`、`ScrollRect`。
- `account_input_text` / `password_input_text` 只是显示占位，不是输入框。
- `welcome_panel` 初始 inactive。

### 5.3 创建 PocPlaygroundScene

创建 `Assets/Scenes/PocPlaygroundScene.unity`。

Scene 结构：

```text
Main Camera
EventSystem
Canvas
├─ click_target             Image
├─ click_target_variant_1   Image
├─ click_target_variant_2   Image
├─ click_target_variant_3   Image
├─ click_target_variant_4   Image
├─ click_target_variant_5   Image
├─ text_target              Image
│  └─ text_target_text      TMP_Text
├─ drag_source              RawImage or Image
├─ drag_target              RawImage or Image
└─ scroll_container         Image
   └─ scroll_content        RectTransform
      ├─ scroll_item_001    Image
      ├─ ...
      └─ scroll_item_030    Image
```

不要添加 `ScrollRect` / `RectMask2D`，这些由 PoC 测试代码运行时加。

### 5.4 补 metadata

当 `StableIdComponent` 可用后，给上述每个关键 GameObject 添加该组件：

- `PinnedId` = 节点名
- `LogicalRole` = 节点清单里的 role
- `StateSprites` = 对应状态 sprite

如果组件暂时不可用，先保证节点名完全准确，并在 PR 描述里标注“metadata 待 adapter inspector 可用后补齐”。

### 5.5 Unity 本地检查

保存场景后运行：

```powershell
python scripts/fixtures/validate_static_fixtures.py --engine unity
```

脚本会检查：

- 必要场景文件是否存在。
- 场景文本里是否误序列化了交互控件。
- sprite / font 是否齐全。

## 六、Unreal 搭建步骤

### 6.1 创建项目

1. 用 UE 5.7 创建 C++ 项目，路径 `fixtures/unreal-test-project`。
2. 项目名建议 `AutoAgentTest`。
3. 不创建 Blueprint-only UI 类；所有 WBP 必须继承 C++ `UUserWidget` 子类。
4. 不在 WBP Event Graph / Function Graph 写任何逻辑。

### 6.2 创建 C++ UserWidget 类

创建：

```text
Source/AutoAgentTest/LoginUserWidget.h
Source/AutoAgentTest/LoginUserWidget.cpp
Source/AutoAgentTest/PocPlaygroundUserWidget.h
Source/AutoAgentTest/PocPlaygroundUserWidget.cpp
```

`LoginUserWidget.h` 的字段示例：

```cpp
#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "LoginUserWidget.generated.h"

UCLASS()
class AUTOAGENTTEST_API ULoginUserWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UPROPERTY(meta=(BindWidget, AutoAgentId="login_panel", AutoAgentLogicalRole="image_only"))
    UImage* LoginPanel;

    UPROPERTY(meta=(BindWidget, AutoAgentId="account_input_bg", AutoAgentLogicalRole="input"))
    UImage* AccountInputBg;

    UPROPERTY(meta=(BindWidget, AutoAgentId="password_input_bg", AutoAgentLogicalRole="input"))
    UImage* PasswordInputBg;

    UPROPERTY(meta=(BindWidget, AutoAgentId="login_button_bg", AutoAgentLogicalRole="button"))
    UImage* LoginButtonBg;

    UPROPERTY(meta=(BindWidget, AutoAgentId="login_button_label", AutoAgentLogicalRole="text_display"))
    UTextBlock* LoginButtonLabel;

    UPROPERTY(meta=(BindWidget, AutoAgentId="error_label", AutoAgentLogicalRole="text_display"))
    UTextBlock* ErrorLabel;

    UPROPERTY(meta=(BindWidget, AutoAgentId="welcome_panel", AutoAgentLogicalRole="image_only"))
    UImage* WelcomePanel;

    UPROPERTY(meta=(BindWidget, AutoAgentId="welcome_text", AutoAgentLogicalRole="text_display"))
    UTextBlock* WelcomeText;
};
```

不要在这些 fixture 头文件里声明 `UButton` / `UEditableTextBox` / `USlider` / `UScrollBox` 字段。后续 AI 会在 C++ `NativeConstruct()` 里创建并包裹 / 替换。

### 6.3 创建 WBP_LoginScreen

1. 创建 `Content/UI/WBP_LoginScreen.uasset`。
2. Parent Class 选择 `ULoginUserWidget`。
3. WidgetTree 只放：
   - `CanvasPanel`
   - `UImage`
   - `UTextBlock`
   - 纯布局容器
4. 把每个 widget 的名字设为 C++ 字段名，例如：
   - `LoginPanel`
   - `AccountInputBg`
   - `PasswordInputBg`
   - `LoginButtonBg`
   - `LoginButtonLabel`
   - `ErrorLabel`
   - `WelcomePanel`
   - `WelcomeText`
5. 勾选 `Is Variable`，确保 `BindWidget` 能绑定。
6. `WelcomePanel` 初始 `Hidden`。

不要添加 `UButton` / `UEditableTextBox`。

### 6.4 创建 WBP_PocPlayground

Parent Class 选择 `UPocPlaygroundUserWidget`。

WidgetTree 放：

```text
CanvasPanel
├─ ClickTarget              UImage
├─ ClickTargetVariant1      UImage
├─ ...
├─ TextTarget               UImage
├─ TextTargetText           UTextBlock
├─ DragSource               UImage
├─ DragTarget               UImage
└─ ScrollContainer          UImage
   └─ ScrollContent         CanvasPanel / VerticalBox
      ├─ ScrollItem001      UImage
      └─ ...
```

### 6.5 创建地图

创建：

```text
Content/Maps/LoginMap.umap
Content/Maps/PocPlaygroundMap.umap
```

每个 map 的 GameMode / LevelScript 只负责把对应 WBP 加到 viewport。不要在 WBP Graph 里写逻辑。

### 6.6 UE 本地检查

```powershell
python scripts/fixtures/validate_static_fixtures.py --engine unreal
```

脚本无法解析二进制 `.uasset` 的内部 WidgetTree，只能检查：

- `.uproject` / `.uasset` / `.umap` 是否存在。
- C++ fixture 头文件是否包含 `AutoAgentId` / `AutoAgentLogicalRole`。
- C++ fixture 是否误声明了交互 widget 类型。
- sprite / font 是否齐全。

WBP 内部是否真的没有 `UButton` 需要你在 UE Editor 里人工确认，后续 adapter dump 也会再次验证。

## 七、Godot 搭建步骤

### 7.1 创建项目

1. 用 Godot 4.6 创建项目，路径 `fixtures/godot-test-project`。
2. 渲染窗口设为 `1920x1080`。
3. 不给 fixture 节点挂业务脚本。
4. 不使用 `Button` / `LineEdit` / `ScrollContainer` 等交互 Control。

### 7.2 创建 login.tscn

创建 `scenes/login.tscn`：

```text
CanvasLayer
└─ login_panel              Control + ColorRect background
   ├─ account_input_bg      TextureRect
   │  └─ account_input_text Label
   ├─ password_input_bg     TextureRect
   │  └─ password_input_text Label
   ├─ login_button_bg       TextureRect
   │  └─ login_button_label Label ("Login")
   └─ error_label           Label ("")
└─ welcome_panel            Control, visible=false
   └─ welcome_text          Label ("Welcome")
```

### 7.3 创建 poc_playground.tscn

```text
CanvasLayer
├─ click_target             TextureRect
├─ click_target_variant_1   TextureRect
├─ ...
├─ text_target              TextureRect
│  └─ text_target_text      Label
├─ drag_source              TextureRect
├─ drag_target              TextureRect
└─ scroll_container         TextureRect
   └─ scroll_content        Control
      ├─ scroll_item_001    TextureRect
      └─ ...
```

不要用 `Container` 自动布局来控制关键尺寸；MVP 先用固定 anchor + offset，避免不同平台布局结果漂移。

### 7.4 写入 metadata

Godot 可以直接用 `set_meta` 持久化到 `.tscn`。如果 Editor plugin 还不可用，可以临时用 Editor 的脚本控制台批量设置。

示例：

```gdscript
@tool
extends EditorScript

func _run() -> void:
    var scene := get_scene()
    _set(scene, "login_panel", "image_only")
    _set(scene, "account_input_bg", "input")
    _set(scene, "password_input_bg", "input")
    _set(scene, "login_button_bg", "button")
    _set(scene, "login_button_label", "text_display")
    _set(scene, "error_label", "text_display")
    _set(scene, "welcome_panel", "image_only")
    _set(scene, "welcome_text", "text_display")

func _set(root: Node, id: String, role: String) -> void:
    var node := root.find_child(id, true, false)
    if node == null:
        push_error("missing node: " + id)
        return
    node.set_meta("autoagent_pinned_id", id)
    node.set_meta("autoagent_logical_role", role)
```

`state_sprites` 后续可通过 Inspector plugin 或直接 `.tscn` 编辑补：

```gdscript
login_button_bg.set_meta("autoagent_state_sprites", {
    "normal": preload("res://assets/ui/btn_login_normal.png"),
    "hover": preload("res://assets/ui/btn_login_hover.png"),
    "pressed": preload("res://assets/ui/btn_login_pressed.png"),
    "disabled": preload("res://assets/ui/btn_login_disabled.png"),
})
```

### 7.5 Godot 本地检查

```powershell
python scripts/fixtures/validate_static_fixtures.py --engine godot
```

## 八、统一验证流程

三引擎都搭完后，在 repo 根目录跑：

```powershell
python scripts/fixtures/validate_static_fixtures.py --engine all
```

这个脚本是**静态检查**，只能提前拦住明显错误。最终还必须通过：

1. adapter `dump_tree`：parent / children 正确、无重复节点。
2. `dump_tree`：任务引用节点 `stable_id_source` 是 `pinned` 或 `auto`，不是 `hash`。
3. `dump_tree`：fixture 阶段 `behavior.attached_components` 为空。
4. `take_screenshot`：截图不是黑屏。
5. 视觉 baseline 人工 review。

## 九、Baseline 捕获顺序

不要一开始就提交所有 baseline。按状态分批：

1. Phase 0 捕获静态初始态：
   - `baselines/unity/windows/poc_playground.png`
   - `baselines/unity/windows/login_screen.png`
   - `baselines/unreal/windows/poc_playground.png`
   - `baselines/unreal/windows/login_screen.png`
   - `baselines/godot/linux/poc_playground.png`
   - `baselines/godot/linux/login_screen.png`
2. Phase 1 登录成功后再捕获：
   - `baselines/unity/windows/welcome_screen.png`

原因：`welcome_panel` 在 fixture 初始态是隐藏的，静态 fixture 阶段截不到 welcome 状态。

## 十、提交前 Checklist

提交 fixture PR 前逐项确认：

- [ ] 三个项目都能被对应 Editor 打开。
- [ ] `Login` / `PocPlayground` 都能 Play，不报错。
- [ ] 没有交互控件被放进静态场景。
- [ ] 节点名与 stable ID 清单一致。
- [ ] 关键节点已补 `PinnedId` / `LogicalRole`，或 PR 明确标注等待 adapter metadata 工具补齐。
- [ ] 三套 sprite 已替换为真实 UI 切图。
- [ ] 三套字体已放入 fixture。
- [ ] `python scripts/fixtures/validate_static_fixtures.py --engine all` 通过，或只剩二进制 WBP 需要人工确认的事项。
- [ ] 未提交 Unity `Library/`、UE `Intermediate/`、Godot `.godot/`。

## 十一、常见坑

- **Unity scene grep 误报**：如果 `.unity` 里出现 `Button` 只是图片文件名或文本内容，也会被脚本标红。优先改资源命名为 `btn_`，避免和组件名冲突。
- **UE WBP 二进制不可 grep**：静态脚本不能证明 WBP 内没有 UButton，需要人工检查 + 后续 adapter dump 双重验证。
- **Godot 自动布局漂移**：固定测试 UI 不要依赖 `HBoxContainer` / `VBoxContainer` 来决定关键坐标。
- **字体缺失**：baseline 前必须换成真实字体，否则 CI 会因为豆腐字或 fallback 差异失败。
- **metadata 工具未完成**：先完成视觉骨架和严格命名；等 adapter editor 工具可用后补 metadata，再捕获 baseline。
