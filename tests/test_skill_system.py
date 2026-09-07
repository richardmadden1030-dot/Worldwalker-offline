import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from skill_system import infer_skill_metadata, normalize_skill_map
from worlds import BASE_STATE


class SkillSystemTests(unittest.TestCase):
    def fresh_combat(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Kael", "world": "Naruto", "difficulty": "Adventurer",
            "campaign_id": "skill-system-test", "opening_complete": True,
            "hp": 100, "hp_max": 100, "resource": 500, "resource_max": 500,
            "stats": {"Taijutsu": 50, "Ninjutsu": 50, "Genjutsu": 40,
                      "Chakra Control": 50, "Willpower": 45, "Intellect": 40},
            "combat": {"active": True, "round": 1, "log": [], "enemy": {
                "name": "Test Rival", "hp": 200, "hp_max": 200, "power": 40,
                "difficulty_min": 30, "difficulty_max": 30,
                "attack_min": 30, "attack_max": 30, "alive": True,
            }},
        })
        game.campaign_active = True
        game.autosave = lambda: None
        return game

    def test_inference_covers_non_damage_categories(self):
        cases = {
            "Flame Barrier": ("defense", "shield"),
            "Purifying Pulse": ("support", "cleanse"),
            "Shadow Bind": ("control", "control"),
            "Wolf Familiar Summoning": ("summon", "summon"),
            "Silent Concealment": ("stealth", "stealth"),
            "Flash Step": ("mobility", "movement"),
            "Bankai — Storm Crown": ("transformation", "transform"),
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                meta = infer_skill_metadata(name, {})
                self.assertEqual((meta["category"], meta["effect_type"]), expected)
                self.assertTrue(meta["combat_usable"])

    def test_legacy_utility_barrier_is_upgraded_but_profession_stays_out_of_combat(self):
        skills = normalize_skill_map({
            "Mirror Barrier": {"effect_type": "utility", "description": "Raises a shield that absorbs attacks."},
            "Navigator Fundamentals": {"description": "Charts routes and reads weather."},
        })
        self.assertEqual(skills["Mirror Barrier"]["effect_type"], "shield")
        self.assertFalse(skills["Navigator Fundamentals"]["combat_usable"])

    def test_barrier_absorbs_damage_instead_of_harming_enemy(self):
        game = self.fresh_combat()
        game.state["skills"] = {"Flame Barrier": {"bonus": 10, "combat_usable": True,
            "effect_type": "shield", "resource_type": "free", "mechanics": {"shield_pct": 30}}}
        with patch.object(game, "_combat_check", return_value={"roll": 90, "total": 100,
                "difficulty": 30, "success": True, "margin": 70, "breakthrough": False}):
            result = game.resolve_combat_round("attack", "Flame Barrier")
        self.assertEqual(result["combat"]["enemy"]["hp"], 200)
        shield_event = next(row for row in result["log_tail"] if row.get("action") == "shield")
        enemy_event = next(row for row in result["log_tail"] if row.get("actor") == "enemy")
        self.assertEqual(shield_event["shield"], 30)
        self.assertGreater(enemy_event["absorbed"], 0)

    def test_stun_prevents_retaliation_and_utility_never_becomes_damage(self):
        game = self.fresh_combat()
        game.state["skills"] = {
            "Lightning Paralysis": {"bonus": 10, "combat_usable": True, "effect_type": "control",
                                     "status_effect": "Paralyzed", "resource_type": "free"},
            "Tactical Hologram": {"bonus": 10, "combat_usable": True, "effect_type": "utility",
                                   "resource_type": "free"},
        }
        passed = {"roll": 90, "total": 100, "difficulty": 30, "success": True,
                  "margin": 70, "breakthrough": False}
        with patch.object(game, "_combat_check", return_value=passed):
            first = game.resolve_combat_round("attack", "Lightning Paralysis")
        self.assertTrue(any(row.get("action") == "controlled" for row in first["log_tail"]))
        enemy_hp = game.state["combat"]["enemy"]["hp"]
        with patch.object(game, "_combat_check", return_value=passed):
            game.resolve_combat_round("attack", "Tactical Hologram")
        self.assertEqual(game.state["combat"]["enemy"]["hp"], enemy_hp)

    def test_cleanse_removes_negative_player_status(self):
        game = self.fresh_combat()
        game.state["combat"]["player_statuses"] = [{"name": "Poisoned", "rounds_left": 3,
                                                       "damage_over_time_pct": 0}]
        game.state["skills"] = {"Purifying Pulse": {"bonus": 8, "combat_usable": True,
                                                     "effect_type": "cleanse", "resource_type": "free"}}
        passed = {"roll": 90, "total": 100, "difficulty": 25, "success": True,
                  "margin": 75, "breakthrough": False}
        with patch.object(game, "_combat_check", return_value=passed):
            result = game.resolve_combat_round("attack", "Purifying Pulse")
        self.assertEqual(result["combat"]["player_statuses"], [])
        event = next(row for row in result["log_tail"] if row.get("action") == "cleanse")
        self.assertIn("Poisoned", event["removed"])

    def test_semantic_paralysis_blocks_enemy_and_player_actions(self):
        game = self.fresh_combat()
        game.state["skills"] = {"Nerve Lock": {"bonus": 10, "combat_usable": True,
            "effect_type": "control", "status_effect": "Paralysis", "duration_rounds": 2,
            "resource_type": "free"}}
        passed = {"roll": 90, "total": 100, "difficulty": 30, "success": True,
                  "margin": 70, "breakthrough": False}
        with patch.object(game, "_combat_check", side_effect=lambda *args: dict(passed)):
            result = game.resolve_combat_round("attack", "Nerve Lock")
        self.assertFalse(any(row.get("actor") == "enemy" and row.get("action") == "attack"
                             for row in result["log_tail"]))
        self.assertTrue(any(row.get("actor") == "enemy" and row.get("action") == "controlled"
                            for row in result["log_tail"]))

        game2 = self.fresh_combat()
        game2.state["combat"]["player_statuses"] = [{"name": "Paralyzed", "rounds_left": 1}]
        with patch.object(game2, "_combat_check", side_effect=lambda *args: dict(passed)):
            result2 = game2.resolve_combat_round("attack")
        self.assertTrue(any(row.get("actor") == "player" and row.get("action") == "controlled"
                            for row in result2["log_tail"]))
        self.assertFalse(any(row.get("actor") == "player" and row.get("action") == "attack"
                             for row in result2["log_tail"]))
        self.assertTrue(any(row.get("actor") == "enemy" and row.get("action") == "attack"
                            for row in result2["log_tail"]))

    def test_weakening_reduces_enemy_accuracy_damage_and_visible_values(self):
        game = self.fresh_combat()
        game.state["skills"] = {"Withering Seal": {"bonus": 10, "combat_usable": True,
            "effect_type": "debuff", "status_effect": "Weakened", "status_potency": 40,
            "duration_rounds": 3, "resource_type": "free"}}
        passed = {"roll": 90, "total": 100, "difficulty": 30, "success": True,
                  "margin": 70, "breakthrough": False}
        with patch.object(game, "_combat_check", side_effect=lambda *args: dict(passed)):
            result = game.resolve_combat_round("attack", "Withering Seal")
        enemy_attack = next(row for row in result["log_tail"]
                            if row.get("actor") == "enemy" and row.get("action") == "attack")
        debuff = result["combat"]["enemy_debuffs"][0]
        self.assertGreater(enemy_attack["debuff_penalty"], 0)
        self.assertLess(enemy_attack["damage_multiplier"], 1)
        self.assertLess(debuff["power_pct"], 0)
        self.assertLess(debuff["defense_pct"], 0)
        self.assertLess(debuff["speed_pct"], 0)

    def test_enemy_on_hit_conditions_apply_without_permanent_control_refresh(self):
        game = self.fresh_combat()
        game.state["combat"]["enemy"]["attack_effect"] = {
            "type": "control", "name": "Paralyzed", "duration_rounds": 2,
        }
        passed = {"roll": 90, "total": 100, "difficulty": 30, "success": True,
                  "margin": 70, "breakthrough": False}
        with patch.object(game, "_combat_check", side_effect=lambda *args: dict(passed)):
            first = game.resolve_combat_round("defend")
            second = game.resolve_combat_round("attack")
        self.assertEqual(next(row for row in first["log_tail"] if row.get("actor") == "enemy")["inflicted_status"], "Paralyzed")
        self.assertTrue(any(row.get("actor") == "player" and row.get("action") == "controlled"
                            for row in second["log_tail"]))
        self.assertEqual(game.state["combat"]["player_statuses"], [])

        game2 = self.fresh_combat()
        game2.state["combat"]["enemy"]["attack_effect"] = {
            "type": "debuff", "name": "Crippled", "duration_rounds": 3, "potency_pct": 35,
        }
        with patch.object(game2, "_combat_check", side_effect=lambda *args: dict(passed)):
            game2.resolve_combat_round("defend")
        penalties = game2._player_effect_bonuses(game2.state["combat"])
        self.assertLess(penalties["power_pct"], 0)
        self.assertLess(penalties["defense_pct"], 0)
        self.assertLess(penalties["speed_pct"], 0)
        self.assertLess(penalties["accuracy_pct"], 0)


if __name__ == "__main__":
    unittest.main()
