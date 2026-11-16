"""Build the five-station cinema candidate on the shared directed-action player."""
import hashlib
import math

import numpy as np
from PIL import Image, ImageChops, ImageOps

from cinema_resident import RESCUE_INK_SIZE, build_rescue_clips, build_resident
from combat_cues import ensure_combat_cues
from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from versions import publish, resolve


ART = ROOT / "gunforge/games/g01/reports/art/T12"
INK_COVERS = ROOT / "gunforge/games/g01/assets/stations/g01_st_l1_01_alley/ink_on_lamp"
GENERATED = ROOT / "gunforge/level_design/generated/cinema"
REVIEWS = ROOT / "gunforge/level_design/reviews"
LIGHT_MS = 7500
LIGHT_FADE_MS = 300
LIGHT_FLICKER = ((6200, 1), (6350, .68), (6550, 1), (6700, 1), (6900, .42))
INK_VARIANTS = {"ticket_office": 0, "poster_hall": 1, "auditorium": 2, "projection_booth": 0}
UMBRELLA_HOLD_MS = 2400
UMBRELLA_FOLD_MS = 600
ACTOR_DEPTH = .41
SCREEN_DEPTH = .29
PROJECTOR_DEPTH = .34
TAPE_CYCLE_MS = 4600
LIGHT_THRESHOLD = .3
# Tape center positions: dark endpoint, illuminated endpoint, shared height.
TAPE_PATROLS = {
    "ticket_office": (755, 540, 342),
    "poster_hall": (525, 340, 367),
    "auditorium": (1624, 1528, 351),
    "projection_booth": (570, 800, 307),
}


def spawn(entity):
    return {"op": "spawn", "entity": entity}


def remove(entity):
    return {"op": "remove", "entity": entity}


def permission(entity, kind):
    return {"op": "permission", "entity": entity, "kind": kind}


def condition(entity, field, value, compare="eq"):
    return {"entity": entity, "field": field, "compare": compare, "value": value}


def after(event, delay_ms):
    return {"after": event, "delay_ms": delay_ms}


def topic(name, entity=None):
    return {"on": name if entity is None else f"{name}:{entity}"}


