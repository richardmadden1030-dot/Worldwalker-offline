import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from long_campaign import (
    build_memory_tiers, compact_checkpoint_state, compact_state_for_storage,
    pre_advance_health_check, record_runtime_error, sync_standing_order_lifecycle,
)
from response_guard import normalize_turn_response
from simulation_enhancements import advance_npc_development
from simulation_integrity import refresh_npc_schedules
from state_guard import migrate_state
from worlds import APP_VERSION, BASE_STATE, abilities_for


class StableAI:
    def request(self, rules, payload, max_output_tokens=0):
        return {
            "narrative": "Chen carries out the plan and the day moves forward.",
            "updates": [{"title": "Progress", "narrative": "The active work advances."}],
            "state_patch": {}, "events": [], "timeline_events": [],
            "elapsed": {"amount": 20, "unit": "minutes"}, "interrupted": False,
            "completed_actions": payload.get("planned_actions", [])[:1],
            "deferred_actions": payload.get("planned_actions", [])[1:],
            "major_event_reached": False, "suggested_actions": ["Continue"],
        }


class LongCampaignHealthTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_deep_shapes_stale_goals_quests_scene_and_combat_repair_together(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(turn=80, location="Hokage Tower", standing_orders=["Protect the archive"])
        state["action_goals"] = [
            {"action": "Learn an old technique", "status": "active", "started_turn": 2},
            {"action": "Protect the archive", "status": "active", "started_turn": 78},
        ]
        state["quests"] = [
            {"name": "Courier Duty", "status": "Completed"},
            {"name": "Open Inquiry", "status": "Active"},
            {"name": "Open Inquiry", "status": "Active"},
        ]
        state["scene_state"] = {"location": "Old Road", "present": ["Ghost"]}
        state["npc_memories"] = {"Ghost": {"status": "deceased"}}
        state["combat"] = {"active": True, "enemy": {"name": "Bandit", "hp": 0}, "round": "4"}
        report = pre_advance_health_check(state)
        self.assertEqual(report["status"], "repaired")
        self.assertEqual(state["scene_state"]["location"], "Hokage Tower")
        self.assertEqual(state["scene_state"]["present"], [])
        self.assertFalse(state["combat"]["active"])
        self.assertEqual([row["name"] for row in state["quests"]], ["Open Inquiry"])
        self.assertEqual(state["quest_archive"][0]["name"], "Courier Duty")
        goals = {row["action"]: row["status"] for row in state["action_goals"]}
        self.assertEqual(goals["Learn an old technique"], "abandoned")
        self.assertEqual(goals["Protect the archive"], "active")

    def test_standing_order_lifecycle_preserves_full_plan(self):
        state = copy.deepcopy(BASE_STATE); state["turn"] = 12
        plan = ["Guard the child", "Train the squad", "Maintain the shelter"]
        sync_standing_order_lifecycle(state, plan, source="test")
        sync_standing_order_lifecycle(state, plan, completed=[plan[0]], deferred=plan[1:], source="resolution")
        self.assertEqual(state["standing_orders"], plan[1:])
        statuses = {row["text"]: row["status"] for row in state["standing_order_state"].values()}
        self.assertEqual(statuses[plan[0]], "completed")
        self.assertEqual(statuses[plan[1]], "deferred")

    def test_memory_tiers_and_compaction_keep_current_truth(self):
        state = copy.deepcopy(BASE_STATE); state.update(turn=200, name="Ari", location="Amegakure")
        state["campaign_canon"] = [{"turn": n, "action": f"Action {n}", "outcome": "Resolved"} for n in range(1, 201)]
        state["chapter_summaries"] = [{"title": f"Chapter {n}", "summary": "Summary"} for n in range(30)]
        state["verified_memory_archive"] = [{"title": f"Archive {n}", "summary": "Verified"} for n in range(70)]
        tiers = build_memory_tiers(state)
        self.assertEqual(len(tiers["hot"]), 16)
        self.assertEqual(len(tiers["warm"]), 12)
        self.assertEqual(len(tiers["cold"]), 40)
        checkpoint = compact_checkpoint_state(state)
        stored = compact_state_for_storage(state)
        self.assertEqual(checkpoint["name"], "Ari")
        self.assertEqual(checkpoint["location"], "Amegakure")
        self.assertEqual(len(checkpoint["campaign_canon"]), 40)
        self.assertIn("memory_tiers", stored)

    def test_partial_json_response_is_recovered_without_second_call(self):
        raw = "```json\n" + json.dumps({
            "updates": [{"title": "Arrival", "narrative": "The envoy arrives."}],
            "state_patch": json.dumps({"location": "Council Hall"}),
        }) + "\n```"
        data = normalize_turn_response(raw)
        self.assertEqual(data["narrative"], "The envoy arrives.")
        self.assertEqual(data["state_patch"]["location"], "Council Hall")
        self.assertTrue(data["response_recovery"]["partial"])

    def test_runtime_diagnostics_have_stable_support_id(self):
        state = copy.deepcopy(BASE_STATE)
        row = record_runtime_error(state, AttributeError("bad nested value"), "/api/time/resolve", {"orders": []})
        self.assertEqual(len(row["id"]), 10)
        self.assertEqual(state["diagnostics"]["last_error_id"], row["id"])
        self.assertEqual(row["type"], "AttributeError")

    def test_npc_updates_describe_progress_and_decisions_in_plain_language(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(turn=20, canon_day=30, companions=["Jiraiya"])
        state["npc_memories"] = {
            "Jiraiya": {"recurring": True, "goal": "Returned to Konoha and watches his former students from afar."},
            "Konan": {"recurring": True, "goal": "Support Yahiko's vision of peace for Amegakure."},
        }
        state["npc_development"] = {
            "Jiraiya": {"progress": 24.8, "milestone": 0, "history": []},
            "Konan": {"progress": 24.8, "milestone": 0, "history": []},
        }
        developments = advance_npc_development(state, 1440)
        self.assertTrue(developments)
        joined = " ".join(row["narrative"] for row in developments)
        self.assertNotIn("has developed through", joined)
        self.assertIn("Current direction", joined)

        state["npc_intentions"] = {"Konan": {"goal": "Support Yahiko's vision of peace", "progress": 100}}
        state["npc_schedules"] = {"Konan": {"goal": "Support Yahiko's vision of peace", "status": "active", "due_day": 30, "commitments": []}}
        schedule_events = refresh_npc_schedules(state, 1440)
        self.assertEqual(len(schedule_events), 1)
        self.assertNotIn("commitment is now due", schedule_events[0]["message"])
        self.assertIn("decision point", schedule_events[0]["message"])

    def test_save_bundle_does_not_repeat_full_long_state_in_every_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.state = copy.deepcopy(BASE_STATE)
            game.state["campaign_canon"] = [{"turn": n, "outcome": "x" * 500} for n in range(300)]
            game.checkpoints = [copy.deepcopy(game.state) for _ in range(8)]
            naive = len(json.dumps({"state": game.state, "checkpoints": game.checkpoints}))
            compact = len(json.dumps(game.save_bundle("manual")))
            self.assertLess(compact, naive * 0.45)
            self.assertLessEqual(len(game.save_bundle("manual")["checkpoints"]), 4)


class ReportedChenSaveRegressionTest(unittest.TestCase):
    def test_attached_long_campaign_migrates_and_advances_when_available(self):
        source = Path(r"C:\Users\gamin\Downloads\Chen_Su_Naruto.worldwalker.json")
        if not source.exists():
            self.skipTest("User-supplied regression save is not installed on this machine.")
        bundle = json.loads(source.read_text(encoding="utf-8"))
        state = migrate_state(bundle["state"], bundle.get("version", "Legacy"))
        self.assertEqual(state["name"], "Chen Su")
        self.assertIn(state["diagnostics"]["pre_advance_health"]["status"], {"healthy", "repaired"})
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.state = state
            game.history = bundle.get("history", [])[-600:]
            game.story_log = bundle.get("story_log", [])[-1200:]
            game.ai = StableAI()
            before_turn = int(game.state.get("turn", 0))
            assessed = game.assess_time_skip(1, "moment", [], "normal", use_model=False)
            result = game.run_time_skip(1, "moment", assessed["orders"], "normal", assessed["assessment"])
            self.assertEqual(result["status"], "resolved")
            self.assertEqual(result["state"]["turn"], before_turn + 1)
            self.assertGreaterEqual(len(result["state"].get("standing_order_state", {})), 1)


if __name__ == "__main__":
    unittest.main()
