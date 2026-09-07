"""Authoritative validation for AI-authored campaign state patches.

The GM may propose any world-consistent outcome, but it cannot directly write
application-owned fields, change the clock outside Advance, or corrupt the save
shape. Every accepted/rejected field is recorded for Diagnostics.
"""
import copy
import re
from datetime import datetime

from util import merge, ai_text
from worlds import BASE_STATE, DIFFICULTIES, WORLD_DATA, abilities_for, expansion_for
from knowledge import normalize_npc_knowledge
from bleach_data import CANON_HADO, CANON_BAKUDO
from world_progression import normalize_world_progression
from age_system import initialize_age_tracking
from world_depth import normalize_world_depth
from lit_systems import initialize_lit_systems
from skill_system import normalize_skill_map
from ability_mechanics import compile_ability_mechanics
from power_benchmarks import benchmark_tier
from politics import normalize_political_state
from simulation_core import refresh_simulation_core
from campaign_features import normalize_companion_combinations, normalize_trophy_state
from canon_integrity import normalize_canon_integrity
from world_activity import normalize_world_activity
from long_campaign import pre_advance_health_check
from systems import ensure_currency_state


def _repair_legacy_local_messages(state):
    """Unwrap v3.41 local messages that narrated their own delivery.

    Chat already displays the thread, sender and date.  Older local messages
    repeated all of that inside the body (``A messenger arrives from X: …``),
    which looked like the sender was quoting the game's event-card title.
    Only rows explicitly marked as locally generated are changed.
    """
    repaired = 0
    threads = state.get("chat_threads")
    if not isinstance(threads, dict):
        return repaired
    pattern = re.compile(r"^A\s+.+?\s+arrives\s+from\s+.+?:\s*[“\"](.+?)[”\"]\s*$", re.I | re.S)
    for rows in threads.values():
        messages = rows.get("messages") if isinstance(rows, dict) else rows
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict) or not isinstance(message.get("metadata"), dict):
                continue
            if not message["metadata"].get("generated_locally"):
                continue
            text = ai_text(message.get("text") or message.get("message"))
            match = pattern.match(text.strip())
            if match:
                clean = match.group(1).strip()
                if "text" in message:
                    message["text"] = clean
                else:
                    message["message"] = clean
                repaired += 1
    return repaired

