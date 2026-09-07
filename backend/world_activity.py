"""Persistent, low-cost world-specific activity records.

The narrator authors unusual fiction through ``state_patch.special``.  This
module turns those facts plus the resolved action into stable, readable
records.  It deliberately avoids a second AI request.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re

from worlds import WORLD_DATA


NEN_PRINCIPLES = ("Ten", "Zetsu", "Ren", "Gyo", "En", "Shu", "Ko", "Ken", "Ryu", "Hatsu")
NARUTO_SPECIALTIES = (
    "Medical Ninjutsu", "Fuinjutsu", "Puppetry", "Summoning", "Sensory Ninjutsu",
    "Kenjutsu", "Poisons", "Barrier Ninjutsu", "Espionage",
)

HUNTER_WORK = {
    "Beast Hunter": ["Track a newly documented magical beast", "Protect a nesting ground without harming its ecosystem"],
    "Blacklist Hunter": ["Identify a wanted criminal through evidence", "Trade verified underworld intelligence"],
    "Ruins Hunter": ["Authenticate a recovered inscription", "Negotiate access to a protected ruin"],
    "Gourmet Hunter": ["Locate a rare ingredient through ecology", "Judge a dangerous culinary trial"],
}

BLEACH_DIVISION_CULTURE = {
    "1": "Command, law, coordination, and the burden of representing the Gotei 13",
    "2": "Stealth, pursuit, discipline, and covert operations",
    "3": "Duty under emotional pressure and precise field leadership",
    "4": "Healing, logistics, rescue, and keeping the Seireitei functioning",
    "5": "Balanced fieldcraft, Kidō literacy, and careful observation",
    "6": "Law, noble responsibility, and exacting martial standards",
    "7": "Loyalty, direct service, and protecting comrades openly",
    "8": "Flexible judgment, tactical creativity, and seeing beyond appearances",
    "9": "Security, publishing, ethics, and investigation",
    "10": "Reliable patrol work, rapid response, and practical command",
    "11": "Front-line combat, endurance, and strength proven in battle",
    "12": "Research, invention, containment, and dangerous experimentation",
    "13": "World of the Living duty, compassion, and balanced judgment",
}


WORLD_ACTIVITY_RULES = {
    "One Piece": """
ONE PIECE ACTIVITY RECORDS:
- A bounty change must update special['Bounty'] and special['Bounty Cause'] with the exact act, witnesses/source, strength demonstrated, public notoriety created, World Government threat created, and whether the number reflects combat power, political danger, reputation, or several of those. Bounty is not a power level.
- For every campaign-original island, keep special['Island Arc'] with name, ruler_or_faction, central_problem, local_culture, secret, and at least three genuinely different conclusions. Conclusions are possibilities, never forced objectives.
- Haki mastery only changes through a concrete breakthrough caused by danger, sharpened perception, conviction, or focused training. Add the evidence and trigger to that Haki branch; never award anonymous Haki points from unrelated stat growth.
- A major victory must create a proportional world response through newspapers, port rumors, Marine or Government orders, rival attention, and territory changes where applicable. Information travels through believable witnesses and channels.
""",
    "Hunter x Hunter": """
HUNTER X HUNTER ACTIVITY RECORDS:
- Keep special['Nen Intelligence'] per named opponent: confirmed facts, suspected rules, false beliefs, unknowns, evidence, and what that opponent has witnessed or learned about the player's Hatsu. Narrator knowledge is never character knowledge.
- New Hatsu applications must preserve the saved governing effect and category logic. Add applications to the existing Hatsu profile instead of inventing a replacement ability.
- A natural-language Nen vow must record promise/restriction, benefit, breach trigger, breach consequence, status and evidence. Its benefit applies only while its real restriction is enforceable.
- Keep special['Hunter Career'] specialties, completed work, contacts and access current. Specialty-appropriate auctions, investigations, tracking, examinations, negotiations, games and information work deserve full story beats and progression, not automatic combat.
- Track Ten, Zetsu, Ren, Gyo, En, Shu, Ko, Ken, Ryu and Hatsu separately. Training names the principle improved and gives concrete feedback.
""",
    "Naruto": """
NARUTO ACTIVITY RECORDS:
- Keep special['Village Intelligence'] with clearance, classified files, bingo-book entries, mission reports and rumors. Every entry records source, confidence and who is allowed to know it; rank and access matter.
- Keep special['Shinobi Career'] separate from combat power: rank, leadership evidence, mission history, recommendations, political support/opposition and next review. Promotion weighs all of them.
- Keep special['Shinobi Specialties'] for medical ninjutsu, fuinjutsu, puppetry, summoning, sensory ninjutsu, kenjutsu, poisons, barriers and espionage. Named techniques remain skills; broad competence remains a specialty/stat record.
- A tailed beast remembers respect, coercion, promises, protection, deception and shared danger. It may initiate contact or refuse exploitation. Its relationship, trust, resentment and transformation cooperation change through play, not passive stat growth.
""",
    "Reincarnated as a Slime": """
SLIME ACTIVITY RECORDS:
- Keep special['Synthesis Analysis'] with inputs, compatible concepts, surviving concept, possible result, losses/risks, confidence and status. Analysis never silently consumes skills; synthesis happens only when confirmed in the story.
- Naming records magicule cost, recipient, species/stat effect, relationship effect, political attention and any evolution caused.
- Keep special['Nation Record'] settlements, specialists, infrastructure, defense, culture, trade, internal pressures, alliances and legitimacy current. Strong characters face governance and diplomacy rather than scaled random enemies.
- Named subordinates are autonomous: track role, current project, training, evolution, relationships, concerns and independent decisions.
- Unknown beings and abilities use progressive analysis: Unknown -> Partial -> Confirmed, with evidence and uncertainty plainly shown.
""",
    "Bleach": """
