import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from state_guard import apply_guarded_patch
from systems import (ensure_currency_state, parse_price, record_finance_debt,
                     resolve_finance_debt, resolve_shop_purchase)
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3441EconomyTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": world, "turn": 4, "canon_day": 10})
        return state

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)

    def test_fractional_prices_are_not_rounded_down_to_free(self):
        self.assertEqual(parse_price("0.5 Gold Coin"), 0.5)

    def test_slime_fractional_purchase_uses_exact_minor_units(self):
        state = self.fresh("Reincarnated as a Slime")
        state["currency"] = {"name": "Gold Coin", "amount": 1, "tracked": True}
        state["shops"] = [{"name": "Tempest Market", "inventory": [
            {"name": "Travel Cloak", "price": 0.5, "effect": "Keeps rain off", "category": "clothing"}
        ]}]
        ensure_currency_state(state)
        ok, _, paid = resolve_shop_purchase(state, "Tempest Market", "Travel Cloak")
        self.assertTrue(ok)
        self.assertEqual(paid, 0.5)
        self.assertEqual(state["currency"]["amount_minor"], 5000)
        self.assertEqual(state["currency"]["amount"], 0.5)
        self.assertEqual(state["inventory"][0]["effect"], "Keeps rain off")

    def test_shop_can_spend_a_named_secondary_currency(self):
        state = self.fresh()
        state["currency"] = {"name": "Ryo", "amount": 50, "tracked": True}
        state["currencies"] = {"Arena Token": 3}
        state["shops"] = [{"name": "Prize Desk", "inventory": [
            {"name": "Champion Ribbon", "price": 2, "currency": "Arena Token"}
        ]}]
        ok, _, _ = resolve_shop_purchase(state, "Prize Desk", "Champion Ribbon")
        self.assertTrue(ok)
        self.assertEqual(state["currencies"]["Arena Token"], 1)
        self.assertEqual(state["currency"]["amount"], 50)

    def test_narrative_only_world_rejects_ai_money_bookkeeping(self):
        state = self.fresh("Jujutsu Kaisen")
        state["currency"] = {"name": "Yen", "amount": 0, "tracked": False}
        report = apply_guarded_patch(state, {
            "currency": {"name": "Yen", "amount": 5000},
            "purchase_offer": {"item": "Tool", "price": 500},
            "recurring_finances": [{"label": "Wages", "kind": "income", "amount": 1000}],
        }, allow_time=False, source="turn")
        rejected = {row["field"] for row in report["rejected"]}
        self.assertTrue({"currency", "purchase_offer", "recurring_finances"}.issubset(rejected))
        self.assertFalse(state["currency"]["tracked"])

    def test_debt_payment_uses_available_cash_and_keeps_a_ledger(self):
        state = self.fresh()
        state["currency"] = {"name": "Ryo", "amount": 70, "tracked": True}
        debt = record_finance_debt(state, "Workshop rent", 100, "Ryo")
        ok, _, paid = resolve_finance_debt(state, debt["id"])
        self.assertTrue(ok)
        self.assertEqual(paid, 70)
        self.assertEqual(state["currency"]["amount"], 0)
        self.assertEqual(debt["amount"], 30)
        self.assertEqual(state["currency_ledger"][-1]["category"], "debt_payment")

    def test_approved_one_piece_poneglyph_skin_is_shipped(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('/fonts/nova-square.ttf', css)
        self.assertIn('[data-tone="special"]', css)
        self.assertIn('turnEnvelope.dataset.presentation = presentationWorld === "Naruto" ? "scroll" : "poneglyph"', js)
        self.assertTrue((ROOT / "frontend" / "art" / "one-piece" / "poneglyph-chronicle.png").is_file())


if __name__ == "__main__":
    unittest.main()
