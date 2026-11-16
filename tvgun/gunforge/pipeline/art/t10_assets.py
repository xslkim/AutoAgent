"""Normalize and screen T10 generated props, effects, and civilian components."""
import json

import numpy as np
import yaml
from PIL import Image, ImageEnhance
from scipy import ndimage as ndi
from skimage.restoration import inpaint_biharmonic

from artlib import GAME, digest, encode_sdf, write_json, yprime
from checks import run
from paper_ops import alpha_crop, component_map, isolated_component, limit_luminance, palette, paper_palette
from preview import pose, transform, translation
from t05_puppets import matrices, pins


REPORT = GAME / "reports/art/T10"
OUTPUT = REPORT / "assets"
ROWS = (
    ("head", "torso"),
    ("upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r"),
    ("thigh_l", "thigh_r", "shin_l", "shin_r"),
)
POSES = {
    "idle": {}, "peek": {"torso": -7},
    "walk": {"thigh_l": 13, "thigh_r": -17, "shin_l": -13, "upper_arm_l": -6, "upper_arm_r": 8},
    "startle": {"upper_arm_l": 28, "upper_arm_r": -28, "head": -9},
    "wave_for_help": {"upper_arm_r": -65, "forearm_r": -65},
    "struggle": {"torso": 7, "upper_arm_l": 23, "upper_arm_r": -21, "forearm_l": 18},
    "rescued_bounce": {"thigh_l": 10, "thigh_r": -10, "shin_l": -13, "shin_r": 13},
    "thank": {"head": 10, "forearm_l": 26, "forearm_r": -26},
}
PAPER_TINTS = {
    "bicycle": "2A1E3D", "shopping_basket": "D9A066", "lantern_off": "C97B84",
    "neon_off": "D9A066", "coin": "D9A066", "paper_fx_01": "D9A066",
    "paper_fx_02": "C97B84", "paper_fx_03": "4E9A92", "paper_fx_04": "D9A066",
}


def ledger():
    rows = []
    paths = [*REPORT.glob("asset_round_*.json"), REPORT / "asset_residents.json"]
    refinement = REPORT / "refinement_sources.json"
    for path in sorted(paths):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    if refinement.exists():
        rows.extend(row for row in json.loads(refinement.read_text(encoding="utf-8"))
                    if row["category"] in {"prop", "fx"})
    latest = {}
    for row in rows:
        previous = latest.get(row["id"])
        if not previous or row["status"] == "generated" and row["attempt"] >= previous["attempt"]:
            latest[row["id"]] = row
    # Keep the prop-first display order used by the review sheet.
    return sorted(latest.values(), key=lambda row: row["category"] != "prop")


def screen(file, folder, include_ink=False):
    with Image.open(file) as image:
        sample = image.copy()
    sample.thumbnail((320, 320))
    path = folder / f"{file.stem}_screen.png"
    sample.save(path)
    return {
        "C01": run("C01", {"file": file, "kind": "color"}),
        "C03": run("C03", {"file": file}),
        "C04": run("C04", {"file": path, "palette_rgb": palette(include_ink=include_ink)}),
        "C14": run("C14", {}),
    }


def cinnabar(pixels):
    r, g, b = pixels[..., :3].astype(float).transpose(2, 0, 1)
    return (pixels[..., 3] >= 128) & (r > 100) & (r > g * 1.65) & (r > b * 1.38)


def grade_texture(image, asset_id, category):
    pixels = np.array(image)
    rgb = pixels[..., :3].astype(float)
    luma = yprime(pixels) * 255
    if category == "enemy":
        stamp = cinnabar(pixels)
        # Preserve the warm wood and paper beneath the dark ink.
        warm = np.clip((rgb[..., 0] - rgb[..., 2] - 12) / 32, 0, 1)
        if asset_id == "ink_drop":
            warm.fill(0)
        ink = np.array([13, 13, 18]) + np.clip(luma * .39, 0, 20)[..., None]
        prop = np.array([217, 160, 102]) + np.clip((luma - 155) * .52, -27, 25)[..., None]
        adjusted = ink * (1 - warm[..., None]) + prop * warm[..., None]
        pixels[..., :3] = np.where(stamp[..., None], rgb, np.rint(adjusted)).astype("uint8")
    elif asset_id.startswith("ink_fx_"):
        ink = np.array([11, 11, 14]) + np.clip(luma * .30, 0, 41)[..., None]
        pixels[..., :3] = np.rint(ink).astype("uint8")
    else:
        swatch = np.array(tuple(bytes.fromhex(PAPER_TINTS[asset_id])))
        mid = np.median(luma[pixels[..., 3] >= 128])
        if asset_id == "coin":
            # The rim and stamped texture stay in the same brass color family.
            tone = np.clip((luma - mid) * .73, -38, 30)
        else:
            tone = np.clip((luma - mid) * .73, -64, 55)
        # Preserve source texture and local contrast with a continuous tonal curve.
        target = swatch + tone[..., None]
        strength = {"lantern_off": .39, "coin": .86}.get(asset_id, .60)
        pixels[..., :3] = np.rint(rgb * (1 - strength) + target * strength).clip(0, 255).astype("uint8")
    result = Image.fromarray(pixels)
    if asset_id in PAPER_TINTS:
        result = paper_palette(result, delta_e=8)
    return result


