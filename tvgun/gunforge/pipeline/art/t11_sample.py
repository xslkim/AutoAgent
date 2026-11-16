"""Build the T11 three-link review sample with one shared paper silhouette."""
import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from scipy import ndimage

from artlib import GAME, digest, write_json
from paper_ops import alpha_crop, limit_luminance
from preview import movie, transform, translation
from t10_preview import COMPOSITION_SIZE, composition_image, read_json, save_jpg


ART = GAME / "reports/art"
REPORT = ART / "T11"
OUTPUT = REPORT / "sample"
ORDER = (2, 1, 0)
FPS = 15
DURATION = 5.0
SHOT_TIMES = (1.25, 2.55, 3.85)
PAPER_PINS = ((69, 510), (1698, 529))


def ink_texture():
    with Image.open(ART / "T09/generation/dragon_active.png") as source:
        rgb = np.asarray(source.convert("RGB"))
    y, x = np.ogrid[:rgb.shape[0], :rgb.shape[1]]
    r, _, b = rgb.astype(np.int16).transpose(2, 0, 1)
    region = (x > 140) & (x < 1580) & (y > 220) & (y < 610)
    dark = region & (r < 100) & (r - b < 27)
    labels, _ = ndimage.label(ndimage.binary_closing(dark, iterations=3))
    size = np.bincount(labels.ravel())
    if len(size) < 2 or size[1:].max() < 10_000:
        raise ValueError("Could not isolate the T09 ink cloud")
    cloud = ndimage.binary_fill_holes(labels == 1 + size[1:].argmax())
    alpha = Image.fromarray(cloud.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(2))
    ink = Image.fromarray(rgb).convert("RGBA")
    ink.putalpha(alpha)
    return alpha_crop(ink, pad=4)[0]


