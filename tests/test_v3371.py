import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from worlds import APP_VERSION


class WorldwalkerV3371Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_bleach_uses_standard_chronicle_panels(self):
        app_js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('new Set(["Naruto", "One Piece"])', app_js)
        self.assertNotIn("hell-butterfly", app_js.lower())
        self.assertNotIn("hell-butterfly", css.lower())
        self.assertNotIn('data-presentation="butterflies"', css)
        self.assertFalse((ROOT / "assets" / "reference" / "bleach-hell-butterfly.webp").exists())


if __name__ == "__main__":
    unittest.main()
