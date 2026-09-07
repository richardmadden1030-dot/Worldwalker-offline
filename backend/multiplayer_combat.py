"""AI-free simultaneous two-player combat rounds."""
from __future__ import annotations
import copy
import random
import re
from skill_system import infer_skill_metadata
from worlds import DIFFICULTIES, primary_stats_for, speed_stat_for, defense_stat_for

HARD_CONTROL = re.compile(r"\b(stunned|paralyzed|asleep|frozen|incapacitated|unconscious|petrified|restrained|bound|controlled)\b", re.I)


def _mapping(value):
    """Return a mutable mapping for legacy/imported multiplayer state.

    Older saves and model-authored patches occasionally stored a display
    label where the current combat engine expects an object.  Combat is a
    hard progression boundary, so repair those shapes instead of letting one
    stale string brick every action button for both players.
    """
    return value if isinstance(value, dict) else {}


def _status_objects(rows):
    """Normalize old string statuses into the current structured shape."""
    if isinstance(rows, str):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    clean = []
    for row in rows:
        if isinstance(row, dict):
            item = copy.deepcopy(row)
        elif str(row or "").strip():
            item = {"name": str(row).strip(), "rounds_left": 1}
        else:
            continue
        item.setdefault("name", "Active effect")
        item.setdefault("rounds_left", 1)
        item.setdefault("blocks_action", bool(HARD_CONTROL.search(str(item.get("name") or ""))))
        clean.append(item)
    return clean


def _normalize_enemy(raw):
    if isinstance(raw, dict):
        enemy = copy.deepcopy(raw)
    elif str(raw or "").strip():
        enemy = {"name": str(raw).strip()}
    else:
        enemy = {}
    enemy["multiplayer_statuses"] = _status_objects(enemy.get("multiplayer_statuses", []))
    return enemy

def _statuses(character):
    character = _mapping(character)
    rows = character.get("conditions") or character.get("status") or []
    if isinstance(rows, str): rows = [rows]
    return rows if isinstance(rows, list) else []

def _blocked(character):
    for row in _statuses(character):
        text = row.get("name") if isinstance(row, dict) else str(row)
        if HARD_CONTROL.search(str(text or "")): return str(text)
    return ""

def _parse_action(actions, skills):
    text = str((actions or ["defend"])[0] or "defend")
    lower = text.lower()
    kind = "flee" if "flee" in lower or "escape" in lower else "defend" if "defend" in lower or "guard" in lower else "overwhelm" if "overwhelm" in lower else "attack"
    ability = next((name for name in skills if str(name).lower() in lower), "")
    return kind, ability, text

def _check(bonus, low, high, shift=0):
    difficulty = random.randint(max(1, int(low) + shift), min(100, int(high) + shift))
    roll = random.randint(1, 100); total = roll + int(bonus)
    return {"roll": roll, "bonus": int(bonus), "total": total, "difficulty": difficulty,
            "success": roll != 1 and total > difficulty}

