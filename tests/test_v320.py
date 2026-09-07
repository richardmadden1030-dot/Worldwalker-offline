import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import app as app_module
import evaluations
from causality import advance_causal_clock, causality_snapshot
from engine_core import CoreMixin
from evaluations import run_model_evaluation, score_evaluation
from knowledge import normalize_npc_knowledge, knowledge_snapshot
from lore import _normalized_entry, detect_lore_conflicts, retrieve_lore
from support import build_diagnostic_bundle, repair_campaign_state, sanitize_for_support
from systems import campaign_health
from worlds import APP_VERSION, BASE_STATE


class FakeEvalClient:
    model = "test-model"
    provider = "local"
    def __init__(self): self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    def request(self, instructions, payload, **kwargs):
        self.usage.update(calls=self.usage["calls"] + 1, input_tokens=self.usage["input_tokens"] + 100,
                          output_tokens=self.usage["output_tokens"] + 80)
        action = payload["action"]
        return {"narrative": f"The action resolves clearly: {action} The consequences and danger are made concrete through world rules.",
                "state_patch": {"location": payload["state"].get("location", ""), "skills": payload["state"].get("skills", {}),
                                "training_log": [], "canon_divergences": [], "memory_updates": {}, "combat": {}, "hp": 50,
                                "npc_memories": payload["state"].get("npc_memories", {})},
                "events": [], "suggested_actions": ["Follow the lead", "Prepare", "Ask a witness"]}


