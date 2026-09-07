"""Low-cost world depth, flexible progression, and encounter identity.

The data in this module is deliberately deterministic.  It gives the narrator
the setting-specific laws and vocabulary it needs without making another AI
request, while leaving players free to discover shortcuts, hybrid routes, and
original powers whenever the fiction supports them.
"""
from __future__ import annotations

import copy
import re


WORLD_DEPTH_PROFILES = {
    "One Piece": {
        "laws": [
            "Power may come from physical mastery, weapons, Haki, a Devil Fruit, unusual biology, science, or a combination that the story establishes.",
            "Devil Fruits remain unique and keep their seawater and Sea-Prism weaknesses; ingenious applications are encouraged and awakening changes scale rather than deleting counterplay.",
            "Haki grows through will, dangerous experience, focused instruction, and repeated application. Conqueror's Haki is an innate disposition, not an ordinary lesson.",
        ],
        "paths": [
            ("haki", "Haki", "Observation, Armament, and exceptionally Conqueror's applications may grow independently.", ["dangerous experience", "focused drills", "a capable teacher"], []),
            ("devil_fruit", "Devil Fruit Mastery", "Discover applications, improve control and stamina, then pursue awakening when body and mind catch up to the fruit.", ["a Devil Fruit ability"], ["Seawater and Sea-Prism suppression remain"]),
            ("martial", "Martial & Weapon Mastery", "Build a personal fighting style through body conditioning, weapons, Rokushiki-like methods, or original named forms.", ["practice", "combat evidence"], []),
            ("crew", "Crew, Ship & Command", "Crew bonds, navigation, medicine, engineering, leadership and a capable ship can change what adventures are possible.", ["people", "resources", "shared voyages"], []),
        ],
        "downtime": {"train": "Condition the body, refine Haki or rehearse named forms", "study": "Research charts, history, medicine, weather or a target", "network": "Build crew trust, port contacts and reputation", "patrol": "Sail, scout waters and respond to island trouble", "craft": "Repair or improve ships, weapons and useful equipment"},
        "elite": ["A recognizable fighting habit that can be read and countered", "A conviction or objective stronger than simple aggression", "A phase change tied to Haki, environment, allies, form, or desperation", "A believable retreat, surrender, capture, or pursuit condition"],
        "opportunities": ["Follow a Log Pose, rumor, or chart toward a specific island problem", "Use a crew role to solve a port, voyage, or shipboard need", "Cross paths with Marines, pirates, revolutionaries, or local rulers whose goals conflict"],
        "faction_doctrine": "Crews prize loyalty and personal dreams; Marines use rank, jurisdiction and orders; governments defend legitimacy, trade and territory.",
        "signature_nouns": ["Style", "Haki Art", "Technique", "Form", "Fruit Application"],
    },
    "Hunter x Hunter": {
        "laws": [
            "Nen follows aura capacity, control, category affinity, experience, personality, and explicit conditions rather than a generic spell list.",
            "Vows and restrictions increase effectiveness only when the cost is real, specific, enforceable, and relevant to the ability.",
            "Information, preparation and interpretation can decide an encounter before raw aura does; ordinary people do not automatically know Nen terminology.",
        ],
        "paths": [
            ("foundations", "Nen Foundations", "Ten, Zetsu, Ren, Gyo and related fundamentals may be learned, combined and refined in whatever order instruction permits.", ["aura awakening or instruction"], []),
            ("hatsu", "Personal Hatsu", "Design and evolve an ability from personality, Nen category, practical purpose, activation rules and meaningful restrictions.", ["Nen foundations", "self-knowledge", "testing"], []),
            ("vows", "Vows & Restrictions", "Add power or precision through a genuine personal stake; poorly chosen conditions can permanently hinder the user.", ["a clearly stated condition and consequence"], ["The restriction must actually be capable of costing something"]),
            ("hunter", "Hunter Career", "Licenses, specialties, contacts, intelligence and completed work expand access as much as combat ability.", ["credible accomplishments"], []),
        ],
        "downtime": {"train": "Refine aura fundamentals, Hatsu conditions or physical execution", "study": "Research a target, specialty, location, artifact or rule", "network": "Trade information and build Hunter, mafia or professional contacts", "patrol": "Track a target, protect a route or survey dangerous territory", "craft": "Prepare specialized tools whose value comes from planning rather than inventory clutter"},
        "elite": ["A Nen ability with observable rules rather than arbitrary effects", "A concealed condition the player can infer", "A motive that permits bargaining, deception, escape, or surrender", "A costly escalation or vow instead of a free second health bar"],
        "opportunities": ["Take a specialty-appropriate Hunter job with a concrete client or target", "Investigate a rumor whose value depends on verifying the information", "Seek a teacher, rival, arena, or field situation that exposes a Nen weakness"],
        "faction_doctrine": "Hunters pursue specialties and contracts; criminal groups protect profit and secrecy; families and teams follow personal obligations more than abstract alignment.",
        "signature_nouns": ["Hatsu", "Nen Ability", "Vow", "Technique"],
    },
    "Naruto": {
        "laws": [
            "Jutsu require a plausible mechanism: chakra control, nature or shape transformation, lineage, body, tool, seal, contract, instruction, research, or legitimate copying.",
            "Official rank and combat power are separate. Original jutsu, summons, bloodlines and ocular abilities are allowed when their mechanics, costs and counters fit the setting.",
            "Elemental interactions, chakra cost, information, teamwork, range and preparation matter; a rare gift can accelerate growth without making every discipline effortless.",
            "A Jinchūriki contains an independent tailed beast. The beast's full canon potential exists from sealing onward, while safe access, transformations, and freedom from loss-of-control drawbacks depend on seal condition, control, trust, and mastery.",
        ],
        "paths": [
            ("control", "Chakra Control", "Improve efficiency, precision, suppression, sensing and the demanding control used by medicine, genjutsu and advanced techniques.", ["repeated chakra use"], []),
            ("nature", "Nature & Shape Transformation", "Develop affinities and forms separately or combine them through a bloodline, insight, teacher, tool or original research.", ["an affinity or a plausible acquisition route"], []),
            ("jutsu", "Jutsu Development", "Create a named technique from a purpose, mechanism, cost, counters and field tests; extensions need not follow a fixed order.", ["knowledge and a workable mechanism"], []),
            ("lineage", "Bloodline, Dōjutsu & Forms", "Awaken and deepen inherited or original traits through compatible experience while retaining weaknesses and physiological costs.", ["the trait, lineage, implant, experiment, or other established source"], []),
            ("jinchuriki", "Jinchūriki Bond & Transformation", "Develop communication, seal stability, chakra access, controlled cloaks, partial transformation, cooperation, full transformation, and Tailed Beast Ball mastery without treating the beast as a passive skill.", ["a tailed beast sealed within the character", "communication, control, trust, or legitimate seal work"], ["The beast remains an independent person", "Extraction is normally fatal"]),
            ("contracts", "Summons, Seals & Tools", "Earn contracts, study formulas and combine preparation with combat rather than treating every capability as a personal stat.", ["access to a contract, teacher, text, or research route"], []),
        ],
        "downtime": {"train": "Practice chakra control, physical conditioning, a nature, or a named jutsu method", "study": "Analyze scrolls, intelligence, seals, medicine or clan theory", "network": "Build team, clan, village and client relationships", "patrol": "Perform reconnaissance, guard duty or a narrative mission", "craft": "Prepare seals, poisons, puppets, tools or field equipment narratively"},
        "elite": ["A readable shinobi style and established information advantage", "Elemental, range or tactical counterplay", "A reserve, transformation, summon, seal or team tactic with a real cost", "A mission objective that may matter more than defeating everyone"],
        "opportunities": ["Follow a village, clan, team or client responsibility as a narrative mission", "Seek a named teacher, archive or field condition for a specific jutsu idea", "Investigate a political or intelligence pressure that can change village relationships"],
        "faction_doctrine": "Villages balance missions, security, clans and national interests; teams follow command but retain personal loyalties; missing-nin and secret groups protect their own agendas.",
        "signature_nouns": ["Jutsu", "Secret Technique", "Formation", "Release", "Mode"],
    },
    "Solo Max-Level Newbie": {
        "laws": [
            "Levels, stats, skills, titles, artifacts, achievements, floors and hidden conditions are literal System mechanics and must remain persistent.",
            "Foreknowledge reveals remembered possibilities, not guaranteed outcomes; reality may diverge and copied abilities keep their stated conditions and capacity costs.",
            "A floor is an ecosystem with rules, factions, alternate clears and consequences, not only a corridor leading to one boss.",
        ],
        "paths": [
            ("build", "Level & Build", "Gain XP from meaningful contributions, assign or earn growth, and combine stats with a coherent combat or support identity.", ["meaningful activity"], []),
            ("copy", "Ability Copy", "Discover, satisfy and preserve copy conditions while managing capacity and restrictions.", ["a copy-capable power and a valid target"], []),
            ("artifacts", "Artifacts & Synergy", "Combine equipment, titles and abilities around effects rather than chasing raw rating alone.", ["acquisition and compatibility"], []),
            ("floors", "Floor Knowledge", "Learn ecology, factions, hidden conditions and alternate clears; confirmed reality supersedes remembered game knowledge.", ["exploration, research or foreknowledge"], []),
        ],
        "downtime": {"train": "Convert repeated practice into XP, proficiency and build refinement", "study": "Confirm floor rules, hidden conditions, enemies and artifact interactions", "network": "Build party, guild and administrator relationships", "patrol": "Farm or scout a floor without pretending routine monsters are bosses", "craft": "Improve durable equipment or prepare meaningful consumables narratively"},
        "elite": ["A floor-specific mechanic or hidden condition", "An ability pattern the player can learn or copy", "A phase tied to environment, threshold or administrator rule", "Rewards and consequences that reflect the chosen clear method"],
        "opportunities": ["Investigate a floor-specific hidden condition or alternate clear", "Challenge a rival's progress through preparation rather than arbitrary scaling", "Build a party role or artifact combination for the next known obstacle"],
        "faction_doctrine": "Guilds compete for clears, recruitment and information; administrators enforce their domains; floor societies pursue survival and local politics independently.",
        "signature_nouns": ["Skill", "Authority", "Artifact Art", "Combination"],
    },
    "Overgeared": {
        "laws": [
            "Satisfy supports combat, magic, support, command, commerce, exploration, social and production classes; Grid's crafting route is not the default player story.",
            "Levels, XP, class skills, titles, reputation, affinity and equipment are literal systems. NPC personalities and the world economy remain real rather than game props.",
            "Legendary or original classes need defining features, restrictions and advancement quests; rarity offers possibility, not automatic mastery.",
        ],
        "paths": [
            ("class", "Class Identity", "Develop features through class-aligned play, then specialize, evolve, add a secondary class, or discover an original route.", ["class use and milestones"], []),
            ("build", "Level, Skills & Titles", "Earn XP from combat and noncombat contribution; skills and titles can create combinations beyond raw level.", ["meaningful contribution"], []),
            ("equipment", "Equipment Synergy", "Choose, earn or create memorable equipment whose effects reinforce a playstyle; ingredients remain narrative.", ["access, loot, purchase, gift or creation"], []),
            ("social", "NPC Affinity, Guild & Rank", "Relationships unlock training, contracts, loyalty, politics and opportunity without overriding consent or personality.", ["repeated meaningful interaction"], []),
        ],
        "downtime": {"train": "Advance class skills, levels, specialization and party execution", "study": "Research class quests, NPC knowledge, dungeons, politics or item effects", "network": "Develop affinity, guild ties, clients, followers and rankings", "patrol": "Quest, scout, hunt or protect territory according to class", "craft": "Narrate production and retain only memorable finished items"},
        "elite": ["Class- and role-specific mechanics rather than generic damage", "Threat phases with party or terrain counterplay", "NPC or player objectives beyond the kill", "System rewards tied to contribution and method"],
        "opportunities": ["Advance the current class through a specific person, place, contract or obstacle", "Combine a class feature with equipment, a companion or a party role", "Pursue an NPC, guild, political, exploration or ranking opportunity unrelated to crafting when appropriate"],
        "faction_doctrine": "Guilds pursue rank, territory and members; kingdoms protect legitimacy and subjects; NPC organizations remember conduct and can outgrow player expectations.",
        "signature_nouns": ["Class Skill", "Combination", "Domain", "Formation", "Technique"],
    },
    "Reincarnated as a Slime": {
        "laws": [
            "Power comes from species, magicules, resistances, intrinsic/extra/unique/ultimate skills, names, gifts, harvests, synthesis and evolution triggers.",
            "Naming transfers power and creates relationships; evolution and Demon Lord awakening require their established causes rather than ordinary practice alone.",
            "Original skills and species are welcome when their hierarchy, costs, resistances, acquisition cause and evolution route fit the world.",
        ],
        "paths": [
            ("skills", "Skill Acquisition & Synthesis", "Acquire, analyze, combine and evolve abilities through compatible causes; a stronger result preserves a coherent conceptual identity.", ["compatible skills, insight or an acquisition event"], []),
            ("species", "Species & Evolution", "Meet biological, magical and narrative triggers for evolution; forms and resistances change what growth is possible.", ["a valid species route and sufficient trigger"], []),
            ("naming", "Naming & Subordinates", "Names can empower and bind communities, but consume magicules and create lasting social consequences.", ["magicules, authority and a recipient"], []),
            ("nation", "Nation, Alliances & Civilization", "Develop people, specialists, diplomacy, defense and institutions; individual strength cannot replace every civic function.", ["people, territory and relationships"], []),
        ],
        "downtime": {"train": "Circulate magicules, test skills, refine forms or coordinate subordinates", "study": "Analyze abilities, species, magic, diplomacy or technology", "network": "Build interspecies trust, alliances, trade and subordinate relationships", "patrol": "Protect settlements, explore the forest or respond to monster pressures", "craft": "Develop useful equipment, potions or infrastructure through specialists"},
        "elite": ["Skills and resistances that interact predictably", "An evolution, named form or ultimate action with a trigger", "Subordinates, territory or diplomacy that make victory more than a duel", "A motive compatible with alliance, submission, escape or transformation"],
        "opportunities": ["Analyze or synthesize a recorded skill toward a specific purpose", "Help a named community or subordinate evolve through an actual need", "Address a diplomatic, territorial or species pressure facing the current settlement"],
        "faction_doctrine": "Monster communities value protection, names and belonging; human states protect trade, faith and legitimacy; Demon Lords test power, influence and entertainment differently.",
        "signature_nouns": ["Intrinsic Skill", "Extra Skill", "Unique Skill", "Ultimate Skill", "Art"],
    },
    "Bleach": {
        "laws": [
            "Soul Reaper growth can involve Zanjutsu, Hakuda, Hoho, Kido, Reiatsu control, duty, experience and the relationship with a unique Zanpakuto spirit.",
            "Shikai and Bankai arise from Zanpakuto recognition and relationship, not a generic level gate. Background-established releases may start unlocked; otherwise the campaign authors them at the breakthrough.",
            "Numbered Kido remain learnable formulas. Unrevealed numbers may receive one permanent campaign-original formula that fits neighboring spells and Bleach logic.",
        ],
        "paths": [
            ("academy", "Soul Reaper Disciplines", "Zanjutsu, Hakuda, Hoho, Kido and Reiatsu control may specialize or support one another without a forced sequence.", ["instruction and practice"], []),
            ("zanpakuto", "Zanpakuto Bond", "Encounter the spirit, understand its identity and learn its true name; actions and values shape the eventual release.", ["an Asauchi or established Zanpakuto", "inner-world contact"], []),
            ("shikai", "Shikai", "Author and master a first release with a command, form, abilities, limits and tactical identity.", ["the Zanpakuto spirit's true name"], []),
            ("bankai", "Bankai", "Materialize and submit or reconcile with the spirit, then master a final release whose scale retains severe control demands.", ["an achieved Shikai", "spirit materialization", "sustained mastery"], []),
            ("squad", "Squad, Duty & Rank", "Division culture, missions, mentors and political standing shape access and responsibility; talented graduates may influence placement.", ["graduation and division acceptance"], []),
        ],
        "downtime": {"train": "Practice a Soul Reaper discipline or communicate with the Zanpakuto", "study": "Learn Kido formulae, Hollow traits, records, law or spiritual theory", "network": "Build academy, squad, Rukongai or Living World relationships", "patrol": "Perform konso, investigate spiritual disturbances and hunt Hollows", "craft": "Request, repair or prepare authorized spiritual equipment narratively"},
        "elite": ["Spiritual pressure and ability interactions rather than only larger numbers", "A release or transformation with a clear conceptual rule", "Damage to terrain, souls or duty that changes the objective", "A motive and command structure that can produce retreat, rescue, defection or pursuit"],
        "opportunities": ["Seek squad placement, mentorship or duty that suits the character's actual strengths", "Train a specific Kido formula or Soul Reaper discipline with a named source", "Enter the Zanpakuto inner world when the relationship or crisis creates an opening"],
        "faction_doctrine": "Divisions follow distinct duties and captains; Central 46 protects law and authority; Hollows, Arrancar and Quincy act through their own hierarchies and needs.",
        "signature_nouns": ["Zanpakuto Release", "Kido", "Technique", "Reiatsu Art"],
    },
    "Jujutsu Kaisen": {
        "laws": [
            "Every person has one birth slot: one innate cursed technique or one Heavenly Restriction. Learned applications extend that single rule rather than becoming extra innate techniques.",
            "Cursed energy, output, control, reinforcement, information and technique matchups matter. Grades describe expected assignment risk but do not replace an actual power assessment.",
            "Binding vows exchange real freedom, safety, time, information or capability. Black Flash is possible during exceptional impact timing but cannot be guaranteed on command.",
            "Original techniques may be overwhelmingly strong and need not have a contrived weakness, but their actual rule, activation and capabilities remain consistent once established.",
        ],
        "paths": [
            ("reinforcement", "Cursed-Energy Reinforcement", "Improve physical reinforcement, efficiency, output timing and the defense of body and soul.", ["cursed-energy access or a physical restriction path"], []),
            ("applications", "Technique Applications", "Invent named uses of the one innate technique by applying its governing rule to new tactical purposes.", ["an innate technique and a coherent derived use"], []),
            ("restriction", "Heavenly-Restriction Mastery", "Condition the enhanced body, sharpen senses and master cursed tools without pretending a restriction also grants a technique.", ["a Heavenly Restriction"], []),
            ("barriers", "Barriers, Simple Domains & Domains", "Learn curtains and anti-domain methods, then develop a complete domain only when barrier skill, output and self-understanding support it.", ["instruction, insight or a story-valid breakthrough"], []),
            ("healing", "Reverse Cursed Technique", "Learn to create positive energy through an exceptionally difficult control breakthrough; output and healing others remain separate accomplishments.", ["extreme control, insight and a valid breakthrough"], []),
            ("maximum", "Maximum Technique", "Express the innate rule at its greatest non-domain output without turning it into a different power.", ["deep birth-slot mastery, output and a coherent interpretation"], []),
            ("vows", "Binding Vows", "Trade a precise restriction, danger or sacrifice for a proportional advantage whose terms remain binding afterward.", ["an explicit promise, benefit, price and breach consequence"], []),
            ("grade", "Mission & Grade Record", "Build witnessed exorcisms, recommendations, judgment and reliability so official standing can catch up to real capability.", ["verified field work or recognized accomplishments"], []),
            ("society", "Clan, Curse & Soul Affairs", "Navigate clan duties, cursed-spirit identity, incarnation, possession and competing souls as persistent relationships and pressures.", ["a relevant origin, relationship or encounter"], []),
        ],
        "downtime": {"train":"Practice reinforcement, output timing or a named technique application", "study":"Analyze barriers, souls, curse ecology, vows or technique matchups", "network":"Build school, clan, headquarters or curse-user relationships", "patrol":"Investigate manifestations and protect civilians through narrative assignments", "craft":"Acquire, maintain or commission memorable cursed tools narratively"},
        "elite": ["A readable cursed-technique rule and information battle", "A barrier, vow or terrain interaction", "A reason the curse or curse user fights beyond random hostility", "A domain or maximum expression that evolves the established technique"],
        "opportunities": ["Investigate a local manifestation with a specific human cause", "Develop a named application of the birth slot", "Choose how to respond to a school, clan or headquarters obligation"],
        "faction_doctrine": "Schools protect and train sorcerers while disagreeing on methods; headquarters protects tradition and risk control; clans protect inherited authority; curses follow the fears, instincts and ideals that formed them.",
        "signature_nouns": ["Cursed Technique", "Technique Application", "Maximum Technique", "Domain Expansion", "Barrier Art"],
    },
    "Custom World": {
        "laws": ["Use the player's described metaphysics as binding campaign law and preserve every established exception.", "A new ability needs a source, present effect, cost or limitation, counterplay and a route for growth."],
        "paths": [("personal", "Personal Development", "Develop established powers, relationships, knowledge and position through any plausible route.", ["a world-valid method"], [])],
        "downtime": {"train": "Practice a defined capability", "study": "Research the world's rules and people", "network": "Build relationships and standing", "patrol": "Engage with local pressures", "craft": "Create memorable finished objects narratively"},
        "elite": ["A consistent signature mechanic", "A motive beyond attacking", "Readable counterplay", "A consequence or retreat condition"],
        "opportunities": ["Follow a known local pressure", "Develop an established capability", "Build a relationship that changes access or responsibility"],
        "faction_doctrine": "Groups act from their resources, beliefs, relationships and physical reach.",
        "signature_nouns": ["Technique", "Spell", "Art", "Form"],
    },
}


