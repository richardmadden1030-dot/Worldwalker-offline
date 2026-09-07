import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import abilities_for


class WorldwalkerV3211ZanpakutoPreviewTests(unittest.TestCase):
    def preview(self, background=""):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Bleach")}
        preview = game.preview_campaign(
            "Aoi", "Bleach", "Adventurer", background, "", "",
            "Recent Shin'o Academy Graduate", "Zanjutsu Specialist", stats,
            start_location="Seireitei", starting_era_id="week_before_arrival",
        )
        return game, preview

    def test_normal_soul_reaper_can_preview_and_reroll_dormant_release(self):
        game, preview = self.preview("A disciplined swordswoman who protects others and studies every defeat.")
        original = preview["starting_profile"]["bleach_release_profile"]
        self.assertEqual(original["stage"], "Dormant")
        self.assertFalse(any(
            isinstance(detail, dict) and detail.get("release_stage")
            for detail in preview["starting_profile"]["skills"].values()
        ))
        rerolled = game.reroll_campaign_preview(preview, "zanpakuto", "A disciplined swordswoman who protects others and studies every defeat.")
        replacement = rerolled["starting_profile"]["bleach_release_profile"]
        self.assertEqual(replacement["stage"], "Dormant")
        self.assertNotEqual(replacement["name"], original["name"])
        self.assertEqual(rerolled["abilities"], preview["abilities"])

    def test_dormant_preview_does_not_grant_shikai_when_campaign_starts(self):
        game, preview = self.preview("A quiet academy graduate with an affinity for echoes.")
        game.new_campaign(
            "Aoi", "Bleach", "Adventurer", "A quiet academy graduate with an affinity for echoes.", "", "",
            "Recent Shin'o Academy Graduate", "Zanjutsu Specialist", preview["abilities"],
            start_location="Seireitei", starting_era_id="week_before_arrival",
            preview_stats=preview["abilities"], preview_profile=preview["starting_profile"],
        )
        self.assertEqual(game.state["special"]["Shikai"], "Unachieved")
        self.assertEqual(game.state["special"]["Bankai"], "Unachieved")
        self.assertEqual(game.state["special"]["Zanpakuto Profile"]["stage"], "Dormant")

    def test_owned_shikai_reroll_replaces_release_skill_but_keeps_ownership(self):
        background = "I already possess and can use Shikai, shaped by my affinity for shadows."
        game, preview = self.preview(background)
        original = preview["starting_profile"]["bleach_release_profile"]
        old_skill = f"Shikai — {original['shikai_name']}"
        rerolled = game.reroll_campaign_preview(preview, "zanpakuto", background)
        replacement = rerolled["starting_profile"]["bleach_release_profile"]
        new_skill = f"Shikai — {replacement['shikai_name']}"
        self.assertEqual(replacement["stage"], "Shikai")
        self.assertNotEqual(replacement["name"], original["name"])
        self.assertNotIn(old_skill, rerolled["starting_profile"]["skills"])
        self.assertIn(new_skill, rerolled["starting_profile"]["skills"])

    def test_preview_ui_exposes_bleach_only_reroll_and_unearned_notice(self):
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-preview-reroll="zanpakuto"', script)
        self.assertIn("Zanpakutō abilities", script)
        self.assertIn("Previewed potential — this release is not yet achieved.", script)


if __name__ == "__main__":
    unittest.main()
