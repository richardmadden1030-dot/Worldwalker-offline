import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE, abilities_for


class ResolutionAI:
    def __init__(self):
        self.payload = None

    def request(self, rules, payload, max_output_tokens=0):
        self.payload = payload
        return {
            "narrative": "The itinerary is resolved in order.",
            "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
            "elapsed": {"amount": 1, "unit": "days"},
            "interrupted": False, "interruption_kind": "", "interruption_reason": "",
            "interruption_context": "", "intervention_prompt": "",
            "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
            "goal_status": {}, "new_contacts": [], "incoming_chats": [],
            "completed_actions": payload.get("planned_actions", []), "deferred_actions": [],
            "suggested_actions": ["Follow the current lead", "Practice the signature skill", "Ask a local mentor"],
        }


class WorldwalkerV300Tests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession()

    def profile(self, world, background, random_values=(1.0, 1.0)):
        stats = {name: 30 for name in abilities_for(world)}
        with patch("engine_campaign.random.random", side_effect=random_values), \
             patch("engine_campaign.random.choice", side_effect=lambda seq: seq[0]), \
             patch("engine_campaign.random.uniform", return_value=1.0):
            return self.game.infer_starting_profile(
                world, "New Player", "Blacksmith" if world == "Overgeared" else "Scout",
                background, stats, allow_starting_specials=True,
            )

    def test_version_3_and_schema_8_are_declared(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertIn("class_profile", BASE_STATE)

    def test_explicit_hidden_class_is_complete_and_mechanical(self):
        profile = self.profile("Overgeared", "I begin with a hidden class.")
        hidden = profile["hidden_class"]
        self.assertNotIn(hidden["name"], {"Unidentified Hidden Class", "Unidentified Class Signature"})
        self.assertTrue(hidden["class_type"])
        for field in ("kind", "rank", "description", "effect", "limitation", "growth_path", "signature_skill"):
            self.assertTrue(hidden[field])
        self.assertTrue(hidden["stat_bonuses"])
        self.assertIn(hidden["signature_skill"], profile["skills"])
        self.assertTrue(all(profile["stats"][name] > 30 for name in hidden["stat_bonuses"]))
        self.assertGreater(profile["growth_profile"]["learning_rate"], 1.0)

    def test_explicit_class_and_ability_can_coexist_and_persist(self):
        profile = self.profile("Overgeared", "I begin with a hidden class and a fire ability.")
        self.assertIsNotNone(profile["hidden_class"])
        self.assertIsNotNone(profile["generated_ability"])
        state = self.game.new_campaign(
            "Ari", "Overgeared", "Adventurer", "I begin with a hidden class and a fire ability.",
            "", "", "New Player", "Blacksmith", {name: 30 for name in abilities_for("Overgeared")},
            preview_stats=profile["stats"], preview_profile=profile,
        )
        self.assertEqual(state["class_profile"]["name"], profile["hidden_class"]["name"])
        self.assertEqual(state["special"]["Hidden Class"]["name"], profile["hidden_class"]["name"])
        self.assertEqual(state["special"]["Starting Ability"]["name"], profile["generated_ability"]["name"])

    def test_rare_starting_ability_can_be_awarded_without_a_request(self):
        profile = self.profile("Naruto", "An ordinary academy hopeful.", random_values=(1.0, 0.0))
        self.assertIsNone(profile["hidden_class"])
        self.assertIsNotNone(profile["generated_ability"])
        self.assertIn(profile["generated_ability"]["name"], profile["skills"])

    def test_rare_hidden_class_can_be_awarded_without_a_request(self):
        profile = self.profile("Naruto", "An ordinary academy hopeful.", random_values=(0.0, 1.0))
        self.assertIsNotNone(profile["hidden_class"])
        self.assertIsNone(profile["generated_ability"])

    def test_canon_character_profiles_do_not_receive_random_extras(self):
        with patch("engine_campaign.random.random", return_value=0.0):
            preview = self.game.preview_campaign(
                "", "Bleach", "Adventurer", "", "", "", "", "", {},
                canon_character_id="ichigo_series_start",
            )
        self.assertIsNone(preview["starting_profile"]["hidden_class"])
        self.assertIsNone(preview["starting_profile"]["generated_ability"])

    def test_player_facing_creation_copy_does_not_call_content_generated(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        campaign = (ROOT / "backend" / "engine_campaign.py").read_text(encoding="utf-8")
        forbidden = ("GENERATED ABILITY", "GENERATED BACKSTORY", "Generated background loadout", "Generated from the character")
        for phrase in forbidden:
            self.assertNotIn(phrase, js)
            self.assertNotIn(phrase, campaign)
        self.assertNotIn("generated_from", campaign)

    def test_each_time_skip_check_keeps_its_own_action(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(
            name="Ari", world="Naruto", difficulty="Adventurer",
            stats={name: 30 for name in abilities_for("Naruto")},
        )
        ai = ResolutionAI()
        self.game.ai = ai
        orders = ["Scout the eastern road", "Practice chakra control", "Question the courier"]
        checks = [
            {"id": "scout", "action_index": 0, "reason": "Find tracks", "ability": "Intellect", "skill": None,
             "difficulty_min": 30, "difficulty_max": 30, "relevant_average_stat": 30, "lethal_risk": "none"},
            {"id": "train", "action_index": 1, "reason": "Control chakra", "ability": "Chakra Control", "skill": None,
             "difficulty_min": 30, "difficulty_max": 30, "relevant_average_stat": 30, "lethal_risk": "none"},
            {"id": "talk", "action_index": 2, "reason": "Read courier", "ability": "Intellect", "skill": None,
             "difficulty_min": 30, "difficulty_max": 30, "relevant_average_stat": 30, "lethal_risk": "none"},
        ]
        with patch("engine_time.random.randint", return_value=60):
            result = self.game.run_time_skip(1, "days", orders, "normal", {"checks": checks})
        self.assertEqual([roll["action"] for roll in result["rolls"]], orders)
        self.assertEqual([roll["action_index"] for roll in result["rolls"]], [0, 1, 2])
        roll_details = [entry.get("detail", "") for entry in result["story"] if entry.get("tag") == "roll"]
        self.assertEqual([detail.split(" · ", 1)[0] for detail in roll_details], [f"Action: {order}" for order in orders])


if __name__ == "__main__":
    unittest.main()
