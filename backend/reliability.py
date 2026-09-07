"""Application-owned reliability, memory, discovery, and progression helpers.

The GM can propose narrative state, but these records are derived and maintained
by the application so a smaller model cannot accidentally erase campaign memory
or relabel a mechanical change after the fact.
"""
from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher

from util import ai_text


MEMORY_CATEGORIES = (
    "established_facts", "player_goals", "unresolved_mysteries",
    "promises", "relationships", "consequences",
)


def _memory_store(state):
    memory = state.setdefault("narrative_memory", {})
    for category in MEMORY_CATEGORIES:
        if not isinstance(memory.get(category), list):
            memory[category] = []
    return memory


def _memory_text(value):
    if isinstance(value, dict):
        return ai_text(value.get("text") or value.get("summary") or value.get("fact") or value.get("goal"))
    return ai_text(value)


def _add_memory(state, category, text, source="GM", status="active"):
    text = re.sub(r"\s+", " ", ai_text(text)).strip()[:700]
    if not text or category not in MEMORY_CATEGORIES:
        return None
    rows = _memory_store(state)[category]
    key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    for row in rows:
        if isinstance(row, dict) and row.get("key") == key:
            row.update(turn=state.get("turn", 0), canon_day=state.get("canon_day"), status=status)
            return row
    row = {
        "text": text, "key": key, "source": source, "status": status,
        "turn": state.get("turn", 0), "canon_day": state.get("canon_day"),
    }
    rows.append(row)
    _memory_store(state)[category] = rows[-120:]
    return row


def update_narrative_memory(before, state, action="", narrative=""):
    """Consume GM-authored memory suggestions and add deterministic facts.

    ``memory_updates`` is intentionally transient: the GM may suggest concise
    records, but only this function writes the permanent narrative_memory.
    """
    updates = state.pop("memory_updates", {})
    if isinstance(updates, dict):
        aliases = {
            "facts": "established_facts", "goals": "player_goals",
            "mysteries": "unresolved_mysteries", "relationship": "relationships",
            "consequence": "consequences",
        }
        for raw_category, values in updates.items():
            category = aliases.get(raw_category, raw_category)
            if category not in MEMORY_CATEGORIES:
                continue
            if not isinstance(values, list):
                values = [values]
            for value in values[:20]:
                text = _memory_text(value)
                status = str(value.get("status", "active")) if isinstance(value, dict) else "active"
                _add_memory(state, category, text, "GM", status)

    if before.get("location") != state.get("location") and state.get("location"):
        _add_memory(state, "established_facts", f"The player reached {state['location']}.", "State change", "established")
    before_skills = before.get("skills", {}) if isinstance(before.get("skills"), dict) else {}
    after_skills = state.get("skills", {}) if isinstance(state.get("skills"), dict) else {}
    for name in after_skills.keys() - before_skills.keys():
        _add_memory(state, "established_facts", f"The player learned {name}.", "Progression", "established")
    before_titles = {ai_text(x) for x in before.get("titles", [])}
    for title in {ai_text(x) for x in state.get("titles", [])} - before_titles:
        if title:
            _add_memory(state, "consequences", f"The player earned the title {title}.", "Progression", "established")
    old_quests = {str(q.get("name", "")).lower() for q in before.get("quests", []) if isinstance(q, dict)}
    for quest in state.get("quests", []):
        if not isinstance(quest, dict) or str(quest.get("name", "")).lower() in old_quests:
            continue
        goal = quest.get("completion_conditions") or quest.get("clear_conditions") or quest.get("objectives") or []
        if isinstance(goal, list) and goal:
            goal = goal[0].get("text") if isinstance(goal[0], dict) else goal[0]
        _add_memory(state, "player_goals", f"{quest.get('name')}: {goal or quest.get('explanation', 'See the quest through.')}", "Quest", "active")
    before_divergences = before.get("canon_divergences", []) if isinstance(before.get("canon_divergences"), list) else []
    for divergence in (state.get("canon_divergences", []) or [])[len(before_divergences):]:
        _add_memory(state, "consequences", _memory_text(divergence), "Canon divergence", "established")

    # Capture an explicit promise without trying to manufacture one from any
    # ordinary future-tense sentence. The structured GM field remains the
    # preferred route, but this keeps a plainly narrated oath from vanishing.
    for sentence in re.split(r"(?<=[.!?])\s+", str(narrative or "")):
        if re.search(r"\b(?:you promise|you swear|your word|vow to)\b", sentence, re.I):
            _add_memory(state, "promises", sentence, "Narrative", "active")
    return copy.deepcopy(_memory_store(state))


