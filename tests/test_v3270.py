import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from jjk_system import (advance_jjk_state, generate_birth_slot, initialize_jjk_state,
                        normalize_birth_slot_package)
from game import GameSession
from worlds import BASE_STATE, abilities_for
from util import scene_image_url


def jjk_state(slot=None, origin="Tokyo Jujutsu High — First Year", background=""):
    state = copy.deepcopy(BASE_STATE)
    state.update({
        "world":"Jujutsu Kaisen", "name":"Aoi", "background":background,
        "stats":{name:55 for name in abilities_for("Jujutsu Kaisen")},
        "special":{"Origin":origin}, "skills":{}, "affiliations":[], "reputation":{},
    })
    slot = slot or generate_birth_slot("A technique based on sound", seed="v323")
    initialize_jjk_state(state, slot, origin)
    return state


class WorldwalkerV3270JjkDepthTests(unittest.TestCase):
    def test_jjk_starting_gear_is_not_mislabeled_as_a_weapon(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Jujutsu Kaisen")}
        profile = game.infer_starting_profile(
            "Jujutsu Kaisen", "Tokyo Jujutsu High — First Year", "Jujutsu Sorcerer",
            "A new student with a sound technique.", stats, start_location="Tokyo Jujutsu High",
        )
        self.assertIn("Field Gear", profile["equipment"])
        self.assertNotIn("Weapon", profile["equipment"])

    def test_jjk_creation_and_preview_use_clear_labels(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('world === "Jujutsu Kaisen" ? "Starting Placement" : "Starting Location"', source)
        self.assertIn("Starting attributes", source)
        self.assertNotIn("Open-ended starting abilities", source)

    def test_ai_rename_rebuilds_the_whole_technique_package(self):
        fallback = generate_birth_slot("A shadow technique", seed="old")
        updated = normalize_birth_slot_package({
            "name":"Glass Horizon", "governing_rule":"Refraction redirects cursed energy that crosses a visible glass plane",
        }, fallback)
        self.assertEqual(updated["name"], "Glass Horizon")
        self.assertTrue(all("shadow" not in (row["name"] + row["effect"]).lower() for row in updated["applications"]))
        self.assertIn("Glass Horizon", updated["domain_profile"]["sure_hit"])

    def test_black_flash_requires_an_eligible_confirmed_impact(self):
        state = jjk_state()
        before = copy.deepcopy(state)
        notes = advance_jjk_state(state, before, ["Study barrier theory"], "A decorative sign reads Black Flash.", [], 60)
        self.assertEqual(state["jjk_system"]["black_flash_count"], 0)
        before = copy.deepcopy(state)
        notes = advance_jjk_state(state, before, ["Punch the curse and align cursed energy for Black Flash"], "The impact becomes a Black Flash.", [], 5)
        self.assertEqual(state["jjk_system"]["black_flash_count"], 1)
        self.assertEqual(state["jjk_system"]["black_flash"]["in_the_zone_turns"], 3)
        self.assertTrue(any("BLACK FLASH" in note for note in notes))

    def test_explicit_progression_unlocks_barriers_rct_maximum_and_domain(self):
        state = jjk_state()
        for name, value in (("Barrier Arts",54), ("Reverse Cursed Technique",59), ("Maximum Technique",69), ("Domain Expansion",99)):
            state["jjk_system"]["progression"][name]["mastery"] = value
        before = copy.deepcopy(state)
        notes = advance_jjk_state(
            state, before,
            ["Train barrier arts and Simple Domain", "Master Reverse Cursed Technique with positive energy", "Develop my Maximum Technique", "Complete my Domain Expansion and sure-hit barrier"],
            "Months of exacting instruction produce coherent breakthroughs.", [], 30 * 1440,
        )
        self.assertIn("Simple Domain", state["skills"])
        self.assertIn("Reverse Cursed Technique", state["skills"])
        self.assertNotEqual(state["jjk_system"]["maximum_technique"], "Unachieved")
        self.assertNotEqual(state["jjk_system"]["domain_status"], "Unachieved")
        self.assertTrue(any("DOMAIN AWAKENED" in note for note in notes))

    def test_binding_vow_terms_persist(self):
        state = jjk_state()
        before = copy.deepcopy(state)
        advance_jjk_state(state, before, ["I form a binding vow: give up using my technique at night to gain double output at noon"], "The binding vow takes hold.", [], 5)
        vow = state["jjk_system"]["binding_vows"][0]
        self.assertEqual(vow["status"], "Active")
        self.assertTrue(vow["price"])
        self.assertTrue(vow["benefit"])
        self.assertTrue(vow["breach"])

    def test_heavenly_restriction_uses_physical_path_not_domain(self):
        slot = generate_birth_slot("I have zero cursed energy and a complete Heavenly Restriction", True, seed="hr")
        state = jjk_state(slot)
        state["jjk_system"]["heavenly_restriction_mastery"]["body"] = 69
        before = copy.deepcopy(state)
        advance_jjk_state(state, before, ["Train my body, speed, senses and cursed tool mastery"], "The restriction's body adapts.", [], 30 * 1440)
        self.assertIn("Air-Step Footwork", state["skills"])
        self.assertEqual(state["jjk_system"]["domain_status"], "Unachieved")
        self.assertNotIn("Domain Expansion", state["skills"])

    def test_grade_record_uses_real_missions_and_separates_recommendation(self):
        state = jjk_state()
        state["stats"] = {name:90 for name in state["stats"]}
        state["quests"] = [{"name":"Hospital Curse", "status":"Active"}]
        before = copy.deepcopy(state)
        state["quests"][0]["status"] = "Completed"
        state["jjk_system"]["grade_record"].update(missions_completed=4, difficult_exorcisms=3)
        advance_jjk_state(state, before, [], "The Grade 1 curse is exorcised and the mission is complete.", [], 5)
        record = state["jjk_system"]["grade_record"]
        self.assertEqual(record["missions_completed"], 5)
        self.assertIn("Grade 1", record["promotion_recommendation"])
        self.assertEqual(state["special"]["Grade"], "Unassessed")

    def test_technique_use_records_witness_exposure(self):
        state = jjk_state()
        skill = next(name for name, row in state["skills"].items() if row.get("parent_technique"))
        state["combat"] = {"active":True, "enemy":{"name":"Clever Curse"}}
        before = copy.deepcopy(state)
        advance_jjk_state(state, before, [f"Use {skill} against the curse"], "The curse survives and studies the effect.", [], 5)
        observed = state["jjk_system"]["technique_exposure"]["witnesses"]["Clever Curse"]
        self.assertTrue(any(skill in fact for fact in observed))

    def test_curse_feeding_counts_multiple_victims_and_public_infamy(self):
        state = jjk_state(origin="Sentient Cursed Spirit")
        before = copy.deepcopy(state)
        advance_jjk_state(state, before, ["Hunt"], "The curse killed 12 humans and consumed their fear.", [], 60)
        self.assertEqual(state["jjk_system"]["humans_killed"], 12)
        self.assertGreater(state["jjk_system"]["feeding_growth"], 12)
        self.assertNotEqual(state["jjk_system"]["curse_development"]["public_assessment"], "Unregistered")

    def test_great_clan_and_vessel_soul_are_concrete(self):
        clan_state = jjk_state(origin="Great Clan Member", background="I was born into the Kamo Clan.")
        self.assertEqual(clan_state["jjk_system"]["clan"]["name"], "Kamo Clan")
        self.assertTrue(clan_state["jjk_system"]["clan"]["obligations"])
        self.assertTrue(any(row.get("faction") == "Kamo Clan" for row in clan_state["affiliations"]))
        vessel_state = copy.deepcopy(BASE_STATE)
        vessel_state.update(world="Jujutsu Kaisen", name="Yuji", background="", stats={name:50 for name in abilities_for("Jujutsu Kaisen")}, special={"Origin":"Tokyo Jujutsu High — First Year", "Vessel":"Ryomen Sukuna"}, affiliations=[], reputation={})
        initialize_jjk_state(vessel_state, {"slot_type":"Vessel Physiology", "name":"Ryomen Sukuna", "governing_rule":"Contains an incarnated soul", "applications":[]}, vessel_state["special"]["Origin"])
        self.assertEqual(vessel_state["jjk_system"]["soul"]["occupants"][0]["name"], "Ryomen Sukuna")

    def test_journal_exposes_every_new_record(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for label in ("DOMAIN DEVELOPMENT", "BINDING VOWS", "TECHNIQUE INTELLIGENCE", "CLAN POSITION", "SOUL & POSSESSION", "CURSED SPIRIT DEVELOPMENT"):
            self.assertIn(label, source)

    def test_dedicated_jjk_scene_art_is_optimized_and_selected(self):
        assets = {
            "jjk_cursed_hospital.webp":"Abandoned Cursed Hospital",
            "jjk_subway_tunnel.webp":"Underground Subway Station",
            "jjk_clan_estate.webp":"Kamo Estate",
            "jjk_domain_interior.webp":"Tokyo Jujutsu High",
        }
        for filename, location in assets.items():
            path = ROOT / "assets" / "generated_scenes" / filename
            self.assertTrue(path.exists(), filename)
            self.assertLess(path.stat().st_size, 250_000)
            state = jjk_state()
            state["location"] = location
            if filename == "jjk_domain_interior.webp":
                state["current_activity"] = "Domain Expansion manifests its sure-hit"
            url, _ = scene_image_url(state)
            self.assertTrue(url.endswith(filename), (filename, url))


if __name__ == "__main__":
    unittest.main()
