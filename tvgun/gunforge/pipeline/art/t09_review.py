"""Run the T09 concept checks and build the local review package."""
import hashlib
import html
import json
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
import yaml

from artlib import GAME
from checks import run


REPORT = GAME / "reports/art/T09"
REUSE = [
    ("vendor", "卖糖葫芦的", "../T05/gallery/vendor_idle_v5.png"),
    ("video_owner", "录像厅老板", "../T05/gallery/video_idle_v5.png"),
    ("crow", "墨鸦", "../T06/gallery/crow_normal.png"),
    ("tadpole", "墨蝌蚪", "../T06/gallery/tadpole0_normal.png"),
]
CHECKS = ("C03", "C04", "C05", "C14")
LABELS = {"pass": "通过", "fail": "失败", "pending": "待检查", "na": "不适用"}
GROUPS = ("纸居民", "墨怪", "Boss", "标题字")
TITLE_IDS = ("game_title_", "night_market_", "old_cinema_", "railway_station_")
TITLE_NAMES = ("纸灯城", "夜市", "旧影院", "火车站")


def group(item_id):
    if item_id.startswith(TITLE_IDS):
        return "标题字"
    if item_id in {"crow", "tadpole"} or item_id.startswith(("ink_", "umbrella_")):
        return "墨怪"
    if item_id.startswith(("dragon", "screen_", "projector", "film_", "forget_")):
        return "Boss"
    return "纸居民"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_attempts():
    return [
        item
        for ledger in sorted(REPORT.glob("batch-*.json"))
        for item in json.loads(ledger.read_text(encoding="utf-8"))
    ]


def inspect(item, palette, scratch):
    row = {**item, "group": group(item["id"]), "review_status": "pending"}
    if item.get("prompt"):
        reference = item.get("reference")
        reference_hash = digest((REPORT / reference).read_bytes()) if reference else None
        request = {"prompt": item["prompt"], "reference_sha256": reference_hash, "transparent_background": False}
        row.update(
            request_fingerprint=digest(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()),
            reference_sha256=reference_hash,
            provider_task_id=None,
            model=None,
            seed=None,
            requested_size=None,
            cost=None,
            normalization="none; original preserved",
        )
    if not item.get("output"):
        return row
    source = REPORT / item["output"]
    row["sha256"] = digest(source.read_bytes())
    expected = item.get("expected_text", "忘" if item["id"] == "forget_boss" else "")
    with Image.open(source) as original:
        row["actual_size"] = list(original.size)
        row["mode"] = original.mode
        sample = original.convert("RGBA")
        sample.thumbnail((320, 320), Image.Resampling.BOX)
        sampled_path = scratch / (item.get("local_attempt_id", item["id"]) + ".png")
        sample.save(sampled_path)
    row["checks"] = {
        "C03": run("C03", {"file": source}),
        "C04": run("C04", {"file": sampled_path, "palette_rgb": palette}),
        "C05": run("C05", {"file": source, "expected_text": expected}),
        "C14": run("C14", {}),
    }
    row["checks"]["C04"]["details"]["scope"] = "缩略概念图，含背景和印迹，供初筛"
    return row


def select_items(rows):
    selected = {}
    for row in rows:
        prior = selected.get(row["id"])
        if prior is None or row.get("output"):
            selected[row["id"]] = row
    return list(selected.values())


def severity(row):
    statuses = {check["status"] for check in row.get("checks", {}).values()}
    return (0 if not row.get("output") or "fail" in statuses else 1 if "pending" in statuses else 2)


