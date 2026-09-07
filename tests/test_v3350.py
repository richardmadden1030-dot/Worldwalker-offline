import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3350CanonCinematicTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_every_canon_notice_gets_cached_scene_art(self):
        for world, location in (
            ("Naruto", "Konohagakure"),
            ("One Piece", "Foosha Village"),
            ("Bleach", "Karakura Town"),
            ("Jujutsu Kaisen", "Tokyo Jujutsu High"),
            ("Overgeared", "Winston"),
            ("Solo Max-Level Newbie", "Tower Entrance"),
            ("Reincarnated as a Slime", "Tempest"),
            ("Hunter x Hunter", "Whale Island"),
        ):
            game = GameSession()
            game.state = copy.deepcopy(BASE_STATE)
            game.state.update({"world": world, "location": location, "canon_day": 10, "active_canon_event": "A Canon Turning Point"})
            notice = game._event_notice_payload(
                {"interrupted": True, "major_event_title": "A Canon Turning Point", "active_major_event": "A Canon Turning Point"},
                {"title": "A Canon Turning Point", "location": location, "scope": "regional", "canon_day": 10},
            )
            self.assertTrue(notice["scene_image"], world)
            self.assertIn("/assets/", notice["scene_image"], world)

    def test_full_screen_cinematic_and_replay_ship(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for marker in ("event-cinematic-stage", "event-window-particles", "btn-event-window-replay"):
            self.assertIn(marker, html)
        for marker in ("restartCanonCinematic", "canon-cinematic", "THE TIMELINE HAS REACHED THIS MOMENT"):
            self.assertIn(marker, script)
        for world_slug in ("naruto", "one-piece", "bleach", "jujutsu-kaisen", "overgeared", "solo-max-level-newbie"):
            self.assertIn(f'data-event-world="{world_slug}"', css)
        self.assertIn("prefers-reduced-motion:reduce", css)


if __name__ == "__main__":
    unittest.main()
