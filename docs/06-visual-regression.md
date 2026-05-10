# 06 - 视觉回归与美术保真

> 用引擎自带工具 + 业界阈值，**不自研算法**。叠 4 道防护保证 AI 不会破坏美术效果。

## 一、整体策略

```
┌──────────────────────────────────────────────────────────────┐
│  1. 非侵入硬约束（schema 权限分离）                          │
│     AI 只能写 behavior + meta，禁止写 visual / 结构          │
├──────────────────────────────────────────────────────────────┤
│  2. ID 稳定性（stable_id + pin + orphan tracker）             │
│     美术迭代后 ID 不丢                                       │
├──────────────────────────────────────────────────────────────┤
│  3. 视觉回归（截图 + SSIM + LPIPS + LLM 二次裁决）            │
│     每次 AI 改完代码自动截图比 baseline                      │
├──────────────────────────────────────────────────────────────┤
│  4. 资源 GUID 追踪（引擎自带，不污染框架）                    │
│     引用关系靠 .meta / AssetRegistry / .uid                   │
└──────────────────────────────────────────────────────────────┘
```

## 二、防护 1：schema 权限分离

**实现位置**：协议层（01-protocol-spec.md）已规定。adapter 实现 setter 时强制校验。

```csharp
// 例：Unity adapter
public void SetProperty(NodeData node, string property, object value, string category) {
    if (category == "visual") {
        throw new VisualPropertyWriteError(property);
    }
    // behavior / meta 才放行
}
```

错误码 `-32003 VisualPropertyWrite` / `-32004 StructuralChange`。

AI 收到错误后会自我修正——这是 schema 层面的硬规则，AI 无法绕过。

## 三、防护 2：ID 稳定性

### 算法
```
stable_id = pinned_id if pinned else hash(transform_path + name + type)[:12]
```

### Pin 机制
- Editor Inspector 提供 UI（三引擎都有）
- 美术 / 程序员选中节点 → 输入想要的 ID → 持久化到组件字段（Unity StableIdComponent / UE StableIdMeta UObject / Godot Object.set_meta）

### Orphan Detection
每次 `dump_tree` 调用时：
1. 加载上次 dump 的 ID 列表（持久化到 `Library/AutoAgent/last_scan.json`）
2. 比对当前树
3. 上次见过这次找不到 → orphan
4. orphan 列表通过 `list_orphan_ids` MCP tool 暴露给 AI

**AI 看到 orphan 必须停下来要求人工 rebind，禁止自动猜测**——这是 prompt 层面的约定，写在 task spec 里。

## 四、防护 3：视觉回归

### 4.1 引擎自带能力（不重复造轮子）

**Unity**：`com.unity.testframework.graphics`（Graphics Test Framework）
- `ImageComparisonSettings.PerPixelCorrectnessThreshold`（DeltaE 单像素差）
- `ImageComparisonSettings.AverageCorrectnessThreshold`（整图平均差）
- `ImageComparisonSettings.IncorrectPixelsThreshold`（容错像素比例）
- 自动生成 diff 图

**Unreal**：Screenshot Comparison Tool（Functional Screenshot Test Actor）
- 区分 "scene view" / "UI screenshot"
- 结果落 `Saved/Automation/Comparisons`
- Session Frontend 可视化 diff

**Godot**：无原生 baseline diff 工具，框架自实现（用 `Image.compute_image_metrics` 做 SSIM 计算）。

### 4.2 框架的 Vision 模块（包装上面三种）

`mcp-server/src/autoagent_mcp/vision/comparator.py`：

```python
def compare(current_path, baseline_path, method="both"):
    img_c = load_image(current_path)
    img_b = load_image(baseline_path)
    
    result = {}
    if method in ("ssim", "both"):
        result["ssim"] = compute_ssim(img_c, img_b)
    if method in ("lpips", "both"):
        result["lpips"] = compute_lpips(img_c, img_b)  # 用 lpips package, GPU/CPU 都行
    
    result["pass"] = (
        result.get("ssim", 1.0) >= 0.95 and
        result.get("lpips", 0.0) < 0.10
    )
    
    if not result["pass"]:
        result["diff_path"] = save_diff_image(img_c, img_b)
    
    return result
```

### 4.3 业界阈值（已收敛）

| 指标 | 视觉安全 | 触发告警 |
|---|---|---|
| SSIM | ≥ 0.95 | < 0.92 |
| LPIPS | < 0.10 | ≥ 0.20 |