def gallery_html(items):
    e = html.escape
    sections = []
    partitions = [(label, [row for row in items if row["group"] == label]) for label in GROUPS[:-1]]
    partitions.extend(
        (f"标题字 · {name}", [row for row in items if row["id"].startswith(prefix)])
        for prefix, name in zip(TITLE_IDS, TITLE_NAMES)
    )
    for label, group_items in partitions:
        cards = []
        for row in sorted(group_items, key=severity):
            name, file = e(row["name"]), row.get("output")
            image = ""
            if file:
                href = e("../" + file, quote=True)
                image = f'<a href="{href}"><img loading="lazy" src="{href}" alt="{name}"></a>'
            details = []
            for key, check in row.get("checks", {}).items():
                recognized = check["details"].get("recognized")
                suffix = ""
                if recognized and (row.get("expected_text") or row["id"] == "forget_boss"):
                    short = recognized[:32] + ("…" if len(recognized) > 32 else "")
                    suffix = f" · OCR：{e(short)}"
                details.append(f'<li><b>{key}</b> {LABELS[check["status"]]}{suffix}</li>')
            size = " × ".join(map(str, row.get("actual_size", [])))
            origin = "沿用既有设定" if row["status"] == "reused" else "新生成候选"
            state = f"{origin} · {size}" if file else "图像待补"
            notes = e(row.get("visual_note", ""))
            cards.append(f'<article>{image}<div><h3>{name}</h3><p>{state}</p><ul>{"".join(details)}</ul><p>{notes}</p></div></article>')
        sections.append(f'<section><h2>{label}</h2><div class="grid">{"".join(cards)}</div></section>')
    return """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>纸灯城 · T09 设定审阅</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0 auto;max-width:1440px;padding:28px;font:16px/1.55 system-ui,"Microsoft YaHei",sans-serif;background:#151a28;color:#f1e6d7}
h1{font-size:28px;margin:0}h2{font-size:21px;color:#e9ae77;margin-top:32px}h3{font-size:16px;margin:0}
p{color:#c8bec0;margin:.4rem 0}a{color:#f0bc8a}ul{margin:.5rem 0;padding-left:20px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:12px}
article{border:1px solid #3d4050;background:#202639;overflow:hidden}article div{padding:12px}
img{display:block;width:100%;height:240px;object-fit:contain;background:#353745}
</style><main><h1>T09 · 纸灯城设定审阅</h1>
<p>按类别比对设定和字形。点击图片看原尺寸。每组标题可选 A、B 或 C。</p>
<p>C04 含灰底，供概念初筛。C05 的完整 OCR 结果和 C14 的待检查原因见检查清单。</p>
<p><a href="../report.md">检查报告</a> · <a href="../review.yaml">审核表</a> · <a href="../manifest.json">提示词与检查数据</a></p>
""" + "".join(sections) + "</main></html>\n"


def main():
    attempts = load_attempts()
    notes_path = REPORT / "visual_notes.json"
    notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    reused = [{"id": key, "name": name, "output": path, "status": "reused"} for key, name, path in REUSE]
    for row in attempts + reused:
        if row["id"] in notes:
            row["visual_note"] = notes[row["id"]]
    palette = [
        tuple(bytes.fromhex(color["hex"][1:]))
        for color in json.loads((GAME / "bible/palette.json").read_text(encoding="utf-8"))["colors"]
    ]
    with tempfile.TemporaryDirectory(prefix="gunforge-t09-") as tmp, ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda item: inspect(item, palette, Path(tmp)), attempts + reused))
    items = select_items(rows)
    review_path = REPORT / "review.yaml"
    existing = yaml.safe_load(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    decisions = {row["id"]: row for row in (existing or {}).get("items", [])}
    review = {**(existing or {}), "stage": "A4", "items": []}
    for row in items:
        if not row.get("output"):
            continue
        prior = decisions.get(row["id"], {})
        same_art = prior.get("sha256") == row["sha256"]
        review["items"].append({
            "id": row["id"], "name": row["name"], "sha256": row["sha256"],
            "status": prior.get("status", "pending") if same_art else "pending",
            "note": prior.get("note", "") if same_art else "",
        })
    approved = {(item["id"], item["sha256"]): item["status"] for item in review["items"]}
    for row in rows:
        row["review_status"] = approved.get((row["id"], row.get("sha256")), "pending")
    (REPORT / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review_path.write_text(yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding="utf-8")
    gallery = REPORT / "gallery"
    gallery.mkdir(exist_ok=True)
    (gallery / "index.html").write_text(gallery_html(items), encoding="utf-8")
    counters = {check: dict(Counter(row["checks"][check]["status"] for row in items if row.get("checks"))) for check in CHECKS}
    print(json.dumps({"attempts": len(attempts), "outputs": sum(bool(row.get("output")) for row in items),
                      "missing": [row["id"] for row in items if not row.get("output")], "checks": counters}, ensure_ascii=False))


if __name__ == "__main__":
    main()
