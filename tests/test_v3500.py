import unittest
from pathlib import Path

from release_notes import notes_for
from worlds import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class PortraitIdentityUpdateTests(unittest.TestCase):
    def test_release_metadata(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(notes_for(APP_VERSION)["version"], APP_VERSION)

    def test_shared_portrait_surfaces_are_present(self):
        app = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for marker in (
            "personPortraitHtml",
            "mentionedPortraitsHtml",
            "location-people",
            "message-preview",
            "event-window-cast",
        ):
            self.assertIn(marker, app)

    def test_tactical_portraits_cover_turns_and_targets(self):
        html = (ROOT / "frontend" / "tactical" / "campaign.html").read_text(encoding="utf-8")
        script = (ROOT / "frontend" / "tactical" / "campaign.js").read_text(encoding="utf-8")
        self.assertIn('id="turn-order"', html)
        self.assertIn('class="turn-item', script)
        self.assertIn('class="roster-unit', script)
        self.assertIn("portrait(u)", script)


if __name__ == "__main__":
    unittest.main()
