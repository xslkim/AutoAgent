"""Build and verify the train-station parallax art packs."""
import argparse
import math
from pathlib import Path
from shutil import copyfile

import numpy as np
from PIL import Image, ImageOps

from artlib import GAME, digest, write_json
from checks import overlap, run
from paper_ops import palette, paper_palette
from t10_layers import build, region, verify_captures
from t10_preview import COMPOSITION_SIZE, ORIGIN, light_composition, read_json
from t12_layers import grade, resize_lamp, scale_lamp_layer, verify_lamp_reservation
from t12_whitebox import within


REPORT = GAME / "reports/art/T13"
OUTPUT = REPORT / "parallax"


def lighting(row):
    light = row.get("lighting")
    if light is None:
        return None
    scale = row.get("lamp_scale", 1)
    return light["center"], [radius * scale for radius in light["emitter"]], light["spill"]


def verify_workbench_geometry(pack, folder, layout):
    stages = read_json(REPORT / "layouts.json")["stations"]
    boss = next(stage["boss_region"] for stage in stages if stage["id"] == pack["id"])
    layer_by_id = {layer["id"]: layer for layer in pack["layers"]}
    inkstone = layer_by_id[pack["anchors"]["ink_well"]["layer"]]
    x, y, width, height = boss
    dx, dy = [math.ceil(limit * inkstone["parallax"]) for limit in (68, 34)]
    swept = [x - dx, y - dy, width + 2 * dx, height + 2 * dy]
    edge = layout["edge_band"]
    content_width, content_height = layout["content_size"]
    if not within(swept, [edge, edge, content_width - 2 * edge, content_height - 2 * edge]):
        raise ValueError("Workbench boss region enters the edge reserve")
    if any(overlap(swept, item["rect"]) for item in layout["reserved"].values() if item["when"] == "playing"):
        raise ValueError("Workbench boss region enters the playing HUD")
    for layer in pack["layers"][1:]:
        if layer["parallax"] != inkstone["parallax"]:
            raise ValueError(f"{layer['id']}: expected workbench props to move with the desk")
        left, top = [p - o for p, o in zip(layer["pos"], pack["content_origin"])]
        with Image.open(folder / layer["file"]) as image:
            if overlap(boss, [left, top, *image.size]):
                raise ValueError(f"{layer['id']}: overlaps the workbench boss region")
    return {"rect": boss, "space": inkstone["id"], "swept_rect": swept}


def visible_layer_region(layers, index, guide_size):
    visible = region(layers[index]["paths"], guide_size)
    for nearer in layers[index + 1:]:
        visible &= ~region(nearer["paths"], guide_size)
    return visible


def correct_visible_layers(frame, layers, selected, guide_size):
    x, y = ORIGIN
    width, height = COMPOSITION_SIZE
    for index, layer in enumerate(layers):
        if layer["id"] not in selected:
            continue
        visible = visible_layer_region(layers, index, guide_size)
        alpha = Image.fromarray(visible[y:y + height, x:x + width].astype("uint8") * 255)
        box = alpha.getbbox()
        if box is None:
            raise ValueError(f"{layer['id']}: selected palette layer has no visible pixels")
        mask = alpha.crop(box)
        patch = frame.crop(box).convert("RGBA")
        patch.putalpha(mask)
        frame.paste(paper_palette(patch).convert("RGB"), box[:2], mask)


def prepare(stage, row, guide_size, output):
    folder = output / stage
    folder.mkdir(parents=True, exist_ok=True)
    source = REPORT / row["source"]
    with Image.open(source) as original:
        frame = ImageOps.fit(original.convert("RGB"), COMPOSITION_SIZE, Image.Resampling.LANCZOS)
    profile = row["color_profile"]
    corrected = grade(frame, profile)
    layers = row["layers"].copy()
    selected = row.get("palette_layers", [])
    correct_visible_layers(corrected, layers, selected, guide_size)
    scale = row.get("lamp_scale", 1)
    if scale != 1:
        lamp_index = next(index for index, layer in enumerate(layers) if layer["id"] == "lamp")
        corrected, layers[lamp_index] = resize_lamp(corrected, layers[lamp_index], guide_size, lighting(row)[0], scale)
    original_source = REPORT / row.get("original_source", row["source"])
    if original_source != source:
        with Image.open(original_source) as original:
            frame = ImageOps.fit(original.convert("RGB"), COMPOSITION_SIZE, Image.Resampling.LANCZOS)
    matches_original = np.array_equal(np.asarray(corrected), np.asarray(frame))
    render_source = folder / "render_source.png"
    corrected.save(render_source)
    color = run("C04", {"file": render_source, "palette_rgb": palette()})
    if color["status"] != "pass":
        raise ValueError(f"{stage}: render source failed C04: {color['details']}")
    pack = build(stage, layers, guide_size, output, (render_source, lighting(row)))
    pack.update(original_sha256=digest(original_source), rest_matches_original=matches_original, rest_matches_render_source=True)
    layout = read_json(GAME / "assets/ui/hud_layout.json")
    result = {"source_sha256": digest(original_source), "C04_render_source": color, "color_profile": profile,
              "palette_layers": selected, "layer_count": len(pack["layers"]),
              "rest_matches_original": matches_original, "rest_matches_render_source": True}
    if pack["lights"]:
        radius, swept = verify_lamp_reservation(pack, folder, layout)
        result.update(visible_lamp_scale=scale, lamp_effective_radius_px=round(radius, 2), lamp_swept_rect=swept)
    if "anchors" in row:
        pack["anchors"] = row["anchors"]
        pack["boss_region"] = verify_workbench_geometry(pack, folder, layout)
        result.update(anchors=pack["anchors"], boss_region=pack["boss_region"])
    write_json(folder / "station.json", pack)
    return result


