"""Bounded evidence, current-fact views and semantic turn checks (no AI calls).

The model still judges the fiction. These checks cover verifiable contracts;
they do not claim to prove arbitrary natural-language prose correct.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from util import ai_text
from gm_refinements import (commanded_people, connected_memory, relevant_evidence,
                            record_settled_stories, closure_issues, REFINEMENT_RULE)


def mapping(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) else []


def text(value, limit=350):
    return ai_text(value).strip()[:limit]


def number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def compact_values(value, limit=6):
    if isinstance(value, list):
        return [text(row) for row in value[:limit]]
    return [text(value)] if value else []


def ref_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


def present_people(state):
    memories = mapping(state.get("npc_memories"))
    scene = mapping(state.get("scene_state"))
    if scene.get("location") and scene["location"] != state.get("location"):
        return []
    return [text(row.get("name") if isinstance(row, dict) else row) for row in rows(scene.get("present"))
            if text(mapping(memories.get(text(row.get("name") if isinstance(row, dict) else row))).get("status")).lower()
            not in {"dead", "deceased", "missing", "absent"}][:16]


def fact_values(state):
    """Current structured values are authoritative; summaries remain history."""
    result = {}
    for key in ("position", "location", "alive", "affiliations"):
        if key in state:
            result[("player", key)] = state[key]
    for name, memory in mapping(state.get("npc_memories")).items():
        for key in ("role", "rank", "status", "affiliation", "faction", "attitude", "last_known_location", "immediate_goal"):
            if key in mapping(memory):
                result[(str(name), key)] = memory[key]
    for name, value in mapping(state.get("relationships")).items():
        result[(str(name), "relationship")] = value
    return result


def record_fact_changes(before, state):
    record_settled_stories(before, state)
    old, current = fact_values(before), fact_values(state)
    history = rows(state.get("fact_history"))
    for (subject, field), value in current.items():
        if (subject, field) in old and old[(subject, field)] != value:
            row = {"subject": subject, "field": field, "previous": copy.deepcopy(old[(subject, field)]),
                   "current": copy.deepcopy(value), "turn": max(number(state.get("turn")), number(before.get("turn")) + 1), "canon_day": state.get("canon_day"),
                   "source": "committed state change"}
            if not history or history[-1] != row:
                history.append(row)
    state["fact_history"] = history[-240:]


def current_fact_view(state, names):
    wanted = {str(name).casefold() for name in names} | {"player"}
    facts = [{"subject": subject, "field": field, "value": copy.deepcopy(value)}
             for (subject, field), value in fact_values(state).items() if subject.casefold() in wanted]
    history = [copy.deepcopy(row) for row in rows(state.get("fact_history"))
               if isinstance(row, dict) and text(row.get("subject")).casefold() in wanted][-12:]
    return {"current": facts[:72], "superseded_history": history,
            "rule": "Current fields override older summaries for the SAME subject and field. Previous values are historical, not current authority. Player corrections outrank both. Missing information is unknown, not proof of reversal."}


def decision_profiles(state, names):
    profiles = []
    for name in names[:8]:
        memory = mapping(mapping(state.get("npc_memories")).get(name))
        intention = mapping(mapping(state.get("npc_intentions")).get(name))
        profiles.append({
            "name": name, "current_goal": text(memory.get("immediate_goal") or intention.get("goal") or memory.get("goal")),
            "relationship": copy.deepcopy(mapping(state.get("relationships")).get(name, memory.get("attitude", "unknown"))),
            "loyalties": compact_values(memory.get("loyalties") or intention.get("loyalties")),
            "fears": compact_values(memory.get("fears") or intention.get("fears")),
            "temperament": text(memory.get("temperament") or memory.get("personality")),
            "nemesis": memory.get("nemesis") is True,
            "recent_experiences": copy.deepcopy(rows(memory.get("chain"))[-3:]),
            "beliefs": {key: copy.deepcopy(rows(mapping(memory.get("knowledge")).get(key))[-4:])
                        for key in ("confirmed", "heard", "suspected", "false_beliefs")},
            "rule": "Choose a response from this person's motives and actual knowledge. Gratitude, disagreement, silence and uncomplicated support are all valid. Do not turn every conversation into advice or a new task. False beliefs can motivate them but are not objective truth.",
        })
    return profiles


def command_contracts(state, query):
    """Use established command relationships, never mere friendship or power."""
    if not re.search(r"\b(?:order|command|instruct|tell|direct|assign|have|ask)\b|(?:^|:)\s*(?:please\s+)?(?:deliver|guard|escort|patrol|protect|carry|report)\b", query, re.I):
        return []
    from organizations import organization_commands, ensure_organizations
    organized = organization_commands(state, query)
    managed = {name for group in ensure_organizations(state).values() if isinstance(group, dict) for name in mapping(group.get("members"))}
    player = text(state.get("name")).casefold()
    known = copy.deepcopy(mapping(state.get("npc_memories")))
    for companion in rows(state.get("companions")):
        if isinstance(companion, dict) and companion.get("name"):
            name = text(companion["name"])
            known[name] = {**mapping(known.get(name)), **companion}
    contracts = []
    targets = set(commanded_people(state, query))
    for name, raw in known.items():
        row = mapping(raw)
        if name not in targets or name in managed:
            continue
        leader = text(row.get("reports_to") or row.get("commander") or row.get("leader")).casefold()
        role = text(row.get("role")).casefold()
        subordinate = row.get("subordinate") is True or leader in {player, "player", "the player"} - {""}
        subordinate = subordinate or bool(re.search(r"\b(?:subordinate|retainer|summon)\b", role))
        if subordinate:
            contracts.append({"actor": str(name), "order": query[:900], "basis": "established command relationship",
                              "default": "Execute the stated objective and constraints faithfully; ordinary method choices must not replace the objective.",
                              "exceptions": "Only an established conflict of loyalty, actual inability, unavailable resources, or genuine ambiguity warrants refusal, delay or clarification. Record the specific evidence; no automatic twist."})
    return list({row["actor"]: row for row in [*contracts, *organized]}.values())[:16]


def evidence_packet(state, query="", payload=None):
    """Stable references to pre-turn facts; never trust the proposed state patch."""
    payload = mapping(payload)
    now = number(state.get("canon_time_minutes"), number(state.get("canon_day")) * 1440)
    evidence = []
    present = present_people(state)
    for name in present:
        evidence.append({"id": "scene:" + ref_id(name, state.get("location")), "kind": "witness",
                         "actor": name, "fact": "Present in the live scene; perceives observable events only, not concealed thoughts or abilities."})
    memories = mapping(state.get("npc_memories"))
    connected = connected_memory(state, query)
    selected = sorted(memories, key=lambda name: (str(name).casefold() not in query.casefold(), name not in connected["names"], str(name) not in present, str(name)))
    for name in selected[:8]:
        knowledge = mapping(mapping(memories[name]).get("knowledge"))
        for field in ("loyalties", "limitations", "injuries", "conflicting_orders"):
            value = mapping(memories[name]).get(field)
            if value:
                evidence.append({"id": "motive:" + ref_id(name, field, value), "kind": field, "actor": name, "fact": text(value)})
        for bucket in ("confirmed", "heard", "suspected", "false_beliefs"):
            for raw in rows(knowledge.get(bucket))[-6:]:
                row = raw if isinstance(raw, dict) else {"fact": raw}
                if number(row.get("turn")) > number(state.get("turn")):
                    continue
                if number(row.get("available_at_minutes", row.get("delivered_at_minutes", now))) > now:
                    continue
                if row.get("canon_day") is not None and number(row["canon_day"]) > number(state.get("canon_day")):
                    continue
                fact = text(row.get("fact") or row.get("text"))
                if fact:
                    evidence.append({"id": "knowledge:" + ref_id(name, bucket, fact), "kind": bucket,
                                     "actor": name, "fact": fact, "source": text(row.get("source")), "turn": row.get("turn")})
    for index, roll in enumerate(rows(payload.get("dice_results")) or rows(payload.get("rolls")) or
                                 ([payload["dice_result"]] if isinstance(payload.get("dice_result"), dict) else [])):
        if isinstance(roll, dict) and roll.get("success") is False:
            evidence.append({"id": f"roll:{index}", "kind": "failed_check", "fact": text(roll.get("action") or roll.get("reason") or "Failed check")})
    # Established active threats/costs, not arbitrary proposed future setbacks.
    for field in ("conditions", "delayed_consequences", "obligation_ledger"):
        for raw in rows(state.get(field))[-10:]:
            row = raw if isinstance(raw, dict) else {"name": raw}
            if text(row.get("status")).lower() in {"resolved", "cancelled", "completed", "expired"}:
                continue
            fact = text(row.get("name") or row.get("effect") or row.get("description") or row.get("summary"))
            if fact:
                evidence.append({"id": "state:" + ref_id(field, raw), "kind": field, "fact": fact})
    # Keep local rolls/obstacles even when long-running NPCs know many facts.
    critical = [row for row in evidence if row.get("kind") not in {"confirmed", "heard", "suspected", "false_beliefs"}]
    knowledge_rows = [row for row in evidence if row not in critical]
    return (critical + knowledge_rows)[:80]


def pacing_packet(state, payload):
    assessment = mapping(payload.get("assessment"))
    return {"routine": "Accumulate routine care, practice and duties silently; summarize concrete progress once per activity, not once per day.",
            "spotlight": "Give distinct space to a relationship turning point, earned breakthrough, real world change or decision. Never invent one to fill a quota.",
            "stop": "Stop for an immediate consequential choice, committed danger, explicit player stop condition, or an applicable canon boundary. A routine milestone or report alone is not a hard stop.",
            "canon_boundary": copy.deepcopy(payload.get("canon_boundary") or assessment.get("canon_stop") or {}),
            "active_danger": bool(mapping(state.get("combat")).get("active"))}


CONSISTENCY_RULE = """
VERIFIABLE TURN CONTRACT:
- Respect prohibited and conditional clauses. Preserve raw player intent; resolve ambiguous pronouns from context rather than inventing a target.
- causal_outcome.reactions and complications: include evidence_refs containing exact IDs from turn_evidence. Witness presence permits only observable facts, not secrets. Existing hearsay/suspicion/false beliefs remain uncertain. A failed roll permits its actual consequences, not unrelated punishment.
- A NEW information path may instead use information_event_index referencing this response's information_events, with an established sender, recipients and delivery delay. Reaction timing must follow delivery, and explain how that sender acquired the fact. Do not invent a messenger to justify an otherwise unsupported reaction.
- Genuine direct physical consequences of the player's chosen act may use basis='direct_action' and related_action equal to the relevant supplied action, with a specific causal explanation. This is not permission for remote people to know it.
- Every earned/lost skill, title, notable item or changed condition must agree with state_patch and consequence_manifest. New skills require details with effect/description and combat mechanics when applicable. Never claim a failed/refused purchase succeeded. Narrative remains authoritative only when it agrees with the committed outcome.
- Read current_fact_view before old summaries; use NPC decision profiles without revealing their private knowledge to the player. A quiet success needs no twist.
- COMMAND FIDELITY: a subordinate who recognizes the player's authority executes a clear feasible order as stated, including method, limits, secrecy and timing. Do not replace its objective with their preferred lesson, compromise, negotiation or agenda. Advice can accompany compliance. Independent NPCs retain agency. Refusal/deviation requires established conflicting loyalty, actual inability or a genuinely unclear order, not newly manufactured reluctance. For supplied command_contracts return command_outcomes [{actor, status: obeyed|in_progress|blocked|refused|deviated, evidence_refs: []}]; blocked/refused/deviated outcomes require applicable established evidence IDs.
- On long skips group routine progress; preserve meaningful developments and stop at real decisions. Label truly routine update rows significance='routine' with a routine_group and use significance='milestone'/'decision' for actual developments. A voluntary milestone is not automatically an interruption.
"""

CHAT_CONSISTENCY_RULE = """
Use current_fact_view and npc_decision_profiles before old chat history. No automatic suspicion or advice. Subordinates follow clear feasible orders as given; return command_outcomes for supplied contracts. Refusal/deviation needs applicable turn_evidence IDs, not mere presence. Independent NPCs retain agency; nobody knows undiscovered secrets.
"""


def prepare_request(state, payload):
    packet = copy.deepcopy(payload)
    actions = rows(packet.get("actions")) or rows(packet.get("planned_actions")) or rows(packet.get("queued_actions"))
    query = text(packet.get("action") or packet.get("player_message") or "; ".join(ai_text(row) for row in actions), 4000)
    if packet.get("thread"):
        query = f"{text(packet['thread'])}: {query}"
    packet["turn_evidence"] = evidence_packet(state, query, packet)
    packet["command_contracts"] = command_contracts(state, query)
    packet["connected_memories"] = connected_memory(state, query)
    from organizations import organization_context, ORGANIZATION_RULE
    packet["organization_context"] = organization_context(state, query)
    packet["continuity_guidance"] = REFINEMENT_RULE + ORGANIZATION_RULE
    from chronicle_prose import WRITING_RULE
    packet["chronicle_writing"] = WRITING_RULE
    from relationship_life import prepare as prepare_relationships
    prepare_relationships(state, packet)
    if re.search(r"\b(?:her|him|them)\b", query, re.I) and not packet["command_contracts"]:
        packet["reference_resolution"] = "ambiguous unless the current conversation clearly identifies the referent; do not guess"
    schema = mapping(packet.get("schema"))
    for claim in rows(schema.get("consequence_manifest")):
        if isinstance(claim, dict):
            claim["subject"] = "player or exact NPC who owns this gain/loss; never give NPC gains to the player"
            claim["change"] = "explicit settled transition: gained|lost|destroyed|completed|in_progress|discovered|arrived|died; suspected/planned outcomes are not settled"
    schema["organization_updates"] = [{"group": "established group name", "event": "establish|invite|join|position|leave|retire|expel|death|away|return|development|life|birth|succession_plan", "name": "person", "reason": "actual narrative cause", "accepted": "true only after agreement", "position": "world-appropriate role", "reports_to": "recognized superior", "unit": "existing unit", "activity": "for development: established practice", "discipline": "actual world stat, combat or noncombat specialty", "mentor": "known mentor or empty", "rate": "routine|focused|exceptional", "method": "established acceleration if exceptional"}]
    schema["organization_updates"][0].update(kind="crew|marine|squad|organization|guild|division|clan|team|nation|company", leader="recognized leader, for establishment or leadership change", independent="true only for an independent ally", terms="agreed recruitment terms", loyalty_basis="established reason for loyalty", parents=["known parent"], aging_mode="mortal|ageless|immortal|spiritual|arrested", maturity_age="only when established", active="false to end ongoing development")
    if isinstance(schema.get("causal_outcome"), dict):
        for kind in ("reactions", "complications"):
            for row in rows(schema["causal_outcome"].get(kind)):
                if isinstance(row, dict):
                    row["evidence_refs"] = ["exact applicable ID from turn_evidence"]
                    row["basis_fact"] = "the specific observable or remembered fact supporting this response, not merely an unrelated citation"
    if isinstance(schema.get("updates"), list):
        for row in schema["updates"]:
            if isinstance(row, dict):
                row.update(significance="routine|milestone|decision", routine_group="same activity key for routine progress, otherwise empty")
    if packet["command_contracts"]:
        schema["command_outcomes"] = [{"actor": "commanded subordinate", "status": "obeyed|in_progress|blocked|refused|deviated", "basis_fact": "specific evidence for any obstacle or refusal", "evidence_refs": []}]
    schema["reopened_threads"] = [{"name": "exact previously settled problem, only if genuinely reopened", "cause": "new established cause", "evidence_refs": []}]
    if schema:
        packet["schema"] = schema
    from chapter_recaps import prepare_chapter_request
    prepare_chapter_request(state, packet)
    if "skip" in text(packet.get("task")) or packet.get("requested_duration"):
        packet["narrative_pacing"] = pacing_packet(state, packet)
    return packet


def _all_prose(data):
    return " ".join([text(data.get("narrative"), 20000),
                     *[text(mapping(row).get("narrative"), 10000) for row in rows(data.get("updates"))]])


def _names(value):
    if isinstance(value, dict):
        return {str(key).casefold() for key in value}
    return {text(row.get("name") or row.get("title") if isinstance(row, dict) else row).casefold() for row in rows(value)}


def semantic_issues(state, data, payload=None):
    """High-confidence structural/semantic contradictions, not keyword grading."""
    payload = mapping(payload)
    patch = mapping(data.get("state_patch"))
    from organizations import organization_issues
    issues = organization_issues(state, data)
    evidence = {row["id"]: row for row in rows(payload.get("turn_evidence")) if isinstance(row, dict) and row.get("id")}
    # Legacy callers without a prepared evidence contract retain compatibility.
    if "turn_evidence" in payload:
        if payload.get("task") != "resolve_time_skip" and len(rows(mapping(data.get("causal_outcome")).get("complications"))) > 1:
            issues.append("An ordinary beat may carry at most one supported complication. Preserve the direct result and remove the additional setbacks from prose and state, not merely their labels.")
        for command in rows(payload.get("command_contracts")):
            actor = command["actor"]
            outcomes = [row for row in rows(data.get("command_outcomes")) if isinstance(row, dict) and text(row.get("actor")).casefold() == actor.casefold()]
            refusal = re.search(rf"\b{re.escape(actor)}\s+(?:flatly\s+)?(?:refuses|refused|rejects|rejected|disobeys|disobeyed|ignores|ignored)\b", _all_prose(data), re.I)
            if not outcomes:
                issues.append(f"Report command_outcomes for {actor}: the order's actual completion, ongoing work or evidenced obstacle, without changing its objective.")
            for outcome in outcomes or ([{"status": "refused"}] if refusal else []):
                if outcome.get("status") not in {"obeyed", "in_progress", "blocked", "refused", "deviated"}:
                    issues.append(f"{actor}'s command_outcome needs an actual completion, progress or obstacle status.")
                if refusal and outcome.get("status") in {"obeyed", "in_progress"}:
                    issues.append(f"{actor}'s prose refuses the order while command_outcomes says compliance. Make the settled outcome consistent.")
                if outcome.get("status") in {"blocked", "refused", "deviated"}:
                    refs = [evidence.get(ref) for ref in rows(outcome.get("evidence_refs")) if isinstance(ref, str)]
                    applicable = [ref for ref in refs if ref and ref.get("kind") != "witness" and (not ref.get("actor") or text(ref.get("actor")).casefold() == actor.casefold())]
                    supported_outcome = {"cause": command.get("order", ""), **outcome}
                    if not applicable or not relevant_evidence(supported_outcome, applicable, actor):
                        issues.append(f"{actor} has an established command relationship but refuses or changes the order without applicable evidence. Preserve the player's objective and constraints; do not invent disobedience.")
        for kind in ("reactions", "complications"):
            for row in rows(mapping(data.get("causal_outcome")).get(kind)):
                if not isinstance(row, dict):
                    continue
                actor = text(row.get("actor") or row.get("who"))
                refs = rows(row.get("evidence_refs"))
                supplied = [evidence[ref] for ref in refs if isinstance(ref, str) and ref in evidence]
                valid = bool(supplied) and len(supplied) == len(refs) and relevant_evidence(row, supplied, actor)
                if kind == "reactions":
                    valid = valid and any(text(ref.get("actor")).casefold() == actor.casefold() for ref in supplied)
                    from knowledge import concealed_player_facts
                    reaction_text = text(row, 3000).casefold()
                    secrets = [secret for secret in concealed_player_facts(state) if secret.casefold() in reaction_text]
                    for secret in secrets:
                        # Presence alone does not disclose a hidden power's identity.
                        if not any(ref.get("kind") in {"confirmed", "heard"} and secret.casefold() in text(ref.get("fact")).casefold() and text(ref.get("actor")).casefold() == actor.casefold() for ref in supplied):
                            valid = False
                index = row.get("information_event_index")
                events = rows(data.get("information_events"))
                if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(events):
                    event = mapping(events[index])
                    sender = text(event.get("source"))
                    recipients = _names(event.get("recipients"))
                    observable_sender = sender in present_people(state)
                    sender_facts = [ref for ref in evidence.values() if ref.get("actor") == sender and ref.get("kind") in {"confirmed", "heard"}]
                    fact = text(event.get("fact"))
                    knows_fact = any(fact and fact.casefold() in text(ref.get("fact")).casefold() for ref in sender_facts)
                    delay = number(event.get("delay_minutes"), -1)
                    reaction_time = number(row.get("elapsed_minutes"), -1)
                    elapsed = mapping(data.get("elapsed"))
                    factor = {"minute": 1, "minutes": 1, "hour": 60, "hours": 60, "day": 1440, "days": 1440,
                              "week": 10080, "weeks": 10080, "month": 43200, "months": 43200, "year": 525600, "years": 525600}.get(text(elapsed.get("unit")).lower(), 1)
                    end = number(elapsed.get("amount"), number(payload.get("elapsed_minutes"), 5)) * factor
                    valid = bool(actor.casefold() in recipients and (observable_sender or knows_fact)
                                 and delay >= 0 and end >= reaction_time >= delay)
                if kind == "complications" and row.get("basis") == "direct_action":
                    actions = rows(payload.get("actions")) or rows(payload.get("planned_actions")) or rows(payload.get("queued_actions")) or [payload.get("action")]
                    valid = bool(text(row.get("cause")) and text(row.get("related_action")) in [text(action) for action in actions if text(action)]
                                 and (not actor or actor in present_people(state)))
                if not valid:
                    issues.append(f"Unsupported {kind[:-1]}: {actor or text(row.get('effect'))}. Supply applicable pre-turn evidence or a verified, delivered information path; otherwise remove this reaction/consequence from prose, updates and state changes.")
    updates = [row for row in rows(data.get("updates")) if isinstance(row, dict)]
    if (data.get("interrupted") and data.get("interruption_kind") in {"other", "world_event"}
            and updates and all(row.get("significance") == "routine" and not row.get("decision_required") for row in updates)):
        issues.append("The skip stops solely for routine progress with no decision. Continue to the requested endpoint or supply the genuine, evidenced decision boundary; do not silently advance beyond danger.")
    manifest = [row for row in rows(data.get("consequence_manifest")) if isinstance(row, dict)]
    for row in manifest:
        kind, target = text(row.get("kind")).lower(), text(row.get("target") or row.get("name"))
        change = text(row.get("change") or row.get("status")).lower()
        if change in {"attempted", "failed", "refused", "planned", "possible", "rumored"}:
            field = {"skill": "skills", "item": "inventory", "loot": "inventory", "title": "titles"}.get(kind)
            if field and target.casefold() in _names(patch.get(field)) - _names(state.get(field)):
                issues.append(f"{target} is marked {change}, but the patch grants it. Preserve the settled outcome, not the contradictory award.")
            continue
        if kind == "skill" and target and change not in {"lost", "removed", "sealed", "forgotten"}:
            existing = next((value for name, value in {**mapping(state.get('skills')), **mapping(patch.get('skills'))}.items()
                             if str(name).casefold() == target.casefold()), None)
            details = mapping(existing) or mapping(row.get("details"))
            if not (details.get("effect") or details.get("description")):
                issues.append(f"Learned skill {target} has no usable mechanics. Supply its actual effect and combat category, or correct the unsupported learning claim.")
    # Exact player acquisition clauses only: no 'tries to', NPC learning or conditional promises.
    prose = _all_prose(data)
    subject = "(?:You|" + re.escape(text(state.get("name")) or "The player") + ")"
    claimed = re.findall(rf"\b{subject}\s+(?:have\s+|has\s+)?(?:learned|unlocked|awakened)\s+(?:the\s+)?(?:skill|technique|ability)\s+[\"*]*([A-Z][\w'’ -]{{2,70}}?)(?=[\"*.!,;:]|$)", prose)
    recorded = _names(state.get("skills")) | _names(patch.get("skills")) | {text(row.get("target")).casefold() for row in manifest if row.get("kind") == "skill" and mapping(row.get("details"))}
    for name in claimed:
        if name.strip().casefold() not in recorded:
            issues.append(f"The prose awards {name.strip()} without a matching recorded skill and mechanics.")
    issues.extend(closure_issues(state, data, evidence))
    return list(dict.fromkeys(issues))[:8]


def outcome_assertions(scenario, response):
    """Scenario checks examine values and changes, not whether words occur."""
    state, patch = mapping(scenario.get("state")), mapping(response.get("state_patch"))
    checks = []
    for assertion in rows(scenario.get("outcome_assertions")):
        kind = assertion.get("kind")
        if kind == "no_combat":
            passed = mapping(patch.get("combat")).get("active", mapping(state.get("combat")).get("active", False)) is False
        elif kind == "owns_skill":
            skill = mapping(patch.get("skills")).get(assertion.get("name"), mapping(state.get("skills")).get(assertion.get("name")))
            passed = bool(mapping(skill).get("effect") or mapping(skill).get("description"))
        elif kind == "no_award":
            field = assertion.get("field", "inventory")
            passed = text(assertion.get("name")).casefold() not in _names(patch.get(field)) - _names(state.get(field))
        elif kind == "no_unsupported_reaction":
            prepared = prepare_request(state, {"action": scenario.get("action"), "task": "evaluation"})
            passed = not semantic_issues(state, response, prepared)
        else:
            passed = False
        checks.append({"name": text(assertion.get("name") or kind), "passed": passed})
    return checks


def coalesce_routine_updates(updates):
    """Group only explicitly routine rows. Never discard a decision or reward."""
    output, groups = [], {}
    for raw in rows(updates):
        if not isinstance(raw, dict):
            continue
        row = copy.deepcopy(raw)
        group = text(row.get("routine_group"))
        routine = row.get("significance") == "routine" and group
        important = (row.get("type") in {"interruption", "canon_event", "consequence"}
                     or row.get("map_changes") or row.get("decision_required") or row.get("rewards")
                     or re.search(r"\b(?:learned|unlocked|awakened|died|injured|title acquired|level up|betrayed)\b", text(row.get("narrative"), 10000), re.I))
        if not routine or important:
            output.append(row)
            continue
        if group not in groups:
            groups[group] = len(output)
            row["period_start_day"] = row.get("canon_day")
            output.append(row)
        else:
            previous = output[groups[group]]
            # Preserve all distinct concrete developments verbatim, without another heading per day.
            line = text(row.get("narrative"), 10000)
            if line and line not in previous.get("narrative", ""):
                previous["narrative"] = previous.get("narrative", "") + "\n\n" + line
            previous["period_end_day"] = row.get("canon_day")
    return output
