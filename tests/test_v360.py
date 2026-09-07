import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import evaluations
from ai_client import AI
from director import (build_cause_effect, enrich_npc_depth,
                      ensure_productive_failures, maybe_offer_relationship_scene,
                      update_campaign_direction)
from evaluations import run_model_comparison
from game import GameSession
from simulation import deterministic_assessment
from worlds import BASE_STATE


class FakeEvalClient:
    provider = "local"

    def __init__(self, model):
        self.model = model
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    def request(self, instructions, payload, **kwargs):
        self.usage["calls"] += 1
        self.usage["input_tokens"] += 100
        self.usage["output_tokens"] += 50
        action = payload["action"]
        return {"narrative": f"The character resolves {action} while respecting chakra and every consequence.",
                "state_patch": {"location": "Training Ground"}, "events": [],
                "suggested_actions": ["Follow the new lead"]}


class WorldwalkerV360Tests(unittest.TestCase):
    def test_recurring_npc_depth_persists_without_revealing_secrets(self):
        state = copy.deepcopy(BASE_STATE)
        state["relationships"] = {"Konan": 70}
        state["npc_intentions"] = {"Konan": {"goal": "Protect the Rain", "status": "active"}}
        state["npc_memories"] = {"Konan": {"loyalties": ["Yahiko", "Nagato"], "fears": ["Civil war"],
                                                   "secrets": ["A private contingency"], "last_known_location": "Amegakure"}}
        depth = enrich_npc_depth(state)["Konan"]
        self.assertEqual(depth["loyalties"], ["Yahiko", "Nagato"])
        self.assertEqual(depth["opinion_of_player"], "70")
        self.assertIn("A private contingency", depth["secrets"])

    def test_director_tracks_goal_obstacle_npcs_and_canon_pressure(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Naruto", "canon_time_minutes": -20 * 1440,
                      "quests": [{"name": "Earn Iruka's Trust", "status": "active",
                                  "objectives": [{"text": "Complete the training exercise", "status": "active"}],
                                  "current_obstacles": ["Iruka remains cautious"]}],
                      "npc_intentions": {"Mizuki": {"goal": "Steal the scroll", "progress": 44, "status": "active"}}})
        direction = update_campaign_direction(state, [], [], 60)
        self.assertEqual(direction["primary_goal"], "Complete the training exercise")
        self.assertEqual(direction["next_obstacle"], "Iruka remains cautious")
        self.assertEqual(direction["unresolved_characters"][0]["name"], "Mizuki")
        self.assertTrue(direction["approaching_canon_event"]["title"])

    def test_relationship_scene_is_optional_and_not_every_turn(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"turn": 3, "location": "Konoha",
                      "npc_memories": {"Iruka": {"recurring": True, "goal": "Guide the academy class",
                                                     "last_known_location": "Konoha"}}})
        offer = maybe_offer_relationship_scene(state)
        self.assertEqual(offer["status"], "available")
        self.assertIn("Iruka", offer["prompt"])
        self.assertIsNone(maybe_offer_relationship_scene(state))

    def test_failed_checks_gain_a_specific_lead(self):
        data = {"updates": [], "suggested_actions": []}
        ensure_productive_failures(data, [{"action": "Train chakra control", "success": False}])
        self.assertEqual(data["updates"][0]["type"], "consequence")
        self.assertIn("weakness", data["suggested_actions"][0].lower())

    def test_cause_effect_names_action_and_roll(self):
        before = copy.deepcopy(BASE_STATE)
        after = copy.deepcopy(before)
        before["stats"] = {"Chakra Control": 20}
        after["stats"] = {"Chakra Control": 23}
        rows = build_cause_effect(before, after, ["Practice chakra control"],
                                  [{"action": "Practice chakra control", "success": True,
                                    "total": 72, "difficulty": 60}])
        self.assertIn("72 versus 60", rows[0]["because"])

    def test_action_queue_can_be_edited_and_reordered_without_time_moving(self):
        game = GameSession()
        game.state["queued_actions"] = ["First", "Second", "Third"]
        before = game.state.get("canon_time_minutes")
        self.assertEqual(game.update_queued_action(1, "Revised"), ["First", "Revised", "Third"])
        self.assertEqual(game.move_queued_action(2, 0), ["Third", "First", "Revised"])
        self.assertEqual(game.state.get("canon_time_minutes"), before)

    def test_model_comparison_uses_identical_scenarios_without_mutating_campaign(self):
        class FakeGame:
            settings = {"model": "alpha", "provider": "local"}
            state = {"untouched": True}
            def make_client(self, model): return FakeEvalClient(model)
            def ai_ready(self): return True
        game = FakeGame()
        before = copy.deepcopy(game.state)
        with tempfile.TemporaryDirectory() as temp, patch.object(evaluations, "EVAL_DIR", Path(temp)):
            result = run_model_comparison(game, ["alpha", "beta"], ["queued_actions"])
        self.assertEqual(game.state, before)
        self.assertEqual(len(result["ranking"]), 2)
        self.assertEqual({row["calls"] for row in result["ranking"]}, {1})

    def test_cloud_cost_cap_blocks_before_a_request(self):
        client = AI(key="unused", model="gpt-5.4", provider="cloud", max_estimated_cost_usd=0.000001)
        with self.assertRaisesRegex(RuntimeError, "estimated at"):
            client.request("Long instructions " * 50, {"action": "test"}, max_output_tokens=1000)

    def test_routine_training_politics_strategy_and_combat_do_not_roll(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Naruto", "stats": {"Ninjutsu": 30, "Willpower": 30}})
        actions = [
            "Train chakra control every morning for a week",
            "Negotiate a patrol agreement with the clan council",
            "Plan a strategy for protecting the eastern road",
            "Defeat an ordinary street bandit",
        ]
        budget = {"reachable_actions": actions, "deferred_actions": [], "time_dc_modifier": 0}
        self.assertEqual(deterministic_assessment(state, actions, budget)["checks"], [])

    def test_extreme_obstacles_and_power_leaps_still_roll(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "One Piece", "stats": {"Willpower": 30}})
        actions = ["Defeat an elite guardian alone", "Train to awaken a new Haki ability"]
        budget = {"reachable_actions": actions, "deferred_actions": [], "time_dc_modifier": 0}
        checks = deterministic_assessment(state, actions, budget)["checks"]
        self.assertEqual(len(checks), 2)
        self.assertTrue(checks[1]["major_event"])
        self.assertGreaterEqual(checks[0]["difficulty_min"], 70)

    def test_focused_month_training_now_produces_large_visible_gain(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({"world": "Naruto", "stats": {"Ninjutsu": 30, "Chakra Control": 30},
                           "special": {"Archetype": "Ninjutsu Student"}})
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("game.random.random", return_value=1.0):
            game.enforce_training_progress(data, [], 1, "months", ["Train Ninjutsu daily until I improve"], "normal")
        self.assertGreaterEqual(data["state_patch"]["stats"]["Ninjutsu"], 50)

    def test_major_power_leap_uses_its_visible_roll_not_hidden_chance(self):
        game = GameSession()
        game.state["power_goal_tracker"] = {"key": "train to awaken a new haki ability", "days_invested": 40}
        failed = game._check_power_goal_progress(
            ["Train to awaken a new Haki ability"], 1,
            [{"action": "Train to awaken a new Haki ability", "major_event": True,
              "success": False, "total": 70, "difficulty": 80}],
        )
        succeeded = game._check_power_goal_progress(
            ["Train to awaken a new Haki ability"], 1,
            [{"action": "Train to awaken a new Haki ability", "major_event": True,
              "success": True, "total": 90, "difficulty": 80}],
        )
        self.assertFalse(failed["mechanical_success"])
        self.assertTrue(succeeded["mechanical_success"])
        self.assertTrue(succeeded["roll_based"])

    def test_system_world_training_xp_is_noticeable_over_a_month(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state["world"] = "Overgeared"
        award, reasons = game.calculate_xp_award(["Practice blacksmithing every day"], [], 30 * 1440, "normal", [])
        self.assertGreaterEqual(award, 300)
        self.assertIn("30.0 effective days", reasons[0]["reason"])


if __name__ == "__main__":
    unittest.main()