def _compile_skill_mechanics(state):
    skills = normalize_skill_map(state.get("skills", {}))
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    numeric_stats = [value for value in stats.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    tier = benchmark_tier(state.get("world", "Custom World"), max(numeric_stats, default=30)).get("index", 2)
    compiled = {}
    for name, detail in skills.items():
        package = compile_ability_mechanics(state.get("world", "Custom World"), {"name": name, **detail}, tier)
        package.pop("name", None); compiled[name] = package
    state["skills"] = compiled


APP_OWNED = {
    "adventures", "travel_access", "_world_calendar",
    "character_paths", "world_conflict", "expeditions", "canon_interventions",
    "organization_command", "public_reputation", "property_economy",
    "team_membership_offers", "team_membership_engine_version", "team_membership_truth_started_turn",
    "official_party_group_id", "naruto_squad_assignment",
    "_request_receipts", "_recovery_guard",
    'relationship_life',
    'atlas_start_day',
    "turn", "campaign_id", "campaign_created_version", "campaign_last_saved_version",
    "schema_version", "validation_log", "diagnostics", "last_autosave",
    # Mechanically maintained bookkeeping (continuity.py, systems.py, the
    # canon-timeline firing logic) — the GM sees these in "state" for context
    # but must never author them itself. Without this guard a model that
    # mimics the shape of its own context can duplicate a campaign_canon
    # entry the mechanical system is about to append anyway, and a weaker
    # local model burning its limited output budget re-typing these back
    # verbatim is a real contributor to truncated, invalid JSON.
    "campaign_canon", "continuity_ledger", "chapter_summaries", "chapter_buffer", "world_plans", "world_benefits",
    "verified_memory_archive", "memory_consolidation", "consequence_ledger",
    "canon_events_fired", "pending_minor_events",
    # Fixed once at campaign creation to whatever start_day this campaign
    # actually began on (a canon character's birth, a chosen starting era,
    # or the world default) — every calendar date shown for the rest of the
    # campaign is computed relative to it. It has no type validation of its
    # own (BASE_STATE's default is None), so a model that echoes it back
    # from context could silently corrupt every date in the campaign.
    "calendar_anchor_day", "last_protagonist_tick_day", "active_canon_event",
    # Deterministic pacing bookkeeping (systems.tick_world_clocks/pacing_guidance)
    # and the player's own standing preference field — both set only through
    # their own dedicated mechanism/endpoint, never through the GM's own
    # narrated state_patch.
    "last_major_beat_day", "director_notes",
    # The permanent "why reputation moved" trail (continuity.py) — the GM
    # supplies a one-line reason via reputation_chain_events each turn, but
    # never authors the accumulated faction_chain history directly.
    "faction_chain",
    # The permanent, app-owned purchase-offer ledger (systems.py) — the GM
    # supplies a one-turn purchase_offer, but never authors the resolved
    # flag or ids in purchase_offers directly.
    "purchase_offers", "currency_ledger", "finance_debts", "canon_integrity_repairs",
    # Only the player's own rating action (engine_journal.rate_last_turn_good)
    # writes this — never the GM.
    "rated_good_turns", "narrative_memory", "progression_ledger", "causality_ledger", "knowledge_audit", "health_repairs",
    "npc_intentions", "simulation_events", "local_background_turn", "standing_intents",
    # Acknowledgement of an ongoing dangerous scene is maintained locally.
    # The narrator can conclude a scene through its response flag, but cannot
    # forge or erase the stored warning state through state_patch.
    "danger_scenario",
    # v3.4 deterministic simulation records. The narrator may describe
    # inputs for these systems, but only local code may author their ledgers.
    "action_goals", "correction_log", "authoritative_corrections",
    "information_packets", "npc_schedules", "canon_event_states",
    "simulation_validation",
    "campaign_direction", "relationship_opportunities", "last_cause_effect", "last_training_summary", "last_ai_route",
    "campaign_arcs", "campaign_arc_archive", "campaign_arc_director", "campaign_arc_context",
    "scene_state", "scene_history", "last_outcome_scale", "outcome_scale_ledger",
    "obligation_ledger", "delayed_consequences", "canon_divergence_impacts", "pacing_profile",
    "player_style_profile", "lore_confidence_log", "fact_history",
    "overgeared_system", "solo_system", "jjk_system", "world_depth",
    "capability_profile", "ability_registry", "progression_calibration", "npc_continuity",
    "encounter_state", "story_threads", "scenario_memory", "world_milestones", "resolution_ledger", "simulation_core_version", "world_activity",
    "last_failed_turn", "recovery_timeline", "last_combat", "standing_order_state", "memory_tiers",
    "settled_stories", "last_command_context",
    "organizations", "organization_lives",
    "legacy_trophies", "dismissed_trophy_ids", "downtime_surprise_state", "message_delivery_state",
    "companion_autonomy", "npc_development", "ability_evolution", "world_downtime_cycles", "prompt_budget_log",
}
TIME_OWNED = {"world_time", "world_clock_minutes", "calendar", "canon_time_minutes", "canon_day"}
FLEXIBLE_TYPES = {"age", "current_activity", "position"}

NESTED_DICT_FIELDS = {
    "stats", "hidden_stats", "skills", "class_profile", "equipment", "relationships",
    "reputation", "special", "contacts", "chat_threads", "combat", "portrait_identity",
    "growth_profile", "background_details", "npc_memories", "npc_clocks", "faction_clocks",
    "difficulty_controls", "progression_preset", "overgeared_system", "solo_system", "jjk_system", "world_depth",
    "polity_state", "downtime_surprise_state", "message_delivery_state", "world_activity", "memory_consolidation",
    "scene_state", "last_outcome_scale", "canon_divergence_impacts", "pacing_profile", "player_style_profile", "scenario_memory", "last_failed_turn",
    "companion_autonomy", "npc_development", "ability_evolution", "world_downtime_cycles",
    "last_combat", "standing_order_state", "memory_tiers",
}
NESTED_LIST_FIELDS = {
    "titles", "inventory", "quests", "hidden_quests", "quest_archive", "affiliations",
    "companions", "codex", "status", "conditions", "known_recipes", "training_log",
    "active_encounters", "achievements", "travel_history", "loot_history", "queued_actions",
    "standing_orders", "suggested_actions", "prerequisite_tracks", "lore_sources",
    "political_regions", "companion_combinations", "trophy_proposals", "legacy_trophies", "dismissed_trophy_ids",
    "verified_memory_archive", "consequence_ledger",
    "currency_ledger", "finance_debts",
    "scene_history", "outcome_scale_ledger", "obligation_ledger", "delayed_consequences", "lore_confidence_log",
    "prompt_budget_log", "world_milestones", "recovery_timeline",
}


def _safe_number(value, default=0, minimum=None):
    if isinstance(value, bool):
        result = default
    elif isinstance(value, (int, float)):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"\s*[-+]?\d+(?:\.\d+)?\s*", value):
        result = float(value)
    else:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    return int(result) if float(result).is_integer() else float(result)


