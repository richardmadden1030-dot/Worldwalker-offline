"""Opt-in, repeatable quality evaluations for the configured narrator model."""
import copy
import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

from lore import format_lore_context
from worlds import BASE_STATE, WORLD_DATA, abilities_for
from simulation_core import (refresh_simulation_core, record_resolution_transaction,
                             companion_support_for_combat)
from util import DATA_DIR
from response_guard import normalize_turn_response
from gm_consistency import CONSISTENCY_RULE, prepare_request, outcome_assertions
from experience_systems import record_world_milestones, update_scenario_memory


EVAL_DIR = DATA_DIR / "evaluations"


def _evaluation_dir():
    try:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        return EVAL_DIR
    except OSError:
        # Read-only/test sandboxes should not make the whole application
        # unimportable merely because optional evaluation history cannot use
        # the normal roaming-data folder.
        fallback = Path(tempfile.gettempdir()) / "WorldwalkerRPG_evaluations"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

EVALUATION_SCENARIOS = [
    {"id": "conditional_watch", "name": "Conditional action does not start combat", "world": "Naruto",
     "action": "Watch the guard, but do not attack unless he threatens Konan. He has not threatened anyone.",
     "state": {"name": "Tester", "world": "Naruto", "location": "Gate", "combat": {"active": False}},
     "must_address": ["watch"], "outcome_assertions": [{"kind": "no_combat"}]},
    {"id": "failed_purchase", "name": "Refused purchase cannot award an item", "world": "One Piece",
     "action": "The seller has refused to sell the compass. Accept the refusal and leave without it.",
     "state": {"name": "Tester", "world": "One Piece", "inventory": []},
     "must_address": ["leave"], "outcome_assertions": [{"kind": "no_award", "field": "inventory", "name": "Compass"}]},
    {"id": "obedient_subordinate", "name": "Established subordinate follows the actual order", "world": "Reincarnated as a Slime",
     "action": "Order Rina to deliver this sealed invitation, without opening it or changing the terms.",
     "state": {"name": "Tester", "world": "Reincarnated as a Slime", "location": "Hall",
               "npc_memories": {"Rina": {"subordinate": True, "attitude": "Loyal"}},
               "scene_state": {"location": "Hall", "present": ["Rina"]}},
     "must_address": ["invitation"], "outcome_assertions": [{"kind": "no_unsupported_reaction"}]},
    {"id": "queued_actions", "name": "Multiple queued actions", "world": "Naruto",
     "action": "Travel to the training ground; ask Iruka about chakra control; practice until sunset.",
     "state": {"location": "Konohagakure", "world_time": "Morning", "stats": {"Chakra Control": 38}, "skills": {}},
     "must_address": ["travel", "iruka", "practice"], "expected_fields": ["location"], "lore_terms": ["chakra"]},
    {"id": "long_training", "name": "Long training proportionality", "world": "Hunter x Hunter",
     "action": "Train Ten and Ren consistently for thirty days with a qualified mentor.",
     "state": {"location": "Heaven's Arena", "world_time": "Day 12", "stats": {"Aura Control": 42}, "skills": {"Ten": {"rank": "Novice"}}},
     "must_address": ["thirty", "training", "mentor"], "expected_fields": ["skills", "training_log"], "lore_terms": ["nen", "aura"]},
    {"id": "canon_intervention", "name": "Canon intervention", "world": "One Piece",
     "action": "Warn the people of Marineford before the scheduled execution and try to change who arrives.",
     "state": {"location": "Marineford", "active_canon_event": "Portgas D. Ace's execution", "canon_divergences": []},
     "must_address": ["warn", "execution", "consequence"], "expected_fields": ["canon_divergences"], "lore_terms": ["marine"]},
    {"id": "hidden_class", "name": "Concealed hidden class", "world": "Overgeared",
     "action": "Examine the strange crafting intuition without knowing its true class name.",
     "state": {"location": "Winston", "class_profile": {"name": "Unidentified Hidden Class", "true_name": "Ashen Relic Smith", "discovery": {"concealed": True, "progress": 25}}},
     "must_address": ["examine", "clue"], "expected_fields": ["memory_updates"], "forbidden": ["ashen relic smith"]},
    {"id": "difficult_combat", "name": "Difficult combat realism", "world": "Bleach",
     "action": "A barely trained spirit-sensitive human attacks a Menos Grande head-on.",
     "state": {"location": "Karakura Town", "stats": {"Reiatsu Control": 18}, "combat": {}},
     "must_address": ["danger", "failure"], "expected_fields": ["combat", "hp"], "lore_terms": ["spiritual"]},
    {"id": "npc_secrecy", "name": "NPC knowledge boundary", "world": "Reincarnated as a Slime",
     "action": "Speak with a merchant who has never witnessed or heard about my concealed Unique Skill.",
     "state": {"location": "Dwargon", "skills": {"Hidden Devourer": {"hidden": True}},
               "npc_memories": {"Merchant Toma": {"knowledge": {"confirmed": [], "heard": [], "suspected": [], "false_beliefs": []}}}},
     "must_address": ["merchant"], "expected_fields": ["npc_memories"], "forbidden": ["hidden devourer"]},
    {"id": "solo_xp_title", "name": "Solo XP and title persistence", "world": "Solo Max-Level Newbie",
     "action": "Clear the Floor 1 hidden condition, collect the earned XP, and claim its title.",
     "state": {"location": "Floor 1", "level": 2, "xp": 40, "titles": [], "solo_system": {"floor": 1}},
     "must_address": ["hidden condition", "xp", "title"], "expected_fields": ["xp", "titles", "solo_system"], "lore_terms": ["system"]},
    {"id": "overgeared_xp_title", "name": "Overgeared XP and title persistence", "world": "Overgeared",
     "action": "Finish the named smithing commission, receive its XP, and record any earned production title.",
     "state": {"location": "Winston", "level": 3, "xp": 70, "titles": [], "known_recipes": ["Commissioned Iron Sword"]},
     "must_address": ["commission", "xp", "title"], "expected_fields": ["xp", "titles", "inventory"], "lore_terms": ["craft"]},
    {"id": "bleach_background_power", "name": "Bleach background power fidelity", "world": "Bleach",
     "action": "Have the examiner assess the immense spiritual pressure I was born with without pretending it means mastered control.",
     "state": {"location": "Shin'o Academy", "stats": {"Reiatsu Control": 72, "Willpower": 54}, "resource": 213,
               "special": {"Growth Profile": {"background_stat_reasons": ["The background establishes unusually high reiatsu control"]}}},
     "must_address": ["immense", "spiritual pressure", "control"], "expected_fields": ["special"], "lore_terms": ["reiatsu"],
     "forbidden": ["average spiritual pressure"]},
    {"id": "naruto_original_dojutsu", "name": "Original Dōjutsu parity", "world": "Naruto",
     "action": "Use the first awakened application of my original Dōjutsu to read the enemy's chakra rhythm.",
     "state": {"location": "Konohagakure", "special": {"Dōjutsu Profile": {"name": "Pulseglass Eye", "stage": "Nascent", "abilities": ["Reads repeating chakra rhythms"], "limitations": ["Eye strain and misleading irregular rhythms"], "non_canon_allowed": True}}},
     "must_address": ["pulseglass", "chakra rhythm", "strain"], "expected_fields": ["special"], "lore_terms": ["dōjutsu"],
     "forbidden": ["cannot exist because it is not canon"]},
    {"id": "custom_world_consistency", "name": "Custom-world rule continuity", "world": "Custom World",
     "action": "Use the previously established glass-song magic to reinforce the bridge without inventing a new power source.",
     "state": {"location": "Western March", "custom_world": "Magic comes only from resonating marked glass.", "skills": {"Glass-Song Brace": {"effect": "Resonates marked glass to reinforce a structure", "limitation": "Needs prepared glass marks"}}},
     "must_address": ["glass", "bridge", "mark"], "expected_fields": ["skills"], "forbidden": ["mana pool"]},
    {"id": "style_fidelity", "name": "Combat-style fidelity", "world": "One Piece",
     "action": "As a lifelong brawler, defeat the guard using my practiced style.",
     "state": {"location": "Loguetown", "stats": {"Strength": 58, "Agility": 44}, "skills": {},
               "special": {"Growth Profile": {"combat_style": "Brawler", "style_rule": "Uses fists, body movement and grappling"}}},
     "must_address": ["fist", "body", "guard"], "expected_fields": ["stats"], "forbidden": ["sword technique", "brawler fundamentals"]},
]


