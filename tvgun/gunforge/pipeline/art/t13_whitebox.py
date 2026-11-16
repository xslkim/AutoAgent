"""Check and draw the train-station composition guides."""
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from artlib import GAME, digest, write_json
from t10_preview import read_json, save_jpg
from t10_whitebox import intersects, render
from t12_whitebox import prepare, within


REPORT = GAME / "reports/art/T13"


def main():
    layout = read_json(GAME / "assets/ui/hud_layout.json")
    stages = read_json(REPORT / "layouts.json")["stations"]
    output = REPORT / "whiteboxes"
    output.mkdir(exist_ok=True)
    width, height = layout["content_size"]
    edge = layout["edge_band"]
    safe = (edge, edge, width - 2 * edge, height - 2 * edge)
    playing_hud = [item["rect"] for item in layout["reserved"].values() if item["when"] == "playing"]
    results = {}
    with TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        for stage in stages:
            box, checks = prepare(stage, layout)
            if any(resident["rect"][3] < 300 for resident in stage["residents"]):
                raise ValueError(f"{stage['id']}: protected resident needs 300 px of height")
            if "boss_region" in stage:
                region = stage["boss_region"]
                blocked = stage["cover"] + playing_hud + [feature["rect"] for feature in stage["features"]]
                if region[2] != region[3] or not within(region, safe) or any(intersects(region, rect) for rect in blocked):
                    raise ValueError("The seven-stroke canvas needs a clear square on the workbench")
                box["features"] = stage["features"] + [{"rect": region, "label": "七笔 Boss 占位"}]
                box["legend"] = "上方方框 = 字形占位　下方砚台为背景"
                checks["boss_canvas_clear"] = True
            render(box, layout, scratch)
            jpg = output / f"{stage['id']}.jpg"
            with Image.open(scratch / f"{stage['id']}.png") as frame:
                save_jpg(frame.convert("RGB"), jpg)
            checks["preview_sha256"] = digest(jpg)
            results[stage["id"]] = checks
    write_json(REPORT / "whitebox_checks.json", {"status": "passed", "scope": "provisional geometry", "stations": results})
    print(f"{len(results)} train-station whiteboxes validated")


if __name__ == "__main__":
    main()
