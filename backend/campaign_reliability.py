"""Local grounding, consequence reconciliation, and memory consolidation.

These helpers deliberately make no model calls.  They turn the durable save
into a small evidence packet for each AI job, verify narrated consequences
against mechanical state, and archive old campaign history without discarding
the facts later turns still need.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from util import ai_text
from gm_consistency import current_fact_view, decision_profiles, record_fact_changes


_OUTCOME_SCALE_PATTERNS = (
    ("transformative", re.compile(r"\b(?:transcend(?:ed|s)?|reality[- ]bending|godlike|ascend(?:ed|s)?|evol(?:ve|ved|ution)|awak(?:en|ened|ening)|bankai|domain expansion|became? vastly|overwhelming breakthrough)\b", re.I)),
    ("major", re.compile(r"\b(?:master(?:ed|y)|major breakthrough|dramatic(?:ally)? stronger|huge(?:ly)? stronger|massive gain|new form|class evolution|tier breakthrough)\b", re.I)),
    ("noticeable", re.compile(r"\b(?:noticeable|significant|substantial|improved|breakthrough|learned|unlocked|gained)\b", re.I)),
)


def _numeric_delta(before, state, field):
    old = before.get(field) if isinstance(before.get(field), dict) else {}
    new = state.get(field) if isinstance(state.get(field), dict) else {}
    return {name: round(float(value) - float(old.get(name, value)), 3)
            for name, value in new.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            and isinstance(old.get(name, value), (int, float))
            and float(value) != float(old.get(name, value))}


def refresh_scene_state(state, data=None, actions=None):
    """Maintain one compact, authoritative description of the live scene."""
    data = data if isinstance(data, dict) else {}
    narrative = ai_text(data.get("narrative"))
    updates = data.get("updates") if isinstance(data.get("updates"), list) else []
    narrative_blob = " ".join([narrative, *[ai_text(row.get("narrative")) for row in updates if isinstance(row, dict)]])
    location = ai_text(state.get("location")) or "Unknown"
    details = (state.get("location_details") or {}).get(location, {})
    details = details if isinstance(details, dict) else {}
    present = []
    previous_scene = state.get("scene_state") if isinstance(state.get("scene_state"), dict) else {}
    previous_present = previous_scene.get("present", []) if previous_scene.get("location") == location else []
    nearby = []
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict) or str(memory.get("status", "active")).lower() in {"dead", "deceased", "missing", "absent"}:
            continue
        same_place = ai_text(memory.get("last_known_location")).casefold() == location.casefold()
        named_now = bool(name and re.search(rf"(?<!\w){re.escape(str(name))}(?!\w)", narrative_blob, re.I))
        # Discussing a distant person, or sharing a whole city, is not witnessing
        # this scene. Keep nearby people available without granting them secrets.
        reported = bool(re.search(rf"\b(?:about|of|from|regarding)\s+{re.escape(str(name))}\b", narrative_blob, re.I))
        if same_place:
            nearby.append(str(name))
        if (same_place and named_now and not reported) or (str(name) in previous_present and same_place):
            present.append(str(name))
    for row in state.get("companions", []) or []:
        name = ai_text(row.get("name") if isinstance(row, dict) else row)
        if isinstance(row, dict) and (row.get("status") in {"dead", "deceased", "away", "absent"} or
                                     (row.get("location") and row.get("location") != location)):
            continue
        if name and name not in present:
            present.append(name)
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
    if combat.get("active") and ai_text(enemy.get("name")) and ai_text(enemy.get("name")) not in present:
        present.append(ai_text(enemy.get("name")))
    questions = re.findall(r"([^.!?]{3,220}\?)", narrative_blob)
    direction = state.get("campaign_direction") if isinstance(state.get("campaign_direction"), dict) else {}
    active_goals = [row for row in state.get("action_goals", [])
                    if isinstance(row, dict) and row.get("status") == "active"]
    objective = (ai_text(active_goals[-1].get("condition")) if active_goals else
                 ai_text(direction.get("primary_goal") or direction.get("current_goal")))
    row = {
        "turn": int(state.get("turn", 0) or 0), "location": location,
        "sublocation": ai_text(details.get("sublocation") or details.get("setting")),
        "indoors": details.get("indoors"), "activity": ai_text(details.get("activity") or state.get("current_activity")),
        "weather": ai_text(state.get("weather")), "present": present[:16],
        "nearby_not_confirmed_present": [name for name in nearby if name not in present][:16],
        "immediate_danger": (ai_text(enemy.get("name")) or "Active combat") if combat.get("active") else
                            ai_text((state.get("danger_scenario") or {}).get("summary")),
        "unresolved_question": ai_text(questions[-1]) if questions else "",
        "current_objective": objective[:400],
        "last_player_input": "; ".join(ai_text(item) for item in actions or [] if ai_text(item))[:700],
    }
    state["scene_state"] = _prune(row)
    history = state.setdefault("scene_history", [])
    signature = (row["location"], tuple(row["present"]), row.get("immediate_danger", ""), row.get("unresolved_question", ""))
    previous = history[-1].get("signature") if history and isinstance(history[-1], dict) else None
    if signature != tuple(previous) if isinstance(previous, list) else signature != previous:
        history.append({"turn": row["turn"], "signature": list(signature), "scene": copy.deepcopy(state["scene_state"])})
        state["scene_history"] = history[-40:]
    return copy.deepcopy(state["scene_state"])


def normalize_outcome_scale(before, state, data, elapsed_minutes=5):
    """Record whether the prose's claimed magnitude matches durable mechanics."""
    narrative = " ".join([ai_text((data or {}).get("narrative")), *[
        ai_text(row.get("narrative")) for row in (data or {}).get("updates", []) if isinstance(row, dict)
    ]])
    claimed = "routine"
    for label, pattern in _OUTCOME_SCALE_PATTERNS:
        if pattern.search(narrative):
            claimed = label
            break
    stat_delta = _numeric_delta(before, state, "stats")
    level_delta = int(state.get("level", 0) or 0) - int(before.get("level", 0) or 0)
    xp_delta = int(state.get("xp", 0) or 0) - int(before.get("xp", 0) or 0)
    new_skills = sorted(set(state.get("skills", {})) - set(before.get("skills", {})))
    old_titles = {_item_name(item).casefold() for item in before.get("titles", [])}
    new_titles = [_item_name(item) for item in state.get("titles", []) if _item_name(item).casefold() not in old_titles]
    form_changed = ((state.get("portrait_identity") or {}).get("active_form") !=
                    (before.get("portrait_identity") or {}).get("active_form"))
    magnitude = max([abs(value) for value in stat_delta.values()] or [0])
    mechanical = ("transformative" if form_changed or level_delta >= 10 or magnitude >= 100 else
                  "major" if level_delta >= 3 or magnitude >= 25 or len(new_skills) >= 2 else
                  "noticeable" if level_delta or xp_delta or magnitude or new_skills or new_titles else "routine")
    ranks = {"routine": 0, "noticeable": 1, "major": 2, "transformative": 3}
    aligned = ranks[claimed] <= ranks[mechanical] + (1 if claimed == "noticeable" else 0)
    result = {"turn": int(state.get("turn", 0) or 0), "claimed": claimed, "mechanical": mechanical,
              "aligned": aligned, "elapsed_minutes": int(elapsed_minutes or 0),
              "stat_changes": stat_delta, "level_change": level_delta, "xp_change": xp_delta,
              "new_skills": new_skills[:12], "new_titles": new_titles[:12], "form_changed": bool(form_changed)}
    state["last_outcome_scale"] = _prune(result)
    ledger = state.setdefault("outcome_scale_ledger", [])
    ledger.append(copy.deepcopy(state["last_outcome_scale"])); state["outcome_scale_ledger"] = ledger[-120:]
    if not aligned:
        state.setdefault("simulation_validation", []).append({
            "turn": result["turn"], "area": "outcome_scale",
            "warnings": [f"Narrative claimed a {claimed} result but durable mechanics recorded only a {mechanical} change."],
        })
        state["simulation_validation"] = state["simulation_validation"][-100:]
    return result


