"""Build cinema NPC pose samples and separate ink collision from props."""
import html

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.restoration import inpaint_biharmonic

from artlib import GAME, digest, effective_radius, encode_sdf, write_json
from checks import run
from paper_ops import alpha_crop
from t10_assets import bind_puppet, cinnabar, pair_components
from t10_preview import read_json, save_jpg
from t12_art import REPORT, sprite


OUTPUT = REPORT / "actors"
RESIDENTS = {"projectionist": "放映员", "ticket_clerk": "检票员", "passerby_b": "路人 B"}


def polygon_mask(image, points):
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).polygon([(round(x * image.width), round(y * image.height)) for x, y in points], fill=255)
    return (np.asarray(mask) >= 128) & (np.asarray(image.getchannel("A")) >= 128)


def erase_stamp(image, stamp_rect=None):
    pixels = np.array(image)
    if stamp_rect:
        left, top, right, bottom = stamp_rect
        mark = np.zeros(pixels.shape[:2], dtype=bool)
        mark[round(top * image.height):round(bottom * image.height),
             round(left * image.width):round(right * image.width)] = True
    else:
        labels, _ = ndimage.label(cinnabar(pixels))
        sizes = np.bincount(labels.ravel())[1:]
        if not sizes.size or sizes.max() < 18:
            return image
        mark = labels == sizes.argmax() + 1
    ys, xs = np.nonzero(mark)
    pad = max(4, round((xs.max() - xs.min()) * (.05 if stamp_rect else .20)))
    region = np.s_[max(0, ys.min() - 2 * pad):ys.max() + 2 * pad + 1,
                   max(0, xs.min() - 2 * pad):xs.max() + 2 * pad + 1]
    repair = ndimage.binary_dilation(mark[region], iterations=pad)
    rgb = pixels[region][..., :3]
    filled = inpaint_biharmonic(rgb, repair, channel_axis=-1)
    rgb[repair] = np.rint(filled[repair] * 255).astype("uint8")
    return Image.fromarray(pixels)


def jpg(image, path):
    area = image.getchannel("A").getbbox()
    if area:
        image = image.crop(area)
    background = Image.new("RGBA", image.size, "#615b68")
    background.alpha_composite(image)
    save_jpg(background.convert("RGB"), path)


def save_mask(mask, path):
    Image.fromarray(mask.astype("uint8") * 255).save(path)


def fit_mask(mask, display_width):
    height, width = mask.shape
    scale = display_width / width
    image = Image.fromarray(mask.astype("uint8") * 255)
    image = image.resize((display_width, round(height * scale)), Image.Resampling.LANCZOS)
    return np.asarray(image) >= 128


