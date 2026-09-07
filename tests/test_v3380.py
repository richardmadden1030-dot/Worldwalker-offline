import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from jjk_system import advance_jjk_state, generate_birth_slot, initialize_jjk_state, resolve_domain_clash
from lit_systems import build_floor_state, process_lit_turn
from world_activity import activity_rules_for, advance_world_activity, normalize_world_activity
from worlds import BASE_STATE, abilities_for
from worlds import APP_VERSION


def state_for(world):
    state = copy.deepcopy(BASE_STATE)
    state.update({"world":world, "name":"Depth Tester", "campaign_id":f"v338-{world}", "turn":4,
                  "special":{}, "skills":{}, "quests":[], "relationships":{}, "stats":{}})
    return state


class WorldwalkerV3380DepthTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_prompt_router_includes_only_relevant_one_piece_rule(self):
        compact = activity_rules_for("One Piece", "message", "incoming crew message")
        bounty = activity_rules_for("One Piece", "moment", "A Marine officer raises my bounty")
        haki = activity_rules_for("One Piece", "moment", "Train Observation Haki")
        self.assertLess(len(compact), 250)
        self.assertIn("bounty", bounty.lower())
        self.assertNotIn("campaign-original island", bounty.lower())
        self.assertIn("haki mastery", haki.lower())
        self.assertNotIn("bounty change", haki.lower())

    def test_one_piece_arc_and_causal_bounty_history(self):
        state = state_for("One Piece")
        state.update(location="Original Lantern Island", special={"Bounty":1000})
        normalize_world_activity(state)
        self.assertGreaterEqual(len(state["special"]["Island Arc"]["conclusions"]), 3)
        before = copy.deepcopy(state)
        state["special"]["Bounty"] = 5000
        state["special"]["Bounty Cause"] = {"act":"Liberated the harbor", "notoriety":"Public celebration", "government_threat":"Removed an allied ruler"}
        advance_world_activity(state, before, ["Liberate the harbor"], "The ruler falls.")
        cause = state["world_activity"]["one_piece"]["bounty"]["history"][-1]
        self.assertEqual(cause["act"], "Liberated the harbor")
        self.assertEqual(cause["government_threat"], "Removed an allied ruler")

    def test_hxh_tracks_each_principle_and_vow(self):
        state = state_for("Hunter x Hunter")
        normalize_world_activity(state)
        before = copy.deepcopy(state)
        notes = advance_world_activity(state, before, ["Train Gyo for seven days", "I vow to use my Hatsu only while protecting someone"], "The training and vow take hold.", elapsed_minutes=10080)
        hx = state["world_activity"]["hunter_x_hunter"]
        self.assertEqual(set(hx["nen_principles"]), {"Ten","Zetsu","Ren","Gyo","En","Shu","Ko","Ken","Ryu","Hatsu"})
        self.assertGreater(hx["nen_principles"]["Gyo"]["mastery"], 0)
        self.assertEqual(hx["nen_principles"]["Hatsu"]["mastery"], 0)
        self.assertTrue(hx["vows"])
        self.assertTrue(any("NEN VOW" in row for row in notes))

    def test_naruto_career_is_not_power_only_and_beast_remembers(self):
        state = state_for("Naruto")
        state["special"] = {"Shinobi Rank":"Genin", "Jinchūriki Profile":{"beast":"Kurama", "bond_progress":10}}
        normalize_world_activity(state)
        career = state["special"]["Shinobi Career"]
        self.assertIn("combat_power_is_not_rank", career["promotion_factors"])
        before = copy.deepcopy(state)
        advance_world_activity(state, before, ["I listen to Kurama and thank the beast"], "Kurama recognizes the respect.")
        bond = state["world_activity"]["naruto"]["tailed_beast_relationship"]
        self.assertGreater(bond["trust"], 10)

    def test_solo_floor_package_and_overgeared_behavior_evolution(self):
        floor = build_floor_state(20)
        self.assertIn("Murim", floor["name"])
        self.assertTrue(floor["factions"])
        self.assertIn("personality", floor["administrator"])
        state = state_for("Overgeared")
        state.update(level=10, xp=0, xp_next=100, currency={"amount":100,"name":"Gold"}, special={"Archetype":"Explorer", "Satisfy Profile":{"primary_class":"Pathfinder", "class_type":"Exploration / Utility"}})
        before = copy.deepcopy(state)
        process_lit_turn(before, state, ["Explore and map the hidden valley"], "A hidden road is charted.", 30 * 1440)
        routes = state["overgeared_system"]["class_behavior"]["routes"]
        self.assertTrue(routes)

    def test_slime_and_bleach_records(self):
        slime = state_for("Reincarnated as a Slime")
        slime["special"] = {"Evolution Profile":{"species":"Slime", "stage":"Awakened", "evolution_requirements":["Magicules"]}, "Named Subordinates":{"Ranga":{"role":"Guard captain"}}}
        normalize_world_activity(slime)
        self.assertEqual(slime["world_activity"]["slime"]["evolution"]["species"], "Slime")
        self.assertIn("Ranga", slime["world_activity"]["slime"]["subordinates"])
        bleach = state_for("Bleach")
        bleach["special"] = {"Squad":"Division 4", "Zanpakuto Profile":{"name":"Kuroshio", "spirit":"Black tide"}}
        bleach["skills"] = {"Hadō #31: Shakkahō":{"bonus":22, "incantation_knowledge":"Complete"}}
        normalize_world_activity(bleach)
        activity = bleach["world_activity"]["bleach"]
        self.assertEqual(activity["zanpakuto_relationship"]["name"], "Kuroshio")
        self.assertIn("31", activity["kido_reference"]["Hado"])
        self.assertIn("Healing", activity["duty"]["division_culture"]["identity"])

    def test_jjk_disclosure_bonus_vows_and_domain_clash(self):
        state = state_for("Jujutsu Kaisen")
        state["stats"] = {name:60 for name in abilities_for("Jujutsu Kaisen")}
        slot = generate_birth_slot("A momentum-storing technique", seed="v338-disclosure")
        initialize_jjk_state(state, slot, "Tokyo Jujutsu High — First Year")
        state["combat"] = {"active":True, "enemy":{"name":"Test Curse", "power":55}}
        before = copy.deepcopy(state)
        notes = advance_jjk_state(state, before, ["I explain my technique rule to Test Curse"], "The curse understands how the technique stores momentum.", [], 5)
        disclosure = state["jjk_system"]["technique_disclosure"]
        self.assertEqual(disclosure["active_bonus"], 10)
        self.assertTrue(any("REVEALING ONE'S HAND" in row for row in notes))
        clash = resolve_domain_clash({"refinement":90,"barrier_integrity":80,"output":75,"range":30,"compatibility":60}, {"refinement":50,"barrier_integrity":50,"output":55,"range":20,"compatibility":50})
        self.assertEqual(clash["outcome"], "Player domain prevails")

    def test_long_event_title_layout_is_flow_based(self):
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("Keep the cinematic copy in normal document flow", css)
        self.assertIn(".canon-cinematic .event-window-notice h3{", css)
        self.assertIn("overflow-wrap:anywhere", css)


if __name__ == "__main__":
    unittest.main()
