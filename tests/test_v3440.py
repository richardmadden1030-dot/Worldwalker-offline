import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ai_client import AI, CLOUD_REQUEST_SOFT_TOKEN_CAP
from game import GameSession
from portrait_generator import (
    CANON_FORM_PORTRAITS,
    CANON_START_PORTRAITS,
    canon_form_portrait_url,
    canon_start_portrait_url,
    portrait_view,
)
from simulation_enhancements import apply_prompt_budget
from worlds import BASE_STATE


class TokenBudgetRegressionTests(unittest.TestCase):
    def test_long_campaign_prompt_budget_is_actually_enforced(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(turn=900, world="One Piece")
        huge = "A remembered scene with detailed dialogue. " * 900
        snapshot = copy.deepcopy(state)
        snapshot["npc_memories"] = {
            f"NPC {index}": {
                "history": [{"turn": turn, "detail": huge} for turn in range(25)],
                "confirmed_knowledge": [huge for _ in range(30)],
            }
            for index in range(45)
        }
        result = apply_prompt_budget(snapshot, state, "talk with NPC 44", "moment", "balanced")
        self.assertLessEqual(result["prompt_budget"]["estimated_characters"], 56_000)
        self.assertLessEqual(len(result.get("npc_memories", {})), 12)
        self.assertTrue(result["prompt_budget"]["trimmed"])

    def test_cloud_client_retries_token_limit_with_smaller_payload(self):
        class LimitedAI(AI):
            def __init__(self):
                super().__init__(key="test", model="gpt-5.6-luna", provider="cloud")
                self.sent = []

            def _responses_request(self, instructions, payload, timeout, max_output_tokens=700):
                self.sent.append((instructions, payload, max_output_tokens))
                if len(self.sent) == 1:
                    raise RuntimeError(
                        '/responses HTTP 429: Request too large for gpt-5.6-luna on tokens per min (TPM): '
                        'Limit 200000, Requested 216817. The input or output tokens must be reduced.'
                    )
                return {"narrative": "The saved turn continues."}

        ai = LimitedAI()
        payload = {"task": "resolve_time_skip", "state_before": {
            "name": "Traveler", "world": "One Piece", "location": "Harbor",
            "npc_memories": {f"NPC {i}": {"history": ["x" * 12_000 for _ in range(30)]} for i in range(30)},
        }}
        result = ai.request("Return JSON.", payload, max_output_tokens=2200)
        self.assertEqual(result["narrative"], "The saved turn continues.")
        self.assertEqual(len(ai.sent), 2)
        retry_instructions, retry_payload, retry_output = ai.sent[-1]
        self.assertLessEqual(ai._request_token_estimate(retry_instructions, retry_payload, retry_output), 60_000)
        self.assertGreaterEqual(ai.usage.get("request_compactions", 0), 1)
        self.assertEqual(CLOUD_REQUEST_SOFT_TOKEN_CAP, 80_000)


class PromptContractRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.game = GameSession(save_dir=root / "saves", settings_path=root / "settings.json")

    def test_outcome_contract_replaces_duplicate_drama_rules(self):
        prompt = self.game.task_rules("moment", "Negotiate a peaceful alliance")
        self.assertEqual(prompt.count("OUTCOME CONTRACT"), 1)
        for required in (
            "RESULT FIRST", "SEPARATE REACTION", "PROVE NEGATIVES", "LIMIT AWARENESS AND SCALE",
            "NO DEFAULT DISTRUST", "NO AUTOMATIC ESCALATION OR CANON GRAVITY", "ALLOW ENDINGS", "PRESERVE GAINS",
        ):
            self.assertIn(required, prompt)
        self.assertNotIn("NPC and faction reactions require awareness", prompt)
        self.assertNotIn("Most ordinary successful actions should resolve positively or neutrally", prompt)

    def test_support_jobs_do_not_receive_the_full_narrator_prompt(self):
        moment = self.game.task_rules("moment", "Train with a mentor")
        assessment = self.game.task_rules("assessment", "Train with a mentor")
        time_plan = self.game.task_rules("time_plan", "Train with a mentor")
        combat = self.game.task_rules("combat_summary")
        continuity = self.game.task_rules("continuity_audit")
        self.assertLess(len(assessment), len(moment) // 3)
        self.assertLess(len(time_plan), len(moment) // 3)
        self.assertLess(len(combat), 2_000)
        self.assertLess(len(continuity), 1_000)
        self.assertNotIn("recurring_finances", assessment)
        self.assertNotIn("Starting a quest requires", assessment)

    def test_nightmare_keeps_strict_feasibility_but_same_causality(self):
        self.game.state["difficulty"] = "Nightmare"
        prompt = self.game.task_rules("moment", "Demand the impossible")
        self.assertIn("Nightmare remains strict", prompt)
        self.assertIn("PROVE NEGATIVES", prompt)
        self.assertIn("PRESERVE GAINS", prompt)


class ApprovedPortraitRegressionTests(unittest.TestCase):
    def naruto_state(self, active_form=None):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", player_identity={"canon_character_id": "naruto_graduation"})
        state["portrait_identity"] = {"active_form": active_form or {}}
        return state

    def test_approved_canon_start_portrait_is_bundled(self):
        self.assertEqual(canon_start_portrait_url(self.naruto_state()), "/assets/canon_portraits/naruto_graduation.webp")

    def test_every_approved_canon_portrait_file_is_present(self):
        portrait_root = ROOT / "assets" / "canon_portraits"
        missing = [filename for filename in CANON_START_PORTRAITS.values() if not (portrait_root / filename).is_file()]
        for form_entries in CANON_FORM_PORTRAITS.values():
            missing.extend(filename for _pattern, filename in form_entries if not (portrait_root / filename).is_file())
        self.assertEqual(missing, [])

    def test_approved_eight_gates_stages_select_matching_art(self):
        cases = {
            "Fifth Gate": "naruto_eight_gates_1_to_5.png",
            "Seventh Gate": "naruto_eight_gates_6_to_7.png",
            "Eighth Gate, Gate of Death": "naruto_eighth_gate_death.png",
        }
        for form_name, expected in cases.items():
            state = self.naruto_state({"name": form_name, "kind": "Eight Gates", "details": "Active"})
            self.assertTrue(canon_form_portrait_url(state).endswith(expected), form_name)
            view = portrait_view(state, {"portrait_generation_enabled": True, "portrait_auto_generate": True})
            self.assertTrue(view["_portrait_canon"])
            self.assertFalse(view["_portrait_auto_generate"])

    def test_original_eight_gates_user_keeps_identity_specific_generation(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", player_identity={"canon_character_id": ""})
        state["portrait_identity"] = {"active_form": {"name": "Seventh Gate", "kind": "Eight Gates"}}
        self.assertIsNone(canon_form_portrait_url(state))


if __name__ == "__main__":
    unittest.main()
