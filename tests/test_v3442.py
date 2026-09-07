import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from simulation_enhancements import reactive_communication
from skill_system import build_combat_ability_options
from state_guard import migrate_state
from worlds import APP_VERSION, BASE_STATE, abilities_for


def game_state():
    state = copy.deepcopy(BASE_STATE)
    state.update({
        "world": "One Piece", "name": "Asura", "opening_complete": True,
        "campaign_id": "v3442-combat", "location": "Harbor",
        "stats": {name: 60 for name in abilities_for("One Piece")},
        "hp": 150, "hp_max": 150, "resource": 160, "resource_max": 160,
        "skills": {
            "Celestial Ember": {
                "rank": "C", "bonus": 4, "category": "defense",
                "effect_type": "shield", "combat_usable": True,
                "description": "Ignites and shapes the flame carried on Asura's back.",
                "limitation": "Using *Flame Flight* drains stamina quickly; *Fiery Shield* costs energy and blocks one major attack; *Ember Strike* requires physical contact.",
            },
            "Ignition Kick": {
                "rank": "C", "bonus": 4, "category": "utility", "effect_type": "utility", "combat_usable": False,
                "description": "A flame-propelled kick that strikes an enemy.",
            },
        },
        "combat": {
            "active": True, "round": 1, "enemy": {
                "name": "Tunnel Guard", "hp": 180, "hp_max": 180,
                "power": 40, "difficulty_min": 20, "difficulty_max": 30,
                "attack_min": 20, "attack_max": 30, "alive": True,
            },
        },
    })
    return state


class CombatApplicationTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_umbrella_moves_and_kick_are_real_combat_options(self):
        options = build_combat_ability_options(game_state()["skills"])
        self.assertEqual(options["Celestial Ember::Flame Flight"]["effect_type"], "movement")
        self.assertEqual(options["Celestial Ember::Fiery Shield"]["effect_type"], "shield")
        self.assertEqual(options["Celestial Ember::Ember Strike"]["effect_type"], "damage")
        self.assertEqual(options["Ignition Kick"]["effect_type"], "damage")
        self.assertTrue(options["Ignition Kick"]["combat_usable"])

    def test_nested_shield_resolves_in_an_actual_round(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.autosave = lambda: None
            game.state = game_state()
            game.ensure_combat_numbers()
            with patch("combat.random.randint", return_value=80):
                result = game.resolve_combat_round("attack", "Celestial Ember::Fiery Shield")
            player_event = next(row for row in result["log_tail"] if row.get("actor") == "player")
            self.assertEqual(player_event["action"], "shield")
            self.assertEqual(player_event["ability"], "Fiery Shield")
            self.assertGreater(player_event["shield"], 0)
            self.assertGreaterEqual(game.state["combat"]["player_shield"], 0)


class CommunicationAndAgendaTests(unittest.TestCase):
    def test_famous_canon_character_never_falls_to_generic_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.state = copy.deepcopy(BASE_STATE)
            game.state.update({
                "world": "Naruto", "name": "Yahiko",
                "stats": {name: 400 for name in abilities_for("Naruto")},
            })
            result = game._local_power_comparison("How strong am I against Minato?", True)
            rows = {row["label"]: row["value"] for row in result["chart"]["items"]}
            self.assertEqual(rows["Minato"], 620.0)
            self.assertIn("Kage Class", result["points"][0])
            self.assertNotIn("low-confidence world-role estimate", result["points"][0])

    def test_local_message_requires_relevance_and_contains_only_dialogue(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "world": "Naruto", "turn": 12,
            "contacts": {"Konohagakure": {"kind": "faction"}, "Konan": {"kind": "person", "relationship": 40}},
            "npc_memories": {"Konan": {"goal": "Protect Amegakure"}},
        })
        event = {"type": "story", "title": "Konan's Shadow Doctrine",
                 "narrative": "Konan reorganized the watch around the new doctrine.", "importance": 60}
        messages = reactive_communication(state, [event], 43200)
        self.assertEqual(messages[0]["sender"], "Konan")
        self.assertNotIn("arrives from", messages[0]["message"])
        self.assertNotIn("I heard about Konan's", messages[0]["message"])

        state["contacts"] = {"Konohagakure": {"kind": "faction"}}
        self.assertEqual(reactive_communication(state, [event], 43200), [])

    def test_migration_unwraps_existing_local_message(self):
        state = copy.deepcopy(BASE_STATE)
        state["chat_threads"] = {"Konan": [{
            "sender": "Konan", "direction": "incoming",
            "text": "A mission report or messenger arrives from Konan: “I have an update.”",
            "metadata": {"generated_locally": True},
        }]}
        migrated = migrate_state(state, "3.44.1")
        self.assertEqual(migrated["chat_threads"]["Konan"][0]["text"], "I have an update.")

    def test_narrative_assignment_omits_none_and_repeated_boilerplate(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.settings["autosave"] = False
            game.story_log = []
            before = copy.deepcopy(BASE_STATE)
            game.state = copy.deepcopy(BASE_STATE)
            game.state.update({"world": "Naruto", "location": "Akatsuki pump station safehouse", "quests": [{
                "name": "Akatsuki Civilian Foundation", "status": "Active",
                "explanation": "Yahiko spends the month strengthening Akatsuki's civilian foundation while training.",
                "current_knowledge": ["Yahiko spends the month strengthening Akatsuki's civilian foundation while training."],
                "first_step": "None", "risks": ["No specific danger is confirmed yet."],
            }]})
            game.ensure_quest_briefings(before, "Yahiko spends the month strengthening Akatsuki's civilian foundation while training.")
            text = game.story_log[-1]["text"]
            self.assertNotIn("Current direction: None", text)
            self.assertNotIn("What you know:", text)
            self.assertNotIn("No specific danger", text)
            self.assertEqual(text.count("Yahiko spends the month"), 1)


if __name__ == "__main__":
    unittest.main()
