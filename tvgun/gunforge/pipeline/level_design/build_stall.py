"""Build the candy stall prototype from approved night-market assets."""
from copy import deepcopy

from compiler import DEFAULT_CACHE, ROOT, compile_source, read, write_build
from freeze_baseline import dump
from review_revision import preview
from versions import publish, resolve


REVIEWS = ROOT / "gunforge/level_design/reviews"
ASSET_REFERENCE = REVIEWS / "agent_proposals/proposal-1794237379343236500.json"
LIGHT_MS = 6000


def build(*, source_only=False):
    # Reuse the reviewed asset manifest and regenerate its derived sounds on a fresh checkout.
    preview(ASSET_REFERENCE)
    reference = read(ASSET_REFERENCE)
    _, station, _ = resolve("paper.station", reference["source_revision"])
    presentation = station["presentation"]
    presentation.update(subtitle="第二站 · 糖葫芦摊", instructions="灯光解除硬壳。墨鸦出现红圈时，趁它出手前击破。")
    presentation.pop("support")
    presentation["entity_tints"] = {}
    presentation["entity_state_labels"] = {}
    presentation["activation_glows"] = {}
    presentation["labels"].update(section_unit="轮", result_success="摊口重新亮了", result_failure="摊口陷入黑暗")
    presentation["layers"]["far_base"]["tint"] = "#d1bbd6"
    presentation["sound_bindings"]["target.blocked"] = "empty"
    presentation["sound_bindings"]["interaction.activated"] = "lamp"

    source = {
        "schema_version": 1, "id": "paper.stall", "ruleset": "directed_action@1",
        "seed": 422, "tick_hz": 60, "duration_ms": 50000, "layout": station["layout"],
        "presentation": presentation, "resources": station["resources"], "cues": station["cues"],
        "effects": station["effects"], "controls": station["controls"], "hud": station["hud"],
        "entities": {"lamp_cover": station["entities"]["lamp_cover"]},
        "events": {}, "sections": {}, "queries": {},
        "initial_resources": {"lives": 5, "ammo": 35, "score": 0, "purified": 0},
        "resource_bounds": {"lives": {"min": 0, "max": 5}, "ammo": {"min": 0, "max": 35}},
    }
    entities, events, sections, effects = (source[key] for key in ("entities", "events", "sections", "effects"))
    effects.update({
        "light_open": {"kind": "pulse", "duration_ms": 900, "color": "#ffda91", "radius": 1300, "label": "灯亮 · 墨鸦可打"},
        "light_closed": {"kind": "warning", "duration_ms": 900, "color": "#be9a83", "radius": 110, "label": "灯灭 · 可再次点亮"},
        "hardened_hit": {"kind": "spark", "duration_ms": 500, "color": "#ad9db2", "radius": 54, "label": "硬化 · 先点灯"},
        "stall_warning": {"kind": "warning", "duration_ms": 1800, "color": "#ff7764", "radius": 155, "label": "蓄力 · 击破可打断"},
        "stall_slash": {"kind": "attack_release", "duration_ms": 700, "color": "#ff655a", "radius": 98},
    })

    def event(name, trigger, actions, guards=(), limit=1, priority=0):
        order = [f"a{i}" for i in range(len(actions))]
        events[name] = {"trigger": trigger, "actions": dict(zip(order, actions)),
                        "order": order, "guards": list(guards), "max_firings": limit, "priority": priority}

    def entity_value(entity, field, value):
        return {"entity": entity, "field": field, "compare": "eq", "value": value}

    def permission(entity, kind):
        return {"op": "permission", "entity": entity, "kind": kind}

    sections["arrival"] = {"index": 4, "title": "守住糖葫芦摊", "targets": [],
                           "hint": "巷口的灯火把你带到摊前。照亮墨鸦，再击破它们。"}
    event("open", {"at_ms": 0}, [
        {"op": "section", "section": "arrival"}, {"op": "input", "enabled": False},
        {"op": "cue", "cue": "night_market"},
    ])
    groups = [
        ("认识硬化", "射右侧巷灯，照开左边墨鸦的硬壳。灯灭了可以再点。", [(420, 215)]),
        ("灯下拦击", "墨鸦会自行蓄力。射灯解除硬壳，优先击破红圈墨鸦。", [(355, 180), (905, 230)]),
        ("守住摊口", "暖光只有 6 秒。灯灭就补射巷灯，留意红圈。", [(260, 210), (620, 140), (965, 255)]),
    ]
    total = 0
    for wave, (title, hint, positions) in enumerate(groups, start=1):
        group = f"round_{wave}"
        lamp = f"lamp_{wave}"
        light = lamp + ".light"
        entities[lamp] = deepcopy(station["entities"]["lamp"])
        entities[lamp]["properties"]["activation_cooldown_ms"] = LIGHT_MS
        presentation["activation_glows"][lamp] = {"color": "#ffc25d", "radius": 148, "label": "灯亮"}
        lit = entity_value(lamp, "value", 1)
        actors = []
        spawn = [{"op": "section", "section": group}, {"op": "spawn", "entity": lamp},
                 {"op": "input", "enabled": True}, {"op": "vfx", "effect": "lesson_ring", "entity": lamp}]
        light_actions = [{"op": "remove", "entity": "lamp_cover"},
                         {"op": "vfx", "effect": "light_open", "entity": lamp}]
        expire_actions = [{"op": "set", "entity": lamp, "field": "value", "value": 0},
                          {"op": "spawn", "entity": "lamp_cover"},
                          {"op": "vfx", "effect": "light_closed", "entity": lamp}]
        for slot, (x, y) in enumerate(positions, start=1):
            actor = f"crow_{wave}_{slot}"
            actors.append(actor)
            entities[actor] = {
                "template": "target", "x": x, "y": y, "width": 260, "height": 260,
                "properties": {"z": 75, "label": "硬化墨鸦"},
                "parts": station["entities"]["w1_crow_1"]["parts"], "part_order": ["body", "stamp"],
                "motion": {"frames": [{"at_ms": 0, "x": x, "y": y},
                                      {"at_ms": 1500, "x": x + 36, "y": y + 24},
                                      {"at_ms": 4000, "x": x - 35, "y": y}]},
                "bob": {"amplitude_x": 12, "amplitude_y": 9, "period_ms": 1150 + slot * 90},
            }
            presentation["entity_tints"][actor] = {"invalid": "#545d85"}
            presentation["entity_state_labels"][actor] = {"invalid": "硬化", "primary": "可击破"}
            spawn += [{"op": "spawn", "entity": actor}, permission(actor, "invalid")]
            light_actions.append(permission(actor, "primary"))
            expire_actions.append(permission(actor, "invalid"))
            active = entity_value(actor, "active", True)
            event(actor + ".blocked", {"on": "target.blocked:" + actor},
                  [{"op": "vfx", "effect": "hardened_hit", "entity": actor}], [active], limit=40)
            event(actor + ".clear", {"on": "target.neutralized:" + actor}, [
                {"op": "resource_add", "resource": "score", "amount": 100},
                {"op": "resource_add", "resource": "purified", "amount": 1},
            ], priority=10)
            if wave > 1:
                warning = actor + ".warning"
                release = actor + ".release"
                event(warning, {"after": group + ".start", "delay_ms": 2100 + slot * 950},
                      [{"op": "cue", "cue": "windup"}, {"op": "vfx", "effect": "stall_warning", "entity": actor}],
                      [active])
                event(release, {"after": warning, "delay_ms": 1800}, [
                    {"op": "cue", "cue": "attack"},
                    {"op": "vfx", "effect": "stall_slash", "entity": actor},
                ], [active])
                event(actor + ".attack", {"after": release, "delay_ms": 650}, [
                    {"op": "resource_add", "resource": "lives", "amount": -1},
                    {"op": "vfx", "effect": "player_hurt", "entity": actor},
                    {"op": "emit", "event": "player.damaged"},
                ])

        sections[group] = {"index": wave, "title": title, "targets": actors, "hint": hint}
        trigger = {"at_ms": 1800} if wave == 1 else {"after": f"round_{wave-1}.clear", "delay_ms": 1800}
        event(group + ".start", trigger, spawn)
        total += len(actors)
        event(group + ".clear", {"on": "target.neutralized"}, [
            {"op": "input", "enabled": False}, {"op": "remove", "entity": lamp},
            {"op": "spawn", "entity": "lamp_cover"},
            {"op": "set", "entity": lamp, "field": "value", "value": 0},
        ], [{"resource": "purified", "compare": "eq", "value": total}])
        event(light, {"on": "interaction.activated:" + lamp}, light_actions, limit=10)
        event(lamp + ".expire", {"after": light, "delay_ms": LIGHT_MS}, expire_actions, [lit], limit=10)

    event("stall.clear", {"after": "round_3.clear", "delay_ms": 900}, [{"op": "complete", "result": "clear"}])
    event("stall.fail", {"on": "player.damaged"},
          [{"op": "fail", "result": "overrun"}], [{"resource": "lives", "compare": "lte", "value": 0}])

    if source_only:
        return source
    entry = publish(source)
    _, verified, manifest = resolve(source["id"], entry.parent.name)
    compiled = compile_source(verified, source_manifest=manifest)
    output = write_build(compiled, DEFAULT_CACHE)
    dump(REVIEWS / "stall_build.json", {
        "source": str(entry), "source_revision": compiled["source_revision"],
        "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted",
    })
    print(output)


if __name__ == "__main__":
    build()
