"""Safe campaign repairs and privacy-conscious support bundles."""
import copy
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from reliability import validate_campaign_state
from systems import normalize_quest_state_machine, campaign_health
from util import ai_text
from knowledge import knowledge_snapshot
from causality import causality_snapshot
from lore import lore_library_status


SENSITIVE_KEYS = {"api_key", "local_token", "authorization", "password", "pass", "secret", "token"}


def _sensitive_key(key):
    low = str(key).lower()
    return low in SENSITIVE_KEYS or low.endswith("_token") or low.endswith("_key") or "password" in low


def sanitize_for_support(value):
    """Remove credentials and replace local user paths without hiding game facts."""
    if isinstance(value, dict):
        return {str(k): ("<REDACTED>" if _sensitive_key(k) else sanitize_for_support(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_support(x) for x in value]
    if isinstance(value, tuple):
        return [sanitize_for_support(x) for x in value]
    if isinstance(value, str):
        text = value
        home = str(Path.home())
        if home: text = text.replace(home, "<USER_HOME>")
        text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+", r"\1<REDACTED>", text)
        text = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1<REDACTED>", text)
        return text
    return value


def repair_campaign_state(state, repair_id="safe_all"):
    """Apply only deterministic repairs that cannot invent story outcomes."""
    applied = []
    requested = {repair_id}
    if repair_id == "safe_all":
        requested = {"map_current_location", "normalize_quests", "describe_skills", "remove_deceased_companions", "deduplicate_rewards"}
    if "repair_scene" in requested:
        from campaign_reliability import refresh_scene_state
        before = copy.deepcopy(state.get("scene_state", {}))
        refresh_scene_state(state, {}, [])
        if state.get("scene_state", {}) != before:
            applied.append("Rebuilt the current scene identity from the campaign's real location and context.")
    if "repair_combat" in requested:
        combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
        if combat.get("active"):
            enemy = combat.get("enemy")
            if not isinstance(enemy, dict):
                name = ai_text(enemy) or "Current opponent"
                baseline = max(10, int(max((state.get("stats") or {}).values(), default=20) * .65))
                combat["enemy"] = {"name":name, "is_group":False, "group_size":None, "hp":baseline * 2,
                                   "hp_max":baseline * 2, "difficulty_min":35, "difficulty_max":55,
                                   "attack_min":30, "attack_max":50, "power":baseline, "alive":True}
                applied.append("Rebuilt a malformed combat opponent without changing the encounter outcome.")
            else:
                hp_max = max(1, int(enemy.get("hp_max", enemy.get("hp", 1)) or 1))
                enemy["hp_max"] = hp_max; enemy["hp"] = max(0, min(hp_max, int(enemy.get("hp", hp_max) or 0)))
                enemy.setdefault("alive", enemy["hp"] > 0)
                combat["round"] = max(1, int(combat.get("round", 1) or 1))
                applied.append("Normalized the active combatant, HP, and round state.")
        elif state.get("combat") not in ({}, None) and not isinstance(state.get("combat"), dict):
            state["combat"] = {}; applied.append("Cleared an unreadable inactive combat record.")
    if "repair_progression" in requested:
        from world_progression import normalize_world_progression
        from lit_systems import initialize_lit_systems
        normalize_world_progression(state); initialize_lit_systems(state)
        state["hp_max"] = max(1, int(state.get("hp_max", state.get("hp", 1)) or 1))
        state["hp"] = max(0, min(state["hp_max"], int(state.get("hp", state["hp_max"]) or 0)))
        state["resource_max"] = max(0, int(state.get("resource_max", state.get("resource", 0)) or 0))
        state["resource"] = max(0, min(state["resource_max"], int(state.get("resource", state["resource_max"]) or 0)))
        applied.append("Reconciled world progression, levels, pools, and special-system records.")
    if "repair_abilities" in requested:
        from simulation_core import normalize_ability_registry
        normalize_ability_registry(state)
        requested.add("describe_skills")
        applied.append("Rebuilt the ability registry from the character's established skills and special powers.")
    if "repair_social" in requested:
        from simulation_core import normalize_npc_continuity
        normalize_npc_continuity(state)
        requested.add("remove_deceased_companions")
        applied.append("Reconciled named NPC continuity, relationships, and active party membership.")
    if "repair_world" in requested:
        from simulation_core import refresh_simulation_core
        refresh_simulation_core(state, [], 0, "Campaign recovery")
        requested.add("map_current_location")
        applied.append("Rebuilt world threads, location continuity, and local simulation indexes.")
    if "map_current_location" in requested:
        location = str(state.get("location") or "").strip()
        if location and location not in state.setdefault("discovered_locations", []):
            state["discovered_locations"].append(location); applied.append(f"Added {location} to discovered locations.")
    if "normalize_quests" in requested:
        before = copy.deepcopy(state.get("quests", []))
        for quest in state.get("quests", []):
            if isinstance(quest, dict) and not (quest.get("objectives") or quest.get("clear_conditions")):
                quest["objectives"] = [{"id": "obj-1", "text": quest.get("first_step") or "Discover the quest's concrete completion requirements.",
                                        "status": "active", "optional": False, "progress": 0}]
            if isinstance(quest, dict) and not (quest.get("next_hint") or quest.get("first_step")):
                quest["next_hint"] = "Investigate the most immediate known lead and ask what would count as completion."
        normalize_quest_state_machine(state)
        if state.get("quests", []) != before: applied.append("Normalized quest objectives, progress, and next leads.")
    if "describe_skills" in requested:
        changed = 0
        for name, skill in list((state.get("skills") or {}).items()):
            if not isinstance(skill, dict):
                state["skills"][name] = {"rank": "Known", "bonus": 0, "description": f"A known capability called {name}; its exact limits remain to be established through use."}; changed += 1
            elif not (skill.get("description") or skill.get("effect")):
                skill["description"] = f"A known capability called {name}; its exact limits remain to be established through use."; changed += 1
        if changed: applied.append(f"Added readable descriptions to {changed} skill(s).")
    if "remove_deceased_companions" in requested:
        dead = {name for name, memory in (state.get("npc_memories") or {}).items()
                if isinstance(memory, dict) and str(memory.get("status", "")).lower() in {"dead", "deceased"}}
        before_count = len(state.get("companions", []))
        state["companions"] = [c for c in state.get("companions", []) if ai_text(c.get("name") if isinstance(c, dict) else c) not in dead]
        removed = before_count - len(state["companions"])
        if removed: applied.append(f"Removed {removed} deceased character(s) from the active party.")
    if "deduplicate_rewards" in requested:
        for key in ("titles", "achievements"):
            seen, clean = set(), []
            for item in state.get(key, []):
                label = ai_text(item.get("name") if isinstance(item, dict) else item).strip().lower()
                if label and label not in seen:
                    seen.add(label); clean.append(item)
            if len(clean) != len(state.get(key, [])):
                applied.append(f"Removed {len(state.get(key, [])) - len(clean)} duplicate {key}.")
                state[key] = clean
    record = {"time": datetime.now().isoformat(timespec="seconds"), "turn": state.get("turn", 0),
              "repair_id": repair_id, "applied": applied, "remaining_warnings": validate_campaign_state(state, state)}
    state.setdefault("health_repairs", []).append(record)
    state["health_repairs"] = state["health_repairs"][-100:]
    return record


def build_diagnostic_bundle(game):
    diagnostics = game.diagnostics_snapshot()
    state = copy.deepcopy(game.state)
    diagnostics["campaign_health"] = campaign_health(state)
    diagnostics["npc_knowledge"] = knowledge_snapshot(state)
    diagnostics["causality"] = causality_snapshot(state)
    diagnostics["lore_status"] = lore_library_status(state.get("world", "Custom World"))
    settings = copy.deepcopy(game.settings)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": diagnostics.get("app_version"), "schema_version": state.get("schema_version"),
        "campaign": {"name": state.get("name"), "world": state.get("world"), "turn": state.get("turn")},
        "privacy": "Credentials and user-home paths were redacted automatically.",
        "files": ["manifest.json", "diagnostics.json", "campaign_state.json", "recent_story.json", "settings.json", "README.txt"],
    }
    files = {
        "manifest.json": manifest,
        "diagnostics.json": diagnostics,
        "campaign_state.json": state,
        "recent_story.json": (game.story_log or [])[-100:],
        "settings.json": settings,
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, json.dumps(sanitize_for_support(value), indent=2, ensure_ascii=False))
        archive.writestr("README.txt", "Worldwalker support bundle\n\nThis archive was generated locally. API keys, tokens, passwords, and user-home paths were redacted. It contains campaign state and recent story text so a bug can be reproduced. Review it before sharing if your campaign narrative contains personal information.\n")
    stream.seek(0)
    return stream
