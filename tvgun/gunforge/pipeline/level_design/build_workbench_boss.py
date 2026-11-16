"""Author the seven-stroke boss after the lantern pullback."""
import hashlib

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, PngImagePlugin

from build_cinema import after, condition, permission, remove, spawn, topic
from build_lantern_pullback import LanternPullback
from build_train_stop import ART
from compiler import ROOT, read


STROKES = ART / "forget_strokes"
STROKE_HEALTH = 5
RISE_MS = 650
# Each stroke has a distinct windup time, ink stream width and contact point.
ATTACKS = (
    (2300, 54, [.50, .85]), (1950, 96, [.24, .87]), (1800, 74, [.76, .87]),
    (1600, 62, [.30, .80]), (1450, 124, [.53, .93]), (1300, 50, [.67, .79]),
    (1150, 105, [.48, .87]),
)


class WorkbenchBoss(LanternPullback):
    generated = ROOT / "gunforge/level_design/generated/workbench_boss"

    def stroke_images(self, row, display, grain, notice):
        mask_path = STROKES / row["source_mask"]
        if hashlib.sha256(mask_path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Workbench stroke mask has changed: {mask_path}")
        x, y, width, height = display
        with Image.open(mask_path) as source:
            mask = source.resize((width, height), Image.Resampling.LANCZOS)
        outer = mask.filter(ImageFilter.MaxFilter(13))
        crop = outer.getbbox()
        rim = ImageChops.subtract(outer, mask.filter(ImageFilter.MinFilter(3)))
        ink = Image.fromarray(np.uint8(grain))
        ink.putalpha(mask)
        outline = Image.new("RGBA", mask.size, "#d67c69")
        outline.putalpha(rim)
        start_x, start_y = row["start_marker"]
        px, py = start_x - x, start_y - y
        marker = ImageDraw.Draw(outline)
        marker.ellipse((px - 9, py - 9, px + 9, py + 9), fill="#d67c69")
        marker.ellipse((px - 4, py - 4, px + 4, py + 4), fill="#ebc58e")
        residue = Image.new("RGBA", mask.size, "#a1a2ac")
        residue.putalpha(mask.point(lambda alpha: alpha * 48 // 255))
        metadata = PngImagePlugin.PngInfo()
        metadata.add_itxt("Source", notice + " Added ink, outline, and residue for the workbench candidate.")
        assets = []
        for suffix, image in (("ink", ink), ("outline", outline), ("residue", residue)):
            path = self.generated / f"stroke_{row['order']:02d}_{suffix}.png"
            image.crop(crop).save(path, pnginfo=metadata)
            assets.append(path)
        left, top, right, bottom = crop
        return (x + left, y + top, right - left, bottom - top), assets

    def author(self):
        super().author()
        self.source.update(id="paper.workbench_boss", duration_ms=135000)
        self.presentation["labels"]["result_success"] = "灯城重新亮了"
        layout = read(STROKES / "geometry.json")
        display = layout["display_rect"]
        width, height = display[2:]
        random = np.random.default_rng(435)
        flecks = random.integers(0, 6, (height, width), dtype=np.uint8)
        wash = Image.fromarray(random.integers(0, 15, (30, 30), dtype=np.uint8))
        fibers = Image.fromarray(random.integers(0, 10, (200, 18), dtype=np.uint8))
        grain = flecks + np.asarray(wash.resize((width, height), Image.Resampling.BICUBIC))
        grain += np.asarray(fibers.resize((width, height), Image.Resampling.BILINEAR))
        grain = grain[..., None] + np.array([16, 18, 30])

        # The invisible first pose lets the workbench cut preload the seven ink textures.
        cut_delay = self.events["workbench.prepare"]["trigger"]["delay_ms"]
        settle_delay = self.events["pullback.settle"]["trigger"]["delay_ms"]
        rise_start = settle_delay - cut_delay

        targets = []
        for row in layout["strokes"]:
            order = row["order"]
            name = f"forget.stroke_{order}"
            targets.append(name)
            rect, (ink, outline, residue) = self.stroke_images(row, display, grain, layout["source_notice"])
            z = 32 + 3 * row["z_order"]
            target = self.entity(name, "target", rect, ink, z=z, hits=STROKE_HEALTH, weak_damage=STROKE_HEALTH)
            # Use the same alpha raster for ink coverage and hits, including the 2/3 crossing.
            target["hit_resource"] = target["resource"]
            x, y = rect[:2]
            target["motion"] = {"easing": "smoothstep", "frames": [
                {"at_ms": 0, "x": x, "y": y + 100, "opacity": 0},
                {"at_ms": rise_start, "x": x, "y": y + 100, "opacity": 0},
                {"at_ms": rise_start + RISE_MS, "x": x, "y": y, "opacity": 1},
            ]}
            cue = self.entity(name + ".outline", "decoration", rect, outline, z=z + 1)
            cue["motion"] = {"easing": "smoothstep", "frames": [
                {"at_ms": index * 340, "x": rect[0], "y": rect[1], "opacity": opacity}
                for index, opacity in enumerate((1, .5) * 12 + (1,))
            ]}
            self.entity(name + ".residue", "decoration", rect, residue, z=30)

        self.sections["workbench"].update(targets=targets, hint="跟着朱砂描边和落笔光点，逐笔净化。")
        self.source["effects"]["forget.wrong"] = {"kind": "pulse", "duration_ms": 360,
                                                     "color": "#aaa9b3", "radius": 75}
        workbench = self.events["workbench.enter"]
        self.event("workbench.enter", workbench["trigger"], [
            *(workbench["actions"][key] for key in workbench["order"]),
            *map(spawn, targets), *(permission(target, "invalid") for target in targets),
        ])
        self.event("forget.start", after("pullback.settle", RISE_MS), [{"op": "input", "enabled": True}])
        previous = "forget.start"
        for target, (delay, radius, destination) in zip(targets, ATTACKS, strict=True):
            ready, clear = target + ".ready", target + ".clear"
            outline = target + ".outline"
            locked = [condition(target, "active", True), condition(outline, "active", False)]
            self.event(ready, after(previous, 0), [permission(target, "weak"), spawn(outline)])
            self.event(target + ".wrong", topic("target.blocked", target), [
                {"op": "vfx", "entity": target, "effect": "forget.wrong"},
            ], locked, limit=100)
            self.event(target + ".graze", topic("target.blocked", target), [
                {"op": "set", "entity": target, "field": "health", "value": STROKE_HEALTH - 1},
            ], [*locked, condition(target, "health", STROKE_HEALTH)])
            actions = [remove(outline), spawn(target + ".residue"),
                       {"op": "resource_add", "resource": "score", "amount": 100}]
            if target == targets[-1]:
                actions.append({"op": "input", "enabled": False})
            self.event(clear, topic("target.neutralized", target), actions)
            attack = target + ".ink"
            self.source["effects"][attack] = {"kind": "attack_release", "duration_ms": 550, "color": "#a786c5",
                                               "radius": radius, "anchor_uv": destination}
            for attempt in range(5):
                self.strike(target, f"{target}.attack_{attempt + 1}", ready, delay + attempt * 3400, attack)
            previous = clear
        self.events["lantern_base.complete"]["trigger"] = after(previous, 1150)
        return self.source


if __name__ == "__main__":
    WorkbenchBoss().build()
