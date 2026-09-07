"""Local causal follow-ups for the Living World Director.

This module never invents a disconnected crisis. It converts repeated player
behavior and already-recorded relationships into eligible, deduplicated story
prompts that the normal narrator may elaborate during the same turn.
"""
from __future__ import annotations

import copy
import hashlib
import re

from gm_policy import parse_player_intent
from util import ai_text


WORLD_LABELS = {
    "Naruto": {"training": "shinobi training", "quest": "mission work", "governance": "village leadership", "social": "team life"},
    "One Piece": {"training": "crew training", "quest": "island work", "governance": "territory leadership", "social": "crew life"},
    "Hunter x Hunter": {"training": "Nen development", "quest": "Hunter work", "governance": "organizational leadership", "social": "professional contacts"},
    "Bleach": {"training": "spiritual training", "quest": "Soul Reaper duty", "governance": "division leadership", "social": "division life"},
    "Jujutsu Kaisen": {"training": "jujutsu training", "quest": "curse investigations", "governance": "school or clan leadership", "social": "sorcerer life"},
    "Overgeared": {"training": "class development", "quest": "Satisfy opportunities", "governance": "guild leadership", "social": "guild life"},
    "Solo Max-Level Newbie": {"training": "build development", "quest": "Tower clears", "governance": "faction leadership", "social": "party life"},
    "Reincarnated as a Slime": {"training": "skill development", "quest": "nation work", "governance": "national leadership", "social": "subordinate life"},
    "Custom World": {"training": "training", "quest": "local work", "governance": "leadership", "social": "relationships"},
}


def _living(state):
    value = state.setdefault("living_world", {})
    if not isinstance(value, dict):
        value = state["living_world"] = {}
    value.setdefault("patterns", {})
    value.setdefault("target_patterns", {})
    value.setdefault("event_history", [])
    value.setdefault("cooldowns", {})
    value.setdefault("interpretation_history", [])
    value.setdefault("outcome_history", [])
    value.setdefault("npc_contact_history", [])
    state.setdefault("generated_content_history", [])
    return value


def interpretation(action, state=None):
    """Return the player-visible local reading of an action."""
    contract = parse_player_intent(action, state)
    activities = contract.get("activity") or ["general"]
    targets = contract.get("targets") or []
    if not targets:
        companion = re.search(r"\b(?:with|ask|tell|teach|help|visit|contact)\s+([A-Z][A-Za-z' -]{1,40}?)(?=\s+(?:for|to|about|at|in)\b|[.,;!?]|$)", ai_text(action))
        if companion:
            targets = [companion.group(1).strip()]
    duration = contract.get("duration") or {}
    duration_text = ""
    if duration:
        duration_text = f"{duration.get('amount', '')} {duration.get('unit', '')}".strip()
    elif contract.get("standing"):
        duration_text = "ongoing"
    scene = state.get("scene_state", {}) if isinstance(state, dict) else {}
    present = scene.get("present", []) if isinstance(scene, dict) and isinstance(scene.get("present"), list) else []
    pronouns = bool(re.search(r"\b(?:him|her|them|they|he|she|that person)\b", ai_text(action), re.I))
    reasons = []
    if activities == ["general"] and (len(ai_text(action).split()) < 3 or re.search(r"\b(?:something|somehow|it|that|this)\b", ai_text(action), re.I)):
        reasons.append("The action type is not specific enough for a confident local classification.")
    if pronouns and len(present) != 1 and not targets:
        reasons.append("The pronoun could refer to more than one person in the current scene.")
    if len(targets) > 1 and re.search(r"\b(?:him|her|them|one of them)\b", ai_text(action), re.I):
        reasons.append("More than one known target fits the wording.")
    method = ai_text(contract.get("method"))
    summary = f"{', '.join(x.replace('_', ' ') for x in activities).title()}"
    if targets:
        summary += f" involving {', '.join(targets)}"
    if method:
        summary += f" using {method}"
    if duration_text:
        summary += f" for {duration_text}"
    if contract.get("standing"):
        summary += " as a standing instruction"
    if contract.get("lethality") != "unspecified":
        summary += f" ({contract['lethality']})"
    return {"summary": summary[:500], "activity": activities, "targets": targets,
            "method": method, "duration": duration_text, "standing": bool(contract.get("standing")),
            "lethality": contract.get("lethality", "unspecified"), "ambiguous": bool(reasons),
            "ambiguity_reasons": reasons, "contract": contract}


