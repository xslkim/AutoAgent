"""Stage the workbench and city epilogue in the three-chapter player."""
import wave

from build_cinema import after, remove, spawn
from build_lantern_city_campaign import assemble_campaign
from build_lantern_city_ui import attach_ui
from build_night_market import publish_candidate
from build_train_stop import GAME
from build_workbench_ending import WorkbenchEnding


CITY_ART = GAME / "cinematics/opening_original/keyframes/city.png"
WIDE_ART = GAME / "assets/cutscenes/epilogue/city_wide_v1.png"
ENDING_TAPE = GAME / "assets/cutscenes/epilogue/ending_wide_tape.wav"
LIGHT_MS, STREET_MS, WIDE_MS, QUOTE_MS = 7200, 13600, 27000, 10200


class WorkbenchEpilogue(WorkbenchEnding):
    def author(self):
        super().author()
        self.source["id"] = "paper.workbench_epilogue"
        duration = LIGHT_MS + STREET_MS + WIDE_MS + QUOTE_MS
        short_duration = (self.events["ending.quote"]["trigger"]["delay_ms"]
                          + self.events["lantern_base.complete"]["trigger"]["delay_ms"])
        self.source["duration_ms"] += duration - short_duration

        quote = self.events["ending.quote"]
        quote_actions = [quote["actions"][key] for key in quote["order"]]
        lights_off = [action for action in quote_actions if action["op"] == "remove"]
        quote_section = self.sections["ending_quote"]
        self.sections["ending_city"] = {
            "index": quote_section["index"], "title": "夜市的灯", "targets": [],
            "skippable": True, "hint": "夜市的灯，又亮了起来。",
        }
        self.sections["ending_wide"] = {"index": quote_section["index"] + 1, "title": "灯城",
                                          "targets": [], "skippable": True}
        quote_section["index"] += 2
        layers = self.presentation["layers"]
        for key, layer in tuple(layers.items()):
            if layer["section"] == "ending_quote":
                for section in ("ending_city", "ending_wide"):
                    layers[f"{section}.{key}"] = dict(layer, section=section)

        city = "ending.city_view"
        # Preserve the source aspect ratio and keep the full viewport covered through the pan.
        actor = self.entity(city, "decoration", (-145, -81, 1984, 1117), CITY_ART, z=100, parallax=0)
        actor["motion"] = {"easing": "smoothstep", "frames": [
            {"at_ms": time, "x": x, "y": y, "opacity": opacity}
            for time, x, y, opacity in (
                (0, -145, -81, 0), (1200, -141, -83, 1), (STREET_MS, -69, -103, 1),
            )
        ]}
        wide = "ending.wide_view"
        panorama = self.entity(wide, "decoration", (0, -31, 1776, 999), WIDE_ART, z=101, parallax=0)
        panorama["motion"] = {"easing": "smoothstep", "frames": [
            {"at_ms": time, "x": x, "y": y, "scale": scale, "opacity": opacity}
            for time, x, y, scale, opacity in (
                (0, -27, -33, 1.125, 0), (1800, -25, -33, 1.125, 1),
                (15800, -12, -31, 1.03125, 1), (22800, 0, -31, 1, 1),
                (25000, 0, -31, 1, 1), (WIDE_MS, 0, -31, 1, 0),
            )
        ]}

        # The wait/enter pair allows the renderer to upload the city texture during relighting.
        light = self.events["ending.light"]
        # The tape mix includes the original lamp cue at its opening.
        light_actions = [light["actions"][key] for key in light["order"]]
        light_actions = [action for action in light_actions if action.get("cue") != "lamp"]
        with wave.open(str(ENDING_TAPE), "rb") as tape:
            if ((tape.getnchannels(), tape.getsampwidth(), tape.getframerate()) != (2, 2, 48000)
                    or tape.getnframes() * 1000 != duration * tape.getframerate()):
                raise ValueError("Ending tape must be stereo 48 kHz PCM and match the authored ending duration")
        self.source["cues"]["ending.tape"] = {"resource": self.resource(ENDING_TAPE, "audio"),
                                                "channel": "voice", "duration_ms": duration, "volume_db": 0}
        lock_input = {"op": "input", "enabled": False}
        tape_cue = {"op": "cue", "cue": "ending.tape", "replace_existing": True}
        self.event("ending.light", light["trigger"], [*light_actions, tape_cue, lock_input])
        self.event("ending.city_prepare", after("ending.light", LIGHT_MS), [lock_input])
        self.event("ending.city", after("ending.city_prepare", 0), [
            *lights_off, {"op": "section", "section": "ending_city"}, spawn(city), lock_input,
        ])
        self.event("ending.wide_prepare", after("ending.city", STREET_MS), [lock_input])
        self.event("ending.wide", after("ending.wide_prepare", 0), [
            {"op": "section", "section": "ending_wide"}, spawn(wide),
        ])
        self.event("ending.wide_dissolve", after("ending.wide", 1800), [remove(city)])
        self.event("ending.quote", after("ending.wide", WIDE_MS), [remove(wide), *quote_actions])
        self.events["lantern_base.complete"]["trigger"] = after("ending.quote", QUOTE_MS)
        skip = self.events["ending.skip"]
        self.event("ending.skip", skip["trigger"], [
            remove(city), remove(wide), *(skip["actions"][key] for key in skip["order"]),
        ])
        return self.source


def build():
    campaign, revisions = assemble_campaign(ending=WorkbenchEpilogue)
    campaign.source["id"] = "paper.lantern_city_epilogue"
    attach_ui(campaign)
    publish_candidate(campaign, revisions)


if __name__ == "__main__":
    build()
