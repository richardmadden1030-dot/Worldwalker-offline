"""Deterministic campaign subsystems used around AI-authored narration.

These helpers keep long-campaign memory, world clocks, quest structure,
progression tuning, map planning, and health diagnostics stable even when a
smaller narrator model omits optional bookkeeping.
"""
import copy
import math
import random
import re
import secrets

from util import ai_text
from causality import advance_causal_clock
from politics import political_regions_for_map, tick_polity_governance
from world_atlas import political_atlas

# A chapter is meant to read as a season of the story, not a fixed number of
# actions — consolidate roughly every in-game quarter (90 days on the
# standard 30-day-month calendar) rather than every few turns, so chapter
# count tracks how much story time has actually passed. The beat-count
# backstop exists only for a campaign that lingers a long time without much
# date movement (heavy dialogue, a single extended scene), so chapters still
# happen eventually even then.
CHAPTER_SPAN_DAYS = 90
CHAPTER_BEAT_BACKSTOP = 24


WORLD_PROGRESSION_PRESETS = {
    "One Piece": {"label": "Will and hard-won mastery", "training_rate": 1.08, "breakthrough_rate": 1.10, "xp_rate": 0.0, "travel_scale": 1.45},
    "Hunter x Hunter": {"label": "Nen fundamentals and deliberate conditions", "training_rate": .92, "breakthrough_rate": .85, "xp_rate": 0.0, "travel_scale": 1.10},
    "Naruto": {"label": "Chakra practice, missions, and instruction", "training_rate": 1.00, "breakthrough_rate": 1.00, "xp_rate": 0.0, "travel_scale": 1.00},
    "Solo Max-Level Newbie": {"label": "Tower XP and achievement progression", "training_rate": .88, "breakthrough_rate": 1.05, "xp_rate": 1.18, "travel_scale": .85},
    "Overgeared": {"label": "Satisfy XP, class advancement, quests, affinity, and optional professions", "training_rate": .95, "breakthrough_rate": 1.08, "xp_rate": 1.10, "travel_scale": .90},
    "Reincarnated as a Slime": {"label": "Skills, magicules, naming, and evolution", "training_rate": 1.04, "breakthrough_rate": .92, "xp_rate": 0.0, "travel_scale": 1.05},
    "Bleach": {"label": "Zanjutsu drills, Kido study, and a bond with one's Zanpakuto", "training_rate": .96, "breakthrough_rate": .90, "xp_rate": 0.0, "travel_scale": 1.05},
    "Jujutsu Kaisen": {"label":"Cursed-energy control, physical reinforcement, technique applications and barrier study", "training_rate":1.02, "breakthrough_rate":.92, "xp_rate":0.0, "travel_scale":1.0},
    "Custom World": {"label": "Setting-defined growth", "training_rate": 1.00, "breakthrough_rate": 1.00, "xp_rate": 1.00, "travel_scale": 1.00},
}


LITERAL_QUEST_WORLDS = {"Overgeared", "Solo Max-Level Newbie"}

WORLD_QUEST_PRESENTATION = {
    "Overgeared": {"literal": True, "tab_label": "Quests", "rail_label": "Active Quest", "empty_label": "No active quest", "entry_label": "Quest", "archive_label": "Completed / failed quests"},
    "Solo Max-Level Newbie": {"literal": True, "tab_label": "System Quests", "rail_label": "Active Quest", "empty_label": "No active quest", "entry_label": "Quest", "archive_label": "Completed / failed quests"},
    "Naruto": {"literal": False, "tab_label": "Mission Agenda", "rail_label": "Current Assignment", "empty_label": "No current assignment", "entry_label": "Assignment", "archive_label": "Mission history"},
    "One Piece": {"literal": False, "tab_label": "Voyage Log", "rail_label": "Current Priority", "empty_label": "No current priority", "entry_label": "Priority", "archive_label": "Past voyages and promises"},
    "Hunter x Hunter": {"literal": False, "tab_label": "Hunter Agenda", "rail_label": "Current Case", "empty_label": "No current case", "entry_label": "Case", "archive_label": "Closed cases and hunts"},
    "Bleach": {"literal": False, "tab_label": "Division Agenda", "rail_label": "Current Order", "empty_label": "No current order", "entry_label": "Order", "archive_label": "Completed orders and incidents"},
    "Reincarnated as a Slime": {"literal": False, "tab_label": "Journey Agenda", "rail_label": "Current Concern", "empty_label": "No current concern", "entry_label": "Concern", "archive_label": "Resolved concerns"},
    "Custom World": {"literal": False, "tab_label": "Agenda", "rail_label": "Current Direction", "empty_label": "No current direction", "entry_label": "Agenda", "archive_label": "Past goals and outcomes"},
}


def uses_literal_quests(world):
    return str(world or "Custom World") in LITERAL_QUEST_WORLDS


def quest_presentation_for(world):
    return copy.deepcopy(WORLD_QUEST_PRESENTATION.get(str(world or "Custom World"), WORLD_QUEST_PRESENTATION["Custom World"]))


WORLD_TERRITORIES = {
    "One Piece": {"Shells Town": "Marines", "Loguetown": "Marines", "Enies Lobby": "World Government", "Sabaody": "World Government", "Arlong Park": "Pirates",
                  "Fishman Island": "Whitebeard Pirates", "Totto Land": "Big Mom Pirates", "Wano Country": "Kaido's Beasts Pirates",
                  "Marineford": "Marines", "Impel Down": "World Government"},
    "Hunter x Hunter": {"Hunter Exam Site": "Hunter Association", "Hunter Association HQ": "Hunter Association", "Meteor City": "Phantom Troupe", "Kukuroo Mountain": "Zoldyck Family", "Yorknew City": "Yorknew Mafia"},
    "Naruto": {"Konohagakure": "Konohagakure", "Sunagakure": "Sunagakure", "Kirigakure": "Kirigakure", "Kumogakure": "Kumogakure", "Iwagakure": "Iwagakure",
               "Amegakure": "Amegakure", "Iron Country": "Iron Country"},
    # Floors are self-contained stages, not neighboring countries. The tower
    # overview therefore has no misleading territorial blobs; per-floor maps
    # can later use the same board contract as Bleach realms.
    "Solo Max-Level Newbie": {},
    "Overgeared": {"Winston": "Eternal Kingdom", "Titan": "Saharan Empire", "Saharan Empire": "Saharan Empire", "Reidan": "Eternal Kingdom", "Reinhardt": "Eternal Kingdom", "Valhalla": "Valhalla"},
    "Reincarnated as a Slime": {"Great Jura Forest": "Jura Forest", "Goblin Village": "Jura Forest", "Tempest": "Jura Tempest Federation", "Kingdom of Falmuth": "Kingdom of Falmuth", "Dwargon": "Armed Nation of Dwargon", "Holy Empire of Lubelius": "Holy Empire of Lubelius", "Eurazania": "Beast Kingdom Eurazania", "Jistav": "Jistav", "El Dorado": "El Dorado"},
    # Hueco Mundo/Las Noches deliberately have no controller seeded here —
    # at this world's default campaign start (pre-Aizen-reveal), who
    # actually holds it isn't public knowledge yet, and seeding one would
    # spoil the Soul Society arc's own twist before the story gets there.
    "Bleach": {"Seireitei": "Gotei 13", "Rukongai": "Gotei 13", "Shin'o Academy": "Gotei 13",
               "Senzaikyu": "Central 46", "Central 46 Chambers": "Central 46"},
    "Custom World": {"Starting Region": "Local Faction"},
}


WORLD_MAP_META = {
    "One Piece": {"projection": "World sea chart", "accuracy_note": "Routes and relative seas follow established canon; many islands have no survey-grade coordinates."},
    "Hunter x Hunter": {"projection": "Known World and Lake Mobius", "accuracy_note": "Confirmed regions are preserved; deliberately undisclosed locations remain approximate."},
    "Naruto": {"projection": "Shinobi continent", "accuracy_note": "Major countries and villages follow canon relative geography; borders remain narrative and repaintable."},
    "Solo Max-Level Newbie": {"projection": "Tower overview", "accuracy_note": "Floors are sequential realms, not adjacent territory. Individual floor maps are reserved for a later update."},
    "Overgeared": {"projection": "Satisfy continental atlas", "accuracy_note": "Confirmed places and political relationships are prioritized where the source does not publish a complete atlas."},
    "Reincarnated as a Slime": {"projection": "Central World", "accuracy_note": "Nations follow their established relationship to the Great Jura Forest; borders remain campaign-reactive."},
    "Bleach": {"projection": "Realm atlas", "accuracy_note": "Each dimension has its own board. Switching boards changes only the view, never the character's location."},
    "Jujutsu Kaisen": {"projection": "Japan", "accuracy_note": "Schools, incidents, and Culling Game barriers follow their established regions; overlays are not political borders."},
    "Custom World": {"projection": "Campaign atlas", "accuracy_note": "The atlas grows and repaints as the narrative establishes new geography and control."},
}

BLEACH_REALM_NODES = {
    "Soul Society": {"Rukongai": (50,52), "North Rukongai": (50,14), "East Rukongai": (81,50), "South Rukongai": (50,86), "West Rukongai": (18,50), "Shin'o Academy": (42,43), "Seireitei": (50,50), "Gotei 13 Barracks": (58,59), "Kido Corps Headquarters": (55,43), "Onmitsukido Headquarters": (40,54), "Senzaikyu": (45,60), "Sokyoku Hill": (61,38), "Central 46 Chambers": (50,58), "Maggot's Nest": (19,63), "Muken": (50,91), "Silbern": (50,50)},
    "World of the Living": {"Karakura Town": (50,52), "Karakura High School": (55,49), "Kurosaki Clinic": (41,63), "Urahara Shop": (31,68), "Naruki City": (72,25), "Urahara Training Grounds": (70,81), "Senkaimon": (94,34), "Dangai": (96,43), "Valley of Screams": (92,56)},
    "Hueco Mundo": {"Hueco Mundo Desert": (50,50), "Forest of Menos": (68,69), "Las Noches": (72,25), "Garganta": (14,22)},
    "Royal Realm": {"Soul King Palace": (50,44), "Royal Guard Domains": (28,28), "Wahrwelt": (81,72)},
    "Hell": {"Gates of Hell": (23,17)},
}
BLEACH_REALM_IMAGES = {realm: f"/assets/generated_maps/Bleach_{realm.replace(' ', '_')}.webp" for realm in BLEACH_REALM_NODES}


