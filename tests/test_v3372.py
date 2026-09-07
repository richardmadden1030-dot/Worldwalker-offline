import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from canon_integrity import (CANON_IDENTITIES, canon_identity_context,
                             registry_audit, repair_canon_text)
from engine_campaign import CampaignMixin
from game import GameSession
from simulation_core import action_commits_violence, classify_action
from reliability import visible_class_profile
from state_guard import migrate_state
from worlds import APP_VERSION, BASE_STATE


class WorldwalkerV3372Tests(unittest.TestCase):
    def fresh(self, world="Bleach"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "Jabari Mizuno", "world": world, "difficulty": "Adventurer",
            "location": "Shin'o Academy", "campaign_id": "v3372-test",
            "opening_complete": True, "canon_day": 71,
        })
        game.campaign_active = True
        return game

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_duel_request_with_a_deep_bow_is_not_combat(self):
        action = "Take Tosens test then again request a witnessed duel with a deep bow"
        self.assertFalse(action_commits_violence(action))
        self.assertIn("social", classify_action(action)["kinds"])
        self.assertNotIn("violence", classify_action(action)["kinds"])

        game = self.fresh()
        assessment = game.assess_time_skip(1, "moment", action, "normal", use_model=False)["assessment"]
        self.assertEqual(assessment["checks"], [])
        self.assertFalse(assessment["requires_difficulty_confirmation"])
        data = {
            "narrative": "Tosen considers the respectful request.",
            "state_patch": {"combat": {"active": True, "enemy": {"name": "Deep Bow"}}},
        }
        self.assertFalse(game.ensure_immediate_combat_patch(data, [action]))
        self.assertNotIn("combat", data["state_patch"])
        self.assertIn("No concrete hostile act", data["combat_start_rejected"])

    def test_committed_attack_still_starts_combat(self):
        game = self.fresh()
        data = {"narrative": "Tosen draws his blade as the strike begins.", "state_patch": {}}
        action = "Challenge Tosen to a duel, then immediately attack Tosen"
        self.assertTrue(action_commits_violence(action))
        self.assertTrue(game.ensure_immediate_combat_patch(data, [action]))
        self.assertEqual(data["state_patch"]["combat"]["enemy"]["name"], "Tosen")

    def test_bleach_division_swap_is_repaired_but_correct_worded_ordinal_is_not(self):
        state = self.fresh().state
        fixed, repairs = repair_canon_text(
            "Bleach", "Kaname Tosen is Captain of the 5th Division.", state,
        )
        self.assertEqual(fixed, "Kaname Tosen is Captain of the 9th Division.")
        self.assertTrue(repairs)
        correct, repairs = repair_canon_text(
            "Bleach", "Sosuke Aizen remains captain of the Fifth Division.", state,
        )
        self.assertEqual(correct, "Sosuke Aizen remains captain of the Fifth Division.")
        self.assertEqual(repairs, [])
        appositive, repairs = repair_canon_text(
            "Bleach", "Kaoru records the **5th Division** and **Captain Kaname Tosen** as the target.", state,
        )
        self.assertIn("**9th Division**", appositive)
        self.assertTrue(repairs)

    def test_migration_flags_bad_old_chronicle_without_erasing_history(self):
        state = self.fresh().state
        state["story_log"] = [{"text": "Kaname Tosen is Captain of the 5th Division.", "tag": None}]
        state["campaign_canon"] = [{"outcome": "Kaname Tosen is Captain of the 5th Division."}]
        migrated = migrate_state(state)
        self.assertEqual(migrated["story_log"][0]["text"], state["story_log"][0]["text"])
        self.assertIn("9th Division", migrated["campaign_canon"][0]["outcome"])
        correction = "\n".join(migrated.get("_pending_chronicle_notes", []))
        self.assertIn("[CANON CORRECTION]", correction)
        self.assertIn("9th Division", correction)

    def test_every_canon_world_has_identity_locks(self):
        self.assertEqual(registry_audit(), [])
        for world, rows in CANON_IDENTITIES.items():
            query = rows[0]["name"]
            context = canon_identity_context(world, query, {"world": world, "canon_day": 0})
            self.assertIn(query, context, world)

    def test_placeholder_class_names_are_rejected(self):
        for name in ("Hidden Flash-related class", "Custom shadow themed ability", "Unnamed Class"):
            self.assertTrue(CampaignMixin.special_name_is_placeholder(name), name)
        self.assertFalse(CampaignMixin.special_name_is_placeholder("Afterclock Sealspace Covenant Path"))

    def test_concealed_class_affinity_is_a_clue_not_the_class_name(self):
        visible = visible_class_profile({
            "name": "Afterclock Sealspace Covenant Path",
            "discovery": {"concealed": True, "progress": 20,
                          "public_name": "Unidentified Flash Class",
                          "clue": "A dormant feature reacts to flash-aligned actions."},
        })
        self.assertEqual(visible["name"], "Unidentified Hidden Class — Flash affinity")
        self.assertIn("flash-aligned", visible["description"])


if __name__ == "__main__":
    unittest.main()
