import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ai_client import AI
from engine_core import DEFAULT_SETTINGS
from game import GameSession
from util import scene_art_confidence, scene_category
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV370Tests(unittest.TestCase):
    def fresh(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": "Naruto", "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward merchant stall",
            "position": "Genin", "campaign_id": "v370-test", "opening_complete": True,
            "stats": {"Taijutsu": 35, "Ninjutsu": 38, "Genjutsu": 24,
                      "Chakra Control": 33, "Willpower": 31, "Intellect": 29},
        })
        game.campaign_active = True
        return game

    def test_version_and_manual_portrait_default(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertFalse(DEFAULT_SETTINGS["portrait_auto_generate"])

    def test_completed_combat_never_overrides_the_current_environment_art(self):
        game = self.fresh()
        game.state["combat"] = {
            "active": False, "outcome": "victory", "log": [{"action": "attack"}],
            "enemy": {"name": "Monster Horde", "is_group": True},
        }
        self.assertEqual(scene_category(game.state), "merchant_shop")
        self.assertEqual(scene_art_confidence(game.state)["label"], "Location match")

        game.state["combat"]["active"] = True
        self.assertEqual(scene_category(game.state), "monster_battlefield")
        self.assertEqual(scene_art_confidence(game.state)["label"], "Combat match")

    def test_each_combat_round_returns_only_its_new_log_rows(self):
        game = self.fresh()
        game.state.update(hp=500, hp_max=500)
        game.state["combat"] = {
            "active": True, "round": 1, "log": [], "cooldowns": {}, "enemy_debuffs": [],
            "enemy": {"name": "Durable Rival", "hp": 5000, "hp_max": 5000, "power": 30,
                      "difficulty_min": 99, "difficulty_max": 99, "attack_min": 99, "attack_max": 99},
        }
        first = game.resolve_combat_round("defend")
        first_len = len(first["log_tail"])
        total_after_first = len(game.state["combat"]["log"])
        second = game.resolve_combat_round("defend")
        self.assertGreater(first_len, 0)
        self.assertEqual(len(second["log_tail"]), len(game.state["combat"]["log"]) - total_after_first)

    def test_denied_or_absent_attack_target_does_not_spawn_contradictory_combat(self):
        game = self.fresh()
        data = {"narrative": "There is no armed bandit present. The attack cannot occur; no combat is initiated.",
                "state_patch": {}}
        started = game.ensure_immediate_combat_patch(
            data, ["Attack the armed bandit threatening Selka, leaving no room to negotiate."]
        )
        self.assertFalse(started)
        self.assertNotIn("combat", data["state_patch"])

    def test_explicit_attack_target_is_parsed_before_unrelated_known_names(self):
        game = self.fresh()
        game.state["contacts"] = {"Selka Vane": {"can_contact": True}}
        data = {"narrative": "The armed bandit lunges as Selka Vane takes cover.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(
            data, ["Attack the armed bandit threatening Selka Vane."]
        ))
        self.assertEqual(data["state_patch"]["combat"]["enemy"]["name"], "Armed Bandit")

    def test_guided_suggestions_drop_stale_combat_location_and_unknown_contact(self):
        game = self.fresh()
        game.state["combat"] = {"active": False, "outcome": "victory", "enemy": {"name": "Bandit"}}
        suggestions = game.guided_suggestions([
            "Defeat the Bandit", "Travel to Konohagakure — Eastern Ward merchant stall",
            "Reach out to Invented Stranger", "Inspect the sealed letter",
        ])
        joined = " | ".join(suggestions).lower()
        self.assertIn("inspect the sealed letter", joined)
        self.assertNotIn("defeat the bandit", joined)
        self.assertNotIn("invented stranger", joined)
        self.assertNotIn("travel to konohagakure", joined)

    def test_profession_skills_are_explicitly_hidden_from_combat(self):
        game = self.fresh()
        navigation = game.combat_skill_metadata("Navigator Fundamentals", "Chart routes and read weather")
        self.assertFalse(navigation["combat_usable"])
        self.assertEqual(navigation["effect_type"], "utility")
        self.assertEqual(navigation["category"], "utility")
        self.assertEqual(game.combat_skill_metadata("Fireball Jutsu", "Attack with a damaging chakra blast")["combat_usable"], True)

    def test_task_prompts_are_smaller_than_the_legacy_everything_prompt(self):
        game = self.fresh()
        game.state["story_log"] = [{"text": "old " * 300}] * 80
        full = game.gm_rules()
        moment = game.task_context("moment", "Train chakra control")
        combat = game.task_context("combat_summary")
        self.assertLess(len(moment), len(full) * 0.55)
        self.assertLess(len(combat), len(full) * 0.35)
        self.assertNotIn("advisor_thread", game.task_state_for_ai("moment"))

    def test_cached_input_tokens_are_reported_separately(self):
        ai = AI(key="test", model="gpt-5-mini", provider="cloud")
        ai._record_usage({"usage": {"input_tokens": 1000, "output_tokens": 100,
                                     "input_tokens_details": {"cached_tokens": 700}}})
        self.assertEqual(ai.usage["cached_input_tokens"], 700)
        self.assertEqual(ai.usage["uncached_input_tokens"], 300)
        self.assertTrue(ai.usage["cost_is_conservative"])

    def test_skill_notifications_never_dump_internal_dictionaries(self):
        game = self.fresh()
        before = copy.deepcopy(game.state)
        before["skills"] = {"Gale Imprint Style": {"rank": "Nascent", "bonus": 3,
                            "description": "Shape wind into prepared movement.", "origin": "old"}}
        after = copy.deepcopy(before)
        after["skills"]["Gale Imprint Style"]["origin"] = "new internal provenance"
        messages = game.notify(before, after, [])
        self.assertEqual(messages[0]["message"], "SKILL REFINED: Gale Imprint Style — details clarified")
        self.assertNotIn("{'rank'", messages[0]["message"])

    def test_placeholder_quest_is_replaced_with_a_concrete_briefing(self):
        game = self.fresh()
        before = copy.deepcopy(game.state)
        game.state["quests"] = [{
            "name": "The Bracer That Remembers", "status": "Active",
            "explanation": "No additional explanation is known yet.",
            "current_knowledge": ["The quest begins at Konohagakure — Eastern Ward merchant stall."],
            "clear_conditions": ["Advance The Bracer That Remembers"],
            "first_step": "Follow the first known lead: The quest begins at Konohagakure — Eastern Ward merchant stall.",
        }]
        game.ensure_quest_briefings(
            before,
            "A warped bracer pulses when touched, revealing living metal inside ordinary iron. The workshop owner asks you to explain it.",
        )
        quest = game.state["quests"][0]
        self.assertIn("warped bracer", quest["explanation"].lower())
        self.assertIn("investigate", quest["clear_conditions"][0].lower())
        self.assertIn("examine the evidence", quest["first_step"].lower())
        self.assertNotIn("no additional explanation", " ".join(str(v) for v in quest.values()).lower())

    def test_goal_completed_at_requested_endpoint_is_not_called_interrupted(self):
        class CompletedAtEndpointAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "The planned day of focused work is completed.", "updates": [],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 1, "unit": "days"},
                    "interrupted": True, "interruption_kind": "goal_complete",
                    "interruption_reason": "The goal was completed.",
                    "goal_status": {"action": "Train navigation", "achieved": True,
                                    "elapsed": {"amount": 1, "unit": "days"},
                                    "explanation": "The planned work is done."},
                    "completed_actions": ["Train navigation"], "deferred_actions": [],
                    "suggested_actions": ["Test the result", "Ask a mentor", "Rest"],
                }

        game = self.fresh()
        game.state["canon_day"] = 5000
        game.state["calendar_anchor_day"] = 5000
        game.ai = CompletedAtEndpointAI()
        result = game.run_time_skip(
            1, "days", ["Train navigation"], "normal",
            {"checks": [], "reachable_actions": ["Train navigation"], "deferred_actions": []},
        )
        self.assertFalse(result["interrupted"])
        self.assertEqual(result["interruption_kind"], "")

    def test_autosaves_keep_fewer_checkpoints_than_manual_saves(self):
        game = self.fresh()
        game.checkpoints = [{"id": i} for i in range(12)]
        game.system_log = [str(i) for i in range(1200)]
        self.assertEqual(len(game.save_bundle("autosave")["checkpoints"]), 2)
        self.assertEqual(len(game.save_bundle("manual")["checkpoints"]), 4)
        self.assertEqual(len(game.save_bundle("autosave")["system_log"]), 400)

    def test_frontend_filters_combat_skills_resets_time_and_supports_mobile_advisor(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("combatAbilityUsable", js)
        self.assertIn(".filter((name) => combatAbilityUsable(s, name))", js)
        self.assertIn('$("#time-unit").value = "moment";', js)
        self.assertIn("flex-wrap:wrap", css)
        self.assertIn('id="st-portrait-auto"', html)


if __name__ == "__main__":
    unittest.main()
