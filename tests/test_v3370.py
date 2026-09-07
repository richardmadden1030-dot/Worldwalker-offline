import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from campaign_features import (downtime_surprise_prompt, normalize_companion_combinations,
                               normalize_trophy_state, recent_chat_context)
from politics import normalize_political_state, political_regions_for_map
from simulation import compile_context_snapshot
from state_guard import apply_guarded_patch
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3370Tests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": world, "name": "Ari", "campaign_id": "v3370", "turn": 10,
                      "companions": [{"name": "Mina"}], "location": "Founders Hill"})
        return state

    def test_version_and_new_persistent_fields(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        for key in ("companion_combinations", "trophy_proposals", "legacy_trophies",
                    "dismissed_trophy_ids", "downtime_surprise_state", "message_delivery_state"):
            self.assertIn(key, BASE_STATE)

    def test_companion_combination_requires_real_party_and_becomes_usable(self):
        state = self.fresh()
        patch = {"companion_combinations": [{
            "name": "Twin Leaf Reversal", "participants": ["Ari", "Mina"],
            "description": "Mina redirects an incoming strike into Ari's counter.",
            "activation": "Both partners must see the attacker.", "limitation": "Fails if separated.",
            "mastery": 12, "combat_usable": True,
        }]}
        report = apply_guarded_patch(state, patch)
        self.assertIn("companion_combinations", report["accepted"])
        self.assertEqual(state["companion_combinations"][0]["name"], "Twin Leaf Reversal")
        self.assertIn("Twin Leaf Reversal", state["skills"])
        state["companion_combinations"].append({"name":"False Pair", "participants":["Ari","Stranger"]})
        normalize_companion_combinations(state)
        self.assertNotIn("False Pair", {row["name"] for row in state["companion_combinations"]})

    def test_trophy_is_only_a_proposal_until_player_accepts(self):
        state = self.fresh()
        apply_guarded_patch(state, {"trophy_proposals": [{"id":"banner-1", "title":"The Torn Banner",
                                                           "description":"Taken after the hill defense."}],
                                    "legacy_trophies": [{"id":"forged", "title":"Forged"}]})
        self.assertEqual([row["id"] for row in state["trophy_proposals"]], ["banner-1"])
        self.assertEqual(state["legacy_trophies"], [])
        state["dismissed_trophy_ids"] = ["banner-1"]
        normalize_trophy_state(state)
        self.assertEqual(state["trophy_proposals"], [])

    def test_small_player_founded_claim_is_exactly_one_hex_in_map_payload(self):
        state = self.fresh()
        state["political_regions"] = [{"name":"Ari's Refuge", "controller":"Ari's Refuge",
                                        "anchor":"Founders Hill", "player_founded":True,
                                        "hex_count":1, "scale":"holding"}]
        normalize_political_state(state)
        regions = political_regions_for_map(state, [{"name":"Founders Hill","x":42,"y":38,"current":True}])
        claim = next(row for row in regions if row["name"] == "Ari's Refuge")
        self.assertEqual(claim["hex_count"], 1)
        self.assertTrue(claim["player_founded"])
        state["political_regions"] = [{"name":"Fire Country", "controller":"Konoha", "scale":"nation"}]
        normalize_political_state(state)
        self.assertEqual(state["political_regions"][0]["hex_count"], 0)

    def test_recent_chats_are_explicit_in_every_compiled_context(self):
        state = self.fresh()
        state["chat_threads"] = {"Mina": [
            {"sender":"Ari", "direction":"outgoing", "text":"Warn the eastern guard about the traitor."},
            {"sender":"Mina", "direction":"incoming", "text":"I will alert them before sundown."},
        ]}
        context = recent_chat_context(state, "What happens at the eastern guard?")
        self.assertEqual(context[0]["thread"], "Mina")
        compiled = compile_context_snapshot(copy.deepcopy(state), state, "eastern guard")
        self.assertEqual(compiled["recent_chat_context"][0]["latest"][-1]["sender"], "Mina")
        self.assertIn("must affect", compiled["chat_context_rule"])

    def test_downtime_surprise_is_deterministic_and_rate_limited(self):
        state = self.fresh("Bleach")
        first = downtime_surprise_prompt(state, 60 * 1440, ["Train Kidō"])
        second = downtime_surprise_prompt(state, 60 * 1440, ["Train Kidō"])
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        state["downtime_surprise_state"] = {"last_turn": state["turn"] - 1}
        self.assertIsNone(downtime_surprise_prompt(state, 60 * 1440, ["Train Kidō"]))


if __name__ == "__main__":
    unittest.main()