def narrative_memory_snapshot(state):
    memory = copy.deepcopy(_memory_store(state))
    # Relationship records are also projected from the authoritative NPC
    # memory so the long-term-memory page never disagrees with Relationships.
    projected = []
    for name, value in (state.get("npc_memories") or {}).items():
        if not isinstance(value, dict):
            continue
        projected.append({
            "text": f"{name}: {value.get('attitude', 'Unknown')} — {value.get('immediate_goal') or value.get('goal') or 'goal unknown'}",
            "source": "Relationship state", "status": value.get("status", "active"),
            "turn": state.get("turn", 0), "canon_day": state.get("canon_day"),
        })
    if projected:
        memory["relationships"] = projected[-80:]
    return memory


def _detail_text(value):
    if isinstance(value, dict):
        return " ".join(ai_text(value.get(k)) for k in ("description", "effect", "limitation", "growth_path") if value.get(k))
    return ai_text(value)


def validate_campaign_state(before, after, narrative=""):
    """Return high-confidence contradictions not covered by type validation."""
    warnings = []
    memories = after.get("npc_memories") if isinstance(after.get("npc_memories"), dict) else {}
    companions = after.get("companions") if isinstance(after.get("companions"), list) else []
    player_location = ai_text(after.get("location")) if after.get("location") not in (None, "") else ""
    for container_name in ("current_activity", "combat"):
        container = after.get(container_name) if isinstance(after.get(container_name), dict) else {}
        other_location = ai_text(container.get("location")) if container.get("location") not in (None, "") else ""
        if player_location and other_location and player_location != other_location:
            warnings.append(f"The player is simultaneously placed at {player_location} and {other_location} ({container_name}).")
    for companion in companions:
        if not isinstance(companion, dict) or not companion.get("name"):
            continue
        name = str(companion["name"])
        memory = memories.get(name) if isinstance(memories.get(name), dict) else {}
        status = str(memory.get("status", "")).lower()
        if status in {"deceased", "dead", "destroyed"}:
            warnings.append(f"{name} is marked {status} but is still listed as an active companion.")
        companion_location = companion.get("location")
        known_location = memory.get("last_known_location")
        if companion_location and known_location and known_location != "Unknown" and companion_location != known_location:
            warnings.append(f"{name} is simultaneously placed at {companion_location} and {known_location}.")

    before_skills = before.get("skills") if isinstance(before.get("skills"), dict) else {}
    after_skills = after.get("skills") if isinstance(after.get("skills"), dict) else {}
    removed = [name for name in before_skills if name not in after_skills]
    added = [name for name in after_skills if name not in before_skills]
    for old_name in removed:
        old_detail = _detail_text(before_skills[old_name]).lower()
        for new_name in added:
            new_detail = _detail_text(after_skills[new_name]).lower()
            if old_detail and new_detail and SequenceMatcher(None, old_detail, new_detail).ratio() >= .78:
                warnings.append(f"Ability '{old_name}' appears to have been renamed '{new_name}' without an explained evolution.")

    title_names = [ai_text(value.get("name") or value.get("title")) if isinstance(value, dict) else ai_text(value)
                   for value in after.get("titles", [])]
    if len([name for name in title_names if name]) != len(set(name.lower() for name in title_names if name)):
        warnings.append("The title list contains a duplicated reward.")
    achievement_names = [ai_text(value.get("name") or value.get("title")) if isinstance(value, dict) else ai_text(value)
                         for value in after.get("achievements", [])]
    if len([name for name in achievement_names if name]) != len(set(name.lower() for name in achievement_names if name)):
        warnings.append("The achievement list contains a duplicated reward.")

    now = after.get("canon_day")
    if isinstance(now, (int, float)):
        for event in after.get("scheduled_events", []) or []:
            if not isinstance(event, dict) or event.get("resolved") or event.get("due_canon_day") is None:
                continue
            try:
                due = float(event["due_canon_day"])
            except (TypeError, ValueError):
                continue
            if due < float(now) - 1:
                warnings.append(f"Scheduled event '{event.get('title') or event.get('name') or 'Unnamed event'}' is overdue but unresolved.")
    return list(dict.fromkeys(warnings))[:30]