def list_evaluations():
    history = []
    for path in sorted(_evaluation_dir().glob("evaluation_*.json"), reverse=True)[:20]:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            history.append({"file": path.name, "created_at": row.get("created_at"), "model": row.get("model"),
                            "score": row.get("score"), "scenario_count": len(row.get("results", []))})
        except Exception:
            continue
    return {"scenarios": [{k: v for k, v in row.items() if k not in {"state"}} for row in EVALUATION_SCENARIOS], "history": history}


def run_local_simulation_evaluation():
    """Exercise core contracts in every world without an API/model call."""
    results = []
    for world in WORLD_DATA:
        state = copy.deepcopy(BASE_STATE)
        state["world"] = world
        state["stats"] = {name: 45 + index * 3 for index, name in enumerate(abilities_for(world))}
        state["resource_name"] = WORLD_DATA[world].get("resource", "Energy")
        state["skills"] = {"Signature Test Art": {
            "description": "A controlled world-valid technique used to test the simulation contract.",
            "effect": "Applies a precise controlled effect.", "limitation": "Consumes the world's normal resource.",
            "growth_path": "Refine precision and efficiency.", "combat_usable": True, "effect_type": "control",
        }}
        state["companions"] = [{"name": "Test Ally", "role": "Support", "combat_support": True}]
        state["npc_memories"] = {
            "Test Ally": {"goal": "Keep the player alive", "recurring": True, "last_known_location": "Starting Region"},
            "Test Nemesis": {"goal": "Complete a long-running scheme", "recurring": True, "nemesis": True},
        }
        state["location"] = "Starting Region"
        state["quests"] = [{"name": "Test Thread", "status": "Active", "next_hint": "Follow the established lead"}]
        refresh_simulation_core(state, ["Train the Signature Test Art through focused daily drills"], 43200)
        checks = {
            "capability": bool((state.get("capability_profile") or {}).get("power")),
            "ability_contract": bool(((state.get("ability_registry") or {}).get("Signature Test Art") or {}).get("mechanics", {}).get("counterplay")),
            "progression": (state.get("progression_calibration") or {}).get("expected_primary_gain", {}).get("typical", 0) > 0,
            "npc_continuity": bool((state.get("npc_continuity") or {}).get("Test Nemesis", {}).get("nemesis")),
            "companion_support": bool(companion_support_for_combat(state)),
            "story_thread": bool(state.get("story_threads")),
            "encounter_phase": (state.get("encounter_state") or {}).get("phase") == "idle",
        }
        before = copy.deepcopy(state)
        state["stats"][next(iter(state["stats"]))] += 2
        tx = record_resolution_transaction(state, before, ["Train the Signature Test Art"], 60, "Training produces a visible gain.", [])
        checks["resolution_pipeline"] = bool(tx.get("phases", {}).get("mechanics", {}).get("stat_changes"))
        malformed = normalize_turn_response({"narrative": "A valid beat.", "events": "A compact event",
                                             "updates": "A compact update", "state_patch": {"combat": {"enemy": "Test Rival"}}})
        checks["response_recovery"] = bool(malformed["events"] and malformed["updates"] and malformed["state_patch"]["combat"]["enemy"]["name"] == "Test Rival")
        combat_data = {"narrative": "The Test Rival attacks and combat begins.", "state_patch": {}, "events": []}
        state["combat"] = {"active": True, "enemy": {"name": "Test Rival"}, "cause": "Test Rival attacked",
                           "victory_condition": "End the attack", "defeat_risk": "Injury"}
        refresh_simulation_core(state, ["Defend against Test Rival"], 5, "Defend against Test Rival")
        update_scenario_memory(before, state, ["Defend against Test Rival"], combat_data)
        checks["scenario_memory"] = (state.get("scenario_memory") or {}).get("active", {}).get("kind") == "combat"
        # The detector must always be safe; worlds only record a milestone
        # when the phrasing is setting-relevant.
        record_world_milestones(state, {"narrative": "A meaningful campaign development is recorded.", "events": []})
        checks["milestone_detector"] = isinstance(state.get("world_milestones"), list)
        results.append({"world": world, "passed": sum(bool(v) for v in checks.values()),
                        "total": len(checks), "checks": checks})
    passed = sum(row["passed"] for row in results)
    total = sum(row["total"] for row in results)
    return {"kind": "local_simulation_core", "created_at": datetime.now().isoformat(timespec="seconds"),
            "score": round(100 * passed / max(1, total)), "passed": passed, "total": total,
            "worlds": results, "ai_calls": 0, "estimated_cost_usd": 0.0, "campaign_mutated": False}


