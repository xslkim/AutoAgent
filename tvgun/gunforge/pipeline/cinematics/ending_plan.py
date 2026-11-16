from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "games/g01/cinematics/ending_original"
FPS = 30
SIZE = (1920, 1080)
OVERLAP = 0.7
# Start and end refer to the final edit. Adjacent shots overlap by OVERLAP.
SHOTS = [
    ("ink", 0, 6.7, "最后一笔落尽"),
    ("market", 6, 15.7, "夜市重新开张"),
    ("cinema", 15, 24.7, "旧影院重新放映"),
    ("train", 24, 34.7, "站台送别绿皮车"),
    ("city", 34, 46.7, "灯城全景"),
    ("tape", 46, 53.7, "磁带最后一句"),
    ("desk", 53, 60, "空椅旁，纸灯还亮着"),
]
LINES = [
    (8.2, "夜市的灯，又亮了起来。"),
    (18.1, "那家旧影院啊，散场了还有人舍不得走。"),
    (26.8, "末班车走了，站台的灯还得给晚回来的人留着。"),
    (38.4, "我怕日子一长，就忘了这些寻常事。"),
    (48.5, "灯亮着，就还在。"),
]
VOICE_STYLE = "七十五岁中国北方爷爷，低沉温和，略沙哑，亲切朴素，轻声对孙辈讲家常。语速舒缓，句末自然下沉。普通话。"
