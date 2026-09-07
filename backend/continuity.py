"""Deterministic campaign-continuity ledger and contradiction warnings."""
import re
from datetime import datetime

from util import ai_text
from reliability import validate_campaign_state
from worlds import expansion_for
from systems import (ensure_currency_state, currency_balance,
                     record_observed_currency_change, record_finance_debt)


def _quest_map(items):
    return {str(q.get("name", "")).lower(): q for q in items if isinstance(q, dict) and q.get("name")}


# A real player report: buying something in the narrative repeatedly left
# currency.amount untouched, and payment for work that should plausibly pay
# rarely showed up either. The GM prompt already says currency "must change
# with every transaction" (engine_core.py), but that's prose the model can
# just forget under schema pressure the same way it forgets other fields —
# this catches the mismatch after the fact so it can feed the same
# correction pass every other continuity warning already uses, rather than
# relying on the instruction alone.
_CURRENCY_SPEND_RE = re.compile(r"\b(buys?|bought|purchas\w*|pays? for|paid for|hands? over|handed over)\b", re.I)
_CURRENCY_EARN_RE = re.compile(
    r"\b(gets? paid|is paid|was paid|pays? (?:you|your|him|her|them|the)|receives? payment|"
    r"collects? (?:the|a|her|his|their|your) (?:reward|payment|fee|wages?)|"
    r"earns? (?:you|your|him|her|them)? ?(?:\d+|a (?:hefty|tidy|small|large|handsome)? ?(?:sum|purse|bounty|fee|payment|wage))|"
    r"paid (?:him|her|them)|sells? it for|sold it for)\b", re.I,
)
_CURRENCY_NO_TRANSACTION_RE = re.compile(
    r"\b(declin\w*|refus\w*|can'?t afford|cannot afford|couldn'?t afford|too expensive|"
    r"decides? not to|chooses? not to|considers? buying|thinks? about buying)\b", re.I,
)
_CURRENCY_GENERIC_RE = re.compile(r"\b(coins?|gold|money|payment|reward|fee|wages?)\b", re.I)

# Same shape of bug as currency: the model narrates a clear wound and just
# forgets to patch hp to match. Tied to "you" specifically (this game
# narrates the player in second person — see gm_rules) rather than any
# wound language in the scene, since combat narration wounds NPCs and
# enemies constantly and those never touch the player's own hp.
_WOUND_RE = re.compile(
    r"\b(cuts? (?:deep )?into you|stabs? you|slashes? (?:you|across you|into you)|"
    r"you(?:'re| are) (?:cut|stabbed|slashed|wounded|gashed|pierced|struck down|badly hurt)|"
    r"wounds? you|pierces? you|you(?:'re| are)? bleed\w*|you collapse\w*,? bleeding|"
    r"blood (?:pours?|pools?|runs?) (?:from|down) you|"
    r"knocks? you out|you(?:'re| are) knocked out|"
    r"breaks? your (?:arm|leg|ribs?|bones?|nose)|"
    r"burns? you (?:badly|deeply|severely)|"
    r"you take (?:a|the) (?:heavy|brutal|serious|grievous|solid) (?:hit|blow|wound)|"
    r"the blade (?:bites|sinks) into you|"
    r"tears? into your (?:flesh|skin)|"
    r"leaves? you (?:bleeding|wounded|gashed|badly hurt))\b", re.I,
)
_WOUND_AVOIDED_RE = re.compile(
    r"\b(you (?:dodge|block|parry|parries|deflect|sidestep|narrowly avoid)\w*|"
    r"(?:the (?:blow|blade|strike|hit|attack)) (?:misses|goes wide)|"
    r"leaves? you (?:unharmed|unscathed)|you(?:'re| are) (?:unharmed|unscathed)|"
    r"barely (?:a scratch|grazes? you)|you shrug\w* (?:it|them )?off)\b", re.I,
)

# Mirror of the quest-regression check further down: the model says the
# quest is done but never flips its status field to match.
_QUEST_COMPLETE_RE = re.compile(
    r"\b(quest (?:is |has been |'s )?(?:complete|completed|done|finished)|"
    r"(?:complet\w+|finish\w+|accomplish\w+) (?:the |your )?(?:quest|delivery|task|job|mission|errand)|"
    r"mission (?:is |)accomplished|"
    r"(?:the )?(?:task|delivery|job) (?:is |)(?:complete|completed|done|finished|delivered))\b", re.I,
)


