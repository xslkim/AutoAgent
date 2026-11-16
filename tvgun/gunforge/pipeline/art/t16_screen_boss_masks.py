"""Check the cinema boss's rendered hit masks and paired projector frames."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_erosion

from artlib import GAME, digest, effective_radius, mask, write_json
from checks import run
from t10_preview import read_json, save_jpg
from t13_readability import image_for

OUTPUT = GAME / "reports/art/T16/cast/screen_boss_masks"
SIDES = ("left", "center", "right")
LABELS = ("左胶片盘墨渍", "中胶片盘墨渍", "右胶片盘墨渍", "银幕影核")
RGB_DELTA = 8


def difference(frame, reference):
    return np.asarray(frame, dtype=np.int16) - np.asarray(reference, dtype=np.int16)


def measure_target(folder, sample):
    stem = sample["frame"]
    paths = {key: folder / f"{stem}{suffix}.png" for key, suffix in
             (("frame", ""), ("reference", "_reference"), ("mask", "_mask"))}
    frame = image_for(paths["frame"])
    reference = image_for(paths["reference"])
    hittable = mask(paths["mask"])
    if int(hittable.sum()) != sample["hit_pixels"]:
        raise ValueError(f"Hit pixel count does not match the Godot receipt for {stem}")
    radius, _ = effective_radius(hittable)
    changed = np.max(np.abs(difference(frame, reference)), axis=-1) >= RGB_DELTA
    row = {**sample, "effective_radius_px": round(radius, 2), "effective_radius_passed": radius >= 40,
           "hit_pixels_changed_when_hidden": int(np.count_nonzero(changed & hittable)),
           "C03": run("C03", {"file": paths["frame"]}),
           "sha256": {key: digest(path) for key, path in paths.items()}}
    return row, frame, hittable


def hit_sheet(samples, font, output):
    width, height = 204, 168
    margin, gap, caption = 16, 10, 24
    group_width = 2 * width + gap
    group_height = height + 2 * caption + gap
    page = Image.new("RGB", (2 * margin + 2 * group_width + 2 * gap, 2 * margin + 2 * group_height), "#181c28")
    draw = ImageDraw.Draw(page)
    for index, ((_, frame, hittable), label) in enumerate(zip(samples, LABELS, strict=True)):
        x = margin + (index % 2) * (group_width + 2 * gap)
        y = margin + (index // 2) * group_height
        ys, xs = np.nonzero(hittable)
        center_x = (int(xs.min()) + int(xs.max())) // 2
        center_y = (int(ys.min()) + int(ys.max())) // 2
        box = (center_x - width // 2, center_y - height // 2,
               center_x + width // 2, center_y + height // 2)
        outline = hittable & ~binary_erosion(hittable, iterations=2)
        contour = Image.fromarray(outline.astype(np.uint8) * 255)
        annotated = frame.crop(box)
        annotated.paste("#63e2c1", (0, 0, width, height), contour.crop(box))
        draw.text((x, y), label, font=font, fill="#e7e2d6")
        draw.text((x, y + caption), "游戏画面", font=font, fill="#bfc9d0")
        draw.text((x + width + gap, y + caption), "命中边界", font=font, fill="#bfc9d0")
        page.paste(frame.crop(box), (x, y + 2 * caption))
        page.paste(annotated, (x + width + gap, y + 2 * caption))
    save_jpg(page, output)


def compare_lights(folder, font, output):
    width, height = 444, 234
    margin, gap, caption = 16, 12, 25
    row_height = height + caption + gap
    page = Image.new("RGB", (2 * margin + 2 * width + gap, 2 * margin + 3 * row_height), "#181c28")
    draw = ImageDraw.Draw(page)
    results = []
    for index, side in enumerate(SIDES):
        path = folder / f"{side}_warm.png"
        ref_path = folder / f"{side}_warm_reference.png"
        warm, dark = image_for(path), image_for(ref_path)
        delta = difference(warm, dark)
        changed = np.max(np.abs(delta), axis=-1) >= RGB_DELTA
        if not changed.any():
            raise ValueError(f"Warm light did not render for {side}")
        red_minus_blue = np.median((delta[..., 0] - delta[..., 2])[changed])
        results.append({"side": side, "changed_pixels": int(changed.sum()),
                        "median_red_minus_blue_increase_8bit": float(red_minus_blue),
                        "frame_sha256": digest(path), "reference_sha256": digest(ref_path)})
        y = margin + index * row_height
        draw.text((margin, y), f"{LABELS[index]}净化后", font=font, fill="#e7e2d6")
        draw.text((margin + width + gap, y), "同帧墨光对照", font=font, fill="#bfc9d0")
        page.paste(warm.resize((width, height), Image.Resampling.LANCZOS), (margin, y + caption))
        page.paste(dark.resize((width, height), Image.Resampling.LANCZOS), (margin + width + gap, y + caption))
    save_jpg(page, output)
    return results


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
            or receipt["source_revision"] != build["source_revision"] or len(receipt["targets"]) != 4):
        raise ValueError("Expected four verified screen boss poses from the supplied campaign")
    font = ImageFont.truetype(args.font, 15)
    args.output.mkdir(parents=True, exist_ok=True)
    measurements = [measure_target(args.captures, row) for row in receipt["targets"]]
    targets = [row for row, _, _ in measurements]
    hit_sheet(measurements, font, args.output / "hit_regions.jpg")
    lights = compare_lights(args.captures, font, args.output / "light_swaps.jpg")
    misfire_path = args.captures / "projector_invalid.png"
    misfire = image_for(misfire_path).resize((888, 468), Image.Resampling.LANCZOS)
    save_jpg(misfire, args.output / "projector_invalid.jpg")
    summary = {"targets": len(targets), "radius_passed": sum(row["effective_radius_passed"] for row in targets),
               "hud_clear_at_camera_extremes": sum(row["hud_clear_at_camera_extremes"] for row in targets),
               "hit_pixels_outside_visual_alpha": sum(row["hit_outside_ink_pixels"] for row in targets),
               "positive_warm_light_swaps": sum(row["median_red_minus_blue_increase_8bit"] > 0 for row in lights),
               "C03_frames_passed": sum(row["C03"]["status"] == "pass" for row in targets)}
    previews = ("hit_regions.jpg", "light_swaps.jpg", "projector_invalid.jpg")
    write_json(args.output / "checks.json", {**receipt, "compiled_sha256": digest(args.build), "targets": targets,
               "light_swaps": lights, "summary": summary, "physical_lightgun": "pending",
               "misfire_frame_sha256": digest(misfire_path),
               "previews": {name: digest(args.output / name) for name in previews}})
    print(summary)


if __name__ == "__main__":
    main()
