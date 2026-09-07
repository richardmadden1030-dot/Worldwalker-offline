import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from simulation_integrity import (
    apply_player_correction, build_travel_graph, campaign_search,
    canon_dependency_graph, event_confidence, parse_action_goals,
    refresh_npc_schedules, transmit_information, travel_plan_for_actions,
    travel_route, validate_turn_response,
)
from state_guard import migrate_state
from simulation import deterministic_assessment
from worlds import APP_VERSION, BASE_STATE
from util import scene_art_confidence, scene_display_label, scene_image_url
from game import GameSession
import app as app_module


class WorldwalkerV340Tests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        state = copy.deepcopy(BASE_STATE)
        state.update(world=world, name="Ari", location="Konohagakure", canon_day=-7,
                     stats={"Taijutsu": 35, "Ninjutsu": 38, "Genjutsu": 25,
                            "Chakra Control": 40, "Willpower": 34, "Intellect": 32})
        return state

    def test_version_schema_and_new_ledgers(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        for key in ("action_goals", "correction_log", "authoritative_corrections",
                    "information_packets", "npc_schedules", "canon_event_states",
                    "simulation_validation"):
            self.assertIn(key, BASE_STATE)

    def test_iconic_location_label_matches_the_art(self):
        state = self.fresh("One Piece")
        state["location"] = "Foosha Village"
        image, category = scene_image_url(state)
        self.assertIn("one_piece_foosha_village", image)
        self.assertEqual(scene_display_label(state, image, category), "one_piece_foosha_village")
        self.assertEqual(scene_art_confidence(state, category)["label"], "Landmark match")

    def test_specific_shop_still_overrides_broad_iconic_location(self):
        state = self.fresh("One Piece")
        state["location"] = "Foosha Village merchant stall"
        image, category = scene_image_url(state)
        self.assertEqual(category, "merchant_shop")
        self.assertNotIn("one_piece_foosha_village", image or "")

    def test_explicit_hidden_class_theme_is_preserved(self):
        stats = {"Taijutsu": 35, "Ninjutsu": 40, "Genjutsu": 25,
                 "Chakra Control": 42, "Willpower": 30, "Intellect": 33}
        profile = GameSession().generate_hidden_class(
            "Naruto", "I awakened a hidden class tied to space-time ninjutsu.",
            0, ["Ninjutsu", "Chakra Control"], stats,
        )
        combined = " ".join(str(profile.get(key, "")) for key in
                            ("name", "description", "effect", "signature_skill")).lower()
        self.assertIn("warp", combined)
        self.assertNotIn("sensory-combat", combined)

    def test_old_save_migrates_all_integrity_fields(self):
        state = migrate_state({"schema_version": 10, "world": "Naruto"}, "3.3.0")
        self.assertEqual(state["schema_version"], 21)
        self.assertIn("information_packets", state)

    def test_structured_goals_keep_exact_action_indices(self):
        actions = ["Buy lunch", "Train until I master tree walking", "Find Kakashi"]
        goals = parse_action_goals(actions, 2)
        self.assertEqual([row["action_index"] for row in goals], [1, 2])
        self.assertEqual(goals[0]["kind"], "growth")

    def test_local_preflight_flags_elite_guardian_as_a_hard_check(self):
        result = deterministic_assessment(
            self.fresh(), ["Defeat the elite guardian"],
            {"time_dc_modifier": 0, "reachable_actions": ["Defeat the elite guardian"], "deferred_actions": []},
        )
        self.assertEqual(len(result["checks"]), 1)
        self.assertGreaterEqual(result["checks"][0]["difficulty_min"], 75)
        self.assertEqual(result["checks"][0]["lethal_risk"], "moderate")

    def test_validator_reattaches_stale_roll_labels(self):
        state = self.fresh()
        rolls = [{"action_index": 0, "action": "Final queued action"},
                 {"action_index": 1, "action": "Final queued action"}]
        _, report = validate_turn_response(state, {"elapsed": {"amount": 1, "unit": "hours"}},
                                           ["Train", "Question the guard"], rolls, 60)
        self.assertEqual(rolls[0]["action"], "Train")
        self.assertEqual(rolls[1]["action"], "Question the guard")
        self.assertEqual(report["rolls_checked"], 2)

    def test_validator_caps_elapsed_time(self):
        state = self.fresh()
        data, report = validate_turn_response(state, {"elapsed": {"amount": 4, "unit": "days"}}, [], [], 1440)
        self.assertEqual(data["elapsed"], {"amount": 1440, "unit": "minutes"})
        self.assertEqual(report["status"], "repaired")

    def test_exact_skip_cannot_end_early_without_a_reason(self):
        state = self.fresh()
        data, report = validate_turn_response(
            state, {"elapsed": {"amount": 4, "unit": "hours"}, "interrupted": False},
            ["Train for two days"], [], 2880, exact_duration=True,
        )
        self.assertEqual(data["elapsed"], {"amount": 2880, "unit": "minutes"})
        self.assertIn("exact time skip", " ".join(report["repairs"]))

    def test_moment_skip_may_end_before_its_24_hour_cap(self):
        state = self.fresh()
        data, _ = validate_turn_response(
            state, {"elapsed": {"amount": 4, "unit": "hours"}}, [], [], 1440,
            exact_duration=False,
        )
        self.assertEqual(data["elapsed"], {"amount": 4, "unit": "hours"})

    def test_goal_completion_stops_at_early_elapsed(self):
        state = self.fresh()
        data = {"elapsed": {"amount": 30, "unit": "days"},
                "goal_status": {"action": "Master it", "achieved": True,
                                "elapsed": {"amount": 13, "unit": "days"}}}
        data, _ = validate_turn_response(state, data, ["Master it"], [], 30 * 1440)
        self.assertEqual(data["elapsed"], {"amount": 18720, "unit": "minutes"})

    def test_travel_graph_is_connected_from_konoha_to_suna(self):
        route = travel_route(self.fresh(), "Sunagakure")
        self.assertTrue(route["reachable"])
        self.assertEqual(route["origin"], "Konohagakure")
        self.assertGreater(route["minutes"], 0)

    def test_travel_plan_detects_named_destination(self):
        plans = travel_plan_for_actions(self.fresh(), ["Travel to Sunagakure and find lodging"])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["destination"], "Sunagakure")

    def test_tower_routes_are_sequential(self):
        state = self.fresh("Solo Max-Level Newbie")
        state["location"] = "Floor 1"
        graph = build_travel_graph(state)
        self.assertEqual({x["to"] for x in graph["edges"]["Floor 1"]}, {"Earth — Tower Entrance", "Floor 2"})

    def test_validator_blocks_atlas_travel_that_is_too_fast(self):
        state = self.fresh()
        data = {"narrative": "You start down the road.", "elapsed": {"amount": 10, "unit": "minutes"},
                "state_patch": {"location": "Sunagakure"}}
        data, report = validate_turn_response(state, data, ["Travel to Sunagakure"], [], 10,
                                              travel_plan_for_actions(state, ["Travel to Sunagakure"]))
        self.assertNotIn("location", data["state_patch"])
        self.assertTrue(report["warnings"])

    def test_validator_allows_local_sublocation(self):
        state = self.fresh()
        data = {"narrative": "You enter the old tea shop.", "elapsed": {"amount": 5, "unit": "minutes"},
                "state_patch": {"location": "Old Tea Shop"}}
        data, _ = validate_turn_response(state, data, ["Enter the shop"], [], 5)
        self.assertEqual(data["state_patch"]["location"], "Old Tea Shop")

    def test_canon_graph_exposes_dependencies_and_confidence(self):
        graph = canon_dependency_graph(self.fresh())
        future = [row for row in graph["events"] if not row.get("major") is False and not row["status"] == "history"]
        self.assertTrue(future)
        self.assertIn("confidence", future[0])
        self.assertIn("requires", future[-1])

    def test_canon_divergence_marks_matching_event_impossible(self):
        state = self.fresh()
        graph = canon_dependency_graph(state)
        target = next(row for row in graph["events"] if row["status"] == "upcoming")
        state["canon_divergences"] = [{"event": target["title"], "status": "impossible",
                                       "reason": "The cause was prevented."}]
        changed = next(row for row in canon_dependency_graph(state)["events"] if row["title"] == target["title"])
        self.assertEqual(changed["status"], "impossible")

    def test_uncertainty_label_is_honest_about_reconstructed_dates(self):
        confidence = event_confidence({"title": "Known event", "day": 4})
        self.assertEqual(confidence["label"], "Best-fit timeline")

    def test_information_waits_for_delay_then_teaches_recipient(self):
        state = self.fresh()
        data = {"information_events": [{"fact": "A bridge was attacked", "source": "Courier",
                                        "channel": "letter", "recipients": ["Kakashi"],
                                        "delay_minutes": 60, "confidence": 90}]}
        transmit_information(state, data, 30)
        self.assertNotIn("Kakashi", state["npc_memories"])
        transmit_information(state, {}, 30)
        fact = state["npc_memories"]["Kakashi"]["knowledge"]["confirmed"][0]
        self.assertEqual(fact["fact"], "A bridge was attacked")

    def test_npc_schedule_becomes_due(self):
        state = self.fresh()
        state["npc_intentions"] = {"Kakashi": {"goal": "Report to the Hokage", "progress": 95,
                                                 "next_action": "Walk to the tower", "location": "Konohagakure"}}
        refresh_npc_schedules(state)
        state["canon_day"] = state["npc_schedules"]["Kakashi"]["due_day"]
        events = refresh_npc_schedules(state, 1440)
        self.assertEqual(state["npc_schedules"]["Kakashi"]["status"], "due")
        self.assertTrue(events)

    def test_player_correction_repairs_inventory_and_is_authoritative(self):
        state = self.fresh()
        record = apply_player_correction(state, "inventory_add", "", "Family sword", "It was never sold.")
        self.assertIn("Family sword", state["inventory"])
        self.assertEqual(state["authoritative_corrections"][-1]["id"], record["id"])

    def test_player_correction_repairs_quest_status(self):
        state = self.fresh()
        state["quests"] = [{"name": "Find the Courier", "status": "Active"}]
        apply_player_correction(state, "quest_status", "Find the Courier", "Complete")
        self.assertEqual(state["quests"][0]["status"], "Complete")

    def test_campaign_search_finds_history_skills_and_people(self):
        state = self.fresh()
        state["campaign_canon"] = [{"turn": 2, "action": "Meet Kakashi", "outcome": "Kakashi gives Ari a sealed letter."}]
        state["skills"] = {"Leaf Step": {"description": "A fast movement technique."}}
        state["npc_memories"] = {"Kakashi": {"attitude": "Friendly", "last_known_location": "Hokage Tower"}}
        self.assertGreaterEqual(len(campaign_search(state, "Kakashi")), 2)
        self.assertEqual(campaign_search(state, "Leaf Step")[0]["kind"], "skill")

    def test_campaign_search_finds_player_corrections(self):
        state = self.fresh()
        apply_player_correction(state, "fact", "Sword ownership", "The family sword was never sold.")
        results = campaign_search(state, "family sword")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["kind"], "correction")

    def test_deterministic_assessment_exposes_goals_and_routes(self):
        game = GameSession()
        game.state = self.fresh()
        result = game.assess_time_skip(2, "days", ["Travel to Sunagakure", "Train until I master tree walking"], "normal", use_model=False)
        self.assertEqual(result["assessment"]["structured_goals"][0]["action_index"], 1)
        self.assertEqual(result["assessment"]["travel_plans"][0]["destination"], "Sunagakure")

    def test_search_and_correction_http_endpoints_are_local(self):
        original_state, original_active = app_module.game.state, app_module.game.campaign_active
        try:
            app_module.game.state = self.fresh()
            app_module.game.state["campaign_canon"] = [{"turn": 1, "action": "Meet Kakashi", "outcome": "Kakashi shares a map."}]
            app_module.game.campaign_active = True
            client = app_module.app.test_client()
            found = client.get("/api/campaign/search?q=Kakashi")
            self.assertEqual(found.status_code, 200)
            self.assertTrue(found.get_json()["results"])
            corrected = client.post("/api/campaign/correct", json={"type": "currency", "value": "777", "target": ""})
            self.assertEqual(corrected.status_code, 200)
            self.assertEqual(app_module.game.state["currency"]["amount"], 777)
            self.assertEqual(app_module.game.state["turn"], 0)
        finally:
            app_module.game.state, app_module.game.campaign_active = original_state, original_active

    def test_panels_expose_integrity_travel_and_canon_dependencies(self):
        original_state, original_active = app_module.game.state, app_module.game.campaign_active
        try:
            app_module.game.state = self.fresh()
            app_module.game.campaign_active = True
            data = app_module.app.test_client().get("/api/panels").get_json()
            self.assertIn("integrity", data["simulation"])
            self.assertIn("travel_graph", data)
            self.assertIn("canon_dependencies", data)
        finally:
            app_module.game.state, app_module.game.campaign_active = original_state, original_active


if __name__ == "__main__":
    unittest.main()