def _text_blob(value):
    return json.dumps(value, ensure_ascii=False).lower()


def score_evaluation(scenario, response):
    criteria = []
    structured = isinstance(response, dict) and isinstance(response.get("narrative"), str) and isinstance(response.get("state_patch", {}), dict)
    criteria.append({"name": "Structured response", "score": 15 if structured else 0, "max": 15,
                     "detail": "Required narrative and state-patch fields are present." if structured else "Required JSON fields are missing."})
    if not isinstance(response, dict):
        return {"score": 0, "criteria": criteria}
    narrative = str(response.get("narrative") or "")
    clean = 80 <= len(narrative) <= 2400 and not re.search(r"Generated (Ability|Backstory|Class)|\[\s*\{|undefined|null", narrative, re.I)
    criteria.append({"name": "Readable narrative", "score": 15 if clean else 6 if narrative else 0, "max": 15,
                     "detail": "Narrative is readable and free of internal-generation labels." if clean else "Narrative is empty, unusually sized, or exposes internal formatting."})
    blob = _text_blob(response)
    addressed = [term for term in scenario.get("must_address", []) if term.lower() in blob]
    coverage = round(20 * len(addressed) / max(1, len(scenario.get("must_address", []))))
    criteria.append({"name": "Action coverage", "score": coverage, "max": 20,
                     "detail": f"Addressed {len(addressed)} of {len(scenario.get('must_address', []))} required action elements."})
    patch = response.get("state_patch") if isinstance(response.get("state_patch"), dict) else {}
    fields = scenario.get("expected_fields", [])
    present = [field for field in fields if field in patch]
    state_score = round(20 * len(present) / max(1, len(fields)))
    forbidden_owned = {"turn", "campaign_canon", "continuity_ledger", "narrative_memory", "progression_ledger"}.intersection(patch)
    if forbidden_owned: state_score = max(0, state_score - 8)
    criteria.append({"name": "State accuracy", "score": state_score, "max": 20,
                     "detail": f"Represented {len(present)} of {len(fields)} expected persistent outcomes" + (f"; illegally authored {', '.join(sorted(forbidden_owned))}." if forbidden_owned else ".")})
    forbidden = [term for term in scenario.get("forbidden", []) if term.lower() in blob]
    lore_found = [term for term in scenario.get("lore_terms", []) if term.lower() in blob]
    lore_score = 0 if forbidden else (15 if not scenario.get("lore_terms") or lore_found else 6)
    criteria.append({"name": "Lore and secrecy", "score": lore_score, "max": 15,
                     "detail": ("No forbidden reveal or lore violation detected." if not forbidden else "Revealed or used forbidden information: " + ", ".join(forbidden))})
    suggestions = response.get("suggested_actions") if isinstance(response.get("suggested_actions"), list) else []
    causal = bool(narrative.strip()) and len([x for x in suggestions if str(x).strip()]) >= 2
    criteria.append({"name": "Causality and continuation", "score": 15 if causal else 7 if patch else 0, "max": 15,
                     "detail": "Outcome offers usable continuation; quiet success need not mutate state." if causal else "Outcome lacks usable continuation."})
    checks = outcome_assertions(scenario, response)
    for check in checks:
        criteria.append({"name": "Outcome contract: " + check["name"], "score": 0, "max": 0,
                         "detail": "Passed" if check["passed"] else "FAILED: actual outcome contradicts scenario", "passed": check["passed"]})
    score = sum(row["score"] for row in criteria)
    if any(not check["passed"] for check in checks):
        score = min(49, score)
    return {"score": score, "criteria": criteria}


