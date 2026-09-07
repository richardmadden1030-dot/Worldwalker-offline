"""Persistent world-native membership, command chains and NPC life histories.

Membership is independent of scene presence. Changes arrive through narrative
events; the roster is a view, not a strategy-game management menu.
"""
import copy
import math
import re
from gm_refinements import obj, seq, fingerprint
from age_system import numeric_age
from power_benchmarks import benchmark_tier
from worlds import power_profile_for, abilities_for

ACTIVE = {"active", "away", "missing"}
FORMER = {"left", "retired", "dead", "deceased", "expelled"}
LABELS = {
    "One Piece": "Pirate Crew", "Naruto": "Ninja Squad", "Bleach": "Division",
    "Hunter x Hunter": "Hunter Team", "Jujutsu Kaisen": "Sorcerer Team",
    "Overgeared": "Guild", "Solo Max-Level Newbie": "Raid Party",
    "Reincarnated as a Slime": "Nation & Retainers", "Custom World": "Company",
}

MEMBERSHIP_ENGINE_VERSION = 2
NARUTO_SQUAD_DELAY_DAYS = 4
_MEMBERSHIP_POSITIVE = re.compile(r"\b(?:join(?:ed|s|ing)?|recruit(?:ed|s|ing)?|member|founder|accepted into|part of|belongs to|serves in|asks? to join|offers? to join|agrees? to join|invited? to join|assigned to|added to|recognized(?: as| as an?)?(?: [a-z-]+){0,4} operative|confirmed(?: as| as an?)?(?: [a-z-]+){0,4} operative|inner[- ]circle (?:member|operative))\b", re.I)
_MEMBERSHIP_NEGATIVE = re.compile(r"\b(?:refus(?:e|ed|es|ing)|declin(?:e|ed|es|ing)|reject(?:ed|s|ing)?|failed to join|did not join|didn't join|has not joined|hasn't joined|never joined|has not accepted|hasn't accepted|not accepted|not (?:a )?(?:formal )?member|isn't (?:a )?(?:formal )?member|rather than (?:a )?(?:formal )?member|independent (?:research )?partner|research partner rather than|outside (?:the )?(?:formal )?(?:roster|membership)|left|leaves|departed|expelled|exiled|former member|no longer (?:a )?member|quit|retired|defected)\b", re.I)
_ENTITY_NAME_WORDS = re.compile(r"\b(?:village|city|town|country|kingdom|empire|republic|federation|forest|island|mountain|district|province|region|territory|headquarters|hq|academy|school|shrine|temple|organization|organisation|guild|crew|clan|faction|army|forces|battalion|division|squad|team|party|unit|hideout|base|camp|road|route|bridge|tower|floor|realm|world|memorial|hospital|clinic|shop|office|gate|compound|estate|palace|castle|harbor|port|sea|ocean|river|lake)\b", re.I)
_GAKURE_NAME = re.compile(r"(?:^|\b)[a-z-]*gakure\b", re.I)


def text(value):
    return str(value or "").strip()


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (ValueError, TypeError):
        return default


def campaign_day(state):
    minute = state.get("canon_time_minutes")
    if isinstance(minute, (int, float)) and math.floor(minute / 1440) == number(state.get("canon_day")):
        return minute / 1440
    return number(state.get("canon_day"))


def label_for(world, name="", kind=""):
    blob = f"{kind} {name}".casefold()
    if world == "One Piece":
        if re.search(r"marine|navy", blob): return "Marine Squad"
        if re.search(r"revolution", blob): return "Revolutionary Unit"
    if world == "Naruto" and re.search(r"organization|organisation|\borg\b|akatsuki|root|anbu|village|gakure|konoha", blob): return "Shinobi Organization"
    if world == "Bleach":
        if re.search(r"quincy|wandenreich", blob): return "Quincy Unit"
        if re.search(r"arrancar|espada|hollow", blob): return "Arrancar Faction"
        if re.search(r"academy|student", blob): return "Academy Cohort"
    if world == "Hunter x Hunter":
        if "troupe" in blob: return "Phantom Troupe"
        if "expedition" in blob: return "Expedition Team"
    if world == "Jujutsu Kaisen":
        if "clan" in blob: return "Great Clan"
        if "curse" in blob and "user" in blob: return "Curse-User Group"
        if "spirit" in blob: return "Curse Alliance"
    if world == "Solo Max-Level Newbie" and "guild" in blob: return "Guild"
    return LABELS.get(world, "Company")


def known_people(state):
    people = {name: dict(obj(row)) for name, row in obj(state.get("npc_memories")).items()}
    for row in seq(state.get("companions")):
        if isinstance(row, str): row = {"name": row}
        if isinstance(row, dict) and text(row.get("name")):
            name = text(row["name"])
            name = next((n for n in people if n.casefold() == name.casefold()), name)
            people[name] = {**row, **obj(people.get(name))}
    return people


def membership_copy(state):
    """Views must not copy the campaign's growing Chronicle and image caches."""
    local = dict(state)
    for key in ("organizations", "organization_lives"):
        local[key] = copy.deepcopy(obj(state.get(key)))
    return local


def group_id(name):
    return fingerprint(text(name).casefold())[:16]


def member_status(row):
    status = text(row.get("membership_status") or row.get("status")).casefold()
    status = {"former": "left", "exiled": "expelled", "invited": "candidate"}.get(status, status)
    if row.get("alive") is False: return "dead"
    return status if status in ACTIVE | FORMER | {"candidate"} else "active"


def _entity_names(state):
    names = set()
    def add(value):
        value = text(value)
        if value: names.add(value.casefold())
    add(state.get("location"))
    for value in seq(state.get("discovered_locations")): add(value)
    for name in obj(state.get("location_details")): add(name)
    for name in obj(state.get("faction_rosters")): add(name)
    for group in obj(state.get("organizations")).values():
        if isinstance(group, dict): add(group.get("name"))
    for row in seq(state.get("political_regions")):
        if isinstance(row, dict): add(row.get("name")); add(row.get("controller"))
    return names


def _canon_people(state):
    try:
        from canon_integrity import active_canon_identities
        return {text(alias).casefold(): record for record in active_canon_identities(state.get("world"), state)
                for alias in [record.get("name"), *seq(record.get("aliases"))] if text(alias)}
    except Exception:
        return {}


