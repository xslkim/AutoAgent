---
task_id: T B.1
title: DPI 归一化初始化
agent: dev
status: ready_for_test
pr: 7
iteration: 1
---

# T B.1: DPI 归一化初始化

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/control/__init__.py` | control 包初始化 |
| `src/autovisiontest/control/dpi.py` | DPI 归一化工具 |
| `tests/unit/control/test_dpi.py` | 5 项单元测试 |

## 实现细节

### enable_dpi_awareness()
- 首先尝试 `SetProcessDpiAwareness(2)` (Per-Monitor V2)
- 失败降级到 `SetProcessDPIAware()`
- 再失败记录 warning
- 幂等：通过 `_DPI_AWARENESS_ENABLED` 全局标志

### get_primary_screen_size()
- 返回 `(width, height)` 物理像素
- 调用前自动 `enable_dpi_awareness()`

### get_dpi_scale()
- 返回 DPI 缩放因子 (1.0 / 1.25 / 1.5 等)
- 通过 `GetDeviceCaps(LOGPIXELSX) / 96` 计算

## 验收 Checklist

- [x] `pytest tests/unit/control/test_dpi.py` 全通过 (5/5)
- [x] `enable_dpi_awareness` 幂等
- [x] `get_primary_screen_size` 返回 (int, int) 且均 > 0