def run_model_evaluation(game, scenario_ids=None, client=None):
    selected_ids = set(scenario_ids or [EVALUATION_SCENARIOS[0]["id"]])
    scenarios = [row for row in EVALUATION_SCENARIOS if row["id"] in selected_ids]
    if not scenarios:
        raise ValueError("Choose at least one known evaluation scenario.")
    if client is None and not game.ai_ready():
        raise RuntimeError("Configure a narrator model before running a live evaluation.")
    client = client or game.make_client(game.settings.get("model", ""))
    before_usage = copy.deepcopy(getattr(client, "usage", {}))
    results = []
    for scenario in scenarios:
        instructions = (
            "You are being evaluated as the Worldwalker RPG narrator. Resolve the isolated scenario without changing any real campaign. "
            "Return one JSON object with narrative, state_patch, events, and suggested_actions. Address every action in order, preserve lore, "
            "respect what NPCs can personally know, and never write application-owned bookkeeping fields.\n\n" +
            format_lore_context(scenario["world"], scenario["action"], scenario["state"])
        )
        instructions += CONSISTENCY_RULE
        payload = {"evaluation": scenario["name"], "world": scenario["world"], "action": scenario["action"],
                   "state": scenario["state"], "required_output": {"narrative": "string", "state_patch": {}, "events": [], "suggested_actions": []}}
        payload = prepare_request(scenario["state"], payload)
        started = time.perf_counter()
        try:
            response = client.request(instructions, payload, timeout=240, max_output_tokens=900)
            scored = score_evaluation(scenario, response)
            results.append({"id": scenario["id"], "name": scenario["name"], "world": scenario["world"],
                            "score": scored["score"], "criteria": scored["criteria"], "duration_seconds": round(time.perf_counter() - started, 2),
                            "response_excerpt": str(response.get("narrative", ""))[:1200] if isinstance(response, dict) else ""})
        except Exception as exc:
            results.append({"id": scenario["id"], "name": scenario["name"], "world": scenario["world"], "score": 0,
                            "criteria": [{"name": "Model call", "score": 0, "max": 100, "detail": str(exc)[:800]}],
                            "duration_seconds": round(time.perf_counter() - started, 2), "error": str(exc)[:1000]})
    usage = getattr(client, "usage", {})
    usage_delta = {key: usage.get(key, 0) - before_usage.get(key, 0) for key in ("calls", "input_tokens", "output_tokens", "cost_usd")}
    report = {"created_at": datetime.now().isoformat(timespec="seconds"), "model": getattr(client, "model", game.settings.get("model", "")),
              "provider": getattr(client, "provider", game.settings.get("provider", "")),
              "score": round(sum(row["score"] for row in results) / len(results)), "results": results, "usage": usage_delta,
              "campaign_mutated": False}
    filename = "evaluation_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
    (_evaluation_dir() / filename).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["file"] = filename
    return report


