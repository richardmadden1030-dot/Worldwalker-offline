import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module
import game as game_module
from game import GameSession
from worlds import BASE_STATE, WORLD_DATA


class WorldwalkerV251Tests(unittest.TestCase):
    def test_vague_background_generates_named_world_ability_and_full_context(self):
        game = GameSession()
        original = "I am a gifted student with some kind of fire ability who wants to protect people."
        preview = game.preview_campaign(
            "Ari", "Naruto", "Adventurer", original, "", "",
            "Academy Graduate", "Ninjutsu Student", {},
        )
        profile = preview["starting_profile"]
        generated = profile["generated_ability"]
        self.assertIn("Ember", generated["name"])
        self.assertIn(generated["name"], profile["skills"])
        for field in ("origin", "effect", "limitation", "growth_path"):
            self.assertTrue(generated["details"][field])
        self.assertIn(original.rstrip("."), preview["background"])
        self.assertGreater(len(preview["background"]), len(original) + 200)
        self.assertGreater(profile["growth_profile"]["learning_rate"], 1)
        self.assertIn("motivation", profile["background_details"])

    def test_generated_background_profile_persists_into_new_campaign(self):
        game = GameSession()
        preview = game.preview_campaign(
            "Mira", "Hunter x Hunter", "Adventurer", "I have a strange sensing talent.", "", "",
            "Whale Island Local", "Rookie Hunter", {},
        )
        state = game.new_campaign(
            "Mira", "Hunter x Hunter", "Adventurer", "I have a strange sensing talent.", "", "",
            "Whale Island Local", "Rookie Hunter", {},
            preview_stats=preview["abilities"], preview_profile=preview["starting_profile"],
        )
        # Hunter x Hunter now reserves supernatural personal powers for the
        # persistent Nen system instead of a generic starting-ability card.
        self.assertIsNone(preview["starting_profile"]["generated_ability"])
        self.assertEqual(state["special"]["Nen Access"], "Undiscovered")
        self.assertEqual(state["special"]["Hatsu"], "Undiscovered")
        self.assertIn("_latent_nen_profile", game.state)
        self.assertIn("Growth Profile", state["special"])
        self.assertIn("Background Details", state["special"])
        self.assertIn("unfinished expectation", state["background"].lower())
        self.assertIn("guidance", state["special"]["Background Details"]["key_connection"].lower())

    def test_growth_profile_multiplier_affects_sustained_training(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(
            world="Naruto",
            stats={k: 35 for k in ("Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect")},
            special={"Archetype": "Ninjutsu Student", "Growth Profile": {"learning_rate": 1.5}},
        )
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("game.random.random", return_value=1.0):
            game.enforce_training_progress(data, [], 10, "days", ["Train ninjutsu every day"], "normal")
        entry = data["state_patch"]["progression_log"][-1]
        self.assertEqual(entry["learning_rate_multiplier"], 1.5)
        self.assertGreaterEqual(entry["stat_gain"], 3)

    def test_fresh_campaign_has_three_useful_leads_without_ai(self):
        game = GameSession()
        state = game.new_campaign(
            "Mira", "Naruto", "Adventurer", "", "", "",
            "Academy Graduate", "Ninjutsu Student", {},
        )
        self.assertEqual(len(state["suggested_actions"]), 3)
        self.assertTrue(any("training" in lead.lower() for lead in state["suggested_actions"]))
        self.assertTrue(any(state["location"].lower() in lead.lower() for lead in state["suggested_actions"]))

    def test_guided_suggestions_prioritize_quest_and_prerequisite(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(
            world="Hunter x Hunter",
            location="Whale Island",
            quests=[{"name": "Hunter Exam", "clear_conditions": ["Reach the exam site"]}],
            prerequisite_tracks=[{"name": "Learn Nen", "next_steps": ["Find a qualified teacher"]}],
        )
        leads = game.guided_suggestions([])
        self.assertEqual(len(leads), 3)
        self.assertIn("Hunter Exam", leads[0])
        self.assertIn("Learn Nen", leads[1])

    def test_gm_contract_requires_contextual_journey_leads(self):
        rules = GameSession().gm_rules()
        self.assertIn("exactly 3 concise suggested_actions", rules)
        self.assertIn("strongest current lead", rules)
        self.assertIn("journey", rules.lower())

    def test_music_api_creates_world_folders_and_lists_world_plus_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(app_module, "MUSIC_ROOT", root):
                app_module.ensure_music_folders()
                (root / "Naruto" / "village.mp3").write_bytes(b"ID3")
                (root / "Shared" / "travel.mp4").write_bytes(b"test")
                response = app_module.app.test_client().get("/api/music?world=Naruto")
                payload = response.get_json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual({track["filename"] for track in payload["tracks"]}, {"village.mp3", "travel.mp4"})
                self.assertEqual({path.name for path in root.iterdir()}, {"Shared", *WORLD_DATA.keys()})

    def test_empty_advance_continues_previous_standing_orders(self):
        class PlanningAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}

        game = GameSession()
        game.ai = PlanningAI()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Naruto", standing_orders=["Continue sensory training"])
        result = game.assess_time_skip(3, "days", "", "normal")
        self.assertEqual(result["orders"], ["Continue sensory training"])

    def test_goal_completion_stops_skip_at_actual_elapsed_time(self):
        class ResolutionAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "Ari masters the sensing exercise on the thirteenth morning.",
                    "updates": [{"sequence": 1, "type": "action", "title": "Mastery", "narrative": "The technique finally stabilizes."}],
                    "state_patch": {"skills": {"Sensory Ninjutsu": {"rank": "Novice"}}},
                    "events": [], "timeline_events": [], "elapsed": {"amount": 13, "unit": "days"},
                    "interrupted": False, "completed_actions": ["Train until I master sensory ninjutsu"], "deferred_actions": [],
                    "goal_status": {"action": "Train until I master sensory ninjutsu", "achieved": True,
                                    "elapsed": {"amount": 13, "unit": "days"}, "explanation": "The sensing pattern becomes reliable.", "next_hint": ""},
                    "suggested_actions": ["Test the technique", "Recover", "Ask a mentor for refinement"],
                }

        game = GameSession()
        game.ai = ResolutionAI()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Ari", world="Naruto", stats={k: 35 for k in ("Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect")}, special={"Archetype": "Ninjutsu Student"})
        before = game.state["canon_time_minutes"]
        result = game.run_time_skip(1, "months", ["Train until I master sensory ninjutsu"], "normal", {"checks": []})
        self.assertEqual(result["interruption_kind"], "goal_complete")
        self.assertEqual(result["elapsed"], {"amount": 13, "unit": "days"})
        self.assertEqual(game.state["canon_time_minutes"] - before, 13 * 1440)
        self.assertTrue(result["goal_status"]["achieved"])

    def test_moment_assesses_only_next_beat_and_defers_later_actions(self):
        class PlanningAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {"checks": [], "deferred_actions": []}

        game = GameSession()
        game.ai = PlanningAI()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Naruto", queued_actions=["Speak with the Hokage", "Travel to the border"])
        result = game.assess_time_skip(99, "moment", "", "normal")
        self.assertEqual(result["amount"], 1)
        self.assertEqual(result["orders"], ["Speak with the Hokage"])
        self.assertIn("Travel to the border", result["assessment"]["deferred_actions"])
        self.assertEqual(result["time_budget"]["max_elapsed_minutes"], 1440)

    def test_moment_ui_has_no_quantity_and_routine_advance_has_no_preview_modal(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="time-amount" type="number" min="1" value="1" aria-label="Time skip amount" hidden', html)
        self.assertNotIn('value="minutes"', html)
        self.assertNotIn('value="hours"', html)
        self.assertNotIn('id="modal-advance-preview"', html)
        self.assertNotIn('openModal("modal-advance-preview")', script)

    def test_chronicle_scroll_and_major_event_notice_is_informational(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="intervention-bar"', html)
        self.assertNotIn('id="btn-canon-intervene"', html)
        self.assertNotIn('NO — KEEP SIMULATING', html)
        self.assertIn('id="modal-event-window"', html)
        self.assertIn('ACKNOWLEDGE EVENT', html)
        self.assertIn('response prompt is waiting in the Chronicle', html)
        self.assertIn('function openEventNotice(result)', script)
        self.assertNotIn('/api/event/respond', script)
        self.assertIn('overflow-y:scroll', css)
        self.assertIn('.modal-xl>.modal-body{ min-height:0; overflow-y:auto; }', css)

    def test_roll_summary_is_one_readable_action_line(self):
        game = GameSession()
        summary = game.format_roll_summary("Climb the tower", {
            "roll": 63, "total": 71, "difficulty": 65,
            "success": True, "breakthrough": False,
        })
        self.assertEqual(summary, "Climb the tower — 63 +8 = 71/100 vs. 66 needed — SUCCESS")
        self.assertNotIn("Stat", summary)
        self.assertNotIn("Titles", summary)

    def test_explicit_quest_start_always_creates_a_briefing(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Ari", location="Whale Island")
        before = copy.deepcopy(game.state)
        new_quests = game.ensure_quest_briefings(before, "I start a quest to find the missing fishing boat")
        self.assertEqual(len(new_quests), 1)
        quest = game.state["quests"][0]
        self.assertEqual(quest["status"], "Active")
        self.assertTrue(quest["explanation"])
        self.assertTrue(quest["current_knowledge"])
        self.assertTrue(quest["clear_conditions"])
        self.assertTrue(quest["first_step"])
        self.assertTrue(quest["risks"])
        self.assertTrue(any("ADDED" in entry["text"] for entry in game.story_log))
        self.assertFalse(any("Objective:" in entry["text"] for entry in game.story_log))

    def test_autosave_overwrites_one_file_per_campaign(self):
        with tempfile.TemporaryDirectory() as temp:
            save_root = Path(temp)
            with patch.object(game_module, "SAVE_DIR", save_root):
                game = GameSession()
                game.state = copy.deepcopy(BASE_STATE)
                game.state.update(name="Ari", world="Naruto", turn=1)
                game.autosave()
                legacy = save_root / "_autosaves" / "Ari_Naruto_autosave_2.json"
                legacy.write_text("{}", encoding="utf-8")
                game.state["turn"] = 2
                game.autosave()
                autosaves = list((save_root / "_autosaves").glob("*.json"))
                self.assertEqual([path.name for path in autosaves], ["Ari_Naruto_autosave.json"])
                self.assertEqual(len([entry for entry in game.list_saves() if entry["kind"] == "autosave"]), 1)


if __name__ == "__main__":
    unittest.main()
