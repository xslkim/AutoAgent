"""Assemble the full-game review from one compiled candidate's Godot captures."""
import argparse
from html import escape
import json
from math import ceil, floor
from pathlib import Path
import os

import numpy as np
from PIL import Image

from artlib import digest, write_json
from checks import run


ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "gunforge/games/g01/reports/art"
OUTPUT = ART / "T16"
CAST = "paper.lantern_city_cast"
STATIONS = ("alley", "stall", "video_shop", "footbridge", "plaza", "ticket_office", "poster_hall", "auditorium",
            "projection_booth", "screen_stage", "waiting_room", "platform", "green_car", "lantern_base", "workbench")
RESIDENTS = {
    "vendor": ("卖糖葫芦的", "夜市巷口"), "video_owner": ("录像厅老板", "录像厅门口"),
    "ticket_clerk": ("检票员", "售票处与站台共用同一造型"), "projectionist": ("放映员", "放映室"),
    "passerby_b": ("路人 B", "观众席"), "passerby_c": ("路人 C", "候车室"),
}
ENEMIES = {
    "ink_crow": ("墨鸦", "夜市巷口"), "ink_drop": ("滴墨", "录像厅门口"),
    "ink_cart": ("墨车夫", "天桥"), "ink_sign": ("墨招牌", "录像厅门口"),
    "ink_tape": ("磁带墨", "旧影院售票处"), "umbrella_open": ("墨伞", "旧影院 · 撑伞"),
}
BOSSES = {
    "dragon": ("墨舞龙", "夜市广场"), "screen_shadow": ("银幕影", "旧影院银幕前"),
    "forget": ("「忘」字", "爷爷的工作台"),
}
UI = {
    "controls/start_button": "标题、夜市字形与开始按钮", "controls/start_hover": "开始按钮 · 光枪瞄准",
    "controls/start_pressed": "开始按钮 · 按下", "route/cinema_transition": "旧影院转场字形",
    "route/train_station_transition": "火车站转场字形", "route/hud_reload": "灯芯、光弹、印章与回光提示",
    "controls/reticle_on": "半透明准星", "controls/reticle_off": "关闭准星", "controls/tracking_lost": "失锁提示",
    "route/campaign_clear": "通关结算", "controls/retry_button": "失败结算与重试按钮",
    "display/overscan_monitor": "显示器 · 四角标记", "display/overscan_tv": "电视 · 四角标记",
    "display/calibration_target": "光枪校准靶",
}


def result_log(directory, name):
    lines = (directory / f"{name}.log").read_text(encoding="utf-8-sig").splitlines()
    return [json.loads(line) for line in lines if line.startswith("{")]


def save_frame(image, path):
    image.save(path, "JPEG", quality=92, subsampling=0, optimize=True)


def crop_subject(image, bounds):
    x, y, width, height = bounds
    margin = max(24, .18 * max(width, height))
    return image.crop((max(0, floor(x - margin)), max(0, floor(y - margin)),
                       min(image.width, ceil(x + width + margin)), min(image.height, ceil(y + height + margin))))


def display_content(image, name):
    pixels = np.asarray(image)
    y, x = np.where(np.all(pixels == 255, axis=2))
    left, right, top, bottom = int(x.min()), int(x.max()) + 1, int(y.min()), int(y.max()) + 1
    inset = (74 if name == "overscan_monitor" else 72) * (right - left) / 1920
    return image.crop((ceil(left + inset), ceil(top + inset), floor(right - inset), floor(bottom - inset)))


def markup_card(row):
    title, caption = escape(row["title"]), escape(row.get("caption", ""))
    width, height = row["size"]
    return (f'<figure><a href="{escape(row["full"])}"><img src="{escape(row["image"])}" '
            f'alt="{title}" width="{width}" height="{height}" loading="lazy"></a>'
            f'<figcaption><strong>{title}</strong>{f"<span>{caption}</span>" if caption else ""}</figcaption></figure>')


def section(identifier, title, cards, text="", links=(), narrow=False):
    source_links = " · ".join(f'<a href="{escape(href)}">{escape(label)}</a>' for href, label in links)
    paragraphs = (f"<p>{escape(text)}</p>" if text else "", f"<p>{source_links}</p>" if links else "")
    layout = "cards compact" if narrow else "cards"
    return (f'<section id="{identifier}"><h2>{escape(title)}</h2>{paragraphs[0]}'
            f'<div class="{layout}">\n' + "\n".join(map(markup_card, cards)) + f'\n</div>{paragraphs[1]}</section>')


