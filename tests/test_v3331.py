import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import migrate_state
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3331AgeTrackingTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_new_campaign_records_the_starting_age_anchor(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Naruto")}
        game.new_campaign("Ari", "Naruto", "Adventurer", "", "", "", "Academy Graduate",
                          "Scout", stats, age="17")
        self.assertEqual(game.state["age"], "17")
        self.assertEqual(game.state["age_at_campaign_start"], "17")
        self.assertEqual(game.state["age_anchor_year"], 1)

    def test_age_advances_once_per_completed_campaign_year(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Ari", world="Naruto", age="17",
                          age_at_campaign_start="17", age_anchor_year=1)
        before = copy.deepcopy(game.state)
        first = game.advance_clock(before, 11, "months")
        self.assertEqual(game.state["age"], "17")
        self.assertFalse(any("[BIRTHDAY]" in row.get("text", "") for row in first))
        before = copy.deepcopy(game.state)
        second = game.advance_clock(before, 25, "months")
        self.assertEqual(game.state["age"], "20")
        birthday = next(row for row in second if "[BIRTHDAY]" in row.get("text", ""))
        self.assertIn("Ari is now 20 after 3 completed campaign years", birthday["text"])

    def test_old_long_running_save_is_repaired_exactly_once(self):
        old = copy.deepcopy(BASE_STATE)
        old.pop("age_anchor_year", None)
        old.pop("age_at_campaign_start", None)
        old.update(age="17", calendar={"day": 1, "month": 1, "year": 4, "hour": 8, "minute": 0})
        repaired = migrate_state(old, "3.33.0")
        self.assertEqual(repaired["age"], "20")
        self.assertEqual(repaired["age_at_campaign_start"], "17")
        self.assertEqual(repaired["age_anchor_year"], 4)
        repaired_again = migrate_state(repaired, "3.33.1")
        self.assertEqual(repaired_again["age"], "20")

    def test_unknown_or_descriptive_age_is_not_invented(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(age="Unknown", age_anchor_year=1)
        before = copy.deepcopy(game.state)
        game.advance_clock(before, 60, "months")
        self.assertEqual(game.state["age"], "Unknown")


if __name__ == "__main__":
    unittest.main()
