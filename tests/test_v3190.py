import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from lit_systems import process_lit_turn
from overgeared_classes import (CANON_CLASS_NAMES, CLASS_DESIGN_FAMILIES,
                                canon_class_prompt_reference)
from worlds import APP_VERSION, WORLD_EXPANSIONS, abilities_for


class WorldwalkerV3190SatisfyBreadthTests(unittest.TestCase):
    def campaign(self, origin="New Player", archetype="Summoner"):
        game = GameSession()
        game.settings["autosave"] = False
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Class Tester", "Overgeared", "Adventurer",
                "A versatile player seeking an unusual path through Satisfy.",
                "", "", origin, archetype,
                {name: 30 for name in abilities_for("Overgeared")},
            )
        return game

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_full_canon_catalog_is_available_only_as_class_design_reference(self):
        self.assertGreaterEqual(len(CANON_CLASS_NAMES), 130)
        self.assertEqual(len(CANON_CLASS_NAMES), len(set(CANON_CLASS_NAMES)))
        reference = canon_class_prompt_reference()
        for name in CANON_CLASS_NAMES:
            self.assertIn(name, reference)
        for family in CLASS_DESIGN_FAMILIES:
            self.assertIn(family, reference)
        self.assertIn("do not copy a canon class", reference)

    def test_satisfy_creation_offers_nonproduction_roles(self):
        archetypes = WORLD_EXPANSIONS["Overgeared"]["archetypes"]
        for name in ("Knight", "Magic Swordsman", "Priest/Healer", "Summoner",
                     "Tactician", "Beast Master", "Explorer", "Merchant/Orator"):
            self.assertIn(name, archetypes)

    def test_nonproduction_start_has_role_progression_without_fake_crafting_path(self):
        state = self.campaign(archetype="Summoner").state
        system = state["overgeared_system"]
        self.assertEqual(state["special"]["Satisfy Profile"]["class_type"], "Unassigned")
        self.assertEqual(system["class_reception"]["preferred_route"], "Summoner")
        self.assertEqual(system["production_paths"], {})
        self.assertNotIn("Production standing", system["rankings"])
        before = copy.deepcopy(state)
        process_lit_turn(before, state, ["Train with my summoned companion and coordinate our formation"],
                         "The pair refine their timing through repeated field drills.", 7 * 1440)
        self.assertEqual(state["overgeared_system"]["class_progression"]["stage"], "Awaiting class")
        self.assertEqual(state["overgeared_system"]["production_paths"], {})

    def test_a_nonproduction_character_can_later_choose_a_real_profession(self):
        state = self.campaign(archetype="Knight").state
        before = copy.deepcopy(state)
        process_lit_turn(before, state, ["Forge a reusable shield at the village smithy"],
                         "The knight learns the first steps of blacksmithing.", 3 * 1440)
        self.assertIn("Blacksmithing", state["overgeared_system"]["production_paths"])
        self.assertIn("Production standing", state["overgeared_system"]["rankings"])

    def test_explicit_original_hidden_class_uses_the_requested_role_not_relicwright(self):
        game = self.campaign(archetype="Summoner")
        with patch.object(game, "ai_bg_ready", return_value=False):
            profile = game.generate_hidden_class(
                "Overgeared", "I am guaranteed a hidden summoning class tied to willing spirit contracts.",
                45, ["Intelligence", "Wisdom"], game.state["stats"], concealed=False,
            )
        self.assertIn("Companion", profile["class_type"])
        self.assertNotIn("Relicwright", profile["name"])
        self.assertTrue(profile["signature_skill"])
        self.assertTrue(profile["growth_path"])

    def test_full_catalog_is_added_to_midgame_class_authorship_but_not_normal_turns(self):
        game = self.campaign(archetype="Explorer")
        normal = game.task_context("moment", "Explore the ruined road and scout ahead")
        authorship = game.task_context("moment", "I try to discover and unlock a unique explorer class")
        self.assertNotIn("Accessory Maker", normal)
        for name in CANON_CLASS_NAMES:
            self.assertIn(name, authorship)


if __name__ == "__main__":
    unittest.main()