def _event_match(divergence, event):
    if isinstance(divergence, dict):
        named = ai_text(divergence.get("event") or divergence.get("title") or divergence.get("canon_event"))
        blob = " ".join(ai_text(divergence.get(k)) for k in ("event", "title", "canon_event", "text", "reason", "replacement"))
    else:
        named, blob = "", ai_text(divergence)
    title = ai_text(event.get("title"))
    if named and (named.lower() in title.lower() or title.lower() in named.lower()):
        return True
    stop = {"the", "and", "with", "from", "into", "that", "this", "event", "canon"}
    event_words = {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3 and w not in stop}
    blob_words = set(re.findall(r"[a-z0-9]+", blob.lower()))
    return bool(event_words and len(event_words & blob_words) >= min(2, len(event_words)))


def canon_event_tracker(state, events):
    """Project each fixed event as likely, altered, delayed, or impossible."""
    current_day = int(state.get("canon_day", 0) or 0)
    fired = set(state.get("canon_events_fired", []) or [])
    divergences = state.get("canon_divergences", []) if isinstance(state.get("canon_divergences"), list) else []
    rows = []
    for event in events or []:
        day = int(event.get("day", 0) or 0)
        event_id = f"day:{day}:{event.get('title', 'event')}"
        status = "occurred" if event_id in fired or day < current_day else "likely"
        reason = "No known divergence currently prevents this event."
        replacement = ""
        effective_day = day
        matched = next((d for d in reversed(divergences) if _event_match(d, event)), None)
        if matched is not None:
            blob = _memory_text(matched)
            raw_status = str(matched.get("status", "") if isinstance(matched, dict) else "").lower()
            if raw_status in {"impossible", "prevented", "cancelled", "canceled"} or re.search(r"\b(impossible|prevented|cannot occur|no longer possible|averted)\b", blob, re.I):
                status = "impossible"
            elif raw_status == "delayed" or re.search(r"\b(delay|postpone)\w*\b", blob, re.I):
                status = "delayed"
            else:
                status = "altered"
            if isinstance(matched, dict):
                reason = ai_text(matched.get("reason") or matched.get("text")) or blob
                replacement = ai_text(matched.get("replacement") or matched.get("alternate_event"))
                try:
                    effective_day = int(matched.get("new_day", matched.get("delayed_until", day)))
                except (TypeError, ValueError):
                    effective_day = day
            else:
                reason = blob
            if status == "impossible" and not replacement:
                replacement = "The original event cannot occur; its surviving motives and faction pressures must produce a new consequence."
        rows.append({**copy.deepcopy(event), "status": status, "reason": reason,
                     "replacement": replacement, "effective_day": effective_day})
    return rows


def record_progression_ledger(before, after, cause="", elapsed_minutes=0, rolls=None):
    """Record an exact, player-readable diff for every lasting growth change."""
    changes = []
    before_stats = before.get("stats") if isinstance(before.get("stats"), dict) else {}
    after_stats = after.get("stats") if isinstance(after.get("stats"), dict) else {}
    for name in sorted(set(before_stats) | set(after_stats)):
        old, new = before_stats.get(name), after_stats.get(name)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
            changes.append({"kind": "stat", "name": name, "before": old, "after": new, "delta": new - old})
    for key, label in (("level", "Level"), ("xp", "XP"), ("hp_max", "Maximum HP"), ("resource_max", f"Maximum {after.get('resource_name', 'Resource')}")):
        old, new = before.get(key), after.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
            changes.append({"kind": key, "name": label, "before": old, "after": new, "delta": new - old})
    old_skills = before.get("skills") if isinstance(before.get("skills"), dict) else {}
    new_skills = after.get("skills") if isinstance(after.get("skills"), dict) else {}
    for name in new_skills.keys() - old_skills.keys():
        changes.append({"kind": "skill", "name": name, "change": "learned"})
    old_titles = {ai_text(x) for x in before.get("titles", [])}
    for title in {ai_text(x) for x in after.get("titles", [])} - old_titles:
        if title:
            changes.append({"kind": "title", "name": title, "change": "earned"})
    old_class = before.get("class_profile") if isinstance(before.get("class_profile"), dict) else {}
    new_class = after.get("class_profile") if isinstance(after.get("class_profile"), dict) else {}
    if old_class.get("name") != new_class.get("name") and new_class.get("name"):
        changes.append({"kind": "class", "name": new_class.get("name"), "change": "awakened"})
    old_progress = (old_class.get("discovery") or {}).get("progress", 100)
    new_progress = (new_class.get("discovery") or {}).get("progress", 100)
    if new_progress != old_progress:
        changes.append({"kind": "class_discovery", "name": new_class.get("name", "Hidden Class"),
                        "before": old_progress, "after": new_progress, "delta": new_progress - old_progress})
    if not changes:
        return None
    roll_notes = []
    for roll in rolls or []:
        if isinstance(roll, dict):
            roll_notes.append(f"{roll.get('action', 'Check')}: {roll.get('total', roll.get('roll', '?'))}/{roll.get('difficulty', '?')} {'success' if roll.get('success') else 'failure'}")
    entry = {
        "type": "ledger", "turn": after.get("turn", 0), "canon_day": after.get("canon_day"),
        "cause": ai_text(cause) or "Story development", "elapsed_minutes": int(elapsed_minutes or 0),
        "rolls": roll_notes[:12], "changes": changes,
        "explanation": "Changes are derived from the completed actions, elapsed time, outcomes, and world rules shown here.",
    }
    after.setdefault("progression_ledger", []).append(entry)
    after["progression_ledger"] = after["progression_ledger"][-300:]
    return entry


