"""Local simulation integrity systems used by v3.4.

Nothing in this module calls a model.  It gives the narrator a smaller,
authoritative set of facts to work from and checks its answer before campaign
state is changed.  The systems intentionally favour conservative repairs over
inventing a second story after the narrator has already spoken.
"""
from __future__ import annotations

import copy
import heapq
import math
import re
from datetime import datetime

from util import ai_text
from worlds import WORLD_DATA, timeline_for


GOAL_WORDS = re.compile(r"\b(until|master|learn|find|reach|finish|complete|unlock|awaken|discover|defeat|capture|build|create)\b", re.I)
TRAVEL_WORDS = re.compile(r"\b(travel|go to|head to|journey|sail|fly to|walk to|ride to|return to|reach)\b", re.I)
INSTANT_TRAVEL_WORDS = re.compile(r"\b(teleport|portal|warp|space[- ]time|flying raijin|instant transmission)\b", re.I)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _minutes(amount, unit):
    try:
        amount = max(0.0, float(amount or 0))
    except (TypeError, ValueError):
        return 0
    multipliers = {"minute": 1, "minutes": 1, "hour": 60, "hours": 60,
                   "day": 1440, "days": 1440, "week": 10080, "weeks": 10080,
                   "month": 43200, "months": 43200, "year": 525600, "years": 525600}
    return int(round(amount * multipliers.get(str(unit or "minutes").lower(), 1)))


def parse_action_goals(actions, turn=0):
    """Turn free-form orders into explicit, inspectable stopping conditions."""
    goals = []
    for index, raw in enumerate(actions or []):
        action = ai_text(raw)
        if not action or not GOAL_WORDS.search(action):
            continue
        lower = action.lower()
        kind = "completion"
        if any(x in lower for x in ("master", "learn", "unlock", "awaken")): kind = "growth"
        elif any(x in lower for x in ("find", "discover", "reach")): kind = "discovery"
        elif any(x in lower for x in ("defeat", "capture")): kind = "conflict"
        elif any(x in lower for x in ("build", "create")): kind = "project"
        match = re.search(r"\buntil\b\s+(.+)$", action, re.I)
        condition = match.group(1).strip(" .") if match else action
        goals.append({
            "id": f"turn-{int(turn or 0) + 1}-action-{index + 1}", "action_index": index,
            "action": action[:500], "kind": kind, "condition": condition[:500],
            "status": "active", "started_turn": int(turn or 0) + 1,
        })
    return goals


def register_action_goals(state, actions):
    active = parse_action_goals(actions, state.get("turn", 0))
    history = state.setdefault("action_goals", [])
    existing = {(row.get("action"), row.get("status")) for row in history if isinstance(row, dict)}
    for row in active:
        if (row["action"], "active") not in existing:
            history.append(row)
    state["action_goals"] = history[-100:]
    return active


def reconcile_action_goals(state, goals, data, elapsed_minutes):
    status = data.get("goal_status") if isinstance(data.get("goal_status"), dict) else {}
    action = ai_text(status.get("action"))
    achieved = bool(status.get("achieved"))
    for row in state.get("action_goals", []):
        if not isinstance(row, dict) or row.get("status") != "active":
            continue
        if action and (action.lower() in str(row.get("action", "")).lower() or str(row.get("action", "")).lower() in action.lower()):
            row["status"] = "achieved" if achieved else "incomplete"
            row["elapsed_minutes"] = int(elapsed_minutes or 0)
            row["explanation"] = ai_text(status.get("explanation"))[:1000]
            row["next_hint"] = ai_text(status.get("next_hint"))[:500]
            row["completed_turn"] = int(state.get("turn", 0) or 0) + 1
    return goals


def _map_nodes(world):
    nodes = []
    for raw in WORLD_DATA.get(world, WORLD_DATA.get("Custom World", {})).get("map", []):
        if isinstance(raw, (list, tuple)) and len(raw) >= 5:
            nodes.append({"name": str(raw[0]), "x": float(raw[1]), "y": float(raw[2]),
                          "kind": str(raw[3]), "tier": int(raw[4] or 1)})
        elif isinstance(raw, dict) and raw.get("name"):
            nodes.append({"name": str(raw["name"]), "x": float(raw.get("x", 0)), "y": float(raw.get("y", 0)),
                          "kind": str(raw.get("kind", "landmark")), "tier": int(raw.get("tier", 1) or 1)})
    return nodes


