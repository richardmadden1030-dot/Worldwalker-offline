"""Normalize untrusted model responses before gameplay code consumes them.

The state guard protects persisted state.  This module protects the *response
envelope* itself: inexpensive/local models often return useful shorthand such
as a string event, a single update object, or a string combatant.  Treat those
as recoverable input rather than allowing a later ``.get`` to end the turn.
"""
from __future__ import annotations

import copy
import json
import re

from state_guard import normalize_combat_payload
from util import ai_text


def _dict(value):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    decoded = _decode_json(value)
    return copy.deepcopy(decoded) if isinstance(decoded, dict) else {}


def _decode_json(value):
    """Recover JSON objects/lists returned as strings or fenced blocks."""
    if not isinstance(value, str):
        return value
    source = value.strip()
    if source.startswith("```"):
        source = re.sub(r"^```(?:json)?\s*", "", source, flags=re.I)
        source = re.sub(r"\s*```$", "", source)
    if not source or source[0] not in "[{":
        return value
    try:
        return json.loads(source)
    except (TypeError, ValueError):
        # A truncated object cannot be safely invented, but a complete JSON
        # value wrapped in model chatter can still be recovered.
        starts = [index for index in (source.find("{"), source.find("[")) if index >= 0]
        for start in sorted(starts):
            for end in range(len(source), start + 1, -1):
                try:
                    return json.loads(source[start:end])
                except (TypeError, ValueError):
                    continue
    return value


def _text_list(value, limit=40):
    value = _decode_json(value)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    return [ai_text(row).strip()[:700] for row in value[:limit] if ai_text(row).strip()]


def _event_list(value):
    value = _decode_json(value)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for item in value[:80]:
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            row["type"] = ai_text(row.get("type") or "world").strip() or "world"
            row["message"] = ai_text(row.get("message") or row.get("narrative") or row.get("text") or row.get("title")).strip()
        else:
            row = {"type": "world", "message": ai_text(item).strip()}
        if row.get("message"):
            rows.append(row)
    return rows


def _update_list(value):
    value = _decode_json(value)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for index, item in enumerate(value[:120]):
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            narrative = ai_text(row.get("narrative") or row.get("message") or row.get("text")).strip()
            title = ai_text(row.get("title") or row.get("type") or "Story Update").strip()
        else:
            narrative, title, row = ai_text(item).strip(), "Story Update", {}
        if not narrative:
            continue
        row.update({"narrative": narrative, "title": title or "Story Update"})
        row.setdefault("type", "story")
        row.setdefault("sequence", index)
        rows.append(row)
    return rows


def _chat_list(value):
    value = _decode_json(value)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for item in value[:40]:
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            row["sender"] = ai_text(row.get("sender") or row.get("thread") or "Unknown contact").strip()
            row["thread"] = ai_text(row.get("thread") or row.get("sender")).strip()
            row["message"] = ai_text(row.get("message") or row.get("text") or row.get("narrative")).strip()
        else:
            row = {"sender": "Unknown contact", "thread": "Unknown contact", "message": ai_text(item).strip()}
        if row.get("message"):
            rows.append(row)
    return rows


def _information_list(value):
    value = _decode_json(value)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for item in value[:80]:
        if not isinstance(item, dict):
            continue
        fact = ai_text(item.get("fact") or item.get("message") or item.get("text")).strip()
        if not fact:
            continue
        recipients = item.get("recipients")
        if isinstance(recipients, str):
            recipients = [recipients]
        elif not isinstance(recipients, list):
            recipients = []
        try:
            delay = max(0, int(item.get("delay_minutes", 0) or 0))
        except (TypeError, ValueError):
            delay = 0
        try:
            confidence = max(0, min(100, int(item.get("confidence", 80) or 80)))
        except (TypeError, ValueError):
            confidence = 80
        rows.append({
            "fact": fact[:500],
            "source": ai_text(item.get("source") or "Unknown").strip()[:160],
            "channel": ai_text(item.get("channel") or "conversation").strip()[:80],
            "recipients": [ai_text(row).strip()[:160] for row in recipients if ai_text(row).strip()][:30],
            "delay_minutes": delay,
            "confidence": confidence,
        })
    return rows