def _bleach_realm_and_anchor(location):
    text = str(location or "").lower()
    if any(word in text for word in ("hueco", "las noches", "menos")):
        return "Hueco Mundo", "Hueco Mundo Desert"
    if any(word in text for word in ("royal realm", "soul king", "royal palace", "zero division", "squad zero", "wahrwelt")):
        return "Royal Realm", "Soul King Palace"
    if "hell" in text:
        return "Hell", "Gates of Hell"
    if any(word in text for word in ("soul society", "seireitei", "rukongai", "division", "gotei", "academy", "sokyoku", "senzaikyu", "central 46", "muken", "maggot")):
        anchor = "Gotei 13 Barracks" if "division" in text or "barracks" in text else "Seireitei"
        return "Soul Society", anchor
    return "World of the Living", "Karakura Town"


def progression_preset_for(world):
    return copy.deepcopy(WORLD_PROGRESSION_PRESETS.get(world, WORLD_PROGRESSION_PRESETS["Custom World"]))


def default_tuning_for(world):
    preset = progression_preset_for(world)
    return {
        "check_warning_threshold": 65,
        "xp_rate": preset["xp_rate"] if preset["xp_rate"] else 1.0,
        "training_rate": preset["training_rate"],
        "breakthrough_rate": preset["breakthrough_rate"],
        "combat_danger": 1.0,
        "resource_pressure": 1.0,
    }


def normalize_tuning(state):
    defaults = default_tuning_for(state.get("world", "Custom World"))
    current = state.get("difficulty_controls") if isinstance(state.get("difficulty_controls"), dict) else {}
    clean = {}
    for key, default in defaults.items():
        try:
            value = float(current.get(key, default))
        except (TypeError, ValueError):
            value = default
        if key == "check_warning_threshold":
            clean[key] = int(max(40, min(95, value)))
        else:
            clean[key] = round(max(.5, min(2.0, value)), 2)
    state["difficulty_controls"] = clean
    state["progression_preset"] = progression_preset_for(state.get("world", "Custom World"))
    return clean


def _list(value):
    if isinstance(value, list): return value
    if value in (None, ""): return []
    return [value]


def normalize_quest_state_machine(state):
    """Keep literal quests mechanical and narrative-world agendas flexible."""
    literal = uses_literal_quests(state.get("world"))
    completed = []
    for quest in state.get("quests", []):
        if not isinstance(quest, dict):
            continue
        raw_objectives = quest.get("objectives")
        if not isinstance(raw_objectives, list) or not raw_objectives:
            raw_objectives = quest.get("clear_conditions") or quest.get("conditions") or []
        objectives = []
        for index, raw in enumerate(_list(raw_objectives)):
            if isinstance(raw, dict):
                text = str(raw.get("text") or raw.get("name") or raw.get("objective") or f"Objective {index + 1}")[:500]
                status = str(raw.get("status") or ("complete" if raw.get("complete") else "active")).lower()
                objectives.append({"id": str(raw.get("id") or f"obj-{index + 1}"), "text": text,
                                   "status": status if status in {"active", "complete", "failed", "locked"} else "active",
                                   "optional": bool(raw.get("optional")), "progress": max(0, min(100, int(raw.get("progress", 100 if status == "complete" else 0) or 0)))})
            else:
                objectives.append({"id": f"obj-{index + 1}", "text": str(raw)[:500], "status": "active", "optional": False, "progress": 0})
        quest["agenda_mode"] = "literal" if literal else "narrative"
        quest["objectives"] = objectives
        quest["completion_conditions"] = [obj["text"] for obj in objectives if not obj.get("optional")]
        quest["optional_objectives"] = [obj["text"] for obj in objectives if obj.get("optional")]
        quest["discovered_clues"] = _list(quest.get("discovered_clues") or quest.get("current_knowledge") or quest.get("evidence"))
        quest["current_obstacles"] = _list(quest.get("current_obstacles") or quest.get("risks"))
        quest["next_hint"] = str(quest.get("next_hint") or quest.get("first_step") or
                                 (f"Continue working on: {next((o['text'] for o in objectives if o['status'] == 'active'), 'the next known lead')}") )[:500]
        required = [obj for obj in objectives if not obj.get("optional")]
        branch = quest.get("branch_state") if isinstance(quest.get("branch_state"), dict) else {}
        branch.setdefault("current", "main")
        branch["available"] = [str(x)[:300] for x in _list(branch.get("available")) if str(x).strip()]
        branch["locked"] = [str(x)[:300] for x in _list(branch.get("locked")) if str(x).strip()]
        if not literal:
            # These fields remain private continuity memory, but narrative
            # worlds never turn them into a progress bar, mandatory route, or
            # automatic completion gate. The fiction may resolve a mission by
            # any logically valid route the GM and player establish.
            quest.pop("progress_percent", None)
            generic_routes = (
                "follow the primary lead:", "seek an alternate route through",
                "investigate an alternate route at", "search for an alternate source",
            )
            branch["available"] = [name for name in branch["available"] if not name.lower().startswith(generic_routes)]
            branch["locked"] = []
            branch["routes"] = [
                {"name": name, "status": "possible", "consequence": "One possible approach; other story-valid approaches remain available."}
                for name in branch["available"]
            ]
            quest["branch_state"] = branch
            quest.setdefault("developments", [])
            quest.setdefault("commitments", [])
            explanation = str(quest.get("explanation") or quest.get("description") or "").strip()
            if not explanation or explanation.lower().startswith(("no additional explanation", "no briefing recorded", "no explanation recorded")):
                source = str(quest.get("giver") or quest.get("cause") or "your current circumstances").strip()
                quest["explanation"] = (
                    f"{quest.get('name', 'This concern')} remains active. It began with {source}; "
                    f"current circumstances point toward {quest['next_hint'].rstrip('.')} ."
                ).replace(" .", ".")[:2000]
            if str(quest.get("status", "active")).lower() in {"complete", "completed"}:
                completed.append(quest.get("name", "Agenda"))
            continue

        required_progress = [obj.get("progress", 0) for obj in objectives if not obj.get("optional")]
        quest["progress_percent"] = round(sum(required_progress) / len(required_progress)) if required_progress else 0
        # A quest without choices is an isolated checklist.  Seed two grounded
        # routes from its own briefing, then unlock the confrontation route as
        # earlier required objectives are completed.  This is deterministic
        # scaffolding; the narrator can replace or enrich it with specific
        # world-authored branches on later turns.
        if not branch["available"] and not branch["locked"]:
            locations = _list(quest.get("locations") or quest.get("location"))
            giver = str(quest.get("giver") or quest.get("cause") or "the quest giver").strip()
            lead = str(quest.get("next_hint") or quest.get("first_step") or "the primary lead").strip()
            branch["available"] = [f"Follow the primary lead: {lead}"[:300]]
            alternate = (f"Seek an alternate route through {giver}" if giver else
                         f"Investigate an alternate route at {locations[0]}" if locations else "Search for an alternate source")
            if alternate.lower() not in {x.lower() for x in branch["available"]}:
                branch["available"].append(alternate[:300])
            if required:
                branch["locked"] = [f"Directly resolve: {required[-1]['text']}"[:300]]
        completed_required = [obj for obj in objectives if not obj.get("optional") and obj.get("status") == "complete"]
        if completed_required and branch["locked"]:
            unlocked = branch["locked"].pop(0)
            if unlocked.lower() not in {x.lower() for x in branch["available"]}:
                branch["available"].append(unlocked)
        branch["routes"] = [
            {"name": name, "status": "available", "consequence": "Choosing this route may close or alter competing approaches."}
            for name in branch["available"]
        ] + [
            {"name": name, "status": "locked", "consequence": "Complete an earlier objective or discover the missing prerequisite."}
            for name in branch["locked"]
        ]
        quest["branch_state"] = branch
        quest.setdefault("consequences", [])
        if required and all(obj.get("status") == "complete" for obj in required):
            quest["status"] = "Completed"
            completed.append(quest.get("name", "Quest"))
    return completed


def update_chapter_memory(before, state, trigger, narrative, recap=None):
    turn = int(state.get("turn", 0) or 0)
    canon_day = int(state.get("canon_day", 0) or 0)
    from chapter_recaps import compact_recap
    clean_narrative = compact_recap([{"summary": narrative, "action": trigger}], state.get("name", ""), max_words=150)
    changes = []
    if before.get("location") != state.get("location"):
        changes.append(f"Moved to {state.get('location')}.")
    old_titles = set(ai_text(t) for t in before.get("titles", []) if ai_text(t))
    new_titles = set(ai_text(t) for t in state.get("titles", []) if ai_text(t))
    if new_titles - old_titles: changes.append("Titles: " + ", ".join(sorted(new_titles - old_titles)))
    old_skills, new_skills = set(before.get("skills", {})), set(state.get("skills", {}))
    if new_skills - old_skills: changes.append("Skills: " + ", ".join(sorted(new_skills - old_skills)))
    old_quests = {str(q.get("name")) for q in before.get("quests", []) if isinstance(q, dict)}
    new_quests = {str(q.get("name")) for q in state.get("quests", []) if isinstance(q, dict)}
    if new_quests - old_quests: changes.append("New quests: " + ", ".join(sorted(new_quests - old_quests)))
    beat = {"turn": turn, "time": state.get("world_time", ""), "canon_day": canon_day,
            "action": str(trigger or "World advance")[:300], "summary": clean_narrative, "changes": changes}
    buffer = state.setdefault("chapter_buffer", [])
    buffer.append(beat)
    state["chapter_buffer"] = buffer[-CHAPTER_BEAT_BACKSTOP:]
    buffer = state["chapter_buffer"]
    first_day = buffer[0].get("canon_day", canon_day)
    days_elapsed = canon_day - first_day
    if days_elapsed < CHAPTER_SPAN_DAYS and len(buffer) < CHAPTER_BEAT_BACKSTOP:
        return None
    chapter_number = len(state.setdefault("chapter_summaries", [])) + 1
    snippets = [entry.get("summary", "") for entry in buffer if entry.get("summary")]
    summary = " ".join(snippets)[:2400]
    chapter = {
        "number": chapter_number,
        "title": f"Chapter {chapter_number}: {state.get('location', 'A Changing World')}",
        "turns": [buffer[0].get("turn", turn), buffer[-1].get("turn", turn)],
        "time_span": f"{buffer[0].get('time', '')} — {buffer[-1].get('time', '')}",
        "summary": summary,
        "key_decisions": [entry.get("action") for entry in buffer if entry.get("action")][:12],
        "lasting_changes": [change for entry in buffer for change in entry.get("changes", [])][:20],
        "unresolved_quests": [q.get("name") for q in state.get("quests", []) if isinstance(q, dict) and str(q.get("status", "active")).lower() == "active"],
    }
    from chapter_recaps import finish_recap
    finish_recap(chapter, buffer, state.get("name", ""), recap)
    state["chapter_summaries"].append(chapter)
    state["chapter_summaries"] = state["chapter_summaries"][-60:]
    state["chapter_buffer"] = []
    return chapter