def build_enemy(identifier, source, alignment, folder):
    body = erase_stamp(sprite(source, (768, 768)), alignment.get("erase_rect"))
    hit = polygon_mask(body, alignment["ink"])
    labels, _ = ndimage.label(hit)
    sizes = np.bincount(labels.ravel())[1:]
    if not sizes.size:
        raise ValueError(f"{identifier} ink mask is empty")
    hit = labels == sizes.argmax() + 1
    width = alignment["display_width"]
    radius = effective_radius(fit_mask(hit, width))[0]
    if radius < 40:
        raise ValueError(f"{identifier} effective hit radius {radius:.2f} below 40 at {width}px")
    distance = ndimage.distance_transform_edt(hit)
    y, x = np.unravel_index(distance.argmax(), hit.shape)
    stamp_file = GAME / "reports/art/T10/assets/ink_sign/core.png"
    with Image.open(stamp_file) as image:
        stamp, _ = alpha_crop(image, pad=0)
    diameter = round(min(distance[y, x] * .92, body.width * .10))
    stamp.thumbnail((diameter, diameter), Image.Resampling.LANCZOS)
    core = Image.new("RGBA", body.size)
    core.alpha_composite(stamp, (x - stamp.width // 2, y - stamp.height // 2))
    weak = np.asarray(core.getchannel("A")) >= 128
    if np.any(weak & ~hit) or not weak.any():
        raise ValueError(f"{identifier}: weak stamp not contained in ink")
    body.save(folder / "body.png")
    core.save(folder / "weak.png")
    save_mask(hit, folder / "hit.png")
    save_mask(weak, folder / "weak_mask.png")
    Image.fromarray(encode_sdf(hit)).save(folder / "sdf.png")
    display = body.copy()
    display.alpha_composite(core)
    display.save(folder / "vulnerable.png")
    jpg(display, folder / "vulnerable.jpg")
    ink_outline = hit & ~ndimage.binary_erosion(hit, iterations=3)
    overlay = Image.new("RGBA", body.size, "#e9c88d")
    overlay.putalpha(Image.fromarray(ink_outline.astype("uint8") * 255))
    display.alpha_composite(overlay)
    jpg(display, folder / "hit_zone.jpg")
    sdf = run("C16", {"alpha": folder / "hit.png", "sdf": folder / "sdf.png", "source_color": False})
    if sdf["status"] != "pass":
        raise ValueError(f"{identifier} distance-field roundtrip failed")
    return {"id": identifier, "states": {"vulnerable": {"sprite": "vulnerable.png", "body": "body.png",
             "primary": "hit.png", "weak": "weak_mask.png", "weak_texture": "weak.png", "sdf": "sdf.png"}},
            "display_width_px": width, "effective_radius_px": radius, "C16": sdf}


def build_umbrella(source, alignment, folder):
    opened = erase_stamp(sprite(source, (768, 768)))
    canopy = polygon_mask(opened, alignment)
    if not canopy.any():
        raise ValueError("Umbrella canopy mask is empty")
    opened.save(folder / "open.png")
    save_mask(canopy, folder / "canopy_invalid.png")
    jpg(opened, folder / "open.jpg")
    return {"sprite": "open.png", "invalid": "canopy_invalid.png", "primary": None, "weak": None}


def write_gallery():
    cards = []
    for identifier, title in (*RESIDENTS.items(), ("ink_tape", "磁带墨"), ("ink_umbrella", "墨伞")):
        files = ["idle", "wave_for_help"] if identifier in RESIDENTS else ["vulnerable", "hit_zone"]
        if identifier == "ink_umbrella":
            files.insert(0, "open")
        labels = {"idle": "待机", "wave_for_help": "呼救", "vulnerable": "可射态",
                  "hit_zone": "命中区", "open": "撑伞 · 伞面不可射"}
        tiles = []
        for file in files:
            url = f"{identifier}/{file}.jpg"
            tiles.append(f'<figure><a href="{url}"><img src="{url}" alt="{labels[file]}"></a><figcaption>{labels[file]}</figcaption></figure>')
        cards.append(f"<section><h2>{html.escape(title)}</h2><div>{''.join(tiles)}</div></section>")
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>旧影院 · 角色与墨怪</title>
<style>body{background:#191b28;color:#eee0d8;font:16px system-ui;max-width:1100px;margin:24px auto;padding:0 18px}
section div{display:flex;flex-wrap:wrap;gap:16px}figure{margin:0}img{height:255px;max-width:100%;object-fit:contain;background:#615b68}
figcaption{padding:5px}a{color:#ebc7a1}</style><h1>旧影院 · 角色与墨怪</h1>
<p>点图打开 JPG。金线标出主可伤害区。</p><p><a href="../report.md">制作记录</a></p>"""
    (OUTPUT / "index.html").write_text(page + "".join(cards), encoding="utf-8")


def main():
    alignment = read_json(REPORT / "actor_alignment.json")
    generation = read_json(REPORT / "actor_generation.json")
    sources = {row["id"]: row["output"] for row in generation}
    evidence = {}
    for identifier in RESIDENTS:
        source = REPORT / sources[identifier]
        folder = OUTPUT / identifier
        folder.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as sheet:
            parts = pair_components(sheet)
        row = bind_puppet(parts, folder, source)
        if row["checks"]["C10"]["status"] == "fail":
            raise ValueError(f"{identifier} has a disconnected joint in a sampled pose")
        for state in ("idle", "wave_for_help"):
            with Image.open(folder / f"pose_{state}.png") as image:
                jpg(image, folder / f"{state}.jpg")
        evidence[identifier] = row
    for identifier, source_id in (("ink_tape", "ink_tape"), ("ink_umbrella", "umbrella_closed")):
        folder = OUTPUT / identifier
        folder.mkdir(parents=True, exist_ok=True)
        row = build_enemy(identifier, sources[source_id], alignment[identifier], folder)
        if identifier == "ink_umbrella":
            row["states"]["open"] = build_umbrella(sources["umbrella_open"], alignment["canopy"], folder)
        write_json(folder / "enemy.json", row)
        evidence[identifier] = row
    for row in generation:
        file = REPORT / row["output"]
        with Image.open(file) as image:
            row["size"] = list(image.size)
        row["sha256"] = digest(file)
    write_json(REPORT / "actor_generation.json", generation)
    write_json(OUTPUT / "checks.json", evidence)
    write_gallery()


if __name__ == "__main__":
    main()
