"""Bind the approved passerby C design to the train station's paper puppet."""
import numpy as np
from PIL import Image

from artlib import GAME, write_json
from checks import run
from t10_assets import bind_puppet, pair_components
from t12_actors import jpg


REPORT = GAME / "reports/art/T13"
SOURCE = REPORT / "source/passerby_c_sheet.png"
OUTPUT = REPORT / "actors/passerby_c"


def tint_joint_tab(image, lower_edge=False):
    """Match the exposed pale tabs to the adjacent garment without changing alpha."""
    pixels = np.array(image)
    height = image.height
    band = slice(round(height * .88), height) if lower_edge else slice(0, round(height * .15))
    reference = slice(round(height * .73), round(height * .87)) if lower_edge else slice(round(height * .20), round(height * .34))
    garment = pixels[reference][pixels[reference, :, 3] >= 128, :3]
    if not garment.size:
        return image
    joint = pixels[band]
    red, green, blue = np.moveaxis(joint[..., :3].astype(np.int16), -1, 0)
    pale = (red >= 142) & (green >= 111) & (blue >= 75) & (red > green + 8)
    pale &= joint[..., 3] > 0
    if pale.any():
        target = np.median(garment, axis=0)
        source = joint[pale, :3].astype(np.float64)
        joint[pale, :3] = np.rint(source - np.median(source, axis=0) + target).clip(0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as sheet:
        parts = pair_components(sheet)
    for name, image in parts.items():
        if name == "torso" or name.startswith(("forearm", "thigh", "shin")):
            parts[name] = tint_joint_tab(image, lower_edge=name == "torso")
    result = bind_puppet(parts, OUTPUT, SOURCE)
    if result["checks"]["C10"]["status"] == "fail":
        raise ValueError("Passerby C has a disconnected joint in a sampled pose")
    result["pose_brightness"] = {}
    for name in ("idle", "struggle", "rescued_bounce", "thank"):
        path = OUTPUT / f"pose_{name}.png"
        with Image.open(path) as image:
            jpg(image, OUTPUT / f"{name}.jpg")
        result["pose_brightness"][name] = run("C03", {"file": path})
    if any(row["status"] != "pass" for row in result["pose_brightness"].values()):
        raise ValueError("Passerby C pose exceeds the brightness cap")
    write_json(OUTPUT / "checks.json", result)


if __name__ == "__main__":
    main()