def _clock(name, kind, goal, threshold=100):
    return {"name": name, "kind": kind, "goal": goal, "progress": 0, "threshold": threshold, "status": "active",
            "last_update": "Not yet advanced", "method": "organized effort" if kind == "faction" else "personal effort",
            "target_location": "", "travel_remaining_days": 0, "dependencies": [],
            "resources": {"capacity": 50, "influence": 50, "logistics": 50, "intelligence": 50}, "resource_cost": {},
            "strategic_goal": goal if kind == "faction" else "", "immediate_goal": goal,
            "operations": [], "alliances": [], "rivals": [], "leadership": {}, "recent_outcomes": []}


def _faction_operation_type(goal):
    text = str(goal or "").lower()
    if re.search(r"\b(?:war|attack|invade|seize|defeat|destroy|defend|military)\b", text): return "military"
    if re.search(r"\b(?:trade|market|supply|resource|contract|econom)\b", text): return "economic"
    if re.search(r"\b(?:spy|intel|investigat|secret|infiltrat|discover)\b", text): return "intelligence"
    if re.search(r"\b(?:ally|alliance|treaty|negotiate|diploma|recruit)\b", text): return "diplomatic"
    return "influence"


def _normalize_faction_strategy(state, name, clock):
    """Upgrade legacy faction clocks into compact living strategic actors."""
    goal = str(clock.get("goal") or f"Advance {name}'s current agenda")
    clock["strategic_goal"] = str(clock.get("strategic_goal") or clock.get("core_ambition") or goal)
    clock["immediate_goal"] = str(clock.get("immediate_goal") or goal)
    resources = clock.get("resources") if isinstance(clock.get("resources"), dict) else {}
    holdings = sum(1 for detail in (state.get("location_details") or {}).values()
                   if isinstance(detail, dict) and detail.get("controlling_faction") == name)
    baseline = max(20, min(90, 45 + holdings * 5))
    for key in ("capacity", "influence", "logistics", "intelligence"):
        try: resources[key] = max(0, min(100, int(resources.get(key, baseline) or baseline)))
        except (TypeError, ValueError): resources[key] = baseline
    clock["resources"] = resources
    clock["alliances"] = list(dict.fromkeys([*(clock.get("alliances") or []), *([clock.get("ally")] if clock.get("ally") else [])]))[:12]
    clock["rivals"] = list(dict.fromkeys([*(clock.get("rivals") or []), *([clock.get("opponent")] if clock.get("opponent") else [])]))[:12]
    leadership = clock.get("leadership") if isinstance(clock.get("leadership"), dict) else {}
    if not leadership.get("leader"):
        leader = next((npc for npc, memory in (state.get("npc_memories") or {}).items()
                       if isinstance(memory, dict) and memory.get("leads_faction") == name), "")
        if leader: leadership["leader"] = leader
    leader_memory = (state.get("npc_memories") or {}).get(leadership.get("leader"), {})
    if isinstance(leader_memory, dict) and str(leader_memory.get("status", "active")).lower() in {"deceased", "dead", "captured", "exiled"}:
        leadership["status"] = "succession pressure"
    else:
        leadership.setdefault("status", "stable" if leadership.get("leader") else "unconfirmed")
    clock["leadership"] = leadership
    operations = [copy.deepcopy(op) for op in (clock.get("operations") or []) if isinstance(op, dict)][-12:]
    if not any(op.get("status") == "active" for op in operations):
        objective = clock["immediate_goal"]
        operations.append({
            "id": f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}-op-{int(state.get('turn', 0) or 0)}",
            "type": _faction_operation_type(objective), "objective": objective,
            "target_location": clock.get("target_location") or clock.get("contested_location") or "",
            "progress": 0, "status": "active", "started_turn": int(state.get("turn", 0) or 0),
        })
    clock["operations"] = operations
    clock["recent_outcomes"] = [copy.deepcopy(row) for row in (clock.get("recent_outcomes") or []) if isinstance(row, dict)][-12:]
    return clock


# A nemesis clock deliberately takes much longer to reach its turning point
# than an ordinary companion/NPC clock (100) — a major canon villain's scheme
# is meant to loom over a long stretch of the campaign, not resolve in a
# handful of world-clock ticks like an ordinary recurring NPC's errand.
NEMESIS_CLOCK_THRESHOLD = 260


