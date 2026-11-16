"""Review paired warning frames from the current three-chapter campaign."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from artlib import GAME, digest, write_json
from t10_preview import read_json, save_jpg
from t13_readability import THUMBNAIL, image_for, inspect

OUTPUT = GAME / "reports/art/T16/cast/attack_warnings"


def comparison_sheet(rows, previews, font, output):
    width, height = THUMBNAIL
    margin, gap, caption = 16, 12, 26
    group_width = 2 * width + gap
    row_height = height + caption + gap
    group_height = 2 * caption + 3 * row_height
    page = Image.new("RGB", (2 * margin + 2 * group_width + 2 * gap, 2 * margin + 2 * group_height), "#181c28")
    draw = ImageDraw.Draw(page)
    for index, (row, (visible, reference)) in enumerate(zip(rows, previews, strict=True)):
        group, sample = divmod(index, 3)
        x = margin + (group % 2) * (group_width + 2 * gap)
        y = margin + (group // 2) * group_height
        if sample == 0:
            draw.text((x, y), row["label"], font=font, fill="#e7e2d6")
            draw.text((x, y + caption), "游戏画面", font=font, fill="#bfc9d0")
            draw.text((x + width + gap, y + caption), "移除对应效果", font=font, fill="#bfc9d0")
        y += 2 * caption + sample * row_height
        draw.text((x, y), row["phase"], font=font, fill="#e7e2d6")
        page.paste(visible, (x, y + caption))
        page.paste(reference, (x + width + gap, y + caption))
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
            or receipt["source_revision"] != build["source_revision"] or len(receipt["frames"]) != 12):
        raise ValueError("Expected verified bridge and cinema warning pairs from the supplied build")
    font = ImageFont.truetype(args.font, 15)
    args.output.mkdir(parents=True, exist_ok=True)
    rows, previews = [], []
    for frame in receipt["frames"]:
        row, thumb = inspect(args.captures, frame)
        reference = image_for(args.captures / f"{row['frame']}_reference.png")
        previews.append((thumb, reference.resize(THUMBNAIL, Image.Resampling.LANCZOS)))
        rows.append(row)
    sheet = args.output / "comparison_1_8.jpg"
    comparison_sheet(rows, previews, font, sheet)
    summary = {"frame_pairs": len(rows),
               "C03_frames_passed": sum(row["C03"]["status"] == "pass" for row in rows),
               "pairs_changed_at_eighth": sum(row["pixels_changed_at_eighth"] > 0 for row in rows),
               "interrupted_attack_sequences": 1 + len(receipt["projectors"])}
    write_json(args.output / "checks.json", {**receipt, "compiled_sha256": digest(args.build), "frames": rows,
               "summary": summary, "comparison_sha256": digest(sheet), "visual_and_hardware_review": "pending"})
    print(summary)


if __name__ == "__main__":
    main()
