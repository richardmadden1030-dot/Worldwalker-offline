"""Local long-campaign maintenance and recovery.

The functions in this module make no AI calls.  They are intentionally
conservative: malformed or obsolete bookkeeping is repaired, while authored
story facts are retained.  Every resolving route runs the health pass before
it snapshots the campaign so old saves cannot fail before rollback exists.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime


_TERMINAL = {"achieved", "complete", "completed", "failed", "abandoned", "superseded", "cancelled", "resolved"}
_ACTIVE = {"active", "ongoing", "in_progress", "pending"}
_COMBAT_END = {"dead", "deceased", "defeated", "escaped", "fled", "captured", "subdued", "resolved"}
_CANCEL_ORDER = re.compile(r"\b(?:cancel|stop|end|drop|revoke|withdraw|no longer|do not continue)\b", re.I)


def _text(value, limit=700):
    if value is None:
        return ""
    if isinstance(value, str):
        result = value
    elif isinstance(value, (int, float, bool)):
        result = str(value)
    elif isinstance(value, dict):
        result = str(value.get("text") or value.get("name") or value.get("title") or "")
    else:
        result = str(value)
    return re.sub(r"\s+", " ", result).strip()[:limit]


def _integer(value, default=0, minimum=None, maximum=None):
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _order_id(text):
    return hashlib.sha256(_text(text).casefold().encode("utf-8")).hexdigest()[:14]


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def validate_nested_campaign_state(state):
    """Repair nested container shapes and report exact paths.

    The top-level state guard already validates known fields.  This pass
    protects the deep collections most likely to accumulate mixed model and
    legacy values over hundreds of turns.
    """
    repairs, warnings = [], []
    list_fields = (
        "action_goals", "standing_orders", "standing_intents", "queued_actions",
        "quests", "hidden_quests", "quest_archive", "companions", "conditions",
        "scheduled_events", "campaign_canon", "chapter_summaries", "scene_history",
        "verified_memory_archive", "resolution_ledger", "progression_ledger",
        "consequence_ledger", "obligation_ledger", "delayed_consequences", "fact_history",
        "campaign_arcs", "campaign_arc_archive",
    )
    dict_fields = (
        "scene_state", "combat", "danger_scenario", "npc_memories", "contacts",
        "chat_threads", "narrative_memory", "memory_consolidation", "scenario_memory",
        "continuity_ledger", "diagnostics", "standing_order_state", "memory_tiers",
        "campaign_arc_director", "campaign_arc_context", "life_simulation", "life_context",
    )
    for key in list_fields:
        if not isinstance(state.get(key), list):
            meaningful = state.get(key) not in (None, "", {})
            if meaningful:
                warnings.append(f"{key}: expected list, received {type(state.get(key)).__name__}")
            state[key] = []
            if meaningful:
                repairs.append(f"Rebuilt malformed {key}")
    for key in dict_fields:
        if not isinstance(state.get(key), dict):
            meaningful = state.get(key) not in (None, "", [])
            if meaningful:
                warnings.append(f"{key}: expected object, received {type(state.get(key)).__name__}")
            state[key] = {}
            if meaningful:
                repairs.append(f"Rebuilt malformed {key}")

    # Dict rows are retained only when their identity can be recovered.
    for key in ("action_goals", "quests", "hidden_quests", "quest_archive", "scene_history"):
        cleaned = []
        for index, raw in enumerate(state.get(key, [])):
            if isinstance(raw, dict):
                cleaned.append(raw)
            elif isinstance(raw, str) and raw.strip() and key in {"quests", "hidden_quests", "quest_archive"}:
                cleaned.append({"name": raw.strip(), "status": "Hidden" if key == "hidden_quests" else "Active"})
                repairs.append(f"Converted {key}[{index}] text into a record")
            else:
                warnings.append(f"{key}[{index}]: removed invalid {type(raw).__name__} row")
        state[key] = cleaned

    memories = {}
    for name, raw in state.get("npc_memories", {}).items():
        label = _text(name, 160)
        if not label:
            continue
        if isinstance(raw, dict):
            memories[label] = raw
        elif isinstance(raw, str) and raw.strip():
            memories[label] = {"notes": raw.strip()[:1000]}
            repairs.append(f"Converted npc_memories.{label} into a dossier")
        else:
            warnings.append(f"npc_memories.{label}: removed invalid {type(raw).__name__} dossier")
    state["npc_memories"] = memories

    combat = state["combat"]
    if "enemy" in combat and not isinstance(combat.get("enemy"), dict):
        name = _text(combat.get("enemy"), 160)
        combat["enemy"] = {"name": name, "hp": 1, "hp_max": 1} if name else {}
        repairs.append("Converted combat.enemy into a structured combatant")
    if "status_effects" in combat and not isinstance(combat.get("status_effects"), list):
        raw = combat.get("status_effects")
        combat["status_effects"] = [raw] if isinstance(raw, (str, dict)) else []
        repairs.append("Rebuilt malformed combat.status_effects")
    return repairs, warnings


def cleanup_action_goals(state, active_orders=None):
    """Expire orphaned goals without erasing their history."""
    turn = _integer(state.get("turn"), 0, 0)
    orders = [_text(row) for row in (active_orders if active_orders is not None else state.get("standing_orders", []))]
    order_blob = " ".join(orders).casefold()
    rows, repairs, active_by_action = [], [], {}
    for index, raw in enumerate(state.get("action_goals", [])):
        if not isinstance(raw, dict):
            continue
        row = copy.deepcopy(raw)
        action = _text(row.get("action") or row.get("condition"), 500)
        if not action:
            continue
        row["action"] = action
        row["condition"] = _text(row.get("condition") or action, 500)
        row["started_turn"] = _integer(row.get("started_turn"), turn, 0)
        status = _text(row.get("status") or "active", 40).lower()
        status = "active" if status in _ACTIVE else status
        if status == "active":
            key = re.sub(r"[^a-z0-9]+", " ", action.casefold()).strip()
            prior = active_by_action.get(key)
            if prior is not None:
                rows[prior]["status"] = "superseded"
                rows[prior]["completed_turn"] = turn
                repairs.append(f"Superseded duplicate action goal: {action[:80]}")
            active_by_action[key] = len(rows)
            age = turn - row["started_turn"]
            referenced = action.casefold() in order_blob or any(order.casefold() in action.casefold() for order in orders if order)
            if age > 24 and not referenced:
                status = "abandoned"
                row["status"] = status
                row["completed_turn"] = turn
                row["explanation"] = "Archived because its originating plan is no longer active."
                repairs.append(f"Archived stale action goal from turn {row['started_turn']}: {action[:80]}")
        elif status not in _TERMINAL:
            status = "active"
        row["status"] = status
        rows.append(row)
    terminal = [row for row in rows if row.get("status") != "active"][-100:]
    active = [row for row in rows if row.get("status") == "active"][-24:]
    state["action_goals"] = terminal + active
    return repairs


def reconcile_quests_and_scene(state):
    """Keep the current scene, quests and resolved quest archive coherent."""
    repairs = []
    archive = list(state.get("quest_archive", []))
    archive_names = {_text(row.get("name") if isinstance(row, dict) else row).casefold() for row in archive}
    for key in ("quests", "hidden_quests"):
        kept, seen = [], set()
        for raw in state.get(key, []):
            if not isinstance(raw, dict):
                continue
            row = copy.deepcopy(raw)
            name = _text(row.get("name") or row.get("title"), 160)
            if not name or name.casefold() in seen:
                if name:
                    repairs.append(f"Removed duplicate quest record: {name}")
                continue
            seen.add(name.casefold())
            row["name"] = name
            status = _text(row.get("status") or ("Hidden" if key == "hidden_quests" else "Active"), 40)
            row["status"] = status
            if status.casefold() in {"complete", "completed", "failed", "abandoned", "resolved"}:
                if name.casefold() not in archive_names:
                    archive.append(row); archive_names.add(name.casefold())
                repairs.append(f"Archived resolved quest: {name}")
            else:
                kept.append(row)
        state[key] = kept[-100:]
    state["quest_archive"] = archive[-240:]

    scene = state.get("scene_state", {})
    location = _text(state.get("location"), 200) or "Unknown"
    if _text(scene.get("location"), 200) != location:
        scene["location"] = location
        scene["turn"] = _integer(state.get("turn"), 0, 0)
        repairs.append("Reconciled the live scene with the current location")
    present = []
    for raw in _list(scene.get("present")):
        name = _text(raw, 160)
        memory = state.get("npc_memories", {}).get(name, {})
        if name and _text(memory.get("status")).casefold() not in {"dead", "deceased"} and name not in present:
            present.append(name)
    scene["present"] = present[:16]
    state["scene_state"] = scene
    return repairs


def cleanup_combat_state(state):
    """Close impossible/stale combat while preserving the last outcome."""
    combat = state.get("combat", {})
    repairs = []
    if not combat:
        state["combat"] = {}
        return repairs
    enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
    active = bool(combat.get("active"))
    player_alive = bool(state.get("alive", True)) and _integer(state.get("hp"), 1) > 0
    enemy_name = _text(enemy.get("name"), 160)
    enemy_hp = _integer(enemy.get("hp"), 1)
    enemy_status = _text(enemy.get("status") or combat.get("outcome"), 80).casefold()
    reason = ""
    if active and not player_alive:
        reason = "the player is no longer able to fight"
    elif active and not enemy_name:
        reason = "no valid opponent remained"
    elif active and (enemy_hp <= 0 or enemy_status in _COMBAT_END) and not (
            isinstance(combat.get('adventure_objective'),dict) and not combat['adventure_objective'].get('settled')):
        reason = f"{enemy_name or 'the opponent'} was already resolved"
    if reason:
        state["last_combat"] = {
            "turn": _integer(state.get("turn"), 0), "enemy": enemy_name,
            "outcome": _text(combat.get("outcome") or enemy_status or "resolved", 120),
            "reason": reason,
        }
        combat["active"] = False
        combat["ended_turn"] = _integer(state.get("turn"), 0)
        combat["cleanup_reason"] = reason
        repairs.append(f"Closed stale combat because {reason}")
    combat["round"] = _integer(combat.get("round"), 1, 1, 10000)
    if not combat.get("active"):
        # A completed combat can remain as a compact receipt but cannot keep
        # danger gates or active effects alive.
        state["danger_scenario"] = {}
        combat.pop("pending_extra_turn", None)
        combat.pop("awaiting_player", None)
    state["combat"] = combat
    return repairs


def sync_standing_order_lifecycle(state, orders=None, completed=None, deferred=None, source="health_check"):
    """Mirror legacy standing-order strings into lifecycle records."""
    turn = _integer(state.get("turn"), 0, 0)
    raw_orders = orders if orders is not None else state.get("standing_orders", [])
    clean = []
    for raw in raw_orders if isinstance(raw_orders, list) else []:
        text = _text(raw, 500)
        if text and text not in clean:
            clean.append(text)
    completed_set = {_text(row, 500).casefold() for row in (completed or []) if _text(row)}
    deferred_set = {_text(row, 500).casefold() for row in (deferred or []) if _text(row)}
    ledger = state.get("standing_order_state", {})
    if not isinstance(ledger, dict):
        ledger = {}
    active_ids = set()
    for text in clean:
        key = _order_id(text); active_ids.add(key)
        row = ledger.get(key) if isinstance(ledger.get(key), dict) else {}
        row.update({"id": key, "text": text, "status": "active", "last_used_turn": turn, "source": source})
        row.setdefault("created_turn", turn)
        row.setdefault("continuation", "until_completed_or_cancelled")
        if text.casefold() in completed_set:
            row["status"], row["completed_turn"] = "completed", turn
        elif text.casefold() in deferred_set:
            row["status"] = "deferred"
        ledger[key] = row
    for key, row in list(ledger.items()):
        if not isinstance(row, dict):
            ledger.pop(key, None); continue
        if row.get("status") in {"active", "deferred"} and key not in active_ids:
            row["status"] = "superseded"
            row["completed_turn"] = turn
    # Explicit cancellation language ends matching prior orders without
    # making that cancellation sentence itself a standing instruction.
    if any(_CANCEL_ORDER.search(text) for text in clean):
        for row in ledger.values():
            if isinstance(row, dict) and row.get("status") in {"active", "deferred"} and _CANCEL_ORDER.search(_text(row.get("text"))):
                row["status"], row["completed_turn"] = "completed", turn
    state["standing_order_state"] = dict(list(ledger.items())[-80:])
    state["standing_orders"] = [row["text"] for row in state["standing_order_state"].values()
                                if isinstance(row, dict) and row.get("status") in {"active", "deferred"}]
    return copy.deepcopy(state["standing_order_state"])


def build_memory_tiers(state):
    """Create bounded hot/warm/cold context indexes from durable history."""
    canon = [row for row in state.get("campaign_canon", []) if isinstance(row, dict)]
    chapters = [row for row in state.get("chapter_summaries", []) if isinstance(row, dict)]
    archive = [row for row in state.get("verified_memory_archive", []) if isinstance(row, dict)]
    hot = []
    for row in canon[-16:]:
        hot.append({key: copy.deepcopy(row.get(key)) for key in ("turn", "canon_day", "action", "outcome", "text") if row.get(key) not in (None, "")})
    warm = []
    for row in chapters[-12:]:
        warm.append({key: copy.deepcopy(row.get(key)) for key in ("title", "turns", "canon_days", "summary", "key_events") if row.get(key) not in (None, "", [])})
    cold = []
    for row in archive[-40:]:
        cold.append({key: copy.deepcopy(row.get(key)) for key in ("title", "turns", "canon_days", "summary", "source_digest") if row.get(key) not in (None, "", [])})
    state["memory_tiers"] = {
        "hot": hot, "warm": warm, "cold": cold,
        "policy": "hot=recent verified turns; warm=chapter summaries; cold=archived verified history",
        "rebuilt_turn": _integer(state.get("turn"), 0),
    }
    return state["memory_tiers"]


def compact_checkpoint_state(state):
    """Return an undo-safe state without redundant historical copies."""
    snapshot = copy.deepcopy(state)
    limits = {
        "campaign_canon": 40, "scene_history": 12, "progression_ledger": 40,
        "resolution_ledger": 24, "consequence_ledger": 60, "simulation_events": 60,
        "validation_log": 20, "simulation_validation": 20, "health_repairs": 20,
        "recovery_timeline": 12, "background_world_feed": 40, "world_events": 40,
    }
    for key, limit in limits.items():
        if isinstance(snapshot.get(key), list):
            snapshot[key] = snapshot[key][-limit:]
    if isinstance(snapshot.get("narrative_memory"), dict):
        for key, rows in snapshot["narrative_memory"].items():
            if isinstance(rows, list):
                snapshot["narrative_memory"][key] = rows[-40:]
    snapshot.pop("diagnostics", None)
    return snapshot


def compact_state_for_storage(state):
    """Bound redundant ledgers while retaining all current campaign facts."""
    stored = copy.deepcopy(state)
    limits = {
        "scene_history": 40, "validation_log": 60, "simulation_validation": 80,
        "health_repairs": 80, "recovery_timeline": 24, "progression_ledger": 180,
        "resolution_ledger": 120, "consequence_ledger": 240, "world_events": 240,
        "background_world_feed": 240, "travel_history": 160, "loot_history": 160,
    }
    for key, limit in limits.items():
        if isinstance(stored.get(key), list):
            stored[key] = stored[key][-limit:]
    build_memory_tiers(stored)
    return stored


def record_runtime_error(state, error, route="runtime", payload=None, trace=""):
    now = datetime.now().isoformat(timespec="seconds")
    seed = f"{now}|{route}|{type(error).__name__}|{error}"
    error_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
    row = {
        "id": error_id, "time": now, "turn": _integer(state.get("turn"), 0),
        "route": _text(route, 120), "type": type(error).__name__, "message": _text(error, 500),
        "payload_shape": sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        "trace_tail": _text(trace, 1800),
    }
    diagnostics = state.setdefault("diagnostics", {})
    errors = diagnostics.setdefault("runtime_errors", [])
    errors.append(row); diagnostics["runtime_errors"] = errors[-40:]
    diagnostics["last_error_id"] = error_id
    return row


def pre_advance_health_check(state, actions=None, source="pre_advance"):
    """Run all safe local repairs before a turn can enter AI code."""
    if not isinstance(state, dict):
        raise TypeError("Campaign state must be an object.")
    repairs, warnings = validate_nested_campaign_state(state)
    orders = actions if isinstance(actions, list) and actions else state.get("standing_orders", [])
    sync_standing_order_lifecycle(state, orders, source=source)
    repairs.extend(cleanup_action_goals(state, state.get("standing_orders", [])))
    repairs.extend(reconcile_quests_and_scene(state))
    repairs.extend(cleanup_combat_state(state))
    build_memory_tiers(state)
    report = {
        "time": datetime.now().isoformat(timespec="seconds"), "turn": _integer(state.get("turn"), 0),
        "source": source, "repairs": list(dict.fromkeys(repairs)), "warnings": warnings[:30],
        "status": "repaired" if repairs else "healthy",
    }
    state.setdefault("diagnostics", {})["pre_advance_health"] = copy.deepcopy(report)
    if repairs or warnings:
        state.setdefault("health_repairs", []).append(copy.deepcopy(report))
        state["health_repairs"] = state["health_repairs"][-80:]
    return report
