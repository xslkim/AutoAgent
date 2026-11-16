"""Measure C04 color coverage for the locked three-chapter candidate."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.color import deltaE_ciede2000, rgb2lab

from artlib import GAME, digest, write_json
from paper_ops import palette
from t10_assets import cinnabar

DELTA_E_LIMIT = 15
NEAR_STAMP_DELTA_E = 10
PALETTE_LIMIT = .90
STAMP_RGB = (200, 50, 44)
STAMP_LAB = rgb2lab(np.array([STAMP_RGB]) / 255)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def matched_path(stage, item):
    path = (stage / item["path"]).resolve()
    if not path.is_relative_to(stage) or digest(path) != item["sha256"]:
        raise ValueError(f"Stage file checksum mismatch: {item['path']}")
    return path


def exclusions(stage, level):
    art = level["presentation"]
    lighting, stamps = defaultdict(set), defaultdict(set)
    ordinary_draws = set()
    dedicated_stamps, other_uses = set(), set()
    weak_entities = {action["entity"] for event in level["events"].values()
                     for action in event["actions"].values()
                     if action["op"] == "permission" and action["kind"] == "weak"}

    for name, layer in art["layers"].items():
        resource = layer["resource"]
        if layer["z"] == art["additive_z"] or name.endswith(".ending.halo"):
            lighting[resource].add(f"layer:{name}")
        else:
            ordinary_draws.add(resource)
        other_uses.add(resource)

    for name, entity in level["entities"].items():
        if entity.get("properties", {}).get("virtual", False):
            continue
        parts = entity.get("parts")
        if parts:
            for index, part_id in enumerate(entity["part_order"]):
                part = parts[part_id]
                resources = [part["resource"]]
                if "hardened_visual" in part:
                    resources.append(part["hardened_visual"]["resource"])
                for resource in resources:
                    if index == 0 and int(entity["properties"].get("z", 0)) == art["additive_z"]:
                        lighting[resource].add(f"part:{name}/{part_id}")
                    else:
                        ordinary_draws.add(resource)
                    if part.get("kind") == "weak":
                        stamps[resource].add(f"weak_part:{name}/{part_id}")
                    if part.get("kind") == "weak" and part_id in {"stamp", "seal"} and resource == part["resource"]:
                        dedicated_stamps.add(resource)
                    else:
                        other_uses.add(resource)
            continue
        if "resource" not in entity:
            continue
        resource = entity["resource"]
        z = int(entity.get("properties", {}).get("z", 0))
        projector_beam = name.startswith("cinema.projector") and name.endswith((".dark", ".warm"))
        if z == art["additive_z"] or projector_beam or name == "lantern_base.ending.halo":
            lighting[resource].add(f"entity:{name}")
        else:
            ordinary_draws.add(resource)
        if name in weak_entities or name == "cinema.shadow_core":
            stamps[resource].add(f"weak_entity:{name}")
        if name == "cinema.shadow_core":
            dedicated_stamps.add(resource)
        else:
            other_uses.add(resource)

    dragon = art["dragon"]
    layout = read(matched_path(stage, level["resources"][dragon["layout"]]))
    mouth = layout["mouth"]
    mouth_core = dragon["images"][mouth["core"]]
    stamps[mouth_core].add("dragon:mouth.core")
    dedicated_stamps.add(mouth_core)
    other_uses.update(resource for path, resource in dragon["images"].items() if path != mouth["core"])
    lighting[dragon["images"][mouth["glow"]]].add("dragon:mouth.glow")
    for node in layout["body_nodes"]:
        lighting[dragon["images"][node["textures"]["glow"]]].add(f"dragon:{node['id']}.glow")
    score = art["hud_art"]["images"]["score_seal"]
    stamps[score].add("hud:score_seal")
    dedicated_stamps.add(score)
    binding = art["hud_art"]["lettering"]
    lettering = {binding["title"], binding["first_chapter"], *binding["chapters"].values()}
    ordinary_draws.update(lettering)
    ordinary_draws.update(art["hud_art"]["images"].values())
    ordinary_draws.update(row["atlas"] for row in art["puppets"].values())
    other_uses.update(lettering)
    other_uses.update(resource for key, resource in art["hud_art"]["images"].items() if key != "score_seal")
    other_uses.update(row["atlas"] for row in art["puppets"].values())
    return lighting, stamps, lettering, ordinary_draws, dedicated_stamps - other_uses


def matte_opacity(pixels):
    # Mirrors the color-key alpha in framework/core/lettering_matte.gdshader.
    r, g, b = np.moveaxis(pixels[..., :3] / 255, -1, 0)
    warm = np.clip((r - b - .035) / (.15 - .035), 0, 1)
    indigo = np.clip((b - np.maximum(r, g) - .025) / (.09 - .025), 0, 1)
    return np.maximum(warm * warm * (3 - 2 * warm), indigo * indigo * (3 - 2 * indigo) * .92)


def stamp_distances(pixels):
    candidates = cinnabar(pixels)
    reds = pixels[candidates, :3] / 255
    return candidates, deltaE_ciede2000(rgb2lab(reds), STAMP_LAB)


def red_pixels(pixels):
    candidates, distances = stamp_distances(pixels)
    candidates[candidates] = distances <= DELTA_E_LIMIT
    return candidates


def measure(pixels, swatches, permitted_red=False, lettering=False):
    alpha = pixels[..., 3] / 255
    if lettering:
        alpha *= matte_opacity(pixels)
    visible = alpha >= .5
    red = red_pixels(pixels) & visible
    ordinary = visible & ~red if permitted_red else visible
    selected = pixels[ordinary, :3].astype(np.uint32)
    weight = alpha[ordinary]
    packed = (selected[:, 0] << 16) | (selected[:, 1] << 8) | selected[:, 2]
    unique, index = np.unique(packed, return_inverse=True)
    total = float(weight.sum())
    coverage = None
    largest_misses = []
    if total:
        rgb = np.column_stack((unique >> 16, (unique >> 8) & 255, unique & 255))
        lab = rgb2lab(rgb / 255)
        distance = np.min([deltaE_ciede2000(lab, value[None, :]) for value in swatches], axis=0)
        weights = np.bincount(index, weights=weight)
        accepted = distance <= DELTA_E_LIMIT
        coverage = float(weights[accepted].sum() / total)
        misses = np.flatnonzero(~accepted)
        priority = misses[np.argsort(-weights[misses], kind="stable")[:5]]
        largest_misses = [{"hex": f"#{int(unique[i]):06X}", "pixels_alpha_weighted": round(weights[i], 4),
                           "nearest_delta_e00": round(float(distance[i]), 4)} for i in priority]
    return {
        "status": "na" if coverage is None else ("pass" if coverage >= PALETTE_LIMIT else "fail"),
        "coverage": coverage, "visible_pixels": int(visible.sum()), "eligible_pixels_alpha_weighted": total,
        "cinnabar_pixels": int(red.sum()), "cinnabar_pixels_alpha_weighted": float(alpha[red].sum()),
        "cinnabar_fraction_visible": float(alpha[red].sum() / max(1., alpha[visible].sum())),
        "largest_out_of_palette_colors": largest_misses,
    }


def image_pixels(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def frame_colors(pixels):
    if pixels.shape != (936, 1776, 4):
        raise ValueError("Expected a 1776 by 936 game viewport")
    candidates, distances = stamp_distances(pixels)
    near = candidates.copy()
    near[near] = distances <= NEAR_STAMP_DELTA_E
    count = int(np.count_nonzero(distances <= DELTA_E_LIMIT))
    near_count = int(near.sum())
    return {"near_cinnabar_pixels_delta_e15": count, "fraction_delta_e15": count / near.size,
            "near_cinnabar_pixels_delta_e10": near_count, "fraction_delta_e10": near_count / near.size}, near


def collect_assets(stage, manifest, coverage, level):
    swatches = rgb2lab(np.asarray(palette(include_ink=True)) / 255)
    roles = {row["id"]: row["roles"] for row in coverage["resources"] if row["kind"] == "image"}
    lighting, stamps, lettering, ordinary_draws, dedicated_stamps = exclusions(stage, level)
    rows, measured = {}, {}
    for source in manifest["resources"]:
        if source["kind"] != "image":
            continue
        resource = source["id"]
        path = matched_path(stage, source)
        reasons = sorted(lighting[resource])
        permit = sorted(stamps[resource])
        item = {"path": source["path"], "sha256": source["sha256"], "bindings": source["level_field_matches"],
                "source_evidence": source.get("source_evidence"), "roles": roles[resource],
                "light_bindings": reasons, "cinnabar_bindings": permit, "lettering_matte": resource in lettering}
        if "color" not in roles[resource]:
            item.update(status="na", reason="Dedicated hit or scalar raster")
        elif reasons and resource not in ordinary_draws:
            item.update(status="na", reason="Dedicated lighting layer")
        elif resource in dedicated_stamps:
            item.update(status="na", reason="Dedicated cinnabar artwork",
                        cinnabar_pixels=int(red_pixels(image_pixels(path)).sum()))
        else:
            key = (source["sha256"], bool(permit), resource in lettering)
            if key not in measured:
                measured[key] = measure(image_pixels(path), swatches, key[1], key[2])
            item.update(measured[key])
            if item["status"] == "na":
                item["reason"] = ("Permitted cinnabar only" if item["cinnabar_pixels"] else "No eligible pixels at alpha 0.5")
            item["cinnabar_review"] = bool(item["cinnabar_pixels"] and not permit)
        rows[resource] = item
    return rows


def collect_frames(captures, gallery, limit):
    frames = {}
    for identifier, row in gallery["frames"].items():
        if not row["capture"].startswith("route/") or not row["source_png_sha256"]:
            continue
        path = captures / f"{row['capture']}.png"
        if digest(path) != row["source_png_sha256"]:
            raise ValueError(f"Godot capture checksum mismatch: {identifier}")
        colors, _ = frame_colors(image_pixels(path))
        frames[identifier] = {"capture": row["capture"], "sha256": row["source_png_sha256"],
                              **colors, "screening_status": "review" if colors["fraction_delta_e15"] > limit
                              else "within_reference"}
    stations = {int(identifier.split("_")[1]) for identifier in frames if identifier.startswith("station_")}
    if stations != set(range(1, 16)):
        raise ValueError("Cinnabar samples must cover all 15 stations")
    return frames


def compare_stamps(route, frames, preview):
    variants = sorted(route.glob("*_without_stamps.png"))
    if not variants:
        raise ValueError("Expected same-tick Godot stamp comparisons")
    sample_width, sample_height = 480, 253
    sheet = Image.new("RGB", (3 * sample_width, len(variants) * (sample_height + 30)), "#251f2a")
    labels = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    results = {}
    for index, alternate in enumerate(variants):
        identifier = alternate.stem.removesuffix("_without_stamps")
        original = route / f"{identifier}.png"
        original_sha = digest(original)
        if original_sha != frames[identifier]["sha256"]:
            raise ValueError(f"Stamp probe pose differs from the gallery: {identifier}")
        original_pixels = image_pixels(original)
        hidden_pixels = image_pixels(alternate)
        colors, remaining = frame_colors(hidden_pixels)
        results[identifier] = {
            "original_sha256": original_sha, "without_stamps_sha256": digest(alternate),
            "different_pixels": int(np.count_nonzero(np.any(original_pixels != hidden_pixels, axis=2))),
            "original_fraction_delta_e10": frames[identifier]["fraction_delta_e10"],
            "without_stamps": colors,
        }
        highlight = hidden_pixels[..., :3].copy()
        highlight[remaining] = (66, 244, 240)
        panels = (Image.fromarray(original_pixels), Image.fromarray(hidden_pixels), Image.fromarray(highlight))
        top = index * (sample_height + 30)
        labels.text((12, top + 5), identifier, font=font, fill="#faf0dd")
        for column, panel in enumerate(panels):
            sheet.paste(panel.convert("RGB").resize((sample_width, sample_height), Image.Resampling.LANCZOS),
                        (column * sample_width, top + 30))
    if preview:
        sheet.save(preview, quality=91, optimize=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "manifest", "coverage", "captures", "gallery", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--stamps-probe", type=Path)
    parser.add_argument("--stamps-preview", type=Path)
    args = parser.parse_args()
    stage = args.stage.resolve()
    manifest = read(args.manifest)
    coverage = read(args.coverage)
    gallery = read(args.gallery)
    level_path = stage / "level.json"
    compiled = read(level_path)
    if (manifest["package"] != "paper.lantern_city_cast"
            or len({manifest["build_id"], coverage["build_id"], compiled["build_id"], gallery["build_id"]}) != 1
            or digest(level_path) != manifest["compiled_sha256"]
            or digest(args.manifest) != coverage["candidate_manifest_sha256"]):
        raise ValueError("Compiled build, inventory, coverage and Godot captures must match")
    limit = read(GAME / "bible/palette.json")["cinnabar_max_fraction"]
    assets = collect_assets(stage, manifest, coverage, compiled["level"])
    frames = collect_frames(args.captures, gallery, limit)
    summary = {"asset_coverage": dict(Counter(row["status"] for row in assets.values())),
               "excluded_assets": dict(Counter(row["reason"] for row in assets.values() if row["status"] == "na")),
               "cinnabar_source_review": sum(row.get("cinnabar_review", False) for row in assets.values()),
               "rendered_frames": dict(Counter(row["screening_status"] for row in frames.values())),
               "frames_over_reference_delta_e10": sum(row["fraction_delta_e10"] > limit for row in frames.values())}
    comparisons = compare_stamps(args.stamps_probe, frames, args.stamps_preview) if args.stamps_probe else {}
    write_json(args.output, {"build_id": manifest["build_id"], "manifest_sha256": digest(args.manifest),
                             "gallery_sha256": digest(args.gallery), "palette_sha256": digest(GAME / "bible/palette.json"),
                             "checker_sha256": digest(Path(__file__)), "colors_rgb": palette(include_ink=True),
                             "thresholds": {"alpha": .5, "delta_e00": DELTA_E_LIMIT,
                                            "near_cinnabar_delta_e00": NEAR_STAMP_DELTA_E,
                                            "palette_coverage": PALETTE_LIMIT, "cinnabar_area": limit},
                             "summary": summary, "assets": assets, "frames": frames,
                             "stamp_visibility_probe": comparisons})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