def _looks_like_person(state, name, row=None, people=None, canon_people=None):
    """Reject places/factions while preserving established custom characters."""
    name = text(name)
    if not name: return False
    if name.casefold() == text(state.get("name")).casefold(): return True
    entities = _entity_names(state)
    if name.casefold() in entities: return False
    if _ENTITY_NAME_WORDS.search(name) or _GAKURE_NAME.search(name): return False
    people = people if people is not None else known_people(state)
    canon_people = canon_people if canon_people is not None else _canon_people(state)
    if name.casefold() in {text(n).casefold() for n in people}: return True
    if name.casefold() in canon_people: return True
    row = obj(row)
    # An explicit person/member record can stand alone in old custom saves, but
    # generic relationship-only records cannot manufacture a person.
    return bool(row.get("person_id") or row.get("character_id") or row.get("npc_id") or
                any(text(row.get(k)) for k in ("position", "rank", "role", "reports_to", "unit")))


def _latest_membership_evidence(state, person, group):
    """Return (is_member, text) from the latest explicit campaign evidence."""
    person_cf, group_cf = text(person).casefold(), text(group).casefold()
    latest = None
    sources = []
    for key in ("campaign_canon", "continuity_facts", "canon_changes"):
        for i, raw in enumerate(seq(state.get(key))):
            if isinstance(raw, dict):
                blob = text(raw.get("fact") or raw.get("text") or raw.get("summary") or raw.get("description"))
                order = (number(raw.get("turn"), -1), number(raw.get("canon_day"), -1), i)
            else:
                blob = text(raw); order = (-1, -1, i)
            if blob and person_cf in blob.casefold() and group_cf in blob.casefold(): sources.append((order, blob))
    # Current Chronicle/history evidence may be stored in compact fact ledgers.
    for i, raw in enumerate(seq(obj(state.get("continuity_ledger")).get("facts"))):
        blob = text(raw.get("text") if isinstance(raw, dict) else raw)
        if blob and person_cf in blob.casefold() and group_cf in blob.casefold():
            sources.append(((number(raw.get("turn"), -1) if isinstance(raw, dict) else -1, -1, i), blob))
    for order, blob in sources:
        if not (_MEMBERSHIP_POSITIVE.search(blob) or _MEMBERSHIP_NEGATIVE.search(blob)): continue
        if latest is None or order >= latest[0]: latest = (order, blob)
    if latest is None: return None, ""
    blob = latest[1]
    if _MEMBERSHIP_NEGATIVE.search(blob): return False, blob
    return bool(_MEMBERSHIP_POSITIVE.search(blob)), blob


def _member_row(state, name, memory=None, basis="Recorded campaign membership", position=""):
    memory = obj(memory)
    return {"name": name,
            "position": text(position or memory.get("position") or memory.get("rank") or memory.get("role")) or "Member",
            "status": member_status(memory), "joined_day": campaign_day(state),
            "reports_to": text(memory.get("reports_to") or memory.get("commander")),
            "unit": text(memory.get("unit") or memory.get("squad")), "membership_basis": text(basis) or "Recorded campaign membership"}


def _prune_and_recover_group(state, group, legacy_mode=False):
    """One-way repair: remove non-people, recover only affirmative real people."""
    if not isinstance(group, dict): return
    people = known_people(state); canon_people = _canon_people(state)
    members = obj(group.get("members")); group["members"] = members
    group_name = text(group.get("name"))
    player = text(state.get("name"))
    # Remove polluted entity rows and any explicitly contradicted old member.
    entity_names = _entity_names(state)
    for name in list(members):
        row = obj(members.get(name))
        # Existing ledger rows are already character records unless their name
        # is demonstrably a world entity. Do not require an NPC-memory record;
        # large crews and generated organizations may have lightweight members.
        if text(name).casefold() in entity_names or _ENTITY_NAME_WORDS.search(text(name)) or _GAKURE_NAME.search(text(name)):
            members.pop(name, None); continue
        verdict, evidence = _latest_membership_evidence(state, name, group_name)
        if verdict is False and name.casefold() != player.casefold():
            members.pop(name, None)
    if not legacy_mode: return
    candidates = {}
    for raw in seq(obj(state.get("faction_rosters")).get(group_name)):
        row = raw if isinstance(raw, dict) else {"name": raw}
        if text(row.get("name")): candidates[text(row["name"])] = row
    for name, memory in people.items():
        assigned = text(memory.get("organization") or memory.get("group") or memory.get("faction") or memory.get("team"))
        if assigned.casefold() == group_name.casefold(): candidates[name] = memory
    # Campaign evidence can recover a member even if legacy roster bookkeeping
    # omitted them (the exact failure seen in old Yahiko campaigns).
    for name, memory in people.items():
        verdict, evidence = _latest_membership_evidence(state, name, group_name)
        if verdict is True:
            row = dict(memory); row["_membership_evidence"] = evidence; candidates[name] = row
    if player:
        candidates.setdefault(player, {"name": player, "position": state.get("position") or "Member"})
    for name, candidate in candidates.items():
        name = text(name)
        if not _looks_like_person(state, name, candidate, people, canon_people): continue
        verdict, evidence = _latest_membership_evidence(state, name, group_name)
        if verdict is False: continue
        # New engine-owned campaigns require explicit confirmation; legacy
        # recovery is only for facts that predate the membership truth engine.
        if name not in members:
            strong = verdict is True or text(obj(candidate).get("organization") or obj(candidate).get("group") or obj(candidate).get("faction")).casefold() == group_name.casefold()
            # Legacy faction_roster itself is sufficient only before the truth
            # engine started; after that it is a mirror, not an authority.
            if not strong and state.get("team_membership_engine_version") == MEMBERSHIP_ENGINE_VERSION: continue
            memory = {**obj(canon_people.get(name.casefold())), **obj(people.get(name)), **obj(candidate)}
            members[name] = _member_row(state, name, memory, evidence or "Recovered from established pre-engine membership")


def _pending_offers(state):
    rows = state.get("team_membership_offers")
    if not isinstance(rows, list): rows = state["team_membership_offers"] = []
    return rows


