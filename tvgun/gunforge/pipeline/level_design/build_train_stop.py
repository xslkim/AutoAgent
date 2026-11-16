"""Shared art and encounter authoring for the train station's combat stops."""
from build_cinema import Cinema, after, condition, remove, spawn, topic
from cinema_resident import build_rescue_clips
from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from versions import publish, resolve


GAME = ROOT / "gunforge/games/g01"
ART = GAME / "reports/art/T13"
CROW = GAME / "assets/stations/g01_st_l1_01_alley/crow"
REVIEWS = ROOT / "gunforge/level_design/reviews"
LIGHT_DURATION = 6000


class TrainStop(Cinema):
    def prepare_stop(self, rescue=True):
        self.generated.mkdir(parents=True, exist_ok=True)
        if rescue:
            self.rescue_clips = {name: self.resource(path, "metadata")
                                 for name, path in build_rescue_clips(self.generated).items()}
        self.audio({"attack.launched": "attack"})
        return next(row for row in read(ART / "layouts.json")["stations"] if row["id"] == self.stage)

    def crow(self, lane):
        identifier = f"{self.stage}.crow"
        x, y, width, height = lane
        size = 250
        left = round(x + (width - size) / 2)
        top = round(y + (height - size) / 2)
        entity = self.entity(identifier, "target", (left, top, size, size), z=32)
        entity["parts"] = {
            "body": {"resource": self.image(CROW / "body.png"), "x": 62 / 1024, "y": 154 / 1024,
                     "width": 917 / 1024, "height": 753 / 1024},
            "stamp": {"resource": self.image(CROW / "core.png"), "source": [417, 202, 132, 132],
                      "x": 533 / 1024, "y": 400 / 1024, "width": 132 / 1024, "height": 132 / 1024,
                      "kind": "weak"},
        }
        entity["part_order"] = ["body", "stamp"]
        return identifier

    def bind_lamp(self, lamp, light):
        self.event(lamp + ".open", topic("interaction.activated", lamp),
                   [spawn(light), {"op": "vfx", "effect": "light_fx", "entity": lamp}], limit=12, priority=10)
        self.event(lamp + ".expire", after(lamp + ".open", LIGHT_DURATION), [remove(light),
                   {"op": "set", "entity": lamp, "field": "value", "value": 0}], limit=12)

    def strike(self, target, name, start, delay, effect):
        active = [condition(target, "active", True)]
        warning, release = f"{name}.warning", f"{name}.release"
        self.event(warning, after(start, delay), [
            {"op": "emit", "event": "attack.warning"}, {"op": "vfx", "effect": "warn_fx", "entity": target},
        ], active)
        self.event(release, after(warning, 1250), [
            {"op": "emit", "event": "attack.launched"}, {"op": "vfx", "effect": effect, "entity": target},
        ], active)
        self.event(f"{name}.hit", after(release, 550), [
            {"op": "resource_add", "resource": "lives", "amount": -1},
            {"op": "vfx", "effect": "hurt_fx", "entity": target}, {"op": "emit", "event": "player.damaged"},
        ], active)

    def finish(self, targets):
        stage = self.stage
        self.event(f"{stage}.score", topic("target.neutralized"),
                   [{"op": "resource_add", "resource": "score", "amount": 100}], limit=len(targets), priority=30)
        self.event(f"{stage}.clear", topic("target.neutralized"), [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])
        self.event(f"{stage}.complete", after(f"{stage}.clear", 1500), [{"op": "complete", "result": "clear"}])
        self.event(f"{stage}.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])

    def build(self):
        entry = publish(self.author())
        _, verified, manifest = resolve(self.source["id"], entry.parent.name)
        compiled = compile_source(verified, source_manifest=manifest)
        output = write_build(compiled, DEFAULT_CACHE)
        name = self.source["id"].removeprefix("paper.")
        dump(REVIEWS / f"{name}_build.json", {"source": str(entry), "source_revision": compiled["source_revision"],
             "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted"})
        print(output)
