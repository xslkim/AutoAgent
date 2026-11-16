"""Build the first level's footbridge encounter from the approved art."""
from build_cinema import Cinema, LIGHT_MS, LIGHT_THRESHOLD, after, condition, remove, spawn, topic
from build_video_shop import ART, t10_ink
from compiler import DEFAULT_CACHE, ROOT, compile_source, write_build
from freeze_baseline import dump
from versions import publish, resolve


STAGE = "footbridge"
REVIEWS = ROOT / "gunforge/level_design/reviews"


class Footbridge(Cinema):
    generated = ROOT / "gunforge/level_design/generated/footbridge"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.footbridge", seed=427, duration_ms=75000)
        del self.source["initial_resources"]["rescued"]
        self.source["hud"] = [field for field in self.source["hud"] if field["resource"] != "rescued"]
        self.presentation.update(subtitle="第一关 · 天桥", instructions="射亮桥上灯笼 · 拦截滴墨 · 听铃声打断墨车夫")
        self.presentation["labels"].update(result_success="天桥重新亮了", result_failure="天桥陷入黑暗")
        self.source["effects"].pop("sweep_fx")
        self.source["effects"].update({
            "cart_warn": {"kind": "warning", "duration_ms": 1250, "color": "#dcaa7f", "radius": 105, "label": "铃响 · 甩墨"},
            "cart_spit": {"kind": "attack_release", "duration_ms": 600, "color": "#a786c5", "radius": 82},
        })

    def falling_ink(self, light, influence):
        identifier = "bridge.drop"
        entity = t10_ink(self, identifier, "ink_drop", 1045, 140, 280)
        entity["motion"] = {"frames": [
            {"at_ms": time, "x": x, "y": y, "scale": scale}
            for time, x, y, scale in ((0, 1045, 140, 1), (950, 1165, 145, 1), (3050, 1165, 145, 1),
                                      (3950, 1185, 485, 1.10), (4850, 1185, 485, 1.10), (6050, 1165, 145, 1),
                                      (8250, 1165, 145, 1), (9150, 1185, 485, 1.10), (10050, 1185, 485, 1.10),
                                      (11250, 1165, 145, 1))
        ]}
        entity["mask_permission"] = {"source": light, "resource": influence, "threshold": LIGHT_THRESHOLD}
        self.presentation["entity_tints"][identifier] = {"invalid": "#68758e"}
        self.presentation["entity_state_labels"][identifier] = {"invalid": "硬化", "primary": "软化 · 射击"}
        for number, start in enumerate((1800, 7000), 1):
            self.strike(identifier, f"bridge.fall{number}", start, 900, "warn_fx", "attack.warning")
        return identifier

    def cyclist(self):
        identifier = "bridge.cyclist"
        entity = t10_ink(self, identifier, "ink_cart", 230, 626, 425)
        entity["motion"] = {"frames": [
            {"at_ms": time, "x": x, "y": 626}
            for time, x in ((0, 230), (2050, 690), (3800, 690), (6100, 1010), (7500, 1010))
        ]}
        for number, start in enumerate((2050, 6200, 10500), 1):
            self.strike(identifier, f"bridge.cart{number}", start, 420, "cart_warn", "attack.cart_warning", "cart_spit")
        return identifier

    def strike(self, entity, name, start, travel_ms, warning, warning_topic, release_effect=None):
        active = [condition(entity, "active", True)]
        warn, release = name + ".warn", name + ".release"
        self.event(warn, after("bridge.start", start), [
            {"op": "emit", "event": warning_topic}, {"op": "vfx", "effect": warning, "entity": entity},
        ], active)
        actions = [{"op": "emit", "event": "attack.launched"}]
        if release_effect:
            actions.append({"op": "vfx", "effect": release_effect, "entity": entity})
        self.event(release, after(warn, 1250), actions, active)
        self.event(name + ".hit", after(release, travel_ms), [
            {"op": "resource_add", "resource": "lives", "amount": -1},
            {"op": "vfx", "effect": "hurt_fx", "entity": entity}, {"op": "emit", "event": "player.damaged"},
        ], active)

    def scenery(self):
        return ()

    def author(self):
        self.generated.mkdir(parents=True, exist_ok=True)
        self.audio({"attack.cart_warning": "bell", "attack.launched": "attack"})
        lamp, light, influence, cover = self.stage_art(STAGE, ART, ink_variant=1)
        self.presentation["layers"]["footbridge.bridge"].update(z=60, blocker=True)
        drop, cyclist = self.falling_ink(light, influence), self.cyclist()
        targets = [drop, cyclist]
        self.sections[STAGE] = {"index": 1, "title": "天桥", "targets": targets,
                                "hint": "射亮右上灯笼，等滴墨入光。桥下铃响时，先打断墨车夫。"}
        self.event("bridge.start", {"at_ms": 0}, [{"op": "section", "section": STAGE},
                   *map(spawn, (lamp, cover, drop, cyclist, *self.scenery()))])
        self.event(lamp + ".open", topic("interaction.activated", lamp),
                   [spawn(light), {"op": "vfx", "effect": "light_fx", "entity": lamp}], limit=10, priority=10)
        self.event(lamp + ".expire", after(lamp + ".open", LIGHT_MS), [remove(light),
                   {"op": "set", "entity": lamp, "field": "value", "value": 0}],
                   [condition(lamp, "value", 1)], limit=10)
        self.event("bridge.clear", topic("target.neutralized"), [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])
        self.event("bridge.complete", after("bridge.clear", 700), [{"op": "complete", "result": "clear"}])
        self.event("bridge.score", topic("target.neutralized"), [{"op": "resource_add", "resource": "score", "amount": 100}],
                   limit=len(targets), priority=30)
        self.event("bridge.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])
        return self.source

    def build(self):
        entry = publish(self.author())
        _, verified, manifest = resolve(self.source["id"], entry.parent.name)
        compiled = compile_source(verified, source_manifest=manifest)
        output = write_build(compiled, DEFAULT_CACHE)
        name = self.source["id"].removeprefix("paper.")
        dump(REVIEWS / f"{name}_build.json", {"source": str(entry), "source_revision": compiled["source_revision"],
             "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted"})
        print(output)


if __name__ == "__main__":
    Footbridge().build()