def _route_requirement(a, b, world):
    kinds = {a.get("kind", ""), b.get("kind", "")}
    if world == "Bleach":
        living = {"Karakura Town", "Karakura High School", "Kurosaki Clinic", "Urahara Shop", "Naruki City", "Urahara Training Grounds"}
        transit = {"Senkaimon", "Dangai", "Garganta", "Valley of Screams"}
        hueco = {"Hueco Mundo Desert", "Forest of Menos", "Las Noches"}
        royal = {"Soul King Palace", "Royal Guard Domains", "Wahrwelt"}
        enemy = {"Silbern"}
        def realm(name):
            if name in living: return "Living World"
            if name in transit: return "Inter-realm passage"
            if name in hueco: return "Hueco Mundo"
            if name in royal: return "Royal Realm"
            if name in enemy: return "Hidden Quincy domain"
            if name == "Gates of Hell": return "Hell"
            return "Soul Society"
        ra, rb = realm(a["name"]), realm(b["name"])
        if ra != rb:
            joined = {ra, rb}
            if "Hueco Mundo" in joined: return "Open or obtain access to a Garganta"
            if "Royal Realm" in joined: return "Royal Guard authorization, Oken access, or another established Royal Realm route"
            if "Hidden Quincy domain" in joined: return "Discover and breach the Wandenreich's shadow route"
            if "Hell" in joined: return "A canon-valid opening of the Gates of Hell"
            if joined <= {"Living World", "Soul Society", "Inter-realm passage"}: return "Use a Senkaimon and cross the Dangai"
        if a["name"] in {"Muken", "Maggot's Nest", "Central 46 Chambers", "Senzaikyu"} or b["name"] in {"Muken", "Maggot's Nest", "Central 46 Chambers", "Senzaikyu"}:
            return "Official clearance, an authorized escort, or a credible covert route"
    if world == "Solo Max-Level Newbie" and (a["name"].startswith("Floor ") or b["name"].startswith("Floor ")):
        return "Clear each intervening floor"
    if "sky" in kinds: return "A sky route or flight-capable transport"
    if kinds & {"island", "sea", "archipelago"}: return "A seaworthy boat, ship, or equivalent passage"
    if kinds & {"prison", "government", "hq"}: return "Permission, credentials, an escort, or a covert route"
    return ""


def build_travel_graph(state):
    """Create a connected local travel graph from the world's landmark map."""
    world = state.get("world", "Custom World")
    nodes = _map_nodes(world)
    graph = {row["name"]: [] for row in nodes}
    if world == "Solo Max-Level Newbie":
        ordered = nodes
        pairs = [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)]
    else:
        pairs, seen = [], set()
        for a in nodes:
            candidates = [(math.hypot(a["x"] - b["x"], a["y"] - b["y"]), b)
                          for b in nodes if b["name"] != a["name"]]
            nearest = sorted(candidates, key=lambda row: (row[0], row[1]["name"]))[:3]
            for distance, b in nearest:
                key = tuple(sorted((a["name"], b["name"])))
                if key not in seen:
                    seen.add(key); pairs.append((a, b))
    scale = float(WORLD_DATA.get(world, {}).get("travel_scale", 1.0) or 1.0)
    for a, b in pairs:
        distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        travel_minutes = max(30, int(round((distance * 38 + abs(a["tier"] - b["tier"]) * 12) * scale)))
        # Improvements are endpoint-specific, durable and non-stacking.
        from world_plans import obj, number
        factors=[number(v.get('factor'),1) for v in obj(state.get('world_benefits')).values()
                 if isinstance(v,dict) and v.get('active') is True and v.get('kind')=='safer_route'
                 and {v.get('origin'),v.get('destination')}=={a['name'],b['name']}]
        if factors: travel_minutes=max(1,int(round(travel_minutes*max(.5,min(1,min(factors))))))
        requirement = _route_requirement(a, b, world)
        for source, target in ((a, b), (b, a)):
            graph[source["name"]].append({"to": target["name"], "minutes": travel_minutes,
                                           "requirement": requirement, "kind": target["kind"]})
    return {"world": world, "nodes": nodes, "edges": graph, "built_for_version": "3.4"}