_NPC_MEMORY_RESPONSE_KEYS = {
    "elapsed", "goal_status", "memory_updates", "new_contacts", "information_events",
    "completed_actions", "deferred_actions", "suggested_actions", "interrupted",
    "interruption_kind", "interruption_reason", "interruption_context", "intervention_prompt",
    "danger_scenario_concluded", "major_event_reached", "major_event_kind",
    "major_event_title", "active_major_event", "incoming_chats", "simulation_scale",
}


def normalize_npc_memory_map(raw):
    """Keep only named NPC/group dossiers in the NPC-memory namespace.

    A truncated model response can accidentally place the rest of its response
    object inside ``npc_memories``.  Those keys are valid JSON and therefore
    survived older type checks, bloating context and eventually exposing
    consumers to unrelated strings/lists.  Real entries are always objects;
    app-state and response-envelope labels can be removed deterministically.
    """
    if not isinstance(raw, dict):
        return {}
    reserved = {str(key).casefold() for key in BASE_STATE}
    reserved.update(key.casefold() for key in _NPC_MEMORY_RESPONSE_KEYS)
    clean = {}
    for name, detail in raw.items():
        label = str(name or "").strip()
        if not label or label.casefold() in reserved or not isinstance(detail, dict):
            continue
        clean[label] = copy.deepcopy(detail)
    return clean


def _repair_nested_shapes(state):
    """Repair common malformed nested AI/save values before consumers read them."""
    repairs = []
    for key in NESTED_DICT_FIELDS:
        if not isinstance(state.get(key), dict):
            state[key] = copy.deepcopy(BASE_STATE.get(key, {})) if isinstance(BASE_STATE.get(key), dict) else {}
            repairs.append(f"Repaired invalid {key} object")
    for key in NESTED_LIST_FIELDS:
        if not isinstance(state.get(key), list):
            state[key] = copy.deepcopy(BASE_STATE.get(key, [])) if isinstance(BASE_STATE.get(key), list) else []
            repairs.append(f"Repaired invalid {key} list")
    cleaned_memories = normalize_npc_memory_map(state.get("npc_memories"))
    if cleaned_memories != state.get("npc_memories"):
        removed = max(0, len(state.get("npc_memories", {})) - len(cleaned_memories))
        state["npc_memories"] = cleaned_memories
        repairs.append(f"Removed {removed} misplaced value(s) from NPC memories")
    allowed_stats = set(abilities_for(state.get("world", "Custom World")))
    state["stats"] = {
        str(name): _safe_number(value, 1, 1)
        for name, value in state.get("stats", {}).items()
        if name in allowed_stats and not isinstance(value, (dict, list, bool))
    }
    for key in ("level", "xp", "xp_next", "hp", "hp_max", "resource", "resource_max", "turn", "world_clock_minutes", "canon_day"):
        if key in state:
            minimum = 1 if key in {"level", "xp_next", "hp_max", "resource_max"} else None
            state[key] = _safe_number(state.get(key), BASE_STATE.get(key, 0), minimum)
    return repairs


