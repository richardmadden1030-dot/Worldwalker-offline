"""Deterministic simulation budgeting and world-state consolidation.

This module deliberately contains no AI client.  It decides what deserves
full detail, advances off-screen intentions, prepares mechanical checks, and
deduplicates event records before the narrator sees or describes them.  The
normal Advance path can therefore spend its single model call on storytelling
instead of asking a model to perform bookkeeping first.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime

from worlds import abilities_for
from director import enrich_npc_depth
from campaign_features import recent_chat_context


SIMULATION_MODES = {
    "economy": {
        "label": "Economy", "description": "Compact context and lightweight off-screen simulation.",
        "recent_turns": 6, "full_npcs": 4, "offscreen_npcs": 6, "active_quests": 3,
        "world_feed": 6, "max_updates": 3, "lore_limit": 3, "output_ratio": 0.58,
        "background_ai_interval": 0,
    },
    "balanced": {
        "label": "Balanced", "description": "Focused local detail with concise wider-world movement.",
        "recent_turns": 10, "full_npcs": 8, "offscreen_npcs": 10, "active_quests": 6,
        "world_feed": 10, "max_updates": 5, "lore_limit": 4, "output_ratio": 0.80,
        "background_ai_interval": 0,
    },
    "deep": {
        "label": "Deep", "description": "More nearby actors, lore, and occasional background narration.",
        "recent_turns": 15, "full_npcs": 14, "offscreen_npcs": 20, "active_quests": 10,
        "world_feed": 18, "max_updates": 8, "lore_limit": 5, "output_ratio": 1.0,
        "background_ai_interval": 4,
    },
}


def normalize_simulation_mode(value):
    mode = str(value or "balanced").strip().lower()
    return mode if mode in SIMULATION_MODES else "balanced"


def simulation_profile(value):
    mode = normalize_simulation_mode(value)
    return {"id": mode, **copy.deepcopy(SIMULATION_MODES[mode])}


def output_budget(requested, mode):
    profile = simulation_profile(mode)
    requested = max(200, int(requested or 700))
    # Even Economy receives enough room to close a structured JSON object.
    return max(500, min(requested, int(round(requested * profile["output_ratio"]))))


def _text(value):
    return str(value or "").strip()


def _npc_name(value):
    return _text(value.get("name")) if isinstance(value, dict) else _text(value)


def relevance_bubble(state, query="", mode="balanced"):
    """Return named actors that merit detailed simulation this turn."""
    profile = simulation_profile(mode)
    location = _text(state.get("location")).lower()
    query_blob = _text(query).lower()
    recent = " ".join(_text(x.get("outcome")) for x in (state.get("campaign_canon") or [])[-4:] if isinstance(x, dict)).lower()
    companions = {_npc_name(x) for x in state.get("companions") or [] if _npc_name(x)}
    scored = []
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict):
            continue
        score, reasons = 0, []
        if name in companions:
            score += 100; reasons.append("companion")
        if location and _text(memory.get("last_known_location")).lower() == location:
            score += 80; reasons.append("same location")
        if memory.get("nemesis"):
            score += 60; reasons.append("active nemesis")
        if memory.get("recurring") or _text(memory.get("importance")).lower() in {"major", "important", "high"}:
            score += 35; reasons.append("recurring")
        if _text(name).lower() in query_blob:
            score += 90; reasons.append("named by player")
        if _text(name).lower() in recent:
            score += 25; reasons.append("recently involved")
        scored.append((score, _text(name), reasons))
    scored.sort(key=lambda row: (-row[0], row[1].lower()))
    detailed = [name for score, name, _ in scored if score > 0][:profile["full_npcs"]]
    return {
        "mode": profile["id"], "location": state.get("location", ""), "detailed_npcs": detailed,
        "coarse_npcs": [name for _, name, _ in scored if name not in detailed][:profile["offscreen_npcs"]],
        "reasons": {name: reasons for _, name, reasons in scored if reasons},
    }


def compile_context_snapshot(snapshot, state, query="", mode="balanced"):
    """Trim a save-shaped snapshot into a relevance-shaped narrator context."""
    profile = simulation_profile(mode)
    out = copy.deepcopy(snapshot)
    bubble = relevance_bubble(state, query, mode)
    memories = out.get("npc_memories")
    if isinstance(memories, dict) and len(memories) > profile["full_npcs"]:
        keep = set(bubble["detailed_npcs"])
        coarse = set(bubble["coarse_npcs"])
        compact = {}
        for name, memory in memories.items():
            if name in keep or not isinstance(memory, dict):
                compact[name] = memory
            elif name in coarse:
                compact[name] = {
                    "attitude": memory.get("attitude", "Unknown"),
                    "last_known_location": memory.get("last_known_location", "Unknown"),
                    "goal": memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal") or "",
                    "next_action": memory.get("next_action") or memory.get("plan") or "",
                    "chain": (memory.get("chain") or [])[-4:],
                    "promises": (memory.get("promises") or [])[:2], "debts": (memory.get("debts") or [])[:2],
                }
        out["npc_memories"] = compact
    if isinstance(out.get("campaign_canon"), list):
        out["campaign_canon"] = out["campaign_canon"][-profile["recent_turns"]:]
    if isinstance(out.get("chapter_summaries"), list):
        out["chapter_summaries"] = out["chapter_summaries"][-3:]
    if isinstance(out.get("background_world_feed"), list):
        out["background_world_feed"] = out["background_world_feed"][-profile["world_feed"]:]
    if isinstance(out.get("world_events"), list):
        out["world_events"] = out["world_events"][-profile["world_feed"]:]
    if isinstance(out.get("quests"), list):
        active = [q for q in out["quests"] if not isinstance(q, dict) or _text(q.get("status", "active")).lower() not in {"complete", "completed", "failed", "archived"}]
        out["quests"] = active[:profile["active_quests"]]
    for field, limit in (("inventory", 40), ("codex", 30), ("timeline", 25), ("chat_threads", 12)):
        value = out.get(field)
        if isinstance(value, list):
            out[field] = value[-limit:]
        elif isinstance(value, dict) and len(value) > limit:
            out[field] = dict(list(value.items())[-limit:])
    out["simulation_context"] = {
        "mode": profile["id"], "detail_bubble": bubble,
        "rule": "Fully resolve the local bubble; treat listed coarse actors as summaries until they become relevant.",
    }
    out["recent_chat_context"] = recent_chat_context(state, query)
    out["chat_context_rule"] = "Treat these recent messages as established events. Agreements, threats, facts, warnings, promises and plans said in chat must affect the main simulation when relevant."
    return out


EXTREME_RE = re.compile(
    r"\b(impossible|near[- ]impossible|legendary|ultimate|boss|climactic|deathmatch|"
    r"alone against|one[- ]shot|single[- ]handedly|elite|guardian|godlike|overthrow|"
    r"entire (?:nation|village|kingdom|world)|admiral|emperor|kage)\b", re.I)
MAJOR_RE = re.compile(r"\b(awaken|evolve|transformation|transform|legendary|ultimate|boss|climactic|deathmatch|conqueror)\b", re.I)
LETHAL_RE = re.compile(r"\b(kill|deathmatch|assassinate|boss|suicide|alone against|invade|lethal|to the death)\b", re.I)
POWER_RE = re.compile(
    r"\b(learn|master|unlock|awaken|acquire|gain|develop|achieve|manifest|discover)\b.*\b("
    r"ability|power|form|class|haki|nen|jutsu|skill|technique|magic|fruit|"
    r"zanpakut[ōo]|shikai|bankai|hollowfication|resurrecci[óo]n|segunda etapa|schrift|vollst[äa]ndig|fullbring|"
    r"had[ōo]|bakud[ōo]|kid[ōo])\b",
    re.I,
)

DIPLOMACY_RE = re.compile(
    r"\b(negotiate|persuade|convince|diploma|politic|petition|propose|proposal|alliance|ally|"
    r"bargain|mediate|appeal to|make (?:a |my )?case|present (?:a |my )?case|request|recruit|"
    r"lobby|debate|argue|offer terms|peace talk|ceasefire|treaty)\b", re.I)
EXPLICIT_METHOD_RE = re.compile(
    r"\b(by|through|using|via|with the help of|under the guidance of|under .+?'?s guidance|"
    r"because|leveraging|offering|in exchange for|every day|daily|rigorous(?:ly)?|systematically|"
    r"step by step|according to|following)\b", re.I)
HARD_BLOCK_REASON_RE = re.compile(
    r"\b(no known ability|physically impossible|metaphysically impossible|does not exist|"
    r"dead|deceased|mutually exclusive|world[- ]rule contradiction|no logical possibility|"
    r"requires an? (?:absent|missing|specific) (?:bloodline|lineage|body|species|artifact)|"
    r"cannot .+ without (?:the|an?) (?:required|specific|unique))\b", re.I)


def player_favoring_difficulty(state):
    """All modes below Nightmare prioritize achievable power-fantasy play."""
    return str((state or {}).get("difficulty", "Adventurer")) != "Nightmare"


def diplomatic_action(action):
    return bool(DIPLOMACY_RE.search(_text(action)))


def explicit_world_method(action):
    """A concrete player-authored route should count as real preparation.

    This is intentionally lexical and generous. The narrator still checks the
    route against setting facts; this helper only prevents a logically usable
    plan from being converted into an arbitrary luck gate.
    """
    text = _text(action)
    return len(text.split()) >= 6 and bool(EXPLICIT_METHOD_RE.search(text))


def agency_bypasses_check(state, action, assessment=None):
    if not player_favoring_difficulty(state):
        return False
    assessment = assessment if isinstance(assessment, dict) else {}
    if assessment.get("hard_rule_block"):
        return False
    if diplomatic_action(action):
        return True
    lethal = str(assessment.get("lethal_risk") or "none").lower()
    return explicit_world_method(action) and lethal not in {"high", "extreme"}


def normalize_assessment_for_agency(state, action, assessment):
    """Keep model caution from becoming an extra lower-mode rules gate."""
    result = copy.deepcopy(assessment) if isinstance(assessment, dict) else {}
    if not player_favoring_difficulty(state):
        return result
    # Cached v3.7.0 assessments predate hard_rule_block. Preserve only their
    # concrete impossibilities; social reluctance and low odds are not blocks.
    hard_block = bool(result.get("hard_rule_block")) or bool(
        result.get("impossible") and "hard_rule_block" not in result
        and HARD_BLOCK_REASON_RE.search(_text(result.get("reason")))
    )
    if hard_block:
        result["hard_rule_block"] = True
    if result.get("impossible") and not hard_block:
        result["impossible"] = False
        result["reason"] = "The action can be attempted within the world's rules; its consequences depend on the people and forces involved."
    if agency_bypasses_check(state, action, result):
        result["requires_check"] = False
        result["difficulty_min"] = None
        result["difficulty_max"] = None
    return result


def deterministic_assessment(state, actions, budget, mode="balanced"):
    """Build rare high-stakes d100 gates without spending a model call.

    Ordinary training, politics, strategy, investigation, travel, social play,
    and routine combat resolve directly. Dice are reserved for an extreme
    obstacle, lethal undertaking, or a genuine leap into a new power tier.
    """
    abilities = abilities_for(state.get("world", "Custom World")) or ["Willpower"]
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    checks = []
    for index, action in enumerate(actions or []):
        text = _text(action)
        power_leap = bool(POWER_RE.search(text))
        extreme = bool(EXTREME_RE.search(text))
        lethal_attempt = bool(LETHAL_RE.search(text))
        if player_favoring_difficulty(state) and (
            diplomatic_action(text) or (explicit_world_method(text) and not lethal_attempt)
        ):
            continue
        if not (power_leap or extreme or lethal_attempt):
            continue
        lower = text.lower()
        if any(word in lower for word in ("impossible", "godlike", "entire world", "alone against")):
            dc_min, dc_max = 82, 96
        elif power_leap:
            dc_min, dc_max = 68, 86
        else:
            dc_min, dc_max = 75, 92
        ability = max(abilities, key=lambda name: float(stats.get(name, 0) or 0)) if stats else abilities[index % len(abilities)]
        major = power_leap or bool(MAJOR_RE.search(text))
        lethal = "high" if lethal_attempt else "moderate" if any(x in lower for x in ("boss", "deathmatch", "guardian", "elite", "alone against")) else "none"
        tracker = state.get("power_goal_tracker") if isinstance(state.get("power_goal_tracker"), dict) else {}
        action_key = re.sub(r"\s+", " ", text.strip().lower())
        prior_days = float(tracker.get("days_invested", 0) or 0) if power_leap and tracker.get("key") == action_key else 0
        preparation_bonus = min(20, int(prior_days // 3)) if power_leap else 0
        checks.append({
            "id": f"action_{index + 1}", "action_index": index, "reason": text[:80], "ability": ability,
            "skill": None, "difficulty_min": dc_min, "difficulty_max": dc_max,
            "relevant_average_stat": 30, "situational_bonus": preparation_bonus,
            "time_difficulty_modifier": int(budget.get("time_dc_modifier", 0) or 0) * 3,
            "major_event": major, "major_reason": "Extreme obstacle or major power leap" if major else "",
            "lethal_risk": lethal, "lethal_warning": "Failure could be fatal." if lethal == "high" else "",
        })
    power_action = next((a for a in actions or [] if POWER_RE.search(_text(a))), "")
    return {
        "checks": checks, "fixed_facts": "Mechanical preview compiled locally from campaign state.",
        "simulation_notes": f"{simulation_profile(mode)['label']} relevance limits apply.",
        "reachable_actions": list(budget.get("reachable_actions", [])),
        "deferred_actions": list(budget.get("deferred_actions", [])),
        "power_jump_warning": ("Power at that scale will require a genuine breakthrough and a world-valid cause." if power_action else ""),
        "assessment_source": "deterministic_local",
    }


def refresh_npc_intentions(state):
    intentions = state.setdefault("npc_intentions", {})
    relationships = state.get("npc_relationships") if isinstance(state.get("npc_relationships"), dict) else {}
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict):
            continue
        goal = _text(memory.get("immediate_goal") or memory.get("current_goal") or memory.get("goal"))
        if not goal and not (memory.get("recurring") or memory.get("nemesis")):
            continue
        row = intentions.setdefault(name, {})
        if goal and goal != row.get("goal"):
            row.update({"goal": goal, "progress": 0, "milestone": 0, "status": "active"})
        row.setdefault("goal", goal or "Pursue a private objective")
        row["plan"] = _text(memory.get("plan") or memory.get("next_action") or row.get("plan") or "Take the next practical step")
        row["next_action"] = _text(memory.get("next_action") or row.get("next_action") or row["plan"])
        row["resources"] = copy.deepcopy(memory.get("resources") or row.get("resources") or {})
        row["relationship"] = copy.deepcopy(relationships.get(name) or memory.get("attitude") or row.get("relationship") or "Unknown")
        row["knowledge"] = copy.deepcopy(memory.get("knowledge") or row.get("knowledge") or {})
        row["location"] = _text(memory.get("last_known_location") or row.get("location") or "Unknown")
        row["nemesis"] = bool(memory.get("nemesis") or row.get("nemesis"))
        row["recurring"] = bool(memory.get("recurring") or row.get("recurring") or row["nemesis"])
        row["status"] = row.get("status") or "active"
    # Do not delete old intentions: defeated, missing, or absent NPCs are
    # historical state.  They simply stop advancing unless marked active.
    enrich_npc_depth(state)
    return intentions


def _event_summary(event):
    if isinstance(event, dict):
        return _text(event.get("narrative") or event.get("message") or event.get("summary") or event.get("title"))
    return _text(event)


def event_importance(event):
    text = _event_summary(event).lower()
    kind = _text(event.get("type") if isinstance(event, dict) else "").lower()
    score = 25
    if kind in {"canon_event", "death", "danger", "combat", "quest_complete", "breakthrough"}: score += 55
    if any(x in text for x in ("died", "death", "destroyed", "canon", "invasion", "war", "awaken", "evolution", "quest complete", "turning point")): score += 45
    if any(x in text for x in ("player", "you ", "your ", "companion", "nearby", "current location")): score += 20
    if any(x in text for x in ("routine", "minor", "incremental", "continued", "small progress")): score -= 15
    return max(0, min(100, score))


def _fingerprint(text):
    words = re.findall(r"[a-z0-9']+", _text(text).lower())
    return hashlib.sha1(" ".join(words[:32]).encode("utf-8")).hexdigest()[:14]


def prioritize_updates(updates, mode="balanced"):
    """Deduplicate updates and summarize low-importance overflow."""
    profile = simulation_profile(mode)
    unique, seen = [], set()
    for raw in updates or []:
        if not isinstance(raw, dict) or not _event_summary(raw):
            continue
        row = copy.deepcopy(raw)
        row["importance"] = event_importance(row)
        key = _fingerprint(_event_summary(row))
        if key in seen:
            continue
        seen.add(key); unique.append(row)
    cap = profile["max_updates"]
    selected_indices = set(sorted(range(len(unique)), key=lambda i: (-unique[i]["importance"], i))[:cap])
    kept = [row for i, row in enumerate(unique) if i in selected_indices]
    overflow = [row for i, row in enumerate(unique) if i not in selected_indices]
    if overflow:
        summaries = [_event_summary(x).rstrip(". ") for x in overflow[:6]]
        kept.append({"type": "world", "title": "Wider World", "importance": 20,
                     "narrative": "Elsewhere, " + "; meanwhile, ".join(summaries) + "."})
    return kept


def record_simulation_events(state, events, source="turn"):
    ledger = state.setdefault("simulation_events", [])
    turn = int(state.get("turn", 0) or 0)
    day = int(state.get("canon_day", 0) or 0)
    for event in events or []:
        summary = _event_summary(event)
        if not summary:
            continue
        key = _fingerprint(summary)
        existing = next((x for x in reversed(ledger[-30:]) if x.get("fingerprint") == key and x.get("turn") == turn), None)
        if existing:
            if source not in existing["sources"]:
                existing["sources"].append(source)
            continue
        ledger.append({"id": f"e{turn}-{key}", "fingerprint": key, "turn": turn, "canon_day": day,
                       "summary": summary[:1000], "importance": event_importance(event),
                       "sources": [source], "recorded_at": datetime.now().isoformat(timespec="seconds")})
    state["simulation_events"] = ledger[-300:]
    return ledger


def advance_npc_intentions(state, elapsed_minutes, mode="balanced"):
    intentions = refresh_npc_intentions(state)
    bubble = relevance_bubble(state, "", mode)
    detailed = set(bubble["detailed_npcs"])
    days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    events = []
    for name, row in intentions.items():
        if not isinstance(row, dict) or row.get("status") != "active":
            continue
        previous = float(row.get("progress", 0) or 0)
        # Nearby actors move in fine increments; off-screen actors move in a
        # coarser but bounded step.  Neither receives a separate AI call.
        # Nemeses remain slow-burn threats, but their flag is carried into
        # this newer intention system rather than only the legacy clock.
        rate = (0.65 if row.get("nemesis") else 2.0) if name in detailed else (0.4 if row.get("nemesis") else 1.2)
        step = max(0.25 if elapsed_minutes else 0, min(18.0, days * rate))
        current = min(100.0, previous + step)
        row["progress"] = round(current, 1)
        row["detail"] = "full" if name in detailed else "coarse"
        row["last_advanced_day"] = state.get("canon_day", 0)
        milestone = int(current // 25)
        old_milestone = int(row.get("milestone", 0) or 0)
        if milestone > old_milestone:
            row["milestone"] = milestone
            events.append({"type": "world", "nemesis": bool(row.get("nemesis")), "message": f"{name} advances a {'scheme' if row.get('nemesis') else 'personal plan'}: {row.get('goal')}",
                           "importance": 55 if name in detailed else 35})
        if current >= 100:
            row["status"] = "turning_point"
            events.append({"type": "world", "nemesis": bool(row.get("nemesis")), "message": f"{name}'s {'scheme' if row.get('nemesis') else 'plan'} reaches a turning point: {row.get('goal')}", "importance": 90 if row.get("nemesis") else 80})
    record_simulation_events(state, events, "npc_intentions")
    return events


def background_ai_due(state, mode):
    interval = int(simulation_profile(mode).get("background_ai_interval", 0) or 0)
    turn = int(state.get("turn", 0) or 0)
    return bool(interval and turn and turn % interval == 0)