def travel_route(state, destination, origin=None):
    graph = build_travel_graph(state)
    names = list(graph["edges"])
    origin = ai_text(origin or state.get("location"))
    destination = ai_text(destination)
    def closest(value):
        low = value.lower()
        if not low.strip(): return ""
        exact = next((n for n in names if n.lower() == low), None)
        if exact: return exact
        contained = [n for n in names if re.search(r'(?<!\w)' + re.escape(n.lower()) + r'(?!\w)',low)]
        if contained: return max(contained,key=len)
        partial = [n for n in names if low in n.lower()]
        return partial[0] if len(partial)==1 else ""
    start, target = closest(origin), closest(destination)
    if not start or not target:
        return {"reachable": False, "origin": origin, "destination": destination,
                "reason": "One or both places are not on the known landmark graph.", "steps": [], "minutes": 0, "requirements": []}
    queue, best = [(0, start, [])], {start: 0}
    while queue:
        cost, name, path = heapq.heappop(queue)
        if name == target:
            requirements = list(dict.fromkeys(step["requirement"] for step in path if step.get("requirement")))
            return {"reachable": True, "origin": start, "destination": target, "minutes": cost,
                    "steps": path, "requirements": requirements,
                    "route": [start] + [step["to"] for step in path]}
        if cost != best.get(name): continue
        for edge in graph["edges"].get(name, []):
            new_cost = cost + int(edge["minutes"])
            if new_cost < best.get(edge["to"], 10**18):
                best[edge["to"]] = new_cost
                heapq.heappush(queue, (new_cost, edge["to"], path + [copy.deepcopy(edge)]))
    return {"reachable": False, "origin": start, "destination": target,
            "reason": "No connected route is known.", "steps": [], "minutes": 0, "requirements": []}


def travel_plan_for_actions(state, actions):
    plans = []
    origin = state.get('location')
    names = [row["name"] for row in _map_nodes(state.get("world", "Custom World"))]
    for index, action in enumerate(actions or []):
        text = ai_text(action)
        if not TRAVEL_WORDS.search(text): continue
        destination = next((name for name in sorted(names, key=len, reverse=True) if name.lower() in text.lower()), "")
        if destination:
            route = travel_route(state, destination, origin=origin)
            plans.append({"action_index": index, "action": text, **route})
            if route.get('reachable'): origin = route['destination']
    return plans


def event_confidence(event):
    source_type = str(event.get("source_type") or "").lower()
    if source_type in {"official_source", "manga", "novel", "source_material"}:
        return {"level": "confirmed", "label": "Confirmed canon", "score": 100,
                "note": "Directly supported by official source material."}
    if event.get("date_estimated") or not source_type:
        return {"level": "reconstruction", "label": "Best-fit timeline", "score": 78,
                "note": "The event is canon; its exact campaign date is a practical reconstruction."}
    if source_type in {"anime", "licensed_reference", "official_reference"}:
        return {"level": "adaptation", "label": "Adaptation-dependent", "score": 85,
                "note": "Details may vary between official versions."}
    return {"level": "uncertain", "label": "Uncertain lore", "score": 55,
            "note": "This detail is useful but not firmly established by the strongest source."}


def _match_divergence(divergence, title):
    if isinstance(divergence, dict):
        blob = " ".join(ai_text(divergence.get(k)) for k in ("event", "title", "canon_event", "text", "reason", "replacement"))
    else: blob = ai_text(divergence)
    words = {word for word in re.findall(r"[a-z0-9]+", title.lower()) if len(word) > 3}
    found = set(re.findall(r"[a-z0-9]+", blob.lower()))
    return title.lower() in blob.lower() or bool(words and len(words & found) >= min(2, len(words)))


