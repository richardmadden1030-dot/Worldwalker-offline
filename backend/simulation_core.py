"""Deterministic coordination layer for Worldwalker's simulation systems.

This module does not narrate and never calls an AI model.  It turns the
campaign's authored facts into compact, authoritative structures shared by
the GM, combat, progression, NPC continuity and the local evaluator.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime

from ability_mechanics import compile_ability_mechanics
from power_benchmarks import benchmark_tier
from skill_system import normalize_skill_map
from worlds import power_profile_for, uses_xp_for


CORE_VERSION = 1
_TRAINING_RE = re.compile(r"\b(train|practice|study|meditat|drill|condition|master|learn|refine)\w*\b", re.I)
_VIOLENCE_RE = re.compile(r"\b(attack|strike|fight|kill|stab|shoot|ambush|assault|duel|battle)\w*\b", re.I)
_COMMITTED_VIOLENCE_RE = re.compile(
    r"\b(?:attack|strike|fight|kill|stab|shoot|ambush|assault|duel|spar|battle|slash|punch|kick|hit|tackle|grapple|choke)\w*\b|"
    r"\b(?:cast|throw|unleash|fire|blast|launch)\b.{1,45}\b(?:at|on|toward|into)\b|"
    r"\b(?:charge|lunge|swing)\b.{0,35}\b(?:at|on|toward|into)\b",
    re.I,
)
_VIOLENCE_PROPOSAL_RE = re.compile(
    r"\b(?:ask|request|propose|offer|arrange|schedule|seek|petition|invite|challenge)\b.{0,90}"
    r"\b(?:duel|spar|bout|match|fight|battle|combat)\b", re.I,
)
_COMMITTED_AFTER_PROPOSAL_RE = re.compile(
    r"\b(?:then|and then|immediately|once (?:he|she|they) (?:accepts?|agrees?))\b.{0,60}"
    r"\b(?:attack|strike|stab|slash|shoot|punch|kick|ambush|kill|charge|lunge)\b", re.I,
)
_ESCAPE_RE = re.compile(r"\b(flee|escape|retreat|withdraw|surrender|yield)\w*\b", re.I)
_SOCIAL_RE = re.compile(r"\b(negotiate|persuade|ask|convince|bargain|diploma|speech|meet|propose)\w*\b", re.I)


def _text(value):
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or value.get("label") or "").strip()
    return str(value or "").strip()


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def build_capability_profile(state):
    """Build one canonical answer to "what can this character actually do?"""
    world = state.get("world", "Custom World")
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    special = state.get("special") if isinstance(state.get("special"), dict) else {}
    profile = power_profile_for(world, stats, special.get("Archetype", ""))
    peak_score = int((profile.get("peak") or {}).get("score", max((_number(v) for v in stats.values()), default=1)) or 1)
    tier = benchmark_tier(world, peak_score)
    skills = normalize_skill_map(state.get("skills", {}))
    available, passive, locked = [], [], []
    for name, detail in skills.items():
        row = {"name": name, "category": detail.get("category", "utility"),
               "effect_type": detail.get("effect_type", "utility"),
               "combat_usable": bool(detail.get("combat_usable")),
               "rank": detail.get("rank", "Learned")}
        if detail.get("locked") or str(detail.get("status", "")).lower() in {"locked", "unachieved", "dormant"}:
            locked.append(row)
        elif row["combat_usable"]:
            available.append(row)
        else:
            passive.append(row)
    equipment = []
    raw_equipment = state.get("equipment") if isinstance(state.get("equipment"), dict) else {}
    for slot, item in raw_equipment.items():
        if item not in (None, "", {}, []):
            equipment.append({"slot": str(slot), "item": _text(item) or str(item)[:120]})
    titles = [_text(row) for row in state.get("titles", []) if _text(row)]
    limitations = []
    for name, detail in skills.items():
        if detail.get("limitation"):
            limitations.append(f"{name}: {str(detail['limitation'])[:180]}")
    for status in state.get("status", []) or []:
        label = _text(status)
        if label: limitations.append(label)
    world_traits = {}
    if world == "Naruto":
        world_traits = {key: copy.deepcopy(special.get(key)) for key in
                        ("Chakra Affinity", "Secondary Nature Proficiencies", "Kekkei Genkai", "Dōjutsu", "Jinchuriki")
                        if special.get(key) not in (None, "", "None", "Unachieved", {})}
    elif world == "Bleach":
        world_traits = {key: copy.deepcopy(special.get(key)) for key in
                        ("Spiritual Nature", "Shinigami Rank", "Zanpakuto", "Shikai", "Bankai", "Squad")
                        if special.get(key) not in (None, "", "Unachieved", {})}
    elif world == "Jujutsu Kaisen":
        world_traits = {key: copy.deepcopy(special.get(key)) for key in
                        ("Grade", "Innate Technique", "Heavenly Restriction", "Domain Expansion")
                        if special.get(key) not in (None, "", "None", "Unachieved", {})}
    result = {
        "version": CORE_VERSION, "world": world, "power": copy.deepcopy(profile),
        "tier": {"index": tier.get("index", 0), "label": tier.get("label", "Unknown")},
        "effective_stats": {str(k): int(_number(v, 1)) for k, v in stats.items()},
        "combat_abilities": available, "noncombat_abilities": passive, "locked_abilities": locked,
        "titles": titles, "equipment": equipment, "world_traits": world_traits,
        "limitations": limitations[:30], "resource": {"name": state.get("resource_name", "Energy"),
        "current": int(_number(state.get("resource"))), "maximum": int(_number(state.get("resource_max"), 1))},
    }
    state["capability_profile"] = result
    return result