def advance_hidden_class_discovery(state, action=""):
    profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    if not profile or not discovery.get("concealed"):
        return False
    text = ai_text(action).lower()
    raw_signature = profile.get("signature_skill")
    signature = ai_text(raw_signature.get("name") if isinstance(raw_signature, dict) else raw_signature).lower()
    relevant = bool(re.search(r"\b(hidden class|class|apprais|identify|inspect|meditat|train|practice|experiment|awaken)\w*\b", text))
    if signature and any(word in text for word in signature.split() if len(word) > 4):
        relevant = True
    if not relevant:
        return False
    progress = min(100, int(discovery.get("progress", 0) or 0) + (35 if "class" in text or "apprais" in text else 20))
    discovery["progress"] = progress
    discovery["stage"] = "understood" if progress >= 100 else "identified" if progress >= 70 else "manifesting" if progress >= 35 else "dormant"
    if progress >= 100:
        discovery["concealed"] = False
    profile["discovery"] = discovery
    state["class_profile"] = profile
    if isinstance(state.get("special", {}).get("Hidden Class"), dict):
        state["special"]["Hidden Class"] = copy.deepcopy(profile)
    return True


def visible_class_profile(state_or_profile):
    profile = state_or_profile.get("class_profile", {}) if "class_profile" in state_or_profile else state_or_profile
    if not isinstance(profile, dict) or not profile:
        return {}
    visible = copy.deepcopy(profile)
    discovery = visible.get("discovery") if isinstance(visible.get("discovery"), dict) else {}
    if not discovery.get("concealed"):
        visible.pop("true_name", None)
        return visible
    progress = int(discovery.get("progress", 0) or 0)
    public_name = discovery.get("public_name") or "Unidentified Class Signature"
    legacy = re.fullmatch(r"Unidentified (.+) Class", str(public_name), re.I)
    if legacy:
        public_name = f"Unidentified Hidden Class — {legacy.group(1)} affinity"
    visible["name"] = public_name
    visible["description"] = discovery.get("clue") or "A dormant class-shaped power is present, but its nature is not yet understood."
    visible["effect"] = "Some bonuses are already active; their exact source remains unclear." if progress < 70 else visible.get("effect", "Its core feature is becoming clear.")
    if progress < 50:
        visible.pop("signature_skill", None)
    if progress < 70:
        visible.pop("stat_bonuses", None)
        visible["limitation"] = "Use, appraisal, or class-relevant training is required to identify it."
        visible["growth_path"] = "Experiment with the unusual capability and seek someone or something able to appraise hidden paths."
    visible.pop("true_name", None)
    return visible


def visible_skills(state):
    skills = copy.deepcopy(state.get("skills", {})) if isinstance(state.get("skills"), dict) else {}
    evolution = state.get("ability_evolution") if isinstance(state.get("ability_evolution"), dict) else {}
    for name, detail in list(skills.items()):
        history = evolution.get(name) if isinstance(evolution.get(name), dict) else {}
        if not history:
            continue
        if not isinstance(detail, dict):
            detail = {"description": str(detail)}
            skills[name] = detail
        detail["developed_applications"] = copy.deepcopy(history.get("applications", []))
        detail["evolution_history"] = [
            str(row.get("development") or "").strip()
            + (f" — {str(row.get('application')).strip()}" if str(row.get("application") or "").strip() else "")
            for row in history.get("history", [])[-8:] if isinstance(row, dict) and str(row.get("development") or "").strip()
        ]
    profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    if discovery.get("concealed") and int(discovery.get("progress", 0) or 0) < 50:
        signature = profile.get("signature_skill")
        if signature:
            skills.pop(str(signature), None)
    return skills
