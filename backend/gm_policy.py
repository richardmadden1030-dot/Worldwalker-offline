"""Deterministic controls around the narrative GM.

The model supplies prose and world judgment.  This module supplies the parts
that should not vary with model mood: intent shape, prompt routing, temporal
scope, causal evidence requirements, template cleanup, progression targets,
and distinct next-action choices.  None of these helpers makes another AI
call or mutates campaign state.
"""
from __future__ import annotations

import copy
import re

from util import ai_text


_ACTION_PATTERNS = {
    "combat": r"\b(?:attack|fight|strike|stab|slash|shoot|punch|kick|kill|duel|spar|defend|parry|ambush)\b",
    "training": r"\b(?:train(?:s|ed|ing)?|practic(?:e|es|ed|ing)|stud(?:y|ies|ied|ying)|learn(?:s|ed|ing)?|master(?:s|ed|ing)?|condition(?:s|ed|ing)?|meditat(?:e|es|ed|ing)|exercis(?:e|es|ed|ing)|drill(?:s|ed|ing)?)\b",
    "social": r"\b(?:talk|ask|convince|persuade|negotiate|befriend|apologize|invite|reassure|threaten)\b",
    "communication": r"\b(?:message|write|call|contact|send word|report|letter)\b",
    "travel": r"\b(?:travel|go to|head to|sail|fly to|walk to|return to|leave for|journey)\b",
    "crafting": r"\b(?:craft|forge|build|cook|brew|make|repair|invent|design)\b",
    "investigation": r"\b(?:investigate|search|research|track|inspect|question|scout|analyze|watch|observe|check)\b",
    "governance": r"\b(?:rule|govern|order|command|policy|territory|land|faction|guild|village|nation|army)\b",
    "finance": r"(?:[$£¥₩]|\b(?:buy|sell|pay|price|money|currency|gold|bel[iy]|ryo|wage|rent|income|expense|shop)\b)",
    "quest": r"\b(?:quest|mission|job|contract|objective|goal|assignment|agenda|promise)\b",
    "ability": r"\b(?:skill|ability|technique|jutsu|spell|class|shikai|bankai|domain|hatsu|nen|haki|devil fruit|kekkei|dojutsu|transformation|form)\b",
}

_STANDING_RE = re.compile(
    r"\b(?:always|continually|continuously|regularly|every\s+(?:day|morning|night|week|month)|"
    r"from now on|keep\s+\w+ing|continue\s+\w+ing|ensure that|make sure|maintain|until (?:i|we|the)|ongoing)\b",
    re.I,
)
_DURATION_RE = re.compile(
    r"\b(?:for|over|during)\s+(?:the\s+next\s+)?(?P<amount>\d+|a|an|one|two|three|four|five|six|several|few)\s+"
    r"(?P<unit>minutes?|hours?|days?|weeks?|months?|years?)\b",
    re.I,
)
_METHOD_RE = re.compile(r"\b(?:by|using|through|via|with the help of)\s+([^.;]{3,180})", re.I)
_RESULT_RE = re.compile(r"\b(?:so that|in order to|with the goal of|until)\s+([^.;]{3,180})", re.I)


def _known_targets(state):
    state = state if isinstance(state, dict) else {}
    values = []
    for field in ("contacts", "npc_memories", "factions"):
        mapping = state.get(field)
        if isinstance(mapping, dict):
            values.extend(mapping.keys())
    locations = state.get("discovered_locations")
    if isinstance(locations, list):
        values.extend(locations)
    values.append(state.get("location"))
    companions = state.get("companions") if isinstance(state.get("companions"), list) else []
    for row in companions:
        values.append(row.get("name") if isinstance(row, dict) else row)
    quests = state.get("quests") if isinstance(state.get("quests"), list) else []
    for row in quests:
        if isinstance(row, dict):
            values.append(row.get("name") or row.get("title"))
    return list(dict.fromkeys(ai_text(value).strip() for value in values if ai_text(value).strip()))


