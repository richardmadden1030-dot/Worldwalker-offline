import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from systems import normalize_quest_state_machine
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3250QuestCompletionTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v3250-test", "opening_complete": True, "canon_day": 0,
        })
        game.campaign_active = True
        return game

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_gm_rules_require_a_completable_path_for_player_stated_goals(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn('A player-stated goal (e.g. "I want to prepare for [event]") becomes a real quest', rules)
        self.assertIn("never sit permanently vague with no path to finishing it", rules)

    def test_gm_rules_distinguish_specific_from_ambiguous_goals(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("set quest objectives to those exact things", rules)
        self.assertIn("actively create narrative opportunities", rules)
        self.assertIn("credit real, felt progress toward it", rules)
        self.assertIn("consistent honest effort actually reaches completion by its due date", rules)

    def test_gm_rules_require_actually_completing_finished_quests(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("resolve the quest as complete in that turn's state_patch", rules)
        self.assertIn("A completable goal must actually be able to complete", rules)

    def test_narrative_world_quest_can_reach_completed_status(self):
        """A non-XP (narrative-mode) world's quest is not permanently stuck
        open -- a status of complete written by the GM is preserved through
        normalization, the same mechanism the AI's state_patch relies on."""
        state = self.fresh("Naruto").state
        state["quests"] = [{
            "name": "Prepare for the Chunin Exams", "status": "complete",
            "objectives": [{"text": "Master a new jutsu", "status": "complete", "progress": 100}],
        }]
        completed = normalize_quest_state_machine(state)
        self.assertIn("Prepare for the Chunin Exams", completed)
        self.assertEqual(state["quests"][0]["agenda_mode"], "narrative")


if __name__ == "__main__":
    unittest.main()
