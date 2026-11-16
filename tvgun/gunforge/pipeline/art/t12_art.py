"""Screen the cinema compositions and preview localized lighting on their original art."""
import argparse
import html
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from artlib import GAME, digest, effective_radius, write_json
from checks import run
from paper_ops import alpha_crop, limit_luminance, palette
from t10_preview import COMPOSITION_SIZE, light_composition, read_json, save_jpg


REPORT = GAME / "reports/art/T12"
PREVIEWS = REPORT / "previews"
BOSS = REPORT / "screen_shadow"


def checked_jpg(image, path):
    save_jpg(image.convert("RGB"), path)
    result = run("C03", {"file": path})
    if result["status"] != "pass":
        raise ValueError(f"Preview exceeds brightness cap: {path.name}")
    return result


def source_art(source):
    with Image.open(REPORT / source) as original:
        return original.convert("RGB")


def sprite(source, target):
    with Image.open(REPORT / source) as original:
        image = original.convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda a: round(max(0, a - 16) * 255 / 239)))
    image, _ = alpha_crop(image, threshold=32, pad=4)
    image.thumbnail(target, Image.Resampling.LANCZOS)
    return limit_luminance(image)


def placement(image, rect):
    x, y, width, height = rect
    fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
    return fitted, (x + (width - fitted.width) // 2, y + (height - fitted.height) // 2)


def put(frame, image, rect):
    fitted, position = placement(image, rect)
    frame.alpha_composite(fitted, position)


def paper_target(size, color, shape):
    width, height = size
    y, x = np.ogrid[:height, :width]
    dx, dy = (x - width / 2) / (width * .46), (y - height / 2) / (height * .46)
    distance = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    edge = 1 + .045 * np.sin(5 * angle) + .018 * np.cos(8 * angle)
    mask = Image.fromarray((distance < edge).astype("uint8") * 255)
    source = ImageOps.fit(shape, size, Image.Resampling.LANCZOS)
    grain = (np.asarray(source.convert("L"), dtype=float) - 64) * .23
    bands = 8 * np.exp(-((distance - .79) / .08) ** 2)
    rgb = np.clip(np.asarray(color) + (grain + bands)[..., None], 0, 255).astype("uint8")
    image = Image.fromarray(rgb).convert("RGBA")
    image.putalpha(mask.filter(ImageFilter.GaussianBlur(.9)))
    return image


def beam_mask(projector):
    matte = Image.new("L", COMPOSITION_SIZE)
    lens = tuple(projector["lens"])
    left, right = (tuple(point) for point in projector["screen_span"])
    ImageDraw.Draw(matte).polygon([lens, left, right], fill=255)
    matte = matte.filter(ImageFilter.GaussianBlur(7))
    y = np.arange(COMPOSITION_SIZE[1])[:, None]
    length = max(1, lens[1] - (left[1] + right[1]) * .5)
    taper = np.clip(1 - (lens[1] - y) / length * .36, 0, 1)
    return Image.fromarray(np.rint(np.asarray(matte) * taper).astype("uint8"))


def boss_art(base, boss, generated):
    BOSS.mkdir(exist_ok=True)
    machine = sprite(generated["projector"], (432, 240))
    reel = sprite(generated["reel"], (252, 228))
    shadow = sprite(generated["shadow"], (920, 450))
    reel_size = tuple(boss["projectors"][0]["reel"]["rect"][2:])
    ink = paper_target(reel_size, (27, 22, 39), shadow)
    core = paper_target(tuple(boss["core"]["rect"][2:]), (182, 53, 68), shadow)
    assets = {"projector": machine, "clean_reel": reel, "shadow": shadow, "reel_ink": ink, "core": core}
    for name, image in assets.items():
        image.save(BOSS / f"{name}.png")
    for name, image in (("reel_ink", ink), ("core", core)):
        mask = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        mask.save(BOSS / f"{name}_hit.png")
    radii = {name: round(effective_radius(np.asarray(image.getchannel("A")) >= 128)[0], 2)
             for name, image in (("reel_ink", ink), ("core", core))}
    if min(radii.values()) < 40:
        raise ValueError("A Boss target is below the 40-pixel effective-radius floor")

    background = ImageOps.fit(base, COMPOSITION_SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    projectors = []
    for projector in boss["projectors"]:
        fitted, position = placement(machine, projector["rect"])
        lens = [round(position[axis] + fitted.size[axis] * boss["lens_uv"][axis]) for axis in (0, 1)]
        x, y, width, height = projector["reel"]["rect"]
        dx, dy = boss["reel_offset"]
        reel_rect = [x + dx, y + dy, width, height]
        projectors.append({**projector, "lens": lens, "art_rect": [*position, *fitted.size],
                           "reel": {**projector["reel"], "rect": reel_rect}})
    fixtures = Image.new("RGBA", COMPOSITION_SIZE)
    fixture = ImageDraw.Draw(fixtures)
    for projector in projectors:
        rx, ry, rw, rh = projector["reel"]["rect"]
        x, y, width, _ = projector["rect"]
        pin = (rx + rw // 2, ry + rh // 2)
        base_pin = (x + width // 2 - 38, y + 23)
        fixture.line((pin, base_pin), fill="#271f30", width=15)
        fixture.line((pin, base_pin), fill="#816952", width=7)
    background.save(BOSS / "background.png")
    fixtures.save(BOSS / "fixtures.png")
    put(background, shadow, boss["shadow_rect"])
    lights = [beam_mask(projector) for projector in projectors]
    beam_textures = []
    for index, mask in enumerate(lights, 1):
        mask.save(BOSS / f"beam_{index}_mask.png")
        texture = Image.new("RGBA", COMPOSITION_SIZE, "white")
        texture.putalpha(mask)
        file = f"beam_{index}.png"
        texture.save(BOSS / file)
        beam_textures.append(file)
    proofs = {}
    before = None
    for cleared in (0, 1, 3):
        frame = background.copy()
        for index, mask in enumerate(lights):
            warm = index < cleared
            tint = Image.new("RGBA", COMPOSITION_SIZE, (233, 163, 105) if warm else (44, 36, 84))
            tint.putalpha(mask.point(lambda value: round(value * (.32 if warm else .44))))
            frame.alpha_composite(tint)
        frame.alpha_composite(fixtures)
        for index, projector in enumerate(projectors):
            warm = index < cleared
            put(frame, machine, projector["rect"])
            put(frame, reel, projector["reel"]["rect"])
            if not warm:
                put(frame, ink, projector["reel"]["rect"])
        if cleared == 3:
            put(frame, core, boss["core"]["rect"])
        if cleared == 0:
            before = np.asarray(frame).copy()
        elif cleared == 1:
            changed = np.any(np.asarray(frame) != before, axis=2)
            allowed = np.asarray(lights[0]) > 0
            x, y, width, height = projectors[0]["reel"]["rect"]
            allowed[y:y + height, x:x + width] = True
            if not changed.any() or np.any(changed & ~allowed):
                raise ValueError("Cleaning one reel changed pixels outside its beam and reel")
        proofs[f"screen_{cleared}"] = checked_jpg(frame, PREVIEWS / f"screen_{cleared}.jpg")
    write_json(BOSS / "art.json", {
        "scope": "art preview and standalone Godot review", "layout": {**boss, "projectors": projectors},
        "assets": {key: f"{key}.png" for key in (*assets, "background", "fixtures")},
        "hit_masks": {"reel_ink": "reel_ink_hit.png", "core": "core_hit.png"},
        "beam_masks": [f"beam_{index}_mask.png" for index in range(1, 4)], "radii_px": radii,
        "beam_textures": beam_textures,
        "C03": proofs, "first_beam_change_local": True,
    })


def gallery(stations):
    def picture(file, label):
        return f'<figure><a href="previews/{file}.jpg"><img src="previews/{file}.jpg" alt="{label}" loading="lazy"></a><figcaption>{label}</figcaption></figure>'

    sections = []
    parallax = REPORT / "parallax"
    for stage in stations:
        name = html.escape(stage["title"])
        identifier = stage["id"]
        if identifier == "screen_stage":
            cards = [picture("screen_stage_off", "背景原画"), picture("screen_0", "三束墨光"),
                     picture("screen_1", "左束恢复暖光"), picture("screen_3", "影核开放")]
            if (BOSS / "gpu_checks.json").exists():
                cards.extend(picture(f"godot_screen_{step}", label) for step, label in
                             ((0, "Godot · 三束墨光"), (1, "Godot · 左束恢复"), (3, "Godot · 影核开放")))
        else:
            cards = [picture(f"{identifier}_off", "关灯"), picture(f"{identifier}_lit", "点灯")]
        proof_links = []
        if (parallax / "engine_checks.json").exists():
            for suffix, label in (("rest", "静止"), ("lit", "点灯"), ("corner_2", "视差极限")):
                relative = f"parallax/frames/{identifier}_{suffix}.jpg"
                if (REPORT / relative).is_file():
                    proof_links.append(f'<a href="{relative}">{label}</a>')
        proof = f"<p>Godot 分层版　{' · '.join(proof_links)}</p>" if proof_links else ""
        sections.append(f"<section><h2>{name}</h2><div>{''.join(cards)}</div>{proof}</section>")
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>纸灯城 · 旧影院构图</title>
<style>
body{color:#eee2db;background:#171823;font:16px system-ui;margin:24px auto;padding:0 20px;max-width:1320px}
section{border-top:1px solid #5a4d60;margin-top:22px}section div{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
figure{margin:0;background:#232535}figcaption{padding:8px}img{width:100%;display:block}a{color:#f2c9a7}
@media(max-width:700px){section div{grid-template-columns:1fr}}
</style><h1>纸灯城 · 旧影院构图初稿</h1>
<p>点图打开原尺寸 JPG。普通站点的关灯和点灯使用同一张原画，银幕前展示胶片盘和光束的分层预览。</p>
<p><a href="report.md">制作记录</a></p>
"""
    if (REPORT / "actors/index.html").exists():
        page += '<p><a href="actors/index.html">纸居民和墨怪 JPG</a></p>'
    (REPORT / "gallery.html").write_text(page + "".join(sections), encoding="utf-8")


def verify_gpu(captures):
    pack = read_json(BOSS / "art.json")
    screens = {}
    checks = {}
    for step in (0, 1, 3):
        file = captures / f"screen_{step}.png"
        with Image.open(file) as image:
            if image.size != COMPOSITION_SIZE:
                raise ValueError(f"Unexpected capture size: {file}")
            screens[step] = image.convert("RGB")
        checks[str(step)] = checked_jpg(screens[step], PREVIEWS / f"godot_screen_{step}.jpg")
    difference = np.any(np.asarray(screens[0]) != np.asarray(screens[1]), axis=2)
    with Image.open(BOSS / pack["beam_masks"][0]) as mask:
        allowed = np.asarray(mask) > 0
    x, y, width, height = pack["layout"]["projectors"][0]["reel"]["rect"]
    allowed[y:y + height, x:x + width] = True
    if not difference.any() or np.any(difference & ~allowed):
        raise ValueError("Godot changed pixels outside the selected reel and beam")
    with Image.open(BOSS / pack["assets"]["core"]) as image:
        core, (x, y) = placement(image, pack["layout"]["core"]["rect"])
        point = (core.width // 2, core.height // 2)
        pixel = (x + point[0], y + point[1])
        expected = core.getpixel(point)[:3]
    if screens[3].getpixel(pixel) != expected or any(screens[step].getpixel(pixel) == expected for step in (0, 1)):
        raise ValueError("Godot did not reveal the final core exclusively in the last state")
    write_json(BOSS / "gpu_checks.json", {"C03": checks, "viewport": COMPOSITION_SIZE,
               "first_beam_changed_pixels": int(difference.sum()), "first_beam_change_local": True,
               "core_color_verified": True})
    gallery(read_json(REPORT / "layouts.json")["stations"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-gpu", type=Path)
    args = parser.parse_args()
    PREVIEWS.mkdir(exist_ok=True)
    if args.verify_gpu:
        verify_gpu(args.verify_gpu)
        return
    alignment = read_json(REPORT / "art_alignment.json")
    generated = read_json(REPORT / "generation.json")
    by_id = {row["id"]: row["output"] for row in generated}
    stations = read_json(REPORT / "layouts.json")["stations"]
    checks = {}
    for stage in stations:
        identifier = stage["id"]
        original = source_art(by_id[identifier])
        checks[identifier] = {"size": list(original.size),
                              "C03_off": checked_jpg(original, PREVIEWS / f"{identifier}_off.jpg")}
        sample = original.copy()
        sample.thumbnail((360, 360))
        sample_path = PREVIEWS / f"{identifier}_screen.png"
        sample.save(sample_path)
        checks[identifier]["C04"] = run("C04", {"file": sample_path, "palette_rgb": palette()})
        if identifier == "screen_stage":
            boss_art(original, {**stage["boss"], **alignment["boss"]}, by_id)
            continue
        light = alignment["lamps"][identifier]
        lit = light_composition(original, light["center"], light["emitter"], light["spill"])
        y, x = np.ogrid[:original.height, :original.width]
        cx, cy = light["center"]
        rx, ry = light["spill"]
        outside = ((x / original.width - cx) / rx) ** 2 + ((y / original.height - cy) / ry) ** 2 >= 1
        if np.any(np.asarray(lit)[outside] != np.asarray(original)[outside]):
            raise ValueError(f"{identifier}: lit preview changed the area outside the lamp")
        checks[identifier]["C03_lit"] = checked_jpg(lit, PREVIEWS / f"{identifier}_lit.jpg")
        checks[identifier]["outside_spill_unchanged"] = True
    for row in generated:
        source = REPORT / row["output"]
        with Image.open(source) as image:
            row["size"] = list(image.size)
        row["sha256"] = digest(source)
    write_json(REPORT / "generation.json", generated)
    write_json(REPORT / "art_checks.json", checks)
    gallery(stations)


if __name__ == "__main__":
    main()