def normalize_ability_registry(state):
    """Persist complete mechanical contracts for every named ability."""
    capability = state.get("capability_profile") or build_capability_profile(state)
    tier_index = int((capability.get("tier") or {}).get("index", 2) or 2)
    skills = normalize_skill_map(state.get("skills", {}))
    registry = {}
    for name, detail in skills.items():
        compiled = compile_ability_mechanics(state.get("world", "Custom World"), {"name": name, **detail}, tier_index)
        mechanics = compiled.get("compiled_mechanics", {})
        registry[name] = {
            "name": name, "rank": compiled.get("rank", "Learned"),
            "governing_rule": compiled.get("governing_rule") or compiled.get("effect") or compiled.get("description") or "Uses its established campaign effect.",
            "applications": copy.deepcopy(compiled.get("applications") or [compiled.get("effect") or compiled.get("description") or name]),
            "category": compiled.get("category", "utility"), "effect_type": compiled.get("effect_type", "utility"),
            "combat_usable": bool(compiled.get("combat_usable")), "mechanics": copy.deepcopy(mechanics),
            "limits": copy.deepcopy(compiled.get("limitations") or compiled.get("limitation") or mechanics.get("counterplay") or ""),
            "growth": copy.deepcopy(compiled.get("growth_path") or mechanics.get("mastery_stages") or []),
            "current_mastery": compiled.get("mastery") or compiled.get("rank") or "Learned",
            "theoretical_potential": "World-relative; may grow through established applications and earned breakthroughs.",
        }
        compiled.pop("name", None)
        skills[name] = compiled
    state["skills"] = skills
    state["ability_registry"] = registry
    return registry


def classify_action(action):
    text = str(action or "").strip()
    kinds = []
    if _TRAINING_RE.search(text): kinds.append("training")
    if action_commits_violence(text): kinds.append("violence")
    if _ESCAPE_RE.search(text): kinds.append("escape")
    if _SOCIAL_RE.search(text) or _VIOLENCE_PROPOSAL_RE.search(text): kinds.append("social")
    if not kinds: kinds.append("general")
    return {"text": text[:500], "kinds": kinds,
            "has_method": bool(re.search(r"\b(by|using|through|with|via|because)\b", text, re.I)),
            "has_goal": bool(re.search(r"\b(to|until|so that|in order to)\b", text, re.I))}


def action_commits_violence(action):
    """Distinguish an actual hostile act from asking to arrange a fight."""
    from gm_policy import intent_clauses
    text = "; ".join(row["text"] for row in intent_clauses(action) if row["mode"] == "immediate")
    if not _COMMITTED_VIOLENCE_RE.search(text):
        return False
    proposal = _VIOLENCE_PROPOSAL_RE.search(text)
    if proposal and not _COMMITTED_AFTER_PROPOSAL_RE.search(text[proposal.start():]):
        return False
    return True


def progression_calibration(state, actions=None, elapsed_minutes=0):
    """Produce a local expected-growth band without changing awarded gains."""
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    action_rows = [classify_action(row) for row in (actions or []) if str(row).strip()]
    training = [row for row in action_rows if "training" in row["kinds"]]
    focus = 1.0 + min(1.25, .25 * sum(1 for row in training if row["has_method"]))
    consistency = 1.0 if days < 1 else min(2.0, 1.0 + days / 180.0)
    world = state.get("world", "Custom World")
    base = {"Naruto": .42, "Bleach": .38, "One Piece": .36, "Hunter x Hunter": .40,
            "Jujutsu Kaisen": .39, "Overgeared": .30, "Solo Max-Level Newbie": .32,
            "Reincarnated as a Slime": .44}.get(world, .35)
    expected = days * base * focus * consistency if training else 0.0
    result = {"version": CORE_VERSION, "elapsed_days": round(days, 3), "training_actions": len(training),
              "focused_method": any(row["has_method"] for row in training),
              "expected_primary_gain": {"minimum": int(expected * .65), "typical": max(0, round(expected)), "high": max(0, round(expected * 1.8))},
              "supporting_stat_share": .35 if training else 0.0,
              "xp_world": bool(uses_xp_for(world, state.get("custom_world", ""))),
              "guidance": "Award visible gains proportional to every day invested; named methods concentrate gains while related fundamentals also improve."}
    state["progression_calibration"] = result
    return result