def run_model_comparison(game, models, scenario_ids=None):
    """Run identical, isolated scenarios against several configured models.

    This is deliberately opt-in because it makes one paid call per model per
    scenario. The real campaign is never passed to or changed by the test.
    """
    clean_models = []
    for model in models or []:
        model = str(model or "").strip()
        if model and model not in clean_models:
            clean_models.append(model)
    if len(clean_models) < 2:
        raise ValueError("Enter at least two different model names to compare.")
    if len(clean_models) > 5:
        raise ValueError("Compare at most five models at a time to limit cost.")
    reports = [run_model_evaluation(game, scenario_ids, client=game.make_client(model)) for model in clean_models]
    ranking = sorted(({
        "model": row.get("model", ""),
        "score": row.get("score", 0),
        "duration_seconds": round(sum(float(item.get("duration_seconds", 0)) for item in row.get("results", [])), 2),
        "calls": row.get("usage", {}).get("calls", 0),
        "cost_usd": round(float(row.get("usage", {}).get("cost_usd", 0) or 0), 6),
    } for row in reports), key=lambda row: (-row["score"], row["cost_usd"], row["duration_seconds"]))
    for position, row in enumerate(ranking, 1):
        row["rank"] = position
    return {"reports": reports, "ranking": ranking, "campaign_mutated": False,
            "scenario_count": len(reports[0].get("results", [])) if reports else 0}
