import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app
from game import GameSession
from portrait_generator import clear_active_portrait_form
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3340PresentationTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_native_event_sheet_and_world_dice_ship(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for marker in ("event-window-player-location", "event-window-travel", "event-window-involvement", "ACKNOWLEDGE EVENT"):
            self.assertIn(marker, html)
        for theme in ("SHINOBI FATE", "SOUL VERDICT", "CURSED FATE", "GRAND LINE FATE", "SATISFY SYSTEM"):
            self.assertIn(theme, script)
        for world in ("Naruto", "One Piece", "Bleach", "Jujutsu Kaisen", "Overgeared", "Solo Max-Level Newbie"):
            self.assertIn(f'body[data-world="{world}"] .percentile-tray', css)

    def test_action_cards_and_transformation_panel_ship(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for marker in ("active-form-panel", "active-form-bonuses", "btn-end-transformation"):
            self.assertIn(marker, html)
        self.assertIn("function renderActiveFormPanel", script)
        self.assertIn("suggestion-card-own", script)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", css)

    def test_event_notice_uses_real_position_and_map_travel(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({"world": "Naruto", "name": "Kael", "location": "Konohagakure", "position": "Jonin", "canon_day": 50})
        notice = game._event_notice_payload(
            {"interrupted": True, "major_event_title": "Assault on Amegakure", "active_major_event": "Assault on Amegakure"},
            {"title": "Assault on Amegakure", "location": "Amegakure", "scope": "regional", "canon_day": 51},
        )
        self.assertEqual(notice["player_location"], "Konohagakure")
        self.assertEqual(notice["location"], "Amegakure")
        self.assertIn("ordinary route", notice["travel_time"])
        self.assertEqual(notice["canon_day"], 51)

    def test_return_to_base_form_clears_visual_state_and_route_ships(self):
        state = {"portrait_identity": {"active_form": {"name": "Nine-Tails Chakra Cloak", "kind": "Transformation"}}}
        self.assertTrue(clear_active_portrait_form(state))
        self.assertEqual(state["portrait_identity"]["active_form"], {})
        self.assertIn("/api/portrait/form/end", {rule.rule for rule in app.url_map.iter_rules()})


if __name__ == "__main__":
    unittest.main()
