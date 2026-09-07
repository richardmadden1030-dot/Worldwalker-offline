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


class WorldwalkerV3260RecurringFinancePersistenceTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v3260-test", "opening_complete": True, "canon_day": 0,
        })
        game.campaign_active = True
        return game

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_unmentioned_income_survives_an_unrelated_recurring_finances_patch(self):
        """The real bug: establishing a second income source later, without
        perfectly re-listing the first, used to silently delete the first."""
        game = self.fresh()
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        apply_guarded_patch(game.state, {"recurring_finances": [
            {"label": "Herb stall takings", "kind": "income", "amount": 20,
             "interval_days": 7, "next_due_day": 7, "active": True},
        ]}, allow_time=False)
        labels = {e["label"] for e in game.state["recurring_finances"]}
        self.assertEqual(labels, {"Chunin instructor salary", "Herb stall takings"})

    def test_explicit_deactivation_by_matching_label_still_works(self):
        game = self.fresh()
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        apply_guarded_patch(game.state, {"recurring_finances": [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": False},
        ]}, allow_time=False)
        self.assertEqual(len(game.state["recurring_finances"]), 1)
        self.assertFalse(game.state["recurring_finances"][0]["active"])

    def test_updating_an_existing_entry_by_label_replaces_not_duplicates(self):
        game = self.fresh()
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        apply_guarded_patch(game.state, {"recurring_finances": [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 450,
             "interval_days": 30, "next_due_day": 30, "active": True, "notes": "Promoted to jonin-sensei"},
        ]}, allow_time=False)
        self.assertEqual(len(game.state["recurring_finances"]), 1)
        self.assertEqual(game.state["recurring_finances"][0]["amount"], 450)

    def test_partial_update_keeps_existing_schedule_fields(self):
        game = self.fresh()
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True,
             "notes": "Original appointment"},
        ]
        apply_guarded_patch(game.state, {"recurring_finances": [
            {"label": "Chunin instructor salary", "amount": 450},
        ]}, allow_time=False)
        entry = game.state["recurring_finances"][0]
        self.assertEqual(entry["amount"], 450)
        self.assertEqual(entry["kind"], "income")
        self.assertEqual(entry["interval_days"], 30)
        self.assertEqual(entry["next_due_day"], 30)
        self.assertEqual(entry["notes"], "Original appointment")

    def test_harmless_label_punctuation_does_not_duplicate_income(self):
        game = self.fresh()
        game.state["recurring_finances"] = [
            {"label": "Chunin instructor salary", "kind": "income", "amount": 300,
             "interval_days": 30, "next_due_day": 30, "active": True},
        ]
        apply_guarded_patch(game.state, {"recurring_finances": [
            {"label": "Chunin instructor salary!", "amount": 450},
        ]}, allow_time=False)
        self.assertEqual(len(game.state["recurring_finances"]), 1)
        self.assertEqual(game.state["recurring_finances"][0]["amount"], 450)

    def test_daily_income_catches_up_a_full_year_without_truncation(self):
        game = self.fresh()
        game.state["currency"] = {"name": "Ryo", "amount": 0}
        game.state["recurring_finances"] = [
            {"label": "Daily stall", "kind": "income", "amount": 10,
             "interval_days": 1, "next_due_day": 1, "active": True},
        ]
        notes = game._pay_recurring_finances(365 * 1440 + 480)
        self.assertEqual(game.state["currency"]["amount"], 3650)
        self.assertEqual(game.state["recurring_finances"][0]["next_due_day"], 366)
        self.assertIn("x365 cycles", notes[0]["text"])

    def test_scheduled_events_get_the_same_omission_protection(self):
        game = self.fresh()
        game.state["scheduled_events"] = [
            {"title": "Grimmjow's rematch", "due_canon_day": 40, "resolved": False},
        ]
        apply_guarded_patch(game.state, {"scheduled_events": [
            {"title": "Merchant's delivery", "due_canon_day": 5, "resolved": False},
        ]}, allow_time=False)
        titles = {e["title"] for e in game.state["scheduled_events"]}
        self.assertEqual(titles, {"Grimmjow's rematch", "Merchant's delivery"})


class WorldwalkerV3260TradeAndFactionConflictTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v3260-test", "opening_complete": True, "canon_day": 0,
        })
        game.campaign_active = True
        return game

    def test_gm_rules_document_the_real_faction_clock_conflict_mechanic(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("opponent (a rival faction/NPC)", rules)
        self.assertIn("contested_location", rules)
        self.assertIn("the application resolves a real strength-weighted outcome automatically", rules)
        self.assertIn("This applies to trade disputes and blockades exactly like open conflict", rules)

    def test_gm_rules_require_real_consequences_for_trade_and_resource_scarcity(self):
        game = self.fresh()
        rules = game.task_rules("moment")
        self.assertIn("Tolls, blockades, secured or cut trade routes", rules)
        self.assertIn("should visibly struggle", rules)
        self.assertIn("more likely to act to secure supplies", rules)
        self.assertIn("shifts toward whoever is actually providing for them", rules)

    def test_faction_trade_rule_present_in_time_skip_but_not_combat_summary(self):
        """Confirms the rule reaches the tasks that actually need it while
        staying out of the size-constrained combat recap (see
        test_task_prompts_are_smaller_than_the_legacy_everything_prompt)."""
        game = self.fresh()
        self.assertIn("contested_location", game.task_rules("time_skip"))
        self.assertNotIn("contested_location", game.task_rules("combat_summary"))
        self.assertNotIn("contested_location", game.task_rules("opening"))


class WorldwalkerV3260PlaytestPresentationTests(unittest.TestCase):
    def test_queue_preview_does_not_call_routine_training_uncertain(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"Focused growth"', source)
        self.assertNotIn('? "Uncertain" : "Routine"', source)

    def test_sticky_modal_header_has_an_opaque_surface(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        modal_head = css.split(".modal-head{", 1)[1].split("}", 1)[0]
        self.assertIn("rgba(var(--glass-rgb),.97)", modal_head)


if __name__ == "__main__":
    unittest.main()
