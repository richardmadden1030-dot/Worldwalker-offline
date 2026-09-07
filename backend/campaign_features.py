"""Low-cost campaign features shared by the narrator and interface.

These systems deliberately store only durable fiction.  They do not create a
second tactical or management game and they do not require extra AI calls.
"""
import copy
import hashlib
import re


WORLD_DELIVERY = {
    "Naruto": ("Mission scroll", "Village intelligence", "Traveler report"),
    "Bleach": ("Hell Butterfly", "Division dispatch", "Spiritual report"),
    "One Piece": ("World Economy News", "Den Den Mushi", "Port rumor"),
    "Jujutsu Kaisen": ("Jujutsu Headquarters notice", "Mission file", "Sorcerer report"),
    "Hunter x Hunter": ("Hunter Association dispatch", "Contact report", "Local rumor"),
    "Overgeared": ("Satisfy system notice", "Guild message", "Player report"),
    "Solo Max-Level Newbie": ("Tower system notice", "Guild report", "Ranking alert"),
    "Reincarnated as a Slime": ("Thought Communication", "Nation report", "Analysis result"),
    "Custom World": ("Courier report", "Local report", "Rumor"),
}


def _text(value, limit=1000):
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or value.get("description") or ""
    return str(value).strip()[:limit]


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", _text(value).lower()).strip("-") or "entry"


def recent_chat_context(state, query="", max_threads=6, max_messages=4):
    """Return a compact, explicit chat digest for every GM task.

    Chat threads were present in raw state before, but buried deeply enough
    that small models often ignored them.  This digest makes the latest
    agreements and warnings visible without resending entire conversations.
    """
    threads = state.get("chat_threads") if isinstance(state.get("chat_threads"), dict) else {}
    query_words = set(re.findall(r"[a-z0-9']+", _text(query).lower()))
    ranked = []
    for name, raw in threads.items():
        messages = raw.get("messages", []) if isinstance(raw, dict) else raw
        if not isinstance(messages, list) or not messages:
            continue
        latest = messages[-max_messages:]
        blob = " ".join(_text(row.get("message") or row.get("text") if isinstance(row, dict) else row) for row in latest).lower()
        score = 20 + (80 if _text(name).lower() in _text(query).lower() else 0)
        score += min(30, len(query_words & set(re.findall(r"[a-z0-9']+", blob))) * 5)
        ranked.append((score, _text(name, 160), latest))
    ranked.sort(key=lambda row: (-row[0], row[1].lower()))
    result = []
    for _, name, messages in ranked[:max_threads]:
        rows = []
        for raw in messages:
            if isinstance(raw, dict):
                body = _text(raw.get("message") or raw.get("text"), 600)
                sender = _text(raw.get("sender") or raw.get("from") or raw.get("name"), 120)
                direction = _text(raw.get("direction") or raw.get("type"), 40)
            else:
                body, sender, direction = _text(raw, 600), "", ""
            if body:
                rows.append({"sender": sender, "direction": direction, "message": body})
        if rows:
            result.append({"thread": name, "latest": rows})
    return result


def normalize_companion_combinations(state, before=None):
    raw_entries = state.get("companion_combinations")
    if not isinstance(raw_entries, list):
        raw_entries = []
    previous = {}
    for row in (before or {}).get("companion_combinations", []) if isinstance(before, dict) else []:
        if isinstance(row, dict):
            previous[_text(row.get("id") or row.get("name")).lower()] = row
    companions = {_text(row.get("name") if isinstance(row, dict) else row).lower()
                  for row in state.get("companions", []) or []}
    companions.add(_text(state.get("name") or "Player").lower())
    cleaned, seen = [], set()
    for index, raw in enumerate(raw_entries[:100]):
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("name") or raw.get("title"), 160)
        participants = raw.get("participants") or []
        if isinstance(participants, str):
            participants = [part.strip() for part in re.split(r"[,;&]", participants) if part.strip()]
        participants = [_text(part, 120) for part in participants if _text(part)] if isinstance(participants, list) else []
        key = _text(raw.get("id") or name).lower()
        if not name or key in seen or len({p.lower() for p in participants}) < 2:
            continue
        # A narrator may only establish a real combination for people who
        # actually exist in the active party/player state.
        if not all(part.lower() in companions for part in participants):
            continue
        prior = previous.get(key, {})
        entry = {
            "id": _text(raw.get("id") or f"combo-{_slug(name)}", 100),
            "name": name,
            "participants": participants[:8],
            "description": _text(raw.get("description") or raw.get("effect"), 1200),
            "activation": _text(raw.get("activation") or raw.get("use"), 600),
            "limitation": _text(raw.get("limitation") or raw.get("cost"), 600),
            "mastery": max(0, min(100, int(raw.get("mastery", prior.get("mastery", 1)) or 1))),
            "status": _text(raw.get("status") or "unlocked", 40).lower(),
            "combat_usable": bool(raw.get("combat_usable", True)),
            "unlocked_turn": int(raw.get("unlocked_turn", prior.get("unlocked_turn", state.get("turn", 0))) or 0),
        }
        if entry["status"] not in {"unlocked", "developing", "mastered", "dormant"}:
            entry["status"] = "unlocked"
        cleaned.append(entry); seen.add(key)
    state["companion_combinations"] = cleaned
    # Combat already reads skills. Mirror only established, combat-usable
    # combinations into that registry so the player can actually select them.
    skills = state.setdefault("skills", {})
    for entry in cleaned:
        if entry["combat_usable"] and entry["status"] != "dormant":
            skills.setdefault(entry["name"], {
                "rank": "Combination", "description": entry["description"],
                "effect": entry["description"], "activation": entry["activation"],
                "limitation": entry["limitation"], "participants": entry["participants"],
                "category": "combination", "combat_usable": True,
                "effect_type": "support", "growth_path": "Practice together in real scenes to improve timing and mastery.",
            })
    return state