class Cinema:
    generated = GENERATED

    def __init__(self):
        self.presentation = {"title": "纸灯城", "subtitle": "第二关 · 旧影院",
                             "instructions": "射灯后等磁带墨入光 · 看准收伞时机 · 净化胶片盘墨渍",
                             "debug_shell": False, "default_sound": True, "layers": {}, "puppets": {},
                             "camera": {"amplitude_x": 38, "amplitude_y": 15}, "additive_z": 11,
                             "bottom_wipes": {},
                             "entity_state_labels": {}, "entity_tints": {}, "sound_bindings": {},
                             "labels": {"section_unit": "站", "progress": "净化",
                                        "result_success": "旧影院重新亮了", "result_failure": "银幕陷入黑暗"},
                             "feedback": {"hit": "hit", "weak": "hit", "neutralized": "clear_fx"}}
        self.source = {
            "schema_version": 1, "id": "paper.cinema", "ruleset": "directed_action@1",
            "seed": 424, "tick_hz": 60, "duration_ms": 180000, "layout": {"width": 1776, "height": 936},
            "resources": {}, "entities": {}, "queries": {}, "events": {}, "cues": {}, "sections": {},
            "presentation": self.presentation, "initial_resources": {"lives": 5, "ammo": 12, "score": 0, "rescued": 0},
            "resource_bounds": {"lives": {"min": 0, "max": 5}, "ammo": {"min": 0, "max": 12}, "score": {"min": 0}},
            "controls": {"ammo_resource": "ammo", "magazine": 12, "reload_ms": 480, "shot_interval_ms": 145, "assist_px": 0},
            "hud": [{"label": label, "resource": key} for key, label in
                    (("lives", "灯芯"), ("ammo", "光弹"), ("rescued", "获救"), ("score", "印记"))],
            "effects": {
                "hit": {"kind": "spark", "duration_ms": 220, "color": "#ead6aa", "radius": 48},
                "clear_fx": {"kind": "burst", "duration_ms": 470, "color": "#eac993", "radius": 80},
                "light_fx": {"kind": "pulse", "duration_ms": 530, "color": "#e9c480", "radius": 155, "label": "灯亮"},
                "warn_fx": {"kind": "warning", "duration_ms": 1250, "color": "#d77672", "radius": 104, "label": "蓄力"},
                "hurt_fx": {"kind": "player_hit", "duration_ms": 520, "color": "#ce6864", "label": "墨潮击中"},
                "sweep_fx": {"kind": "beam_sweep", "duration_ms": 900, "color": "#9c83d6", "radius": 152},
            },
        }
        self.resources, self.entities, self.sections, self.events = (
            self.source[key] for key in ("resources", "entities", "sections", "events"))
        self.registered = {}
        self.rescue_clips = {}

    def image(self, path):
        return self.resource(path, "image")

    def resource(self, path, kind):
        if path not in self.registered:
            key = f"{kind}_{len(self.registered):03d}"
            self.resources[key] = {"path": path.relative_to(ROOT).as_posix(),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "kind": kind}
            self.registered[path] = key
        return self.registered[path]

    def write_image(self, name, image):
        path = self.generated / f"{name}.png"
        image.save(path)
        return path

    def alpha_mask(self, path, name):
        with Image.open(path) as image:
            coverage = image.convert("L")
        result = Image.new("RGBA", coverage.size, "white")
        result.putalpha(coverage)
        return self.write_image(name, result)

    def entity(self, identifier, template, rect, art=None, z=28, mask=None, parallax=ACTOR_DEPTH, **properties):
        x, y, width, height = rect
        entity = {"template": template, "x": x, "y": y, "width": width, "height": height,
                  "parallax": parallax, "properties": {"z": z, **properties}}
        if art:
            entity["resource"] = self.image(art)
        if mask:
            entity["hit_resource"] = self.image(mask)
        self.entities[identifier] = entity
        return entity

    def layer(self, stage, identifier, path, rect, z, parallax, blocker=False):
        x, y, width, height = rect
        self.presentation["layers"][f"{stage}.{identifier}"] = {
            "resource": self.image(path), "x": x, "y": y, "width": width, "height": height,
            "z": z, "parallax": parallax, "blocker": blocker, "section": stage,
        }

    def event(self, identifier, trigger, actions, guards=(), limit=1, priority=0):
        order = [f"a{i}" for i in range(len(actions))]
        self.events[identifier] = {"trigger": trigger, "actions": dict(zip(order, actions)),
                                   "order": order, "guards": list(guards),
                                   "max_firings": limit, "priority": priority}

    def audio(self, extra_bindings=None):
        groups = {"weapon.fired": "shot", "target.hit": "hit", "target.weak_hit": "weak",
                  "target.neutralized": "purify", "target.blocked": "empty", "attack.warning": "windup",
                  "player.damaged": "hurt", "interaction.activated": "lamp", "weapon.reloaded": "reload"}
        groups.update(extra_bindings or {})
        assets = ensure_combat_cues()
        for cue in sorted(set(groups.values())):
            key = f"sound_{cue}"
            self.resources[key] = assets[cue]["resource"]
            self.source["cues"][cue] = {"resource": key, "channel": "weapon" if cue == "shot" else "impact",
                                       "duration_ms": assets[cue]["duration_ms"], "volume_db": -10}
        self.presentation["sound_bindings"].update(groups)

    def stage_art(self, stage, art=ART, ink_variant=None, light_ms=LIGHT_MS):
        folder = art / "parallax" / stage
        pack = read(folder / "station.json")
        ox, oy = pack["content_origin"]
        for index, layer in enumerate(pack["layers"]):
            if layer["id"] == "lamp":
                continue
            path = folder / layer["file"]
            with Image.open(path) as image:
                width, height = image.size
            x, y = layer["pos"]
            blocker = layer.get("blocks_shots", False)
            self.layer(stage, layer["id"], path, (x - ox, y - oy, width, height),
                       66 + index if blocker else index, layer["parallax"], blocker)
        if not pack["lights"]:
            return None
        light = pack["lights"][0]
        lamp = next(layer for layer in pack["layers"] if layer["id"] == light["space"])
        art = folder / lamp["file"]
        with Image.open(art) as image:
            lamp_size = image.size
        mx, my = [a - b for a, b in zip(light["hit_pos"], lamp["pos"])]
        coverage = Image.new("L", lamp_size)
        with Image.open(folder / light["hit_mask"]) as shape:
            shade = shape.convert("L")
        coverage.paste(shade, (mx, my))
        hit = Image.new("RGBA", lamp_size, "white")
        hit.putalpha(coverage)
        mask = self.write_image(f"{stage}_lamp_hit", hit)
        x, y = lamp["pos"]
        lamp_id = f"{stage}.lamp"
        self.entity(lamp_id, "activation_source", (x - ox, y - oy, *lamp_size), art, z=10, mask=mask,
                    parallax=lamp["parallax"], activation_cooldown_ms=light_ms)
        lx, ly = [a - b for a, b in zip(light["pos"], pack["content_origin"])]
        with Image.open(folder / light["spill"]) as spill, Image.open(folder / light["glow"]) as glow:
            delta = np.asarray(spill, dtype=np.int16) + np.asarray(glow, dtype=np.int16)
        height, width = delta.shape[:2]
        lit = Image.fromarray(np.clip(delta, 0, 255).astype("uint8"))
        light_id = f"{stage}.light"
        glow_entity = self.entity(light_id, "decoration", (lx, ly, width, height),
                                  self.write_image(f"{stage}_light_add", lit), z=11, parallax=lamp["parallax"])
        flicker = [(at + light_ms - LIGHT_MS, opacity) for at, opacity in LIGHT_FLICKER]
        glow_entity["motion"] = {"easing": "smoothstep", "frames": [
            {"at_ms": at, "x": lx, "y": ly, "opacity": opacity}
            for at, opacity in ((0, 0), (LIGHT_FADE_MS, 1), *flicker, (light_ms - LIGHT_FADE_MS, 1), (light_ms, 0))
        ]}
        ink = f"{stage}.lamp_ink"
        ink_art = self.lamp_ink(stage, shade, INK_VARIANTS[stage] if ink_variant is None else ink_variant)
        self.entity(ink, "decoration", (x + mx - ox, y + my - oy, *shade.size), ink_art,
                    z=12, parallax=lamp["parallax"])
        self.presentation["bottom_wipes"][ink] = light_id
        # The raw spill map covers the padded station, while RGB light is already cropped.
        left, top = light["pos"]
        with Image.open(folder / light["influence"]) as image:
            influence = image.crop((left, top, left + width, top + height))
        peak = influence.getextrema()[1]
        if peak == 0:
            raise ValueError(f"{stage}: light has no measurable spill")
        mask = influence.point(lambda value: round(value * 255 / peak))
        influence_id = self.image(self.write_image(f"{stage}_light_influence", mask))
        return lamp_id, light_id, influence_id, ink

    def lamp_ink(self, stage, shade, variant):
        width = min(round(shade.width * .78), round(shade.height * 1.8))
        height = round(shade.height * .86)
        with Image.open(INK_COVERS / f"cover_{variant:02d}.png") as image:
            ink = image.convert("RGBA")
            ink = ink.crop(ink.getbbox()).resize((width, height), Image.Resampling.LANCZOS)
        cover = Image.new("RGBA", shade.size)
        cover.alpha_composite(ink, ((shade.width - width) // 2, (shade.height - height) // 2))
        cover.putalpha(ImageChops.multiply(cover.getchannel("A"), shade))
        return self.write_image(f"{stage}_lamp_ink", cover)

    def enemy(self, identifier, name, lane, display_width=None):
        folder = ART / "actors" / name
        info = read(folder / "enemy.json")
        art = folder / "body.png"
        with Image.open(art) as image:
            source_width, source_height = image.size
        x, y, width, height = lane
        shown_width = min(display_width or info["display_width_px"], width, int(height * source_width / source_height))
        shown_height = round(source_height * shown_width / source_width)
        if info["effective_radius_px"] * shown_width / info["display_width_px"] < 40:
            raise ValueError(f"{identifier}: target is too small inside the reserved lane")
        position = (round(x + (width - shown_width) / 2), round(y + (height - shown_height) / 2))
        mask = self.alpha_mask(folder / "hit.png", f"{name}_hit")
        entity = self.entity(identifier, "target", (*position, shown_width, shown_height), art)
        entity["parts"] = {
            "body": {"resource": self.image(art), "hit_resource": self.image(mask),
                     "x": 0, "y": 0, "width": 1, "height": 1},
            "seal": {"resource": self.image(folder / "weak.png"), "kind": "weak",
                     "x": 0, "y": 0, "width": 1, "height": 1},
        }
        entity["part_order"] = ["body", "seal"]
        travel = min(19, (width - shown_width) // 2)
        entity["motion"] = {"frames": [{"at_ms": at, "x": position[0] + shift, "y": position[1]}
                                       for at, shift in ((0, 0), (1500, travel), (3800, -travel), (6000, 0))]}
        return entity

    def resident(self, stage, data, art=ART, *, folder=None, ink_size=RESCUE_INK_SIZE):
        rig = data["id"]
        if folder is None:
            folder = art / "actors" / rig
        character, atlas = build_resident(folder, ART / "screen_shadow/reel_ink.png", self.generated, ink_size=ink_size)
        self.presentation["puppets"][rig] = {"character": self.resource(character, "metadata"),
                                             "atlas": self.image(atlas), "clips": self.rescue_clips}
        x, y, width, height = data["rect"]
        resident = f"{stage}.resident"
        rescue = f"{stage}.rescue"
        body = self.entity(resident, "protected", (x, y, width, height), z=24)
        body["puppet"] = {"rig": rig, "target": rescue, "target_part": "rescue_ink",
                          "idle": "struggle", "success": "rescued", "rest": "thank"}
        self.entity(rescue, "target", (x + width / 2 - 50, y + height * .36, 100, 92), z=25, virtual=True)
        self.event(rescue + ".clean", topic("target.neutralized", rescue),
                   [{"op": "resource_add", "resource": "rescued", "amount": 1}])
        self.event(resident + ".protected", topic("target.protected_hit", resident),
                   [{"op": "resource_add", "resource": "score", "amount": -50}], limit=30)
        return resident, rescue

    def attack(self, entity, start, windup_ms):
        active = [condition(entity, "active", True)]
        self.event(entity + ".warn", after(start, windup_ms),
                   [{"op": "emit", "event": "attack.warning"}, {"op": "vfx", "effect": "warn_fx", "entity": entity}], active)
        self.event(entity + ".damage", after(entity + ".warn", 1250),
                   [{"op": "resource_add", "resource": "lives", "amount": -1},
                    {"op": "vfx", "effect": "hurt_fx", "entity": entity},
                    {"op": "emit", "event": "player.damaged"}], active)

    def umbrella(self, stage, lane):
        umbrella, canopy, reveal = (f"{stage}.{part}" for part in ("umbrella", "canopy", "fold_body"))
        body = self.enemy(umbrella, "ink_umbrella", lane)
        x, y, width, height = (body[key] for key in ("x", "y", "width", "height"))
        folder = ART / "actors/ink_umbrella"
        open_art = folder / "open.png"
        with Image.open(open_art) as image:
            canopy_height = round(width * image.height / image.width)
        canopy_y = y + (height - canopy_height) // 2
        shield = self.entity(canopy, "target", (x, canopy_y, width, canopy_height), open_art, z=30,
                             mask=self.alpha_mask(folder / "canopy_invalid.png", "umbrella_open_hit"))
        shield["motion"] = {"frames": [
            {"at_ms": 0, "x": x, "y": canopy_y},
            {"at_ms": UMBRELLA_HOLD_MS, "x": x, "y": canopy_y},
            {"at_ms": UMBRELLA_HOLD_MS + 160, "x": x + width * .045, "y": canopy_y + 3,
             "scale_x": .76, "scale_y": .98, "rotation_rad": .12},
            {"at_ms": UMBRELLA_HOLD_MS + 385, "x": x + width * .18, "y": canopy_y - 5,
             "scale_x": .34, "scale_y": .82, "rotation_rad": .27},
            {"at_ms": UMBRELLA_HOLD_MS + UMBRELLA_FOLD_MS, "x": x + width * .29, "y": canopy_y - 7,
             "scale_x": .09, "scale_y": .61, "rotation_rad": .38, "opacity": 0},
        ]}
        paper = self.entity(reveal, "target", (x, y, width, height), folder / "body.png", z=29,
                            mask=self.alpha_mask(folder / "hit.png", "ink_umbrella_hit"))
        paper["motion"] = {"frames": [
            {"at_ms": 0, "x": x, "y": y + 12, "opacity": 0},
            {"at_ms": 125, "x": x, "y": y + 12, "opacity": 0},
            {"at_ms": 365, "x": x, "y": y + 5, "opacity": .92},
            {"at_ms": UMBRELLA_FOLD_MS, "x": x, "y": y},
        ]}
        labels = self.presentation["entity_state_labels"]
        labels[canopy] = {"invalid": "撑伞 · 等收伞"}
        labels[reveal] = {"invalid": "收伞中"}
        labels[umbrella] = {"primary": "收伞 · 射击"}
        self.event(stage + ".fold.start", after(stage + ".start", UMBRELLA_HOLD_MS),
                   [permission(canopy, "blocker"), spawn(reveal), permission(reveal, "invalid")])
        self.event(stage + ".fold", after(stage + ".fold.start", UMBRELLA_FOLD_MS),
                   [remove(canopy), remove(reveal), spawn(umbrella)])
        return umbrella, canopy

    def normal_stage(self, row, index, trigger):
        stage = row["id"]
        lamp, light, influence, ink = self.stage_art(stage)
        tape = stage + ".tape"
        patrol = self.enemy(tape, "ink_tape", row["lanes"][0]["rect"], display_width=270)
        outside, inside, height = TAPE_PATROLS[stage]
        x = (outside + inside - patrol["width"]) / 2
        y = height - patrol["height"] / 2
        patrol["motion"] = {"frames": [{"at_ms": tick, "x": x, "y": y} for tick in (0, TAPE_CYCLE_MS)]}
        patrol["bob"] = {"amplitude_x": (inside - outside) / 2, "amplitude_y": 0,
                         "period_ms": TAPE_CYCLE_MS, "phase_rad": -math.pi / 2}
        patrol["mask_permission"] = {"source": light, "resource": influence, "threshold": LIGHT_THRESHOLD}
        umbrella, canopy = self.umbrella(stage, row["lanes"][1]["rect"])
        self.presentation["entity_tints"][tape] = {"invalid": "#6a7797"}
        self.presentation["entity_state_labels"][tape] = {"invalid": "硬化", "primary": "软化 · 射击"}
        targets = [tape, umbrella]
        extras = []
        actions = [{"op": "section", "section": stage}, spawn(lamp), spawn(ink), spawn(tape),
                   spawn(canopy), permission(canopy, "invalid"), {"op": "input", "enabled": True}]
        for resident_data in row["residents"]:
            resident, rescue = self.resident(stage, resident_data)
            extras.append(resident)
            targets.append(rescue)
            actions.extend((spawn(resident), spawn(rescue)))
        self.sections[stage] = {"index": index, "title": row["title"], "targets": targets,
                                "hint": "射灯后等磁带墨进入暖光，等墨伞收起再射。" +
                                        (" 只射居民胸口的墨团。" if extras else "")}
        self.event(stage + ".start", trigger, actions)
        self.event(lamp + ".open", topic("interaction.activated", lamp),
                   [{"op": "set", "entity": lamp, "field": "value", "value": 1}, spawn(light),
                    {"op": "vfx", "effect": "light_fx", "entity": lamp}],
                   [condition(lamp, "active", True)], limit=24, priority=10)
        self.event(lamp + ".expire", after(lamp + ".open", LIGHT_MS),
                   [remove(light), {"op": "set", "entity": lamp, "field": "value", "value": 0}],
                   [condition(lamp, "active", True), condition(lamp, "value", 1)], limit=24)
        self.attack(tape, stage + ".start", 7100 + index * 550)
        self.attack(umbrella, stage + ".fold", 6000 + index * 500)
        self.event(stage + ".clear", topic("target.neutralized"),
                   [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])
        self.event(stage + ".leave", after(stage + ".clear", 1300 if extras else 850),
                   [remove(lamp), remove(light), remove(ink), *map(remove, extras)])
        return after(stage + ".leave", 0)

    def screen_art(self):
        folder = ART / "screen_shadow"
        pack = read(folder / "art.json")
        stage = "screen_stage"
        boss = pack["layout"]
        self.stage_art(stage)
        self.layer(stage, "shadow", folder / pack["assets"]["shadow"], self.fit(folder / pack["assets"]["shadow"],
                   boss["shadow_rect"]), 14, SCREEN_DEPTH)
        self.layer(stage, "fixtures", folder / pack["assets"]["fixtures"], (0, 0, 1776, 936), 20, PROJECTOR_DEPTH)
        self.entity("shadow_core", "target", boss["core"]["rect"], folder / pack["assets"]["core"], z=42,
                    parallax=SCREEN_DEPTH, mask=self.alpha_mask(folder / pack["hit_masks"]["core"], "shadow_core_hit"))
        return folder, pack

    @staticmethod
    def fit(path, rect):
        x, y, width, height = rect
        with Image.open(path) as image:
            fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        return x + (width - fitted.width) // 2, y + (height - fitted.height) // 2, *fitted.size

    def screen_stage(self, index, trigger):
        folder, pack = self.screen_art()
        stage = "screen_stage"
        start = stage + ".start"
        actions = [{"op": "section", "section": stage}, {"op": "input", "enabled": True}]
        reels, attackers = [], []
        for slot, (projector, beam_file) in enumerate(zip(pack["layout"]["projectors"], pack["beam_masks"])):
            projector_id = projector["id"]
            machine = folder / pack["assets"]["projector"]
            self.entity(projector_id, "target", projector["art_rect"], machine, z=22, parallax=PROJECTOR_DEPTH)
            lens = projector_id + ".lens"
            x, y = projector["lens"]
            self.entity(lens, "decoration", (x, y, 1, 1), parallax=PROJECTOR_DEPTH, virtual=True)
            self.layer(stage, projector_id + ".clean", folder / pack["assets"]["clean_reel"],
                       self.fit(folder / pack["assets"]["clean_reel"], projector["reel"]["rect"]), 23, PROJECTOR_DEPTH)
            reel = projector["reel"]["id"]
            reels.append(reel)
            self.entity(reel, "target", projector["reel"]["rect"], folder / pack["assets"]["reel_ink"], z=24,
                        parallax=PROJECTOR_DEPTH, mask=self.alpha_mask(folder / pack["hit_masks"]["reel_ink"], "reel_hit"))
            dark, warm = projector_id + ".dark", projector_id + ".warm"
            with Image.open(folder / beam_file) as image:
                beam = image.convert("L")
            left, top, right, bottom = beam.getbbox()
            beam = beam.crop((left, top, right, bottom))
            for name, rgb, strength in ((dark, (44, 36, 84), .44), (warm, (233, 163, 105), .32)):
                texture = Image.new("RGBA", beam.size, rgb)
                texture.putalpha(beam.point(lambda value: round(value * strength)))
                self.entity(name, "decoration", (left, top, *beam.size), self.write_image(name, texture),
                            z=18 + slot, parallax=PROJECTOR_DEPTH)
            actions.extend((spawn(projector_id), permission(projector_id, "invalid"), spawn(reel), spawn(dark)))
            enemy = f"sweep_tape_{slot + 1}"
            attackers.append(enemy)
            center = round(sum(point[0] for point in projector["screen_span"]) / 2)
            self.enemy(enemy, "ink_tape", (center - 136, 320, 272, 193), display_width=262)
            sweep = projector_id + ".sweep"
            enabled = [condition(reel, "active", True)]
            self.event(sweep, after(start, 1500 + 1600 * slot),
                       [{"op": "vfx", "effect": "sweep_fx", "entity": enemy, "source": lens}], enabled)
            self.event(sweep + ".spawn", after(sweep, 450), [spawn(enemy)], enabled)
            self.attack(enemy, sweep + ".spawn", 2800)
            self.event(reel + ".clean", topic("target.neutralized", reel),
                       [remove(dark), spawn(warm), remove(enemy)], priority=12)
        self.sections[stage] = {"index": index, "title": "银幕前 · 银幕影", "targets": reels + ["shadow_core"],
                                "hint": "墨光扫过会冒出磁带墨。清除三盘墨渍，最后净化影核。"}
        self.event(start, trigger, actions)
        self.event("shadow.reveal", topic("target.neutralized"),
                   [spawn("shadow_core")], [condition(reel, "health", 0, "lte") for reel in reels])
        self.event("shadow.clear", topic("target.neutralized", "shadow_core"),
                   [*map(remove, attackers), {"op": "complete", "result": "clear"}])

    def author(self):
        GENERATED.mkdir(parents=True, exist_ok=True)
        self.rescue_clips = {name: self.resource(path, "metadata")
                             for name, path in build_rescue_clips(GENERATED).items()}
        self.audio()
        trigger = {"at_ms": 0}
        for index, stage in enumerate(read(ART / "layouts.json")["stations"], 1):
            if "boss" in stage:
                self.screen_stage(index, trigger)
            else:
                trigger = self.normal_stage(stage, index, trigger)
        self.event("score", topic("target.neutralized"), [{"op": "resource_add", "resource": "score", "amount": 100}],
                   limit=80, priority=30)
        self.event("cinema.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])
        return self.source

    def build(self):
        entry = publish(self.author())
        _, verified, manifest = resolve(self.source["id"], entry.parent.name)
        compiled = compile_source(verified, source_manifest=manifest)
        output = write_build(compiled, DEFAULT_CACHE)
        dump(REVIEWS / "cinema_build.json", {"source": str(entry), "source_revision": compiled["source_revision"],
             "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted"})
        print(output)


if __name__ == "__main__":
    Cinema().build()
