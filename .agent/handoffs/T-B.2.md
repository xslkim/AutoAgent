---
task_id: T B.2
title: 截图采集
agent: dev
status: ready_for_test
pr: 8
iteration: 1
---

# T B.2: 截图采集

## 交付物

| 文件 | 说明 |
|------|------|
| `src/autovisiontest/control/screenshot.py` | 截图采集模块 |
| `tests/unit/control/test_screenshot.py` | 4 项单元测试 |

## 实现细节

### capture_primary_screen() -> bytes
- 返回 PNG 字节
- 使用 mss，线程安全（Lock）

### capture_region(x, y, w, h) -> bytes
- 截取指定区域，返回 PNG 字节

### capture_to_ndarray() -> np.ndarray
- 返回 BGR ndarray (H, W, 3)，便于 OpenCV 使用

### 设计决策
- mss 实例懒初始化+线程安全单例
- 所有接口调用前自动 enable_dpi_awareness()
- BGRA → BGR 转换用 cv2.imencode

## 验收 Checklist

- [x] `pytest tests/unit/control/test_screenshot.py` 全通过 (4/4)
- [x] capture_primary_screen 返回 PNG magic
- [x] capture_region 解码后尺寸匹配
- [x] capture_to_ndarray 返回 (H, W, 3) ndarray
