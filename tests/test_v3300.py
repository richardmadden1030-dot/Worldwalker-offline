import copy
import unittest
from pathlib import Path

from worlds import APP_VERSION, BASE_STATE
from state_guard import APP_OWNED, migrate_state
from simulation import refresh_npc_intentions, advance_npc_intentions
from simulation_core import (refresh_simulation_core, companion_support_for_combat,
                             normalize_encounter_state, record_resolution_transaction)
from evaluations import run_local_simulation_evaluation
from game import GameSession
from combat import _fallback_enemy_power
from naruto_system import (apply_jinchuriki_start, build_jinchuriki_profile,
                           jinchuriki_story_evidence)
from world_progression import normalize_world_progression
from portrait_generator import portrait_signature, sync_active_portrait_form


ROOT = Path(__file__).resolve().parents[1]


class WorldwalkerV3300SimulationCoreTests(unittest.TestCase):
    def test_release_and_owned_core_records(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        for field in ("capability_profile", "ability_registry", "progression_calibration", "npc_continuity",
                      "encounter_state", "story_threads", "resolution_ledger", "simulation_core_version"):
            self.assertIn(field, BASE_STATE)
            self.assertIn(field, APP_OWNED)

    def test_core_unifies_capability_ability_progression_npcs_and_threads(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Amegakure",
                     stats={"Taijutsu": 80, "Ninjutsu": 120, "Genjutsu": 30, "Chakra Control": 90, "Willpower": 70, "Intellect": 55},
                     skills={"Storm Needle": {"effect": "Pins an enemy with lightning chakra.", "limitation": "Needs line of sight.", "combat_usable": True, "effect_type": "control"}},
                     companions=[{"name": "Konan", "role": "Ranged support", "combat_support": True, "support_bonus": 8}],
                     npc_memories={"Konan": {"goal": "Protect Amegakure", "last_known_location": "Amegakure"},
                                   "Hanzō": {"goal": "Destroy the Akatsuki", "nemesis": True, "recurring": True}},
                     quests=[{"name": "Secure Amegakure", "status": "Active", "next_hint": "Win local support"}])
        refresh_simulation_core(state, ["Train Storm Needle through daily chakra drills"], 43200)
        self.assertEqual(state["capability_profile"]["power"]["peak"]["score"], 120)
        self.assertTrue(state["ability_registry"]["Storm Needle"]["mechanics"]["counterplay"])
        self.assertGreater(state["progression_calibration"]["expected_primary_gain"]["typical"], 0)
        self.assertTrue(state["npc_continuity"]["Hanzō"]["nemesis"])
        self.assertEqual(companion_support_for_combat(state)[0]["bonus"], 8)
        self.assertIn("quest:secure amegakure", state["story_threads"])

    def test_encounter_lifecycle_and_resolution_transaction(self):
        state = copy.deepcopy(BASE_STATE)
        before = copy.deepcopy(state)
        state["combat"] = {"active": True, "enemy": {"name": "Bandit"}}
        self.assertEqual(normalize_encounter_state(state)["phase"], "active_combat")
        state["combat"].update(active=False, outcome="victory")
        self.assertEqual(normalize_encounter_state(state)["phase"], "aftermath")
        state["stats"]["Strength"] += 3
        tx = record_resolution_transaction(state, before, ["Train with weighted drills"], 1440, "The training works.")
        self.assertEqual(tx["phases"]["mechanics"]["stat_changes"]["Strength"], 3)

    def test_nemesis_flag_survives_intention_system_and_advances_slowly(self):
        state = copy.deepcopy(BASE_STATE)
        state["npc_memories"] = {"Nemesis": {"goal": "A long scheme", "nemesis": True, "recurring": True}}
        row = refresh_npc_intentions(state)["Nemesis"]
        self.assertTrue(row["nemesis"])
        advance_npc_intentions(state, 14400)
        self.assertLess(state["npc_intentions"]["Nemesis"]["progress"], 10)

    def test_existing_nemesis_and_combat_support_flags_reach_gm_and_combat(self):
        game = GameSession()
        game.state.update(world="Naruto", location="Amegakure",
                          companions=[{"name": "Konan", "combat_support": True, "support_bonus": 9}],
                          npc_memories={"Konan": {"goal": "Protect Yahiko"},
                                        "Hanzō": {"nemesis": True, "goal": "Break the Akatsuki"}},
                          combat={"active": True, "enemy": {"name": "Hanzō's guard", "power": 60,
                                                              "hp": 100, "hp_max": 100}})
        prompt_state = game.task_state_for_ai("moment")
        role_flags = {row["name"]: row for row in prompt_state["npc_role_flags"]}
        self.assertTrue(role_flags["Hanzō"]["nemesis"])
        self.assertTrue(role_flags["Konan"]["combat_support"])
        game.ensure_combat_numbers()
        self.assertEqual(game.state["combat"]["ally_support"], 9)
        self.assertEqual(game.state["combat"]["supporting_companions"][0]["name"], "Konan")

    def test_migration_backfills_core_and_local_evaluator_is_free(self):
        migrated = migrate_state({"world": "Bleach", "schema_version": 19}, "3.29.0")
        self.assertTrue(migrated["capability_profile"])
        report = run_local_simulation_evaluation()
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["ai_calls"], 0)
        self.assertEqual(report["estimated_cost_usd"], 0.0)

    def test_advisor_receives_full_question_evidence_and_uses_main_model_by_default(self):
        class RecordingAI:
            def __init__(self, name):
                self.name, self.calls = name, []

            def request(self, rules, payload, max_output_tokens=0):
                self.calls.append({"rules": rules, "payload": payload, "max_output_tokens": max_output_tokens})
                return {"summary": "Konan is still leading the evacuation.", "points": [], "follow_ups": []}

        game = GameSession()
        game.settings.update(model="main-model", secondary_model="cheap-background", advisor_model="", advisor_provider="inherit",
                             ai_connection_status="valid")
        main, background = RecordingAI("main"), RecordingAI("background")
        game.ai, game.ai_bg = main, background
        game.state.update(world="Naruto", turn=25,
                          campaign_canon=[{"turn": i, "action": f"Turn {i}", "outcome": ("Konan began the evacuation." if i == 3 else f"Result {i}")} for i in range(1, 26)],
                          continuity_ledger={"facts": [{"turn": 3, "type": "npc", "text": "Konan began the evacuation."}], "warnings": [], "last_checked_turn": 25},
                          npc_memories={"Konan": {"goal": "Lead the evacuation", "attitude": "Allied"}},
                          faction_chain={"Akatsuki": [{"event": "The player protected its founders.", "turn": 4}]},
                          npc_relationships={"Konan::Nagato": {"a": "Konan", "b": "Nagato", "type": "allies", "strength": 90}},
                          faction_rosters={"Akatsuki": ["Konan", "Nagato"]})
        result = game.ask_advisor("What happened to Konan?")
        self.assertEqual(result["entry"]["summary"], "Konan is still leading the evacuation.")
        self.assertEqual(len(main.calls), 1)
        self.assertEqual(background.calls, [])
        payload = main.calls[0]["payload"]
        self.assertEqual(payload["thread_history"], [])
        self.assertTrue(any("evacuation" in row.get("text", "").lower() for row in payload["state"]["question_evidence"]))
        self.assertIn("faction_chain", payload["state"])
        self.assertIn("npc_relationships", payload["state"])
        self.assertIn("faction_rosters", payload["state"])
        self.assertNotIn("SHORT/LOW-EFFORT", main.calls[0]["rules"])

    def test_advisor_local_quest_shortcut_does_not_hijack_specific_questions(self):
        game = GameSession()
        game.state["quests"] = [{"name": "Rescue Konan", "status": "Active", "description": "Find her."}]
        self.assertIsNone(game._local_advisor_answer("Why did the previous quest fail?"))

    def test_advisor_power_comparison_uses_guaranteed_local_chart(self):
        class RecordingAI:
            def __init__(self): self.calls = []
            def request(self, rules, payload, max_output_tokens=0):
                self.calls.append((rules, payload))
                return {"summary": "You rank near the upper half.", "points": [], "follow_ups": [],
                        "chart": {"title": "Current Akatsuki comparison", "unit": "Balanced combat estimate",
                                  "items": [{"label": "Yahiko", "value": 547}, {"label": "Pain", "value": 620}]}}
        game = GameSession(); game.settings.update(model="test", ai_connection_status="valid")
        game.state.update(world="Naruto", name="Yahiko")
        ai = RecordingAI(); game.ai = ai
        self.assertIsNone(game._local_advisor_answer("How strong am I compared to other members of the Akatsuki?"))
        result = game.ask_advisor("How strong am I compared to other members of the Akatsuki?")
        self.assertTrue(result.get("local_answer", False))
        self.assertEqual(ai.calls, [])
        self.assertEqual(result["entry"]["chart"]["unit"], "Balanced combat estimate")
        self.assertIn("Pain", {row["label"] for row in result["entry"]["chart"]["items"]})

    def test_missing_enemy_numbers_use_world_role_not_player_level(self):
        game = GameSession()
        game.state.update(world="Naruto", difficulty="Adventurer",
                          stats={"Taijutsu": 800, "Ninjutsu": 900, "Genjutsu": 500,
                                 "Chakra Control": 750, "Willpower": 600, "Intellect": 550},
                          combat={"active": True, "enemy": {"name": "Random Bandit Group", "is_group": True, "group_size": 4}})
        game.ensure_combat_numbers()
        enemy = game.state["combat"]["enemy"]
        self.assertEqual(enemy["power"], 45)
        self.assertEqual(enemy["hp_max"], 90)
        self.assertEqual(enemy["power_source"], "world_role_fallback")
        self.assertLess(enemy["power"], 100)
        self.assertEqual(_fallback_enemy_power("Naruto", {"name": "Veteran Jonin"}), 130)

    def test_explicit_canon_enemy_power_is_never_rebalanced(self):
        game = GameSession()
        game.state.update(world="Naruto", difficulty="Adventurer", stats={"Ninjutsu": 900},
                          combat={"active": True, "enemy": {"name": "Canon Opponent", "power": 600, "hp": 1200}})
        game.ensure_combat_numbers()
        self.assertEqual(game.state["combat"]["enemy"]["power"], 600)
        self.assertEqual(game.state["combat"]["enemy"]["hp_max"], 1200)
        self.assertEqual(game.state["combat"]["enemy"]["power_source"], "narrator_or_canon")

    def test_jinchuriki_panel_uses_exact_mechanical_boosts_and_fourth_position(self):
        profile = build_jinchuriki_profile("I am Kurama's fully mastered jinchuriki", seed="panel-test")
        self.assertEqual(profile["tails"], 9)
        self.assertEqual(profile["chakra_reserve_bonus_percent"], 90)
        self.assertEqual(profile["stat_boosts"], {"Willpower": 14, "Chakra Control": 12})
        applied = apply_jinchuriki_start({"Willpower": 20, "Chakra Control": 20}, profile)
        self.assertEqual(applied, {"Willpower": 34, "Chakra Control": 32})
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("renderNarutoLineagePanel(special)", js)
        self.assertLess(js.index("renderNarutoLineagePanel(special)"), js.index("${hostCard}</section>"))
        self.assertIn("Host bonuses", js)
        self.assertIn("naruto_tailed_beasts_sprite.png", css)
        self.assertIn('.jinchuriki-beast-art[data-tails="9"]', css)

    def test_narrative_transfer_recovers_missing_jinchuriki_profile_once(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", name="Yahiko", turn=71, campaign_id="story-host",
                     stats={"Taijutsu": 100, "Ninjutsu": 150, "Genjutsu": 50,
                            "Chakra Control": 80, "Willpower": 70, "Intellect": 60},
                     resource=200, resource_max=200,
                     campaign_canon=[
                         {"turn": 64, "action": "Extract the Nine-Tails and seal it into myself.",
                          "outcome": "Kurama is sealed into Yahiko through an Uzumaki-derived ritual."},
                         {"turn": 70, "action": "Train with Kurama.",
                          "outcome": "Yahiko and Kurama establish a practiced combat partnership and shared combat timing."},
                     ])
        self.assertTrue(jinchuriki_story_evidence(state))
        normalize_world_progression(state)
        host = state["special"]["Jinchūriki Profile"]
        self.assertEqual(host["beast"], "Kurama")
        self.assertEqual(host["mastery"], "Cooperative")
        self.assertEqual(host["acquired_turn"], 64)
        self.assertEqual(state["stats"]["Willpower"], 82)
        self.assertEqual(state["stats"]["Chakra Control"], 85)
        self.assertEqual(state["resource_max"], 330)
        snapshot = copy.deepcopy(state)
        normalize_world_progression(state, snapshot)
        self.assertEqual(state["stats"], snapshot["stats"])
        self.assertEqual(state["resource_max"], snapshot["resource_max"])

    def test_special_form_changes_portrait_signature_then_returns_to_base(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", campaign_id="form-test", appearance_desc="A dark-haired shinobi")
        state["special"] = {"Dōjutsu Profile": {"name": "Pulseglass Eye", "category": "Dōjutsu", "stage": "Nascent"}}
        base = portrait_signature(state)
        self.assertTrue(sync_active_portrait_form(state, ["I activate my Pulseglass Eye"], "The eye awakens."))
        self.assertEqual(state["portrait_identity"]["active_form"]["name"], "Pulseglass Eye")
        self.assertNotEqual(portrait_signature(state), base)
        self.assertTrue(sync_active_portrait_form(state, ["I deactivate my dojutsu and return to normal"], "The eye closes."))
        self.assertEqual(state["portrait_identity"]["active_form"], {})
        self.assertEqual(portrait_signature(state), base)

    def test_lethal_combat_kills_by_default_and_mercy_is_explicit(self):
        game = GameSession()
        game.state["combat"] = {"active": True, "non_lethal": False, "spare_enemy": False,
                                "enemy": {"name": "Bandit", "hp": 1, "hp_max": 30, "alive": True}}
        game.end_combat("victory")
        self.assertTrue(game.state["combat"]["enemy_died"])
        self.assertFalse(game.state["combat"]["enemy"]["alive"])
        self.assertEqual(game.state["combat"]["enemy"]["hp"], 0)

        spared = GameSession()
        spared.state["combat"] = {"active": True, "spare_enemy": True,
                                   "enemy": {"name": "Rival", "hp": 1, "hp_max": 30, "alive": False}}
        spared.end_combat("victory")
        self.assertFalse(spared.state["combat"]["enemy_died"])
        self.assertTrue(spared.state["combat"]["enemy"]["alive"])
        self.assertEqual(spared.state["combat"]["enemy"]["hp"], 1)


if __name__ == "__main__":
    unittest.main()
