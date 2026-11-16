"""Assemble and screen T10's independently generated scene layers."""
import argparse
import html
import json
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps
from scipy.spatial import cKDTree
from skimage.color import deltaE_ciede2000, rgb2lab

from artlib import GAME, digest, write_json, yprime
from checks import run
from paper_ops import alpha_crop, limit_luminance, palette
from preview import render, review_form


REPORT = GAME / "reports/art/T10"
SOURCE = REPORT / "source"
CANVAS = (1920, 1020)
ORIGIN = (72, 42)
LAYER_NAMES = ("base", "far_roofs", "mid_structure", "mid_left", "mid_right", "near_left", "near_right")
LIGHT_NAMES = {"stall": "streetlamp_off", "video_shop": "neon_off",
               "footbridge": "lantern_off", "square": "lantern_off"}
# Center, emitter radii and spill radii, measured on the selected compositions.
# These coordinates belong to the review artwork; gameplay uses layouts.json.
COMPOSITION_LIGHTS = {
    "stall": ("stall_02", (.773, .450), (.022, .016), (.090, .110)),
    "video_shop": ("video_shop_02", (.722, .182), (.080, .042), (.145, .140)),
    "footbridge": ("footbridge_02", (.770, .245), (.028, .052), (.090, .140)),
    "square": ("square_02", (.124, .432), (.017, .045), (.085, .135)),
}
COMPOSITION_SIZE = (1776, 936)
CAMERA_SAMPLES = {
    "upper_left": (-60, -30, 0), "upper_right": (60, -30, .25),
    "lower_right": (60, 30, .65), "lower_left": (-60, 30, 1),
}
BANDS = {"far": (.45, .75), "middle": (.25, .55), "near": (.05, .20)}
STATION_FRAMES = (
    ("rest", "关灯"), ("lit", "点灯"), ("upper_left", "左上极限"),
    ("upper_right", "右上极限"), ("lower_right", "右下极限"), ("lower_left", "左下极限"),
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def screen_compositions():
    data = []
    for name in ("composition_attempts.json", "composition_round_2.json",
                 "composition_round_3.json", "composition_round_4.json"):
        for row in read_json(REPORT / name):
            if row["status"] != "generated":
                data.append(row)
                continue
            path = REPORT / row["output"]
            with Image.open(path) as image:
                row["actual_size"] = list(image.size)
                thumbnail = image.convert("RGB")
                thumbnail.thumbnail((360, 360))
                sample = REPORT / "screen" / path.name
                sample.parent.mkdir(exist_ok=True)
                thumbnail.save(sample)
            row.update(sha256=digest(path), reference_sha256=digest(REPORT / row["reference"]), cost=None)
            row["checks"] = {
                "C03": run("C03", {"file": path}),
                "C04": run("C04", {"file": sample, "palette_rgb": palette()}),
            }
            data.append(row)
    write_json(REPORT / "composition_screen.json", data)
    choices = {}
    for stage in LIGHT_NAMES:
        valid = [row for row in data if row["id"] == stage and row.get("checks", {}).get("C03", {}).get("status") == "pass"]
        if valid:
            chosen = max(valid, key=lambda row: row["checks"]["C04"]["details"]["coverage"])
            choices[stage] = {
                "reference": chosen["output"], "sha256": chosen["sha256"],
                "coverage": chosen["checks"]["C04"]["details"]["coverage"],
                "scope": "composition reference chosen among brightness-passing drafts by palette coverage",
            }
    write_json(REPORT / "composition_selection.json", choices)
    return data


def stage_rectangles(stage):
    if stage["id"] == "footbridge":
        left, right = stage["midground"][1:]
        middle = stage["midground"][0]
    else:
        left, right = stage["midground"]
        middle = (-72, 300, 1920, 310)
    near_left, near_right = stage["cover"]
    return (None, (-72, 215, 1920, 275), middle, left, right, near_left, near_right)


@lru_cache
def paper_lookup(band):
    """Map RGB values to nearby paper colors inside both art tolerances."""
    axis = np.arange(0, 256, 8, dtype=np.uint8)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    low, high = BANDS[band]
    y = yprime(grid[None, ...])[0]
    lab = rgb2lab(grid.reshape(-1, 1, 3)).reshape(-1, 3)
    # Keep each depth band in a single color family. Using the whole game's
    # palette here can turn neighboring paper pixels into green/magenta speckle.
    anchors = {"near": ("141A33", "2A1E3D"), "middle": ("D9A066", "C97B84"),
               "far": ("B8C4D6", "4A90B8")}
    swatches = np.array([tuple(bytes.fromhex(color)) for color in anchors[band]], dtype=np.uint8)
    targets = rgb2lab(swatches.reshape(-1, 1, 3)).reshape(-1, 3)
    nearest = np.min([deltaE_ciede2000(lab, np.broadcast_to(color, lab.shape)) for color in targets], axis=0)
    # Leave headroom for alpha-composited edges and the additive light pass.
    gamut = grid[(y >= low + .01) & (y <= high - .01) & (nearest <= 8)]
    _, index = cKDTree(gamut).query(grid)
    target = gamut[index].astype(float)
    original = grid.astype(float)
    lo, hi = np.zeros(len(grid)), np.ones(len(grid))
    for _ in range(7):
        amount = (lo + hi) / 2
        sample = original + (target - original) * amount[:, None]
        lab = rgb2lab((sample / 255).reshape(-1, 1, 3)).reshape(-1, 3)
        distance = np.min([deltaE_ciede2000(lab, np.broadcast_to(color, lab.shape))
                           for color in targets], axis=0)
        lo = np.where(distance > 11, amount, lo)
        hi = np.where(distance > 11, hi, amount)
    return target.reshape(32, 32, 32, 3), hi.reshape(32, 32, 32)


def normalize(image, band):
    """Set encoded mean luminance inside the declared band, retaining alpha."""
    a = np.array(image.convert("RGBA"))
    visible = a[..., 3] >= 128
    if not visible.any():
        raise ValueError("empty layer")
    before = float(yprime(a)[visible].mean())
    low, high = BANDS[band]
    desired = min(high - .02, max(low + .02, before))
    rgb = a[..., :3].astype(float)
    if before > desired:
        rgb *= desired / before
    elif before < desired:
        # Keep the distant night sky cool while lifting it above the minimum.
        fill = np.array([184., 196., 214.] if band == "far" else [217., 160., 102.])
        reference = float(yprime(np.array([[list(fill) + [255]]], dtype=np.uint8))[0, 0])
        rgb += (fill - rgb) * min(1, (desired - before) / max(.001, reference - before))
    a[..., :3] = rgb.clip(0, 255).astype("uint8")
    if band != "near":
        # Lift dark backing paper with a soft toe. Preserve upper-mid paper tones.
        measured = yprime(a)
        wanted = np.interp(measured, (0, .25, .46, 1), (.26, .31, .46, 1))
        fill = np.array([184., 196., 214.] if band == "far" else [217., 160., 102.])
        ref = float(yprime(np.array([[list(fill) + [255]]], dtype=np.uint8))[0, 0])
        amount = np.maximum(0, wanted - measured) / np.maximum(.001, ref - measured)
        a[..., :3] = (a[..., :3] + (fill - a[..., :3]) * amount[..., None]).astype("uint8")
    rgb = a[..., :3]
    key = np.minimum((rgb.astype("uint16") + 4) // 8, 31)
    targets, weights = paper_lookup(band)
    indices = tuple(key[..., channel] for channel in range(3))
    a[..., :3] = np.rint(rgb + (targets[indices] - rgb) * weights[indices][..., None]).astype("uint8")
    return limit_luminance(Image.fromarray(a), high)


def place_layer(src, dest, name, rect, z, parallax, band):
    with Image.open(src) as original:
        if rect is None:
            image = original.convert("RGB").resize(CANVAS, Image.Resampling.LANCZOS).convert("RGBA")
            pos = (0, 0)
        else:
            alpha = original.convert("RGBA").getchannel("A")
            transparent, solid = alpha.getextrema()
            if transparent > 15 or solid < 240:
                raise ValueError(f"layer needs transparent and solid pixels: {src.name}")
            x, y, width, height = rect
            cutout = alpha_crop(original, pad=0)[0]
            if name in {"mid_left", "mid_right", "near_left", "near_right"}:
                image = ImageOps.contain(cutout, (width, height), Image.Resampling.LANCZOS)
                x += (width - image.width) // 2
                y += height - image.height
            else:
                image = cutout.resize((width, height), Image.Resampling.LANCZOS)
            pos = (ORIGIN[0] + x, ORIGIN[1] + y)
    image = normalize(image, band)
    image.save(dest / f"{name}.png")
    mask = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    mask.save(dest / f"{name}_extent.png")
    layer = {"id": name, "file": f"{name}.png", "pos": pos, "z": z, "parallax": parallax,
             "band": band, "extent": f"{name}_extent.png", "source_sha256": digest(src)}
    if band == "near":
        mask.save(dest / f"{name}_block.png")
        layer["blocks_shots"] = True
        layer["block_mask"] = f"{name}_block.png"
    return layer


def install_light(stage, dest):
    lamp = stage["light"]
    x, y, w, h = lamp["rect"]
    src = SOURCE / f"{LIGHT_NAMES[stage['id']]}.png"
    lamp_pos = (x + ORIGIN[0], y + ORIGIN[1])
    if not src.is_file() and stage["id"] == "stall":
        # Preserve the pole as art, while the hit mask only includes the accepted shade.
        folder = GAME / "assets/stations/g01_st_l1_01_alley/station"
        original_lamp = next(layer for layer in read_json(folder / "station.json")["layers"] if layer["id"] == "lamp")
        lamp_pos = tuple(original_lamp["pos"])
        src = folder / original_lamp["file"]
        with Image.open(src) as original:
            image = original.convert("RGBA")
        left, top = x + ORIGIN[0] - lamp_pos[0], y + ORIGIN[1] - lamp_pos[1]
        hit = image.getchannel("A").crop((left, top, left + w, top + h))
    else:
        with Image.open(src) as original:
            transparent, solid = original.convert("RGBA").getchannel("A").getextrema()
            if transparent > 15 or solid < 240:
                raise ValueError(f"lamp needs alpha: {src.name}")
            image = alpha_crop(original, pad=0)[0].resize((w, h), Image.Resampling.LANCZOS)
        hit = image.getchannel("A")
    image.save(dest / "lamp.png")
    hit.point(lambda a: 255 if a >= 128 else 0).save(dest / "lamp_hit.png")
    yy, xx = np.ogrid[:CANVAS[1], :CANVAS[0]]
    _, _, lw, lh = lamp["range"]
    radius2 = ((xx - ORIGIN[0] - x - w / 2) / min(lw / 2, w * 1.9)) ** 2
    radius2 = radius2 + ((yy - ORIGIN[1] - y - h / 2) / min(lh / 2, h * 1.8)) ** 2
    Image.fromarray((np.clip(1 - radius2, 0, 1) ** 2 * 255).astype("uint8")).save(dest / "spill.png")
    g = Image.new("RGBA", CANVAS)
    glow = Image.new("RGBA", hit.size, (217, 160, 102, 0))
    glow.putalpha(hit.point(lambda a: int(a * .6)))
    g.alpha_composite(glow, (x + ORIGIN[0], y + ORIGIN[1]))
    g.save(dest / "glow.png")
    light = {"id": "lamp", "space": "lamp", "spill": "spill.png", "glow": "glow.png",
             "intensity": .38, "color": "#D9A066", "hit_mask": "lamp_hit.png", "hit_rect": lamp["rect"]}
    layer = {"id": "lamp", "file": "lamp.png", "pos": lamp_pos,
             "z": 4.5, "parallax": .45, "source_sha256": digest(src)}
    return layer, light


def probe_slots(stage, dest, layers, frame, shift):
    luminance = yprime(np.asarray(frame))
    block = Image.new("L", frame.size)
    for layer in layers:
        if not layer.get("block_mask"):
            continue
        with Image.open(dest / layer["block_mask"]) as mask:
            pos = tuple(round(layer["pos"][i] - ORIGIN[i] - shift[i] * layer["parallax"]) for i in range(2))
            block.paste(255, (*pos, pos[0] + mask.width, pos[1] + mask.height), mask)
    cover = np.asarray(block) > 0
    values = []
    for x, y, w, h in stage["targets"]:
        x -= round(shift[0] * .45)
        y -= round(shift[1] * .45)
        region = np.s_[y:y+h, x:x+w]
        values.append({"background_yprime_p10": float(np.quantile(luminance[region], .10)),
                       "covered_fraction": float(cover[region].mean())})
    return values


def stage_preview(stage, hud):
    dest = REPORT / "stations" / stage["id"]
    dest.mkdir(parents=True, exist_ok=True)
    specification = zip(LAYER_NAMES, stage_rectangles(stage), (.1, .2, .4, .46, .52, .8, 1.0),
                        ("far", "far", "middle", "middle", "middle", "near", "near"))
    layers = []
    for z, (name, rect, parallax, band) in enumerate(specification):
        source = SOURCE / f"{stage['id']}_{name}.png"
        revision = source.with_stem(source.stem + "_v2")
        layers.append(place_layer(revision if revision.is_file() else source,
                                  dest, name, rect, z, parallax, band))
    lamp, light = install_light(stage, dest)
    support = SOURCE / "lantern_support.png"
    if stage["id"] in {"footbridge", "square"} and support.is_file():
        x, y, width, _ = stage["light"]["rect"]
        layers.append(place_layer(support, dest, "lamp_support", (x + width // 2 - 64, y - 12, 64, 736 - y),
                                  4.4, .45, "middle"))
    layers.append(lamp)
    station = {"id": stage["id"], "status": "offline_candidate", "canvas": CANVAS, "content_origin": ORIGIN,
               "layers": layers, "lights": [light], "target_slots": stage["targets"],
               "protected": stage.get("protected", [])}
    write_json(dest / "station.json", station)
    checks = {}
    visibility = {}
    coverage = {}
    colors = {}
    for name, camera, breath, strength in [
        ("rest", (0, 0), (0, 0), 0),
        ("upper_left", (-60, -30), (-8, -4), 0),
        ("upper_right", (60, -30), (8, -4), .25),
        ("lower_right", (60, 30), (8, 4), .65),
        ("lower_left", (-60, 30), (-8, 4), 1),
        ("lit", (0, 0), (0, 0), 1),
    ]:
        frame = render(station, dest, camera=camera, breath=breath, light_states={"lamp": strength})
        frame.save(dest / f"{name}.png")
        save_jpg(frame.convert("RGB"), dest / f"{name}.jpg")
        checks[name] = run("C03", {"file": dest / f"{name}.png"})
        coverage[name] = frame.getchannel("A").getextrema() == (255, 255)
        shift = (camera[0] + breath[0], camera[1] + breath[1])
        visibility[name] = probe_slots(stage, dest, layers, frame, shift)
        if name in {"rest", "lit"}:
            sample = dest / f"{name}_palette_screen.png"
            frame.thumbnail((360, 360))
            frame.save(sample)
            colors[name] = run("C04", {"file": sample, "palette_rgb": palette()})
    band_checks = {
        layer["id"]: run("C03", {"file": dest / layer["file"], "band_range": BANDS[layer["band"]]})
        for layer in layers if "band" in layer
    }
    block_checks = {
        layer["id"]: run("C08", {"file": dest / layer["file"], "block_mask": dest / layer["block_mask"]})
        for layer in layers if layer.get("block_mask")
    }
    rgba8_mips = 0
    for layer in layers:
        with Image.open(dest / layer["file"]) as image:
            rgba8_mips += round(image.width * image.height * 4 * 4 / 3)
    write_json(dest / "checks.json", {"C03_frames": checks, "C03_layers": band_checks,
                                      "C04_samples": colors, "C08_blocks": block_checks,
                                      "target_zone_motion_screen": visibility,
                                      "opaque_viewport_at_extremes": coverage,
                                      "texture_bytes_rgba8_mips_estimate": rgba8_mips,
                                      "runtime": "pending", "light": "procedural preview"})
    return {"id": stage["title"], "status": "pending",
            "composition_frames": composition_frames(stage["id"], dest),
            "frames": [(label, dest / f"{key}.png") for key, label in STATION_FRAMES]}


def save_jpg(image, path):
    image.save(path, format="JPEG", quality=96, subsampling=0, optimize=True)


def light_composition(image, center, emitter, spill, amount=1):
    """Light the original artwork locally, with identical pixels beyond the spill."""
    y, x = np.ogrid[:image.height, :image.width]
    dx = x / image.width - center[0]
    dy = y / image.height - center[1]

    def falloff(radii):
        distance_squared = (dx / radii[0]) ** 2 + (dy / radii[1]) ** 2
        return np.maximum(1 - distance_squared, 0) ** 2

    strength = amount * (.78 * falloff(emitter) + .22 * falloff(spill))
    rgb = np.asarray(image, dtype=np.float32)
    warm = np.array([.83, .64, .34])
    return Image.fromarray(np.rint(rgb + (255 - rgb) * warm * strength[..., None]).astype("uint8"))


def composition_image(stage_id):
    source = COMPOSITION_LIGHTS[stage_id][0]
    with Image.open(REPORT / "compositions" / f"{source}.png") as original:
        return original.convert("RGB")


def composition_frames(stage_id, dest):
    image = composition_image(stage_id)
    _, center, emitter, spill = COMPOSITION_LIGHTS[stage_id]
    off = dest / "composition_off.jpg"
    on = dest / "composition_on.jpg"
    save_jpg(image, off)
    save_jpg(light_composition(image, center, emitter, spill), on)
    frames = [("关灯 · 原始构图", off), ("点灯 · 同一构图", on)]
    labels = dict(STATION_FRAMES)
    # Overscan the same artwork just enough to pan without exposing blank edges.
    width, height = COMPOSITION_SIZE
    for name, (x, y, amount) in CAMERA_SAMPLES.items():
        lit = light_composition(image, center, emitter, spill, amount) if amount else image
        overscan = ImageOps.fit(lit, (width + 120, height + 60), Image.Resampling.LANCZOS)
        left, top = 60 + x, 30 + y
        path = dest / f"composition_{name}.jpg"
        save_jpg(overscan.crop((left, top, left + width, top + height)), path)
        frames.append((labels[name], path))
    return frames


def preview_transitions(stages):
    alley = GAME / "assets/stations/g01_st_l1_01_alley/station"
    previous = render(read_json(alley / "station.json"), alley).convert("RGB")
    transitions = {}
    for stage in stages:
        dest = REPORT / "stations" / stage["id"]
        following = ImageOps.fit(composition_image(stage["id"]), COMPOSITION_SIZE, Image.Resampling.LANCZOS)
        frames = []
        for step in range(5):
            if step == 0:
                frame = previous.copy()
            elif step == 4:
                frame = following.copy()
            else:
                width, height = previous.size
                y, x = np.ogrid[:height, :width]
                edge = width * step / 4 + (y / height - .5) * 220
                opacity = np.clip((edge - x) / 18 + .5, 0, 1)
                mask = Image.fromarray(np.rint(opacity * 255).astype("uint8"))
                frame = Image.composite(following, previous, mask)
            output = dest / f"transition_{step * 25:03d}.png"
            frame.save(output)
            frames.append((f"转场 {step * 25}%", output))
        transitions[stage["title"]] = frames
        previous = following
    return transitions


def write_gallery(stations, transitions, assets):
    folder = REPORT / "gallery"
    folder.mkdir(exist_ok=True)

    def tile(label, source):
        destination = source.with_suffix(".jpg")
        if source != destination:
            with Image.open(source) as original:
                rgba = original.convert("RGBA")
                base = Image.new("RGBA", rgba.size, "#77737b")
                base.alpha_composite(rgba)
                save_jpg(base.convert("RGB"), destination)
        href = html.escape(os.path.relpath(destination, folder).replace(os.sep, "/"), quote=True)
        name = html.escape(label)
        return (f'<figure><a href="{href}" target="_blank"><img src="{href}" alt="{name}" '
                f'loading="lazy" decoding="async"></a><figcaption>{name}</figcaption></figure>')

    sections = []
    for index, station in enumerate(stations, 1):
        primary = "".join(tile(label, file) for label, file in station["composition_frames"][:2])
        secondary = "".join(tile(label, file) for label, file in
                            station["composition_frames"][2:] + transitions.get(station["id"], []))
        sections.append(
            f'<section id="station-{index}"><h2>{html.escape(station["id"])}</h2><div class="pair">{primary}</div>'
            f'<details><summary>原始构图 · 相机移动与入场转场</summary>'
            f'<div class="grid">{secondary}</div></details></section>'
        )
    asset_cards = []
    for asset in assets:
        frames = asset["frames"]
        extra = ""
        if len(frames) > 1:
            extra = '<details><summary>查看其他状态</summary>' + "".join(
                tile(label, file) for label, file in frames[1:]) + "</details>"
        asset_cards.append(f'<article>{tile(*frames[0])}{extra}</article>')
    links = " · ".join(f'<a href="#station-{i}">{html.escape(s["id"])}</a>' for i, s in enumerate(stations, 1))
    page = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>纸灯城 · T10 A5 静帧画廊</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0 auto;max-width:1500px;padding:28px;background:#171b25;color:#f0e7dd;font:16px/1.55 system-ui,sans-serif}
h1{margin:0 0 6px}h2{font-size:22px;margin:0 0 12px}p,nav{margin:8px 0;color:#c8c4ca}a{color:#efb78b}
section{border-top:1px solid #41414c;margin-top:24px;padding-top:18px}
.pair,.grid{display:grid;gap:12px}.pair{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr))}
figure{margin:0;background:#222835;border:1px solid #404350}
img{display:block;width:100%;height:auto}figcaption{padding:8px 10px}details{margin-top:12px}summary{cursor:pointer;margin-bottom:10px}
#assets img{height:210px;object-fit:contain;background:#77737b}
@media(max-width:720px){body{padding:14px}.pair{grid-template-columns:1fr}}
</style></head><body><main><h1>纸灯城 · T10 A5 静帧画廊</h1>
<p>每站左图直接取自原始构图，右图沿用同一张图，只在灯具或招牌周围加光。点图打开原尺寸 JPG。</p>
<p><a href="../report.md">制作与检查报告</a> · <a href="../review.yaml">审核表</a></p>
"""
    page += f'<nav>{links} · <a href="#assets">角色和新素材</a></nav>' + "".join(sections)
    page += '<section id="assets"><h2>角色和新素材</h2><div class="grid">' + "".join(asset_cards)
    (folder / "index.html").write_text(page + "</div></section></main></body></html>\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", action="store_true")
    parser.add_argument("--stage", choices=tuple(LIGHT_NAMES))
    args = parser.parse_args()
    if args.screen:
        screen_compositions()
        return
    layout = read_json(REPORT / "layouts.json")
    hud = read_json(GAME / "assets/ui/hud_layout.json")
    results = []
    stages = [stage for stage in layout["stations"] if args.stage in (None, stage["id"])]
    for stage in stages:
        try:
            results.append(stage_preview(stage, hud))
        except (ValueError, FileNotFoundError) as error:
            print(f"{stage['id']}: {error}")
    if results and not args.stage:
        transitions = preview_transitions(stages) if len(results) == len(stages) else {}
        asset_index = REPORT / "asset_screen.json"
        assets = []
        if asset_index.exists():
            for asset in read_json(asset_index):
                if asset["status"] != "prepared":
                    continue
                folder = REPORT / "assets" / asset["id"]
                if asset["category"] == "puppet_sheet":
                    labels = ("待机", "探出", "走路", "受惊", "呼救", "挣扎", "获救", "感谢")
                    frames = [(f'{asset["id"]} · {label}', folder / f"pose_{pose}.png")
                              for pose, label in zip(asset["poses"], labels)]
                elif asset["category"] == "enemy":
                    frames = [(f'{asset["id"]} · 朱砂态', folder / "texture.png"),
                              ("硬化态", folder / "hardened_preview.png")]
                else:
                    frames = [(asset["id"], folder / "texture.png")]
                assets.append({"id": asset["id"], "status": "pending", "frames": frames})
        write_gallery(results, transitions, assets)
        review_path = REPORT / "review.yaml"
        if len(results) == 4 and len(assets) == 20 and not review_path.exists():
            review_form(results + assets, review_path)
    if len(results) != len(stages):
        raise SystemExit(1)
    print(f"{len(results)} stage preview packs rendered")


if __name__ == "__main__":
    main()