def reconcile_commitments_and_consequences(state, data, elapsed_minutes=0):
    """Structure promises/debts and queue consequences without another model call."""
    data = data if isinstance(data, dict) else {}
    turn, day = int(state.get("turn", 0) or 0), int(state.get("canon_day", 0) or 0)
    obligations = state.setdefault("obligation_ledger", [])
    authored = data.get("commitment_updates") if isinstance(data.get("commitment_updates"), list) else []
    for raw in authored[:24]:
        if not isinstance(raw, dict) or not ai_text(raw.get("promise") or raw.get("text")):
            continue
        text_value = ai_text(raw.get("promise") or raw.get("text"))[:500]
        key = hashlib.sha256("|".join((ai_text(raw.get("owner") or ""), ai_text(raw.get("owed_to") or ""), text_value)).casefold().encode("utf-8")).hexdigest()[:16]
        existing = next((row for row in obligations if isinstance(row, dict) and row.get("id") == key), None)
        row = existing or {"id": key, "created_turn": turn}
        row.update({"owner": ai_text(raw.get("owner") or "") or "Unspecified", "owed_to": ai_text(raw.get("owed_to") or "") or "Unspecified",
                    "text": text_value, "due_canon_day": raw.get("due_canon_day"),
                    "trigger": ai_text(raw.get("trigger") or ""), "status": ai_text(raw.get("status") or "") or "active",
                    "consequence": ai_text(raw.get("consequence") or ""), "last_updated_turn": turn})
        if existing is None: obligations.append(row)
    # Legacy promises remain useful; normalize them into the ledger once.
    for raw in (state.get("narrative_memory") or {}).get("promises", [])[-30:]:
        text_value = ai_text(raw.get("text") if isinstance(raw, dict) else raw)
        if not text_value: continue
        key = hashlib.sha256(("legacy|" + text_value.casefold()).encode("utf-8")).hexdigest()[:16]
        if not any(isinstance(row, dict) and row.get("id") == key for row in obligations):
            obligations.append({"id": key, "owner": "Unspecified", "owed_to": "Unspecified", "text": text_value[:500],
                                "status": (raw.get("status", "active") if isinstance(raw, dict) else "active"),
                                "created_turn": int(raw.get("turn", turn) if isinstance(raw, dict) else turn), "last_updated_turn": turn})
    for row in obligations:
        if not isinstance(row, dict) or row.get("status", "active") != "active": continue
        try: due = int(row.get("due_canon_day"))
        except (TypeError, ValueError): continue
        if due <= day: row["status"] = "due"
    state["obligation_ledger"] = obligations[-160:]

    queue = state.setdefault("delayed_consequences", [])
    authored_delayed = data.get("delayed_consequences") if isinstance(data.get("delayed_consequences"), list) else []
    for raw in authored_delayed[:24]:
        if not isinstance(raw, dict) or not ai_text(raw.get("effect") or raw.get("text")): continue
        effect = ai_text(raw.get("effect") or raw.get("text"))[:600]
        key = hashlib.sha256("|".join((effect, ai_text(raw.get("trigger") or ""), str(raw.get("due_canon_day") or ""))).casefold().encode("utf-8")).hexdigest()[:16]
        if any(isinstance(row, dict) and row.get("id") == key for row in queue): continue
        queue.append({"id": key, "effect": effect, "source": ai_text(raw.get("source") or "") or "Narrative consequence",
                      "horizon": ai_text(raw.get("horizon") or "") or "later", "due_canon_day": raw.get("due_canon_day"),
                      "trigger": ai_text(raw.get("trigger") or ""), "status": "pending", "created_turn": turn})
    for row in queue:
        if not isinstance(row, dict) or row.get("status", "pending") != "pending": continue
        try: due = int(row.get("due_canon_day"))
        except (TypeError, ValueError): continue
        if due <= day: row["status"], row["became_due_turn"] = "due", turn
    state["delayed_consequences"] = queue[-160:]
    return {"active_obligations": sum(row.get("status") in {"active", "due"} for row in obligations if isinstance(row, dict)),
            "pending_consequences": sum(row.get("status") in {"pending", "due"} for row in queue if isinstance(row, dict))}


