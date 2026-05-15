# 04a - Unreal 适配器：C++ / Blueprint 分层补充

> [04 主文档](04-adapter-unreal.md) 的补充。主文档已经定了"WBP 不写 Event Graph、所有逻辑在 C++"这条硬规则；这份文档把分层模型讲透，回答**"AI 能改哪些文件 / 不能改哪些文件"**这个反复出现的问题。
>
> 适用范围：UE 5.7，与 [10 fixture 搭建指南](10-fixture-setup-guide.md) 配套阅读。

## 一、为什么必须分层

`.uasset` 是 UE 序列化的**二进制资产**。这一条事实推导出 AutoAgent 必须做的所有妥协：

- AI（包括 Claude / 本地 LLM）**读不懂二进制 .uasset**：拿不到 WidgetTree 结构、改不了一个 anchor 值。
- `git diff` 在 `.uasset` 上输出 `Binary files differ`：code review 失效。
- 任何"AI 自动给 WBP 加节点"的工作流，都得绕一圈 UE Editor Python API 才能成立——慢、脆弱、CI 不友好。

Unity 的 YAML scene 和 Godot 的 tscn 没这问题——文本格式，AI 直接读写。**这是 UE 适配器的独有困难。**

应对策略：把 UE UI 的"形状"和"行为"切开，分别交给两类载体——形状交给薄 WBP（只在 fixture 阶段一次性人工搭建），行为全部用 C++（AI 反复读写）。

## 二、三档分层

