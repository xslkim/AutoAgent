"""Prepare C02 black/white composites and measure transparent RGB in the cast build."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from artlib import digest, write_json
from t10_preview import read_json, save_jpg
from t16_asset_coverage import CAST, PACKAGE, verify_build
from cast_edge_fill import adjacent_color_gaps


GROUPS = {
    "blocker": "挡弹前景", "atlas": "纸偶图集", "lettering": "标题与关卡字形",
    "hud": "界面图形", "boss": "Boss 纸层与描边", "actor": "角色、墨怪与可射目标",
    "scene": "场景纸层、灯光和特效",
}
EDGE_RADIUS = 8
DETAIL_SIZE = 96


def staged_resource(stage, declaration):
    path = (stage / declaration["path"]).resolve()
    if not path.is_relative_to(stage.resolve()) or digest(path) != declaration["sha256"]:
        raise ValueError(f"Staged bytes do not match the build: {declaration['path']}")
    return path


def attachment_rectangles(stage, level):
    atlases = {}
    for puppet in level["presentation"]["puppets"].values():
        metadata = read_json(staged_resource(stage, level["resources"][puppet["character"]]))
        rects = {row["part"]: row["rect"] for row in metadata["rig"]["attachments"]}
        previous = atlases.setdefault(puppet["atlas"], rects)
        if previous != rects:
            raise ValueError(f"Atlas has multiple attachment layouts: {puppet['atlas']}")
    return atlases


def edge_metrics(pixels):
    rgb, alpha = pixels[..., :3], pixels[..., 3]
    visible = alpha > 0
    if not visible.any():
        raise ValueError("Empty color attachment")
    x, y, right, bottom = Image.fromarray(alpha).getbbox()
    height, width = alpha.shape
    distance, nearest = ndi.distance_transform_edt(~visible, return_indices=True)
    nearest_rgb = rgb[tuple(nearest)]
    fill_band = (~visible) & (distance <= EDGE_RADIUS)
    empty_rgb = fill_band & (rgb == 0).all(axis=2) & (nearest_rgb != 0).any(axis=2)
    partial = visible & (alpha < 255)
    adjacent_empty = adjacent_color_gaps(pixels)
    # Sample the midpoint between each zero-RGB texel and its visible neighbors.
    # Encoded straight-alpha bilinear color loss is independent of the composite background.
    edge_strength = rgb.max(axis=2).astype(np.uint16) * alpha
    midpoint_loss = max(
        edge_strength[:-1][adjacent_empty[1:]].max(initial=0),
        edge_strength[1:][adjacent_empty[:-1]].max(initial=0),
        edge_strength[:, :-1][adjacent_empty[:, 1:]].max(initial=0),
        edge_strength[:, 1:][adjacent_empty[:, :-1]].max(initial=0),
    ) / 1020
    return {
        "alpha_bbox": [x, y, right, bottom],
        "transparent_outer_margins_ltrb": [x, y, width - right, height - bottom],
        "semitransparent_pixels": int(partial.sum()),
        "transparent_pixels_within_8px": int(fill_band.sum()),
        "transparent_rgb_matches_nearest_visible": int((fill_band & (rgb == nearest_rgb).all(axis=2)).sum()),
        "zero_rgb_next_to_colored_edge_within_8px": int(empty_rgb.sum()),
        "zero_rgb_next_to_colored_edge_at_1px": int(adjacent_empty.sum()),
        "midpoint_max_encoded_rgb_loss_in_byte_values": round(float(midpoint_loss), 2),
    }, edge_selection(partial, ~visible) | adjacent_empty


def edge_selection(partial, transparent):
    edge = partial & ndi.binary_dilation(transparent, iterations=EDGE_RADIUS)
    return edge if edge.any() else partial


def detail_rect(candidates):
    height, width = candidates.shape
    radius = DETAIL_SIZE // 2
    scores = ndi.uniform_filter(candidates.astype(np.float32), DETAIL_SIZE, mode="constant")
    y, x = np.unravel_index(scores.argmax(), scores.shape)
    left = int(np.clip(x - radius, 0, max(width - DETAIL_SIZE, 0)))
    top = int(np.clip(y - radius, 0, max(height - DETAIL_SIZE, 0)))
    return [left, top, min(width, left + DETAIL_SIZE), min(height, top + DETAIL_SIZE)]


def composite(image, background):
    return Image.alpha_composite(Image.new("RGBA", image.size, background), image).convert("RGB")


def plate(pair, detail, output):
    cell_width, overview_height, detail_height = 344, 190, 178
    result = Image.new("RGB", (cell_width * 2, overview_height + detail_height), "#273040")
    for column, (image, color) in enumerate(zip(pair, ("black", "white"), strict=True)):
        x = column * cell_width
        overview = image.copy()
        overview.thumbnail((cell_width - 12, overview_height - 8), Image.Resampling.LANCZOS)
        region = image.crop(detail)
        region = region.resize((region.width * 2, region.height * 2), Image.Resampling.NEAREST)
        region.thumbnail((cell_width - 12, detail_height - 8), Image.Resampling.NEAREST)
        result.paste(color, (x + 3, 0, x + cell_width - 3, overview_height - 3))
        result.paste(color, (x + 3, overview_height + 3, x + cell_width - 3, result.height))
        result.paste(overview, (x + (cell_width - overview.width) // 2, (overview_height - overview.height) // 2))
        result.paste(region, (x + (cell_width - region.width) // 2, overview_height + (detail_height - region.height) // 2))
    save_jpg(result, output)


def source_path(row):
    return row.get("derived_from", row)["path"]


def group_for(row, declaration, atlases):
    if "artwork_alpha_blocker" in row["roles"]:
        return "blocker"
    if row["id"] in atlases:
        return "atlas"
    if row["id"].startswith("hud."):
        return "hud"
    if ("/T12/screen_shadow/" in source_path(row) or any(".forget.stroke_" in ref or ref.startswith("/presentation/dragon/")
                                                       for ref in declaration["level_field_matches"])):
        return "boss"
    if any(ref.startswith("/entities/") for ref in declaration["level_field_matches"]):
        return "actor"
    return "scene"


def matte_provenance(row):
    original = source_path(row)
    name = Path(original).name
    if ("/generated/workbench_boss/" in original and (name.startswith("stroke_") or name == "ending_lantern_halo.png")
            or "/generated/tadpole_encounter/" in original and name in {"puddle_surface.png", "alley_wet_reflection.png"}):
        return {"status": "procedural_no_generation_matte", "evidence": row["source_evidence"]}
    historical = [match["file"] for match in row["matched_historical_review"]
                  if match["scope"] == "T08_approved_offline_sample"]
    if historical:
        return {"status": "T08_review_no_matte_rgb_recorded", "evidence": historical}
    return {"status": "no_numeric_matte_rgb_located", "evidence": row["source_evidence"]}


def prepare_image(row, declaration, stage, group, rects, output):
    path = staged_resource(stage, declaration)
    with Image.open(path) as source:
        image = source.copy()
    pixels = np.asarray(image)
    if image.mode != "RGBA" or list(image.size) != row["decoded"]["pixels"]:
        raise ValueError(f"Unexpected source format: {row['id']}")

    if rects:
        metrics, candidates = {}, {}
        for part, rect in rects.items():
            x, y, width, height = rect
            if min(x, y) < 0 or min(width, height) < 1 or x + width > image.width or y + height > image.height:
                raise ValueError(f"Invalid attachment rectangle: {row['id']}/{part}")
            values, candidates[part] = edge_metrics(pixels[y:y + height, x:x + width])
            metrics[part] = {"rect": rect, **values}
        part = max(metrics, key=lambda key: (metrics[key]["zero_rgb_next_to_colored_edge_at_1px"],
                                             metrics[key]["semitransparent_pixels"]))
        x, y = rects[part][:2]
        left, top, right, bottom = detail_rect(candidates[part])
        detail = [left + x, top + y, right + x, bottom + y]
        evidence = {"attachments": metrics, "detail_part": part}
    else:
        metrics, candidates = edge_metrics(pixels)
        if metrics["semitransparent_pixels"] != row["C02"]["semitransparent_pixels"]:
            raise ValueError(f"Alpha count does not match the audit: {row['id']}")
        detail = detail_rect(candidates)
        evidence = {"texture": metrics}

    pair = (composite(image, "black"), composite(image, "white"))
    thumbnail = f"plates/{row['id']}.jpg"
    plate(pair, detail, output / thumbnail)
    return {"id": row["id"], "group": group, "path": row["path"], "source_path": source_path(row), "sha256": row["sha256"],
            "pixels": list(image.size), "semitransparent_pixels": row["C02"]["semitransparent_pixels"],
            "matte": matte_provenance(row), "C02": "visual_review_pending", **evidence, "detail_rect": detail,
            "plate": thumbnail, "plate_sha256": digest(output / thumbnail)}


def prepare_lettering(identifier, declaration, stage, captures, size, output):
    staged_resource(stage, declaration)
    paths = [captures / f"{identifier}-{tone}.png" for tone in ("black", "white")]
    pair = []
    for path in paths:
        with Image.open(path) as image:
            pair.append(image.convert("RGB"))
    black, white = (np.asarray(image, dtype=np.int16) for image in pair)
    if any(list(image.size) != size for image in pair):
        raise ValueError(f"Unexpected Godot lettering capture size: {identifier}")
    difference = white - black
    if np.any(difference < 0) or np.ptp(difference, axis=2).max() > 2:
        raise ValueError(f"Godot lettering backgrounds do not form an alpha pair: {identifier}")
    alpha = 255 - np.rint(difference.mean(axis=2)).astype(np.uint8)
    partial = (alpha > 0) & (alpha < 255)
    if not partial.any() or alpha[0, 0] != 0 or not (alpha[8:-8, 8:-8] == 0).any():
        raise ValueError(f"Godot lettering matte did not yield transparent background and soft edges: {identifier}")
    detail = detail_rect(edge_selection(partial, alpha == 0))
    thumbnail = f"plates/{identifier}.jpg"
    plate(pair, detail, output / thumbnail)
    return {"id": identifier, "group": "lettering", "path": declaration["path"], "sha256": declaration["sha256"],
            "pixels": size, "semitransparent_pixels": int(partial.sum()), "transparent_pixels": int((alpha == 0).sum()),
            "opaque_pixels": int((alpha == 255).sum()), "C02": "runtime_shader_composite_visual_review_pending",
            "capture_sha256": {path.name: digest(path) for path in paths}, "detail_rect": detail,
            "plate": thumbnail, "plate_sha256": digest(output / thumbnail)}


def gallery(rows, build_id, output):
    navigation, sections = [], []
    for group, title in GROUPS.items():
        items = [row for row in rows if row["group"] == group]
        if not items:
            continue
        navigation.append(f'<a href="#{group}">{title} · {len(items)}</a>')
        cards = []
        for row in items:
            identifier = escape(row["id"])
            name = escape(Path(row["source_path"]).name) if group != "lettering" else identifier
            preview = escape(row["plate"])
            cards.append(f'<figure id="{identifier}"><a href="{preview}"><img src="{preview}" alt="{name} 的黑白叠底" '
                         f'width="688" height="368" loading="lazy"></a><figcaption><strong>{name}</strong> '
                         f'<a href="#{identifier}">{identifier}</a><br>{row["semitransparent_pixels"]:,} 个半透明像素'
                         '</figcaption></figure>')
        sections.append(f'<section id="{group}"><h2>{title}</h2><div class="grid">{"".join(cards)}</div></section>')
    html = f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>纸灯城 · 半透明边缘对照</title>
<style>
body{{margin:0 auto;max-width:1440px;padding:1rem 1.5rem 3rem;background:#151b25;color:#f0e6d4;font:16px/1.5 "Source Sans 3","Microsoft YaHei",system-ui,sans-serif}}
a{{color:#e7bd86;overflow-wrap:anywhere}}nav{{display:flex;flex-wrap:wrap;gap:.75rem 1.25rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,370px),1fr));gap:1rem}}
figure{{margin:0;background:#26303e}}img{{display:block;width:100%;height:auto}}figcaption{{padding:.5rem .75rem;overflow-wrap:anywhere}}
code{{overflow-wrap:anywhere}}h2{{margin:1.75rem 0 .75rem}}
</style>
<h1>纸灯城 · 半透明边缘对照</h1>
<p>每张左黑右白。上排为全图，下排为同一区域的近景。点图打开原尺寸对照。</p>
<p><a href="checks.json">逐件来源、坐标和填色数据</a> · <code>{build_id}</code></p>
<nav>{"".join(navigation)}</nav>
{"".join(sections)}
</html>
'''
    (output / "index.html").write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--lettering", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=CAST / "candidate_manifest.json")
    parser.add_argument("--coverage", type=Path, default=CAST / "a7/asset_coverage.json")
    parser.add_argument("--output", type=Path, default=CAST / "a7/alpha_edges")
    args = parser.parse_args()
    compiled_path = args.stage / "level.json"
    compiled, manifest, coverage = map(read_json, (compiled_path, args.manifest, args.coverage))
    verify_build(compiled, PACKAGE)
    capture_index = read_json(args.lettering / "captures.json")
    build_id = compiled["build_id"]
    if (any(doc["build_id"] != build_id for doc in (manifest, coverage, capture_index))
            or manifest["compiled_sha256"] != digest(compiled_path)
            or coverage["candidate_manifest_sha256"] != digest(args.manifest)):
        raise ValueError("Staged level, inventory, alpha coverage and Godot captures must use the same build")
    level = compiled["level"]
    resources = level["resources"]
    declared = {row["id"]: row for row in manifest["resources"]}
    atlases = attachment_rectangles(args.stage, level)
    (args.output / "plates").mkdir(parents=True, exist_ok=True)
    rows = []
    for row in coverage["resources"]:
        if row.get("C02", {}).get("status") != "pending":
            continue
        identifier = row["id"]
        declaration = declared[identifier]
        if any(row[key] != declaration[key] or row[key] != resources[identifier][key] for key in ("path", "sha256", "kind")):
            raise ValueError(f"Mismatched resource: {identifier}")
        group = group_for(row, declaration, atlases)
        rows.append(prepare_image(row, declaration, args.stage, group, atlases.get(identifier), args.output))
    if len(rows) != coverage["summary"]["C02"]["pending"] or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Incomplete source alpha coverage")
    hud = level["presentation"]["hud_art"]["lettering"]
    if set(capture_index["sizes"]) != {hud["title"], hud["first_chapter"], *hud["chapters"].values()}:
        raise ValueError("Expected every compiled HUD lettering resource")
    lettering = [prepare_lettering(identifier, resources[identifier], args.stage, args.lettering, size, args.output)
                 for identifier, size in capture_index["sizes"].items()]
    gallery(rows + lettering, build_id, args.output)
    textures = [row["texture"] for row in rows if "texture" in row]
    parts = [part for row in rows if "attachments" in row for part in row["attachments"].values()]
    gap = "zero_rgb_next_to_colored_edge_at_1px"
    summary = {"source_composites": len(rows), "Godot_lettering_composites": len(lettering),
               "single_textures_with_adjacent_zero_rgb": sum(bool(texture[gap]) for texture in textures),
               "atlas_attachments_checked": len(parts), "atlas_attachments_with_adjacent_zero_rgb": sum(bool(part[gap]) for part in parts),
               "groups": dict(Counter(row["group"] for row in rows + lettering)),
               "matte_source_status": dict(Counter(row["matte"]["status"] for row in rows))}
    write_json(args.output / "checks.json", {"build_id": build_id, "compiled_sha256": manifest["compiled_sha256"],
               "candidate_manifest_sha256": digest(args.manifest), "source_coverage_sha256": digest(args.coverage),
               "gallery_sha256": digest(args.output / "index.html"), "summary": summary, "resources": rows,
               "lettering": lettering, "formal_C02": "pending_visual_review_and_remaining_edge_fixes"})
    print(summary)


if __name__ == "__main__":
    main()