def normalize_trophy_state(state, before=None):
    accepted_ids = {_text(row.get("id") if isinstance(row, dict) else row).lower()
                    for row in state.get("legacy_trophies", []) or []}
    dismissed = {_text(value).lower() for value in state.get("dismissed_trophy_ids", []) or []}
    clean = []
    for raw in state.get("trophy_proposals", []) if isinstance(state.get("trophy_proposals"), list) else []:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title") or raw.get("name"), 160)
        proposal_id = _text(raw.get("id") or f"trophy-{_slug(title)}-{state.get('turn', 0)}", 120)
        if not title or proposal_id.lower() in accepted_ids | dismissed or any(row["id"].lower() == proposal_id.lower() for row in clean):
            continue
        clean.append({
            "id": proposal_id, "title": title,
            "description": _text(raw.get("description") or raw.get("summary"), 900),
            "category": _text(raw.get("category") or "Legacy", 80),
            "source_turn": int(raw.get("source_turn", state.get("turn", 0)) or 0),
        })
    state["trophy_proposals"] = clean[:20]
    state["legacy_trophies"] = [copy.deepcopy(row) for row in state.get("legacy_trophies", []) if isinstance(row, dict)][-100:]
    state["dismissed_trophy_ids"] = list(dict.fromkeys(_text(value, 120) for value in state.get("dismissed_trophy_ids", []) if _text(value)))[-200:]
    return state


def downtime_surprise_prompt(state, elapsed_minutes, actions=None):
    """Select a deterministic optional downtime beat without another call."""
    if int(elapsed_minutes or 0) < 1440:
        return None
    turn = int(state.get("turn", 0) or 0)
    tracker = state.get("downtime_surprise_state") if isinstance(state.get("downtime_surprise_state"), dict) else {}
    if turn - int(tracker.get("last_turn", -99) or -99) < 3:
        return None
    seed = f"{state.get('campaign_id')}|{turn}|{state.get('canon_day')}|{elapsed_minutes}"
    roll = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 100
    if elapsed_minutes < 43200 and roll >= 30:
        return None
    world = state.get("world", "Custom World")
    ideas = {
        "Naruto": ["a village festival or ceremony", "a mentor conversation", "a surprising mission visitor"],
        "Bleach": ["a division ceremony", "a Zanpakuto-spirit encounter", "a Hell Butterfly carrying unexpected news"],
        "One Piece": ["an island celebration", "a strange visitor at port", "a crew bonding incident"],
        "Jujutsu Kaisen": ["a quiet school incident", "an unexpected mentor lesson", "a mission notice with personal stakes"],
        "Hunter x Hunter": ["a Hunter contact's visit", "an unusual local competition", "a revealing training conversation"],
        "Overgeared": ["a Satisfy limited event", "a guild celebration", "an NPC affinity encounter"],
        "Solo Max-Level Newbie": ["a hidden System condition", "an administrator's unexpected visit", "a party relationship event"],
        "Reincarnated as a Slime": ["a nation celebration", "a diplomatic visitor", "an unexpected evolution or naming moment"],
    }.get(world, ["a local celebration", "an unexpected visitor", "a personal relationship moment"])
    return {"due": True, "suggestion": ideas[roll % len(ideas)], "delivery": delivery_channel(world, "personal")}


def delivery_channel(world, scope="world"):
    choices = WORLD_DELIVERY.get(world, WORLD_DELIVERY["Custom World"])
    return choices[0 if scope == "system" else 1 if scope == "faction" else 2]
