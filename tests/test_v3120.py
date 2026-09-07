import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module
from game import GameSession
from systems import (normalize_quest_state_machine, quest_presentation_for,
                     uses_literal_quests)
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3120NarrativeAgendaTests(unittest.TestCase):
    def test_release_and_world_presentation_profiles(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertTrue(uses_literal_quests("Overgeared"))
        self.assertTrue(uses_literal_quests("Solo Max-Level Newbie"))
        for world in ("Naruto", "One Piece", "Hunter x Hunter", "Bleach",
                      "Reincarnated as a Slime", "Custom World"):
            self.assertFalse(uses_literal_quests(world))
            self.assertFalse(quest_presentation_for(world)["literal"])
        self.assertEqual(quest_presentation_for("Naruto")["tab_label"], "Mission Agenda")
        self.assertEqual(quest_presentation_for("Bleach")["rail_label"], "Current Order")

    def test_narrative_objectives_do_not_auto_complete_or_seed_locked_routes(self):
        state = {
            "world": "Naruto",
            "quests": [{
                "name": "Escort the Courier", "status": "Active",
                "objectives": [{"text": "Reach the border", "status": "complete", "progress": 100}],
                "branch_state": {"locked": ["Report to the Hokage"]},
            }],
        }
        completed = normalize_quest_state_machine(state)
        quest = state["quests"][0]
        self.assertEqual(completed, [])
        self.assertEqual(quest["status"], "Active")
        self.assertEqual(quest["agenda_mode"], "narrative")
        self.assertNotIn("progress_percent", quest)
        self.assertEqual(quest["branch_state"]["locked"], [])

    def test_literal_quest_objectives_still_complete_mechanically(self):
        state = {
            "world": "Overgeared",
            "quests": [{
                "name": "Khan's Commission", "status": "Active",
                "objectives": [{"text": "Forge the blade", "status": "complete", "progress": 100}],
            }],
        }
        completed = normalize_quest_state_machine(state)
        quest = state["quests"][0]
        self.assertEqual(completed, ["Khan's Commission"])
        self.assertEqual(quest["status"], "Completed")
        self.assertEqual(quest["agenda_mode"], "literal")
        self.assertEqual(quest["progress_percent"], 100)

    def test_explicit_narrative_completion_is_preserved(self):
        state = {"world": "One Piece", "quests": [{
            "name": "Promise at Dawn", "status": "Completed",
            "clear_conditions": ["Meet at the harbor"],
        }]}
        self.assertEqual(normalize_quest_state_machine(state), ["Promise at Dawn"])

    def test_chronicle_briefings_match_the_world(self):
        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Naruto", location="Konohagakure", quests=[])
        game.story_log = []
        before = copy.deepcopy(game.state)
        game.ensure_quest_briefings(before, "I start a mission to escort the bridge builder")
        narrative_text = game.story_log[-1]["text"]
        self.assertIn("ASSIGNMENT ADDED", narrative_text)
        self.assertIn("Next:", narrative_text)
        self.assertNotIn("Objective:", narrative_text)

        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Overgeared", location="Winston", quests=[])
        game.story_log = []
        before = copy.deepcopy(game.state)
        game.ensure_quest_briefings(before, "I start a quest to forge a named sword")
        literal_text = game.story_log[-1]["text"]
        self.assertIn("QUEST STARTED", literal_text)
        self.assertIn("Objective:", literal_text)

    def test_panels_expose_authoritative_presentation_profile(self):
        prior = copy.deepcopy(app_module.game.state)
        try:
            app_module.game.state = copy.deepcopy(BASE_STATE)
            app_module.game.state["world"] = "Hunter x Hunter"
            response = app_module.app.test_client().get("/api/panels")
            self.assertEqual(response.status_code, 200)
            profile = response.get_json()["quest_presentation"]
            self.assertEqual(profile["tab_label"], "Hunter Agenda")
            self.assertFalse(profile["literal"])
        finally:
            app_module.game.state = prior

    def test_frontend_has_separate_literal_and_narrative_renderers(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (qp.literal)", source)
        self.assertIn("This records responsibilities, promises, investigations", source)
        self.assertIn("Add your own agenda note", source)
        self.assertIn("Hidden quests discovered", source)


if __name__ == "__main__":
    unittest.main()
