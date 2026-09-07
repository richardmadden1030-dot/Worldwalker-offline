import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import apply_guarded_patch
from worlds import (WORLD_DATA, WORLD_EXPANSIONS, abilities_for,
                    playable_characters_for, start_options_for, timeline_for)


class WorldwalkerV3100Tests(unittest.TestCase):
    MAP_COUNTS = {
        "One Piece": 38, "Hunter x Hunter": 16, "Naruto": 21,
        "Solo Max-Level Newbie": 51, "Overgeared": 16,
        "Reincarnated as a Slime": 16, "Bleach": 33,
    }
    TIMELINE_DAYS = {
        "One Piece": [-7799,-7331,-7180,-6450,-6112,-3530,-975,-123,0,2,5,10,11,13,14,17,17,18,20,31,36,45,47,52,59,67,68,68,82,733,734,735,736,748,758,760,763,774,792,797],
        "Hunter x Hunter": [0,1,3,4,5,7,8,9,12,13,15,17,18,24,26,30,35,40,41,55,70,85,100,170,180,190,230,270,330,365,430],
        "Naruto": [-22319,-19822,-16710,-9323,-6641,-5220,-4857,-4856,-4380,-4233,-3233,-1603,0,2,3,4,20,40,56,60,65,70,76,100,161,166,175,185,190,192,229,238,241,330,1069,1076,1337,1360,1361,1400,1409,1409,1410,1420,1684,1685,1686,1687,2064,2553,4413,6910],
        "Solo Max-Level Newbie": [0,1,1,2,3,5,7,10,14,20,25,30],
        "Overgeared": [-3,0,2,4,7,10,15,22,30,45,60,62,75,90],
        "Reincarnated as a Slime": [0,1,2,3,5,8,12,15,16,20,30,38,45,52,60,65,70,74,80,90,100,130,180,184,200],
        "Bleach": [-40150,-2190,-1460,0,20,40,60,61,71,74,88,175,185,205,214,226,238,252,278,795,850,930,935,950,970,990,1005],
    }

    def test_intentional_map_node_counts_and_unchanged_timeline_dates(self):
        for world, count in self.MAP_COUNTS.items():
            self.assertEqual(len(WORLD_DATA[world]["map"]), count, world)
            self.assertEqual([e["day"] for e in timeline_for(world)["events"]], self.TIMELINE_DAYS[world], world)

    def test_every_selectable_start_is_an_existing_map_node(self):
        for world in self.MAP_COUNTS:
            mapped = {row[0] for row in WORLD_DATA[world]["map"]}
            for option in start_options_for(world):
                self.assertIn(option["location"], mapped, f"{world}: {option['location']}")

    def test_existing_future_events_are_spoiler_safe_and_ordered(self):
        for world in self.MAP_COUNTS:
            previous = None
            for event in timeline_for(world)["events"]:
                if event.get("historical_only"):
                    continue
                self.assertTrue(event.get("spoiler"), f"{world}: {event['title']}")
                if previous:
                    self.assertTrue(event.get("requires"), f"{world}: {event['title']}")
                previous = event["title"]

    def test_all_ordinary_origins_get_mechanics_quest_and_world_profile(self):
        profile_keys = {
            "One Piece":"Haki Profile", "Hunter x Hunter":"Nen Profile", "Naruto":"Shinobi Profile",
            "Solo Max-Level Newbie":"System Profile", "Overgeared":"Satisfy Profile",
            "Reincarnated as a Slime":"Evolution Profile", "Bleach":"Zanpakuto Profile",
            "Jujutsu Kaisen":"Innate Technique Profile",
        }
        for world, ex in WORLD_EXPANSIONS.items():
            if world == "Custom World":
                continue
            for origin in ex["origins"]:
                game = GameSession()
                archetype = ex["archetypes"][0] if ex["archetypes"] else "Jujutsu Sorcerer"
                state = game.new_campaign("Tester", world, "Adventurer", "", "", "", origin, archetype, {})
                self.assertTrue(state["position"], f"{world}: {origin}")
                self.assertTrue(state["equipment"], f"{world}: {origin}")
                self.assertTrue(state["quests"], f"{world}: {origin}")
                if world == "Jujutsu Kaisen":
                    self.assertTrue(any(key in state["special"] for key in ("Innate Technique Profile", "Heavenly Restriction Profile")), f"{world}: {origin}")
                else:
                    self.assertIn(profile_keys[world], state["special"], f"{world}: {origin}")

    def test_canon_start_stats_are_complete_exact_and_deterministic(self):
        for world in self.MAP_COUNTS:
            for row in playable_characters_for(world):
                sheets = []
                for _ in range(2):
                    game = GameSession()
                    state = game.new_campaign("", world, "Adventurer", "", "", "", row["origin"], row["archetype"], {}, canon_character_id=row["id"])
                    sheets.append(state["stats"])
                    self.assertEqual(set(state["stats"]), set(abilities_for(world)))
                    self.assertTrue(state["quests"])
                self.assertEqual(sheets[0], sheets[1], row["id"])

    def test_structured_progression_and_legacy_fields_stay_synchronized(self):
        game = GameSession()
        state = game.new_campaign("Ninja", "Naruto", "Adventurer", "", "", "", "Academy Graduate", "Ninjutsu Student", {})
        apply_guarded_patch(state, {"special":{"Shinobi Profile":{**state["special"]["Shinobi Profile"], "rank":"Chunin"}}})
        self.assertEqual(state["special"]["Shinobi Rank"], "Chunin")
        game = GameSession()
        state = game.new_campaign("Crafter", "Overgeared", "Adventurer", "", "", "", "Crafter", "Blacksmith", {})
        apply_guarded_patch(state, {"special":{**state["special"], "Crafting Mastery":42}})
        self.assertEqual(state["special"]["Satisfy Profile"]["crafting_mastery"], 42)

    def test_creation_honors_explicit_refusal_of_random_specials(self):
        game = GameSession()
        state = game.new_campaign(
            "Aria", "Overgeared", "Adventurer",
            "A novice crafter without any hidden class and with no special ability.",
            "", "", "Crafter", "Blacksmith", {},
        )
        self.assertFalse(state["special"].get("Hidden Class"))
        self.assertFalse(state["special"].get("Starting Ability"))

    def test_frontend_has_world_system_cards_and_no_forced_level_in_party(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for world in ("One Piece","Hunter x Hunter","Naruto","Solo Max-Level Newbie","Overgeared","Reincarnated as a Slime"):
            self.assertIn(f'world === "{world}"', js)
        self.assertIn("renderWorldProgression", js)
        self.assertIn("s._uses_xp ? `Level", js)


if __name__ == "__main__":
    unittest.main()
