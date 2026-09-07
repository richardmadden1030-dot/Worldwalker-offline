import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from naruto_system import build_chakra_affinity_profile, normalize_chakra_affinity_profile
from standing_intents import (active_standing_intents, advance_standing_intents,
                              infer_standing_intent, register_standing_intents,
                              standing_intent_context)
from world_progression import normalize_world_progression
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3290Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_durable_commands_become_hidden_persistent_intents(self):
        care = infer_standing_intent("Ensure Konan is cared for until she recovers", 4)
        training = infer_standing_intent("Have Jiraiya train the children every day", 4)
        self.assertEqual(care["kind"], "care")
        self.assertEqual(care["until_condition"], "she recovers")
        self.assertTrue(care["hidden_by_default"])
        self.assertEqual(training["kind"], "training")
        self.assertEqual(training["actor"], "Jiraiya")
        self.assertIsNone(infer_standing_intent("Ask Konan what happened", 4))

    def test_standing_intent_deduplicates_accumulates_and_can_end(self):
        state = {"turn": 2, "standing_intents": []}
        command = "Have Jiraiya train the children every day"
        first = register_standing_intents(state, [command])
        second = register_standing_intents(state, [command])
        self.assertEqual(first["adopted"], second["adopted"])
        self.assertEqual(len(state["standing_intents"]), 1)
        intent_id = first["adopted"][0]
        projected = standing_intent_context(state, 14 * 1440)[0]
        self.assertEqual(projected["new_milestones_due"], 2)
        advance_standing_intents(state, 14 * 1440, [{
            "id": intent_id, "status": "completed", "reason": "The course is complete."
        }])
        self.assertEqual(state["standing_intents"][0]["elapsed_minutes"], 14 * 1440)
        self.assertEqual(state["standing_intents"][0]["status"], "completed")
        self.assertEqual(active_standing_intents(state), [])

    def test_advance_passes_intent_to_gm_and_keeps_it_after_the_turn(self):
        class Narrator:
            def __init__(self):
                self.payload = None

            def request(self, rules, payload, max_output_tokens=0):
                self.payload = payload
                return {
                    "narrative": "Konan's care arrangements remain dependable while the week passes.",
                    "updates": [{"sequence": 1, "type": "consequence", "title": "Care continues",
                                 "canon_day": 7, "narrative": "The established routine remains in place."}],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 7, "unit": "days"}, "interrupted": False,
                    "completed_actions": ["Ensure Konan is cared for"], "deferred_actions": [],
                    "suggested_actions": ["Speak with Konan", "Inspect the shelter", "Review the week's reports"],
                }

        game = GameSession()
        game.ai = Narrator()
        game.state = copy.deepcopy(BASE_STATE)
        command = "Ensure Konan is cared for"
        game.state.update(name="Yahiko", world="Naruto", standing_orders=[command],
                          stats={name: 30 for name in abilities_for("Naruto")})
        game.run_time_skip(7, "days", [command], "normal", {"checks": []})
        self.assertEqual(game.ai.payload["persistent_intents"][0]["kind"], "care")
        self.assertEqual(game.state["standing_intents"][0]["elapsed_minutes"], 7 * 1440)
        self.assertEqual(game.state["standing_intents"][0]["status"], "active")
        self.assertNotIn(command, game.state["standing_orders"])

    def test_canon_naruto_starts_have_authoritative_affinity_profiles(self):
        expected = {
            "naruto_birth": ("Wind Release", ["Wind Release"], [], []),
            "naruto_graduation": ("Wind Release", ["Wind Release"], [], []),
            "yahiko_akatsuki": ("Water Release", ["Water Release"], [], ["Water Release"]),
            "pain_birth": ("Unconfirmed", [], list(("Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release")), list(("Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release"))),
        }
        for scenario_id, wanted in expected.items():
            profile = normalize_chakra_affinity_profile(canon_character_id=scenario_id, seed=scenario_id)
            self.assertEqual((profile["primary"], profile["natural_affinities"],
                              profile["proficiencies"], profile["mastered_natures"]), wanted)
        pain = normalize_chakra_affinity_profile(canon_character_id="pain_birth")
        self.assertEqual(pain["special_mastery_source"], "Rinnegan")
        self.assertFalse(pain["requires_kekkei_genkai"])

    def test_multiple_natural_affinities_require_a_lineage_mechanism(self):
        profile = build_chakra_affinity_profile(
            "I was born with dual natural Fire and Wind affinities.", "dual-affinity"
        )
        self.assertEqual(profile["natural_affinities"], ["Fire Release", "Wind Release"])
        self.assertTrue(profile["requires_kekkei_genkai"])
        self.assertEqual(profile["combined_nature_components"], ["Fire Release", "Wind Release"])

    def test_learning_an_off_affinity_nature_adds_proficiency_not_affinity(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "world": "Naruto", "campaign_id": "affinity-learning",
            "background": "My natural chakra affinity is Wind Release.",
            "special": {
                "Nature Affinity": "Wind Release",
                "Chakra Affinity Profile": build_chakra_affinity_profile(
                    "My natural chakra affinity is Wind Release.", "affinity-learning"
                ),
                "Known Jutsu": ["Water Release: Water Bullet"],
                "Shinobi Rank": "Genin", "Clan": "None",
            },
        })
        normalize_world_progression(state)
        affinity = state["special"]["Chakra Affinity Profile"]
        self.assertEqual(affinity["natural_affinities"], ["Wind Release"])
        self.assertIn("Water Release", affinity["proficiencies"])
        self.assertIn("Water Release", affinity["mastered_natures"])

    def test_single_affinity_does_not_create_a_generic_special_ability(self):
        game = GameSession()
        stats = {name: 20 for name in abilities_for("Naruto")}
        with patch("engine_campaign.random.random", return_value=1.0):
            profile = game.infer_starting_profile(
                "Naruto", "Academy Graduate", "Ninjutsu Student",
                "My natural chakra affinity is Wind Release.", stats,
                start_location="Konohagakure", allow_starting_specials=True,
            )
        self.assertEqual(profile["naruto_affinity_profile"]["natural_affinities"], ["Wind Release"])
        self.assertIsNone(profile["generated_ability"])

    def test_frontend_distinguishes_natural_and_learned_natures(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Natural affinities", source)
        self.assertIn("Learned proficiencies", source)
        self.assertIn("Special mastery source", source)


if __name__ == "__main__":
    unittest.main()