def profile_for(world):
    return WORLD_DEPTH_PROFILES.get(world, WORLD_DEPTH_PROFILES["Custom World"])


def _text(value):
    return str(value or "").strip()


def _readiness(state, path):
    """Return an informative status, never a lock or required order."""
    haystack = " ".join([
        _text(state.get("background")), _text(state.get("position")),
        " ".join(map(str, (state.get("skills") or {}).keys())),
        _text(state.get("special")), _text(state.get("class_profile")),
    ]).lower()
    path_id, label = path[0], path[1]
    tokens = {
        "haki": ("haki",), "devil_fruit": ("devil fruit",), "martial": ("style", "sword", "martial", "combat"),
        "foundations": ("ten", "zetsu", "ren", "nen"), "hatsu": ("hatsu",), "vows": ("vow", "restriction"),
        "control": ("chakra",), "nature": ("release", "nature affinity"), "jutsu": ("jutsu", "technique"), "lineage": ("kekkei", "dojutsu", "bloodline"),
        "jinchuriki": ("jinchuriki", "jinchūriki", "tailed beast", "kurama", "shukaku", "gyuki"),
        "copy": ("copied", "copy"), "artifacts": ("artifact",), "floors": ("floor", "tower"),
        "class": ("class",), "equipment": ("equipment", "weapon", "armor"), "social": ("guild", "affinity", "reputation"),
        "skills": ("skill",), "species": ("species", "evolution"), "naming": ("named", "naming"), "nation": ("nation", "leader", "ruler"),
        "zanpakuto": ("zanpakuto",), "shikai": ("shikai",), "bankai": ("bankai",), "squad": ("squad", "division", "academy"),
        "reinforcement": ("cursed energy", "reinforcement", "heavenly restriction"), "applications": ("cursed technique", "application"),
        "restriction": ("heavenly restriction",), "barriers": ("barrier", "domain"), "healing": ("reverse cursed technique",),
    }.get(path_id, (label.lower(),))
    if any(token in haystack for token in tokens):
        return "Active or established"
    return "Available through a plausible route"


