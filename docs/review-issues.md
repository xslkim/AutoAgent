# 文档 Review 问题清单

> 来源：2026-05-12 全量文档 review，共发现 20 个问题。
> 修改状态：✅ 已完成 / ⏳ 待定 / ❌ 忽略

---

## 关键问题（Critical / High）

### 1. 06-visual-regression.md 章节编号错乱 ✅
**位置**：`docs/06-visual-regression.md`「二、防护 0」
**处理**：已重新排序为 2.1 → 2.2 → 2.3 → 2.4 → 2.5。

### 2. MCP Tool 分组与任务清单矛盾 ✅
**位置**：`docs/02-mcp-server.md` vs `docs/tasks.md`
**处理**：
- tasks.md 已拆分为 99-tasks-phase0~4.md 五个文件
- TASK-0115（invoke_method/get_property/set_property）从 Phase 1 移至 Phase 4，与 02-mcp-server.md 一致

### 3. ARCHITECTURE.md 工作量估算加总不一致 ✅
**位置**：`ARCHITECTURE.md`
**处理**：已删除所有工作量估算内容，ARCHITECTURE.md 精简为决策摘要 + 架构图 + 文档导航。

### 4. ARCHITECTURE.md 定位模糊 ✅
**位置**：`ARCHITECTURE.md` 第 28 行
**处理**：已精简为摘要 + 关键决策 + 架构图 + 指向 docs/ 的导航。删除了重复的阶段计划、详细风险、调研引用。

### 5. 大量跨文档引用指向不存在的文件 ✅
**位置**：多处
**处理**：
- `docs/00-product-overview.md` 文档导航表新增"状态"列，标注未来产出文件及其对应任务编号
- 确认所有引用文件均为必要产出，由对应 TASK 在后续 Phase 创建
- `scripts/fixtures/bootstrap_fixture_assets.py` 和 `scripts/fixtures/validate_static_fixtures.py` 保留引用，作为 fixture 阶段必要工具

### 6. 「程序员搭建边界」约束在 6+ 个文档中重复定义 ✅
**位置**：00 §四, 01 §三, 03 §三, 04 §三, 05 §三, 10 §二
**处理**：
- `01-protocol-spec.md` §三：长版重复内容精简为简版，添加"完整约束以 00 为准"
- `10-fixture-setup-guide.md` §二：新增"唯一权威定义见 00"的明确声明
- `00-product-overview.md` §四 保留为 normative 权威定义

### 7. 硬编码 Windows 路径导致不可移植 ✅
**位置**：`02-mcp-server.md`, `09-orchestration.md`
**处理**：
- `D:/AutoAgent/mcp-server` → `<REPO_ROOT>/mcp-server`
- `D:\AutoAgent.worktrees\` → `<REPO_ROOT>.worktrees\`，并添加 Windows/Linux/macOS 路径示例
- `D:\AutoAgent\` → `<REPO_ROOT>\`

---

## 中等问题（Medium）

### 8. `stable_id_source: "auto"` 在 Unity 端无实现 ✅
**位置**：`01-protocol-spec.md` §三 vs `03-adapter-unity.md`
**处理**：Unity 和 Godot 均通过框架实现 `auto` 来源——Unity `StableIdComponent.AutoDeclaredId` + `[AutoAgentId]` 特性扫描；Godot `autoagent_declared_id` meta + `@export` 变量扫描。与 UE 的 `UPROPERTY(meta=(AutoAgentId=...))` 等价。

### 9. TASK-0132 依赖过重形成瓶颈 ✅
**位置**：`docs/tasks.md` TASK-0132
**处理**：维持现有设计，不拆分。15 个前置依赖确保所有基础设施在 AI 执行复杂任务前就绪，优先稳定和可控。

### 10. 路径白名单规则存在三份「权威源」 ✅
**位置**：`06-visual-regression.md` §2.1, `07-agent-operations.md` §3.2, `scripts/ci/path_whitelist.yml`
**处理**：
- `06-visual-regression.md` §2.1：明确 `scripts/ci/path_whitelist.yml` 是唯一权威源
- `07-agent-operations.md` §3.2：改写为"唯一权威源：YAML 文件"

### 11. 03-adapter-unity.md 已知坑与当前约束矛盾 ✅
**位置**：`03-adapter-unity.md` §九 已知坑第 7 条
**处理**：已更新为"StableIdComponent 可以挂到任意 GameObject，prefab 根节点也支持"。

### 12. 04-adapter-unreal.md 内部引用格式不匹配 ✅
**位置**：`04-adapter-unreal.md`
**处理**：`§六-A` → `§三 AI 实现路径`（链接到正确的章节锚点）；`06-visual-regression.md` 中对应引用 `§3.5` → `[04 §三 路径 A](04-adapter-unreal.md)`。

### 13. 引擎版本号统一 ✅
**位置**：多处
**处理**：
- Unreal Engine：全部 `5.6` → `5.7`（含 04-adapter-unreal.md, 08-ci-runners.md, 00-product-overview.md, 10-fixture-setup-guide.md）
- Godot：全部 `4.3` → `4.6`（含 05-adapter-godot.md, 08-ci-runners.md, 00-product-overview.md, 10-fixture-setup-guide.md）
- CI runner 标签 `UE-5.6` → `UE-5.7`
- Godot CI 下载文件名 `Godot_v4.3-stable` → `Godot_v4.6-stable`
- `ENGINE_MINOR_VERSION >= 6` → `>= 7`
- Godot known issue 描述已更新

### 14. `~/.autoagent/` Unix 路径未做 Windows 适配说明 ✅
**位置**：02/06/07/08 等多处
**处理**：在 `02-mcp-server.md` 的配置文件路径和日志文件路径首次出现处添加 Windows 对应路径说明（`%USERPROFILE%\.autoagent\`）。

### 15. 02-mcp-server.md SSIM 内存预算描述不准确 ✅
**位置**：`02-mcp-server.md` §十
**处理**：改为"运行时内存 ~5MB，安装大小约 80-100MB"。

---

## 低优先级（Low / Cosmetic）

### 16. docs/00 §四 表格中 `Mask` 归属模糊 ✅
**位置**：`docs/00-product-overview.md`
**处理**：从"程序员可手放"列移除 `Mask`，改为"由 AI 在代码里加"。

### 17. 缺少 README.md ❌
**位置**：项目根目录
**处理**：暂时不创建。

### 18. Phase 0 任务编号与执行顺序不一致 ✅
**位置**：`docs/tasks.md`
**处理**：TASK-0017（gate review，依赖所有其他任务）重新编号为 TASK-0023，移至 Phase 0 文件末尾，反映其作为最后一个任务的位置。tasks.md 中所有引用已同步更新。

### 19. 禁止 force push 到任意分支过于严格 ✅
**位置**：`07-agent-operations.md` §5.2
**处理**：改为"禁止 force push 到 main / protected branch，feature branch 允许"。

### 20. `logical_role` 取值表缺少 `draggable` / `drop_zone` ✅
**位置**：`01-protocol-spec.md` §三 logical_role 取值表
**处理**：在取值表中新增 `drag_source` 和 `drop_target` 两个条目，说明三引擎的对应实现方式。
