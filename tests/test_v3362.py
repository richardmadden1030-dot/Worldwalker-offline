import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ability_archive import GeneratedAbilityArchive, semantic_similarity
from game import GameSession
from worlds import APP_VERSION


class WorldwalkerV3362Tests(unittest.TestCase):
    def make_game(self, folder):
        game = GameSession(save_dir=Path(folder) / "saves", settings_path=Path(folder) / "settings.json")
        game.generated_ability_archive = GeneratedAbilityArchive(Path(folder) / "generated_abilities.json")
        return game

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_world_cursors_and_naruto_loading_shuriken_are_local_and_accessible(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        sw = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        for filename in ("naruto-kunai.svg", "naruto-shuriken.svg", "bleach-zanpakuto.svg", "jjk-sukuna-finger.svg"):
            asset = ROOT / "frontend" / "cursors" / filename
            self.assertTrue(asset.exists(), filename)
            self.assertLess(asset.stat().st_size, 8_000, filename)
            self.assertIn(f'/cursors/{filename}', css + sw)
        self.assertIn('document.body.classList.toggle("app-busy"', js)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn(".ai-pill.busy::before", css)

    def test_jjk_generic_rerolls_change_the_actual_governing_rule(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self.make_game(folder)
            slots = [game.generate_jjk_birth_slot("A sorcerer with an innate technique.", seed="reroll") for _ in range(18)]
            self.assertEqual(len({row["name"] for row in slots}), len(slots))
            self.assertTrue(all(" — " not in row["name"] for row in slots))
            for index, left in enumerate(slots):
                for right in slots[index + 1:]:
                    # The archive rejects 0.78+ before the setting compiler;
                    # normalized applications can add a few shared JJK words.
                    # They must still remain materially distinct on output.
                    self.assertLess(semantic_similarity(left, right), .82)

    def test_duplicate_fallback_changes_mechanics_in_every_original_power_family(self):
        fixtures = (
            ("Naruto", "starting_ability", {"name":"Seed", "details":{"effect":"Stores heat from blocked attacks."}}),
            ("Solo Max-Level Newbie", "starting_ability", {"name":"Seed", "details":{"effect":"Stores heat from blocked attacks."}}),
            ("Reincarnated as a Slime", "starting_ability", {"name":"Seed", "details":{"effect":"Stores heat from blocked attacks."}}),
            ("Overgeared", "hidden_class", {"name":"Seed", "true_name":"Seed", "effect":"Stores heat from blocked attacks.", "skill":{}}),
            ("Bleach", "zanpakuto", {"name":"Seed", "shikai_effect":"Stores heat from blocked attacks."}),
            ("Hunter x Hunter", "nen_ability", {"name":"Seed", "governing_rule":"Stores heat from blocked attacks."}),
            ("One Piece", "devil_fruit", {"name":"Seed Fruit", "type":"Paramecia", "abilities":["Stores heat from blocked attacks."]}),
            ("Jujutsu Kaisen", "birth_slot", {"name":"Seed", "slot_type":"Innate Cursed Technique", "governing_rule":"Stores heat from blocked attacks."}),
        )
        with tempfile.TemporaryDirectory() as folder:
            game = self.make_game(folder)
            for world, category, seed in fixtures:
                first = game._finalize_original_special(world, category, seed, source="test")
                second = game._finalize_original_special(world, category, seed, source="test")
                self.assertNotEqual(first.get("name"), second.get("name"), (world, category))
                self.assertLess(semantic_similarity(first, second), .78, (world, category))
                self.assertNotIn(" — ", str(second.get("name")), (world, category))


if __name__ == "__main__":
    unittest.main()