def canon_dependency_graph(state):
    """Explain how fixed events depend on earlier story dominoes."""
    events = timeline_for(state.get("world", "Custom World")).get("events", [])
    fired = set(state.get("canon_events_fired", []))
    divergences = state.get("canon_divergences", []) if isinstance(state.get("canon_divergences"), list) else []
    current_day = int(state.get("canon_day", 0) or 0)
    rows, last_major = [], None
    for event in events:
        title, day = ai_text(event.get("title")), int(event.get("day", 0) or 0)
        event_id = f"day:{day}:{title or 'event'}"
        requires = list(event.get("requires") or []) if isinstance(event.get("requires"), list) else []
        if not requires and last_major and not event.get("historical_only"):
            requires = [last_major]
        matched = next((d for d in reversed(divergences) if _match_divergence(d, title)), None)
        status, reason, replacement, effective_day = ("occurred" if event_id in fired else "upcoming"), "Its known prerequisites remain possible.", "", day
        if event.get("historical_only") or day < current_day and event_id not in fired:
            status = "history"
        if matched is not None:
            raw_status = str(matched.get("status", "altered") if isinstance(matched, dict) else "altered").lower()
            status = "impossible" if raw_status in {"impossible", "prevented", "cancelled", "canceled"} else "delayed" if raw_status == "delayed" else "altered"
            reason = ai_text(matched.get("reason") if isinstance(matched, dict) else matched) or "Player actions changed the original cause."
            replacement = ai_text(matched.get("replacement") if isinstance(matched, dict) else "")
            if isinstance(matched, dict):
                try: effective_day = int(matched.get("new_day", matched.get("delayed_until", day)))
                except (TypeError, ValueError): effective_day = day
        blocked = []
        for requirement in requires:
            requirement_row = next((row for row in rows if row["title"].lower() == ai_text(requirement).lower()), None)
            if requirement_row and requirement_row["status"] == "impossible": blocked.append(requirement_row["title"])
        if blocked and status not in {"occurred", "history"}:
            status = "replaced" if replacement else "impossible"
            reason = "A required earlier event is no longer possible: " + ", ".join(blocked)
        rows.append({"id": event_id, "title": title, "day": day, "location": event.get("location", "Unknown"),
                     "summary": event.get("summary", ""), "major": event.get("major", True),
                     "requires": requires, "status": status, "reason": reason, "replacement": replacement,
                     "effective_day": effective_day,
                     "confidence": event_confidence(event)})
        if event.get("major", True) and not event.get("historical_only"): last_major = title
    return {"events": rows, "counts": {status: sum(1 for row in rows if row["status"] == status)
                                          for status in ("upcoming", "occurred", "altered", "delayed", "impossible", "replaced", "history")}}


def refresh_npc_schedules(state, elapsed_minutes=0):
    schedules = state.setdefault("npc_schedules", {})
    current_day = int(state.get("canon_day", 0) or 0)
    elapsed_days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    intentions = state.get("npc_intentions") if isinstance(state.get("npc_intentions"), dict) else {}
    memories = state.get("npc_memories") if isinstance(state.get("npc_memories"), dict) else {}
    events = []
    for name, intention in intentions.items():
        if not isinstance(intention, dict): continue
        row = schedules.setdefault(name, {})
        row.setdefault("commitments", [])
        goal = ai_text(intention.get("goal")) or "Pursue a private objective"
        if row.get("goal") != goal:
            row.update({"goal": goal, "status": "planned", "due_day": current_day + max(1, int(round(7 + (100 - float(intention.get('progress', 0) or 0)) / 12)))})
        row["next_action"] = ai_text(intention.get("next_action") or intention.get("plan"))
        row["location"] = ai_text(intention.get("location") or memories.get(name, {}).get("last_known_location")) or "Unknown"
        if elapsed_days and row.get("status") in {"planned", "active"}:
            row["status"] = "active"
            if current_day >= int(row.get("due_day", current_day + 1)):
                row["status"] = "due"
                events.append({
                    "type": "world", "title": f"{name}'s Plans Move",
                    "message": f"{name}'s ongoing objective has reached a decision point. They may act soon: {goal}",
                    "importance": 70,
                })
        row["last_checked_day"] = current_day
    state["npc_schedules"] = schedules
    return events


