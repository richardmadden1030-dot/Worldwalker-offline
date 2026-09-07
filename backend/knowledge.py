"""Deterministic NPC knowledge boundaries.

The narrator may know the whole campaign, but individual characters should not.
This module normalizes each NPC's confirmed knowledge, hearsay, suspicions and
false beliefs, and downgrades unsupported claims about concealed player facts.
"""
import copy
import re

from util import ai_text


KNOWLEDGE_BUCKETS = ("confirmed", "heard", "suspected", "false_beliefs")
SUPPORTED_SOURCES = {
    "witnessed", "witness", "told", "conversation", "message", "letter",
    "evidence", "report", "rumor", "broadcast", "research", "ability",
    "public", "canon", "inference",
}


def _fact_record(value, default_source="unknown", turn=0):
    if isinstance(value, dict):
        text = ai_text(value.get("fact") or value.get("text") or value.get("claim"))
        source = ai_text(value.get("source") or default_source).lower()
        confidence = value.get("confidence")
    else:
        text, source, confidence = ai_text(value), default_source, None
    if not text:
        return None
    try:
        confidence = max(0, min(100, int(confidence))) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    provenance = {key: copy.deepcopy(value[key]) for key in ("id", "canon_day", "available_at_minutes", "delivered_at_minutes") if key in value} if isinstance(value, dict) else {}
    recorded_turn = value.get("turn", turn) if isinstance(value, dict) else turn
    try:
        recorded_turn = int(recorded_turn or 0)
    except (ValueError, TypeError, OverflowError):
        recorded_turn = int(turn or 0)
    return {**provenance, "fact": text[:500], "source": source[:80] or "unknown", "turn": recorded_turn,
            **({"confidence": confidence} if confidence is not None else {})}


def _records(value, default_source="unknown", turn=0):
    if isinstance(value, str) or isinstance(value, dict):
        value = [value]
    out, seen = [], set()
    for raw in value if isinstance(value, list) else []:
        row = _fact_record(raw, default_source, turn)
        if not row:
            continue
        key = row["fact"].strip().lower()
        if key in seen:
            continue
        seen.add(key); out.append(row)
    return out[:80]


def concealed_player_facts(state):
    """Facts the narrator may use but NPCs need a believable route to know."""
    state = state if isinstance(state, dict) else {}
    facts = []
    profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    if discovery.get("concealed") and int(discovery.get("progress", 0) or 0) < 100:
        for value in (profile.get("true_name"), profile.get("name"), profile.get("signature_skill")):
            if ai_text(value): facts.append(ai_text(value))
    skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name, value in skills.items():
        if isinstance(value, dict) and (value.get("secret") or value.get("hidden")):
            facts.append(str(name))
    hidden_stats = state.get("hidden_stats") if isinstance(state.get("hidden_stats"), dict) else {}
    for name in hidden_stats:
        facts.append(str(name))
    return list(dict.fromkeys(x for x in facts if x))


def _mentions_secret(text, secrets):
    low = text.lower()
    for secret in secrets:
        words = [x for x in re.findall(r"[a-z0-9'-]+", secret.lower()) if len(x) >= 4]
        if secret.lower() in low or (words and sum(word in low for word in words) >= min(2, len(words))):
            return secret
    return ""


def normalize_npc_knowledge(state, before=None, source="state_patch"):
    """Normalize knowledge records and audit unsupported new secret knowledge.

    Unsupported *confirmed* facts are not deleted. They become suspicions, which
    preserves the story idea without granting unexplained omniscience.
    """
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    before_memories = before.get("npc_memories", {}) if isinstance(before, dict) and isinstance(before.get("npc_memories"), dict) else {}
    secrets = concealed_player_facts(state)
    audit = state.setdefault("knowledge_audit", [])
    turn = int(state.get("turn", 0) or 0)
    changes = []
    for name, memory in memories.items():
        if not isinstance(memory, dict):
            continue
        raw = memory.get("knowledge") if isinstance(memory.get("knowledge"), dict) else {}
        # Legacy `knows` meant confirmed personal knowledge.
        if memory.get("knows") and not raw.get("confirmed"):
            raw = {**raw, "confirmed": memory.get("knows")}
        knowledge = {bucket: _records(raw.get(bucket, []), "unknown", turn) for bucket in KNOWLEDGE_BUCKETS}
        previous = before_memories.get(name, {}) if isinstance(before_memories.get(name), dict) else {}
        previous_knowledge = previous.get("knowledge") if isinstance(previous.get("knowledge"), dict) else {}
        previous_confirmed = {ai_text(x.get("fact") if isinstance(x, dict) else x).lower() for x in previous_knowledge.get("confirmed", [])}
        kept = []
        for row in knowledge["confirmed"]:
            secret = _mentions_secret(row["fact"], secrets)
            source_kind = row.get("source", "unknown").split(":", 1)[0]
            is_new = row["fact"].lower() not in previous_confirmed
            if secret and is_new and source_kind not in SUPPORTED_SOURCES:
                downgraded = dict(row, source="unsupported inference", confidence=min(65, int(row.get("confidence", 50) or 50)))
                knowledge["suspected"].append(downgraded)
                item = {"npc": str(name), "fact": row["fact"], "secret": secret, "action": "downgraded_to_suspicion",
                        "reason": "No witnessed, reported, researched, or public information path was recorded.",
                        "turn": turn, "source": source}
                audit.append(item); changes.append(item)
            else:
                kept.append(row)
        knowledge["confirmed"] = kept
        memory["knowledge"] = knowledge
        memory.pop("knows", None)
    state["knowledge_audit"] = audit[-200:]
    return changes


def npc_knowledge_boundaries(state):
    out = {}
    state = state if isinstance(state, dict) else {}
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    for name, memory in memories.items():
        if not isinstance(memory, dict):
            continue
        knowledge = memory.get("knowledge") if isinstance(memory.get("knowledge"), dict) else {}
        out[name] = {bucket: [row.get("fact", "") if isinstance(row, dict) else ai_text(row)
                              for row in knowledge.get(bucket, [])]
                     for bucket in KNOWLEDGE_BUCKETS}
    return out


def knowledge_snapshot(state):
    rows = []
    state = state if isinstance(state, dict) else {}
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    for name, memory in memories.items():
        if not isinstance(memory, dict):
            continue
        knowledge = copy.deepcopy(memory.get("knowledge")) if isinstance(memory.get("knowledge"), dict) else {}
        if any(knowledge.get(bucket) for bucket in KNOWLEDGE_BUCKETS):
            rows.append({"name": name, "knowledge": knowledge, "last_known_location": memory.get("last_known_location", "Unknown")})
    audit = state.get("knowledge_audit") if isinstance(state.get("knowledge_audit"), list) else []
    return {"people": rows, "recent_audit": copy.deepcopy(audit[-30:]),
            "concealed_fact_count": len(concealed_player_facts(state))}
