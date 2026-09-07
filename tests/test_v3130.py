import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import apply_guarded_patch
from world_progression import normalize_world_progression
from worlds import APP_VERSION, BASE_STATE, abilities_for, start_options_for


class WorldwalkerV3130Tests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession()
        self.game.settings["autosave"] = False

    def profile(self, world, background, archetype="Brawler"):
        stats = {name: 30 for name in abilities_for(world)}
        with patch("engine_campaign.random.random", return_value=1.0), \
             patch("engine_campaign.random.choice", side_effect=lambda seq: seq[0]), \
             patch("engine_campaign.random.uniform", return_value=1.0):
            return self.game.infer_starting_profile(
                world, "Original Character", archetype, background, stats,
                start_location="Shin'o Academy" if world == "Bleach" else "Konohagakure",
            )

    def test_version_and_schema(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)

    def test_descriptive_magicule_placeholder_cannot_crash_normalization(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Reincarnated as a Slime", "special": {"Magicule Capacity": "Baseline; not yet measured"}})
        normalize_world_progression(state)
        self.assertEqual(state["special"]["Evolution Profile"]["magicule_capacity"], 0)

    def test_immense_bleach_pressure_changes_stats_and_resource_pool(self):
        plain = self.profile("Bleach", "A normal academy senior.", "Zanjutsu Specialist")
        immense = self.profile("Bleach", "A soul born with immense spiritual pressure.", "Zanjutsu Specialist")
        self.assertGreater(immense["stats"]["Reiatsu Control"], plain["stats"]["Reiatsu Control"])
        self.assertGreater(immense["stats"]["Willpower"], plain["stats"]["Willpower"])
        self.assertGreater(immense["resource_max"], plain["resource_max"])
        self.assertTrue(immense["growth_profile"]["background_stat_reasons"])

    def test_naruto_original_dojutsu_has_dedicated_profile(self):
        profile = self.profile("Naruto", "I was born with an original dojutsu that reads chakra rhythms.", "Sensor")
        lineage = profile["naruto_lineage_profile"]
        self.assertEqual(lineage["category"], "Dōjutsu")
        self.assertTrue(lineage["non_canon_allowed"])
        self.assertTrue(lineage["abilities"])
        self.assertTrue(lineage["limitations"])
        self.assertTrue(lineage["growth_path"])

    def test_generic_archetype_competence_is_stats_not_a_fake_skill(self):
        profile = self.profile("One Piece", "A trained dockside brawler.", "Brawler")
        self.assertFalse(any("fundamental" in name.lower() for name in profile["skills"]))
        self.assertEqual(profile["growth_profile"]["combat_style"], "Brawler")
        self.assertIn("fists", profile["growth_profile"]["style_rule"])

    def test_bleach_start_package_keeps_named_techniques_not_curriculum_labels(self):
        preview = self.game.preview_campaign(
            "Mira", "Bleach", "Adventurer",
            "A soul born with immense spiritual pressure who fights with Hakuda and body movement.",
            "", "", "Shin'o Academy Senior", "Hakuda Fighter", {},
            "Shin'o Academy", "Kidō honors", "", "week_before_ichigo",
        )
        profile = preview["starting_profile"]
        names = list(profile["skills"])
        self.assertTrue(any(name.startswith(("Hado #", "Bakudo #")) for name in names))
        self.assertFalse(any("curriculum" in name.lower() or "readiness" in name.lower() for name in names))
        self.assertEqual(profile["growth_profile"]["combat_style"], "Hakuda Fighter")
        self.assertIn("body", profile["growth_profile"]["style_rule"])
        self.assertGreater(profile["resource_max"], 100)

    def test_nested_state_shapes_are_repaired(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Naruto", "skills": "broken", "inventory": {}, "stats": {"Ninjutsu": "80", "Bad": 9}})
        report = apply_guarded_patch(state, {}, source="test")
        self.assertIsInstance(state["skills"], dict)
        self.assertIsInstance(state["inventory"], list)
        self.assertEqual(state["stats"]["Ninjutsu"], 80)
        self.assertNotIn("Bad", state["stats"])
        self.assertTrue(report["repairs"])

    def test_every_world_has_multiple_start_choices(self):
        for world in ("One Piece", "Hunter x Hunter", "Naruto", "Solo Max-Level Newbie", "Overgeared", "Reincarnated as a Slime", "Bleach", "Custom World"):
            self.assertGreaterEqual(len(start_options_for(world)), 4, world)


if __name__ == "__main__":
    unittest.main()