def normalize_combat_payload(raw):
    """Return a safe structured combat object for saves and AI patches.

    Smaller models sometimes use the convenient JSON shorthand
    ``{"enemy": "Tunnel Guard"}``. That is meaningful input, but combat
    consumers require an object. Normalize it at the trust boundary instead
    of allowing a later ``enemy.get(...)`` call to strand the campaign.
    """
    if not isinstance(raw, dict):
        return {}
    combat = copy.deepcopy(raw)
    enemy = combat.get("enemy")
    if isinstance(enemy, str):
        combat["enemy"] = {"name": enemy.strip() or "Enemy", "alive": True}
    elif isinstance(enemy, (int, float)) and not isinstance(enemy, bool):
        combat["enemy"] = {"name": str(enemy), "alive": True}
    elif isinstance(enemy, list):
        valid = [copy.deepcopy(row) for row in enemy if isinstance(row, dict)]
        labels = [ai_text(row).strip() for row in enemy if not isinstance(row, dict) and ai_text(row).strip()]
        if valid:
            combat["enemies"] = valid
            combat.pop("enemy", None)
        elif labels:
            combat["enemy"] = {
                "name": labels[0] if len(labels) == 1 else f"{labels[0]} and allies",
                "is_group": len(labels) > 1, "group_size": len(labels), "alive": True,
            }
        else:
            combat.pop("enemy", None)
    elif enemy is not None and not isinstance(enemy, dict):
        combat["enemy"] = {"name": ai_text(enemy).strip() or "Enemy", "alive": True}

    for key in ("enemy_statuses", "player_statuses", "enemy_debuffs", "player_debuffs", "player_buffs", "summons"):
        value = combat.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            value = [value]
        clean = []
        for row in value:
            if isinstance(row, dict):
                clean.append(copy.deepcopy(row))
            elif ai_text(row).strip():
                clean.append({"name": ai_text(row).strip(), "rounds_left": 1})
        combat[key] = clean
    if "log" in combat and not isinstance(combat.get("log"), list):
        combat["log"] = []
    if "cooldowns" in combat and not isinstance(combat.get("cooldowns"), dict):
        combat["cooldowns"] = {}
    if "opening_check" in combat and not isinstance(combat.get("opening_check"), dict):
        combat.pop("opening_check", None)
    return combat


def _type_ok(key, value):
    if key in FLEXIBLE_TYPES:
        return value is None or isinstance(value, (str, int, float, dict))
    expected = BASE_STATE.get(key)
    if isinstance(expected, bool):
        return isinstance(value, bool)
    if isinstance(expected, int):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(expected, str):
        return isinstance(value, str)
    if isinstance(expected, list):
        return isinstance(value, list)
    if isinstance(expected, dict):
        return isinstance(value, dict)
    return True


def _clean_quest(raw, hidden=False):
    if isinstance(raw, str):
        raw = {"name": raw, "explanation": "No briefing recorded yet."}
    if not isinstance(raw, dict) or not str(raw.get("name") or raw.get("title") or "").strip():
        return None
    q = copy.deepcopy(raw)
    q["name"] = str(q.get("name") or q.get("title")).strip()[:160]
    q["status"] = str(q.get("status") or ("Hidden" if hidden else "Active"))[:40]
    q["category"] = str(q.get("category") or ("hidden" if hidden else "side")).lower()
    if q["category"] not in {"main", "side", "personal", "hidden"}:
        q["category"] = "side"
    q["explanation"] = str(q.get("explanation") or q.get("description") or "No additional explanation is known yet.")[:2000]
    aliases = {
        "current_knowledge": ("current_knowledge", "knowledge", "clues", "known_facts"),
        "clear_conditions": ("clear_conditions", "completion_conditions", "conditions", "objectives"),
        "evidence": ("evidence", "clues"), "involved_npcs": ("involved_npcs", "npcs"),
        "locations": ("locations",), "consequences": ("consequences",),
        "discovered_clues": ("discovered_clues", "clues", "evidence", "current_knowledge"),
        "completion_conditions": ("completion_conditions", "clear_conditions", "conditions"),
        "optional_objectives": ("optional_objectives",),
        "current_obstacles": ("current_obstacles", "obstacles", "risks", "known_risks"),
    }
    for target, keys in aliases.items():
        value = next((q.get(k) for k in keys if q.get(k) is not None), [])
        if isinstance(value, str):
            value = [value]
        q[target] = [ai_text(x)[:500] for x in value[:40] if ai_text(x)] if isinstance(value, list) else []
    q["deadline"] = q.get("deadline") or None
    raw_objectives = q.get("objectives", q.get("clear_conditions", []))
    if isinstance(raw_objectives, str):
        raw_objectives = [raw_objectives]
    q["objectives"] = copy.deepcopy(raw_objectives[:40]) if isinstance(raw_objectives, list) else []
    branch = q.get("branch_state")
    q["branch_state"] = copy.deepcopy(branch) if isinstance(branch, dict) else {"current": "main", "available": [], "locked": []}
    q["first_step"] = str(q.get("first_step") or q.get("next_step") or "")[:500]
    q["next_hint"] = str(q.get("next_hint") or q.get("hint") or q.get("first_step") or q.get("next_step") or "")[:500]
    q["player_notes"] = str(q.get("player_notes") or "")[:4000]
    return q