def assets():
    source = REPORT / "source/segment_paper.png"
    with Image.open(source) as original:
        paper, crop = alpha_crop(original, pad=8)
    original_size = paper.size
    paper.thumbnail((768, 768), Image.Resampling.LANCZOS)
    paper = limit_luminance(paper)
    pivots = [tuple((pin[axis] - crop[axis]) * paper.size[axis] / original_size[axis] for axis in (0, 1))
              for pin in PAPER_PINS]
    for x, y in pivots:
        if paper.getpixel((round(x), round(y)))[3] < 128:
            raise ValueError("Copper pin lies outside paper silhouette")
    ink = ink_texture()
    ink.thumbnail((round(paper.width * .69), round(paper.height * .44)), Image.Resampling.LANCZOS)
    pos = ((paper.width - ink.width) // 2, round(paper.height * .50 - ink.height / 2))
    hit_ink = Image.new("RGBA", paper.size)
    hit_ink.alpha_composite(ink, pos)
    ink_a = hit_ink.getchannel("A")
    hit = np.asarray(ink_a) >= 128
    if (hit & (np.asarray(paper.getchannel("A")) < 128)).any():
        raise ValueError("Ink hit zone lies outside paper")
    edge = ink_a.filter(ImageFilter.GaussianBlur(12))
    glow = Image.new("RGBA", paper.size, (246, 181, 92, 0))
    glow.putalpha(edge)
    purified_glow = Image.new("RGBA", paper.size, (241, 172, 93, 0))
    purified_glow.putalpha(paper.getchannel("A").filter(ImageFilter.GaussianBlur(16)))
    dim = grade(paper, .73, .88)
    locked = dim.copy()
    locked_ink = grade(hit_ink, .28, 1.8)
    locked.alpha_composite(locked_ink)
    paper.save(OUTPUT / "paper.png")
    hit_ink.save(OUTPUT / "ink.png")
    glow.save(OUTPUT / "warm_glow.png")
    purified_glow.save(OUTPUT / "purified_glow.png")
    locked.save(OUTPUT / "locked.png")
    Image.fromarray(hit.astype("uint8") * 255).save(OUTPUT / "hit_mask.png")
    source_record = read_json(REPORT / "source/generation.json")
    source_record.update(size=list(original.size), sha256=digest(source),
                         reference_sha256=digest(REPORT / source_record["reference"]))
    write_json(OUTPUT / "source.json", source_record)
    return paper, hit_ink, glow, purified_glow, locked, pivots


def grade(image, saturation, value):
    """Grade one layer while leaving its silhouette and dimensions in place."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    gray = rgb @ np.array([.2126, .7152, .0722])
    graded = np.rint((gray[..., None] + (rgb - gray[..., None]) * saturation) * value)
    result = Image.fromarray(graded.clip(0, 255).astype("uint8"))
    result.putalpha(image.getchannel("A"))
    return result


def fade_layer(image, opacity):
    faded = image.copy()
    faded.putalpha(image.getchannel("A").point(lambda value: round(value * opacity)))
    return faded


def chain(pivots, clock):
    left, right = pivots
    scale = .44
    anchor = np.array([423 + 46 * math.sin(clock * 1.3), 465 + 42 * math.sin(clock * 1.9), 1])
    output = []
    for index in range(3):
        heading = math.radians(14 * math.sin(clock * 2.3 - index * 1.16))
        c, s = math.cos(heading), math.sin(heading)
        rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        matrix = translation(*anchor[:2]) @ rotation @ np.diag([scale, scale, 1]) @ translation(-left[0], -left[1])
        if not np.allclose(matrix @ [*left, 1], anchor, atol=1e-7):
            raise ValueError("Segment joint separated from chain")
        output.append(matrix)
        anchor = matrix @ [*right, 1]
    return output


def state(index, time):
    shot = ORDER.index(index)
    if time >= SHOT_TIMES[shot]:
        return "purified", min(1, (time - SHOT_TIMES[shot]) / .38)
    if shot == 0 or time >= SHOT_TIMES[shot - 1]:
        return "active", 1
    return "locked", 1


def frame(background, pieces, clock, comparison=False):
    paper, ink, glow, purified_glow, locked, pivots = pieces
    scene = background.copy()
    matrices = chain(pivots, clock)
    for index in (2, 1, 0):
        phase, progress = state(index, clock) if not comparison else (("locked", 1), ("active", 1), ("purified", 1))[index]
        if phase == "locked":
            body = locked
        else:
            body = paper.copy()
            if phase == "purified":
                body = fade_layer(purified_glow, .24 * progress)
                body.alpha_composite(paper)
            if phase == "active" or progress < 1:
                pulse = .45 + .27 * (1 + math.sin(clock * 9))
                opacity = 1 - progress if phase == "purified" else 1
                body.alpha_composite(fade_layer(glow, pulse * opacity))
                body.alpha_composite(fade_layer(ink, opacity))
        scene.alpha_composite(transform(body, matrices[index], COMPOSITION_SIZE))
    return limit_luminance(scene).convert("RGB")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pieces = assets()
    background = ImageOps.fit(composition_image("square"), COMPOSITION_SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    save_jpg(frame(background, pieces, 0, comparison=True), OUTPUT / "three_states.jpg")
    for name, clock in (("start", .75), ("tail_purified", 1.85), ("body_purified", 3.05), ("all_purified", 4.55)):
        save_jpg(frame(background, pieces, clock), OUTPUT / f"{name}.jpg")
    duration = round(DURATION * FPS)
    video_frames = [frame(background, pieces, i / FPS).resize((1280, 674), Image.Resampling.LANCZOS)
                    for i in range(duration)]
    movie(video_frames, OUTPUT / "purification.mp4", fps=FPS)
    samples = []
    for tick in range(duration):
        clock = tick / FPS
        states = [state(index, clock)[0] for index in range(3)]
        if states.count("active") > 1:
            raise ValueError("Sample exposes more than one shootable link")
        samples.append(states)
    write_json(OUTPUT / "sample.json", {
        "status": "sample_for_first_review", "pivots": pieces[-1], "chain": [0, 1, 2],
        "head_side": 0, "tail_side": 2, "opening_order": ORDER, "shot_seconds": SHOT_TIMES,
        "base": "paper.png", "locked": "locked.png", "ink": "ink.png", "active_glow": "warm_glow.png",
        "purified_glow": "purified_glow.png",
        "active_hit_mask": "hit_mask.png", "shared_silhouette": True,
        "active_max": max(states.count("active") for states in samples), "frames_checked": duration,
        "scope": "three-link preview compositor sample",
    })
    print(f"T11: {duration} linked frames; one active link at a time")


if __name__ == "__main__":
    main()
