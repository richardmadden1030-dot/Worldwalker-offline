import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import app as app_module
from game import GameSession
from reliability import visible_class_profile
from systems import relationship_snapshot
from worlds import APP_VERSION, BASE_STATE, timeline_for


class WorldwalkerV350Tests(unittest.TestCase):
    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertFalse(BASE_STATE["opening_complete"])

    def test_yahiko_start_is_normalized_and_precedes_foundation_and_death(self):
        game = GameSession()
        preview = game.preview_campaign(
            "", "Naruto", "Story", "ignored", "", "", "", "", {},
            canon_character_id="yahiko_akatsuki",
        )
        profile = preview["starting_profile"]
        self.assertEqual(preview["name"], "Yahiko")
        self.assertIn("Akatsuki Founder", profile["titles"])
        self.assertIn("Water Release Ninjutsu", profile["skills"])
        self.assertNotIn("Raised around", preview["background"])
        self.assertNotIn("Their own account adds", preview["background"])

        game.new_campaign(
            "", "Naruto", "Story", "ignored", "", "", "", "", {},
            preview_stats=profile["stats"], preview_profile=profile,
            canon_character_id="yahiko_akatsuki",
        )
        state = game.state
        self.assertEqual(state["name"], "Yahiko")
        self.assertEqual(state["position"], "Founder and Leader of the Akatsuki")
        self.assertGreater(state["reputation"]["Akatsuki"], 0)
        self.assertTrue(any(row["faction"] == "Akatsuki" and row["rank"] == "Founder and Leader"
                            for row in state["affiliations"]))
        self.assertIn("Nagato", [row["name"] for row in state["companions"]])
        self.assertIn("Konan", [row["name"] for row in state["companions"]])
        self.assertIn("Jiraiya", state["background"])
        self.assertNotIn("Rei Uzuki", str(state))

        relations = relationship_snapshot(state)
        self.assertNotIn("Akatsuki", [row["name"] for row in relations["people"]])
        self.assertIn("Akatsuki", [row["name"] for row in relations["factions"]])

        events = timeline_for("Naruto")["events"]
        founding = next(row for row in events if row["title"] == "The original Akatsuki is founded")
        death = next(row for row in events if row["title"].startswith("Yahiko's death"))
        self.assertLess(state["canon_day"], founding["day"])
        self.assertGreater(death["day"] - founding["day"], 300)

    def test_opening_cannot_overwrite_canon_identity_or_mechanics(self):
        game = GameSession()
        game.new_campaign(
            "", "Naruto", "Story", "", "", "", "", "", {},
            canon_character_id="yahiko_akatsuki",
        )
        original = copy.deepcopy(game.state)
        game.apply_resolution({
            "narrative": "A concrete opening situation unfolds in Amegakure.",
            "state_patch": {
                "name": "Generic Hero", "age": 22, "background": "Invented mentor Rei Uzuki.",
                "location": "Winston", "position": "Unaffiliated wanderer",
                "affiliations": [], "reputation": {"Akatsuki": 0},
                "skills": {"Generic Skill": {"rank": "Novice"}}, "titles": ["Member"],
            },
            "events": [], "suggested_actions": ["Speak to Nagato", "Speak to Konan", "Survey Amegakure"],
        }, is_opening=True)
        self.assertEqual(game.state["name"], original["name"])
        self.assertEqual(game.state["age"], 17)
        self.assertEqual(game.state["location"], "Amegakure")
        self.assertIn("Jiraiya", game.state["background"])
        self.assertIn("Water Release Ninjutsu", game.state["skills"])
        self.assertIn("Akatsuki Founder", game.state["titles"])
        self.assertGreater(game.state["reputation"]["Akatsuki"], 0)
        self.assertTrue(game.state["opening_complete"])

    def test_guaranteed_unknown_hidden_crafting_class_is_automatic_and_real(self):
        background = (
            "Rune is guaranteed a hidden crafting class tied to repairing cursed relics, "
            "but Rune does not know its true name."
        )
        with patch("engine_campaign.random.random", return_value=1.0):
            profile = GameSession().infer_starting_profile(
                "Overgeared", "Player", "Crafter", background, {}, start_location="Winston"
            )
        hidden = profile["hidden_class"]
        self.assertIsNotNone(hidden)
        self.assertTrue(hidden["discovery"]["concealed"])
        self.assertIn("Hexed Relic", hidden["true_name"])
        for key in ("effect", "limitation", "growth_path", "signature_skill", "stat_bonuses"):
            self.assertIn(key, hidden)
        public = visible_class_profile(hidden)
        self.assertNotIn("true_name", public)
        self.assertIn("Hexed Relic", public["name"])

    def test_moment_continuation_keeps_the_complete_standing_plan(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(
            world="One Piece", name="Nami", location="Foosha Village",
            stats={"Strength": 20, "Speed": 35, "Endurance": 28, "Willpower": 40,
                   "Intellect": 55, "Combat Skill": 25},
            standing_orders=["Chart the route", "Ask the navigator", "Prepare the ship"],
        )
        result = game.assess_time_skip(7, "moment", [], "normal", use_model=False)
        self.assertTrue(result["assessment"]["continuing_previous_orders"])
        self.assertEqual(
            result["assessment"]["standing_plan"],
            ["Chart the route", "Ask the navigator", "Prepare the ship"],
        )
        self.assertEqual(result["orders"], ["Chart the route"])
        self.assertEqual(result["assessment"]["deferred_actions"],
                         ["Ask the navigator", "Prepare the ship"])
        self.assertEqual(game.state["standing_orders"],
                         ["Chart the route", "Ask the navigator", "Prepare the ship"])

    def test_roll_summary_always_names_its_action(self):
        summary = GameSession().format_roll_summary(
            "Ask the navigator to chart the route..",
            {"roll": 53, "total": 59, "difficulty": 66, "success": False},
        )
        self.assertEqual(
            summary,
            "Ask the navigator to chart the route. — 53 +6 = 59/100 vs. 67 needed — FAILURE",
        )

    def test_world_metadata_has_visible_overgeared_defaults(self):
        with app_module.app.test_client() as client:
            payload = client.get("/api/worlds").get_json()
        overgeared = payload["worlds"]["Overgeared"]
        self.assertTrue(overgeared["start_options"])
        self.assertTrue(overgeared["starting_eras"])
        self.assertTrue(overgeared["start_options"][0]["label"])
        self.assertTrue(overgeared["starting_eras"][0]["label"])

    def test_frontend_instructions_and_contextual_tactics_are_current(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("local d20 rolls", html)
        self.assertIn("contextual d100", html)
        self.assertIn("Wear a clerk's disguise", js)
        self.assertIn("Enter across the rooftops", js)
        self.assertIn("Bribe a records clerk", js)
        self.assertIn("Apply measured pressure", js)
        self.assertIn("Scout every sign", js)
        self.assertIn("Secret shinobi path", js)
        self.assertIn("ordinaryGrowth", js)
        self.assertIn("removeOpeningSetupNotice", js)
        self.assertIn('$("#story-feed .story-entry").forEach', js)
        self.assertIn("opening_complete", js)


if __name__ == "__main__":
    unittest.main()
