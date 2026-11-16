"""Build the first level's plaza encounter for the normal level player."""
from build_cinema import Cinema, after, condition, permission, spawn, topic
from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from versions import publish, resolve


ART = ROOT / "gunforge/games/g01/reports/art"
LAYOUT = ART / "T11/boss.json"
REVIEWS = ROOT / "gunforge/level_design/reviews"


class Plaza(Cinema):
    generated = ROOT / "gunforge/level_design/generated/plaza"

    def __init__(self):
        super().__init__()
        self.source.update(id="paper.plaza", seed=425, duration_ms=120000)
        self.source["initial_resources"].pop("rescued")
        self.source["hud"] = [field for field in self.source["hud"] if field["resource"] != "rescued"]
        self.presentation.update(subtitle="第一关 · 夜市广场", instructions="清开广场 · 从龙尾逐节净化 · 最后击中龙嘴朱砂核")
        for field in ("camera", "additive_z", "bottom_wipes"):
            self.presentation.pop(field)
        self.presentation["labels"].update(section_unit="段", result_success="纸龙重归夜市", result_failure="广场陷入黑暗")
        self.source["effects"].pop("light_fx")
        self.source["effects"].pop("sweep_fx")

    def warmup(self):
        targets = ["square.sign", "square.ink"]
        for target, name, x, y, width, height in (
            (targets[0], "ink_sign", 400, 300, 430, 183),
            (targets[1], "ink_drop", 1060, 378, 315, 220),
        ):
            folder = ART / "T10/assets" / name
            body = self.entity(target, "target", (x, y, width, height))
            body["parts"] = {
                "body": {"resource": self.image(folder / "body.png"),
                         "hit_resource": self.image(self.alpha_mask(folder / "hit.png", name + "_hit")),
                         "x": 0, "y": 0, "width": 1, "height": 1},
                "stamp": {"resource": self.image(folder / "core.png"), "kind": "weak",
                          "x": 0, "y": 0, "width": 1, "height": 1},
            }
            body["part_order"] = ["body", "stamp"]
            body["motion"] = {"frames": [{"at_ms": 0, "x": x, "y": y}, {"at_ms": 1600, "x": x + 26, "y": y + 14},
                                          {"at_ms": 3400, "x": x - 20, "y": y}]}
        self.sections["square_watch"] = {"index": 1, "title": "清开广场", "targets": targets,
                                         "hint": "清除广场里的两个墨怪。红圈出现时，优先打断蓄力。"}
        self.event("square.start", {"at_ms": 0}, [{"op": "section", "section": "square_watch"}, *map(spawn, targets)])
        for index, target in enumerate(targets):
            self.attack(target, "square.start", 3600 + index * 900)
        self.event("square.clear", topic("target.neutralized"), [{"op": "input", "enabled": False}],
                   [condition(target, "health", 0, "lte") for target in targets])

    def boss(self):
        layout = read(LAYOUT)
        order = layout["opening_order"]
        anchor, mouth = "dragon.anchor", "dragon.mouth"
        images = [node["textures"][key] for node in layout["body_nodes"]
                  for key in ("paper", "locked", "ink", "glow", "purified")]
        images.extend((layout["head"]["upper_jaw"], layout["head"]["lower_jaw"], layout["tail"]["file"],
                       *(layout["mouth"][key] for key in ("core", "glow", "interior"))))
        self.presentation["dragon"] = {"layout": self.resource(LAYOUT, "metadata"),
                                       "images": {path: self.image(LAYOUT.parent / path) for path in images},
                                       "anchor": anchor, "mouth": mouth, "warning_effect": "dragon_windup"}
        self.entity(anchor, "decoration", (0, 0, 1, 1), virtual=True)
        for target in (*order, mouth):
            self.entity(target, "target", (0, 0, 1, 1), virtual=True)
        background = (LAYOUT.parent / layout["background"]).resolve()
        for section in ("square_watch", "ink_dragon"):
            self.layer(section, "square", background, (0, 0, *layout["content_size"]), 0, 0)
        self.sections["ink_dragon"] = {"index": 2, "title": "广场 · 墨舞龙", "targets": [*order, mouth],
                                       "hint": "从尾到头逐节清墨。龙嘴亮起朱砂后，赶在喷墨前击破。"}
        self.event("dragon.start", after("square.clear", 850),
                   [{"op": "section", "section": "ink_dragon"}, spawn(anchor),
                    *[action for target in order for action in (spawn(target), permission(target, "invalid"))],
                    permission(order[0], "primary"), {"op": "input", "enabled": True}])
        for target, following in zip(order, order[1:]):
            self.event(target + ".clean", topic("target.neutralized", target), [permission(following, "primary")])
        self.event("dragon.mouth_open", topic("target.neutralized", order[-1]),
                   [spawn(mouth), permission(mouth, "weak")])
        self.event("dragon.mouth_clean", topic("target.neutralized", mouth), [{"op": "input", "enabled": False}])
        self.event("dragon.clear", after("dragon.mouth_clean", 650), [{"op": "complete", "result": "clear"}])
        self.mouth_attacks(mouth)

    def mouth_attacks(self, mouth):
        self.source["effects"].update({
            "dragon_windup": {"kind": "warning", "duration_ms": 1250, "color": "#db8c6e", "radius": 108,
                              "label": "摆头 · 即将喷墨"},
            "dragon_breath": {"kind": "attack_release", "duration_ms": 620, "color": "#ac8dc1", "radius": 108},
        })
        active = [condition(mouth, "active", True)]
        for cycle in range(5):
            warning = f"dragon.breath{cycle + 1}.warn"
            release = f"dragon.breath{cycle + 1}.release"
            self.event(warning, after("dragon.mouth_open", 2500 + cycle * 4300), [
                {"op": "emit", "event": "attack.warning"},
                {"op": "vfx", "effect": "dragon_windup", "entity": mouth},
            ], active)
            self.event(release, after(warning, 1250), [
                {"op": "emit", "event": "attack.launched"},
                {"op": "vfx", "effect": "dragon_breath", "entity": mouth},
            ], active)
            self.event(release + ".hit", after(release, 420), [
                {"op": "resource_add", "resource": "lives", "amount": -1},
                {"op": "vfx", "effect": "hurt_fx", "entity": mouth},
                {"op": "emit", "event": "player.damaged"},
            ], active)

    def author(self):
        self.generated.mkdir(parents=True, exist_ok=True)
        self.audio({"attack.launched": "attack"})
        self.warmup()
        self.boss()
        self.event("score", topic("target.neutralized"), [{"op": "resource_add", "resource": "score", "amount": 100}],
                   limit=11, priority=30)
        self.event("square.fail", topic("player.damaged"), [{"op": "fail", "result": "overrun"}],
                   [{"resource": "lives", "compare": "lte", "value": 0}])
        return self.source

    def build(self):
        entry = publish(self.author())
        _, verified, manifest = resolve(self.source["id"], entry.parent.name)
        compiled = compile_source(verified, source_manifest=manifest)
        output = write_build(compiled, DEFAULT_CACHE)
        dump(REVIEWS / "plaza_build.json", {"source": str(entry), "source_revision": compiled["source_revision"],
             "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted"})
        print(output)


if __name__ == "__main__":
    Plaza().build()
