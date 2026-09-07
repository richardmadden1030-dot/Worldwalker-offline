"""Deterministic campaign-direction and consequence helpers.

These functions turn state the game already owns into useful direction without
spending another model call.  The narrator may enrich the same records, but it
cannot make the campaign forget its goal, active pressures, or why a mechanical
change occurred.
"""
from __future__ import annotations

import copy
import re

from worlds import timeline_for


def _text(value):
    return str(value or "").strip()


def _list(value):
    if isinstance(value, list):
        return value
    return [] if value in (None, "") else [value]


def enrich_npc_depth(state):
    """Persist the motives required for an autonomous recurring character."""
    intentions = state.setdefault("npc_intentions", {})
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    player_relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    for name, row in intentions.items():
        if not isinstance(row, dict):
            continue
        memory = memories.get(name) if isinstance(memories.get(name), dict) else {}
        row["loyalties"] = copy.deepcopy(_list(memory.get("loyalties") or memory.get("allegiances") or row.get("loyalties")))[:8]
        row["fears"] = copy.deepcopy(_list(memory.get("fears") or memory.get("concerns") or row.get("fears")))[:8]
        # Secrets remain simulation-only.  They are deliberately not rendered
        # in the relationship panel merely because the narrator knows them.
        row["secrets"] = copy.deepcopy(_list(memory.get("secrets") or row.get("secrets")))[:8]
        row["opinion_of_player"] = _text(
            memory.get("opinion_of_player") or memory.get("attitude") or
            player_relationships.get(name) or row.get("opinion_of_player") or "Uncertain"
        )[:300]
        row["last_known_location"] = _text(memory.get("last_known_location") or row.get("location") or "Unknown")
    return intentions


def _next_canon_pressure(state):
    now = int(state.get("canon_time_minutes", int(state.get("canon_day", -7) or -7) * 1440 + 480) or 0)
    fired = set(state.get("canon_events_fired", []))
    candidates = []
    for event in timeline_for(state.get("world", "Custom World")).get("events", []):
        event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
        minute = int(event.get("day", 0) or 0) * 1440 + 480
        if minute > now and event_id not in fired:
            candidates.append((minute, event))
    if not candidates:
        return {}
    minute, event = min(candidates, key=lambda item: item[0])
    remaining = max(0, minute - now)
    return {
        "title": _text(event.get("title")), "location": _text(event.get("location")),
        "minutes_until": remaining, "days_until": round(remaining / 1440, 1),
        "summary": _text(event.get("summary"))[:600],
    }


