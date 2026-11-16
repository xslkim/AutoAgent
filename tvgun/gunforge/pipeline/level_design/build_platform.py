"""Build the train platform's signal, umbrella and rescue encounter."""
from build_cinema import ART as CINEMA_ART, permission, spawn
from build_train_stop import ART, LIGHT_DURATION, TrainStop
from compiler import ROOT


class Platform(TrainStop):
    stage = "platform"
    generated = ROOT / "gunforge/level_design/generated/platform"
    resident_name = "检票员"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.platform", seed=431, duration_ms=75000)
        self.presentation.update(subtitle="第三关 · 站台", instructions=f"拦截左侧墨鸦 · 射亮信号灯 · 救出{self.resident_name}")
        self.presentation["labels"].update(result_success="站台安全了", result_failure="站台陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"]["light_fx"].update(label="信号亮", radius=108)
        self.source["effects"].update({
            "crow_release": {"kind": "attack_release", "duration_ms": 560, "color": "#e5726e", "radius": 84,
                             "anchor_uv": [.31, .98]},
            "umbrella_release": {"kind": "attack_release", "duration_ms": 510, "color": "#a786c5", "radius": 76,
                                  "anchor_uv": [.72, .98]},
        })

    def crow_patrol(self, lane):
        identifier = self.crow(lane)
        entity = self.entities[identifier]
        left, top = entity["x"], entity["y"]
        path = ((0, left - 30, top, -.08), (1150, left + 35, top - 24, .06),
                (3400, left + 14, top - 18, -.08), (4700, left + 40, top + 2, .14),
                (6200, left - 31, top - 9, -.05), (8100, left + 15, top - 22, .04))
        entity["motion"] = {"frames": [{"at_ms": time, "x": x, "y": y, "rotation_rad": angle}
                                       for time, x, y, angle in path]}
        return identifier

    def platform_resident(self, data):
        return self.resident(self.stage, data, CINEMA_ART)

    def author(self):
        stage = self.stage
        row = self.prepare_stop()
        lamp, light, influence, ink = self.stage_art(stage, ART, ink_variant=1, light_ms=LIGHT_DURATION)
        crow = self.crow_patrol(row["lanes"][0]["rect"])
        x, y, width, height = row["lanes"][1]["rect"]
        # Move the encounter up the platform into the right-hand signal's actual spill.
        umbrella, canopy = self.umbrella(stage, (x + 105, y - 42, width, height))
        self.entities[umbrella]["mask_permission"] = {"source": light, "resource": influence, "threshold": .13}
        self.presentation["entity_tints"][umbrella] = {"invalid": "#657198"}
        self.presentation["entity_state_labels"][umbrella] = {"invalid": "硬化 · 射信号灯", "primary": "软化 · 射击"}
        resident, rescue = self.platform_resident(row["residents"][0])
        targets = [crow, umbrella, rescue]
        self.sections[stage] = {"index": 1, "title": row["title"], "targets": targets,
                                "hint": f"左侧墨鸦可直接打。点亮信号灯，等右侧墨伞收伞；只打{self.resident_name}胸口的墨团。"}
        self.event(f"{stage}.start", {"at_ms": 0}, [{"op": "section", "section": stage},
                   *map(spawn, (lamp, ink, crow, canopy, resident, rescue)), permission(canopy, "invalid")])
        self.bind_lamp(lamp, light)
        for number, delay in enumerate((3000, 8300, 14100), 1):
            self.strike(crow, f"{stage}.crow{number}", f"{stage}.start", delay, "crow_release")
        for number, delay in enumerate((3800, 9500), 1):
            self.strike(umbrella, f"{stage}.umbrella{number}", f"{stage}.fold", delay, "umbrella_release")
        self.finish(targets)
        return self.source


if __name__ == "__main__":
    Platform().build()
