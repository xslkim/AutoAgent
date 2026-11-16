"""Build reviewable parallax packs from T10's approved composition pixels."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage

from artlib import digest, write_json
from checks import run
from t10_preview import CANVAS, COMPOSITION_LIGHTS, COMPOSITION_SIZE, ORIGIN, REPORT
from t10_preview import light_composition, read_json, save_jpg


def region(paths, guide_size):
    mask = Image.new("L", COMPOSITION_SIZE)
    draw = ImageDraw.Draw(mask)
    for points in paths:
        draw.polygon([(round(x * COMPOSITION_SIZE[0] / guide_size[0]),
                       round(y * COMPOSITION_SIZE[1] / guide_size[1])) for x, y in points], fill=255)
    return np.pad(np.asarray(mask) == 255,
                  ((ORIGIN[1], ORIGIN[1]), (ORIGIN[0], ORIGIN[0])), mode="edge")


def rect_for(mask):
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def visible_inpaint(pixels, visible, hidden):
    result = pixels.copy()
    if hidden.any():
        # Extend only this plane's visible colors. Hidden pixels never sample a
        # nearer plane, which would create a second outline as the layers move.
        # Exclude a small guide tolerance around the cut so stray edge pixels
        # cannot stretch into a duplicate lamp, canopy or masonry cap.
        donors = visible & (ndimage.distance_transform_edt(~hidden) >= 12)
        if not donors.any():
            donors = visible
        nearest = ndimage.distance_transform_edt(~donors, return_distances=False, return_indices=True)
        result[hidden] = pixels[nearest[0][hidden], nearest[1][hidden]]
        soft = ndimage.gaussian_filter(result.astype(np.float32), (1.6, 1.6, 0))
        result[hidden] = np.rint(soft[hidden]).astype("uint8")
    return result


def layer_texture(folder, spec, extent, visible, pixels):
    name = spec["id"]
    box = rect_for(extent)
    left, top, right, bottom = box
    crop = np.s_[top:bottom, left:right]
    area, exposed = extent[crop], visible[crop]
    hidden = area & ~exposed
    rgb = visible_inpaint(pixels[crop], exposed, hidden)
    rgba = np.dstack((rgb, area.astype("uint8") * 255))
    filename = f"{name}.png"
    Image.fromarray(rgba).save(folder / filename)
    Image.fromarray(rgba[..., 3]).save(folder / f"{name}_extent.png")
    layer = {"id": name, "file": filename, "pos": [left, top],
             "parallax": spec["parallax"], "extent": f"{name}_extent.png"}
    if hidden.any():
        layer["fill"] = f"{name}_fill.png"
        Image.fromarray(hidden.astype("uint8") * 255).save(folder / layer["fill"])
    if spec.get("blocks_shots"):
        layer["blocks_shots"] = True
        layer["block_mask"] = f"{name}_block.png"
        Image.fromarray(rgba[..., 3]).save(folder / layer["block_mask"])
        result = run("C08", {"file": folder / filename, "block_mask": folder / layer["block_mask"]})
        if result["status"] != "pass":
            raise ValueError(f"Block mask disagrees with {name} alpha")
    return layer


def split_lighting(geometry, original, off, folder, lamp_mask, lamp_visible, lamp_hit):
    center, emitter, spill = geometry
    lit = light_composition(original, center, emitter, spill)
    lit = np.asarray(ImageOps.fit(lit, COMPOSITION_SIZE, Image.Resampling.LANCZOS))
    delta = np.maximum(0, lit.astype(np.int16) - off.astype(np.int16)).astype("uint8")
    delta = np.pad(delta, ((ORIGIN[1], ORIGIN[1]), (ORIGIN[0], ORIGIN[0]), (0, 0)))
    glow = np.where(lamp_mask[..., None], delta, 0)
    falloff = delta - glow
    left, top, right, bottom = rect_for(delta.any(axis=2))
    for name, light in (("glow", glow), ("spill", falloff)):
        Image.fromarray(light[top:bottom, left:right]).save(folder / f"lamp_{name}.png")
    Image.fromarray(np.max(falloff, axis=2)).save(folder / "lamp_influence.png")
    hit = lamp_hit & lamp_visible
    hx, hy, hr, hb = rect_for(hit)
    Image.fromarray(hit[hy:hb, hx:hr].astype("uint8") * 255).save(folder / "lamp_hit.png")
    score = ndimage.distance_transform_edt(hit)
    y, x = np.unravel_index(score.argmax(), score.shape)
    return {"id": "lamp", "space": "lamp", "glow": "lamp_glow.png", "spill": "lamp_spill.png",
            "influence": "lamp_influence.png", "pos": [left, top],
            "hit_mask": "lamp_hit.png", "hit_pos": [hx, hy], "aim": [int(x), int(y)]}


def t10_sources():
    return {stage: (REPORT / "compositions" / f"{source}.png", (center, emitter, spill))
            for stage, (source, center, emitter, spill) in COMPOSITION_LIGHTS.items()}


def build(stage, specs, guide_size, output, source_spec=None):
    folder = output / stage
    folder.mkdir(parents=True, exist_ok=True)
    source, geometry = source_spec if source_spec is not None else t10_sources()[stage]
    with Image.open(source) as image:
        original = image.convert("RGB")
    off = np.asarray(ImageOps.fit(original, COMPOSITION_SIZE, Image.Resampling.LANCZOS))
    padding = ((ORIGIN[1], ORIGIN[1]), (ORIGIN[0], ORIGIN[0]), (0, 0))
    pixels = np.pad(off, padding, mode="reflect")
    extended_pixels = np.pad(off, padding, mode="edge") if any(spec.get("extend_edges") for spec in specs) else pixels
    all_canvas = np.ones(pixels.shape[:2], dtype=bool)
    opaque = {"id": "sky", "parallax": .10}
    masks = [all_canvas, *(region(spec["paths"], guide_size) for spec in specs)]
    remaining = all_canvas.copy()
    layers = []
    lights = []
    for spec, extent in reversed(list(zip([opaque, *specs], masks))):
        visible = extent & remaining
        if not visible.any():
            raise ValueError(f"{stage}: {spec['id']} has no visible pixels")
        remaining &= ~extent
        layer_pixels = extended_pixels if spec.get("extend_edges") else pixels
        layers.append(layer_texture(folder, spec, extent, visible, layer_pixels))
        if spec["id"] == "lamp":
            if geometry is None:
                raise ValueError(f"{stage}: lamp has no light geometry")
            hit = region(spec["hit"], guide_size)
            lights.append(split_lighting(geometry, original, off, folder, extent, visible, hit))
    if geometry is not None and not lights:
        raise ValueError(f"{stage}: light geometry has no lamp layer")
    layers.reverse()
    reconstructed = Image.new("RGBA", CANVAS)
    for layer in layers:
        with Image.open(folder / layer["file"]) as image:
            reconstructed.alpha_composite(image, tuple(layer["pos"]))
    crop = (*ORIGIN, ORIGIN[0] + COMPOSITION_SIZE[0], ORIGIN[1] + COMPOSITION_SIZE[1])
    if not np.array_equal(np.asarray(reconstructed.crop(crop).convert("RGB")), off):
        raise ValueError(f"{stage}: layered rest frame differs from composition")
    manifest = {"id": stage, "status": "runtime_probe_candidate", "source_sha256": digest(source),
                "canvas": CANVAS, "content_origin": ORIGIN, "content_size": COMPOSITION_SIZE,
                "layers": layers, "lights": lights, "rest_matches_original": True}
    write_json(folder / "station.json", manifest)
    return manifest


def verify_captures(captures, output, entries=None):
    evidence = read_json(captures / "engine_checks.json")
    if not evidence["passed"] or not evidence["gpu_capture"]:
        raise ValueError("Passing GPU probe results are required")
    frames = output / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    tags = ["rest", "lit", *(f"corner_{index}{suffix}"
                             for index in range(4) for suffix in ("", "_against"))]
    entries = t10_sources() if entries is None else entries
    for stage, (source, geometry) in entries.items():
        with Image.open(source) as image:
            original = image.convert("RGB")
        expected = {"rest": original}
        if geometry is not None:
            expected["lit"] = light_composition(original, *geometry)
        checks = {}
        for tag in (tag for tag in tags if geometry is not None or tag != "lit"):
            path = captures / f"{stage}_{tag}.png"
            with Image.open(path) as frame:
                if frame.size != COMPOSITION_SIZE or "A" not in frame.getbands():
                    raise ValueError(f"Unexpected capture format: {path}")
                if frame.getchannel("A").getextrema() != (255, 255):
                    raise ValueError(f"Parallax exposed the viewport: {path}")
                checks[tag] = {"sha256": digest(path), "opaque": True}
                if tag in expected:
                    base = ImageOps.fit(expected[tag], COMPOSITION_SIZE, Image.Resampling.LANCZOS)
                    error = np.abs(np.asarray(frame.convert("RGB"), dtype=np.int16)
                                   - np.asarray(base, dtype=np.int16))
                    maximum = int(error.max())
                    if maximum > (0 if tag == "rest" else 2):
                        raise ValueError(f"{stage} {tag}: unexpected source difference ({maximum})")
                    checks[tag]["max_channel_difference"] = maximum
                if tag in {"rest", "lit", "corner_2"}:
                    save_jpg(frame.convert("RGB"), frames / f"{stage}_{tag}.jpg")
            brightness = run("C03", {"file": path})
            checks[tag]["C03"] = brightness
            if brightness["status"] != "pass":
                raise ValueError(f"Capture exceeds visible brightness cap: {path}")
        evidence["samples"][stage]["captures"] = checks
    write_json(output / "engine_checks.json", evidence)
    count = sum(len(stage["captures"]) for stage in evidence["samples"].values())
    print(f"{count} GPU captures: full coverage, render-source match and brightness checks passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPORT / "parallax")
    parser.add_argument("--verify-captures", type=Path)
    args = parser.parse_args()
    if args.verify_captures:
        verify_captures(args.verify_captures, args.output)
        return
    data = read_json(REPORT / "composition_layers.json")
    for stage, specs in data["stations"].items():
        build(stage, specs, data["guide_size"], args.output)
        print(f"{stage}: {1 + len(specs)} layers, rest pixels verified")


if __name__ == "__main__":
    main()
