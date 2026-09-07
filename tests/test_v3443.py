import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from gm_policy import (
    clean_model_text, distinct_suggestions, enforce_response_policy,
    parse_player_intent, progression_plan, select_approved_example,
    temporal_budget,
)
from response_guard import normalize_turn_response
from world_progression import normalize_world_progression
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3443GMPolicyTests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": world, "difficulty": "Adventurer",
            "location": "Konohagakure", "position": "Genin", "opening_complete": True,
            "stats": {"Taijutsu": 80, "Ninjutsu": 120, "Genjutsu": 40,
                      "Chakra Control": 75, "Willpower": 70, "Intellect": 55},
            "npc_memories": {"Konan": {"role": "Akatsuki founder"}},
            "contacts": {"Konan": {"relationship": "Ally"}},
        })
        game.campaign_active = True
        return game

    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_intent_parser_preserves_method_target_duration_and_standing_order(self):
        contract = parse_player_intent(
            "Ensure Konan trains every day for six months using shadow clones so that she masters sealing.",
            self.fresh().state,
        )
        self.assertIn("training", contract["activity"])
        self.assertIn("Konan", contract["targets"])
        self.assertEqual(contract["duration"]["unit"], "months")
        self.assertTrue(contract["standing"])
        self.assertIn("shadow clones", contract["method"])

    def test_real_turn_prompts_route_only_relevant_large_modules(self):
        game = self.fresh()
        social = game.task_rules("moment", "Negotiate a peace with Konan")
        finance = game.task_rules("moment", "Pay the monthly rent for my shop")
        self.assertNotIn("do NOT manually re-add", social)
        self.assertIn("do NOT manually re-add", finance)
        self.assertLess(len(social), len(finance))

    def test_temporal_budget_stops_moments_at_the_next_decision(self):
        budget = temporal_budget("moment")
        self.assertEqual(budget["mode"], "immediate_beat")
        self.assertIn("decision point", budget["stop"])
        self.assertLessEqual(budget["max_minutes"], 1440)

    def test_progression_plan_promises_visible_sustained_training(self):
        plan = progression_plan(self.fresh().state, ["Train Ninjutsu rigorously"], 30 * 1440, "rigorous")
        self.assertTrue(plan["training"])
        self.assertIn(plan["expected_progress"], {"substantial", "breakthrough-eligible"})
        self.assertIn("Ninjutsu", plan["targets"])

    def test_one_complication_limit_requires_a_cause(self):
        data = {"narrative": "The plan works.", "causal_outcome": {"direct_result": "The plan works.", "complications": [
            {"effect": "A guard objects", "cause": "The guard witnessed the trespass"},
            {"effect": "A storm arrives", "cause": "The established forecast reached the coast"},
            {"effect": "Unseen enemies gather"},
        ]}}
        fixed = enforce_response_policy(data, {"task": "narrator_and_resolution"}, self.fresh().state)
        self.assertEqual(len(fixed["causal_outcome"]["complications"]), 1)
        self.assertTrue(fixed["causal_outcome"]["complications"][0]["cause"])

    def test_template_cleanup_removes_filler_and_duplicate_lines(self):
        text = clean_model_text("The training works. The training works. What does this change for your next move?", True)
        self.assertEqual(text, "The training works.")

    def test_information_envelope_repairs_string_recipients(self):
        data = normalize_turn_response({"narrative": "News travels.", "information_events": {
            "fact": "Kael returned", "source": "Konan", "channel": "message", "recipients": "Nagato",
            "delay_minutes": "15", "confidence": "90",
        }})
        self.assertEqual(data["information_events"][0]["recipients"], ["Nagato"])
        self.assertEqual(data["information_events"][0]["delay_minutes"], 15)

    def test_approved_example_selection_prefers_matching_activity(self):
        rated = [
            {"action": "Fight the bandits", "outcome": "The bandits fall."},
            {"action": "Talk with Konan", "outcome": "Konan agrees to listen."},
        ]
        chosen = select_approved_example(rated, "Negotiate with Konan")
        self.assertEqual(chosen["action"], "Talk with Konan")

    def test_suggestions_drop_unknown_contacts_and_finished_combat(self):
        state = self.fresh().state
        state["combat"] = {"active": False}
        choices = distinct_suggestions([
            "Talk to Stranger about the plan", "Continue the fight", "Investigate the eastern gate",
        ], state)
        self.assertFalse(any("Stranger" in row or "Continue the fight" in row for row in choices))
        self.assertEqual(len(choices), 3)

    def test_advisor_estimates_named_campaign_npc_from_world_role(self):
        game = self.fresh("Bleach")
        game.state["name"] = "Aiko"
        game.state["stats"] = {"Zanjutsu": 110, "Hakuda": 80, "Hoho": 95,
                               "Kido": 70, "Reiatsu Control": 90, "Willpower": 85}
        game.state["npc_memories"] = {"Rina": {"role": "Captain of Division 6"}}
        result = game._local_power_comparison("How strong am I compared with Rina?")
        self.assertIsNotNone(result)
        self.assertIn("Rina", result["points"][0])
        self.assertIn("350.0", result["points"][0])

    def test_naruto_scroll_rolls_use_high_contrast_ink(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        selector = 'body[data-world="Naruto"] .world-turn-envelope[data-presentation="scroll"] .story-roll-pill.hit'
        self.assertIn(selector, css)
        self.assertIn("color:#173d26", css)
        self.assertIn("background:#d9e5bb", css)

    def test_new_turn_focus_uses_the_actual_scroll_owner(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("feed.scrollHeight > feed.clientHeight + 2", js)
        self.assertIn("firstNewBeat.getBoundingClientRect().top + window.scrollY", js)


class WorldwalkerV3443NarutoLineageRecoveryTests(unittest.TestCase):
    def state(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Naruto", "name": "Ren", "special": {}, "skills": {},
                      "campaign_canon": [], "chapter_summaries": []})
        return state

    def test_narratively_awakened_sharingan_populates_dojutsu_panel(self):
        state = self.state()
        state["campaign_canon"] = [{
            "turn": 18, "action": "I awaken my Sharingan to follow his movement.",
            "outcome": "Ren's Sharingan opens, letting him read the attack.",
        }]
        normalize_world_progression(state)
        profile = state["special"]["Dōjutsu Profile"]
        self.assertEqual(profile["name"], "Sharingan")
        self.assertTrue(profile["abilities"])
        self.assertEqual(state["special"]["Dōjutsu"], "Sharingan")

    def test_sharingan_skill_in_an_old_save_repairs_the_panel(self):
        state = self.state()
        state["skills"]["Sharingan"] = {"rank": "Two-Tomoe", "description": "Reads movement and chakra."}
        normalize_world_progression(state)
        self.assertEqual(state["special"]["Dōjutsu Profile"]["name"], "Sharingan")


if __name__ == "__main__":
    unittest.main()
