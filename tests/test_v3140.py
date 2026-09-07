import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from politics import PEOPLE_REPORT_INTERVAL_DAYS, tick_polity_governance
from state_guard import apply_guarded_patch
from systems import map_snapshot
from worlds import APP_VERSION, BASE_STATE, WORLD_DATA


class WorldwalkerV3140Tests(unittest.TestCase):
    def test_version_and_schema(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)

    def test_player_founded_land_becomes_a_first_class_faction_and_region(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Amegakure", canon_day=20)
        report = apply_guarded_patch(state, {
            "political_regions": [{
                "name": "Dawn Province", "controller": "Dawn Republic",
                "anchor": "Amegakure", "scale": "province",
            }],
            "polity_state": {"Dawn Republic": {
                "player_led": True, "people_relationship": "hopeful",
                "relationship_reason": "The founding charter protects local farms.",
            }},
            "affiliations": [{"faction": "Dawn Republic", "rank": "Founder", "status": "active"}],
        }, source="test")
        self.assertFalse(report["rejected"])
        self.assertIn("Dawn Republic", state["factions"])
        self.assertIn("Dawn Republic", state["faction_clocks"])
        self.assertEqual(state["political_regions"][0]["size"], 17)
        snapshot = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")
        claim = next(row for row in snapshot["regions"] if row["name"] == "Dawn Province")
        ame = next(row for row in snapshot["nodes"] if row["name"] == "Amegakure")
        self.assertEqual((claim["x"], claim["y"]), (ame["x"], ame["y"]))
        self.assertEqual(claim["controller"], "Dawn Republic")

    def test_canon_landowners_have_public_map_regions(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Konohagakure")
        snapshot = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")
        controllers = {row["controller"] for row in snapshot["regions"]}
        self.assertIn("Konohagakure", controllers)
        self.assertIn("Amegakure", controllers)
        self.assertTrue(all(4 <= row["size"] <= 42 for row in snapshot["regions"]))

    def test_ruler_gets_periodic_and_rapid_people_updates_as_one_line(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", canon_day=0,
                     affiliations=[{"faction": "Konohagakure", "rank": "Hokage", "status": "active"}],
                     polity_state={"Konohagakure": {
                         "player_led": True, "people_relationship": "guardedly supportive",
                         "relationship_reason": "food deliveries have become reliable",
                         "last_people_report_day": 0,
                         "reported_people_relationship": "guardedly supportive",
                         "pending_people_report": False,
                     }})
        self.assertFalse(tick_polity_governance(state, 1440, {"Konohagakure"}))
        state["canon_day"] = PEOPLE_REPORT_INTERVAL_DAYS
        events = tick_polity_governance(state, 1440, {"Konohagakure"})
        self.assertEqual(len(events), 1)
        self.assertNotIn("\n", events[0]["message"])
        before = copy.deepcopy(state)
        apply_guarded_patch(state, {"polity_state": {"Konohagakure": {
            **state["polity_state"]["Konohagakure"],
            "people_relationship": "openly angry",
            "relationship_reason": "a harsh levy disrupted winter stores",
        }}}, source="test")
        self.assertTrue(state["polity_state"]["Konohagakure"]["pending_people_report"])
        rapid = tick_polity_governance(state, 0, {"Konohagakure"})
        self.assertEqual(len(rapid), 1)
        self.assertIn("openly angry", rapid[0]["message"])
        self.assertNotEqual(before["polity_state"], state["polity_state"])

    def test_hidden_governance_bookkeeping_is_not_in_public_state(self):
        game = GameSession()
        game.state["polity_state"] = {"Test Realm": {"player_led": True}}
        self.assertNotIn("polity_state", game.public_state())

    def test_gm_rules_keep_governance_narrative_and_update_the_atlas(self):
        game = GameSession()
        rules = game.gm_rules()
        self.assertIn("player-founded landholding becomes a real polity", rules)
        self.assertIn("Do not turn government into a visible spreadsheet", rules)
        self.assertIn("political_regions", rules)

    def test_frontend_merges_same_owner_regions_at_the_border_layer(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("mapPayload.regions", js)
        self.assertIn("neighborForEdge", js)
        self.assertIn("neighborForEdge(cell, edge)?.controller === cell.controller", js)


if __name__ == "__main__":
    unittest.main()
