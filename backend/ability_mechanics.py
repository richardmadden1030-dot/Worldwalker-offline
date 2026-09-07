"""Compile authored ability prose into complete, bounded local mechanics."""
from __future__ import annotations
import copy
import re
from skill_system import infer_skill_metadata
from util import clamp

WORLD_RESOURCES = {"Naruto": "Chakra", "Hunter x Hunter": "Aura", "Bleach": "Reiryoku",
    "Jujutsu Kaisen": "Cursed Energy", "One Piece": "Stamina", "Overgeared": "Mana or cooldown",
    "Solo Max-Level Newbie": "Mana or cooldown", "Reincarnated as a Slime": "Magicules", "Custom World": "Energy"}

def _text(package):
    if not isinstance(package, dict): return str(package or "")
    pieces = []
    for key in ("name", "description", "effect", "governing_rule", "shikai_effect", "bankai_effect", "enhancement", "limitations", "costs", "weakness", "restrictions", "applications"):
        value = package.get(key)
        pieces.extend(map(str, value)) if isinstance(value, list) else pieces.append(str(value)) if value else None
    details = package.get("details")
    if isinstance(details, dict): pieces.extend(str(v) for v in details.values() if isinstance(v, (str, int, float)))
    return " ".join(pieces)

def compile_ability_mechanics(world, package, tier_index=3):
    """Fill missing activation/cost/counter/progression fields without AI."""
    result = copy.deepcopy(package) if isinstance(package, dict) else {"description": str(package or "")}
    name = str(result.get("name") or result.get("true_name") or result.get("shikai_name") or "Original Ability")
    blob = _text(result); explicit = result.get("mechanics") if isinstance(result.get("mechanics"), dict) else {}
    meta = infer_skill_metadata(name, {"description": blob, "mechanics": explicit})
    tier = clamp(int(tier_index or 3), 0, 10); resource = WORLD_RESOURCES.get(world, "Energy")
    effect = meta["effect_type"]; scope = "area" if meta["area"] else meta["target_type"]
    mechanics = copy.deepcopy(result.get("compiled_mechanics")) if isinstance(result.get("compiled_mechanics"), dict) else {}
    mechanics.setdefault("activation", result.get("activation") or ("A deliberate release or transformation" if effect == "transform" else "Focused intent and a deliberate action"))
    mechanics.setdefault("resource", resource)
    mechanics.setdefault("cost", result.get("cost") or result.get("costs") or ("Severe" if tier >= 8 else "High" if tier >= 6 else "Moderate" if tier >= 3 else "Low"))
    mechanics.setdefault("range", result.get("range") or ("Area around the user" if scope in {"area", "enemies", "allies"} else "Close to medium"))
    mechanics.setdefault("targets", scope)
    mechanics.setdefault("duration", result.get("duration") or (f"About {meta['duration_rounds']} combat rounds" if meta["duration_rounds"] else "Immediate"))
    mechanics.setdefault("cooldown", result.get("cooldown") or ("Once per major scene" if tier >= 9 else "Requires recovery after full-output use" if tier >= 6 else "None beyond its resource cost"))
    mechanics.setdefault("effect_type", effect); mechanics.setdefault("status_effect", meta.get("status_effect") or "")
    mechanics.setdefault("counterplay", result.get("weakness") or result.get("limitations") or result.get("counterplay") or f"Interrupt activation, evade its {mechanics['range'].lower()} reach, or exhaust the user's {resource.lower()}.")
    mechanics.setdefault("scaling", result.get("scaling") or f"Output scales with mastery and relevant stats; tier {tier} describes current impact, not an automatic win.")
    mechanics.setdefault("mastery_stages", result.get("mastery_stages") or ["Awakening — reliable core effect", "Refinement — efficient alternate applications", "Mastery — full output with practiced costs and counters"])
    mechanics.setdefault("validation", {"world_resource_named": bool(resource), "has_counterplay": bool(mechanics.get("counterplay")), "has_cost": bool(mechanics.get("cost")), "overwhelming": tier >= 9 or bool(re.search(r"\b(absolute|godlike|immeasurable|reality|infinite)\b", blob, re.I))})
    result["compiled_mechanics"] = mechanics; result.setdefault("mechanics", meta.get("mechanics", {}))
    for key in ("combat_usable", "category", "effect_type", "target_type", "area", "duration_rounds", "status_effect", "status_potency"):
        result.setdefault(key, meta.get(key))
    return result
