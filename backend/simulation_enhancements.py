"""Local simulation depth added in v3.41.0.

The functions here never call an AI model.  They convert already-established
campaign state into bounded progression, dated Chronicle beats, communication
hooks, and prompt budgets.  Narration remains flexible while the underlying
facts stay persistent and inexpensive.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from util import ai_text


WORLD_DOWNTIME = {
    "Naruto": ("Shinobi Downtime", "Mission reports, intelligence, team practice, recovery, and village obligations continued around the active plan."),
    "Bleach": ("Division Routine", "Patrols, reports, Konso duties, training, and the Soul Society's chain of command continued between major incidents."),
    "One Piece": ("Voyage Between Headlines", "Navigation, shipboard routines, island rumors, newspapers, and crew responsibilities continued around the voyage."),
    "Hunter x Hunter": ("Hunter Work", "Research, contacts, travel, examinations, information trading, and Nen practice continued between major encounters."),
    "Jujutsu Kaisen": ("Jujutsu Duties", "Mission reports, residual analysis, barrier preparation, civilian protection, and headquarters pressure continued in the background."),
    "Overgeared": ("Satisfy Activity", "Quests, rankings, guild activity, NPC relationships, equipment upkeep, and class opportunities continued throughout Satisfy."),
    "Solo Max-Level Newbie": ("Tower Interval", "System notices, floor reconnaissance, hidden-condition research, rival movement, and build preparation continued between major clears."),
    "Reincarnated as a Slime": ("Nation and Household", "Subordinates, settlement work, trade, defense, naming obligations, and diplomacy continued without waiting for direct orders."),
    "Custom World": ("Life Between Turning Points", "Work, relationships, local obligations, recovery, and wider-world developments continued around the active plan."),
}

WORLD_MESSAGE_MEDIUM = {
    "Naruto": "mission report or messenger",
    "Bleach": "Hell Butterfly or division report",
    "One Piece": "Den Den Mushi, newspaper, or courier",
    "Hunter x Hunter": "call, message, or Hunter contact",
    "Jujutsu Kaisen": "phone message or headquarters report",
    "Overgeared": "Satisfy whisper or system mail",
    "Solo Max-Level Newbie": "system message or player contact",
    "Reincarnated as a Slime": "messenger, Thought Communication, or diplomatic report",
    "Custom World": "setting-appropriate message",
}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _name(value):
    if isinstance(value, dict):
        return ai_text(value.get("name") or value.get("title") or value.get("label"))
    return ai_text(value)


def _fingerprint(*parts):
    return hashlib.sha256("|".join(ai_text(part).casefold() for part in parts).encode("utf-8")).hexdigest()[:16]


def normalize_dated_updates(updates, start_day, end_day, elapsed_minutes):
    """Give long-skip cards stable chronology without inventing story facts."""
    rows = [copy.deepcopy(row) for row in (updates or []) if isinstance(row, dict) and ai_text(row.get("narrative") or row.get("message"))]
    if not rows:
        return rows
    start_day, end_day = int(start_day or 0), int(end_day or start_day or 0)
    span = max(0, end_day - start_day)
    long_skip = int(elapsed_minutes or 0) >= 1440
    total = len(rows)
    for index, row in enumerate(rows):
        if long_skip and row.get("canon_day") in (None, ""):
            # Preserve authored ordering while spreading cards through the
            # interval. A one-card response remains anchored at the end.
            fraction = (index + 1) / max(1, total)
            row["canon_day"] = start_day + min(span, max(0, round(span * fraction)))
        row.setdefault("sequence", index + 1)
        row.setdefault("section", _update_section(row))
    return rows


def _update_section(row):
    blob = " ".join(ai_text(row.get(key)) for key in ("type", "title", "narrative", "related_action")).lower()
    if re.search(r"\b(train|practice|master|learn|level|xp|skill|class|evol)", blob): return "progression"
    if re.search(r"\b(message|letter|report|rumou?r|newspaper|broadcast)", blob): return "communication"
    if re.search(r"\b(companion|party|ally|relationship|bond)", blob): return "companions"
    if re.search(r"\b(canon|war|faction|village|kingdom|guild|world)", blob): return "world"
    return "story"


def advance_companion_autonomy(state, elapsed_minutes):
    """Advance delegated companion work and growth at milestone boundaries."""
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days <= 0:
        return []
    intents = [row for row in state.get("standing_intents", []) if isinstance(row, dict) and row.get("status", "active") == "active"]
    companions = state.get("companions") if isinstance(state.get("companions"), list) else []
    ledger = state.setdefault("companion_autonomy", {})
    events = []
    for companion in companions:
        if not isinstance(companion, dict) or not _name(companion):
            continue
        name = _name(companion)
        assigned = []
        for intent in intents:
            responsible = ai_text(intent.get("responsible") or intent.get("owner") or "").casefold()
            if responsible and (name.casefold() in responsible or responsible in {"party", "companions", "team", "crew"}):
                assigned.append(ai_text(intent.get("outcome") or intent.get("directive") or intent.get("text")))
        assigned.extend(ai_text(item) for item in companion.get("standing_orders", []) if ai_text(item))
        assigned = list(dict.fromkeys(item for item in assigned if item))
        if not assigned:
            continue
        if not isinstance(ledger.get(name), dict):
            ledger[name] = {"progress": 0.0, "milestone": 0, "history": []}
        row = ledger[name]
        previous = _number(row.get("progress"))
        loyalty = _number(companion.get("loyalty"), 50)
        health = ai_text(companion.get("condition") or "healthy").lower()
        condition_factor = .55 if any(word in health for word in ("injured", "wounded", "critical")) else 1.0
        gain = min(45.0, days * (1.1 + max(0.0, loyalty - 50.0) / 250.0) * condition_factor)
        current = min(100.0, previous + gain)
        row.update({"progress": round(current, 1), "directives": assigned[:4], "last_advanced_day": state.get("canon_day")})
        companion["autonomy_progress"] = round(current, 1)
        companion["active_directives"] = assigned[:4]
        milestone = int(current // 25)
        if milestone > int(row.get("milestone", 0) or 0):
            row["milestone"] = milestone
            development = f"{name} made meaningful independent progress on: {assigned[0]}"
            history = row.setdefault("history", [])
            history.append({"turn": state.get("turn", 0), "canon_day": state.get("canon_day"), "development": development})
            row["history"] = history[-20:]
            events.append({"type": "companion", "title": f"{name}'s Independent Progress", "narrative": development + ".", "importance": 58})
    state["companion_autonomy"] = ledger
    return events


def advance_npc_development(state, elapsed_minutes):
    """Let recurring NPCs develop from their own work, never from player scaling."""
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days < 1:
        return []
    registry = state.setdefault("npc_development", {})
    events = []
    organized = {name for group in (state.get("organizations") or {}).values() if isinstance(group, dict) for name in (group.get("members") or {})}
    companions = {_name(row).casefold() for row in state.get("companions", []) if _name(row)}
    for name, memory in (state.get("npc_memories") or {}).items():
        if name in organized:
            continue  # organization life progression owns these NPCs; never award twice
        if not isinstance(memory, dict) or str(memory.get("status", "active")).lower() in {"dead", "deceased"}:
            continue
        goal = ai_text(memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"))
        active = bool(memory.get("recurring") or memory.get("nemesis") or str(name).casefold() in companions)
        if not active:
            continue
        if not isinstance(registry.get(str(name)), dict):
            registry[str(name)] = {"progress": 0.0, "milestone": 0, "history": []}
        row = registry[str(name)]
        training = bool(re.search(r"\b(train|practice|study|learn|master|mission|fight|hunt|research|prepare)\w*\b", goal, re.I))
        rate = .9 if training else .35
        if memory.get("nemesis"): rate *= .65
        previous = _number(row.get("progress"))
        current = previous + min(30.0, days * rate)
        row.update({"progress": round(current, 1), "basis": goal or "Ongoing personal activity",
                    "last_advanced_day": state.get("canon_day"), "independent_of_player": True})
        memory["development_progress"] = round(current % 100, 1)
        milestone = int(current // 25)
        if milestone > int(row.get("milestone", 0) or 0):
            crossed = milestone - int(row.get("milestone", 0) or 0)
            row["milestone"] = milestone
            if training:
                old_bonus = _number(memory.get("development_bonus"), 0)
                power_gain = max(1.0, round((2.0 + min(8.0, _number(memory.get("power_score") or memory.get("power"), 20) * .025)) * crossed, 1))
                memory["development_bonus"] = round(old_bonus + power_gain, 1)
                row["power_growth"] = round(_number(row.get("power_growth"), 0) + power_gain, 1)
                if isinstance(memory.get("power_score"), (int, float)):
                    memory["power_score"] = round(_number(memory.get("power_score")) + power_gain, 1)
            if training:
                detail = f"{name} has made independent progress toward: {goal or 'their current training'}"
                title = f"{name}'s Training Progress"
            else:
                detail = f"{name}'s situation has moved forward. Current direction: {goal or 'their own continuing activity'}"
                title = f"{name}'s Ongoing Story"
            row.setdefault("history", []).append({"turn": state.get("turn", 0), "canon_day": state.get("canon_day"), "detail": detail})
            row["history"] = row["history"][-20:]
            events.append({"type": "world", "title": title, "narrative": detail.rstrip(".") + ".", "importance": 45})
    state["npc_development"] = registry
    return events


def record_ability_evolution(before, state, data, actions=None):
    """Persist an ability's applications and breakthroughs across the campaign."""
    ledger = state.setdefault("ability_evolution", {})
    authored = data.get("ability_developments") if isinstance(data, dict) and isinstance(data.get("ability_developments"), list) else []
    old_skills = before.get("skills") if isinstance(before.get("skills"), dict) else {}
    new_skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name, detail in new_skills.items():
        if name not in old_skills:
            authored.append({"ability": name, "kind": "learned", "development": "Ability learned", "application": ""})
        elif isinstance(detail, dict) and isinstance(old_skills.get(name), dict):
            old_apps = {ai_text(item) for item in old_skills[name].get("applications", []) if ai_text(item)}
            for application in detail.get("applications", []) if isinstance(detail.get("applications"), list) else []:
                if ai_text(application) and ai_text(application) not in old_apps:
                    authored.append({"ability": name, "kind": "application", "development": "New application developed", "application": ai_text(application)})
    seen = set()
    for raw in authored[:30]:
        if not isinstance(raw, dict):
            continue
        ability = ai_text(raw.get("ability") or raw.get("name"))
        development = ai_text(raw.get("development") or raw.get("effect") or raw.get("kind"))
        if not ability or not development:
            continue
        key = _fingerprint(ability, development, raw.get("application"), state.get("turn"))
        if key in seen:
            continue
        seen.add(key)
        row = ledger.setdefault(ability, {"name": ability, "applications": [], "history": []})
        application = ai_text(raw.get("application"))
        if application and application.casefold() not in {ai_text(item).casefold() for item in row.get("applications", [])}:
            row.setdefault("applications", []).append(application)
        row.setdefault("history", []).append({
            "turn": int(state.get("turn", 0) or 0), "canon_day": state.get("canon_day"),
            "kind": ai_text(raw.get("kind") or "development"), "development": development[:500],
            "application": application[:300], "evidence": ai_text(raw.get("evidence") or "; ".join(actions or []))[:500],
        })
        row["applications"] = row.get("applications", [])[-30:]
        row["history"] = row.get("history", [])[-40:]
    state["ability_evolution"] = ledger
    return ledger


