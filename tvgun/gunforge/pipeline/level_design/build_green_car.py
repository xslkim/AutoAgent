"""Build the green train car encounter with real seat occlusion and ceiling light."""
from build_cinema import permission, spawn
from build_train_stop import ART, LIGHT_DURATION, TrainStop
from compiler import ROOT


class GreenCar(TrainStop):
    stage = "green_car"
    generated = ROOT / "gunforge/level_design/generated/green_car"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.green_car", seed=432, duration_ms=65000)
        del self.source["initial_resources"]["rescued"]
        self.source["hud"] = [field for field in self.source["hud"] if field["resource"] != "rescued"]
        self.presentation.update(subtitle="第三关 · 绿皮车厢", instructions="射亮顶灯 · 拦截飞入灯光的墨鸦 · 等墨伞收伞")
        self.presentation["labels"].update(result_success="车厢安全了", result_failure="车厢陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"]["light_fx"].update(label="顶灯亮", radius=118)
        self.source["effects"].update({
            "crow_release": {"kind": "attack_release", "duration_ms": 560, "color": "#e5726e", "radius": 84,
                             "anchor_uv": [.36, .98]},
            "umbrella_release": {"kind": "attack_release", "duration_ms": 510, "color": "#a786c5", "radius": 76,
                                  "anchor_uv": [.68, .98]},
        })

    def crow_patrol(self, lane, light, influence):
        identifier = self.crow(lane)
        entity = self.entities[identifier]
        left, top = entity["x"], entity["y"]
        outside = (left - 48, top + 66)
        inside = (left + 75, top - 58)
        # Start behind the left seat and rise into the actual overhead spill.
        path = ((0, 115, 590, -.13), (410, 145, 553, -.19), (980, *outside, -.12),
                (1690, *inside, .04), (3550, *inside, -.06),
                (4850, inside[0] + 16, inside[1] + 14, .17), (6100, *outside, .09),
                (7490, *inside, .03), (10000, *inside, -.05))
        entity["motion"] = {"frames": [{"at_ms": time, "x": x, "y": y, "rotation_rad": angle}
                                       for time, x, y, angle in path]}
        entity["mask_permission"] = {"source": light, "resource": influence, "threshold": .16}
        self.presentation["entity_tints"][identifier] = {"invalid": "#657198"}
        self.presentation["entity_state_labels"][identifier] = {"invalid": "硬化", "primary": "软化 · 射击"}
        return identifier

    def author(self):
        stage = self.stage
        row = self.prepare_stop(rescue=False)
        lamp, light, influence, ink = self.stage_art(stage, ART, ink_variant=2, light_ms=LIGHT_DURATION)
        crow = self.crow_patrol(row["lanes"][0]["rect"], light, influence)
        umbrella, canopy = self.umbrella(stage, row["lanes"][1]["rect"])
        targets = [crow, umbrella]
        self.sections[stage] = {"index": 1, "title": row["title"], "targets": targets,
                                "hint": "座椅挡光弹。射亮顶灯，等墨鸦飞入光区；右侧墨伞收伞后可直接净化。"}
        self.event(f"{stage}.start", {"at_ms": 0}, [{"op": "section", "section": stage},
                   *map(spawn, (lamp, ink, crow, canopy)), permission(canopy, "invalid")])
        self.bind_lamp(lamp, light)
        for number, delay in enumerate((3600, 9200, 14700), 1):
            self.strike(crow, f"{stage}.crow{number}", f"{stage}.start", delay, "crow_release")
        for number, delay in enumerate((3000, 9700), 1):
            self.strike(umbrella, f"{stage}.umbrella{number}", f"{stage}.fold", delay, "umbrella_release")
        self.finish(targets)
        return self.source


if __name__ == "__main__":
    GreenCar().build()
