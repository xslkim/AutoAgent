"""Build the last train-station combat stop inside the lantern base."""
from build_cinema import permission, spawn
from build_train_stop import ART, LIGHT_DURATION, TrainStop
from compiler import ROOT


class LanternBase(TrainStop):
    stage = "lantern_base"
    generated = ROOT / "gunforge/level_design/generated/lantern_base"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.lantern_base", seed=433, duration_ms=65000)
        del self.source["initial_resources"]["rescued"]
        self.source["hud"] = [field for field in self.source["hud"] if field["resource"] != "rescued"]
        self.presentation.update(subtitle="第三关 · 灯座", instructions="射亮中央站灯 · 拦截右侧墨鸦 · 等左侧墨伞收伞")
        self.presentation["labels"].update(result_success="灯座清空了", result_failure="灯座陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"]["light_fx"].update(label="站灯亮", radius=112)
        self.source["effects"].update({
            "crow_release": {"kind": "attack_release", "duration_ms": 560, "color": "#e5726e", "radius": 84,
                             "anchor_uv": [.64, .98]},
            "umbrella_release": {"kind": "attack_release", "duration_ms": 510, "color": "#a786c5", "radius": 76,
                                  "anchor_uv": [.35, .98]},
        })

    def crow_patrol(self, lane):
        identifier = self.crow(lane)
        entity = self.entities[identifier]
        x, y = entity["x"], entity["y"]
        inside = (x - 164, y - 45)
        path = ((0, x, y, .09), (830, x + 18, y - 10, -.08), (1610, *inside, -.03),
                (3500, *inside, .07), (4900, inside[0] - 18, inside[1] + 18, -.15),
                (6230, x, y, .06), (7720, *inside, -.03), (10100, *inside, .04))
        entity["motion"] = {"frames": [{"at_ms": time, "x": px, "y": py, "rotation_rad": angle}
                                       for time, px, py, angle in path]}
        return identifier

    def author(self):
        stage = self.stage
        row = self.prepare_stop(rescue=False)
        lamp, light, influence, ink = self.stage_art(stage, ART, ink_variant=1, light_ms=LIGHT_DURATION)
        lanes = {lane["actor"]: lane["rect"] for lane in row["lanes"]}
        crow = self.crow_patrol(lanes["墨鸦"])
        x, y, width, height = lanes["墨伞"]
        # Place the exposed umbrella at the left edge of the central spill.
        umbrella, canopy = self.umbrella(stage, (x + 125, y - 52, width, height))
        targets = [crow, umbrella]
        for target in targets:
            self.entities[target]["mask_permission"] = {"source": light, "resource": influence, "threshold": .16}
            self.presentation["entity_tints"][target] = {"invalid": "#657198"}
            self.presentation["entity_state_labels"][target] = {"invalid": "硬化 · 射站灯", "primary": "软化 · 射击"}
        self.sections[stage] = {"index": 1, "title": row["title"], "targets": targets,
                                "hint": "中央站灯能软化两侧墨怪。等墨鸦进光、墨伞收伞，再净化。"}
        self.event(f"{stage}.start", {"at_ms": 0}, [{"op": "section", "section": stage},
                   *map(spawn, (lamp, ink, crow, canopy)), permission(canopy, "invalid")])
        self.bind_lamp(lamp, light)
        for number, delay in enumerate((3450, 8800, 14400), 1):
            self.strike(crow, f"{stage}.crow{number}", f"{stage}.start", delay, "crow_release")
        for number, delay in enumerate((3500, 9300), 1):
            self.strike(umbrella, f"{stage}.umbrella{number}", f"{stage}.fold", delay, "umbrella_release")
        self.finish(targets)
        return self.source


if __name__ == "__main__":
    LanternBase().build()
