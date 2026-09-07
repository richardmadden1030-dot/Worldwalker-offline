import copy
import tempfile
import unittest
from pathlib import Path

from game import GameSession
from multiplayer_combat import resolve_multiplayer_combat_round
from world_progression import normalize_world_progression
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3360Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.game = GameSession(save_dir=root / "saves", settings_path=root / "settings.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_legacy_multiplayer_combat_shapes_cannot_lock_buttons(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="One Piece", combat={"active": True, "round": 1, "enemy": "Them", "log": "legacy"})
        participants = [
            {"user_id":"a", "username":"A", "character":{"name":"A", "hp":100, "hp_max":100,
             "special":"legacy", "status":"Weakened"}, "actions":["attack"]},
            {"user_id":"b", "username":"B", "character":{"name":"B", "hp":100, "hp_max":100}, "actions":["defend"]},
        ]
        result = resolve_multiplayer_combat_round(state, participants, 1)
        self.assertIsInstance(result["state"]["combat"]["enemy"], dict)
        self.assertIsInstance(result["state"]["combat"]["log"], list)
        self.assertEqual(set(result["characters"]), {"a", "b"})

    def test_nen_toggle_reveals_unique_hatsu_and_affinity(self):
        preview = self.game.preview_campaign(
            "Nia", "Hunter x Hunter", "Adventurer", "A patient strategist who binds promises.", "", "",
            "Hunter Aspirant", "Martial Artist", {}, hxh_start_with_nen=True,
        )
        nen = preview["starting_profile"]["nen_profile"]
        self.assertEqual(nen["visibility"], "Discovered")
        self.assertIn(nen["category"], nen["category_efficiency"])
        self.assertIn(nen["hatsu_profile"]["name"], preview["starting_profile"]["skills"])
        rerolled = self.game.reroll_campaign_preview(preview, "nen_ability", preview["background"])
        self.assertNotEqual(nen["hatsu_profile"]["name"], rerolled["starting_profile"]["nen_profile"]["hatsu_profile"]["name"])

    def test_locked_nen_is_concealed_then_reveals_same_latent_identity(self):
        preview = self.game.preview_campaign(
            "Mira", "Hunter x Hunter", "Adventurer", "An ordinary tracker.", "", "",
            "Hunter Aspirant", "Tracker", {}, hxh_start_with_nen=False,
        )
        latent_name = preview["starting_profile"]["nen_profile"]["latent_hatsu_profile"]["name"]
        self.game.new_campaign(
            "Mira", "Hunter x Hunter", "Adventurer", "An ordinary tracker.", "", "",
            "Hunter Aspirant", "Tracker", {}, preview_stats=preview["abilities"],
            preview_profile=preview["starting_profile"], hxh_start_with_nen=False,
        )
        self.assertNotIn("_latent_nen_profile", self.game.public_state())
        self.assertEqual(self.game.public_state()["special"]["Hatsu"], "Undiscovered")
        self.game.state["special"]["Nen Access"] = "Discovered"
        normalize_world_progression(self.game.state)
        self.assertEqual(self.game.state["special"]["Hatsu"], latent_name)
        self.assertIn(latent_name, self.game.state["skills"])

    def test_one_piece_creation_adds_selected_haki_and_never_repeats_fruit(self):
        preview = self.game.preview_campaign(
            "Vale", "One Piece", "Adventurer", "I ate a Logia fruit based on glass storms.", "", "",
            "Aspiring Pirate", "Brawler", {}, one_piece_devil_fruit=True,
            one_piece_haki_types=["Observation", "Armament"],
        )
        profile = preview["starting_profile"]
        fruit = profile["devil_fruit_profile"]
        self.assertEqual(fruit["type"], "Logia")
        self.assertIn("Glass Storms", fruit["name"])
        self.assertGreater(profile["haki_profile"]["Observation"]["mastery"], 0)
        self.assertEqual(profile["haki_profile"]["Conqueror"]["mastery"], 0)
        rerolled = self.game.reroll_campaign_preview(preview, "devil_fruit", preview["background"])
        self.assertNotEqual(fruit["name"], rerolled["starting_profile"]["devil_fruit_profile"]["name"])


if __name__ == "__main__":
    unittest.main()
