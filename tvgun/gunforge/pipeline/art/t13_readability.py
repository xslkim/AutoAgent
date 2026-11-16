"""Evaluate the four train-station stops from paired Godot GPU captures."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import find_objects, label

from artlib import GAME, digest, write_json, yprime
from checks import run
from t10_preview import COMPOSITION_SIZE, read_json, save_jpg


REPORT = GAME / "reports/art/T13"
OUTPUT = REPORT / "gameplay/readability"
STOPS = ("waiting_room", "platform", "green_car", "lantern_base")
ACTORS = {"crow": "墨鸦", "umbrella": "墨伞"}
THUMBNAIL = tuple(dimension // 8 for dimension in COMPOSITION_SIZE)


def image_for(path):
    with Image.open(path) as frame:
        if frame.size != COMPOSITION_SIZE:
            raise ValueError(f"Unexpected frame size: {path}")
        return frame.convert("RGB")


def inspect_eyes(shape, frame, reference):
    components, _ = label(np.asarray(shape) >= 128, structure=np.ones((3, 3)))
    sizes = np.bincount(components.ravel())
    # The rotated alpha raster can leave an isolated edge pixel beside a connected eye.
    eyes_to_measure = [(index, box) for index, box in enumerate(find_objects(components), 1) if sizes[index] > 1]
    if len(eyes_to_measure) != 2:
        raise ValueError(f"Expected two separately visible hardened eyes in {frame}")
    eyes = []
    with TemporaryDirectory() as directory:
        for index, (ys, xs) in eyes_to_measure:
            mask = Path(directory) / f"eye_{index}.png"
            Image.fromarray((components == index).astype(np.uint8) * 255).save(mask)
            length = max(xs.stop - xs.start, ys.stop - ys.start)
            result = run("C06", {"state": "hardened", "file": frame, "target": mask,
                                 "background": reference, "eye_length": length})
            eyes.append({"length_px": length, "median_luminance_difference": round(result["details"]["contrast"], 4),
                         "C06": result})
    return eyes


def inspect(folder, sample):
    name = sample["frame"]
    frame = folder / f"{name}.png"
    reference = folder / f"{name}_reference.png"
    actual, behind = image_for(frame), image_for(reference)
    thumb = actual.resize(THUMBNAIL, Image.Resampling.LANCZOS)
    row = dict(sample, frame_sha256=digest(frame), reference_sha256=digest(reference),
               C03=run("C03", {"file": frame}))
    state = sample["state"]
    if state == "warning":
        background = behind.resize(THUMBNAIL, Image.Resampling.LANCZOS)
        full_delta = abs(yprime(actual) - yprime(behind))
        thumbnail_delta = abs(yprime(thumb) - yprime(background))
        row.update(pixels_changed_full=int(np.count_nonzero(full_delta > .03)),
                   pixels_changed_at_eighth=int(np.count_nonzero(thumbnail_delta > .03)),
                   visual_review="A5_pending")
        if not row["pixels_changed_full"]:
            raise ValueError(f"Warning did not render: {frame}")
        return row, thumb

    mask = folder / f"{name}_mask.png"
    with Image.open(mask) as shape:
        if shape.size != COMPOSITION_SIZE or shape.mode != "L" or shape.getbbox() is None:
            raise ValueError(f"Invalid target mask: {mask}")
        x0, y0, x1, y1 = shape.getbbox()
        visible_pixels = int(np.count_nonzero(np.asarray(shape) >= 128))
        if sample.get("hardened_cue") == "eyes":
            eyes = inspect_eyes(shape, frame, reference)
            row.update(mask_sha256=digest(mask), visible_pixels=visible_pixels, eyes=eyes,
                       numeric_passed=all(eye["C06"]["status"] == "pending" for eye in eyes))
            return row, thumb
    args = {"state": state, "file": frame, "target": mask, "background": reference,
            "eye_length": max(x1 - x0, y1 - y0)}
    result = run("C06", args)
    row.update(mask_sha256=digest(mask), visible_pixels=visible_pixels, measured_extent_px=args["eye_length"],
               median_luminance_difference=round(result["details"]["contrast"], 4))
    if state == "normal":
        row.update(numeric_passed=result["status"] == "pending", C06=result)
    else:
        # These encounters draw a tinted stamp in the hardened state; the eye check needs its own art.
        row.update(diagnostic="visible stamp compared with the same pose without the stamp",
                   meets_hardened_numeric_threshold_as_proxy=result["status"] == "pending",
                   C06={"status": "pending", "reason": "Separate hardened-eye art is not bound in these samples"})
    return row, thumb


def contact_sheet(titles, previews, columns, target, font):
    width, height = THUMBNAIL
    gap, margin = 12, 16
    header, row_height = 42, height + 47
    page = Image.new("RGB", (2 * margin + len(columns) * width + (len(columns) - 1) * gap,
                             margin + header + len(STOPS) * row_height), "#181c28")
    draw = ImageDraw.Draw(page)
    color = "#e7e2d6"
    for column, (actor, state, label) in enumerate(columns):
        x = margin + column * (width + gap)
        draw.text((x, margin), label, font=font, fill=color)
        for index, stage in enumerate(STOPS):
            y = margin + header + index * row_height
            entry = previews.get((stage, actor, state))
            draw.text((x, y), titles[stage], font=font, fill=color)
            if entry is None:
                draw.rectangle((x, y + 23, x + width - 1, y + 23 + height - 1), fill="#212633")
                draw.text((x + 9, y + 30), "无硬化态", font=font, fill="#b7bdc7")
            else:
                page.paste(entry, (x, y + 23))
    save_jpg(page, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    parser.add_argument("--build", type=Path, help="Require all captures to come from this compiled campaign")
    args = parser.parse_args()
    build = read_json(args.build) if args.build else None
    font = ImageFont.truetype(args.font, 15)
    args.output.mkdir(parents=True, exist_ok=True)
    titles = {row["id"]: row["title"] for row in read_json(REPORT / "layouts.json")["stations"]}
    stages, previews = {}, {}
    for stage in STOPS:
        folder = args.captures / stage
        receipt = read_json(folder / "samples.json")
        if not receipt["passed"] or receipt["stage"] != stage:
            raise ValueError(f"GPU capture verification failed for {stage}")
        if build and (receipt["build_id"] != build["build_id"] or receipt["source_revision"] != build["source_revision"]
                      or "campaign_entry_tick" not in receipt):
            raise ValueError(f"Expected captures from campaign {build['build_id']} for {stage}")
        results = []
        for sample in receipt["samples"]:
            row, thumb = inspect(folder, sample)
            previews.setdefault((stage, row["actor"], row["state"]), thumb)
            results.append(row)
        stages[stage] = {**receipt, "samples": results}
    contact_sheet(titles, previews, [(actor, state, label + suffix)
                  for state, suffix in (("normal", "可射"), ("hardened", "硬化")) for actor, label in ACTORS.items()],
                  args.output / "targets_1_8.jpg", font)
    contact_sheet(titles, previews, [(actor, "warning", label + "预警") for actor, label in ACTORS.items()],
                  args.output / "warnings_1_8.jpg", font)
    rows = [row for stage in stages.values() for row in stage["samples"]]
    normal = [row for row in rows if row["state"] == "normal"]
    hardened = [row for row in rows if row["state"] == "hardened"]
    eyes = [row for row in hardened if row.get("hardened_cue") == "eyes"]
    warnings = [row for row in rows if row["state"] == "warning"]
    summary = {"normal_numeric_passed": sum(row["numeric_passed"] for row in normal), "normal_samples": len(normal),
               "hardened_stamp_proxy_samples": len(hardened) - len(eyes), "hardened_eye_samples": len(eyes),
               "hardened_eye_numeric_passed": sum(row["numeric_passed"] for row in eyes), "warning_samples": len(warnings),
               "warning_visible_at_eighth": sum(bool(row["pixels_changed_at_eighth"]) for row in warnings),
               "brightness_samples": len(rows), "brightness_passed": sum(row["C03"]["status"] == "pass" for row in rows)}
    evidence = {"scope": "fixed gameplay poses for four stops; warning and thumbnail acceptance at A5",
                "summary": summary, "stages": stages,
                "previews": {name: digest(args.output / name) for name in ("targets_1_8.jpg", "warnings_1_8.jpg")}}
    if build:
        evidence.update(build_id=build["build_id"], source_revision=build["source_revision"], compiled_sha256=digest(args.build))
    write_json(args.output / "checks.json", evidence)
    print(summary)


if __name__ == "__main__":
    main()
