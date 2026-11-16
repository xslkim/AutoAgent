"""Assemble the five first-level stations into one deterministic player session."""
from copy import deepcopy

from build_assault import build as build_alley
from build_cinema import Cinema, after, condition, remove, spawn
from build_footbridge import Footbridge
from build_plaza import Plaza
from build_stall import build as build_stall
from build_video_shop import VideoShop
from compiler import CompileError, DEFAULT_CACHE, ROOT, compile_source, write_build
from encounter import expand_encounter
from freeze_baseline import dump
from versions import publish, resolve


STATIONS = (
    ("alley", "巷口", "level.clear", lambda: build_alley(station_candidate=True, source_only=True)),
    ("stall", "糖葫芦摊", "stall.clear", lambda: build_stall(source_only=True)),
    ("video_shop", "录像厅门口", "shop.complete", lambda: VideoShop().author()),
    ("footbridge", "天桥", "bridge.complete", lambda: Footbridge().author()),
    ("plaza", "广场", "dragon.clear", lambda: Plaza().author()),
)
TRANSITION_MS = 600


def event(trigger, actions, guards=()):
    order = [f"a{i}" for i in range(len(actions))]
    return {"trigger": trigger, "actions": dict(zip(order, actions)), "order": order,
            "guards": list(guards), "max_firings": 1, "priority": 0}


def renamed(data, **fields):
    return {key: fields[key][value] if key in fields else value for key, value in data.items()}


def bind_topic(topic, entities):
    name, separator, entity = topic.partition(":")
    return name + separator + entities[entity] if separator else topic


