import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import migrate_state, normalize_combat_payload
from worlds import APP_VERSION, BASE_STATE, abilities_for


class CompactCombatAI:
    def request(self, rules, payload, max_output_tokens=0):
        return {
            "narrative": "The tunnel guard attacks and combat begins.",
            "updates": [{"type": "action", "title": "Fight", "narrative": "The tunnel guard attacks."}],
            "state_patch": {"combat": {"active": True, "enemy": "Tunnel Guard"}},
            "events": [], "timeline_events": [],
            "elapsed": {"amount": 5, "unit": "minutes"},
            "interrupted": False,
            "completed_actions": ["Attack the tunnel guard"], "deferred_actions": [],
            "suggested_actions": ["Fight"],
        }


class WorldwalkerV3411Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_compact_enemy_string_is_normalized(self):
        combat = normalize_combat_payload({"active": True, "enemy": "Tunnel Guard"})
        self.assertEqual(combat["enemy"]["name"], "Tunnel Guard")

    def test_advance_accepts_compact_enemy_without_crashing(self):
        game = GameSession(); game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Tester", world="One Piece", difficulty="Adventurer", opening_complete=True,
                          stats={name: 35 for name in abilities_for("One Piece")})
        game.ai = CompactCombatAI()
        result = game.run_time_skip(1, "moment", ["Attack the tunnel guard"], "normal",
                                    {"checks": [], "time_budget": {"max_elapsed_minutes": 1440}})
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["state"]["combat"]["enemy"]["name"], "Tunnel Guard")
        self.assertTrue(result["state"]["combat"]["active"])

    def test_existing_malformed_nested_combat_repairs_on_migration(self):
        state = copy.deepcopy(BASE_STATE)
        state["combat"] = {"active": True, "enemy": "Guard", "enemy_statuses": "Paralyzed",
                           "cooldowns": "bad", "log": "bad"}
        repaired = migrate_state(state, "3.41.0")
        self.assertEqual(repaired["combat"]["enemy"]["name"], "Guard")
        self.assertEqual(repaired["combat"]["enemy_statuses"][0]["name"], "Paralyzed")
        self.assertEqual(repaired["combat"]["cooldowns"], {})
        self.assertEqual(repaired["combat"]["log"], [])

    def test_malformed_assessment_rows_do_not_block_advance(self):
        game = GameSession(); game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Tester", world="One Piece", difficulty="Adventurer", opening_complete=True,
                          stats={name: 35 for name in abilities_for("One Piece")})
        game.ai = CompactCombatAI()
        result = game.run_time_skip(1, "moment", ["Attack the tunnel guard"], "normal",
                                    {"checks": ["bad legacy row"], "time_budget": {"max_elapsed_minutes": 1440}})
        self.assertEqual(result["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
