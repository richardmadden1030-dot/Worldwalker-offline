"""Small local safeguards and bounded retrieval; no additional model calls."""
from __future__ import annotations

import copy
import hashlib
import json
import re


def obj(value):
    return value if isinstance(value, dict) else {}


def seq(value):
    return value if isinstance(value, list) else []


def words(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    stop = {"the", "and", "that", "this", "with", "from", "have", "has", "was", "were", "you", "your",
            "they", "their", "them", "about", "into", "for", "not", "but", "she", "her", "him", "his",
            "then", "would", "could", "should", "will", "said", "says", "knows", "known", "heard",
            "fact", "confirmed", "source", "report", "reports", "because", "after", "before", "player"}
    tokens = [w.strip("'-") for w in re.findall(r"[\w'-]+", value.casefold())]
    return {re.sub(r"(?:ing|ed|s)$", "", w) if len(w) > 5 else w for w in tokens if len(w) > 2 and w not in stop}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def acquisition_claim(state, narrative):
    """Require an affirmative player acquisition, not a power keyword anywhere."""
    subject = r"(?:you|" + re.escape(str(state.get("name") or "the player")) + r")"
    for sentence in re.split(r"(?<=[.!?])\s+|\n", str(narrative or "")):
        # Quoted lessons, future/conditional/historical clauses are not a new award.
        if re.search(r'\b(?:if|unless|might|could|would|will|already|previously|once|remember|recall|discuss|explain|ask|had|not|never)\b|[“”"]', sentence, re.I):
            continue
        match = re.search(rf"\b{subject}\s+(?:(?:have|has|finally|now|successfully)\s+){{0,3}}"
                          r"(?:master(?:ed|s)?|awaken(?:ed|s)?|unlock(?:ed|s)?|acquire(?:d|s)?|learn(?:ed|s)?|achieve(?:d|s)?)\s+(.+)", sentence, re.I)
        if match and re.search(r"\b(?:bankai|shikai|haki|nen|domain|skill|technique|ability|form|class|release|transformation)\b", match[1], re.I):
            return True
        if re.search(rf"\b{subject}\s+(?:finally\s+|now\s+)?(?:evolve|evolved)\s+into\b", sentence, re.I):
            return True
    return False


def commanded_people(state, query, thread=""):
    """Ground pronouns/groups in established membership AND command authority."""
    known = copy.deepcopy(obj(state.get("npc_memories")))
    for row in seq(state.get("companions")):
        if isinstance(row, dict) and row.get("name"):
            known[row["name"]] = {**obj(known.get(row["name"])), **row}
    player = str(state.get("name", "")).casefold()
    eligible = {}
    for name, raw in known.items():
        row = obj(raw)
        leader = str(row.get("reports_to") or row.get("commander") or row.get("leader") or "").casefold()
        if str(row.get("status", "")).casefold() in {"dead", "deceased", "missing"}:
            continue
        if (row.get("subordinate") is True or leader in ({player, "player", "the player"} - {""})
                or re.search(r"\b(?:subordinate|retainer|summon)\b", str(row.get("role", "")), re.I)):
            eligible[str(name)] = row
    explicit = [n for n in eligible if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", query, re.I)]
    if explicit:
        return explicit[:16]
    group = re.search(r"\b(?:my|our|the)\s+(guards|squad|soldiers|retainers|subordinates|crew|team)\b", query, re.I)
    if group:
        label = group[1].lower()
        patterns = {"guards": r"guard|security", "soldiers": r"soldier|military|guard", "crew": r"crew|sailor|navigator|cook",
                    "squad": r"squad", "team": r"team", "retainers": r"retainer", "subordinates": r"."}
        return [n for n, row in eligible.items() if re.search(patterns[label], " ".join(str(row.get(k, "")) for k in
                ("role", "group", "squad", "team", "unit", "affiliation")), re.I)][:16]
    if re.search(r"\b(?:her|him|them|he|she|continue|keep)\b", query, re.I):
        if thread in eligible:
            return [thread]
        recent = obj(state.get("last_command_context"))
        if int(state.get("turn", 0) or 0) - int(recent.get("turn", -100) or 0) <= 2:
            candidates = [n for n in seq(recent.get("actors")) if n in eligible]
            if len(candidates) == 1 or (candidates and re.search(r"\bthem\b", query, re.I)):
                return candidates[:16]
        present = [n for n in seq(obj(state.get("scene_state")).get("present")) if isinstance(n, str)]
        # Multiple people present means a pronoun is genuinely ambiguous.
        if len(present) == 1 and present[0] in eligible:
            return present
    return []


def connected_memory(state, query, limit=12):
    """One bounded association hop across durable records; no whole-history prompt."""
    terms = words(query)
    if not terms:
        return {"records": [], "names": []}
    pool = []
    fields = ("npc_memories", "factions", "faction_rosters", "settlements", "projects", "long_term_projects", "npc_relationships",
              "location_details", "custom_locations", "standing_intents", "obligation_ledger", "quest_archive", "quests", "settled_stories", "story_threads")
    pools = [(field, state.get(field)) for field in fields]
    pools += [("narrative_memory.promises", obj(state.get("narrative_memory")).get("promises")),
              ("special.Nation Record.settlements", obj(obj(state.get("special")).get("Nation Record")).get("settlements"))]
    for field, raw in pools:
        rows = list(raw.items()) if isinstance(raw, dict) else [("", r) for r in seq(raw)]
        for key, value in rows[-400:]:
            row = obj(value) if isinstance(value, dict) else {"members": value} if isinstance(value, list) else {"text": str(value or "")}
            if field == "npc_relationships" and isinstance(value, dict):
                row = {"relationship": value}
            name = str(key or row.get("name") or row.get("title") or row.get("owner") or "")
            # Avoid large nested archives in an otherwise relevant record.
            detail = {k: copy.deepcopy(v) for k, v in row.items() if k in {
                "name", "title", "owner", "responsible", "caretaker", "location", "last_known_location", "status", "goal",
                "immediate_goal", "promise", "outcome", "directive", "text", "effect", "result", "summary", "affiliation",
                "faction", "leader", "members", "participants", "subject", "target", "relationship", "reports_to", "rank",
                "actor", "owed_to", "condition", "description", "notes"}}
            blob = json.dumps([name, detail], ensure_ascii=False, default=str)
            pool.append({"source": field, "name": name, "detail": detail, "terms": words(blob), "blob": blob})
    seeds = sorted([(len(terms & r["terms"]), i, r) for i, r in enumerate(pool) if terms & r["terms"]],
                   key=lambda x: (-x[0], -x[1]))[:6]
    names = [name for name in obj(state.get("npc_memories")) if re.search(rf"(?<!\w){re.escape(str(name))}(?!\w)", query, re.I)]
    for _, _, seed in seeds:
        for name in obj(state.get("npc_memories")):
            if name not in names and re.search(rf"(?<!\w){re.escape(str(name))}(?!\w)", seed["blob"], re.I):
                names.append(name)
    expanded = terms | set().union(*(words(n) for n in names[:8])) if names else terms
    ranked = sorted([(len(terms & r["terms"]) * 4 + len(expanded & r["terms"]), i, r)
                     for i, r in enumerate(pool) if expanded & r["terms"]], key=lambda x: (-x[0], -x[1]))
    records = [{"source": r["source"], "name": r["name"], "detail": r["detail"]} for _, _, r in ranked[:limit]]
    # Bound each record without cutting JSON or injecting an incomplete object.
    for record in records:
        for key, value in list(record["detail"].items()):
            if isinstance(value, str): record["detail"][key] = value[:350]
            elif isinstance(value, list): record["detail"][key] = value[:6]
            elif isinstance(value, dict): record["detail"][key] = str(value)[:350]
    return {"records": records, "names": names[:8]}


def relevant_evidence(row, references, actor=""):
    """Reject unrelated citations; lexical checks are not a proof of all prose."""
    claim = str(row.get("basis_fact") or row.get("cause") or row.get("response") or row.get("effect") or "")
    terms = words(claim) - words(actor)
    for ref in references:
        if not isinstance(ref, dict): continue
        if ref.get("kind") == "witness": return True
        fact = str(ref.get("fact") or "")
        if not terms or not words(fact): continue
        if terms & (words(fact) - words(actor)):
            if ref.get("kind") in {"suspected", "false_beliefs"} and row.get("certainty") == "confirmed":
                continue
            return True
    return False


FINAL = {"complete", "completed", "resolved", "fulfilled", "cancelled", "canceled", "archived"}
SETTLED_FIELDS = ("quests", "quest_archive", "projects", "long_term_projects", "obligation_ledger", "standing_intents", "story_threads", "action_goals")


def story_name(row):
    return str(row.get("name") or row.get("title") or row.get("promise") or row.get("text") or row.get("directive") or row.get("condition") or "").strip()


def story_source(field):
    return {"quest_archive": "quests", "long_term_projects": "projects"}.get(field, field)


def record_settled_stories(before, state):
    archive = seq(state.get("settled_stories"))
    for field in SETTLED_FIELDS:
        raw = state.get(field)
        entries = list(raw.values()) if isinstance(raw, dict) else seq(raw)
        for row in entries:
            if not isinstance(row, dict) or str(row.get("status", "")).lower() not in FINAL: continue
            name = story_name(row)
            if not name: continue
            source_field = story_source(field)
            identity = fingerprint([source_field, name.casefold()])[:20]
            if not any(r.get("id") == identity for r in archive if isinstance(r, dict)):
                archive.append({"id": identity, "source": source_field, "name": name, "status": row["status"],
                                "result": str(row.get("outcome") or row.get("result") or row.get("summary") or "")[:500],
                                "location": row.get("location", ""), "turn": state.get("turn", 0)})
    state["settled_stories"] = archive[-160:]


def closure_issues(state, data, evidence):
    settled = {(r.get("source"), str(r.get("name", "")).casefold()): r for r in seq(state.get("settled_stories")) if isinstance(r, dict)}
    # Also protect old saves before their first archive refresh.
    scratch = {key: copy.deepcopy(state.get(key)) for key in
               (*SETTLED_FIELDS, "settled_stories", "turn")}
    record_settled_stories(state, scratch)
    settled.update({(r.get("source"), r["name"].casefold()): r for r in scratch.get("settled_stories", [])})
    issues = []
    proposed = [(field, obj(data.get("state_patch")).get(field)) for field in SETTLED_FIELDS if field != "quest_archive"]
    proposed.append(("obligation_ledger", [{**r, "status": r.get("status") or "active"} for r in seq(data.get("commitment_updates")) if isinstance(r, dict)]))
    standing = {str(r.get("id")): r for r in seq(state.get("standing_intents")) if isinstance(r, dict)}
    proposed.append(("standing_intents", [{**standing.get(str(r.get("id")), {}), **r} for r in seq(data.get("standing_intent_updates")) if isinstance(r, dict)]))
    for field, raw in proposed:
        for row in (list(raw.values()) if isinstance(raw, dict) else seq(raw)):
            if not isinstance(row, dict) or "status" not in row: continue
            name = story_name(row)
            if (story_source(field), name.casefold()) not in settled or str(row["status"]).lower() in FINAL: continue
            reopening = next((r for r in seq(data.get("reopened_threads")) if isinstance(r, dict) and str(r.get("name", "")).casefold() == name.casefold()), {})
            refs = [evidence.get(ref) for ref in seq(reopening.get("evidence_refs")) if isinstance(ref, str)]
            if not reopening.get("cause") or not relevant_evidence(reopening, [r for r in refs if r and r.get("kind") != "witness"]):
                issues.append(f"{name} was settled. Keep it settled unless a new evidenced cause explicitly reopens it; retain the original accomplishment.")
    return issues


REFINEMENT_RULE = """
Use connected_memories to follow relevant people, promises and places, not to expose secrets to NPCs.
Settled stories remain settled. Let completed work have ordinary beneficial uses and natural callbacks;
do not manufacture another crisis, repeat the award, or force a callback into every scene. To genuinely
reopen the SAME problem, return reopened_threads with name, cause and applicable turn_evidence IDs.
For non-witness reactions or obstacles, basis_fact must identify what the cited evidence actually says.
An unrelated true fact is not justification. Heard/suspected/false-belief information is not confirmed truth.
Recognized command targets include groups and unambiguous follow-ups; preserve the objective, constraints
and standing nature of the order. If reference_resolution is ambiguous, ask one narrow clarification
without executing an irreversible interpretation. Friendship or strength alone does not confer authority.
"""
