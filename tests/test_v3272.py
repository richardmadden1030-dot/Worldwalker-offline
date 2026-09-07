import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APPDATA", str(ROOT / "tests" / ".runtime"))
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from naruto_system import build_jinchuriki_profile
from world_progression import normalize_world_progression
from worlds import BASE_STATE, abilities_for


class WorldwalkerV3272JinchurikiTests(unittest.TestCase):
    def setUp(self):
        self.stats = {name: 30 for name in abilities_for("Naruto")}

    def test_original_host_gets_a_separate_complete_system(self):
        game = GameSession()
        profile = game.infer_starting_profile(
            "Naruto", "Academy Graduate", "Ninjutsu Student",
            "I am the unmastered jinchuriki of Kurama, the Nine-Tails.",
            self.stats, start_location="Konohagakure",
        )
        host = profile["jinchuriki_profile"]
        self.assertEqual(host["beast"], "Kurama")
        self.assertEqual(host["mastery"], "Unmastered")
        self.assertTrue(host["independent_beast"])
        self.assertIn("Tailed Beast Ball and derived variants after the necessary ratio and control are mastered", host["canonical_abilities"])
        self.assertTrue(any("seize control" in row for row in host["drawbacks"]))
        self.assertIn("Full tailed-beast transformation after genuine cooperation or overpowering control", host["locked_by_mastery"])
        self.assertIsNone(profile["generated_ability"])
        base_resource = game.derive_pools("Naruto", profile["stats"])[1]
        self.assertGreater(profile["resource_max"], base_resource)

    def test_perfect_host_has_full_access_but_keeps_real_limits(self):
        host = build_jinchuriki_profile("I am a perfect jinchuriki in full cooperation with Gyuki.")
        self.assertEqual(host["beast"], "Gyuki")
        self.assertEqual(host["mastery"], "Perfect Jinchuriki")
        self.assertIn("Full tailed-beast transformation", host["available_abilities"])
        self.assertIn("Tailed Beast Ball", host["available_abilities"])
        self.assertFalse(any("seize control" in row for row in host["drawbacks"]))
        self.assertTrue(any("extraction" in row.lower() for row in host["drawbacks"]))

    def test_canon_naruto_starts_have_correct_host_stage(self):
        game = GameSession()
        birth = game.preview_campaign(
            "", "Naruto", "Adventurer", "", "", "", "", "", self.stats,
            canon_character_id="naruto_birth",
        )["starting_profile"]["jinchuriki_profile"]
        graduation = game.preview_campaign(
            "", "Naruto", "Adventurer", "", "", "", "", "", self.stats,
            canon_character_id="naruto_graduation",
        )["starting_profile"]["jinchuriki_profile"]
        self.assertEqual(birth["mastery"], "Seal Pending")
        self.assertEqual(birth["available_abilities"], [])
        self.assertEqual(graduation["beast"], "Kurama")
        self.assertEqual(graduation["mastery"], "Unmastered")
        naruto_preview = game.preview_campaign(
            "", "Naruto", "Adventurer", "", "", "", "", "", self.stats,
            canon_character_id="naruto_graduation",
        )["starting_profile"]
        self.assertEqual(naruto_preview["naruto_affinity_profile"]["primary"], "Wind Release")
        self.assertEqual(naruto_preview["naruto_affinity_profile"]["discovery_status"], "Latent / not yet tested")

    def test_legacy_host_string_migrates_without_changing_current_pools(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "world": "Naruto", "campaign_id": "legacy-host", "background": "A Kumo shinobi.",
            "special": {"Jinchuriki": "Eight-Tails (identity concealed)", "Shinobi Rank": "Genin"},
            "resource": 123, "resource_max": 456,
        })
        normalize_world_progression(state)
        host = state["special"]["Jinchūriki Profile"]
        self.assertEqual(host["beast"], "Gyuki")
        self.assertEqual(state["special"]["Shinobi Profile"]["jinchuriki"]["beast"], "Gyuki")
        self.assertEqual((state["resource"], state["resource_max"]), (123, 456))

    def test_frontend_renders_dedicated_expandable_host_card(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('special["Jinchūriki Profile"]', source)
        self.assertIn("renderNarutoJinchurikiPanel", source)
        self.assertIn("JINCHŪRIKI", source)
        self.assertIn("Risks and drawbacks", source)
        self.assertIn("Abilities still locked", source)
        self.assertIn("chakra_reserve_bonus_percent", source)

    def test_started_campaign_persists_host_and_codex_entry(self):
        game = GameSession()
        profile = game.infer_starting_profile(
            "Naruto", "Academy Graduate", "Ninjutsu Student",
            "I am the developing jinchuriki of Matatabi and can use a controlled chakra cloak.",
            self.stats, start_location="Kumogakure",
        )
        game.new_campaign(
            "Rei", "Naruto", "Adventurer",
            "I am the developing jinchuriki of Matatabi and can use a controlled chakra cloak.",
            "", "", "Academy Graduate", "Ninjutsu Student", profile["stats"],
            start_location="Kumogakure", preview_stats=profile["stats"], preview_profile=profile,
        )
        host = game.state["special"]["Jinchūriki Profile"]
        self.assertEqual(host["beast"], "Matatabi")
        self.assertEqual(host["mastery"], "Developing")
        self.assertIn("Controlled tailed-beast chakra cloak", host["available_abilities"])
        self.assertEqual(game.state["special"]["Shinobi Profile"]["jinchuriki"]["beast"], "Matatabi")
        self.assertTrue(any(row.get("name") == "Matatabi" and row.get("type") == "Tailed Beast" for row in game.state["codex"]))

    def test_chakra_affinity_is_visible_and_changes_learning_rules(self):
        game = GameSession()
        profile = game.infer_starting_profile(
            "Naruto", "Academy Graduate", "Ninjutsu Student",
            "My natural chakra affinity is Wind Release, but I hope to learn Water Release later.",
            self.stats, start_location="Konohagakure",
        )
        affinity = profile["naruto_affinity_profile"]
        self.assertEqual(affinity["primary"], "Wind Release")
        self.assertNotIn("Water Release", affinity["secondary"])
        self.assertGreater(affinity["learning_rates"]["Wind Release"], affinity["learning_rates"]["Water Release"])
        self.assertIn("remain learnable", affinity["off_affinity_rule"])
        script = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('card("CHAKRA AFFINITY"', script)
        self.assertIn("Learning pace", script)

    def test_tailed_beast_natures_do_not_replace_host_affinity(self):
        game = GameSession()
        profile = game.infer_starting_profile(
            "Naruto", "Academy Graduate", "Ninjutsu Student",
            "I am Matatabi's jinchuriki and my own natural affinity is Water Release.",
            self.stats, start_location="Kumogakure",
        )
        game.new_campaign(
            "Mizu", "Naruto", "Adventurer",
            "I am Matatabi's jinchuriki and my own natural affinity is Water Release.",
            "", "", "Academy Graduate", "Ninjutsu Student", profile["stats"],
            start_location="Kumogakure", preview_stats=profile["stats"], preview_profile=profile,
        )
        affinity = game.state["special"]["Chakra Affinity Profile"]
        self.assertEqual(affinity["primary"], "Water Release")
        self.assertIn("Fire Release", affinity["external_natures"])

    def test_speed_advantage_pauses_for_a_player_chosen_bonus_turn(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Swift", "world": "Naruto", "difficulty": "Adventurer",
            "campaign_id": "speed-choice", "opening_complete": True,
            "hp": 200, "hp_max": 200, "resource": 200, "resource_max": 200,
            "stats": {"Taijutsu": 100, "Ninjutsu": 70, "Genjutsu": 30, "Chakra Control": 60, "Willpower": 55, "Intellect": 45},
            "combat": {"active": True, "round": 1, "log": [], "enemy": {
                "name": "Slower Rival", "hp": 500, "hp_max": 500, "power": 40,
                "difficulty_min": 30, "difficulty_max": 30, "attack_min": 30, "attack_max": 30, "alive": True,
            }},
        })
        game.campaign_active = True
        game.autosave = lambda: None
        passed = {"roll": 80, "total": 90, "difficulty": 30, "success": True, "margin": 60, "breakthrough": False}
        with patch.object(game, "_combat_check", side_effect=lambda *args: dict(passed)):
            first = game.resolve_combat_round("attack")
            self.assertTrue(first["awaiting_bonus_action"])
            self.assertTrue(first["combat"]["bonus_turn_pending"])
            self.assertEqual(first["combat"]["round"], 1)
            self.assertEqual(sum(row.get("actor") == "player" and row.get("action") == "attack" for row in first["log_tail"]), 1)
            self.assertFalse(any(row.get("actor") == "enemy" and row.get("action") == "attack" for row in first["log_tail"]))

            second = game.resolve_combat_round("defend")
        self.assertTrue(any(row.get("actor") == "player" and row.get("action") == "defend" for row in second["log_tail"]))
        self.assertTrue(any(row.get("actor") == "enemy" and row.get("action") == "attack" for row in second["log_tail"]))
        self.assertFalse(second["combat"].get("bonus_turn_pending"))
        self.assertEqual(second["combat"]["round"], 2)

    def test_speed_advantage_is_a_full_turn_even_after_defending_first(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Swift", "world": "Naruto", "difficulty": "Adventurer",
            "campaign_id": "speed-defense-choice", "opening_complete": True,
            "hp": 200, "hp_max": 200, "resource": 200, "resource_max": 200,
            "stats": {"Taijutsu": 100, "Ninjutsu": 70, "Genjutsu": 30, "Chakra Control": 60, "Willpower": 55, "Intellect": 45},
            "combat": {"active": True, "round": 1, "log": [], "enemy": {
                "name": "Slower Rival", "hp": 500, "hp_max": 500, "power": 40,
                "difficulty_min": 30, "difficulty_max": 30, "attack_min": 30, "attack_max": 30, "alive": True,
            }},
        })
        game.campaign_active = True
        game.autosave = lambda: None
        passed = {"roll": 80, "total": 90, "difficulty": 30, "success": True, "margin": 60, "breakthrough": False}
        with patch.object(game, "_combat_check", side_effect=lambda *args: dict(passed)):
            first = game.resolve_combat_round("defend")
            self.assertTrue(first["awaiting_bonus_action"])
            self.assertFalse(any(row.get("actor") == "enemy" for row in first["log_tail"]))
            second = game.resolve_combat_round("attack")
        self.assertTrue(any(row.get("actor") == "player" and row.get("action") == "attack" for row in second["log_tail"]))
        self.assertTrue(any(row.get("actor") == "enemy" and row.get("action") == "attack" for row in second["log_tail"]))
        self.assertEqual(second["combat"]["round"], 2)


if __name__ == "__main__":
    unittest.main()
