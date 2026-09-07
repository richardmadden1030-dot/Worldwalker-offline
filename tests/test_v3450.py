import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from campaign_reliability import build_grounding_packet, reconcile_narrated_consequences, refresh_scene_state
from evaluations import score_evaluation
from game import GameSession
from gm_consistency import (coalesce_routine_updates, command_contracts, current_fact_view,
                            decision_profiles, evidence_packet, prepare_request,
                            record_fact_changes, semantic_issues)
from gm_policy import parse_player_intent
from knowledge import normalize_npc_knowledge
from simulation_core import action_commits_violence
from simulation_enhancements import apply_prompt_budget
from state_guard import migrate_state
from worlds import BASE_STATE, WORLD_DATA, abilities_for


def fresh(world="Naruto"):
    state = copy.deepcopy(BASE_STATE)
    state.update(name="Tester", world=world, location="Hall", turn=40, canon_day=90,
                 canon_time_minutes=90 * 1440, opening_complete=True,
                 stats={name: 50 for name in abilities_for(world)},
                 npc_memories={"Rina": {"subordinate": True, "attitude": "Loyal", "role": "Captain",
                                        "last_known_location": "Hall"}},
                 scene_state={"location": "Hall", "present": ["Rina"]})
    return state


class IntentContracts(unittest.TestCase):
    def test_negation_condition_and_observation(self):
        action = "Watch him, but do not attack unless he threatens Konan"
        result = parse_player_intent(action, fresh())
        self.assertIn("investigation", result["activity"])
        self.assertNotIn("combat", result["activity"])
        self.assertEqual(result["reference_candidates"], ["Rina"])
        self.assertTrue(result["conditional"])
        self.assertFalse(action_commits_violence(action))

    def test_scope_table(self):
        for action, expected in [
            ("Don't attack him", False), ("Do not kill him", False),
            ("If he attacks, then strike back", False),
            ("Only attack if the hostage is safe", False),
            ("Inspect the guard without attacking him", False),
            ("Ask Rina to arrange a spar", False),
            ("Ask for a spar and then punch him", True),
            ("Attack the guard; then leave", True),
            ("Never attack Rina; attack the bandit", True),
        ]:
            with self.subTest(action=action):
                self.assertEqual(action_commits_violence(action), expected)

    def test_does_not_resolve_ambiguous_pronouns_to_random_npc(self):
        state = fresh(); state["scene_state"]["present"].append("Mira")
        contract = parse_player_intent("Ask her what happened", state)
        self.assertEqual(contract["targets"], [])
        self.assertEqual(contract["reference_candidates"], ["Rina", "Mira"])


