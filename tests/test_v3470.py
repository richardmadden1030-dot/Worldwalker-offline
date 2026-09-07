"""Persistent organizations, narrative recruitment and independent life progression."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from worlds import BASE_STATE, abilities_for
from organizations import (LABELS, ensure_organizations, group_id, apply_updates, advance_lives,
    process_organizations, roster_view, organization_context, organization_issues, command_chain)
from gm_consistency import command_contracts, prepare_request
from state_guard import migrate_state
from game import GameSession


def fresh(world="Naruto", group="River Squad"):
    s = copy.deepcopy(BASE_STATE)
    s.update(world=world, name="Ari", turn=5, canon_day=0, canon_time_minutes=0,
             opening_complete=True, stats={k: 40 for k in abilities_for(world)},
             affiliations=[{"faction": group, "rank": "Captain", "status": "active"}],
             faction_rosters={group: ["Ari", "Rina", "Mira"]}, companions=[{"name": "Rina"}],
             npc_memories={"Rina": {"role": "Deputy", "age": 20, "stats": {k: 40 for k in abilities_for(world)}},
                           "Mira": {"role": "Medic", "age": 16, "power_score": 30, "last_known_location": "Distant island"}})
    ensure_organizations(s)
    return s


def event(s, kind, name="Rina", **fields):
    group = next(iter(s["organizations"].values()))["name"]
    data = {"organization_updates": [{"group": group, "event": kind, "name": name,
                                      "reason": "Established in the current scene", **fields}]}
    apply_updates(s, data)
    return data


def tick(s, days):
    before = copy.deepcopy(s)
    s["canon_time_minutes"] += days * 1440
    s["canon_day"] = int(s["canon_time_minutes"] // 1440)
    return process_organizations(before, s, {}, days * 1440)


class RosterTests(unittest.TestCase):
    def test_every_world_has_native_label(self):
        for world, expected in LABELS.items():
            with self.subTest(world=world):
                self.assertEqual(roster_view(fresh(world, "River Company"))["label"], expected)
        self.assertEqual(roster_view(fresh("One Piece", "Marine 4th Unit"))["label"], "Marine Squad")
        self.assertEqual(roster_view(fresh("Naruto", "Akatsuki"))["label"], "Shinobi Organization")

    def test_all_members_remain_after_companions_removed(self):
        s = fresh(); s["companions"] = []
        rows = roster_view(s)["groups"][0]["members"]
        self.assertEqual({r["name"] for r in rows}, {"Ari", "Rina", "Mira"})
        self.assertEqual(next(r for r in rows if r["name"] == "Mira")["position"], "Medic")

    def test_large_roster_has_no_scene_cap_but_prompt_does(self):
        s = fresh(); group = next(iter(s["organizations"].values()))
        for n in range(120): group["members"][f"Sailor {n}"] = {"name": f"Sailor {n}", "status": "active"}
        self.assertEqual(len(roster_view(s)["groups"][0]["members"]), 123)
        context = organization_context(s, "Ask Sailor 119 about training")
        self.assertLessEqual(len(context["groups"][0]["members"]), 16)
        self.assertIn("Sailor 119", {r["name"] for r in context["groups"][0]["members"]})

    def test_no_fake_unknown_power_and_no_hidden_power_leak(self):
        s = fresh(); s["npc_memories"]["Mira"] = {"role": "Civilian doctor"}
        row = next(r for r in roster_view(s)["groups"][0]["members"] if r["name"] == "Mira")
        self.assertIsNone(row["power"]["score"])
        s["npc_memories"]["Rina"]["power_known"] = False
        row = next(r for r in roster_view(s)["groups"][0]["members"] if r["name"] == "Rina")
        self.assertIsNone(row["power"]["score"])

    def test_malformed_and_string_legacy_members(self):
        s = fresh(); s["organizations"] = {"bad": "string", "empty": {"members": ["bad"]}}
        s["organization_lives"] = "bad"; s["companions"] = ["Mira", 12, None, {"name": "Rina"}]
        self.assertTrue(roster_view(s)["groups"])

    def test_migration_and_view_do_not_rewrite_source(self):
        s = fresh(); s.pop("organizations"); s.pop("organization_lives")
        before = copy.deepcopy(s); roster_view(s)
        self.assertEqual(s, before)
        migrated = migrate_state(s)
        self.assertTrue(migrated["organizations"])
        self.assertEqual(roster_view(json.loads(json.dumps(migrated))), roster_view(migrated))

    def test_former_affiliation_does_not_create_active_membership(self):
        s = fresh(); s["organizations"] = {}; s["faction_rosters"] = {}; s["companions"] = []
        s["affiliations"][0]["status"] = "former"
        self.assertEqual(roster_view(s)["groups"], [])


class CommandAndMembershipTests(unittest.TestCase):
    def test_hierarchy_independent_ally_and_cycles(self):
        s = fresh(); event(s, "position", "Mira", position="Medic", reports_to="Rina")
        contracts = command_contracts(s, "Tell Mira to care for the children")
        self.assertEqual(contracts[0]["via"], ["Rina"])
        event(s, "position", "Mira", independent=True)
        self.assertEqual(command_contracts(s, "Tell Mira to care for the children"), [])
        event(s, "position", "Mira", independent=False)
        event(s, "position", "Rina", reports_to="Mira")
        self.assertEqual(command_contracts(s, "Order Mira to train"), [])

    def test_invite_is_not_join_and_departure_cannot_be_undone_by_stale_rows(self):
        s = fresh(); event(s, "invite", "Toma", position="Navigator")
        event(s, "join", "Toma", accepted=False)
        group = next(iter(s["organizations"].values()))
        self.assertEqual(group["members"]["Toma"]["status"], "candidate")
        self.assertFalse(command_contracts(s, "Order Toma to sail"))
        event(s, "join", "Toma", accepted=True, terms="Share discoveries", loyalty_basis="Rescued his family")
        self.assertTrue(command_contracts(s, "Order Toma to sail"))
        event(s, "leave", "Toma")
        s["faction_rosters"][group["name"]].append("Toma")
        s["companions"].append({"name": "Toma", "subordinate": True})
        ensure_organizations(s)
        self.assertEqual(group["members"]["Toma"]["status"], "left")
        self.assertFalse(command_contracts(s, "Order Toma to sail"))

    def test_new_companion_does_not_implicitly_join_existing_roster(self):
        s = fresh(); s["companions"].append({"name": "Visitor"})
        event(s, "invite", "Visitor")
        self.assertEqual(next(iter(s["organizations"].values()))["members"]["Visitor"]["status"], "candidate")

    def test_death_propagates_and_cannot_recruit_dead_member(self):
        s = fresh(); event(s, "death", "Rina"); event(s, "join", "Rina", accepted=True)
        self.assertFalse(s["npc_memories"]["Rina"]["alive"])
        self.assertEqual(next(iter(s["organizations"].values()))["members"]["Rina"]["status"], "dead")

    def test_legacy_subordinate_keeps_authority_without_inventing_group_leader(self):
        s = fresh(); s["organizations"] = {}; s["affiliations"] = []; s["faction_rosters"] = {}
        s["npc_memories"]["Rina"]["subordinate"] = True
        self.assertTrue(command_contracts(s, "Tell Rina to deliver the letter"))

    def test_query_schema_and_invalid_agreement(self):
        s = fresh(); payload = prepare_request(s, {"action": "Recruit a navigator"})
        self.assertIn("organization_context", payload)
        self.assertIn("organization_updates", json.dumps(payload))
        self.assertTrue(organization_issues(s, {"organization_updates": [{"event": "join", "group": "River Squad", "name": "Toma"}]}))


class LifeTests(unittest.TestCase):
    def test_training_uses_npc_not_player_power_and_reloads(self):
        s = fresh(); event(s, "development", activity="Practice Taijutsu", discipline="Taijutsu")
        strong = copy.deepcopy(s); strong["stats"] = {k: 900000 for k in strong["stats"]}
        tick(s, 180); tick(strong, 180)
        self.assertEqual(s["npc_memories"]["Rina"]["stats"], strong["npc_memories"]["Rina"]["stats"])
        self.assertGreater(s["npc_memories"]["Rina"]["stats"]["Taijutsu"], 40)
        self.assertEqual(s["companions"][0]["stats"], s["npc_memories"]["Rina"]["stats"])
        before = copy.deepcopy(s["npc_memories"]); advance_lives(s, 180*1440)
        self.assertEqual(before, s["npc_memories"])
        s = json.loads(json.dumps(s)); tick(s, 30)
        self.assertGreater(s["npc_memories"]["Rina"]["stats"]["Taijutsu"], strong["npc_memories"]["Rina"]["stats"]["Taijutsu"])

    def test_short_and_long_ticks_match(self):
        s = fresh(); event(s, "development", activity="Practice Taijutsu", discipline="Taijutsu")
        short = copy.deepcopy(s); tick(s, 60)
        for _ in range(240): tick(short, .25)
        self.assertEqual(s["npc_memories"]["Rina"]["stats"], short["npc_memories"]["Rina"]["stats"])

    def test_noncombat_idle_and_incapacitated_do_not_gain_combat(self):
        for activity, discipline, condition in [("Study medicine", "Medicine", ""), ("Wait at home", "Taijutsu", ""), ("Practice Taijutsu", "Taijutsu", "Unconscious")]:
            with self.subTest(activity=activity, condition=condition):
                s = fresh(); event(s, "development", activity=activity, discipline=discipline)
                s["npc_memories"]["Rina"]["condition"] = condition; tick(s, 90)
                self.assertEqual(s["npc_memories"]["Rina"]["stats"]["Taijutsu"], 40)

    def test_age_unknown_spiritual_and_correction(self):
        s = fresh(); event(s, "life", "Mira", aging_mode="spiritual")
        event(s, "join", "Toma", accepted=True); tick(s, 360*5)
        self.assertEqual(s["npc_memories"]["Rina"]["age"], 25)
        self.assertEqual(s["npc_memories"]["Mira"]["age"], 16)
        self.assertNotIn("age", s["npc_memories"]["Toma"])
        s["npc_memories"]["Rina"]["age"] = 30; tick(s, 1)
        self.assertEqual(s["npc_memories"]["Rina"]["age"], 30)

    def test_family_maturity_without_inherited_power_or_duplicate_birth_reset(self):
        s = fresh(); event(s, "birth", "Nori", parents=["Ari", "Rina"])
        event(s, "life", "Nori", maturity_age=18, mentor="Mira")
        tick(s, 360*18); event(s, "birth", "Nori", parents=["Ari", "Rina"])
        self.assertEqual(s["npc_memories"]["Nori"]["age"], 18)
        self.assertEqual(s["organization_lives"]["Nori"]["stage"], "adult")
        self.assertNotIn("stats", s["npc_memories"]["Nori"])

    def test_only_accepted_succession_after_explicit_retirement(self):
        s = fresh(); group = next(iter(s["organizations"].values()))
        event(s, "succession_plan", accepted=False); tick(s, 3600)
        self.assertEqual(group["leader"], "Ari")
        event(s, "succession_plan", accepted=True); advance_lives(s, 0)
        self.assertEqual(group["leader"], "Ari")
        event(s, "retire", "Ari"); advance_lives(s, 0)
        self.assertEqual(group["leader"], "Ari")
        event(s, "retire", "Ari", accepted=True)
        self.assertEqual(len(advance_lives(s, 0)), 1)
        self.assertEqual(group["leader"], "Rina")
        self.assertEqual(s["name"], "Ari")
        self.assertFalse(command_contracts(s, "Order Mira to guard the house"))
        self.assertFalse(advance_lives(s, 0))
        self.assertEqual(s["affiliations"][0]["status"], "former")

    def test_existing_narrated_training_gain_is_not_awarded_twice(self):
        s = fresh(); event(s, "development", activity="Practice Taijutsu", discipline="Taijutsu")
        before = copy.deepcopy(s)
        s.update(canon_day=30, canon_time_minutes=30*1440)
        s["npc_memories"]["Rina"]["stats"]["Taijutsu"] = 100
        process_organizations(before, s, {}, 30*1440)
        self.assertEqual(s["npc_memories"]["Rina"]["stats"]["Taijutsu"], 100)

    def test_missing_heir_does_not_trigger_succession(self):
        s = fresh(); event(s, "succession_plan", accepted=True)
        group = next(iter(s["organizations"].values()))
        group["members"]["Rina"]["status"] = "missing"
        event(s, "retire", "Ari", accepted=True)
        self.assertFalse(advance_lives(s, 0))
        self.assertEqual(group["leader"], "Ari")

    def test_secondary_former_membership_does_not_stop_active_training(self):
        s = fresh(); event(s, "development", activity="Practice Taijutsu", discipline="Taijutsu")
        s["organizations"]["old"] = {"id": "old", "name": "Old Squad", "members": {"Rina": {"name": "Rina", "status": "left"}}}
        tick(s, 60)
        self.assertGreater(s["npc_memories"]["Rina"]["stats"]["Taijutsu"], 40)

    def test_real_time_skip_updates_roster_and_lives(self):
        g = GameSession(); g.state = fresh(); g.autosave = lambda *a, **kw: None
        result = g.apply_time_skip({"narrative": "Rina practices Taijutsu through the month.", "state_patch": {},
            "organization_updates": [{"group": "River Squad", "event": "development", "name": "Rina", "activity": "Practice Taijutsu", "discipline": "Taijutsu", "reason": "A month of agreed practice"}]}, 1, "months")
        self.assertGreater(g.state["npc_memories"]["Rina"]["stats"]["Taijutsu"], 40)
        self.assertIn("_organization_roster", g.public_state())


if __name__ == "__main__": unittest.main()
