import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from canon_integrity import canon_identity_context
from game import GameSession
from state_guard import apply_guarded_patch, migrate_state
from worlds import APP_VERSION, BASE_STATE, abilities_for


class StableTurnAI:
    def request(self, rules, payload, max_output_tokens=0):
        return {
            "narrative": "The plan continues without corrupting the campaign.",
            "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
            "elapsed": {"amount": 15, "unit": "minutes"}, "interrupted": False,
            "completed_actions": payload.get("planned_actions", []), "deferred_actions": [],
            "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
            "suggested_actions": ["Continue"], "incoming_chats": [],
        }


class LongCampaignStringCompanionRegressionTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_canon_context_accepts_compact_companion_names(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", companions=["Emi Kuroda", "Riku Noma", "Jōnin Ayame Fushimi"])
        context = canon_identity_context("Naruto", "train with Team 11", state)
        self.assertIsInstance(context, str)

    def test_migration_removes_response_envelope_from_npc_memories(self):
        state = copy.deepcopy(BASE_STATE)
        state["npc_memories"] = {
            "Emi Kuroda": {"attitude": "trusted", "goal": "Support Team 11"},
            "current_activity": "Training in the yard",
            "quests": [{"name": "Wrong namespace"}],
            "elapsed": {"amount": 15, "unit": "minutes"},
            "completed_actions": ["Train"],
        }
        repaired = migrate_state(state, "3.43.0")
        self.assertEqual(set(repaired["npc_memories"]), {"Emi Kuroda"})
        self.assertTrue(any("NPC memories" in row for row in repaired["diagnostics"]["migration"]["repairs"]))

    def test_incoming_patch_cannot_reintroduce_misplaced_memory_fields(self):
        state = copy.deepcopy(BASE_STATE)
        apply_guarded_patch(state, {"npc_memories": {
            "Emi Kuroda": {"attitude": "trusted"},
            "interrupted": True,
            "goal_status": {"achieved": True},
        }})
        self.assertEqual(set(state["npc_memories"]), {"Emi Kuroda"})

    def test_advance_preparation_works_with_reported_campaign_shape(self):
        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(
            name="Chen Su", world="Naruto", opening_complete=True, turn=311,
            companions=["Emi Kuroda", "Riku Noma", "Jōnin Ayame Fushimi"],
            standing_orders=["Meditate", "Find a Hyūga archivist", "Train with Team 11"],
            stats={name: 50 for name in abilities_for("Naruto")},
        )
        game.ai = StableTurnAI()
        assessed = game.assess_time_skip(1, "moment", [], "normal", use_model=False)
        result = game.run_time_skip(
            assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"]
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["state"]["turn"], 312)


if __name__ == "__main__":
    unittest.main()
