# 06 - 视觉回归与美术保真

> 用引擎自带工具 + 业界阈值，**不自研算法**。叠 5 道防护保证 AI 不会破坏美术效果。

## 一、整体策略

> ⚠️ **重要边界**：协议层的 schema 权限分离只能拦住 *runtime API* 写 visual。
> AI Agent 是直接写源码（C# / C++ / GDScript），完全可以在源码里直接改 visual 字段、改场景文件、换 sprite 引用。
> **必须在源码层（防护 0）也建立审计 + 路径白名单 + diff gate，才形成真正的安全边界**。

```
┌────────────────────────────────────────────────────────────────────┐
│  0. 源码层防护（PR diff 审计 + 路径白名单 + dump 前后 diff）        │
│     拦截 AI 在源码 / 场景文件里偷改 visual / 结构。最重要的一道。   │
├────────────────────────────────────────────────────────────────────┤
│  1. 协议层硬约束（schema 权限分离）                                 │
│     运行时 set_property 只允许 behavior / meta，拒 visual / 结构    │
├────────────────────────────────────────────────────────────────────┤
│  2. ID 稳定性（pinned / auto declared，禁用 hash 作 task contract）│
│     美术迭代 + hot reload + PIE 后 ID 不丢                          │
├────────────────────────────────────────────────────────────────────┤
│  3. 视觉回归（截图 + 引擎 diff + SSIM + LLM 二次裁决）              │
│     每次 AI 改完代码自动截图比 baseline                             │
├────────────────────────────────────────────────────────────────────┤
│  4. 资源 GUID 追踪（引擎自带，不污染框架）                          │
│     引用关系靠 .meta / AssetRegistry / .uid                         │
└────────────────────────────────────────────────────────────────────┘
```

**关键认识**：防护 1-4 都建立在防护 0 之上。AI 一旦能改源码绕过 runtime API，1-4 就只是"好心提示"，不是"安全边界"。

## 二、防护 0：源码层审计（最重要）

### 2.1 路径白名单（PR diff 阶段强制）

CI 第一步是 diff 路径检查。AI 触发 PR 后，扫 changed paths：

| 路径模式 | AI 是否允许修改 | 备注 |
|---|---|---|
| `adapters/{unity,unreal,godot}/Runtime/**/*.cs *.cpp *.h *.gd` | ✅ | adapter 框架代码 |
| `adapters/{unity,unreal,godot}/Tests/**` | ✅ | adapter 测试 |
| `mcp-server/src/**/*.py mcp-server/tests/**/*.py` | ✅ | MCP server 代码 + 测试 |
| `fixtures/*/Scripts/**/*.cs *.cpp *.h *.gd` | ✅ | fixture 业务脚本（AI 实现交互） |
| `fixtures/*/*.unity *.uasset *.tscn *.umap` | ❌ | 静态场景文件（程序员手搭，AI 不碰） |
| `fixtures/*/Assets/Sprites/** Resources/UI/** Content/UI/**` | ❌ | 美术资源 |
| `fixtures/*/Assets/Fonts/**` | ❌ | 字体 |
| `fixtures/*/ProjectSettings/** Config/DefaultEngine.ini` | ❌ | 引擎配置 |
| `baselines/**` | ❌ | 视觉 baseline，单独 PR |
| `.github/workflows/**` | ⚠️ | 需人工 review |
| `**/.env **/secrets/** **/*.key **/*.pem` | ❌ | 永禁 |
| `docs/00-08*.md` | ❌ | 产品文档（除非任务明确要求） |

CI 实现：`scripts/ci/check_changed_paths.py` 用 `git diff --name-only origin/main...HEAD` 拿 changed 文件列表，对照白名单 fail-closed。

### 2.2 源码 diff 审计（AST/regex 扫描）

即使 AI 只改 fixture scripts，也可能在 C# / C++ / GDScript 里设置 visual 属性。CI 第二步扫源码 diff：

