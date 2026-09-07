import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module
from game import GameSession
from lit_systems import (build_floor_state, initialize_lit_systems,
                         normalize_memorable_inventory, process_lit_turn)
from state_guard import apply_guarded_patch, migrate_state
from world_progression import NARRATIVE_CRAFTING_RULE
from worlds import APP_VERSION, BASE_STATE, abilities_for, tower_floor_theme


class WorldwalkerV3110LitRPGTests(unittest.TestCase):
    def campaign(self, world, origin, archetype):
        game = GameSession()
        game.settings["autosave"] = False
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "System Tester", world, "Adventurer", "A determined specialist.",
                "", "", origin, archetype,
                {name: 30 for name in abilities_for(world)},
            )
        return game

    def test_release_schema_and_owned_system_records(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertIn("overgeared_system", BASE_STATE)
        self.assertIn("solo_system", BASE_STATE)

    def test_narrative_crafting_rule_keeps_components_out_of_inventory(self):
        self.assertIn("every world", NARRATIVE_CRAFTING_RULE)
        self.assertIn("MUST NOT be added to inventory", NARRATIVE_CRAFTING_RULE)
        self.assertIn("finished product", NARRATIVE_CRAFTING_RULE)

    def test_inventory_removes_ingredients_but_keeps_memorable_and_story_objects(self):
        before = {"inventory": ["Old Iron Sword"]}
        state = {"inventory": [
            "Old Iron Sword", "Star Iron Ore", "Invitation Letter",
            {"name": "Dawn-Splitter", "rating": "Rare", "effect": "Cuts armor", "creator": "System Tester"},
            {"name": "Vault Seal", "quest_item": True},
        ]}
        result = normalize_memorable_inventory(state, before)
        names = [x.get("name") if isinstance(x, dict) else x for x in state["inventory"]]
        self.assertNotIn("Star Iron Ore", names)
        self.assertIn("Invitation Letter", names)
        self.assertIn("Dawn-Splitter", names)
        self.assertEqual(state["inventory"][2]["effects"], ["Cuts armor"])
        self.assertEqual(result["removed_materials"], ["Star Iron Ore"])

    def test_overgeared_start_has_separate_class_production_social_and_world_tracks(self):
        state = self.campaign("Overgeared", "New Player", "Blacksmith").state
        system = state["overgeared_system"]
        for key in ("production_paths", "class_progression", "class_questlines",
                    "npc_affinity", "guild", "territory", "crafting_orders",
                    "rankings", "economy"):
            self.assertIn(key, system)
        self.assertEqual(system["class_progression"]["class"], "Beginner")
        self.assertEqual(system["class_reception"]["status"], "pending")
        self.assertIn("Blacksmithing", system["production_paths"])
        self.assertEqual(system["economy"]["personal_gold"], state["currency"]["amount"])
        self.assertIn("Production standing", system["rankings"])

    def test_overgeared_crafting_advances_the_correct_discipline_and_filters_ore(self):
        state = self.campaign("Overgeared", "New Player", "Blacksmith").state
        before = copy.deepcopy(state)
        state["inventory"] = ["Star Iron Ore", {
            "name": "Named Ember Blade", "rating": "Rare", "effects": ["Adds fire damage"],
            "restrictions": ["Requires Strength 40"], "creator": "System Tester",
        }]
        notes = process_lit_turn(before, state, ["Forge a named sword from star iron"],
                                 "The workshop rings for thirty days.", 30 * 1440)
        self.assertGreater(state["overgeared_system"]["production_paths"]["Blacksmithing"]["mastery"], 0)
        self.assertEqual(state["overgeared_system"]["class_progression"]["class"], "Beginner")
        self.assertNotIn("Star Iron Ore", state["inventory"])
        self.assertEqual(state["inventory"][0]["name"], "Named Ember Blade")
        self.assertTrue(any("PRODUCTION" in row for row in notes))
        self.assertTrue(any("MATERIALS" in row for row in notes))

    def test_overgeared_affinity_and_rankings_mirror_real_state(self):
        state = self.campaign("Overgeared", "New Player", "Blacksmith").state
        before = copy.deepcopy(state)
        state["relationships"] = {"Khan": {"score": 68}}
        state["affiliations"] = [{"faction": "Tzedakah Guild", "rank": "Member", "status": "active"}]
        process_lit_turn(before, state, ["Help Khan and talk about the guild"], "Khan listens.", 60)
        self.assertEqual(state["overgeared_system"]["npc_affinity"]["Khan"]["tier"], "Devoted")
        self.assertEqual(state["overgeared_system"]["guild"]["name"], "Tzedakah Guild")
        self.assertIn("Production standing", state["overgeared_system"]["rankings"])

    def test_solo_floor_uses_existing_tower_theme_and_has_complete_scenario(self):
        floor = build_floor_state(20)
        self.assertIn(tower_floor_theme(20), floor["name"])
        for key in ("scenario", "clear_condition", "deadline_days", "environment_rule",
                    "administrator", "ordinary_enemies", "elite_enemy", "boss",
                    "hidden_conditions", "routes"):
            self.assertTrue(floor.get(key), key)
        self.assertEqual(len(floor["hidden_conditions"]), 2)

    def test_solo_inspection_reveals_one_clue_without_auto_completing_it(self):
        state = self.campaign("Solo Max-Level Newbie", "Veteran Gamer", "All-Rounder").state
        before = copy.deepcopy(state)
        notes = process_lit_turn(before, state, ["Inspect the station for a hidden condition"], "I search carefully.", 30)
        hidden = state["solo_system"]["floor_state"]["hidden_conditions"]
        self.assertEqual(sum(bool(x["discovered"]) for x in hidden), 1)
        self.assertFalse(any(x["completed"] for x in hidden))
        self.assertTrue(any("HIDDEN-CONDITION CLUE" in row for row in notes))

    def test_solo_copy_attempt_records_condition_instead_of_granting_ability(self):
        state = self.campaign("Solo Max-Level Newbie", "Veteran Gamer", "All-Rounder").state
        before = copy.deepcopy(state)
        process_lit_turn(before, state, ["Try to copy the guardian's shield ability"], "The System observes.", 5)
        self.assertEqual(len(state["solo_system"]["copy_attempts"]), 1)
        self.assertEqual(state["special"]["System Profile"]["copied_abilities"], [])

    def test_solo_floor_clear_preserves_cleared_floor_report_then_builds_next_floor(self):
        state = self.campaign("Solo Max-Level Newbie", "Veteran Gamer", "All-Rounder").state
        before = copy.deepcopy(state)
        cleared_name = before["solo_system"]["floor_state"]["name"]
        state["tower_floor"] = 2
        state["level"] += 2
        state["xp"] += 300
        state["achievements"] = [{"name": "First Clear"}]
        process_lit_turn(before, state, ["Activate the ascent gate"], "The first floor is cleared.", 360)
        report = state["solo_system"]["floor_history"][-1]
        self.assertEqual(report["floor"], 1)
        self.assertEqual(report["name"], cleared_name)
        self.assertEqual(report["levels_gained"], 2)
        self.assertEqual(state["solo_system"]["floor_state"]["floor"], 2)
        self.assertEqual(state["special"]["System Profile"]["floor"], 2)

    def test_solo_artifacts_party_roles_rivals_and_achievement_chains_are_persistent(self):
        state = self.campaign("Solo Max-Level Newbie", "Veteran Gamer", "All-Rounder").state
        before = copy.deepcopy(state)
        state["companions"] = [{"name": "Mina", "role": "Scout", "notes": "Finds safe routes."}]
        state["inventory"] = [{"name": "Moon Key", "artifact": True, "rating": "Unique", "effects": ["Opens lunar gates"]}]
        state["achievements"] = [{"name": "Hidden Routebreaker"}]
        process_lit_turn(before, state, ["Travel with Mina"], "The party moves.", 3 * 1440)
        system = state["solo_system"]
        self.assertEqual(system["party_roles"][0]["role"], "Scout")
        self.assertEqual(system["artifact_index"][0]["name"], "Moon Key")
        self.assertIn("Scenario Defiance", system["achievement_chains"])
        self.assertGreater(system["rivals"][0]["influence"], 10)

    def test_lit_systems_are_app_owned_and_migrated_locally(self):
        state = copy.deepcopy(BASE_STATE)
        state["world"] = "Overgeared"
        apply_guarded_patch(state, {"overgeared_system": {"economy": {"personal_gold": 999999}}})
        self.assertNotEqual(state["overgeared_system"].get("economy", {}).get("personal_gold"), 999999)
        migrated = migrate_state({"world": "Solo Max-Level Newbie", "tower_floor": 4}, "3.10.0")
        self.assertEqual(migrated["solo_system"]["floor_state"]["floor"], 4)

    def test_panels_and_frontend_surface_both_systems_and_structured_inventory(self):
        app_module.game.state = copy.deepcopy(BASE_STATE)
        app_module.game.state["world"] = "Overgeared"
        initialize_lit_systems(app_module.game.state)
        with app_module.app.test_client() as client:
            data = client.get("/api/panels").get_json()
        self.assertIn("overgeared_system", data)
        self.assertIn("solo_system", data)
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for marker in ("CURRENT SCENARIO", "ABILITY COPY", "PRODUCTION PATHS",
                       "CRAFTING ORDERS", "inventory-detail-card"):
            self.assertIn(marker, js + css)


if __name__ == "__main__":
    unittest.main()