def world_downtime_events(state, elapsed_minutes, actions=None):
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days < 7:
        return []
    world = state.get("world", "Custom World")
    title, narrative = WORLD_DOWNTIME.get(world, WORLD_DOWNTIME["Custom World"])
    row = state.setdefault("world_downtime_cycles", {})
    if not isinstance(row, dict):
        row = state["world_downtime_cycles"] = {}
    prior_cycle = int(row.get("cycle", 0) or 0)
    cycle = prior_cycle + max(1, int(days // 7))
    row.update({"cycle": cycle, "last_canon_day": state.get("canon_day"), "world": world,
                "active_plan": [ai_text(item) for item in actions or [] if ai_text(item)][:4]})
    return [{"type": "downtime", "title": title, "narrative": narrative, "importance": 32}]


def reactive_communication(state, events, elapsed_minutes, existing=None):
    """Create at most one grounded incoming message from a real known contact."""
    if existing or int(elapsed_minutes or 0) < 1440:
        return []
    delivery = state.get("message_delivery_state") if isinstance(state.get("message_delivery_state"), dict) else {}
    turn = int(state.get("turn", 0) or 0)
    candidates = []
    companion_names = [_name(row) for row in state.get("companions", []) if _name(row)]
    for name in companion_names + list((state.get("contacts") or {}).keys()):
        if not name or name in candidates:
            continue
        from relationship_life import available
        if not available(state, name):
            continue
        contact = (state.get("contacts") or {}).get(name, {})
        if isinstance(contact, dict) and contact.get("can_contact", True) is False:
            continue
        delivery_row = delivery.get(name)
        if not isinstance(delivery_row, dict):
            delivery_row = {}
        if turn - int(delivery_row.get("last_incoming_turn", -99) or -99) >= 3:
            candidates.append(name)
    if not candidates:
        return []
    # Match a sender to something they could plausibly know or care about.
    # The old fallback always selected candidates[0], which let an unrelated
    # polity quote private character developments as if it had witnessed
    # them.  Direct involvement wins; only genuinely public major news may
    # reach an otherwise-unrelated contact.
    best = None
    for row in events:
        if not isinstance(row, dict) or not _name(row.get("title")) or _number(row.get("importance"), 0) < 40:
            continue
        title = ai_text(row.get("title"))
        detail = ai_text(row.get("narrative") or row.get("message"))
        blob = f"{title} {detail}".casefold()
        event_type = ai_text(row.get("type")).casefold()
        public_news = _number(row.get("importance"), 0) >= 75 and event_type in {"canon", "canon_event", "world", "headline", "news"}
        event_words = {word for word in re.findall(r"[a-z0-9'-]+", blob) if len(word) >= 4}
        for name in candidates:
            contact = (state.get("contacts") or {}).get(name, {})
            memory = (state.get("npc_memories") or {}).get(name, {})
            context = f"{contact} {memory}".casefold()
            direct = name.casefold() in blob
            overlap = len(event_words & {word for word in re.findall(r"[a-z0-9'-]+", context) if len(word) >= 4})
            # Shared vocabulary is not evidence that somebody knows a secret.
            score = (120 if direct else 0) + (min(30, overlap * 5) if direct or public_news else 0) + (20 if public_news else 0)
            if score and (best is None or score > best[0]):
                best = (score, name, row)
    if not best:
        return []
    _, sender, relevant_event = best
    subject = ai_text(relevant_event.get("title") or "recent developments")
    medium = WORLD_MESSAGE_MEDIUM.get(state.get("world"), WORLD_MESSAGE_MEDIUM["Custom World"])
    detail = ai_text(relevant_event.get("narrative") or relevant_event.get("message"))
    contact = (state.get("contacts") or {}).get(sender, {})
    relationship = _number(contact.get("relationship") if isinstance(contact, dict) else 0, 0)
    event_blob = f"{subject} {detail}".lower()
    # A thread already shows its sender and delivery date; the message body
    # should be what they actually said, not another narrated envelope around
    # a fake quotation.  Prefer the factual event detail over a stylized card
    # title and remove third-person possessives from self-authored updates.
    clean_subject = re.sub(rf"^{re.escape(sender)}(?:['’]s)?\s+", "", subject, flags=re.I).strip(" —:-") or subject
    detail = re.sub(r"\s+", " ", detail).strip()
    if len(detail) > 260:
        detail = detail[:257].rsplit(" ", 1)[0] + "…"
    kind = str(contact.get("kind") or "person").lower() if isinstance(contact, dict) else "person"
    group_sender = kind in {"group", "faction", "organization", "village", "guild", "nation"}
    if re.search(r"\b(attack|danger|killed|death|injur|ambush|war|threat)\w*\b", event_blob, re.I):
        message = f"{detail or f'I received word about {clean_subject}.'} Are you safe, and do you need help?"
        purpose = "warning_and_welfare"
    elif re.search(r"\b(level|title|promotion|victory|awaken|master|achievement|clear)\w*\b", event_blob, re.I):
        tone = "I knew you could do it" if relationship >= 25 else "That is going to change how people see you"
        message = f"{tone}. {detail or f'The news about {clean_subject} reached me.'}"
        purpose = "recognition"
    elif group_sender:
        message = f"Report — {clean_subject}: {detail or 'A relevant development has been confirmed.'}"
        purpose = "report"
    else:
        message = f"{detail or f'I have an update on {clean_subject}.'} Let me know if this changes what you want me to do next."
        purpose = "follow_up"
    memories = state.setdefault("npc_memories", {})
    memory = memories.setdefault(sender, {}) if isinstance(memories, dict) else {}
    if isinstance(memory, dict):
        known = memory.setdefault("confirmed_knowledge", [])
        if not isinstance(known, list):
            known = memory["confirmed_knowledge"] = []
        fact = f"Learned through {medium}: {subject} — {detail[:220]}".strip(" —")
        if fact not in known:
            known.append(fact); memory["confirmed_knowledge"] = known[-30:]
    return [{"thread": sender, "sender": sender,
             "message": message.strip(),
             "metadata": {"generated_locally": True, "source_event": subject, "medium": medium, "purpose": purpose}}]


def apply_prompt_budget(snapshot, state, query="", purpose="moment", mode="balanced"):
    """Trim low-relevance payload tails and expose an auditable local budget."""
    out = copy.deepcopy(snapshot)
    limits = {
        "economy": {"chars": 32000, "skills": 18, "items": 20, "codex": 12, "threads": 5},
        "balanced": {"chars": 56000, "skills": 28, "items": 32, "codex": 20, "threads": 8},
        "deep": {"chars": 90000, "skills": 45, "items": 50, "codex": 35, "threads": 12},
    }.get(str(mode), {}) or {"chars": 56000, "skills": 28, "items": 32, "codex": 20, "threads": 8}
    terms = {word for word in re.findall(r"[a-z0-9'-]+", ai_text(query).lower()) if len(word) > 2}
    trimmed = {}

    def relevant_map(value, cap):
        if not isinstance(value, dict) or len(value) <= cap:
            return value
        ranked = []
        for index, (key, detail) in enumerate(value.items()):
            blob = f"{key} {detail}".lower()
            score = sum(term in blob for term in terms) * 100 - index / 1000
            ranked.append((score, index, key, detail))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        keep = sorted(ranked[:cap], key=lambda row: row[1])
        return {key: detail for _, _, key, detail in keep}

    if isinstance(out.get("skills"), dict):
        old = len(out["skills"]); out["skills"] = relevant_map(out["skills"], limits["skills"]); trimmed["skills"] = old - len(out["skills"])
    for key, cap in (("inventory", limits["items"]), ("codex", limits["codex"])):
        if isinstance(out.get(key), list) and len(out[key]) > cap:
            old = len(out[key]); out[key] = out[key][-cap:]; trimmed[key] = old - len(out[key])
    if isinstance(out.get("chat_threads"), dict) and len(out["chat_threads"]) > limits["threads"]:
        old = len(out["chat_threads"]); out["chat_threads"] = dict(list(out["chat_threads"].items())[-limits["threads"]:]); trimmed["chat_threads"] = old - len(out["chat_threads"])

    # Enforce the advertised budget instead of merely reporting it. Long
    # campaigns can accumulate a few extremely large NPC dossiers, chat
    # histories, chapter archives, and ledgers even after the obvious skill
    # and inventory caps above. The save remains untouched; only this request
    # snapshot is reduced. Current scene/mechanics and query-matched records
    # are protected, while old tails are represented by their newest entries.
    list_caps = {
        "campaign_canon": 15, "chapter_summaries": 8, "world_feed": 16,
        "background_world_feed": 12, "progression_log": 16, "story_log": 12,
        "events": 16, "scheduled_events": 16, "information_packets": 12,
        "standing_orders": 12, "standing_intents": 16, "action_goals": 12,
        "consequences": 12, "history": 10, "messages": 12,
        "confirmed_knowledge": 12, "heard_knowledge": 10, "suspected_knowledge": 10,
        "false_beliefs": 8, "recent_outcomes": 8,
    }
    map_caps = {
        "npc_memories": 18 if mode == "deep" else 12,
        "contacts": 18, "relationships": 18, "npc_relationships": 18,
        "factions": 16, "faction_clocks": 14, "npc_clocks": 14,
        "story_threads": 14, "quests": 14, "chat_threads": limits["threads"],
        "codex": limits["codex"], "shops": 10, "location_details": 14,
    }

    def encoded_size(value):
        try:
            return len(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")))
        except Exception:
            return len(repr(value))

    def compact_nested(value, parent="", depth=0, aggressive=False):
        if isinstance(value, str):
            cap = (650 if aggressive else 1200) if depth > 1 else (1200 if aggressive else 2400)
            return value if len(value) <= cap else value[:cap].rstrip() + "…"
        if isinstance(value, list):
            cap = list_caps.get(parent, 10 if aggressive else 20)
            source = value[-cap:] if len(value) > cap else value
            if len(source) < len(value):
                trimmed[parent or "nested_lists"] = trimmed.get(parent or "nested_lists", 0) + len(value) - len(source)
            return [compact_nested(item, parent, depth + 1, aggressive) for item in source]
        if isinstance(value, dict):
            items = list(value.items())
            cap = map_caps.get(parent, 20 if aggressive else 36)
            if len(items) > cap:
                ranked = []
                for index, (key, detail) in enumerate(items):
                    blob = f"{key} {detail}".lower()
                    score = sum(term in blob for term in terms) * 100 - index / 1000
                    ranked.append((score, index, key, detail))
                ranked.sort(key=lambda row: (-row[0], row[1]))
                items = [(key, detail) for _, _, key, detail in sorted(ranked[:cap], key=lambda row: row[1])]
                trimmed[parent or "nested_maps"] = trimmed.get(parent or "nested_maps", 0) + len(value) - len(items)
            return {str(key): compact_nested(detail, str(key), depth + 1, aggressive) for key, detail in items}
        return value

    for key in list(out):
        if key in list_caps or key in map_caps:
            out[key] = compact_nested(out[key], key, 0, False)

    estimated = encoded_size(out)
    if estimated > limits["chars"]:
        protected = {
            "name", "world", "difficulty", "location", "world_time", "canon_day", "canon_anchor",
            "stats", "hidden_stats", "hp", "hp_max", "resource", "resource_max", "resource_name",
            "skills", "special", "class_profile", "equipment", "combat", "danger_scenario",
            "live_scene", "scene_state", "grounding_packet", "mechanical_power_profile",
            "capability_summary", "active_scenario", "simulation_context", "prompt_budget",
        }
        candidates = sorted(
            (encoded_size(value), key) for key, value in out.items()
            if key not in protected and isinstance(value, (dict, list, str))
        )
        for _, key in reversed(candidates):
            out[key] = compact_nested(out[key], key, 0, True)
            estimated = encoded_size(out)
            if estimated <= limits["chars"]:
                break
        # A pathological single field must not defeat the limit. Drop only
        # the largest non-protected request-only sections, leaving an audit
        # marker so the model knows older unrelated material was omitted.
        omitted = []
        if estimated > limits["chars"]:
            candidates = sorted(
                (encoded_size(value), key) for key, value in out.items()
                if key not in protected and key != "prompt_budget"
            )
            for _, key in reversed(candidates):
                if estimated <= limits["chars"]:
                    break
                omitted.append(key)
                out.pop(key, None)
                estimated = encoded_size(out)
            if omitted:
                trimmed["omitted_sections"] = omitted

    visible_trimmed = {k: v for k, v in trimmed.items()
                       if (isinstance(v, (int, float)) and v > 0) or (isinstance(v, (list, dict)) and v)}
    manifest = {"purpose": str(purpose), "mode": str(mode), "character_budget": limits["chars"],
                "estimated_characters": estimated, "trimmed": visible_trimmed,
                "rule": "Current mechanics, the live scene, named subjects, corrections, and recent consequences outrank old unrelated detail."}
    out["prompt_budget"] = manifest
    logs = state.setdefault("prompt_budget_log", [])
    logs.append({"turn": state.get("turn", 0), **copy.deepcopy(manifest)})
    state["prompt_budget_log"] = logs[-80:]
    return out
