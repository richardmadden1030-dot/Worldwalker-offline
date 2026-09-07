import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, WORLD_EXPANSIONS, abilities_for, playable_characters_for, starting_eras_for, uses_xp_for


class WorldwalkerV380Tests(unittest.TestCase):
    def create(self, world, origin, archetype, location="", note="", era="", canon=""):
        game = GameSession()
        stats = {name: 12 for name in abilities_for(world)}
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign("Tester", world, "Adventurer", "A practical local background.", "", "",
                              origin, archetype, stats, start_location=location, start_note=note,
                              canon_character_id=canon, starting_era_id=era)
        return game

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_high_status_original_starts_are_mechanical(self):
        marine = self.create("One Piece", "Marine Recruit", "Marksman", "Shells Town", "Starting posted as a Marine recruit at Shells Town.")
        self.assertEqual(marine.state["position"], "Marine Recruit")
        self.assertEqual(marine.state["affiliations"][0]["faction"], "Marines")

        hunter = self.create("Hunter x Hunter", "Licensed Hunter", "Strategist", "Yorknew City")
        self.assertEqual(hunter.state["special"]["Hunter License"], "Active")
        self.assertEqual(hunter.state["affiliations"][0]["faction"], "Hunter Association")

        jonin = self.create("Naruto", "Jonin Squad Leader", "Sensor", "Konohagakure")
        self.assertEqual(jonin.state["special"]["Shinobi Rank"], "Jonin")
        self.assertEqual(jonin.state["position"], "Jonin Squad Leader")
        self.assertGreaterEqual(jonin.state["stats"]["Ninjutsu"], 48)

        craftsman = self.create("Overgeared", "Renowned Craftsman", "Blacksmith", "Winston")
        self.assertEqual(craftsman.state["special"]["Class"], "Beginner")
        self.assertEqual(craftsman.state["overgeared_system"]["class_reception"]["status"], "pending")
        self.assertGreaterEqual(craftsman.state["special"]["Crafting Mastery"], 65)

    def test_tempest_officer_default_is_moved_to_a_possible_era(self):
        game = GameSession()
        stats = {name: 12 for name in abilities_for("Reincarnated as a Slime")}
        preview = game.preview_campaign("Officer", "Reincarnated as a Slime", "Adventurer", "", "", "",
                                        "Veteran Tempest Officer", "Diplomat/Leader", stats,
                                        start_location="Great Jura Forest", starting_era_id="reincarnation")
        self.assertEqual(preview["start_day"], 100)
        self.assertEqual(preview["start_location"], "Tempest")
        self.assertTrue(preview["start_warnings"])

    def test_canon_presets_seed_signature_mechanics(self):
        cases = [
            ("One Piece", "luffy_departure", "Gum-Gum Fruit", "Gum-Gum Fruit (rubber body)"),
            ("One Piece", "zoro_shells", "Three-Sword Style", None),
            ("Hunter x Hunter", "gon_departure", "Exceptional Senses", None),
            ("Hunter x Hunter", "kurapika_exam", "Kurta Scarlet Eyes", None),
            ("Solo Max-Level Newbie", "jinhyeok_tower", "Tower Encyclopedia", None),
            ("Overgeared", "grid_pagma", "Legendary Blacksmithing", "Pagma's Descendant"),
            ("Reincarnated as a Slime", "rimuru_awakens", "Great Sage", "Slime"),
        ]
        for world, canon_id, skill, special_value in cases:
            scenario = next(row for row in playable_characters_for(world) if row["id"] == canon_id)
            game = self.create(world, scenario["origin"], scenario["archetype"], canon=canon_id)
            self.assertIn(skill, game.state["skills"], (world, canon_id))
            if canon_id == "luffy_departure":
                self.assertEqual(game.state["special"]["Devil Fruit"], special_value)
            elif canon_id == "grid_pagma":
                self.assertEqual(game.state["special"]["Class"], special_value)
                self.assertEqual(game.state["class_profile"]["name"], special_value)
                self.assertEqual(game.state["class_profile"]["kind"], "Successor Class")
                self.assertEqual(game.state["class_profile"]["rank"], "Legendary")
            elif canon_id == "rimuru_awakens":
                self.assertEqual(game.state["race"], special_value)
                self.assertEqual(game.state["location"], "Great Jura Forest — Sealed Cave")

    def test_early_canon_presets_do_not_grant_future_techniques_or_duplicate_stats(self):
        naruto = next(row for row in playable_characters_for("Naruto") if row["id"] == "naruto_graduation")
        game = self.create("Naruto", naruto["origin"], naruto["archetype"], canon="naruto_graduation")
        self.assertNotIn("Shadow Clone Technique", game.state["skills"])
        self.assertNotIn("Chakra Control", game.state["special"])
        facts = game.state["narrative_memory"]["established_facts"]
        self.assertTrue(any("not yet learned" in fact for fact in facts))

        gon = next(row for row in playable_characters_for("Hunter x Hunter") if row["id"] == "gon_departure")
        hunter = self.create("Hunter x Hunter", gon["origin"], gon["archetype"], canon="gon_departure")
        self.assertNotIn("Aura Control", hunter.state["special"])

    def test_secret_factions_are_known_but_not_directly_contactable(self):
        one_piece = self.create("One Piece", "Aspiring Pirate", "Brawler", "Foosha Village")
        self.assertFalse(one_piece.state["contacts"]["Big Mom Pirates"]["can_contact"])
        hunter = self.create("Hunter x Hunter", "Exam Aspirant", "Tracker", "Whale Island")
        self.assertFalse(hunter.state["contacts"]["Phantom Troupe"]["can_contact"])

    def test_new_eras_and_archetypes_are_exposed(self):
        self.assertIn("marineford_eve", {e["id"] for e in starting_eras_for("One Piece")})
        self.assertIn("chimera_ant_outbreak", {e["id"] for e in starting_eras_for("Hunter x Hunter")})
        self.assertIn("fourth_war_eve", {e["id"] for e in starting_eras_for("Naruto")})
        self.assertIn("Alchemist", WORLD_EXPANSIONS["Overgeared"]["archetypes"])

    def test_custom_world_can_explicitly_use_levels_and_xp(self):
        self.assertTrue(uses_xp_for("Custom World", "Heroes earn XP and level up through quests."))
        self.assertFalse(uses_xp_for("Custom World", "A political fantasy with reputation and learned techniques."))


if __name__ == "__main__":
    unittest.main()
