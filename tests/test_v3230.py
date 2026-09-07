import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import apply_guarded_patch
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3230RecurringFinancesTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v3230-test", "opening_complete": True, "canon_day": 0,
        })
        game.campaign_active = True
        return game

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertEqual(BASE_STATE["recurring_finances"], [])

    def test_gm_rules_documents_recurring_finances_for_a_normal_world(self):
        game = self.fresh("Naruto")
        rules = game.task_rules("moment")
        self.assertIn("recurring_finances", rules)
        self.assertIn("do NOT manually re-add", rules)

    def test_gm_rules_excludes_recurring_finances_for_bleach(self):
        game = self.fresh("Bleach")
        rules = game.task_rules("moment")
        self.assertIn("never write currency, currencies, recurring_finances", rules)

    def test_monthly_income_pays_out_once_a_month_elapses(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 100}
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        # Not yet due: still one minute before day 30 begins.
        appends = game._pay_recurring_finances(30 * 1440 + 479)
        self.assertEqual(appends, [])
        self.assertEqual(game.state["currency"]["amount"], 100)
        # Due: day 30 has begun.
        appends = game._pay_recurring_finances(30 * 1440 + 480)
        self.assertEqual(game.state["currency"]["amount"], 400)
        self.assertEqual(game.state["recurring_finances"][0]["next_due_day"], 60)
        self.assertTrue(appends)
        self.assertIn("[FINANCES]", appends[0]["text"])
        self.assertFalse(appends[0]["major"])

    def test_long_time_skip_catches_up_multiple_cycles_in_one_pass(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 0}
        game.state["recurring_finances"] = [
            {"label": "Shop takings", "kind": "income", "amount": 50,
             "interval_days": 7, "next_due_day": 7, "active": True},
        ]
        # Skip a full year in one call — should apply all elapsed weekly cycles
        # at once instead of only the first, and never hang.
        appends = game._pay_recurring_finances(370 * 1440)
        self.assertEqual(game.state["currency"]["amount"], 52 * 50)
        self.assertIn("x52 cycles", appends[0]["text"])

    def test_expense_uses_available_cash_and_records_the_shortfall_as_debt(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 50}
        game.state["recurring_finances"] = [
            {"label": "Workshop rent", "kind": "expense", "amount": 200,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        game._pay_recurring_finances(30 * 1440 + 480)
        self.assertEqual(game.state["currency"]["amount"], 0)
        self.assertEqual(game.state["finance_debts"][0]["label"], "Workshop rent")
        self.assertEqual(game.state["finance_debts"][0]["amount"], 150)

    def test_inactive_entry_is_skipped(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 100}
        game.state["recurring_finances"] = [
            {"label": "Old job", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": False},
        ]
        game._pay_recurring_finances(30 * 1440 + 480)
        self.assertEqual(game.state["currency"]["amount"], 100)

    def test_bleach_never_pays_out_and_rejects_the_patch(self):
        game = self.fresh("Bleach")
        game.state["currency"] = {"name": "Currency", "amount": 100}
        game.state["recurring_finances"] = [
            {"label": "Stipend", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        game._pay_recurring_finances(30 * 1440 + 480)
        self.assertEqual(game.state["currency"]["amount"], 100)

        before = copy.deepcopy(game.state)
        result = apply_guarded_patch(game.state, {"recurring_finances": [{"label": "x", "kind": "income",
                                     "amount": 10, "interval_days": 1, "next_due_day": 1}]}, allow_time=False)
        self.assertEqual(game.state["recurring_finances"], before["recurring_finances"])

    def test_fire_canon_events_integrates_recurring_finances(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 0}
        game.state["canon_day"] = 0
        game.state["recurring_finances"] = [
            {"label": "Stipend", "kind": "income", "amount": 25,
             "interval_days": 10, "next_due_day": 10, "active": True},
        ]
        before_minutes = 0
        after_minutes = 15 * 1440
        appends = game.fire_canon_events(before_minutes, after_minutes)
        self.assertEqual(game.state["currency"]["amount"], 25)
        self.assertTrue(any("[FINANCES]" in a["text"] for a in appends))


if __name__ == "__main__":
    unittest.main()
