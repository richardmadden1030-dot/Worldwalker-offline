import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3240PlayerAgencyTests(unittest.TestCase):
    def fresh(self, world="Naruto", difficulty="Adventurer"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": difficulty,
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v3240-test", "opening_complete": True, "canon_day": 0,
        })
        game.campaign_active = True
        return game

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_commanded_characters_obey_without_gm_pushback(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("that character carries out the order as given", rules)
        self.assertIn("Do not have them refuse, hesitate, or fail through GM fiat", rules)
        # Independent NPC agency is explicitly preserved, not removed.
        self.assertIn("independent NPCs, canon characters acting on their own motives", rules)

    def test_player_described_actions_are_carried_out_as_stated(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("carry out the action exactly as they described it", rules)
        self.assertIn("never from the GM quietly softening, downgrading, or overriding", rules)

    def test_non_combat_impossibility_rolls_instead_of_flat_refusal(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("genuinely impossible on paper under this world's own established rules", rules)
        self.assertIn("still resolve it with a roll instead of an outright refusal", rules)
        self.assertIn("never a flat \"nothing happens.\"", rules)
        self.assertIn("Combat and violence keep their own existing risk and danger rules unchanged", rules)
        # The old flat-block phrasing must be gone.
        self.assertNotIn("impossible actions are not rollable", rules)

    def test_extreme_and_lethal_risk_is_explicitly_preserved(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("real risk stays real there", rules)

    def test_nightmare_keeps_its_own_stricter_contract(self):
        game = self.fresh(difficulty="Nightmare")
        rules = game.task_rules("moment")
        self.assertIn("NIGHTMARE AGENCY POLICY", rules)
        self.assertIn("plausible actions may fail", rules)


if __name__ == "__main__":
    unittest.main()
