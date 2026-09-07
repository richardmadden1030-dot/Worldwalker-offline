import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from worlds import APP_VERSION


EXPECTED_BLEACH_TRACKS = {
    "Clavar La Espada.mp3",
    "Escalon.mp3",
    "Everything I Lost - 2024 mix.mp3",
    "La Distancia Para Un Duelo.mp3",
    "Nube Negra.mp3",
    "Number One (Vocal Version).mp3",
    "Wandenreich Theme - Bleach TYBW Episode 1 & 2 OST (HQ Cover).mp3",
}

EXPECTED_NARUTO_TRACKS = {
    "Naruto OST - Gai Sensei Theme.mp3",
    "Naruto Shippuden - Girei (Pain's Theme Song).mp3",
    "Naruto Soundtrack - The Raising Fighting Spirit.mp3",
    "Sarutobi - Naruto OST 3.mp3",
}


class WorldwalkerV3162Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_all_default_bleach_tracks_are_bundled(self):
        folder = ROOT / "music" / "Bleach"
        tracks = {path.name for path in folder.glob("*.mp3")}
        self.assertEqual(tracks, EXPECTED_BLEACH_TRACKS)
        for filename in tracks:
            self.assertGreater((folder / filename).stat().st_size, 1_000_000, filename)

    def test_all_default_naruto_tracks_are_bundled(self):
        folder = ROOT / "music" / "Naruto"
        tracks = {path.name for path in folder.glob("*.mp3")}
        self.assertEqual(tracks, EXPECTED_NARUTO_TRACKS)
        for filename in tracks:
            self.assertGreater((folder / filename).stat().st_size, 1_000_000, filename)

    def test_music_api_exposes_the_bundled_bleach_playlist(self):
        from app import app as flask_app
        client = flask_app.test_client()
        response = client.get("/api/music?world=Bleach")
        try:
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            bleach_tracks = {row["filename"] for row in data["tracks"] if row["source"] == "Bleach"}
            self.assertEqual(bleach_tracks, EXPECTED_BLEACH_TRACKS)
        finally:
            response.close()

    def test_music_api_exposes_the_bundled_naruto_playlist(self):
        from app import app as flask_app
        client = flask_app.test_client()
        response = client.get("/api/music?world=Naruto")
        try:
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            naruto_tracks = {row["filename"] for row in data["tracks"] if row["source"] == "Naruto"}
            self.assertEqual(naruto_tracks, EXPECTED_NARUTO_TRACKS)
        finally:
            response.close()

    def test_pyinstaller_does_not_embed_a_duplicate_music_directory(self):
        spec = (ROOT / "WorldwalkerRPG.spec").read_text(encoding="utf-8")
        self.assertNotIn("('music', 'music')", spec)
        self.assertIn("Music is copied beside the finished EXE", spec)


if __name__ == "__main__":
    unittest.main()