def _signature_candidate(name, detail):
    if not isinstance(detail, dict):
        return False
    label = f"{name} {detail.get('rank', '')} {detail.get('category', '')}".lower()
    if re.search(r"fundamentals?|proficiency|conditioning|literacy|basic|curriculum", label):
        return False
    explicit = any(detail.get(key) for key in ("signature", "release_stage", "kido", "non_canon", "original"))
    developed = bool(detail.get("effect") and (detail.get("limitation") or detail.get("cost")) and detail.get("growth_path"))
    named_kind = any(token in label for token in ("jutsu", "hatsu", "shikai", "bankai", "unique skill", "ultimate skill", "class skill", "technique", "form", "release"))
    return explicit or (developed and named_kind)


def normalize_world_depth(state, before=None):
    """Synchronize a compact, app-owned view from state the campaign has earned."""
    if not isinstance(state, dict):
        return []
    world = state.get("world", "Custom World")
    profile = profile_for(world)
    depth = state.get("world_depth") if isinstance(state.get("world_depth"), dict) else {}
    repairs = []
    if depth.get("world") != world or int(depth.get("profile_version", 0) or 0) < 1:
        depth = {"world": world, "profile_version": 1, "progression_paths": [], "signature_techniques": [],
                 "faction_doctrines": {}, "downtime_history": [], "canon_ripples": [],
                 "elite_encounters": {}, "opportunities": []}
        repairs.append(f"Initialized flexible {world} world-depth profile")

    depth["progression_paths"] = [{
        "id": row[0], "name": row[1], "description": row[2],
        "possible_routes": list(row[3]), "hard_requirements": list(row[4]),
        "status": _readiness(state, row), "fixed_order": False,
    } for row in profile["paths"]]

    existing = {str(row.get("name", "")).lower(): row for row in depth.get("signature_techniques", []) if isinstance(row, dict)}
    for name, detail in (state.get("skills") or {}).items():
        if not _signature_candidate(name, detail):
            continue
        row = existing.get(str(name).lower(), {"name": str(name), "created_turn": int(state.get("turn", 0) or 0)})
        row.update({
            "stage": _text(detail.get("stage") or detail.get("rank") or "Established"),
            "mechanism": _text(detail.get("effect") or detail.get("description")),
            "activation": _text(detail.get("activation") or detail.get("use")),
            "cost": _text(detail.get("cost") or detail.get("limitation")),
            "counters": copy.deepcopy(detail.get("counters") or []),
            "next_milestone": _text(detail.get("growth_path") or "Develop a new application through training or meaningful use"),
            "evidence": copy.deepcopy(detail.get("evidence") or []),
        })
        existing[str(name).lower()] = row
    depth["signature_techniques"] = list(existing.values())[-60:]

    factions = state.get("factions") if isinstance(state.get("factions"), dict) else {}
    doctrines = depth.get("faction_doctrines") if isinstance(depth.get("faction_doctrines"), dict) else {}
    clocks = state.get("faction_clocks") if isinstance(state.get("faction_clocks"), dict) else {}
    for name in factions:
        row = doctrines.setdefault(str(name), {})
        clock = clocks.get(name) if isinstance(clocks.get(name), dict) else {}
        row.setdefault("doctrine", profile["faction_doctrine"])
        row["current_pressure"] = _text(clock.get("immediate_goal") or clock.get("goal") or row.get("current_pressure") or "Protect current interests")
        row["capabilities"] = copy.deepcopy(clock.get("resources") or row.get("capabilities") or {})
        row["status"] = _text(clock.get("status") or row.get("status") or "active")
    depth["faction_doctrines"] = doctrines
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
    enemy_name = _text(enemy.get("name"))
    if enemy_name and (enemy.get("elite") or enemy.get("boss") or re.search(r"elite|boss|captain|commander|guardian|admiral|kage", enemy_name, re.I)):
        encounters = depth.get("elite_encounters") if isinstance(depth.get("elite_encounters"), dict) else {}
        encounter = encounters.setdefault(enemy_name, {})
        encounter.update({
            "identity": _text(enemy.get("identity") or encounter.get("identity") or "A named threat whose tactics should remain consistent"),
            "habit": _text(enemy.get("habit") or enemy.get("pattern") or encounter.get("habit") or "Not yet read"),
            "weakness": _text(enemy.get("weakness") or encounter.get("weakness") or "Not yet discovered"),
            "objective": _text(enemy.get("objective") or encounter.get("objective") or "Unknown"),
            "phases": copy.deepcopy(enemy.get("phases") or encounter.get("phases") or []),
            "retreat_condition": _text(enemy.get("retreat_condition") or encounter.get("retreat_condition") or "Depends on motive and battlefield state"),
            "last_seen_turn": int(state.get("turn", 0) or 0),
        })
        encounters[enemy_name] = encounter
        depth["elite_encounters"] = encounters
    depth["opportunities"] = contextual_opportunities(state, depth=depth)
    state["world_depth"] = depth
    return repairs


