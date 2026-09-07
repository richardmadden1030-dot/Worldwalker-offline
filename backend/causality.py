"""Causal requirements for NPC and faction world clocks."""
import copy

from util import ai_text


def _dependency_met(state, dependency):
    if isinstance(dependency, str):
        needle = dependency.lower().strip()
        canon = " ".join(ai_text(x.get("outcome") if isinstance(x, dict) else x) for x in state.get("campaign_canon", [])).lower()
        return (needle in canon, f"campaign history contains '{dependency}'")
    if not isinstance(dependency, dict):
        return True, "no requirement"
    kind = str(dependency.get("type") or "event").lower()
    target = str(dependency.get("target") or dependency.get("name") or "").strip()
    if kind == "clock":
        clocks = {**(state.get("faction_clocks") or {}), **(state.get("npc_clocks") or {})}
        row = clocks.get(target, {}) if isinstance(clocks.get(target), dict) else {}
        required = str(dependency.get("status") or "turning_point")
        return row.get("status") == required, f"{target} must be {required}"
    if kind == "location_control":
        location = str(dependency.get("location") or target)
        controller = str(dependency.get("controller") or dependency.get("value") or "")
        actual = (state.get("location_details") or {}).get(location, {})
        actual = actual.get("controlling_faction") if isinstance(actual, dict) else ""
        return actual == controller, f"{controller} must control {location}"
    if kind == "reputation":
        minimum = int(dependency.get("minimum", 0) or 0)
        actual = int((state.get("reputation") or {}).get(target, 0) or 0)
        return actual >= minimum, f"{target} reputation must be at least {minimum}"
    needle = str(dependency.get("event") or target).lower()
    canon = " ".join(ai_text(x.get("outcome") if isinstance(x, dict) else x) for x in state.get("campaign_canon", [])).lower()
    return (not needle or needle in canon), f"campaign history must establish '{needle}'"


def advance_causal_clock(state, actor, clock, base_step, elapsed_days, kind="clock"):
    """Return a justified progress delta and store a concise causal audit."""
    explicit = any(key in clock for key in ("method", "target_location", "travel_remaining_days", "dependencies", "resources", "resource_cost"))
    reasons, blockers = [], []
    dependencies = clock.get("dependencies") if isinstance(clock.get("dependencies"), list) else []
    for dependency in dependencies:
        met, explanation = _dependency_met(state, dependency)
        (reasons if met else blockers).append(explanation)

    travel = max(0.0, float(clock.get("travel_remaining_days", 0) or 0))
    if travel > 0:
        moved = min(travel, max(0.0, elapsed_days))
        travel = max(0.0, travel - moved)
        clock["travel_remaining_days"] = round(travel, 2)
        if travel > 0:
            blockers.append(f"{travel:g} travel day(s) remain before reaching {clock.get('target_location') or 'the objective'}")
        else:
            clock["current_location"] = clock.get("target_location") or clock.get("current_location", "")
            reasons.append(f"arrived at {clock.get('current_location') or 'the target'}")

    resources = clock.get("resources") if isinstance(clock.get("resources"), dict) else {}
    costs = clock.get("resource_cost") if isinstance(clock.get("resource_cost"), dict) else {}
    for resource, amount in costs.items():
        try:
            needed, available = max(0.0, float(amount)), max(0.0, float(resources.get(resource, 0) or 0))
        except (TypeError, ValueError):
            continue
        if available < needed:
            blockers.append(f"needs {needed:g} {resource}, has {available:g}")
    delta = 0 if blockers else int(base_step)
    if delta:
        for resource, amount in costs.items():
            try: resources[resource] = max(0, round(float(resources.get(resource, 0) or 0) - float(amount), 2))
            except (TypeError, ValueError): pass
        if costs: clock["resources"] = resources
        method = str(clock.get("method") or "steady effort")
        support = max(-50, min(100, int(clock.get("support", 0) or 0)))
        if support:
            delta = max(1, round(delta * (1 + support / 200)))
        reasons.append(f"used {method}")
        if costs: reasons.append("spent " + ", ".join(f"{v} {k}" for k, v in costs.items()))

    reason = "; ".join(reasons) if reasons else ("ordinary off-screen effort" if not blockers else "")
    blocked_reason = "; ".join(blockers)
    clock["last_cause"] = reason or blocked_reason
    clock["blocked_reason"] = blocked_reason
    if explicit or blockers or delta:
        state.setdefault("causality_ledger", []).append({
            "turn": int(state.get("turn", 0) or 0), "time": state.get("world_time", ""), "actor": actor,
            "kind": kind, "goal": clock.get("immediate_goal") or clock.get("goal", ""),
            "progress_delta": delta, "reason": reason, "blocked_reason": blocked_reason,
            "target_location": clock.get("target_location", ""), "resources": copy.deepcopy(resources),
        })
        state["causality_ledger"] = state["causality_ledger"][-250:]
    return delta


def causality_snapshot(state):
    def rows(clocks):
        return [{"name": clock.get("name") or name, "goal": clock.get("immediate_goal") or clock.get("goal", ""),
                 "status": clock.get("status", "active"), "last_cause": clock.get("last_cause", ""),
                 "blocked_reason": clock.get("blocked_reason", ""), "target_location": clock.get("target_location", ""),
                 "resources": copy.deepcopy(clock.get("resources", {}))}
                for name, clock in (clocks or {}).items() if isinstance(clock, dict)]
    return {"factions": rows(state.get("faction_clocks")), "npcs": rows(state.get("npc_clocks")),
            "recent": copy.deepcopy((state.get("causality_ledger") or [])[-50:])}