def update_campaign_direction(state, actions=None, updates=None, elapsed_minutes=0):
    """Maintain a small, visible campaign-director state from existing facts."""
    actions = [_text(x) for x in (actions or []) if _text(x)]
    updates = [x for x in (updates or []) if isinstance(x, dict)]
    active_quests = [q for q in state.get("quests", []) if isinstance(q, dict) and _text(q.get("status", "active")).lower() not in {"complete", "completed", "failed", "archived", "abandoned"}]
    quest = active_quests[0] if active_quests else {}
    objectives = [o for o in quest.get("objectives", []) if isinstance(o, dict) and o.get("status", "active") == "active"]
    action_goals = [g for g in state.get("action_goals", []) if isinstance(g, dict) and g.get("status", "active") == "active"]
    primary_goal = (
        _text((action_goals[0] if action_goals else {}).get("action") or (action_goals[0] if action_goals else {}).get("goal")) or
        _text((objectives[0] if objectives else {}).get("text")) or
        _text(quest.get("name")) or (actions[0] if actions else _text((state.get("standing_orders") or [""])[0])) or
        "Choose what your character wants to accomplish next"
    )
    obstacles = _list(quest.get("current_obstacles") or quest.get("risks"))
    pressures = [_text(u.get("next_pressure")) for u in updates if _text(u.get("next_pressure"))]
    next_obstacle = (pressures[0] if pressures else _text(obstacles[0]) if obstacles else "No immediate obstacle has been confirmed")
    intentions = enrich_npc_depth(state)
    unresolved = [
        {"name": name, "goal": _text(row.get("goal")), "progress": row.get("progress", 0), "location": _text(row.get("location") or row.get("last_known_location"))}
        for name, row in intentions.items() if isinstance(row, dict) and row.get("status", "active") in {"active", "turning_point"}
    ]
    unresolved.sort(key=lambda row: (-float(row.get("progress", 0) or 0), row["name"].lower()))
    branch = quest.get("branch_state") if isinstance(quest.get("branch_state"), dict) else {}
    opportunities = [_text(x) for x in branch.get("available", []) if _text(x)]
    opportunities += [_text(x) for x in state.get("suggested_actions", []) if _text(x)]
    unique_opportunities = []
    for item in opportunities:
        if item.lower() not in {x.lower() for x in unique_opportunities}:
            unique_opportunities.append(item[:240])
    previous = state.get("campaign_direction") if isinstance(state.get("campaign_direction"), dict) else {}
    meaningful = bool(actions or any(int(u.get("importance", 0) or 0) >= 60 for u in updates))
    inactivity = 0 if meaningful else int(previous.get("inactivity_turns", 0) or 0) + 1
    state["campaign_direction"] = {
        "primary_goal": primary_goal[:500], "next_obstacle": next_obstacle[:500],
        "unresolved_characters": unresolved[:8], "nearby_opportunities": unique_opportunities[:5],
        "approaching_canon_event": _next_canon_pressure(state),
        "inactivity_turns": inactivity, "last_updated_turn": int(state.get("turn", 0) or 0),
        "elapsed_minutes_considered": max(0, int(elapsed_minutes or 0)),
    }
    return state["campaign_direction"]


def maybe_offer_relationship_scene(state, updates=None):
    """Offer, never force, one grounded character scene when timing permits."""
    turn = int(state.get("turn", 0) or 0)
    existing = state.setdefault("relationship_opportunities", [])
    if turn <= 0 or turn % 3 or any(isinstance(x, dict) and x.get("status") == "available" for x in existing[-4:]):
        return None
    location = _text(state.get("location")).lower()
    candidates = []
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict) or memory.get("nemesis"):
            continue
        npc_location = _text(memory.get("last_known_location")).lower()
        if location and npc_location and npc_location != location:
            continue
        topic = _text(memory.get("immediate_goal") or memory.get("goal"))
        if not topic:
            promises = _list(memory.get("promises"))
            topic = _text(promises[0]) if promises else "what has changed between you"
        score = 20 if npc_location == location else 0
        score += 20 if memory.get("recurring") else 0
        candidates.append((score, _text(name), topic))
    if not candidates:
        return None
    _, name, topic = max(candidates, key=lambda row: (row[0], row[1]))
    prompt = f"Talk with {name} about {topic}"[:240]
    row = {"npc": name, "prompt": prompt, "reason": f"{name} is nearby and has something unresolved with you.",
           "created_turn": turn, "status": "available"}
    existing.append(row)
    state["relationship_opportunities"] = existing[-30:]
    return row


