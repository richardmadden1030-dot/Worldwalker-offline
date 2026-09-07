import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ability_archive import ability_fingerprint
from game import GameSession


class GeneratedAbilityArchiveTests(unittest.TestCase):
    def make_game(self, root):
        settings = Path(root) / "settings.json"
        settings.write_text(json.dumps({"provider": "local", "model": ""}), encoding="utf-8")
        return GameSession(save_dir=Path(root) / "saves", settings_path=settings)

    def test_every_original_special_is_archived_and_rerolls_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            game = self.make_game(td)
            first = game.generate_background_ability("Naruto", "I was born with a strange bloodline power.", 35)
            second = game.generate_background_ability("Naruto", "I was born with a strange bloodline power.", 35)
            self.assertNotEqual(first["name"].casefold(), second["name"].casefold())
            self.assertNotEqual(ability_fingerprint(first), ability_fingerprint(second))

            stats = {"Ninjutsu": 30, "Chakra Control": 30}
            class_one = game.generate_hidden_class("Naruto", "I have a hidden class.", 20, list(stats), stats)
            class_two = game.generate_hidden_class("Naruto", "I have a hidden class.", 20, list(stats), stats)
            self.assertNotEqual(class_one["name"].casefold(), class_two["name"].casefold())

            blade_one = game.generate_zanpakuto_profile("A protective Soul Reaper.")
            blade_two = game.generate_zanpakuto_profile("A protective Soul Reaper.", exclude_name=blade_one["name"])
            self.assertNotEqual(blade_one["name"].casefold(), blade_two["name"].casefold())

            slot_one = game.generate_jjk_birth_slot("A sorcerer with an innate technique.", seed="same")
            slot_two = game.generate_jjk_birth_slot("A sorcerer with an innate technique.", seed="same")
            self.assertNotEqual(slot_one["name"].casefold(), slot_two["name"].casefold())

            archive_path = Path(td) / "generated_abilities.json"
            payload = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["entries"]), 8)
            self.assertTrue(all(row["canon"] is False for row in payload["entries"]))
            self.assertTrue(all(row.get("fingerprint") for row in payload["entries"]))

            # A new process/session for the same account still excludes every
            # design recorded by the previous one.
            restarted = self.make_game(td)
            third = restarted.generate_background_ability("Naruto", "I was born with a strange bloodline power.", 35)
            self.assertNotIn(third["name"].casefold(), {first["name"].casefold(), second["name"].casefold()})


if __name__ == "__main__":
    unittest.main()
