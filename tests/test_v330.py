import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import app as app_module
from game import GameSession
from lore import lore_library_status, retrieve_lore
from portrait_generator import portrait_signature
from simulation import (SIMULATION_MODES, advance_npc_intentions, background_ai_due,
                        compile_context_snapshot, deterministic_assessment,
                        output_budget, prioritize_updates, record_simulation_events,
                        relevance_bubble, simulation_profile)
from util import scene_art_signature
from worlds import APP_VERSION, BASE_STATE


class NoCallAI:
    def request(self, *args, **kwargs):
        raise AssertionError("The deterministic planning path must not call AI")


class WorldwalkerV330Tests(unittest.TestCase):
    def fresh(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", name="Ari", location="Konoha Market Square",
                     stats={"Taijutsu": 34, "Ninjutsu": 40, "Genjutsu": 20,
                            "Chakra Control": 38, "Willpower": 36, "Intellect": 30})
        return state

    def test_version_schema_and_simulation_ledgers(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        for field in ("npc_intentions", "simulation_events", "local_background_turn"):
            self.assertIn(field, BASE_STATE)

    def test_three_modes_have_distinct_bounded_profiles(self):
        self.assertEqual(set(SIMULATION_MODES), {"economy", "balanced", "deep"})
        self.assertLess(simulation_profile("economy")["recent_turns"], simulation_profile("deep")["recent_turns"])
        self.assertEqual(simulation_profile("nonsense")["id"], "balanced")
        self.assertEqual(simulation_profile("balanced")["background_ai_interval"], 0)

    def test_output_budget_reduces_normal_modes_but_keeps_json_room(self):
        self.assertEqual(output_budget(2800, "deep"), 2800)
        self.assertLess(output_budget(2800, "balanced"), 2800)
        self.assertGreaterEqual(output_budget(600, "economy"), 500)

    def test_context_compiler_keeps_local_bubble_and_compacts_distant_actors(self):
        state = self.fresh()
        state["npc_memories"] = {
            "Mira": {"last_known_location": state["location"], "goal": "Protect Ari", "knowledge": {"confirmed": ["secret"]}, "notes": list(range(20))},
            **{f"Distant {i}": {"last_known_location": "Elsewhere", "goal": f"Plan {i}", "notes": list(range(20))} for i in range(12)},
        }
        bubble = relevance_bubble(state, "Ask Mira for help", "economy")
        self.assertIn("Mira", bubble["detailed_npcs"])
        compiled = compile_context_snapshot(state, state, "Ask Mira for help", "economy")
        self.assertEqual(compiled["npc_memories"]["Mira"]["notes"], list(range(20)))
        self.assertLessEqual(len(compiled["npc_memories"]), 10)
        self.assertIn("simulation_context", compiled)

    def test_production_planning_can_run_without_an_ai_call(self):
        game = GameSession()
        game.state = self.fresh()
        game.settings["simulation_mode"] = "balanced"
        game.ai = NoCallAI()
        result = game.assess_time_skip(3, "days", ["Train chakra control", "Talk to Mira"], "normal", use_model=False)
        self.assertEqual(result["assessment"]["assessment_source"], "deterministic_local")
        self.assertEqual(result["assessment"]["checks"], [])
        self.assertEqual(result["assessment"]["reachable_actions"], result["time_budget"]["reachable_actions"])

    def test_normal_api_advance_uses_exactly_one_narrator_call(self):
        class Narrator:
            def __init__(self): self.calls = 0
            def request(self, rules, payload, **kwargs):
                self.calls += 1
                return {"narrative": "Ari speaks with Mira and learns that the eastern road remains open.",
                        "updates": [{"sequence": 1, "type": "action", "title": "A useful conversation",
                                     "canon_day": 0, "narrative": "Ari speaks with Mira and learns that the eastern road remains open."}],
                        "state_patch": {}, "events": [], "timeline_events": [],
                        "elapsed": {"amount": 10, "unit": "minutes"}, "interrupted": False,
                        "completed_actions": payload.get("planned_actions", []), "deferred_actions": [],
                        "suggested_actions": ["Visit the eastern gate", "Ask Mira about the courier", "Prepare road supplies"]}
        game = app_module.game
        game.state = self.fresh(); game.campaign_active = True
        game.settings.update({"provider": "local", "model": "test", "simulation_mode": "balanced"})
        narrator = Narrator(); game.ai = narrator
        with app_module.app.test_client() as client:
            assessed_response = client.post("/api/time/assess", json={"amount": 1, "unit": "moment", "orders": ["Talk to Mira"], "intensity": "normal"})
            self.assertEqual(assessed_response.status_code, 200)
            assessed = assessed_response.get_json()
            self.assertEqual(narrator.calls, 0)
            resolved = client.post("/api/time/resolve", json={"amount": assessed["amount"], "unit": assessed["unit"],
                                   "orders": assessed["orders"], "intensity": "normal", "assessment": assessed["assessment"]})
            self.assertEqual(resolved.status_code, 200)
        self.assertEqual(narrator.calls, 1)

    def test_local_assessment_marks_major_and_lethal_actions(self):
        state = self.fresh()
        budget = {"reachable_actions": ["Awaken an ultimate form in a deathmatch"], "deferred_actions": [], "time_dc_modifier": 0}
        result = deterministic_assessment(state, budget["reachable_actions"], budget)
        self.assertTrue(result["checks"][0]["major_event"])
        self.assertEqual(result["checks"][0]["lethal_risk"], "high")
        self.assertTrue(result["power_jump_warning"])

    def test_lore_retrieval_cache_reuses_ranked_evidence(self):
        state = self.fresh()
        retrieve_lore("Naruto", "learn chakra nature", state, 3)
        before = lore_library_status("Naruto")["cache"]["hits"]
        retrieve_lore("Naruto", "learn chakra nature", state, 3)
        after = lore_library_status("Naruto")["cache"]["hits"]
        self.assertGreater(after, before)

    def test_npc_intentions_persist_goal_plan_resources_and_progress(self):
        state = self.fresh()
        state["npc_memories"] = {"Mira": {"last_known_location": state["location"], "goal": "Find the courier",
                                                  "next_action": "Question the gate guards", "resources": {"coin": 3},
                                                  "attitude": "Trusted", "recurring": True}}
        advance_npc_intentions(state, 10 * 1440, "balanced")
        row = state["npc_intentions"]["Mira"]
        self.assertEqual(row["goal"], "Find the courier")
        self.assertEqual(row["next_action"], "Question the gate guards")
        self.assertEqual(row["resources"]["coin"], 3)
        self.assertGreater(row["progress"], 0)

    def test_importance_scheduler_keeps_major_events_and_summarizes_overflow(self):
        updates = [{"type": "world", "narrative": f"Routine patrol {i} continued."} for i in range(8)]
        updates.insert(5, {"type": "canon_event", "narrative": "A major canon invasion begins."})
        selected = prioritize_updates(updates, "economy")
        self.assertTrue(any("canon invasion" in row.get("narrative", "") for row in selected))
        self.assertTrue(any(row.get("title") == "Wider World" for row in selected))
        self.assertLess(len(selected), len(updates))

    def test_unified_event_ledger_deduplicates_sources(self):
        state = self.fresh()
        event = {"type": "world", "message": "The eastern gate closes."}
        record_simulation_events(state, [event], "clock")
        record_simulation_events(state, [event], "narrator")
        self.assertEqual(len(state["simulation_events"]), 1)
        self.assertEqual(set(state["simulation_events"][0]["sources"]), {"clock", "narrator"})

    def test_background_ai_is_opt_in_and_rate_limited(self):
        state = self.fresh(); state["turn"] = 4
        self.assertFalse(background_ai_due(state, "economy"))
        self.assertFalse(background_ai_due(state, "balanced"))
        self.assertTrue(background_ai_due(state, "deep"))
        state["turn"] = 5
        self.assertFalse(background_ai_due(state, "deep"))

    def test_portrait_cache_ignores_stats_and_position_but_tracks_visible_change(self):
        state = self.fresh(); state["appearance_desc"] = "Black hair and a green coat"
        baseline = portrait_signature(state)
        state["stats"]["Ninjutsu"] += 50; state["position"] = "Squad Captain"
        self.assertEqual(portrait_signature(state), baseline)
        state["equipment"]["Outerwear"] = "Red traveling cloak"
        self.assertNotEqual(portrait_signature(state), baseline)

    def test_scene_cache_ignores_chronicle_but_tracks_place(self):
        state = self.fresh(); baseline = scene_art_signature(state)
        state["timeline"].append("A distant battlefield erupted")
        self.assertEqual(scene_art_signature(state), baseline)
        state["location"] = "Underground Cave"
        self.assertNotEqual(scene_art_signature(state), baseline)

    def test_panels_and_settings_expose_modes_without_a_new_cost_dashboard(self):
        app_module.game.state = self.fresh()
        app_module.game.settings["simulation_mode"] = "balanced"
        with app_module.app.test_client() as client:
            settings = client.get("/api/settings").get_json()
            panels = client.get("/api/panels").get_json()
        self.assertEqual(settings["simulation_mode"], "balanced")
        self.assertIn("simulation", panels)
        source = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="st-simulation-mode"', source)


if __name__ == "__main__":
    unittest.main()
