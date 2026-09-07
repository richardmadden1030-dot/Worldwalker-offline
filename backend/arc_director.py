"""Deterministic campaign-arc pacing built from facts the campaign already owns.

Arcs do not invent scenes or force objectives.  They remember which established
threads the player repeatedly engages, recognize genuine turning points, expose
several valid approaches, and give resolved threads a quiet aftermath.
"""
from __future__ import annotations

import copy
import hashlib
import re


TERMINAL = {"complete", "completed", "resolved", "failed", "abandoned", "archived", "cancelled"}
PHASES = ((0, "emerging"), (24, "developing"), (48, "escalating"), (72, "turning_point"), (90, "resolution_ready"))
STOP = {"the", "and", "with", "from", "into", "your", "their", "that", "this", "have", "will", "about", "through", "toward", "current"}


def _text(value, limit=600):
    if isinstance(value, dict):
        value = value.get("name") or value.get("title") or value.get("text") or value.get("action") or ""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _tokenize(value):
    return {x for x in re.findall(r"[a-z0-9']+", _text(value).casefold()) if len(x) > 2 and x not in STOP}


def _id(kind, title):
    return hashlib.sha256(f"{kind}|{_text(title).casefold()}".encode()).hexdigest()[:16]


def _store(state):
    rows = state.setdefault("campaign_arcs", [])
    if not isinstance(rows, list):
        rows = state["campaign_arcs"] = []
    archive = state.setdefault("campaign_arc_archive", [])
    if not isinstance(archive, list):
        state["campaign_arc_archive"] = []
    director = state.setdefault("campaign_arc_director", {})
    if not isinstance(director, dict):
        director = state["campaign_arc_director"] = {}
    director.setdefault("quiet_until_turn", 0)
    director.setdefault("last_beat_turn", -1)
    director.setdefault("last_resolution_turn", -1)
    director.setdefault("history", [])
    return rows, director


def _phase(progress):
    result = "emerging"
    for threshold, name in PHASES:
        if progress >= threshold:
            result = name
    return result


def _branches(kind):
    if kind == "development":
        return ["continue disciplined practice", "seek specialized instruction", "test it under real pressure", "pause and consolidate"]
    if kind == "relationship":
        return ["speak honestly", "support them through action", "set a boundary", "allow the relationship to cool"]
    if kind == "rivalry":
        return ["confront the rival", "outmaneuver their plan", "seek reconciliation", "walk away if circumstances permit"]
    if kind == "governance":
        return ["negotiate a settlement", "reform the underlying conditions", "enforce legitimate authority", "relinquish or transfer control"]
    return ["pursue it directly", "investigate before committing", "seek allies or negotiate", "withdraw or let the opportunity pass"]


def _new_arc(state, title, kind, source, participants=None, progress=8):
    turn = int(state.get("turn", 0) or 0)
    return {"id": _id(kind, title), "title": _text(title, 180), "kind": kind,
            "status": "active", "phase": _phase(progress), "progress": progress,
            "created_turn": turn, "last_touched_turn": turn, "touches": 0,
            "source": _text(source, 300), "participants": [x for x in (participants or []) if _text(x)][:8],
            "available_approaches": _branches(kind), "history": [], "resolution": {},
            "last_transition_turn": turn}


def _candidates(state):
    found = []
    for quest in state.get("quests", []) if isinstance(state.get("quests"), list) else []:
        if not isinstance(quest, dict) or _text(quest.get("status") or "active").casefold() in TERMINAL:
            continue
        title = _text(quest.get("name") or quest.get("title"))
        if title:
            found.append((title, "quest", f"Active campaign thread: {title}", [], max(8, min(70, int(quest.get("progress_percent", 0) or 0)))))
    for order in state.get("standing_orders", []) if isinstance(state.get("standing_orders"), list) else []:
        title = _text(order)
        if len(title.split()) >= 3:
            kind = "governance" if re.search(r"\b(?:rule|govern|country|village|territory|organization|command|protect|care for)\b", title, re.I) else "goal"
            found.append((title, kind, "A continuing player instruction", [], 12))
    living = state.get("living_world") if isinstance(state.get("living_world"), dict) else {}
    for pattern, count in (living.get("patterns") or {}).items():
        if int(count or 0) >= 3 and pattern in {"training", "investigation", "governance", "crafting", "social"}:
            kind = "development" if pattern in {"training", "crafting"} else "relationship" if pattern == "social" else pattern
            found.append((f"Ongoing {_text(pattern).replace('_', ' ').title()}", kind, f"Repeated behavior recorded {count} times", [], 18))
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    for name, memory in memories.items():
        if not isinstance(memory, dict) or not memory.get("nemesis"):
            continue
        found.append((f"Rivalry with {_text(name)}", "rivalry", "A named nemesis remains active", [_text(name)], 20))
    return found