def update_continuity(before, after, action="", narrative=""):
    ledger = after.setdefault("continuity_ledger", {"facts": [], "warnings": [], "last_checked_turn": 0})
    facts = ledger.setdefault("facts", [])
    warnings = []
    turn = after.get("turn", 0)
    stamp = {"turn": turn, "time": datetime.now().isoformat(timespec="seconds")}
    if before.get("location") != after.get("location"):
        facts.append({**stamp, "type": "location", "text": f"Player moved from {before.get('location')} to {after.get('location')}."})
    if before.get("appearance_desc") != after.get("appearance_desc"):
        appearance = str(after.get("appearance_desc") or "").strip().rstrip(" .!?")
        facts.append({**stamp, "type": "appearance", "text": f"Current appearance: {appearance}."})
    # A location's controlling_faction can change from either source: the
    # GM's own state_patch (a player-witnessed change) or the mechanical
    # off-screen conflict resolver in systems.py (a background one) — both
    # have already been applied to `after` by the time this runs, so a
    # single before/after diff here catches either origin instead of having
    # to stamp the same thing in two separate places. Stamped here rather
    # than left implicit so the map can show a "recently changed" highlight
    # instead of a territory flip only ever being visible as a buried
    # single-line world-event message.
    before_details = before.get("location_details") if isinstance(before.get("location_details"), dict) else {}
    after_details = after.get("location_details") if isinstance(after.get("location_details"), dict) else {}
    for loc, detail in after_details.items():
        if not isinstance(detail, dict):
            continue
        prior_detail = before_details.get(loc) if isinstance(before_details.get(loc), dict) else {}
        prior_controller = prior_detail.get("controlling_faction")
        new_controller = detail.get("controlling_faction")
        if new_controller != prior_controller and (prior_detail or new_controller):
            detail["controller_changed_turn"] = turn
            facts.append({**stamp, "type": "territory", "text": f"{loc}'s controlling power changed from {prior_controller or 'unclaimed'} to {new_controller or 'unclaimed'}."})
    new_titles = set(ai_text(t) for t in after.get("titles", []) if ai_text(t))
    old_titles = set(ai_text(t) for t in before.get("titles", []) if ai_text(t))
    for title in new_titles - old_titles:
        facts.append({**stamp, "type": "title", "text": f"Earned title: {title}."})
    old_quests, new_quests = _quest_map(before.get("quests", [])), _quest_map(after.get("quests", []))
    for key, quest in new_quests.items():
        old = old_quests.get(key)
        if not old:
            facts.append({**stamp, "type": "quest", "text": f"Quest accepted: {quest.get('name')}."})
        elif old.get("status") != quest.get("status"):
            facts.append({**stamp, "type": "quest", "text": f"{quest.get('name')} changed from {old.get('status')} to {quest.get('status')}."})
    names = [str(c.get("name", "")).lower() for c in after.get("codex", []) if isinstance(c, dict)]
    if len(names) != len(set(n for n in names if n)):
        warnings.append("The codex contains duplicate named entries.")
    for name, memory in after.get("npc_memories", {}).items():
        if isinstance(memory, dict) and memory.get("last_known_location") == "Unknown" and memory.get("can_contact"):
            warnings.append(f"{name} is contactable but has no known communication location/method.")
    # A quest silently un-completing (or un-failing) is almost always the AI
    # losing track of prior state rather than an intentional twist — a real
    # twist would say so in the narrative, which this can't see, so it only
    # flags the structural regression and lets the correction pass decide.
    for key, quest in new_quests.items():
        old = old_quests.get(key)
        if not old:
            continue
        old_status, new_status = str(old.get("status", "")).lower(), str(quest.get("status", "")).lower()
        if old_status in ("complete", "completed", "failed") and new_status not in (old_status, ""):
            warnings.append(f"Quest '{quest.get('name')}' regressed from {old_status} to {new_status} without explanation.")
    # The mirror case: the narrative declares a quest finished, but the
    # quest's own status field never actually flipped to complete. Only
    # fires when the target is unambiguous — the quest is named outright,
    # or it's the only quest still active and the narrative uses the
    # generic "the quest is done" phrasing — so a passing mention of some
    # other completed job doesn't get misattributed.
    if narrative and _QUEST_COMPLETE_RE.search(narrative):
        active = [(k, q) for k, q in new_quests.items() if str(q.get("status", "")).lower() not in ("complete", "completed", "failed")]
        for key, quest in active:
            old = old_quests.get(key)
            old_status = str(old.get("status", "")).lower() if old else ""
            if old_status in ("complete", "completed", "failed"):
                continue
            quest_name = str(quest.get("name", ""))
            name_mentioned = bool(quest_name) and quest_name.lower() in narrative.lower()
            generic_singular = len(active) == 1 and re.search(r"\bquest\b", narrative, re.I)
            if name_mentioned or generic_singular:
                warnings.append(f"The narrative describes '{quest_name}' as finished, but its status is still '{quest.get('status')}'.")
    # A location that changed without the narrative ever naming the new place
    # is the clearest sign the AI moved the player mechanically (or forgot
    # where they were) rather than actually narrating travel.
    new_location = after.get("location")
    if before.get("location") != new_location and new_location and narrative:
        if str(new_location).lower() not in str(narrative).lower():
            warnings.append(f"Location changed to {new_location}, but the narrative never mentions arriving there.")
    # An NPC's last-known location updating in memory without ever being
    # named in this turn's narrative is the same class of silent drift.
    before_npc = before.get("npc_memories", {}) if isinstance(before.get("npc_memories"), dict) else {}
    after_npc = after.get("npc_memories", {}) if isinstance(after.get("npc_memories"), dict) else {}
    for name, memory in after_npc.items():
        if not isinstance(memory, dict):
            continue
        old_memory = before_npc.get(name) if isinstance(before_npc.get(name), dict) else {}
        new_loc = memory.get("last_known_location")
        if new_loc and new_loc != "Unknown" and new_loc != old_memory.get("last_known_location") and narrative:
            if str(name).lower() not in str(narrative).lower() and str(new_loc).lower() not in str(narrative).lower():
                warnings.append(f"{name}'s last-known location changed to {new_loc}, but neither is mentioned in the narrative.")
    # Consequence chains: npc_memories[name].chain_event is a transient,
    # AI-facing field — one plain sentence explaining why this NPC's
    # attitude just moved (or deepened). The application turns it into a
    # permanent {event, turn, canon_day} entry in npc_memories[name].chain
    # so "why does this NPC feel this way about me" has a real, queryable
    # answer instead of needing to be re-derived from raw narrative history
    # every time it's asked (the Advisor does exactly that — see
    # engine_social.py). Only pings the Chronicle when the attitude label
    # itself actually changed, so a reinforcing beat still gets recorded
    # without spamming a visible notice for every minor nudge.
    for name, memory in after_npc.items():
        if not isinstance(memory, dict):
            continue
        reason = memory.pop("chain_event", None)
        if not reason:
            continue
        old_memory = before_npc.get(name) if isinstance(before_npc.get(name), dict) else {}
        chain = memory.setdefault("chain", [])
        if not isinstance(chain, list):
            chain = []
        normalized_reason = re.sub(r"\W+", " ", str(reason).casefold()).strip()
        if any(re.sub(r"\W+", " ", str(row.get('event', '') if isinstance(row, dict) else row).casefold()).strip() == normalized_reason for row in chain):
            memory['chain'] = chain[-12:]
            continue
        chain.append({"event": str(reason)[:300], "turn": turn, "canon_day": after.get("canon_day")})
        memory["chain"] = chain[-12:]
        if memory.get("attitude") != old_memory.get("attitude"):
            after.setdefault("_pending_chronicle_notes", []).append(f"🔗 {name}'s attitude toward you shifted — {reason}")
    # Same idea for factions: reputation_chain_events is a transient
    # {faction: "one-line reason"} the GM supplies alongside a reputation
    # change, folded into the permanent faction_chain[name] trail and then
    # cleared — mirrors npc_memories[name].chain_event exactly.
    reputation_events = after.pop("reputation_chain_events", None)
    if isinstance(reputation_events, dict) and reputation_events:
        reputation_before = before.get("reputation", {}) if isinstance(before.get("reputation"), dict) else {}
        reputation_after = after.get("reputation", {}) if isinstance(after.get("reputation"), dict) else {}
        faction_chain = after.setdefault("faction_chain", {})
        for fname, reason in reputation_events.items():
            if not reason:
                continue
            entries = faction_chain.setdefault(str(fname), [])
            entries.append({"event": str(reason)[:300], "turn": turn, "canon_day": after.get("canon_day")})
            faction_chain[str(fname)] = entries[-12:]
            if reputation_after.get(fname) != reputation_before.get(fname):
                after.setdefault("_pending_chronicle_notes", []).append(f"🔗 {fname}'s standing toward you shifted — {reason}")
    currency_before = before.get("currency") if isinstance(before.get("currency"), dict) else {}
    currency_after = after.get("currency") if isinstance(after.get("currency"), dict) else {}
    tracks_currency = expansion_for(after.get("world", "Custom World")).get("tracks_currency", True) and currency_before.get("tracked", True) is not False
    if tracks_currency:
        ensure_currency_state(after)
        try:
            before_amount = float(currency_before.get("amount", 0) or 0)
            after_amount = float(currency_balance(after, currency_after.get("name")) or 0)
        except (TypeError, ValueError):
            before_amount = after_amount = 0.0
        if after_amount < 0:
            shortfall = abs(after_amount)
            normalized = ensure_currency_state(after)
            normalized["amount"] = 0
            if int(normalized.get("minor_per_major", 0) or 0) > 1:
                normalized["amount_minor"] = 0
            record_finance_debt(after, "Narrative obligation", shortfall, normalized.get("name"), narrative[:500])
            after_amount = 0.0
            after.setdefault("_pending_chronicle_notes", []).append(
                f"An unpaid obligation of {shortfall:g} {normalized.get('name', 'Currency')} remains outstanding."
            )
        delta = after_amount - before_amount
        already_recorded = any(
            isinstance(row, dict) and row.get("turn") == turn
            and str(row.get("currency", "")).casefold() == str(currency_after.get("name", "")).casefold()
            and abs(float(row.get("balance_after", 0) or 0) - after_amount) < 0.0001
            for row in after.get("currency_ledger", [])
        )
        if abs(delta) > 0.0001 and not already_recorded:
            reason = (str(narrative).strip().splitlines()[0] if narrative else "Narrative transaction")[:300]
            record_observed_currency_change(after, delta, reason, currency_after.get("name"))
    if tracks_currency and narrative and currency_before.get("amount") == currency_after.get("amount") and not _CURRENCY_NO_TRANSACTION_RE.search(narrative):
        currency_name = str(currency_after.get("name") or currency_before.get("name") or "").strip()
        currency_mentioned = (bool(currency_name) and currency_name.lower() in narrative.lower()) or bool(_CURRENCY_GENERIC_RE.search(narrative))
        if currency_mentioned and _CURRENCY_SPEND_RE.search(narrative):
            warnings.append(f"The narrative describes a purchase or payment being made, but currency.amount ({currency_after.get('amount')} {currency_name}) did not decrease.")
        elif currency_mentioned and _CURRENCY_EARN_RE.search(narrative):
            warnings.append(f"The narrative describes the player being paid, rewarded, or earning {currency_name or 'money'}, but currency.amount did not increase.")
    hp_before, hp_after = before.get("hp"), after.get("hp")
    if narrative and isinstance(hp_before, (int, float)) and isinstance(hp_after, (int, float)):
        if hp_after >= hp_before and _WOUND_RE.search(narrative) and not _WOUND_AVOIDED_RE.search(narrative):
            warnings.append(f"The narrative describes the player being wounded, but hp ({hp_after}) did not decrease from {hp_before}.")
    if action:
        after.setdefault("campaign_canon", []).append({**stamp, "action": str(action)[:500], "outcome": str(narrative)[:1200]})
        after["campaign_canon"] = after["campaign_canon"][-250:]
    warnings.extend(validate_campaign_state(before, after, narrative))
    warnings = list(dict.fromkeys(warnings))
    ledger["facts"] = facts[-300:]
    ledger["warnings"] = warnings[-40:]
    ledger["last_checked_turn"] = turn
    return warnings
