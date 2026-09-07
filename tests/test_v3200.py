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
from lit_systems import process_lit_turn
from overgeared_classes import (ROLE_STARTER_KITS, class_action_bonus,
                                class_encyclopedia, starter_kit_for)
from worlds import abilities_for


class WorldwalkerV3200ClassGameplayTests(unittest.TestCase):
    def test_release_version(self):
        from worlds import APP_VERSION
        self.assertEqual(APP_VERSION, "3.64.0")

    def campaign(self, role="Summoner"):
        game = GameSession()
        game.settings["autosave"] = False
        with patch("engine_campaign.random.random", return_value=1.0):
            game.new_campaign(
                "Role Tester", "Overgeared", "Adventurer",
                "I want an independent life in Satisfy built around this role.",
                "", "", "New Player", role,
                {name: 30 for name in abilities_for("Overgeared")},
            )
        return game

    def test_every_creation_role_is_a_preference_until_a_class_is_received(self):
        for role in ROLE_STARTER_KITS:
            state = self.campaign(role).state
            kit = starter_kit_for(role)
            self.assertGreaterEqual(len(kit["skills"]), 2, role)
            self.assertFalse(set(kit["skills"]).issubset(state["skills"]), role)
            self.assertEqual(state["special"]["Class"], "Beginner")
            self.assertEqual(state["overgeared_system"]["class_reception"]["preferred_route"], role)
            self.assertEqual(len(kit["advancements"]), 2, role)

    def test_summoner_contract_is_not_granted_before_the_class(self):
        state = self.campaign("Summoner").state
        self.assertEqual(state["overgeared_system"]["companion_contracts"], {})
        self.assertNotIn("Lumen Wisp", [row["name"] for row in state["companions"]])

    def test_suggestions_follow_the_preferred_route_without_an_unearned_bonus(self):
        game = self.campaign("Summoner")
        joined = " | ".join(game.state["suggested_actions"])
        self.assertIn("Summoner", joined)
        self.assertNotIn("Weapon Proficiency", joined)
        self.assertEqual(class_action_bonus(game.state, "Command Lumen Wisp to bind the attacker"), 0)
        self.assertEqual(class_action_bonus(game.state, "Forge a sword"), 0)

    def test_support_social_scout_and_companion_contributions_receive_real_xp(self):
        game = self.campaign("Priest/Healer")
        for action in ("Heal the injured guard", "Scout and map the dangerous route",
                       "Negotiate a fair escort agreement", "Coordinate my companion to protect the party"):
            xp, rows = game.calculate_xp_award([action], elapsed_minutes=60)
            self.assertGreaterEqual(xp, 10, action)
            self.assertIn("contribution", rows[0]["reason"])

    def test_receiving_a_class_in_the_narrative_synchronizes_the_system(self):
        state = self.campaign("Summoner").state
        before = copy.deepcopy(state)
        state["class_profile"] = {
            "name":"Concord Summoner", "kind":"Summoner Class", "rank":"Rare", "class_type":"Companion / Summoning",
            "growth_path":"Develop contracts through shared achievements.", "signature_skill":"Concord Contract",
        }
        process_lit_turn(before, state, ["Accept the Concord Summoner class from the spirit shrine"],
                         "The Satisfy System awards the class.", 60)
        self.assertEqual(state["special"]["Class"], "Concord Summoner")
        self.assertEqual(state["overgeared_system"]["class_reception"]["status"], "received")
        self.assertTrue(state["overgeared_system"]["system_notifications"])

    def test_class_encyclopedia_exposes_breadth_without_an_ai_call(self):
        data = class_encyclopedia()
        self.assertEqual(len(data["starter_classes"]), len(ROLE_STARTER_KITS))
        self.assertGreaterEqual(data["canon_name_count"], 130)
        self.assertGreaterEqual(len(data["families"]), 8)

    def test_overgeared_backstory_is_role_specific_and_not_generation_labeled(self):
        profile = self.campaign("Summoner").state
        text = profile["background"]
        self.assertIn("contracted creatures as partners", text)
        self.assertNotIn("Generated", text)
        self.assertNotIn("Their own account adds", text)

    def test_ai_ready_requires_a_successful_connection_validation(self):
        game = GameSession()
        game.settings.update(provider="cloud", api_key="bad", model="gpt-5-nano", ai_connection_status="untested")
        self.assertFalse(game.ai_ready())
        game.settings["ai_connection_status"] = "invalid"
        self.assertFalse(game.ai_ready())
        game.settings["ai_connection_status"] = "valid"
        self.assertTrue(game.ai_ready())

    def test_litrpg_levels_are_visible_and_notifications_use_in_world_systems(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('card("SATISFY STATUS", `LEVEL ${data.level || 1}`', js)
        self.assertIn('card("SYSTEM STATUS", `LEVEL ${data.level || 1}`', js)
        game = self.campaign("Summoner")
        before = copy.deepcopy(game.state)
        game.state.update(xp=25, level=2, xp_next=150)
        notices = game.notify(before, game.state, [])
        self.assertTrue(any(row["cinematic"] == "level_up" and row["world_system"] == "satisfy" for row in notices))
        self.assertTrue(any("Your level has risen" in row["display_message"] for row in notices))
        self.assertTrue(any("[SATISFY SYSTEM]" in row["text"] for row in game.story_log))

        game.state["world"] = "Solo Max-Level Newbie"
        before = copy.deepcopy(game.state)
        game.state["xp"] += 10
        notices = game.notify(before, game.state, [])
        self.assertTrue(any("[Experience acquired:" in row["display_message"] for row in notices))
        self.assertTrue(any("[SYSTEM MESSAGE]" in row["text"] for row in game.story_log))


class WorldwalkerV3200CombatStartGuardTests(unittest.TestCase):
    def game(self):
        game = GameSession()
        game.settings["autosave"] = False
        game.state.update(world="Overgeared", name="Tester", location="Winston", combat={},
                          npc_memories={}, contacts={})
        return game

    def test_tense_or_figurative_scene_cannot_start_combat(self):
        game = self.game()
        for action in ("Strike a deal with the merchant", "Hit the road", "Fight the fear and keep training"):
            data = {"narrative": "The discussion remains tense, but no one attacks.",
                    "state_patch": {"combat": {"active": True, "enemy": {"name": "Merchant"}}}}
            game.ensure_immediate_combat_patch(data, [action])
            self.assertNotIn("combat", data["state_patch"], action)
            self.assertIn("combat_start_rejected", data)

    def test_explicit_attack_still_starts_combat(self):
        game = self.game()
        data = {"narrative": "The bandit reels as the player commits to the attack.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(data, ["Attack the bandit with my sword"]))
        self.assertTrue(data["state_patch"]["combat"]["active"])

    def test_unavoidable_enemy_attack_still_starts_combat(self):
        game = self.game()
        data = {"narrative": "The bandit lunges at you with a drawn blade.", "state_patch": {}}
        self.assertTrue(game.ensure_immediate_combat_patch(data, ["Demand an explanation"]))
        self.assertTrue(data["state_patch"]["combat"]["active"])


if __name__ == "__main__":
    unittest.main()
