import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ability_archive import GeneratedAbilityArchive, semantic_similarity
from ability_mechanics import compile_ability_mechanics
from game import GameSession
from multiplayer_combat import resolve_multiplayer_combat_round
from politics import normalize_political_state, political_regions_for_map, transfer_territory
from power_benchmarks import benchmark_tier
from worlds import APP_VERSION, BASE_STATE, power_profile_for


class WorldwalkerV3280Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_world_power_benchmark_is_part_of_authoritative_profile(self):
        profile = power_profile_for("Naruto", {"Taijutsu": 199, "Ninjutsu": 749, "Genjutsu": 35,
            "Chakra Control": 188, "Willpower": 59, "Intellect": 53}, "Ninjutsu Student")
        self.assertEqual(profile["world_combat"]["name"], "Special Jonin")
        self.assertEqual(profile["world_peak"]["name"], "Kage Class")
        self.assertEqual(benchmark_tier("Bleach", 210)["name"], "Captain Class")

    def test_ability_compiler_fills_playable_contract_without_erasing_identity(self):
        result = compile_ability_mechanics("Naruto", {"name": "Glass Moon Thread", "effect": "Binds an enemy in refracted chakra threads."}, 6)
        compiled = result["compiled_mechanics"]
        self.assertEqual(compiled["resource"], "Chakra")
        self.assertTrue(compiled["activation"])
        self.assertTrue(compiled["counterplay"])
        self.assertEqual(len(compiled["mastery_stages"]), 3)
        self.assertEqual(result["effect_type"], "control")

    def test_semantic_duplicate_guard_catches_renamed_paraphrase(self):
        first = {"name": "Ash Covenant", "governing_rule": "Stores incoming fire and releases it as a delayed defensive barrier.", "costs": "Consumes stamina"}
        renamed = {"name": "Ember Pact", "governing_rule": "Stores incoming fire, then releases it later as a defensive barrier.", "costs": "Consumes stamina"}
        self.assertGreaterEqual(semantic_similarity(first, renamed), .78)
        with tempfile.TemporaryDirectory() as td:
            archive = GeneratedAbilityArchive(Path(td) / "abilities.json")
            archive.record("Naruto", "starting_ability", first)
            self.assertTrue(archive.is_duplicate("Naruto", "starting_ability", renamed))
            self.assertEqual(len(archive.entries()), 1)

    def test_territories_use_non_overlapping_strategy_geometry_and_transfer(self):
        state = {"turn": 4, "canon_day": 0, "polity_state": {}, "factions": {}, "faction_clocks": {},
                 "political_regions": [{"id": "rain", "name": "Rain Country", "controller": "Akatsuki", "anchor": "Amegakure", "size": 18}],
                 "location_details": {}}
        normalize_political_state(state)
        regions = political_regions_for_map(state, [{"name": "Amegakure", "x": 44, "y": 52, "controller": "Akatsuki"}])
        self.assertEqual(regions[0]["geometry"], "strategic")
        self.assertIsNone(regions[0]["polygon"])
        self.assertEqual(transfer_territory(state, "rain", "New Rain", ["Akatsuki"])["to"], "New Rain")
        self.assertEqual(state["political_regions"][0]["contested_by"], ["Akatsuki"])
        self.assertEqual(state["location_details"]["Amegakure"]["controlling_faction"], "New Rain")

    def test_narrative_location_control_repaints_matching_region(self):
        state = {"turn": 9, "canon_day": 0, "polity_state": {}, "factions": {}, "faction_clocks": {},
                 "political_regions": [{"id": "rain", "name": "Rain Country", "controller": "Amegakure", "anchor": "Amegakure", "size": 18}],
                 "location_details": {"Amegakure": {"controlling_faction": "Player's Rain", "controller_changed_turn": 9}}}
        normalize_political_state(state)
        self.assertEqual(state["political_regions"][0]["controller"], "Player's Rain")
        regions = political_regions_for_map(state, [{"name": "Amegakure", "x": 44, "y": 52, "controller": "Player's Rain", "recently_changed": True}])
        self.assertEqual(regions[0]["controller"], "Player's Rain")
        self.assertTrue(regions[0]["recently_changed"])

    def test_authored_boundaries_remain_available_to_strategy_partition(self):
        state = {"turn": 1, "political_regions": [{"id": "isle", "name": "Crown Isle", "controller": "Crown", "x": 30, "y": 40,
                 "polygon": [[20, 30], [40, 30], [42, 48], [22, 50]]}]}
        regions = political_regions_for_map(state, [])
        self.assertEqual(regions[0]["geometry"], "authored")
        self.assertEqual(len(regions[0]["polygon"]), 4)

    def test_local_advisor_power_answer_uses_no_ai_call(self):
        game = GameSession(); game.settings["ai_connection_status"] = "valid"; game.settings["model"] = "local-test"
        game.state = copy.deepcopy(BASE_STATE); game.state.update(world="Naruto", stats={"Taijutsu": 80, "Ninjutsu": 90, "Genjutsu": 40, "Chakra Control": 70, "Willpower": 60, "Intellect": 50})
        before = game.ai.usage["calls"]
        result = game.ask_advisor("How strong am I?")
        self.assertTrue(result["local_answer"])
        self.assertEqual(game.ai.usage["calls"], before)

    def test_multiplayer_combat_resolves_both_characters_locally(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", difficulty="Adventurer", combat={"active": True, "round": 1,
            "enemy": {"name": "Bandit", "hp": 100, "hp_max": 100, "power": 30,
                      "difficulty_min": 1, "difficulty_max": 1, "attack_min": 1, "attack_max": 1, "alive": True}})
        character = lambda name: {"name": name, "hp": 100, "hp_max": 100, "alive": True,
            "stats": {"Taijutsu": 50, "Ninjutsu": 50, "Willpower": 50}, "skills": {}, "status": []}
        participants = [{"user_id": "a", "username": "a", "character": character("A"), "actions": ["attack"]},
                        {"user_id": "b", "username": "b", "character": character("B"), "actions": ["defend"]}]
        with patch("multiplayer_combat.random.randint", side_effect=lambda low, high: high):
            result = resolve_multiplayer_combat_round(state, participants, 1)
        self.assertEqual(set(result["characters"]), {"a", "b"})
        self.assertTrue(any(row.get("name") == "A" for row in result["state"]["combat"]["log"]))
        self.assertIn("MULTIPLAYER COMBAT", result["result"]["story"][0]["text"])


if __name__ == "__main__":
    unittest.main()
