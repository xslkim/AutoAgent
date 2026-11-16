"""Build the three-chapter candidate with all eight paper resident designs."""
from audit_lantern_city_release import bindings
from build_assault import build as build_alley
from build_footbridge_cyclist import FootbridgeCyclist
from build_lantern_city_rescue import assemble_rescue_campaign
from build_night_market import event, publish_candidate
from cast_color_images import normalize_color_images
from cast_edge_fill import repair_cast_edges
from compiler import ROOT


def alley_for_cast():
    source = build_alley(station_candidate=True, source_only=True, crow_windup_ms=1650, crow_lunge_ms=520)
    # Keep the shootable lantern and its decorative ink behind the moving crows.
    source["entities"]["lamp"]["properties"]["z"] = 73
    source["entities"]["lamp_cover"]["properties"]["z"] = 74
    source["sections"]["lamp_lesson"]["hint"] = "首次点亮巷灯可补 4 发光弹，并震停墨鸦。"
    source["sections"]["rescue"]["hint"] = "瞄准居民胸口的墨团。救出居民可回复 1 点生命。"
    return source


def tune_crow_warnings(source):
    events = source["events"]
    effects = source["effects"]
    effects["stall.stall_warning"]["duration_ms"] = 2400
    for name, release in events.items():
        if not name.endswith(".release"):
            continue
        if name.startswith("stall.crow_"):
            release["trigger"]["delay_ms"] = 2400
            # A crow struck during the dive can still be stopped before contact.
            contact = events[name.removesuffix(".release") + ".attack"]
            contact["guards"] = release["guards"][:]
        elif any(action.get("effect", "").endswith(".crow_release") for action in release["actions"].values()):
            release["trigger"]["delay_ms"] = 2000
            warning = events[release["trigger"]["after"]]
            for action in warning["actions"].values():
                if action["op"] == "vfx":
                    effect = action["effect"] + "_crow"
                    effects[effect] = dict(effects[action["effect"]], duration_ms=2000)
                    action["effect"] = effect


def attach_supplies(source):
    source["initial_resources"]["ammo"] = 8
    source["resource_bounds"]["ammo"]["max"] = 8
    source["controls"].update(magazine=8, reload_ms=600, auto_reload=True)
    source["effects"].update(
        ammo_supply={"kind": "spark", "duration_ms": 1150, "color": "#ffdd94", "radius": 20, "label": "光弹补给"},
        life_supply={"kind": "spark", "duration_ms": 1300, "color": "#b9e5c3", "radius": 26, "label": "生命 +1"},
    )
    events = source["events"]
    for name, definition in list(events.items()):
        if not any(action.get("op") == "resource_add" and action.get("resource") == "rescued"
                   for action in definition["actions"].values()):
            continue
        target = definition["trigger"]["on"].split(":", 1)[1]
        events[name + ".life_supply"] = event(definition["trigger"], [
            {"op": "resource_add", "resource": "lives", "amount": 1},
            {"op": "vfx", "entity": target, "effect": "life_supply"},
        ], [*definition["guards"], {"resource": "lives", "compare": "lt", "value": 5}])

    for name, entity in source["entities"].items():
        if entity["template"] == "activation_source":
            events[name + ".ammo_supply"] = event({"on": "interaction.activated:" + name}, [
                {"op": "resource_add", "resource": "ammo", "amount": 4},
                {"op": "vfx", "entity": name, "effect": "ammo_supply"},
            ])


def build():
    campaign, revisions = assemble_rescue_campaign(
        station_sources={"alley": alley_for_cast, "footbridge": FootbridgeCyclist().author},
    )
    campaign.source["id"] = "paper.lantern_city_cast"
    attach_supplies(campaign.source)
    tune_crow_warnings(campaign.source)
    references = bindings(campaign.source)
    normalize_color_images(ROOT, campaign.source["resources"], references)
    repair_cast_edges(ROOT, campaign.source, references)
    publish_candidate(campaign, revisions)


if __name__ == "__main__":
    build()