**Unity（C#）禁止赋值的字段：**
```regex
\.transform\.(position|localPosition|rotation|localRotation|localScale)\s*=
\.rectTransform\.(anchoredPosition|sizeDelta|anchorMin|anchorMax|pivot)\s*=
\.color\s*=          # Image/Text/Graphic.color
\.sprite\s*=         # Image.sprite
\.material\s*=       # Renderer.material
SetActive\((true|false)\)
\.enabled\s*=        # 仅针对 Image/Renderer/Graphic
```

**UE（C++）禁止：**
```regex
SetVisibility|SetRenderOpacity|SetColorAndOpacity|SetBrushFromTexture
SetRenderTransform|SetRenderScale|SetRenderTranslation
SetBrush\(|SetBrushFromAsset
```

**Godot（GDScript）禁止：**
```regex
\.position\s*=|\.global_position\s*=|\.size\s*=
\.modulate\s*=|\.self_modulate\s*=
\.texture\s*=|\.icon\s*=
\.visible\s*=|\.show\(\)|\.hide\(\)
```

CI 实现：`scripts/ci/audit_visual_writes.py`
- C# 用 Roslyn 命令行（`dotnet roslyn`） / SyntaxKind 树
- C++ 用 libclang AST（Python `clang.cindex`）
- GDScript 用 regex（语言简单足够）
- 结果：fail with line numbers + 违规字段名

**白名单豁免**：业务允许的 visual 操作（如"按钮按下变色"动画）必须在文件顶部显式声明：

```csharp
// AUTOAGENT_ALLOW_VISUAL: button-press-feedback
public class ButtonFeedback : MonoBehaviour {
    public void OnPress() { image.color = Color.gray; }  // 豁免
}
```

扫描器跳过这些文件的视觉字段检查（仍记录到 audit log，方便 review 时核对）。

### 2.3 dump 前后 diff gate（运行时验证）

CI e2e 测试时：
1. 启动引擎、加载 fixture scene
2. **AI 代码挂载前** dump 一次树 → `before.json`
3. AI 添加的脚本 / 行为执行
4. dump 一次 → `after.json`
5. 对比 `before.json` 和 `after.json` 的所有节点 visual 字段

**期望**：visual 字段完全一致（除非该节点在 AUTOAGENT_ALLOW_VISUAL 白名单内）。
**任何 visual 字段变化** → CI fail，附 diff 详情（哪个节点的哪个字段从 X 变成 Y）。

实现：`scripts/ci/diff_visual_dump.py`，对比 JSON 树。

### 2.4 PR Review Gate

- CI 全绿才允许 merge（GitHub branch protection rule）
- visual / 结构 diff 失败的 PR 必须 human review approve（不允许 AI 自己 dismiss）
- baseline 更新走单独 PR（path: `baselines/**`），强制 human review

## 三、防护 1：协议层 Schema 权限分离

实现位置：协议层（[01-protocol-spec.md](01-protocol-spec.md)）已规定。adapter 实现 setter 时强制校验：

```csharp
// 例：Unity adapter
public void SetProperty(NodeData node, string property, object value, string category) {
    if (category == "visual") {
        throw new VisualPropertyWriteError(property);  // -32003
    }
    // behavior / meta 才放行
}
```

错误码 `-32003 VisualPropertyWrite` / `-32004 StructuralChange`。

AI 收到错误后会自我修正——schema 层面的硬规则，AI 无法绕过 *runtime API*。但**不能阻止 AI 改源码**——见防护 0。

## 四、防护 2：ID 稳定性

### 算法
```
stable_id = pinned_id (来源 1)
       or auto_declared_id (来源 2/3, 来自源码 / 注册表)
       or hash(transform_path + name + type)[:12]   // 仅诊断
```

### Pin / Declare 机制

每个引擎 adapter 必须实现以下"显式声明"机制（详见各 adapter 文档）：
- **Unity**：`StableIdComponent` MonoBehaviour（pin via Inspector）
- **UE**：`UPROPERTY(meta=(AutoAgentId="..."))` 或运行时 `RegisterStableId` 或 `Config/AutoAgentIds.ini`
- **Godot**：`Object.set_meta("autoagent_pinned_id", "...")`

### 强制约束（normative）

**任务 DSL 引用的节点必须 `stable_id_source ∈ {pinned, auto}`，禁止引用 `hash`**。