def normalize_npc_continuity(state):
    """Unify dispersed NPC facts, including nemesis and combat-support flags."""
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    intentions = state.get("npc_intentions") if isinstance(state.get("npc_intentions"), dict) else {}
    schedules = state.get("npc_schedules") if isinstance(state.get("npc_schedules"), dict) else {}
    relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    companions = {}
    for row in state.get("companions", []) or []:
        if isinstance(row, dict) and row.get("name"):
            companions[str(row["name"])] = row
    names = set(memories) | set(intentions) | set(schedules) | set(relationships) | set(companions)
    registry = {}
    for name in sorted(names):
        memory = memories.get(name) if isinstance(memories.get(name), dict) else {}
        companion = companions.get(name, {})
        intention = intentions.get(name) if isinstance(intentions.get(name), dict) else {}
        support_flag = companion.get("combat_support", companion.get("supports_combat", memory.get("combat_support", False)))
        support_bonus = int(_number(companion.get("support_bonus", memory.get("support_bonus", 0))))
        if support_flag and support_bonus <= 0:
            support_bonus = 5
        registry[name] = {
            "name": name, "role": companion.get("role") or memory.get("role") or "NPC",
            "companion": name in companions, "nemesis": bool(memory.get("nemesis") or intention.get("nemesis")),
            "recurring": bool(memory.get("recurring") or intention.get("recurring") or name in companions),
            "combat_support": bool(support_flag or support_bonus), "support_bonus": max(0, min(30, support_bonus)),
            "goal": intention.get("goal") or memory.get("goal") or companion.get("goal") or "",
            "status": memory.get("status", "active"),
            "last_known_location": memory.get("last_known_location") or companion.get("location") or "Unknown",
            "attitude": memory.get("attitude") or relationships.get(name) or "Unknown",
            "schedule": copy.deepcopy(schedules.get(name, {})),
            "knowledge": copy.deepcopy(memory.get("knowledge", {})),
            "memory_chain": copy.deepcopy((memory.get("chain") or [])[-8:]),
        }
        if registry[name]["nemesis"]:
            memory["nemesis"] = True; memory["recurring"] = True
        if name in companions and registry[name]["combat_support"]:
            companion["combat_support"] = True
            companion["support_bonus"] = registry[name]["support_bonus"]
    state["npc_continuity"] = registry
    return registry


def companion_support_for_combat(state):
    registry = state.get("npc_continuity") or normalize_npc_continuity(state)
    current = str(state.get("location") or "").lower()
    companions={str(row.get('name')):row for row in state.get('companions',[]) if isinstance(row,dict) and row.get('name')}
    memories=state.get('npc_memories') if isinstance(state.get('npc_memories'),dict) else {}
    supporters = []
    for row in registry.values():
        present = row.get("last_known_location") in ("", "Unknown") or str(row.get("last_known_location", "")).lower() == current
        if row.get("companion") and row.get("combat_support") and row.get("status") != "deceased" and present:
            # Preserve the ally's own saved stats, abilities, portrait and forms.
            # The old aggregate-support row was sufficient for narrative combat,
            # but it cannot represent a player-controlled tactical piece.
            source=copy.deepcopy(memories.get(row['name'],{})) if isinstance(memories.get(row['name']),dict) else {}
            source.update(copy.deepcopy(companions.get(row['name'],{})))
            source.update(name=row['name'],bonus=row.get('support_bonus',0),role=row.get('role','Support'),
                          combat_support=True)
            supporters.append(source)
    return supporters


def normalize_encounter_state(state, action=""):
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    old = state.get("encounter_state") if isinstance(state.get("encounter_state"), dict) else {}
    phase = old.get("phase", "idle")
    if combat.get("active"):
        phase = "active_combat"
    elif combat.get("outcome"):
        phase = "aftermath"
    elif _ESCAPE_RE.search(str(action or "")):
        phase = "escape_or_surrender"
    elif action_commits_violence(action):
        phase = "committed_violence"
    elif state.get("danger_scenario"):
        phase = "confrontation"
    elif phase not in {"aftermath", "resolved"}:
        phase = "idle"
    result = {"version": CORE_VERSION, "phase": phase,
              "negotiation_possible": phase in {"idle", "confrontation"},
              "violence_committed": phase in {"committed_violence", "active_combat", "escape_or_surrender", "aftermath"},
              "opponent": _text(combat.get("enemy", {})), "outcome": combat.get("outcome", ""),
              "updated_turn": int(state.get("turn", 0) or 0)}
    state["encounter_state"] = result
    return result


