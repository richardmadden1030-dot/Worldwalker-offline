"""Resume expensive failed stages and keep settled dice without global RNG rewinds."""
import copy
from gm_refinements import fingerprint, obj


def guard(state):
    keys = ("adventures", "travel_access", "world_benefits", "location_details", "shops", "calendar_epoch", "calendar_anchor_day", "campaign_id", "world", "name", "turn", "canon_day", "canon_time_minutes", "world_time", "location", "position",
            "level", "xp", "xp_next", "equipment", "ability_progress", "ability_evolution", "quest_archive",
            "hp", "hp_max", "resource", "resource_max", "stats", "skills", "titles", "inventory", "currency",
            "conditions", "combat", "special", "world_systems", "class_profile", "npc_memories", "contacts",
            "chat_threads", "quests", "relationships", "companions", "affiliations", "standing_orders", "queued_actions",
            "authoritative_corrections", "portrait_identity", "chapter_buffer", "chapter_summaries", "alive", "organizations", "organization_lives")
    return fingerprint({key: state.get(key) for key in keys})


def begin(game, route, payload):
    failed = obj(game.state.get("last_failed_turn"))
    previous = obj(failed.get("work"))
    valid = failed.get("route") == route and failed.get("payload") == payload and previous.get("guard") == guard(game.state)
    game._turn_work = copy.deepcopy(previous) if valid else {"guard": guard(game.state), "stages": {}}
    game._turn_cursors = {}


def stage(game, kind, inputs):
    work = getattr(game, "_turn_work", None)
    if not isinstance(work, dict): return {}
    cursor = getattr(game, "_turn_cursors", {})
    index = cursor.get(kind, 0)
    cursor[kind] = index + 1
    key = f"{kind}:{index}"
    digest = fingerprint(inputs)
    record = work["stages"].get(key)
    if not isinstance(record, dict) or record.get("digest") != digest:
        record = {"digest": digest}
        work["stages"][key] = record
    return record


def request_signature(instructions, payload, model, output_limit):
    # Error/recovery bookkeeping changes after rollback; gameplay inputs do not.
    # Include the whole request so a different duration, scene or model cannot
    # accidentally receive a cached answer for the same short action string.
    volatile = {"last_failed_turn", "recovery_timeline", "diagnostics", "validation_log", "health_repairs", "prompt_budget_log"}
    def clean(value):
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items() if k not in volatile}
        if isinstance(value, list): return [clean(v) for v in value]
        return value
    return {"instructions": instructions, "payload": clean(payload), "model": model, "output_limit": output_limit}


def remember_commands(state, data):
    actors = [str(row["actor"]) for row in data.get("command_outcomes", [])
              if isinstance(row, dict) and row.get("actor") and row.get("status") in {"obeyed", "in_progress"}]
    if actors:
        state["last_command_context"] = {"actors": list(dict.fromkeys(actors))[:16], "turn": state.get("turn", 0)}
