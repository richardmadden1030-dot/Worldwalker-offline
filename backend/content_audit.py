"""Deterministic content-depth audit for every bundled world.

This is intentionally local and cheap.  It checks the data the player will
actually receive before an AI call: starts, starter equipment, named ability
support, factions, progression, canon-character state, timelines and opening
guidance.  The report is also useful as a release gate when a world grows.
"""
from __future__ import annotations

import re
from collections import Counter

from worlds import (
    WORLD_DATA, expansion_for, abilities_for, playable_characters_for,
    start_options_for, starting_eras_for, timeline_for, world_primer_for,
)


def _text(value):
    return str(value or "").strip()


def _location_matches(location, map_names):
    """Accept a real sublocation without requiring a redundant map pin."""
    needle = re.sub(r"[^a-z0-9]+", " ", _text(location).lower()).strip()
    if not needle:
        return False
    for name in map_names:
        candidate = re.sub(r"[^a-z0-9]+", " ", _text(name).lower()).strip()
        if needle == candidate or needle in candidate or candidate in needle:
            return True
    aliases = {
        "hunter exam route": "route to the exam",
        "hueco mundo desert": "hueco mundo",
        "sokyoku hill": "seireitei",
        "urahara shop": "karakura town",
        "kurosaki clinic": "karakura town",
        "shin o academy": "seireitei",
        "soul king palace": "royal realm",
    }
    alias = aliases.get(needle)
    return bool(alias and any(alias in re.sub(r"[^a-z0-9]+", " ", n.lower()) for n in map_names))


def _check(area, passed, detail, severity="warning"):
    return {"area": area, "passed": bool(passed), "severity": "ok" if passed else severity, "detail": detail}