| 档位 | 载体 | 修改者 | 修改频率 | 用途 |
|------|------|--------|---------|------|
| **A. Fixture WBP** | `Content/UI/WBP_*.uasset` | **人** 在 UMG Editor | 一次（baseline 冻结后只在视觉资源更新时改） | 视觉骨架基线；adapter dump_tree 的初始状态；视觉回归 baseline 截图的来源 |
| **B. Runtime C++ 装配层** | `Source/AutoAgentTest/*UserWidget.cpp::NativeConstruct()` | **AI**（也可人工） | 每个迭代 | 在 fixture WidgetTree 上**运行时**包裹 / 替换：UImage → UButton、UImage → UEditableTextBox（[04 §三 路径 A/B](04-adapter-unreal.md#ue-特殊性fixture-不放交互-widget-的两条-ai-实现路径)） |
| **C. 纯 C++ 动态 UI**（可选） | `Source/AutoAgentTest/Tools/*.cpp` 等模块 | **AI** | 任意 | 不依赖 WBP 的整棵 widget 树由 `WidgetTree->ConstructWidget<>()` 在代码里完整构建。用于 debug overlay、AI 自己造的临时 panel、不需要 designer 预览的工具 UI |

### A 档：fixture WBP 的硬约束

为什么不能是空 WBP / 不能在 C++ 里也动态造一遍：

- **fixture 必须能在 UMG Editor 里可视化预览**——美术 / 程序员对 baseline 截图的唯一手段。
- **adapter dump_tree 的"零态"必须可重复**——同一 fixture 反复加载得到的 WidgetTree 是同一棵；纯 C++ 动态构建会引入 `NativeConstruct` 的不确定性。
- **视觉回归 baseline 截图**（[06](06-visual-regression.md)）锚定在这棵树上。

允许的 widget 类型（与 [04 §三 前提](04-adapter-unreal.md#三ui-树反射) 一致）：`UImage` / `UTextBlock` / `UCanvasPanel` / `UVerticalBox` / `UHorizontalBox` / `UScaleBox`。禁止：`UButton` / `UEditableTextBox` / `USlider` / `UScrollBox` / `UCheckBox` / `UComboBoxString`（这些 [10 §二 硬规则](10-fixture-setup-guide.md#二硬规则) 已经列了）。

### B 档：Runtime C++ 装配层是 AI 的主战场

AI 写交互的全部代码都在这里，对应 fixture 里的 `BindWidget` 字段（在 [04 §三 路径 A](04-adapter-unreal.md#路径-a包裹推荐) 给出了完整 recipe）：

```cpp
// AI 生成 / 改写的代码 - 不碰任何 .uasset
void ULoginUserWidget::NativeConstruct() {
    Super::NativeConstruct();
    UButton* Btn = WrapImageWithButton(LoginButtonBg, TEXT("LoginButton_Wrapper"));
    Btn->OnClicked.AddDynamic(this, &ULoginUserWidget::OnLoginClicked);
    AutoAgentSubsystem->TransferStableId(LoginButtonBg, Btn);
}
```

`WrapImageWithButton` 是 adapter 提供的 helper（[04 §三 路径 A](04-adapter-unreal.md#路径-a包裹推荐) 那段 boilerplate 应该收敛成一个工具函数）；AI 不需要每次手抄 ReplaceChildAt + CopySlotProperties。

### C 档：纯 C++ 动态 UI（什么时候用、什么时候别用）

**用**：
- AutoAgent 自己的工具 panel（debug overlay、节点高亮框、stable_id_source 提示气泡）
- AI 实验性临时 widget——不需要进 fixture / baseline
- 网络列表、动态生成的卡片等数据驱动的 widget（数据是 runtime 的，不该 hardcode 在 WBP 里）

**别用**：
- 任何会被 `dump_tree` baseline 锚定的视觉骨架——会破坏可重复性。

最小示例：

```cpp
UCLASS()
class AUTOAGENTTEST_API UAutoAgentDebugOverlay : public UUserWidget
{
    GENERATED_BODY()
public:
    virtual void NativeConstruct() override {
        Super::NativeConstruct();
        UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>();
        WidgetTree->RootWidget = Root;

        UTextBlock* StatusText = WidgetTree->ConstructWidget<UTextBlock>(
            UTextBlock::StaticClass(), TEXT("StatusText"));
        StatusText->SetText(FText::FromString(TEXT("AutoAgent connected.")));
        Root->AddChild(StatusText);
    }
};
```

注意：这种 widget 因为没有对应 .uasset，**parent class 在 BP-Only 项目里不会出现在 New Widget Blueprint 下拉**——必须用 `CreateWidget<UAutoAgentDebugOverlay>()` 在 C++ 里实例化。

## 三、AI 可修改文件清单

这是给 [07 agent operations](07-agent-operations.md) 的硬约束底稿，用来约束 AI 工具的写权限：

| Path | AI 可读 | AI 可写 | 说明 |
|------|---------|---------|------|
| `Source/AutoAgentTest/**.h` | ✅ | ⚠️ **追加 UPROPERTY 字段 OK；改已有 fixture 字段需 PR review** | 加新交互需要新 BindWidget 字段时允许；改 fixture 字段名 = 改 baseline = 走人工 PR |
| `Source/AutoAgentTest/**.cpp` | ✅ | ✅ | AI 主战场 |
| `Source/AutoAgentTest/Tools/**.cpp` | ✅ | ✅ | C 档纯 C++ widget |
| `Config/AutoAgentIds.ini` | ✅ | ⚠️ | 改 stable ID = 改 baseline → PR review |
| `Config/Default*.ini` | ✅ | ⚠️ | 通常 AI 不该改 |
| `Content/UI/WBP_*.uasset` | ❌（二进制无意义） | ❌ | 由 [Scripts/build_fixtures.py](../fixtures/unreal-test-project/Scripts/build_fixtures.py) 在 UE Editor 里建/改，**人工触发** |
| `Content/Maps/*.umap` | ❌ | ❌ | 同上 |
| `Content/UI/Sprites/*.uasset` | ❌ | ❌ | 美术资源由人工 PR ([10 §二](10-fixture-setup-guide.md#二硬规则)) |

agent runtime 应该把 `Content/**/*.uasset` 和 `*.umap` 显式加进 deny list，避免 AI 尝试用 `str_replace_editor` 之类的工具往二进制文件里写。

## 四、Diff / Review 礼仪

| Diff 类型 | review 路径 |
|----------|------------|
| `*.cpp` / `*.h` 任意改动 | 走 AI PR 流程，code review 走源码 diff |
| 新增 / 删除 `Source/**` 文件 | 走 AI PR 流程 |
| 任何 `Content/**` 改动 | **必须** 标注 `[fixture]` 或 `[art]`，走人工 review，附带 UMG Editor 截图 |
| `Config/AutoAgentIds.ini` 改动 | 走人工 review，因为它等价于改 stable ID |
| `Scripts/build_fixtures.py` 改动 | 走 AI PR，但跑过的产物（uasset/umap）必须由人工在 UE Editor 验证后另外 PR |

CI 在 `.uasset` diff 出现时自动 require human reviewer（[08 §三 CI 规则](08-ci-runners.md) 补一条）。

## 五、和其它引擎的对照

| 引擎 | 视觉骨架载体 | AI 可直接读写？ | 这份文档解决的问题 |
|------|--------------|-----------------|-------------------|
| Unity | `.unity` (YAML) | ✅ | 不需要——AI 可以在 scene YAML 里直接加 GameObject |
| Godot | `.tscn` (文本) | ✅ | 不需要——AI 可以直接 patch 节点 |
| **Unreal** | `.uasset` (二进制) | ❌ | **必须** 走三档分层 |

Unity 和 Godot 的 fixture / runtime 边界是软的，AI 想动 scene 文件也行；UE 的边界是硬的——`.uasset` 边界由文件格式本身强制。

## 六、相关章节

- [04 主文档](04-adapter-unreal.md) — adapter 实现细节、§三路径 A/B 的完整 code recipe、§九已知坑
- [10 fixture setup guide](10-fixture-setup-guide.md) — Phase 0 fixture 怎么搭出来
- [06 visual regression](06-visual-regression.md) — A 档 fixture 为何不能动（baseline 锚定）
- [07 agent operations](07-agent-operations.md) — 把本文 §三的可写文件清单写进 agent 工具白名单
- `fixtures/unreal-test-project/Scripts/build_fixtures.py` — A 档 WBP 的人工/半自动建立工具