def contextual_opportunities(state, depth=None):
    profile = profile_for(state.get("world", "Custom World"))
    location = _text(state.get("location") or "the current area")
    role = _text((state.get("special") or {}).get("Archetype") or state.get("position") or "your role")
    known_people = list((state.get("npc_memories") or {}).keys())
    target = known_people[-1] if known_people else ""
    seeds = profile["opportunities"]
    results = []
    for seed in seeds:
        lead = f"At {location}, use {role} training or field experience to {seed[:1].lower() + seed[1:]}"
        if target:
            lead += f" with {target} if useful"
        results.append(lead.rstrip(".") + ".")
    return results[:3]


def record_downtime(state, actions, elapsed_minutes):
    if int(elapsed_minutes or 0) < 60:
        return None
    profile = profile_for(state.get("world", "Custom World"))
    text = " ".join(_text(x) for x in (actions or [])).lower()
    kind = next((kind for kind in ("train", "study", "network", "patrol", "craft") if kind in text), "other")
    if kind == "other":
        if re.search(r"talk|meet|relationship|recruit|diplom", text): kind = "network"
        elif re.search(r"research|read|learn|analy", text): kind = "study"
        elif re.search(r"guard|scout|hunt|mission|quest", text): kind = "patrol"
        elif re.search(r"forge|make|build|sew|brew|repair", text): kind = "craft"
        elif re.search(r"practice|master|exercise", text): kind = "train"
    if kind == "other":
        return None
    row = {"turn": int(state.get("turn", 0) or 0), "canon_day": int(state.get("canon_day", 0) or 0),
           "kind": kind, "actions": [_text(x)[:240] for x in (actions or []) if _text(x)],
           "elapsed_minutes": int(elapsed_minutes), "world_method": profile["downtime"][kind]}
    depth = state.setdefault("world_depth", {})
    depth.setdefault("downtime_history", []).append(row)
    depth["downtime_history"] = depth["downtime_history"][-100:]
    return row