def _queue_offer(state, kind, group, person, reason, members=None, leader="", title="", prompt=""):
    group, person = text(group), text(person)
    if not group or not person: return None
    gid = group_id(group)
    current = obj(obj(state.get("organizations")).get(gid)).get("members", {})
    if kind == "recruit" and any(text(n).casefold() == person.casefold() and obj(r).get("status") in ACTIVE for n, r in obj(current).items()): return None
    for row in _pending_offers(state):
        if isinstance(row, dict) and row.get("status") == "pending" and text(row.get("kind")) == kind and text(row.get("group")).casefold() == group.casefold() and text(row.get("person")).casefold() == person.casefold():
            return row
    ident = fingerprint(f"membership|{state.get('campaign_id')}|{state.get('turn')}|{kind}|{group}|{person}|{reason}")[:20]
    row = {"id": ident, "kind": kind, "group": group, "person": person, "reason": text(reason)[:900],
           "status": "pending", "requires_player_choice": True, "created_turn": state.get("turn", 0),
           "created_day": state.get("canon_day", 0)}
    if members: row["members"] = copy.deepcopy(members)
    if leader: row["leader"] = text(leader)
    if title: row["title"] = text(title)
    if prompt: row["prompt"] = text(prompt)
    _pending_offers(state).append(row)
    state["team_membership_offers"] = state["team_membership_offers"][-30:]
    return row


def _exact_group(state, name):
    ensure_organizations(state)
    return next((g for g in obj(state.get("organizations")).values() if isinstance(g, dict) and text(g.get("name")).casefold() == text(name).casefold()), None)


def resolve_membership_offer(state, offer_id, decision):
    offer = next((r for r in _pending_offers(state) if isinstance(r, dict) and text(r.get("id")) == text(offer_id)), None)
    if not offer or offer.get("status") != "pending": raise ValueError("That team membership decision is no longer pending.")
    accepted = text(decision).casefold() in {"accept", "accepted", "yes", "join", "recruit"}
    if not accepted:
        offer.update(status="declined", resolved_turn=state.get("turn", 0))
        return f"Membership in {offer['group']} was declined."
    group_name = text(offer.get("group")); gid = group_id(group_name)
    groups = ensure_organizations(state)
    group = groups.setdefault(gid, {"id": gid, "name": group_name, "kind": "", "leader": text(offer.get("leader")), "members": {}, "history": []})
    members = group.setdefault("members", {})
    if offer.get("kind") == "naruto_squad":
        for raw in seq(offer.get("members")):
            row = raw if isinstance(raw, dict) else {"name": raw}
            name = text(row.get("name"))
            if not name: continue
            members[name] = _member_row(state, name, row, offer.get("reason"), row.get("position"))
        if text(offer.get("leader")): group["leader"] = text(offer["leader"])
        state["official_party_group_id"] = gid
        assignment = obj(state.get("naruto_squad_assignment")); assignment["status"] = "accepted"; assignment["group"] = group_name; state["naruto_squad_assignment"] = assignment
    else:
        person = text(offer.get("person"))
        memory = obj(known_people(state).get(person)) if person.casefold() != text(state.get("name")).casefold() else state
        members[person] = _member_row(state, person, memory, offer.get("reason"))
        if person.casefold() == text(state.get("name")).casefold(): state["official_party_group_id"] = gid
    offer.update(status="accepted", resolved_turn=state.get("turn", 0))
    history(group, state, "join", text(offer.get("person")), offer.get("reason") or "Player-confirmed membership")
    sync_memberships(state, groups)
    return f"Official membership in {group_name} was confirmed."


def resolve_direct_player_join(state, group_name, decision):
    group = _exact_group(state, group_name)
    if not group: raise ValueError("That organization is not established in this campaign.")
    if text(decision).casefold() not in {"accept", "accepted", "yes", "join"}:
        return f"You did not join {group['name']}."
    player = text(state.get("name")); members = group.setdefault("members", {})
    existing = next((n for n in members if n.casefold() == player.casefold()), player)
    members[existing] = {**obj(members.get(existing)), **_member_row(state, player, state, "Player-confirmed direct join")}
    members[existing]["status"] = "active"
    state["official_party_group_id"] = group.get("id") or group_id(group.get("name"))
    history(group, state, "join", player, "Player explicitly confirmed joining this established team.")
    sync_memberships(state, state["organizations"])
    return f"You officially joined {group['name']}."


def authoritative_active_rosters(state):
    view = roster_view(state)
    return {g["name"]: [r["name"] for r in g["members"] if r.get("status") in ACTIVE] for g in view.get("groups", [])}


def _rank_text(state):
    special = obj(state.get("special")); profile = obj(special.get("Shinobi Profile"))
    return text(state.get("rank") or state.get("position") or profile.get("rank") or special.get("Shinobi Rank") or special.get("Rank"))


def _schedule_naruto_squad(before, state):
    if state.get("world") != "Naruto": return
    before_rank, now_rank = _rank_text(before).casefold(), _rank_text(state).casefold()
    assignment = state.get("naruto_squad_assignment") if isinstance(state.get("naruto_squad_assignment"), dict) else None
    if assignment is None and ("academy" in before_rank and "student" in before_rank) and "genin" in now_rank:
        due = int(number(state.get("canon_day"))) + NARUTO_SQUAD_DELAY_DAYS
        assignment = {"status":"scheduled", "graduated_day":int(number(state.get("canon_day"))), "due_day":due}
        state["naruto_squad_assignment"] = assignment
        events = state.setdefault("scheduled_events", [])
        if not any(isinstance(e, dict) and e.get("kind") == "ninja_squad_assignment" and not e.get("resolved") for e in events):
            events.append({"title":"Ninja squad assignment", "kind":"ninja_squad_assignment", "due_canon_day":due,
                           "location":state.get("location"), "visibility":"visible", "resolved":False})