class EvidenceAndOrders(unittest.TestCase):
    def test_prepared_request_retains_ordinary_complication_limit(self):
        payload = prepare_request(fresh(), {"task": "narrator_and_resolution", "action": "Climb", "dice_result": {"success": False}})
        rows = [{"effect": "Slip", "cause": "Lost footing", "evidence_refs": ["roll:0"]},
                {"effect": "Lose rope", "cause": "Lost grip", "evidence_refs": ["roll:0"]}]
        self.assertTrue(semantic_issues(fresh(), {"causal_outcome": {"complications": rows}}, payload))

    def test_normal_advance_uses_planned_actions_for_commands(self):
        payload = prepare_request(fresh(), {"task": "resolve_time_skip", "planned_actions": ["Order Rina to deliver the invitation"]})
        self.assertEqual(payload["command_contracts"][0]["actor"], "Rina")
        self.assertIn("narrative_pacing", payload)

    def test_side_chat_greeting_is_not_an_order(self):
        payload = prepare_request(fresh(), {"thread": "Rina", "player_message": "How are you?"})
        self.assertEqual(payload["command_contracts"], [])
        payload = prepare_request(fresh(), {"thread": "Rina", "player_message": "Please deliver this invitation"})
        self.assertEqual(payload["command_contracts"][0]["actor"], "Rina")

    def test_mentioning_a_distant_person_does_not_make_them_a_witness(self):
        state = fresh()
        state["npc_memories"]["Mira"] = {"last_known_location": "Another city", "status": "active"}
        scene = refresh_scene_state(state, {"narrative": "Rina reads a report about Mira."})
        self.assertNotIn("Mira", scene["present"])

    def test_legacy_dict_shaped_motives_are_safe(self):
        state = fresh(); state["npc_memories"]["Rina"]["loyalties"] = {"leader": "Tester"}
        self.assertTrue(decision_profiles(state, ["Rina"])[0]["loyalties"])

    def test_made_up_information_source_fails(self):
        state = fresh(); payload = prepare_request(state, {"action": "Train secretly"})
        data = {"causal_outcome": {"reactions": [{"actor": "Distant king", "knowledge_source": "a messenger said so"}]}}
        self.assertTrue(semantic_issues(state, data, payload))

    def test_witness_ref_is_actor_specific(self):
        state = fresh(); payload = prepare_request(state, {"action": "Greet Rina"})
        ref = payload["turn_evidence"][0]["id"]
        data = {"causal_outcome": {"reactions": [{"actor": "Rina", "response": "Returns the greeting", "evidence_refs": [ref]}]}}
        self.assertFalse(semantic_issues(state, data, payload))
        data["causal_outcome"]["reactions"][0]["actor"] = "Distant king"
        self.assertTrue(semantic_issues(state, data, payload))

    def test_hidden_skill_not_disclosed_by_presence(self):
        state = fresh(); state["skills"] = {"Secret Lotus": {"hidden": True, "effect": "Conceals aura"}}
        payload = prepare_request(state, {"action": "Speak about the weather"})
        data = {"causal_outcome": {"reactions": [{"actor": "Rina", "response": "Asks about Secret Lotus", "evidence_refs": [payload["turn_evidence"][0]["id"]]}]}}
        self.assertTrue(semantic_issues(state, data, payload))

    def test_future_knowledge_and_dead_witness_excluded(self):
        state = fresh()
        state["npc_memories"]["Rina"].update(status="deceased", knowledge={"confirmed": [
            {"fact": "An undelivered letter", "available_at_minutes": state["canon_time_minutes"] + 5},
            {"fact": "Future discovery", "turn": 50}]})
        self.assertEqual(evidence_packet(state), [])

    def test_information_delivery_time_matters(self):
        state = fresh(); payload = prepare_request(state, {"action": "Send Rina to tell Mira the result"})
        data = {"elapsed": {"amount": 20, "unit": "minutes"},
                "command_outcomes": [{"actor": "Rina", "status": "obeyed"}],
                "information_events": [{"source": "Rina", "recipients": ["Mira"], "fact": "A public result", "delay_minutes": 15}],
                "causal_outcome": {"reactions": [{"actor": "Mira", "information_event_index": 0, "elapsed_minutes": 10}]}}
        self.assertTrue(semantic_issues(state, data, payload))
        data["causal_outcome"]["reactions"][0]["elapsed_minutes"] = 16
        self.assertFalse(semantic_issues(state, data, payload))
        data["causal_outcome"]["reactions"][0]["elapsed_minutes"] = 30
        self.assertTrue(semantic_issues(state, data, payload))

    def test_failed_roll_is_evidence_not_an_arbitrary_source(self):
        payload = prepare_request(fresh(), {"action": "Climb the wall", "dice_result": {"success": False, "action": "Climb the wall"}})
        data = {"causal_outcome": {"complications": [{"effect": "The foothold gives way", "cause": "Failed climb", "evidence_refs": ["roll:0"]}]}}
        self.assertFalse(semantic_issues(fresh(), data, payload))

    def test_loyal_subordinate_cannot_refuse_without_evidence(self):
        state = fresh(); payload = prepare_request(state, {"action": "Order Rina to deliver the invitation"})
        self.assertEqual(payload["command_contracts"][0]["actor"], "Rina")
        data = {"narrative": "Rina refuses the order because she prefers another approach."}
        self.assertTrue(semantic_issues(state, data, payload))
        data = {"narrative": "Rina accepts the invitation and leaves to deliver it.", "command_outcomes": [{"actor": "Rina", "status": "in_progress"}]}
        self.assertFalse(semantic_issues(state, data, payload))

    def test_established_injury_can_block_order(self):
        state = fresh(); state["npc_memories"]["Rina"]["injuries"] = ["Broken legs prevent walking"]
        payload = prepare_request(state, {"action": "Order Rina to walk to the village"})
        ref = next(row["id"] for row in payload["turn_evidence"] if row["kind"] == "injuries")
        data = {"command_outcomes": [{"actor": "Rina", "status": "blocked", "evidence_refs": [ref]}]}
        self.assertFalse(semantic_issues(state, data, payload))

    def test_friendship_does_not_imply_authority(self):
        state = fresh(); state["npc_memories"]["Rina"].pop("subordinate")
        self.assertEqual(command_contracts(state, "Tell Rina to follow me"), [])