def build_cause_effect(before, state, actions=None, rolls=None):
    """Explain the important mechanical deltas from the player's perspective."""
    actions = [_text(x) for x in (actions or []) if _text(x)]
    rolls = [r for r in (rolls or []) if isinstance(r, dict)]
    rows = []
    fallback_action = actions[0] if actions else "the world advancing"

    def reason_for(label=""):
        match = next((r for r in rolls if _text(r.get("action")) and (_text(r.get("action")) in actions or _text(r.get("action")).lower() in label.lower())), None)
        if match:
            result = "succeeded" if match.get("success") else "failed"
            return f"The check for {_text(match.get('action')) or label} {result} at {match.get('total', match.get('roll', '?'))} versus {match.get('difficulty', '?')}."
        return f"This follows from {fallback_action}."

    old_stats, new_stats = before.get("stats", {}) or {}, state.get("stats", {}) or {}
    for name, value in new_stats.items():
        try:
            delta = float(value) - float(old_stats.get(name, value))
        except (TypeError, ValueError):
            continue
        if delta:
            rows.append({"category": "Growth", "target": name, "change": f"{old_stats.get(name)} → {value}", "because": reason_for(name)})
    old_skills, new_skills = before.get("skills", {}) or {}, state.get("skills", {}) or {}
    for name in new_skills:
        if name not in old_skills:
            rows.append({"category": "Skill", "target": name, "change": "Learned", "because": reason_for(name)})
    old_titles = {_text(x) for x in before.get("titles", [])}
    for title in [_text(x) for x in state.get("titles", []) if _text(x) not in old_titles]:
        rows.append({"category": "Title", "target": title, "change": "Earned", "because": reason_for(title)})
    if before.get("location") != state.get("location"):
        rows.append({"category": "Location", "target": _text(state.get("location")), "change": f"Moved from {_text(before.get('location'))}", "because": reason_for("travel")})
    old_relationships = before.get("relationships") if isinstance(before.get("relationships"), dict) else {}
    new_relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    for name, value in new_relationships.items():
        if old_relationships.get(name) != value:
            rows.append({"category": "Relationship", "target": name, "change": f"{old_relationships.get(name, 'Unknown')} → {value}", "because": reason_for(name)})
    old_quests = {str(q.get("name")): q for q in before.get("quests", []) if isinstance(q, dict)}
    for quest in state.get("quests", []):
        if not isinstance(quest, dict):
            continue
        name = _text(quest.get("name"))
        old = old_quests.get(name, {})
        if not old:
            rows.append({"category": "Quest", "target": name, "change": "Started", "because": reason_for(name)})
        elif old.get("progress_percent") != quest.get("progress_percent"):
            rows.append({"category": "Quest", "target": name, "change": f"{old.get('progress_percent', 0)}% → {quest.get('progress_percent', 0)}%", "because": reason_for(name)})
    state["last_cause_effect"] = rows[:16]
    return state["last_cause_effect"]


def ensure_productive_failures(data, rolls):
    """Guarantee that failed checks create a setback, clue, or partial gain."""
    if not isinstance(data, dict):
        return data
    updates = data.setdefault("updates", [])
    suggestions = data.setdefault("suggested_actions", [])
    represented = " ".join(_text(u.get("related_action")) + " " + _text(u.get("narrative")) for u in updates if isinstance(u, dict)).lower()
    for index, roll in enumerate(rolls or []):
        if not isinstance(roll, dict) or roll.get("success"):
            continue
        action = _text(roll.get("action") or roll.get("reason") or "the attempt")
        if action.lower() in represented:
            continue
        lower = action.lower()
        if re.search(r"train|practice|study|learn|master", lower):
            consequence = "The attempt falls short, but it reveals the exact weakness preventing progress instead of erasing the work already invested."
            lead = f"Address the weakness exposed while trying to {action}"[:220]
        elif re.search(r"talk|ask|persuade|convince|deceive|negotiate", lower):
            consequence = "The answer is not won, but the reaction exposes a condition, hesitation, or pressure that can be approached differently."
            lead = f"Reapproach {action} using the condition the reaction revealed"[:220]
        elif re.search(r"fight|attack|duel|battle|escape|infiltrate", lower):
            consequence = "The attempt fails and leaves the opposition better positioned, but their response exposes a usable habit or opening."
            lead = f"Exploit the opening revealed by the failed attempt to {action}"[:220]
        else:
            consequence = "The attempt does not achieve its goal; time and position are lost, but the setback reveals a concrete next lead."
            lead = f"Try a different approach to {action}"[:220]
        updates.append({"sequence": 8800 + index, "type": "consequence", "title": "Setback Creates a New Lead",
                        "related_action": action, "narrative": consequence,
                        "why_it_matters": "Failure changes the situation instead of stopping the story.",
                        "player_knowledge": "You now know what blocked the attempt.", "next_pressure": lead})
        suggestions.insert(0, lead)
    return data
