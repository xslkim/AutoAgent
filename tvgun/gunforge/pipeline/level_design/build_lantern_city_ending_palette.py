"""Publish a local epilogue color comparison against the exact cast revision."""
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from audit_lantern_city_release import bindings
from cast_color_images import publish_image_copy
from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from versions import patch, resolve

PACKAGE = "paper.lantern_city_cast"
REVIEWS = ROOT / "gunforge/level_design/reviews"
COPIES = Path("gunforge/level_design/generated/lantern_city_ending_palette")
OPERATION = "epilogue_left_stalls_warm_apricot_v1"
WIDE_ENTITY = "lantern_base.ending.wide_view"
# Normalized bounds with fully feathered margins, measured on city_wide_v1.png.
BOUNDS = (.054, .448, .385, .765)
PAPER_LIGHT = (217, 160, 102)
YPRIME = (.2126, .7152, .0722)


def smoothstep(value, low, high):
    t = np.clip((value - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def grade_panorama(image):
    pixels = np.array(image.convert("RGBA"))
    height, width = pixels.shape[:2]
    x = np.arange(width) / width
    y = np.arange(height) / height
    left, top, right, bottom = BOUNDS
    feather_x = smoothstep(x, left, .082) * (1 - smoothstep(x, .32, right))
    feather_y = smoothstep(y, top, .485) * (1 - smoothstep(y, .72, bottom))
    rgb = pixels[..., :3].astype(np.float64)
    r, g, b = np.moveaxis(rgb, -1, 0)
    luminance = r * YPRIME[0] + g * YPRIME[1] + b * YPRIME[2]
    warm = smoothstep(r - g, 32, 63) * smoothstep(r - b, 45, 90)
    lamp_protection = 1 - smoothstep(luminance, 155, 195)
    amount = .55 * feather_y[:, None] * feather_x[None, :] * warm * lamp_protection
    tone = np.asarray(PAPER_LIGHT)
    reference = sum(channel * weight for channel, weight in zip(PAPER_LIGHT, YPRIME))
    target = np.clip(tone * (1 + .55 * (luminance[..., None] / reference - 1)), 0, 255)
    mix = amount[..., None]
    pixels[..., :3] = np.rint(rgb * (1 - mix) + target * mix).astype(np.uint8)
    return Image.fromarray(pixels)


def build():
    baseline = read(REVIEWS / "lantern_city_cast_build.json")
    revision = baseline["source_revision"]
    _, source, _ = resolve(PACKAGE, revision)
    resource_id = source["entities"][WIDE_ENTITY]["resource"]
    original = source["resources"][resource_id]
    if (original["kind"] != "image" or Path(original["path"]).name != "city_wide_v1.png"
            or bindings(source)[resource_id] != [f"/entities/{WIDE_ENTITY}/resource"]):
        raise ValueError("Expected the independently bound city panorama")
    data = (ROOT / original["path"]).read_bytes()
    with Image.open(BytesIO(data)) as image:
        comparison = grade_panorama(image)
    candidate = original.copy()
    publish_image_copy(ROOT, COPIES, OPERATION, candidate, data, comparison)
    if candidate["sha256"] == original["sha256"]:
        raise ValueError("The left stall grade produced no pixel changes")
    entry = patch(PACKAGE, revision, {"base_revision": revision, "changes": [
        {"op": "replace", "path": f"/resources/{resource_id}", "expected": original, "value": candidate},
    ]})
    _, verified, manifest = resolve(PACKAGE, entry.parent.name)
    compiled = compile_source(verified, source_manifest=manifest)
    output = write_build(compiled, DEFAULT_CACHE)
    dump(REVIEWS / "lantern_city_ending_palette_build.json", {
        "package": PACKAGE, "source": str(entry), "source_revision": compiled["source_revision"],
        "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted",
        "base_build_id": baseline["build_id"], "base_source_revision": revision, "resource_id": resource_id,
        "original_image": original, "candidate_image": candidate, "grade_operation": OPERATION,
        "bounds_xyxy_normalized": list(BOUNDS),
    })
    print(output)


if __name__ == "__main__":
    build()
