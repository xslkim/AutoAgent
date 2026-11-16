"""Build the standalone night-market puddle encounter."""
import math
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from build_cinema import Cinema, after, condition, spawn, topic
from build_night_market import publish_candidate
from compiler import ROOT, read


ART = ROOT / "gunforge/games/g01"
ALLEY = ART / "assets/stations/g01_st_l1_01_alley/station"
ATLAS = ART / "reports/art/T06/gallery/loop_atlas.png"
TADPOLE_CELL = (12, 780, 372, 1140)
STAGE = "puddle"
START = "puddle.start"
ACTOR_SIZE = 240
FIRST_WARNING_MS = 2750
CONTACT_DELAY_MS = 1250


class TadpoleEncounter(Cinema):
    generated = ROOT / "gunforge/level_design/generated/tadpole_encounter"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.tadpole_encounter", seed=436, duration_ms=24000)
        del self.source["initial_resources"]["rescued"]
        self.source["hud"] = [field for field in self.source["hud"] if field["resource"] != "rescued"]
        self.presentation.update(subtitle="夜市巷口 · 墨蝌蚪", instructions="瞄准头部墨团 · 听水声抢先开火",
                                 camera={"amplitude_x": 0, "amplitude_y": 0})
        self.presentation["labels"].update(result_success="水洼恢复平静", result_failure="灯芯耗尽")
        self.source["effects"]["warn_fx"].update(color="#d8ad90", radius=86)
        del self.source["effects"]["warn_fx"]["label"]
        self.source["effects"]["hurt_fx"]["label"] = "墨水溅中"

    def stage_layers(self, alley):
        if alley is not None:
            for name, layer in alley["presentation"]["layers"].items():
                resource = layer["resource"]
                self.resources[resource] = alley["resources"][resource]
                self.presentation["layers"][f"{STAGE}.{name}"] = dict(layer, section=STAGE)
            return
        station = read(ALLEY / "station.json")
        ox, oy = station["content_origin"]
        for layer in station["layers"]:
            path = ALLEY / layer["file"]
            with Image.open(path) as image:
                size = image.size
            x, y = layer["pos"]
            blocker = layer.get("blocks_shots", False)
            z = round(layer["z"] * 10) + (60 if blocker else -30)
            self.layer(STAGE, layer["id"], path, (x - ox, y - oy, *size), z, layer["parallax"], blocker)

    def puddle_surface(self, z):
        surface = Image.new("RGBA", (780, 156))
        draw = ImageDraw.Draw(surface)
        draw.polygon([(28, 55), (110, 40), (174, 21), (270, 14), (335, 22), (435, 7), (550, 17),
                      (609, 30), (688, 29), (758, 49), (767, 68), (741, 83), (711, 108), (642, 117),
                      (538, 139), (457, 134), (369, 148), (276, 133), (197, 142), (128, 122), (53, 115),
                      (16, 92), (7, 71)], fill=(35, 44, 66, 137))
        for bounds, start, end in (((24, 32, 306, 108), 30, 147), ((258, 22, 573, 123), 25, 151),
                                   ((483, 24, 751, 93), 38, 148), ((142, 79, 658, 141), 38, 145)):
            draw.arc(bounds, start, end, fill=(124, 144, 160, 100), width=2)
        draw.line([(116, 68), (236, 65), (287, 66)], fill=(191, 143, 123, 74), width=2)
        draw.line([(472, 46), (537, 44), (644, 45)], fill=(191, 143, 123, 70), width=2)
        path = self.write_image("puddle_surface", surface.filter(ImageFilter.GaussianBlur(1.4)))
        self.layer(STAGE, "puddle_surface", path, (490, 701, *surface.size), z, .41)

    def alley_reflection(self):
        # Warm reflected window light across the wet lane, behind the moving silhouettes.
        width, height = 1120, 458
        yy, xx = np.ogrid[:height, :width]
        distance = np.hypot((xx - width / 2) / (width / 2), (yy - height / 2) / (height / 2))
        edge = np.clip((distance - .45) / .55, 0, 1)
        alpha = np.rint(82 * (1 - edge ** 2 * (3 - 2 * edge))).astype(np.uint8)
        wash = Image.new("RGBA", (width, height), (168, 137, 127))
        wash.putalpha(Image.fromarray(alpha))
        path = self.write_image("alley_wet_reflection", wash)
        self.layer(STAGE, "wet_reflection", path, (335, 454, width, height), 72, .41)

    def tadpole_parts(self):
        with Image.open(ATLAS) as atlas:
            body = atlas.crop(TADPOLE_CELL).convert("RGBA")
        rgba = np.asarray(body)
        opaque = rgba[:, :, 3] >= 128
        yy, xx = np.ogrid[:body.height, :body.width]
        distance_squared = (xx - body.width // 2) ** 2 + (yy - body.height // 2) ** 2
        radius = math.isqrt(int(distance_squared[~opaque].min()) - 1)
        head = distance_squared <= radius ** 2
        red, green, blue = rgba[:, :, :3].transpose(2, 0, 1)
        seal = head & (red > 70) & (red > 1.6 * green) & (red > 1.4 * blue)
        if not 75 <= radius <= 77 or not seal.any() or not (opaque & ~head).any():
            raise ValueError("The T06 atlas cell no longer matches the tadpole head, seal and tail")
        mask = Image.new("RGBA", body.size, "white")
        mask.putalpha(Image.fromarray(head.astype(np.uint8) * 255))
        seal_rgba = rgba.copy()
        seal_rgba[~seal, 3] = 0
        body_path = self.write_image("tadpole_body", body)
        hit_path = self.write_image("tadpole_head", mask)
        seal_path = self.write_image("tadpole_seal", Image.fromarray(seal_rgba))
        rect = {"x": 0, "y": 0, "width": 1, "height": 1}
        return {"body": {**rect, "resource": self.image(body_path), "hit_resource": self.image(hit_path)},
                "seal": {**rect, "resource": self.image(seal_path), "kind": "weak"}}

    def water_cue(self):
        # Short overlapping splashes, each with a falling resonant tone and filtered noise.
        rate = 22050
        t = np.arange(int(rate * .55)) / rate
        noise = np.random.default_rng(436).standard_normal(len(t))
        ripple = np.convolve(noise, np.ones(11) / 11, mode="same")
        pcm = np.zeros_like(t)
        for onset, frequency in ((0, 210), (.12, 285), (.25, 165)):
            age = np.maximum(t - onset, 0)
            envelope = np.minimum(age / .012, 1) * np.exp(-age * 23)
            pcm += envelope * (.42 * np.sin(math.tau * (frequency * age - 90 * age ** 2)) + ripple)
        path = self.generated / "water_warning.wav"
        with wave.open(str(path), "wb") as out:
            out.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            out.writeframes((pcm * (15000 / np.max(np.abs(pcm)))).astype("<i2").tobytes())
        self.source["cues"]["water_warning"] = {"resource": self.resource(path, "audio"), "channel": "warning",
                                                  "duration_ms": 550, "volume_db": -9}

    def tadpole(self, number, lane, parts, z):
        identifier = f"puddle.tadpole{number}"
        side = number - 2
        delay = (number - 1) * 280
        x, y = lane
        half = ACTOR_SIZE / 2
        entity = self.entity(identifier, "target", (x - half, y - half, ACTOR_SIZE, ACTOR_SIZE), z=z, hits=1)
        entity.update(parts=parts, part_order=["body", "seal"])
        entity["motion"] = {"easing": "smoothstep", "frames": [
            {"at_ms": at, "x": cx - half, "y": cy - half, "scale": scale}
            for at, cx, cy, scale in ((0, x, y, .95),
                                      (1600 + delay, x + side * 12, y + 24, 1.06),
                                      (FIRST_WARNING_MS + CONTACT_DELAY_MS + delay, x + side * 34, y + 106, 1.25))
        ]}
        entity["bob"] = {"amplitude_x": 7, "amplitude_y": 4, "period_ms": 1130 + delay,
                         "phase_rad": side * .8}
        active = [condition(identifier, "active", True)]
        for cycle in range(3):
            warning = f"{identifier}.warn{cycle + 1}"
            self.event(warning, after(START, FIRST_WARNING_MS + delay + cycle * 4000), [
                {"op": "cue", "cue": "water_warning"}, {"op": "vfx", "effect": "warn_fx", "entity": identifier},
            ], active)
            self.event(f"{identifier}.contact{cycle + 1}", after(warning, CONTACT_DELAY_MS), [
                {"op": "resource_add", "resource": "lives", "amount": -1},
                {"op": "vfx", "effect": "hurt_fx", "entity": identifier}, {"op": "emit", "event": "player.damaged"},
            ], active)
        return identifier

    def author(self, alley=None):
        if alley is not None:
            self.source["id"] = "paper.tadpole_alley"
        self.generated.mkdir(parents=True, exist_ok=True)
        self.stage_layers(alley)
        self.puddle_surface(70 if alley is not None else 26)
        if alley is not None:
            self.alley_reflection()
        self.audio()
        self.water_cue()
        parts = self.tadpole_parts()
        targets = [self.tadpole(number, lane, parts, 75 if alley is not None else 28)
                   for number, lane in enumerate(((620, 642), (866, 618), (1112, 646)), 1)]
        self.sections[STAGE] = {"index": 1, "title": "巷口水洼", "targets": targets,
                                "hint": "瞄准头部墨团。朱印可加分，甩尾时别追着尾巴打。"}
        self.event(START, {"at_ms": 0}, [{"op": "section", "section": STAGE}, *map(spawn, targets)])
        for name, event, amount in (("score", "target.neutralized", 100), ("bonus", "target.weak_hit", 25)):
            self.event(f"puddle.{name}", topic(event), [{"op": "resource_add", "resource": "score", "amount": amount}],
                       limit=len(targets), priority=30)
        self.event("puddle.clear", topic("target.neutralized"), [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])
        self.event("puddle.complete", after("puddle.clear", 700), [{"op": "complete", "result": "clear"}])
        self.event("puddle.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])
        return self.source


if __name__ == "__main__":
    encounter = TadpoleEncounter()
    encounter.author()
    publish_candidate(encounter, {})
