"""Build the video-shop encounter from the approved first-level art packs."""
import math

from build_cinema import Cinema, LIGHT_MS, after, condition, remove, spawn, topic
from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from versions import publish, resolve


ART = ROOT / "gunforge/games/g01/reports/art/T10"
OWNER = ROOT / "art2d/assets/paper_lantern_video/export"
REVIEWS = ROOT / "gunforge/level_design/reviews"
STAGE = "video_shop"


def t10_ink(level, identifier, name, x, y, width):
    folder = ART / "assets" / name
    info = read(folder / "enemy.json")
    original_width, original_height = info["canvas"]
    if info["effective_radius_source_px"] * width / original_width < 40:
        raise ValueError(f"{name}: ink silhouette too small")
    height = round(width * original_height / original_width)
    entity = level.entity(identifier, "target", (x, y, width, height))
    entity["parts"] = {
        "body": {"resource": level.image(folder / info["body"]),
                 "hit_resource": level.image(level.alpha_mask(folder / info["hit_mask"], name + "_hit")),
                 "x": 0, "y": 0, "width": 1, "height": 1},
        "stamp": {"resource": level.image(folder / info["core"]), "kind": "weak",
                  "x": 0, "y": 0, "width": 1, "height": 1},
    }
    entity["part_order"] = ["body", "stamp"]
    return entity