def remember_interpretation(state, action):
    view = interpretation(action, state)
    living = _living(state)
    living["interpretation_history"].append({"turn": int(state.get("turn", 0) or 0),
                                             "action": ai_text(action)[:500], **{k: copy.deepcopy(view[k]) for k in ("summary", "activity", "targets", "duration", "standing", "lethality")}})
    living["interpretation_history"] = living["interpretation_history"][-80:]
    return view


def _fingerprint(*parts):
    return hashlib.sha256("|".join(ai_text(x).casefold().strip() for x in parts).encode("utf-8")).hexdigest()[:20]


def _record_generated(state, kind, name, source):
    rows = state.setdefault("generated_content_history", [])
    token = _fingerprint(kind, name)
    if any(isinstance(row, dict) and row.get("fingerprint") == token for row in rows):
        return False
    rows.append({"fingerprint": token, "kind": kind, "name": ai_text(name)[:240],
                 "source": ai_text(source)[:300], "turn": int(state.get("turn", 0) or 0),
                 "canon_day": int(state.get("canon_day", 0) or 0)})
    state["generated_content_history"] = rows[-500:]
    return True


def _known_people(state):
    rows = []
    for field in ("npc_memories", "contacts"):
        mapping = state.get(field) if isinstance(state.get(field), dict) else {}
        for name, raw in mapping.items():
            detail = raw if isinstance(raw, dict) else {}
            if not any(existing[0].casefold() == ai_text(name).casefold() for existing in rows):
                rows.append((ai_text(name), detail))
    return [(name, detail) for name, detail in rows if name and name.casefold() != ai_text(state.get("name")).casefold()]


def _event_for(state, kind, count, target=""):
    world = ai_text(state.get("world") or "Custom World")
    labels = WORLD_LABELS.get(world, WORLD_LABELS["Custom World"])
    location = ai_text(state.get("location") or "the current area")
    if kind == "training":
        return {"title": "Training Bears Fruit", "type": "opportunity",
                "narrative": f"Your repeated {labels['training']} is now visible in your consistency and control. A focused breakthrough, specialist lesson, or harder practical test is available if you pursue it.",
                "why_it_matters": "This opportunity exists because of sustained practice, not a random reward.",
                "next_pressure": "Choose whether to consolidate the improvement, seek instruction, or test it under pressure."}
    if kind in {"quest", "investigation"}:
        return {"title": "A Lead Connects", "type": "opportunity",
                "narrative": f"Your repeated {labels['quest']} in {location} connects two previously separate details. The new lead can be followed, shared, or left alone without forcing a battle.",
                "why_it_matters": "The lead comes from work the character actually performed.",
                "next_pressure": "Decide who should know and whether the lead is worth pursuing now."}
    if kind == "governance":
        return {"title": "Leadership Has Become a Pattern", "type": "faction_reaction",
                "narrative": f"People affected by your {labels['governance']} have enough experience to judge the pattern rather than one isolated command. Their response should reflect recorded treatment, fulfilled promises, safety, and material conditions.",
                "why_it_matters": "Authority now produces a grounded public response instead of an automatic crisis.",
                "next_pressure": "Listen to the people affected or continue the established policy."}
    if kind in {"social", "communication"} and target:
        # Shared-experience candidates now reach the normal narrator. A generic
        # instruction about what an NPC should do is not a player-facing event.
        return None
    if kind in {"crafting", "finance"}:
        return {"title": "Practical Work Creates an Opening", "type": "opportunity",
                "narrative": f"Your repeated practical work in {location} creates a credible new customer, collaborator, improvement, or reuse opportunity. Trivial ingredients remain narrative; only memorable results need inventory records.",
                "why_it_matters": "The opportunity follows demonstrated work and local demand.",
                "next_pressure": "Choose whether this result is worth developing further."}
    return None


