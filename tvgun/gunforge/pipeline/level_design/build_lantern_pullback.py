"""Author the in-engine pullback from the lantern base to the workbench."""
from math import floor

from build_cinema import after, remove, spawn
from build_lantern_base import LanternBase
from build_train_stop import ART
from compiler import ROOT, read


class LanternPullback(LanternBase):
    generated = ROOT / "gunforge/level_design/generated/lantern_pullback"

    def camera_plane(self, name, stage, z, keys):
        width, height = (self.source["layout"][axis] for axis in ("width", "height"))
        source = ART / "parallax" / stage / "render_source.png"
        plane = self.entity(name, "decoration", (0, 0, width, height), source, z=z, parallax=0)
        frames = []
        for time, scale, focus, opacity in keys:
            # Whole-pixel offsets and binary-fraction scales round-trip through the level loader.
            limits = [floor(size * (scale - 1) / 2) for size in (width, height)]
            x, y = [max(-limit, min(round(scale * (size / 2 - axis)), limit))
                    for axis, size, limit in zip(focus, (width, height), limits)]
            frames.append({"at_ms": time, "x": x, "y": y, "scale": scale, "opacity": opacity})
        plane["motion"] = {"easing": "smoothstep", "frames": frames}

    def author(self):
        super().author()
        self.source.update(id="paper.lantern_pullback", duration_ms=69000)
        self.presentation.update(subtitle="第三关 · 纸灯与工作台")
        self.presentation["labels"]["result_success"] = "抵达工作台"
        self.sections["pullback"] = {"index": 2, "title": "纸灯内部", "targets": []}
        self.sections["workbench"] = {"index": 3, "title": "爷爷的工作台", "targets": []}

        layers = self.presentation["layers"]
        for key, layer in tuple(layers.items()):
            if layer["section"] == self.stage:
                layers["pullback." + key] = dict(layer, section="pullback")
        self.stage_art("workbench", ART)

        interior = read(ART / "lantern_base_generation.json")["pullback_anchor_visual_estimate"]
        exterior = read(ART / "parallax/workbench/station.json")["anchors"]["pullback"]["point"]
        center = tuple(self.source["layout"][axis] / 2 for axis in ("width", "height"))
        inside, outside = "pullback.interior", "pullback.exterior"
        self.camera_plane(inside, self.stage, 90, (
            (0, 1, center, 0), (230, 1.03125, (888, 510), 1), (820, 2.8125, interior, 1),
            (1130, 2.8125, interior, 1), (1340, 2.8125, interior, 0),
        ))
        self.camera_plane(outside, "workbench", 91, (
            (0, 4.625, exterior, 0), (900, 4.625, exterior, 0), (1160, 4.625, exterior, 1),
            (2130, 1.078125, (850, 500), 1), (2330, 1, center, 1), (2530, 1, center, 0),
        ))

        # These two wait/enter pairs also let the shared renderer preload each next section.
        self.event("pullback.prepare", after("lantern_base.clear", 550), [{"op": "input", "enabled": False}])
        self.event("pullback.start", after("pullback.prepare", 0), [
            {"op": "section", "section": "pullback"}, spawn(inside), spawn(outside), {"op": "input", "enabled": False},
        ])
        self.event("workbench.prepare", after("pullback.start", 900), [{"op": "input", "enabled": False}])
        self.event("workbench.enter", after("workbench.prepare", 0), [
            {"op": "section", "section": "workbench"},
            *map(remove, ("lantern_base.lamp", "lantern_base.lamp_ink", "lantern_base.light")),
        ])
        self.event("pullback.settle", after("pullback.start", 2530), [remove(inside), remove(outside)])
        self.events["lantern_base.complete"]["trigger"] = after("pullback.settle", 850)
        return self.source


if __name__ == "__main__":
    LanternPullback().build()
