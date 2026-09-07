import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from campaign_reliability import (
    build_grounding_packet, learn_player_style, normalize_outcome_scale,
    reconcile_commitments_and_consequences, record_pacing_beat,
    refresh_canon_divergence_impacts, refresh_scene_state,
)
from game import GameSession
from lore import format_lore_context, lore_retrieval_decision
from release_notes import notes_for
from systems import pacing_guidance
from worlds import APP_VERSION, BASE_STATE, abilities_for


def fresh_state(world="Naruto"):
    state = copy.deepcopy(BASE_STATE)
    state.update(world=world, name="Ari", location="Training Field", opening_complete=True,
                 stats={name: 30 for name in abilities_for(world)}, turn=4)
    return state


class WorldwalkerV3400GMTests(unittest.TestCase):
    def test_version_and_patch_notes_contract(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        notes = notes_for(APP_VERSION)
        self.assertEqual(notes["version"], APP_VERSION)
        # A hotfix may have one change; it still needs useful player-facing notes.
        self.assertGreaterEqual(len(notes["highlights"]), 1)
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="modal-patch-notes"', html)
        self.assertIn("worldwalker_patch_notes_seen", js)
        self.assertIn("maybeShowPatchNotes", js)

    def test_scene_state_tracks_present_people_and_unresolved_question(self):
        state = fresh_state()
        state["npc_memories"] = {
            "Konan": {"last_known_location": "Training Field", "status": "active"},
            "Nagato": {"last_known_location": "Amegakure", "status": "active"},
        }
        scene = refresh_scene_state(state, {"narrative": "Konan lowers the map. Will you take the eastern route?"}, ["Review the route"])
        self.assertIn("Konan", scene["present"])
        self.assertNotIn("Nagato", scene["present"])
        self.assertIn("eastern route", scene["unresolved_question"])
        self.assertEqual(build_grounding_packet(state, "route", "moment")["live_scene"]["location"], "Training Field")

    def test_commitments_and_delayed_consequences_become_due(self):
        state = fresh_state(); state["canon_day"] = 10
        reconcile_commitments_and_consequences(state, {
            "commitment_updates": [{"owner": "Ari", "owed_to": "Konan", "promise": "Deliver the medicine", "due_canon_day": 10}],
            "delayed_consequences": [{"effect": "The eastern clinic runs short", "source": "Delayed delivery", "due_canon_day": 10}],
        })
        self.assertEqual(state["obligation_ledger"][0]["status"], "due")
        self.assertEqual(state["delayed_consequences"][0]["status"], "due")
        packet = build_grounding_packet(state, "medicine", "moment")
        self.assertTrue(packet["due_obligations"])
        self.assertTrue(packet["due_consequences"])

    def test_outcome_scale_detects_a_narrative_mechanics_mismatch(self):
        before = fresh_state(); state = copy.deepcopy(before)
        result = normalize_outcome_scale(before, state, {"narrative": "Ari awakens a godlike new form."}, 60)
        self.assertFalse(result["aligned"])
        self.assertEqual(result["claimed"], "transformative")
        state["stats"][next(iter(state["stats"]))] += 120
        result = normalize_outcome_scale(before, state, {"narrative": "Ari undergoes a transformative awakening."}, 60)
        self.assertTrue(result["aligned"])

    def test_divergence_impacts_propagate_through_timeline_dependencies(self):
        state = fresh_state("Bleach")
        state["canon_divergences"] = [{"event": "Ichigo Becomes a Substitute Soul Reaper", "status": "impossible", "reason": "The transfer never occurred."}]
        impact = refresh_canon_divergence_impacts(state)
        self.assertTrue(impact["affected_events"])
        self.assertTrue(any(row["status"] in {"impossible", "replaced"} for row in impact["affected_events"]))

    def test_pacing_detects_repetition_and_style_uses_only_liked_turns(self):
        state = fresh_state()
        for _ in range(3): record_pacing_beat(state, {"narrative": "The battle continues as they attack."}, ["Fight"])
        self.assertIn("last 3", pacing_guidance(state))
        state["rated_good_turns"] = [{"turn": 1, "action": "Train to master sealing", "outcome": " ".join(["Detailed"] * 120)}]
        profile = learn_player_style(state)
        self.assertEqual(profile["preferred_detail"], "detailed")
        self.assertIn("growth", profile["preferred_beats"])

    def test_selective_lore_skips_routine_actions_but_keeps_canon_queries(self):
        state = fresh_state()
        routine = lore_retrieval_decision("Naruto", "I sit down and rest", state, "moment")
        canon = lore_retrieval_decision("Naruto", "Explain Kakashi's canon chakra abilities", state, "advisor")
        self.assertFalse(routine["retrieve"])
        self.assertTrue(canon["retrieve"])
        self.assertNotIn("RETRIEVED LORE EVIDENCE", format_lore_context("Naruto", "I sit down and rest", state, 3, purpose="moment"))

    def test_quality_gate_retries_a_breakthrough_without_mechanics_once(self):
        game = GameSession(); game.state = fresh_state(); calls = []
        class AIStub:
            def request(self, rules, payload, max_output_tokens=0):
                calls.append(rules)
                if len(calls) == 1:
                    return {"narrative": "Ari awakens a new form.", "state_patch": {}, "suggested_actions": ["Ask Konan", "Rest nearby"]}
                return {"narrative": "Ari awakens a new form.", "state_patch": {"special": {"Awakened Form": {"effect": "A durable transformation"}}}, "suggested_actions": ["Ask Konan", "Rest nearby"]}
        game.ai = AIStub()
        result = game.request_with_narrative("RULES", {"task": "narrator_and_resolution", "action": "Awaken", "schema": {"suggested_actions": []}}, 500)
        self.assertEqual(len(calls), 2)
        self.assertIn("QUALITY REPAIR", calls[1])
        self.assertIn("special", result["state_patch"])

    def test_advisor_entries_include_expandable_evidence(self):
        game = GameSession(); game.state = fresh_state()
        result = game.ask_advisor("How strong am I?")
        self.assertTrue(result["entry"]["evidence"])
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Why the Advisor says this", js)


if __name__ == "__main__":
    unittest.main()