def tick_world_clocks(state, elapsed_minutes):
    faction_clocks = state.setdefault("faction_clocks", {})
    for name in state.get("factions", {}):
        faction_clocks.setdefault(name, _clock(name, "faction", f"Advance {name}'s current agenda"))
    for name, clock in faction_clocks.items():
        if isinstance(clock, dict): _normalize_faction_strategy(state, name, clock)
    npc_clocks = state.setdefault("npc_clocks", {})
    for name, memory in state.get("npc_memories", {}).items():
        if not isinstance(memory, dict): continue
        goal = memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal")
        nemesis = bool(memory.get("nemesis"))
        important = memory.get("recurring") or nemesis or str(memory.get("importance", "")).lower() in {"important", "major", "high"}
        if goal or important:
            clock = npc_clocks.setdefault(name, _clock(name, "npc", str(goal or "Pursue a private objective"),
                                                         NEMESIS_CLOCK_THRESHOLD if nemesis else 100))
            if nemesis:
                clock["nemesis"] = True
    elapsed_days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    step = max(1, min(18, int(math.ceil(1 + elapsed_days * 3))))
    propose_faction_conflicts(state, elapsed_days)
    events = []
    for clock_kind, clocks in (("faction", faction_clocks), ("npc", npc_clocks)):
        for key, clock in clocks.items():
            if not isinstance(clock, dict) or clock.get("status") not in {None, "active"}: continue
            causal_step = advance_causal_clock(state, clock.get("name") or key, clock, step, elapsed_days, clock_kind)
            if clock_kind == "faction":
                active_operation = next((op for op in clock.get("operations", []) if isinstance(op, dict) and op.get("status") == "active"), None)
                if active_operation:
                    resource_key = {"military":"logistics", "economic":"capacity", "intelligence":"intelligence", "diplomatic":"influence"}.get(active_operation.get("type"), "influence")
                    resource = int((clock.get("resources") or {}).get(resource_key, 50) or 50)
                    operation_step = max(1, round(causal_step * (.65 + resource / 140)))
                    active_operation["progress"] = min(100, int(active_operation.get("progress", 0) or 0) + operation_step)
                    if active_operation["progress"] >= 100:
                        active_operation["status"] = "completed"; active_operation["completed_turn"] = int(state.get("turn", 0) or 0)
                        outcome = {"turn": int(state.get("turn", 0) or 0), "operation": active_operation.get("objective"), "result": "Reached a strategic decision point"}
                        clock["recent_outcomes"] = [*clock.get("recent_outcomes", []), outcome][-12:]
                        clock["immediate_goal"] = f"Consolidate the result of {active_operation.get('objective')}"
                        events.append({"type":"world", "faction": key,
                                       "message": f"{key} has brought an operation to a decision point: {active_operation.get('objective')}."})
                    # Activity spends capacity but ordinary time also restores
                    # organizational readiness. This keeps resources relevant
                    # without turning them into a second economy screen.
                    clock["resources"][resource_key] = max(0, resource - max(0, operation_step // 8))
                    clock["resources"]["capacity"] = min(100, int(clock["resources"].get("capacity", 50)) + max(1, int(elapsed_days // 7)))
                leadership = clock.get("leadership", {})
                if leadership.get("status") == "succession pressure" and not leadership.get("pressure_reported"):
                    events.append({"type":"world", "faction": key,
                                   "message": f"{key} faces a leadership vacuum; its existing agenda continues, but internal contenders are beginning to shape how it is pursued."})
                    leadership["pressure_reported"] = True
            clock["progress"] = min(int(clock.get("threshold", 100) or 100), int(clock.get("progress", 0) or 0) + causal_step)
            clock["last_update"] = state.get("world_time", "")
            if clock["progress"] >= int(clock.get("threshold", 100) or 100):
                clock["status"] = "turning_point"
                # clock.get("name") is set whenever _clock() creates the
                # entry, but the GM can also author npc_clocks/faction_clocks
                # directly via state_patch and isn't guaranteed to include
                # it — falling back to the dict key keeps this readable
                # ("None's agenda...") instead of silently mislabeling whose
                # agenda actually moved.
                who = clock.get("name") or key
                # A clock with a declared opponent gets resolved as a real
                # conflict below instead — this generic line is only for the
                # ordinary "nothing to mechanically resolve yet" case.
                if str(clock.get("opponent") or "").strip():
                    continue
                # Same field-preference pattern as npc_memories' goal
                # layering — a faction's immediate_goal (what it's actually
                # doing right now) is what a turning point should describe,
                # not the flat placeholder .goal every faction starts with.
                current_goal = clock.get("immediate_goal") or clock.get("goal")
                if clock.get("nemesis"):
                    events.append({"type": "world", "nemesis": True,
                                    "message": f"⚠ Word reaches you that {who}'s scheme has reached a breaking point: {current_goal}."})
                else:
                    events.append({"type": "world", "message": f"Somewhere beyond your own path, {who} has made real headway: {current_goal}."})
    events.extend(resolve_clock_conflicts(state))
    events.extend(tick_polity_governance(
        state, elapsed_minutes,
        set(WORLD_TERRITORIES.get(state.get("world", ""), {}).values()),
    ))
    return events


def active_nemesis_threats(state):
    """Named villains whose long-running scheme (tracked the same way as a
    companion subplot, via npc_memories[name].nemesis) has just reached its
    breaking point — the GM should build toward a real confrontation for
    these soon rather than letting the moment quietly pass."""
    out = []
    for name, clock in (state.get("npc_clocks") or {}).items():
        if isinstance(clock, dict) and clock.get("nemesis") and clock.get("status") == "turning_point":
            out.append({"name": clock.get("name") or name, "goal": clock.get("goal", "")})
    return out


def _clock_power(clock):
    try:
        return max(1, min(100, int((clock or {}).get("power", 50) or 50)))
    except (TypeError, ValueError):
        return 50


def _effective_power(name, located):
    """A side's own power plus half their declared ally's power, if that
    ally exists and isn't itself already out of the fight — a lightweight
    stand-in for reinforcement without a full multi-front battle model."""
    _, clock = located.get(name, (None, None))
    if not clock:
        return 50
    base = _clock_power(clock)
    ally_name = str(clock.get("ally") or "").strip()
    if ally_name:
        _, ally_clock = located.get(ally_name, (None, None))
        if ally_clock and ally_clock.get("status") not in ("destroyed", "defeated"):
            base += _clock_power(ally_clock) // 2
    return base


# How low a side's power has to fall, after losing a resolved conflict,
# before it's treated as genuinely wiped out rather than merely weakened —
# giving clocks real permanent stakes instead of only narrative texture.
FACTION_DESTROYED_THRESHOLD = 15
NPC_DEFEATED_THRESHOLD = 15

# Chance per eligible multi-day tick that the sim proposes a background
# skirmish on its own, so faction conflict doesn't depend entirely on the
# GM remembering to declare one.
PROPOSED_CONFLICT_CHANCE = 0.12


def propose_faction_conflicts(state, elapsed_days):
    """Occasionally proposes a skirmish between two eligible, currently
    territory-holding canon factions so the world keeps moving even if the
    GM never gets around to declaring a conflict itself. Always marked
    `proposed` — resolve_clock_conflicts forces these to a stalemate rather
    than ever letting bare dice decide something as canon-significant as a
    faction's survival; only a GM-declared conflict (informed by the GM's
    actual canon knowledge) can end in a real win, loss, or destruction."""
    if elapsed_days < 1 or random.random() > PROPOSED_CONFLICT_CHANCE:
        return
    faction_clocks = state.get("faction_clocks") or {}
    holdings = {}
    world = state.get("world", "")
    # Begin with canon ownership, then let campaign overrides replace it.
    for loc, faction in WORLD_TERRITORIES.get(world, {}).items():
        if faction:
            holdings.setdefault(faction, []).append(loc)
    for loc, detail in (state.get("location_details") or {}).items():
        if isinstance(detail, dict):
            # Remove a canon location from its old owner's holding list before
            # applying the campaign's real current controller, including an
            # explicit empty/unclaimed result.
            for places in holdings.values():
                if loc in places:
                    places.remove(loc)
            f = detail.get("controlling_faction") if "controlling_faction" in detail else detail.get("faction")
            if f:
                holdings.setdefault(f, []).append(loc)
    eligible = [name for name, clock in faction_clocks.items()
                if isinstance(clock, dict) and clock.get("status") == "active"
                and not str(clock.get("opponent") or "").strip() and name in holdings]
    if len(eligible) < 2:
        return
    attacker, defender = random.sample(eligible, 2)
    clock = faction_clocks[attacker]
    clock["opponent"], clock["proposed"], clock["player_involved"] = defender, True, False
    clock["contested_location"] = random.choice(holdings[defender])
    clock["progress"] = min(clock.get("threshold", 100), int(clock.get("progress", 0) or 0) + 45)


def resolve_clock_conflicts(state):
    """Off-screen faction-vs-faction / NPC-vs-opponent conflict resolution.

    A clock that reaches its turning point with a GM-declared `opponent`
    rolls a strength-weighted contest between the two sides instead of just
    narrating a vague turning point — territory can change hands, and a side
    that loses badly enough is genuinely destroyed (a faction) or lost (an
    NPC), independent of whether the player witnessed any of it. A clock
    with no opponent (the ordinary case, and a nemesis whose real target is
    the player) is left completely untouched by this — it only ever fires
    for a conflict the GM explicitly opted into. A clock the application
    itself proposed (see propose_faction_conflicts) always ends in a
    stalemate instead, unless the GM has since flagged player_involved —
    only a GM-declared or GM-supervised conflict can end in a real outcome."""
    located = {}
    for coll_name in ("faction_clocks", "npc_clocks"):
        for name, clock in (state.get(coll_name) or {}).items():
            if isinstance(clock, dict):
                located[name] = (coll_name, clock)

    events = []
    resolved_this_tick = set()
    for coll_name in ("faction_clocks", "npc_clocks"):
        for name, clock in list((state.get(coll_name) or {}).items()):
            # Guards a mutual matchup (A's opponent is B and B's opponent is
            # A) from resolving twice in the same tick if both happened to
            # cross their threshold together — once either side has been
            # consumed as an actor or an opponent, it's settled for this tick.
            if name in resolved_this_tick:
                continue
            if not isinstance(clock, dict) or clock.get("status") != "turning_point":
                continue
            opponent_name = str(clock.get("opponent") or "").strip()
            if not opponent_name:
                continue
            resolved_this_tick.add(name)
            resolved_this_tick.add(opponent_name)
            opp_coll, opp_clock = located.get(opponent_name, (None, None))
            location = str(clock.get("contested_location") or "").strip()

            if clock.get("proposed") and not clock.get("player_involved"):
                # Pure dice never get to decide a faction's survival — a
                # sim-proposed skirmish always ends in a stalemate: both
                # sides feel it, nobody wins, nothing permanent changes.
                clock["power"] = max(1, _clock_power(clock) - 8)
                if opp_clock: opp_clock["power"] = max(1, _clock_power(opp_clock) - 8)
                clock["progress"], clock["opponent"], clock["contested_location"], clock["proposed"] = 0, "", "", False
                events.append({"type": "world", "conflict": True,
                                "message": f"⚔ {name} and {opponent_name} clash" + (f" over {location}" if location else "") + ", but neither gains lasting advantage."})
                continue

            power, opp_power = _effective_power(name, located), _effective_power(opponent_name, located)
            won = random.random() * (power + opp_power) < power
            ally_name = str(clock.get("ally") or "").strip()
            opp_ally_name = str(opp_clock.get("ally") or "").strip() if opp_clock else ""
            clock["progress"], clock["opponent"], clock["contested_location"], clock["proposed"] = 0, "", "", False
            winner_name = name if won else opponent_name
            winner_coll = coll_name if won else opp_coll
            if won:
                clock["power"], clock["status"] = min(100, _clock_power(clock) + 12), "active"
                if opp_clock: opp_clock["power"] = max(0, _clock_power(opp_clock) - 20)
                loser_name, loser_coll, loser_clock = opponent_name, opp_coll, opp_clock
                winner_ally, loser_ally = ally_name, opp_ally_name
            else:
                clock["power"] = max(0, _clock_power(clock) - 20)
                if opp_clock: opp_clock["power"] = min(100, _clock_power(opp_clock) + 12)
                loser_name, loser_coll, loser_clock = name, coll_name, clock
                winner_ally, loser_ally = opp_ally_name, ally_name
            # A contributing ally shares lightly in the outcome — reinforcing
            # troops gain a little from a win, or get bloodied in a loss.
            for reinforcer, delta in ((winner_ally, 3), (loser_ally, -5)):
                _, reinforcer_clock = located.get(reinforcer, (None, None))
                if reinforcer_clock and reinforcer_clock.get("status") not in ("destroyed", "defeated"):
                    reinforcer_clock["power"] = max(0, min(100, _clock_power(reinforcer_clock) + delta))
            if location and winner_coll == "faction_clocks":
                state.setdefault("location_details", {}).setdefault(location, {})["controlling_faction"] = winner_name
            if won:
                message = f"⚔ {name} has triumphed over {opponent_name}" + (f", seizing control of {location}." if location else ".")
            else:
                message = f"⚔ {name}'s campaign against {opponent_name} has failed." + (f" {opponent_name} holds {location}." if location else "")
            events.append({"type": "world", "conflict": True, "message": message})
            if loser_clock is not None and loser_coll is not None:
                threshold = FACTION_DESTROYED_THRESHOLD if loser_coll == "faction_clocks" else NPC_DEFEATED_THRESHOLD
                if loser_clock.get("power", 50) <= threshold and loser_clock.get("status") not in ("destroyed", "defeated"):
                    protected = _is_canon_protected(state, loser_name, loser_coll)
                    if loser_coll == "faction_clocks":
                        if protected:
                            # A canon-major power can be battered without
                            # being erased outright — an off-screen dice
                            # roll destroying Konoha or the World Government
                            # would break the setting's own premise, not
                            # just this campaign's continuity. It survives,
                            # weakened, instead of being wiped out.
                            loser_clock["power"] = max(loser_clock.get("power", 0), threshold + 1)
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has been badly weakened by {winner_name}, but holds on."})
                        else:
                            loser_clock["status"] = "destroyed"
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has been effectively wiped out by {winner_name}."})
                            events.extend(_collapse_faction(state, loser_name, winner_name))
                    else:
                        if protected:
                            loser_clock["power"] = max(loser_clock.get("power", 0), threshold + 1)
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} barely survives {winner_name}'s assault, badly shaken."})
                        else:
                            loser_clock["status"] = "defeated"
                            state.setdefault("npc_memories", {}).setdefault(loser_name, {})["status"] = "deceased"
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has fallen, defeated by {winner_name}."})
    return events


def _is_canon_protected(state, name, kind):
    """A background/GM-declared conflict can weaken or displace a
    canon-major power, but shouldn't casually erase one outright. Factions
    are checked against this world's own known canon polities (the same
    WORLD_TERRITORIES already used to seed the map's starting territory
    colors) — cheap, reliable, no new authoring needed. NPCs have no
    equivalent built-in roster reliable enough to check automatically, so
    they're protected only when the GM has explicitly flagged them via
    npc_memories[name].canon_protected — a scripted-to-matter-later figure
    the GM knows about, not a guess this function can make on its own."""
    if kind == "faction_clocks":
        world = state.get("world", "")
        return name in set(WORLD_TERRITORIES.get(world, {}).values())
    memory = (state.get("npc_memories") or {}).get(name)
    return isinstance(memory, dict) and bool(memory.get("canon_protected"))


_LEADER_FATES = (("deceased", 0.25), ("captured", 0.40), ("exiled", 0.35))


def _collapse_faction(state, loser_name, winner_name):
    """A destroyed faction doesn't just lose the one contested location —
    everything else it held becomes genuinely unclaimed (a real power
    vacuum a neighboring faction can move into next) instead of frozen in
    place, and whoever led it shares in its fall rather than quietly
    continuing to exist untouched."""
    events = []
    vacated = []
    # Materialize canon holdings as campaign overrides when their owner
    # collapses, otherwise map_snapshot's canon fallback would restore them.
    for loc, faction in WORLD_TERRITORIES.get(state.get("world", ""), {}).items():
        if faction == loser_name:
            detail = state.setdefault("location_details", {}).setdefault(loc, {})
            if "controlling_faction" not in detail:
                detail["controlling_faction"] = ""
                vacated.append(loc)
    for loc, detail in (state.get("location_details") or {}).items():
        if isinstance(detail, dict) and detail.get("controlling_faction") == loser_name:
            detail["controlling_faction"] = ""
            if loc not in vacated:
                vacated.append(loc)
    if vacated:
        events.append({"type": "world", "conflict": True,
                        "message": f"With {loser_name} gone, {', '.join(vacated)} " +
                                   ("are" if len(vacated) > 1 else "is") + " left unclaimed — ripe for another power to move in."})
    leaders = [name for name, mem in (state.get("npc_memories") or {}).items()
               if isinstance(mem, dict) and mem.get("leads_faction") == loser_name and mem.get("status") != "deceased"]
    for leader in leaders:
        roll, total = random.random(), 0.0
        fate = _LEADER_FATES[-1][0]
        for label, weight in _LEADER_FATES:
            total += weight
            if roll <= total:
                fate = label
                break
        state["npc_memories"][leader]["status"] = fate
        events.append({"type": "world", "conflict": True,
                        "message": f"{loser_name}'s leader, {leader}, has been {fate} in the collapse."})
    return events


def _chain_entries(value):
    """Sanitize a consequence-chain list (continuity.py) for display: keep
    only well-formed {event, turn, canon_day} entries, most recent first,
    capped for the journal card rather than the full stored history."""
    if not isinstance(value, list):
        return []
    out = [{"event": str(item.get("event"))[:300], "turn": item.get("turn"), "canon_day": item.get("canon_day")}
           for item in value if isinstance(item, dict) and item.get("event")]
    return list(reversed(out[-6:]))


def relationship_snapshot(state):
    rows = []
    memories = state.get("npc_memories", {})
    relationships = state.get("relationships", {})
    contacts = state.get("contacts", {})
    for name in sorted(set(memories) | set(relationships) | set(contacts)):
        contact = contacts.get(name, {}) if isinstance(contacts.get(name), dict) else {}
        # Major factions are contactable from campaign start, but a group
        # contact is not a person and should stay in the faction sections.
        if contact.get("kind") == "group" and name not in memories and name not in relationships:
            continue
        mem = memories.get(name) if isinstance(memories.get(name), dict) else {}
        raw = relationships.get(name, {})
        if isinstance(raw, dict):
            score = raw.get("score", raw.get("trust", mem.get("trust", 0)))
            label = raw.get("label", raw.get("status", mem.get("attitude", "Unknown")))
            promises = _list(raw.get("promises")) + _list(mem.get("promises"))
            debts = _list(raw.get("debts")) + _list(mem.get("debts"))
        else:
            score, label, promises, debts = raw, mem.get("attitude", "Unknown"), _list(mem.get("promises")), _list(mem.get("debts"))
        try: score = int(score or 0)
        except (TypeError, ValueError): score = 0
        rows.append({"name": name, "score": max(-100, min(100, score)), "label": str(label or "Unknown"),
                     "last_known_location": mem.get("last_known_location", "Unknown"), "knowledge": _list(mem.get("knows") or mem.get("knowledge")),
                     "promises": list(dict.fromkeys(map(str, promises)))[:20], "debts": list(dict.fromkeys(map(str, debts)))[:20],
                     "goal": mem.get("immediate_goal") or mem.get("goal") or mem.get("current_goal") or "Unknown", "contact": contacts.get(name, {}),
                     # mid_term_goal/core_ambition are optional depth beyond the
                     # single goal line every NPC already gets — only present
                     # once the GM has actually bothered laying out this NPC's
                     # longer arc, not backfilled for every minor character.
                     "mid_term_goal": mem.get("mid_term_goal") or "", "core_ambition": mem.get("core_ambition") or "",
                     "nemesis": bool(mem.get("nemesis")), "chain": _chain_entries(mem.get("chain"))})
    affiliations = []
    for aff in state.get("affiliations", []):
        if not isinstance(aff, dict) or not str(aff.get("faction", "")).strip():
            continue
        affiliations.append({
            "faction": str(aff.get("faction", "")).strip(), "rank": str(aff.get("rank", "Member") or "Member"),
            "status": str(aff.get("status", "active") or "active"), "joined": str(aff.get("joined", "")),
            "notes": str(aff.get("notes", "")),
        })
    npc_network = []
    for key, rel in (state.get("npc_relationships") or {}).items():
        if not isinstance(rel, dict):
            continue
        a, b = str(rel.get("a") or "").strip(), str(rel.get("b") or "").strip()
        if not a or not b:
            parts = str(key).split("::", 1)
            a = a or (parts[0] if parts else "")
            b = b or (parts[1] if len(parts) > 1 else "")
        if not a or not b:
            continue
        try:
            strength = max(-100, min(100, int(rel.get("strength", 0) or 0)))
        except (TypeError, ValueError):
            strength = 0
        npc_network.append({"a": a, "b": b, "type": str(rel.get("type") or "unknown"),
                             "strength": strength, "status": str(rel.get("status") or "active"),
                             "note": str(rel.get("note") or "")})
    faction_chain = state.get("faction_chain") if isinstance(state.get("faction_chain"), dict) else {}
    return {"people": rows, "factions": [{"name": name, "standing": value, "chain": _chain_entries(faction_chain.get(name))}
                                          for name, value in state.get("reputation", {}).items()],
            "affiliations": affiliations, "npc_network": npc_network}


def campaign_health(state):
    issues = []
    def add(severity, area, message, fix, repair_id=""):
        issues.append({"severity": severity, "area": area, "message": message, "suggestion": fix,
                       "repair_id": repair_id, "repairable": bool(repair_id)})
    if not state.get("quests"): add("warning", "Journey", "No active quest is giving the campaign a visible medium-term objective.", "Follow a current lead or declare a personal quest.")
    if not state.get("chapter_summaries") and int(state.get("turn", 0) or 0) >= 8: add("warning", "Memory", "No chapter summary exists for this older campaign.", "Advance once to let the chapter memory system consolidate recent turns.")
    for quest in state.get("quests", []):
        if isinstance(quest, dict) and not quest.get("objectives"): add("error", "Quest", f"{quest.get('name', 'A quest')} has no tracked objectives.", "Normalize it into a safe discovery objective.", "normalize_quests")
        if isinstance(quest, dict) and not (quest.get("next_hint") or quest.get("first_step")): add("warning", "Quest", f"{quest.get('name', 'A quest')} has no actionable next hint.", "Add a conservative investigate-the-requirements lead.", "normalize_quests")
    vague_skills = [name for name, value in state.get("skills", {}).items() if not isinstance(value, dict) or not (value.get("description") or value.get("effect"))]
    if vague_skills: add("warning", "Skills", f"{len(vague_skills)} skill descriptions are incomplete.", "Add readable placeholder descriptions without inventing mechanics.", "describe_skills")
    if state.get("continuity_ledger", {}).get("warnings"): add("error", "Continuity", "The continuity ledger contains unresolved warnings.", "Review Journal → Continuity before a long skip.")
    if not state.get("npc_memories") and int(state.get("turn", 0) or 0) >= 4: add("warning", "NPCs", "No recurring NPC memory has been established.", "Interact with named characters or pursue a social lead.")
    memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    if int(state.get("turn", 0) or 0) >= 4 and not any(memory.get(key) for key in ("established_facts", "player_goals", "consequences")):
        add("warning", "Memory", "Long-term narrative memory has no established facts, goals, or consequences.", "Complete a meaningful turn so the memory ledger can establish campaign anchors.")
    if state.get("location") not in state.get("discovered_locations", []): add("error", "Map", "The current location is missing from discovered locations.", "Add the current location to the discovered map.", "map_current_location")
    dead = {name for name, row in (state.get("npc_memories") or {}).items() if isinstance(row, dict) and str(row.get("status", "")).lower() in {"dead", "deceased"}}
    active_dead = [ai_text(c.get("name") if isinstance(c, dict) else c) for c in state.get("companions", []) if ai_text(c.get("name") if isinstance(c, dict) else c) in dead]
    if active_dead: add("error", "Party", f"Deceased companions remain active: {', '.join(active_dead)}.", "Remove them from the active party while preserving their history.", "remove_deceased_companions")
    duplicate_rewards = 0
    for key in ("titles", "achievements"):
        labels = [ai_text(x.get("name") if isinstance(x, dict) else x).lower() for x in state.get(key, [])]
        duplicate_rewards += len([x for i, x in enumerate(labels) if x and x in labels[:i]])
    if duplicate_rewards: add("warning", "Rewards", f"{duplicate_rewards} duplicate title or achievement entries were detected.", "Remove exact duplicates while keeping the first record.", "deduplicate_rewards")
    blocked = [clock for clocks in (state.get("npc_clocks", {}), state.get("faction_clocks", {})) for clock in clocks.values() if isinstance(clock, dict) and clock.get("blocked_reason")]
    if blocked: add("warning", "World causality", f"{len(blocked)} off-screen agenda(s) are blocked by travel, resources, or prerequisites.", "Review World Clocks to see the specific causal blockers.")
    score = max(0, 100 - sum(18 if x["severity"] == "error" else 8 for x in issues))
    return {"score": score, "status": "Healthy" if score >= 85 else "Needs attention" if score >= 60 else "Unstable", "issues": issues,
            "counts": {"active_quests": len(state.get("quests", [])), "chapters": len(state.get("chapter_summaries", [])),
                       "npc_clocks": len(state.get("npc_clocks", {})), "faction_clocks": len(state.get("faction_clocks", {})),
                       "continuity_warnings": len(state.get("continuity_ledger", {}).get("warnings", [])),
                       "memory_records": sum(len(v) for v in memory.values() if isinstance(v, list)),
                       "knowledge_audits": len(state.get("knowledge_audit", [])),
                       "causal_records": len(state.get("causality_ledger", [])),
                       "repairs": len(state.get("health_repairs", []))}}


def tension_level(state):
    """A lightweight, always-available read on how dangerous the player's
    current situation is — synthesized entirely from signals the game
    already tracks (HP, active combat, an imminent promised confrontation,
    the Tower's floor countdown where it applies). This is a UI aid only,
    never written back into narrative canon or shown to the GM as fact."""
    try:
        hp_max = max(1.0, float(state.get("hp_max", 100) or 100))
        hp_ratio = max(0.0, min(1.0, float(state.get("hp", hp_max) or 0) / hp_max))
    except (TypeError, ValueError):
        hp_ratio = 1.0
    score = 0
    reasons = []
    if hp_ratio < 0.15: score += 55; reasons.append("critically low HP")
    elif hp_ratio < 0.35: score += 35; reasons.append("badly hurt")
    elif hp_ratio < 0.6: score += 15; reasons.append("wounded")
    if isinstance(state.get("combat"), dict) and state["combat"].get("active"):
        score += 25; reasons.append("in active combat")
    canon_day = state.get("canon_day", 0) or 0
    soonest_days = None
    for sched in state.get("scheduled_events", []) or []:
        if not isinstance(sched, dict) or sched.get("resolved") or sched.get("due_canon_day") is None:
            continue
        if str(sched.get("visibility", "confirmed")).lower() == "hidden":
            continue
        try:
            days = int(sched["due_canon_day"]) - int(canon_day)
        except (TypeError, ValueError):
            continue
        if days >= 0 and (soonest_days is None or days < soonest_days):
            soonest_days = days
    if soonest_days is not None:
        if soonest_days <= 2: score += 25; reasons.append("a promised confrontation is imminent")
        elif soonest_days <= 7: score += 12; reasons.append("a promised confrontation is approaching")
    if state.get("world") == "Solo Max-Level Newbie" and not state.get("tower_over"):
        deadline = state.get("tower_floor_deadline_day")
        if isinstance(deadline, (int, float)):
            days_left = max(0, int(deadline - canon_day))
            if days_left <= 3: score += 30; reasons.append("the floor's countdown is nearly out")
            elif days_left <= 14: score += 15; reasons.append("the floor's countdown is running low")
    if active_nemesis_threats(state):
        score += 20; reasons.append("a nemesis threat has reached a breaking point")
    score = min(100, score)
    label = "Critical" if score >= 70 else "Tense" if score >= 40 else "Uneasy" if score >= 15 else "Calm"
    return {"score": score, "label": label, "reasons": reasons}


def pacing_guidance(state):
    """Deterministic pacing nudge for the GM prompt — a thin wrapper around
    signals the game already tracks (tension_level, the canon day of the
    last major beat, chapter count) rather than a new subsystem. Returns an
    instruction string to fold into gm_rules, or "" most turns, when pacing
    looks fine and there's nothing worth saying."""
    recent = [row.get("kind") for row in (state.get("pacing_profile") or {}).get("recent_beats", [])
              if isinstance(row, dict) and row.get("kind")]
    if len(recent) >= 3 and len(set(recent[-3:])) == 1:
        repeated = recent[-1]
        alternatives = {
            "combat": "let consequences, recovery, relationships, discovery, or strategy breathe before another unrelated fight",
            "training": "turn accumulated growth into a test, relationship beat, discovery, or concrete opportunity",
            "social": "let a decision produce action, travel, investigation, or a material consequence",
            "exploration": "let a discovered place produce a person, conflict, choice, or reward rather than another arrival",
            "politics": "show one policy or order changing ordinary lives before introducing another council decision",
            "recovery": "introduce a specific voluntary lead without manufacturing danger",
            "story": "shift the dramatic texture with a grounded social, growth, exploration, or consequence beat",
        }
        guidance = (f"\n- PACING RHYTHM: the last {min(3, len(recent))} resolved beats were all {repeated}. "
                    f"Unless the player's current order explicitly continues that activity, {alternatives.get(repeated, alternatives['story'])}. "
                    "Do not manufacture a genre change; vary the next meaningful beat through existing people, obligations, consequences, and locations.")
        state.setdefault("pacing_profile", {})["last_guidance"] = guidance
        return guidance
    if len(state.get("chapter_summaries") or []) < 1:
        return ""  # early campaigns can still use repetition detection above
    last_beat_day = state.get("last_major_beat_day")
    if not isinstance(last_beat_day, (int, float)):
        return ""
    days_since_beat = int(state.get("canon_day", 0) or 0) - int(last_beat_day)
    label = tension_level(state)["label"]
    if days_since_beat >= 10 and label in ("Calm", "Uneasy"):
        guidance = (f"\n- PACING: it has been {days_since_beat} in-story days since the last major turning point, and the "
                "situation currently reads as low-stakes. Proactively introduce a concrete complication, opportunity, or "
                "piece of rising pressure this turn rather than continuing routine, low-stakes narration — the player "
                "should rarely go this long without something new to engage with.")
        state.setdefault("pacing_profile", {})["last_guidance"] = guidance
        return guidance
    if days_since_beat <= 1 and label in ("Tense", "Critical"):
        guidance = ("\n- PACING: multiple major beats have landed in very quick succession. Ease off for this turn or the "
                "next — let the player process, recover, and act on what just happened before introducing the next "
                "major pressure or event.")
        state.setdefault("pacing_profile", {})["last_guidance"] = guidance
        return guidance
    return ""


# Shops are only loosely specified in the GM prompt ("populate shops with
# name/type and plausible inventory/prices") — there's no strict schema, so
# an inventory item might be a {name, price} dict, use "item"/"cost"/"value"
# instead, or even just be a free-text string. This has to tolerate all of
# that rather than assume one shape.
_PRICE_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _clean_money_number(value, default=0):
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(number) if number.is_integer() else round(number, 4)


def parse_price(value):
    """Pull a plausible non-negative price out of a loosely-typed
    shop item field — a raw number, or free text like '50 Berries' or
    'Price: 1,200'. Fractional prices are preserved for economies where
    ordinary purchases cost less than one primary coin."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = _clean_money_number(value, None)
        return None if number is None else max(0, number)
    if isinstance(value, str):
        match = _PRICE_NUMBER_RE.search(value.replace(",", ""))
        if match:
            try:
                number = float(match.group(0))
                return max(0, int(number) if number.is_integer() else round(number, 4))
            except ValueError:
                return None
    return None


def ensure_currency_state(state):
    """Normalize currency and seed durable accounting containers.

    Slime stores an exact copper-equivalent integer alongside its familiar
    Gold Coin amount. Existing saves and AI-facing state retain Gold Coins,
    while local arithmetic no longer truncates fractional purchases to zero.
    """
    currency = state.get("currency") if isinstance(state.get("currency"), dict) else {}
    currency.setdefault("name", "Currency")
    currency["amount"] = _clean_money_number(currency.get("amount"), 0)
    if state.get("world") == "Reincarnated as a Slime":
        scale = 10_000
        currency.update({
            "name": "Gold Coin", "storage_unit": "Copper Coin",
            "minor_per_major": scale,
            "denominations": {"Gold Coin": scale, "Silver Coin": 100, "Copper Coin": 1},
        })
        expected_minor = int(round(float(currency.get("amount", 0)) * scale))
        if not isinstance(currency.get("amount_minor"), (int, float)) or isinstance(currency.get("amount_minor"), bool):
            currency["amount_minor"] = expected_minor
        else:
            currency["amount_minor"] = int(round(currency["amount_minor"]))
            currency["amount"] = round(currency["amount_minor"] / scale, 4)
    state["currency"] = currency
    state.setdefault("currencies", {})
    state.setdefault("currency_ledger", [])
    state.setdefault("finance_debts", [])
    return currency


def format_currency_amount(currency):
    if not isinstance(currency, dict):
        return "0 Currency"
    scale = int(currency.get("minor_per_major", 0) or 0)
    if scale > 1:
        minor = int(round(currency.get("amount_minor", float(currency.get("amount", 0) or 0) * scale)))
        sign = "-" if minor < 0 else ""
        minor = abs(minor)
        gold, remainder = divmod(minor, scale)
        silver, copper = divmod(remainder, 100)
        parts = []
        if gold:
            parts.append(f"{gold:,} Gold")
        if silver:
            parts.append(f"{silver} Silver")
        if copper or not parts:
            parts.append(f"{copper} Copper")
        return sign + " ".join(parts)
    amount = _clean_money_number(currency.get("amount"), 0)
    shown = f"{amount:,}" if isinstance(amount, int) else f"{amount:,.4f}".rstrip("0").rstrip(".")
    return f"{shown} {currency.get('name', 'Currency')}"


def _currency_account(state, currency_name=None):
    primary = ensure_currency_state(state)
    requested = str(currency_name or primary.get("name") or "Currency").strip()
    if not requested or requested.casefold() == str(primary.get("name", "")).casefold():
        return "primary", primary.get("name", "Currency"), primary
    currencies = state.setdefault("currencies", {})
    key = next((name for name in currencies if str(name).casefold() == requested.casefold()), requested)
    raw = currencies.get(key, 0)
    if isinstance(raw, dict):
        account = raw
        account["amount"] = _clean_money_number(account.get("amount"), 0)
    else:
        account = {"amount": _clean_money_number(raw, 0)}
    return "secondary", key, account


def currency_balance(state, currency_name=None):
    kind, _, account = _currency_account(state, currency_name)
    if kind == "primary" and int(account.get("minor_per_major", 0) or 0) > 1:
        return round(account.get("amount_minor", 0) / account["minor_per_major"], 4)
    return _clean_money_number(account.get("amount"), 0)


def record_currency_transaction(state, delta, reason, category="transaction", currency_name=None,
                                source="system", metadata=None):
    """Apply one local money change and explain it in the durable ledger."""
    delta = _clean_money_number(delta, 0)
    kind, name, account = _currency_account(state, currency_name)
    before = currency_balance(state, name)
    after = _clean_money_number(before + delta, 0)
    if kind == "primary":
        scale = int(account.get("minor_per_major", 0) or 0)
        if scale > 1:
            account["amount_minor"] = int(round(after * scale))
            account["amount"] = round(account["amount_minor"] / scale, 4)
        else:
            account["amount"] = after
        state["currency"] = account
    else:
        original = state.setdefault("currencies", {}).get(name)
        if isinstance(original, dict):
            account["amount"] = after
            state["currencies"][name] = account
        else:
            state["currencies"][name] = after
    row = {
        "id": secrets.token_hex(6), "turn": state.get("turn", 0),
        "canon_day": state.get("canon_day"), "currency": name,
        "amount": delta, "balance_after": after,
        "category": str(category or "transaction")[:60],
        "reason": str(reason or "Money changed hands")[:300],
        "source": str(source or "system")[:60],
    }
    if isinstance(metadata, dict) and metadata:
        row["metadata"] = copy.deepcopy(metadata)
    state.setdefault("currency_ledger", []).append(row)
    state["currency_ledger"] = state["currency_ledger"][-200:]
    return row


def record_observed_currency_change(state, delta, reason, currency_name=None, source="gm"):
    """Record a money delta already applied by a guarded GM patch.

    Unlike ``record_currency_transaction`` this never changes the balance a
    second time; it only makes an AI-authored gain or expense auditable.
    """
    delta = _clean_money_number(delta, 0)
    if not delta:
        return None
    currency_name = str(currency_name or ensure_currency_state(state).get("name") or "Currency")
    row = {
        "id": secrets.token_hex(6), "turn": state.get("turn", 0),
        "canon_day": state.get("canon_day"), "currency": currency_name,
        "amount": delta, "balance_after": currency_balance(state, currency_name),
        "category": "narrative_transaction", "reason": str(reason or "Narrative transaction")[:300],
        "source": str(source or "gm")[:60],
    }
    state.setdefault("currency_ledger", []).append(row)
    state["currency_ledger"] = state["currency_ledger"][-200:]
    return row


def record_opening_currency(state, reason="Starting funds from the character's established background"):
    currency = ensure_currency_state(state)
    if currency.get("tracked") is False:
        return None
    balance = currency_balance(state, currency.get("name"))
    if state.get("currency_ledger"):
        return state["currency_ledger"][0]
    row = {
        "id": secrets.token_hex(6), "turn": state.get("turn", 0),
        "canon_day": state.get("canon_day"), "currency": currency.get("name", "Currency"),
        "amount": balance, "balance_after": balance, "category": "opening_balance",
        "reason": str(reason)[:300], "source": "character_creation",
    }
    state.setdefault("currency_ledger", []).append(row)
    return row


def record_finance_debt(state, label, amount, currency_name=None, notes=""):
    amount = max(0, _clean_money_number(amount, 0))
    if not amount:
        return None
    currency_name = str(currency_name or ensure_currency_state(state).get("name") or "Currency")
    debts = state.setdefault("finance_debts", [])
    debt = next((row for row in debts if isinstance(row, dict) and row.get("active", True)
                 and str(row.get("label", "")).casefold() == str(label).casefold()
                 and str(row.get("currency", "")).casefold() == currency_name.casefold()), None)
    if debt is None:
        debt = {"id": secrets.token_hex(6), "label": str(label)[:160], "currency": currency_name,
                "amount": 0, "active": True, "created_turn": state.get("turn", 0), "history": []}
        debts.append(debt)
    debt["amount"] = _clean_money_number(debt.get("amount", 0) + amount, 0)
    debt["notes"] = str(notes or debt.get("notes") or "")[:500]
    debt.setdefault("history", []).append({"turn": state.get("turn", 0), "change": amount, "reason": "Payment came due"})
    debt["history"] = debt["history"][-30:]
    state["finance_debts"] = debts[-100:]
    return debt


def resolve_finance_debt(state, debt_id, requested_amount=None):
    debts = state.get("finance_debts") if isinstance(state.get("finance_debts"), list) else []
    debt = next((row for row in debts if isinstance(row, dict) and row.get("id") == debt_id and row.get("active", True)), None)
    if debt is None:
        return False, "That obligation is no longer outstanding.", None
    owed = max(0, _clean_money_number(debt.get("amount"), 0))
    available = max(0, currency_balance(state, debt.get("currency")))
    requested = owed if requested_amount in (None, "") else max(0, _clean_money_number(requested_amount, 0))
    payment = min(owed, available, requested)
    if payment <= 0:
        return False, f"No {debt.get('currency', 'currency')} is available to pay this obligation.", None
    record_currency_transaction(state, -payment, f"Paid {debt.get('label', 'outstanding obligation')}",
                                "debt_payment", debt.get("currency"), "player")
    debt["amount"] = _clean_money_number(owed - payment, 0)
    debt.setdefault("history", []).append({"turn": state.get("turn", 0), "change": -payment, "reason": "Player payment"})
    debt["active"] = debt["amount"] > 0
    remaining = debt["amount"]
    message = f"Paid {payment:g} {debt.get('currency', 'currency')} toward {debt.get('label', 'the obligation')}."
    message += f" {remaining:g} remains outstanding." if remaining else " The obligation is settled."
    return True, message, payment


def _shop_item_name(item):
    if isinstance(item, dict):
        return str(item.get("name") or item.get("item") or "").strip()
    return str(item).strip()


def _shop_item_price(item):
    if isinstance(item, dict):
        for key in ("price", "cost", "value"):
            if key in item:
                price = parse_price(item[key])
                if price is not None:
                    return price
        return None
    return parse_price(item)


def _shop_item_currency(state, item):
    primary = ensure_currency_state(state)
    if isinstance(item, dict):
        requested = item.get("currency") or item.get("currency_name") or item.get("price_currency")
        if requested:
            return str(requested).strip()
    return str(primary.get("name") or "Currency")


def _inventory_item_from_purchase(item, display_name, source):
    """Preserve reusable item mechanics while dropping shop bookkeeping."""
    if isinstance(item, dict):
        saved = copy.deepcopy(item)
        for key in ("price", "cost", "value", "stock", "currency", "currency_name", "price_currency"):
            saved.pop(key, None)
        saved["name"] = display_name
        saved["source"] = source
        return saved
    return {"name": display_name, "source": source}


def resolve_shop_purchase(state, shop_name, item_name):
    """Deterministic buy: once a shop item has a real price, the arithmetic
    of paying for it doesn't need an AI turn at all — this mutates state
    in place and never touches the model, so there's no way for it to
    produce the narrated-but-not-patched currency drift the continuity
    detector (continuity.py) otherwise exists to catch after the fact.
    Returns (ok, message, price_paid_or_None)."""
    if isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False:
        return False, "This world does not use tracked money; ordinary access comes through favors, requisitions, and story consequences.", None
    shops = state.get("shops") if isinstance(state.get("shops"), list) else []
    shop = next((sh for sh in shops if isinstance(sh, dict)
                 and str(sh.get("name", "")).strip().lower() == str(shop_name or "").strip().lower()), None)
    if not shop:
        return False, f"No shop named '{shop_name}' is known here.", None
    inventory = shop.get("inventory") if isinstance(shop.get("inventory"), list) else (
        shop.get("items") if isinstance(shop.get("items"), list) else [])
    item = next((it for it in inventory if _shop_item_name(it).strip().lower() == str(item_name or "").strip().lower()), None)
    if item is None:
        return False, f"'{item_name}' isn't in {shop.get('name', shop_name)}'s current inventory.", None
    if isinstance(item, dict) and isinstance(item.get("stock"), (int, float)) and item.get("stock") <= 0:
        return False, f"'{item_name}' is sold out.", None
    price = _shop_item_price(item)
    if price is None:
        return False, f"'{item_name}' doesn't have a clear price and can't be bought this way.", None
    try:
        from property_economy import purchase_price
        price = purchase_price(state, shop.get("name", shop_name), _shop_item_name(item), price)
    except Exception:
        pass
    currency_name = _shop_item_currency(state, item)
    amount = currency_balance(state, currency_name)
    if amount < price:
        return False, f"Not enough {currency_name} — {_shop_item_name(item)} costs {price:g}, you have {amount:g}.", None
    display_name = _shop_item_name(item)
    record_currency_transaction(
        state, -price, f"Bought {display_name} from {shop.get('name', shop_name)}",
        "purchase", currency_name, "shop", {"shop": shop.get("name", shop_name), "item": display_name},
    )
    state.setdefault("inventory", []).append(_inventory_item_from_purchase(
        item, display_name, f"Bought from {shop.get('name', shop_name)}"))
    if isinstance(item, dict) and isinstance(item.get("stock"), (int, float)):
        item["stock"] = item["stock"] - 1
        if item["stock"] <= 0:
            inventory.remove(item)
    return True, f"Bought {display_name} from {shop.get('name', shop_name)} for {price:g} {currency_name}.", price


def record_purchase_offer(state):
    """A transient, AI-facing purchase_offer ({item, price, vendor}) — set
    whenever this turn's narrative presents a concrete opportunity to buy
    something, e.g. a merchant naming a price mid-scene — becomes a
    permanent, app-owned entry in purchase_offers with a real id and
    resolved=false. Mirrors the npc_memories[name].chain_event pattern in
    continuity.py: the AI's job is just naming what's on offer, the app
    owns the durable bookkeeping (id, resolved state) so a purchase can
    never be trusted to whatever the client echoes back on click. Returns
    a small dict for the story entry's `detail` (None if nothing valid was
    offered) so the Chronicle can render a real Buy button for it."""
    raw = state.pop("purchase_offer", None)
    state["purchase_offer"] = None
    if isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False:
        return None
    if not isinstance(raw, dict):
        return None
    item = str(raw.get("item") or "").strip()
    price = parse_price(raw.get("price"))
    if not item or price is None:
        return None
    offer_id = secrets.token_hex(6)
    vendor = str(raw.get("vendor") or "").strip()
    offers = state.setdefault("purchase_offers", [])
    currency_name = str(raw.get("currency") or (state.get("currency") or {}).get("name", "Currency"))
    offer_metadata = raw.get("item_details") if isinstance(raw.get("item_details"), dict) else {}
    offers.append({"id": offer_id, "item": item, "price": price, "currency": currency_name,
                   "vendor": vendor, "item_details": copy.deepcopy(offer_metadata),
                   "turn": state.get("turn", 0), "resolved": False})
    state["purchase_offers"] = offers[-20:]
    return {"id": offer_id, "item": item, "price": price, "vendor": vendor, "currency": currency_name}


def resolve_purchase_offer(state, offer_id):
    """Deterministic buy for a narrative purchase_offer (see
    record_purchase_offer above): looks up the REAL stored price by id —
    never trusts a client-supplied price — deducts currency, adds
    inventory, and marks the offer resolved so it can't be bought twice.
    Returns (ok, message, price_paid_or_None), same shape as
    resolve_shop_purchase."""
    if isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False:
        return False, "This world does not use tracked money; equipment comes through narrative access instead.", None
    offers = state.get("purchase_offers") if isinstance(state.get("purchase_offers"), list) else []
    offer = next((o for o in offers if isinstance(o, dict) and o.get("id") == offer_id), None)
    if offer is None:
        return False, "That offer is no longer available.", None
    if offer.get("resolved"):
        return False, f"You already bought {offer.get('item')}.", None
    price = offer.get("price")
    currency_name = str(offer.get("currency") or (state.get("currency") or {}).get("name") or "Currency")
    amount = currency_balance(state, currency_name)
    if amount < price:
        return False, f"Not enough {currency_name} — {offer.get('item')} costs {price:g}, you have {amount:g}.", None
    record_currency_transaction(
        state, -price, f"Bought {offer.get('item')} from {offer.get('vendor') or 'an offer'}",
        "purchase", currency_name, "chronicle_offer", {"offer_id": offer_id},
    )
    detail = copy.deepcopy(offer.get("item_details")) if isinstance(offer.get("item_details"), dict) else {}
    detail.update({"name": offer.get("item"), "source": f"Bought from {offer.get('vendor') or 'an offer'}"})
    state.setdefault("inventory", []).append(detail)
    offer["resolved"] = True
    return True, f"Bought {offer.get('item')} for {price:g} {currency_name}.", price


def _notable_individuals_for(state, place_name):
    """Best-effort cross-reference for the map's info panel: named people
    (not locations/factions/items) whose codex notes or last-known location
    mention this place. There's no dedicated location-link field in either
    structure, so this is a loose substring match, same spirit as the
    location-category matching used elsewhere."""
    place_l = str(place_name).lower()
    names = []
    for entry in state.get("codex", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "")).lower() in ("location", "faction", "item", "region"):
            continue
        if place_l in str(entry.get("notes", "")).lower():
            name = entry.get("name")
            if name:
                names.append(str(name))
    npc_memories = state.get("npc_memories", {})
    if isinstance(npc_memories, dict):
        for name, info in npc_memories.items():
            if not isinstance(info, dict):
                continue
            loc = str(info.get("location") or info.get("last_location") or info.get("last_known_location") or "").lower()
            if loc and (place_l in loc or loc in place_l):
                names.append(str(name))
    return list(dict.fromkeys(names))


def map_snapshot(state, world_map, world):
    current = str(state.get("location", ""))
    discovered = set(state.get("discovered_locations", []))
    territories = WORLD_TERRITORIES.get(world, {})
    # Original locations the story itself introduced (a new village, a hidden
    # camp, a ruin nobody canon ever named) — the AI places these with its
    # own x/y on request; skip any that collide by name with a fixed map
    # entry rather than let a custom one silently shadow a canon location.
    fixed_names = {str(n[0]).lower() for n in world_map}
    custom_nodes = []
    for entry in state.get("custom_locations", []) or []:
        if not isinstance(entry, dict): continue
        name = str(entry.get("name") or "").strip()
        if not name or name.lower() in fixed_names: continue
        try:
            x, y = float(entry.get("x", 50)), float(entry.get("y", 50))
        except (TypeError, ValueError):
            x, y = 50.0, 50.0
        custom_nodes.append((name, x, y, str(entry.get("kind") or "landmark"), int(entry.get("tier", 1) or 1)))
    full_map = list(world_map) + custom_nodes
    matched_current = next((node for node in full_map if str(node[0]).lower() in current.lower() or current.lower() in str(node[0]).lower()), None)
    current_node = matched_current or (full_map[0] if full_map else (current, 50, 50, "region", 1))
    quest_locations = {}
    for quest in state.get("quests", []):
        if not isinstance(quest, dict): continue
        for location in _list(quest.get("locations")):
            quest_locations.setdefault(str(location).lower(), []).append(quest.get("name", "Quest"))
    scale = progression_preset_for(world).get("travel_scale", 1.0)
    current_turn = int(state.get("turn", 0) or 0)
    nodes = []
    for name, x, y, kind, tier in full_map:
        distance = math.dist((float(current_node[1]), float(current_node[2])), (float(x), float(y)))
        travel_minutes = 0 if name == current_node[0] else max(30, int(round(distance * 38 * scale + max(0, int(tier or 1) - 1) * 12)))
        quests = []
        for loc, names in quest_locations.items():
            if loc in str(name).lower() or str(name).lower() in loc: quests.extend(names)
        detail = state.get("location_details", {}).get(name, {}) if isinstance(state.get("location_details", {}).get(name), dict) else {}
        changed_turn = detail.get("controller_changed_turn")
        # A window, not a one-shot flag, so the highlight survives across a
        # couple of turns of the player just not happening to open the map
        # the instant it changed — see update_continuity's territory diff.
        recently_changed = isinstance(changed_turn, (int, float)) and (current_turn - int(changed_turn)) <= 3
        if "controlling_faction" in detail:
            controller = detail.get("controlling_faction") or "Unclaimed"
        elif detail.get("faction"):
            controller = detail.get("faction")
        else:
            controller = territories.get(name, "Unknown")
        nodes.append({"name": name, "x": x, "y": y, "kind": kind, "tier": tier, "current": name == current_node[0],
                      "discovered": name in discovered or name == current_node[0], "travel_minutes": travel_minutes,
                      "controller": controller,
                      "quests": list(dict.fromkeys(quests)), "notes": detail.get("notes") or detail.get("description") or "No additional local notes recorded.",
                      "notable_individuals": _notable_individuals_for(state, name), "danger_level": str(detail.get("danger_level") or ""),
                      "recently_changed": recently_changed})
    result = {"nodes": nodes, "regions": political_regions_for_map(state, nodes), "meta": copy.deepcopy(WORLD_MAP_META.get(world, WORLD_MAP_META["Custom World"]))}
    if world == "Bleach":
        boards = []
        active_realm, fallback_anchor = _bleach_realm_and_anchor(current)
        current_name = str(current_node[0])
        for realm, placements in BLEACH_REALM_NODES.items():
            if matched_current and current_name in placements:
                active_realm = realm
            board_nodes = []
            for node in nodes:
                if node["name"] not in placements:
                    continue
                placed = copy.deepcopy(node)
                placed["x"], placed["y"] = placements[node["name"]]
                placed["current"] = (bool(matched_current) and node["name"] == current_name) or (not matched_current and realm == active_realm and node["name"] == fallback_anchor)
                board_nodes.append(placed)
            # Custom destinations require an explicit realm, so they cannot
            # accidentally appear on all five boards.
            for custom in state.get("custom_locations", []) or []:
                if isinstance(custom, dict) and (custom.get("realm") or custom.get("board")) == realm:
                    original = next((n for n in nodes if n["name"] == custom.get("name")), None)
                    if original and original["name"] not in placements: board_nodes.append(copy.deepcopy(original))
            atlas = political_atlas(state, board_nodes, world, realm)
            boards.append({"id": re.sub(r"[^a-z0-9]+", "-", realm.lower()).strip("-"), "name": realm,
                           "image": BLEACH_REALM_IMAGES[realm], "nodes": board_nodes,
                           "atlas": atlas,
                           "regions": political_regions_for_map(state, board_nodes)})
        active = next(board for board in boards if board["name"] == active_realm)
        result.update({"nodes": active["nodes"], "regions": active["regions"], "boards": boards, "active_board": active_realm, "atlas": active["atlas"]})
    elif world == "Solo Max-Level Newbie":
        floor = re.search(r"\bfloor\s*(\d+)\b", current, re.I)
        board = f"Floor {max(1, min(50, int(floor.group(1))))}" if floor else "Earth"
        floor_nodes = [copy.deepcopy(n) for n in nodes if n["name"] == board or (board == "Earth" and "Entrance" in n["name"])]
        for n in floor_nodes: n.update(x=50, y=50, current=True)
        for custom in state.get("custom_locations", []) or []:
            if isinstance(custom, dict) and (custom.get("board") or custom.get("realm")) == board:
                n = next((copy.deepcopy(n) for n in nodes if n["name"] == custom.get("name")), None)
                if n: floor_nodes.append(n)
        result.update(nodes=floor_nodes, regions=[], active_board=board, atlas=political_atlas(state, floor_nodes, world, board))
        result["meta"] = {"projection": f"Tower atlas · {board}", "accuracy_note": "Only the current floor is visible. This is a schematic territorial board; detailed floor terrain has not yet been authored."}
    else:
        result["atlas"] = political_atlas(state, nodes, world)
    return result