def parse_player_intent(action, state=None):
    """Turn free-form input into a compact, non-authoritative control packet."""
    text = re.sub(r"\s+", " ", ai_text(action)).strip()
    lower = text.lower()
    clauses = intent_clauses(text)
    immediate = " ; ".join(row["text"] for row in clauses if row["mode"] == "immediate")
    kinds = [name for name, pattern in _ACTION_PATTERNS.items() if re.search(pattern, immediate, re.I)]
    if not kinds:
        kinds = ["general"]
    duration = {}
    match = _DURATION_RE.search(text)
    if match:
        duration = {"amount": match.group("amount").lower(), "unit": match.group("unit").lower()}
    method = _METHOD_RE.search(text)
    desired = _RESULT_RE.search(text)
    targets = [name for name in sorted(_known_targets(state), key=len, reverse=True)
               if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I)][:8]
    nonlethal = bool(re.search(r"\b(?:spare|capture|subdue|knock out|non[- ]?lethal)\b", immediate, re.I)
                    or re.search(r"\b(?:do not|don't|never) kill\b", lower))
    lethal = bool(re.search(r"\b(?:kill|execute|slay|assassinate|to the death|lethal)\b", immediate, re.I)) and not nonlethal
    scene = (state or {}).get("scene_state") if isinstance(state, dict) else {}
    scene = scene if isinstance(scene, dict) else {}
    present = [ai_text(row.get("name") if isinstance(row, dict) else row)
               for row in scene.get("present", []) if row] if isinstance(scene.get("present"), list) else []
    return {
        "raw": text[:1200],
        "activity": kinds,
        "clauses": clauses,
        "immediate_text": immediate,
        "prohibited": [row["text"] for row in clauses if row["mode"] == "prohibited"],
        "conditional": [row for row in clauses if row["mode"] == "conditional"],
        "reference_candidates": present[:8] if re.search(r"\b(?:him|her|them|he|she|they)\b", text, re.I) else [],
        "reference_rule": "Resolve pronouns from this scene and preceding clauses, never guess among ambiguous people.",
        "targets": targets,
        "desired_result": (desired.group(1).strip()[:220] if desired else ""),
        "method": (method.group(1).strip()[:220] if method else ""),
        "duration": duration,
        "standing": bool(_STANDING_RE.search(text)),
        "lethality": "nonlethal" if nonlethal else "lethal" if lethal else "unspecified",
        "player_controls": "the stated character action and method",
        "world_controls": "other characters' informed reactions and consequences caused by established facts",
    }


def intent_clauses(text):
    """Conservative scope hints, not a replacement for understanding free text.

    Keep conditions attached to their governed action, including negated-unless
    clauses. Never assert that an unobserved condition has been satisfied.
    """
    text = ai_text(text).replace("’", "'")
    # Split action boundaries but not a leading 'if X, do Y' condition.
    pieces = re.split(r"[;\n]|(?<=[.!?])\s+|\bbut\b|\b(?:and|or)\s+(?=(?:I\s+)?(?:don't|do not|never|avoid)\b)", text, flags=re.I)
    rows = []
    for piece in pieces:
        piece = piece.strip(" ,.")
        if not piece:
            continue
        condition = re.search(r"\b(?:only if|unless|if|once|when|provided that)\b", piece, re.I)
        if condition:
            rows.append({"text": piece[:500], "mode": "conditional", "condition": piece[condition.start():][:300]})
            continue
        # 'Inspect the door without touching it' retains inspection, excludes contact.
        # Explicit sequencing is retained inside immediate text so existing
        # fight-proposal logic can distinguish 'ask to spar' from 'then attack'.
        bits = re.split(r"\b(without|don't|do not|never|avoid|refrain from)\b", piece, maxsplit=1, flags=re.I)
        if len(bits) > 1:
            prefix = bits[0].strip(" ,")
            if prefix and prefix.lower() not in {"i", "we", "please", "i will", "we will"}:
                rows.append({"text": prefix[:500], "mode": "immediate"})
            rows.append({"text": (bits[1] + " " + bits[2]).strip()[:500], "mode": "prohibited"})
        else:
            rows.append({"text": piece[:500], "mode": "immediate"})
    return rows[:20]