def _naruto_squad_offer(state):
    assignment = obj(state.get("naruto_squad_assignment"))
    if state.get("world") != "Naruto" or assignment.get("status") != "scheduled" or number(state.get("canon_day")) < number(assignment.get("due_day"), 10**9): return None
    player = text(state.get("name")); low = player.casefold()
    canon = {
        "naruto": ("Team 7", ["Naruto", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake"], "Kakashi Hatake"),
        "naruto uzumaki": ("Team 7", ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake"], "Kakashi Hatake"),
        "sasuke uchiha": ("Team 7", ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake"], "Kakashi Hatake"),
        "sakura haruno": ("Team 7", ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake"], "Kakashi Hatake"),
    }
    if low in canon:
        group, names, leader = canon[low]
    else:
        seed = int(fingerprint(f"{state.get('campaign_id')}|{player}|squad")[:8], 16)
        number_id = 1 + seed % 20; group = f"Genin Squad {number_id}"
        names = [player, f"Genin Teammate {chr(65 + seed % 12)}", f"Genin Teammate {chr(78 + seed % 10)}", f"Jonin Instructor {1 + seed % 9}"]
        leader = names[-1]
    members = [{"name": n, "position": "Jōnin Instructor" if n == leader else "Genin"} for n in names]
    offer = _queue_offer(state, "naruto_squad", group, player,
                         f"Your academy graduation has reached its scheduled ninja-squad assignment {NARUTO_SQUAD_DELAY_DAYS} days later.",
                         members=members, leader=leader, title=f"Join {group}?",
                         prompt=f"You have been assigned to {group}. Accepting makes this your official Party/Team display.")
    if offer: assignment["status"] = "offered"; assignment["offer_id"] = offer["id"]; state["naruto_squad_assignment"] = assignment
    return offer


def _membership_updates_to_offers(state, data):
    """GM may establish an opportunity; the engine owns the actual join."""
    filtered = []
    player = text(state.get("name"))
    for event in seq(data.get("organization_updates")):
        if not isinstance(event, dict): continue
        action = text(event.get("event")).casefold(); group = text(event.get("group")); person = text(event.get("name"))
        if action == "join" and group and person and event.get("accepted") is True:
            kind = "join_team" if person.casefold() == player.casefold() else "recruit"
            _queue_offer(state, kind, group, person, event.get("reason") or f"{person} agreed to join {group}.")
            continue
        filtered.append(event)
    data["organization_updates"] = filtered
    narrative = text(data.get("narrative"))
    if not narrative: return
    groups = [g for g in obj(state.get("organizations")).values() if isinstance(g, dict) and text(g.get("name"))]
    people = known_people(state)
    for group in groups:
        gname = text(group.get("name"))
        if gname.casefold() not in narrative.casefold(): continue
        for name in people:
            if name.casefold() not in narrative.casefold() or name in obj(group.get("members")): continue
            # Require affirmative person+group language and no refusal/qualified nonmembership.
            sentences = [x.strip() for x in re.split(r"(?<=[.!?])\\s+", narrative) if name.casefold() in x.casefold() and gname.casefold() in x.casefold()]
            evidence = next((x for x in reversed(sentences) if _MEMBERSHIP_POSITIVE.search(x) or _MEMBERSHIP_NEGATIVE.search(x)), "")
            if evidence and _MEMBERSHIP_POSITIVE.search(evidence) and not _MEMBERSHIP_NEGATIVE.search(evidence):
                _queue_offer(state, "recruit", gname, name, evidence)


def _merge_legacy_memberships(state, source=None):
    """Migrate old saves once, then stop treating mirrors as authorities."""
    source = source if isinstance(source, dict) else state
    # Work from current ledger plus the old save's explicit evidence.
    if source is not state:
        for key in ("faction_rosters", "campaign_canon", "npc_memories", "companions", "affiliations", "location_details"):
            if key not in state and key in source: state[key] = copy.deepcopy(source[key])
    ensure_organizations(state, legacy_mode=True)
    state["team_membership_engine_version"] = MEMBERSHIP_ENGINE_VERSION
    state.setdefault("team_membership_truth_started_turn", state.get("turn", 0))
    sync_memberships(state, state["organizations"])


def ensure_organizations(state, legacy_mode=False):
    """Add/repair memberships; omissions/proximity never remove members."""
    groups = state.get("organizations")
    if not isinstance(groups, dict): groups = state["organizations"] = {}
    for gid, group in list(groups.items()):
        if not isinstance(group, dict):
            groups.pop(gid)
            continue
        group.setdefault("id", gid)
        group.setdefault("name", "Unnamed group")
        group["members"] = {text(n): row for n, row in obj(group.get("members")).items() if text(n) and isinstance(row, dict)}
        group["history"] = seq(group.get("history"))
    player = text(state.get("name"))
    people = known_people(state)
    canon_people = None
    discovered = {}
    for raw in seq(state.get("affiliations")):
        row = raw if isinstance(raw, dict) else {"name": raw}
        name = text(row.get("name") or row.get("faction") or row.get("organization"))
        if name and member_status(row) in ACTIVE:
            discovered[name] = row
    for name, roster in obj(state.get("faction_rosters")).items():
        names = [text(r.get("name") if isinstance(r, dict) else r) for r in seq(roster)]
        if player and player.casefold() in [n.casefold() for n in names]: discovered.setdefault(name, {})
    for raw in seq(state.get("companions")):
        if isinstance(raw, dict):
            name = text(raw.get("group") or raw.get("organization"))
            if name: discovered.setdefault(name, {})
    if not discovered and seq(state.get("companions")) and not groups:
        discovered["Unnamed group"] = {"provisional": True}
    for name, info in discovered.items():
        gid = group_id(name)
        initial_membership = gid not in groups
        group = groups.setdefault(gid, {"id": gid, "name": name, "members": {}, "history": [], "leader": "",
                                        "kind": info.get("kind", ""), "provisional": bool(info.get("provisional"))})
        members = group.setdefault("members", {})
        if not isinstance(members, dict): members = group["members"] = {}
        roster = seq(obj(state.get("faction_rosters")).get(name))
        candidates = [r if isinstance(r, dict) else {"name": r} for r in roster]
        if player: candidates.insert(0, {"name": player, "position": info.get("rank") or info.get("role") or state.get("position") or "Member"})
        for raw in seq(state.get("companions")):
            row = raw if isinstance(raw, dict) else {"name": raw}
            assigned = text(row.get("group") or row.get("organization"))
            if assigned == name or (not assigned and len(discovered) == 1): candidates.append(row)
        for candidate in candidates:
            member_name = text(candidate.get("name"))
            if not member_name: continue
            member_name = next((n for n in members if n.casefold() == member_name.casefold()), member_name)
            if member_name not in members and not initial_membership: continue
            if member_name not in members and canon_people is None:
                from canon_integrity import active_canon_identities
                canon_people = {text(alias).casefold(): record for record in active_canon_identities(state.get("world"), state)
                                for alias in [record.get("name"), *seq(record.get("aliases"))] if text(alias)}
            memory = {**obj(obj(canon_people).get(member_name.casefold())), **obj(people.get(member_name)), **candidate}
            if member_name not in members:
                members[member_name] = {"name": member_name, "position": text(memory.get("position") or memory.get("rank") or memory.get("role")) or "Member",
                    "status": member_status(memory), "joined_day": campaign_day(state), "reports_to": text(memory.get("reports_to") or memory.get("commander")),
                    "unit": text(memory.get("unit") or memory.get("squad")), "membership_basis": "Recorded campaign membership"}
                for key in ("independent", "motivation", "terms", "commitments", "loyalty_basis"):
                    if key in memory: members[member_name][key] = copy.deepcopy(memory[key])
                if memory.get("subordinate") is True and not members[member_name]["reports_to"]:
                    members[member_name]["reports_to"] = player
            # Current facts can mark a member absent/dead, but stale roster rows
            # must never resurrect a former member or undo an explicit departure.
            current_status = member_status(obj(people.get(member_name)))
            if current_status in FORMER: members[member_name]["status"] = current_status
            if not group.get("leader") and re.fullmatch(r"captain|leader|guild master|commander|founder|ruler", members[member_name]["position"], re.I):
                group["leader"] = member_name
    # Apply current known deaths even to groups no longer in the nearby party.
    for group in groups.values():
        if not isinstance(group, dict): continue
        for name, member in obj(group.get("members")).items():
            if not isinstance(member, dict): continue
            memory = obj(people.get(name))
            if memory and member_status(memory) in FORMER: member["status"] = member_status(memory)
            if name == player and state.get("alive") is False: member["status"] = "dead"
    for group in groups.values():
        if isinstance(group, dict): _prune_and_recover_group(state, group, legacy_mode=legacy_mode)
    state["organization_lives"] = {text(n): row for n, row in obj(state.get("organization_lives")).items() if isinstance(row, dict)}
    return groups


def command_chain(group, name, player):
    members = obj(group.get("members")); path = []; seen = set()
    while name and name not in seen and name in members:
        seen.add(name)
        row = obj(members[name])
        if row.get("status") not in ACTIVE or row.get("status") == "missing": return []
        if row.get("independent") is True: return []
        if name == player: return list(reversed(path))
        path.append(name)
        parent = text(row.get("reports_to")) or text(group.get("leader"))
        name = player if parent in {"player", "the player"} else parent
    return []


def organization_commands(state, query):
    if not re.search(r"\b(order|command|instruct|tell|direct|assign|have|ask)\b", query, re.I): return []
    groups = ensure_organizations(state); player = text(state.get("name")); result = []
    recent = obj(state.get("last_command_context"))
    referents = seq(recent.get("actors")) if 0 <= number(state.get("turn"))-number(recent.get("turn"), -100) <= 2 else []
    if not re.search(r"\bthem\b", query, re.I) and len(referents) != 1: referents = []
    followup = bool(re.search(r"\b(?:her|him|them)\b", query, re.I))
    explicit_names = {name for group in groups.values() for name in obj(group.get("members"))
                      if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", query, re.I)}
    for group in groups.values():
        if not isinstance(group, dict): continue
        label = label_for(state.get("world"), group.get("name", ""), group.get("kind", ""))
        generic = re.search(r"\bmy (crew|squad|organization|guild|retainers|team)\b", query, re.I)
        whole = text(group.get("name")).casefold() in query.casefold() or bool(generic and (generic[1].casefold() in label.casefold() or len(groups) == 1))
        for name, member in obj(group.get("members")).items():
            if not isinstance(member, dict) or name == player: continue
            unit = text(member.get("unit"))
            selected = whole or name in explicit_names or (unit and unit.casefold() in query.casefold()) or (followup and not explicit_names and name in referents)
            if not selected: continue
            chain = command_chain(group, name, player)
            if not chain: continue
            result.append({"actor": name, "order": query[:900], "group": group["name"], "group_type": label,
                "via": chain[:-1], "basis": "established organizational command chain",
                "default": "Preserve the objective, constraints and duration through this command chain; use real communication, not telepathy.",
                "exceptions": "Only established inability, conflicting duty, or ambiguity; ordinary disagreement does not replace the command."})
    return result


def power_for(state, name, member=None, people=None):
    world = state.get("world", "Custom World")
    player = name == state.get("name")
    memory = state if player else obj((people if people is not None else known_people(state)).get(name))
    if not player and (memory.get("power_hidden") or memory.get("power_known") is False):
        return {"label": "Not assessed", "score": None, "source": "Hidden or unobserved capability", "estimated": True}
    stats = obj(memory.get("stats"))
    score = None; source = ""; estimated = not player
    if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in stats.values()):
        profile = power_profile_for(world, stats, memory.get("archetype", ""))
        score = obj(profile.get("world_combat") or profile.get("combat")).get("score")
        source = "Character sheet" if player else "Recorded combat attributes"; estimated = False
    elif isinstance(memory.get("power_score"), (int, float)):
        score = number(memory["power_score"]); source = "Campaign estimate"
    if score is None:
        from engine_social import _role_power_estimate, LOCAL_CANON_POWER_ESTIMATES
        from canon_integrity import active_canon_identities
        role = " ".join(text(memory.get(k)) for k in ("rank", "role", "combat_tier"))
        score = _role_power_estimate(world, role); source = "Recorded role estimate"
        if score is None:
            for record in active_canon_identities(world, state):
                aliases = [record.get("name"), *seq(record.get("aliases"))]
                if name.casefold() in [text(a).casefold() for a in aliases]:
                    score = _role_power_estimate(world, " ".join(text(record.get(k)) for k in ("role", "rank", "position")))
                    source = "Current-era canon role estimate"; break
            if score is None:
                candidates = [(alias, value) for alias, value in LOCAL_CANON_POWER_ESTIMATES.get(world, {}).items()
                              if alias.casefold() == name.casefold()]
                if candidates:
                    score = max(candidates, key=lambda pair: len(pair[0]))[1]; source = "Canon baseline estimate"
    if score is None:
        return {"label": "Not assessed", "score": None, "source": "No observed combat benchmark yet", "estimated": True}
    tier = benchmark_tier(world, score)
    return {"label": tier["name"], "score": tier["score"], "source": source, "estimated": estimated}


def history(group, state, event, name, reason):
    row = {"turn": state.get("turn", 0), "day": state.get("canon_day"), "event": event, "name": name, "reason": reason}
    rows = group.setdefault("history", [])
    if row not in rows: rows.append(row)
    group["history"] = rows[-160:]


def sync_memberships(state, groups):
    """One source for organizational roles; keep legacy prompt fields consistent."""
    state["faction_rosters"] = obj(state.get("faction_rosters"))
    for group in groups.values():
        if group.get("provisional"): continue
        members = obj(group.get("members"))
        state["faction_rosters"][group["name"]] = [name for name, row in members.items() if obj(row).get("status") in ACTIVE]
        player = obj(members.get(text(state.get("name"))))
        if not player: continue
        affiliations = seq(state.get("affiliations"))
        affiliation = next((r for r in affiliations if isinstance(r, dict) and text(r.get("faction") or r.get("name")).casefold() == group["name"].casefold()), None)
        if affiliation is None:
            affiliation = {"faction": group["name"]}; affiliations.append(affiliation)
        affiliation.update(rank=player.get("position", "Member"), status="active" if player.get("status") in ACTIVE else "former")
        state["affiliations"] = affiliations


def organization_issues(state, data):
    if not seq(data.get("organization_updates")): return []
    groups = ensure_organizations(membership_copy(state)); issues = []
    for event in seq(data.get("organization_updates")):
        if not isinstance(event, dict): continue
        if not text(event.get("reason")): issues.append("Organizational changes require an established narrative reason.")
        action = event.get("event")
        group = groups.get(group_id(event.get("group", "")), {})
        if action == "join" and event.get("accepted") is not True:
            issues.append("Joining requires agreement; an invitation alone creates a candidate, not a member.")
        if action == "succession_plan" and event.get("accepted") is not True:
            issues.append("A successor must accept before a succession plan takes effect.")
        if action == "succession_plan" and text(event.get("name")) not in obj(group.get("members")):
            issues.append("Choose an established member as successor; do not invent a replacement.")
        if action == "retire" and event.get("name") == state.get("name") and event.get("accepted") is not True:
            issues.append("The player's retirement must be explicitly voluntary and accepted, never automatic.")
        if action == "development" and not text(event.get("activity")):
            issues.append("NPC development needs a concrete ongoing activity, not player-level scaling.")
        if action == "development" and event.get("rate") == "exceptional" and not text(event.get("method")):
            issues.append("Exceptional NPC growth requires an established accelerated method.")
    return issues


def apply_updates(state, data, interval_start=None):
    groups = ensure_organizations(state)
    for event in seq(data.get("organization_updates"))[:100]:
        if not isinstance(event, dict) or not text(event.get("reason")): continue
        group_name = text(event.get("group")); gid = group_id(group_name); action = event.get("event")
        if not group_name: continue
        if action == "establish":
            if gid not in groups:
                groups[gid] = {"id": gid, "name": group_name, "kind": text(event.get("kind")), "leader": text(event.get("leader")), "members": {}, "history": []}
                groups[gid]["members"][text(state.get("name"))] = {"name": state.get("name"), "position": text(event.get("position")) or ("Leader" if event.get("leader") == state.get("name") else "Member"), "status": "active", "joined_day": state.get("canon_day", 0)}
            history(groups[gid], state, action, state.get("name"), event["reason"])
            continue
        group = groups.get(gid)
        if not isinstance(group, dict): continue
        name = text(event.get("name")); members = group.setdefault("members", {})
        name = next((n for n in members if n.casefold() == name.casefold()), name)
        if not name: continue
        row = obj(members.get(name))
        if action in {"invite", "join", "birth"}:
            if action == "join" and event.get("accepted") is not True: continue
            if action == "invite" and row.get("status") in ACTIVE: continue
            # A dead member never returns through a routine recruitment event.
            if row.get("status") in {"dead", "deceased"}: continue
            row = members.setdefault(name, {"name": name, "joined_day": state.get("canon_day", 0)})
            row.update(status="candidate" if action == "invite" else "active",
                       position=text(event.get("position")) or ("Dependent" if action == "birth" else row.get("position", "Member")),
                       membership_basis=text(event["reason"]))
            memories = state.setdefault("npc_memories", {})
            if not isinstance(memories.get(name), dict): memories[name] = {}
            memory = memories[name]
            if action == "birth":
                if name in state["organization_lives"] and state["organization_lives"][name].get("birth_recorded"): continue
                memory["age"] = 0
                life = state["organization_lives"].setdefault(name, {})
                life.update(age_anchor_day=number(state.get("canon_day")), age_anchor_value=0, stage="child", birth_recorded=True)
                for key in ("parents", "aging_mode"):
                    if key in event: life[key] = copy.deepcopy(event[key])
        elif not row: continue
        elif action in {"leave", "retire", "expel", "death", "away", "return"}:
            if action == "retire" and name == state.get("name") and event.get("accepted") is not True: continue
            if row.get("status") in {"dead", "deceased"}: continue
            if action == "return" and row.get("status") not in {"away", "missing"}: continue
            row["status"] = {"leave": "left", "retire": "retired", "expel": "expelled", "death": "dead", "away": "away", "return": "active"}[action]
            if row["status"] in FORMER:
                row["departure_reason"] = event["reason"]
                # Membership ends here, not every independent relationship.
                state["companions"] = [c for c in seq(state.get("companions")) if text(c.get("name") if isinstance(c, dict) else c).casefold() != name.casefold()]
            if action == "death":
                memories = state.setdefault("npc_memories", {})
                memories[name] = {**obj(memories.get(name)), "alive": False, "status": "dead"}
        elif action == "position":
            row["position"] = text(event.get("position")) or row.get("position", "Member")
        elif action == "succession_plan":
            if event.get("accepted") is not True or row.get("status") not in ACTIVE: continue
            group["succession"] = {"successor": name, "accepted": True, "trigger": "leader death or explicit retirement", "reason": event["reason"]}
        elif action == "development":
            if not text(event.get("activity")): continue
            life = state["organization_lives"].setdefault(name, {})
            life["development"] = {k: copy.deepcopy(event[k]) for k in ("activity", "discipline", "mentor", "rate", "method", "active") if k in event}
            life["development"]["started_day"] = number(interval_start, number(state.get("canon_day")))
        elif action == "life":
            life = state["organization_lives"].setdefault(name, {})
            for key in ("parents", "mentor", "stage", "aging_mode", "maturity_age"):
                if key in event: life[key] = copy.deepcopy(event[key])
        else: continue
        for key in ("reports_to", "unit", "independent", "motivation", "terms", "commitments", "loyalty_basis"):
            if key in event: row[key] = copy.deepcopy(event[key])
        if action in {"position", "join"} and event.get("leader") == name:
            group["leader"] = name
        history(group, state, action, name, event["reason"])
    # The legacy membership field remains useful to existing GM/map systems.
    sync_memberships(state, groups)


def advance_lives(state, elapsed_minutes, before=None):
    groups = ensure_organizations(state); people = known_people(state)
    end = campaign_day(state); elapsed_days = max(0, number(elapsed_minutes) / 1440)
    lives = state["organization_lives"]; notices = []
    members = {}
    for group in groups.values():
        for name, row in obj(group.get("members")).items():
            if name not in members or row.get("status") in ACTIVE: members[name] = row
    for name, member in members.items():
        if name == state.get("name") or member.get("status") in {"candidate", "dead", "deceased"}: continue
        memories = state.setdefault("npc_memories", {})
        if not isinstance(memories.get(name), dict): memories[name] = dict(obj(people.get(name)))
        memory = memories[name]
        for key in ("age", "stats", "power_score", "training", "goal", "condition"):
            if key not in memory and key in obj(people.get(name)): memory[key] = copy.deepcopy(people[name][key])
        life = lives.setdefault(name, {})
        start = max(number(life.get("last_day"), end-elapsed_days), end-elapsed_days, number(member.get("joined_day"), end-elapsed_days))
        days = max(0, end-start); life["last_day"] = max(end, number(life.get("last_day"), end))
        age = numeric_age(memory.get("age"))
        if age is not None:
            if "last_published_age" in life and life["last_published_age"] != age:
                life.update(age_anchor_day=end, age_anchor_value=age)
            if "age_anchor_day" not in life:
                life.update(age_anchor_day=start, age_anchor_value=age)
            chronological = int(life["age_anchor_value"]) + int(max(0, end-number(life["age_anchor_day"])) // 360)
            life["chronological_age"] = chronological
            mode = life.get("aging_mode") or memory.get("aging_mode", "mortal")
            if mode not in {"ageless", "immortal", "spiritual", "arrested"}: memory["age"] = chronological
            life["last_published_age"] = memory["age"]
            if life.get("stage") == "child" and number(life.get("maturity_age")) > 0 and memory["age"] >= number(life["maturity_age"]):
                life["stage"] = "adult"
        development = obj(life.get("development"))
        # Existing narrative training directives are also usable, without inventing a job.
        activity = text(development.get("activity")) or text(memory.get("training") or memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"))
        if member.get("status") not in {"active", "away"} or development.get("active") is False: continue
        if not re.search(r"\b(train|practice|study|learn|research|apprentice)\w*\b", activity, re.I): continue
        if re.search(r"\b(unconscious|critical|incapacitated)\b", text(memory.get("condition")), re.I): continue
        effective_days = min(days, max(0, end-number(development.get("started_day"), start)))
        credit = number(life.get("training_days")) + effective_days
        months = int((credit + 1e-8) // 30); life["training_days"] = max(0, credit - months * 30)
        if not months: continue
        discipline = text(development.get("discipline"))
        if not discipline:
            discipline = next((key for key in abilities_for(state.get("world", "Custom World")) if key.casefold() in activity.casefold()), "")
        stat_key = next((key for key in abilities_for(state.get("world", "Custom World")) if key.casefold() == discipline.casefold()), None)
        rate = 1.5 if development.get("rate") == "focused" else 1
        if development.get("rate") == "exceptional" and text(development.get("method")): rate = 3
        if text(development.get("mentor")) in people: rate *= 1.2
        if re.search(r"injur|wound|recover", text(memory.get("condition")), re.I): rate *= .5
        gain = 0.0
        if stat_key and isinstance(obj(memory.get("stats")).get(stat_key), (int, float)):
            old = number(memory["stats"][stat_key]); value = old
            prior = obj(obj(obj(before).get("npc_memories")).get(name))
            baseline = obj(prior.get("stats")).get(stat_key)
            if isinstance(baseline, (int, float)) and 0 <= baseline <= old: value = baseline
            for _ in range(min(months, 1200)): value = round(value + max(.25, math.sqrt(max(0, value)+16)/4)*rate, 2)
            value = max(old, value)
            memory["stats"][stat_key] = round(value, 2); gain = value-old
        elif discipline.casefold() == "combat" and isinstance(memory.get("power_score"), (int, float)):
            old = number(memory["power_score"]); value = old
            baseline = obj(obj(obj(before).get("npc_memories")).get(name)).get("power_score")
            if isinstance(baseline, (int, float)) and 0 <= baseline <= old: value = baseline
            for _ in range(min(months, 1200)): value = round(value + max(.25, math.sqrt(max(0, value)+16)/4)*rate, 2)
            value = max(old, value)
            memory["power_score"] = round(value, 2); gain = value-old
        expertise = life.setdefault("expertise", {})
        key = discipline or activity[:80]; expertise[key] = round(number(expertise.get(key)) + months*rate, 1)
        life.setdefault("history", []).append({"day": end, "activity": activity, "discipline": discipline, "months": months, "gain": round(gain, 2)})
        life["history"] = life["history"][-40:]
        for companion in seq(state.get("companions")):
            if isinstance(companion, dict) and text(companion.get("name")).casefold() == name.casefold():
                for key in ("stats", "power_score", "age"):
                    if key in memory: companion[key] = copy.deepcopy(memory[key])
        # No omniscient off-screen Chronicle notification. The next report or
        # conversation may reveal this ordinary development through real contact.
    for group in groups.values():
        if not isinstance(group, dict): continue
        leader = text(group.get("leader")); plan = obj(group.get("succession")); heir = text(plan.get("successor"))
        roster = obj(group.get("members")); previous = obj(roster.get(leader)); successor = obj(roster.get(heir))
        if not leader or not heir or not plan.get("accepted") or previous.get("status") not in {"retired", "dead", "deceased"}: continue
        if successor.get("status") not in {"active", "away"} or heir == leader: continue
        successor["position"] = previous.get("position", "Leader"); successor["reports_to"] = ""
        group["leader"] = heir
        for name, row in roster.items():
            if isinstance(row, dict) and name != heir and row.get("reports_to") == leader: row["reports_to"] = heir
        history(group, state, "succession", heir, f"Succeeded {leader} under the accepted succession plan.")
        group["succession"] = {}
        notices.append({"type": "organization", "title": f"{group['name']}: succession", "narrative": f"Under the agreed succession, {heir} takes over {leader}'s position in {group['name']}.", "importance": 65})
    sync_memberships(state, groups)
    return notices


def process_organizations(before, state, data, elapsed_minutes=0):
    """Shared post-turn hook and sole authority for official membership."""
    # Freeze all pre-engine facts into the official ledger once. This is how
    # old campaigns recover real recruits without asking the player to rejoin.
    if state.get("team_membership_engine_version") != MEMBERSHIP_ENGINE_VERSION:
        _merge_legacy_memberships(state, before if before.get("world") == state.get("world") else state)
    else:
        ensure_organizations(state)
    _schedule_naruto_squad(before, state)
    _membership_updates_to_offers(state, data)
    apply_updates(state, data, campaign_day(before))
    _naruto_squad_offer(state)
    notices = advance_lives(state, elapsed_minutes, before)
    actions = []
    for key in ("completed_actions", "deferred_actions"):
        actions.extend(text(x) for x in seq(data.get(key)) if text(x))
    if text(data.get("narrative")): actions.append(text(data.get("narrative")))
    try:
        from character_paths import record_turn
        record_turn(before, state, actions, elapsed_minutes)
    except Exception:
        pass
    try:
        from world_conflict import refresh as refresh_world_conflict
        refresh_world_conflict(state, elapsed_minutes)
    except Exception:
        pass
    try:
        from reputation_system import sync as sync_reputation, advance as advance_reputation
        sync_reputation(before, state, source=text(data.get("narrative")), events=seq(data.get("events")))
        advance_reputation(state, elapsed_minutes)
    except Exception:
        pass
    try:
        from property_economy import bootstrap_established_holdings, advance as advance_property_economy
        bootstrap_established_holdings(state); advance_property_economy(state, elapsed_minutes)
    except Exception:
        pass
    try:
        from organization_command import advance as advance_organization_command
        advance_organization_command(state, elapsed_minutes)
    except Exception:
        pass
    return notices

def roster_view(state):
    local = membership_copy(state); groups = ensure_organizations(local, legacy_mode=True); output = []
    people = known_people(local)
    for group in groups.values():
        if not isinstance(group, dict): continue
        rows = []
        for name, raw in obj(group.get("members")).items():
            if not isinstance(raw, dict): continue
            life = obj(obj(local.get("organization_lives")).get(name)); memory = obj(people.get(name))
            rows.append({"name": name, "position": raw.get("position", "Member"), "status": raw.get("status", "active"),
                         "independent": raw.get("independent") is True,
                         "unit": raw.get("unit", ""), "reports_to": raw.get("reports_to", ""), "player": name == local.get("name"),
                         "power": power_for(local, name, raw, people), "age": memory.get("age", ""),
                         "notes": text(memory.get("notes")), "reason": raw.get("departure_reason") or (raw.get("membership_basis", "") if raw.get("membership_basis") != "Recorded campaign membership" else ""),
                         "terms": raw.get("terms", ""), "loyalty_basis": raw.get("loyalty_basis", ""),
                         "stage": life.get("stage", ""), "mentor": life.get("mentor", ""), "parents": life.get("parents", [])})
        rows.sort(key=lambda r: (r["status"] in FORMER, not r["player"], r["name"].casefold()))
        output.append({"id": group.get("id"), "name": group.get("name"), "type": label_for(local.get("world"), group.get("name", ""), group.get("kind", "")),
                       "leader": group.get("leader", ""), "members": rows, "history": seq(group.get("history"))[-12:],
                       "successor": obj(group.get("succession")).get("successor", "")})
    official = text(local.get("official_party_group_id"))
    if official: output.sort(key=lambda g: (text(g.get("id")) != official, text(g.get("name")).casefold()))
    label = output[0]["type"] if len(output) == 1 else "Groups" if output else LABELS.get(state.get("world"), "Company")
    return {"label": label, "groups": output, "official_group_id": official, "source": "canonical_organization_ledger_v2"}


def organization_context(state, query=""):
    view = roster_view(state)
    selected = sorted(view["groups"], key=lambda g: (g["name"].casefold() not in query.casefold(),
                      not any(r["name"].casefold() in query.casefold() for r in g["members"])))[:6]
    return {"groups": [{"name": g["name"], "type": g["type"], "leader": g["leader"], "successor": g["successor"],
                        "member_count": len(g["members"]), "members": [
                            {k: (v[:300] if isinstance(v, str) else v) for k, v in r.items() if k not in {"notes", "reason"}}
                            for r in sorted(g["members"], key=lambda r: (r["name"].casefold() not in query.casefold(), not r["player"]))[:16]]} for g in selected],
            "life_development": {name: {k: copy.deepcopy(v[-4:] if k == "history" and isinstance(v, list) else v) for k, v in obj(row).items()}
                                 for name, row in list(obj(state.get("organization_lives")).items())[:100] if name.casefold() in query.casefold()}}


def _install_shared_membership_truth():
    """Give every GM/Advisor task the same official roster used by the UI."""
    try:
        from engine_core import CoreMixin
    except Exception:
        return
    original = getattr(CoreMixin, "task_state_for_ai", None)
    if not callable(original) or getattr(original, "_membership_truth_v2", False): return
    def task_state_for_ai(self, purpose="moment", query=""):
        result = original(self, purpose, query)
        if isinstance(result, dict):
            result["organization_roster"] = organization_context(self.state, query)
            result["faction_rosters"] = authoritative_active_rosters(self.state)
            result["organization_membership_rule"] = "organization_roster is authoritative for official membership; do not infer members from relationships, contacts, places, faction names or contradictory old prose."
            try:
                from canon_divergence import gm_context
                target_context = gm_context(self.state)
                if target_context: result["player_canon_intervention_targets"] = target_context
            except Exception:
                pass
        return result
    task_state_for_ai._membership_truth_v2 = True
    CoreMixin.task_state_for_ai = task_state_for_ai


_install_shared_membership_truth()


ORGANIZATION_RULE = """
ORGANIZATIONS AND LIVES: Membership is permanent until a real membership event, independent of proximity. Return organization_updates for established changes: group, event, name, reason and event-specific fields. Establish a named world-appropriate group with event=establish, kind and leader; do not create a crew/guild merely because someone met the player. Invite creates a candidate; join requires accepted=true and actual agreement. Positions, reports_to and unit express authority, never friendship or combat strength. Independent allies retain agency; subordinates preserve commands through their chain and actual communication.
Use event=position for rank/role changes; leave/retire/expel/death/away/return only when narratively established. Do not manufacture betrayal, departure, death, retirement or a crisis to fill a quota. Off-screen members train through development {activity, discipline, mentor, rate:routine|focused|exceptional, method, active}; discipline is an actual world stat or 'combat', and exceptional growth requires a real method. Noncombat expertise must not inflate combat power. No automatic matching to player stats, generic skill awards or fixed promotion trees.
Birth and life events preserve family, mentor, stage, aging_mode (mortal|ageless|immortal|spiritual|arrested) and maturity_age where known. Unknown ages stay unknown; no forced old-age death or compulsory retirement. Children and apprentices develop over actual elapsed time; no inherited mastery without learning. Succession_plan requires an established member and accepted=true; only a recorded death or voluntary retirement activates it. It changes the organization, never replaces the player's character. Public rosters show everyone associated, but hidden powers and distant secret activity are not revealed. Report developments through actual contact. NPC power_score/stats are same-world current estimates, never political rank alone.
"""
