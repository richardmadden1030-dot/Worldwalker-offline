"""Validated installable world-pack loader.

Players can add JSON files under %APPDATA%/WorldwalkerRPG/world_packs. A bad
pack is reported and skipped without preventing the game from launching.
"""
import json
from pathlib import Path


REQUIRED = {"id", "name", "tagline", "resource", "rules", "start", "abilities", "origins", "archetypes", "map"}


def _validate(pack):
    missing = sorted(REQUIRED - set(pack))
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    if not isinstance(pack["abilities"], list) or len(pack["abilities"]) < 3:
        raise ValueError("abilities must contain at least three names")
    if not isinstance(pack["map"], list) or not pack["map"]:
        raise ValueError("map must contain at least one landmark")
    for node in pack["map"]:
        if not isinstance(node, (list, tuple)) or len(node) < 5:
            raise ValueError("each map landmark must be [name, x, y, kind, tier]")
    return pack


def load_world_packs(pack_dir, registries):
    pack_dir = Path(pack_dir)
    loaded, errors = [], []
    try:
        pack_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Optional packs must never make the base game fail to launch.
        return loaded, [{"file": str(pack_dir), "error": f"World-pack folder unavailable: {exc}"}]
    for path in sorted(pack_dir.glob("*.json")):
        try:
            pack = _validate(json.loads(path.read_text(encoding="utf-8")))
            name = str(pack["name"]).strip()
            registries["data"][name] = {
                "tagline": str(pack["tagline"]), "resource": str(pack["resource"]),
                "rules": str(pack["rules"]), "start": str(pack["start"]),
                "progression": list(pack.get("progression", ["Level", "XP", "Skills", "Reputation", "Titles"])),
                "factions": dict(pack.get("factions", {"Local Faction": 0})),
                "map": [tuple(x[:5]) for x in pack["map"]], "special": dict(pack.get("special", {})),
                "pack_id": str(pack["id"]), "pack_version": str(pack.get("version", "1.0")),
            }
            registries["expansions"][name] = {
                "currency": str(pack.get("currency", "Currency")), "origins": list(pack["origins"]),
                "archetypes": list(pack["archetypes"]), "training": list(pack.get("training", [])),
                "shop_types": list(pack.get("shop_types", [])), "loot": list(pack.get("loot", [])),
                "encounters": list(pack.get("encounters", [])), "systems": list(pack.get("systems", [])),
            }
            registries["abilities"][name] = list(pack["abilities"])
            registries["stat_style"][name] = str(pack.get("stat_style", "narrative"))
            registries["gear_style"][name] = str(pack.get("gear_style", "weapon_only"))
            registries["starts"][name] = list(pack.get("start_options", []))
            registries["timelines"][name] = dict(pack.get("timeline", {"start_day": -7, "anchor": "Before the opening incident", "events": []}))
            registries["primary"][name] = dict(pack.get("archetype_primary_stats", {}))
            registries["characters"][name] = list(pack.get("playable_characters", []))
            loaded.append({"id": pack["id"], "name": name, "version": pack.get("version", "1.0"), "file": path.name})
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    return loaded, errors
