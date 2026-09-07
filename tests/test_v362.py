import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV362Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def fresh(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": "Naruto", "difficulty": "Adventurer",
            "location": "Konohagakure — Eastern Ward", "position": "Genin",
            "stats": {"Taijutsu": 30, "Ninjutsu": 30, "Genjutsu": 30,
                      "Chakra Control": 30, "Willpower": 30, "Intellect": 30},
            "campaign_id": "v362-test", "opening_complete": True,
        })
        game.campaign_active = True
        return game

    def test_event_notice_has_no_private_chat_or_yes_no_intervention(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ACKNOWLEDGE EVENT", html)
        self.assertIn("response prompt is waiting in the Chronicle", html)
        self.assertNotIn('id="event-window-input"', html)
        self.assertNotIn('id="btn-canon-intervene"', html)
        self.assertNotIn("/api/event/respond", js)
        self.assertNotIn("APP.eventWindow", js)

    def test_canon_prompt_fallback_uses_location_role_and_event(self):
        game = self.fresh()
        prompt = game._event_action_prompt({"title": "The Nine-Tails Attack", "location": "Konohagakure"})
        self.assertIn("Kael", prompt)
        self.assertIn("Eastern Ward", prompt)
        self.assertIn("Genin", prompt)
        self.assertIn("Nine-Tails", prompt)

    def test_explicit_attack_backfills_structured_combat(self):
        game = self.fresh()
        game.state["npc_memories"] = {"Mizuki": {"attitude": "hostile"}}
        data = {"narrative": "**Mizuki** reaches for a weapon.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(data, ["I attack Mizuki before he escapes"]))
        combat = data["state_patch"]["combat"]
        self.assertTrue(combat["active"])
        self.assertEqual(combat["enemy"]["name"], "Mizuki")

    def test_unavoidable_incoming_attack_backfills_combat_but_negotiation_does_not(self):
        game = self.fresh()
        attacked = {"narrative": "The masked shinobi ambushes you; there is no time to negotiate.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(attacked, []))
        peaceful = {"narrative": "The guard waits for an answer.", "state_patch": {}}
        self.assertFalse(game.ensure_immediate_combat_patch(peaceful, ["Negotiate to avoid a fight"]))

    def test_challenge_play_and_stop_defers_remaining_plan(self):
        class Narrator:
            model = "test"
            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "The seal gives way after a focused struggle.",
                    "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 1, "unit": "days"}, "interrupted": False,
                    "interruption_kind": "", "interruption_reason": "", "interruption_context": "",
                    "intervention_prompt": "", "major_event_reached": False,
                    "major_event_kind": "", "major_event_title": "", "goal_status": {},
                    "new_contacts": [], "incoming_chats": [],
                    "completed_actions": ["Break the ancient seal", "Travel to the capital"],
                    "deferred_actions": [], "suggested_actions": ["Inspect the opened seal", "Rest", "Ask Sakura for help"],
                }

        game = self.fresh()
        game.ai = Narrator()
        assessment = {
            "checks": [{"id": "seal", "action_index": 0, "reason": "Break the ancient seal",
                        "ability": "Ninjutsu", "difficulty_min": 80, "difficulty_max": 90,
                        "relevant_average_stat": 30, "major_event": False}],
            "time_budget": {"max_elapsed_minutes": 43200}, "standing_plan": [],
            "travel_plans": [], "deferred_actions": [],
        }
        result = game.run_time_skip(
            30, "days", ["Break the ancient seal", "Travel to the capital"], "normal", assessment,
            manual_rolls={"seal": 95}, challenge_modes={"seal": "timing"}, challenge_resolution_mode="stop",
        )
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["interruption_kind"], "challenge_complete")
        self.assertIn("Travel to the capital", result["deferred_actions"])

    def test_mobile_chat_and_advisor_keep_large_scrollable_message_areas(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("chat-modal", html)
        self.assertIn("advisor-modal", html)
        self.assertIn(".chat-modal,.advisor-modal{ height:calc(100dvh - 14px)", css)
        self.assertIn(".advisor-messages{ flex:1 1 0; min-height:0", css)
        self.assertIn(".advisor-starters,.advisor-followups{ flex:0 0 auto; flex-wrap:nowrap", css)


if __name__ == "__main__":
    unittest.main()