class NightMarket:
    def __init__(self):
        self.presentation = {"title": "纸灯城", "subtitle": "第一关 · 夜市",
                             "instructions": "守住巷口 · 穿过夜市 · 在广场净化墨舞龙",
                             "stations": [title for _, title, _, _ in STATIONS],
                             "camera": {"amplitude_x": 38, "amplitude_y": 15}, "additive_z": 11,
                             "debug_shell": False, "default_sound": True,
                             "labels": {"progress": "净化", "result_success": "夜市重新亮了", "result_failure": "夜市陷入黑暗"}}
        for key in ("layers", "puppets", "bottom_wipes", "entity_tints", "entity_state_labels", "activation_glows", "sound_bindings", "feedback"):
            self.presentation[key] = {}
        self.source = {"schema_version": 1, "id": "paper.night_market", "ruleset": "directed_action@1", "seed": 428,
                       "tick_hz": 60, "duration_ms": 0, "layout": {"width": 1776, "height": 936},
                       "resources": {}, "entities": {}, "events": {}, "queries": {}, "effects": {}, "cues": {}, "sections": {},
                       "presentation": self.presentation, "initial_resources": {"lives": 5, "ammo": 12, "score": 0, "rescued": 0},
                       "resource_bounds": {"lives": {"min": 0, "max": 5}, "ammo": {"min": 0, "max": 12}, "score": {"min": 0}},
                       "controls": {"ammo_resource": "ammo", "magazine": 12, "reload_ms": 480, "shot_interval_ms": 150, "assist_px": 0},
                       "hud": [{"label": label, "resource": key} for key, label in
                               (("lives", "灯芯"), ("ammo", "光弹"), ("rescued", "获救"), ("score", "印记"))]}
        self.assets = {}
        self.previous_finish = None
        self.previous_entities = []

    def resource_ids(self, station, resources):
        result = {}
        for name, item in resources.items():
            key = item["path"], item["sha256"], item["kind"]
            identifier = self.assets.setdefault(key, f"{station}.{name}")
            self.source["resources"][identifier] = item
            result[name] = identifier
        return result

    def append(self, station, index, finish, source, *, continue_after, station_indices=None, transition_ms=TRANSITION_MS):
        source = deepcopy(source)
        if "encounter" in source:
            expand_encounter(source, CompileError)
        art = source["presentation"]
        names = {table: {name: f"{station}.{name}" for name in source[table]}
                 for table in ("entities", "events", "queries", "effects", "cues", "sections")}
        entities, events, queries, effects, cues, sections = (names[key] for key in
                    ("entities", "events", "queries", "effects", "cues", "sections"))
        if "dragon" in art:
            # The verified dragon rig names its raster hit zones directly.
            entities = {name: name for name in source["entities"]}
        resources = self.resource_ids(station, source["resources"])
        counters = {}
        for name, value in source["initial_resources"].items():
            counter = name if name in ("lives", "ammo", "score", "rescued") else f"{station}.{name}"
            counters[name] = counter
            self.source["initial_resources"].setdefault(counter, value)
        puppets = {name: f"{station}.{name}" for name in art.get("puppets", {})}
        initially_active = []
        for name, node in source["entities"].items():
            actor = renamed(node, resource=resources, hit_resource=resources)
            properties = actor.setdefault("properties", {})
            if properties.pop("active", False):
                initially_active.append(entities[name])
            if "camera" not in art:
                actor.pop("parallax", None)
            if "parts" in actor:
                actor["parts"] = {part: renamed(data, resource=resources, hit_resource=resources)
                                  for part, data in actor["parts"].items()}
                for part in actor["parts"].values():
                    if "hardened_visual" in part:
                        part["hardened_visual"] = renamed(part["hardened_visual"], resource=resources)
            if "puppet" in actor:
                actor["puppet"] = renamed(actor["puppet"], rig=puppets, target=entities)
            if "mask_permission" in actor:
                actor["mask_permission"] = renamed(actor["mask_permission"], source=entities, resource=resources)
            self.source["entities"][entities[name]] = actor
        for name, definition in source["queries"].items():
            self.source["queries"][queries[name]] = renamed(definition, entity=entities, other=entities, resource=resources)
        self.source["effects"].update({effects[name]: data for name, data in source["effects"].items()})
        self.source["cues"].update({cues[name]: renamed(data, resource=resources) for name, data in source["cues"].items()})
        for name, definition in sorted(source["sections"].items(), key=lambda pair: pair[1]["index"]):
            station_index = station_indices[name] if station_indices is not None else index
            section = dict(definition,
                index=len(self.source["sections"]) + 1, targets=[entities[target] for target in definition["targets"]])
            if station_index is not None:
                station_title = self.presentation["stations"][station_index - 1]
                section.update(station=station_index, title=definition["title"].removeprefix(station_title + " · "))
            self.source["sections"][sections[name]] = section

        self.bind_art(station, art, resources, entities, effects, cues, sections, puppets)
        marker = f"flow.{station}"
        enter = marker + ".enter"
        self.source["entities"][marker] = {"template": "decoration", "x": 0, "y": 0, "width": 1, "height": 1,
                                             "properties": {"virtual": True}}
        cleanup = [{"op": "set", "entity": old, "field": "visible", "value": False} for old in self.previous_entities]
        cleanup.extend(map(remove, self.previous_entities))
        self.source["events"][enter] = event(after(self.previous_finish, transition_ms) if self.previous_finish else {"at_ms": 0},
            [*cleanup, spawn(marker), *map(spawn, initially_active), {"op": "input", "enabled": True}])
        active = condition(marker, "active", True)
        for name, definition in source["events"].items():
            original = definition["trigger"]
            if "at_ms" in original:
                trigger = after(enter, original["at_ms"])
            elif "on" in original:
                trigger = {"on": bind_topic(original["on"], entities)}
            else:
                trigger = renamed(original, after=events, query=queries)
            actions = {key: renamed(action, entity=entities, source=entities, section=sections, cue=cues, effect=effects, resource=counters)
                       for key, action in definition["actions"].items()}
            order = definition["order"][:]
            if continue_after:
                for key, action in actions.items():
                    if action["op"] == "complete":
                        actions[key] = {"op": "input", "enabled": False}
                if name == finish:
                    actions["deactivate_stage"] = remove(marker)
                    order.append("deactivate_stage")
            guards = [active, *(renamed(guard, entity=entities, query=queries, resource=counters)
                                 for guard in definition.get("guards", []))]
            self.source["events"][events[name]] = dict(definition, trigger=trigger, actions=actions, order=order, guards=guards)
        self.source["events"][marker + ".timeout"] = event(after(enter, source["duration_ms"]),
            [{"op": "fail", "result": "timeout"}], [active])
        self.previous_finish = events[finish]
        self.previous_entities = list(entities.values())
        self.source["duration_ms"] += source["duration_ms"] + transition_ms

    def bind_art(self, station, art, resources, entities, effects, cues, sections, puppets):
        for name, data in art.get("layers", {}).items():
            local_sections = [data["section"]] if "section" in data else sections
            for section in local_sections:
                key = f"{station}.{section}.{name}"
                self.presentation["layers"][key] = dict(data, resource=resources[data["resource"]], section=sections[section])
        for name, data in art.get("puppets", {}).items():
            self.presentation["puppets"][puppets[name]] = {
                "character": resources[data["character"]], "atlas": resources[data["atlas"]],
                "clips": {clip: resources[resource] for clip, resource in data["clips"].items()},
            }
        for field in ("entity_tints", "entity_state_labels", "activation_glows"):
            self.presentation[field].update({entities[name]: value for name, value in art.get(field, {}).items()})
        self.presentation["bottom_wipes"].update({entities[name]: entities[emitter]
                                                   for name, emitter in art.get("bottom_wipes", {}).items()})
        for name, cue in art.get("sound_bindings", {}).items():
            entity = name.partition(":")[2]
            if not entity or entity in entities:
                self.presentation["sound_bindings"].setdefault(bind_topic(name, entities), cues[cue])
        for name, effect in art.get("feedback", {}).items():
            self.presentation["feedback"].setdefault(name, effects[effect])
        if "support" in art:
            self.presentation["support"] = renamed(art["support"], entity=entities)
        if "dragon" in art:
            dragon = renamed(art["dragon"], layout=resources, anchor=entities, mouth=entities, warning_effect=effects)
            dragon["images"] = {file: resources[resource] for file, resource in dragon["images"].items()}
            self.presentation["dragon"] = dragon