def _normalize_patch(patch, before, allow_time=False, source="gm"):
    safe, accepted, rejected = {}, [], []
    if not isinstance(patch, dict):
        return {}, accepted, [{"field": "<root>", "reason": "state_patch was not an object"}]
    for key, value in patch.items():
        if key not in BASE_STATE:
            rejected.append({"field": key, "reason": "unknown state field"})
            continue
        if not expansion_for(before.get("world", "Custom World")).get("tracks_currency", True) and key in {"currency", "currencies", "purchase_offer", "recurring_finances"}:
            rejected.append({"field": key, "reason": "This world treats currency as narrative context rather than tracked state"})
            continue
        if key in APP_OWNED or (key in TIME_OWNED and not allow_time):
            rejected.append({"field": key, "reason": "application-owned field"})
            continue
        if key in {"world", "difficulty"} and value != before.get(key):
            rejected.append({"field": key, "reason": "campaign identity cannot be rewritten by the GM"})
            continue
        if not _type_ok(key, value):
            rejected.append({"field": key, "reason": f"invalid type {type(value).__name__}"})
            continue
        if key == "currency":
            value = copy.deepcopy(value)
            if before.get("world") == "Reincarnated as a Slime" and isinstance(value.get("amount"), (int, float)) and not isinstance(value.get("amount"), bool):
                value["minor_per_major"] = 10_000
                value["amount_minor"] = int(round(float(value["amount"]) * 10_000))
                value["storage_unit"] = "Copper Coin"
                value["denominations"] = {"Gold Coin": 10_000, "Silver Coin": 100, "Copper Coin": 1}
            value["tracked"] = True
        if key == "stats":
            allowed = set(abilities_for(before.get("world", "Custom World")))
            value = {str(k): max(1, int(v)) for k, v in value.items() if k in allowed and isinstance(v, (int, float))}
        elif key == "combat":
            value = normalize_combat_payload(value)
        elif key == "npc_memories":
            value = normalize_npc_memory_map(value)
        elif key in {"quests", "hidden_quests", "quest_archive"}:
            cleaned = [_clean_quest(q, key == "hidden_quests") for q in value[:200]]
            value = [q for q in cleaned if q]
        elif key == "titles":
            # A narrator patch often contains only the newly earned title.
            # Treat titles as an append-only achievement ledger so that such
            # a patch cannot silently erase everything earned earlier.
            combined = [*(before.get("titles", []) or []), *value]
            seen, preserved = set(), []
            for title in combined:
                label = ai_text(title).strip()
                if not label or label.lower() in seen:
                    continue
                seen.add(label.lower())
                preserved.append(copy.deepcopy(title))
            value = preserved[-200:]
        elif key in {"recurring_finances", "scheduled_events"}:
            # The GM is told to "always include the full current list" when
            # touching one of these entries -- but a real user report showed
            # that convention is fragile: mentioning income again for an
            # unrelated reason and imperfectly recalling every prior entry
            # silently deleted the omitted ones, causing an established
            # income to just stop with no in-fiction cause. Match incoming
            # entries to existing ones by label and merge instead of
            # replacing wholesale, so an entry the GM's patch doesn't
            # mention this turn is preserved rather than erased. The only
            # way an entry actually goes away is the GM explicitly marking
            # it (active:false / resolved:true) or a player correction.
            def _label(entry):
                raw = str((entry or {}).get("label") or (entry or {}).get("title") or "").casefold()
                # Models occasionally vary harmless punctuation/casing when
                # recalling a label. Treat "Instructor salary" and
                # "Instructor salary!" as the same persistent source.
                return re.sub(r"[\W_]+", " ", raw, flags=re.UNICODE).strip()
            existing = before.get(key) if isinstance(before.get(key), list) else []
            existing_by_label = {_label(e): e for e in existing if isinstance(e, dict) and _label(e)}
            merged, seen, positions = [], set(), {}
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                label = _label(entry)
                if label and label in positions:
                    merge(merged[positions[label]], entry)
                    continue
                combined = copy.deepcopy(existing_by_label.get(label, {})) if label else {}
                merge(combined, entry)
                if label:
                    seen.add(label)
                    positions[label] = len(merged)
                merged.append(combined)
            for label, old_entry in existing_by_label.items():
                if label not in seen:
                    merged.append(old_entry)
            value = merged[:500]
        elif isinstance(value, list):
            value = value[:500]
        safe[key] = copy.deepcopy(value)
        accepted.append(key)
    return safe, accepted, rejected


