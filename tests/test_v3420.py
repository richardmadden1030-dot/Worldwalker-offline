import copy
import tempfile
import unittest
from pathlib import Path

from ability_archive import GeneratedAbilityArchive, mechanic_signature
from evaluations import run_local_simulation_evaluation
from experience_systems import record_world_milestones, update_scenario_memory
from game import GameSession
from response_guard import normalize_assessment_response, normalize_object_response, normalize_turn_response
from worlds import APP_VERSION, BASE_STATE


class ResponseGuardTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_compact_response_is_recovered(self):
        data = normalize_turn_response({
            "story": "The scene advances.", "events": "A witness arrives",
            "updates": "The gate opens", "incoming_chats": "Come quickly",
            "state_patch": {"combat": {"enemy": "Gate Guard", "enemy_statuses": "Bound"}},
        })
        self.assertEqual(data["narrative"], "The scene advances.")
        self.assertEqual(data["events"][0]["message"], "A witness arrives")
        self.assertEqual(data["updates"][0]["narrative"], "The gate opens")
        self.assertEqual(data["state_patch"]["combat"]["enemy"]["name"], "Gate Guard")
        self.assertEqual(data["state_patch"]["combat"]["enemy_statuses"][0]["name"], "Bound")

    def test_non_object_helpers_are_safe(self):
        self.assertEqual(normalize_object_response("Yes.", "reply")["reply"], "Yes.")
        self.assertEqual(normalize_assessment_response("bad")["checks"], [])


class AtomicTurnTests(unittest.TestCase):
    def test_failed_turn_restores_all_mutable_surfaces(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.state = copy.deepcopy(BASE_STATE)
            game.state.update({"name": "Atomic", "world": "Naruto", "turn": 7})
            game.history = [{"turn": 7}]
            game.story_log = [{"text": "Before", "tag": "narrative"}]
            tx = game.begin_turn_transaction("time_resolve", {"orders": ["Train"]})
            game.state["turn"] = 8
            game.state["location"] = "Wrong Place"
            game.history.append({"turn": 8})
            game.story_log.append({"text": "Partial", "tag": "narrative"})
            failed = game.rollback_turn_transaction(tx, AttributeError("bad nested shape"))
            self.assertEqual(game.state["turn"], 7)
            self.assertEqual(game.state["location"], "Starting Region")
            self.assertEqual(len(game.history), 1)
            self.assertEqual(game.story_log[-1]["text"], "Before")
            self.assertEqual(failed["status"], "ready_to_retry")
            self.assertEqual(game.state["last_failed_turn"]["payload"]["orders"], ["Train"])


class ScenarioAndMilestoneTests(unittest.TestCase):
    def test_active_combat_scenario_has_cause_objective_and_risk(self):
        before = copy.deepcopy(BASE_STATE)
        state = copy.deepcopy(BASE_STATE)
        state.update({"name": "Rin", "world": "Naruto", "turn": 4, "location": "Forest Road"})
        state["combat"] = {"active": True, "enemy": {"name": "Missing-nin"}, "cause": "The Missing-nin attacked Rin.",
                           "victory_condition": "Drive them away.", "defeat_risk": "Capture."}
        state["encounter_state"] = {"phase": "active_combat"}
        result = update_scenario_memory(before, state, ["Defend"], {"narrative": "Steel meets steel."})
        self.assertEqual(result["active"]["kind"], "combat")
        self.assertIn("Missing-nin attacked", result["active"]["cause"])
        self.assertEqual(result["active"]["objective"], "Drive them away.")

    def test_world_milestones_dedupe(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Bleach", "turn": 10})
        data = {"narrative": "Mira finally achieves Shikai after hearing her blade's name.", "events": []}
        self.assertEqual(len(record_world_milestones(state, data)), 1)
        self.assertEqual(record_world_milestones(state, data), [])


class AbilityAndMatrixTests(unittest.TestCase):
    def test_mechanically_reworded_power_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = GeneratedAbilityArchive(Path(folder) / "abilities.json")
            first = {"name": "Stored Horizon", "governing_rule": "Stores kinetic momentum from every impact and releases the accumulated motion through a chosen strike."}
            renamed = {"name": "Velocity Vault", "governing_rule": "Accumulates motion and kinetic force from impacts, then releases that stored momentum in one selected blow."}
            archive.record("Jujutsu Kaisen", "birth_slot", first)
            self.assertTrue(archive.is_duplicate("Jujutsu Kaisen", "birth_slot", renamed))
            self.assertIn("momentum", mechanic_signature(renamed)["concepts"])

    def test_every_world_passes_free_playtest_matrix(self):
        report = run_local_simulation_evaluation()
        self.assertEqual(report["ai_calls"], 0)
        self.assertEqual(report["score"], 100)
        self.assertGreaterEqual(len(report["worlds"]), 9)


if __name__ == "__main__":
    unittest.main()