MCP server 在加载任务时校验：
```python
def validate_task_dsl(task, current_dump):
    referenced_ids = extract_ids_from_task(task)
    for id in referenced_ids:
        node = find_node(current_dump, id)
        if node is None or node.stable_id_source == "hash":
            raise TaskValidationError(f"ID '{id}' must be pinned or auto-declared")
```

### Orphan Detection
每次 `dump_tree`：
1. 加载上次 dump 的 ID 列表（持久化到 `Library/AutoAgent/last_scan.json`）
2. 比对当前树
3. 上次见过这次找不到 → orphan
4. 通过 `list_orphan_ids` MCP tool 暴露给 AI

**AI 看到 orphan 必须停下来要求人工 rebind，禁止自动猜测**——这是 prompt 层面的约定（见 [07-agent-operations.md](07-agent-operations.md)）。

## 五、防护 3：视觉回归

### 5.1 引擎自带能力（不重复造轮子）

**Unity**：`com.unity.testframework.graphics`（Graphics Test Framework）
- `ImageComparisonSettings.PerPixelCorrectnessThreshold` / `AverageCorrectnessThreshold` / `IncorrectPixelsThreshold`
- 自动生成 diff 图

**Unreal**：Screenshot Comparison Tool（Functional Screenshot Test Actor）
- 区分 "scene view" / "UI screenshot"
- 结果落 `Saved/Automation/Comparisons`

**Godot**：无原生 baseline diff 工具，框架自实现（`Image` API + scikit-image SSIM）

### 5.2 框架 Vision 模块（MVP 仅 SSIM）

`mcp-server/src/autoagent_mcp/vision/comparator.py`：

```python
def compare(current_path, baseline_path, method="ssim"):
    img_c = load_image(current_path)
    img_b = load_image(baseline_path)
    
    if method == "ssim":
        score = compute_ssim(img_c, img_b)  # scikit-image
        return {
            "method": "ssim",
            "score": score,
            "pass": score >= 0.95,
            "warn": score < 0.92,
            "diff_path": save_diff(img_c, img_b) if score < 0.95 else None,
        }
    elif method == "lpips":
        # Phase 4 only: 启用前必须 pip install autoagent-mcp[lpips]
        # 强制子进程化避免 PyTorch 污染主 server 内存
        from .lpips_subprocess import run_lpips
        return run_lpips(current_path, baseline_path)
```

**MVP 决策**：仅启用 SSIM。LPIPS 需 PyTorch（~500MB）破坏 MCP server <100MB 预算，**Phase 4 才引入 + 子进程化 + 可选安装**。

### 5.3 业界阈值

| 指标 | 视觉安全 | 触发告警（→ LLM 二次裁决） |
|---|---|---|
| SSIM | ≥ 0.95 | < 0.92 |
| LPIPS（Phase 4） | < 0.10 | ≥ 0.20 |

**不要用 pHash**：对 UI 误判率高（实测会因为字体 hinting 微差就误判）。

### 5.4 Baseline 管理

```
baselines/
├─ unity/windows/{login_screen.png, login_screen.meta.json}
├─ unreal/windows/...
└─ godot/linux/...
```

- `meta.json`：`{ engine_version, resolution, color_space, captured_at, captured_by, runner_label }`
- 每个引擎独立 baseline + 每个 OS 独立子目录（pixel 差异不可避免）
- 第一次跑通后程序员 review 截图 → manual approve → commit
- Baseline 更新走单独 PR（防护 0 路径白名单外，强制 human review）

### 5.5 多模态 LLM 二次裁决

SSIM 报警后（< 0.92），不直接 fail，先让 Claude Vision 看：

```python
def llm_judge(current_path, baseline_path, ssim_score):
    if ssim_score >= 0.95:
        return {"verdict": "pass"}
    
    response = claude.messages.create(
        model="claude-opus-4-7",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": load_image(baseline_path)},
                {"type": "image", "source": load_image(current_path)},
                {"type": "text", "text": (
                    "First image is the design baseline. Second is the current "
                    "implementation. Are they visually equivalent? Differences in "
                    "anti-aliasing, sub-pixel rendering, or interactive states "
                    "(button hover) are acceptable. Layout shifts, color changes, "
                    "missing elements are NOT acceptable. Reply JSON: "
                    "{\"verdict\":\"pass\"|\"fail\",\"reason\":\"...\"}"
                )}
            ]
        }]
    )
    return parse_json(response)
```