def _repair(state):
    repairs = []
    if state.get("world") not in WORLD_DATA:
        state["world"] = "Custom World"; repairs.append("Unknown world changed to Custom World")
    if state.get("difficulty") not in DIFFICULTIES:
        state["difficulty"] = "Adventurer"; repairs.append("Unknown difficulty changed to Adventurer")
    repairs.extend(_repair_nested_shapes(state))
    ensure_currency_state(state)
    normalized_combat = normalize_combat_payload(state.get("combat"))
    if normalized_combat != state.get("combat"):
        state["combat"] = normalized_combat
        repairs.append("Normalized malformed nested combat data")
    for current, maximum in (("hp", "hp_max"), ("resource", "resource_max")):
        try:
            state[maximum] = max(1, int(state.get(maximum, 100)))
            state[current] = max(0, min(state[maximum], int(state.get(current, state[maximum]))))
        except (TypeError, ValueError):
            state[maximum], state[current] = 100, 100
            repairs.append(f"Repaired invalid {current}/{maximum}")
    state["alive"] = bool(state.get("alive", True) and state.get("hp", 0) > 0)
    for key, default in BASE_STATE.items():
        if key not in state:
            state[key] = copy.deepcopy(default); repairs.append(f"Restored missing {key}")
    if state.get("location") and state["location"] not in state.setdefault("discovered_locations", []):
        state["discovered_locations"].append(state["location"])
        repairs.append("Added current location to discovered locations")
    return repairs


_KIDO_SKILL_RE = re.compile(r"^(Had[ōo]|Bakud[ōo])\s*#\s*(\d{1,2})(?:\s*:\s*(.+))?$", re.I)


