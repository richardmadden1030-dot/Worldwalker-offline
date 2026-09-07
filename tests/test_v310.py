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
from reliability import (canon_event_tracker, narrative_memory_snapshot,
                         record_progression_ledger, update_narrative_memory,
                         validate_campaign_state, visible_class_profile,
                         visible_skills)
from systems import normalize_quest_state_machine
from util import scene_art_confidence, scene_category, scene_image_url, scene_display_label
from worlds import APP_VERSION, BASE_STATE, WORLD_DATA, abilities_for
import app as app_module


class WorldwalkerV310Tests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession()
        self.game.settings["autosave"] = False

    def test_v310_schema_declares_owned_memory_and_progression_ledgers(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertIn("narrative_memory", BASE_STATE)
        self.assertIn("progression_ledger", BASE_STATE)

    def test_memory_updates_are_consumed_deduplicated_and_separated(self):
        before = copy.deepcopy(BASE_STATE)
        state = copy.deepcopy(BASE_STATE)
        state["turn"] = 2
        state["location"] = "Winston Smithy"
        state["memory_updates"] = {
            "unresolved_mysteries": ["The sealed furnace answers to no known class."],
            "promises": ["Mira promised to return with star iron."],
        }
        update_narrative_memory(before, state, "Inspect the furnace", "You promise to keep the smithy safe.")
        state["memory_updates"] = {"unresolved_mysteries": ["The sealed furnace answers to no known class."]}
        update_narrative_memory(state, state, "Inspect it again", "")
        memory = narrative_memory_snapshot(state)
        self.assertEqual(len(memory["unresolved_mysteries"]), 1)
        self.assertTrue(memory["promises"])
        self.assertTrue(memory["established_facts"])
        self.assertNotIn("memory_updates", state)

    def test_state_validator_catches_dual_location_and_dead_companion(self):
        before = copy.deepcopy(BASE_STATE)
        after = copy.deepcopy(BASE_STATE)
        after["companions"] = [{"name": "Mira", "location": "Winston"}]
        after["npc_memories"] = {"Mira": {"status": "deceased", "last_known_location": "Reidan"}}
        warnings = validate_campaign_state(before, after, "")
        self.assertTrue(any("active companion" in warning for warning in warnings))
        self.assertTrue(any("simultaneously placed" in warning for warning in warnings))

    def test_state_validator_catches_unexplained_ability_rename(self):
        before = copy.deepcopy(BASE_STATE)
        after = copy.deepcopy(BASE_STATE)
        detail = {"description": "Shapes fire into a narrow cutting edge.", "limitation": "Consumes aura quickly."}
        before["skills"] = {"Ember Edge": detail}
        after["skills"] = {"Flame Blade": copy.deepcopy(detail)}
        self.assertTrue(any("renamed" in warning for warning in validate_campaign_state(before, after, "")))

    def test_canon_tracker_explains_impossible_events_and_replacements(self):
        state = copy.deepcopy(BASE_STATE)
        state["canon_day"] = 5
        state["canon_divergences"] = [{
            "event": "The Bridge Ambush", "status": "impossible",
            "reason": "The ambusher was arrested beforehand.",
            "replacement": "Their employer hires a different team to recover the documents.",
        }]
        rows = canon_event_tracker(state, [{"day": 12, "title": "The Bridge Ambush", "location": "River Road", "summary": "An ambush."}])
        self.assertEqual(rows[0]["status"], "impossible")
        self.assertIn("different team", rows[0]["replacement"])

    def test_quest_progression_has_clues_obstacles_optional_goals_and_hint(self):
        state = {"world": "Overgeared", "quests": [{
            "name": "Find the Relic", "status": "Active",
            "objectives": [
                {"text": "Locate the vault", "progress": 50},
                {"text": "Do not alert the guild", "optional": True, "progress": 0},
            ],
            "current_knowledge": ["The key was sold in Winston"],
            "risks": ["The rival guild is searching too"],
            "first_step": "Question the key broker",
        }]}
        normalize_quest_state_machine(state)
        quest = state["quests"][0]
        self.assertEqual(quest["progress_percent"], 50)
        self.assertEqual(quest["discovered_clues"][0], "The key was sold in Winston")
        self.assertEqual(quest["current_obstacles"][0], "The rival guild is searching too")
        self.assertIn("Do not alert", quest["optional_objectives"][0])
        self.assertEqual(quest["next_hint"], "Question the key broker")

    def test_progression_ledger_records_exact_diffs_and_cause(self):
        before = copy.deepcopy(BASE_STATE)
        after = copy.deepcopy(BASE_STATE)
        after["turn"] = 4
        after["stats"]["Strength"] = 13
        after["skills"] = {"Stone Guard": {"description": "Brace against impact."}}
        entry = record_progression_ledger(before, after, "Train under Master Ro", 1440,
                                          [{"action": "Endurance drill", "total": 72, "difficulty": 55, "success": True}])
        self.assertEqual(entry["cause"], "Train under Master Ro")
        self.assertTrue(any(change["name"] == "Strength" and change["delta"] == 3 for change in entry["changes"]))
        self.assertTrue(any(change["name"] == "Stone Guard" for change in entry["changes"]))
        self.assertIn("72/55", entry["rolls"][0])

    def test_overgeared_does_not_randomly_award_a_class_without_the_creation_option(self):
        stats = {name: 30 for name in abilities_for("Overgeared")}
        with patch("engine_campaign.random.random", side_effect=[0.0, 1.0]), \
             patch("engine_campaign.random.choice", side_effect=lambda seq: seq[0]), \
             patch("engine_campaign.random.uniform", return_value=1.0):
            profile = self.game.infer_starting_profile("Overgeared", "New Player", "Blacksmith", "An ordinary crafter.", stats)
        self.assertIsNone(profile["hidden_class"])
        self.assertEqual(profile["class_profile"]["name"], "Beginner")
        self.assertEqual(profile["overgeared_class_start"], "narrative")

    def test_explicit_hidden_class_is_fully_identified(self):
        stats = {name: 30 for name in abilities_for("Naruto")}
        with patch("engine_campaign.random.choice", side_effect=lambda seq: seq[0]), \
             patch("engine_campaign.random.random", return_value=1.0), \
             patch("engine_campaign.random.uniform", return_value=1.0):
            profile = self.game.infer_starting_profile("Naruto", "Academy Graduate", "Ninjutsu Student", "I possess a hidden class.", stats)
        self.assertFalse(profile["hidden_class"]["discovery"]["concealed"])
        self.assertEqual(visible_class_profile(profile["hidden_class"])["name"], profile["hidden_class"]["name"])

    def test_component_rerolls_preserve_unselected_character_parts(self):
        stats = {name: 30 for name in abilities_for("Overgeared")}
        with patch("engine_campaign.random.choice", side_effect=lambda seq: seq[0]), \
             patch("engine_campaign.random.random", return_value=1.0), \
             patch("engine_campaign.random.uniform", return_value=1.0):
            preview = self.game.preview_campaign("Ari", "Overgeared", "Adventurer", "I have a fire ability.", "", "", "New Player", "Blacksmith", stats)
            old_background = preview["background"]
            old_ability = preview["starting_profile"]["generated_ability"]["name"]
            rerolled = self.game.reroll_campaign_preview(preview, "loadout", "I have a fire ability.")
        self.assertEqual(rerolled["background"], old_background)
        self.assertEqual(rerolled["starting_profile"]["generated_ability"]["name"], old_ability)
        self.assertNotEqual(rerolled["starting_profile"]["equipment"], preview["starting_profile"]["equipment"])

    def test_art_confidence_prefers_physical_location_over_old_battle_text(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Overgeared", location="Old Merchant Stall", timeline=["A battlefield burned yesterday."], combat={})
        self.assertEqual(scene_category(state), "merchant_shop")
        self.assertGreaterEqual(scene_art_confidence(state)["score"], 90)
        _url, category = scene_image_url(state)
        self.assertEqual(category, "merchant_shop")

    def test_landmark_scene_reports_the_art_actually_selected(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Konohagakure", weather="clear", timeline=[], world_events=[])
        image, category = scene_image_url(state)
        self.assertIn("naruto_konohagakure", image)
        self.assertEqual(scene_display_label(state, image, category), "naruto_konohagakure")

    def test_every_world_runs_three_deterministic_story_turns_cleanly(self):
        for world, data in WORLD_DATA.items():
            with self.subTest(world=world), patch("engine_campaign.random.random", return_value=1.0):
                game = GameSession()
                game.settings["autosave"] = False
                stats = {name: 30 for name in abilities_for(world)}
                ex_origin = next(iter(__import__("worlds").expansion_for(world)["origins"]))
                ex_arch = next(iter(__import__("worlds").expansion_for(world)["archetypes"]), "Jujutsu Sorcerer")
                game.new_campaign("Tester", world, "Adventurer", "A determined local explorer.", "", "", ex_origin, ex_arch, stats)
                for turn in range(3):
                    current_skills = copy.deepcopy(game.state.get("skills", {}))
                    current_skills[f"Field Lesson {turn + 1}"] = {"description": f"A practical lesson from turn {turn + 1}."}
                    result = game.apply_resolution(
                        {"narrative": f"Tester completes field lesson {turn + 1}.", "state_patch": {"skills": current_skills}, "events": [], "suggested_actions": []},
                        pending_action=f"Complete field lesson {turn + 1}",
                        progression_context={"actions": [f"Complete field lesson {turn + 1}"], "rolls": [], "elapsed_minutes": 5, "intensity": "normal"},
                    )
                    self.assertFalse(result["continuity_warnings"], result["continuity_warnings"])
                self.assertEqual(game.state["turn"], 3)
                self.assertEqual(len(game.state["progression_ledger"]), 3)
                self.assertTrue(narrative_memory_snapshot(game.state)["established_facts"])
                self.assertIn("score", game.public_state()["_scene_confidence"])

    def test_panels_expose_memory_divergence_quest_and_progression_surfaces(self):
        app_module.game.state = copy.deepcopy(BASE_STATE)
        app_module.game.state["world"] = "Naruto"
        app_module.game.state["narrative_memory"]["player_goals"] = [{"text": "Become a dependable shinobi."}]
        with app_module.app.test_client() as client:
            data = client.get("/api/panels").get_json()
        self.assertIn("narrative_memory", data)
        self.assertIn("canon_event_tracker", data)
        self.assertIn("progression_ledger", data)

    def test_frontend_contains_rerolls_memory_art_confidence_and_all_world_themes(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8") + (ROOT / "frontend" / "js" / "living-adventures.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("data-preview-reroll", "LONG-TERM NARRATIVE MEMORY", "_scene_confidence", "canon_event_tracker"):
            self.assertIn(marker, js + html)
        for world in WORLD_DATA:
            self.assertIn(world, js)
        self.assertIn('body[data-world="Bleach"]', css)


if __name__ == "__main__":
    unittest.main()
