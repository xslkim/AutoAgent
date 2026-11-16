"""Contract checks for authored combat scenes and ID-addressed Agent edits."""
import copy
import tempfile
import unittest
from pathlib import Path

from compiler import ROOT, CompileError, compile_source, read
from versions import patch, publish


class EncounterTests(unittest.TestCase):
    def setUp(self):
        self.source = read(ROOT / "gunforge/level_design/examples/orbital.siege.json")

    def test_generated_events_trace_to_authored_fields(self):
        self.source["events"]["post_launch"] = {
            "trigger": {"after": "launcher.attack", "delay_ms": 500},
            "actions": {"report": {"op": "emit", "event": "station.launch_observed"}},
            "order": ["report"], "max_firings": 1,
        }
        build = compile_source(self.source)
        self.assertEqual(build["source_map"]["rammer.spawn"]["pointer"], "/encounter/waves/approach/spawns/rammer")
        self.assertEqual(build["source_map"]["slug.impact"]["pointer"], "/encounter/attacks/launcher/projectile/flight_ms")
        self.assertEqual(build["level"]["events"]["rammer.spawn"]["at_tick"], 36)
        self.assertEqual(build["level"]["events"]["post_launch"]["trigger"]["after"], "launcher.attack")
        self.assertEqual(build["level"]["events"]["rammer.jam"]["actions"]["a1"]["source"], "jammer")

    def test_invalid_encounters_are_rejected(self):
        mutations = [
            (lambda s: s["encounter"]["waves"]["sweep"]["spawns"].update(rammer=50), "belongs to a wave"),
            (lambda s: s["encounter"]["attacks"]["rammer"].update(release_ms=1401, contact_ms=1402), "melee contact must follow release"),
            (lambda s: s["encounter"]["attacks"]["launcher"]["projectile"].update(entity="jammer"), "expected a projectile"),
            (lambda s: s["entities"]["launcher"]["motion"]["frames"][2].update(attack_time="contact"), "unavailable attack time"),
            (lambda s: s["encounter"]["attacks"]["rammer"]["damage"].update(resource="missing"), "unknown resource"),
            (lambda s: s["encounter"]["supports"]["jam"].update(source="rammer"), "expected an activation source"),
            (lambda s: s["encounter"]["waves"]["sweep"]["spawns"].update(sweeper=6500), "finish before"),
            (lambda s: s["events"].update({"rammer.spawn": s["events"]["station.secure"]}), "generated ID already exists"),
        ]
        for edit, message in mutations:
            source = copy.deepcopy(self.source)
            edit(source)
            with self.subTest(message=message), self.assertRaisesRegex(CompileError, message):
                compile_source(source)

    def test_id_addressed_wave_patch_keeps_other_wave_and_ammo(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            base = publish(self.source, store)
            result = patch(self.source["id"], base.parent.name, {
                "base_revision": base.parent.name,
                "changes": [
                    {"path": "/encounter/waves/approach/spawns/rammer", "expected": 300, "value": 600},
                    {"path": "/encounter/attacks/rammer/contact_ms", "expected": 1750, "value": 1850},
                ],
            }, store)
            candidate = read(result)
            self.assertEqual(read(base), self.source)
            self.assertEqual(candidate["encounter"]["waves"]["sweep"], self.source["encounter"]["waves"]["sweep"])
            self.assertEqual(candidate["controls"], self.source["controls"])
            compiled = compile_source(candidate)["level"]
            self.assertEqual(compiled["events"]["rammer.spawn"]["at_tick"], 54)
            self.assertEqual(compiled["events"]["rammer.attack"]["trigger"]["value"], 1850)
            self.assertEqual(compiled["entities"]["rammer"]["motion"]["frames"][3]["at_ms"], 1850)