def refresh_canon_divergence_impacts(state):
    from simulation_integrity import canon_dependency_graph
    graph = canon_dependency_graph(state)
    affected = [copy.deepcopy(row) for row in graph.get("events", [])
                if row.get("status") in {"altered", "delayed", "impossible", "replaced"}]
    state["canon_divergence_impacts"] = {"turn": int(state.get("turn", 0) or 0),
                                          "counts": copy.deepcopy(graph.get("counts", {})),
                                          "affected_events": affected[:80]}
    return copy.deepcopy(state["canon_divergence_impacts"])


def record_pacing_beat(state, data, actions=None):
    text_value = " ".join([" ".join(ai_text(x) for x in actions or []), ai_text((data or {}).get("narrative")),
                           " ".join(ai_text(row.get("narrative")) for row in (data or {}).get("updates", []) if isinstance(row, dict))]).lower()
    categories = (("combat", r"\b(?:fight|attack|battle|combat|duel|wound|defeat)\b"),
                  ("training", r"\b(?:train|practice|master|study|exercise)\b"),
                  ("social", r"\b(?:talk|ask|negot|convince|relationship|promise|meeting)\b"),
                  ("exploration", r"\b(?:travel|explore|discover|arrive|investigat|search)\b"),
                  ("politics", r"\b(?:faction|treaty|alliance|ruler|council|policy|territory)\b"),
                  ("recovery", r"\b(?:rest|recover|heal|downtime|relax)\b"))
    kind = next((label for label, pattern in categories if re.search(pattern, text_value, re.I)), "story")
    profile = state.setdefault("pacing_profile", {"recent_beats": [], "counts": {}, "last_guidance": ""})
    profile.setdefault("recent_beats", []).append({"turn": int(state.get("turn", 0) or 0), "kind": kind})
    profile["recent_beats"] = profile["recent_beats"][-16:]
    profile["counts"] = {label: sum(row.get("kind") == label for row in profile["recent_beats"])
                         for label in {row.get("kind") for row in profile["recent_beats"]}}
    return kind


def learn_player_style(state):
    """Infer only from explicit positive ratings and chosen presentation settings."""
    rated = state.get("rated_good_turns") or []
    outcomes = [ai_text(row.get("outcome")) for row in rated if isinstance(row, dict)]
    actions = [ai_text(row.get("action")) for row in rated if isinstance(row, dict)]
    avg_words = round(sum(len(text.split()) for text in outcomes) / max(1, len(outcomes)))
    blob = " ".join(actions).lower()
    preferences = []
    for label, pattern in (("combat", r"\b(?:fight|attack|battle|duel)\b"), ("growth", r"\b(?:train|learn|master|grow)\b"),
                           ("social", r"\b(?:talk|ask|persuad|relationship)\b"), ("strategy", r"\b(?:plan|order|politic|faction|rule)\b"),
                           ("exploration", r"\b(?:travel|explore|discover|search)\b")):
        if re.search(pattern, blob): preferences.append(label)
    profile = {"sample_count": len(rated), "preferred_detail": "detailed" if avg_words >= 110 else "balanced" if avg_words >= 45 else "concise",
               "preferred_beats": preferences[:5], "approved_average_words": avg_words,
               "rule": "A soft presentation preference only; never changes facts, difficulty, NPC autonomy, or outcomes."}
    state["player_style_profile"] = profile
    return copy.deepcopy(profile)


