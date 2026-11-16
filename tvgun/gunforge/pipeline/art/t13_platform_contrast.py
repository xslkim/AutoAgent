"""Lift the platform windows and surrounding panel tones within the carriage silhouette."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from t10_preview import COMPOSITION_SIZE, ORIGIN
from t13_layers import contrast_main, visible_layer_region


def grade(source, layers, guide_size):
    with Image.open(source) as art:
        pixels = np.array(art.convert("RGB"), dtype=np.float32)
    glass = Image.new("L", COMPOSITION_SIZE)
    draw = ImageDraw.Draw(glass)
    for left, right in ((0, 80), (128, 186), (362, 468), (522, 627), (681, 788), (841, 948),
                        (1001, 1108), (1161, 1268), (1321, 1427), (1674, 1775)):
        draw.rounded_rectangle((left, 333, right, 421), radius=6, fill=255)
    panels = Image.new("L", COMPOSITION_SIZE)
    ImageDraw.Draw(panels).rectangle((0, 315, COMPOSITION_SIZE[0] - 1, 430), fill=255)

    index = next(i for i, layer in enumerate(layers) if layer["id"] == "carriage")
    visible = visible_layer_region(layers, index, guide_size)
    x, y = ORIGIN
    width, height = COMPOSITION_SIZE
    carriage = visible[y:y + height, x:x + width]
    pane_weight = np.asarray(glass.filter(ImageFilter.GaussianBlur(1.15)), dtype=np.float32) / 255
    panel_weight = np.asarray(panels.filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255
    adjustment = pane_weight[..., None] * np.array((15, 55, 63)) + panel_weight[..., None] * np.array((4, 20, 20))
    pixels += carriage[..., None] * adjustment
    return Image.fromarray(np.rint(pixels).clip(0, 255).astype(np.uint8))


if __name__ == "__main__":
    contrast_main("platform", grade, keep_baseline_influence=True)
