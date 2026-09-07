import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from politics import normalize_political_state, political_regions_for_map
from systems import map_snapshot
from worlds import APP_VERSION, BASE_STATE, WORLD_DATA


class WorldwalkerV3320AtlasTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_strategy_atlas_uses_one_partition_and_controller_boundaries(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('data-map-render="strategic"', js)
        self.assertIn("mapHexPath", js)
        self.assertIn("neighborForEdge", js)
        self.assertIn("neighborForEdge(cell, edge)?.controller === cell.controller", js)
        self.assertIn("map-faction-label", css)
        self.assertIn("territory-chip i", css)

    def test_story_ownership_change_is_authoritative_for_atlas_shading(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Amegakure", turn=12,
                     political_regions=[{"id": "rain", "name": "Rain Country", "anchor": "Amegakure",
                                         "controller": "Amegakure", "size": 18}],
                     location_details={"Amegakure": {"controlling_faction": "New Rain Republic",
                                                       "controller_changed_turn": 12}})
        normalize_political_state(state)
        snapshot = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")
        rain_node = next(row for row in snapshot["nodes"] if row["name"] == "Amegakure")
        rain_region = next(row for row in snapshot["regions"] if row["id"] == "rain")
        self.assertEqual(rain_node["controller"], "New Rain Republic")
        self.assertEqual(rain_region["controller"], "New Rain Republic")
        self.assertTrue(rain_region["recently_changed"])
        self.assertEqual(rain_region["geometry"], "strategic")

    def test_neighboring_claims_can_merge_under_one_controller(self):
        state = {"turn": 2, "political_regions": [
            {"id": "west", "name": "West", "controller": "Union", "x": 35, "y": 50, "size": 14},
            {"id": "east", "name": "East", "controller": "Union", "x": 55, "y": 50, "size": 14},
        ]}
        regions = political_regions_for_map(state, [])
        self.assertEqual({row["controller"] for row in regions}, {"Union"})
        self.assertTrue(all(row["geometry"] == "strategic" for row in regions))

    def test_mobile_quick_time_controls_keep_action_queue(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for element_id in ("mobile-time-amount", "mobile-time-unit", "btn-mobile-time", "td-queued-summary"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("applyMobileTimeInputs", js)
        self.assertIn("will be kept</b>", js)
        self.assertIn('if (draft) await submitAction(draft);', js)
        self.assertIn("grid-template-columns:minmax(0,1fr) 50px", css)


if __name__ == "__main__":
    unittest.main()