def _causal_outcome(value):
    value = _decode_json(value)
    if not isinstance(value, dict):
        return {}
    result = {
        "direct_result": ai_text(value.get("direct_result") or value.get("result")).strip()[:900],
        "witnesses": _text_list(value.get("witnesses"), 30),
    }
    for key in ("reactions", "costs", "complications"):
        rows = value.get(key)
        if not isinstance(rows, list):
            rows = [rows] if isinstance(rows, dict) else []
        result[key] = [copy.deepcopy(row) for row in rows[:30] if isinstance(row, dict)]
    return result


def normalize_assessment_response(value):
    data = _dict(value)
    checks = data.get("checks")
    if not isinstance(checks, list):
        checks = [checks] if isinstance(checks, dict) else []
    data["checks"] = [copy.deepcopy(row) for row in checks[:30] if isinstance(row, dict)]
    data["reachable_actions"] = _text_list(data.get("reachable_actions"))
    data["deferred_actions"] = _text_list(data.get("deferred_actions"))
    data["time_budget"] = _dict(data.get("time_budget"))
    return data


def normalize_turn_response(value, task="turn"):
    """Return a safe, meaning-preserving response envelope.

    A bare string is retained as narrative.  Nested structures are normalized
    only where the engine has a documented shape; unknown keys remain intact.
    """
    decoded = _decode_json(value)
    if isinstance(decoded, dict):
        data = copy.deepcopy(decoded)
    elif isinstance(decoded, list):
        data = {"updates": decoded}
    elif isinstance(value, str):
        data = {"narrative": value}
    elif isinstance(value, dict):
        data = copy.deepcopy(value)
    else:
        data = {}
    narrative_value = data.get("narrative") or data.get("story") or data.get("text")
    data["narrative"] = ai_text(narrative_value).strip() if narrative_value not in (None, "") else ""
    data["state_patch"] = _dict(data.get("state_patch"))
    if "combat" in data["state_patch"]:
        data["state_patch"]["combat"] = normalize_combat_payload(data["state_patch"].get("combat"))
    data["events"] = _event_list(data.get("events"))
    data["updates"] = _update_list(data.get("updates"))
    data["incoming_chats"] = _chat_list(data.get("incoming_chats"))
    data["information_events"] = _information_list(data.get("information_events"))
    data["causal_outcome"] = _causal_outcome(data.get("causal_outcome"))
    data["suggested_actions"] = _text_list(data.get("suggested_actions"), 12)
    data["completed_actions"] = _text_list(data.get("completed_actions"))
    data["deferred_actions"] = _text_list(data.get("deferred_actions"))
    data["timeline_events"] = _text_list(data.get("timeline_events"))
    data["new_contacts"] = ([copy.deepcopy(row) for row in data.get("new_contacts", [])[:40]
                             if isinstance(row, dict)] if isinstance(data.get("new_contacts"), list) else [])
    for key in ("elapsed", "goal_status", "integrity_report"):
        if key in data:
            data[key] = _dict(data.get(key))
    for key in ("consequence_manifest", "commitment_updates", "delayed_consequences", "ability_developments"):
        value = _decode_json(data.get(key))
        data[key] = [copy.deepcopy(row) for row in value[:60] if isinstance(row, dict)] if isinstance(value, list) else []
    recovered_from = []
    if not data["narrative"] and data["updates"]:
        data["narrative"] = "\n\n".join(row["narrative"] for row in data["updates"] if row.get("narrative"))[:12000]
        recovered_from.append("updates")
    if not data["narrative"] and data["events"]:
        data["narrative"] = "\n".join(row["message"] for row in data["events"] if row.get("message"))[:12000]
        recovered_from.append("events")
    if not data["narrative"] and data["state_patch"]:
        data["narrative"] = "The planned action resolves, and the resulting changes are recorded."
        recovered_from.append("state_patch")
    if recovered_from:
        data["response_recovery"] = {
            "partial": True, "recovered_from": recovered_from,
            "note": "Usable response fields were recovered locally; no second AI call was needed.",
        }
    return data


def normalize_object_response(value, primary="reply"):
    """Make non-turn AI utilities safe without erasing their custom keys."""
    if isinstance(value, dict):
        data = copy.deepcopy(value)
    elif isinstance(value, str):
        data = {primary: value}
    else:
        data = {}
    if "state_patch" in data and not isinstance(data.get("state_patch"), dict):
        data["state_patch"] = {}
    if "events" in data:
        data["events"] = _event_list(data.get("events"))
    return data
