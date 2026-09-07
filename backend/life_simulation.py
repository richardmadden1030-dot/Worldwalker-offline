"""Deterministic character-life, relationship, and legacy simulation.

This module deliberately does not invent marriages, children, deaths, or betrayals.
It turns facts already established by play into durable records and locally
resolvable choices.  Both AI narration and a future/standalone offline resolver
can consume the same compact ``life_context`` and choice records.
"""
from __future__ import annotations

import hashlib
import re


WORLD_TERMS = {
    "Naruto": {"group": "shinobi team or organization", "mentor": "sensei", "legacy": "clan and shinobi legacy"},
    "One Piece": {"group": "crew", "mentor": "mentor", "legacy": "inherited will"},
    "Hunter x Hunter": {"group": "Hunter network", "mentor": "Nen mentor", "legacy": "Hunter legacy"},
    "Solo Max-Level Newbie": {"group": "party", "mentor": "sponsor", "legacy": "Tower legacy"},
    "Overgeared": {"group": "guild", "mentor": "master", "legacy": "legend"},
    "Reincarnated as a Slime": {"group": "nation", "mentor": "leader", "legacy": "nation legacy"},
    "Bleach": {"group": "division", "mentor": "senior officer", "legacy": "Soul Reaper legacy"},
    "Jujutsu Kaisen": {"group": "team or clan", "mentor": "teacher", "legacy": "sorcerer legacy"},
    "Custom World": {"group": "group", "mentor": "mentor", "legacy": "legacy"},
}

RELATIONSHIP_WORDS = {
    "family": r"\b(parent|mother|father|sibling|brother|sister|family|spouse|wife|husband|child|son|daughter)\b",
    "mentor": r"\b(mentor|sensei|teacher|master|student|pupil|apprentice|train(?:ing|ed)? under)\b",
    "romance": r"\b(love|romance|dating|partner|marry|married|engaged)\b",
    "rival": r"\b(rival|competition|compete|surpass)\b",
    "enemy": r"\b(enemy|betray|betrayed|hatred|vendetta)\b",
}


def _text(value, limit=500):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _id(*parts):
    return hashlib.sha256("|".join(_text(part).casefold() for part in parts).encode("utf-8")).hexdigest()[:16]


def _name(row):
    if isinstance(row, dict):
        return _text(row.get("name") or row.get("character") or row.get("npc"), 120)
    return _text(row, 120)


def _phase(score, kind=""):
    if kind == "enemy" or score <= -60:
        return "Hostile"
    if score <= -20:
        return "Strained"
    if score < 20:
        return "Acquainted"
    if score < 50:
        return "Trusted"
    if score < 80:
        return "Close"
    return "Unbreakable"


def normalize(state):
    life = state.get("life_simulation")
    if not isinstance(life, dict):
        life = {}
    defaults = {
        "version": 1, "last_processed_day": int(state.get("canon_day", 0) or 0),
        "people": {}, "relationships": {}, "households": [], "mentorships": [],
        "event_history": [], "pending_choices": [], "legacy_records": [],
        "succession": {}, "processed_evidence": [],
    }
    for key, value in defaults.items():
        if key not in life or not isinstance(life[key], type(value)):
            life[key] = value.copy() if isinstance(value, (dict, list)) else value
    state["life_simulation"] = life
    refresh_context(state)
    return life


def _relationship_rows(state):
    rows = []
    contacts = state.get("contacts") if isinstance(state.get("contacts"), dict) else {}
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    for name in set(contacts) | set(memories):
        contact, memory = contacts.get(name, {}), memories.get(name, {})
        contact = contact if isinstance(contact, dict) else {}
        memory = memory if isinstance(memory, dict) else {}
        score = contact.get("relationship", memory.get("relationship", memory.get("affinity", 0)))
        try: score = float(score or 0)
        except (TypeError, ValueError): score = 0
        blob = _text({**memory, **contact}, 2000)
        kind = next((kind for kind, pattern in RELATIONSHIP_WORDS.items() if re.search(pattern, blob, re.I)), "associate")
        rows.append((str(name), score, kind, memory, contact))
    return rows