def transmit_information(state, data, elapsed_minutes=0):
    """Record how news moves; only explicitly addressed packets teach NPCs."""
    packets = state.setdefault("information_packets", [])
    authored = data.get("information_events") if isinstance(data.get("information_events"), list) else []
    for raw in authored:
        if not isinstance(raw, dict) or not ai_text(raw.get("fact")): continue
        delay = max(0, int(raw.get("delay_minutes", 0) or 0))
        packet = {"fact": ai_text(raw.get("fact"))[:500], "source": ai_text(raw.get("source")) or "Unknown",
                  "channel": ai_text(raw.get("channel")) or "direct observation",
                  "recipients": [ai_text(x) for x in raw.get("recipients", []) if ai_text(x)][:30],
                  "created_day": int(state.get("canon_day", 0) or 0), "available_after_minutes": delay,
                  "confidence": max(0, min(100, int(raw.get("confidence", 80) or 80))), "delivered": []}
        packets.append(packet)
    for packet in packets:
        if not isinstance(packet, dict): continue
        packet["available_after_minutes"] = max(0, int(packet.get("available_after_minutes", 0) or 0) - int(elapsed_minutes or 0))
        if packet["available_after_minutes"] > 0: continue
        delivered = set(packet.get("delivered", []))
        for recipient in packet.get("recipients", []):
            if recipient in delivered: continue
            memory = state.setdefault("npc_memories", {}).setdefault(recipient, {})
            knowledge = memory.setdefault("knowledge", {})
            bucket = "confirmed" if packet.get("confidence", 0) >= 80 else "heard"
            knowledge.setdefault(bucket, []).append({"fact": packet["fact"], "source": f"report:{packet['channel']}",
                                                     "confidence": packet["confidence"], "turn": state.get("turn", 0)})
            delivered.add(recipient)
        packet["delivered"] = sorted(delivered)
    state["information_packets"] = packets[-200:]
    return packets