def _npc_contact(state, living):
    # Compatibility entry point: never fabricate dialogue by pasting a goal.
    # relationship_life prepares evidence for the already-budgeted GM turn.
    return None


def record_outcome(state, data, actions):
    causal = data.get("causal_outcome") if isinstance(data, dict) and isinstance(data.get("causal_outcome"), dict) else {}
    complications = causal.get("complications") if isinstance(causal.get("complications"), list) else []
    reactions = causal.get("reactions") if isinstance(causal.get("reactions"), list) else []
    result = ai_text(causal.get("direct_result") or (data or {}).get("narrative"))
    if complications:
        kind = "setback" if not result else "mixed"
    elif re.search(r"\b(?:fail|cannot|unable|falls short|does not)\b", result, re.I):
        kind = "failure"
    elif reactions:
        kind = "success_with_response"
    else:
        kind = "clean_success"
    living = _living(state)
    living["outcome_history"].append({"turn": int(state.get("turn", 0) or 0), "kind": kind,
                                      "actions": [ai_text(x)[:300] for x in actions or []], "result": result[:500]})
    living["outcome_history"] = living["outcome_history"][-120:]
    return kind


def advance(state, actions=None, elapsed_minutes=0, updates=None, plan_updates=None):
    """Advance local patterns and return eligible follow-ups for this turn."""
    actions = [ai_text(x).strip() for x in actions or [] if ai_text(x).strip()]
    living = _living(state)
    turn = int(state.get("turn", 0) or 0)
    events = []
    for action in actions:
        view = remember_interpretation(state, action)
        target = (view.get("targets") or [""])[0]
        for kind in view.get("activity") or ["general"]:
            living["patterns"][kind] = int(living["patterns"].get(kind, 0) or 0) + 1
            if target:
                target_key = f"{kind}:{target.casefold()}"
                living["target_patterns"][target_key] = int(living["target_patterns"].get(target_key, 0) or 0) + 1
            count = living["patterns"][kind]
            cooldown = int(living["cooldowns"].get(kind, -999) or -999)
            if count < 3 or count % 3 or turn - cooldown < 5:
                continue
            event = _event_for(state, kind, count, target)
            if not event:
                continue
            token = _fingerprint(state.get("world"), kind, count // 3, target)
            if any(isinstance(row, dict) and row.get("id") == token for row in living["event_history"]):
                continue
            event.update(id=token, source_action=action[:400], pattern=kind, count=count,
                         sequence=7600 + len(events), importance=55)
            living["event_history"].append({"id": token, "title": event["title"], "pattern": kind,
                                            "turn": turn, "source_action": action[:300]})
            living["cooldowns"][kind] = turn
            _record_generated(state, "causal_event", event["title"], action)
            events.append(event)
    living["event_history"] = living["event_history"][-200:]
    from world_plans import advance as advance_plans
    plan_events = advance_plans(state,elapsed_minutes,plan_updates)
    contact = _npc_contact(state, living)
    return {"events": [*plan_events,*events][:2], "incoming_chats": [contact] if contact else [],
            "patterns": copy.deepcopy(living["patterns"]), "elapsed_minutes": max(0, int(elapsed_minutes or 0))}


def snapshot(state):
    living = _living(state)
    return {key: copy.deepcopy(living.get(key)) for key in
            ("patterns", "target_patterns", "event_history", "interpretation_history", "outcome_history", "npc_contact_history")}
