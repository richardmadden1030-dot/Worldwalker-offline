import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from worlds import APP_VERSION


class WorldwalkerV3161Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_optimized_naruto_cues_are_packaged_and_small(self):
        limits = {
            "naruto_advance.mp3": 20_000,
            "naruto_character_start.mp3": 25_000,
            "naruto_pain_start.mp3": 160_000,
            "naruto_death.mp3": 220_000,
        }
        for filename, limit in limits.items():
            path = ROOT / "assets" / "sounds" / filename
            self.assertTrue(path.is_file(), filename)
            self.assertGreater(path.stat().st_size, 1_000, filename)
            self.assertLess(path.stat().st_size, limit, filename)

    def test_audio_elements_and_world_cue_router_are_present(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for cue in ("naruto_advance", "naruto_character_start", "naruto_pain_start", "naruto_death"):
            self.assertIn(f'id="snd-{cue}"', html)
        self.assertIn('APP.state?.world === "Naruto"', js)
        self.assertIn('canon_character_id === "pain_birth"', js)
        self.assertIn("playCampaignStartCue(APP.pendingCampaign)", js)
        self.assertIn('playWorldCue("naruto_character_start")', js)
        self.assertIn('"pain\'s assault on konoha"', js)
        self.assertIn('playWorldCue("naruto_death")', js)

    def test_audio_assets_are_served_by_the_real_app(self):
        from app import app as flask_app
        client = flask_app.test_client()
        for filename in ("naruto_advance.mp3", "naruto_character_start.mp3", "naruto_pain_start.mp3", "naruto_death.mp3"):
            response = client.get(f"/assets/sounds/{filename}")
            try:
                self.assertEqual(response.status_code, 200, filename)
                self.assertEqual(response.mimetype, "audio/mpeg", filename)
                self.assertGreater(len(response.data), 1_000, filename)
            finally:
                response.close()


if __name__ == "__main__":
    unittest.main()
