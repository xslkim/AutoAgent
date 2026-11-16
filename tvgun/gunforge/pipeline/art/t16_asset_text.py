"""Audit the visible artwork in the locked Paper Lantern City candidate."""
import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from artlib import digest, write_json
from checks import check_ocr_data

LETTERS = {
    "hud.title": "纸灯城",
    "hud.night_market": "夜市",
    "hud.cinema": "旧影院",
    "hud.train_station": "火车站",
}
CONTROLS = {"control_blank": "", "control_added_text": "LANTERN2026"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def job(sha, layout):
    return {"id": sha, "file": f"inputs/{sha}.png", "layout": layout}


def prepare(stage, manifest_path, coverage_path, work):
    manifest = read(manifest_path)
    coverage = read(coverage_path)
    build = read(stage / "level.json")
    if (manifest["package"] != "paper.lantern_city_cast"
            or len({manifest["build_id"], coverage["build_id"], build["build_id"]}) != 1
            or digest(stage / "level.json") != manifest["compiled_sha256"]
            or digest(manifest_path) != coverage["candidate_manifest_sha256"]):
        raise ValueError("The isolated build, asset coverage, and inventory must match")
    bindings = build["level"]["presentation"]["hud_art"]["lettering"]
    if set(LETTERS) != {bindings["title"], bindings["first_chapter"], *bindings["chapters"].values()}:
        raise ValueError("Review the allowed text for the current lettering bindings")
    roles = {row["id"]: row["roles"] for row in coverage["resources"] if row["kind"] == "image"}
    stage = stage.resolve()
    (work / "inputs").mkdir(parents=True, exist_ok=True)
    inventory, cases, jobs = {}, {}, []
    for row in manifest["resources"]:
        if row["kind"] != "image":
            continue
        identifier = row["id"]
        path = (stage / row["path"]).resolve()
        sha = row["sha256"]
        if not path.is_relative_to(stage) or digest(path) != sha:
            raise ValueError(f"Asset checksum mismatch: {identifier}")
        inventory[identifier] = {"sha256": sha, "path": row["path"], "roles": roles[identifier]}
        if "color" not in roles[identifier]:
            continue
        expected = LETTERS.get(identifier, "")
        if sha in cases:
            if expected != cases[sha]:
                raise ValueError(f"The same texture has conflicting allowed text: {identifier}")
            continue
        cases[sha] = expected
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", image.size, "white")
            Image.alpha_composite(white, rgba).convert("RGB").save(work / job(sha, "")["file"])
        jobs.append(job(sha, "line" if expected else "sparse"))
    for identifier, expected in CONTROLS.items():
        image = Image.new("RGB", (640, 160), "white")
        if expected:
            ImageDraw.Draw(image).text((28, 36), "LANTERN 2026", fill="black", font=ImageFont.load_default(size=56))
        request = job(identifier, "line" if expected else "sparse")
        image.save(work / request["file"])
        jobs.append(request)
    write_json(work / "inventory.json", {"build_id": build["build_id"], "manifest_sha256": digest(manifest_path),
                                          "images": inventory, "cases": cases})
    write_json(work / "first.json", jobs)
    print(f"Prepared {len(cases)} distinct visible textures and {len(CONTROLS)} OCR controls")


def read_results(path, jobs):
    rows = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        if row["id"] in rows:
            raise ValueError(f"Duplicate OCR result: {row['id']}")
        rows[row["id"]] = row
    if set(rows) != {job["id"] for job in jobs}:
        raise ValueError(f"Incomplete OCR results: {path}")
    return rows


def validate_controls(first):
    blank = check_ocr_data(first["control_blank"], "")
    injected = check_ocr_data(first["control_added_text"], "")
    if blank["status"] != "pass" or injected["status"] != "fail" or injected["details"]["recognized"] != CONTROLS["control_added_text"]:
        raise ValueError("The blank control must pass and injected text must be rejected")
    return {"blank": blank, "added_text": injected}


def prepare_retry(work, cases, first):
    retries = []
    for sha, expected in cases.items():
        if check_ocr_data(first[sha], expected)["status"] == "pass":
            continue
        request = job(sha, "auto")
        if expected:
            # Retain the warm paper and indigo used by the game's lettering matte.
            with Image.open(work / request["file"]) as image:
                pixels = np.asarray(image, dtype=np.int16)
            red, green, blue = np.moveaxis(pixels, -1, 0)
            glyphs = ((red - blue >= 18) | (blue - np.maximum(red, green) >= 13))
            mask = Image.fromarray(glyphs.astype(np.uint8) * 255)
            bounds = mask.getbbox()
            if bounds:
                glyph = Image.fromarray(255 - np.asarray(mask.crop(bounds)))
                retry = Image.new("L", (glyph.width + 48, glyph.height + 48), 255)
                retry.paste(glyph, (24, 24))
                request["file"] = f"inputs/{sha}-retry.png"
                request["layout"] = "line"
                retry.save(work / request["file"])
        retries.append(request)
    write_json(work / "retry.json", retries)
    print(f"Prepared {len(retries)} single retries")


def record(data, expected):
    return {**check_ocr_data(data, expected), "words": data["words"]}


def review_gallery(path, work, checks_path):
    report = read(checks_path)
    previews = path.parent / "c05_previews"
    previews.mkdir(parents=True, exist_ok=True)
    letters, flagged = [], []
    for identifier, row in report["images"].items():
        artwork = report["artworks_by_sha256"].get(row["sha256"])
        if row["status"] == "na" or (row["status"] == "pass" and not artwork["expected"]):
            continue
        with Image.open(work / job(row["sha256"], "")["file"]) as source:
            width, height = source.size
            frame = source.convert("RGB")
        frame.thumbnail((1200, 900))
        preview_name = f"{row['sha256']}.jpg"
        frame.save(previews / preview_name, quality=90, subsampling=0, optimize=True)
        boxes = []
        # Lettering retries may use a cropped OCR input with its own coordinates.
        displayed = artwork["attempts"][:1] if artwork["expected"] else artwork["attempts"]
        for index, attempt in enumerate(displayed, 1):
            for word in attempt["words"]:
                box = word["bbox"]
                left = 100 * box["x0"] / width
                top = 100 * box["y0"] / height
                span_x = 100 * (box["x1"] - box["x0"]) / width
                span_y = 100 * (box["y1"] - box["y0"]) / height
                boxes.append(f'<i class="attempt{index}" aria-hidden="true" '
                             f'style="left:{left:.3f}%;top:{top:.3f}%;width:{span_x:.3f}%;height:{span_y:.3f}%"></i>')
        descriptions = []
        for index, attempt in enumerate(artwork["attempts"], 1):
            data = attempt["details"]
            text = data["recognized"]
            descriptions.append(f"第 {index} 次 {escape(text)}（{data['confidence']}）" if text else
                                f"第 {index} 次无文字输出")
        filename = Path(row["path"]).name
        caption = escape(f"{identifier} · {filename}")
        reference = f"预定文字「{artwork['expected']}」" if artwork["expected"] else ""
        card = (
            f'<figure><a class="preview" href="c05_previews/{preview_name}">'
            f'<img src="c05_previews/{preview_name}" alt="{caption}" loading="lazy" '
            f'width="{frame.width}" height="{frame.height}">{"".join(boxes)}</a>'
            f'<figcaption><strong>{caption}</strong><p>{escape(reference)}</p>'
            f'<p>{"<br>".join(descriptions)}</p></figcaption></figure>'
        )
        if artwork["expected"]:
            letters.append((identifier, card))
        else:
            detections = [attempt for attempt in artwork["attempts"] if attempt["details"]["recognized"]]
            confidence = max((attempt["details"]["confidence"] for attempt in detections), default=0)
            flagged.append((len(detections), confidence, identifier, card))
    checks_link = escape(Path(os.path.relpath(checks_path, path.parent)).as_posix(), quote=True)
    letter_cards = dict(letters)
    lettering = "".join(letter_cards[identifier] for identifier in LETTERS)
    flagged.sort(key=lambda item: (-item[0], -item[1], item[2]))
    review_cards = "".join(card for _, _, _, card in flagged)
    path.write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>纸灯城 C05 文字复核</title><style>'
        'body{box-sizing:border-box;font:1rem/1.5 system-ui,sans-serif;margin:1.5rem auto;padding:0 1rem;max-width:80rem;color:#eee9dd;background:#211c2a;overflow-wrap:anywhere}'
        'a{color:#f8bc83}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));gap:1rem;align-items:start}'
        '.letters{grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr))}'
        'figure{margin:0;border:1px solid #65586b;border-radius:.4rem;overflow:hidden;background:#302838}'
        '.preview{display:block;position:relative;overflow:hidden}.preview i{position:absolute;border:1px solid #ff6f28;box-sizing:border-box;pointer-events:none}'
        '.preview i.attempt2{border-color:#40e4ed}img{display:block;width:100%;height:auto;background:#ddd}'
        'figcaption{padding:.75rem;overflow-wrap:anywhere}'
        'p{margin:.25rem 0}p:empty{display:none}</style>'
        '<h1>纸灯城 C05 文字复核</h1>'
        f'<p>构建 <code>{report["build_id"]}</code></p>'
        '<p>橙框和蓝框分别标出两次 OCR 的定位。点击查看无框图。'
        f'逐件结果与原文件路径见 <a href="{checks_link}">检查数据</a>。</p>'
        f'<h2>标题与关卡名（{len(letters)}）</h2><div class="grid letters">{lettering}</div>'
        f'<h2>待核对的图像（{len(flagged)}）</h2><div class="grid">{review_cards}</div></html>\n',
        encoding="utf-8",
    )