def prompt_modules(purpose, query, state=None):
    """Return only the instruction domains this job can plausibly touch."""
    purpose = str(purpose or "moment")
    text = ai_text(query)
    active = {name for name, pattern in _ACTION_PATTERNS.items() if re.search(pattern, text, re.I)}
    state = state if isinstance(state, dict) else {}
    # A direct task_rules() inspection has no player query to route from.  In
    # that diagnostic/plug-in case retain the complete narrator contract;
    # production task_context() always supplies the actual action and remains
    # narrowly routed.
    if not text.strip() and purpose in {"moment", "time_skip"}:
        active.update({"finance", "quest", "governance"})
    if purpose == "opening":
        active.update({"ability", "quest", "social", "travel"})
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    if purpose == "combat_summary" or combat.get("active"):
        active.update({"combat", "ability"})
    if purpose in {"time_skip", "time_plan"}:
        quests = state.get("quests") if isinstance(state.get("quests"), list) else []
        if any(isinstance(row, dict) and str(row.get("status", "active")).lower() == "active" for row in quests):
            active.add("quest")
        if state.get("standing_intents") or state.get("standing_orders"):
            active.add("standing")
    if str(state.get("simulation_scale") or "Individual") != "Individual":
        active.add("governance")
    return {
        "active": sorted(active),
        "combat": "combat" in active,
        "training": "training" in active,
        "finance": "finance" in active,
        "quest": "quest" in active,
        "ability": "ability" in active or "training" in active,
        "faction": "governance" in active,
        "communication": bool(active & {"social", "communication"}),
    }


def intent_prompt(contract):
    if not isinstance(contract, dict) or not contract.get("raw"):
        return ""
    return (
        "\nTURN INTENT CONTRACT (local parse; the player's actual words remain authoritative):\n"
        f"- Activity: {', '.join(contract.get('activity') or ['general'])}. "
        f"Targets: {', '.join(contract.get('targets') or []) or 'not explicitly named'}. "
        f"Duration: {contract.get('duration') or 'this beat'}.\n"
        f"- Method: {contract.get('method') or 'use the stated method exactly'}. "
        f"Desired result: {contract.get('desired_result') or 'the direct ordinary result of the action'}.\n"
        f"- Standing instruction: {'yes' if contract.get('standing') else 'no'}. "
        f"Lethality: {contract.get('lethality', 'unspecified')}.\n"
        f"- Ordered clauses: {contract.get('clauses', [])}. Prohibited actions are never performed. "
        "Conditional actions wait until their trigger actually occurs; mentioning a threat is not committing violence.\n"
        f"- Pronoun candidates: {contract.get('reference_candidates', [])}. {contract.get('reference_rule', '')}\n"
        "Resolve the player-controlled act first. Keep independent NPC choice in their subsequent informed reaction; do not turn that reaction into retroactive failure."
    )


def temporal_budget(purpose, amount=None, unit=None):
    purpose = str(purpose or "moment")
    if purpose in {"moment", "event"}:
        return {"mode": "immediate_beat", "max_minutes": 1440,
                "stop": "the next meaningful decision point after the action resolves"}
    if purpose == "major_event":
        return {"mode": "major_boundary", "max_minutes": 0,
                "stop": "the event's arrival and the player's grounded immediate position"}
    if purpose in {"time_skip", "time_plan"}:
        return {"mode": "bounded_skip", "amount": amount, "unit": unit,
                "stop": "the requested endpoint or the first legitimate hard-stop event"}
    return {"mode": "no_time_advance", "max_minutes": 0}


