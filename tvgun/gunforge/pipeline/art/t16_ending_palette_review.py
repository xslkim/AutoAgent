"""Compare the cast epilogue's existing and locally graded panorama."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.color import rgb2lab

from artlib import digest, write_json
from checks import run
from t16_asset_palette import frame_colors, image_pixels, measure, palette, read


POSES = {
    "ending_city_end": "Street before dissolve",
    "ending_dissolve_000": "Dissolve begins",
    "ending_dissolve_027": "Dissolve +0.45 s",
    "ending_dissolve_054": "Dissolve +0.90 s",
    "ending_dissolve_081": "Dissolve +1.35 s",
    "ending_wide_near": "Dissolve complete",
    "ending_wide_full": "Full panorama",
}
DIFF_FRAMES = set(POSES) - {"ending_city_end", "ending_dissolve_000"}


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.startswith("{")]


def build_resource(stage, manifest_path, receipt, edition):
    compiled = read(stage / "level.json")
    manifest = read(manifest_path)
    identifier = receipt["resource_id"]
    expected = receipt["base_build_id"] if edition == "before" else receipt["build_id"]
    if compiled["build_id"] != expected or manifest["build_id"] != expected or digest(stage / "level.json") != manifest["compiled_sha256"]:
        raise ValueError(f"Compiled {edition} candidate and release inventory differ")
    resource = compiled["level"]["resources"][identifier]
    path = stage / resource["path"]
    if digest(path) != resource["sha256"]:
        raise ValueError(f"Panorama checksum mismatch: {edition}")
    return compiled, manifest, path


def verify_isolation(baseline, candidate, identifier):
    before, base_manifest, _ = baseline
    after, variant_manifest, _ = candidate
    if before["tool_lock"] != after["tool_lock"] or before["source_map"] != after["source_map"]:
        raise ValueError("A palette review must use the same player, compiler, and source map")
    for key in ("player_files", "opening_files", "resource_counts"):
        if base_manifest[key] != variant_manifest[key]:
            raise ValueError(f"Unexpected release inventory change: {key}")
    left = before["level"]
    right = after["level"]
    if {key: item for key, item in left.items() if key != "resources"} != {key: item for key, item in right.items() if key != "resources"}:
        raise ValueError("The compiled gameplay changed")
    if left["resources"].keys() != right["resources"].keys():
        raise ValueError("The set of compiled resources changed")
    changed = {key for key in left["resources"] if left["resources"][key] != right["resources"][key]}
    if changed != {identifier}:
        raise ValueError(f"Expected only the panorama resource to change, got {changed}")


def compare_artwork(baseline, candidate, bounds, output):
    before = image_pixels(baseline)
    after = image_pixels(candidate)
    if before.shape != after.shape or not np.array_equal(before[..., 3], after[..., 3]):
        raise ValueError("The grade changed panorama dimensions or alpha")
    height, width = before.shape[:2]
    changed = np.any(before[..., :3] != after[..., :3], axis=2)
    y, x = np.nonzero(changed)
    left, top, right, bottom = bounds
    inside = ((x / width > left) & (x / width < right) & (y / height > top) & (y / height < bottom))
    if not len(x) or not inside.all():
        raise ValueError("The grade must stay inside the feathered stalls region")
    swatches = rgb2lab(np.asarray(palette(include_ink=True)) / 255)
    photo = {"size": [width, height], "pixels_changed": len(x), "changed_bounds_xyxy": [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1],
             "alpha_identical": True, "outside_region_pixel_identical": True, "editions": {}}
    for name, path, pixels in (("before", baseline, before), ("after", candidate, after)):
        photo["editions"][name] = {"sha256": digest(path), "C03": run("C03", {"file": str(path.resolve())}),
                                   "C04": measure(pixels, swatches)}
    if (photo["editions"]["after"]["C03"]["status"] != "pass"
            or photo["editions"]["after"]["C04"]["coverage"] < photo["editions"]["before"]["C04"]["coverage"]):
        raise ValueError("Candidate must keep the luminance limit and improve texture palette coverage")
    box = (max(0, x.min() - 30), max(0, y.min() - 30), min(width, x.max() + 31), min(height, y.max() + 31))
    gallery(output / "stalls_detail.jpg", [("Night market stalls and eaves",
            Image.fromarray(before).crop(box), Image.fromarray(after).crop(box))], 660)
    return photo


def gallery(path, rows, width):
    font = ImageFont.load_default(size=17)
    header, row_title = 31, 27
    sizes = [round(left.height * width / left.width) for _, left, _ in rows]
    sheet = Image.new("RGB", (width * 2, header + sum(h + row_title for h in sizes)), "#2a2230")
    label = ImageDraw.Draw(sheet)
    label.text((11, 7), "Current candidate", fill="#f6e5d1", font=font)
    label.text((width + 11, 7), "Local color comparison", fill="#f6e5d1", font=font)
    y = header
    for (caption, left, right), height in zip(rows, sizes, strict=True):
        label.text((11, y + 4), caption, fill="#f6e5d1", font=font)
        for column, image in enumerate((left, right)):
            sheet.paste(image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS),
                        (column * width, y + row_title))
        y += row_title + height
    sheet.save(path, quality=91, optimize=True)


def compare_routes(captures, baseline_id, candidate_id, output):
    routes, dissolves = {}, {}
    for edition, identifier in (("before", baseline_id), ("after", candidate_id)):
        log = read_log(captures / f"{edition}.log")
        route = log[-1]
        if (route["build_id"] != identifier or not route["passed"] or route["reached"] != list(range(1, 16))
                or route["replay"]["inputs"] < route["counters"]["shots"] or not route["failure_retries"]
                or not route["ending"]["city_texture_preloaded"] or not route["ending"]["wide_texture_preloaded"]):
            raise ValueError(f"Full replay, retry or texture preload failed in {edition}")
        routes[edition] = route
        dissolves[edition] = next(row["ending_dissolve"] for row in log if "ending_dissolve" in row)
    if dissolves["before"] != dissolves["after"]:
        raise ValueError("Crossfade poses or input state differ")
    for key in ("handoffs", "ending", "end_tick", "counters", "result", "failure_retries"):
        if routes["before"][key] != routes["after"][key]:
            raise ValueError(f"Gameplay or ending timing changed: {key}")
    recording = read_log(captures / "recording.log")[-1]
    if (recording["reference_build_id"] != baseline_id or recording["build_id"] != candidate_id
            or not recording["serialized_input_tape_identical"] or not recording["handoffs_identical"]):
        raise ValueError("Serialized inputs or handoffs differ")
    before = {path.stem: path for path in (captures / "before").glob("*.png")}
    after = {path.stem: path for path in (captures / "after").glob("*.png")}
    if before.keys() != after.keys() or len(before) != 54:
        raise ValueError("Expected the same 54 full-route and dissolve frames")
    changed = {key for key in before if digest(before[key]) != digest(after[key])}
    if changed != DIFF_FRAMES:
        raise ValueError(f"Unexpected changed GPU frames: {changed}")
    pairs, table = [], {}
    for name, label in POSES.items():
        left, right = image_pixels(before[name]), image_pixels(after[name])
        pairs.append((label, Image.fromarray(left), Image.fromarray(right)))
        table[name] = {
            "before": {"sha256": digest(before[name]), "C03": run("C03", {"file": str(before[name].resolve())}), **frame_colors(left)[0]},
            "after": {"sha256": digest(after[name]), "C03": run("C03", {"file": str(after[name].resolve())}), **frame_colors(right)[0]},
            "different_pixels": int(np.count_nonzero(np.any(left != right, axis=2))),
        }
    if any(row["after"]["C03"]["status"] != "pass" for row in table.values()):
        raise ValueError("A candidate dissolve pose exceeded the brightness limit")
    wide = table["ending_wide_full"]
    if not wide["after"]["fraction_delta_e10"] < .01 < wide["before"]["fraction_delta_e10"]:
        raise ValueError("Panorama did not improve the near-cinnabar screening result")
    gallery(output / "dissolve_compare.jpg", pairs, 580)
    return {"dissolve_poses": dissolves["after"], "captures": table, "identical_frames": sorted(set(before) - changed),
            "changed_frames": sorted(changed), "recording": recording,
            "before": routes["before"], "after": routes["after"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("before-stage", "after-stage", "before-manifest", "after-manifest", "receipt", "captures", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    args = parser.parse_args()
    receipt = read(args.receipt)
    baseline = build_resource(args.before_stage, args.before_manifest, receipt, "before")
    candidate = build_resource(args.after_stage, args.after_manifest, receipt, "after")
    verify_isolation(baseline, candidate, receipt["resource_id"])
    args.output.mkdir(parents=True, exist_ok=True)
    image = compare_artwork(baseline[2], candidate[2], receipt["bounds_xyxy_normalized"], args.output)
    route = compare_routes(args.captures, receipt["base_build_id"], receipt["build_id"], args.output)
    write_json(args.output / "checks.json", {"build_id": receipt["build_id"], "base_build_id": receipt["base_build_id"],
        "resource_id": receipt["resource_id"], "grade_operation": receipt["grade_operation"], "asset": image,
        "route": route, "candidate_manifest_sha256": digest(args.after_manifest), "frozen": False})
    print(json.dumps({"build_id": receipt["build_id"], "pixels_changed": image["pixels_changed"],
                      "unchanged_frames": len(route["identical_frames"]), "changed_frames": route["changed_frames"]}))


if __name__ == "__main__":
    main()