def process_texture(source, folder, category, asset_id):
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
    transparent, solid = rgba.getchannel("A").getextrema()
    if transparent > 15 or solid < 240:
        raise ValueError("missing useful alpha")
    image, box = alpha_crop(rgba, pad=8)
    file = folder / "texture.png"
    image.thumbnail((496, 496) if category == "fx" else (1024, 1024), Image.Resampling.LANCZOS)
    image = grade_texture(image, asset_id, category)
    if category == "fx":
        texture = Image.new("RGBA", (512, 512))
        texture.paste(image, ((512 - image.width) // 2, (512 - image.height) // 2))
        image = texture
    limit_luminance(image).save(file)
    checks = {} if category == "enemy" else screen(file, folder, include_ink=category == "fx")
    if category not in {"enemy", "fx"}:
        checks["C05"] = run("C05", {"file": file, "expected_text": ""})
    return {"texture": file.name, "crop_box": box, "source_size": list(rgba.size),
            "checks": checks,
            "palette_correction": "texture-preserving paper and ink grades",
            "scope": "body/core and hit zone annotation pending" if category == "enemy" else "offline texture candidate"}


def prepare_enemy(source, folder, evidence):
    with Image.open(folder / evidence["texture"]) as image:
        original = np.asarray(image.convert("RGBA")).copy()
    height, width = original.shape[:2]
    r, g, b = original[..., :3].astype(float).transpose(2, 0, 1)
    visible = original[..., 3] >= 128
    red = cinnabar(original)
    labels, _ = ndi.label(red)
    sizes = np.bincount(labels.ravel())
    if len(sizes) < 2 or sizes[1:].max() < 20:
        raise ValueError("no identifiable cinnabar region")
    stamp = labels == (1 + sizes[1:].argmax())
    yy = np.arange(height)[:, None]
    ink_zone = (yy < height * .58) if source.stem in {"ink_cart", "ink_sign"} else (yy > height * .4)
    dark_ink = visible & ink_zone & (b >= r * .9) & (b >= g * .92) & (r < 100)
    mark_neighborhood = ndi.binary_dilation(stamp, iterations=3) & visible
    labels, _ = ndi.label(dark_ink | mark_neighborhood)
    containing = np.unique(labels[stamp])
    if len(containing) != 1 or not containing[0]:
        raise ValueError("stamp is disconnected from the ink mask")
    hit = (labels == containing[0]) & visible
    if not (dark_ink & hit).any():
        raise ValueError("stamp does not touch a dark ink region")
    body = original.copy()
    # Reconstruct the ink beneath the stamp with a local solve instead of
    # streaking the nearest edge pixels across the rectangular mark.
    ys, xs = np.nonzero(stamp)
    pad = max(6, round((xs.max() - xs.min() + 1) * .12))
    crop = np.s_[max(0, ys.min() - 2 * pad):ys.max() + 2 * pad + 1,
                 max(0, xs.min() - 2 * pad):xs.max() + 2 * pad + 1]
    area = ndi.binary_dilation(stamp[crop], iterations=pad)
    base = body[crop][..., :3]
    clean = dark_ink[crop] & ~area
    if not clean.any():
        raise ValueError("no clean ink next to cinnabar")
    indices = ndi.distance_transform_edt(~clean, return_distances=False, return_indices=True)
    boundary = base[indices[0], indices[1]]
    fixed = inpaint_biharmonic(boundary, area, channel_axis=-1)
    base[area] = np.rint(fixed[area] * 255).astype("uint8")
    core = original.copy()
    core[~stamp, 3] = 0
    body_image = paper_palette(Image.fromarray(body), include_ink=True, delta_e=8)
    core_image = Image.fromarray(core)
    body_image.save(folder / "body.png")
    core_image.save(folder / "core.png")
    vulnerable = body_image.copy()
    vulnerable.alpha_composite(core_image)
    vulnerable.save(folder / evidence["texture"])
    Image.fromarray((hit * 255).astype("uint8")).save(folder / "hit.png")
    Image.fromarray((stamp * 255).astype("uint8")).save(folder / "core_mask.png")
    Image.fromarray(encode_sdf(hit)).save(folder / "sdf.png")
    distances = ndi.distance_transform_edt(hit)
    cy, cx = np.unravel_index(distances.argmax(), distances.shape)
    radius = float(distances[cy, cx])
    eye_source = GAME / "assets/stations/g01_st_l1_01_alley/crow/core_hardened.png"
    with Image.open(eye_source) as original_eye:
        eye = alpha_crop(original_eye, pad=0)[0]
    eye.thumbnail((max(2, round(radius * 1.35)), max(2, round(radius * .45))),
                  Image.Resampling.LANCZOS)
    hard_core = Image.new("RGBA", (width, height))
    hard_core.alpha_composite(eye, (cx - eye.width // 2, cy - eye.height // 2))
    contained = not ((np.asarray(hard_core.getchannel("A")) >= 128) & ~hit).any()
    hard_core.save(folder / "core_hardened.png")
    hardened = ImageEnhance.Color(body_image).enhance(.17)
    hardened.alpha_composite(hard_core)
    hardened.save(folder / "hardened_preview.png")
    checks = screen(folder / evidence["texture"], folder, include_ink=True)
    checks.update({
        "C04": screen(folder / "body.png", folder, include_ink=True)["C04"],
        "C05": run("C05", {"file": folder / evidence["texture"], "expected_text": ""}),
        "C11": run("C11", {"body": folder / "hit.png", "core": folder / "core_mask.png"}),
        "C16": run("C16", {"alpha": folder / "hit.png", "sdf": folder / "sdf.png", "source_color": False}),
        "static_hardened_containment": {"status": "pass" if contained else "fail"},
    })
    evidence["checks"] = checks
    evidence["scope"] = "separate ink/stamp/hardened layers and provisional geometry; animation and runtime pending"
    write_json(folder / "enemy.json", {
        "id": source.stem, "human": False, "status": "offline_candidate", "canvas": [width, height],
        "body": "body.png", "core": "core.png", "core_hardened": "core_hardened.png",
        "hit_mask": "hit.png", "sdf": "sdf.png", "hardened_eye_source_sha256": digest(eye_source),
        "effective_radius_source_px": radius, "stamp_inside_hit_mask": bool(np.all(hit[stamp])),
        "mask_method": "luminance/chroma segmentation of generated concept; inspect before runtime adoption",
    })
    return evidence


def pair_components(image):
    labels, components = component_map(image)
    if len(components) != 10:
        raise ValueError(f"expected ten isolated pieces, got {len(components)}")
    components.sort(key=lambda component: component["center"][1])
    pieces = {}
    for names, start in zip(ROWS, (0, 2, 6)):
        row = sorted(components[start:start + len(names)], key=lambda component: component["center"][0])
        for name, part in zip(names, row):
            pieces[name] = isolated_component(image, part["label"], labels)
    return pieces


def joint_overlap(puppet, alphas, position, scale, angles):
    transforms = matrices(puppet, position, scale, angles)
    overlaps = {}
    for node in puppet["parts"]:
        name, parent = node["id"], node["parent"]
        if parent is None:
            continue
        x, y, _ = transforms[parent] @ np.array([*node["attach"], 1])
        window = translation(14 - x, 14 - y)
        child_alpha, parent_alpha = (
            np.asarray(transform(alphas[part], window @ transforms[part], (29, 29))) >= 128
            for part in (name, parent)
        )
        overlaps[name] = int(np.count_nonzero(child_alpha & parent_alpha))
    return overlaps


def bind_puppet(parts, folder, source):
    dimensions = {"head": (177, 182), "torso": (255, 278)}
    template = yaml.safe_load((GAME / "bible/rigs/humanoid_10.yaml").read_text(encoding="utf-8"))
    for name, image in parts.items():
        size = dimensions.get(name, (94, 171) if "arm" in name else (113, 180))
        parts[name] = limit_luminance(image.resize(size, Image.Resampling.LANCZOS))
    nodes = []
    for spec in template["parts"]:
        name, parent = spec["id"], spec["parent"]
        image = parts[name]
        w, h = image.size
        nodespec = {"id": name, "parent": parent, "file": f"{name}.png", "rest_deg": 0}
        image.save(folder / nodespec["file"])
        detected = [dot["point"] for dot in pins(image) if dot["point"][1] < h * .25]
        pivot = detected[0] if detected else [w / 2, h * .16]
        attach = None
        z = 0
        if name == "torso":
            pivot, z = [w / 2, 16], 5
        elif name == "head":
            pivot, attach, z = [w * .5, h * .86], [127, 28], 7
        elif name.startswith("upper_arm"):
            attach, z = [50 if name.endswith("_l") else 205, 60], 3
        elif name.startswith("thigh"):
            attach, z = [82 if name.endswith("_l") else 173, 254], 2
        elif parent is not None:
            parent_image = parts[parent]
            attach = [parent_image.width / 2, parent_image.height * .84]
            z = 6 if name.startswith("forearm") else 1
        nodes.append({**nodespec, "pivot": pivot, "attach": attach, "z": z,
                      "angle_range": [-75, 75] if "arm" in name else [-30, 30]})
    puppet = {"id": source.stem.removesuffix("_sheet"), "rig": "humanoid_10", "role": "hostage_or_npc",
              "human_body_attackable": False, "human_attacks_player": False, "parts": nodes,
              "ink_anchor": [127, 118], "status": "offline_candidate", "source_sha256": digest(source),
              "actions": [name for name in POSES if name != "idle"]}
    rest = pose(puppet, folder, (500, 250), 1, {}, (1000, 1000))
    _, top, _, bottom = rest.getchannel("A").getbbox()
    factor = 768 / (bottom - top)
    for node in nodes:
        file = folder / node["file"]
        with Image.open(file) as image:
            normalized = image.resize(tuple(round(value * factor) for value in image.size), Image.Resampling.LANCZOS)
        normalized.save(file)
        for key in ("pivot", "attach"):
            if node[key] is not None:
                node[key] = [value * factor for value in node[key]]
    puppet["ink_anchor"] = [value * factor for value in puppet["ink_anchor"]]
    puppet["assembled_height_target"] = 768
    write_json(folder / "puppet.json", puppet)
    components = {}
    joints = {}
    alphas = {}
    for node in nodes:
        with Image.open(folder / node["file"]) as image:
            alphas[node["id"]] = image.getchannel("A")
    for name, angles in POSES.items():
        frame = pose(puppet, folder, (330, 180), .74, angles, (660, 830))
        frame.save(folder / f"pose_{name}.png")
        labels, _ = ndi.label(np.asarray(frame.getchannel("A")) >= 128)
        components[name] = int((np.bincount(labels.ravel())[1:] >= 500).sum())
        joints[name] = joint_overlap(puppet, alphas, (330, 180), .74, angles)
    connected = all(value == 1 for value in components.values())
    connected &= all(area > 0 for pose_joints in joints.values() for area in pose_joints.values())
    return {"parts": len(nodes), "poses": list(POSES), "major_silhouette_components": components,
            "sampled_joint_overlap_px": joints,
            "checks": {"C10": {"status": "pending" if connected else "fail",
                               "reason": "Sampled joints overlap; check extreme motion and copper tabs in runtime"
                               if connected else "A sampled silhouette or joint is disconnected"}},
            "scope": "preliminary part map and pose samples"}


def main():
    index = []
    for row in ledger():
        if row["status"] != "generated":
            index.append(row)
            continue
        source = REPORT / row["output"]
        folder = OUTPUT / row["id"]
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if row["category"] == "puppet_sheet":
                with Image.open(source) as sheet:
                    parts = pair_components(sheet)
                evidence = bind_puppet(parts, folder, source)
            else:
                evidence = process_texture(source, folder, row["category"], row["id"])
                if row["category"] == "enemy":
                    evidence = prepare_enemy(source, folder, evidence)
            result = {**row, "sha256": digest(source), "cost": None, "status": "prepared", **evidence}
        except ValueError as error:
            result = {**row, "status": "needs_revision", "error": str(error)}
        index.append(result)
    write_json(REPORT / "asset_screen.json", index)
    print([(row["id"], row["status"]) for row in index])


if __name__ == "__main__":
    main()