class OutcomesMemoryAndPacing(unittest.TestCase):
    def test_failed_purchase_does_not_award_inventory(self):
        state = fresh(); before = copy.deepcopy(state)
        data = {"consequence_manifest": [{"kind": "item", "target": "Compass", "change": "refused"}]}
        reconcile_narrated_consequences(before, state, data)
        self.assertNotIn("Compass", json.dumps(state["inventory"]))
        data["state_patch"] = {"inventory": [{"name": "Compass"}]}
        self.assertTrue(semantic_issues(state, data))

    def test_named_skill_requires_mechanics_not_placeholder(self):
        state = fresh()
        data = {"narrative": "You learned the technique Silent Step.", "state_patch": {}}
        self.assertTrue(semantic_issues(state, data))
        data["consequence_manifest"] = [{"kind": "skill", "target": "Silent Step", "details": {"effect": "Muffles footfalls", "category": "Utility"}}]
        self.assertFalse(semantic_issues(state, data))
        reconcile_narrated_consequences(copy.deepcopy(state), state, data)
        self.assertIn("Silent Step", state["skills"])

    def test_explicit_losses_and_recovery_not_reawarded(self):
        state = fresh(); state.update(skills={"Test Skill": {"effect": "Test"}}, titles=["Champion"], conditions=[{"name": "Burned"}])
        data = {"consequence_manifest": [{"kind": "skill", "target": "Test Skill", "change": "removed"},
                                         {"kind": "title", "target": "Champion", "change": "lost"},
                                         {"kind": "condition", "target": "Burned", "change": "cured"}]}
        reconcile_narrated_consequences(copy.deepcopy(state), state, data)
        self.assertEqual(state["skills"], {})
        self.assertEqual(state["titles"], [])
        self.assertEqual(state["conditions"], [])

    def test_current_facts_replace_authority_not_history(self):
        before = fresh(); state = copy.deepcopy(before)
        state["npc_memories"]["Rina"].update(role="Former captain", attitude="Hostile")
        state["relationships"] = {"Rina": "Enemy"}
        record_fact_changes(before, state)
        packet = build_grounding_packet(state, "Ask Rina for help")
        current = packet["current_fact_view"]
        self.assertTrue(any(row["value"] == "Former captain" for row in current["current"]))
        self.assertTrue(any(row["previous"] == "Captain" for row in current["superseded_history"]))
        self.assertEqual(packet["npc_decision_profiles"][0]["relationship"], "Enemy")

    def test_knowledge_timestamp_survives_normalization(self):
        state = fresh(); state["npc_memories"]["Rina"]["knowledge"] = {"confirmed": [{"id": "a", "fact": "Old event", "turn": 3, "canon_day": 20, "source": "witness"}]}
        normalize_npc_knowledge(state)
        record = state["npc_memories"]["Rina"]["knowledge"]["confirmed"][0]
        self.assertEqual((record["id"], record["turn"], record["canon_day"]), ("a", 3, 20))

    def test_routine_grouping_keeps_all_concrete_progress_and_decisions(self):
        updates = [{"type": "action", "significance": "routine", "routine_group": "training", "canon_day": 1, "narrative": "Footwork improves."},
                   {"type": "action", "significance": "routine", "routine_group": "training", "canon_day": 10, "narrative": "Stamina improves."},
                   {"type": "action", "significance": "milestone", "narrative": "You awakened a new technique."},
                   {"type": "interruption", "significance": "decision", "narrative": "Rina asks whether to accept the offer."}]
        output = coalesce_routine_updates(updates)
        self.assertEqual(len(output), 3)
        self.assertIn("Stamina improves", output[0]["narrative"])
        self.assertEqual(output[-1]["type"], "interruption")

    def test_routine_only_skip_should_not_interrupt(self):
        data = {"interrupted": True, "interruption_kind": "other", "updates": [{"significance": "routine", "narrative": "Practice continues."}]}
        self.assertTrue(semantic_issues(fresh(), data))
        data["interruption_kind"] = "danger"
        self.assertFalse(semantic_issues(fresh(), data))

    def test_keyword_stuffing_cannot_pass_outcome_contract(self):
        scenario = {"state": {"combat": {"active": False}}, "must_address": ["watch"], "outcome_assertions": [{"kind": "no_combat"}]}
        data = {"narrative": "You watch peacefully without combat. " * 4, "state_patch": {"combat": {"active": True}}, "suggested_actions": ["Watch", "Leave"]}
        self.assertLess(score_evaluation(scenario, data)["score"], 50)

    def test_old_save_needs_no_new_creation_fields(self):
        state = fresh(); state.pop("fact_history", None)
        restored = migrate_state(json.loads(json.dumps(state)))
        # migrate_state returns a state/report pair in some historical versions.
        restored = restored[0] if isinstance(restored, tuple) else restored
        self.assertTrue(command_contracts(restored, "Order Rina to deliver the message"))
        self.assertTrue(current_fact_view(restored, ["Rina"])["current"])

    def test_small_prompt_retains_current_fact_view(self):
        state = fresh()
        packet = build_grounding_packet(state, "Speak to Rina")
        result = apply_prompt_budget({"grounding_packet": packet, "history": ["old " * 100000]}, state, "Speak to Rina")
        self.assertIn("current_fact_view", result["grounding_packet"])