def validate_turn_response(before, data, actions, rolls, requested_minutes, travel_plans=None, exact_duration=False):
    """Conservatively repair a narrator response before state application."""
    data = copy.deepcopy(data) if isinstance(data, dict) else {}
    actions = [ai_text(x) for x in actions or [] if ai_text(x)]
    warnings, repairs = [], []
    patch = data.get("state_patch") if isinstance(data.get("state_patch"), dict) else {}
    data["state_patch"] = patch

    # Preserve exact roll/action pairing and reject stale or invented labels.
    for index, roll in enumerate(rolls or []):
        try: action_index = int(roll.get("action_index", index))
        except (TypeError, ValueError): action_index = index
        action_index = max(0, min(action_index, max(0, len(actions) - 1)))
        expected = actions[action_index] if actions else ai_text(roll.get("reason")) or "Time-skip milestone"
        if roll.get("action") != expected:
            roll["action"] = expected; repairs.append(f"Reattached roll {index + 1} to action {action_index + 1}.")

    completed = [ai_text(x) for x in data.get("completed_actions", []) if ai_text(x)] if isinstance(data.get("completed_actions"), list) else []
    safe_completed = [action for action in actions if action in completed]
    if len(safe_completed) != len(completed):
        repairs.append("Removed completed-action labels that were not part of the submitted itinerary.")
    data["completed_actions"] = safe_completed

    updates = [row for row in data.get("updates", []) if isinstance(row, dict)] if isinstance(data.get("updates"), list) else []
    for row in updates:
        related = ai_text(row.get("related_action"))
        if related and related not in actions:
            closest = next((action for action in actions if related.lower() in action.lower() or action.lower() in related.lower()), "")
            if closest: row["related_action"] = closest; repairs.append("Normalized an update's related action.")
            else: row["related_action"] = ""; warnings.append(f"Update '{ai_text(row.get('title'))}' referenced an unknown action.")
    data["updates"] = updates

    elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
    elapsed_minutes = _minutes(elapsed.get("amount", 0), elapsed.get("unit", "minutes"))
    if requested_minutes > 0 and elapsed_minutes > requested_minutes:
        data["elapsed"] = {"amount": requested_minutes, "unit": "minutes"}
        elapsed_minutes = requested_minutes; repairs.append("Capped elapsed time at the requested simulation boundary.")
    goal = data.get("goal_status") if isinstance(data.get("goal_status"), dict) else {}
    if goal.get("achieved"):
        goal_elapsed = goal.get("elapsed") if isinstance(goal.get("elapsed"), dict) else {}
        goal_minutes = _minutes(goal_elapsed.get("amount", 0), goal_elapsed.get("unit", "minutes"))
        if goal_minutes and (not elapsed_minutes or goal_minutes < elapsed_minutes):
            data["elapsed"] = {"amount": goal_minutes, "unit": "minutes"}
            elapsed_minutes = goal_minutes; repairs.append("Stopped time at the stated goal-completion moment.")
    # Days/weeks/months are exact player commitments.  A narrator may stop
    # early only for an actual interruption, a reached major event, or a goal
    # completed before the boundary.  Moment mode intentionally remains
    # variable-length and therefore never enables this repair.
    may_stop_early = bool(data.get("interrupted") or data.get("major_event_reached") or goal.get("achieved"))
    if exact_duration and requested_minutes > 0 and elapsed_minutes < requested_minutes and not may_stop_early:
        data["elapsed"] = {"amount": requested_minutes, "unit": "minutes"}
        elapsed_minutes = requested_minutes
        repairs.append("Filled an unexplained early stop to the exact time skip requested by the player.")

    # A location mutation must fit a known route and the accepted elapsed time.
    new_location = ai_text(patch.get("location"))
    old_location = ai_text(before.get("location"))
    if new_location and old_location and new_location != old_location:
        route = travel_route(before, new_location, old_location)
        narration = " ".join([ai_text(data.get("narrative")), *[ai_text(x.get("narrative")) for x in updates]])
        instant = bool(INSTANT_TRAVEL_WORDS.search(narration + " " + " ".join(actions)))
        if not route.get("reachable"):
            # Most scene changes are local sublocations (market stall,
            # classroom, alley) that do not belong on the world atlas.  The
            # graph only blocks impossible movement when both ends are known
            # landmarks; it never mistakes entering a shop for teleporting.
            known = [row["name"] for row in _map_nodes(before.get("world", "Custom World"))]
            old_known = any(name.lower() in old_location.lower() or old_location.lower() in name.lower() for name in known)
            new_known = any(name.lower() in new_location.lower() or new_location.lower() in name.lower() for name in known)
            if old_known and new_known:
                patch.pop("location", None); warnings.append(f"Rejected travel to {new_location}: no known route connects it to {old_location}.")
        elif route.get("minutes", 0) > elapsed_minutes and not instant:
            patch.pop("location", None)
            data.setdefault("deferred_actions", []).extend([p.get("action") for p in travel_plans or [] if p.get("destination") == route.get("destination")])
            warnings.append(f"Travel to {new_location} needs about {route['minutes']} minutes, but only {elapsed_minutes} elapsed.")
        else:
            data["travel_result"] = route

    # Structural safety for values that should never become nonsensical.
    if isinstance(patch.get("currency"), dict):
        try: patch["currency"]["amount"] = max(0, int(patch["currency"].get("amount", 0) or 0))
        except (TypeError, ValueError):
            patch["currency"] = copy.deepcopy(before.get("currency", {"name": "Currency", "amount": 0})); repairs.append("Restored malformed currency.")
    for key, max_key in (("hp", "hp_max"), ("resource", "resource_max")):
        if key in patch:
            try: patch[key] = max(0, min(int(patch.get(max_key, before.get(max_key, 100)) or 100), int(patch[key])))
            except (TypeError, ValueError): patch.pop(key, None); repairs.append(f"Rejected malformed {key} value.")

    report = {"turn": int(before.get("turn", 0) or 0) + 1, "time": _now(), "warnings": warnings,
              "repairs": list(dict.fromkeys(repairs)), "rolls_checked": len(rolls or []),
              "actions_checked": len(actions), "elapsed_minutes": elapsed_minutes,
              "status": "repaired" if repairs else "warning" if warnings else "passed"}
    data["integrity_report"] = report
    return data, report