def progression_plan(state, actions, elapsed_minutes, intensity="normal"):
    """Describe the locally expected shape of training before prose is written."""
    actions = [ai_text(row).strip() for row in (actions or []) if ai_text(row).strip()]
    training = [row for row in actions if re.search(_ACTION_PATTERNS["training"], row, re.I)]
    days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    if not training:
        return {"training": False, "elapsed_days": round(days, 3)}
    state = state if isinstance(state, dict) else {}
    named = []
    haystack = " ".join(training)
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name in [*stats.keys(), *skills.keys()]:
        if re.search(rf"(?<!\w){re.escape(str(name))}(?!\w)", haystack, re.I):
            named.append(str(name))
    multiplier = {"light": .7, "normal": 1.0, "rigorous": 1.35, "extreme": 1.65}.get(str(intensity).lower(), 1.0)
    visible = days * multiplier >= .75
    milestone = ("breakthrough-eligible" if days * multiplier >= 30 else
                 "substantial" if days * multiplier >= 7 else
                 "noticeable" if visible else "foundation")
    return {
        "training": True, "orders": training[:8], "targets": named[:12],
        "elapsed_days": round(days, 3), "intensity_multiplier": multiplier,
        "expected_progress": milestone,
        "requirements": [
            "Grant visible proportional progress when expected_progress is noticeable or higher.",
            "A named target receives the strongest gain; related foundations may also rise proportionally.",
            "A breakthrough changes tier/form only when the method, elapsed effort, and world prerequisites support it.",
        ],
    }


_DROP_SENTENCES = [
    re.compile(r"^(?:what does this change|how does this change) for your next move\??$", re.I),
    re.compile(r"^no (?:specific|immediate|known) (?:danger|pressure|risk) (?:is )?(?:confirmed|known|present|visible)(?: yet)?\.?$", re.I),
    re.compile(r"^(?:a|the) wave of clarity washes over (?:you|them|him|her)\.?$", re.I),
]
_MANUFACTURED_NEGATIVE = [
    re.compile(r"^(?:however|but|yet),? (?:this|the success|your success) (?:draws?|attracts?) (?:unwanted |dangerous )?(?:attention|eyes)\.?$", re.I),
    re.compile(r"^(?:unbeknownst to you|somewhere in the shadows),? (?:someone|unseen eyes|powerful figures) (?:is|are) watching\.?$", re.I),
    re.compile(r"^(?:every|such a) (?:victory|success|gain) (?:has|comes with) (?:a )?(?:price|cost)\.?$", re.I),
]


def clean_model_text(value, remove_manufactured=False):
    text = ai_text(value).replace("..", ".")
    if not text.strip():
        return ""
    pieces = re.split(r"(?<=[.!?])(?:\s+|\n+)", text.strip())
    kept, seen = [], set()
    for piece in pieces:
        clean = re.sub(r"\s+", " ", piece).strip()
        if not clean or any(pattern.match(clean) for pattern in _DROP_SENTENCES):
            continue
        if remove_manufactured and any(pattern.match(clean) for pattern in _MANUFACTURED_NEGATIVE):
            continue
        key = re.sub(r"[^a-z0-9]+", " ", clean.lower()).strip()
        if key in seen:
            continue
        seen.add(key); kept.append(clean)
    return " ".join(kept).strip()


def _has_settled_negative_cause(payload, state):
    assessment = payload.get("assessment") if isinstance(payload, dict) else {}
    rolls = payload.get("dice_results") if isinstance(payload, dict) else []
    if payload.get("dice_result"):
        rolls = [payload.get("dice_result")]
    failed = any(isinstance(row, dict) and not bool(row.get("success")) for row in (rolls or []))
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    return bool(failed or combat.get("active") or
                str((assessment or {}).get("lethal_risk") or "none").lower() in {"moderate", "high", "extreme"})