class VideoShop(Cinema):
    generated = ROOT / "gunforge/level_design/generated/video_shop"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.video_shop", seed=426, duration_ms=75000)
        self.presentation.update(subtitle="第一关 · 录像厅门口", instructions="拦住滴墨 · 射亮霓虹招牌 · 净化老板胸口的墨团")
        self.presentation["labels"].update(result_success="录像厅保住了", result_failure="录像厅陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"]["sign_spit"] = {"kind": "attack_release", "duration_ms": 560, "color": "#a786c5", "radius": 70}

    def owner(self):
        layout = read(ART / "layouts.json")
        rect = next(row["protected"][0] for row in layout["stations"] if row["id"] == STAGE)
        character = OWNER / "character.json"
        clips = read(character)["clips"]
        self.presentation["puppets"]["owner"] = {
            "character": self.resource(character, "metadata"), "atlas": self.image(OWNER / "atlas.png"),
            "clips": {key: self.resource(OWNER / clips[key], "metadata") for key in ("struggle", "rescued_bounce", "thank")},
        }
        resident, rescue = "shop.owner", "shop.rescue"
        paper = self.entity(resident, "protected", rect, z=24)
        paper["puppet"] = {"rig": "owner", "target": rescue, "target_part": "rescue_ink",
                          "idle": "struggle", "success": "rescued_bounce", "rest": "thank"}
        x, y, width, height = rect
        self.entity(rescue, "target", (x + width / 2 - 50, y + height * .36, 100, 92), virtual=True)
        self.event("shop.owner.protected", topic("target.protected_hit", resident),
                   [{"op": "resource_add", "resource": "score", "amount": -50}], limit=30)
        self.event("shop.rescued", topic("target.neutralized", rescue),
                   [{"op": "resource_add", "resource": "rescued", "amount": 1}])
        return resident, rescue

    def drop(self):
        identifier = "shop.drop"
        entity = t10_ink(self, identifier, "ink_drop", 311, 123, 286)
        entity["motion"] = {"easing": "linear", "frames": [
            {"at_ms": age, "x": x, "y": y, "scale": scale}
            for age, x, y, scale in ((0, 311, 123, .95), (650, 315, 133, 1), (1900, 319, 143, 1),
                                     (2820, 349, 495, 1.08), (4200, 325, 440, 1.02))
        ]}
        self.attack(identifier, "shop.start", 650)
        # The sprite itself is the falling projectile. Contact follows the fall rather than the warning.
        self.events[identifier + ".damage"]["trigger"]["delay_ms"] = 2170
        self.event(identifier + ".fall", after(identifier + ".warn", 1250),
                   [{"op": "emit", "event": "attack.launched"}], [condition(identifier, "active", True)])
        return identifier

    def sign(self, light, influence):
        identifier = "shop.sign"
        entity = t10_ink(self, identifier, "ink_sign", 0, 0, 430)
        x = (1465 + 1285 - entity["width"]) / 2
        y = 245 - entity["height"] / 2
        entity["x"], entity["y"] = x, y - 30
        entity["motion"] = {"frames": [{"at_ms": 0, "x": x, "y": y - 30}, {"at_ms": 500, "x": x, "y": y}]}
        entity["bob"] = {"amplitude_x": -90, "amplitude_y": 0, "period_ms": 4500, "phase_rad": -math.pi / 2}
        entity["mask_permission"] = {"source": light, "resource": influence, "threshold": .3}
        self.presentation["entity_tints"][identifier] = {"invalid": "#68758e"}
        self.presentation["entity_state_labels"][identifier] = {"invalid": "硬化", "primary": "软化 · 射击"}
        active = [condition(identifier, "active", True)]
        for index, age in enumerate((4500, 10500, 16500), 1):
            warn = f"shop.spit{index}.warn"
            release = f"shop.spit{index}.release"
            self.event(warn, after("shop.start", age), [
                {"op": "emit", "event": "attack.warning"}, {"op": "vfx", "effect": "warn_fx", "entity": identifier},
            ], active)
            self.event(release, after(warn, 1250), [
                {"op": "emit", "event": "attack.launched"}, {"op": "vfx", "effect": "sign_spit", "entity": identifier},
            ], active)
            self.event(release + ".hit", after(release, 420), [
                {"op": "resource_add", "resource": "lives", "amount": -1},
                {"op": "vfx", "effect": "hurt_fx", "entity": identifier}, {"op": "emit", "event": "player.damaged"},
            ], active)
        return identifier

    def author(self):
        self.generated.mkdir(parents=True, exist_ok=True)
        self.audio({"attack.launched": "attack"})
        lamp, light, influence, cover = self.stage_art(STAGE, ART, ink_variant=2)
        resident, rescue = self.owner()
        drop, sign = self.drop(), self.sign(light, influence)
        targets = [drop, sign, rescue]
        self.sections[STAGE] = {"index": 1, "title": "录像厅门口", "targets": targets,
                                "hint": "拦住屋檐滴墨。射亮右上霓虹，等墨招牌入光。只射老板胸口墨团。"}
        self.event("shop.start", {"at_ms": 0}, [{"op": "section", "section": STAGE},
                   *map(spawn, (lamp, cover, resident, rescue, drop, sign))])
        self.event(lamp + ".open", topic("interaction.activated", lamp),
                   [spawn(light), {"op": "vfx", "effect": "light_fx", "entity": lamp}], limit=10, priority=10)
        self.event(lamp + ".expire", after(lamp + ".open", LIGHT_MS), [remove(light),
                   {"op": "set", "entity": lamp, "field": "value", "value": 0}],
                   [condition(lamp, "value", 1)], limit=10)
        self.event("shop.clear", topic("target.neutralized"), [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])
        self.event("shop.complete", after("shop.clear", 3100), [{"op": "complete", "result": "clear"}])
        self.event("shop.score", topic("target.neutralized"), [{"op": "resource_add", "resource": "score", "amount": 100}],
                   limit=len(targets), priority=30)
        self.event("shop.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])
        return self.source

    def build(self):
        entry = publish(self.author())
        _, verified, manifest = resolve(self.source["id"], entry.parent.name)
        compiled = compile_source(verified, source_manifest=manifest)
        output = write_build(compiled, DEFAULT_CACHE)
        dump(REVIEWS / "video_shop_build.json", {"source": str(entry), "source_revision": compiled["source_revision"],
             "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted"})
        print(output)


if __name__ == "__main__":
    VideoShop().build()