_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "did", "do", "does", "for", "from",
    "had", "has", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "that", "the", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "with", "you", "your",
}


def _terms(value):
    return [word for word in re.findall(r"[a-z0-9'-]+", ai_text(value).lower())
            if len(word) > 1 and word not in _STOP]


def _score(query_terms, *values):
    blob = " ".join(ai_text(value).lower() for value in values)
    return sum(1 for term in query_terms if term in blob)


def _compact_memory(row):
    if not isinstance(row, dict):
        return {"text": ai_text(row)[:500]}
    return {key: copy.deepcopy(row.get(key)) for key in
            ("text", "source", "status", "turn", "first_turn", "last_turn", "canon_day")
            if row.get(key) not in (None, "", [], {})}


def build_grounding_packet(state, query="", purpose="moment", max_items=18):
    """Return a bounded, source-ranked set of facts every AI role must obey."""
    state = state if isinstance(state, dict) else {}
    terms = _terms(query)
    from gm_refinements import connected_memory
    connections = connected_memory(state, query)
    special = state.get("special") if isinstance(state.get("special"), dict) else {}
    active_form = ((state.get("portrait_identity") or {}).get("active_form")
                   if isinstance(state.get("portrait_identity"), dict) else {}) or {}
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    top_stats = sorted(((name, value) for name, value in stats.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)),
                       key=lambda pair: (-pair[1], pair[0]))[:8]
    packet = {
        "source_priority": [
            "player corrections and current mechanical state",
            "confirmed campaign consequences and recent resolutions",
            "verified memory archive and chapter summaries",
            "opening-era canon only where the campaign has not diverged",
        ],
        "current_truth": {
            "name": state.get("name"), "world": state.get("world"),
            "turn": state.get("turn", 0), "time": state.get("world_time"),
            "canon_day": state.get("canon_day"), "location": state.get("location"),
            "position": state.get("position"), "alive": state.get("alive", True),
            "hp": [state.get("hp"), state.get("hp_max")],
            "resource": [state.get("resource_name"), state.get("resource"), state.get("resource_max")],
            "top_stats": top_stats, "affiliations": copy.deepcopy(state.get("affiliations", []))[:12],
            "active_form": copy.deepcopy(active_form),
            "combat": copy.deepcopy(state.get("combat", {}))
            if isinstance(state.get("combat"), dict) and state.get("combat", {}).get("active") else {},
        },
        "locked_facts": copy.deepcopy((state.get("authoritative_corrections") or [])[-12:]),
        "relevant_people": [], "relevant_factions": [], "commitments": [],
        "connected_memories": connections["records"],
        "verified_history": [], "consistency_rule": (
            "Answer and narrate from this packet first. Never replace a current campaign fact with stock canon. "
            "If two facts truly conflict, name the conflict instead of silently choosing one."
        ),
    }
    packet["live_scene"] = copy.deepcopy(state.get("scene_state", {})) if isinstance(state.get("scene_state"), dict) else {}
    tiers = state.get("memory_tiers") if isinstance(state.get("memory_tiers"), dict) else {}
    packet["memory_tiers"] = {
        "hot": copy.deepcopy((tiers.get("hot") or [])[-8:]),
        "warm": copy.deepcopy((tiers.get("warm") or [])[-5:]),
        "cold": copy.deepcopy((tiers.get("cold") or [])[-5:]),
    }
    obligations = state.get("obligation_ledger") if isinstance(state.get("obligation_ledger"), list) else []
    consequences = state.get("delayed_consequences") if isinstance(state.get("delayed_consequences"), list) else []
    packet["due_obligations"] = [copy.deepcopy(row) for row in obligations
                                  if isinstance(row, dict) and row.get("status") in {"active", "due"}][-10:]
    packet["due_consequences"] = [copy.deepcopy(row) for row in consequences
                                   if isinstance(row, dict) and row.get("status") == "due"][-8:]
    divergence_impacts = state.get("canon_divergence_impacts") if isinstance(state.get("canon_divergence_impacts"), dict) else {}
    packet["divergence_impacts"] = copy.deepcopy(divergence_impacts.get("affected_events", []))[:8]
    packet["outcome_scale"] = copy.deepcopy(state.get("last_outcome_scale", {}))
    packet["player_style"] = copy.deepcopy(state.get("player_style_profile", {}))
    packet["companion_autonomy"] = {
        name: {"progress": row.get("progress"), "directives": copy.deepcopy(row.get("directives", [])),
               "latest": copy.deepcopy((row.get("history") or [])[-1:])}
        for name, row in list((state.get("companion_autonomy") or {}).items())[:8] if isinstance(row, dict)
    }
    packet["npc_development"] = {
        name: {"progress": row.get("progress"), "basis": row.get("basis"),
               "latest": copy.deepcopy((row.get("history") or [])[-1:])}
        for name, row in list((state.get("npc_development") or {}).items())[:8] if isinstance(row, dict)
    }
    packet["ability_evolution"] = {
        name: {"applications": copy.deepcopy((row.get("applications") or [])[-8:]),
               "latest": copy.deepcopy((row.get("history") or [])[-3:])}
        for name, row in list((state.get("ability_evolution") or {}).items())[:12] if isinstance(row, dict)
    }

    people = []
    companion_rows = state.get("companions") if isinstance(state.get("companions"), list) else []
    companions = {ai_text(row.get("name") if isinstance(row, dict) else row).lower()
                  for row in companion_rows}
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    for name, memory in memories.items():
        if not isinstance(memory, dict):
            continue
        priority = _score(terms, name, memory.get("goal"), memory.get("immediate_goal"), memory.get("last_known_location"))
        if name in connections["names"]: priority += 20
        if ai_text(name).lower() in companions: priority += 8
        if memory.get("nemesis"): priority += 6
        if memory.get("last_known_location") == state.get("location"): priority += 5
        if not terms and (priority or memory.get("recurring")): priority += 1
        if priority:
            people.append((priority, {
                "name": name, "status": memory.get("status", "active"),
                "location": memory.get("last_known_location", "Unknown"),
                "attitude": memory.get("attitude", "Unknown"),
                "affiliation": memory.get("affiliation") or memory.get("faction"),
                "goal": memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"),
                "power": memory.get("power_score", memory.get("power")),
                "nemesis": bool(memory.get("nemesis")), "companion": ai_text(name).lower() in companions,
                "recent_reasons": copy.deepcopy((memory.get("chain") or [])[-3:]),
            }))
    people.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
    packet["relevant_people"] = [row for _, row in people[:8]]
    names = [row["name"] for row in packet["relevant_people"]]
    packet["current_fact_view"] = current_fact_view(state, names)
    packet["npc_decision_profiles"] = decision_profiles(state, names)

    affiliation_names = _affiliation_names(state)
    factions = state.get("factions") if isinstance(state.get("factions"), dict) else {}
    faction_clocks = state.get("faction_clocks") if isinstance(state.get("faction_clocks"), dict) else {}
    reputation = state.get("reputation") if isinstance(state.get("reputation"), dict) else {}
    faction_names = set(factions) | set(faction_clocks)
    faction_names |= affiliation_names
    faction_rows = []
    for name in faction_names:
        clock = faction_clocks.get(name, {})
        if not isinstance(clock, dict): clock = {}
        priority = _score(terms, name, clock.get("strategic_goal"), clock.get("immediate_goal"), clock.get("goal"))
        if name in affiliation_names: priority += 8
        if clock.get("opponent") or clock.get("status") == "turning_point": priority += 5
        if not terms and priority == 0: priority = 1
        if priority:
            faction_rows.append((priority, {
                "name": name, "standing": reputation.get(name),
                "status": clock.get("status", "active"),
                "strategic_goal": clock.get("strategic_goal") or clock.get("core_ambition") or clock.get("goal"),
                "current_operation": copy.deepcopy(next((op for op in clock.get("operations", [])
                    if isinstance(op, dict) and op.get("status") == "active"), {})),
                "alliances": copy.deepcopy(clock.get("alliances", [])),
                "rivals": copy.deepcopy(clock.get("rivals", [])),
                "leader": copy.deepcopy(clock.get("leadership", {})),
            }))
    faction_rows.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
    packet["relevant_factions"] = [row for _, row in faction_rows[:6]]

    commitments = []
    standing_intents = state.get("standing_intents") if isinstance(state.get("standing_intents"), list) else []
    for row in standing_intents[-12:]:
        if isinstance(row, dict) and row.get("status", "active") == "active":
            commitments.append({"kind": "standing intent", "text": row.get("outcome") or row.get("directive") or row.get("text"), "owner": row.get("responsible")})
    narrative_memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    promises = narrative_memory.get("promises") if isinstance(narrative_memory.get("promises"), list) else []
    for row in promises[-8:]:
        if not isinstance(row, dict) or row.get("status", "active") == "active":
            commitments.append({"kind": "promise", **_compact_memory(row)})
    quests = state.get("quests") if isinstance(state.get("quests"), list) else []
    for quest in quests:
        if isinstance(quest, dict) and str(quest.get("status", "active")).lower() not in {"complete", "completed", "resolved", "failed", "archived"}:
            commitments.append({"kind": "quest", "name": quest.get("name"), "next": quest.get("next_hint") or quest.get("first_step")})
    commitments.sort(key=lambda row: -_score(terms, row))
    packet["commitments"] = commitments[:12]

    history = []
    pools = [
        ("recent resolution", (state.get("resolution_ledger") or [])[-8:]),
        ("causal result", (state.get("causality_ledger") or [])[-12:]),
        ("confirmed consequence", (state.get("consequence_ledger") or [])[-10:]),
        ("verified archive", (state.get("verified_memory_archive") or [])[-5:]),
        ("chapter", (state.get("chapter_summaries") or [])[-5:]),
        ("campaign", (state.get("campaign_canon") or [])[-16:]),
    ]
    for kind, rows in pools:
        for row in rows:
            if not isinstance(row, dict): continue
            title = row.get("title") or row.get("action") or row.get("kind") or (row.get("actions") or [""])[0] or kind
            body = (row.get("summary") or row.get("outcome") or row.get("direct_result") or row.get("reason")
                    or row.get("narrative") or row.get("evidence") or row.get("text"))
            score = _score(terms, title, body)
            if not terms and kind in {"recent resolution", "causal result", "confirmed consequence", "campaign"}: score = 1
            if score:
                history.append((score, int(row.get("turn") or (row.get("turns") or [0])[-1] or 0), {
                    "source": kind, "title": ai_text(title)[:180], "fact": ai_text(body)[:700],
                    "turn": row.get("turn") or (row.get("turns") or [None])[-1],
                }))
    history.sort(key=lambda item: (-item[0], -item[1]))
    packet["verified_history"] = [row for _, _, row in history[:max(4, min(24, int(max_items or 18)))]]
    return _prune(packet)