def enforce_response_policy(data, payload, state):
    """Clean model output and enforce structured causality without a retry."""
    if not isinstance(data, dict):
        return data
    result = copy.deepcopy(data)
    repairs = []
    remove_manufactured = str((state or {}).get("difficulty") or "") != "Nightmare" and not _has_settled_negative_cause(payload or {}, state or {})
    for key in ("narrative", "interruption_reason", "interruption_context", "intervention_prompt"):
        if key in result:
            cleaned = clean_model_text(result.get(key), remove_manufactured)
            if cleaned != ai_text(result.get(key)).strip(): repairs.append(f"cleaned_{key}")
            result[key] = cleaned
    for update in result.get("updates") or []:
        if not isinstance(update, dict): continue
        for key in ("narrative", "why_it_matters", "player_knowledge", "next_pressure"):
            if key in update:
                update[key] = clean_model_text(update.get(key), remove_manufactured)
    for event in result.get("events") or []:
        if isinstance(event, dict) and event.get("message"):
            event["message"] = clean_model_text(event.get("message"), False)

    # The prepared request uses stronger provenance validation before this
    # cleanup; do not erase referenced rows just because legacy text is absent.
    if "turn_evidence" in (payload or {}):
        if repairs:
            result["gm_policy_repairs"] = repairs
        return result

    causal = result.get("causal_outcome") if isinstance(result.get("causal_outcome"), dict) else {}
    complications = causal.get("complications") if isinstance(causal.get("complications"), list) else []
    valid_complications = []
    for row in complications:
        if not isinstance(row, dict): continue
        cause = ai_text(row.get("cause") or row.get("evidence")).strip()
        effect = ai_text(row.get("effect") or row.get("result")).strip()
        if cause and effect:
            valid_complications.append({**row, "cause": cause[:400], "effect": effect[:400]})
    if str((payload or {}).get("task") or "") != "resolve_time_skip":
        valid_complications = valid_complications[:1]
    if len(valid_complications) != len(complications): repairs.append("removed_unsupported_complication")
    causal["complications"] = valid_complications

    reactions = causal.get("reactions") if isinstance(causal.get("reactions"), list) else []
    valid_reactions = []
    scene = (state or {}).get("scene_state")
    scene = scene if isinstance(scene, dict) else {}
    present_rows = scene.get("present") if isinstance(scene.get("present"), list) else []
    present = {ai_text(row).lower() for row in present_rows if ai_text(row)}
    for row in reactions:
        if not isinstance(row, dict): continue
        actor = ai_text(row.get("actor") or row.get("who")).strip()
        source = ai_text(row.get("knowledge_source") or row.get("source")).strip().lower()
        if actor and (source or actor.lower() in present):
            valid_reactions.append(row)
    if len(valid_reactions) != len(reactions): repairs.append("removed_omniscient_reaction")
    causal["reactions"] = valid_reactions
    if causal:
        result["causal_outcome"] = causal
    if repairs:
        result["local_policy_repairs"] = list(dict.fromkeys(repairs))
    return result


def record_causal_outcome(state, data, actions, elapsed_minutes=0):
    """Persist the compact reason for a resolution for Advisor/Journal use."""
    if not isinstance(state, dict) or not isinstance(data, dict):
        return None
    causal = data.get("causal_outcome") if isinstance(data.get("causal_outcome"), dict) else {}
    if not causal:
        narrative = clean_model_text(data.get("narrative"))
        first = re.split(r"(?<=[.!?])\s+", narrative, maxsplit=1)[0] if narrative else ""
        causal = {"direct_result": first[:500], "reactions": [], "costs": [], "complications": []}
    row = {
        "turn": int(state.get("turn", 0) or 0),
        "canon_day": int(state.get("canon_day", 0) or 0),
        "actions": [ai_text(value)[:500] for value in (actions or []) if ai_text(value)][:12],
        "direct_result": ai_text(causal.get("direct_result") or causal.get("result"))[:700],
        "witnesses": [ai_text(value)[:120] for value in causal.get("witnesses", []) if ai_text(value)][:20],
        "reactions": copy.deepcopy((causal.get("reactions") or [])[:20]),
        "costs": copy.deepcopy((causal.get("costs") or [])[:20]),
        "complications": copy.deepcopy((causal.get("complications") or [])[:10]),
        "elapsed_minutes": max(0, int(elapsed_minutes or 0)),
    }
    if not any(row.get(key) for key in ("direct_result", "reactions", "costs", "complications")):
        return None
    state.setdefault("causality_ledger", []).append(row)
    state["causality_ledger"] = state["causality_ledger"][-240:]
    return row


