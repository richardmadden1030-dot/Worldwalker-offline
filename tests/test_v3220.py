import copy
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from jjk_system import (GRADE_BASELINES, apply_birth_slot, feeding_growth_for_target,
                        generate_birth_slot, generate_curse_identity)
from world_progression import normalize_world_progression
from worlds import (APP_VERSION, BASE_STATE, WORLD_DATA, abilities_for,
                    expansion_for, playable_characters_for, starting_eras_for)


class WorldwalkerV3220JujutsuKaisenTests(unittest.TestCase):
    def test_release_world_and_complete_start_matrix(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        self.assertIn("Jujutsu Kaisen", WORLD_DATA)
        self.assertEqual(len(abilities_for("Jujutsu Kaisen")), 7)
        expansion = expansion_for("Jujutsu Kaisen")
        self.assertEqual(expansion["archetypes"], [])
        self.assertEqual(expansion["origins"], [
            "Tokyo Jujutsu High — First Year", "Tokyo Jujutsu High — Second Year", "Tokyo Jujutsu High — Third Year",
            "Kyoto Jujutsu High — First Year", "Kyoto Jujutsu High — Second Year", "Kyoto Jujutsu High — Third Year",
            "Independent Curse User", "Great Clan Member", "Sentient Cursed Spirit",
        ])
        self.assertEqual({row["name"] for row in playable_characters_for("Jujutsu Kaisen")},
                         {"Yuji Itadori", "Satoru Gojo", "Yuta Okkotsu", "Megumi Fushiguro", "Maki Zenin"})
        self.assertEqual(len(starting_eras_for("Jujutsu Kaisen")), 4)

    def test_birth_slot_is_exclusive_and_strong_toggle_is_material(self):
        slot = generate_birth_slot("A quiet prodigy who manipulates shadows.", True, "strong-test")
        self.assertEqual(slot["slot_type"], "Innate Cursed Technique")
        self.assertTrue(slot["overwhelming"])
        self.assertEqual(slot["power_grade"], "Overwhelming")
        profile = apply_birth_slot({"stats": {name: 20 for name in abilities_for("Jujutsu Kaisen")}, "skills": {}}, slot)
        self.assertTrue(profile["skills"])
        self.assertTrue(all(row["parent_technique"] == slot["name"] for row in profile["skills"].values()))

        restriction = generate_birth_slot("I was born with zero cursed energy and a complete Heavenly Restriction.", False, "hr-test")
        self.assertEqual(restriction["slot_type"], "Heavenly Restriction")
        staged = apply_birth_slot({"stats": {name: 30 for name in abilities_for("Jujutsu Kaisen")}, "skills": {}}, restriction)
        self.assertEqual(staged["stats"]["Cursed Energy Reserves"], 1)
        self.assertEqual(staged["stats"]["Cursed Energy Output"], 1)
        self.assertFalse(staged["skills"])

    def test_curse_identity_grade_and_exponential_feeding(self):
        identity = generate_curse_identity("A self-aware curse with no stated origin.", "identity-test")
        self.assertTrue(identity["source"])
        self.assertTrue(identity["manifestation"])
        slot = generate_birth_slot("A self-aware cursed spirit.", False, "curse-test", force_kind="innate_technique")
        staged = apply_birth_slot({"stats": {name: 10 for name in abilities_for("Jujutsu Kaisen")}, "skills": {}}, slot, "Grade 1")
        self.assertGreaterEqual(staged["stats"]["Physical Ability"], GRADE_BASELINES["Grade 1"])
        values = [feeding_growth_for_target(x) for x in ("ordinary human", "grade 3", "grade 2", "grade 1", "special grade")]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[-2] * 2)

    def test_curse_preview_has_no_invented_human_childhood_or_uniform(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Jujutsu Kaisen")}
        preview = game.preview_campaign(
            "Kuroha", "Jujutsu Kaisen", "Adventurer",
            "A self-aware curse born from the fear of abandonment, with a powerful spatial cursed technique.", "", "",
            "Sentient Cursed Spirit", "Jujutsu Sorcerer", stats, start_location="Tokyo",
            starting_era_id="week_before_yuji", jjk_guarantee_strong=True, jjk_curse_grade="Special Grade",
        )
        profile = preview["starting_profile"]
        self.assertNotRegex(profile["expanded_background"].lower(), r"home life|retired local|childhood mentor")
        self.assertEqual(profile["equipment"], {"Natural Weapon": "Manifested cursed body"})
        self.assertEqual(profile["jjk_curse_identity"]["source"].lower(), "the fear of abandonment")
        slot = profile["jjk_birth_slot"]
        self.assertTrue(slot["name"])
        self.assertRegex(
            f"{slot.get('governing_rule', '')} {slot.get('limitations', '')}".lower(),
            r"space|distance|boundary|interval|position|separation",
        )
        self.assertGreaterEqual(profile["stats"]["Cursed Energy Reserves"], GRADE_BASELINES["Special Grade"])

    def test_preview_and_campaign_preserve_generated_birth_slot(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Jujutsu Kaisen")}
        preview = game.preview_campaign(
            "Aya", "Jujutsu Kaisen", "Adventurer", "A talented barrier student.", "", "",
            "Tokyo Jujutsu High — First Year", "Jujutsu Sorcerer", stats,
            start_location="Tokyo Jujutsu High", starting_era_id="week_before_yuji", jjk_guarantee_strong=True,
        )
        slot = preview["starting_profile"]["jjk_birth_slot"]
        self.assertIn(slot["slot_type"], {"Innate Cursed Technique", "Heavenly Restriction"})
        game.new_campaign(
            "Aya", "Jujutsu Kaisen", "Adventurer", "A talented barrier student.", "", "",
            "Tokyo Jujutsu High — First Year", "Jujutsu Sorcerer", stats,
            start_location="Tokyo Jujutsu High", starting_era_id="week_before_yuji",
            preview_stats=preview["abilities"], preview_profile=preview["starting_profile"], jjk_guarantee_strong=True,
        )
        self.assertEqual(game.state["jjk_system"]["birth_slot"]["name"], slot["name"])
        self.assertEqual(game.state["special"]["Birth Slot"], slot["slot_type"])

    def test_all_canon_starts_have_a_structured_power_record_and_opening_goal(self):
        game = GameSession()
        for scenario in playable_characters_for("Jujutsu Kaisen"):
            state = game.new_campaign(
                "", "Jujutsu Kaisen", "Adventurer", "", "", "", scenario["origin"], scenario["archetype"], {},
                canon_character_id=scenario["id"],
            )
            self.assertTrue(state["jjk_system"]["birth_slot"], scenario["name"])
            self.assertTrue(state["quests"], scenario["name"])
            self.assertEqual(state["special"]["Grade"], scenario["special_patch"]["Grade"])

    def test_black_flash_and_visual_package_are_wired(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Jujutsu Kaisen", special={}, stats={name: 20 for name in abilities_for("Jujutsu Kaisen")})
        notes = game.apply_jjk_turn_effects(copy.deepcopy(game.state), ["Strike the curse with cursed energy timed for Black Flash"], "A Black Flash lands.", [{"message": "BLACK FLASH erupts."}])
        self.assertEqual(game.state["jjk_system"]["black_flash_count"], 1)
        self.assertIn("BLACK FLASH RECORDED", notes[0])
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("triggerBlackFlash", js)
        self.assertIn("black-flash-fx", css)
        for asset in (
            ROOT / "assets" / "generated_scenes" / "jjk_tokyo_high.webp",
            ROOT / "assets" / "generated_scenes" / "jjk_kyoto_high.webp",
            ROOT / "assets" / "generated_scenes" / "jjk_shibuya_night.webp",
            ROOT / "assets" / "generated_maps" / "Jujutsu_Kaisen.webp",
        ):
            self.assertTrue(asset.exists(), asset)
            self.assertLess(asset.stat().st_size, 500_000)

    def test_bleach_achieved_release_recovers_name_from_skill(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Bleach", special={
            "Zanpakuto": "Unnamed Asauchi",
            "Zanpakuto Profile": {"name": "Unknown", "stage": "Bankai"},
            "Shikai": "Achieved", "Bankai": "Achieved",
        }, skills={
            "Shikai — Kagehibiki": {"rank": "Shikai", "release_stage": "Shikai", "description": "Echoes through shadow."},
            "Bankai: Kagehibiki Mugenrō": {"rank": "Bankai", "release_stage": "Bankai"},
        }, equipment={"Weapon": "Unnamed Asauchi"})
        repairs = normalize_world_progression(state)
        self.assertEqual(state["special"]["Zanpakuto"], "Kagehibiki")
        self.assertEqual(state["special"]["Zanpakuto Profile"]["name"], "Kagehibiki")
        self.assertEqual(state["equipment"]["Weapon"], "Kagehibiki")
        self.assertTrue(any("Recovered" in row for row in repairs))


if __name__ == "__main__":
    unittest.main()
