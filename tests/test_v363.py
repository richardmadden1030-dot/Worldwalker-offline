import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV363Tests(unittest.TestCase):
    def fresh(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": "Naruto", "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v363-test", "opening_complete": True,
        })
        game.campaign_active = True
        return game

    def test_version_and_danger_state_schema(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertEqual(BASE_STATE["danger_scenario"], {})

    def test_warns_once_then_suppresses_repeat_nonlethal_difficulty_gate(self):
        game = self.fresh()
        first = game.assess_time_skip(1, "moment", "Defeat the elite guardian", "normal", use_model=False)
        self.assertTrue(first["assessment"]["difficult_checks"])

        game.acknowledge_danger_scenario("The guardian confrontation")
        repeated = game.assess_time_skip(1, "moment", "Press the elite guardian back", "normal", use_model=False)
        self.assertTrue(repeated["assessment"]["check_previews"])
        self.assertEqual(repeated["assessment"]["difficult_checks"], [])
        self.assertTrue(repeated["assessment"]["check_previews"][0]["warning_suppressed"])

    def test_new_lethal_action_is_never_suppressed_inside_warned_scenario(self):
        game = self.fresh()
        game.acknowledge_danger_scenario("The guardian confrontation")
        lethal = game.assess_time_skip(1, "moment", "Fight the boss to the death", "normal", use_model=False)
        preview = lethal["assessment"]["check_previews"][0]
        self.assertEqual(preview["risk"], "high")
        self.assertFalse(preview["warning_suppressed"])
        self.assertTrue(lethal["assessment"]["requires_difficulty_confirmation"])

    def test_committed_attack_language_starts_combat_immediately(self):
        game = self.fresh()
        incoming = {"narrative": "The missing-nin lunges at you with his blade; the strike is already committed.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(incoming, []))
        self.assertTrue(incoming["state_patch"]["combat"]["active"])

        player = {"narrative": "Flame gathers around the target.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(player, ["I cast Fireball at the missing-nin"]))
        self.assertTrue(player["state_patch"]["combat"]["active"])

    def test_negotiation_before_violence_does_not_force_combat(self):
        game = self.fresh()
        data = {"narrative": "The missing-nin waits, tense but listening.", "state_patch": {}}
        self.assertFalse(game.ensure_immediate_combat_patch(data, ["Negotiate to avoid the attack"]))

    def test_combat_outcome_clears_scenario_acknowledgement(self):
        game = self.fresh()
        game.acknowledge_danger_scenario("Bandit attack")
        game.state["combat"] = {"active": True, "log": [], "enemy": {"name": "Bandit"}}
        game.end_combat("fled")
        self.assertEqual(game.state["danger_scenario"], {})

    def test_frontend_skips_repeat_danger_notice_and_merges_lethal_consent(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('result.danger_notice_required !== false', js)
        self.assertIn('danger_warning_acknowledged: true', js)
        self.assertIn('confirmed_lethal: Boolean', js)


if __name__ == "__main__":
    unittest.main()
