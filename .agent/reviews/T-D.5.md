# Review: T D.5 — ShowUI Grounding 后端

**任务**: showui.py — ShowUI-2B Grounding 后端
**分支**: task/td5-showui-grounding
**PR**: #23
**Reviewer**: test-agent (gaobiedongtian)
**日期**: 2026-04-18
**轮次**: 1

## 验收 Checklist

| # | 项目 | 结果 |
|---|------|------|
| 1 | `pytest tests/unit/backends/test_showui.py` 全通过 | ✅ 5/5 passed |
| 2 | ShowUIGroundingBackend 满足 GroundingBackend Protocol | ✅ |
| 3 | 归一化坐标→绝对坐标转换 | ✅ 已验证 |
| 4 | 越界坐标 clamp 到 [0, w-1]/[0, h-1] | ✅ 已验证 |
| 5 | JSON 解析 + x=y= pattern fallback | ✅ 已验证 |
| 6 | 无法解析→GroundingBackendError | ✅ 已验证 |

## 代码质量

- 归一化 [0,1] 坐标设计 — 适配不同分辨率
- _parse_coordinates 双 fallback — 容错性好
- confidence_threshold 可配置 — 适配不同精度需求
- _get_image_dimensions 用 cv2 解码 — 正确获取图像尺寸
- 图片解码失败 fallback 到 1920x1080 — 合理

## 结论

**APPROVED** — 无修改要求。