BLEACH ACTIVITY RECORDS:
- Academy graduates awaiting placement receive evaluations, division interviews/offers and political pressure. Placement is a narrative choice; do not assign a squad without resolving that choice.
- Keep one living Zanpakuto identity synchronized across equipment and releases. Its spirit has temperament, values, memories, approval, disagreements, initiated contact and a changing inner world.
- Keep special['Kido Reference'] Hadō and Bakudō entries with number, name, incantation knowledge, mastery, modifications, evidence and source. A campaign-original missing number becomes permanent once authored.
- Keep special['Soul Reaper Duty'] patrols, konso, Hollow investigations, Gigai use, reports and balance-of-souls consequences. Division culture changes missions, mentors, training, expectations and promotion.
- Reiatsu affects detection, concealment, intimidation, movement and weaker spiritual beings. Record witnessed interactions instead of treating Reiatsu only as a combat number.
""",
    "Solo Max-Level Newbie": """
SOLO MAX-LEVEL NEWBIE ACTIVITY RECORDS:
- A floor scene respects floor_state: canon_status, scenario, factions, ecosystem, administrator personality, hidden/alternate clears, boss mechanics and rewards. Contextual reconstructions are allowed where canon is unrevealed, but never presented as published canon fact.
- Foreknowledge has three states: remembered from the game, confirmed in the changed reality, or now unreliable. An exploit is not guaranteed until tested here.
- Ability-copy attempts state the observed ability, missing copy conditions, capacity cost and target awareness. XP, levels, titles, achievements, penalties and rewards appear as canonical System notices.
- Explain meaningful build synergy among titles, artifacts, stats and copied abilities. Administrators remember loopholes and react according to their preferences and rivalries.
""",
    "Overgeared": """
OVERGEARED ACTIVITY RECORDS:
- Class growth follows repeated behavior and accomplishments, not a predetermined crafting tree. Combat, magic, religion, command, politics, exploration, social, merchant, production and monster-taming routes are equally valid in Satisfy.
- NPC affinity changes preserve the reason: promises, gifts, disrespect, protection, shared experiences and treatment of other NPCs. Important equipment accumulates history, disputes, upgrades and class synergy.
- Track only important economic effects: significant items, guild resources, contracts and major production influence reputation or politics; trivial ingredients remain narrative. Other players and guilds move in the rankings without waiting for the player.
- Rare classes create personal milestones, rivals, responsibilities and consequences proportional to their rarity.
""",
    "Jujutsu Kaisen": """
