import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import migrate_state
from worlds import BASE_STATE, uses_xp_for


class WorldwalkerV250Tests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession()

    def test_start_profile_is_open_ended_and_pools_derive_from_stats(self):
        preview = self.game.preview_campaign("Kara", "Naruto", "Adventurer", "A trained prodigy", "", "", "Academy Graduate", "Ninjutsu Student", {}, "", "", "")
        self.assertGreater(preview["abilities"]["Ninjutsu"], 40)
        profile = preview["starting_profile"]
        self.assertNotEqual(profile["hp_max"], 100)
        self.assertNotEqual(profile["resource_max"], 100)
        self.assertEqual(profile["growth_profile"]["combat_style"], "Ninjutsu Student")
        self.assertFalse(any("fundamental" in name.lower() for name in profile["skills"]))
        self.assertTrue(profile["equipment"])

    def test_world_shaking_background_warns_but_is_allowed(self):
        preview = self.game.preview_campaign("Nova", "One Piece", "Story", "Already a godlike emperor of the sea", "", "", "Aspiring Pirate", "Brawler", {}, "", "", "")
        self.assertEqual(preview["starting_profile"]["power_band"], "Emperor Class")
        self.assertTrue(preview["starting_profile"]["power_notice"])
        self.assertGreater(max(preview["abilities"].values()), 100)

    def test_d100_requires_total_strictly_above_difficulty(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Naruto", difficulty="Adventurer", stats={k: 30 for k in ("Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect")}, titles=[])
        assessment = {"ability": "Ninjutsu", "difficulty_min": 56, "difficulty_max": 56, "relevant_average_stat": 30}
        # Adventurer shifts 56 to 50; raw 50 + zero bonuses equals 50 and fails.
        with patch("game.random.randint", side_effect=[50, 50]):
            result = self.game.roll(assessment)
        self.assertEqual(result["total"], result["difficulty"])
        self.assertFalse(result["success"])

    def test_month_training_accumulates_daily_sessions(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Naruto", stats={k: 30 for k in ("Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect")}, special={"Archetype": "Ninjutsu Student"})
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("game.random.random", return_value=1.0):
            self.game.enforce_training_progress(data, [{"ability": "Ninjutsu", "success": True, "breakthrough": False}], 1, "months", ["Train ninjutsu every day"], "normal")
        self.assertGreaterEqual(data["state_patch"]["stats"]["Ninjutsu"], 37)
        entry = data["state_patch"]["progression_log"][-1]
        self.assertEqual(entry["effective_training_days"], 30.0)

    def test_training_scales_continuously_and_carries_fractional_progress(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Naruto", stats={k: 30 for k in ("Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect")}, special={"Archetype": "Ninjutsu Student"})
        short, long = {"state_patch": {}, "events": [], "updates": []}, {"state_patch": {}, "events": [], "updates": []}
        with patch("game.random.random", return_value=1.0):
            self.game.enforce_training_progress(short, [{"ability": "Ninjutsu", "success": True}], 2, "hours", ["Practice ninjutsu"], "normal")
            self.game.enforce_training_progress(long, [{"ability": "Ninjutsu", "success": True}], 2, "weeks", ["Practice ninjutsu"], "normal")
        self.assertGreater(short["state_patch"]["ability_progress"]["Ninjutsu"], 0)
        self.assertGreater(long["state_patch"]["stats"]["Ninjutsu"], short["state_patch"]["stats"]["Ninjutsu"])

    def test_major_event_requires_manual_roll(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Naruto", difficulty="Adventurer")
        result = self.game.run_time_skip(1, "hours", ["Awaken a transformation"], "normal", {"checks": [{"id": "evolve", "reason": "Awaken", "ability": "Willpower", "difficulty_min": 70, "difficulty_max": 80, "relevant_average_stat": 30, "major_event": True, "lethal_risk": "none"}]})
        self.assertEqual(result["status"], "manual_roll_required")
        self.assertEqual(result["check_id"], "evolve")

    def test_xp_only_exists_in_canonical_system_worlds(self):
        self.assertFalse(uses_xp_for("Naruto"))
        self.assertFalse(uses_xp_for("One Piece"))
        self.assertTrue(uses_xp_for("Overgeared"))
        self.assertTrue(uses_xp_for("Solo Max-Level Newbie"))

    def test_every_meaningful_system_world_action_gets_xp(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Overgeared", level=1, xp=0, xp_next=100,
                               stats={k: 30 for k in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck")},
                               special={"Archetype": "Warrior"})
        before = copy.deepcopy(self.game.state)
        result = self.game.apply_system_xp(before, ["Speak with the village smith"], [], 15, "normal", [])
        self.assertGreater(result["xp_awarded"], 0)
        self.assertEqual(self.game.state["xp"], result["xp_awarded"])
        self.assertEqual(self.game.state["level"], 1)

    def test_system_level_up_spends_xp_and_increases_base_stats(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        stats = {k: 30 for k in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck")}
        self.game.state.update(world="Overgeared", level=1, xp=90, xp_next=100,
                               stats=copy.deepcopy(stats), special={"Archetype": "Warrior"})
        before = copy.deepcopy(self.game.state)
        result = self.game.apply_system_xp(
            before, ["Defeat the dungeon boss"],
            [{"difficulty": 84, "success": True, "major_event": True}], 60, "intense", [],
        )
        self.assertEqual(result["levels_gained"], 1)
        self.assertEqual(self.game.state["level"], 2)
        self.assertLess(self.game.state["xp"], self.game.state["xp_next"])
        self.assertTrue(all(self.game.state["stats"][name] > value for name, value in stats.items()))
        messages = [entry["message"] for entry in self.game.notify(before, self.game.state, [])]
        self.assertTrue(any(message.startswith("XP +") for message in messages))
        self.assertFalse(any(message.startswith("XP -") for message in messages))

    def test_system_training_builds_proficiency_then_levels_instead_of_direct_stat_patch(self):
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Solo Max-Level Newbie", level=1, xp=0, xp_next=100,
                               stats={k: 30 for k in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck")},
                               special={"Archetype": "Fighter"})
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("game.random.random", return_value=1.0):
            self.game.enforce_training_progress(data, [{"ability": "Strength", "success": True}], 1, "months", ["Train strength every day"], "normal")
        self.assertFalse(data["state_patch"]["stats"])
        self.assertGreater(data["state_patch"]["ability_progress"]["Strength"], 0)
        before = copy.deepcopy(self.game.state)
        result = self.game.apply_system_xp(before, ["Train strength every day"], [], 30 * 1440, "normal", [])
        self.assertGreaterEqual(result["xp_awarded"], 100)
        self.assertGreaterEqual(self.game.state["level"], 2)
        self.assertGreater(self.game.state["stats"]["Strength"], 30)

    def test_advisor_fourth_wall_receives_mechanics_mode_and_canon_countdown(self):
        class AdvisorAI:
            def __init__(self): self.payload = None
            def request(self, rules, payload, max_output_tokens=0):
                self.payload = payload
                return {"summary": "Plan around the next canon event.", "points": ["Use the d100 bonus."], "follow_ups": []}
        ai = AdvisorAI()
        self.game.state = copy.deepcopy(BASE_STATE)
        self.game.state.update(world="Naruto", canon_day=-7, canon_time_minutes=-7 * 1440 + 480)
        self.game.settings["model"] = "fake"
        self.game.ai = ai
        result = self.game.ask_advisor("How can I exploit the timing?", fourth_wall=True)
        self.assertEqual(ai.payload["advisor_mode"], "fourth_wall")
        self.assertTrue(ai.payload["next_canon_event"]["available"])
        self.assertTrue(result["entry"]["fourth_wall"])
        self.assertIn("until", result["entry"]["canon_countdown"]["label"])

    def test_legacy_stats_and_pool_ratios_migrate(self):
        old = copy.deepcopy(BASE_STATE)
        old.update(schema_version=4, world="Naruto", stats={"Taijutsu": 10, "Ninjutsu": 15, "Genjutsu": 8, "Chakra Control": 12, "Willpower": 11, "Intellect": 13}, hp=50, hp_max=100, resource=25, resource_max=100)
        migrated = migrate_state(old, "2.4.0")
        self.assertEqual(migrated["schema_version"], 21)
        self.assertEqual(migrated["stats"]["Ninjutsu"], 45)
        self.assertAlmostEqual(migrated["hp"] / migrated["hp_max"], .5, delta=.02)
        self.assertAlmostEqual(migrated["resource"] / migrated["resource_max"], .25, delta=.02)


if __name__ == "__main__":
    unittest.main()