def _repair_bleach_mechanics(state, before):
    """Keep releases and numbered Kido persistent and source-consistent."""
    if state.get("world") != "Bleach":
        return []
    repairs = []
    skills = state.setdefault("skills", {})
    previous = before.get("skills", {}) if isinstance(before.get("skills"), dict) else {}

    def indexed(source):
        result = {}
        for name, detail in source.items():
            match = _KIDO_SKILL_RE.match(str(name))
            if match:
                branch = "Hado" if match.group(1).lower().startswith("ha") else "Bakudo"
                result[(branch, int(match.group(2)))] = (name, copy.deepcopy(detail))
        return result

    old_index, new_index = indexed(previous), indexed(skills)
    for key, (name, detail) in list(new_index.items()):
        branch, number = key
        catalog = CANON_HADO if branch == "Hado" else CANON_BAKUDO
        if number in catalog:
            canon_name, canon_effect = catalog[number]
            expected = f"{branch} #{number}: {canon_name}"
            if name != expected:
                skills.pop(name, None); skills[expected] = detail; name = expected
                repairs.append(f"Restored the established name of {branch} #{number}")
            if isinstance(skills[name], dict):
                skills[name].setdefault("description", canon_effect)
                skills[name].setdefault("effect", canon_effect)
                skills[name]["kido"] = {"branch": branch, "number": number, "source_status": "established"}
        elif key in old_index and old_index[key][0] != name:
            skills.pop(name, None)
            old_name, old_detail = old_index[key]
            skills[old_name] = old_detail
            repairs.append(f"Preserved the campaign's established {branch} #{number} formula")
        elif isinstance(skills.get(name), dict):
            skills[name]["kido"] = {"branch": branch, "number": number, "source_status": "campaign_original"}
            skills[name].setdefault("limitation", "Casting requires sufficient Reiryoku, control and knowledge of the formula; chantless use is weaker until mastered.")
            skills[name].setdefault("growth_path", "Refine the incantation, efficiency, chantless output and tactical applications.")
        if not any(isinstance(row, dict) and row.get("name") == name for row in state.setdefault("codex", [])):
            state["codex"].append({"name": name, "type": "Kido Spell", "notes": "A permanently recorded numbered formula in this campaign."})

    special = state.setdefault("special", {})
    shikai = str(special.get("Shikai", "Unachieved"))
    bankai = str(special.get("Bankai", "Unachieved"))
    shikai_ok = shikai.lower() not in {"", "none", "unknown", "unachieved"}
    bankai_ok = bankai.lower() not in {"", "none", "unknown", "unachieved"}
    if bankai_ok and not shikai_ok:
        special["Bankai"] = "Unachieved"
        bankai_ok = False
        repairs.append("Blocked Bankai without an achieved Shikai")
    profile = special.get("Zanpakuto Profile") if isinstance(special.get("Zanpakuto Profile"), dict) else {}
    if shikai_ok and profile.get("shikai_name"):
        skill_name = f"Shikai — {profile['shikai_name']}"
        skills.setdefault(skill_name, {"rank":"Shikai", "bonus":10, "description":profile.get("shikai_effect", "The recorded first release of this Zanpakuto."), "effect":profile.get("shikai_effect", ""), "limitation":profile.get("shikai_limitation", "Consumes Reiryoku and requires release control."), "growth_path":"Deepen the bond and refine applications.", "combat_usable":True, "effect_type":"transform", "release_stage":"Shikai"})
    if bankai_ok and profile.get("bankai_name"):
        skills.setdefault(profile["bankai_name"], {"rank":"Bankai", "bonus":14, "description":profile.get("bankai_effect", "The recorded final release of this Zanpakuto."), "effect":profile.get("bankai_effect", ""), "limitation":profile.get("bankai_cost", "Consumes immense Reiryoku."), "growth_path":"Extend safe duration and mastery.", "combat_usable":True, "effect_type":"transform", "release_stage":"Bankai"})
    return repairs


def apply_guarded_patch(state, patch, allow_time=False, source="gm"):
    before = copy.deepcopy(state)
    safe, accepted, rejected = _normalize_patch(patch, state, allow_time, source)
    if isinstance(before.get("combat"), dict) and before["combat"].get("adventure_objective") and before["combat"].get("active"):
        if "combat" in safe:
            safe.pop("combat")
            rejected.append("combat: objective encounters are resolved by the tactical rules")
    for field in ("quests", "quest_archive"):
        owned = [copy.deepcopy(q) for q in before.get(field, []) if isinstance(q, dict) and q.get("adventure_id")]
        if owned and field in safe:
            safe[field] = [q for q in safe[field] if not isinstance(q, dict) or
                           (not q.get("adventure_id") and q.get("id") not in {r.get("id") for r in owned})] + owned
    merge(state, safe)
    _compile_skill_mechanics(state)
    repairs = _repair(state)
    repairs.extend(_repair_bleach_mechanics(state, before))
    repairs.extend(normalize_world_progression(state, before))
    repairs.extend(normalize_world_depth(state, before))
    repairs.extend(normalize_world_activity(state, before))
    repairs.extend(initialize_lit_systems(state))
    repairs.extend(normalize_political_state(state, before))
    repairs.extend(normalize_canon_integrity(state))
    normalize_companion_combinations(state, before)
    normalize_trophy_state(state, before)
    refresh_simulation_core(state)
    knowledge_changes = normalize_npc_knowledge(state, before, source)
    if knowledge_changes:
        repairs.extend(f"Downgraded unsupported secret knowledge for {row['npc']} to a suspicion" for row in knowledge_changes)
    report = {
        "time": datetime.now().isoformat(timespec="seconds"), "turn": state.get("turn", 0),
        "source": source, "accepted": accepted, "rejected": rejected, "repairs": repairs,
    }
    state.setdefault("validation_log", []).append(report)
    state["validation_log"] = state["validation_log"][-100:]
    return report


