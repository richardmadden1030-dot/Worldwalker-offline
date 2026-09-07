import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from campaign_reliability import (
    build_grounding_packet,
    consolidate_long_campaign_memory,
    reconcile_narrated_consequences,
)
from game import GameSession
from simulation_integrity import campaign_search
from systems import tick_world_clocks
from worlds import APP_VERSION, BASE_STATE, WORLD_DATA, abilities_for


def state_for(world="Naruto"):
    state = copy.deepcopy(BASE_STATE)
    state.update({
        "world": world,
        "name": "Reliability Tester",
        "campaign_id": f"v3390-{world}",
        "opening_complete": True,
        "location": "Test District",
        "stats": {name: 30 for name in abilities_for(world)},
        "hp": 100,
        "hp_max": 100,
        "resource": 100,
        "resource_max": 100,
    })
    return state


class WorldwalkerV3390ReliabilityTests(unittest.TestCase):
    def test_version_and_schema(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)

    def test_grounding_packet_prioritizes_current_state_and_named_context(self):
        state = state_for()
        state.update({
            "turn": 42,
            "location": "Amegakure Tower",
            "affiliations": [{"faction": "Akatsuki", "rank": "Leader", "status": "active"}],
            "authoritative_corrections": [{"fact": "Konan remains co-leader", "turn": 40}],
            "npc_memories": {
                "Konan": {"recurring": True, "last_known_location": "Amegakure Tower", "goal": "Protect the village"},
                "Distant Merchant": {"last_known_location": "Fire Country"},
            },
            "faction_clocks": {"Akatsuki": {"goal": "Protect Amegakure", "status": "active"}},
            "campaign_canon": [{"turn": 41, "action": "Speak with Konan", "outcome": "Konan agreed to guard the tower."}],
        })
        packet = build_grounding_packet(state, "What did Konan agree to do and where are we?", "advisor")
        self.assertEqual(packet["current_truth"]["location"], "Amegakure Tower")
        self.assertEqual(packet["locked_facts"][0]["fact"], "Konan remains co-leader")
        self.assertEqual(packet["relevant_people"][0]["name"], "Konan")
        self.assertEqual(packet["relevant_factions"][0]["name"], "Akatsuki")
        self.assertTrue(any("guard the tower" in row["fact"] for row in packet["verified_history"]))

    def test_consequence_reconciliation_repairs_safe_omissions(self):
        state = state_for("One Piece")
        before = copy.deepcopy(state)
        data = {
            "narrative": "The crew claims the chart and begins the island investigation.",
            "consequence_manifest": [
                {"kind": "title", "target": "Storm Cartographer", "change": "gained", "evidence": "The harbor recognizes the feat."},
                {"kind": "item", "target": "Storm Route Chart", "change": "gained", "evidence": "The chart is handed over."},
                {"kind": "quest", "target": "The Drowned Beacon", "change": "started", "evidence": "The keeper asks for help."},
                {"kind": "location", "target": "Beacon Harbor", "change": "arrived", "evidence": "The crew docks."},
            ],
        }
        report = reconcile_narrated_consequences(before, state, data, ["Take the chart"], 60)
        self.assertEqual(report["repairs"], 4)
        self.assertIn("Storm Cartographer", state["titles"])
        self.assertTrue(any(row.get("name") == "Storm Route Chart" for row in state["inventory"]))
        self.assertTrue(any(row.get("name") == "The Drowned Beacon" for row in state["quests"]))
        self.assertEqual(state["location"], "Beacon Harbor")
        self.assertTrue(state["consequence_ledger"])

    def test_long_campaign_memory_is_deduplicated_archived_and_searchable(self):
        state = state_for("Bleach")
        state["turn"] = 120
        state["campaign_canon"] = [
            {"turn": turn, "canon_day": turn, "action": f"Patrol {turn}", "outcome": f"Resolved Hollow incident {turn}"}
            for turn in range(1, 111)
        ]
        state["narrative_memory"]["promises"] = [
            {"text": "Protect the western district", "turn": 20},
            {"text": "Protect the western district", "turn": 80},
        ]
        archive = consolidate_long_campaign_memory(state, force=True)
        self.assertTrue(archive["verified"])
        self.assertEqual(len(state["narrative_memory"]["promises"]), 1)
        self.assertLess(len(state["campaign_canon"]), 111)
        results = campaign_search(state, "Hollow incident 20")
        self.assertTrue(any(row["kind"] == "verified_archive" for row in results))

    def test_factions_have_goals_resources_operations_and_leadership_continuity(self):
        state = state_for("Naruto")
        state["factions"] = {"Rain Council": {}}
        state["npc_memories"] = {
            "Elder Sora": {"leads_faction": "Rain Council", "status": "dead"},
        }
        state["faction_clocks"] = {
            "Rain Council": {"name": "Rain Council", "kind": "faction", "goal": "Negotiate a river treaty", "progress": 0, "threshold": 100, "status": "active"},
        }
        events = tick_world_clocks(state, 7 * 1440)
        clock = state["faction_clocks"]["Rain Council"]
        self.assertEqual(clock["leadership"]["leader"], "Elder Sora")
        self.assertEqual(clock["leadership"]["status"], "succession pressure")
        self.assertTrue(clock["operations"])
        self.assertGreater(clock["operations"][0]["progress"], 0)
        self.assertEqual(clock["operations"][0]["type"], "diplomatic")
        self.assertEqual(set(clock["resources"]), {"capacity", "influence", "logistics", "intelligence"})
        self.assertTrue(any("leadership vacuum" in row.get("message", "") for row in events))

    def test_every_world_survives_three_deterministic_turns(self):
        for world in WORLD_DATA:
            with self.subTest(world=world):
                game = GameSession()
                game.autosave = lambda: None
                game.campaign_active = True
                game.state = state_for(world)
                for index in range(3):
                    action = f"Observe the surroundings on beat {index + 1}"
                    result = game.apply_resolution(
                        {
                            "narrative": f"{world} advances through test beat {index + 1}.",
                            "state_patch": {},
                            "events": [],
                            "suggested_actions": ["Continue observing"],
                        },
                        is_opening=False,
                        pending_action=action,
                        progression_context={"actions": [action], "rolls": [], "elapsed_minutes": 5},
                    )
                    self.assertFalse(result["died"])
                self.assertEqual(game.state["turn"], 3)
                self.assertEqual(len(game.state["resolution_ledger"]), 3)
                packet = build_grounding_packet(game.state, "What just happened?", "advisor")
                self.assertEqual(packet["current_truth"]["world"], world)

    def test_journal_more_only_contains_player_facing_history_tools(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        advanced = html.split('id="journal-tabs-advanced"', 1)[1].split("</div>", 1)[0]
        self.assertEqual(advanced.count("data-tab="), 3)
        for label in ("Progress", "Chapters", "NPC Knowledge"):
            self.assertIn(label, advanced)
        self.assertIn('data-tab="timeline">Canon Timeline', html.split('id="journal-tabs-advanced"')[0])
        for removed in ("Simulation Checks", "Campaign Health", "Model Evaluations", "Lore Sources", "Long-Term Memory"):
            self.assertNotIn(removed, advanced)


if __name__ == "__main__":
    unittest.main()
