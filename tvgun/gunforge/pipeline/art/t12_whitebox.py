"""Validate second-level composition guides and render the cinema whiteboxes."""
from itertools import combinations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from artlib import GAME, effective_radius, write_json
from t10_preview import read_json, save_jpg
from t10_whitebox import intersects, render, xyxy


REPORT = GAME / "reports/art/T12"


def within(rect, region):
    x, y, r, b = xyxy(rect)
    left, top, right, bottom = xyxy(region)
    return x < r and y < b and x >= left and y >= top and r <= right and b <= bottom


def point_in(point, region):
    x, y, r, b = xyxy(region)
    return x <= point[0] < r and y <= point[1] < b


def ellipse_radius(rect):
    width, height = rect[2:]
    mask = Image.new("L", (width, height))
    ImageDraw.Draw(mask).ellipse((0, 0, width - 1, height - 1), fill=255)
    radius, _ = effective_radius(np.asarray(mask) >= 128)
    return round(radius, 2)


def boss_objects(boss, stage):
    projectors = boss["projectors"]
    if len(projectors) != 3:
        raise ValueError("Silver Screen Shadow requires three projectors")
    if not within(boss["core"]["rect"], boss["screen"]):
        raise ValueError("The shadow core must stay on the screen")
    for projector in projectors:
        if not point_in(projector["lens"], projector["rect"]):
            raise ValueError(f"{projector['id']} lens must sit inside the projector")
        if not all(point_in(point, boss["screen"]) for point in projector["screen_span"]):
            raise ValueError(f"{projector['id']} beam must land on the screen")
    targets = [projector["reel"] for projector in projectors] + [boss["core"]]
    blockers = [projector["rect"] for projector in projectors]
    if stage["lights"]:
        raise ValueError("The boss stage must distinguish non-shootable projectors from lamps")
    return targets, blockers


def prepare(stage, layout):
    boss = stage.get("boss")
    targets, machines = boss_objects(boss, stage) if boss else (stage["lanes"], [])
    residents = stage["residents"]
    lights = stage["lights"]
    width, height = layout["content_size"]
    edge = layout["edge_band"]
    safe = (edge, edge, width - 2 * edge, height - 2 * edge)
    hud = [item["rect"] for item in layout["reserved"].values() if item["when"] == "playing"]
    blockers = [*stage["cover"], *machines, *hud]
    interactive = [*targets, *lights, *residents]
    if len({item["id"] for item in interactive}) != len(interactive):
        raise ValueError(f"{stage['id']}: duplicate layout IDs")
    for item in interactive:
        rect = item["rect"]
        if not within(rect, safe) or any(intersects(rect, blocked) for blocked in blockers):
            raise ValueError(f"{stage['id']}: {item['id']} intersects a reserved or blocked region")
    for a, b in combinations(interactive, 2):
        if intersects(a["rect"], b["rect"]):
            raise ValueError(f"{stage['id']}: {a['id']} intersects {b['id']}")
    for light in lights:
        if not within(light["range"], (0, 0, width, height)) or not within(light["rect"], light["range"]):
            raise ValueError(f"{stage['id']}: {light['id']} lies outside its light range")
    radii = {item["id"]: ellipse_radius(item["rect"]) for item in ([*targets, *lights] if boss else lights)}
    if any(value < 40 for value in radii.values()):
        raise ValueError(f"{stage['id']}: an elliptical prop or boss target is too small")
    box = {**stage, "targets": [item["rect"] for item in targets], "protected": [item["rect"] for item in residents]}
    if boss:
        box["features"] = [{"rect": p["rect"], "label": f"放映机 {i} · 不可射"}
                           for i, p in enumerate(boss["projectors"], 1)]
        box["beams"] = [[p["lens"], *p["screen_span"]] for p in boss["projectors"]]
        box["legend"] = "T1–T3 = 胶片盘墨渍　T4 = 影核（清完三盘后开放）"
    checks = {"target_lanes": len(targets) if not boss else 0, "lights": len(lights), "residents": len(residents),
              "projectors": len(machines), "ellipse_radius_px": radii,
              "reserved_and_pairwise_overlap": "pass"}
    return box, checks


def render_beam_states(boss, view_size, output):
    windows_font = ImageFont.load_default(size=30)
    try:
        windows_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 28)
    except OSError:
        pass
    phases = (
        ("shadow_0", (), "清除胶片盘上的墨渍　·　放映机本体不可射"),
        ("shadow_1", ("reel_left",), "左盘净化　·　只有左侧光束恢复暖色"),
        ("shadow_3", ("reel_left", "reel_center", "reel_right"), "三盘净化完成　·　银幕影核开放"),
    )
    for name, cleaned, caption in phases:
        frame = Image.new("RGB", view_size, "#262238")
        draw = ImageDraw.Draw(frame)
        draw.rectangle(xyxy(boss["screen"]), fill="#4e4662", outline="#8b7d99", width=3)
        draw.ellipse((595, 176, 1175, 533), fill="#333041")
        for i, projector in enumerate(boss["projectors"], 1):
            reel = projector["reel"]
            warm = reel["id"] in cleaned
            draw.polygon([tuple(point) for point in (projector["lens"], *projector["screen_span"])],
                         fill="#966b4b" if warm else "#46456b")
            draw.rectangle(xyxy(projector["rect"]), fill="#3f3d52", outline="#888398", width=3)
            x, y, _, _ = projector["rect"]
            draw.text((x + 12, y + 61), f"放映机 {i}", font=windows_font, fill="#c5bbc9")
            draw.ellipse(xyxy(reel["rect"]), fill="#93745e" if warm else "#191722",
                         outline="#a68b78" if warm else "#bc6f8b", width=4)
        if len(cleaned) == 3:
            draw.ellipse(xyxy(boss["core"]["rect"]), fill="#a4383c", outline="#c9706e", width=4)
        draw.text((66, 42), caption, font=windows_font, fill="#d6cad5")
        save_jpg(frame, output / f"{name}.jpg")


def main():
    layout = read_json(GAME / "assets/ui/hud_layout.json")
    stages = read_json(REPORT / "layouts.json")["stations"]
    output = REPORT / "whiteboxes"
    output.mkdir(exist_ok=True)
    results = {}
    for stage in stages:
        box, checks = prepare(stage, layout)
        render(box, layout, output)
        path = output / f"{stage['id']}.png"
        with Image.open(path) as image:
            save_jpg(image.convert("RGB"), path.with_suffix(".jpg"))
        if "boss" in stage:
            render_beam_states(stage["boss"], tuple(layout["content_size"]), output)
        results[stage["id"]] = checks
    write_json(REPORT / "whitebox_checks.json", {"status": "passed", "scope": "provisional geometry", "stations": results})
    print(f"{len(results)} cinema whiteboxes validated")


if __name__ == "__main__":
    main()