**不要用 pHash**：对 UI 误判率高。

### 4.4 Baseline 管理

```
baselines/
├─ unity/
│  ├─ login_screen.png
│  ├─ login_screen.meta.json   # { engine_version, resolution, captured_at, captured_by }
│  └─ ...
├─ unreal/
└─ godot/
```

- 第一次跑通后程序员 review 截图 → manual approve → commit 到 `baselines/`
- Baseline 更新走 PR + 视觉 review
- 每个引擎独立 baseline（不同引擎渲染像素不同）

### 4.5 多模态 LLM 二次裁决

SSIM 报警后（< 0.92），不直接 fail，先让 Claude Vision 看：

```python
def llm_judge(current_path, baseline_path, ssim_score):
    if ssim_score >= 0.95:
        return {"verdict": "pass", "reason": "above threshold"}
    
    response = claude.messages.create(
        model="claude-opus-4-7",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": load_image(baseline_path)},
                {"type": "image", "source": load_image(current_path)},
                {"type": "text", "text": "First image is the design baseline. Second is the current implementation. Are they visually equivalent? Differences in anti-aliasing, sub-pixel rendering, or interactive states (button hover) are acceptable. Layout shifts, color changes, missing elements are NOT acceptable. Reply with JSON: {\"verdict\": \"pass\"|\"fail\", \"reason\": \"...\"}"}
            ]
        }]
    )
    return parse_json(response)
```

**为什么需要**：抗锯齿 / 字体 hinting 这类无意义差异不应该 fail；但纯 SSIM 看不出"按钮颜色改了"和"按钮按下高亮"的区别。LLM 能。

## 五、防护 4：资源 GUID 追踪

引擎自带，框架不重复实现：
- **Unity**：`.meta` 文件里的 `guid`，`AssetDatabase.GUIDFromAssetPath`
- **UE**：`AssetRegistry`，`FSoftObjectPath`
- **Godot**：4.x 的 `.uid` 文件

dump_tree 输出 `visual.sprite_ref` 时优先用 GUID/UID 而不是 path（path 会因美术重组变化）。

## 六、闭环里的视觉回归集成

### 自动跑（每个 AI 任务）
```
1. AI 写完代码 → push branch
2. CI 编译 + 单元测试
3. CI 启动引擎 headless → 跑 e2e（含 take_screenshot）
4. CI 调 compare_to_baseline → 对每个 baseline 截图比对
5. 全 pass → 标记 task ready for review
6. 任意 fail → CI 失败 → AI 看日志 + diff 图 → 修复
```

### 手动跑（baseline 更新）
```
1. 程序员搭完 UI → 启动框架手动调 take_screenshot
2. review 截图 → 满意 → commit 到 baselines/
3. 失败的话用 LLM 二次裁决 + diff 图分析原因
```

## 七、配置（写到 ~/.autoagent/config.toml）

```toml
[vision]
ssim_threshold = 0.95
lpips_threshold = 0.10
ssim_warn_threshold = 0.92  # 触发 LLM 二次裁决
lpips_warn_threshold = 0.20
baseline_dir = "./baselines"
diff_dir = "./diffs"

[claude_vision]
enabled = true
api_key_env = "ANTHROPIC_API_KEY"
model = "claude-opus-4-7"
max_diff_per_session = 20  # 防 token 爆炸
```

## 八、Phase 出口标准

| Phase | 出口标准 |
|---|---|
| Phase 0 | take_screenshot tool 三引擎可用 |
| Phase 1 | Unity 全套 4 道防护通过 + login MVP 视觉回归绿 |
| Phase 2 | UE 全套防护 + 跨引擎 baseline 独立维护 |
| Phase 3 | Godot 全套防护 + ClassDB cache 联通防护 2 |
| Phase 4 | LPIPS / LLM 裁决稳定 + 性能优化（baseline 加载缓存） |

## 九、已知边界

- **动画状态**：MVP 不做"按钮按下时刻"截图。Loading 旋转、过场动画的视觉对比 Phase 4 加（截多帧序列对比）
- **平台间像素差**：Mac Retina vs Windows 标准分屏 → baseline 必须按平台分目录
- **Linear vs Gamma color space**：每次截图前确认 `Camera.allowHDR` / `PlayerSettings.colorSpace` 一致
- **字体 fallback**：missing font 渲染豆腐方块——baseline 时如果发现，先 fail，等用户补字体
