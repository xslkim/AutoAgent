"""Check the isolated cast candidate's resource encoding, masks, and review evidence."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import yaml

from artlib import GAME, ROOT, digest, write_json
from checks import run
from t10_preview import read_json

sys.path.insert(0, str(ROOT / "gunforge/pipeline/level_design"))
from audit_lantern_city_release import bindings as resource_references, file_format, verify_build  # noqa: E402
from cast_color_images import COPIES as CAST_RGBA8_COPIES, is_data_binding, verify_rgba8_source  # noqa: E402
from cast_edge_fill import COPIES as CAST_EDGE_COPIES, adjacent_color_gaps, verify_edge_fill_source  # noqa: E402

ART = GAME / "reports/art"
CAST = ART / "T16/cast"
PACKAGE = "paper.lantern_city_cast"
OUTPUT = CAST / "a7/asset_coverage.json"
T08 = ART / "T08"
T10 = ART / "T10"


def repo_path(path):
    return path.relative_to(ROOT).as_posix()


def reviewed_sources():
    t08_review = yaml.safe_load((T08 / "review.yaml").read_text(encoding="utf-8"))
    decision = t08_review["offline_sample_decision"]
    pack = T08 / "asset_pack"
    pack_manifest = pack / "manifest.json"
    sample = T08 / "gallery/alley_sample.mp4"
    if (t08_review["status"] != "approved_offline_sample" or digest(pack_manifest) != decision["pack_manifest_sha256"]
            or digest(sample) != decision["sample_sha256"]):
        raise ValueError("T08 review evidence no longer matches the approved sample")
    source_files = {row["file"]: row["sha256"] for row in read_json(pack_manifest)["files"]}
    if any(digest(pack / name) != sha for name, sha in source_files.items()):
        raise ValueError("A file in the approved T08 pack has changed")
    historical_checks = {row["file"]: {check: {key: row[check][key] for key in ("status", "diagnostic_only") if key in row[check]}
                                        for check in ("C01", "C03", "C04", "C05") if check in row}
                         for row in read_json(T08 / "asset_checks.json")["assets"]}
    matches = defaultdict(list)
    for name, sha in source_files.items():
        matches[sha].append({"scope": "T08_approved_offline_sample", "file": repo_path(pack / name),
                             "review": repo_path(T08 / "review.yaml"),
                             "historical_checks": historical_checks.get(name, {})})

    t10_review = yaml.safe_load((T10 / "review.yaml").read_text(encoding="utf-8"))
    gallery = T10 / "gallery/index.html"
    if digest(gallery) != t10_review["visual_approval"]["gallery_sha256"]:
        raise ValueError("T10 gallery differs from the approved visual review")
    gallery_text = gallery.read_text(encoding="utf-8")
    report_lines = (T10 / "report.md").read_text(encoding="utf-8").splitlines()
    approved_labels = tuple(f"- {item['id']} · " for item in t10_review["items"] if item["status"] == "approved")
    for row in read_json(T10 / "generation_manifest.json"):
        if not row.get("sha256") or not row.get("output"):
            continue
        path = T10 / row["output"]
        preview = f"stations/{row['id']}/composition_off.jpg"
        linked = any(line.startswith(approved_labels) and row["output"] in line and preview in line for line in report_lines)
        if linked and preview in gallery_text and path.is_file() and digest(path) == row["sha256"]:
            matches[row["sha256"]].append({"scope": "T10_generation_source_linked_to_approved_gallery",
                                            "file": repo_path(path), "gallery_preview": repo_path(T10 / preview),
                                            "review": repo_path(T10 / "review.yaml")})
    sdf = run("C16", {"sdf": "crow/sdf.png", "alpha": "crow/alpha.png", "source_color": False}, pack)
    sdf["scope"] = "approved T08 source pack"
    sdf["files"] = {repo_path(pack / name): source_files[name] for name in ("crow/sdf.png", "crow/alpha.png")}
    return matches, sdf


def bindings(level):
    hit_pairs, scalar, blockers = [], [], []
    for name, entity in level["entities"].items():
        parts = [(name, entity), *((f"{name}/parts/{part}", item) for part, item in entity.get("parts", {}).items())]
        for owner, item in parts:
            if "hit_resource" in item:
                hit_pairs.append((owner, item["hit_resource"], item.get("resource")))
        if "mask_permission" in entity:
            gate = entity["mask_permission"]
            scalar.append({"owner": name, "resource": gate["resource"], "anchor": gate["source"], "threshold": gate["threshold"]})
    for name, query in level["queries"].items():
        if query["op"] == "mask_sample":
            scalar.append({"owner": name, "resource": query["resource"]})
    for name, layer in level["presentation"].get("layers", {}).items():
        if layer.get("blocker", False):
            blockers.append({"owner": name, "resource": layer["resource"], "channel": "artwork_alpha"})
    return hit_pairs, scalar, blockers


def check_encoding(path, mode, declared_roles):
    with path.open("rb") as stream:
        header = stream.read(26)
    depth = header[24] if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR" else None
    # Dedicated hit rasters use alpha in RasterItem, so their runtime format is RGBA.
    expected = "L" if "scalar_red" in declared_roles else "RGBA"
    return {"status": "pass" if mode == expected and depth == 8 else "fail",
            "mode": mode, "expected_runtime_mode": expected, "bits_per_channel": depth}


def alpha_evidence(image, is_color):
    if not is_color:
        return {"status": "na", "reason": "runtime data raster"}
    if "A" not in image.getbands():
        return {"status": "na", "reason": "opaque source has no semitransparent pixels", "semitransparent_pixels": 0}
    histogram = image.getchannel("A").histogram()
    partial = sum(histogram[1:255])
    row = {"status": "pending" if partial else "na", "transparent_pixels": histogram[0],
           "semitransparent_pixels": partial, "opaque_pixels": histogram[255]}
    row["reason"] = ("requires source matte or visual black/white comparison" if partial
                     else "no semitransparent pixels for the matte-residue check")
    return row


def inspect_hit_pairs(pairs, images):
    results = []
    for owner, mask_id, artwork_id in pairs:
        hit = images[mask_id]
        artwork = images.get(artwork_id)
        row = {"owner": owner, "hit_resource": mask_id, "artwork_resource": artwork_id,
               "hit_size": list(hit.size), "channel": "alpha"}
        if artwork is None or hit.size != artwork.size or "A" not in hit.getbands():
            row.update(status="fail", reason="hit raster must provide alpha on the artwork's source grid")
        else:
            hit_area = np.asarray(hit.getchannel("A")) >= 128
            visible = np.asarray(artwork.convert("RGBA").getchannel("A")) >= 128
            outside = int(np.count_nonzero(hit_area & ~visible))
            row.update(status="pass" if not outside and hit_area.any() else "fail",
                       hit_pixels=int(hit_area.sum()), outside_visible_pixels=outside,
                       artwork_size=list(artwork.size), same_file=mask_id == artwork_id)
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=CAST / "candidate_manifest.json")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    compiled_path = args.stage / "level.json"
    compiled = read_json(compiled_path)
    verify_build(compiled, PACKAGE)
    manifest = read_json(args.manifest)
    if manifest["build_id"] != compiled["build_id"] or manifest["compiled_sha256"] != digest(compiled_path):
        raise ValueError("The isolated build differs from the supplied cast manifest")
    level = compiled["level"]
    declared = level["resources"]
    references = resource_references(level)
    if {row["id"] for row in manifest["resources"]} != set(declared) or len(manifest["resources"]) != len(declared):
        raise ValueError("Manifest must contain each compiled resource exactly once")

    matches, historical_sdf = reviewed_sources()
    pairs, scalar_bindings, blockers = bindings(level)
    alpha_ids = {mask_id for _, mask_id, _ in pairs}
    scalar_ids = {row["resource"] for row in scalar_bindings}
    blocker_ids = {row["resource"] for row in blockers}
    mask_inputs = alpha_ids | scalar_ids | {artwork_id for _, _, artwork_id in pairs}
    images, resources = {}, []
    for row in manifest["resources"]:
        identifier = row["id"]
        declaration = declared[identifier]
        path = args.stage / row["path"]
        if (row["path"] != declaration["path"] or row["sha256"] != declaration["sha256"] or row["kind"] != declaration["kind"]
                or row["level_field_matches"] != references[identifier]
                or not path.resolve().is_relative_to(args.stage.resolve()) or digest(path) != row["sha256"]):
            raise ValueError(f"Staged resource differs from compiled input: {identifier}")
        decoded = file_format(path, row["kind"])
        if decoded != row["decoded"] or not (ROOT / row["source_evidence"]).is_file():
            raise ValueError(f"Decoded format or provenance differs for {identifier}")
        record = {key: row[key] for key in ("id", "path", "kind", "sha256", "source_evidence")}
        record["compiled_reference_count"] = len(row["level_field_matches"])
        record["decoded"] = decoded
        relative = Path(row["path"])
        if relative.is_relative_to(CAST_RGBA8_COPIES):
            origin = verify_rgba8_source(ROOT, relative, path, row["sha256"], row["derived_from"])
            record["derived_from"] = origin
            record["matched_historical_review"] = [dict(match, relation="pixel_equivalent_source")
                                                    for match in matches.get(origin["sha256"], [])]
        elif relative.is_relative_to(CAST_EDGE_COPIES):
            origin = verify_edge_fill_source(ROOT, relative, path, row["sha256"], row["derived_from"])
            record["derived_from"] = origin
            record["matched_historical_review"] = [dict(match, relation="visible_pixels_and_alpha_equivalent_source")
                                                    for match in matches.get(origin["sha256"], [])]
        else:
            record["matched_historical_review"] = matches.get(row["sha256"], [])
        if row["kind"] == "image":
            roles = []
            if identifier in alpha_ids:
                roles.append("alpha_hit")
            if identifier in scalar_ids:
                roles.append("scalar_red")
            if identifier in blocker_ids:
                roles.append("artwork_alpha_blocker")
            is_color = any(not is_data_binding(ref) for ref in row["level_field_matches"])
            if is_color:
                roles.append("color")
            record["roles"] = roles
            record["C01_image_encoding"] = check_encoding(path, decoded["mode"], roles)
            with Image.open(path) as asset:
                record["C02"] = alpha_evidence(asset, is_color)
                if is_color:
                    record["C02_adjacent_transparent_rgb_gaps"] = int(adjacent_color_gaps(np.asarray(asset)).sum()) if asset.mode == "RGBA" else 0
                if identifier in mask_inputs:
                    images[identifier] = asset.copy()
        resources.append(record)

    hit_checks = inspect_hit_pairs(pairs, images)
    for row in scalar_bindings:
        image = images[row["resource"]]
        low, high = image.getextrema() if image.mode == "L" else (None, None)
        row.update(status="pass" if low is not None and high > low else "fail", mode=image.mode,
                   channel="red", min_value=low, max_value=high)
    named_sdfs = [row["id"] for row in resources if row["kind"] == "image" and "sdf" in Path(row["path"]).stem.lower()]
    summary = {
        "decoded_resources": len(resources),
        "images": sum(row["kind"] == "image" for row in resources),
        "pixel_verified_rgba8_copies": sum(Path(row["path"]).is_relative_to(CAST_RGBA8_COPIES) for row in resources),
        "visible_pixels_and_alpha_verified_edge_fills": sum(Path(row["path"]).is_relative_to(CAST_EDGE_COPIES)
                                                            for row in resources),
        "C01_image_encoding": dict(Counter(row["C01_image_encoding"]["status"] for row in resources if "C01_image_encoding" in row)),
        "C02": dict(Counter(row["C02"]["status"] for row in resources if "C02" in row)),
        "C02_color_images_with_adjacent_rgb_gaps": sum(bool(row.get("C02_adjacent_transparent_rgb_gaps")) for row in resources),
        "C02_adjacent_rgb_gap_pixels": sum(row.get("C02_adjacent_transparent_rgb_gaps", 0) for row in resources),
        "alpha_hit_bindings": dict(Counter(row["status"] for row in hit_checks)),
        "distinct_alpha_hit_resources": len(alpha_ids),
        "scalar_red_bindings": dict(Counter(row["status"] for row in scalar_bindings)),
        "distinct_scalar_red_resources": len(scalar_ids),
        "artwork_alpha_blocker_bindings": len(blockers),
        "compiled_sdf_candidates_by_name": named_sdfs,
        "T08_approved_pack_byte_matches": sum(any(item["scope"] == "T08_approved_offline_sample"
                                                 and "relation" not in item
                                                 for item in row["matched_historical_review"]) for row in resources),
        "T08_approved_pack_visible_pixel_matches": sum(any(item["scope"] == "T08_approved_offline_sample"
                                                           and item.get("relation") == "visible_pixels_and_alpha_equivalent_source"
                                                           for item in row["matched_historical_review"]) for row in resources),
        "T10_gallery_source_byte_matches": sum(any(item["scope"] == "T10_generation_source_linked_to_approved_gallery"
                                                   and "relation" not in item
                                                   for item in row["matched_historical_review"]) for row in resources),
        "T10_gallery_source_pixel_matches": sum(any(item["scope"] == "T10_generation_source_linked_to_approved_gallery"
                                                    and item.get("relation") == "pixel_equivalent_source"
                                                    for item in row["matched_historical_review"]) for row in resources),
    }
    write_json(args.output, {"build_id": manifest["build_id"], "compiled_sha256": manifest["compiled_sha256"],
               "candidate_manifest_sha256": digest(args.manifest), "summary": summary, "resources": resources,
               "hit_bindings": hit_checks, "scalar_red_bindings": scalar_bindings, "blocker_bindings": blockers,
               "historical_crow_C16": historical_sdf, "formal_A7": "pending"})
    print(summary)
    if any(row["status"] != "pass" for row in hit_checks + scalar_bindings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
