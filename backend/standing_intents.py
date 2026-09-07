"""Persistent player intentions that continue without repeated commands.

The exact action queue is still an itinerary.  This module tracks a different
thing: durable outcomes, delegated duties, policies and routines which remain
true in the background until completed, cancelled, superseded or made
impossible by the fiction.  Tracking and elapsed-time bookkeeping are local;
the normal GM call only has to narrate a milestone when one matters.
"""
from __future__ import annotations

import copy
import hashlib
import re


ACTIVE_STATUSES = {"active", "temporarily_blocked"}
FINAL_STATUSES = {"completed", "cancelled", "failed", "impossible"}

_PERSISTENT_LANGUAGE = re.compile(
    r"\b(ensure|keep|maintain|continue|ongoing|always|regularly|routinely|daily|weekly|"
    r"every\s+(?:day|week|month|morning|evening)|from now on|until|raise|look after|"
    r"see to it|remain responsible)\b", re.I,
)
_DELEGATED_LANGUAGE = re.compile(
    r"\b(?:have|order|instruct|assign|direct|command|tell|task)\b.{0,90}\b(?:train|teach|"
    r"care|protect|guard|patrol|watch|maintain|manage|oversee|research|support|provide|"
    r"raise|educate|heal|house|feed|recruit|investigate|fortify)\w*\b", re.I,
)
_CANCEL_LANGUAGE = re.compile(
    r"\b(?:stop|cancel|end|cease|revoke|withdraw|abandon|no longer|discontinue)\b", re.I,
)

_KIND_PATTERNS = (
    ("training", re.compile(r"\b(train|teach|practice|drill|study|tutor|mentor|condition)\w*\b", re.I)),
    ("care", re.compile(r"\b(care|look after|raise|feed|house|heal|medical|educat|child|children|ward)\w*\b", re.I)),
    ("security", re.compile(r"\b(protect|guard|patrol|watch|defend|escort|fortif|secure)\w*\b", re.I)),
    ("policy", re.compile(r"\b(policy|treat|permit|forbid|prioriti|govern|rule|tax|civilian|prisoner)\w*\b", re.I)),
    ("project", re.compile(r"\b(build|research|develop|establish|construct|restore|produce|recruit|investigate)\w*\b", re.I)),
)

_NOISE = {
    "the", "a", "an", "to", "of", "for", "that", "this", "them", "it", "my", "our",
    "i", "we", "be", "is", "are", "and", "or", "please", "order", "have", "ensure",
    "keep", "continue", "always", "regularly", "routinely", "until", "stop", "cancel",
}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip(" \t\r\n•.-"))


def _tokens(value):
    result = set()
    for token in re.findall(r"[a-z0-9'-]+", _clean(value).lower()):
        if len(token) <= 2 or token in _NOISE:
            continue
        stem = re.sub(r"(?:ing|ed|es|s)$", "", token) if len(token) > 5 else token
        result.add(stem)
    return result


def _kind(text):
    for name, pattern in _KIND_PATTERNS:
        if pattern.search(text):
            return name
    return "routine"


def _actor(text, kind):
    match = re.search(
        r"\b(?:have|order|instruct|assign|direct|command|tell|task)\s+(.{1,55}?)\s+"
        r"(?:to\s+|with\s+)?(?:keep\s+)?(?:train|teach|care|protect|guard|patrol|manage|"
        r"oversee|research|support|raise|educate)\w*\b",
        text, re.I,
    )
    if match:
        return _clean(match.group(1))[:80]
    if re.search(r"\b(?:i|myself|personally)\b", text, re.I):
        return "player"
    return "delegated" if kind in {"care", "policy", "security"} else "player"


def _until(text):
    match = re.search(r"\buntil\s+(.+)$", text, re.I)
    return _clean(match.group(1))[:180] if match else ""


def _signature(kind, actor, directive):
    important = " ".join(sorted(_tokens(directive)))
    return f"{kind}|{actor.lower()}|{important}"


def infer_standing_intent(action, turn=0):
    """Return a normalized persistent intent, or None for a one-off action."""
    directive = _clean(action)
    if not directive or _CANCEL_LANGUAGE.search(directive):
        return None
    if not (_PERSISTENT_LANGUAGE.search(directive) or _DELEGATED_LANGUAGE.search(directive)):
        return None
    kind = _kind(directive)
    actor = _actor(directive, kind)
    signature = _signature(kind, actor, directive)
    intent_id = "intent-" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
    cadence = 7 if kind in {"care", "training", "security", "project"} else 30
    return {
        "id": intent_id,
        "directive": directive,
        "kind": kind,
        "actor": actor,
        "status": "active",
        "created_turn": int(turn or 0),
        "last_reaffirmed_turn": int(turn or 0),
        "elapsed_minutes": 0,
        "milestones_reached": 0,
        "milestone_cadence_days": cadence,
        "until_condition": _until(directive),
        "blocked_reason": "",
        "ended_reason": "",
        "hidden_by_default": True,
        "signature": signature,
    }


def _cancel_matching(intents, command, turn):
    wanted = _tokens(command)
    cancel_all = bool(re.search(r"\b(all|every|everything)\b", command, re.I))
    changed = []
    for intent in intents:
        if not isinstance(intent, dict) or intent.get("status", "active") not in ACTIVE_STATUSES:
            continue
        overlap = wanted & _tokens(intent.get("directive", ""))
        if cancel_all or len(overlap) >= 1:
            intent["status"] = "cancelled"
            intent["ended_reason"] = _clean(command)[:240]
            intent["ended_turn"] = int(turn or 0)
            changed.append(intent.get("id"))
    return changed


