import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from bleach_data import CANON_BAKUDO, CANON_HADO, academy_kido_skills
from continuity import update_continuity
from game import GameSession
from state_guard import apply_guarded_patch
from systems import record_purchase_offer, resolve_shop_purchase
from worlds import (
    APP_VERSION, WORLD_DATA, WORLD_EXPANSIONS, abilities_for,
    playable_characters_for, start_options_for, starting_eras_for,
)


class WorldwalkerV390BleachTests(unittest.TestCase):
    def make_original(self, origin="Shin'o Academy Senior", location="Shin'o Academy",
                      background="A diligent Soul Reaper student.", archetype="Kido Caster",
                      era="week_before_arrival"):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Bleach")}
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Test Soul Reaper", "Bleach", "Adventurer", background, "", "",
                origin, archetype, stats, start_location=location,
                starting_era_id=era,
            )
        return game

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_bleach_creator_is_soul_reaper_only_with_three_requested_eras(self):
        self.assertEqual(
            WORLD_EXPANSIONS["Bleach"]["origins"],
            ["Shin'o Academy Senior", "Recent Shin'o Academy Graduate"],
        )
        self.assertNotIn("Quincy Marksman", WORLD_EXPANSIONS["Bleach"]["archetypes"])
        starts = start_options_for("Bleach")
        self.assertEqual({row["location"] for row in starts}, {"Shin'o Academy", "Seireitei"})
        self.assertTrue(all("Soul Reaper" in row["note"] for row in starts))
        eras = starting_eras_for("Bleach")
        self.assertEqual([row["id"] for row in eras], [
            "week_before_arrival", "year_before_arrival", "turn_back_pendulum",
        ])
        self.assertEqual([row["start_day"] for row in eras], [-7, -365, -40157])

    def test_original_start_has_real_gear_kido_and_squad_quest_but_no_release(self):
        state = self.make_original().state
        self.assertEqual(state["position"], "Final-year Shin'o Academy Student")
        self.assertEqual(state["special"]["Squad"], "Unassigned")
        self.assertEqual(state["special"]["Shikai"], "Unachieved")
        self.assertEqual(state["special"]["Bankai"], "Unachieved")
        self.assertEqual(state["class_profile"], {})
        self.assertIn("Unnamed Asauchi", state["equipment"]["Weapon"])
        self.assertIn("Hado #1: Sho", state["skills"])
        self.assertIn("Bakudo #1: Sai", state["skills"])
        self.assertEqual(state["quests"][0]["name"], "Graduate and Choose a Division")
        self.assertTrue(any(row["name"] == "Learn the Zanpakutō's Name" for row in state["prerequisite_tracks"]))

    def test_wanting_shikai_does_not_grant_it_at_creation(self):
        state = self.make_original(background="I want to learn Shikai and eventually master Bankai.").state
        self.assertEqual(state["special"]["Shikai"], "Unachieved")
        self.assertEqual(state["special"]["Bankai"], "Unachieved")

    def test_explicit_owned_release_is_structured_and_bankai_requires_shikai(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Bleach")}
        generated = {
            "stage": "Bankai", "name": "Kageori", "release_command": "Fold the dusk",
            "shikai_name": "Kageori", "shikai_effect": "Folds nearby shadows into short defensive planes.",
            "shikai_form": "A dark segmented blade", "shikai_limitation": "Requires nearby shadow.",
            "shikai_counters": "Broad light thins the planes.", "bankai_name": "Bankai — Kageori Tenmaku",
            "bankai_manifestation": "A layered twilight canopy", "bankai_effect": "Extends the folding field.",
            "bankai_cost": "Rapid Reiryoku drain.", "bankai_counters": "Overwhelming area light.",
            "development_evidence": ["The stated background"],
        }
        with patch.object(game, "generate_zanpakuto_profile", return_value=generated), \
             patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Test Soul Reaper", "Bleach", "Adventurer",
                "I already possess and can use both Shikai and Bankai.", "", "",
                "Recent Shin'o Academy Graduate", "Zanjutsu Specialist", stats,
                start_location="Seireitei", starting_era_id="week_before_arrival",
            )
        self.assertEqual(game.state["special"]["Shikai"], "Achieved — Kageori")
        self.assertEqual(game.state["special"]["Bankai"], "Bankai — Kageori Tenmaku")
        self.assertIn("Shikai — Kageori", game.state["skills"])
        self.assertIn("Bankai — Kageori Tenmaku", game.state["skills"])

    def test_ichigo_is_the_only_canon_start_and_begins_in_active_combat(self):
        starts = playable_characters_for("Bleach")
        self.assertEqual([row["id"] for row in starts], ["ichigo_series_start"])
        scenario = starts[0]
        game = GameSession()
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Ichigo Kurosaki", "Bleach", "Adventurer", "", "", "",
                scenario["origin"], scenario["archetype"],
                {name: 10 for name in abilities_for("Bleach")},
                canon_character_id="ichigo_series_start",
            )
        state = game.state
        self.assertEqual(state["canon_day"], 0)
        self.assertEqual(state["location"], "Kurosaki Clinic")
        self.assertTrue(state["combat"]["active"])
        self.assertEqual(state["combat"]["enemy"]["name"], "Fishbone D")
        self.assertEqual(state["stats"]["Kido"], 5)
        self.assertEqual(state["stats"]["Reiatsu Control"], 22)
        self.assertEqual(state["active_canon_event"], "Rukia Kuchiki arrives in Karakura Town")
        self.assertIn(state["active_canon_event"], state["canon_events_fired"])
        self.assertEqual(state["special"]["Shikai"], "Unachieved")
        self.assertIn("Protect the Kurosaki Family", [q["name"] for q in state["quests"]])

    def test_established_kido_names_are_repaired_and_open_slots_persist(self):
        game = self.make_original()
        before = copy.deepcopy(game.state)
        patch_state = copy.deepcopy(game.state["skills"])
        patch_state["Hado #4: Wrong Name"] = {
            "rank": "Trained", "description": "wrong",
        }
        patch_state["Hado #47: Kogane Kusari"] = {
            "rank": "Advanced", "description": "A golden chain of flame binds what it strikes.",
        }
        apply_guarded_patch(game.state, {"skills": patch_state}, source="test")
        self.assertIn("Hado #4: Byakurai", game.state["skills"])
        self.assertNotIn("Hado #4: Wrong Name", game.state["skills"])
        self.assertEqual(
            game.state["skills"]["Hado #47: Kogane Kusari"]["kido"]["source_status"],
            "campaign_original",
        )
        renamed = copy.deepcopy(game.state["skills"])
        renamed.pop("Hado #47: Kogane Kusari")
        renamed["Hado #47: Another Spell"] = {"rank": "Advanced", "description": "different"}
        apply_guarded_patch(game.state, {"skills": renamed}, source="test")
        self.assertIn("Hado #47: Kogane Kusari", game.state["skills"])
        self.assertNotIn("Hado #47: Another Spell", game.state["skills"])

    def test_kido_catalogs_and_map_are_populated(self):
        self.assertGreaterEqual(len(CANON_HADO), 15)
        self.assertGreaterEqual(len(CANON_BAKUDO), 19)
        self.assertGreaterEqual(len(WORLD_DATA["Bleach"]["map"]), 30)
        self.assertTrue((ROOT / "assets" / "generated_maps" / "Bleach.webp").exists())

    def test_bleach_currency_is_narrative_only(self):
        game = self.make_original()
        self.assertFalse(WORLD_EXPANSIONS["Bleach"]["tracks_currency"])
        self.assertEqual(game.state["currency"], {"name": "Kan / Yen", "amount": 0, "tracked": False})
        self.assertEqual(game.state["currencies"], {})
        self.assertFalse(game.public_state()["_tracks_currency"])

    def test_bleach_rejects_currency_patches_and_purchase_buttons(self):
        game = self.make_original()
        report = apply_guarded_patch(game.state, {
            "currency": {"name": "Kan", "amount": 9999},
            "currencies": {"Yen": 5000},
            "purchase_offer": {"item": "Soul Candy", "price": 100},
        }, source="test")
        self.assertEqual({row["field"] for row in report["rejected"]}, {"currency", "currencies", "purchase_offer"})
        self.assertEqual(game.state["currency"]["amount"], 0)
        game.state["purchase_offer"] = {"item": "Soul Candy", "price": 100, "vendor": "Urahara"}
        self.assertIsNone(record_purchase_offer(game.state))
        ok, message, price = resolve_shop_purchase(game.state, "Urahara Shop", "Soul Candy")
        self.assertFalse(ok)
        self.assertIn("tracked money", message.lower())
        self.assertIsNone(price)

    def test_bleach_money_prose_does_not_trigger_currency_drift_warning(self):
        game = self.make_original()
        before = copy.deepcopy(game.state)
        after = copy.deepcopy(game.state)
        warnings = update_continuity(before, after, "Buy lunch", "You pay for lunch and leave the shop.")
        self.assertFalse(any("currency.amount" in row for row in warnings))


if __name__ == "__main__":
    unittest.main()