def apply_player_correction(state, correction_type, target, value, explanation=""):
    """Apply an explicit player-authored fact; player corrections outrank AI prose."""
    kind, target, value = ai_text(correction_type).lower(), ai_text(target), ai_text(value)
    if not kind or not value: raise ValueError("Choose a correction type and enter the correct value.")
    if kind == "currency" and state.get("world") == "Bleach":
        raise ValueError("Bleach does not maintain a tracked currency balance.")
    applied = ""
    if kind == "location":
        state["location"] = value
        if value not in state.setdefault("discovered_locations", []): state["discovered_locations"].append(value)
        applied = f"Current location is {value}."
    elif kind == "inventory_add":
        if value not in [ai_text(x.get("name") if isinstance(x, dict) else x) for x in state.setdefault("inventory", [])]: state["inventory"].append(value)
        applied = f"Inventory contains {value}."
    elif kind == "inventory_remove":
        state["inventory"] = [x for x in state.setdefault("inventory", []) if ai_text(x.get("name") if isinstance(x, dict) else x).lower() != value.lower()]
        applied = f"Inventory does not contain {value}."
    elif kind in {"currency", "hp", "resource"}:
        try: number = max(0, int(float(value)))
        except (TypeError, ValueError): raise ValueError("That correction needs a number.")
        if kind == "currency": state.setdefault("currency", {})["amount"] = number
        else: state[kind] = min(number, int(state.get(kind + "_max", number) or number))
        applied = f"{kind.title()} is {state.get(kind) if kind != 'currency' else number}."
    elif kind == "quest_status":
        quest = next((q for q in state.get("quests", []) if isinstance(q, dict) and ai_text(q.get("name")).lower() == target.lower()), None)
        if not quest: raise ValueError("No active quest with that exact name was found.")
        quest["status"] = value; applied = f"Quest {quest['name']} is {value}."
    elif kind == "territory":
        if not target: raise ValueError("Enter an exact mapped location or holding name.")
        claims=state.get('political_regions',[])
        claims=claims if isinstance(claims,list) else []
        matches=[c for c in claims if isinstance(c,dict) and str(c.get('name','')).casefold()==target.casefold()]
        places=[n['name'] for n in _map_nodes(state.get('world','Custom World'))]
        place=next((n for n in places if n.casefold()==target.casefold()),None)
        if not matches and not place: raise ValueError("Use an exact existing location or holding; a story fact cannot safely guess its borders.")
        for claim in matches:
            claim['controller']=value
            claim['status']='active'
            claim['controller_changed_turn']=int(state.get('turn',0) or 0)
        if place:
            details=state.setdefault('location_details',{})
            detail=details.get(place)
            details[place]={**(detail if isinstance(detail,dict) else {}),'controlling_faction':value}
        applied=f"Control of {target} belongs to {value}. Existing borders are preserved; local control does not grant the surrounding country."
    elif kind == "npc_status":
        if target.casefold() in {"player", "the player", ai_text(state.get('name')).casefold()}:
            raise ValueError("Choose an NPC, not the player character.")
        if value.casefold() != "dead":
            raise ValueError("This correction records a confirmed death. Use a story fact for uncertain reports or other status changes.")
        from narrative_state import record_npc_death
        if not record_npc_death(state, target, explanation or "Player-confirmed campaign correction"):
            raise ValueError("Choose an exact established NPC name.")
        applied = f"{target} is confirmed dead. Existing membership records retain their history."
    elif kind == "organization_membership_choice":
        from organizations import resolve_membership_offer
        result = resolve_membership_offer(state, target, value)
        applied = result
    elif kind == "organization_direct_join":
        from organizations import resolve_direct_player_join
        result = resolve_direct_player_join(state, target, value)
        applied = result
    elif kind == "skill":
        if not target: raise ValueError("Enter the skill name in Target.")
        skills = state.setdefault("skills", {})
        target = next((name for name in skills if str(name).casefold() == target.casefold()), target)
        previous = skills.get(target)
        state["skills"][target] = {**(previous if isinstance(previous, dict) else {}), "description": value, "effect": value}
        applied = f"{target}: {value}"
    else:
        applied = value if not target else f"{target}: {value}"
    record = {"id": f"correction-{len(state.setdefault('correction_log', [])) + 1}", "type": kind,
              "target": target, "value": value, "fact": applied, "explanation": explanation[:1000],
              "turn": int(state.get("turn", 0) or 0), "canon_day": state.get("canon_day"), "time": _now()}
    state["correction_log"].append(record); state["correction_log"] = state["correction_log"][-100:]
    facts = state.setdefault("authoritative_corrections", [])
    facts.append(record); state["authoritative_corrections"] = facts[-60:]
    state.setdefault("continuity_ledger", {}).setdefault("facts", []).append({"turn": state.get("turn", 0), "type": "player_correction", "text": applied})
    return record


