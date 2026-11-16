"""Rasterize and verify the seven-stroke workbench boss layout."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
from scipy import ndimage

from artlib import GAME, ROOT, digest, effective_radius, write_json
from t10_preview import read_json
from t10_whitebox import intersects
from t12_whitebox import within


REPORT = GAME / "reports/art/T13"
OUT = REPORT / "forget_strokes"
SOURCE = OUT / "forget-graphics.json"
LICENSE = OUT / "ARPHICPL.TXT"
REVISION = "bddc96d41bef78427ed0e034e9f7e31d71fd1b92"
SOURCE_SHA256 = "3928672ce313fdc82c7ec425571356d394778c678c787a60220ac3d18fdeecb1"
LICENSE_SHA256 = "3a5e90c0957524a89e48203febcd4492ca4393678abaa7e5b4d70f3ff32b386d"
SIZE = 2048
LABELS = ("亡 · 点", "亡 · 横", "亡 · 竖折", "心 · 左点", "心 · 卧钩", "心 · 中点", "心 · 右点")
EXPANSION_PX = (16, 0, 0, 16, 0, 18, 0)
COLORS = ("#bd644b", "#247d80", "#5f598a", "#975736", "#467953", "#ad5269", "#775d43")
NOTICE = ("2026-11-11: Rasterized and resized the Make Me a Hanzi U+5FD8 outlines for Gunforge, "
          "with adjusted short-stroke width. Copyright (C) 1999 Arphic Technology Co., Ltd. "
          "Arphic Public License, see ARPHICPL.TXT.")

SVG_RENDERER = '''extends SceneTree
func _initialize() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    for index in range(1, 8):
        var base := folder.path_join(str(index))
        var image := Image.new()
        if image.load_svg_from_string(FileAccess.get_file_as_string(base + ".svg")) != OK:
            quit(1)
            return
        if image.save_png(base + ".png") != OK:
            quit(1)
            return
    quit()
'''


def rasterize(paths):
    godot = Path(os.environ.get("GODOT_BIN", ROOT.parent / "gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe"))
    with TemporaryDirectory() as temp:
        scratch = Path(temp)
        script = scratch / "rasterize.gd"
        script.write_text(SVG_RENDERER, encoding="utf-8")
        for index, path in enumerate(paths, 1):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 1024 1024">'
                   f'<path transform="scale(1,-1) translate(0,-900)" d="{path}" fill="white"/></svg>')
            (scratch / f"{index}.svg").write_text(svg, encoding="utf-8")
        subprocess.run([str(godot), "--headless", "--path", str(ROOT / "gunforge/framework"), "--script", str(script),
                        "--", str(scratch)], check=True, timeout=60)
        masks = []
        for index, expansion in enumerate(EXPANSION_PX, 1):
            with Image.open(scratch / f"{index}.png") as frame:
                if frame.size != (SIZE, SIZE):
                    raise ValueError("SVG render size differs from the stroke canvas")
                mask = np.array(frame.convert("RGBA").getchannel("A")) >= 128
            if expansion:
                mask = ndimage.distance_transform_edt(~mask) <= expansion
            masks.append(mask)
    return masks


def mask_image(mask):
    return Image.fromarray(mask.astype("uint8") * 255)


def place_hit_geometry(masks, region, medians):
    x, y, width, height = region
    scaled = [np.asarray(mask_image(mask).resize((width, height), Image.Resampling.LANCZOS)) >= 128 for mask in masks]
    owners = np.zeros((height, width), dtype=np.uint8)
    for index, mask in enumerate(scaled, 1):
        owners[mask] = index
    strokes = []
    for index, mask in enumerate(scaled, 1):
        if ndimage.label(mask)[1] != 1:
            raise ValueError(f"Stroke {index} is disconnected at display size")
        visible = owners == index
        radius, opened = effective_radius(visible)
        if radius < 40:
            raise ValueError(f"Stroke {index} has only {radius:.2f} px of effective radius after occlusion")
        yy, xx = np.nonzero(opened)
        start_x, start_y = medians[index - 1][0]
        start = np.argmin((xx - start_x * width / 1024) ** 2 + (yy - (900 - start_y) * height / 1024) ** 2)
        strokes.append({"order": index, "label": LABELS[index - 1], "z_order": index,
                        "source_mask": f"stroke_{index:02d}.png", "outline_expansion_px_at_2048": EXPANSION_PX[index - 1],
                        "area_before_occlusion_px": int(mask.sum()), "visible_area_px": int(visible.sum()),
                        "effective_area_px": int(opened.sum()), "effective_radius_px": round(radius, 2),
                        "start_marker": [int(x + xx[start]), int(y + yy[start])],
                        "overlapped_by": [{"order": other, "overlap_area_px": int(np.count_nonzero(mask & upper))}
                                          for other, upper in enumerate(scaled, 1) if other > index and (mask & upper).any()]})
    return scaled, owners, strokes


def review_images(scaled, owners, strokes, region, canvas):
    x, y, width, height = region
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 28) if font_path.exists() else ImageFont.load_default(26)
    small = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default(20)
    for name, numbered in (("glyph", False), ("stroke_order", True)):
        frame = Image.new("RGB", canvas, "#25292b")
        draw = ImageDraw.Draw(frame)
        draw.rectangle((x, y, x + width, y + height), fill="#e8dfcd", outline="#aca48e", width=2)
        draw.text((x, y - 52), "工作台 · 忘字七笔遮罩", font=font, fill="#e8dfcd")
        for index, mask in enumerate(scaled, 1):
            color = COLORS[index - 1] if numbered else "#302725"
            frame.paste(color, (x, y, x + width, y + height), mask_image(mask))
        if numbered:
            for index, row in enumerate(strokes):
                marker_x, marker_y = row["start_marker"]
                if owners[marker_y-y, marker_x-x] != row["order"]:
                    raise ValueError("The start marker must stay on its visible stroke")
                draw.ellipse((marker_x-15, marker_y-15, marker_x+15, marker_y+15), fill="#f6f0e3", outline="#282625", width=2)
                draw.text((marker_x, marker_y), str(row["order"]), font=small, fill="#292522", anchor="mm")
                legend_y = y + 50 + index * 54
                draw.rectangle((x+width+46, legend_y+4, x+width+68, legend_y+26), fill=COLORS[index])
                draw.text((x+width+82, legend_y), f"{row['order']}  {row['label']}  {row['effective_radius_px']:.1f} px",
                          font=small, fill="#e8dfcd")
            draw.text((x+width+46, y+462), "交叉处后写笔画在上", font=small, fill="#e8dfcd")
        draw.text((x, y+height+25), "Make Me a Hanzi · Arphic Public License · 2026-11-11 遮罩改制", font=small, fill="#c5bba8")
        frame.save(OUT / f"{name}.jpg", quality=96, subsampling=0, comment=NOTICE.encode())


def main():
    if digest(SOURCE) != SOURCE_SHA256 or digest(LICENSE) != LICENSE_SHA256:
        raise ValueError("The pinned source record or license text changed")
    source = read_json(SOURCE)
    if source["character"] != "忘" or len(source["strokes"]) != 7 or len(source["medians"]) != 7:
        raise ValueError("Expected the seven ordered outlines of U+5FD8")
    stage = next(stage for stage in read_json(REPORT / "layouts.json")["stations"] if stage["id"] == "workbench")
    hud = read_json(GAME / "assets/ui/hud_layout.json")
    width, height = hud["content_size"]
    edge = hud["edge_band"]
    region = stage["boss_region"]
    blocked = stage["cover"] + [slot["rect"] for slot in hud["reserved"].values() if slot["when"] == "playing"]
    if not within(region, (edge, edge, width - 2*edge, height - 2*edge)) or any(intersects(region, rect) for rect in blocked):
        raise ValueError("The workbench glyph overlaps the HUD, cover, or safety margin")
    masks = rasterize(source["strokes"])
    scaled, owners, strokes = place_hit_geometry(masks, region, source["medians"])
    for mask, row in zip(masks, strokes, strict=True):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Source and changes", NOTICE)
        path = OUT / row["source_mask"]
        mask_image(mask).save(path, pnginfo=metadata)
        row["sha256"] = digest(path)
    review_images(scaled, owners, strokes, region, (width, height))
    write_json(OUT / "geometry.json", {"status": "passed_pending_review", "character": "忘", "canvas": [SIZE, SIZE],
               "display_rect": region, "source_revision": REVISION, "source_sha256": SOURCE_SHA256,
               "license_sha256": LICENSE_SHA256, "source_notice": NOTICE,
               "occlusion": "higher stroke order covers lower stroke order", "strokes": strokes,
               "jpg_sha256": {name: digest(OUT / name) for name in ("glyph.jpg", "stroke_order.jpg")}})
    print("Effective radii at display size:", [row["effective_radius_px"] for row in strokes])


if __name__ == "__main__":
    main()
