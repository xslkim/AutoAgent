"""Produce graded, registered cinema parallax packs from the selected compositions."""
import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from artlib import GAME, digest, effective_radius, write_json
from checks import run
from paper_ops import palette
from t10_layers import build, verify_captures, visible_inpaint
from t10_preview import read_json
from t10_whitebox import intersects
from t12_art import REPORT, gallery


OUTPUT = REPORT / "parallax"
LAMP_SCALE = {"poster_hall": 1.13, "auditorium": 1.58}
COLOR_PROFILES = {
    "ticket_office": (.50, (2, -2, 11)),
    "poster_hall": (.06, (1, -3, 6)),
    "projection_booth": (.10, (1, -2, 8)),
    "screen_stage": (.38, (4, -3, 8)),
}


def screen(image, file):
    sample = image.copy()
    sample.thumbnail((360, 360))
    sample.save(file)
    return run("C04", {"file": file, "palette_rgb": palette()})


def grade(image, profile):
    compression, offsets = profile
    rgb = np.asarray(image, dtype=np.float32)
    luma = rgb @ np.array([.2126, .7152, .0722], dtype=np.float32)
    # Compress brighter values continuously and preserve the original texture.
    # Nearest-swatch mapping can split one material into patches of unrelated hues.
    adjusted = rgb - compression * np.maximum(luma[..., None] - 24, 0) + np.asarray(offsets)
    return Image.fromarray(np.rint(adjusted).clip(0, 255).astype("uint8"))


def scale_lamp_layer(layer, guide, center, scale):
    gx, gy = [axis * side for axis, side in zip(center, guide)]
    adjusted = dict(layer)
    for key in ("paths", "hit"):
        adjusted[key] = [[[gx + (x - gx) * scale, gy + (y - gy) * scale] for x, y in polygon]
                         for polygon in layer[key]]
    return adjusted


def resize_lamp(image, layer, guide, center, scale):
    cx, cy = [axis * side for axis, side in zip(center, image.size)]
    mask = Image.new("L", image.size)
    draw = ImageDraw.Draw(mask)
    for polygon in layer["paths"]:
        draw.polygon([(round(x * image.width / guide[0]), round(y * image.height / guide[1]))
                      for x, y in polygon], fill=255)
    left, top, right, bottom = mask.getbbox()
    bounds = (max(0, left - 32), max(0, top - 32),
              min(image.width, right + 32), min(image.height, bottom + 32))
    hidden = np.asarray(mask.crop(bounds)) == 255
    patch = visible_inpaint(np.asarray(image.crop(bounds)), ~hidden, hidden)
    result = image.convert("RGBA")
    result.paste(Image.fromarray(patch), bounds[:2])
    lamp = image.convert("RGBA")
    lamp.putalpha(mask)
    transform = (1 / scale, 0, cx * (1 - 1 / scale), 0, 1 / scale, cy * (1 - 1 / scale))
    result.alpha_composite(lamp.transform(image.size, Image.Transform.AFFINE, transform, Image.Resampling.BICUBIC))
    return result.convert("RGB"), scale_lamp_layer(layer, guide, center, scale)


def inputs():
    annotations = read_json(REPORT / "composition_layers.json")
    alignment = read_json(REPORT / "art_alignment.json")["lamps"]
    ledger = read_json(REPORT / "generation.json")
    originals = {row["id"]: REPORT / row["output"] for row in ledger}
    rows = {}
    for stage, layers in annotations["stations"].items():
        light = alignment.get(stage)
        scale = LAMP_SCALE.get(stage, 1)
        geometry = None if light is None else (
            light["center"], [axis * scale for axis in light["emitter"]], light["spill"])
        rows[stage] = (originals[stage], layers, geometry, scale)
    return annotations["guide_size"], rows


def verify_lamp_reservation(pack, folder, layout):
    light = pack["lights"][0]
    layer = next(layer for layer in pack["layers"] if layer["id"] == light["space"])
    with Image.open(folder / light["hit_mask"]) as mask:
        radius = effective_radius(np.asarray(mask) >= 128)[0]
        width, height = mask.size
    x, y = [a - b for a, b in zip(light["hit_pos"], pack["content_origin"])]
    dx, dy = [math.ceil(limit * layer["parallax"]) for limit in (68, 34)]
    swept = [x - dx, y - dy, width + 2 * dx, height + 2 * dy]
    edge = layout["edge_band"]
    content_width, content_height = layout["content_size"]
    left, top, w, h = swept
    if left < edge or top < edge or left + w > content_width - edge or top + h > content_height - edge:
        raise ValueError(f"{pack['id']}: lamp enters the edge reserve")
    if any(intersects(swept, item["rect"]) for item in layout["reserved"].values() if item["when"] == "playing"):
        raise ValueError(f"{pack['id']}: lamp enters the playing HUD")
    if radius < 40:
        raise ValueError(f"{pack['id']}: lamp effective radius {radius:.2f}px is below 40px")
    return radius, swept


def prepare(stage, source, layers, geometry, scale, guide, output):
    folder = output / stage
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        image = original.convert("RGB")
    initial = screen(image, folder / "palette_before.png")
    color_adjusted = initial["status"] != "pass"
    profile = COLOR_PROFILES.get(stage)
    if color_adjusted:
        if profile is None:
            raise ValueError(f"{stage}: missing continuous color profile")
        image = grade(image, profile)
    layers = layers.copy()
    if scale != 1:
        index = next(index for index, layer in enumerate(layers) if layer["id"] == "lamp")
        image, layers[index] = resize_lamp(image, layers[index], guide, geometry[0], scale)
    final = screen(image, folder / "palette_after.png")
    if final["status"] != "pass":
        raise ValueError(f"{stage}: graded image did not reach C04")
    render_source = folder / "render_source.png"
    image.save(render_source)
    pack = build(stage, layers, guide, output, (render_source, geometry))
    pack.update(original_sha256=digest(source), rest_matches_original=not color_adjusted and scale == 1,
                rest_matches_render_source=True)
    write_json(folder / "station.json", pack)
    lamp, swept = None, None
    if pack["lights"]:
        layout = read_json(GAME / "assets/ui/hud_layout.json")
        lamp, swept = verify_lamp_reservation(pack, folder, layout)
    return {"C04_before": initial, "C04_after": final, "layer_count": len(pack["layers"]),
            "color_profile": profile if color_adjusted else None,
            "visible_lamp_scale": scale if lamp is not None else None,
            "lamp_effective_radius_px": lamp, "lamp_swept_rect": swept,
            "rest_matches_render_source": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify-captures", type=Path)
    args = parser.parse_args()
    guide, rows = inputs()
    if args.verify_captures:
        entries = {stage: (args.output / stage / "render_source.png", row[2]) for stage, row in rows.items()}
        verify_captures(args.verify_captures, args.output, entries)
        if args.output.resolve() == OUTPUT.resolve():
            gallery(read_json(REPORT / "layouts.json")["stations"])
        return
    results = {}
    for stage, (source, layers, geometry, scale) in rows.items():
        results[stage] = prepare(stage, source, layers, geometry, scale, guide, args.output)
        print(stage, results[stage]["layer_count"], results[stage]["lamp_effective_radius_px"])
    write_json(args.output / "art_checks.json", results)


if __name__ == "__main__":
    main()
