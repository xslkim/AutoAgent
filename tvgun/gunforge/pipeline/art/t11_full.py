"""Build the full Ink Dragon art pack and its square-stage review media."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy import ndimage

from artlib import digest, effective_radius, write_json, yprime
from paper_ops import alpha_crop, limit_luminance
from preview import movie, transform, translation
from t10_preview import COMPOSITION_SIZE, composition_image, read_json, save_jpg
from t11_sample import REPORT, fade_layer, grade, ink_texture


PACK = REPORT / "full"
PARTS = PACK / "parts"
SCALE = .5
BODY_SIZES = ((159, 143), (158, 141), (157, 140), (156, 137),
              (154, 135), (152, 133), (150, 131), (147, 128))
ORIGIN = (345, 466)
SWAY = (27, 40)
ORDER = tuple(range(7, -1, -1))
MIN_RADIUS = 40


def glow(mask, color, blur):
    image = Image.new("RGBA", mask.size, color)
    image.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
    return image


def ink_cloud(size, index, alpha, texture):
    height, width = alpha.shape
    y, x = np.ogrid[:height, :width]
    dx = (x - width * (.49 + .012 * math.sin(index * 1.4))) / (width * .365)
    dy = (y - height * .53) / (height * .294)
    theta = np.arctan2(dy, dx)
    edge = 1 + .035 * np.sin(5 * theta + index) + .024 * np.cos(7 * theta)
    mask = (np.hypot(dx, dy) <= edge) & ndimage.binary_erosion(alpha >= 128, iterations=7)
    coverage = Image.fromarray(mask.astype("uint8") * 255)
    coverage = coverage.filter(ImageFilter.GaussianBlur(.85))
    dyed = texture.resize(size, Image.Resampling.BICUBIC).copy()
    dyed.putalpha(coverage)
    return dyed


def body_textures():
    with Image.open(REPORT / "sample/paper.png") as source:
        paper = source.convert("RGBA")
    source_pivots = read_json(REPORT / "sample/sample.json")["pivots"]
    texture = np.asarray(ink_texture())
    opaque = texture[..., 3] >= 128
    nearest = ndimage.distance_transform_edt(~opaque, return_distances=False, return_indices=True)
    dyed = Image.fromarray(texture[nearest[0], nearest[1], :3]).convert("RGBA")
    dyed = grade(dyed, .60, .65)
    rows = []
    for index, display_size in enumerate(BODY_SIZES):
        size = tuple(round(dimension / SCALE) for dimension in display_size)
        segment = limit_luminance(grade(paper.resize(size, Image.Resampling.LANCZOS),
                                        1 - .07 * index / 7, 1 - .035 * index / 7))
        alpha = segment.getchannel("A")
        ink = ink_cloud(size, index, np.asarray(alpha), dyed)
        ink_alpha = ink.getchannel("A")
        mask = np.asarray(ink_alpha) >= 128
        if (mask & (np.asarray(alpha) < 128)).any():
            raise ValueError("Ink extends beyond visible paper")
        locked = grade(segment, .64, .72)
        locked.alpha_composite(grade(ink, .18, 2.10))
        hit = Image.fromarray(mask.astype("uint8") * 255)
        radius, _ = effective_radius(np.asarray(hit.resize(display_size, Image.Resampling.LANCZOS)) >= 128)
        if radius < MIN_RADIUS:
            raise ValueError(f"Body {index + 1} effective radius {radius:.2f} is below {MIN_RADIUS}")
        center_y, center_x = np.unravel_index(ndimage.distance_transform_edt(mask).argmax(), mask.shape)
        textures = {"paper": segment, "locked": locked, "ink": ink,
                    "glow": glow(ink_alpha, (242, 169, 82), 16),
                    "purified": glow(alpha, (242, 164, 85), 14), "hit_mask": hit}
        identifier = f"body_{index + 1:02d}"
        files = save_parts(identifier, textures)
        pivots = [[pin[axis] * size[axis] / paper.size[axis] for axis in range(2)] for pin in source_pivots]
        rows.append({"id": identifier, "parent": rows[-1]["id"] if rows else "head",
                     "pivots": pivots, "textures": files, "aim": [int(center_x), int(center_y)],
                     "effective_radius": radius})
    return rows


def save_parts(identifier, textures):
    files = {}
    for name, image in textures.items():
        file = PARTS / f"{identifier}_{name}.png"
        image.save(file)
        files[name] = file.relative_to(REPORT).as_posix()
    return files


def cut_piece(sheet, box, display_size, pins):
    image = sheet.crop(box).convert("RGBA")
    # Reject translucent generation haze while retaining the edge ramp.
    image.putalpha(image.getchannel("A").point(lambda a: min(255, max(0, round((a - 190) * 255 / 57)))))
    cropped, crop = alpha_crop(image, threshold=32, pad=8)
    size = tuple(round(value / SCALE) for value in display_size)
    mapped = [[(pin[axis] - box[axis] - crop[axis]) * size[axis] / cropped.size[axis]
               for axis in range(2)] for pin in pins]
    return limit_luminance(cropped.resize(size, Image.Resampling.LANCZOS)), mapped


def extremities():
    with Image.open(REPORT / "source/head.png") as sheet:
        upper, (neck, hinge, mouth_anchor) = cut_piece(
            sheet, (0, 0, sheet.width, 620), (253, 138), [(1260, 498), (991, 498), (550, 648)])
        lower, (jaw_pin,) = cut_piece(sheet, (0, 620, sheet.width, sheet.height),
                                     (160, 66), [(1042, 788)])
    with Image.open(REPORT / "source/tail.png") as sheet:
        tail, (tail_pin,) = cut_piece(sheet, (0, 0, sheet.width, sheet.height), (164, 76), [(95, 659)])
    files = save_parts("head", {"upper": upper, "lower": lower})
    head = {"id": "head", "upper_jaw": files["upper"], "lower_jaw": files["lower"],
            "neck_pivot": neck, "hinge": hinge, "jaw_pivot": jaw_pin, "open_degrees": 41}
    tail_files = save_parts("tail", {"paper": tail})
    tail = {"id": "tail", "parent": "body_08", "file": tail_files["paper"], "pivot": tail_pin}
    mouth = {"id": "mouth", "parent": "head", "anchor": mouth_anchor, "center": [100, 100],
             "interior_center": [122, 122]}
    y, x = np.ogrid[:200, :200]
    dx, dy = (x - 100) / 92, (y - 100) / 92
    theta = np.arctan2(dy, dx)
    radius = np.hypot(dx, dy)
    edge = 1 + .027 * np.cos(7 * theta) + .020 * np.sin(5 * theta)
    visible = radius <= edge
    mask = Image.fromarray(visible.astype("uint8") * 255)
    fibers = np.asarray(upper.convert("L").crop((200, 60, 400, 260)), dtype=float) / 255
    ring = np.exp(-((radius - .80) / .065) ** 2)
    warm = (fibers - .50) * 21 + ring * 46 + (1 - np.minimum(radius, 1)) * 23
    color = np.clip(np.array([182, 49, 45]) + warm[..., None] * [.95, .70, .43], 0, 255)
    core = Image.fromarray(color.astype("uint8")).convert("RGBA")
    core.putalpha(mask.filter(ImageFilter.GaussianBlur(.80)))
    mask = core.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    iy, ix = np.ogrid[:244, :244]
    interior_radius = ((ix - 133) / 112) ** 2 + ((iy - 118) / 106) ** 2
    interior_mask = Image.fromarray((interior_radius < 1).astype("uint8") * 255)
    interior = glow(interior_mask, (30, 17, 30), 1.2)
    mouth_files = save_parts("mouth", {"core": core, "hit_mask": mask, "interior": interior,
                                     "glow": glow(mask, (236, 101, 63), 14)})
    mouth.update(mouth_files)
    return head, tail, mouth


def attach(anchor, angle, pivot, scale=SCALE):
    c, s = math.cos(angle), math.sin(angle)
    matrix = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return translation(*anchor) @ matrix @ np.diag([scale, scale, 1]) @ translation(-pivot[0], -pivot[1])


def position(matrix, point):
    return (matrix @ [*point, 1])[:2]


def poses(pack, clock):
    anchor = (ORIGIN[0] + SWAY[0] * math.sin(clock * 1.3), ORIGIN[1] + SWAY[1] * math.sin(clock * 1.9))
    body = []
    for index, row in enumerate(pack["body_nodes"]):
        angle = math.radians(14 * math.sin(clock * 2.3 - index * 1.16))
        left, right = row["pivots"]
        matrix = attach(anchor, angle, left)
        body.append(matrix)
        anchor = position(matrix, right)
    return body


def angle_of(matrix):
    return math.atan2(matrix[1, 0], matrix[0, 0])


def extra_poses(pack, body, clock, open_mouth):
    head = pack["head"]
    tail = pack["tail"]
    first = pack["body_nodes"][0]["pivots"][0]
    last = pack["body_nodes"][-1]["pivots"][1]
    head_angle = angle_of(body[0])
    upper = attach(position(body[0], first), head_angle, head["neck_pivot"])
    jaw_angle = head_angle - math.radians(head["open_degrees"] if open_mouth else 12 + 4 * math.sin(clock * 4))
    lower = attach(position(upper, head["hinge"]), jaw_angle, head["jaw_pivot"])
    tail_angle = angle_of(body[-1]) + math.radians(9 * math.sin(clock * 3 - 2))
    tail_pose = attach(position(body[-1], last), tail_angle, tail["pivot"])
    mouth = pack["mouth"]
    core = attach(position(upper, mouth["anchor"]), head_angle, mouth["center"])
    return upper, lower, tail_pose, core


def load_texture(path):
    with Image.open(REPORT / path) as image:
        return image.convert("RGBA" if image.mode != "L" else "L")


def stage_frame(pack, textures, background, clock, cleared, overlay=False):
    scene = background.copy()
    body = poses(pack, clock)
    mouth_open = cleared == len(ORDER)
    upper, lower, tail, core = extra_poses(pack, body, clock, mouth_open)
    scene.alpha_composite(transform(textures["tail"], tail, COMPOSITION_SIZE))
    active = ORDER[cleared] if cleared < len(ORDER) else None
    hit = None
    for index in ORDER:
        state = ORDER.index(index)
        part = textures["body"][index]
        matrix = body[index]
        if state < cleared:
            piece = fade_layer(part["purified"], .29)
            piece.alpha_composite(part["paper"])
        elif index == active:
            piece = part["paper"].copy()
            piece.alpha_composite(fade_layer(part["glow"], .68 + .20 * math.sin(clock * 8)))
            piece.alpha_composite(part["ink"])
            hit = transform(part["hit_mask"], matrix, COMPOSITION_SIZE)
        else:
            piece = part["locked"]
        scene.alpha_composite(transform(piece, matrix, COMPOSITION_SIZE))
    if mouth_open:
        delta = np.subtract(pack["mouth"]["center"], pack["mouth"]["interior_center"])
        scene.alpha_composite(transform(textures["mouth_interior"], core @ translation(*delta), COMPOSITION_SIZE))
        scene.alpha_composite(transform(fade_layer(textures["mouth_glow"], .65), core, COMPOSITION_SIZE))
        scene.alpha_composite(transform(textures["mouth"], core, COMPOSITION_SIZE))
        hit = transform(textures["mouth_hit"], core, COMPOSITION_SIZE)
    for key, matrix in (("lower", lower), ("upper", upper)):
        jaw = transform(textures[key], matrix, COMPOSITION_SIZE)
        scene.alpha_composite(jaw)
        if mouth_open:
            hit.paste(0, (0, 0), jaw.getchannel("A").point(lambda value: 255 if value >= 128 else 0))
    if overlay and hit is not None:
        visible = np.asarray(hit) >= 128
        edge = visible & ~ndimage.binary_erosion(visible, iterations=3)
        line = Image.new("RGBA", scene.size, (247, 213, 113, 0))
        line.putalpha(Image.fromarray(edge.astype("uint8") * 245))
        scene.alpha_composite(line)
        caption = "MOUTH" if mouth_open else f"BODY {active + 1:02d}"
        ImageDraw.Draw(scene).text((26, 25), caption, fill="#e8bd81")
    return limit_luminance(scene).convert("RGB"), hit


def textures_for(pack):
    head, tail, mouth = (pack[key] for key in ("head", "tail", "mouth"))
    return {"body": [{key: load_texture(file) for key, file in row["textures"].items()}
                     for row in pack["body_nodes"]],
            "upper": load_texture(head["upper_jaw"]), "lower": load_texture(head["lower_jaw"]),
            "tail": load_texture(tail["file"]), "mouth": load_texture(mouth["core"]),
            "mouth_glow": load_texture(mouth["glow"]), "mouth_hit": load_texture(mouth["hit_mask"]),
            "mouth_interior": load_texture(mouth["interior"])}


def check_geometry(pack, textures):
    safe = (60, 60, COMPOSITION_SIZE[0] - 60, COMPOSITION_SIZE[1] - 60)
    minima = {row["id"]: math.inf for row in pack["body_nodes"]}
    minima["mouth"] = math.inf
    maximum_gap = 0.0
    contrasts = {}
    for row, part in zip(pack["body_nodes"], textures["body"]):
        visible = np.asarray(part["hit_mask"]) >= 128
        before = yprime(np.asarray(part["paper"]))
        after = yprime(np.asarray(part["ink"]))
        contrasts[row["id"]] = float(np.median(np.abs(before[visible] - after[visible])))
    core = textures["mouth"]
    visible = np.asarray(textures["mouth_hit"]) >= 128
    contrasts["mouth"] = float(np.median(yprime(np.asarray(core))[visible])
                               - yprime(np.array([[[30, 17, 30]]], dtype="uint8"))[0, 0])
    if min(contrasts.values()) < .2:
        raise ValueError("A target has insufficient contrast against its backing paper")
    frames = 90
    for frame in range(frames):
        clock = frame / 15
        body = poses(pack, clock)
        upper, lower, _, core = extra_poses(pack, body, clock, True)
        targets = [(row["id"], part["hit_mask"], matrix)
                   for row, part, matrix in zip(pack["body_nodes"], textures["body"], body)]
        targets.append(("mouth", textures["mouth_hit"], core))
        for index, (row, following) in enumerate(zip(pack["body_nodes"], pack["body_nodes"][1:])):
            maximum_gap = max(maximum_gap, float(np.linalg.norm(
                position(body[index], row["pivots"][1]) - position(body[index + 1], following["pivots"][0]))))
        for target, mask, matrix in targets:
            left, top, right, bottom = mask.getbbox()
            xy = np.array([position(matrix, xy) for xy in ((left, top), (left, bottom), (right, top), (right, bottom))])
            x, y = np.floor(xy.min(axis=0)).astype(int)
            r, b = np.ceil(xy.max(axis=0)).astype(int)
            if x < safe[0] or y < safe[1] or r > safe[2] or b > safe[3] or y < 152 or b > 776:
                raise ValueError(f"{target} enters a HUD or edge reservation at {clock:.2f}s")
            size = (int(r - x), int(b - y))
            shift = translation(-int(x), -int(y))
            visible = np.asarray(transform(mask, shift @ matrix, size)) >= 128
            if target == "mouth":
                for key, jaw in (("upper", upper), ("lower", lower)):
                    cover = transform(textures[key].getchannel("A"), shift @ jaw, size)
                    visible &= np.asarray(cover) < 128
            radius, _ = effective_radius(visible)
            minima[target] = min(minima[target], radius)
    for target, radius in minima.items():
        if radius < MIN_RADIUS:
            raise ValueError(f"{target} motion minimum effective radius {radius:.2f} is below {MIN_RADIUS}")
    return {"frames": frames, "min_radius_px": minima, "max_joint_gap_px": maximum_gap,
            "median_luminance_contrast_against_backing_paper": contrasts,
            "edge_band_px": 60, "maximum_active": 1}


def main():
    PARTS.mkdir(parents=True, exist_ok=True)
    body = body_textures()
    head, tail, mouth = extremities()
    pack = {"id": "ink_dragon", "status": "full_art_candidate", "background": "../T10/compositions/square_02.png",
            "content_size": COMPOSITION_SIZE, "body_scale": SCALE, "origin": ORIGIN, "sway": SWAY,
            "body_nodes": body, "head": head, "tail": tail, "mouth": mouth,
            "opening_order": [body[index]["id"] for index in ORDER], "max_active": 1}
    textures = textures_for(pack)
    checks = check_geometry(pack, textures)
    write_json(REPORT / "boss.json", pack)
    write_json(PACK / "checks.json", checks)
    generation = read_json(REPORT / "source/full_generation.json")
    for row in generation:
        with Image.open(REPORT / row["output"]) as original:
            row["size"] = list(original.size)
        row["sha256"] = digest(REPORT / row["output"])
    write_json(PACK / "generation.json", generation)
    background = ImageOps.fit(composition_image("square"), COMPOSITION_SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    for tag, clock, cleared, marked in (("swim", .8, 2, False), ("hit_zone", .8, 2, True),
                                       ("mouth", 4.8, 8, False), ("purified", 5.6, 9, False)):
        frame, _ = stage_frame(pack, textures, background, clock, cleared, marked)
        save_jpg(frame, PACK / f"{tag}.jpg")
    video = []
    for tick in range(96):
        frame, _ = stage_frame(pack, textures, background, tick / 15, min(tick // 10, 9), overlay=True)
        video.append(frame.resize((1280, 674), Image.Resampling.LANCZOS))
    movie(video, PACK / "swim_hit_zones.mp4", fps=15)
    print(checks)


if __name__ == "__main__":
    main()
