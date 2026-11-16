"""Build the waiting-room contrast comparison from the registered composition."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from t10_preview import COMPOSITION_SIZE
from t13_layers import contrast_main


def upper_wall_mask():
    mask = Image.new("L", COMPOSITION_SIZE)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 231, 1775, 568), fill=255)
    draw.rectangle((26, 303, 638, 570), fill=0)
    for x in (0, 1036):
        column = [(107, 207), (154, 207), (197, 248), (197, 208), (249, 208), (249, 248),
                  (291, 206), (338, 206), (250, 294), (250, 572), (196, 572), (196, 294)]
        draw.polygon([(left + x, top) for left, top in column], fill=0)
    draw.rectangle((1110, 228, 1124, 306), fill=0)
    draw.rectangle((1119, 255, 1202, 271), fill=0)
    draw.rectangle((1144, 266, 1156, 294), fill=0)
    draw.rectangle((1221, 285, 1238, 397), fill=0)
    draw.ellipse((1088, 284, 1215, 411), fill=0)
    draw.rectangle((1441, 228, 1454, 314), fill=0)
    draw.rectangle((1585, 228, 1598, 314), fill=0)
    draw.polygon([(1424, 310), (1615, 310), (1620, 319), (1638, 325), (1638, 375),
                  (1622, 381), (1615, 390), (1424, 390), (1417, 380), (1405, 376),
                  (1405, 325), (1417, 320)], fill=0)
    return mask


def window_glass_mask():
    mask = Image.new("L", COMPOSITION_SIZE)
    draw = ImageDraw.Draw(mask)
    for left, right in ((43, 121), (133, 198), (249, 416), (429, 620)):
        draw.rectangle((left, 321, right, 372), fill=255)
    for left, right in ((43, 121), (133, 198), (249, 317), (328, 416), (429, 521), (532, 620)):
        draw.rectangle((left, 391, right, 555), fill=255)
    return mask


def grade(source, _layers, _guide_size):
    with Image.open(source) as art:
        pixels = np.array(art.convert("RGB"), dtype=np.float32)
    for mask, feather, offsets in ((upper_wall_mask(), 1.1, (45, 119, 103)),
                                   (window_glass_mask(), 1.3, (31, 97, 96))):
        weights = np.asarray(mask.filter(ImageFilter.GaussianBlur(feather)), dtype=np.float32) / 255
        pixels += weights[..., None] * np.asarray(offsets)
    return Image.fromarray(np.rint(pixels).clip(0, 255).astype(np.uint8))


if __name__ == "__main__":
    contrast_main("waiting_room", grade)
