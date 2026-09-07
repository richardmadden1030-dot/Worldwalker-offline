import sys
import unittest
import copy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION
from worlds import BASE_STATE
from naruto_system import build_jinchuriki_profile
from portrait_generator import portrait_signature


class WorldwalkerV3310MobileTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_approved_mobile_navigation_and_persistent_controls_ship(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for element_id in ("mobile-status-ribbon", "mobile-advance-dock", "mobile-bottom-nav",
                           "mobile-combat-dock", "modal-mobile-more", "mobile-chronicle-tools"):
            self.assertIn(f'id="{element_id}"', html)
        for view in ("chronicle", "actions", "character", "map", "more"):
            self.assertIn(f'data-mobile-view="{view}"', html)
        self.assertIn('body[data-mobile-view="chronicle"] .col-center', css)
        self.assertIn("position:fixed; left:0; right:0", css)
        self.assertIn("renderMobileState", js)

    def test_mobile_qol_is_local_and_does_not_add_ai_calls(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for feature in ("beforeinstallprompt", "mobile-low-data", "mobile-large-text", "navigator.vibrate",
                        "worldwalker_mobile_", "mobile-filtered", "pointerdown", "beforeunload"):
            self.assertIn(feature, js)
        self.assertNotIn('/api/ai/mobile', js)

    def test_mobile_secondary_pages_are_full_screen_and_safe_area_aware(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("#modal-journal>.modal,#modal-advisor>.modal,#modal-chat>.modal,#modal-mobile-more>.modal", css)
        self.assertIn("height:100dvh", css)
        self.assertIn("env(safe-area-inset-bottom)", css)
        self.assertIn("content-visibility:auto", css)

    def test_named_character_power_question_does_not_use_player_shortcut(self):
        game = GameSession()
        game.state["world"] = "Naruto"
        self.assertIsNone(game._local_advisor_answer("How strong is Konan now?"))
        self.assertIsNotNone(game._local_advisor_answer("How strong am I?"))

    def test_advisor_estimates_named_character_from_campaign_and_canon(self):
        class RecordingAI:
            def __init__(self):
                self.calls = []

            def request(self, rules, payload, max_output_tokens=0):
                self.calls.append((rules, payload))
                return {"summary": "Konan is currently a high-level threat based on her recorded campaign feats.",
                        "points": ["Her recent defense of Amegakure is the strongest campaign evidence."],
                        "follow_ups": [], "chart": None}

        game = GameSession()
        game.settings.update(model="test", ai_connection_status="valid")
        game.state.update(world="Naruto", turn=9,
                          npc_memories={"Konan": {"goal": "Defend Amegakure", "attitude": "allied"}},
                          campaign_canon=[{"turn": 8, "action": "Konan defended Amegakure alone",
                                           "outcome": "She defeated an elite hunter squad."}])
        ai = RecordingAI()
        game.ai = ai
        result = game.ask_advisor("How strong is Konan now?")
        self.assertIn("high-level threat", result["entry"]["summary"])
        rules, payload = ai.calls[0]
        self.assertTrue(payload["named_character_power_question"])
        self.assertIn("ANY named character", rules)
        self.assertIn("missing numeric character sheet is not a reason to refuse", rules)
        self.assertIn("Konan", payload["state"]["npc_memories"])

    def test_advance_activates_and_clears_nine_tails_cloak_portrait(self):
        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Naruto", name="Cloak Tester", campaign_active=True,
                          campaign_id="cloak-test", appearance_desc="A dark-haired Leaf shinobi")
        host = build_jinchuriki_profile(
            "I am Kurama's developing jinchuriki and can use a controlled chakra cloak.", seed="cloak-test"
        )
        game.state["special"] = {"Jinchūriki Profile": host, "Jinchuriki": "Kurama — Developing"}
        game.campaign_active = True
        base_signature = portrait_signature(game.state)
        payload = {
            "narrative": "Kurama's chakra answers, surrounding the shinobi in a vivid Nine-Tails chakra cloak.",
            "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
            "elapsed": {"amount": 5, "unit": "minutes"}, "interrupted": False,
            "major_event_reached": False, "goal_status": {}, "new_contacts": [], "incoming_chats": [],
            "completed_actions": ["Activate my Nine-Tails cloak"], "deferred_actions": [], "suggested_actions": [],
        }
        active = game.apply_time_skip(payload, 1, "moment", {
            "actions": ["Activate my Nine-Tails cloak"], "rolls": [], "elapsed_minutes": 5, "intensity": "normal",
        })["state"]
        self.assertEqual(active["_portrait_active_form"]["kind"], "Jinchūriki transformation")
        self.assertIn("Cloak", active["_portrait_active_form"]["name"])
        self.assertNotEqual(active["_portrait_signature"], base_signature)
        expected_base = copy.deepcopy(game.state)
        expected_base["portrait_identity"]["active_form"] = {}
        expected_base_signature = portrait_signature(expected_base)

        payload["narrative"] = "The chakra cloak fades and the shinobi returns to normal."
        payload["completed_actions"] = ["Deactivate the cloak and return to normal"]
        inactive = game.apply_time_skip(payload, 1, "moment", {
            "actions": ["Deactivate the cloak and return to normal"], "rolls": [], "elapsed_minutes": 5, "intensity": "normal",
        })["state"]
        self.assertEqual(inactive["_portrait_active_form"], {})
        self.assertEqual(inactive["_portrait_signature"], expected_base_signature)


if __name__ == "__main__":
    unittest.main()