def build(compiled_path, captures):
    compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
    package = compiled["level"]["id"]
    full_cast = package == CAST
    output = OUTPUT / "cast" if full_cast else OUTPUT
    manifest = json.loads((output / "candidate_manifest.json").read_text(encoding="utf-8"))
    if manifest["package"] != package or manifest["compiled_sha256"] != digest(compiled_path):
        raise ValueError("Gallery requires the exact compiled candidate in the inventory")
    route_logs = result_log(captures, "route")
    subject_log, route = route_logs[-2:]
    controls, display = (result_log(captures, name)[-1] for name in ("controls", "display"))
    build_id = compiled["build_id"]
    for outcome in (manifest, subject_log, route, controls, display):
        if outcome["build_id"] != build_id:
            raise ValueError("Gallery inputs must use the T16 inventory build")
    if not (route["passed"] and route["gpu_capture"] and controls["passed"] and controls["captures"]
            and display["passed"] and display["captures"]):
        raise ValueError("The campaign or player capture did not pass")
    if (route["reached"] != list(range(1, 16)) or route["replay"]["inputs"] < route["counters"]["shots"]
            or route["replay"]["counters"] != route["counters"]):
        raise ValueError("Gallery requires the complete campaign route and replay")
    subjects = subject_log["gallery_subjects"]
    pictures = output / "frames"
    pictures.mkdir(exist_ok=True)
    records = {}

    def relative(path):
        return Path(os.path.relpath(path, output)).as_posix()

    def frame(stem, title, caption="", sample=None, crop=False):
        source = captures / f"{stem}.png"
        image = Image.open(source).convert("RGB")
        name = stem.rsplit("/", 1)[-1]
        full = pictures / f"{name}.jpg"
        save_frame(image, full)
        display = stem.startswith("display/")
        measured = source
        if display:
            measured = captures / f"{name}_content.png"
            display_content(image, name).save(measured)
        thumbnail = full
        if crop:
            image = crop_subject(image, sample["bounds"])
            thumbnail = pictures / f"{name}_detail.jpg"
            save_frame(image, thumbnail)
        check = run("C03", {"file": measured.name}, measured.parent)
        if check["status"] != "pass":
            raise ValueError(f"C03 failed for {stem}: {check}")
        records[name] = {"capture": stem, "source_png_sha256": digest(source), "jpg_sha256": digest(full),
                         "jpg": relative(full), "detail_jpg_sha256": digest(thumbnail) if crop else None,
                         "C03": check, "subject": sample}
        return {"title": title, "caption": caption, "size": image.size, "image": relative(thumbnail), "full": relative(full)}

    a4 = {row["id"]: row for row in json.loads((ART / "T09/manifest.json").read_text(encoding="utf-8"))
          if row.get("review_status") == "approved"}
    concepts = {}

    def design(identifier, *, bound=False):
        row = a4[identifier]
        source = (ART / "T09" / row["output"]).resolve()
        if digest(source) != row["sha256"]:
            raise ValueError(f"Changed A4 reference: {identifier}")
        concepts[identifier] = {"path": source.relative_to(ROOT).as_posix(), "sha256": row["sha256"],
                                "runtime_subject": identifier if bound else None, "checks": row["checks"]}
        return {"title": row["name"], "caption": "A4 设定 · 待接入", "size": row["actual_size"],
                "image": relative(source), "full": relative(source)}

    def subject_cards(group, crop):
        return [frame(f"route/subject_{key}", title, caption, subjects[key], crop)
                for key, (title, caption) in group.items()]

    station_titles = compiled["level"]["presentation"]["stations"]
    stations = [frame(f"route/station_{index}_{key}", title) for index, (key, title) in
                enumerate(zip(STATIONS, station_titles, strict=True), 1)]
    resident_subjects = dict(RESIDENTS)
    enemy_subjects = dict(ENEMIES)
    extra_subjects = {"umbrella_closed": ("墨伞收拢", "旧影院 · 收伞")}
    if full_cast:
        resident_subjects["ticket_clerk"] = ("检票员", "旧影院售票处")
        resident_subjects.update(cyclist=("骑车的人", "天桥上层 · 停车等候"), passerby_a=("路人 A", "火车站台 · 受困"))
        enemy_subjects["tadpole"] = ("墨蝌蚪", "夜市巷口 · 水洼小群")
        extra_subjects.update(bridge_warning=("天桥上下层", "桥下墨车夫响铃"),
                              passerby_a_saved=("路人 A 获救", "火车站台 · 致谢"))
        for identifier in ("cyclist", "passerby_a", "tadpole"):
            design(identifier, bound=True)
    else:
        extra_subjects["platform_clerk"] = ("站台检票员", "站台 · 同一造型")
    residents = subject_cards(resident_subjects, True)
    enemies = subject_cards(enemy_subjects, True)
    if not full_cast:
        residents.extend([design("cyclist"), design("passerby_a")])
        enemies.append(design("tadpole"))
    extra = dict(zip(extra_subjects, subject_cards(extra_subjects, not full_cast), strict=True))
    bosses = subject_cards(BOSSES, False)
    ui = [frame(stem, title) for stem, title in UI.items()]
    ui.insert(6, {**stations[10], "title": "空弹提示"})
    a4_link = (relative(ART / "T09/gallery/index.html"), "A4 设定审核")
    residents_links = [(extra["platform_clerk"]["full"], "站台检票员实战")] if not full_cast else [
        (extra["bridge_warning"]["full"], "天桥上下层 · 墨车夫响铃"),
        (extra["passerby_a_saved"]["full"], "站台路人 A 获救"),
    ]
    residents_text = ("三关出现 8 套居民造型。七位居民可获救，骑车的人在天桥上层等候。" if full_cast else
                      "三关出现 7 次救援，使用 6 套居民造型。骑车的人和路人 A 保留在 A4 设定。")
    enemy_text = ("七种墨怪均有实战画面。墨蝌蚪出现在巷口第六波后的水洼。" if full_cast else
                  "六种墨怪可在当前三关遇到。墨蝌蚪保留在 A4 设定。")
    report_sections = [
        section("market", "夜市", stations[:5], links=((relative(ART / "T10/report.md"), "夜市美术与回归"),)),
        section("cinema", "旧影院", stations[5:10], links=((relative(ART / "T12/report.md"), "旧影院美术与回归"),)),
        section("railway", "火车站与工作台", stations[10:], links=((relative(ART / "T13/gallery.html"), "第三关预审"),)),
        section("residents", "纸居民", residents, residents_text, [*residents_links, a4_link], True),
        section("enemies", "墨怪", enemies, enemy_text,
                ((extra["umbrella_closed"]["full"], "墨伞收拢实战"), (relative(ART / "T06/report.md"), "墨鸦与墨蝌蚪效果验证")), True),
        section("bosses", "三个 Boss", bosses, "截取各 Boss 有目标开放的战斗画面。",
                ((relative(ART / "T11/report.md"), "墨舞龙"), (relative(ART / "T12/report.md"), "银幕影"),
                 (relative(ART / "T13/gallery.html") + "#forget-boss", "忘字七笔"))),
        section("ui", "全套界面", ui, "开始、战斗、结算和显示设置均来自当前构建。",
                ((relative(ART / "T14/gallery.html"), "界面预审与实机清单"),)),
    ]
    hero = (frame("route/ending_wide_full", "片尾灯城全景")["full"] if full_cast else
            relative(ART / "T15/ending_wide_full.jpg"))
    status = ("A7 待验收。角色和界面的可读性、片尾混音及实体光枪仍待实测。" if full_cast else
              "A7 待验收。实体光枪、屏幕可读性、片尾混音与尚未接入的设定见交付报告。")
    template = Path(__file__).with_name("t16_gallery_template.html").read_text(encoding="utf-8")
    page = (template.replace("<!-- CAPTURES -->", "\n".join(report_sections)).replace("{{HERO_IMAGE}}", escape(hero))
            .replace("{{EPILOGUE_REPORT}}", escape(relative(ART / "T15/report.md"))).replace("{{REVIEW_STATUS}}", escape(status)))
    (output / "gallery.html").write_text(page, encoding="utf-8")
    write_json(output / "gallery_checks.json", {
        "package": package, "build_id": build_id, "source_revision": compiled["source_revision"], "engine": "Godot 4.6.3 Windows",
        "coverage": {"stations": len(stations), "resident_designs": len(residents),
                     "resident_designs_in_game": len(resident_subjects), "enemy_designs": len(enemies),
                     "enemy_types_in_game": len(enemy_subjects), "bosses": len(bosses), "ui_states": len(ui)},
        "route": route, "controls": controls, "display": display, "frames": records, "A4_designs": concepts,
    })
    print(f"Gallery assembled from {len(records)} Godot captures")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    args = parser.parse_args()
    build(args.build, args.captures)
