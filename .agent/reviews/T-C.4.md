# Review: T C.4 — 视觉变化/卡死检测

**任务**: change_detector.py — 视觉变化/卡死检测 (环形缓冲 + SSIM)
**分支**: task/tc4-change-detector
**PR**: #17
**Reviewer**: test-agent (gaobiedongtian)
**日期**: 2026-04-18
**轮次**: 1

## 验收 Checklist

| # | 项目 | 结果 |
|---|------|------|
| 1 | `pytest tests/unit/perception/test_change_detector.py` 全通过 | ✅ 7/7 passed |
| 2 | 环形缓冲 + 时间窗口剪枝 | ✅ deque + _prune |
| 3 | is_static: 相邻帧 SSIM >= threshold | ✅ 已验证 |
| 4 | 单帧返回 False（不能判断卡死） | ✅ 已验证 |
| 5 | reset 清空缓冲 | ✅ 已验证 |

## 代码质量

- 环形缓冲 (deque) + 时间窗口剪枝 — 内存效率高
- push + is_static + reset 三接口简洁
- 相邻帧两两 SSIM 比较 — 正确的卡死检测逻辑
- 可配置 static_threshold — 适配不同场景

## 结论

**APPROVED** — 无修改要求。
