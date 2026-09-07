import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from simulation import deterministic_assessment
from portrait_generator import portrait_signature
from util import scene_category, scene_image_url
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3121ProgressionAndQATests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def make_system_game(self, world):
        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "QA Traveler", "world": world, "difficulty": "Adventurer",
            "stats": {name: 20 for name in abilities_for(world)},
            "special": {"Archetype": "Blacksmith" if world == "Overgeared" else "All-Rounder"},
            "titles": ["Early Adopter"], "opening_complete": True,
            "campaign_id": f"qa-{world}", "xp": 0, "xp_next": 100, "level": 1,
        })
        game.campaign_active = True
        return game

    def test_ordinary_numbered_kido_practice_is_not_a_power_leap(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Bleach", "stats": {name: 25 for name in abilities_for("Bleach")}})
        action = "Practice Bakudo #1 and Hado #4 for an hour"
        assessment = deterministic_assessment(
            state, [action], {"reachable_actions": [action], "deferred_actions": [], "time_dc_modifier": 0}
        )
        self.assertFalse(assessment.get("power_jump_warning"))
        self.assertEqual(assessment["checks"], [])

    def test_named_sensor_skill_trains_chakra_control_not_taijutsu(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "world": "Naruto", "difficulty": "Adventurer",
            "stats": {name: 30 for name in abilities_for("Naruto")},
            "skills": {"Echo Thread Technique": {
                "description": "Forms fine chakra threads for precise attacks, traps, sensing, or utility.",
                "growth_path": "Improve chakra control and learn matching nature transformation.",
            }},
        })
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(data, [], 7, "days", ["Train Echo Thread Technique"], "normal")
        self.assertGreater(data["state_patch"]["stats"]["Chakra Control"],
                           data["state_patch"]["stats"]["Taijutsu"])
        self.assertEqual(data["state_patch"]["progression_log"][-1]["ability"], "Chakra Control")

    def test_veteran_gamer_is_trained_not_exceptional(self):
        game = GameSession()
        stats = {name: 20 for name in abilities_for("Solo Max-Level Newbie")}
        profile = game.infer_starting_profile(
            "Solo Max-Level Newbie", "Veteran Gamer", "All-Rounder",
            "A veteran gamer who studies hidden routes and trains efficiently.",
            stats, "Earth — Tower Entrance", allow_starting_specials=False,
        )
        self.assertEqual(profile["power_band"], "Trained starter")
        self.assertEqual(profile["power_notice"], "")

    def test_undated_skip_updates_follow_earlier_canon_events(self):
        game = GameSession()
        game.settings["autosave"] = False
        game.new_campaign(
            "Ari", "Naruto", "Adventurer", "", "", "", "Academy Student",
            "Ninjutsu Student", {name: 30 for name in abilities_for("Naruto")},
            starting_era_id="before_naruto_birth",
        )
        result = game.apply_time_skip({
            "narrative": "Training continues through the full span.",
            "updates": [{"sequence": 1, "type": "action", "title": "Training complete",
                         "narrative": "Ari completes the planned training."}],
            "state_patch": {}, "events": [], "timeline_events": [],
            "elapsed": {"amount": 8, "unit": "days"}, "interrupted": False,
            "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
            "goal_status": {}, "new_contacts": [], "incoming_chats": [],
            "completed_actions": ["Train"], "deferred_actions": [],
            "suggested_actions": ["Review the result", "Speak to a mentor", "Rest"],
        }, 8, "days", {"actions": ["Train"], "rolls": [], "elapsed_minutes": 8 * 1440, "intensity": "normal"})
        dated = [entry for entry in result["story"] if entry.get("canon_day") is not None]
        days = [entry["canon_day"] for entry in dated]
        self.assertEqual(days, sorted(days))
        self.assertEqual(dated[-1]["canon_day"], result["state"]["canon_day"])
        self.assertTrue(any("TRAINING COMPLETE" in entry["text"] for entry in dated))
        self.assertTrue(any("SHINOBI DOWNTIME" in entry["text"] for entry in dated))

    def test_successful_opening_check_changes_combat_state_once(self):
        game = self.make_system_game("Overgeared")
        game.state["combat"] = {
            "active": True, "round": 1,
            "enemy": {"name": "Elite Guardian", "hp": 200, "hp_max": 200, "power": 45},
            "opening_check": {"success": True, "total": 92, "difficulty": 80,
                              "margin": 12, "ability": "Strength", "breakthrough": False},
        }
        game.ensure_combat_numbers()
        first_hp = game.state["combat"]["enemy"]["hp"]
        self.assertLess(first_hp, 200)
        self.assertEqual(game.state["combat"]["opening_advantage"]["remaining_hp"], first_hp)
        game.ensure_combat_numbers()
        self.assertEqual(game.state["combat"]["enemy"]["hp"], first_hp)

    def test_overgeared_skip_tracks_training_xp_and_persistent_earned_title(self):
        game = self.make_system_game("Overgeared")
        before = copy.deepcopy(game.state)
        award = game.calculate_xp_award(["Train blacksmithing every day"], [], 7 * 1440, "normal", [])[0]
        game.apply_system_xp(before, ["Train blacksmithing every day"], [], 7 * 1440, "normal", [])
        game.reconcile_title_events([{"type": "title", "title": "Patient Artisan",
                                      "message": "Title acquired: Patient Artisan"}])
        self.assertEqual(game.state["progression_log"][-1]["xp_awarded"], award)
        self.assertEqual(game.state["xp"], award)
        self.assertIn("Early Adopter", game.state["titles"])
        self.assertIn("Patient Artisan", game.state["titles"])
        notices = game.notify(before, game.state, [])
        self.assertTrue(any(f"XP +{award}" in row["message"] for row in notices))
        self.assertTrue(any("TITLE ACQUIRED: Patient Artisan" in row["message"] for row in notices))

    def test_solo_level_up_reports_xp_even_when_bar_returns_to_same_value(self):
        game = self.make_system_game("Solo Max-Level Newbie")
        award = game.calculate_xp_award(["Defeat the floor guardian"], [], 60, "normal", [])[0]
        game.state["xp_next"] = award
        before = copy.deepcopy(game.state)
        game.apply_system_xp(before, ["Defeat the floor guardian"], [], 60, "normal", [])
        game.reconcile_title_events([{"type": "world", "message": "Earned the title: Gate Breaker"}])
        self.assertEqual(game.state["xp"], 0)
        self.assertEqual(game.state["level"], 2)
        self.assertEqual(game.state["progression_log"][-1]["xp_awarded"], award)
        self.assertIn("Gate Breaker", game.state["titles"])
        notices = game.notify(before, game.state, [])
        self.assertTrue(any(f"XP +{award}" in row["message"] for row in notices))
        self.assertTrue(any("LEVEL UP" in row["message"] for row in notices))

    def test_xp_notice_survives_a_capped_progression_ledger(self):
        game = self.make_system_game("Overgeared")
        game.state["turn"] = 400
        game.state["progression_log"] = [
            {"type": "xp", "turn": turn, "xp_awarded": 1} for turn in range(101, 401)
        ]
        before = copy.deepcopy(game.state)
        game.apply_system_xp(before, ["Study a new production method"], [], 60, "normal", [])
        self.assertEqual(len(game.state["progression_log"]), 300)
        notices = game.notify(before, game.state, [])
        self.assertTrue(any("XP +" in row["message"] for row in notices))

    def test_title_patch_cannot_erase_older_titles(self):
        game = self.make_system_game("Overgeared")
        from state_guard import apply_guarded_patch
        apply_guarded_patch(game.state, {"titles": ["Commission Finisher"]}, source="test")
        self.assertEqual(game.state["titles"], ["Early Adopter", "Commission Finisher"])

    def test_missing_goal_status_gets_a_deterministic_incomplete_explanation(self):
        class GoalOmittingNarrator:
            model = "goal-omitting-test"

            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "The training period ends with the technique still unstable.",
                    "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 3, "unit": "days"}, "interrupted": False,
                    "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["Seek a chakra-control instructor"],
                }

        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "world": "Naruto", "difficulty": "Adventurer", "canon_day": 5000,
            "calendar_anchor_day": 5000,
            "stats": {name: 30 for name in abilities_for("Naruto")},
            "opening_complete": True,
        })
        game.ai = GoalOmittingNarrator()
        action = "Train until I master the Echo Thread Technique"
        result = game.run_time_skip(
            3, "days", [action], "normal",
            {"checks": [], "reachable_actions": [action], "deferred_actions": []},
        )
        self.assertFalse(result["goal_status"]["achieved"])
        self.assertIn("without confirming", result["goal_status"]["explanation"])
        self.assertTrue(result["goal_status"]["next_hint"])
        self.assertTrue(any("GOAL NOT YET COMPLETE" in row["text"] for row in result["story"]))

    def test_frontend_exposes_world_clock_progress_and_grouped_one_piece_starts(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("entry.world_time", source)
        self.assertIn("CURRENT SCENE", source)
        self.assertIn("% to next point", source)
        self.assertIn("Selected skip: next major event", source)
        self.assertIn("<optgroup", source)
        self.assertIn('debuff: "⛓ "', source)
        self.assertIn("function clearTransientFeedback()", source)
        self.assertIn("banner.replaceChildren()", source)

    def test_mobile_suggestions_wrap_instead_of_clipping(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        mobile = css[css.index("@media(max-width:720px){", css.index("@media(max-width:720px){") + 1):]
        self.assertIn(".suggested-actions{ max-width:100%; grid-template-columns:repeat(2,minmax(0,1fr)); overflow:visible; }", mobile)
        self.assertIn("white-space:normal", mobile)

    def test_completed_combat_cannot_override_current_landmark_art(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "world": "Naruto", "location": "Konohagakure",
            "combat": {"active": False, "enemy": {"name": "Bandit"}, "log": ["Fight ended"]},
        })
        image, category = scene_image_url(state)
        self.assertEqual(category, "town_square")
        self.assertIn("naruto_konohagakure", image)

    def test_distant_world_battle_does_not_change_vague_local_activity_art(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "world": "Overgeared", "location": "Workshop",
            "current_activity": "Forge a careful blade",
            "world_events": ["A monster army begins a distant battlefield assault"],
            "timeline": ["War and siege consume the eastern front"],
        })
        self.assertEqual(scene_category(state), "merchant_shop")

    def test_hospital_uses_its_dedicated_still_art(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Custom World", "location": "Royal Hospital Infirmary"})
        image, category = scene_image_url(state)
        self.assertEqual(category, "hospital_clinic")
        self.assertEqual(image, "/assets/generated_scenes/hospital_clinic.png")

    def test_nonvisible_inventory_does_not_regenerate_portrait(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Overgeared", "name": "Rune", "appearance_desc": "A young smith with dark curls."})
        before = portrait_signature(state)
        state["equipment"] = {"Ore pouch": "12 iron ore", "Quest key": "Old workshop key"}
        self.assertEqual(before, portrait_signature(state))
        state["equipment"]["Armor"] = "A newly forged blue-steel breastplate"
        self.assertNotEqual(before, portrait_signature(state))


if __name__ == "__main__":
    unittest.main()