def record_canon_ripples(state, events):
    depth = state.setdefault("world_depth", {})
    ledger = depth.setdefault("canon_ripples", [])
    for event in events or []:
        if not isinstance(event, dict):
            continue
        kind = _text(event.get("type")).lower()
        if "canon" not in kind and not event.get("canon_event"):
            continue
        ledger.append({"turn": int(state.get("turn", 0) or 0), "canon_day": int(state.get("canon_day", 0) or 0),
                       "title": _text(event.get("title") or "Canon development"),
                       "location": _text(event.get("location") or "Unknown"),
                       "effect": _text(event.get("narrative") or event.get("summary"))[:700],
                       "player_relevance": _text(event.get("player_knowledge") or event.get("information_scope") or "Indirect until learned")})
    depth["canon_ripples"] = ledger[-100:]


def world_depth_rules(state):
    """Compact prompt rules. This replaces repeated generic explanation."""
    profile = profile_for(state.get("world", "Custom World"))
    path_lines = [f"{p[1]} — {p[2]} Routes: {', '.join(p[3])}." + (f" True requirements: {', '.join(p[4])}." if p[4] else "") for p in profile["paths"]]
    downtime = "; ".join(f"{key}: {value}" for key, value in profile["downtime"].items())
    return """
WORLD DEPTH (application-provided; no extra model call):
- Laws: {laws}
- Flexible progression map (guidance, NEVER a mandatory order or UI checklist): {paths}
- Downtime resolves in setting-specific terms: {downtime}.
- Elite encounters require: {elite}.
- When structured combat begins against an elite or boss, give combat.enemy a stable identity, habit/pattern, objective, weakness clues, phases when justified, and retreat_condition. Reveal only what the character could observe; preserve the hidden structure between rounds.
- Faction doctrine: {faction}
- Original signature techniques are encouraged. Develop them as concept/prototype/stable/signature/evolved when useful, but allow shortcuts or starting mastery established by the background. A named technique keeps a mechanism, activation, cost/limitation, counters, evidence and next milestone; never replace its identity between turns.
- Canon collision uses distance, relationships, rank, knowledge, timing and prior divergence. A distant event produces believable ripples or delayed information; it does not teleport the player into the canon cast.
- Generate opportunities from the character's role, exact location, known people, responsibilities and unfinished business. Leads are optional and specific, not generic quest filler.
""".format(laws=" | ".join(profile["laws"]), paths=" | ".join(path_lines), downtime=downtime,
           elite="; ".join(profile["elite"]), faction=profile["faction_doctrine"])