def discover(state):
    arcs, director = _store(state)
    known = {row.get("id") for row in [*arcs, *state.get("campaign_arc_archive", [])] if isinstance(row, dict)}
    for title, kind, source, participants, progress in _candidates(state):
        token = _id(kind, title)
        if token in known:
            continue
        arcs.append(_new_arc(state, title, kind, source, participants, progress))
        known.add(token)
    active = [x for x in arcs if isinstance(x, dict) and x.get("status", "active") == "active"]
    terminal = [x for x in arcs if isinstance(x, dict) and x.get("status") != "active"]
    state["campaign_arcs"] = terminal[-20:] + active[-8:]
    return state["campaign_arcs"]


def _relevant(arc, text):
    subject = _tokenize(arc.get("title")) | _tokenize(arc.get("source"))
    for name in arc.get("participants", []):
        subject |= _tokenize(name)
    words = _tokenize(text)
    return bool(subject & words) or (arc.get("kind") == "development" and bool(words & {"train", "practice", "study", "learn", "master"}))


def _resolution_method(text, kind):
    if re.search(r"\b(?:abandon|leave behind|walk away|withdraw|give up|relinquish)\b", text, re.I): return "withdrawal"
    if re.search(r"\b(?:negotiate|peace|reconcile|ally|alliance|agreement|persuade)\b", text, re.I): return "agreement"
    if re.search(r"\b(?:expose|reveal|prove|investigate|publish)\b", text, re.I): return "revelation"
    if re.search(r"\b(?:defeat|kill|destroy|overthrow|conquer|win)\b", text, re.I): return "decisive victory"
    if kind == "development" and re.search(r"\b(?:master|awaken|complete|breakthrough|achieve)\b", text, re.I): return "mastery"
    if re.search(r"\b(?:complete|resolve|finish|succeed|establish)\b", text, re.I): return "completion"
    return ""


def _epilogue(arc, method, evidence):
    title = arc.get("title", "This arc")
    return (f"{title} closes through {method}. The campaign should preserve who witnessed it, what materially changed, "
            f"and any relationship, faction, territorial, or personal effects already established by the resolution. "
            f"It does not create an unrelated punishment merely to keep the story moving. Evidence: {_text(evidence, 260)}")


