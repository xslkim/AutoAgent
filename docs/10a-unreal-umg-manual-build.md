# 10a - Unreal WBP 手工搭建 Checklist

> [10 fixture setup guide](10-fixture-setup-guide.md) 的 Unreal 专属补充。`fixtures/unreal-test-project/Scripts/build_fixtures.py` 只创建**空 WBP** + 设 parent class（参 [04a §三](04a-adapter-unreal-cpp-blueprint-layering.md)），WidgetTree 必须在 UMG Designer 里**手工拖**——因为 UE 5.7 Python API 没暴露 `WidgetTree` 顶层 class，自动化既脆又复杂，fixture 又是 baseline 一次性工作，手工 30 分钟划算。
>
> 本文是这"30 分钟"的精确操作。读完不需要再跳别处。

## 一、三种允许的 widget 类型

| Palette 路径 | C++ class | 用途 |
|---|---|---|
| **Common > Image** | `UImage` | 所有 background / button bg / input bg / scroll bg / slot |
| **Common > Text** | `UTextBlock` | 所有 label / 占位文字 / 按钮文字 / 错误提示 |
| **Panel > Canvas Panel** | `UCanvasPanel` | WBP 根节点 + PocPlayground 的 `ScrollContent` |

**禁止**拖的（[10 §二硬规则](10-fixture-setup-guide.md#二硬规则)）：

`Button` / `Editable Text` / `Editable Text Box` / `Rich Text Block` / `Border` / `Check Box` / `Check Button` / `Slider` / `Combo Box` / `Scroll Box` / `Spin Box`

## 二、UE 的硬限制：UImage 不能有 children

`UImage` 不是 `UPanelWidget` 子类，**无法在 WidgetTree 里挂子节点**。所以 [10 §6.3](10-fixture-setup-guide.md) 画的：

```
AccountInputBg
└─ AccountInputText
```

在 UE 是**做不到**的。改成两个**同层平铺**的兄弟节点，靠**位置重叠**让 Text 看起来"在 Image 上面"：

```
CanvasPanel
├─ AccountInputBg     (Image, 360x56)
├─ AccountInputText   (Text,  位置重叠到 AccountInputBg)
```

C++ `BindWidget` 按名字找节点，**不关心父子关系**，所以平铺没问题。

唯一例外是 `ScrollContent`（C++ 声明为 `UCanvasPanel*`），它**能**有 children——30 个 `ScrollItemNNN` 挂在它下面。

## 三、UMG Designer 窗口布局

| 区域 | 位置 | 作用 |
|---|---|---|
| **Palette** | 左上 | 拖 widget 的源 |
| **Hierarchy** | 左下 | WidgetTree 树状视图（核对名字 / 调层级） |
| **Designer** | 中央 | 可视化预览 |
| **Details** | 右侧 | 编辑选中 widget 的所有属性 |

`Compile` 按钮在顶栏左上，绿勾形状。改完一定要 Compile + Save。

## 四、WBP_LoginScreen

### 4.1 准备根节点

Content Browser 双击 `WBP_LoginScreen` → UMG Designer。若 Hierarchy 里没 `[CanvasPanel]` 根，从 Palette 拖一个 **Canvas Panel** 进去当根。

### 4.2 节点清单

所有节点都是 **CanvasPanel 直接子节点**。Slot Anchor 都选**中心**（9 宫格中间格），Alignment 都设 `(0.5, 0.5)`。**Anchor 具体怎么点见 [§4.4](#44-怎么设-anchor--alignment--position必读做错只显示-14)——做错会出现"UI 中心跑到屏幕左上角，只露出右下 1/4"的现象。**

| 名字（严格大小写） | 类型 | Position (X, Y) | Size (X, Y) | 关键属性 |
|---|---|---|---|---|
| `LoginPanel` | Image | (0, 0) | (640, 480) | Brush > Image = `panel_bg` |
| `AccountInputBg` | Image | (0, -120) | (360, 56) | Brush = `input_bg_normal` |
| `AccountInputText` | Text | (0, -120) | (336, 24) | Text=(空)，Color=Black |
| `PasswordInputBg` | Image | (0, -40) | (360, 56) | Brush = `input_bg_normal` |
| `PasswordInputText` | Text | (0, -40) | (336, 24) | Text=(空)，Color=Black |
| `LoginButtonBg` | Image | (0, 60) | (240, 64) | Brush = `btn_login_normal` |
| `LoginButtonLabel` | Text | (0, 60) | (240, 64) | Text=`Login`，Justification=Center，Color=White |
| `ErrorLabel` | Text | (0, 140) | (480, 28) | Text=(空)，Justification=Center，Color=Red |
| `WelcomePanel` | Image | (0, 0) | (640, 480) | Brush=`panel_bg`，**Visibility=Hidden** |
| `WelcomeText` | Text | (0, 0) | (640, 480) | Text=`Welcome`，Justification=Center，**Visibility=Hidden** |

### 4.3 每个 widget 都要做的三件事

1. **改名字**：Hierarchy 里双击节点改名，**精确大小写**——错一个字母 C++ `BindWidget` Compile 时会红字报 error
2. **勾 `Is Variable`**：Details 顶部那个复选框。**没勾的话 C++ 找不到它**
3. **填属性**：按上表 Slot + Brush/Text（Slot Anchor 操作见 §4.4，Brush 见 §4.5）

### 4.4 怎么设 Anchor / Alignment / Position（必读，做错只显示 1/4）

这是最容易踩的坑——做错会出现 **"UI 中心在屏幕左上角，只露出右下 1/4"** 的现象。

#### 4.4.1 三个概念

| 名字 | 是什么 | 默认值 |
|---|---|---|
| **Anchor** | widget 在父 CanvasPanel 里的"参考点"。0 = 左/上，1 = 右/下，0.5 = 中。屏幕缩放时 widget 跟着这个参考点走 | `(0, 0)` 左上 |
| **Alignment** | widget 自己的哪个点对齐到 Position。`(0,0)` = 用左上角对齐，`(0.5,0.5)` = 用中心对齐 | `(0, 0)` 左上 |
| **Position** | widget 离 Anchor 的偏移像素 | `(0, 0)` |

合起来：**widget 的"Alignment 点"被放在"Anchor 位置 + Position 偏移"处**。

举例：Anchor=中心、Alignment=(0.5,0.5)、Position=(0,-120) → "widget 中心点" 被放在 "屏幕中心向上 120 像素"处。

#### 4.4.2 操作步骤（每个节点都要做）

1. Hierarchy 里选中节点（比如 `LoginPanel`）
2. Details 面板最顶上找 **Slot (Canvas Panel Slot)** 折叠区，没展开就点一下展开
3. 第一行 **Anchors**，最右边有个**九宫格小图标**（4×4 的小方块，里面有几个小蓝点表示当前 anchor 位置）
4. 点这个九宫格图标 → 弹出 **9 个预设格** 的浮窗 → **点正中间那一格**（中间那一格的图标是一个十字准星）
5. 点完后，Slot 区里 Anchors 数值会自动变成 `Minimum X/Y = 0.5  Maximum X/Y = 0.5`（不用手填）
6. 同一个 Slot 区里找 **Alignment**，把 `X=0.5  Y=0.5` 手填进去（默认是 0）
7. **Position X / Position Y** 按 [§4.2 表格](#42-节点清单) 的值填
8. **Size X / Size Y** 按表格填

#### 4.4.3 组合速查表

| 想要的效果 | Anchor 选 | Alignment | Position |
|---|---|---|---|
| widget 中心钉在屏幕中心 | 9 宫格**中间** | `(0.5, 0.5)` | `(0, 0)` |
| widget 中心在屏幕中心**上方 120 像素** | 9 宫格**中间** | `(0.5, 0.5)` | `(0, -120)` |
| widget 中心在屏幕中心**下方 60 像素** | 9 宫格**中间** | `(0.5, 0.5)` | `(0, 60)` |
| widget 左上角钉在屏幕左上角 | 9 宫格**左上**（默认） | `(0, 0)` | `(0, 0)` |
| widget 左上角离屏幕左上 (100,100) | 9 宫格**左上**（默认） | `(0, 0)` | `(100, 100)` |

§4.2 表格里凡是 Position 带负数的（`(0, -120)`、`(0, -40)`），都必须配合 **中心 Anchor + Alignment (0.5, 0.5)** 才能得到"在屏幕中心**上方** 120 像素"这种语义。

#### 4.4.4 怎么知道改对了

改完 `LoginPanel` 一个节点后：

- **Designer 中央**应该看到一个蓝色 640×480 矩形**居中显示**在虚线框（屏幕预览区）正中
- 如果蓝色矩形飘在左上角、或者只露出右下一角 → Anchor 还是左上没改对，回 §4.4.2 重做
- 如果蓝色矩形居中但偏离一点 → Alignment 不是 (0.5, 0.5)，检查 Alignment 那行

#### 4.4.5 批量小技巧

Hierarchy 里 Ctrl + 单击多个节点 → Details 一次显示共有属性 → 改一次 Anchor 九宫格能同时改完所有选中节点的 Anchor。

但 **Position / Alignment 仍要逐个核对**，因为每个节点 Position 不一样（表格里 Y 是 -120 / -40 / 60 / 140 / 0），Alignment 虽然都是 (0.5, 0.5) 但 UE 不一定批量填进去。

### 4.5 怎么改 Brush > Image

选中 Image → Details > **Appearance** > **Brush** > 第一项 **Image** → 点小下拉箭头 → texture picker 弹出 → 搜框输入 `btn_login_normal`（或对应 sprite 名）→ 双击。

**不要**改 Brush 的 Image Size / Tiling / Draw As，保持默认。

### 4.6 怎么改 Visibility

Details > **Behavior** 折叠区 > **Visibility** 下拉。选 **Hidden** 不是 **Collapsed**——

- `Hidden`: 不画，但占布局空间（baseline 一致性需要这个）
- `Collapsed`: 完全不存在，不占空间
- `Visible`: 默认
- `HitTestInvisible`: 画但不接事件

### 4.7 完成

顶栏 **Compile**（绿勾）。若所有名字对、`Is Variable` 都勾，应该全绿无 error。**Save**。

## 五、WBP_PocPlayground

Anchor 用**左上**（9 宫格左上格，这是默认值，多数情况下不用改），Alignment `(0, 0)`，Position 是相对屏幕左上角的像素坐标。Anchor 九宫格怎么点见 [§4.4.2](#442-操作步骤每个节点都要做)。

### 5.1 顶层 12 个节点（CanvasPanel 直接子节点）

| 名字 | 类型 | Position (X, Y) | Size (X, Y) | Brush / Text |
|---|---|---|---|---|
| `ClickTarget` | Image | (100, 100) | (120, 80) | Brush=`slot_bg` |
| `ClickTargetVariant1` | Image | (240, 100) | (120, 80) | Brush=`slot_bg` |
| `ClickTargetVariant2` | Image | (380, 100) | (120, 80) | Brush=`slot_bg` |
| `ClickTargetVariant3` | Image | (520, 100) | (120, 80) | Brush=`slot_bg` |
| `ClickTargetVariant4` | Image | (660, 100) | (120, 80) | Brush=`slot_bg` |
| `ClickTargetVariant5` | Image | (800, 100) | (120, 80) | Brush=`slot_bg` |
| `TextTarget` | Image | (100, 220) | (360, 56) | Brush=`input_bg_normal` |
| `TextTargetText` | Text | (112, 236) | (336, 24) | Text=(空)，Color=Black |
| `DragSource` | Image | (100, 320) | (100, 100) | Brush=`slot_bg` |
| `DragTarget` | Image | (260, 320) | (100, 100) | Brush=`slot_bg` |
| `ScrollContainer` | Image | (100, 460) | (640, 500) | Brush=`panel_bg` |
| `ScrollContent` | **Canvas Panel** | (110, 470) | (620, 480) | (容器，无 brush) |

前 11 个都勾 `Is Variable`。`ScrollContent` 也勾。

### 5.2 ScrollContent 内部的 30 个 ScrollItem（CanvasPanel children）

`ScrollContent` **能**有 children——往里拖 30 个 **Image**：

- 名字 `ScrollItem001` ~ `ScrollItem030`
- 这 30 个 C++ 没 `BindWidget` 字段，**不需要勾 `Is Variable`**
- 每个：Anchor 左上 / Alignment (0,0) / Size (620, 72) / Brush=`slot_bg`
- Position：第 N 个的 Y = `(N-1) * 80`，X 全是 0
  - `ScrollItem001`: (0, 0)
  - `ScrollItem002`: (0, 80)
  - `ScrollItem003`: (0, 160)
  - ……
  - `ScrollItem030`: (0, 2320)

**省事写法**：拖一个 `ScrollItem001` 配置好 → Hierarchy 里右键 **Duplicate** 29 次 → 逐个改名 + 改 Y。或者 **baseline 第一版只放 3 个先意思一下**，等 Phase 1 真做 scroll 测试时再补全 30 个。

Compile + Save。

## 六、Map 接 Level Blueprint

让 PIE 时 UI 真的显示出来。每个 Map 都要做一次。

### 6.1 LoginMap

1. Content Browser 双击 `LoginMap` 打开
2. 顶栏 **Blueprints**（齿轮图标）> **Open Level Blueprint**
3. 空白画布上：
   - 已有 `Event BeginPlay` 节点（红色）；没有的话右键画布 → 搜 `Event BeginPlay`
   - 从 `Event BeginPlay` 右边**白色三角输出 pin** 拖到空白 → 弹搜框，搜 `Create Widget` → 选 **Create Widget**
   - 新节点的 **Class** 下拉选 `WBP_LoginScreen`
   - 从 Create Widget 的 **Return Value**（蓝色圆 pin）拖出 → 搜 `Add to Viewport` → 选 **Add to Viewport**
4. 三个节点白色三角应自动连成串：`BeginPlay → Create Widget → Add to Viewport`
5. 顶栏 **Compile** + **Save**

### 6.2 PocPlaygroundMap

重复一次，Class 选 `WBP_PocPlayground`。

## 七、Project Settings 设默认 Map

`Edit > Project Settings > Maps & Modes > Default Maps`：

- **Editor Startup Map** = `LoginMap`
- **Game Default Map** = `LoginMap`

UE 自动把这两项写回 `Config/DefaultEngine.ini`。下次双击 `.uproject` 启动 Editor 会自动打开 LoginMap。

## 八、Play 看效果

主 Editor 顶栏 **Play** 按钮（▶ 或 Alt+P）→ 进入 PIE。LoginMap 应该显示出蓝色 panel + 两个 input 框 + Login 按钮。按 **Esc** 退出 PIE。

PocPlaygroundMap 同理（打开 Map 再 Play 才会换场景）。

## 九、常见坑

| 现象 | 原因 | 修法 |
|---|---|---|
| Compile 后 BindWidget 报 error | 名字拼错 / 大小写不对 / 没勾 `Is Variable` | Hierarchy 逐个核对，Details 顶部勾 `Is Variable` |
| Image 显示成纯白方块 | Brush > Image 没指定 texture / texture import 失败 | Details 重选 texture，或回 Content Browser 确认 Sprites/ 有该贴图 |
| Play 进 PIE 一片黑 | Map 的 Level Blueprint 没接 / Compile 失败 | 回 Level Blueprint，确认三节点连通 + Compile 绿勾 |
| Welcome 部分 PIE 时还显示 | Visibility 设的是 `Collapsed` 或 `Visible` 而不是 `Hidden` | Details > Behavior > Visibility 改 `Hidden` |
| Designer 里看不到刚拖的 widget | Slot Position / Size 超出可见区 / Anchor 设错 | 检查 Slot 折叠区，Anchor 选对预设格 |
| PIE / Designer 里 UI 中心跑到屏幕左上角，只露出右下 1/4 | LoginScreen 节点的 Anchor 还是默认的"左上"，没改成"中心" | 参 [§4.4](#44-怎么设-anchor--alignment--position必读做错只显示-14)，每个节点 Slot > Anchors 九宫格点中间格，再把 Alignment 改成 `(0.5, 0.5)` |
| ScrollItem 30 个嫌烦 | baseline 第一版可只放 3 个 | Phase 1 真做 scroll 测试时再补 |

## 十、跑通后的验证清单

- [ ] WBP_LoginScreen Compile 全绿
- [ ] WBP_PocPlayground Compile 全绿
- [ ] LoginMap Level Blueprint Compile 全绿
- [ ] PocPlaygroundMap Level Blueprint Compile 全绿
- [ ] PIE LoginMap 能看到 panel + inputs + Login 按钮
- [ ] PIE PocPlaygroundMap 能看到 6 个 click_target + text_target + drag pair + scroll 区域
- [ ] `Config/DefaultEngine.ini` 里 `GameDefaultMap=/Game/Maps/LoginMap.LoginMap` 被自动写回
- [ ] `python scripts/fixtures/validate_static_fixtures.py --engine unreal` 全绿

## 十一、字体处理（baseline 前再做）

UMG Text 默认用 Roboto SDF（UE 自带），baseline 阶段已经够用。要换 fixture/ 自带字体：

1. 把 `Content/UI/Fonts/Roboto-Regular.ttf` 拖进 Content Browser → 自动生成 Font 资产 + FontFace
2. 每个 TextBlock 的 Details > Appearance > Font > Font Family 改成新生成的 Roboto Font 资产
3. 中文兜底：同样导入 `NotoSansCJK-Regular.otf`，在 Roboto Font 资产的 **Fallback Fonts** 列表加进去

这步是 baseline capture 前才需要做的事，[10 §九 Baseline 捕获顺序](10-fixture-setup-guide.md#九baseline-捕获顺序) 之前先完成。

## 十二、相关章节

- [04 主文档](04-adapter-unreal.md) - adapter 实现细节
- [04a 分层补充](04a-adapter-unreal-cpp-blueprint-layering.md) - 为什么 WidgetTree 是 fixture A 档不能自动化
- [10 fixture 总指南](10-fixture-setup-guide.md) - 三引擎统一规范
- `fixtures/unreal-test-project/Scripts/build_fixtures.py` - 跑这个之后才进 UMG 手工流程