def normalize_story_threads(state):
    """Turn agendas, promises and standing work into flexible story threads."""
    previous = state.get("story_threads") if isinstance(state.get("story_threads"), dict) else {}
    threads = {}
    def add(key, title, kind, status="active", detail="", source=""):
        prior = previous.get(key, {}) if isinstance(previous.get(key), dict) else {}
        threads[key] = {"id": key, "title": title[:180], "kind": kind, "status": status,
                        "detail": str(detail or "")[:600], "source": source,
                        "developments": copy.deepcopy((prior.get("developments") or [])[-12:]),
                        "updated_turn": int(state.get("turn", 0) or 0)}
    for index, quest in enumerate(state.get("quests", []) or []):
        if not isinstance(quest, dict): continue
        name = str(quest.get("name") or f"Agenda {index + 1}")
        status = str(quest.get("status", "active")).lower()
        status = "resolved" if status in {"complete", "completed", "resolved"} else "failed" if status == "failed" else "active"
        add(f"quest:{name.lower()}", name, "quest" if quest.get("agenda_mode") == "literal" else "agenda",
            status, quest.get("next_hint") or quest.get("explanation"), "quests")
    for index, intent in enumerate(state.get("standing_intents", []) or []):
        if not isinstance(intent, dict): continue
        title = str(intent.get("label") or intent.get("action") or intent.get("directive") or f"Standing commitment {index + 1}")
        add(f"intent:{str(intent.get('id') or title).lower()}", title, "standing_intent",
            "resolved" if intent.get("active") is False else "active", intent.get("reason") or intent.get("notes"), "standing_intents")
    memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    for kind in ("unresolved_mysteries", "promises"):
        for index, item in enumerate(memory.get(kind, []) or []):
            title = _text(item) or str(item)
            if title: add(f"{kind}:{index}:{title.lower()[:80]}", title, kind[:-1], "active", title, "narrative_memory")
    for name, row in (state.get("npc_continuity") or {}).items():
        if row.get("nemesis") and row.get("status") != "deceased":
            add(f"nemesis:{name.lower()}", name, "nemesis", "turning_point" if str(row.get("status")) == "turning_point" else "active", row.get("goal"), "npc_continuity")
    state["story_threads"] = threads
    return threads


def record_resolution_transaction(state, before, actions, elapsed_minutes, narrative="", rolls=None):
    """Record the six resolution phases as a compact local consistency ledger."""
    action_rows = [classify_action(row) for row in (actions or []) if str(row).strip()]
    stat_changes = {}
    for key, value in (state.get("stats") or {}).items():
        delta = _number(value) - _number((before.get("stats") or {}).get(key))
        if delta: stat_changes[key] = int(delta) if float(delta).is_integer() else round(delta, 2)
    added_skills = sorted(set(state.get("skills", {})) - set(before.get("skills", {})))
    transaction = {
        "id": f"turn-{int(state.get('turn', 0) or 0)}-{len(state.get('resolution_ledger', [])) + 1}",
        "turn": int(state.get("turn", 0) or 0), "time": datetime.now().isoformat(timespec="seconds"),
        "actions": action_rows, "phases": {
            "understand": {"action_count": len(action_rows), "methods_named": sum(1 for row in action_rows if row["has_method"])},
            "feasibility": {"capability_tier": ((state.get("capability_profile") or {}).get("tier") or {}).get("label", "Unknown"), "roll_count": len(rolls or [])},
            "time": {"elapsed_minutes": int(_number(elapsed_minutes))},
            "mechanics": {"stat_changes": stat_changes, "new_skills": added_skills,
                          "hp_change": int(_number(state.get("hp")) - _number(before.get("hp"))),
                          "resource_change": int(_number(state.get("resource")) - _number(before.get("resource")))},
            "state": {"location_changed": before.get("location") != state.get("location"),
                      "combat_phase": (state.get("encounter_state") or {}).get("phase", "idle")},
            "narrative": {"present": bool(str(narrative or "").strip()), "characters": len(str(narrative or ""))},
        }}
    state.setdefault("resolution_ledger", []).append(transaction)
    state["resolution_ledger"] = state["resolution_ledger"][-100:]
    return transaction


def refresh_simulation_core(state, actions=None, elapsed_minutes=0, action=""):
    from campaign_features import normalize_companion_combinations, normalize_trophy_state
    build_capability_profile(state)
    normalize_ability_registry(state)
    normalize_npc_continuity(state)
    normalize_encounter_state(state, action or "; ".join(str(x) for x in (actions or [])))
    normalize_story_threads(state)
    normalize_companion_combinations(state)
    normalize_trophy_state(state)
    progression_calibration(state, actions or [], elapsed_minutes)
    state["simulation_core_version"] = CORE_VERSION
    return state