JUJUTSU KAISEN ACTIVITY RECORDS:
- Technique applications, Maximum Techniques and Domains remain extensions of the saved innate governing principle. Track what each opponent witnessed versus correctly understood. If the opponent knows the governing rule, apply the saved revealing-one's-hand bonus.
- Binding vows record and enforce their benefit, restriction, breach condition and consequence. Actual strength, official grade, mission reliability, political support and headquarters recognition remain separate.
- Jujutsu missions include a human cause, escalating manifestations, incomplete information, civilians and consequences beyond exorcism. Sentient curses grow through originating fear, deaths, consumed energy, infamy and self-understanding; clans create obligations and rivals.
- Domain clashes compare refinement, barrier conditions, range, output and compatibility. Never decide them from one generic power label.
""",
}


_ACTIVITY_RULE_SECTIONS = {
    "One Piece": (
        (r"\bbount|marine|government|notor|newspaper|rumor|victor|defeat|overthrow|liberat", "bounty world-response"),
        (r"\bisland|ruler|kingdom|territor|local|village|port", "island"),
        (r"\bhaki|observation|armament|conqueror|conviction|perception", "haki"),
    ),
    "Hunter x Hunter": (
        (r"\bnen|hatsu|ten|zetsu|ren|gyo|en|shu|ko|ken|ryu|aura", "nen"),
        (r"\bvow|restriction|promise|condition|breach", "vow"),
        (r"\bhunter|auction|investigat|track|exam|negotiat|game|information", "career"),
    ),
    "Naruto": (
        (r"\bclassified|intelligence|bingo|mission report|rumor|clearance", "intelligence"),
        (r"\bpromot|rank|career|leadership|recommend|mission history", "career"),
        (r"\bmedical|heal|seal|fuinjutsu|puppet|summon|sensor|sword|kenjutsu|poison|barrier|spy|espionage", "specialty"),
        (r"\bjinch|tailed beast|kurama|shukaku|inner world|cloak|transform", "jinchuriki"),
    ),
    "Reincarnated as a Slime": (
        (r"\bsynth|combine|merge|skill|analy[sz]|great sage|raphael|appraise", "analysis"),
        (r"\bname|evol|species|magicule", "naming"),
        (r"\bnation|settlement|city|infrastructure|trade|defen|alliance|diplom|govern|subordinate", "nation"),
    ),
    "Bleach": (
        (r"\bacadem|division|squad|placement|interview|offer|captain", "placement"),
        (r"\bzanpak|shikai|bankai|jinzen|inner world|sword spirit", "zanpakuto"),
        (r"\bkido|had[oō]|bakud[oō]|incantation", "kido"),
        (r"\bkonso|patrol|hollow|gigai|report|soul balance|duty", "duty"),
        (r"\breiatsu|spiritual pressure|detect|conceal|intimid", "reiatsu"),
    ),
    "Solo Max-Level Newbie": (
        (r"\bfloor|tower|clear|boss|administrator", "solo_floor"),
        (r"\bforeknowledge|remember|game knowledge|exploit", "solo_foreknowledge"),
        (r"\bcopy|ability", "solo_copy"),
        (r"\bsystem|xp|level|title|artifact|synergy|build", "solo_system"),
    ),
    "Overgeared": (
        (r"\bclass|satisfy|skill|command|explor|tame|magic|relig", "overgeared_class"),
        (r"\baffinity|npc|promise|gift|equipment|item|weapon|armor", "overgeared_identity"),
        (r"\bguild|rank|econom|contract|market|merchant|politic|craft", "overgeared_world"),
    ),
    "Jujutsu Kaisen": (
        (r"\btechnique|application|maximum|reveal|opponent", "jjk_technique"),
        (r"\bvow|grade|promotion|headquarters", "jjk_vow_grade"),
        (r"\bmission|curse|clan|exorcis|sorcerer", "jjk_world"),
        (r"\bdomain|barrier|sure.hit", "jjk_domain"),
    ),
}

_ACTIVITY_COMPACT = {
    "One Piece": "Keep bounty causes, original-island conflicts, Haki breakthroughs, and world responses causally consistent when relevant.",
    "Hunter x Hunter": "Keep Nen rules, vows, information boundaries, and Hunter work causally consistent when relevant.",
    "Naruto": "Keep shinobi intelligence, careers, specialties, and tailed-beast relationships causally consistent when relevant.",
    "Reincarnated as a Slime": "Keep synthesis, naming, evolution, subordinate, nation, and analysis records causally consistent when relevant.",
    "Bleach": "Keep squad placement, Zanpakutō identity, Kidō, Soul Reaper duty, and Reiatsu effects causally consistent when relevant.",
    "Solo Max-Level Newbie": "Keep floor rules, foreknowledge, copy conditions, System notices, synergies, and administrators consistent when relevant.",
    "Overgeared": "Keep behavior-based classes, remembered affinity, important economy/equipment, and the living ranking ecosystem consistent when relevant.",
    "Jujutsu Kaisen": "Keep technique knowledge, vows, grades, missions, curse/clan pressure, and multi-factor domain clashes consistent when relevant.",
}


def activity_rules_for(world, purpose="moment", action_hint="", detailed=False):
    """Return only the world-activity instructions that can affect this job.

    The complete contract remains available for openings and explicit audits,
    while frequent side calls pay only for a stable one-line reminder.  Turn
    calls receive the matching bullet(s), selected locally without another AI
    request.
    """
    world = str(world or "")
    full = WORLD_ACTIVITY_RULES.get(world, "").strip()
    if not full:
        return ""
    compact = _ACTIVITY_COMPACT.get(world, "")
    purpose = str(purpose or "moment").lower()
    if purpose in {"opening", "audit"} or detailed:
        return "\n" + full + "\n"
    if purpose in {"core", "message", "advisor", "combat_summary"}:
        return f"\nWORLD ACTIVITY: {compact}\n"
    text = str(action_hint or "")
    labels = {label for pattern, label in _ACTIVITY_RULE_SECTIONS.get(world, ()) if re.search(pattern, text, re.I)}
    if not labels:
        return f"\nWORLD ACTIVITY: {compact}\n"
    bullets = []
    for line in full.splitlines():
        clean = line.strip()
        if not clean.startswith("-"):
            continue
        lower = clean.casefold()
        if any(
            (label == "bounty world-response" and any(k in lower for k in ("bounty", "victory", "response"))) or
            (label == "island" and "island" in lower) or
            (label == "haki" and "haki" in lower) or
            (label == "nen" and any(k in lower for k in ("hatsu", "track ten", "nen intelligence"))) or
            (label == "vow" and "vow" in lower) or
            (label == "career" and any(k in lower for k in ("career", "specialt", "noncombat", "auction"))) or
            (label == "intelligence" and "village intelligence" in lower) or
            (label == "specialty" and "shinobi specialties" in lower) or
            (label == "jinchuriki" and "tailed beast" in lower) or
            (label == "analysis" and any(k in lower for k in ("synthesis", "analysis"))) or
            (label == "naming" and "naming" in lower) or
            (label == "nation" and any(k in lower for k in ("nation", "subordinate"))) or
            (label == "placement" and "placement" in lower) or
            (label == "zanpakuto" and "zanpakuto" in lower) or
            (label == "kido" and "kido" in lower) or
            (label == "duty" and "duty" in lower) or
            (label == "reiatsu" and "reiatsu" in lower)
            or (label == "solo_floor" and "floor scene" in lower)
            or (label == "solo_foreknowledge" and "foreknowledge" in lower)
            or (label == "solo_copy" and "ability-copy" in lower)
            or (label == "solo_system" and ("build synergy" in lower or "system notices" in lower))
            or (label == "overgeared_class" and "class growth" in lower)
            or (label == "overgeared_identity" and ("npc affinity" in lower or "important equipment" in lower))
            or (label == "overgeared_world" and ("economic" in lower or "rankings" in lower or "rare classes" in lower))
            or (label == "jjk_technique" and "technique applications" in lower)
            or (label == "jjk_vow_grade" and "binding vows" in lower)
            or (label == "jjk_world" and "jujutsu missions" in lower)
            or (label == "jjk_domain" and "domain clashes" in lower)
            for label in labels
        ):
            bullets.append(clean)
    return "\nWORLD ACTIVITY (RELEVANT THIS JOB):\n" + "\n".join(bullets or [f"- {compact}"]) + "\n"


def _num(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _list(value):
    if isinstance(value, list):
        return value
    return [] if value in (None, "") else [value]


def _dedupe(rows, limit=100):
    result, seen = [], set()
    for row in rows:
        key = str(row).strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key); result.append(copy.deepcopy(row))
    return result[-limit:]


def _rng(*parts):
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _original_location(state):
    location = str(state.get("location") or "Unknown Island").strip()
    known = {str(row[0]).casefold() for row in WORLD_DATA.get("One Piece", {}).get("map", []) if isinstance(row, (list, tuple)) and row}
    custom = state.get("custom_locations") if isinstance(state.get("custom_locations"), list) else []
    return location, location.casefold() not in known or any(str(x.get("name", "")).casefold() == location.casefold() for x in custom if isinstance(x, dict))


def _island_seed(state):
    name, original = _original_location(state)
    if not original:
        return {}
    rng = _rng(state.get("campaign_id"), name, "island-arc")
    rulers = ("a hereditary harbor council", "a merchant league", "a pirate protectorate", "a naval governor", "a shrine confederation", "an elected dock assembly")
    problems = ("a succession dispute is splitting the ports", "a vanished current is strangling trade", "a protected secret is drawing outside hunters", "rival protectors are collecting tribute", "a seasonal disaster exposes an old injustice")
    cultures = ("night markets, communal ship repair, and sung navigation records", "masked festivals and ancestor-kept weather lore", "competitive boat races and oath-bound hospitality", "cliff villages joined by rope lifts and messenger gulls", "floating farms and strict guest-right customs")
    secrets = ("the island is built over a dormant ancient mechanism", "the official founding story conceals an abandoned people", "the ruler's legitimacy depends on a forged treaty", "a forbidden route opens only during the island's worst weather", "the local resource is produced by a living creature the elite have imprisoned")
    return {
        "name": name, "original": True, "ruler_or_faction": rng.choice(rulers),
        "central_problem": rng.choice(problems), "local_culture": rng.choice(cultures),
        "secret": rng.choice(secrets), "secret_status": "Hidden",
        "conclusions": [
            "Reform the existing authority while preserving local continuity",
            "Back a rival or popular movement and accept the resulting political struggle",
            "Expose the secret and let island factions negotiate a new settlement",
        ],
        "status": "Emerging", "player_involvement": "Uncommitted",
    }


def normalize_world_activity(state, before=None):
    if not isinstance(state, dict):
        return []
    world = state.get("world")
    special = state.setdefault("special", {})
    root = state.setdefault("world_activity", {})
    if not isinstance(root, dict) or root.get("world") != world:
        root = state["world_activity"] = {"world": world, "version": 1}
    notes = []

    if world == "One Piece":
        op = root.setdefault("one_piece", {})
        reputation = special.get("Public Reputation") if isinstance(special.get("Public Reputation"), dict) else {}
        op.setdefault("bounty", {"current": _num(special.get("Bounty", reputation.get("bounty", 0))), "history": []})
        op["bounty"]["current"] = _num(special.get("Bounty", reputation.get("bounty", op["bounty"].get("current", 0))))
        authored_arc = special.get("Island Arc") if isinstance(special.get("Island Arc"), dict) else {}
        seeded = _island_seed(state)
        if authored_arc or seeded:
            arc = op.setdefault("island_arc", {})
            for key, value in {**seeded, **authored_arc}.items():
                if value not in (None, "", [], {}): arc[key] = copy.deepcopy(value)
            if arc:
                arc["conclusions"] = _dedupe(_list(arc.get("conclusions")), 8)
                while len(arc["conclusions"]) < 3:
                    arc["conclusions"].append(("Leave the island's conflict unresolved and accept how it develops without the player") if len(arc["conclusions"]) == 2 else "Negotiate a temporary settlement between the active factions")
                special["Island Arc"] = copy.deepcopy(arc)
        op.setdefault("haki_breakthroughs", [])
        op.setdefault("world_response", {"newspapers": [], "rumors": [], "marine_orders": [], "rival_attention": [], "territory_changes": []})
        notes.append("Synchronized One Piece activity records")

    elif world == "Hunter x Hunter":
        hx = root.setdefault("hunter_x_hunter", {})
        nen = special.setdefault("Nen Profile", {})
        principles = hx.setdefault("nen_principles", {})
        for name in NEN_PRINCIPLES:
            legacy = nen.get(name.lower(), special.get(name, 0))
            row = principles.setdefault(name, {"mastery": _num(legacy), "training_evidence": [], "last_feedback": "No recent focused training"})
            row["mastery"] = max(row.get("mastery", 0), _num(legacy))
        hx.setdefault("technique_intel", {})
        authored_intel = special.get("Nen Intelligence", {}) if isinstance(special.get("Nen Intelligence"), dict) else {}
        for person, row in authored_intel.items():
            if not isinstance(row, dict): row = {"confirmed":[str(row)]}
            target = hx["technique_intel"].setdefault(str(person), {"confirmed":[], "suspected":[], "false_beliefs":[], "unknowns":[], "evidence":[], "they_know":[]})
            for key in ("confirmed", "suspected", "false_beliefs", "unknowns", "evidence", "they_know"):
                target[key] = _dedupe([*target.get(key, []), *_list(row.get(key))], 30)
        hx.setdefault("vows", copy.deepcopy(nen.get("vow_registry", [])))
        hatsu = nen.get("hatsu_profile") if isinstance(nen.get("hatsu_profile"), dict) else {}
        if hatsu:
            hatsu.setdefault("governing_rule", hatsu.get("effect", "The original Hatsu rule established at awakening"))
            hatsu.setdefault("applications", [])
            hx["hatsu_development"] = {"name":hatsu.get("name", special.get("Hatsu", "Developing Hatsu")), "governing_rule":hatsu["governing_rule"], "applications":copy.deepcopy(hatsu["applications"])}
        career = special.get("Hunter Career") if isinstance(special.get("Hunter Career"), dict) else {}
        career.setdefault("license", special.get("Hunter License", "Unlicensed")); career.setdefault("specialties", [])
        career.setdefault("completed_work", []); career.setdefault("professional_access", []); career.setdefault("contacts", [])
        available = []
        for specialty in _list(career.get("specialties")):
            available.extend(HUNTER_WORK.get(str(specialty), [f"Pursue a {specialty} lead through contacts, research, or field work"]))
        career["available_work"] = _dedupe([*career.get("available_work", []), *available], 20)
        special["Hunter Career"] = career
        hx["career"] = copy.deepcopy(career)
        notes.append("Synchronized Hunter activity records")

    elif world == "Naruto":
        nr = root.setdefault("naruto", {})
        intel = special.get("Village Intelligence") if isinstance(special.get("Village Intelligence"), dict) else {}
        intel.setdefault("clearance", special.get("Shinobi Rank", "Civilian")); intel.setdefault("classified_files", [])
        intel.setdefault("bingo_book", []); intel.setdefault("mission_reports", []); intel.setdefault("rumors", [])
        special["Village Intelligence"] = intel; nr["intelligence"] = copy.deepcopy(intel)
        career = special.get("Shinobi Career") if isinstance(special.get("Shinobi Career"), dict) else {}
        career.setdefault("rank", special.get("Shinobi Rank", "Civilian")); career.setdefault("leadership_evidence", [])
        career.setdefault("mission_history", []); career.setdefault("recommendations", []); career.setdefault("political_support", [])
        career.setdefault("political_opposition", []); career.setdefault("next_review", "No promotion review scheduled")
        missions = len(career.get("mission_history", [])); leadership = len(career.get("leadership_evidence", [])); recommendations = len(career.get("recommendations", []))
        opposition = len(career.get("political_opposition", [])); support = len(career.get("political_support", []))
        career["promotion_readiness"] = max(0, missions * 4 + leadership * 8 + recommendations * 10 + support * 5 - opposition * 6)
        career["promotion_factors"] = {"missions":missions, "leadership":leadership, "recommendations":recommendations, "political_support":support, "political_opposition":opposition, "combat_power_is_not_rank":True}
        special["Shinobi Career"] = career; nr["career"] = copy.deepcopy(career)
        tracks = special.get("Shinobi Specialties") if isinstance(special.get("Shinobi Specialties"), dict) else {}
        for name in NARUTO_SPECIALTIES:
            tracks.setdefault(name, {"mastery": 0, "evidence": [], "known_techniques": []})
        special["Shinobi Specialties"] = tracks; nr["specialties"] = copy.deepcopy(tracks)
        host = special.get("Jinchūriki Profile") if isinstance(special.get("Jinchūriki Profile"), dict) else {}
        if host:
            bond = nr.setdefault("tailed_beast_relationship", {"beast": host.get("beast", "Tailed Beast"), "trust": _num(host.get("bond_progress", 0)), "resentment": 0, "memories": [], "promises": [], "initiated_contact": [], "cooperation": host.get("relationship", "Undeveloped")})
            bond["beast"] = host.get("beast", bond["beast"])
        notes.append("Synchronized Naruto activity records")

    elif world == "Reincarnated as a Slime":
        sl = root.setdefault("slime", {})
        sl.setdefault("synthesis", copy.deepcopy(special.get("Synthesis Analysis", [])) if isinstance(special.get("Synthesis Analysis"), list) else [])
        sl.setdefault("naming_history", [])
        nation = special.get("Nation Record") if isinstance(special.get("Nation Record"), dict) else {}
        for key in ("settlements", "specialists", "infrastructure", "defense", "culture", "trade", "internal_pressures", "alliances"):
            nation.setdefault(key, [])
        nation.setdefault("legitimacy", "Unrecognized")
        special["Nation Record"] = nation; sl["nation"] = copy.deepcopy(nation)
        sl.setdefault("subordinates", {}); sl.setdefault("analysis_records", {})
        evolution = special.get("Evolution Profile") if isinstance(special.get("Evolution Profile"), dict) else {}
        sl["evolution"] = {"species":evolution.get("species", special.get("Species", state.get("race", "Unknown"))), "stage":evolution.get("stage", "Current form"), "routes":copy.deepcopy(evolution.get("routes", [])), "requirements":copy.deepcopy(evolution.get("evolution_requirements", [])), "resistances":copy.deepcopy(evolution.get("resistances", [])), "consequences":copy.deepcopy(evolution.get("transformation_consequences", []))}
        authored_subordinates = special.get("Named Subordinates") if isinstance(special.get("Named Subordinates"), dict) else {}
        for name, row in authored_subordinates.items():
            if not isinstance(row, dict): row = {"role":str(row)}
            target = sl["subordinates"].setdefault(str(name), {})
            for key, value in row.items():
                if value not in (None, "", [], {}): target[key] = copy.deepcopy(value)
            for key, default in (("role","Follower"),("current_project","No assigned project"),("training","Self-directed"),("evolution","Current species"),("relationships",[]),("concerns",[]),("independent_decisions",[])):
                target.setdefault(key, copy.deepcopy(default))
        notes.append("Synchronized Slime activity records")

    elif world == "Bleach":
        bl = root.setdefault("bleach", {})
        soul = special.get("Soul Reaper Record") if isinstance(special.get("Soul Reaper Record"), dict) else {}
        placement = bl.setdefault("squad_placement", {"status": "Placed" if str(soul.get("division", "")).lower() not in {"", "awaiting placement", "none"} else "Awaiting placement", "evaluations": [], "interviews": [], "offers": [], "pressures": [], "player_preferences": []})
        if special.get("Squad") and str(special.get("Squad")).lower() not in {"awaiting placement", "none"}:
            placement["status"] = f"Assigned to {special.get('Squad')}"
        blade = special.get("Zanpakuto Profile") if isinstance(special.get("Zanpakuto Profile"), dict) else {}
        relation = bl.setdefault("zanpakuto_relationship", {"name": blade.get("name", "Unnamed Asauchi"), "spirit": blade.get("spirit", "Not yet understood"), "temperament": "Unknown", "values": [], "approval": 0, "memories": [], "disagreements": [], "initiated_contact": [], "inner_world_changes": []})
        relation.update({"name": blade.get("name", relation["name"]), "spirit": blade.get("spirit", relation["spirit"])})
        kido = special.get("Kido Reference") if isinstance(special.get("Kido Reference"), dict) else {"Hado": {}, "Bakudo": {}}
        kido.setdefault("Hado", {}); kido.setdefault("Bakudo", {})
        for skill_name, detail in (state.get("skills") or {}).items():
            if not isinstance(detail, dict): continue
            match = re.search(r"\b(Had[oō]|Bakud[oō])\s*#?\s*(\d{1,2})\b", str(skill_name), re.I)
            if not match: continue
            branch = "Hado" if match.group(1).casefold().startswith("hado") or match.group(1).casefold().startswith("hadō") else "Bakudo"
            number = str(int(match.group(2)))
            row = kido[branch].setdefault(number, {})
            row.update({"number":int(number), "name":skill_name, "incantation_knowledge":detail.get("incantation_knowledge", "Unknown"), "mastery":detail.get("mastery", detail.get("bonus", 0)), "modified_casting":detail.get("modified_casting", []), "evidence":detail.get("evidence", []), "source":detail.get("source", "Learned in this campaign")})
        special["Kido Reference"] = kido; bl["kido_reference"] = copy.deepcopy(kido)
        duty = special.get("Soul Reaper Duty") if isinstance(special.get("Soul Reaper Duty"), dict) else {}
        for key in ("patrols", "konso", "hollow_investigations", "gigai_use", "division_reports", "soul_balance_consequences"):
            duty.setdefault(key, [])
        squad_text = str(special.get("Squad") or soul.get("division") or "")
        division_match = re.search(r"(\d{1,2})", squad_text)
        culture = BLEACH_DIVISION_CULTURE.get(division_match.group(1), "Placement will determine missions, mentors, training, expectations, and advancement") if division_match else "Placement will determine missions, mentors, training, expectations, and advancement"
        duty.setdefault("division_culture", {"division":squad_text or "Awaiting placement", "identity":culture})
        duty.setdefault("current_assignment", soul.get("duty", "Awaiting assignment"))
        special["Soul Reaper Duty"] = duty; bl["duty"] = copy.deepcopy(duty)
        bl.setdefault("reiatsu_interactions", [])
        notes.append("Synchronized Bleach activity records")
    return notes


def _event_text(events):
    chunks = []
    for event in events or []:
        if isinstance(event, dict): chunks.extend(str(event.get(k) or "") for k in ("type", "title", "message", "narrative"))
        else: chunks.append(str(event))
    return " ".join(chunks)


def advance_world_activity(state, before, actions=None, narrative="", events=None, elapsed_minutes=5):
    """Advance inexpensive world records after a resolved action/time skip."""
    normalize_world_activity(state, before)
    world = state.get("world"); root = state.get("world_activity", {})
    action_items = [str(x) for x in actions or []]
    action_text = " ".join(action_items)
    result_text = " ".join((action_text, str(narrative or ""), _event_text(events)))
    turn = _num(state.get("turn"), _num((before or {}).get("turn"), 0) + 1)
    notes = []

    if world == "One Piece":
        op = root["one_piece"]; old_bounty = _num((before or {}).get("special", {}).get("Bounty", 0)); new_bounty = _num(state.get("special", {}).get("Bounty", old_bounty))
        if new_bounty != old_bounty:
            authored = state["special"].get("Bounty Cause") if isinstance(state["special"].get("Bounty Cause"), dict) else {}
            cause = {"turn": turn, "before": old_bounty, "after": new_bounty, "change": new_bounty-old_bounty,
                     "act": authored.get("act") or action_text[:240] or "Consequences established in the Chronicle",
                     "strength_demonstrated": authored.get("strength_demonstrated") or "Not independently measured by the bounty",
                     "notoriety": authored.get("notoriety") or "Public attention increased",
                     "government_threat": authored.get("government_threat") or "Government assessment changed",
                     "source": authored.get("source") or "Witness reports and official review"}
            op["bounty"]["history"].append(cause); op["bounty"]["history"] = op["bounty"]["history"][-50:]
            notes.append(f"BOUNTY {old_bounty:,} → {new_bounty:,} — {cause['act']}")
        old_haki = (before or {}).get("special", {}).get("Haki Profile", {})
        new_haki = state["special"].get("Haki Profile", {})
        trigger = "Focused training" if re.search(r"\btrain|practice|meditat", action_text, re.I) else "Danger" if re.search(r"\bfight|battle|surviv|near death|protect", result_text, re.I) else "Perception" if re.search(r"\bperceiv|sense|anticipat|intent", result_text, re.I) else "Conviction" if re.search(r"\bresolve|conviction|refus|willpower|stand", result_text, re.I) else "Established breakthrough"
        for branch in ("Observation", "Armament", "Conqueror"):
            old = _num((old_haki.get(branch) or {}).get("mastery", 0)); new = _num((new_haki.get(branch) or {}).get("mastery", old))
            if new > old:
                row = {"turn": turn, "branch": branch, "before": old, "after": new, "trigger": trigger, "evidence": str(narrative or action_text)[:280]}
                op["haki_breakthroughs"].append(row); notes.append(f"{branch} Haki {old}→{new} — {trigger}")
        major = re.search(r"\b(?:major victory|defeated|overthrew|liberated|captured|destroyed).{0,80}\b(?:captain|warlord|admiral|government|marine|kingdom|fleet|island|stronghold)\b", result_text, re.I)
        if major:
            response = op["world_response"]; headline = f"Reports spread after {action_text[:120] or 'the latest victory'}"
            response["newspapers"] = _dedupe([*response["newspapers"], {"turn": turn, "headline": headline}], 40)
            response["rumors"] = _dedupe([*response["rumors"], {"turn": turn, "message": "Ports debate what the victory means and who may act next."}], 40)
            response["marine_orders"] = _dedupe([*response["marine_orders"], {"turn": turn, "order": "Reassess the responsible party and gather verified intelligence."}], 30)
            response["rival_attention"] = _dedupe([*response["rival_attention"], {"turn": turn, "reaction": "Relevant rivals reconsider the player as a factor."}], 30)
            notes.append("WORLD RESPONSE — newspapers, rumors, Marine review, and rival attention were generated")

    elif world == "Hunter x Hunter":
        hx = root["hunter_x_hunter"]
        days = max(1/288, _num(elapsed_minutes, 5) / 1440)
        for name in NEN_PRINCIPLES:
            focus_action = next((item for item in action_items
                                 if re.search(rf"\b{re.escape(name)}\b", item, re.I)
                                 and (re.search(r"\b(?:train|practice|learn|refine|master|study|exercise|maintain)\b", item, re.I)
                                      or (re.search(r"\buse\b", item, re.I)
                                          and not re.search(r"\b(?:vow|restriction|swear|promise|only while|only if|in exchange for)\b", item, re.I)))), "")
            if focus_action:
                row = hx["nen_principles"][name]; old = _num(row.get("mastery")); gain = max(1, min(12, round(days * 2 + 1)))
                row["mastery"] = old + gain; row["last_feedback"] = f"{name} improved through {round(days, 2)} day(s) of focused use"
                row["training_evidence"] = _dedupe([*row.get("training_evidence", []), {"turn": turn, "action": focus_action[:220], "gain": gain}], 30)
                state["special"].setdefault("Nen Profile", {})[name.lower()] = row["mastery"]
                notes.append(f"{name} {old}→{row['mastery']} — {row['last_feedback']}")
        if re.search(r"\b(?:vow|restriction|I swear|I promise|only if|in exchange for)\b", action_text, re.I):
            vow = {"name": f"Vow recorded on turn {turn}", "promise": action_text[:260], "benefit": "Proportional Nen increase where the stated condition applies", "breach_trigger": "The user knowingly violates the stated promise", "breach_consequence": "The granted benefit ends and the established Nen penalty applies", "status": "Active", "evidence": str(narrative)[:220]}
            hx["vows"] = _dedupe([*hx.get("vows", []), vow], 30); state["special"].setdefault("Nen Profile", {})["vow_registry"] = copy.deepcopy(hx["vows"])
            notes.append("NEN VOW — promise, benefit, breach trigger, and consequence recorded")
        hatsu = state["special"].setdefault("Nen Profile", {}).get("hatsu_profile", {})
        if isinstance(hatsu, dict) and re.search(r"\b(?:develop|invent|refine|new application|apply)\b", action_text, re.I) and re.search(r"\b(?:hatsu|nen|ability|technique)\b", result_text, re.I):
            hx["hatsu_development"] = {"name":hatsu.get("name", "Developing Hatsu"), "governing_rule":hatsu.get("governing_rule", hatsu.get("effect", "Original governing rule")), "applications":copy.deepcopy(hatsu.get("applications", []))}
            notes.append(f"HATSU DEVELOPMENT — new use remains governed by {hx['hatsu_development']['governing_rule']}")
        if re.search(r"\b(?:auction|investigat|track|exam|negotiat|game|information trad|research|authenticate)\b", action_text, re.I):
            career = hx["career"]
            entry = {"turn":turn, "work":action_text[:220], "result":str(narrative)[:220]}
            career["completed_work"] = _dedupe([*career.get("completed_work", []), entry], 50)
            notes.append("HUNTER CAREER — noncombat work added to the professional record")
            state["special"]["Hunter Career"] = copy.deepcopy(career)
        state["special"]["Nen Intelligence"] = copy.deepcopy(hx.get("technique_intel", {}))

    elif world == "Naruto":
        nr = root["naruto"]; tracks = state["special"]["Shinobi Specialties"]
        aliases = {"Medical Ninjutsu":"medical|heal", "Fuinjutsu":"fuinjutsu|seal", "Puppetry":"puppet", "Summoning":"summon|contract", "Sensory Ninjutsu":"sensor|sense chakra", "Kenjutsu":"sword|kenjutsu", "Poisons":"poison|toxin", "Barrier Ninjutsu":"barrier|kekkai", "Espionage":"spy|espionage|infiltrat|disguise"}
        days = max(1/288, _num(elapsed_minutes, 5)/1440)
        for name, pattern in aliases.items():
            if re.search(pattern, action_text, re.I) and re.search(r"\btrain|practice|study|learn|research|use|perform|create\b", action_text, re.I):
                row = tracks[name]; old = _num(row.get("mastery")); gain = max(1, min(15, round(days*2+1))); row["mastery"] = old+gain
                row["evidence"] = _dedupe([*row.get("evidence", []), {"turn":turn,"action":action_text[:220],"gain":gain}],30); notes.append(f"{name} {old}→{row['mastery']}")
        host = state["special"].get("Jinchūriki Profile", {}); bond = nr.get("tailed_beast_relationship")
        if host and bond:
            respectful = re.search(r"\b(?:listen|ask|thank|respect|protect|befriend|cooperate|keep my promise|speak with)\b.{0,80}\b(?:beast|kurama|shukaku|jinch|inner world|seal)\b", result_text, re.I)
            coercive = re.search(r"\b(?:force|control|suppress|exploit|take.*chakra|command)\b.{0,80}\b(?:beast|kurama|shukaku|jinch|inner world|seal)\b", result_text, re.I)
            if respectful or coercive:
                delta = 3 if respectful else -4; bond["trust"] = max(0,min(100,_num(bond.get("trust"))+delta)); bond["resentment"] = max(0,min(100,_num(bond.get("resentment")) + (-2 if respectful else 5)))
                bond["memories"] = _dedupe([*bond.get("memories", []), {"turn":turn,"event":str(narrative or action_text)[:260],"effect":"respect" if respectful else "coercion"}],60)
                host["bond_progress"] = bond["trust"]; host["relationship"] = "Cooperative" if bond["trust"]>=70 else "Developing" if bond["trust"]>=35 else "Hostile or distant" if bond["resentment"]>=35 else host.get("relationship","Undeveloped")
                notes.append(f"{bond['beast']} relationship — trust {bond['trust']}%, resentment {bond['resentment']}%")
            if elapsed_minutes >= 10080 and turn % 4 == 0:
                mood = "offers a guarded observation" if bond.get("trust", 0) >= 35 else "voices resentment from behind the seal"
                contact = {"turn":turn, "event":f"{bond['beast']} {mood}; it remembers how the host has treated it."}
                bond["initiated_contact"] = _dedupe([*bond.get("initiated_contact", []), contact], 30)
                notes.append(f"TAILED-BEAST CONTACT — {contact['event']}")
        career = state["special"]["Shinobi Career"]
        old_quests = {str(q.get("name")):str(q.get("status","")).lower() for q in (before or {}).get("quests",[]) if isinstance(q,dict)}
        completed = [q for q in state.get("quests",[]) if isinstance(q,dict) and str(q.get("status","")).lower() in {"complete","completed","resolved"} and old_quests.get(str(q.get("name"))) not in {"complete","completed","resolved"}]
        for quest in completed:
            career["mission_history"] = _dedupe([*career.get("mission_history", []), {"turn":turn,"mission":quest.get("name","Mission"),"outcome":quest.get("outcome","Completed")}], 80)
        if completed:
            normalize_world_activity(state, before)
            notes.append(f"SHINOBI CAREER — {len(completed)} mission result(s) added; promotion still weighs leadership and politics")

    elif world == "Reincarnated as a Slime":
        sl = root["slime"]
        if re.search(r"\b(?:name|named|give.{0,20}name)\b", action_text, re.I) and re.search(r"\b(?:monster|goblin|orc|ogre|wolf|slime|spirit|subordinate|them|him|her)\b", result_text, re.I):
            record = {"turn":turn,"recipient":action_text[:160],"magicule_cost":"Reflected by the resolved resource change","relationship_effect":"Naming bond established","political_attention":"May attract groups that notice the evolution","result":str(narrative)[:240]}
            sl["naming_history"] = _dedupe([*sl.get("naming_history",[]),record],80); notes.append("NAMING — magicule, relationship, evolution, and political consequences recorded")
        if re.search(r"\b(?:analy[sz]e|great sage|raphael|inspect|appraise)\b", action_text, re.I):
            key = re.sub(r"\W+"," ",action_text).strip()[:80] or f"Analysis {turn}"; old = sl["analysis_records"].get(key,{"stage":"Unknown","evidence":[]})
            old["stage"] = "Confirmed" if old["stage"] == "Partial" else "Partial"; old["evidence"] = _dedupe([*old.get("evidence",[]),str(narrative)[:240]],20); sl["analysis_records"][key]=old
            notes.append(f"ANALYSIS — {key}: {old['stage']}")
        if re.search(r"\b(?:synthesi[sz]e|combine|merge)\b", action_text, re.I) and re.search(r"\b(?:skill|ability)\b", action_text, re.I):
            record = {"turn":turn,"inputs":action_text[:220],"compatible_concepts":"Derived from the inputs' shared function","surviving_concept":"The governing concept preserved by the resolved story","possible_result":str(narrative)[:220],"losses_or_risks":"Incompatible secondary traits may be lost","confidence":"Confirmed" if re.search(r"success|created|became|synthesi[sz]ed", narrative, re.I) else "Partial","status":"Resolved"}
            sl["synthesis"] = _dedupe([*sl.get("synthesis", []), record], 40)
            notes.append("SKILL SYNTHESIS — inputs, surviving concept, and possible losses recorded")
        if elapsed_minutes >= 10080:
            for name, row in sl.get("subordinates", {}).items():
                decision = {"turn":turn,"decision":f"Continued {row.get('current_project','their assigned work')} according to their own priorities"}
                row["independent_decisions"] = _dedupe([*row.get("independent_decisions", []), decision], 30)
                notes.append(f"SUBORDINATE AUTONOMY — {name} continued acting during the skip")

    elif world == "Bleach":
        bl = root["bleach"]; blade = state["special"].get("Zanpakuto Profile", {}); relation = bl["zanpakuto_relationship"]
        if re.search(r"\b(?:jinzen|inner world|zanpak|sword spirit|true name|meditat)\b", result_text, re.I):
            positive = not re.search(r"\b(?:reject|ignore|force|dominat|betray)\b", result_text, re.I); delta = 3 if positive else -4
            relation["approval"] = max(-100,min(100,_num(relation.get("approval"))+delta)); relation["memories"] = _dedupe([*relation.get("memories",[]),{"turn":turn,"event":str(narrative or action_text)[:250],"approval_change":delta}],60)
            blade["relationship"] = "Trusted" if relation["approval"]>=60 else "Recognized" if relation["approval"]>=15 else "Strained" if relation["approval"]<0 else blade.get("relationship","Distant")
            notes.append(f"ZANPAKUTŌ BOND — approval {relation['approval']:+d}; relationship {blade['relationship']}")
        if re.search(r"\b(?:reiatsu|spiritual pressure)\b", result_text, re.I) and re.search(r"\b(?:sense|detect|hide|conceal|intimidat|freeze|stagger|move|pressure|collapse)\b", result_text, re.I):
            bl["reiatsu_interactions"] = _dedupe([*bl.get("reiatsu_interactions",[]),{"turn":turn,"effect":str(narrative or action_text)[:260]}],60)
            notes.append("REIATSU INTERACTION — detection, concealment, intimidation, or movement effect recorded")
        placement = bl["squad_placement"]
        if placement.get("status") == "Awaiting placement" and re.search(r"\b(?:interview|evaluation|division offer|squad offer|captain)\b", result_text, re.I):
            placement["interviews"] = _dedupe([*placement.get("interviews", []), {"turn":turn,"detail":str(narrative)[:240]}], 30)
            notes.append("SQUAD PLACEMENT — evaluation or division interest recorded; the player still chooses narratively")
        duty = bl["duty"]
        duty_patterns = (("konso",r"\bkonso\b"),("patrols",r"\bpatrol\b"),("hollow_investigations",r"\b(?:hollow investig|investigat.{0,30}hollow)\b"),("gigai_use",r"\bgigai\b"),("division_reports",r"\b(?:division|squad) report\b"))
        for key, pattern in duty_patterns:
            if re.search(pattern, result_text, re.I):
                duty[key] = _dedupe([*duty.get(key, []), {"turn":turn,"detail":str(narrative or action_text)[:240]}], 50)
                notes.append(f"SOUL REAPER DUTY — {key.replace('_',' ')} updated")
    return notes