def verify_light_region(stage, source, geometry, captures):
    with Image.open(source) as base, Image.open(captures / f"{stage}_rest.png") as off, Image.open(captures / f"{stage}_lit.png") as on:
        base = base.convert("RGB")
        lit = np.asarray(light_composition(base, *geometry))
        mask = (lit != np.asarray(base)).any(axis=2)
        changes = (np.asarray(off.convert("RGB")) != np.asarray(on.convert("RGB"))).any(axis=2)
    if not changes.any() or (changes & ~mask).any():
        raise ValueError(f"{stage}: GPU lighting changed pixels outside the planned light region")
    return {"changed_pixels": int(changes.sum()), "changed_outside_light_region": 0}


def contrast_main(stage, apply_grade, *, keep_baseline_influence=False):
    """Build a single contrast comparison and verify its parallax captures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPORT / f"variants/{stage}_contrast/parallax")
    parser.add_argument("--verify-captures", type=Path)
    args = parser.parse_args()
    spec = read_json(REPORT / "composition_layers.json")
    row = spec["stations"][stage]
    folder = args.output / stage
    render_source = folder / "render_source.png"
    geometry = lighting(row)
    if args.verify_captures:
        verify_captures(args.verify_captures, args.output, {stage: (render_source, geometry)})
        receipt_path = args.output / "engine_checks.json"
        receipt = read_json(receipt_path)
        receipt["samples"][stage]["light_region"] = verify_light_region(stage, render_source, geometry, args.verify_captures)
        write_json(receipt_path, receipt)
        return

    folder.mkdir(parents=True, exist_ok=True)
    original = OUTPUT / stage / "render_source.png"
    layers = row["layers"].copy()
    guide = spec["guide_size"]
    scale = row.get("lamp_scale", 1)
    if scale != 1:
        index = next(i for i, layer in enumerate(layers) if layer["id"] == "lamp")
        # The baseline already contains the resized lamp pixels; align the paths to them.
        layers[index] = scale_lamp_layer(layers[index], guide, geometry[0], scale)
    apply_grade(original, layers, guide).save(render_source)
    color = run("C04", {"file": render_source, "palette_rgb": palette()})
    if color["status"] != "pass":
        raise ValueError(f"{stage}: contrast comparison failed C04: {color['details']}")
    pack = build(stage, layers, guide, args.output, (render_source, geometry))
    if keep_baseline_influence:
        # The visual spill depends on background color, while this mask controls hit permissions.
        influence = pack["lights"][0]["influence"]
        copyfile(original.parent / influence, folder / influence)
    layout = read_json(GAME / "assets/ui/hud_layout.json")
    radius, bounds = verify_lamp_reservation(pack, folder, layout)
    write_json(args.output / "art_checks.json", {
        "baseline_sha256": digest(original), "render_source_sha256": digest(render_source),
        "C04_render_source": color, "layer_count": len(pack["layers"]),
        "lamp_effective_radius_px": round(radius, 2), "lamp_swept_rect": bounds,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify-captures", type=Path)
    args = parser.parse_args()
    spec = read_json(REPORT / "composition_layers.json")
    stations = spec["stations"]
    if args.verify_captures:
        entries = {stage: (args.output / stage / "render_source.png", lighting(row)) for stage, row in stations.items()}
        verify_captures(args.verify_captures, args.output, entries)
        receipt = read_json(args.output / "engine_checks.json")
        for stage, (source, geometry) in entries.items():
            if geometry is not None:
                receipt["samples"][stage]["light_region"] = verify_light_region(stage, source, geometry, args.verify_captures)
        write_json(args.output / "engine_checks.json", receipt)
        return
    results = {stage: prepare(stage, row, spec["guide_size"], args.output) for stage, row in stations.items()}
    write_json(args.output / "art_checks.json", results)
    print({stage: row["C04_render_source"]["details"]["coverage"] for stage, row in results.items()})


if __name__ == "__main__":
    main()