def resolve_multiplayer_combat_round(shared_state, participants, round_number):
    """Resolve each eligible PC choice, then one enemy response."""
    state = copy.deepcopy(_mapping(shared_state)); combat = _mapping(state.get("combat")); enemy = _normalize_enemy(combat.get("enemy"))
    if not combat.get("active") or not enemy:
        return None
    combat["enemy"] = enemy
    world = state.get("world", "Custom World"); difficulty = state.get("difficulty", "Adventurer")
    shift = int(DIFFICULTIES.get(difficulty, {}).get("difficulty_shift", 0) or 0)
    enemy.setdefault("hp_max", max(20, int(enemy.get("hp", 100) or 100))); enemy.setdefault("hp", enemy["hp_max"])
    enemy.setdefault("power", 30); enemy.setdefault("difficulty_min", 30); enemy.setdefault("difficulty_max", 55)
    enemy.setdefault("attack_min", 30); enemy.setdefault("attack_max", 55); enemy.setdefault("alive", True)
    bonus_names = set(combat.pop("multiplayer_bonus_names", []) or [])
    bonus_round = bool(bonus_names)
    characters, events, acted = {}, [], []
    for raw_person in participants or []:
        person = _mapping(raw_person)
        character = copy.deepcopy(_mapping(person.get("character")))
        user_id = str(person.get("user_id")); characters[user_id] = character
        name = str(character.get("name") or person.get("username") or "Player")
        if bonus_round and name not in bonus_names:
            events.append({"actor": "system", "action": "wait", "name": name, "reason": "Another player is taking a speed-earned bonus turn."}); continue
        if not character.get("alive", True) or int(character.get("hp", 1) or 0) <= 0: continue
        blocked = _blocked(character)
        if blocked:
            events.append({"actor": "player", "action": "controlled", "name": name, "status": blocked}); continue
        skills = character.get("skills") if isinstance(character.get("skills"), dict) else {}
        kind, ability, raw_action = _parse_action(person.get("actions"), skills)
        stats = character.get("stats") if isinstance(character.get("stats"), dict) else {}
        primaries = primary_stats_for(world, _mapping(character.get("special")).get("Archetype", "")) or list(stats) or ["Strength"]
        offense = max((float(stats.get(key, 0) or 0) for key in primaries), default=30)
        skill = skills.get(ability) if ability else None
        mastery = float((skill or {}).get("mastery", (skill or {}).get("level", 0)) or 0) if isinstance(skill, dict) else 0
        bonus = round((offense - 30) / 4 + mastery / 5)
        if kind == "defend":
            character["multiplayer_guarding"] = True; events.append({"actor": "player", "name": name, "action": "defend", "result": "braced"}); acted.append(name); continue
        if kind == "flee":
            check = _check(bonus, enemy["attack_min"], enemy["attack_max"], shift)
            events.append({"actor": "player", "name": name, "action": "flee", **check})
            if check["success"]: character["escaped_combat"] = True
            acted.append(name); continue
        padding = 20 if kind == "overwhelm" else 0
        check = _check(bonus, enemy["difficulty_min"] + padding, enemy["difficulty_max"] + padding, shift)
        damage = 0
        if check["success"]:
            damage = max(1, round(enemy["hp_max"] * (.13 + min(60, max(0, check["total"] - check["difficulty"])) / 700)))
            if kind == "overwhelm" and offense - float(enemy["power"]) >= 30: damage = enemy["hp"]
            enemy["hp"] = max(0, int(enemy["hp"]) - damage)
            if ability and isinstance(skill, dict):
                meta = infer_skill_metadata(ability, skill)
                if meta.get("effect_type") in {"control", "debuff"} and meta.get("status_effect"):
                    enemy.setdefault("multiplayer_statuses", []).append({"name": meta["status_effect"], "rounds_left": meta.get("duration_rounds", 2), "blocks_action": meta.get("effect_type") == "control"})
        events.append({"actor": "player", "name": name, "action": kind, "ability": ability, "related_action": raw_action, "damage": damage, **check})
        acted.append(name)
    if int(enemy.get("hp", 0)) <= 0:
        enemy["alive"] = False; combat["active"] = False; combat["outcome"] = "victory"
    hard_enemy_status = next((row for row in enemy.get("multiplayer_statuses", []) if row.get("blocks_action") and int(row.get("rounds_left", 0)) > 0), None)
    earned_bonus = []
    if not bonus_round and enemy.get("alive", True):
        for raw_person in participants or []:
            person = _mapping(raw_person)
            character = characters.get(str(person.get("user_id")), {})
            name = str(character.get("name") or person.get("username") or "Player")
            if name in acted and float((character.get("stats") or {}).get(speed_stat_for(world), 30) or 30) - float(enemy.get("power", 30)) >= 25:
                earned_bonus.append(name)
    if earned_bonus:
        combat["multiplayer_bonus_names"] = earned_bonus
        events.append({"actor": "system", "action": "bonus_turn", "names": earned_bonus, "reason": "Speed advantage earned another player choice before retaliation."})
    elif enemy.get("alive", True):
        if hard_enemy_status:
            events.append({"actor": "enemy", "name": enemy.get("name"), "action": "controlled", "status": hard_enemy_status.get("name")})
        else:
            targets = [(uid, char) for uid, char in characters.items() if char.get("alive", True) and not char.get("escaped_combat") and int(char.get("hp", 1) or 0) > 0]
            if targets:
                uid, target = min(targets, key=lambda pair: int(pair[1].get("hp", 1) or 1) / max(1, int(pair[1].get("hp_max", 100) or 100)))
                defense = float((target.get("stats") or {}).get(defense_stat_for(world), 30) or 30)
                check = _check(round((float(enemy["power"]) - defense) / 4), enemy["attack_min"], enemy["attack_max"], shift)
                damage = max(1, round(int(target.get("hp_max", 100) or 100) * .14)) if check["success"] else 0
                if target.pop("multiplayer_guarding", False): damage = max(1, damage // 2) if damage else 0
                target["hp"] = max(0, int(target.get("hp", 0) or 0) - damage)
                if target["hp"] <= 0: target["alive"] = False
                events.append({"actor": "enemy", "name": enemy.get("name"), "target": target.get("name"), "action": "attack", "damage": damage, **check})
    for row in enemy.get("multiplayer_statuses", []): row["rounds_left"] = max(0, int(row.get("rounds_left", 0)) - 1)
    combat["round"] = int(combat.get("round", 1) or 1) + 1
    if not isinstance(combat.get("log"), list):
        combat["log"] = []
    combat["log"].extend({"round": round_number, **event} for event in events)
    state["combat"] = combat
    summary = " ".join(_event_text(event, enemy.get("name", "Enemy")) for event in events)
    story = [{"text": "[MULTIPLAYER COMBAT]\n" + summary, "tag": "roll"}]
    return {"state": state, "characters": characters, "result": {"status": "resolved", "narrative": summary, "story": story,
            "updates": [], "rolls": [event for event in events if "roll" in event], "notifications": [],
            "interrupted": bool(combat.get("active")), "interruption_kind": "combat" if combat.get("active") else "",
            "interruption_reason": "Combat continues." if combat.get("active") else "Combat ended.",
            "major_event_reached": False}}

def _event_text(event, enemy):
    name = event.get("name") or event.get("actor", "Someone")
    action = event.get("action")
    if action == "attack": return f"{name} attacked {event.get('target') or enemy}: {event.get('total')} vs {event.get('difficulty')} — {'hit for ' + str(event.get('damage')) if event.get('success') else 'miss'} damage."
    if action == "bonus_turn": return f"{', '.join(event.get('names') or [])} earned a chosen bonus turn from speed."
    if action == "controlled": return f"{name} could not act while {event.get('status', 'controlled')}."
    if action == "defend": return f"{name} braced for the counterattack."
    if action == "flee": return f"{name} {'escaped' if event.get('success') else 'failed to escape'}."
    if action == "wait": return f"{name} waits while the speed advantage resolves."
    return f"{name} used {event.get('ability') or action}."