class RepairAndMultiTurn(unittest.TestCase):
    def test_valid_turn_does_not_add_an_ai_call(self):
        game = GameSession(); game.state = fresh()
        class Client:
            model = "test"
            usage = {}
            calls = 0
            def request(self, *args, **kwargs):
                self.calls += 1
                return {"narrative": "The letter arrives safely. Rina thanks you.", "state_patch": {}}
        client = Client()
        game.request_with_narrative("test", {"task": "narrator_and_resolution", "action": "Read the letter"}, 1000, client)
        self.assertEqual(client.calls, 1)

    def test_side_chat_uses_current_memory_and_command_contract(self):
        game = GameSession(); game.state = fresh(); game.settings["model"] = "test"
        game.state["contacts"] = {"Rina": {"name": "Rina", "can_contact": True}}
        class Client:
            calls = []
            def request(self, rules, payload, **kwargs):
                self.calls.append(copy.deepcopy(payload))
                return {"reply": "I will deliver the invitation as sealed.", "state_patch": {}, "command_outcomes": [{"actor": "Rina", "status": "in_progress"}]}
        client = Client(); game.ai = client
        with patch.object(game, "autosave", return_value=None):
            game.resolve_side_chat("Rina", "Please deliver the invitation")
        self.assertEqual(len(client.calls), 1)
        self.assertIn("current_fact_view", client.calls[0]["grounding_packet"])
        self.assertEqual(client.calls[0]["command_contracts"][0]["actor"], "Rina")
    def test_repair_receives_original_draft_and_only_one_retry(self):
        game = GameSession(); game.state = fresh()
        draft = {"narrative": "You learned the technique Silent Step.", "state_patch": {}}
        fixed = {**draft, "state_patch": {"skills": {"Silent Step": {"effect": "Muffles footfalls"}}}}
        class Client:
            model = "test"
            usage = {}
            def __init__(self): self.calls = []
            def request(self, instructions, payload, **kwargs):
                self.calls.append(copy.deepcopy(payload))
                return copy.deepcopy(draft if len(self.calls) == 1 else fixed)
        client = Client()
        result = game.request_with_narrative("test", {"task": "narrator_and_resolution", "action": "Train Silent Step"}, 1000, client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["repair_draft"]["narrative"], draft["narrative"])
        self.assertIn("Silent Step", result["state_patch"]["skills"])

    def test_failed_repair_does_not_mutate_state(self):
        game = GameSession(); game.state = fresh(); before = copy.deepcopy(game.state)
        class Client:
            model = "test"
            usage = {}
            def request(self, *args, **kwargs):
                return {"narrative": "You learned the technique Silent Step.", "state_patch": {}}
        with self.assertRaisesRegex(ValueError, "not applied"):
            game.request_with_narrative("test", {"task": "narrator_and_resolution", "action": "Train"}, 1000, Client())
        self.assertEqual(game.state, before)

    def test_multiturn_secret_save_reload_and_use_all_worlds(self):
        for world in WORLD_DATA:
            with self.subTest(world=world):
                game = GameSession(); game.state = fresh(world); game.campaign_active = True
                game.state["turn"] = 0
                skill = {"effect": "Creates a brief protective barrier", "rank": "C", "category": "Defense", "combat_usable": True, "hidden": True}
                with patch.object(game, "autosave", return_value=None):
                    game.apply_resolution({"narrative": "You learned the technique Silent Ward.", "state_patch": {"skills": {"Silent Ward": skill}}, "events": [], "suggested_actions": ["Rest", "Practice"]},
                                          pending_action="Practice in private", progression_context={"actions": ["Practice in private"], "elapsed_minutes": 5})
                # Exercise the real save bundle, storage JSON and migration with no player save writes.
                bundle = json.loads(json.dumps(game.save_bundle()))
                restored = GameSession()
                with tempfile.TemporaryDirectory(prefix="ww-v3450-roundtrip-") as directory:
                    with patch("engine_persistence._save_dir", return_value=Path(directory)), patch.object(restored, "autosave", return_value=None):
                        imported = restored.import_bundle(bundle)
                        restored.load(imported["id"])
                self.assertIn("Silent Ward", restored.state["skills"])
                self.assertTrue(restored.state["skills"]["Silent Ward"]["hidden"])
                packet = prepare_request(restored.state, {"action": "Talk to Rina about the weather"})
                self.assertFalse(any("Silent Ward" in row.get("fact", "") for row in packet["turn_evidence"]))
                with patch.object(restored, "autosave", return_value=None):
                    restored.apply_resolution({"narrative": "Rina discusses the weather without mentioning your private training.", "state_patch": {}, "events": [], "suggested_actions": ["Rest", "Practice"]}, pending_action="Talk about the weather")
                    restored.apply_resolution({"narrative": "You raise Silent Ward, blocking the incoming debris.", "state_patch": {}, "events": [], "suggested_actions": ["Rest", "Practice"]}, pending_action="Use Silent Ward to block debris")
                self.assertEqual(restored.state["turn"], 3)
                self.assertTrue(restored.state["skills"]["Silent Ward"]["combat_usable"])


if __name__ == "__main__":
    unittest.main()