def _prune(value):
    if isinstance(value, dict):
        if {"subject", "field", "value"}.issubset(value):
            # An empty current affiliation or removed role is meaningful;
            # dropping its value would let an old summary fill it back in.
            return copy.deepcopy(value)
        return {key: _prune(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_prune(item) for item in value if item not in (None, "", [], {})]
    return value


def _item_name(item):
    return ai_text(item.get("name") or item.get("title")) if isinstance(item, dict) else ai_text(item)


def _affiliation_names(state):
    names = set()
    for row in state.get("affiliations", []) or []:
        name = row.get("faction") if isinstance(row, dict) else row
        if ai_text(name):
            names.add(ai_text(name))
    return names


def _quest_by_name(state, name):
    wanted = ai_text(name).casefold()
    return next((quest for quest in state.get("quests", []) if isinstance(quest, dict)
                 and ai_text(quest.get("name") or quest.get("title")).casefold() == wanted), None)


def reconcile_narrated_consequences(before, state, data, actions=None, elapsed_minutes=5):
    """Apply safe omitted consequences and record every claim-to-state check.

    The narrator's consequence_manifest is preferred.  Structured event rows
    are also accepted as a backwards-compatible source.  Ambiguous mechanical
    claims are flagged rather than guessed.
    """
    data = data if isinstance(data, dict) else {}
    manifest = copy.deepcopy(data.get("consequence_manifest")) if isinstance(data.get("consequence_manifest"), list) else []
    for event in data.get("events", []) if isinstance(data.get("events"), list) else []:
        if not isinstance(event, dict): continue
        kind = ai_text(event.get("type")).lower()
        if kind not in {"skill", "title", "item", "loot", "quest", "location", "reputation", "companion", "injury", "death"}:
            continue
        target = event.get("target") or event.get("name")
        if target:
            manifest.append({"kind": kind, "target": target, "change": event.get("change") or event.get("status"), "evidence": event.get("message", "")})
    turn = int(state.get("turn", 0) or 0) + 1
    ledger = state.setdefault("consequence_ledger", [])
    rows, notes = [], []
    for raw in manifest[:40]:
        if not isinstance(raw, dict): continue
        kind = ai_text(raw.get("kind") or raw.get("type")).lower().replace(" ", "_")
        target = ai_text(raw.get("target") or raw.get("name") or raw.get("subject"))[:180]
        change = ai_text(raw.get("change") or raw.get("status") or raw.get("result"))[:120]
        # Attempting/planning a gain is not ownership. Reconciliation must never
        # turn a refused purchase or failed lesson into a reward.
        if change.lower() in {"attempted", "failed", "refused", "planned", "possible", "rumored", "rumoured", "suspected", "unconfirmed", "pending", "offered", "invited"}:
            continue
        evidence = ai_text(raw.get("evidence") or raw.get("reason") or data.get("narrative"))[:500]
        subject = ai_text(raw.get("subject") or raw.get("owner") or "player").strip()
        player_subject = subject.casefold() in {"player", "the player", "you", ai_text(state.get("name")).casefold()}
        applied, status, reason = False, "verified", "Already reflected in state"
        removing = change.lower() in {"lost", "removed", "spent", "consumed", "destroyed", "gave away", "forgotten", "cured", "healed", "cleared"}
        if not player_subject and kind != "death":
            memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
            actor = next((name for name in memories if name.casefold() == subject.casefold()), None)
            details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
            if kind == "skill" and actor and isinstance(memories[actor], dict) and (removing or details.get("effect") or details.get("description")):
                skills = memories[actor].setdefault("skills", {})
                if isinstance(skills, dict):
                    existing = next((n for n in skills if str(n).casefold() == target.casefold()), None)
                    if removing and existing is not None: del skills[existing]; applied = True
                    elif not removing and existing is None: skills[target] = copy.deepcopy(details); applied = True
                    reason = "Recorded ability on the named NPC, not the player"
                else: status, reason = "needs_detail", "NPC skill record requires review"
            else:
                status, reason = "needs_detail", "Non-player consequence needs an explicit NPC or organization update; never award it to the player"
        elif removing and target and kind in {"skill", "title", "condition", "injury"}:
            collection = {"skill": "skills", "title": "titles", "condition": "conditions", "injury": "conditions"}[kind]
            values = state.get(collection, {} if collection == "skills" else [])
            if isinstance(values, dict):
                state[collection] = {name: value for name, value in values.items() if str(name).casefold() != target.casefold()}
            else:
                state[collection] = [value for value in values or [] if _item_name(value).casefold() != target.casefold()]
            applied = values != state[collection]; reason = "Applied explicit loss or recovery"
        elif kind == "title" and target:
            names = {ai_text(item.get("name") or item.get("title") if isinstance(item, dict) else item).casefold() for item in state.get("titles", [])}
            if target.casefold() not in names:
                state.setdefault("titles", []).append(target); applied = True; reason = "Added omitted earned title"
        elif kind in {"item", "loot"} and target:
            names = {_item_name(item).casefold() for item in state.get("inventory", [])}
            removing = re.search(r"\b(?:lost|removed|spent|consumed|destroyed|gave away)\b", change, re.I)
            if removing:
                old_len = len(state.get("inventory", [])); state["inventory"] = [item for item in state.get("inventory", []) if _item_name(item).casefold() != target.casefold()]
                applied = len(state["inventory"]) != old_len; reason = "Removed narrated item" if applied else "Item was not present"
                equipment = state.get("equipment")
                if isinstance(equipment, dict):
                    for slot, item in list(equipment.items()):
                        if _item_name(item).casefold() == target.casefold():
                            equipment[slot] = "None"; applied = True
            elif target.casefold() not in names:
                state.setdefault("inventory", []).append({"name": target, "description": ai_text(raw.get("description")) or "A notable item established by the Chronicle."})
                applied = True; reason = "Added omitted notable item"
        elif kind == "location" and target:
            if target not in state.setdefault("discovered_locations", []):
                state["discovered_locations"].append(target); applied = True
            if change.lower() in {"arrived", "moved", "travelled", "traveled", "relocated", "entered", "visited", "reached"} and state.get("location") != target:
                state["location"] = target
                applied = True; reason = "Synchronized narrated travel"
            else: reason = "Recorded a discovered place without inventing travel"
        elif kind == "quest" and target:
            quest = _quest_by_name(state, target)
            completed = change.lower() in {"complete", "completed", "resolved", "finished", "cleared"}
            if quest and completed and str(quest.get("status", "")).lower() not in {"complete", "completed", "resolved"}:
                quest["status"] = "Completed"; applied = True; reason = "Closed narrated quest"
            elif not quest and not completed:
                state.setdefault("quests", []).append({
                    "name": target, "status": "Active", "category": "personal",
                    "explanation": ai_text(raw.get("description")) or evidence or "A commitment established in the Chronicle.",
                    "current_knowledge": [], "clear_conditions": [], "first_step": ai_text(raw.get("next_step")),
                })
                applied = True; reason = "Added omitted narrative agenda"
        elif kind == "skill" and target:
            if target.casefold() not in {str(name).casefold() for name in (state.get("skills") or {})}:
                details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
                if details.get("effect") or details.get("description"):
                    state.setdefault("skills", {})[target] = copy.deepcopy(details); applied = True; reason = "Added omitted fully described skill"
                else:
                    status = "needs_detail"; reason = "Narrative claims a skill but supplies no mechanics; retained as a validation warning"
        elif kind in {"injury", "condition"} and target:
            names = {ai_text(item.get("name") if isinstance(item, dict) else item).casefold() for item in state.get("conditions", [])}
            if target.casefold() not in names:
                state.setdefault("conditions", []).append({"name": target, "description": evidence or change, "source": "Chronicle"})
                applied = True; reason = "Applied omitted condition"
        elif kind == "death" and target and change.lower() in {"died", "dead", "killed", "deceased"} and evidence:
            if target.casefold() in {ai_text(state.get("name")).casefold(), "player", "the player"}:
                if state.get("alive", True): state["alive"], state["hp"], applied, reason = False, 0, True, "Synchronized narrated player death"
            else:
                from narrative_state import record_npc_death
                applied = record_npc_death(state, target, evidence)
                status, reason = ("verified", "Synchronized confirmed NPC death") if applied else ("recorded", "No matching established NPC; no identity invented")
        else:
            status = "recorded"; reason = "Claim retained for grounding; no safe deterministic mutation"
        row = {"turn": turn, "kind": kind or "consequence", "target": target, "change": change,
               "evidence": evidence, "status": status, "applied_repair": applied, "reason": reason,
               "elapsed_minutes": int(elapsed_minutes or 0), "subject": subject}
        rows.append(row)
        if status == "needs_detail": notes.append(f"Consequence needs review: {target} — {reason}")

    # Always record exact mechanical deltas, even when the narrator supplied
    # no manifest.  This becomes the next turn's verified evidence.
    for key in ("location", "level", "xp", "hp", "resource"):
        if before.get(key) != state.get(key):
            rows.append({"turn": turn, "kind": key, "target": key, "change": f"{before.get(key)} → {state.get(key)}",
                         "evidence": "Authoritative state delta", "status": "verified", "applied_repair": False,
                         "reason": "Mechanical change confirmed", "elapsed_minutes": int(elapsed_minutes or 0)})
    for collection, kind in (("skills", "skill"), ("titles", "title")):
        old = before.get(collection, {})
        new = state.get(collection, {})
        old_names = set(old) if isinstance(old, dict) else {_item_name(item).casefold() for item in old or []}
        new_names = set(new) if isinstance(new, dict) else {_item_name(item).casefold() for item in new or []}
        for name in new_names - old_names:
            rows.append({"turn": turn, "kind": kind, "target": ai_text(name), "change": "gained",
                         "evidence": "Authoritative state delta", "status": "verified", "applied_repair": False,
                         "reason": "Mechanical change confirmed", "elapsed_minutes": int(elapsed_minutes or 0)})
    seen = set()
    for row in rows:
        key = (row["kind"], row["target"].casefold(), row["change"].casefold())
        if key in seen: continue
        seen.add(key); ledger.append(row)
    state["consequence_ledger"] = ledger[-240:]
    record_fact_changes(before, state)
    if notes:
        state.setdefault("simulation_validation", []).append({"turn": turn, "area": "consequence_reconciliation", "warnings": notes[:12]})
        state["simulation_validation"] = state["simulation_validation"][-100:]
    return {"checked": len(rows), "repairs": sum(bool(row.get("applied_repair")) for row in rows), "warnings": notes}


def _dedupe_memory_rows(rows):
    merged = {}
    for raw in rows if isinstance(rows, list) else []:
        row = copy.deepcopy(raw) if isinstance(raw, dict) else {"text": ai_text(raw)}
        text = re.sub(r"\s+", " ", ai_text(row.get("text") or row.get("summary") or row.get("fact"))).strip()[:700]
        if not text: continue
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        prior = merged.get(key)
        if prior:
            prior["first_turn"] = min(int(prior.get("first_turn", prior.get("turn", 0)) or 0), int(row.get("turn", 0) or 0))
            prior["last_turn"] = max(int(prior.get("last_turn", prior.get("turn", 0)) or 0), int(row.get("turn", 0) or 0))
            if row.get("status") not in (None, ""): prior["status"] = row["status"]
            continue
        row["text"], row["key"] = text, key
        row["first_turn"] = int(row.get("first_turn", row.get("turn", 0)) or 0)
        row["last_turn"] = int(row.get("last_turn", row.get("turn", 0)) or 0)
        merged[key] = row
    return sorted(merged.values(), key=lambda row: int(row.get("last_turn", 0) or 0))


def consolidate_long_campaign_memory(state, force=False):
    """Archive verified old turns and deduplicate durable memory locally."""
    turn = int(state.get("turn", 0) or 0)
    meta = state.setdefault("memory_consolidation", {"last_turn": 0, "archived_through_turn": 0, "runs": 0})
    canon = state.get("campaign_canon") if isinstance(state.get("campaign_canon"), list) else []
    memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    oversized = len(canon) > 80 or any(len(rows) > 90 for rows in memory.values() if isinstance(rows, list))
    if not force and not oversized and turn - int(meta.get("last_turn", 0) or 0) < 12:
        return None
    for category, rows in list(memory.items()):
        if isinstance(rows, list): memory[category] = _dedupe_memory_rows(rows)[-100:]
    state["narrative_memory"] = memory

    archive = state.setdefault("verified_memory_archive", [])
    cutoff = max(0, turn - 50)
    already = int(meta.get("archived_through_turn", 0) or 0)
    candidates = [row for row in canon if isinstance(row, dict) and already < int(row.get("turn", 0) or 0) <= cutoff]
    new_archive = None
    if candidates:
        summary_parts = [ai_text(row.get("outcome") or row.get("text")) for row in candidates if ai_text(row.get("outcome") or row.get("text"))]
        actions = [ai_text(row.get("action")) for row in candidates if ai_text(row.get("action"))]
        payload = json.dumps(candidates, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        new_archive = {
            "title": f"Verified turns {candidates[0].get('turn')}–{candidates[-1].get('turn')}",
            "turns": [candidates[0].get("turn"), candidates[-1].get("turn")],
            "canon_days": [candidates[0].get("canon_day"), candidates[-1].get("canon_day")],
            "summary": " ".join(summary_parts)[:5000], "key_actions": actions[-24:],
            "source_digest": hashlib.sha256(payload).hexdigest(), "verified": True,
        }
        archive.append(new_archive); state["verified_memory_archive"] = archive[-80:]
        meta["archived_through_turn"] = int(candidates[-1].get("turn", already) or already)
        # The archive is now the durable searchable copy. Keep a generous
        # recent tail in campaign_canon for the live Chronicle context.
        state["campaign_canon"] = [row for row in canon if not isinstance(row, dict) or int(row.get("turn", 0) or 0) > cutoff]
    meta["last_turn"], meta["runs"] = turn, int(meta.get("runs", 0) or 0) + 1
    meta["last_result"] = {"turn": turn, "archived": len(candidates), "memory_counts": {key: len(value) for key, value in memory.items() if isinstance(value, list)}}
    return copy.deepcopy(new_archive or meta["last_result"])