def _ensure_choice(life, kind, person, title, prompt, options):
    choice_id = _id(kind, person, title)
    if any(row.get("id") == choice_id for row in life["pending_choices"]):
        return
    if any(row.get("choice_id") == choice_id for row in life["event_history"]):
        return
    life["pending_choices"].append({
        "id": choice_id, "kind": kind, "person": person, "title": title,
        "prompt": prompt, "options": options, "requires_player_choice": True,
    })


def record_established_event(state, kind, person, detail, evidence="narrative"):
    """Record a life event after another system or the story establishes it."""
    life = normalize(state)
    detail = _text(detail, 700)
    key = _id(kind, person, detail)
    if key in life["processed_evidence"]:
        return None
    row = {"id": key, "kind": kind, "person": _text(person, 120), "detail": detail,
           "canon_day": state.get("canon_day"), "turn": state.get("turn"), "evidence": _text(evidence, 300)}
    life["event_history"].append(row)
    life["event_history"] = life["event_history"][-160:]
    life["processed_evidence"].append(key)
    life["processed_evidence"] = life["processed_evidence"][-300:]
    refresh_context(state)
    return row


def advance(state, actions=None, source_events=None, elapsed_minutes=0):
    """Advance life records from grounded state/evidence and return visible beats."""
    life = normalize(state)
    actions = [_text(item) for item in (actions or []) if _text(item)]
    events = [row for row in (source_events or []) if isinstance(row, dict)]
    now = int(state.get("canon_day", 0) or 0)
    prior = int(life.get("last_processed_day", now) or now)
    elapsed_days = max(0, now - prior, int(float(elapsed_minutes or 0) / 1440))
    life["last_processed_day"] = now
    visible = []

    companions = {_name(row): row for row in state.get("companions", []) if _name(row)}
    for name, row in companions.items():
        profile = life["people"].setdefault(name, {"name": name, "goals": [], "milestones": [], "status": "active"})
        if not isinstance(profile, dict):
            profile = life["people"][name] = {"name": name, "goals": [], "milestones": [], "status": "active"}
        goal = _text((row if isinstance(row, dict) else {}).get("goal") or (row if isinstance(row, dict) else {}).get("role"))
        memory = (state.get("npc_memories") or {}).get(name, {})
        if isinstance(memory, dict):
            goal = _text(memory.get("immediate_goal") or memory.get("goal") or goal)
            profile["status"] = _text(memory.get("status") or profile.get("status") or "active", 40)
        if goal and goal.casefold() not in {_text(item).casefold() for item in profile.get("goals", [])}:
            profile.setdefault("goals", []).append(goal)
            profile["goals"] = profile["goals"][-6:]
        profile.update({"role": _text((row if isinstance(row, dict) else {}).get("role"), 120),
                        "active_goal": goal, "last_seen_day": now})

    # Persist readable relationship phases from existing scores and facts.
    for name, score, kind, memory, contact in _relationship_rows(state):
        key = _id("player", name)
        life["relationships"][key] = {
            "a": _text(state.get("name") or "Player", 120), "b": name, "type": kind,
            "score": score, "phase": _phase(score, kind),
            "why": _text(contact.get("why") or memory.get("relationship_reason") or memory.get("notes"), 400),
            "updated_day": now,
        }

    evidence_blob = " ".join(actions + [_text(row.get("title")) + " " + _text(row.get("narrative")) for row in events])
    # Explicit long-running training/care commands become durable family or mentorship records.
    for action in actions:
        match = re.search(
            r"\b(?:train|teach|mentor|raise|care for|look after)\s+"
            r"([A-Z][A-Za-z' -]{1,50}?)(?=\s+(?:in|to|as|with|at|every|until|for)\b|[.,;:]|$)",
            action, re.I,
        )
        if not match:
            continue
        person = match.group(1).strip().rstrip(".,;:")
        relation = "care" if re.search(r"\b(raise|care for|look after)\b", action, re.I) else "mentorship"
        record = {"mentor": _text(state.get("name") or "Player", 120), "student": person,
                  "kind": relation, "directive": action, "started_day": now, "active": True}
        target = life["mentorships"]
        if not any(_text(row.get("student")).casefold() == person.casefold() and row.get("active") for row in target if isinstance(row, dict)):
            target.append(record)

    # Recognize major life changes only when an authored event says they happened.
    patterns = {
        "promotion": r"\b(promoted|promotion|appointed|became (?:captain|leader|commander|head|chief))\b",
        "injury": r"\b(permanent injury|lost (?:an arm|a leg|an eye)|crippled|career-ending injury)\b",
        "retirement": r"\b(retired|retirement|stepped down)\b",
        "betrayal": r"\b(betrayed|betrayal|turned against)\b",
        "reconciliation": r"\b(reconciled|made peace|forgave|repaired their relationship)\b",
        "marriage": r"\b(married|wedding|became spouses)\b",
        "child": r"\b(had a child|gave birth|their (?:son|daughter) was born)\b",
        "death": r"\b(died|was killed|is dead|death of)\b",
    }
    for event in events:
        detail = _text(event.get("narrative") or event.get("message"), 700)
        title = _text(event.get("title"), 180)
        text = f"{title} {detail}"
        kind = next((label for label, pattern in patterns.items() if re.search(pattern, text, re.I)), "")
        if kind:
            person = next((name for name in life["people"] if name.casefold() in text.casefold()), _text(event.get("person") or event.get("npc"), 120))
            recorded = record_established_event(state, kind, person, detail or title, "authored event")
            if recorded:
                visible.append({"type": "life", "title": f"{person + ' — ' if person else ''}{kind.title()}",
                                "narrative": detail or title, "importance": 65})

        # A completed, campaign-shaping deed becomes legacy. Importance is
        # supplied by the existing world/arc directors, so routine updates do
        # not get inflated into historical achievements.
        importance = event.get("importance", 0)
        try: importance = float(importance or 0)
        except (TypeError, ValueError): importance = 0
        if importance >= 80 and re.search(r"\b(resolved|defeated|founded|liberated|saved|unified|overthrew|became|mastered|awakened)\b", text, re.I):
            record_legacy(state, title or "A defining deed", detail or title, _text(event.get("type") or "deed", 60))

    # Import already-tracked NPC-to-NPC bonds into the same readable phase
    # model without changing their authoritative source records.
    for raw in (state.get("npc_relationships") or {}).values():
        if not isinstance(raw, dict) or not raw.get("a") or not raw.get("b"):
            continue
        try: score = float(raw.get("strength", 0) or 0)
        except (TypeError, ValueError): score = 0
        key = _id(raw.get("a"), raw.get("b"))
        kind = _text(raw.get("type") or "associate", 60).casefold()
        life["relationships"][key] = {
            "a": _text(raw.get("a"), 120), "b": _text(raw.get("b"), 120), "type": kind,
            "score": score, "phase": _phase(score, kind), "why": _text(raw.get("note"), 400),
            "status": _text(raw.get("status") or "active", 40), "updated_day": now,
        }

    # Months of grounded mentorship produce development, not an invented promotion.
    if elapsed_days:
        for row in life["mentorships"]:
            if not isinstance(row, dict) or not row.get("active"):
                continue
            row["days_active"] = int(row.get("days_active", 0) or 0) + elapsed_days
            crossed = int(row["days_active"] // 90)
            if crossed > int(row.get("milestone", 0) or 0):
                row["milestone"] = crossed
                student = _text(row.get("student"), 120)
                detail = f"{student}'s continuing {row.get('kind', 'training')} has reached a meaningful new stage under the standing instruction: {row.get('directive', '')}"
                recorded = record_established_event(state, "development", student, detail, "standing instruction and elapsed time")
                if recorded:
                    visible.append({"type": "life", "title": f"{student}'s Development", "narrative": detail + ".", "importance": 52})

    # Natural-language intent may open a choice, but never silently forces the event.
    if re.search(r"\b(propose|marry|start a family|have (?:a |another )?child|adopt)\b", evidence_blob, re.I):
        candidate = next((name for name, score, kind, _, _ in _relationship_rows(state) if score >= 50 or kind in {"romance", "family"}), "")
        if candidate:
            _ensure_choice(life, "family", candidate, f"A future with {candidate}",
                           f"Your actions have made a lasting personal choice with {candidate} possible. Nothing changes until you decide.",
                           [{"id": "commit", "label": "Pursue it", "result": "Commit to this relationship direction."},
                            {"id": "wait", "label": "Not yet", "result": "Leave the possibility open without changing the relationship."},
                            {"id": "decline", "label": "Decline", "result": "Close this possibility respectfully."}])

    life["pending_choices"] = life["pending_choices"][-30:]
    life["mentorships"] = life["mentorships"][-80:]
    refresh_context(state)
    return {"events": visible, "pending_choices": life["pending_choices"]}


def resolve_choice(state, choice_id, option_id):
    """Resolve a life choice locally; returns a Chronicle-ready event."""
    life = normalize(state)
    choice = next((row for row in life["pending_choices"] if row.get("id") == choice_id), None)
    if not choice:
        raise ValueError("That life choice is no longer available.")
    option = next((row for row in choice.get("options", []) if row.get("id") == option_id), None)
    if not option:
        raise ValueError("That option is not available.")
    life["pending_choices"] = [row for row in life["pending_choices"] if row.get("id") != choice_id]
    detail = _text(option.get("result") or option.get("label"), 600)
    history = {"id": _id(choice_id, option_id), "choice_id": choice_id, "kind": choice.get("kind"),
               "person": choice.get("person"), "decision": option.get("label"), "detail": detail,
               "canon_day": state.get("canon_day"), "turn": state.get("turn"), "evidence": "player choice"}
    life["event_history"].append(history)
    life["event_history"] = life["event_history"][-160:]
    refresh_context(state)
    return {"type": "life", "title": choice.get("title") or "Life Choice", "narrative": detail,
            "importance": 68, "choice_id": choice_id}


def record_legacy(state, title, detail, kind="deed", inheritors=None):
    life = normalize(state)
    key = _id(kind, title, detail)
    if any(row.get("id") == key for row in life["legacy_records"]):
        return None
    terms = WORLD_TERMS.get(state.get("world"), WORLD_TERMS["Custom World"])
    row = {"id": key, "kind": kind, "title": _text(title, 180), "detail": _text(detail, 700),
           "world_term": terms["legacy"], "inheritors": [_text(x, 120) for x in (inheritors or []) if _text(x)],
           "canon_day": state.get("canon_day"), "turn": state.get("turn")}
    life["legacy_records"].append(row)
    life["legacy_records"] = life["legacy_records"][-100:]
    refresh_context(state)
    return row


def refresh_context(state):
    life = state.get("life_simulation") if isinstance(state.get("life_simulation"), dict) else {}
    terms = WORLD_TERMS.get(state.get("world"), WORLD_TERMS["Custom World"])
    people = []
    for row in (life.get("people") or {}).values():
        if isinstance(row, dict):
            people.append({key: row.get(key) for key in ("name", "role", "active_goal", "status") if row.get(key)})
    state["life_context"] = {
        "world_terms": terms, "people": people[:24],
        "relationship_phases": list((life.get("relationships") or {}).values())[:30],
        "active_mentorships": [row for row in (life.get("mentorships") or []) if isinstance(row, dict) and row.get("active")][:20],
        "pending_choices": (life.get("pending_choices") or [])[:10],
        "recent_life_events": (life.get("event_history") or [])[-16:],
        "legacy": (life.get("legacy_records") or [])[-12:],
    }
    return state["life_context"]