**为什么需要**：抗锯齿 / 字体 hinting 这类无意义差异不应该 fail；纯 SSIM 看不出"按钮颜色改了"和"按钮按下高亮"的区别。LLM 能。

## 六、防护 4：资源 GUID 追踪

引擎自带，框架不重复实现：
- **Unity**：`.meta` 里的 `guid`，`AssetDatabase.GUIDFromAssetPath`
- **UE**：`AssetRegistry`，`FSoftObjectPath`
- **Godot**：4.x 的 `.uid`

dump_tree 输出 `visual.sprite_ref` 时优先用 GUID/UID 而不是 path（path 会因美术重组变化，GUID 不变）。

## 七、闭环里的视觉回归集成

### 自动跑（每个 AI 任务）
```
1. AI 写完代码 → push branch
2. CI 步骤 1：路径白名单检查（防护 0.1）        — 30s
3. CI 步骤 2：源码 diff 审计（防护 0.2）         — 30s
4. CI 步骤 3：编译 + 单元测试                    — 1-5 min
5. CI 步骤 4：启动引擎 → dump before → 跑 AI 代码 → dump after → diff（防护 0.3）
6. CI 步骤 5：take_screenshot → compare_to_baseline（防护 3）
7. 全 pass → 标记 task ready for review
8. 任意 fail → AI 看日志 + diff 图 → 修复 → 再触发（autonomous loop，迭代上限见 07）
```

### 手动跑（baseline 更新）
程序员搭完 UI → 启动框架手动调 take_screenshot → review → 单独 PR commit。

## 八、配置

`~/.autoagent/config.toml`：

```toml
[vision]
ssim_threshold = 0.95
ssim_warn_threshold = 0.92        # 触发 LLM 二次裁决
lpips_enabled = false              # MVP 仅 SSIM；Phase 4 启用
lpips_threshold = 0.10
lpips_subprocess = true            # 子进程化以隔离 PyTorch 内存
baseline_dir = "./baselines"
diff_dir = "./diffs"

[claude_vision]
enabled = false
api_key_env = "ANTHROPIC_API_KEY"
model = "claude-opus-4-7"
max_diff_per_session = 20

[source_audit]
enabled = true
rules_file = "scripts/ci/visual_write_rules.yml"
```

## 九、Phase 出口标准（重点）

| Phase | 出口标准 |
|---|---|
| Phase 0 | 防护 0.1（路径白名单）+ 0.2（源码 diff）CI 步骤可跑通；故意触发一次"AI 改了 .unity / .uasset / .tscn 文件"必须被 CI 拦下 |
| Phase 1 | Unity 全套 5 道防护 + login MVP 视觉回归绿；故意"AI 在 C# 里写 image.color = ..."被防护 0.2 拦下 |
| Phase 2 | UE 全套防护 + 跨引擎 baseline 独立维护 |
| Phase 3 | Godot 全套防护 + ClassDB cache 联通防护 2 |
| Phase 4 | LPIPS / LLM 裁决稳定 + 性能优化 |

## 十、已知边界

- **动画状态**：MVP 不做"按钮按下时刻"截图。Loading 旋转、过场动画 Phase 4 加（多帧序列对比）
- **平台间像素差**：Mac Retina vs Windows 标准分屏 → baseline 必须按平台分目录
- **Linear vs Gamma color space**：每次截图前确认引擎 color space 一致（在 [08-ci-runners.md](08-ci-runners.md) 锁定）
- **字体 fallback**：missing font 渲染豆腐方块——baseline 时 fail，等用户补字体
- **源码审计的局限**：regex / AST 扫描可能被字符串拼接、反射、运算符重载绕过。配合防护 0.3（dump 前后 diff）兜底
- **C# Roslyn 依赖**：CI 需安装 .NET SDK + 写 Roslyn analyzer；Phase 1 起步用 regex，Phase 4 升级 AST