class WorldwalkerV320Tests(unittest.TestCase):
    def test_version_schema_and_owned_reliability_ledgers(self):
        self.assertEqual(APP_VERSION, "3.64.0")
        self.assertEqual(BASE_STATE["schema_version"], 21)
        for key in ("causality_ledger", "knowledge_audit", "health_repairs"):
            self.assertIn(key, BASE_STATE)

    def test_lore_conflicts_choose_the_more_authoritative_source(self):
        official = _normalized_entry({"title": "Rule", "text": "Official", "source": "Volume 10", "source_type": "official_source", "claims": {"can fly": "Only with wings"}})
        forum = _normalized_entry({"title": "Rule", "text": "Forum", "source": "Thread", "source_type": "forum", "claims": {"can fly": "Anyone can fly"}})
        conflict = detect_lore_conflicts([forum, official])[0]
        self.assertEqual(conflict["resolution"], "Only with wings")
        self.assertEqual(conflict["authority"], 100)

    def test_builtin_lore_is_normalized_with_curated_authority(self):
        entry = retrieve_lore("Naruto", "learn chakra nature", {}, 1)[0]
        self.assertEqual(entry["source_type"], "curated")
        self.assertGreater(entry["authority"], 70)

    def test_unsupported_secret_knowledge_becomes_suspicion(self):
        state = copy.deepcopy(BASE_STATE)
        state["class_profile"] = {"name": "Moon Sovereign", "true_name": "Moon Sovereign", "discovery": {"concealed": True, "progress": 10}}
        state["npc_memories"] = {"Mira": {"knowledge": {"confirmed": [{"fact": "You are the Moon Sovereign", "source": "unknown"}]}}}
        changes = normalize_npc_knowledge(state, {}, "test")
        self.assertEqual(len(changes), 1)
        self.assertFalse(state["npc_memories"]["Mira"]["knowledge"]["confirmed"])
        self.assertIn("Moon Sovereign", state["npc_memories"]["Mira"]["knowledge"]["suspected"][0]["fact"])

    def test_witnessed_secret_knowledge_remains_confirmed(self):
        state = copy.deepcopy(BASE_STATE)
        state["class_profile"] = {"name": "Moon Sovereign", "discovery": {"concealed": True, "progress": 10}}
        state["npc_memories"] = {"Mira": {"knowledge": {"confirmed": [{"fact": "Your class is Moon Sovereign", "source": "witnessed: awakening"}]}}}
        normalize_npc_knowledge(state, {}, "test")
        self.assertEqual(len(state["npc_memories"]["Mira"]["knowledge"]["confirmed"]), 1)

    def test_ai_snapshot_contains_boundaries_and_concealed_facts(self):
        core = CoreMixin()
        core.state = copy.deepcopy(BASE_STATE)
        core.state["class_profile"] = {"name": "Secret Class", "discovery": {"concealed": True, "progress": 10}}
        core.state["npc_memories"] = {"Mira": {"knowledge": {"confirmed": ["The player arrived today"]}}}
        normalize_npc_knowledge(core.state, {}, "test")
        snapshot = core.trimmed_state_for_ai()
        self.assertIn("npc_knowledge_boundaries", snapshot)
        self.assertIn("concealed_player_facts", snapshot)

    def test_causal_clock_blocks_for_travel_and_resources(self):
        state = copy.deepcopy(BASE_STATE)
        clock = {"goal": "Raid the archive", "method": "covert raid", "target_location": "Archive",
                 "travel_remaining_days": 3, "resources": {"intel": 1}, "resource_cost": {"intel": 2}}
        delta = advance_causal_clock(state, "Night Guild", clock, 8, 1, "faction")
        self.assertEqual(delta, 0)
        self.assertIn("travel day", clock["blocked_reason"])
        self.assertIn("needs 2 intel", clock["blocked_reason"])
        self.assertEqual(len(state["causality_ledger"]), 1)

    def test_causal_clock_consumes_resources_after_arrival(self):
        state = copy.deepcopy(BASE_STATE)
        clock = {"goal": "Open the gate", "method": "bribery", "target_location": "Gate",
                 "travel_remaining_days": 1, "resources": {"coin": 5}, "resource_cost": {"coin": 2}}
        delta = advance_causal_clock(state, "Agent", clock, 10, 2, "npc")
        self.assertEqual(delta, 10)
        self.assertEqual(clock["resources"]["coin"], 3)
        self.assertEqual(clock["current_location"], "Gate")

    def test_safe_campaign_repairs_are_conservative_and_audited(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(location="Konoha Market", discovered_locations=[], skills={"Mystery Art": {}},
                     titles=["Hero", "Hero"], quests=[{"name": "Find the Scout", "status": "Active"}])
        record = repair_campaign_state(state, "safe_all")
        self.assertIn("Konoha Market", state["discovered_locations"])
        self.assertTrue(state["skills"]["Mystery Art"]["description"])
        self.assertEqual(state["titles"], ["Hero"])
        self.assertTrue(state["quests"][0]["objectives"])
        self.assertTrue(record["applied"])
        self.assertEqual(len(state["health_repairs"]), 1)

    def test_campaign_health_offers_specific_safe_repairs(self):
        state = copy.deepcopy(BASE_STATE)
        state["location"] = "Unmapped Camp"
        health = campaign_health(state)
        issue = next(row for row in health["issues"] if row["area"] == "Map")
        self.assertEqual(issue["repair_id"], "map_current_location")
        self.assertTrue(issue["repairable"])

    def test_support_sanitizer_removes_secrets_and_home_paths(self):
        value = sanitize_for_support({"api_key": "sk-secret", "nested": {"local_token": "abc"}, "path": str(Path.home() / "save.json")})
        self.assertEqual(value["api_key"], "<REDACTED>")
        self.assertEqual(value["nested"]["local_token"], "<REDACTED>")
        self.assertIn("<USER_HOME>", value["path"])

    def test_support_bundle_contains_required_sanitized_files(self):
        class FakeGame:
            state = copy.deepcopy(BASE_STATE)
            settings = {"api_key": "sk-secret", "model": "test"}
            story_log = [{"text": "Recent beat"}]
            def diagnostics_snapshot(self): return {"app_version": "3.3.0", "system_log": []}
        stream = build_diagnostic_bundle(FakeGame())
        with zipfile.ZipFile(stream) as archive:
            self.assertTrue({"manifest.json", "diagnostics.json", "campaign_state.json", "recent_story.json", "settings.json", "README.txt"}.issubset(archive.namelist()))
            settings = json.loads(archive.read("settings.json"))
            self.assertEqual(settings["api_key"], "<REDACTED>")

    def test_live_evaluation_uses_isolated_scenarios_without_mutation(self):
        class FakeGame:
            settings = {"model": "test-model", "provider": "local"}
            state = {"untouched": True}
            def ai_ready(self): return True
        game = FakeGame(); before = copy.deepcopy(game.state)
        with tempfile.TemporaryDirectory() as temp, patch.object(evaluations, "EVAL_DIR", Path(temp)):
            report = run_model_evaluation(game, ["queued_actions"], FakeEvalClient())
            self.assertEqual(game.state, before)
            self.assertFalse(report["campaign_mutated"])
            self.assertEqual(report["usage"]["calls"], 1)
            self.assertTrue((Path(temp) / report["file"]).exists())

    def test_api_and_frontend_expose_v320_surfaces(self):
        app_module.game.state = copy.deepcopy(BASE_STATE)
        with app_module.app.test_client() as client:
            panels = client.get("/api/panels").get_json()
            self.assertIn("npc_knowledge", panels)
            self.assertIn("causality", panels)
            self.assertIn("lore_status", panels)
            self.assertIn("evaluations", panels)
            bundle = client.get("/api/diagnostics/bundle")
            self.assertEqual(bundle.status_code, 200)
            self.assertEqual(bundle.mimetype, "application/zip")
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8") + (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("data-health-repair", "data-eval-run", "NPC KNOWLEDGE BOUNDARIES", "/api/diagnostics/bundle"):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
