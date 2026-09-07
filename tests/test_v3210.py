import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from world_depth import (WORLD_DEPTH_PROFILES, contextual_opportunities,
                         normalize_world_depth, record_canon_ripples,
                         record_downtime, world_depth_rules)
from world_progression import normalize_world_progression
from worlds import BASE_STATE, WORLD_DATA


class WorldwalkerV3210WorldDepthTests(unittest.TestCase):
    def state(self, world="Naruto"):
        state = copy.deepcopy(BASE_STATE)
        state.update(world=world, location=WORLD_DATA[world]["start"], factions=copy.deepcopy(WORLD_DATA[world]["factions"]))
        return state

    def test_release_and_schema(self):
        from worlds import APP_VERSION
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)

    def test_every_world_has_laws_flexible_paths_downtime_elites_and_leads(self):
        for world in WORLD_DATA:
            profile = WORLD_DEPTH_PROFILES.get(world)
            self.assertIsNotNone(profile, world)
            for key in ("laws", "paths", "downtime", "elite", "opportunities", "faction_doctrine"):
                self.assertTrue(profile[key], f"{world}: {key}")
            state = self.state(world)
            normalize_world_depth(state)
            self.assertTrue(state["world_depth"]["progression_paths"], world)
            self.assertTrue(all(row["fixed_order"] is False for row in state["world_depth"]["progression_paths"]), world)
            self.assertEqual(len(contextual_opportunities(state)), 3, world)

    def test_signature_techniques_are_persistent_and_readable(self):
        state = self.state()
        state["skills"] = {"Storm Thread Jutsu": {
            "rank": "Signature Jutsu", "effect": "Guides a lightning filament around cover.",
            "activation": "Shape lightning chakra through two fingers.",
            "limitation": "Numbs the hand after repeated use.", "counters": ["Insulation", "Chakra disruption"],
            "growth_path": "Split the thread without losing control.",
        }}
        normalize_world_depth(state)
        row = state["world_depth"]["signature_techniques"][0]
        self.assertEqual(row["name"], "Storm Thread Jutsu")
        self.assertIn("Numbs", row["cost"])
        before = copy.deepcopy(state)
        normalize_world_depth(state, before)
        self.assertEqual(len(state["world_depth"]["signature_techniques"]), 1)

    def test_world_specific_mechanical_profiles_are_seeded(self):
        expected = {
            "One Piece": ("Crew Profile", "Ship Profile", "Public Reputation"),
            "Hunter x Hunter": ("Nen Profile", "Hunter Career"),
            "Naruto": ("Shinobi Profile",),
            "Solo Max-Level Newbie": ("System Profile",),
            "Overgeared": ("Satisfy Profile",),
            "Reincarnated as a Slime": ("Evolution Profile",),
            "Bleach": ("Zanpakuto Profile", "Soul Reaper Record"),
        }
        for world, keys in expected.items():
            state = self.state(world)
            normalize_world_progression(state)
            for key in keys:
                self.assertIn(key, state["special"], f"{world}: {key}")
        hxh = self.state("Hunter x Hunter"); normalize_world_progression(hxh)
        self.assertIn("category_efficiency", hxh["special"]["Nen Profile"])
        solo = self.state("Solo Max-Level Newbie"); normalize_world_progression(solo)
        self.assertIn("floor_ecology", solo["special"]["System Profile"])
        slime = self.state("Reincarnated as a Slime"); normalize_world_progression(slime)
        self.assertIn("nation_development", slime["special"]["Evolution Profile"])

    def test_downtime_canon_ripples_and_elite_identity_are_recorded_locally(self):
        state = self.state("Bleach")
        normalize_world_depth(state)
        row = record_downtime(state, ["Study Hado formulae for a week"], 7 * 1440)
        self.assertEqual(row["kind"], "study")
        record_canon_ripples(state, [{"type": "canon_event", "title": "A breach", "location": "Seireitei", "narrative": "The walls fall."}])
        self.assertEqual(state["world_depth"]["canon_ripples"][-1]["title"], "A breach")
        state["combat"] = {"active": True, "enemy": {"name": "Hollow Guardian", "elite": True, "habit": "Circles left", "objective": "Protect the gate"}}
        normalize_world_depth(state)
        self.assertEqual(state["world_depth"]["elite_encounters"]["Hollow Guardian"]["habit"], "Circles left")

    def test_depth_rules_explicitly_preserve_player_freedom_and_no_extra_call(self):
        rules = world_depth_rules(self.state("Hunter x Hunter"))
        self.assertIn("NEVER a mandatory order", rules)
        self.assertIn("no extra model call", rules)
        self.assertIn("Vows", rules)

    def test_progress_panel_exposes_paths_and_signature_techniques(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Flexible development paths", js)
        self.assertIn("Signature techniques", js)
        self.assertIn("not a mandatory order", js)


if __name__ == "__main__":
    unittest.main()
