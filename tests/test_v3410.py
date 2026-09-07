import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from reliability import visible_skills
from simulation_enhancements import (
    advance_companion_autonomy, advance_npc_development, apply_prompt_budget,
    normalize_dated_updates, reactive_communication, record_ability_evolution,
    world_downtime_events,
)
from support import repair_campaign_state
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3410Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_long_skip_updates_are_dated_in_order(self):
        rows = normalize_dated_updates([
            {"title":"First", "narrative":"First beat."},
            {"title":"Second", "narrative":"Second beat."},
            {"title":"Third", "narrative":"Third beat."},
        ], 10, 20, 10 * 1440)
        self.assertEqual([row["canon_day"] for row in rows], sorted(row["canon_day"] for row in rows))
        self.assertEqual(rows[-1]["canon_day"], 20)

    def test_companions_and_npcs_advance_independently(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(canon_day=30, turn=5, companions=[{"name":"Konan", "loyalty":80}],
                     standing_intents=[{"status":"active", "responsible":"Konan", "outcome":"Maintain the orphan shelter"}],
                     npc_memories={"Konan":{"recurring":True, "goal":"Train and protect the shelter", "power_score":40}})
        self.assertTrue(advance_companion_autonomy(state, 30 * 1440))
        self.assertTrue(advance_npc_development(state, 30 * 1440))
        self.assertGreater(state["npc_memories"]["Konan"]["power_score"], 40)

    def test_ability_history_is_visible_on_the_skill(self):
        before = copy.deepcopy(BASE_STATE); state = copy.deepcopy(BASE_STATE)
        before["skills"] = {"Shadow Step":{"description":"Move through connected shadows."}}
        state["skills"] = copy.deepcopy(before["skills"])
        record_ability_evolution(before, state, {"ability_developments":[{
            "ability":"Shadow Step", "kind":"application", "development":"Learned to carry an ally",
            "application":"Paired Shadow Step", "evidence":"A week of coordinated practice",
        }]}, ["Practice with Konan"])
        visible = visible_skills(state)["Shadow Step"]
        self.assertIn("Paired Shadow Step", visible["developed_applications"])
        self.assertTrue(visible["evolution_history"])

    def test_downtime_messages_and_prompt_budget_are_local(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Bleach", turn=8, canon_day=14, contacts={"Rukia":{"can_contact":True}})
        events = world_downtime_events(state, 7 * 1440, ["Patrol"])
        self.assertIn("Division", events[0]["title"])
        messages = reactive_communication(state, [{"title":"Rukia's Hollow Report", "narrative":"Rukia's patrol found evidence.", "importance":60}], 7 * 1440)
        self.assertEqual(messages[0]["sender"], "Rukia")
        snapshot = {"skills":{f"Skill {i}":{"description":"x"} for i in range(60)}, "inventory":list(range(80))}
        budgeted = apply_prompt_budget(snapshot, state, "Skill 59", "moment", "economy")
        self.assertLessEqual(len(budgeted["skills"]), 18)
        self.assertLessEqual(len(budgeted["inventory"]), 20)

    def test_overgeared_class_reception_modes(self):
        stats = {name:30 for name in abilities_for("Overgeared")}
        game = GameSession(); game.settings["autosave"] = False
        normal = game.preview_campaign("Ari", "Overgeared", "Adventurer", "A new Satisfy player.", "", "",
                                       "New Player", "Magic Swordsman", stats, overgeared_class_start="narrative")
        self.assertEqual(normal["starting_profile"]["class_profile"]["name"], "Beginner")
        self.assertIsNone(normal["starting_profile"]["hidden_class"])
        legendary = game.preview_campaign("Ari", "Overgeared", "Adventurer", "A new Satisfy player.", "", "",
                                          "New Player", "Magic Swordsman", stats, overgeared_class_start="legendary")
        self.assertEqual(legendary["starting_profile"]["hidden_class"]["rank"], "Legendary")

    def test_targeted_combat_recovery_repairs_string_enemy(self):
        state = copy.deepcopy(BASE_STATE)
        state["combat"] = {"active":True, "round":1, "enemy":"Tunnel Guard"}
        result = repair_campaign_state(state, "repair_combat")
        self.assertTrue(result["applied"])
        self.assertEqual(state["combat"]["enemy"]["name"], "Tunnel Guard")
        self.assertGreater(state["combat"]["enemy"]["hp_max"], 0)


if __name__ == "__main__":
    unittest.main()
