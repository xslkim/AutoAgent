"""Bring back the workbench lantern before the campaign result."""
import numpy as np
from PIL import Image

from build_cinema import after, remove, spawn, topic
from build_workbench_boss import WorkbenchBoss
from compiler import ROOT


class WorkbenchEnding(WorkbenchBoss):
    def lantern_light(self):
        layer = self.presentation["layers"]["workbench.paper_lantern"]
        x, y, width, height = (layer[key] for key in ("x", "y", "width", "height"))
        source = ROOT / self.resources[layer["resource"]]["path"]
        with Image.open(source) as image:
            rgba = np.array(image.convert("RGBA"))

        yy, xx = np.mgrid[:height, :width]
        distance = ((xx / width - .50) / .53)**2 + ((yy / height - .54) / .48)**2
        amount = (.68 * np.maximum(0, 1 - distance))[..., None]
        rgba[..., :3] = np.rint(rgba[..., :3] * (1 - amount) + np.array([249, 180, 88]) * amount)
        lit = self.write_image("ending_lit_paper", Image.fromarray(rgba))

        padding = 100
        halo_width, halo_height = width + 2 * padding, height + 2 * padding
        yy, xx = np.mgrid[:halo_height, :halo_width]
        distance = ((xx / halo_width - .50) / .50)**2 + ((yy / halo_height - .52) / .48)**2
        halo = Image.new("RGBA", (halo_width, halo_height), "#e4a864")
        halo.putalpha(Image.fromarray(np.uint8(49 * np.maximum(0, 1 - distance)**2)))
        halo_path = self.write_image("ending_lantern_halo", halo)

        lights = ("ending.halo", "ending.paper")
        for name, position, art, z in (
            (lights[0], (x - padding, y - padding, halo_width, halo_height), halo_path, 24),
            (lights[1], (x, y, width, height), lit, 25),
        ):
            px, py = position[:2]
            actor = self.entity(name, "decoration", position, art, z=z, parallax=layer["parallax"])
            actor["motion"] = {"easing": "smoothstep", "frames": [
                {"at_ms": time, "x": px, "y": py, "opacity": opacity}
                for time, opacity in ((0, 0), (550, .18), (1450, .75), (3100, 1))
            ]}
        return lights

    def author(self):
        super().author()
        self.source.update(id="paper.workbench_ending", duration_ms=147000)
        lights = self.lantern_light()
        glow_section, quote_section = "ending_light", "ending_quote"
        layers = self.presentation["layers"]
        workbench_layers = [(key, layer) for key, layer in layers.items() if layer["section"] == "workbench"]
        for section in (glow_section, quote_section):
            self.sections[section] = {"index": len(self.sections) + 1, "title": "爷爷的工作台",
                                      "targets": [], "skippable": True}
            for key, layer in workbench_layers:
                layers[f"{section}.{key}"] = dict(layer, section=section)
        for light in lights:
            actor = self.entities[light]
            layers[f"{quote_section}.{light}"] = {
                **{key: actor[key] for key in ("resource", "x", "y", "width", "height", "parallax")},
                "section": quote_section, "z": actor["properties"]["z"],
            }
        self.sections[quote_section]["hint"] = "灯亮着，就还在。"
        self.event("ending.light", after("forget.stroke_7.clear", 750), [
            {"op": "section", "section": glow_section},
            *(remove(target + ".residue") for target in self.sections["workbench"]["targets"]),
            *map(spawn, lights), {"op": "cue", "cue": "lamp"},
        ])
        show_quote = [*map(remove, lights), {"op": "section", "section": quote_section}]
        self.event("ending.quote", after("ending.light", 4600), show_quote)
        self.events["lantern_base.complete"]["trigger"] = after("ending.quote", 6200)
        self.event("ending.skip", topic("section.skipped"), [
            *show_quote,
            {"op": "complete", "result": "clear"},
        ])
        return self.source