def audit_world(world):
    data = WORLD_DATA[world]
    expansion = expansion_for(world)
    starts = start_options_for(world)
    characters = playable_characters_for(world)
    eras = starting_eras_for(world)
    timeline = timeline_for(world)
    events = timeline.get("events", [])
    map_names = [_text(row[0]) for row in data.get("map", []) if isinstance(row, (list, tuple)) and row]
    primer = world_primer_for(world)
    is_custom = world == "Custom World"

    checks = []
    start_bad = [row.get("label") for row in starts if not all(_text(row.get(k)) for k in ("label", "location", "note"))]
    start_unmapped = [row.get("location") for row in starts if not _location_matches(row.get("location"), map_names)]
    checks.append(_check("starts", len(starts) >= (1 if is_custom else 4) and not start_bad,
                         f"{len(starts)} starts; {len(start_bad)} missing player-facing context.", "critical"))
    checks.append(_check("start_map_links", not start_unmapped,
                         "All start locations resolve to the atlas." if not start_unmapped else "Unmapped: " + ", ".join(map(str, start_unmapped))))

    # Equipment is guaranteed by the campaign generator; world-specific
    # equipment labels and loot/requisition vocabulary keep it from becoming
    # the same generic backpack in every setting.
    try:
        from engine_campaign import WORLD_STARTER_GEAR, WORLD_ARCHETYPE_GEAR
        starter_gear = _text(WORLD_STARTER_GEAR.get(world))
        archetype_gear = WORLD_ARCHETYPE_GEAR.get(world, {})
    except Exception:
        starter_gear, archetype_gear = "", {}
    archetypes = expansion.get("archetypes", [])
    missing_gear = [name for name in archetypes if name not in archetype_gear]
    checks.append(_check("equipment", bool(starter_gear) and not missing_gear,
                         f"Starter kit plus {len(archetype_gear)}/{len(archetypes)} archetype loadouts."
                         + ((" Missing: " + ", ".join(missing_gear)) if missing_gear else ""), "critical"))

    ability_names = abilities_for(world)
    systems = expansion.get("systems", [])
    training = expansion.get("training", [])
    checks.append(_check("abilities", len(ability_names) >= 6 and len(training) >= 6,
                         f"{len(ability_names)} world-relative stats and {len(training)} named training paths.", "critical"))
    checks.append(_check("progression", len(data.get("progression", [])) >= 5 and len(systems) >= 4 and bool(_text(data.get("rules"))),
                         f"{len(data.get('progression', []))} progression tracks, {len(systems)} setting systems, and explicit GM rules.", "critical"))

    faction_count = len(data.get("factions", {}))
    checks.append(_check("factions", faction_count >= (1 if is_custom else 4),
                         f"{faction_count} starting factions with independent standing."))

    char_issues = []
    for char in characters:
        required = ("id", "name", "label", "location", "background", "equipment", "skills", "start_day", "starting_quests")
        missing = [key for key in required if not char.get(key) and char.get(key) != 0]
        if missing:
            char_issues.append(f"{char.get('name', 'Unnamed')}: missing {', '.join(missing)}")
        elif not _location_matches(char.get("location"), map_names):
            char_issues.append(f"{char.get('name')}: location '{char.get('location')}' is not atlas-linked")
        unknown_stats = [name for name in (char.get("stat_values") or char.get("stat_minimums") or {}) if name not in ability_names]
        if unknown_stats:
            char_issues.append(f"{char.get('name')}: unknown stats {', '.join(unknown_stats)}")
    char_pass = (not characters and is_custom) or (bool(characters) and not char_issues)
    checks.append(_check("canon_characters", char_pass,
                         f"{len(characters)} playable canon starts normalized."
                         + ((" " + " | ".join(char_issues)) if char_issues else ""), "critical"))

    event_issues = []
    days = []
    titles = []
    for event in events:
        if not all(event.get(k) not in (None, "") for k in ("day", "title", "location", "summary")):
            event_issues.append(_text(event.get("title")) or "Untitled event")
        days.append(event.get("day"))
        titles.append(_text(event.get("title")).lower())
    duplicates = [title for title, count in Counter(titles).items() if title and count > 1]
    timeline_pass = len(events) >= (1 if is_custom else 10) and not event_issues and not duplicates and days == sorted(days)
    checks.append(_check("timelines", timeline_pass,
                         f"{len(events)} ordered events; {sum(bool(e.get('major', True)) for e in events)} major beats."
                         + ((" Incomplete: " + ", ".join(event_issues)) if event_issues else "")
                         + ((" Duplicates: " + ", ".join(duplicates)) if duplicates else ""), "critical"))
    checks.append(_check("eras", bool(eras) or is_custom,
                         f"{len(eras)} selectable original-character eras." if eras else "Custom chronology is authored by the player."))

    primer_fields = ("premise", "tone", "power_system", "starting_note")
    primer_missing = [key for key in primer_fields if not _text(primer.get(key))]
    checks.append(_check("opening_quality", not primer_missing and bool(starts),
                         "Spoiler-safe primer, starting note, and contextual starts are present."
                         if not primer_missing else "Primer missing: " + ", ".join(primer_missing), "critical"))

    passed = sum(row["passed"] for row in checks)
    score = round(100 * passed / max(1, len(checks)))
    return {
        "world": world, "score": score,
        "status": "release-ready" if score == 100 else "needs-attention",
        "counts": {"starts": len(starts), "equipment_loadouts": len(archetype_gear),
                   "abilities": len(ability_names), "factions": faction_count,
                   "canon_characters": len(characters), "eras": len(eras), "timeline_events": len(events)},
        "checks": checks,
        "findings": [row for row in checks if not row["passed"]],
    }


def audit_all_worlds():
    worlds = [audit_world(world) for world in WORLD_DATA]
    issues = [dict(row, world=world["world"]) for world in worlds for row in world["findings"]]
    return {
        "schema": 1,
        "summary": {"worlds": len(worlds), "release_ready": sum(w["status"] == "release-ready" for w in worlds),
                    "issues": len(issues), "critical": sum(x["severity"] == "critical" for x in issues)},
        "worlds": worlds,
        "issues": issues,
    }
