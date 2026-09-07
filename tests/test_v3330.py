import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from worlds import APP_VERSION


class WorldwalkerV3330VisualFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_visual_layers_are_present(self):
        for element_id in ("world-atmosphere", "world-lighting", "portrait-form-fx", "scene-lighting", "music-visualizer"):
            self.assertIn(f'id="{element_id}"', self.html)

    def test_every_shipped_world_has_a_local_ambient_profile(self):
        for world in ("Naruto", "One Piece", "Hunter x Hunter", "Bleach", "Jujutsu Kaisen",
                      "Overgeared", "Solo Max-Level Newbie", "Reincarnated as a Slime", "Custom World"):
            self.assertIn(f'"{world}":', self.js)
        for effect in ("sakura", "sea-spray", "nen", "reishi", "cursed", "forge", "tower", "magicules"):
            self.assertIn(f'data-effect="{effect}"', self.css)

    def test_major_forms_and_narrative_events_have_nonblocking_feedback(self):
        self.assertIn("triggerAbilityEffect", self.js)
        self.assertIn("narrativeAbilityEffect", self.js)
        for effect in ("bankai", "shikai", "domain", "bijuu", "dojutsu", "system", "evolution"):
            self.assertIn(f"ability-{effect}", self.css)
        self.assertIn("pointer-events:none", self.css)

    def test_map_and_progress_feedback_are_local(self):
        self.assertIn("paintMapRoutes", self.js)
        self.assertIn("map-route-canvas", self.js)
        self.assertIn("map-event-marker", self.js)
        self.assertIn("animateStateChanges", self.js)
        self.assertIn("playTimeAdvanceEffect", self.js)

    def test_accessibility_and_performance_controls_cover_new_effects(self):
        self.assertIn("prefers-reduced-motion:reduce", self.css)
        self.assertIn("body.mobile-low-data .ambient-fx", self.css)
        self.assertIn("body.app-backgrounded", self.css)
        self.assertIn(".motion-off .ambient-fx", self.css)


if __name__ == "__main__":
    unittest.main()
