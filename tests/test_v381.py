import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, WORLD_DATA, abilities_for, playable_characters_for, start_options_for


class WorldwalkerV381Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_pain_birth_is_a_complete_canon_start(self):
        scenario = next(row for row in playable_characters_for("Naruto") if row["id"] == "pain_birth")
        game = GameSession()
        stats = {name: 12 for name in abilities_for("Naruto")}
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Pain", "Naruto", "Adventurer", "", "", "",
                scenario["origin"], scenario["archetype"], stats,
                canon_character_id="pain_birth",
            )

        state = game.state
        self.assertEqual(state["name"], "Pain")
        self.assertEqual(state["canon_day"], -4855)
        self.assertEqual(state["special"]["True Identity"], "Nagato")
        self.assertEqual(state["special"]["Public Body"], "Yahiko — nascent Deva Path")
        self.assertGreaterEqual(state["stats"]["Ninjutsu"], 170)
        self.assertIn("Rinnegan — Six Paths Techniques", state["skills"])
        self.assertIn("Deva Path — Yahiko", state["skills"])
        self.assertIn("Demonic Statue of the Outer Path", state["skills"])
        self.assertTrue(any(row["name"] == "Konan" for row in state["companions"]))
        self.assertEqual(state["npc_memories"]["Yahiko"]["last_known_location"], "Deceased")
        self.assertFalse(state["contacts"]["Yahiko"]["can_contact"])
        self.assertEqual(state["faction_rosters"]["Akatsuki"], ["Pain", "Konan"])
        self.assertEqual(state["quests"][0]["name"], "Decide What Pain Will Become")
        self.assertTrue(any("Only the Deva Path" in condition for condition in state["status"]))

    def test_one_piece_start_options_are_broad_and_all_mapped(self):
        options = start_options_for("One Piece")
        locations = {row["location"] for row in options}
        mapped = {row[0] for row in WORLD_DATA["One Piece"]["map"]}
        expected = {
            "Foosha Village", "Loguetown", "Alabasta", "Skypiea", "Water 7",
            "Sabaody", "Fishman Island", "Marineford", "Baltigo", "Kano Country",
            "Sorbet Kingdom", "Germa Kingdom", "Dressrosa", "Totto Land", "Zou",
            "Wano Country", "Egghead Island", "Mary Geoise",
        }
        self.assertGreaterEqual(len(options), 30)
        self.assertTrue(expected.issubset(locations))
        self.assertTrue(locations.issubset(mapped))
        self.assertTrue(all(row["note"] for row in options if row["location"] != "Foosha Village"))


if __name__ == "__main__":
    unittest.main()
