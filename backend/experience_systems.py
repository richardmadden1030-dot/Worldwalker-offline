"""Cost-free scenario continuity and world-native milestone detection."""
from __future__ import annotations

import copy
import hashlib
import re

from util import ai_text


WORLD_MILESTONES = {
    "Naruto": ("SHINOBI RECORD", ((r"\b(chunin|chūnin|jonin|jōnin|promotion|mission complete)\b", "Career recognition"), (r"\b(kekkei genkai|dojutsu|dōjutsu|jinchuriki|jinchūriki|summoning contract)\b", "Shinobi legacy"))),
    "One Piece": ("WORLD NEWS", ((r"\b(bounty|wanted poster|haki|captain|crew formed|island liberated)\b", "A name enters the wider sea"),)),
    "Hunter x Hunter": ("HUNTER RECORD", ((r"\b(hunter license|nen awakened|hatsu|vow|specialty)\b", "Hunter development"),)),
    "Bleach": ("SOUL SOCIETY RECORD", ((r"\b(graduate|squad|division|shikai|bankai|officer|seat)\b", "Shinigami development"),)),
    "Jujutsu Kaisen": ("JUJUTSU RECORD", ((r"\b(grade recommendation|promoted to grade|black flash|domain expansion|maximum technique)\b", "Sorcerer milestone"),)),
    "Overgeared": ("SATISFY SYSTEM", ((r"\b(level up|class acquired|class evolved|ranking|legendary item|guild founded)\b", "Satisfy milestone"),)),
    "Solo Max-Level Newbie": ("TOWER SYSTEM", ((r"\b(level up|floor clear|hidden condition|title acquired|achievement|administrator)\b", "Tower milestone"),)),
    "Reincarnated as a Slime": ("WORLD VOICE", ((r"\b(named|evolution|evolved|settlement|nation|skill synthesis|awakened)\b", "Evolution of self or nation"),)),
}


def _blob(data):
    parts = [ai_text(data.get("narrative"))]
    for key in ("events", "updates"):
        for row in data.get(key, []) if isinstance(data.get(key), list) else []:
            parts.append(ai_text(row))
    return " ".join(parts)


def record_world_milestones(state, data):
    """Detect noteworthy established outcomes without awarding anything new."""
    heading, rules = WORLD_MILESTONES.get(state.get("world"), ("CAMPAIGN RECORD", ()))
    text = _blob(data)
    if not text or not rules:
        return []
    ledger = state.setdefault("world_milestones", [])
    seen = {row.get("id") for row in ledger if isinstance(row, dict)}
    added = []
    for pattern, label in rules:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        context = next((sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text)
                        if match.group(0).lower() in sentence.lower()), text[:300]).strip()[:500]
        key = hashlib.sha1(f"{state.get('world')}|{label}|{context.lower()}".encode("utf-8")).hexdigest()[:16]
        if key in seen:
            continue
        row = {"id": key, "turn": int(state.get("turn", 0) or 0), "canon_day": state.get("canon_day"),
               "world": state.get("world"), "heading": heading, "title": label, "detail": context}
        ledger.append(row); added.append(row); seen.add(key)
    state["world_milestones"] = ledger[-160:]
    return added


def update_scenario_memory(before, state, actions, data):
    """Keep one authoritative active scenario plus a compact completed history."""
    memory = state.get("scenario_memory") if isinstance(state.get("scenario_memory"), dict) else {}
    active = memory.get("active") if isinstance(memory.get("active"), dict) else {}
    history = memory.get("history") if isinstance(memory.get("history"), list) else []
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    encounter = state.get("encounter_state") if isinstance(state.get("encounter_state"), dict) else {}
    action_text = "; ".join(ai_text(row) for row in actions if ai_text(row))
    narrative = ai_text(data.get("narrative"))
    interrupted = bool(data.get("interrupted"))
    event_title = ai_text(data.get("major_event_title") or state.get("active_canon_event"))
    if combat.get("active"):
        enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
        title = f"Confrontation with {enemy.get('name') or 'the opposition'}"
        active = {
            "id": active.get("id") or f"scenario-{state.get('turn', 0)}-combat",
            "title": title, "kind": "combat", "status": "active",
            "cause": combat.get("cause") or action_text or "Violence began in the current scene.",
            "objective": combat.get("victory_condition") or "Survive and decide the outcome of the confrontation.",
            "stakes": combat.get("defeat_risk") or "Injury, defeat, capture, or death as established by the scene.",
            "participants": [state.get("name", "Player"), enemy.get("name", "Opposition")],
            "location": combat.get("location") or state.get("location"),
            "started_turn": active.get("started_turn", state.get("turn", 0)), "updated_turn": state.get("turn", 0),
        }
    elif event_title or interrupted:
        active = {
            "id": active.get("id") or f"scenario-{state.get('turn', 0)}-event",
            "title": event_title or ai_text(data.get("interruption_reason")) or "Immediate development",
            "kind": ai_text(data.get("interruption_kind")) or "event", "status": "active",
            "cause": ai_text(data.get("interruption_reason")) or action_text,
            "objective": ai_text(data.get("intervention_prompt")) or "Choose how to respond.",
            "stakes": ai_text(data.get("interruption_context")), "participants": [],
            "location": state.get("location"), "started_turn": active.get("started_turn", state.get("turn", 0)),
            "updated_turn": state.get("turn", 0),
        }
    elif active and (encounter.get("phase") in {"aftermath", "resolved", "idle"} or data.get("danger_scenario_concluded")):
        finished = copy.deepcopy(active)
        finished.update({"status": "resolved", "resolved_turn": state.get("turn", 0),
                         "resolution": narrative[:700] or encounter.get("outcome", "The scenario concluded.")})
        history.append(finished); active = {}
    elif active:
        active["updated_turn"] = state.get("turn", 0)
        if narrative:
            active["latest_development"] = narrative[:700]
    state["scenario_memory"] = {"active": active, "history": history[-40:]}
    return state["scenario_memory"]
