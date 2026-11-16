"""Lift the scenery visible through the green car's existing window openings."""
import numpy as np
from PIL import Image, ImageFilter

from t10_layers import region
from t10_preview import COMPOSITION_SIZE, ORIGIN
from t13_layers import contrast_main


def grade(source, layers, guide_size):
    with Image.open(source) as art:
        pixels = np.array(art.convert("RGB"), dtype=np.float32)

    foreground = np.logical_or.reduce([region(layer["paths"], guide_size) for layer in layers])
    x, y = ORIGIN
    width, height = COMPOSITION_SIZE
    windows = ~foreground[y:y + height, x:x + width]
    alpha = Image.fromarray(windows.astype(np.uint8) * 255)
    weights = np.asarray(alpha.filter(ImageFilter.GaussianBlur(1.1)), dtype=np.float32) / 255
    weights *= windows
    pixels += weights[..., None] * np.array((29, 85, 84))
    return Image.fromarray(np.rint(pixels).clip(0, 255).astype(np.uint8))


if __name__ == "__main__":
    contrast_main("green_car", grade, keep_baseline_influence=True)