def register_standing_intents(state, actions):
    """Adopt/reaffirm/cancel durable instructions without an extra AI call."""
    intents = state.setdefault("standing_intents", [])
    if not isinstance(intents, list):
        intents = state["standing_intents"] = []
    turn = int(state.get("turn", 0) or 0)
    adopted, consumed, cancelled = [], [], []
    action_rows = [row for row in str(actions or "").splitlines() if row.strip()] if isinstance(actions, str) else (actions or [])
    for action in action_rows:
        text = _clean(action)
        if not text:
            continue
        if _CANCEL_LANGUAGE.search(text):
            changed = _cancel_matching(intents, text, turn)
            if changed:
                cancelled.extend(changed); consumed.append(text)
            continue
        inferred = infer_standing_intent(text, turn)
        if not inferred:
            continue
        existing = next((row for row in intents if isinstance(row, dict) and
                         row.get("signature") == inferred["signature"] and
                         row.get("status", "active") in ACTIVE_STATUSES), None)
        if existing:
            existing["last_reaffirmed_turn"] = turn
            existing["directive"] = inferred["directive"]
            existing["status"] = "active"
            existing["blocked_reason"] = ""
            adopted.append(existing["id"])
        else:
            if re.search(r"\binstead\b", text, re.I):
                for row in intents:
                    if isinstance(row, dict) and row.get("kind") == inferred["kind"] and row.get("actor") == inferred["actor"] and row.get("status") in ACTIVE_STATUSES:
                        row["status"] = "cancelled"; row["ended_reason"] = f"Superseded by: {text}"; row["ended_turn"] = turn
            intents.append(inferred); adopted.append(inferred["id"])
        consumed.append(text)
    state["standing_intents"] = intents[-100:]
    return {"adopted": adopted, "cancelled": cancelled, "consumed_directives": consumed}


def active_standing_intents(state):
    return [copy.deepcopy(row) for row in state.get("standing_intents", [])
            if isinstance(row, dict) and row.get("status", "active") in ACTIVE_STATUSES]


def standing_intent_context(state, elapsed_minutes=0):
    """Compact projection included in an already-needed GM turn."""
    elapsed = max(0, int(elapsed_minutes or 0))
    rows = []
    for intent in active_standing_intents(state):
        cadence = max(1, int(intent.get("milestone_cadence_days", 7) or 7)) * 1440
        before = int(intent.get("elapsed_minutes", 0) or 0) // cadence
        after = (int(intent.get("elapsed_minutes", 0) or 0) + elapsed) // cadence
        rows.append({key: copy.deepcopy(intent.get(key)) for key in (
            "id", "directive", "kind", "actor", "status", "until_condition", "blocked_reason"
        ) if intent.get(key) not in (None, "", [], {})} | {
            "elapsed_before_minutes": int(intent.get("elapsed_minutes", 0) or 0),
            "elapsed_in_this_advance": elapsed,
            "new_milestones_due": max(0, after - before),
        })
    return rows


def _apply_updates(intents, updates, turn):
    indexed = {str(row.get("id")): row for row in intents if isinstance(row, dict) and row.get("id")}
    for update in updates or []:
        if not isinstance(update, dict) or str(update.get("id")) not in indexed:
            continue
        intent = indexed[str(update["id"])]
        status = str(update.get("status") or intent.get("status") or "active").lower()
        if status not in ACTIVE_STATUSES | FINAL_STATUSES:
            status = intent.get("status", "active")
        intent["status"] = status
        if status == "temporarily_blocked":
            intent["blocked_reason"] = _clean(update.get("reason") or "Current circumstances prevent progress")[:240]
        elif status == "active":
            intent["blocked_reason"] = ""
        elif status in FINAL_STATUSES:
            intent["ended_reason"] = _clean(update.get("reason") or status)[:240]
            intent["ended_turn"] = int(turn or 0)


def advance_standing_intents(state, elapsed_minutes, updates=None):
    """Commit elapsed continuity after the validator approves actual time."""
    elapsed = max(0, int(elapsed_minutes or 0)); turn = int(state.get("turn", 0) or 0)
    intents = state.setdefault("standing_intents", [])
    milestone_ids = []
    for intent in intents:
        if not isinstance(intent, dict) or intent.get("status") != "active":
            continue
        cadence = max(1, int(intent.get("milestone_cadence_days", 7) or 7)) * 1440
        before = int(intent.get("elapsed_minutes", 0) or 0)
        after = before + elapsed
        old_count, new_count = before // cadence, after // cadence
        intent["elapsed_minutes"] = after
        intent["last_advanced_turn"] = turn
        intent["milestones_reached"] = max(int(intent.get("milestones_reached", 0) or 0), new_count)
        if new_count > old_count:
            milestone_ids.append(intent.get("id"))
    # A completion or interruption reported for this resolved interval takes
    # effect at its end. The instruction was still operating during the time
    # that just elapsed, so preserve that progress before changing its status.
    _apply_updates(intents, updates, turn)
    return milestone_ids


def player_training_directives(state):
    return [row["directive"] for row in active_standing_intents(state)
            if row.get("kind") == "training" and row.get("actor") == "player" and row.get("status") == "active"]