def campaign_search(state, query, limit=30):
    """Fast local full-text search over the campaign's durable records."""
    stop = {"a", "an", "and", "are", "about", "did", "do", "does", "for", "from", "happen", "happened",
            "has", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on", "please", "that", "the",
            "this", "to", "was", "were", "what", "when", "where", "which", "who", "why", "with", "you", "your"}
    terms = [x for x in re.findall(r"[a-z0-9'-]+", ai_text(query).lower()) if len(x) > 1 and x not in stop]
    # A question made only of stop words is still searchable rather than
    # becoming an empty request; the Advisor will mainly rely on recent state.
    if not terms:
        terms = [x for x in re.findall(r"[a-z0-9'-]+", ai_text(query).lower()) if len(x) > 1]
    if not terms: return []
    rows = []
    def add(kind, title, text, turn=None, canon_day=None, payload=None):
        blob = f"{title} {text}".lower()
        score = sum(3 if term in str(title).lower() else 1 for term in terms if term in blob)
        if score:
            rows.append({"kind": kind, "title": ai_text(title) or kind.title(), "text": ai_text(text)[:1500],
                         "turn": turn, "canon_day": canon_day, "score": score, "payload": payload or {}})
    for row in state.get("campaign_canon", []):
        if isinstance(row, dict): add("chronicle", row.get("action") or row.get("type"), row.get("outcome") or row.get("text"), row.get("turn"), row.get("canon_day"))
    for row in state.get("chapter_summaries", []):
        if isinstance(row, dict): add("chapter", row.get("title"), row.get("summary"), (row.get("turns") or [None])[-1])
    for row in state.get("verified_memory_archive", []):
        if isinstance(row, dict): add("verified_archive", row.get("title"), row.get("summary"), (row.get("turns") or [None])[-1], payload={"verified": True, "source_digest": row.get("source_digest")})
    for row in state.get("consequence_ledger", []):
        if isinstance(row, dict): add("consequence", row.get("target") or row.get("kind"), row.get("evidence") or row.get("change"), row.get("turn"), payload={"kind": row.get("kind"), "status": row.get("status")})
    for row in state.get("quests", []) + state.get("quest_archive", []):
        if isinstance(row, dict): add("quest", row.get("name") or row.get("title"), row.get("explanation") or row.get("description"), payload={"status": row.get("status")})
    for name, detail in (state.get("skills") or {}).items(): add("skill", name, detail if isinstance(detail, str) else detail.get("description") or detail.get("effect"), payload=detail if isinstance(detail, dict) else {})
    for name, memory in (state.get("npc_memories") or {}).items():
        if isinstance(memory, dict): add("npc", name, " ".join(ai_text(memory.get(k)) for k in ("attitude", "goal", "immediate_goal", "last_known_location")), payload={"location": memory.get("last_known_location")})
    for row in state.get("continuity_ledger", {}).get("facts", []):
        if isinstance(row, dict): add("fact", row.get("type"), row.get("text"), row.get("turn"))
    for row in state.get("correction_log", []):
        if isinstance(row, dict): add("correction", row.get("target") or "Player correction", row.get("fact"), row.get("turn"), row.get("canon_day"))
    kind_priority = {"correction": 0, "consequence": 1, "quest": 2, "chronicle": 3, "verified_archive": 4, "chapter": 5, "npc": 6, "skill": 7, "fact": 8}
    rows.sort(key=lambda row: (-row["score"], -(int(row.get("turn") or 0)), kind_priority.get(row["kind"], 9)))
    # Corrections are also copied into the continuity ledger so the GM sees
    # them as authoritative facts.  Search should show that record once, not
    # make the player wonder whether two separate events occurred.
    unique, seen = [], set()
    for row in rows:
        key = re.sub(r"\s+", " ", ai_text(row.get("text")).lower()).strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(row)
    return unique[:max(1, min(100, int(limit or 30)))]


def integrity_snapshot(state):
    graph = build_travel_graph(state)
    return {"recent_validation": copy.deepcopy((state.get("simulation_validation") or [])[-30:]),
            "active_goals": [copy.deepcopy(x) for x in state.get("action_goals", []) if isinstance(x, dict) and x.get("status") == "active"],
            "corrections": copy.deepcopy((state.get("correction_log") or [])[-30:]),
            "npc_schedules": copy.deepcopy(state.get("npc_schedules", {})),
            "information_packets": copy.deepcopy((state.get("information_packets") or [])[-40:]),
            "travel": {"nodes": len(graph["nodes"]), "connections": sum(len(x) for x in graph["edges"].values()) // 2},
            "canon_dependencies": canon_dependency_graph(state)}
