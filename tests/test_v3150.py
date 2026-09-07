import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3150Tests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession()
        self.game.state = copy.deepcopy(BASE_STATE)

    def profile(self, wording, world="Naruto"):
        stats = {name: 30 for name in abilities_for(world)}
        return self.game.infer_starting_profile(
            world, "Original Character", "Ninjutsu Specialist", wording, stats,
            start_location="Konohagakure", allow_starting_specials=False,
        )

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_creation_wording_has_sharply_graduated_open_ended_power(self):
        ordinary = self.profile("I studied at the academy.")
        talented = self.profile("I am a talented shinobi.")
        prodigy = self.profile("I am a prodigy and stronger than others my age.")
        immense = self.profile("I possess immense chakra.")
        godlike = self.profile("My power is godlike.")
        immeasurable = self.profile("My skill and power are immeasurable.")
        peaks = [max(row["stats"].values()) for row in
                 (ordinary, talented, prodigy, immense, godlike, immeasurable)]
        self.assertEqual(peaks, sorted(peaks))
        self.assertEqual(len(set(peaks)), len(peaks))
        self.assertGreater(prodigy["growth_profile"]["learning_rate"], talented["growth_profile"]["learning_rate"])
        self.assertGreater(godlike["hp_max"], immense["hp_max"])
        self.assertGreater(immeasurable["resource_max"], godlike["resource_max"])
        self.assertGreater(max(immeasurable["stats"].values()), 1000)
        self.assertTrue(godlike["power_notice"])
        self.assertTrue(immeasurable["power_notice"])

    def test_immense_named_specialty_is_reflected_more_than_other_stats(self):
        profile = self.profile("My ninjutsu skill is immeasurable, beyond all measurement.")
        self.assertGreater(profile["stats"]["Ninjutsu"], profile["stats"]["Taijutsu"] + 500)
        self.assertGreater(profile["stats"]["Chakra Control"], profile["stats"]["Taijutsu"])
        reasons = profile["growth_profile"]["background_stat_reasons"]
        self.assertTrue(any("immeasurable" in reason for reason in reasons))

    def test_background_prompt_forbids_normalizing_extreme_starts_downward(self):
        self.game.state.update({"world": "Naruto", "difficulty": "Adventurer"})
        rules = self.game.task_rules("opening")
        self.assertIn("Never flatten an explicitly extreme start back toward average", rules)
        source = (ROOT / "backend" / "engine_campaign.py").read_text(encoding="utf-8")
        self.assertIn("Very powerful starts are allowed and must not be normalized downward", source)

    def test_combat_ui_exposes_debuffs_and_cannot_act_conditions(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("...(combat.player_debuffs || [])", source)
        self.assertIn('parts.push("cannot act")', source)
        self.assertIn("inflicted_status", source)


if __name__ == "__main__":
    unittest.main()