def migrate_state(state, from_version="unknown"):
    migrated = copy.deepcopy(state) if isinstance(state, dict) else {}
    old_schema = int(migrated.get("schema_version", 0) or 0)
    missing_age_anchor = "age_anchor_year" not in migrated
    if old_schema < 5 and isinstance(migrated.get("stats"), dict):
        # Convert the former 3-20 D&D-like scale to the open-ended local scale
        # while preserving relative strengths. Pool damage/resource ratios are
        # retained below instead of healing old saves for free.
        migrated["stats"] = {k: max(1, int(v) * 3) for k, v in migrated["stats"].items() if isinstance(v, (int, float))}
        world = migrated.get("world", "Custom World")
        pool_map = {
            "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
            "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
            "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
            "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
            "Bleach": (("Hakuda", "Willpower"), ("Reiatsu Control", "Willpower")),
        }
        hp_keys, resource_keys = pool_map.get(world, (("Constitution", "Strength"), ("Wisdom", "Intelligence")))
        stats = migrated["stats"]
        hp_new = max(20, 25 + int(stats.get(hp_keys[0], 30)) * 2 + int(stats.get(hp_keys[1], 30)))
        resource_new = max(10, 15 + int(stats.get(resource_keys[0], 30)) * 2 + int(stats.get(resource_keys[1], 30)))
        hp_ratio = float(migrated.get("hp", 100) or 0) / max(1, float(migrated.get("hp_max", 100) or 100))
        resource_ratio = float(migrated.get("resource", 100) or 0) / max(1, float(migrated.get("resource_max", 100) or 100))
        migrated.update(hp_max=hp_new, hp=max(0, round(hp_new * hp_ratio)),
                        resource_max=resource_new, resource=max(0, round(resource_new * resource_ratio)))
    for key, default in BASE_STATE.items():
        migrated.setdefault(key, copy.deepcopy(default))
    initialize_age_tracking(migrated, repair_elapsed=missing_age_anchor)
    migrated["schema_version"] = BASE_STATE.get("schema_version", 12)
    normalize_npc_knowledge(migrated, {}, "migration")
    repairs = _repair(migrated)
    _compile_skill_mechanics(migrated)
    repairs.extend(normalize_world_progression(migrated))
    repairs.extend(normalize_world_depth(migrated))
    repairs.extend(normalize_world_activity(migrated))
    repairs.extend(initialize_lit_systems(migrated))
    repairs.extend(normalize_political_state(migrated))
    repairs.extend(normalize_canon_integrity(migrated, scan_chronicle=True))
    normalize_companion_combinations(migrated)
    normalize_trophy_state(migrated)
    from life_simulation import normalize as normalize_life_simulation
    normalize_life_simulation(migrated)
    legacy_messages = _repair_legacy_local_messages(migrated)
    if legacy_messages:
        repairs.append(f"Cleaned {legacy_messages} legacy local message bodies")
    refresh_simulation_core(migrated)
    health = pre_advance_health_check(migrated, source="migration")
    repairs.extend(health.get("repairs", []))
    migrated.setdefault("diagnostics", {})["migration"] = {
        "from_version": from_version, "repairs": repairs,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    from organizations import ensure_organizations
    ensure_organizations(migrated)
    return migrated