def advance(state, actions=None, updates=None, elapsed_minutes=0):
    arcs, director = _store(state)
    discover(state)
    arcs = state["campaign_arcs"]
    turn = int(state.get("turn", 0) or 0)
    actions = [_text(x) for x in (actions or []) if _text(x)]
    updates = [x for x in (updates or []) if isinstance(x, dict)]
    update_text = " ".join(_text(x.get("narrative") or x.get("title")) for x in updates)
    combined = " ".join(actions + [update_text]).strip()
    beats, resolved = [], []
    quiet = turn <= int(director.get("quiet_until_turn", 0) or 0)
    terminal_quests = {_text(q.get("name") or q.get("title")).casefold(): _text(q.get("status")).casefold()
                       for q in [*(state.get("quests") or []), *(state.get("quest_archive") or [])]
                       if isinstance(q, dict) and _text(q.get("status")).casefold() in TERMINAL}
    for arc in arcs:
        if not isinstance(arc, dict) or arc.get("status", "active") != "active":
            continue
        quest_terminal = arc.get("kind") == "quest" and _text(arc.get("title")).casefold() in terminal_quests
        if not quest_terminal and (not combined or not _relevant(arc, combined)):
            continue
        old_phase = arc.get("phase", "emerging")
        action_hits = sum(1 for action in actions if _relevant(arc, action))
        update_hits = sum(1 for row in updates if _relevant(arc, _text(row.get("narrative") or row.get("title"))))
        gain = min(18, action_hits * 9 + update_hits * 5)
        if quiet:
            gain = min(gain, 5)
        arc["progress"] = min(100, int(arc.get("progress", 0) or 0) + gain)
        arc["touches"] = int(arc.get("touches", 0) or 0) + 1
        arc["last_touched_turn"] = turn
        arc["phase"] = _phase(arc["progress"])
        arc.setdefault("history", []).append({"turn": turn, "actions": actions[:3], "progress": arc["progress"], "phase": arc["phase"]})
        arc["history"] = arc["history"][-30:]
        method = _resolution_method(combined, arc.get("kind"))
        if quest_terminal and not method:
            method = "withdrawal" if terminal_quests[_text(arc.get("title")).casefold()] in {"failed", "abandoned", "cancelled"} else "completion"
        explicitly_terminal = quest_terminal or bool(method and (arc["progress"] >= 72 or re.search(r"\b(?:complete|completed|resolved|finished|defeated|overthrown|mastered|abandoned)\b", update_text, re.I)))
        if explicitly_terminal:
            arc["status"] = "resolved" if method != "withdrawal" else "abandoned"
            arc["phase"] = "aftermath"
            arc["resolved_turn"] = turn
            arc["resolution"] = {"method": method, "evidence": _text(update_text or combined, 500), "epilogue": _epilogue(arc, method, update_text or combined)}
            resolved.append(arc)
            beats.append({"type": "arc_resolution", "title": f"Arc Resolved — {arc['title']}", "narrative": arc["resolution"]["epilogue"],
                          "importance": 78, "sequence": 7750 + len(beats), "arc_id": arc["id"], "next_pressure": "A quiet aftermath is available before another major thread demands attention."})
            continue
        if arc["phase"] != old_phase and not quiet and turn != int(director.get("last_beat_turn", -1)):
            beats.append({"type": "arc_transition", "title": f"Arc Develops — {arc['title']}",
                          "narrative": f"Because recent actions directly affected {arc['title']}, it has moved from {old_phase.replace('_', ' ')} to {arc['phase'].replace('_', ' ')}. This is a change in the established thread, not a compulsory objective.",
                          "importance": 66, "sequence": 7720 + len(beats), "arc_id": arc["id"],
                          "next_pressure": "Available approaches: " + "; ".join(arc.get("available_approaches", [])[:4])})
            director["last_beat_turn"] = turn
    if resolved:
        archive = state.setdefault("campaign_arc_archive", [])
        archive.extend(copy.deepcopy(resolved))
        state["campaign_arc_archive"] = archive[-80:]
        resolved_ids = {x["id"] for x in resolved}
        state["campaign_arcs"] = [x for x in arcs if x.get("id") not in resolved_ids]
        director["quiet_until_turn"] = turn + 2
        director["last_resolution_turn"] = turn
    director["history"].extend({"turn": turn, "type": x["type"], "arc_id": x["arc_id"]} for x in beats)
    director["history"] = director["history"][-120:]
    context = snapshot(state)
    state["campaign_arc_context"] = context
    return {"beats": beats[:2], "quiet_period": context["quiet_period"], "active_arcs": context["active_arcs"]}


def snapshot(state):
    arcs, director = _store(state)
    turn = int(state.get("turn", 0) or 0)
    active = [{"id": x.get("id"), "title": x.get("title"), "kind": x.get("kind"), "phase": x.get("phase"),
               "progress": x.get("progress"), "participants": copy.deepcopy(x.get("participants", [])),
               "available_approaches": copy.deepcopy(x.get("available_approaches", []))}
              for x in arcs if isinstance(x, dict) and x.get("status", "active") == "active"]
    return {"active_arcs": active[:8], "quiet_period": turn <= int(director.get("quiet_until_turn", 0) or 0),
            "quiet_until_turn": int(director.get("quiet_until_turn", 0) or 0),
            "recent_resolutions": [{"title": x.get("title"), "resolution": copy.deepcopy(x.get("resolution", {}))}
                                   for x in state.get("campaign_arc_archive", [])[-3:] if isinstance(x, dict)]}