def report(work, destination, inventory, first, controls):
    cases = inventory["cases"]
    retry_jobs = read(work / "retry.json")
    second = read_results(work / "retry.jsonl", retry_jobs)
    attempts = {}
    for sha, expected in cases.items():
        initial = record(first[sha], expected)
        results = [initial]
        if sha in second:
            results.append(record(second[sha], expected))
        status = results[-1]["status"]
        if not expected and len(results) == 2 and status != initial["status"]:
            status = "pending"
        attempts[sha] = {"expected": expected, "status": status, "attempts": results}
    images = inventory["images"]
    counts = Counter()
    for row in images.values():
        audit = attempts.get(row["sha256"]) if "color" in row["roles"] else None
        row["status"] = audit["status"] if audit else "na"
        if audit is None:
            row["reason"] = "Dedicated hit or scalar raster"
        counts[row["status"]] += 1
    project = Path(__file__).parent
    report = {"build_id": inventory["build_id"], "manifest_sha256": inventory["manifest_sha256"],
              "engine": first["control_blank"]["engine"], "bridge_sha256": digest(project / "ocr.cjs"),
              "runner_sha256": digest(Path(__file__)), "checker_sha256": digest(project / "checks.py"),
              "first_ocr_output_sha256": digest(work / "first.jsonl"),
              "retry_ocr_output_sha256": digest(work / "retry.jsonl"),
              "counts": dict(counts), "unique_artworks": len(cases), "retried_artworks": len(retry_jobs),
              "controls": controls, "images": images, "artworks_by_sha256": attempts}
    write_json(destination, report)
    print(json.dumps({"counts": counts, "unique_artworks": len(cases), "retried_artworks": len(retry_jobs)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "retry", "report"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gallery", type=Path)
    args = parser.parse_args()
    if args.phase == "prepare":
        if not all((args.stage, args.manifest, args.coverage)):
            parser.error("prepare requires --stage, --manifest and --coverage")
        prepare(args.stage, args.manifest, args.coverage, args.work)
        return
    inventory = read(args.work / "inventory.json")
    first = read_results(args.work / "first.jsonl", read(args.work / "first.json"))
    controls = validate_controls(first)
    if args.phase == "retry":
        prepare_retry(args.work, inventory["cases"], first)
    elif args.output:
        report(args.work, args.output, inventory, first, controls)
        if args.gallery:
            review_gallery(args.gallery, args.work, args.output)
    else:
        parser.error("report requires --output")


if __name__ == "__main__":
    main()
