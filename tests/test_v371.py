import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from simulation import deterministic_assessment, normalize_assessment_for_agency
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV371Tests(unittest.TestCase):
    def state(self, difficulty="Adventurer"):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "name": "Yahiko", "world": "Naruto", "difficulty": difficulty,
            "stats": {"Taijutsu": 40, "Ninjutsu": 48, "Genjutsu": 30,
                      "Chakra Control": 42, "Willpower": 45, "Intellect": 38},
            "special": {"Archetype": "Ninjutsu Student"},
        })
        return state

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_lower_modes_remove_unsupported_model_impossibility(self):
        assessment = {"impossible": True, "requires_check": True,
                      "reason": "The council is unlikely to agree.", "lethal_risk": "none"}
        result = normalize_assessment_for_agency(
            self.state(), "Negotiate an alliance by offering shared patrol intelligence", assessment
        )
        self.assertFalse(result["impossible"])
        self.assertFalse(result["requires_check"])

    def test_literal_world_rule_blocks_remain(self):
        assessment = {"impossible": True, "hard_rule_block": True, "requires_check": False,
                      "reason": "The target died years ago.", "lethal_risk": "none"}
        result = normalize_assessment_for_agency(
            self.state(), "Negotiate face to face with the deceased target", assessment
        )
        self.assertTrue(result["impossible"])

    def test_nightmare_assessment_is_unchanged(self):
        assessment = {"impossible": True, "requires_check": True,
                      "reason": "The council is unlikely to agree.", "lethal_risk": "none"}
        self.assertEqual(
            normalize_assessment_for_agency(self.state("Nightmare"), "Negotiate an alliance", assessment),
            assessment,
        )

    def test_specific_power_method_bypasses_lower_mode_gate_but_not_nightmare(self):
        action = "Master a new Water Release technique through daily drills under Konan's guidance"
        budget = {"reachable_actions": [action], "deferred_actions": [], "time_dc_modifier": 0,
                  "available_minutes": 30 * 1440}
        self.assertEqual(deterministic_assessment(self.state(), [action], budget)["checks"], [])
        self.assertEqual(len(deterministic_assessment(self.state("Nightmare"), [action], budget)["checks"]), 1)

    def test_extreme_nonlethal_plan_with_a_concrete_method_uses_consequences_not_a_gate(self):
        action = "Overthrow the entire village council through documented corruption evidence and coordinated public petitions"
        budget = {"reachable_actions": [action], "deferred_actions": [], "time_dc_modifier": 0,
                  "available_minutes": 30 * 1440}
        self.assertEqual(deterministic_assessment(self.state(), [action], budget)["checks"], [])
        self.assertEqual(len(deterministic_assessment(self.state("Nightmare"), [action], budget)["checks"]), 1)

    def test_task_prompts_distinguish_player_favoring_and_nightmare_policy(self):
        game = GameSession()
        game.state = self.state()
        self.assertIn("PLAYER-FAVORING AGENCY POLICY", game.task_rules("moment"))
        game.state["difficulty"] = "Nightmare"
        self.assertIn("NIGHTMARE AGENCY POLICY", game.task_rules("moment"))

    def test_plausible_named_power_route_becomes_assured_progression(self):
        game = GameSession()
        game.state = self.state()
        with patch("engine_time.random.random", return_value=1.0):
            result = game._check_power_goal_progress(
                ["Learn a new Water Release technique through daily drills under Konan's guidance"], 7, []
            )
        self.assertTrue(result["mechanical_success"])
        self.assertTrue(result["assured_by_agency_policy"])
        self.assertFalse(result["roll_based"])

    def test_six_month_rigorous_yahiko_training_reaches_jonin_benchmark(self):
        game = GameSession()
        game.state = self.state()
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(
                data, [], 6, "months",
                ["Undertake rigorous all-around combat training every day"], "intense",
            )
        stat_patch = data["state_patch"]["stats"]
        self.assertGreaterEqual(stat_patch["Ninjutsu"], 100)
        self.assertGreaterEqual(stat_patch["Taijutsu"], 60)
        self.assertGreaterEqual(stat_patch["Chakra Control"], 60)
        benchmark = data["state_patch"]["special"]["Combat Benchmark"]
        self.assertEqual(benchmark["tier"], "Jōnin-level combatant")
        self.assertFalse(benchmark["official_rank"])

    def test_nightmare_keeps_old_training_rate_and_single_stat_behavior(self):
        game = GameSession()
        game.state = self.state("Nightmare")
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(
                data, [], 1, "months", ["Undertake rigorous combat training every day"], "normal"
            )
        self.assertEqual(data["state_patch"]["stats"]["Ninjutsu"] - 48, 20)
        self.assertNotIn("Taijutsu", data["state_patch"]["stats"])
        self.assertNotIn("Combat Benchmark", data["state_patch"].get("special", {}))


if __name__ == "__main__":
    unittest.main()
