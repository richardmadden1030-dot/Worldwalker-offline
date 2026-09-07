import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app, _cache_control_for
from worlds import APP_VERSION


class WorldwalkerV3332PhoneRecoveryTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_game_data_is_never_cached(self):
        self.assertTrue(_cache_control_for("/api/state").startswith("no-store"))
        self.assertTrue(_cache_control_for("/api/auth/session").startswith("no-store"))

    def test_versioned_shell_files_are_immutable(self):
        expected = "public, max-age=31536000, immutable"
        self.assertEqual(_cache_control_for("/css/style.css", APP_VERSION), expected)
        self.assertEqual(_cache_control_for("/js/app.js", APP_VERSION), expected)
        self.assertIn("stale-if-error", _cache_control_for("/assets/generated_scenes/town_square.webp"))

    def test_routes_emit_the_expected_cache_headers(self):
        client = app.test_client()
        with client.get(f"/css/style.css?v={APP_VERSION}") as response:
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
        with client.get("/api/version") as response:
            self.assertTrue(response.headers["Cache-Control"].startswith("no-store"))
        with client.get("/") as response:
            self.assertIn("stale-if-error", response.headers["Cache-Control"])

    def test_recovery_shell_and_real_host_probe_ship(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        for marker in ("asset-recovery", "assets-missing", "host-unreachable", "worldwalkerRetry"):
            self.assertIn(marker, html + js)
        for marker in ("probeGameServer", "connection_check", "pageshow", "setInterval(updateNetwork, 15000)"):
            self.assertIn(marker, js)
        self.assertIn(f"style.css?v={APP_VERSION}", worker)
        self.assertIn(f"app.js?v={APP_VERSION}", worker)


if __name__ == "__main__":
    unittest.main()
