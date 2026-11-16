"""Build the train station's waiting-room candidate with the shared player."""
from build_cinema import permission, spawn
from build_train_stop import ART, LIGHT_DURATION, TrainStop
from compiler import ROOT


STAGE = "waiting_room"


class WaitingRoom(TrainStop):
    stage = STAGE
    generated = ROOT / "gunforge/level_design/generated/waiting_room"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.waiting_room", seed=430, duration_ms=75000)
        self.presentation.update(subtitle="第三关 · 候车室", instructions="射亮站灯 · 等墨鸦飞入灯光 · 只打路人胸口的墨团")
        self.presentation["labels"].update(result_success="候车室安全了", result_failure="候车室陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"].update({
            "crow_release": {"kind": "attack_release", "duration_ms": 560, "color": "#e5726e", "radius": 84,
                             "anchor_uv": [.38, .98]},
            "umbrella_release": {"kind": "attack_release", "duration_ms": 510, "color": "#a786c5", "radius": 76,
                                  "anchor_uv": [.59, .98]},
        })

    def crow_patrol(self, lane, light, influence):
        identifier = self.crow(lane)
        entity = self.entities[identifier]
        left, top = entity["x"], entity["y"]
        # The patrol rises toward the edge of the spill, stopping left of the resident and lamp.
        lit_x, lit_y = left + 141, top - 75
        path = ((0, left, top, -.05), (1450, lit_x, lit_y, .05), (3800, lit_x, lit_y, -.06),
                (4950, lit_x + 8, lit_y + 12, .14), (6000, left, top, -.06),
                (7450, lit_x, lit_y, .05), (9600, lit_x, lit_y, -.06))
        entity["motion"] = {"frames": [{"at_ms": at, "x": px, "y": py, "rotation_rad": angle}
                                       for at, px, py, angle in path]}
        entity["mask_permission"] = {"source": light, "resource": influence, "threshold": .13}
        self.presentation["entity_tints"][identifier] = {"invalid": "#657198"}
        self.presentation["entity_state_labels"][identifier] = {"invalid": "硬化", "primary": "软化 · 射击"}
        return identifier

    def author(self):
        row = self.prepare_stop()
        lamp, light, influence, ink = self.stage_art(STAGE, ART, ink_variant=0, light_ms=LIGHT_DURATION)
        crow = self.crow_patrol(row["lanes"][0]["rect"], light, influence)
        umbrella, canopy = self.umbrella(STAGE, row["lanes"][1]["rect"])
        resident, rescue = self.resident(STAGE, row["residents"][0], ART)
        targets = [crow, umbrella, rescue]
        self.sections[STAGE] = {"index": 1, "title": row["title"], "targets": targets,
                                "hint": "灯光里的墨鸦才可净化。等墨伞收起，只打路人胸口的墨团。"}
        self.event(f"{STAGE}.start", {"at_ms": 0}, [{"op": "section", "section": STAGE},
                   *map(spawn, (lamp, ink, crow, canopy, resident, rescue)), permission(canopy, "invalid")])
        self.bind_lamp(lamp, light)
        for number, delay in enumerate((3450, 9000, 14500), 1):
            self.strike(crow, f"{STAGE}.crow{number}", f"{STAGE}.start", delay, "crow_release")
        for number, delay in enumerate((4300, 9800), 1):
            self.strike(umbrella, f"{STAGE}.umbrella{number}", f"{STAGE}.fold", delay, "umbrella_release")
        self.finish(targets)
        return self.source


if __name__ == "__main__":
    WaitingRoom().build()
