"""Measure the playable workbench strokes from paired Godot renders."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from artlib import GAME, digest, effective_radius, mask, write_json, yprime
from checks import run
from t10_preview import read_json, save_jpg
from t13_readability import THUMBNAIL, image_for

OUTPUT = GAME / "reports/art/T16/cast/workbench_readability"
GEOMETRY = GAME / "reports/art/T13/forget_strokes/geometry.json"
VISIBLE_DELTA = .03


def thumbnail(image):
    return image.resize(THUMBNAIL, Image.Resampling.LANCZOS)


def measure_stroke(folder, row):
    stem = row["stem"]
    paths = {name: folder / f"{stem}_{name}.png"
             for name in ("bright", "dim", "cue_off", "background", "ink_mask")}
    bright = image_for(paths["bright"])
    dim = image_for(paths["dim"])
    cue_off = image_for(paths["cue_off"])
    target = mask(paths["ink_mask"])
    if int(target.sum()) != row["hittable_pixels"]:
        raise ValueError(f"Pixel count does not match the Godot hit mask for {stem}")
    radius, _ = effective_radius(target)
    contrast = run("C06", {"state": "normal", "file": paths["cue_off"], "target": paths["ink_mask"],
                           "background": paths["background"]})
    dim_thumb = thumbnail(dim)
    delta = np.abs(yprime(dim_thumb) - yprime(thumbnail(cue_off)))
    marker_x, marker_y = map(int, row["dim_marker"])
    if not target[marker_y, marker_x]:
        raise ValueError(f"The dim marker is outside the current hit mask for {stem}")
    marker_at = (marker_x, marker_y)
    marker_delta = abs(float(yprime(dim.getpixel(marker_at)) - yprime(cue_off.getpixel(marker_at))))
    row = {**row, "effective_radius_px": round(radius, 2), "effective_radius_passed": radius >= 40,
           "C06_ink": contrast, "ink_numeric_passed": contrast["status"] == "pending",
           "dim_cue_pixels_changed_at_eighth": int(np.count_nonzero(delta > VISIBLE_DELTA)),
           "dim_cue_peak_yprime_difference_at_eighth": round(float(delta.max()), 4),
           "dim_marker_yprime_difference": round(marker_delta, 4),
           "C03": {name: run("C03", {"file": paths[name]}) for name in ("bright", "dim")},
           "sha256": {name: digest(path) for name, path in paths.items()}}
    return row, thumbnail(bright), dim_thumb


def stroke_sheet(samples, labels, font, output):
    width, height = THUMBNAIL
    margin, gap, caption = 16, 12, 24
    cell_height = 2 * (height + caption)
    page = Image.new("RGB", (2 * margin + 4 * width + 3 * gap, 2 * margin + 2 * cell_height + gap), "#181c28")
    draw = ImageDraw.Draw(page)
    for index, ((_, bright, dim), label) in enumerate(zip(samples, labels, strict=True)):
        column, row = index % 4, index // 4
        x = margin + column * (width + gap)
        y = margin + row * (cell_height + gap)
        draw.text((x, y), f"{index + 1}  {label} · 高亮", font=font, fill="#e7e2d6")
        page.paste(bright, (x, y + caption))
        y += height + caption
        draw.text((x, y), "低亮", font=font, fill="#e7e2d6")
        page.paste(dim, (x, y + caption))
    save_jpg(page, output)


def inspect_crossing(folder, crossing, font, output):
    dim = image_for(folder / "stroke_02_dim.png")
    cue_off = image_for(folder / "stroke_02_cue_off.png")
    graze = image_for(folder / "stroke_02_crossing_graze.png")
    opaque = mask(folder / "stroke_02_crossing_opaque.png")
    if int(opaque.sum()) != crossing["opaque_pixels"]:
        raise ValueError("Opaque crossing mask does not match the Godot receipt")
    delta = np.abs(yprime(dim)[opaque] - yprime(cue_off)[opaque])
    if crossing["shot"]["kind"] != "invalid":
        raise ValueError("Expected an invalid shot on the locked third stroke")
    x, y = map(int, crossing["shot_point"])
    box = (x - 85, y - 42, x + 155, y + 72)
    page = Image.new("RGB", (992, 274), "#181c28")
    draw = ImageDraw.Draw(page)
    for left, (frame, label) in zip((10, 500), ((dim, "第 2 笔的描边与落笔光点"), (graze, "交叉处开枪 · 第 3 笔擦伤")), strict=True):
        draw.text((left, 10), label, font=font, fill="#e7e2d6")
        page.paste(frame.crop(box).resize((480, 228), Image.Resampling.NEAREST), (left, 35))
        center_x, center_y = left + 170, 35 + 84
        draw.ellipse((center_x - 7, center_y - 7, center_x + 7, center_y + 7), outline="#e9f5f5", width=2)
    save_jpg(page, output)
    return {**crossing, "opaque_pixels_changed_by_cue": int(np.count_nonzero(delta > VISIBLE_DELTA)),
            "peak_yprime_difference_under_third": round(float(delta.max()), 4)}


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
            or receipt["source_revision"] != build["source_revision"]
            or [row["number"] for row in receipt["samples"]] != list(range(1, 8))):
        raise ValueError("Expected verified captures of all seven strokes from the supplied build")
    labels = [row["label"] for row in read_json(GEOMETRY)["strokes"]]
    font = ImageFont.truetype(args.font, 15)
    args.output.mkdir(parents=True, exist_ok=True)
    measurements = [measure_stroke(args.captures, row) for row in receipt["samples"]]
    samples = [row for row, _, _ in measurements]
    stroke_sheet(measurements, labels, font, args.output / "strokes_1_8.jpg")
    crossing = inspect_crossing(args.captures, receipt["crossing"], font, args.output / "crossing.jpg")
    summary = {"ink_numeric_passed": sum(row["ink_numeric_passed"] for row in samples),
               "effective_radius_passed": sum(row["effective_radius_passed"] for row in samples),
               "dim_cues_changed_at_eighth": sum(row["dim_cue_pixels_changed_at_eighth"] > 0 for row in samples),
               "C03_frames_passed": sum(check["status"] == "pass" for row in samples for check in row["C03"].values())}
    write_json(args.output / "checks.json", {**receipt, "compiled_sha256": digest(args.build), "samples": samples,
               "crossing": crossing, "summary": summary, "thumbnail_visual_review": "A5_pending",
               "previews": {name: digest(args.output / name) for name in ("strokes_1_8.jpg", "crossing.jpg")}})
    print(summary)


if __name__ == "__main__":
    main()