def chapter_intro(market, section, backdrop, title, hint):
    market.source["sections"][section] = {"index": len(market.source["sections"]) + 1, "title": title,
                                         "targets": [], "hint": hint}
    layers = market.presentation["layers"]
    for name, layer in list(layers.items()):
        if layer["section"] == backdrop:
            layers["story." + name] = dict(layer, section=section)
    market.source["events"][section] = event(after(market.previous_finish, 0),
        [{"op": "section", "section": section}, {"op": "input", "enabled": False}])
    market.previous_finish = section


def assemble(*, with_cinema=False, continue_after_cinema=False, alley_followup=None, station_sources=None):
    market = NightMarket()
    revisions = {}
    station_sources = station_sources or {}
    for index, (key, _, finish, author) in enumerate(STATIONS, 1):
        source = station_sources.get(key, author)()
        revisions[source["id"]] = publish(source).parent.name
        market.append(key, index, finish, source, continue_after=with_cinema or index < len(STATIONS))
        if key == "alley" and alley_followup is not None:
            name, followup_finish, build_followup = alley_followup
            followup = build_followup(source)
            revisions[followup["id"]] = publish(followup).parent.name
            market.append(name, index, followup_finish, followup, continue_after=True)
    if with_cinema:
        cinema = Cinema().author()
        revisions[cinema["id"]] = publish(cinema).parent.name
        stations = sorted(cinema["sections"].items(), key=lambda pair: pair[1]["index"])
        market.presentation["stations"].extend(data["title"].split(" · ")[0] for _, data in stations)
        market.presentation.update(subtitle="夜市与旧影院", instructions="守住夜市 · 净化墨舞龙 · 走进旧影院")
        market.presentation["labels"].update(result_success="旧影院重新亮了", result_failure="灯芯耗尽")
        market.source["id"] = "paper.lantern_city"
        chapter_intro(market, "story.cinema_intro", "plaza.ink_dragon", "第二关 · 旧影院",
                      "墨雾流进了旧影院。先到售票处找灯。")
        market.append("cinema", len(STATIONS) + 1, "shadow.clear", cinema, continue_after=continue_after_cinema,
                      station_indices={name: index for index, (name, _) in enumerate(stations, len(STATIONS) + 1)},
                      transition_ms=1500)
    return market, revisions


def publish_candidate(market, revisions):
    entry = publish(market.source)
    _, verified, manifest = resolve(market.source["id"], entry.parent.name)
    compiled = compile_source(verified, source_manifest=manifest)
    output = write_build(compiled, DEFAULT_CACHE)
    receipt = market.source["id"].removeprefix("paper.")
    dump(ROOT / f"gunforge/level_design/reviews/{receipt}_build.json", {"source": str(entry),
         "source_revision": compiled["source_revision"], "build_id": compiled["build_id"], "compiled": str(output),
         "state": "candidate_not_adopted", "component_revisions": revisions})
    print(output)


def build(*, with_cinema=False):
    publish_candidate(*assemble(with_cinema=with_cinema))


if __name__ == "__main__":
    build()
