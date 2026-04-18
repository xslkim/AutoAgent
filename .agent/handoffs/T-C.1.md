# T C.1 Handoff — OCR 引擎封装

## 交付物
- `src/autovisiontest/perception/types.py` — BoundingBox, OCRItem, OCRResult, center(), find_text() (含 fuzzy 匹配)
- `src/autovisiontest/perception/ocr.py` — OCREngine (singleton, lazy PaddleOCR init)
- `tests/unit/perception/test_types.py` — 10 项测试
- `tests/unit/perception/test_ocr.py` — 7 项测试
- `tests/fixtures/ocr/generate.py` — fixture 图片生成脚本

## 测试结果
17/17 通过

## PR
https://github.com/xslkim/AutoAgent/pull/14