def suggestion_kind(text):
    text = ai_text(text).lower()
    if re.search(r"\b(?:investigate|research|inspect|question|track|scout|learn|find out)\b", text): return "investigate"
    if re.search(r"\b(?:train|practice|prepare|recover|study|build|craft|recruit)\b", text): return "prepare"
    if re.search(r"\b(?:talk|contact|message|ask|negotiate|visit|meet)\b", text): return "social"
    if re.search(r"\b(?:travel|go to|head to|sail|return to|leave for)\b", text): return "travel"
    return "direct"


def distinct_suggestions(candidates, state, limit=3):
    """Prefer different tactical shapes and grounded named targets."""
    state = state if isinstance(state, dict) else {}
    location = ai_text(state.get("location") or "the current location")
    known = {name.casefold() for name in _known_targets(state)}
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}

    def grounded(text):
        # Do not offer travel to where the player already is.
        if location and re.search(r"\b(?:travel|go|head|sail|return|walk|fly)\s+(?:to|toward|back to)\s+" +
                                  re.escape(location) + r"(?:\b|$)", text, re.I):
            return False
        # Once combat has ended, never preserve a template telling the player
        # to continue the finished exchange.
        if not combat.get("active") and re.search(r"\b(?:continue|resume)\s+(?:the\s+)?(?:fight|battle|duel|combat)\b", text, re.I):
            return False
        # Communication choices must identify a contact the campaign knows.
        target = re.search(
            r"\b(?:speak|talk|contact|message|call|ask|meet|visit|negotiate)\s+(?:to|with)?\s*"
            r"([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3})", text,
            re.I,
        )
        if target and known:
            named = target.group(1).strip().casefold()
            if not any(named == item or named in item or item in named for item in known):
                return False
        return True

    cleaned, seen = [], set()
    for value in candidates or []:
        text = clean_model_text(value)
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if text and key not in seen and grounded(text):
            seen.add(key); cleaned.append(text[:180])
    chosen, kinds = [], set()
    for text in cleaned:
        kind = suggestion_kind(text)
        if kind not in kinds:
            chosen.append(text); kinds.add(kind)
        if len(chosen) >= limit: return chosen
    for text in cleaned:
        if text not in chosen:
            chosen.append(text)
        if len(chosen) >= limit: return chosen
    contacts_map = state.get("contacts") if isinstance(state.get("contacts"), dict) else {}
    skills_map = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    contacts = [ai_text(name) for name in contacts_map if ai_text(name)]
    skills = [ai_text(name) for name in skills_map if ai_text(name)]
    fallbacks = [
        f"Investigate the latest change at {location} and identify its source",
        f"Speak with {contacts[-1]} about the most immediate unresolved issue" if contacts else f"Review the immediate situation at {location} and choose a concrete objective",
        f"Practice {skills[0]} at {location} to develop a useful new application" if skills else f"Prepare at {location} for the clearest established threat or opportunity",
    ]
    for text in fallbacks:
        if text.lower() not in {row.lower() for row in chosen}:
            chosen.append(text[:180])
        if len(chosen) >= limit: break
    return chosen[:limit]


def select_approved_example(rated, query, purpose="moment"):
    rated = [row for row in (rated or []) if isinstance(row, dict) and ai_text(row.get("outcome"))]
    if not rated:
        return None
    # The journal preview and older plug-ins ask for an example without a
    # query.  Return the newest approved turn there; production calls include
    # the current action and use the relevance scoring below.
    if not ai_text(query).strip():
        return rated[-1]
    target = set(parse_player_intent(query).get("activity") or [])
    scored = []
    for index, row in enumerate(rated):
        kinds = set(parse_player_intent(row.get("action", "")).get("activity") or [])
        score = 5 * len(target & kinds)
        score += 2 if ai_text(row.get("purpose")).lower() == str(purpose).lower() else 0
        score += min(3, len(set(re.findall(r"[a-z0-9']{4,}", ai_text(query).lower())) &
                            set(re.findall(r"[a-z0-9']{4,}", ai_text(row.get("action")).lower()))))
        scored.append((score, -index, row))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return scored[0][2] if scored and scored[0][0] > 0 else None
