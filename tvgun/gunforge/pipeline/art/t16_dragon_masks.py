"""Measure the moving dragon's actual hit rasters in the full campaign."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_erosion

from artlib import GAME, digest, effective_radius, mask, write_json
from checks import run
from t10_preview import read_json, save_jpg
from t13_readability import THUMBNAIL, image_for

OUTPUT = GAME / "reports/art/T16/cast/dragon_masks"
RGB_DELTA = 8


def inspect_mask(folder, row):
    path = folder / f"{row['sample']}_mask.png"
    hittable = mask(path)
    ys, xs = np.nonzero(hittable)
    if len(xs) != row["hittable_pixels"] or len(xs) == 0:
        raise ValueError(f"Mask and Godot pixel count differ for {row['sample']}")
    radius, _ = effective_radius(hittable[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    return {**row, "effective_radius_px": round(radius, 2), "radius_passed": radius >= 40,
            "mask_sha256": digest(path)}


def inspect_frame(folder, sample, name):
    path = folder / f"{name}.png"
    reference = folder / f"{name}_reference.png"
    frame = image_for(path)
    behind = image_for(reference)
    hittable = mask(folder / f"{sample}_mask.png")
    delta = np.abs(np.asarray(frame, dtype=np.int16) - np.asarray(behind, dtype=np.int16)).max(axis=-1)
    changed = int(np.count_nonzero((delta >= RGB_DELTA) & hittable))
    if changed == 0:
        raise ValueError(f"Removing the ink did not change its hit region in {name}")
    return {"frame": name, "sample": sample, "pixels_changed_in_hit_mask": changed,
            "frame_sha256": digest(path), "reference_sha256": digest(reference),
            "C03": run("C03", {"file": path})}


def motion_sheet(folder, entries, font, output):
    width, height = THUMBNAIL
    gap, margin, caption = 12, 16, 25
    row_height = height + caption + gap
    page = Image.new("RGB", (2 * margin + 4 * width + 3 * gap, 2 * margin + 3 * row_height), "#181c28")
    draw = ImageDraw.Draw(page)
    for index, (name, label) in enumerate(entries):
        x = margin + (index % 4) * (width + gap)
        y = margin + (index // 4) * row_height
        frame = image_for(folder / f"{name}.png").resize(THUMBNAIL, Image.Resampling.LANCZOS)
        draw.text((x, y), label, font=font, fill="#e7e2d6")
        page.paste(frame, (x, y + caption))
    save_jpg(page, output)


def mouth_sheet(folder, font, output):
    width, height = 244, 184
    margin, gap, caption = 14, 12, 25
    page = Image.new("RGB", (2 * margin + 4 * width + 3 * gap, 2 * margin + 2 * caption + height), "#181c28")
    draw = ImageDraw.Draw(page)
    poses = (("mouth_open", "mouth_idle_36", "龙嘴开放"), ("mouth_warning", "mouth_warning_35", "摆头预警"))
    for index, (name, sample, label) in enumerate(poses):
        frame = image_for(folder / f"{name}.png")
        hittable = mask(folder / f"{sample}_mask.png")
        ys, xs = np.nonzero(hittable)
        center_x = (int(xs.min()) + int(xs.max())) // 2
        center_y = (int(ys.min()) + int(ys.max())) // 2
        box = (center_x - width // 2, center_y - height // 2,
               center_x + width // 2, center_y + height // 2)
        outline = hittable & ~binary_erosion(hittable, iterations=2)
        contour = Image.fromarray(outline.astype(np.uint8) * 255)
        marked = frame.crop(box)
        marked.paste("#63e2c1", (0, 0, width, height), contour.crop(box))
        left = margin + 2 * index * (width + gap)
        right = left + width + gap
        draw.text((left, margin), label, font=font, fill="#e7e2d6")
        draw.text((left, margin + caption), "游戏画面", font=font, fill="#bfc9d0")
        draw.text((right, margin + caption), "可命中边界", font=font, fill="#bfc9d0")
        page.paste(frame.crop(box), (left, margin + 2 * caption))
        page.paste(marked, (right, margin + 2 * caption))
    save_jpg(page, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    args = parser.parse_args()
    receipt = read_json(args.captures / "samples.json")
    build = read_json(args.build)
    if (not receipt["passed"] or receipt["build_id"] != build["build_id"]
            or receipt["source_revision"] != build["source_revision"] or len(receipt["samples"]) != 30):
        raise ValueError("Expected 30 verified dragon poses from the supplied campaign")
    order = [row["id"] for row in receipt["opening_order"]]
    if order != [f"body_{index:02d}" for index in range(8, 0, -1)]:
        raise ValueError("The dragon did not open from tail to head")
    samples = [inspect_mask(args.captures, row) for row in receipt["samples"]]
    pairs = [(f"{target}_36", f"{target}_active") for target in order]
    pairs.extend((("mouth_idle_36", "mouth_open"), ("mouth_warning_35", "mouth_warning")))
    frames = [inspect_frame(args.captures, sample, name) for sample, name in pairs]
    purified = args.captures / "dragon_purified.png"
    frames.append({"frame": "dragon_purified", "frame_sha256": digest(purified), "C03": run("C03", {"file": purified})})
    font = ImageFont.truetype(args.font, 15)
    args.output.mkdir(parents=True, exist_ok=True)
    entries = [(f"{target}_active", f"龙节 {target[-2:]} 开放") for target in order]
    entries.extend((("mouth_open", "龙嘴开放"), ("mouth_warning", "摆头预警"), ("dragon_purified", "净化后暖纸")))
    motion_sheet(args.captures, entries, font, args.output / "motion_1_8.jpg")
    mouth_sheet(args.captures, font, args.output / "mouth_jaws.jpg")
    targets = [*order, "dragon.mouth"]
    minima = {target: min(row["effective_radius_px"] for row in samples if row["target"] == target) for target in targets}
    summary = {"poses": len(samples), "radius_passed": sum(row["radius_passed"] for row in samples),
               "hud_clear": sum(row["hud_clear"] for row in samples),
               "hidden_hittable_pixels": sum(row["hidden_hittable_pixels"] for row in samples),
               "C03_frames_passed": sum(row["C03"]["status"] == "pass" for row in frames),
               "min_radius_by_target_px": minima}
    previews = ("motion_1_8.jpg", "mouth_jaws.jpg")
    write_json(args.output / "checks.json", {**receipt, "compiled_sha256": digest(args.build), "samples": samples,
               "frames": frames, "summary": summary, "physical_lightgun": "pending",
               "previews": {name: digest(args.output / name) for name in previews}})
    print(summary)


if __name__ == "__main__":
    main()
