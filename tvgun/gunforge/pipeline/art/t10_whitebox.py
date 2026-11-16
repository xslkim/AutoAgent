"""Render provisional stage layouts in canonical content coordinates."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from artlib import GAME

REPORT = GAME / "reports/art/T10"


def xyxy(rect):
    x, y, w, h = rect
    return x, y, x + w, y + h


def intersects(a, b):
    x, y, r, d = xyxy(a)
    X, Y, R, D = xyxy(b)
    return x < R and X < r and y < D and Y < d


def render(stage, layout, output):
    width, height = layout["content_size"]
    edge = layout["edge_band"]
    reserved = layout["reserved"]
    safe = (edge, edge, width - edge, height - edge)
    protected = stage.get("protected", [])
    lights = [stage["light"]] if "light" in stage else stage.get("lights", [])
    for rect in stage["targets"] + [light["rect"] for light in lights]:
        x, y, r, d = xyxy(rect)
        assert x >= safe[0] and y >= safe[1] and r <= safe[2] and d <= safe[3], (stage["id"], rect)
        blockers = stage["cover"] + protected + [
            hud["rect"] for hud in reserved.values() if hud["when"] == "playing"
        ]
        assert not any(intersects(rect, blocker) for blocker in blockers), (stage["id"], rect)

    img = Image.new("L", (width, height), 32)
    draw = ImageDraw.Draw(img)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 28) if font_path.exists() else ImageFont.load_default(size=25)
    draw.rectangle(safe, fill=78, outline=150, width=2)
    draw.rectangle((edge, 480, width - edge, height - edge), fill=64)
    for rect in stage["midground"]:
        draw.rectangle(xyxy(rect), fill=51, outline=120, width=2)
    for feature in stage.get("features", []):
        x, y, _, _ = feature["rect"]
        draw.rectangle(xyxy(feature["rect"]), fill=51, outline=156, width=2)
        draw.text((x + 8, y + 5), feature["label"], fill=197, font=font)
    for beam in stage.get("beams", []):
        draw.polygon([tuple(point) for point in beam], outline=104, width=2)
    for rect in stage["cover"]:
        draw.rectangle(xyxy(rect), fill=24, outline=122, width=3)
    for index, rect in enumerate(stage["targets"], 1):
        draw.rectangle(xyxy(rect), outline=184, width=3)
        draw.text((rect[0] + 8, rect[1] + 8), f"T{index}", fill=230, font=font)
    for rect in protected:
        draw.rectangle(xyxy(rect), outline=140, width=4)
        draw.text((rect[0] + 8, rect[1] + 8), "NPC", fill=208, font=font)
    for light in lights:
        draw.ellipse(xyxy(light["range"]), outline=117, width=3)
        lamp = light["rect"]
        draw.rectangle(xyxy(lamp), fill=110, outline=232, width=4)
        draw.text((lamp[0] + 8, lamp[1] + 8), light["kind"], fill=240, font=font)
    for name, hud in reserved.items():
        rect = hud["rect"]
        draw.rectangle(xyxy(rect), outline=105 if name == "subtitle" else 199, width=2)
        draw.text((rect[0] + 6, rect[1] + 5), name, fill=167, font=font)
    draw.text((edge + 6, 16), stage["title"], fill=237, font=font)
    legend = stage.get("legend", "T = 敌人活动区　NPC = 保护区　椭圆 = 预留光区")
    draw.text((edge + 6, 888), legend, fill=200, font=font)
    img.save(output / f"{stage['id']}.png")


def main():
    data = json.loads((REPORT / "layouts.json").read_text(encoding="utf-8"))
    layout = json.loads((GAME / "assets/ui/hud_layout.json").read_text(encoding="utf-8"))
    output = REPORT / "whiteboxes"
    output.mkdir(exist_ok=True)
    for stage in data["stations"]:
        render(stage, layout, output)
    print(f"{len(data['stations'])} whiteboxes rendered; target, foreground cover, edge and HUD geometry checked")


if __name__ == "__main__":
    main()
