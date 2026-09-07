import copy
import tempfile
import unittest
from pathlib import Path

from ability_archive import GeneratedAbilityArchive
from game import GameSession
from state_guard import apply_guarded_patch
from worlds import APP_VERSION, BASE_STATE, power_profile_for


class WorldwalkerV3361Tests(unittest.TestCase):
    def make_game(self, folder):
        game = GameSession()
        game.generated_ability_archive = GeneratedAbilityArchive(Path(folder) / "abilities.json")
        return game

    def test_creation_background_locks_jjk_mechanism_and_bleach_name(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self.make_game(folder)
            slot = game.generate_jjk_birth_slot(
                "My innate technique is named Kinetic Treasury. It stores momentum from movement and impacts for later release."
            )
            self.assertEqual(slot["name"], "Kinetic Treasury")
            self.assertIn("Stores momentum", slot["governing_rule"])
            self.assertTrue(all("Kinetic Treasury" in row["name"] for row in slot["applications"]))

            stats = {name: 35 for name in ("Zanjutsu", "Hakuda", "Hoho", "Kido", "Reiatsu Control", "Willpower")}
            profile = game.infer_starting_profile(
                "Bleach", "Academy Senior", "Zanjutsu Specialist",
                "I named my Zanpakuto Kuroshio. I already possess Shikai, which controls tides and redirected currents.",
                stats, start_location="Shin'o Academy",
            )
            self.assertEqual(profile["bleach_release_profile"]["name"], "Kuroshio")
            self.assertIn("Kuroshio", profile["equipment"]["Weapon"])
            self.assertNotIn("Unnamed Asauchi", profile["equipment"]["Weapon"])

    def test_zanpakuto_sync_repairs_every_identity_surface(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Bleach", equipment={"Weapon": "Unnamed Asauchi and academy kit"})
        state["special"].update({
            "Zanpakuto": "Unnamed Asauchi", "Shikai": "Achieved — Kuroshio",
            "Zanpakuto Profile": {"name": "Kuroshio", "shikai_name": "Kuroshio", "stage": "Shikai"},
        })
        apply_guarded_patch(state, {}, source="test")
        self.assertEqual(state["special"]["Zanpakuto"], "Kuroshio")
        self.assertIn("Kuroshio", state["equipment"]["Weapon"])
        self.assertEqual(state["portrait_identity"]["zanpakuto_name"], "Kuroshio")
        self.assertTrue(any("Kuroshio" in row.get("text", "") for row in state["continuity_ledger"]["facts"]))

    def test_advisor_comparison_has_guaranteed_local_answer_and_chart(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(world="Naruto", name="Yahiko", stats={
            "Taijutsu": 199, "Ninjutsu": 749, "Genjutsu": 35,
            "Chakra Control": 188, "Willpower": 59, "Intellect": 53,
        })
        result = game.ask_advisor("How strong am I compared with Kakashi, early Naruto, and an average jonin?")
        self.assertTrue(result["local_answer"])
        labels = {row["label"] for row in result["entry"]["chart"]["items"]}
        self.assertTrue({"Yahiko", "Kakashi", "Early Naruto", "Average Jonin"}.issubset(labels))
        self.assertIn("Kakashi", " ".join(result["entry"]["points"]))

    def test_owned_title_event_is_not_announced_again(self):
        game = GameSession()
        before = copy.deepcopy(BASE_STATE)
        before.update(world="Solo Max-Level Newbie", titles=["Hidden-Route Analyst"])
        after = copy.deepcopy(before)
        events = [{"type": "title", "title": "Hidden-Route Analyst", "message": "New title acquired: Hidden-Route Analyst"}]
        notices = game.notify(before, after, events)
        self.assertFalse(any("Hidden-Route Analyst" in row["message"] for row in notices))

    def test_player_facing_power_profile_uses_world_terms(self):
        profile = power_profile_for("Naruto", {
            "Taijutsu": 199, "Ninjutsu": 749, "Genjutsu": 35,
            "Chakra Control": 188, "Willpower": 59, "Intellect": 53,
        }, "Ninjutsu Student")
        self.assertEqual(profile["player_facing"]["balanced"]["name"], profile["world_combat"]["name"])
        self.assertEqual(profile["player_facing"]["peak_specialty"]["name"], profile["world_peak"]["name"])
        self.assertIn("Do not display generic", profile["player_facing"]["rule"])

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")


if __name__ == "__main__":
    unittest.main()
