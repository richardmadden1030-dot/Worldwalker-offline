"""GM relevance, durable retry, chapter and multi-year campaign regressions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import BASE_STATE, WORLD_DATA, abilities_for
from gm_refinements import acquisition_claim, connected_memory, relevant_evidence, record_settled_stories
from gm_consistency import prepare_request, semantic_issues, command_contracts, record_fact_changes
from chapter_recaps import compact_recap, chapter_view, finish_recap
from campaign_reliability import build_grounding_packet
from systems import update_chapter_memory


def fresh(world="Naruto"):
    s = copy.deepcopy(BASE_STATE)
    s.update(world=world, name="Ari", location="Hall", turn=4, canon_day=20, opening_complete=True,
             stats={n: 40 for n in abilities_for(world)},
             npc_memories={"Rina": {"subordinate": True, "role": "Guard", "last_known_location": "Hall"},
                           "Mira": {"subordinate": True, "role": "Guard", "last_known_location": "Hall"},
                           "Toma": {"role": "Guard", "attitude": "Friendly"}},
             scene_state={"location": "Hall", "present": ["Rina", "Mira"]})
    return s


class RefinementTests(unittest.TestCase):
    def test_mentions_are_not_acquisitions(self):
        for line in ["You explain your Bankai.", "Rina awakens a new form.", "You hope to awaken Bankai.",
                     "If you master Bankai, you can lead.", "You already mastered the technique.",
                     'Rina says, "You have awakened Bankai."', "You never learned that technique."]:
            with self.subTest(line=line): self.assertFalse(acquisition_claim(fresh(), line))
        for line in ["You finally awaken Bankai.", "Ari awakens a new form.", "You have mastered the technique."]:
            with self.subTest(line=line): self.assertTrue(acquisition_claim(fresh(), line))

    def test_groups_only_include_actual_subordinates(self):
        contracts = command_contracts(fresh(), "Tell my guards to protect the children")
        self.assertEqual({r["actor"] for r in contracts}, {"Rina", "Mira"})
        self.assertTrue(all("protect the children" in r["order"] for r in contracts))

    def test_followup_uses_recent_command_not_a_random_person(self):
        s = fresh(); s["last_command_context"] = {"actors": ["Rina"], "turn": 3}
        self.assertEqual(command_contracts(s, "Have her continue guarding the children")[0]["actor"], "Rina")
        s["last_command_context"]["actors"] = ["Rina", "Mira"]
        self.assertEqual(command_contracts(s, "Have her continue"), [])
        self.assertEqual(len(command_contracts(s, "Have them continue")), 2)
        s["last_command_context"]["turn"] = 0
        self.assertEqual(command_contracts(s, "Have them continue"), [])

    def test_dead_subordinate_is_not_commanded(self):
        s = fresh(); s["npc_memories"]["Rina"]["status"] = "dead"
        self.assertEqual(command_contracts(s, "Order Rina to deliver a letter"), [])

    def test_unrelated_known_fact_is_not_evidence(self):
        s = fresh(); s["npc_memories"]["Rina"]["knowledge"] = {"confirmed": [{"fact": "Ari visited the harbor"}]}
        p = prepare_request(s, {"action": "Train in private"})
        ref = next(r["id"] for r in p["turn_evidence"] if r["kind"] == "confirmed")
        bad = {"causal_outcome": {"reactions": [{"actor": "Rina", "response": "Knows the concealed teleportation technique", "evidence_refs": [ref]}]}}
        self.assertTrue(semantic_issues(s, bad, p))
        bad["causal_outcome"]["reactions"][0]["response"] = "Asks about the harbor visit"
        self.assertFalse(semantic_issues(s, bad, p))

    def test_suspicion_cannot_support_confirmed_claim(self):
        self.assertFalse(relevant_evidence({"response": "The letter is stolen", "certainty": "confirmed"},
                                          [{"kind": "suspected", "fact": "The letter was stolen"}]))

    def test_orphanage_links_caretaker_and_promise_with_bounded_context(self):
        s = fresh(); s["projects"] = [{"name": "Orphanage", "caretaker": "Rina", "status": "complete", "location": "Harbor"}]
        s["obligation_ledger"] = [{"owner": "Ari", "promise": "Fund the orphanage school", "status": "active"}]
        s["npc_memories"].update({f"Unrelated {i}": {"goal": "Sell goods"} for i in range(200)})
        packet = build_grounding_packet(s, "Check the orphanage")
        self.assertEqual(packet["relevant_people"][0]["name"], "Rina")
        self.assertIn("Fund the orphanage school", json.dumps(packet["connected_memories"]))
        self.assertLessEqual(len(packet["connected_memories"]), 12)
        self.assertLess(len(json.dumps(packet["connected_memories"])), 7000)

    def test_completed_project_does_not_reopen_without_cause(self):
        s = fresh(); s["projects"] = [{"name": "Village hospital", "status": "completed", "outcome": "The clinic treats residents"}]
        record_settled_stories({}, s)
        p = prepare_request(s, {"action": "Visit the hospital"})
        data = {"state_patch": {"projects": [{"name": "Village hospital", "status": "active"}]}}
        self.assertTrue(semantic_issues(s, data, p))
        data["state_patch"]["projects"][0]["status"] = "completed"
        self.assertFalse(semantic_issues(s, data, p))
        self.assertIn("clinic treats residents", json.dumps(connected_memory(s, "hospital")))

    def test_actual_commitment_and_standing_update_channels_respect_closure(self):
        s = fresh()
        s["obligation_ledger"] = [{"text": "Deliver the promised medicine", "status": "fulfilled"}]
        s["standing_intents"] = [{"id": "clinic", "directive": "Rebuild the clinic", "status": "completed"}]
        p = prepare_request(s, {"action": "Rest at the clinic"})
        self.assertTrue(semantic_issues(s, {"commitment_updates": [{"promise": "Deliver the promised medicine"}]}, p))
        self.assertTrue(semantic_issues(s, {"standing_intent_updates": [{"id": "clinic", "status": "active"}]}, p))
        self.assertFalse(semantic_issues(s, {"standing_intent_updates": [{"id": "clinic", "status": "completed"}]}, p))

    def test_connected_memory_reads_real_location_and_roster_shapes(self):
        s = fresh()
        s["location_details"] = {"Orphanage": {"caretaker": "Rina", "description": "A restored school"}}
        s["faction_rosters"] = {"Clinic guard": ["Rina", "Mira"]}
        s["narrative_memory"] = {"promises": [{"text": "Fund the orphanage", "status": "active"}]}
        result = connected_memory(s, "Check the orphanage")
        self.assertIn("Rina", result["names"])
        self.assertIn("Fund the orphanage", json.dumps(result))
        self.assertIn("Mira", json.dumps(result))

    def test_legitimate_new_damage_can_reopen_resolved_project(self):
        s = fresh(); s["projects"] = [{"name": "Hospital roof", "status": "completed"}]
        s["conditions"] = [{"name": "Storm damaged the hospital roof"}]
        p = prepare_request(s, {"action": "Repair the damaged hospital roof"})
        ref = next(r["id"] for r in p["turn_evidence"] if r["kind"] == "conditions")
        data = {"state_patch": {"projects": [{"name": "Hospital roof", "status": "active"}]},
                "reopened_threads": [{"name": "Hospital roof", "cause": "Storm damaged the roof", "evidence_refs": [ref]}]}
        self.assertFalse(semantic_issues(s, data, p))


class RecoveryTests(unittest.TestCase):
    def test_retry_signature_respects_duration_and_model_but_not_error_logs(self):
        from turn_recovery import request_signature
        from gm_refinements import fingerprint
        payload = {"action": "Train", "duration": {"amount": 1, "unit": "days"}, "state": fresh()}
        original = fingerprint(request_signature("rules", payload, "model-a", 500))
        payload["state"]["last_failed_turn"] = {"error": "temporary error"}
        self.assertEqual(original, fingerprint(request_signature("rules", payload, "model-a", 500)))
        self.assertNotEqual(original, fingerprint(request_signature("rules", payload, "model-b", 500)))
        payload["duration"]["amount"] = 30
        self.assertNotEqual(original, fingerprint(request_signature("rules", payload, "model-a", 500)))

    def test_failure_reuses_roll_and_valid_draft_without_extra_ai(self):
        g = GameSession(); g.state = fresh(); g.autosave = lambda: None
        class Client:
            usage = {}; model = "stub"; calls = 0
            def request(self, *a, **kw):
                self.calls += 1
                return {"narrative": "Ari rests quietly in the hall.", "state_patch": {}}
        c = Client(); payload = {"orders": ["Rest"], "amount": 1}
        tx = g.begin_turn_transaction("time_resolve", payload)
        assessment = {"action": "Rest", "difficulty_min": 10, "difficulty_max": 20}
        first = g.roll(assessment)
        request = {"task": "narrator_and_resolution", "action": "Rest", "dice_result": first}
        g.request_with_narrative("rules", request, 500, c)
        g.state["hp"] -= 10
        g.rollback_turn_transaction(tx, RuntimeError("synthetic application failure"))
        self.assertEqual(g.state["hp"], tx["state"]["hp"])
        self.assertNotIn("work", g.public_state()["last_failed_turn"])
        # A real export/import-compatible JSON roundtrip preserves private recovery state.
        g.state = json.loads(json.dumps(g.state))
        tx = g.begin_turn_transaction("time_resolve", payload)
        with patch("engine_turns.random.randint", side_effect=AssertionError("must not reroll")):
            self.assertEqual(g.roll(assessment), first)
        g.request_with_narrative("rules", request, 500, c)
        self.assertEqual(c.calls, 1)
        g.complete_turn_transaction(tx)
        self.assertFalse(g.state["last_failed_turn"])

    def test_edited_campaign_invalidates_retry_work(self):
        g = GameSession(); g.state = fresh(); g.autosave = lambda: None
        tx = g.begin_turn_transaction("time_resolve", {})
        g._turn_work["stages"]["test"] = {"draft": "old"}
        g.rollback_turn_transaction(tx, RuntimeError("test"))
        g.state["location"] = "New city"
        g.begin_turn_transaction("time_resolve", {})
        self.assertEqual(g._turn_work["stages"], {})

    def test_second_repair_is_checked_for_narrative_and_quality(self):
        g = GameSession(); g.state = fresh()
        class Client:
            usage = {}; model = "stub"; calls = 0
            def request(self, *a, **kw):
                self.calls += 1
                return {"narrative": "You awaken Bankai.", "state_patch": {}} if self.calls == 1 else {"narrative": "", "state_patch": {}}
        with self.assertRaisesRegex(ValueError, "not applied"):
            g.request_with_narrative("rules", {"task": "narrator_and_resolution", "action": "Awaken Bankai"}, 500, Client())


class ChapterTests(unittest.TestCase):
    def test_sentences_keep_their_original_order_inside_each_beat(self):
        text = "The merchants arrived at the clinic with medicine. Ari welcomed the merchants and supplied every ward."
        self.assertEqual(compact_recap([{"summary": text, "action": "Welcome merchants"}], "Ari"), text)

    def test_short_recap_uses_complete_grounded_sentences(self):
        beats = [{"action": "Build a clinic", "summary": "Ari rebuilt the village clinic with Rina. The new wards welcomed their first patients.", "changes": ["Clinic completed"]},
                 {"action": "Train", "summary": "Ari spent the winter refining his Water Release. By spring, he could guide its current without wasting chakra."}]
        summary = compact_recap(beats, "Ari")
        self.assertLessEqual(len(summary.split()), 110)
        self.assertIn("clinic", summary); self.assertIn("Water Release", summary)
        self.assertTrue(summary.endswith("."))
        self.assertNotIn("Current direction", summary)

    def test_legacy_chapter_display_keeps_full_memory_untouched(self):
        old = {"number": 1, "summary": "Ari brought medicine to the harbor. " * 60, "key_decisions": ["Deliver medicine"]}
        before = copy.deepcopy(old); view = chapter_view(old, "Ari")
        self.assertEqual(old, before)
        self.assertEqual(view["summary"], old["summary"])
        self.assertLessEqual(len(view["narrative_summary"].split()), 110)
        self.assertEqual(view["narrative_summary"].count("brought medicine"), 1)

    def test_unrelated_generated_recap_falls_back_without_stopping_turn(self):
        beats = [{"summary": "Ari delivered medicine to the harbor clinic.", "action": "Deliver medicine"}]
        chapter = finish_recap({"number": 1}, beats, "Ari", {"title": "The Universal King", "summary": "Ari conquered the universe and destroyed every kingdom. " * 10})
        self.assertEqual(chapter["recap_source"], "recorded_events")
        self.assertNotIn("conquered", chapter["narrative_summary"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        import app
        self.module = app
        self.game = GameSession(); self.game.state = fresh(); self.game.campaign_active = True
        self.game.autosave = lambda: None
        self.patcher = patch.object(app, "game", self.game); self.patcher.start()
        self.client = app.app.test_client()

    def tearDown(self): self.patcher.stop()

    def test_correction_preview_does_not_mutate_and_requires_current_preview(self):
        before = copy.deepcopy(self.game.state)
        payload = {"type": "hp", "value": "999", "source": {"text": "An incorrect injury.", "time": "Morning"}}
        preview = self.client.post("/api/campaign/correct/preview", json=payload).get_json()
        self.assertEqual(self.game.state, before)
        self.assertEqual(preview["fact"], f"Hp is {self.game.state['hp_max']}.")
        self.game.state["hp"] -= 1
        response = self.client.post("/api/campaign/correct", json={**payload, "preview_token": preview["preview_token"]})
        self.assertEqual(response.status_code, 409)
        preview = self.client.post("/api/campaign/correct/preview", json=payload).get_json()
        response = self.client.post("/api/campaign/correct", json={**payload, "preview_token": preview["preview_token"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.game.state["hp"], self.game.state["hp_max"])
        self.assertEqual(response.get_json()["correction"]["source_entry"]["text"], payload["source"]["text"])

    def test_successful_request_id_cannot_award_twice(self):
        calls = []
        def award():
            calls.append(1); self.game.state["hp"] -= 1
            return {"status": "resolved", "state": self.game.public_state(), "story": []}
        payload = {"request_id": "test-unique", "orders": ["Rest"]}
        self.module.atomic_game_call("time_resolve", payload, award)
        second = self.module.atomic_game_call("time_resolve", payload, award)
        self.assertEqual(len(calls), 1); self.assertTrue(second["replayed_request"])
        with self.assertRaises(ValueError):
            self.module.atomic_game_call("time_resolve", {**payload, "orders": ["Attack"]}, award)
        self.game.state["campaign_id"] = "another-campaign"
        with self.assertRaisesRegex(ValueError, "another campaign"):
            self.module.atomic_game_call("time_resolve", payload, award)


class LongCampaignTests(unittest.TestCase):
    def test_five_year_campaigns_across_every_world(self):
        for world in WORLD_DATA:
            with self.subTest(world=world), tempfile.TemporaryDirectory(prefix="ww-v3460-soak-") as directory:
                game = GameSession(save_dir=directory, settings_path=Path(directory) / "settings.json")
                game.state = fresh(world); game.campaign_active = True; game.autosave = lambda: None
                game.state["npc_memories"]["Rina"].update(role="Retired captain", status="retired")
                game.state["npc_memories"]["Mira"].update(role="Captain", rank="Commander")
                game.state["quests"] = [{"name": "Build a village clinic", "status": "Completed", "outcome": "The clinic treats residents"}]
                for turn in range(120):
                    before = copy.deepcopy(game.state)
                    game.state["turn"] += 1
                    # Advance the real game calendar and age calculations; canon dispatch is tested separately.
                    with patch.object(game, "fire_canon_events", return_value=[]):
                        game.advance_clock(before, 15, "days")
                    # Use actual commit-time memory/closure/summary and migration paths.
                    if turn == 15: game.state["skills"]["Silent Ward"] = {"effect": "Blocks falling debris", "category": "Defense", "combat_usable": True}
                    if turn == 30: game.state["npc_memories"]["Toma"]["status"] = "dead"
                    record_fact_changes(before, game.state)
                    line = "Ari visited the village clinic. Mira supervised its guards while Rina enjoyed her retirement."
                    update_chapter_memory(before, game.state, "Visit the clinic", line)
                    packet = build_grounding_packet(game.state, "Ask Mira about the clinic and Rina")
                    self.assertIn("Retired captain", json.dumps(packet))
                    self.assertTrue(any(row["name"] == "Build a village clinic" and row["status"] == "Completed" for row in game.state["settled_stories"]))
                    self.assertFalse(any(row.get("name") == "Build a village clinic" and row.get("status", "").lower() == "active" for row in game.state.get("quests", [])))
                    if turn in {39, 79, 119}:
                        bundle = json.loads(json.dumps(game.save_bundle()))
                        with patch("engine_persistence._save_dir", return_value=Path(directory)):
                            imported = game.import_bundle(bundle); game.load(imported["id"])
                        self.assertEqual(game.state["npc_memories"]["Mira"]["rank"], "Commander")
                        self.assertTrue(game.state["skills"]["Silent Ward"]["combat_usable"])
                        self.assertEqual(game.state["npc_memories"]["Toma"]["status"], "dead")
                self.assertGreaterEqual(len(game.state["chapter_summaries"]), 15)
                self.assertTrue(all(len(chapter_view(c)["narrative_summary"].split()) <= 120 for c in game.state["chapter_summaries"]))


if __name__ == "__main__": unittest.main()
