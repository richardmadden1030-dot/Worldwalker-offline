import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from systems import map_snapshot
from worlds import BASE_STATE, WORLD_DATA


class MapWorkspaceTests(unittest.TestCase):
    def test_every_map_is_zoom_ready(self):
        from PIL import Image

        for path in (ROOT / "assets" / "generated_maps").glob("*.webp"):
            with self.subTest(path=path.name), Image.open(path) as image:
                self.assertGreaterEqual(image.width, 3840)
                self.assertGreaterEqual(image.height, 2160)

    def test_naruto_canon_polities_use_stable_country_geometry(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Konohagakure")
        regions = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")["regions"]
        by_name = {row["name"]: row for row in regions}
        for name in ("Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure", "Iwagakure", "Amegakure", "Iron Country"):
            self.assertEqual(by_name[name]["geometry"], "canon")
            self.assertGreaterEqual(len(by_name[name]["polygon"]), 4)

    def test_naruto_major_and_minor_canon_places_are_plotted(self):
        names = {row[0] for row in WORLD_DATA["Naruto"]["map"]}
        for name in ("Kusagakure", "Takigakure", "Yugakure", "Otogakure", "Uzushiogakure Ruins", "Five Kage Summit"):
            self.assertIn(name, names)

    def test_approved_living_map_is_the_main_layout_not_a_separate_screen(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('id="living-map-main"', html)
        self.assertIn('class="panel scene-card location-scene-card"', html)
        self.assertLess(html.index('id="living-map-main"'), html.index('class="panel story-card'))
        self.assertGreater(html.index('location-scene-card'), html.index('class="col col-right"'))
        self.assertNotIn('living-map-shell', html)
        self.assertNotIn('/living-map/index.html', html)
        self.assertIn('renderMainLivingMap(data)', js)
        self.assertIn('if (data.world !== activeWorld)', js)
        self.assertIn('data-mobile-view="map" aria-selected="false"><span>⌖</span>Map', html)
        self.assertIn('body[data-mobile-view="map"] .col-center', css)

    def test_main_map_uses_only_active_world_payload_and_supports_semantic_zoom(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('const mapPayload = data.map_data || {}', js)
        self.assertIn('const mapImage = selectedBoard?.image || data.map_image', js)
        self.assertIn('shell.dataset.mapWorld = world', js)
        self.assertIn('mapView.scale >= 2.2 ? "local"', js)
        self.assertNotIn('naruto_location_registry', js)

    def test_each_world_map_snapshot_contains_only_that_worlds_landmarks(self):
        snapshots = {}
        for world, data in WORLD_DATA.items():
            if world == "Custom World":
                continue
            state = copy.deepcopy(BASE_STATE)
            state.update(world=world, location=data["map"][0][0])
            snapshots[world] = {
                row["name"] for row in map_snapshot(state, data["map"], world)["nodes"]
            }

        self.assertIn("Konohagakure", snapshots["Naruto"])
        for world, names in snapshots.items():
            if world != "Naruto":
                self.assertNotIn("Konohagakure", names, world)

        self.assertIn("Foosha Village", snapshots["One Piece"])
        for world, names in snapshots.items():
            if world != "One Piece":
                self.assertNotIn("Foosha Village", names, world)

    def test_living_map_preserves_tracking_and_world_layer_rules(self):
        js = (ROOT / "frontend" / "living-map" / "js" / "prototype.js").read_text(encoding="utf-8")
        adapter = (ROOT / "frontend" / "living-map" / "js" / "adapter.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "living-map" / "css" / "prototype.css").read_text(encoding="utf-8")
        self.assertIn('Math.abs(Number(r.score) || 0) >= 20', adapter)
        self.assertIn('r.companion || r.mentor || r.nemesis', adapter)
        self.assertIn('const TH = { regional: 2.0, local: 4.0 }', js)
        self.assertIn('if (updateBand()) rebuildMarkers()', js)
        self.assertIn('data-mode="relationships"', (ROOT / "frontend" / "living-map" / "index.html").read_text(encoding="utf-8"))
        self.assertIn('.marker.is-moving', css)


if __name__ == "__main__":
    unittest.main()
