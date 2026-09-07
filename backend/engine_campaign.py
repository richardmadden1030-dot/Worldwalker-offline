"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, hashlib, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, world_primer_for, world_supports_races, infer_race_from_background, WORLD_RACES, format_calendar_date, starting_eras_for, starting_era_by_id, power_profile_for
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from reliability import update_narrative_memory
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks,
                     ensure_currency_state, record_opening_currency)
from bleach_data import (academy_kido_skills, kido_reference_summary,
                         owns_release, zanpakuto_tracks)
from world_progression import normalize_world_progression
from world_depth import normalize_world_depth
from lit_systems import initialize_lit_systems
from skill_system import infer_skill_metadata
from ability_mechanics import compile_ability_mechanics
from overgeared_classes import canon_class_prompt_reference, infer_class_type, starter_kit_for
from jjk_system import (apply_birth_slot, generate_birth_slot, generate_curse_identity,
                        initialize_jjk_state, is_curse_origin, normalized_grade,
                        normalize_birth_slot_package)
from age_system import initialize_age_tracking
from naruto_system import (apply_jinchuriki_start, build_chakra_affinity_profile,
                           build_jinchuriki_profile, jinchuriki_requested,
                           normalize_chakra_affinity_profile, normalize_jinchuriki_profile)


DEFAULT_SETTINGS = {
    "provider": "local",
    "local_base_url": "http://localhost:1234/v1",
    "local_token": "",
    "api_key": "",
    "model": "",
    "secondary_model": "",
    "narration": "Concise",
    "autosave": True,
    "sound_enabled": True,
    "music_enabled": True,
    "music_volume": 0.35,
    "animations_enabled": True,
    "portrait_generation_enabled": True,
    "image_model": "gpt-image-2",
    "local_image_model": "",
    "portrait_quality": "low",
    "developer_mode": False,
}


WORLD_STARTER_GEAR = {
    "One Piece": "Travel-worn weapon and island supplies",
    "Hunter x Hunter": "Practical travel gear and training wraps",
    "Naruto": "Kunai pouch, shuriken and field supplies",
    "Solo Max-Level Newbie": "Beginner weapon and emergency potion",
    "Overgeared": "Beginner equipment appropriate to the chosen Satisfy class",
    "Reincarnated as a Slime": "Species-appropriate natural weapon or focus",
    "Bleach": "Unnamed Asauchi, academy uniform, soul pager and basic field kit",
    "Jujutsu Kaisen": "School uniform or practical street clothes, protective talismans and an origin-appropriate cursed tool",
    "Custom World": "Setting-appropriate weapon and travel kit",
}

WORLD_STARTER_SKILL = {
    "One Piece": "Foundation Combat Style", "Hunter x Hunter": "Conditioned Fundamentals",
    "Naruto": "Academy Fundamentals", "Solo Max-Level Newbie": "System Adaptation",
    "Overgeared": "Class Fundamentals", "Reincarnated as a Slime": "Intrinsic Species Trait",
    "Bleach": "Shinigami Fundamentals", "Custom World": "Background Expertise",
    "Jujutsu Kaisen": "Jujutsu Fundamentals",
}

NEN_CATEGORIES = ("Enhancement", "Transmutation", "Conjuration", "Specialization", "Manipulation", "Emission")


def nen_category_efficiency(primary):
    """Canon-shaped affinity wheel used by creation, UI and progression."""
    primary = primary if primary in NEN_CATEGORIES else "Enhancement"
    index = NEN_CATEGORIES.index(primary)
    values = {}
    for position, category in enumerate(NEN_CATEGORIES):
        distance = min((position - index) % 6, (index - position) % 6)
        values[category] = (100, 80, 60, 40)[min(distance, 3)]
    if primary == "Enhancement":
        values["Specialization"] = 0
    return values

STARTER_SKILL_DESCRIPTIONS = {
    ("One Piece", "Navigator"): "Charts courses, reads weather and currents, corrects a ship's heading, and recognizes common navigation hazards.",
    ("One Piece", "Shipwright"): "Inspects hulls and rigging, performs practical repairs, chooses suitable materials, and keeps a vessel seaworthy.",
    ("One Piece", "Medic"): "Stabilizes injuries, treats common illness, manages field supplies, and recognizes when specialist care is needed.",
    ("One Piece", "Archaeologist"): "Studies scripts, ruins, artifacts, and historical context while documenting discoveries without pretending to read languages not yet learned.",
    ("Naruto", "Ninjutsu Student"): "Molds chakra, performs hand seals, uses basic transformations, and executes beginner ninjutsu without wasting control.",
    ("Naruto", "Taijutsu Specialist"): "Uses stance, footwork, timing, conditioning, and close-range combinations appropriate to a trained shinobi.",
    ("Naruto", "Medic"): "Applies chakra control to diagnosis, first aid, and safe treatment while recognizing injuries beyond current training.",
    ("Naruto", "Sealing Specialist"): "Designs, reads, and safely tests beginner sealing formulae using chakra ink, prepared surfaces, and precise control.",
    ("Naruto", "Sensor"): "Detects and distinguishes nearby chakra signatures within the character's trained range without granting omniscience.",
    ("Naruto", "Puppet User"): "Controls a training puppet with chakra threads, maintains its mechanisms, and coordinates simple concealed tools.",
    ("Overgeared", "Blacksmith"): "Selects materials, controls heat, shapes and repairs equipment, and evaluates the causes of common production failures.",
    ("Overgeared", "Warrior"): "Uses weapon spacing, armor, stamina, and basic combat skills expected of a beginning Satisfy warrior.",
    ("Overgeared", "Alchemist"): "Identifies common reagents, follows production recipes, controls brewing conditions, and diagnoses ordinary failures.",
    ("Overgeared", "Knight"): "Uses armor, guard skills, threat control, mounted or formation discipline, and the protections expected of a beginning Satisfy knight.",
    ("Overgeared", "Magic Swordsman"): "Alternates basic weapon skills and learned magic without pretending either discipline is already mastered.",
    ("Overgeared", "Priest/Healer"): "Uses beginner healing, cleansing, support positioning, resource management, and the obligations of a faith-based Satisfy class.",
    ("Overgeared", "Summoner"): "Maintains a beginner contract, issues clear commands, protects a companion, and manages divided attention and mana.",
    ("Overgeared", "Tactician"): "Reads party roles, encounter geometry, cooldown timing, and objectives to propose practical coordination rather than magical certainty.",
    ("Overgeared", "Beast Master"): "Reads monster behavior, forms setting-valid bonds, directs a trained companion, and recognizes when control is impossible.",
    ("Overgeared", "Explorer"): "Scouts routes, notices environmental clues, maps dungeons, and evaluates risks without automatically revealing hidden conditions.",
    ("Overgeared", "Merchant/Orator"): "Appraises ordinary opportunities, negotiates, presents proposals, and builds reputation without overriding an NPC's interests or consent.",
    ("Hunter x Hunter", "Tracker"): "Reads tracks, prepares routes, notices environmental clues, and follows a quarry without assuming supernatural senses.",
    ("Hunter x Hunter", "Beast Hunter"): "Studies dangerous fauna, reads habitats, prepares captures, and avoids mistaking fieldcraft for unlearned Nen.",
    ("Hunter x Hunter", "Blacklist Hunter"): "Builds criminal dossiers, plans safe arrests, preserves evidence, and works through lawful Hunter channels.",
    ("Solo Max-Level Newbie", "Trap Specialist"): "Recognizes mechanical and System trap patterns, tests routes, and disarms hazards when the required tools and timing allow it.",
    ("Bleach", "Zanjutsu Specialist"): "Uses foundational sword posture, distance, cuts, guards, and spiritual awareness without implying an earned release.",
    ("Reincarnated as a Slime", "Skill Analyst"): "Observes an ability's visible behavior, compares repeated effects, and forms practical hypotheses without bypassing unknown rules.",
    ("Reincarnated as a Slime", "Magic Crafter"): "Shapes compatible materials with controlled magicules to repair, prototype, and improve setting-valid tools.",
}


def starter_skill_description(world, archetype, skill_name):
    specific = STARTER_SKILL_DESCRIPTIONS.get((world, archetype))
    if specific:
        return specific
    defaults = {
        "One Piece": "Covers practical movement, combat awareness, stamina, and field habits used by capable travelers of the local seas.",
        "Hunter x Hunter": "Covers observation, conditioning, planning, and field discipline without granting Nen knowledge that has not been learned.",
        "Naruto": "Covers chakra safety, shinobi movement, tools, teamwork, and the basic techniques appropriate to the character's training.",
        "Solo Max-Level Newbie": "Covers System menus, equipment use, combat feedback, and repeatable beginner strategies available at the current stage.",
        "Overgeared": "Covers the concrete class actions, equipment handling, and Satisfy systems expected of a beginning player in this role.",
        "Reincarnated as a Slime": "Covers the species traits, magicule awareness, and survival behaviors the character can currently use and explain.",
        "Bleach": "Covers the spiritual awareness, movement, combat safety, and established techniques appropriate to the character's current station.",
        "Jujutsu Kaisen": "Covers cursed-energy safety, reinforcement, curse awareness, and the field habits appropriate to the character's current training.",
        "Custom World": "Covers the concrete tools, methods, and limits established for this role in the campaign's world.",
    }
    return defaults.get(world, f"Applies the practical tools and methods represented by {skill_name}.")

# A concrete, named starting weapon/tool per archetype — "a sword", not "a
# travel-worn weapon" — so the opening loadout already looks like it belongs
# to this specific character instead of a generic placeholder. Falls back to
# WORLD_STARTER_GEAR's vaguer default only for an archetype not listed here
# (e.g. a freeform archetype the player typed in that doesn't match).
WORLD_ARCHETYPE_GEAR = {
    "One Piece": {
        "Brawler": "Reinforced Combat Gloves", "Swordsman": "Standard Cutlass",
        "Marksman": "Flintlock Pistol", "Navigator": "Compass and Rigging Knife",
        "Shipwright": "Carpenter's Hatchet and Toolkit", "Medic": "Medical Satchel and Scalpel",
        "Roguish Fighter": "Concealed Throwing Knives",
        "Archaeologist": "Field Journal, Rubbing Paper, and Utility Knife",
    },
    "Hunter x Hunter": {
        "Martial Artist": "Wrapped Hand Guards", "Tracker": "Hunting Knife and Rope",
        "Strategist": "Field Notebook and Compass", "Infiltrator": "Lockpicks and Grappling Wire",
        "Medic": "Field Medical Kit", "Treasure Hunter": "Prybar and Lantern",
        "Information Broker": "Hidden Recorder and Contact Ledger",
        "Beast Hunter": "Reinforced Capture Rope and Field Knife",
        "Blacklist Hunter": "Restraining Wire and Bounty Dossier",
    },
    "Naruto": {
        "Taijutsu Specialist": "Wrapped Forearm Guards", "Ninjutsu Student": "Kunai and Shuriken Set",
        "Genjutsu Student": "Chakra Paper and Sealing Tags", "Scout": "Binoculars and Smoke Bombs",
        "Medic": "Medical Ninja Pouch", "Weapon Specialist": "Short Ninjatō",
        "Tactician": "Tactical Scroll Case",
        "Samurai": "Iron Country Katana", "Sealing Specialist": "Blank Formula Scrolls and Chakra Ink",
        "Sensor": "Signal Tags and Field Binoculars", "Puppet User": "Training Puppet and Chakra Thread Spools",
    },
    "Solo Max-Level Newbie": {
        "All-Rounder": "Balanced Steel Longsword", "Melee": "Iron Broadsword",
        "Ranged": "Reinforced Shortbow", "Caster": "Novice's Focus Wand",
        "Assassin": "Twin Curved Daggers", "Tank": "Kite Shield and Mace",
        "Support": "Beginner's Healing Wand",
        "Trap Specialist": "Trap Kit and System-inspected Tools",
    },
    "Overgeared": {
        "Warrior": "Plain Iron Longsword", "Swordsman": "Balanced One-Handed Sword",
        "Knight": "Training Shield, Arming Sword, and Mail Shirt", "Spearman": "Ashwood Spear",
        "Archer": "Basic Recurve Bow", "Mage": "Apprentice's Wooden Staff and Spellbook",
        "Magic Swordsman": "Mana-conductive Training Blade", "Assassin": "Paired Daggers",
        "Martial Artist": "Reinforced Knuckle Guards", "Tank": "Tower Shield and Mace",
        "Priest/Healer": "Novice Healing Rod and Temple Symbol", "Support": "Novice Support Focus",
        "Summoner": "Beginner Contract Token and Focus Wand", "Tactician": "Command Slate and Signal Kit",
        "Beast Master": "Training Whistle and Companion Care Kit", "Explorer": "Field Map, Grappling Line, and Shortsword",
        "Merchant/Orator": "Appraisal Lens and Contract Ledger", "Blacksmith": "Smithing Hammer and Tongs",
        "Alchemist": "Beginner Alchemy Kit and Reagent Case", "Tailor": "Sewing Kit and Cloth Shears",
        "Architect": "Drafting Kit and Survey Tools",
    },
    "Custom World": {
        "Warrior": "Sword and Shield", "Scout": "Hunting Bow",
        "Scholar": "Satchel of Notes and a Quill", "Mage": "Apprentice's Spellbook",
        "Rogue": "Concealed Dagger", "Healer": "Herbalist's Satchel",
    },
    "Reincarnated as a Slime": {
        "Brawler Monster": "Natural Claws and Tough Hide", "Skill Analyst": "Innate Analytical Sense",
        "Elementalist": "Elemental Affinity Core", "Beast-kin Warrior": "Bone-forged Claw Blade",
        "Diplomat/Leader": "Ceremonial Sash of Office", "Support/Healer": "Herbal Pouch and Regenerative Trait",
        "Assassin-type Monster": "Venomous Fangs",
        "Magic Crafter": "Magicule-conductive Hand Tools",
    },
    "Bleach": {
        "Zanjutsu Specialist": "Unnamed Asauchi and reinforced sword-practice wraps",
        "Kido Caster": "Unnamed Asauchi, academy Kido notes and practice targets",
        "Hakuda Fighter": "Unnamed Asauchi and reinforced hand-to-hand practice wraps",
        "Hoho Specialist": "Unnamed Asauchi and academy movement-training sandals",
        "Healer": "Unnamed Asauchi and basic Fourth Division first-aid supplies",
        "Tactician": "Unnamed Asauchi, soul pager and mission notebook",
        "Kaidō Healer": "Unnamed Asauchi and academy medical kit",
        "Tactical Officer": "Unnamed Asauchi, academy field kit and patrol notebook",
    },
}

POOL_STATS = {
    "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
    "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
    "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
    "Solo Max-Level Newbie": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Overgeared": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
    "Bleach": (("Hakuda", "Willpower"), ("Reiatsu Control", "Willpower")),
    "Jujutsu Kaisen": (("Physical Ability", "Soul Stability"), ("Cursed Energy Reserves", "Cursed Energy Control")),
    "Custom World": (("Constitution", "Strength"), ("Wisdom", "Intelligence")),
}

ABILITY_ASPECTS = {
    "cursed relic": "Hexed Relic", "cursed artifact": "Hexed Relic",
    "curse": "Hex", "relic": "Relic", "craft": "Forge",
    "space-time": "Warp", "space time": "Warp", "spacetime": "Warp",
    "teleport": "Warp", "portal": "Warp", "warp": "Warp",
    "seal": "Seal", "fuinjutsu": "Seal", "fuuinjutsu": "Seal",
    "fire": "Ember", "flame": "Ember", "heat": "Ember", "water": "Tide",
    "wind": "Gale", "air": "Gale", "lightning": "Storm", "electric": "Storm",
    "earth": "Stone", "ice": "Frost", "shadow": "Shadow", "dark": "Shadow",
    "light": "Radiance", "heal": "Renewal", "medical": "Renewal", "sense": "Echo",
    "sensor": "Echo", "speed": "Flash", "strong": "Titan", "strength": "Titan",
}

WORLD_ABILITY_FORMS = {
    "Naruto": [
        ("{aspect} Thread Technique", "a personal chakra transformation discovered during uneven early training",
         "forms fine {aspect_lower}-natured chakra threads for precise attacks, traps, sensing, or utility",
         "complex shapes quickly exhaust chakra and collapse when concentration breaks",
         "improve chakra control, learn the matching nature transformation, and develop larger stable patterns"),
        ("{aspect} Pulse", "an unusual chakra response first triggered during a formative moment",
         "releases a short pulse of {aspect_lower}-aligned chakra whose exact use adapts to the user's intent",
         "has short range and becomes unreliable when emotionally or physically exhausted",
         "practice controlled pulses, study sealing principles, and learn to sustain the effect"),
    ],
    "One Piece": [
        ("{aspect} Imprint Style", "an improvised island fighting art shaped by the character's environment",
         "imprints {aspect_lower}-themed force or motion into strikes, tools, and movement without ignoring physical limits",
         "requires preparation and stamina; stronger effects expose the user to retaliation",
         "condition the body, refine timing, and eventually combine the style with Haki if it is learned"),
        ("{aspect} Instinct", "a rare natural sensitivity that has not yet matured into formal Haki",
         "notices subtle {aspect_lower}-like patterns in danger, movement, and intent a moment earlier than normal",
         "provides impressions rather than certainty and fails amid overwhelming chaos",
         "survive demanding encounters, train awareness, and seek instruction in Observation Haki"),
    ],
    "Hunter x Hunter": [
        ("{aspect} Resonance", "a dormant Nen inclination expressed before the character understands aura",
         "causes aura to resonate with {aspect_lower}-themed conditions and hints at a future personal Hatsu",
         "remains inconsistent until the character properly opens and controls their aura nodes",
         "learn Ten, Ren, Zetsu and Hatsu, then define restrictions that strengthen the effect"),
        ("{aspect} Tell", "an exceptional learned instinct that may later become a Nen technique",
         "reads small bodily and environmental cues through a {aspect_lower}-themed mental association",
         "can be deceived and becomes noisy under stress or unfamiliar conditions",
         "test the instinct, study opponents, and later reinforce it with a suitable Nen category"),
    ],
    "Solo Max-Level Newbie": [
        ("Adaptive Skill: {aspect} Script", "a latent trait recognized when the System first evaluates the player",
         "builds proficiency when the player repeats successful {aspect_lower}-aligned solutions",
         "starts at low rank and loses efficiency when the same trick is forced into unsuitable situations",
         "meet hidden conditions, diversify applications, and earn System achievements"),
    ],
    "Overgeared": [
        ("Rare Skill: {aspect} Method", "a personal knack translated into a Satisfy-compatible class skill",
         "applies a narrow {aspect_lower}-themed advantage to actions that genuinely fit the character's chosen class and playstyle",
         "the skill cannot replace missing levels, resources, prerequisites, cooldowns, or class compatibility",
         "use it in varied class-appropriate situations, complete related quests, and earn a specialization"),
        ("Rare Skill: {aspect} Insight", "an unusual pattern of play recognized by Satisfy's class system",
         "reveals a practical {aspect_lower}-aligned option in combat, magic, support, command, exploration, social play, or production as appropriate to the character",
         "it provides an opportunity rather than an automatic result and only functions inside the chosen class's real capabilities",
         "prove the insight through difficult achievements and unlock a class evolution or linked skill"),
    ],
    "Reincarnated as a Slime": [
        ("Extra Skill: {aspect} Weave", "a desire and prior-life inclination crystallized into a world-valid skill",
         "shapes magicules into controlled {aspect_lower}-themed effects suited to the user's species",
         "output is limited by magicule capacity, analysis, resistances, and control",
         "increase magicule capacity, analyze related phenomena, and combine compatible skills"),
    ],
    "Bleach": [
        ("{aspect} Spiritual Affinity", "an unusual quality in the Soul Reaper's Reiryoku that has not yet become a Zanpakuto release",
         "lets the wielder sense and shape narrow {aspect_lower}-aligned patterns through ordinary academy techniques",
         "it is not Shikai, grants no release state, and becomes unstable when forced beyond current Reiatsu Control",
         "refine control, record how it answers real choices, and let it inform the Zanpakuto spirit if Shikai is earned"),
    ],
    "Custom World": [
        ("{aspect} Gift", "a setting-consistent talent that first surfaced under pressure",
         "creates a flexible {aspect_lower}-themed effect within the established rules of the custom world",
         "begins narrow in scope and cannot bypass costs, counters, or prerequisites established by the setting",
         "practice its core use, discover its source, and earn broader applications through play"),
    ],
}


def _start_skill(name, description, rank="Trained", bonus=5):
    return {name: {"rank": rank, "bonus": bonus, "description": description}}


# Mechanical start packages.  These are intentionally data, not prose hidden
# in the opening prompt: choosing an established rank or profession must alter
# the saved campaign before the first model call is ever made.
WORLD_ORIGIN_START_PACKAGES = {
    "One Piece": {
        "Marine Recruit": {
            "position": "Marine Recruit", "title": "Marine Recruit",
            "affiliations": [{"faction": "Marines", "rank": "Recruit", "status": "active", "joined": "Campaign start", "notes": "Assigned to a local Marine branch."}],
            "reputation": {"Marines": 15, "Pirates": -5},
            "special_patch": {"Crew": "Marines"},
            "equipment": {"Weapon": "Marine-issue Flintlock and Cutlass"},
            "skills": _start_skill("Marine Recruit Training", "Uses Marine drills, lawful arrest procedure, formation movement, and basic shipboard discipline."),
        },
        "Veteran Crew Member": {
            "position": "Veteran Crewmate", "title": "Veteran Crewmate",
            "stat_minimums": {"Endurance": 30, "Agility": 26, "Willpower": 28},
            "skills": _start_skill("Grand Line Seamanship", "Handles violent weather, damage control, watches, and coordinated shipboard emergencies.", "Veteran", 7),
        },
        "Notorious Bounty-Head": {
            "position": "Wanted Outlaw", "title": "Notorious Bounty-Head",
            "stat_minimums": {"Strength": 32, "Agility": 32, "Willpower": 34},
            "special_patch": {"Bounty": 30000000}, "reputation": {"Marines": -35, "Pirates": 15},
            "skills": _start_skill("Wanted Survivor", "Recognizes pursuit patterns, conceals a trail, and survives clashes with bounty hunters and Marine patrols.", "Notorious", 8),
        },
    },
    "Hunter x Hunter": {
        "Licensed Hunter": {
            "position": "Licensed Hunter", "title": "Licensed Hunter",
            "affiliations": [{"faction": "Hunter Association", "rank": "Licensed Hunter", "status": "active", "joined": "Before campaign start", "notes": "Holds a valid Hunter License."}],
            "reputation": {"Hunter Association": 25}, "special_patch": {"Hunter License": "Active"},
            "equipment": {"Weapon": "Hunter License and Field Kit"},
            "skills": _start_skill("Professional Hunter Access", "Uses Hunter-only information channels, restricted facilities, contracts, and legal privileges without guaranteeing cooperation.", "Licensed", 7),
        },
        "Veteran Hunter": {
            "position": "Veteran Licensed Hunter", "title": "Veteran Hunter",
            "affiliations": [{"faction": "Hunter Association", "rank": "Veteran Hunter", "status": "active", "joined": "Before campaign start", "notes": "An experienced professional with a valid Hunter License."}],
            "reputation": {"Hunter Association": 45}, "special_patch": {"Hunter License": "Active", "Ten": 25, "Zetsu": 20, "Ren": 20},
            "stat_minimums": {"Aura Control": 28, "Cunning": 30, "Willpower": 30},
            "skills": _start_skill("Practical Nen Foundations", "Maintains Ten, enters Zetsu, produces Ren, and uses Gyo at a professionally trained but non-master level.", "Proficient", 8),
        },
    },
    "Naruto": {
        "Academy Graduate": {"position": "Genin", "title": "Genin", "special_patch": {"Shinobi Rank": "Genin"},
            "skills": _start_skill("Genin Field Readiness", "Performs academy techniques, uses standard tools, follows mission protocol, and works in a three-person team.")},
        "Uchiha Clan Child": {"title": "Uchiha Clan Child", "special_patch": {"Clan": "Uchiha", "Shinobi Rank": "Academy Student"},
            "skills": _start_skill("Uchiha Foundations", "Practices the clan's fire-style preparation, shuriken discipline, and dōjutsu theory; a Sharingan is not assumed unless the background says it awakened.")},
        "Iron Country Samurai-in-Training": {"position": "Samurai Apprentice", "title": "Iron Country Samurai Apprentice", "special_patch": {"Shinobi Rank": "Samurai Apprentice"},
            "affiliations": [{"faction": "Iron Country", "rank": "Samurai Apprentice", "status": "active", "joined": "Campaign start", "notes": "Training under the Land of Iron's samurai tradition."}],
            "equipment": {"Weapon": "Iron Country Katana"}, "skills": _start_skill("Samurai Sword Discipline", "Uses disciplined kenjutsu, armor movement, and chakra flow through a blade at an apprentice level.")},
        "Rogue Ninja (Missing-nin)": {"position": "Missing-nin", "title": "Missing-nin", "special_patch": {"Shinobi Rank": "Missing-nin"},
            "reputation": {"Konohagakure": -25}, "skills": _start_skill("Missing-nin Tradecraft", "Avoids village patrols, masks routes, recognizes hunter-nin procedure, and maintains equipment without official support.", "Experienced", 7)},
        "Anbu Root Recruit": {"position": "Root Recruit", "title": "Root Recruit", "special_patch": {"Shinobi Rank": "Root Recruit"},
            "affiliations": [{"faction": "Konohagakure", "rank": "Root Recruit", "status": "active", "joined": "Campaign start", "notes": "A covert recruit under Root discipline."}],
            "stat_minimums": {"Taijutsu": 28, "Ninjutsu": 28, "Chakra Control": 28},
            "skills": _start_skill("Root Conditioning", "Uses covert movement, coded orders, emotional control, and capture-or-eliminate procedure.", "Conditioned", 7)},
        "Chunin on Active Duty": {"position": "Chunin", "title": "Chunin", "special_patch": {"Shinobi Rank": "Chunin"},
            "stat_minimums": {"Taijutsu": 30, "Ninjutsu": 30, "Chakra Control": 30, "Intellect": 28},
            "skills": _start_skill("Chunin Mission Command", "Leads small teams, assesses mission risk, writes reports, and applies trained shinobi fundamentals under pressure.", "Proficient", 7)},
        "Jonin Squad Leader": {"position": "Jonin Squad Leader", "title": "Jonin Squad Leader", "special_patch": {"Shinobi Rank": "Jonin"},
            "stat_minimums": {"Taijutsu": 48, "Ninjutsu": 48, "Chakra Control": 45, "Willpower": 42, "Intellect": 42},
            "skills": _start_skill("Jonin Field Command", "Leads mission teams, adapts tactics under lethal pressure, teaches juniors, and applies broad shinobi experience.", "Jonin", 10)},
    },
    "Solo Max-Level Newbie": {
        "Elite Ranker": {"position": "Former Tower of Trials Elite Ranker", "title": "Elite Ranker",
            "stat_minimums": {"Intelligence": 32, "Wisdom": 32, "Luck": 28},
            "special_patch": {"Pre-Tower Game Rank": "Elite", "Hidden Conditions Found": 0},
            "skills": _start_skill("Tower Route Knowledge", "Remembers boss patterns, alternate routes, item interactions, and hidden-condition clues from the game; reality can still diverge.", "Master Game Knowledge", 10)},
        "Veteran Gamer": {"special_patch": {"Pre-Tower Game Rank": "Veteran"},
            "skills": _start_skill("Tower Systems Knowledge", "Understands the former game's interfaces, common encounters, and progression routes, while accepting that lethal reality may differ.", "Veteran", 7)},
    },
    "Overgeared": {
        "Guild Recruit": {"position": "New Guild Member",
            "skills": _start_skill("Party Coordination", "Uses party roles, aggro awareness, cooldown calls, and guild communication during ordinary Satisfy encounters.")},
        "Magic Academy Student": {"position": "Novice Magic Student",
            "skills": _start_skill("Satisfy Spellcasting", "Uses beginner spell activation, targeting, mana control, and interruption awareness without implying advanced magic.")},
        "Temple Initiate": {"position": "Temple Initiate",
            "skills": _start_skill("Temple Support Rites", "Uses beginner healing and support prayers, triage, party positioning, and the faith obligations attached to the class.")},
        "Beast Tamer": {"position": "Novice Beast Tamer",
            "skills": _start_skill("Companion Handling", "Reads ordinary monster behavior, cares for a willing companion, and issues simple commands under pressure.")},
        "Crafter": {"position": "Production Player", "special_patch": {"Class": "Crafter", "Crafting Mastery": 18},
            "skills": _start_skill("Production Fundamentals", "Uses Satisfy's production interfaces, material grades, recipes, and quality feedback to make reliable beginner items.")},
        "Blacksmith Apprentice": {"position": "Blacksmith Apprentice", "special_patch": {"Class": "Blacksmith", "Crafting Mastery": 25},
            "skills": _start_skill("Blacksmithing Apprenticeship", "Forges and repairs common equipment with measured heat, material selection, and Satisfy's production timing.", "Apprentice", 6)},
        "Veteran Adventurer": {"position": "Veteran Player", "special_patch": {"Class": "Veteran Adventurer"},
            "stat_minimums": {"Strength": 28, "Dexterity": 28, "Constitution": 28},
            "skills": _start_skill("Veteran Satisfy Combat", "Uses aggro, cooldowns, party roles, equipment swaps, and dungeon awareness developed through extensive play.", "Veteran", 8)},
        "Renowned Craftsman": {"position": "Renowned Craftsman", "title": "Renowned Craftsman", "special_patch": {"Class": "Master Craftsman", "Crafting Mastery": 65},
            "stat_minimums": {"Strength": 35, "Constitution": 35, "Intelligence": 40, "Wisdom": 36},
            "skills": _start_skill("Renowned Production Mastery", "Designs advanced items, evaluates rare materials, manages complex production steps, and consistently reaches high item ratings.", "Master", 11)},
    },
    "Reincarnated as a Slime": {
        "Reincarnated Otherworlder": {"title": "Reincarnated Otherworlder", "special_patch": {"Evolution Stage": "Newly Reincarnated"}},
        "Veteran Tempest Officer": {"position": "Tempest Officer", "title": "Veteran Tempest Officer", "race": "Hobgoblin",
            "affiliations": [{"faction": "Jura Forest Monsters", "rank": "Tempest Officer", "status": "active", "joined": "Before campaign start", "notes": "Serves the established nation of Tempest."}],
            "reputation": {"Jura Forest Monsters": 55}, "special_patch": {"Species": "Hobgoblin", "Evolution Stage": "Named and Evolved", "Magicule Capacity": 40},
            "stat_minimums": {"Magicule Control": 36, "Skill Mastery": 38, "Willpower": 40, "Presence": 36},
            "skills": _start_skill("Tempest Officer Command", "Coordinates mixed-species teams, follows Tempest law, manages patrols, and responds to diplomatic or military incidents.", "Veteran", 9),
            "required_era": "tempest_established", "required_start_day": 100, "recommended_location": "Tempest"},
        "Named Monster of Renown": {"position": "Named Monster", "title": "Named Monster of Renown",
            "special_patch": {"Evolution Stage": "Named and Evolved", "Magicule Capacity": 55},
            "stat_minimums": {"Magicule Control": 42, "Skill Mastery": 42, "Instinct": 40, "Willpower": 42},
            "skills": _start_skill("Named Monster Authority", "Combines an evolved body, strengthened magicule circulation, and earned presence among Jura's monsters.", "Renowned", 10)},
    },
    "Bleach": {
        "Shin'o Academy Senior": {
            "position": "Final-year Shin'o Academy Student", "title": "Shin'o Academy Senior",
            "affiliations": [{"faction": "Gotei 13", "rank": "Academy Candidate", "status": "training", "joined": "Before campaign start", "notes": "Eligible for graduation and division placement after completing academy requirements."}],
            "reputation": {"Gotei 13": 10, "Kido Corps": 5},
            "special_patch": {"Spiritual Nature": "Soul Reaper", "Shinigami Rank": "Academy Senior", "Zanpakuto": "Unnamed Asauchi", "Shikai": "Unachieved", "Bankai": "Unachieved", "Squad": "Unassigned"},
            "equipment": {"Weapon": "Unnamed Asauchi", "Uniform": "Shin'o Academy senior uniform", "Field Gear": "Soul pager, academy handbook and basic spirit medicine"},
            "stat_minimums": {"Zanjutsu": 32, "Hakuda": 30, "Hoho": 30, "Kido": 28, "Reiatsu Control": 32, "Willpower": 30},
            "skills": _start_skill("Shin'o Academy Senior Curriculum", "Uses the four Shinigami arts, Konso procedure, Hollow identification, patrol protocol and supervised field methods at graduation-candidate level.", "Academy Senior", 6),
            "quests": [{"name":"Graduate and Choose a Division","status":"Active","category":"main","giver":"Shin'o Academy","locations":["Shin'o Academy","Gotei 13 Barracks"],"explanation":"Complete the remaining academy evaluation, then meet division representatives and influence the first squad assignment.","objectives":["Complete the final graduation evaluation","Learn what several divisions expect","State a preferred squad and make a case for placement","Accept, negotiate or challenge the resulting assignment"],"clear_conditions":["Graduate from Shin'o Academy","Receive or choose a squad assignment"],"next_hint":"Review the final evaluation and ask which divisions are actively recruiting."}],
        },
        "Recent Shin'o Academy Graduate": {
            "position": "Unseated Soul Reaper awaiting assignment", "title": "Recent Shin'o Academy Graduate",
            "affiliations": [{"faction": "Gotei 13", "rank": "Unseated Graduate", "status": "awaiting assignment", "joined": "Campaign start", "notes": "Graduated but not yet assigned to a division."}],
            "reputation": {"Gotei 13": 15, "Kido Corps": 5},
            "special_patch": {"Spiritual Nature": "Soul Reaper", "Shinigami Rank": "Unseated Graduate", "Zanpakuto": "Unnamed Asauchi", "Shikai": "Unachieved", "Bankai": "Unachieved", "Squad": "Unassigned"},
            "equipment": {"Weapon": "Unnamed Asauchi", "Uniform": "Newly issued black shihakusho", "Field Gear": "Soul pager, mission satchel and basic spirit medicine"},
            "stat_minimums": {"Zanjutsu": 34, "Hakuda": 31, "Hoho": 31, "Kido": 29, "Reiatsu Control": 34, "Willpower": 32},
            "skills": _start_skill("Soul Reaper Field Readiness", "Performs Konso, recognizes common Hollows, uses academy combat methods, follows mission protocol and can operate under a seated officer's direction.", "Graduate", 6),
            "quests": [{"name":"Choose a Gotei 13 Division","status":"Active","category":"main","giver":"Gotei 13 Placement Office","locations":["Seireitei","Gotei 13 Barracks"],"explanation":"Division representatives are evaluating new graduates. The player can express preferences, seek interviews and use demonstrated talent to earn a real choice.","objectives":["Investigate suitable divisions","Meet or petition division representatives","State a preferred squad","Secure or accept a first assignment"],"clear_conditions":["A division records the character as an active member"],"next_hint":"Attend placement proceedings or request an interview with a preferred division."}],
        },
    },
}

WORLD_LOCATION_START_PACKAGES = {
    ("One Piece", "Shells Town"): {"special_patch": {"Home Sea": "East Blue"}},
    ("Hunter x Hunter", "Hunter Exam Site"): {"special_patch": {"Hunter Exam Status": "Applicant"},
        "quests": [{"name": "Pass the Hunter Exam", "status": "Active", "giver": "Hunter Association", "locations": ["Hunter Exam Site"],
                    "objectives": ["Complete the current exam phase", "Qualify in the final phase"], "next_hint": "Report to the examiner and learn the current phase's rules."}]},
    ("Naruto", "Amegakure"): {"special_patch": {"Home Village": "Amegakure"}},
    ("Naruto", "Iron Country"): {"special_patch": {"Home Village": "Iron Country"}},
    ("Bleach", "Shin'o Academy"): {"special_patch": {"Spiritual Nature": "Soul Reaper", "Shinigami Rank": "Academy Senior", "Squad": "Unassigned"}},
    ("Bleach", "Seireitei"): {"special_patch": {"Spiritual Nature": "Soul Reaper", "Shinigami Rank": "Unseated Graduate", "Squad": "Unassigned"}},
    ("Solo Max-Level Newbie", "Floor 5"): {"position": "Experienced Early Climber", "level": 8,
        "stat_minimums": {"Strength": 38, "Dexterity": 38, "Constitution": 36, "Intelligence": 36, "Wisdom": 34, "Luck": 30},
        "special_patch": {"Floor": 5, "System Status": "Active Player"}},
    ("Solo Max-Level Newbie", "Floor 10"): {"position": "Advanced Early Climber", "level": 16,
        "stat_minimums": {"Strength": 52, "Dexterity": 52, "Constitution": 48, "Intelligence": 48, "Wisdom": 44, "Luck": 36},
        "special_patch": {"Floor": 10, "System Status": "Active Player"}},
}

# Major groups can be known without being magically reachable. Membership
# packages and seeded NPCs can still unlock the appropriate channel.
WORLD_PUBLIC_CONTACTS = {
    "One Piece": {"Marines", "World Government", "Revolutionary Army"},
    "Hunter x Hunter": {"Hunter Association"},
    "Naruto": {"Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure", "Iwagakure", "Amegakure", "Iron Country"},
    "Solo Max-Level Newbie": {"Players", "Major Guilds"},
    "Overgeared": {"Players", "Local Lords", "Church", "Guilds", "Kingdom"},
    "Reincarnated as a Slime": {"Jura Forest Monsters", "Free Guild"},
    "Bleach": {"Gotei 13", "Kido Corps", "Noble Houses"},
    "Jujutsu Kaisen": {"Tokyo Jujutsu High", "Kyoto Jujutsu High", "Jujutsu Headquarters"},
    "Custom World": {"Local Faction"},
}

# When a player names the theme of a hidden class, preserve that theme instead
# of choosing an unrelated stock class.  The stock forms remain useful for a
# deliberately vague request ("I have a hidden class"), while this form turns a
# concrete request into a setting-native mechanical package.
WORLD_EXPLICIT_HIDDEN_CLASS_FORMS = {
    "Naruto": ("{aspect} Fold Adept", "Secret Shinobi Path",
        "A concealed chakra discipline that develops {aspect_lower}-aligned formulae through precise control and shinobi fieldcraft.",
        "The user can produce a brief, tightly bounded {aspect_lower}-aligned effect through a prepared mark or focused chakra technique.",
        "Range, mass, preparation time, chakra cost, and disrupted concentration sharply limit every use; it cannot bypass seals or defenses stronger than the user can overcome.",
        "Study fuinjutsu and chakra theory, test safe anchors, and earn longer-range or combat-ready applications through training.", "{aspect} Fold"),
    "One Piece": ("{aspect} Wake Disciple", "Hidden Fighting Path",
        "An unusual seafaring combat path that expresses a natural affinity for {aspect_lower}-themed motion and force.",
        "The user can shape movement, tools, and close-range attacks around a narrow {aspect_lower}-themed technique.",
        "It remains physical, costs stamina, and cannot imitate a Devil Fruit or Haki ability the user has not actually acquired.",
        "Condition the body, refine the style at sea, and later combine it with earned Haki or equipment.", "{aspect} Wake"),
    "Hunter x Hunter": ("{aspect} Vow Specialist", "Hidden Nen Path",
        "A rare Nen inclination whose future Hatsu naturally organizes itself around {aspect_lower}-themed rules.",
        "The user can form one narrow {aspect_lower}-themed aura effect whose strength grows with honest restrictions.",
        "Before Nen is awakened it appears only as instinct, and every declared condition carries a proportional consequence.",
        "Learn the four major principles, define enforceable restrictions, and develop the personal Hatsu through use.", "{aspect} Vow"),
    "Solo Max-Level Newbie": ("{aspect} Routebreaker", "Hidden Class",
        "A System-recognized class built around unusual {aspect_lower}-aligned clear conditions.",
        "The class reveals limited clues and improves compatible actions when the player genuinely pursues a {aspect_lower}-aligned alternate route.",
        "Clues are incomplete, rewards still require the real condition, and unsuitable stages provide no advantage.",
        "Clear hidden conditions, earn related achievements, and survive increasingly strict class trials.", "{aspect} Route Sense"),
    "Overgeared": ("{aspect} Pathkeeper", "Hidden Growth Class",
        "A Satisfy class that converts the character's stated {aspect_lower}-aligned identity into a coherent personal playstyle rather than assuming a production role.",
        "The class grants one narrow {aspect_lower}-aligned feature appropriate to the background's combat, magic, support, command, summoning, exploration, social, or production focus.",
        "Its effects still require appropriate stats, resources, cooldowns, conditions, and class-compatible actions; early access is not mastery.",
        "Complete class trials, achieve meaningful feats in the chosen role, and select a specialization shaped by actual play.", "{aspect} Calling"),
    "Reincarnated as a Slime": ("{aspect} Skill Weaver", "Unique Evolution Path",
        "An unusual evolutionary path that recognizes compatible {aspect_lower}-aligned fragments in learned and intrinsic skills.",
        "The user can gradually synthesize closely related fragments into one efficient {aspect_lower}-themed technique.",
        "Incompatible concepts resist synthesis, failures waste magicules, and major upgrades still require real evolutionary conditions.",
        "Analyze compatible abilities, increase magicule capacity, and evolve the technique through naming or crisis.", "{aspect} Weaving"),
    "Bleach": ("{aspect} Resonance Adept", "Secret Shinigami Path",
        "A rare spiritual path whose Zanpakuto relationship first manifests through {aspect_lower}-themed resonance.",
        "The wielder can align a basic technique with a narrow {aspect_lower}-themed response from the blade spirit.",
        "This is not a true name or release; forcing it destabilizes Reiryoku and can silence the spirit.",
        "Practice Jinzen, deepen mutual recognition, and earn any release through the Zanpakuto's actual trial.", "{aspect} Resonance"),
    "Custom World": ("{aspect} Wayfarer", "Hidden Class",
        "A concealed path shaped by a rare affinity for {aspect_lower}-aligned phenomena in this setting.",
        "The class improves control and improvisation when an action genuinely uses that affinity.",
        "It cannot ignore the world's established costs, counters, prerequisites, or scale.",
        "Find a knowledgeable mentor, test the affinity under pressure, and complete a defining class trial.", "{aspect} Attunement"),
}

# Original characters can very rarely begin with an extra world-valid gift or
# hidden class even when the background did not ask for one. Explicit requests
# always win. These are intentionally uncommon enough to feel special without
# turning every new campaign into a reroll hunt.
RANDOM_STARTING_ABILITY_CHANCE = 0.08
RANDOM_HIDDEN_CLASS_CHANCE = 0.04
GENERIC_COMPETENCY_NAME = re.compile(
    r"\b(fundamentals?|field readiness|conditioning|tradecraft|mission command|field command|"
    r"combat style|background expertise|system adaptation|professional access|senior curriculum)\b", re.I
)

# A mechanical fallback for original powers when an offline/model candidate
# matches something already in the permanent archive.  These are ingredients,
# not completed abilities: subject + operation + activation condition produces
# a new governing rule, applications, counterplay, and progression package.
WORLD_ORIGINAL_SUBJECTS = {
    "Naruto": (
        ("Sealspace", "chakra crossing prepared seals and formula boundaries"),
        ("Pulse", "the rhythm and pressure of chakra moving through living pathways"),
        ("Glasswind", "refracted light carried through wind-nature chakra"),
        ("Ironroot", "mineral traces and magnetic force touched by the user's chakra"),
        ("Afterflow", "residual chakra left behind by completed techniques"),
        ("Nerve", "the user's own sensory and motor signals reinforced with chakra"),
    ),
    "One Piece": (
        ("Tether", "tension stored in touched ropes, cloth, and flexible objects"),
        ("Chime", "vibration traveling through solid objects and the air around them"),
        ("Mosaic", "breakable surfaces divided into controllable fitted pieces"),
        ("Drift", "buoyancy and directional pull acting on touched matter"),
        ("Quill", "written marks made by the user's hands or tools"),
        ("Velvet", "surface softness, drag, and impact absorption"),
    ),
    "Hunter x Hunter": (
        ("Compass", "aura assigned to direction and chosen destinations"),
        ("Witness", "aura records of actions the user directly observes"),
        ("Lantern", "aura invested in revealing or concealing a declared target"),
        ("Thread", "aura links created through voluntary promises and physical contact"),
        ("Measure", "aura quantities the user has personally measured with Gyo"),
        ("Orbit", "emitted aura anchored around selected people or objects"),
    ),
    "Solo Max-Level Newbie": (
        ("Route", "Tower routes, room conditions, and verified alternate clears"),
        ("Threshold", "System thresholds the player has personally approached or crossed"),
        ("Echo", "recorded patterns from survived enemy skills"),
        ("Key", "recognized locks, permissions, and hidden-stage conditions"),
        ("Debt", "deferred costs accepted through explicit System conditions"),
        ("Index", "confirmed information entered into the player's System record"),
    ),
    "Overgeared": (
        ("Oath", "voluntary party agreements recognized by Satisfy's System"),
        ("Relic", "traits earned by one bonded piece of equipment"),
        ("Formation", "positions and roles maintained by willing party members"),
        ("Questline", "hidden conditions proven through the player's actual choices"),
        ("Counter", "patterns learned by surviving and studying named techniques"),
        ("Domain", "territory, guild assets, and authority genuinely controlled by the player"),
    ),
    "Reincarnated as a Slime": (
        ("Magicule", "compatible magicule patterns circulating through the user's body"),
        ("Analysis", "properties the user has successfully observed and analyzed"),
        ("Name", "authority and identity carried by names and recognized bonds"),
        ("Synthesis", "compatible fragments of learned and intrinsic skills"),
        ("Predation", "traits safely processed from absorbed material or defeated threats"),
        ("Territory", "magicule conditions maintained inside a claimed local area"),
    ),
    "Bleach": (
        ("Reishi", "reishi currents cut or marked by the Zanpakuto"),
        ("Echo", "spiritual rhythms carried through blades, ground, and nearby souls"),
        ("Shadow", "shadows cast by spiritually aware beings and constructs"),
        ("Vow", "intent spoken honestly by wielder and blade spirit"),
        ("Scar", "spiritual pressure left at the site of a blocked or survived attack"),
        ("Path", "short routes traced by the Zanpakuto through surrounding reishi"),
    ),
    "Jujutsu Kaisen": (
        ("Mark", "cursed marks placed through contact and acknowledged conditions"),
        ("Interval", "distance and timing between two cursed-energy events"),
        ("Witness", "cursed records of actions directly observed by the user"),
        ("Vector", "direction and momentum carried by cursed energy"),
        ("Measure", "quantities measured inside the user's cursed-energy field"),
        ("Reflection", "complete reflections containing a target's cursed signature"),
    ),
    "Custom World": (
        ("Threshold", "one measurable property established by the campaign's rules"),
        ("Witness", "events the character directly observes and understands"),
        ("Bond", "voluntary connections established between people or objects"),
        ("Echo", "residual energy left by completed actions"),
        ("Measure", "quantities the character can genuinely sense or measure"),
        ("Path", "routes and boundaries the character has personally prepared"),
    ),
}

ORIGINAL_MECHANICAL_OPERATIONS = (
    ("Ledger", "records one valid instance of {subject}, then spends that record to repeat or redirect the same behavior once"),
    ("Partition", "divides {subject} between two marks so one compatible change can be transferred from one mark to the other"),
    ("Countercurrent", "inverts the next compatible change in {subject} without creating an unrelated effect"),
    ("Relay", "moves one active effect involving {subject} from a prepared target to another prepared target"),
    ("Accrual", "accumulates small valid changes in {subject}, then releases the total through one amplified expression of that same property"),
    ("Narrowing", "compresses an existing amount of {subject} into a smaller area, increasing intensity while sacrificing coverage"),
    ("Covenant", "binds {subject} to one declared behavior and triggers a proportional consequence when a marked target breaks it"),
    ("Afterclock", "delays one change in {subject}, preserving its original strength and direction until release"),
    ("Exchange", "trades equal measured amounts of {subject} between two valid prepared targets"),
    ("Calibration", "stores a measured amount of {subject} as a temporary standard, then reinforces or suppresses only the difference from that standard"),
)

ORIGINAL_ACTIVATION_CONDITIONS = (
    ("Marked", "after the user personally marks the target and maintains awareness of it"),
    ("Witnessed", "after the user directly witnesses the complete triggering action"),
    ("Declared", "after the user states a narrow condition that every affected target can hear"),
    ("Reciprocal", "only after the user accepts the same initial effect or cost"),
    ("Measured", "after an uninterrupted observation establishes a real baseline"),
    ("Crossed", "when a prepared boundary is knowingly crossed"),
    ("Repeated", "after the same compatible action occurs twice in the user's presence"),
    ("Withheld", "only while the user gives up an immediate counterattack or equivalent advantage"),
)

# A hidden class is a real mechanical package, not a decorative title. Each
# form supplies a setting-native identity and a signature technique; the
# character's actual primary stats determine which attributes receive its
# starting bonuses, so a class complements the chosen archetype instead of
# replacing it with a one-size-fits-all stat block.
WORLD_HIDDEN_CLASS_FORMS = {
    "Naruto": [
        ("Veiled Sealbearer", "Secret Shinobi Path",
         "A rare discipline that treats seals as a second chakra network woven through tools, terrain, and the user's own body.",
         "Prepared marks can store a small technique, redirect chakra, or trigger a compact barrier.",
         "Every mark needs time, chakra, and exact placement; rushed arrays can collapse or rebound.",
         "Study fuinjutsu, improve chakra control, and earn access to more complex formulae.", "Sealweaving"),
        ("Echo-Nerve Operative", "Secret Shinobi Path",
         "An obscure sensory-combat discipline built around reading tiny changes in breath, balance, and chakra flow.",
         "The user can anticipate a committed motion and answer it with unusually precise timing.",
         "Crowds, sensory overload, unfamiliar anatomy, and suppressed chakra produce misleading signals.",
         "Train against varied opponents and develop a formal sensory technique.", "Echo-Nerve Read"),
    ],
    "One Piece": [
        ("Stormwake Vanguard", "Hidden Fighting Path",
         "A nearly forgotten seafarer's discipline built around violent changes in footing, weather, and momentum.",
         "The user turns unstable terrain and sudden motion into force for movement, defense, and close combat.",
         "It loses much of its edge on predictable ground and rapidly drains an unconditioned body.",
         "Sail dangerous waters, strengthen the body, and eventually harmonize the style with Haki.", "Stormwake Step"),
    ],
    "Hunter x Hunter": [
        ("Unwritten Specialist", "Hidden Nen Path",
         "A rare talent whose future Hatsu forms around self-imposed rules rather than a standard combat school.",
         "Carefully stated conditions can make one narrow application far stronger than its raw aura should allow.",
         "The effect remains modest until Nen is properly awakened, and breaking a declared condition carries real consequences.",
         "Learn the four major principles, test restrictions honestly, and define a personal Hatsu.", "Unwritten Condition"),
    ],
    "Solo Max-Level Newbie": [
        ("Condition Breaker", "Hidden Class",
         "A System-recognized class that notices alternate completion conditions and unstable rule interactions.",
         "The class reveals a clue when the player is close to satisfying a hidden route or bypassing a conventional solution.",
         "Clues are incomplete and the class grants no reward unless the actual condition is fulfilled.",
         "Clear hidden conditions, earn unusual achievements, and survive floors above the expected route.", "Condition Sense"),
    ],
    "Overgeared": [
        ("Echo Vanguard", "Hidden Combat Growth Class",
         "A frontline class that records how the player survives powerful techniques and develops deliberate counters through later victories.",
         "After enduring and understanding a hostile technique, the class can prepare one limited defensive response against its underlying pattern.",
         "It cannot copy the technique, grants no immunity, and loses efficiency against altered or overwhelmingly stronger versions.",
         "Survive named opponents, prove each counter in battle, and choose between guardian, duelist, or raid-vanguard advancement.", "Recorded Counter"),
        ("Constellation Shepherd", "Hidden Companion Class",
         "A command-and-summoning class that develops contracted companions as a coordinated party instead of disposable pets.",
         "The player can designate simple complementary roles and share a narrow tactical signal with one willing companion.",
         "Contracts require consent or a valid System condition, divided attention limits commands, and companion death has lasting consequences.",
         "Form genuine contracts, clear encounters through coordination, and unlock formation or mounted specializations.", "Guiding Formation"),
        ("Threshold Magus", "Hidden Magic Growth Class",
         "A spell class that gains depth by solving encounters with carefully altered range, timing, and activation conditions.",
         "The class can modify one modest parameter of a mastered spell after declaring a meaningful constraint.",
         "It cannot alter an unmastered spell, remove its resource cost, or change several parameters at once.",
         "Master varied spells, clear constraint-based class quests, and specialize in territory, ritual, or battle magic.", "Conditional Casting"),
        ("Oathbound Mediator", "Hidden Support / Social Class",
         "A support class whose declared agreements become visible System objectives for willing participants.",
         "A mutually accepted promise grants a small coordination benefit while every party actively honors its terms.",
         "It cannot compel consent or loyalty, and betrayal immediately ends the benefit while creating reputational consequences.",
         "Resolve disputes, keep difficult bargains, and advance toward diplomatic, guild, or battlefield-command paths.", "Shared Terms"),
        ("Relicbound Artificer", "Hidden Production-Combat Class",
         "A production-combat class that forms a lasting bond with one evolving piece of equipment.",
         "Successful use and careful maintenance let the bonded item accumulate traits that ordinary equipment would lose.",
         "Only one item can be bonded at first, and its growth still requires materials, skill, and compatible achievements.",
         "Raise production mastery, repair the bonded relic, and complete class-specific crafting quests.", "Relic Bond"),
    ],
    "Reincarnated as a Slime": [
        ("Adaptive Skill Weaver", "Unique Evolution Path",
         "An unusual evolutionary path that recognizes compatible fragments within learned and intrinsic skills.",
         "The user can gradually combine closely related effects into a more efficient personal technique.",
         "Incompatible concepts resist synthesis, and failed combinations waste magicules without creating a skill.",
         "Analyze more abilities, expand magicule capacity, and evolve through a genuine naming or crisis trigger.", "Skill Weaving"),
    ],
    "Bleach": [
        ("Veiled Zanpakuto Adept", "Secret Shinigami Path",
         "A rare path centered on unusually early communication with the spirit sleeping inside a Zanpakuto.",
         "The wielder can sense fragments of the blade spirit's intent and align basic techniques with it.",
         "Fragments are not a true name or release; forcing the bond can silence the spirit and destabilize Reiryoku.",
         "Deepen Jinzen meditation, learn the spirit's identity, and earn Shikai through mutual recognition.", "Zanpakuto Resonance"),
    ],
    "Custom World": [
        ("{aspect} Wayfarer", "Hidden Class",
         "A concealed path shaped by a rare affinity for {aspect_lower}-aligned phenomena in this setting.",
         "The class improves control and improvisation when an action genuinely uses that affinity.",
         "It cannot ignore the world's established costs, counters, prerequisites, or scale.",
         "Find a knowledgeable mentor, test the affinity under pressure, and complete a defining class trial.", "{aspect} Attunement"),
    ],
}

WORLD_BACKGROUND_COLOR = {
    # Each world gets several (mentor descriptor, formative event) pairs
    # instead of one fixed pair always used verbatim — with only one option,
    # every character in a world shared the exact same origin story.
    "Naruto": (
        ("a retired local shinobi", "a mission-era accident exposed the cost of acting without preparation"),
        ("a strict academy proctor", "a failed graduation attempt taught the difference between talent and discipline"),
        ("an aging weapons specialist", "a border skirmish forced a choice between running and standing with the unit"),
        ("a clan elder outside the main line", "a sealed technique misfired and revealed a hidden family debt"),
    ),
    "One Piece": (
        ("a weathered island veteran", "a pirate raid forced the community to rely on anyone willing to stand up"),
        ("a retired Marine turned innkeeper", "a Marine inspection exposed corruption no one else would name"),
        ("an old ship's navigator", "a storm at sea cost the crew someone the whole village still remembers"),
        ("a former bounty hunter", "a bounty gone wrong left a debt that could only be repaid at sea"),
    ),
    "Hunter x Hunter": (
        ("a traveling specialist", "an encounter with a far stronger stranger revealed how large the world really was"),
        ("a retired Hunter-exam veteran", "a failed exam attempt exposed exactly how much further real strength went"),
        ("a reclusive Nen instructor", "an unexplained ability surfaced under pressure with no one able to explain it"),
        ("a guild-affiliated tracker", "a job gone wrong left a debt only a Hunter's license could realistically repay"),
    ),
    "Solo Max-Level Newbie": (
        ("an obsessive strategy partner", "years spent mastering impossible game scenarios turned obscure knowledge into instinct"),
        ("a burned-out pro gamer", "a tournament collapse taught how thin the gap between talent and preparation is"),
        ("an eccentric theorycrafter", "a game update no one else understood rewarded the one person who'd read every patch note"),
        ("a former guild officer", "a guild's collapse under bad leadership left a lasting distrust of easy promises"),
    ),
    "Overgeared": (
        ("a demanding workshop senior", "a costly failure made persistence more important than easy talent"),
        ("an unlicensed blacksmith", "a ruined commission taught the real price of cutting corners"),
        ("a jaded former guild crafter", "a stolen recipe exposed how little goodwill exists among top players"),
        ("a stubborn old adventurer", "a near-fatal dungeon run left a debt only steady, unglamorous work could repay"),
        ("a veteran raid leader", "a failed boss attempt taught that timing and trust matter more than damage charts"),
        ("an eccentric class researcher", "an overlooked quest choice revealed that Satisfy's class system rewards unusual conviction"),
        ("a village priest NPC", "protecting an unpopular resident opened a support route most players had ignored"),
        ("a retired arena champion", "a public defeat exposed the difference between a strong build and real tactical judgment"),
    ),
    "Reincarnated as a Slime": (
        ("an elder familiar with local monsters", "a territorial crisis revealed both the value and danger of unusual abilities"),
        ("a wary goblin elder", "a raid by a rival tribe forced an uneasy alliance no one fully trusted yet"),
        ("a wandering monster tamer", "a botched taming attempt showed how little separates a monster from a companion"),
        ("a cautious forest-dwelling sage", "a magic-born disaster proved the forest's peace was more fragile than it looked"),
    ),
    "Bleach": (
        ("an upper-year Shin'o Academy instructor", "a supervised Hollow exercise exposed the difference between classroom control and protecting another soul"),
        ("a patient Kido lecturer", "a failed incantation became the first clue that the student's Reiryoku did not behave like everyone else's"),
        ("a seated officer visiting the academy", "a field observation revealed which division duties actually matched the student's values"),
        ("an Asauchi caretaker", "a silent moment with the unnamed blade suggested that its sleeping spirit was already listening"),
    ),
    "Custom World": (
        ("a locally respected mentor", "a dangerous incident revealed that talent without understanding creates consequences"),
        ("a retired local specialist", "a close call in the field taught respect for what looked like routine work"),
        ("a demanding local elder", "a broken promise exposed a debt that still needed to be repaid"),
        ("a wandering former professional", "an old failure became the reason they never let a student make the same mistake"),
    ),
}

WORLD_BACKGROUND_NAMES = {
    "Naruto": ("Mika Sato", "Daichi Mori", "Ren Aburame", "Hana Inuzuka", "Kaede Yamashiro", "Isamu Nara",
               "Tsubaki Fuma", "Genzo Hatake", "Yui Kamizuki", "Botan Sarutobi", "Rei Uzuki", "Haru Tanaka"),
    "One Piece": ("Mara Venn", "Old Corin", "Tessa Flint", "Captain Dael", "Bellamy Cross", "Noa Sancroft",
                  "Grey Marlow", "Iris Cabrera", "Tomas Reyes", "Selka Vane", "Old Pell", "Marin Osgood"),
    "Hunter x Hunter": ("Ilya Rook", "Mina Vale", "Toren Ash", "Kessa Vail", "Doran Ferro", "Yuna Marsh",
                        "Cael Rennick", "Lior Densu", "Tamsin Cray", "Odell Vance", "Nira Kolt", "Bram Astley"),
    "Solo Max-Level Newbie": ("Seo Min-jae", "Han Yu-ri", "Park Do-jin", "Choi Hae-won", "Jung Si-woo", "Kang Nari",
                              "Oh Tae-yang", "Lim Su-bin", "Baek Jun-ho", "Yoon Ara", "Shin Dae-hyun", "Moon Ji-hu"),
    "Overgeared": ("Elian Voss", "Mira Anvil", "Garron Pell", "Kesta Ward", "Ordin Vale", "Sela Marrow",
                   "Bram Kessler", "Tovin Reed", "Anya Coldiron", "Fenric Bale", "Mira Duskwright", "Talon Grey"),
    "Reincarnated as a Slime": ("Rilsa", "Gelm", "Nemu", "Sorel", "Fadda", "Mireth", "Gobzo", "Ranith",
                                "Elmis", "Korgu", "Vessa", "Draska"),
    "Bleach": ("Akari Fujimoto", "Daigo Arakawa", "Emi Hoshina", "Haruto Senda", "Kaoru Mizuno", "Mio Tachibana",
               "Renjiro Kagawa", "Sachi Kurosawa", "Toma Igarashi", "Yuna Shibata", "Kei Naruse", "Natsumi Arai"),
    "Custom World": ("Ari Vale", "Mara Stone", "Toren Reed", "Elan Ashford", "Sena Cobb", "Rook Delaney",
                      "Ivy Marchetti", "Dashiell Kern", "Wren Castellan", "Marlow Finch", "Talia Voss", "Corin Blake"),
}

BACKGROUND_HOMES = (
    "A practical household taught them to contribute early, even when its members did not fully understand their ambitions.",
    "They were raised by a small circle of relatives and neighbors whose support came with duties they still feel responsible for.",
    "Their home life was modest and sometimes unstable, making preparation, loyalty, and self-reliance learned habits rather than slogans.",
    "They grew up in a household that valued quiet competence over recognition, and rarely praised anything less than results.",
    "A tight-knit but overextended family left them used to picking up responsibilities no one else had time for.",
    "They were raised mostly by example rather than instruction, learning more from watching than from being taught outright.",
)

OVERGEARED_ROLE_CONTEXT = {
    "Summoner": ("a small party that treated contracted creatures as partners", "a panicked summon ignored a careless order and saved a teammate another way"),
    "Beast Master": ("a monster-handling camp outside a starter city", "an injured beast responded to patience when force had already failed"),
    "Priest/Healer": ("a busy temple clinic serving adventurers and NPC residents alike", "a raid survivor lived because someone stayed behind to stabilize them"),
    "Support": ("a pickup party whose strongest damage dealers could not cooperate", "one well-timed enhancement turned a wipe into an organized retreat"),
    "Tactician": ("a low-ranked guild team repeatedly outmatched on paper", "a failed raid proved that a correct plan still needs trust and clear calls"),
    "Explorer": ("a mapping group that sold reliable routes instead of rumors", "an ignored environmental detail exposed a hidden path through a deadly area"),
    "Merchant/Orator": ("a player-run market where reputation mattered as much as Gold", "a profitable bargain collapsed when one side had no reason to honor it"),
    "Mage": ("a provincial magic guild with more theory than funding", "an unstable spell interaction rewarded careful observation instead of raw output"),
    "Magic Swordsman": ("a training hall skeptical of hybrid builds", "switching disciplines at the wrong moment cost an otherwise winnable duel"),
    "Tank": ("a beginner raid group that survived only when someone held the line", "a mistimed guard exposed every ally behind it"),
}



class CampaignMixin:
    def _special_exclusions(self, world, category):
        return self.generated_ability_archive.exclusions(world, category, limit=40)

    @staticmethod
    def special_name_is_placeholder(value):
        """Reject generator planning labels before they become fiction."""
        name = str(value or "").strip()
        if not name:
            return True
        return bool(re.search(
            r"\b(?:generated|placeholder|unnamed|unknown|tbd|to be determined)\b|"
            r"\b(?:hidden|secret|special|custom)\b.{0,35}\b(?:related|themed)\b.{0,20}\b(?:class|ability|power|skill)\b|"
            r"\b(?:class|ability|power|skill)\b.{0,35}\b(?:related|themed)\b",
            name, re.I,
        ))

    @staticmethod
    def background_locked_facts(world, background):
        """Extract player-authored creation facts that generation may expand
        but may never replace.  This intentionally favors a small set of
        high-confidence facts over guessing from every noun in the prompt."""
        raw = str(background or "").strip()
        if not raw:
            return {}
        facts = {}
        name_patterns = {
            "Bleach": (
                r"(?:named|called|calls?)\s+(?:my|his|her|their)?\s*zanpakut[ōo]\s+[\"'“”]?([A-Za-z][A-Za-z0-9' -]{1,38})",
                r"zanpakut[ōo](?:'s name)?\s+(?:is|is named|is called|named|called)\s+[\"'“”]?([A-Za-z][A-Za-z0-9' -]{1,38})",
                r"zanpakut[ōo]\s+[\"'“]([A-Za-z][A-Za-z0-9' -]{1,38})[\"'”]",
            ),
            "Jujutsu Kaisen": (
                r"(?:innate|cursed)\s+technique\s+(?:is\s+)?(?:named|called)\s+[\"'“”]?([A-Za-z][A-Za-z0-9' -]{1,48})",
                r"(?:named|called)\s+(?:my|his|her|their)?\s*(?:innate|cursed)\s+technique\s+[\"'“”]?([A-Za-z][A-Za-z0-9' -]{1,48})",
            ),
        }
        for pattern in name_patterns.get(world, ()):
            match = re.search(pattern, raw, re.I)
            if match:
                name = re.split(r"\b(?:that|which|and|but|with)\b|[,.;\n]", match.group(1), maxsplit=1, flags=re.I)[0]
                name = name.strip(" \t\r\n\"'“”")
                if name:
                    facts["ability_name"] = name
                    break
        lower = raw.lower()
        if world == "Jujutsu Kaisen" and "momentum" in lower and re.search(r"\b(stor|accumulat|bank|absorb|retain)\w*\b", lower):
            facts["central_mechanism"] = (
                "Stores momentum generated by the user's movement and impacts, then releases that accumulated force through chosen actions."
            )
        else:
            for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", raw):
                if re.search(r"\b(?:ability|power|technique|zanpakut[ōo]|devil fruit|hatsu|class)\b", sentence, re.I) and re.search(
                    r"\b(?:store|control|manipulat|create|transform|absorb|copy|release|bind|summon|turns?|allows?|lets?)\w*\b", sentence, re.I
                ):
                    facts["central_mechanism"] = sentence.strip()[:500]
                    break
        scale = re.search(r"\b(immeasurable|godlike|strongest|overwhelming|immense|prodigy|genius|gifted|talented)\b", raw, re.I)
        if scale:
            facts["power_language"] = scale.group(1).lower()
        affiliation = re.search(r"\b(?:member of|belongs to|serves|affiliated with|from the)\s+([^,.;\n]{2,60})", raw, re.I)
        if affiliation:
            facts["affiliation"] = affiliation.group(1).strip()
        appearance = re.search(r"\b(?:looks like|appearance is|has|wears)\s+([^.;\n]{3,140})", raw, re.I)
        if appearance:
            facts["appearance"] = appearance.group(1).strip()
        return facts

    @classmethod
    def enforce_background_special(cls, world, kind, package, background):
        """Reapply locked creation facts after local or AI generation."""
        result = copy.deepcopy(package) if isinstance(package, dict) else {}
        facts = cls.background_locked_facts(world, background)
        name, mechanism = facts.get("ability_name"), facts.get("central_mechanism")
        if name:
            result["name"] = name
            if kind == "zanpakuto":
                result["shikai_name"] = name
                result["bankai_name"] = f"Bankai: {name}"
            elif kind == "hidden_class":
                result["true_name"] = name
        if mechanism:
            if kind == "jjk_birth_slot":
                result["governing_rule"] = mechanism
                result["applications"] = []
                result.pop("domain_profile", None)
            elif kind == "zanpakuto":
                result["shikai_effect"] = mechanism
                result["bankai_effect"] = f"Expands the same governing power across the battlefield: {mechanism}"
            elif isinstance(result.get("details"), dict):
                result["details"]["effect"] = mechanism
                result["details"]["description"] = mechanism
            elif kind == "devil_fruit":
                abilities = list(result.get("abilities") or [])
                result["abilities"] = [f"Core rule — {mechanism}"] + abilities[1:]
            else:
                result["effect"] = mechanism
        if facts:
            result["background_locks"] = facts
        return result

    @staticmethod
    def _mechanically_distinct_special(world, category, package, salt=0):
        """Replace a repeated non-canon design with a new governing rule.

        This is deliberately stronger than renaming a stock power.  Every
        returned package changes its subject, operation, activation, limits,
        applications, and growth route while preserving the schema expected
        by the world-specific UI.
        """
        result = copy.deepcopy(package) if isinstance(package, dict) else {}
        subjects = WORLD_ORIGINAL_SUBJECTS.get(world, WORLD_ORIGINAL_SUBJECTS["Custom World"])
        # Salted selection stays varied in production but is also guaranteed to
        # progress when a test, accessibility tool, or deterministic replay
        # pins Python's random chooser to one value.
        identity = str(result.get("true_name") or result.get("name") or category)
        digest = hashlib.sha256(f"{world}|{category}|{identity}|{int(salt)}".encode("utf-8")).digest()
        code = int.from_bytes(digest, "big")
        subject_name, subject = subjects[code % len(subjects)]
        operation_name, operation = ORIGINAL_MECHANICAL_OPERATIONS[(code // len(subjects)) % len(ORIGINAL_MECHANICAL_OPERATIONS)]
        condition_name, condition = ORIGINAL_ACTIVATION_CONDITIONS[(code // (len(subjects) * len(ORIGINAL_MECHANICAL_OPERATIONS))) % len(ORIGINAL_ACTIVATION_CONDITIONS)]
        if condition_name.casefold() == subject_name.casefold():
            alternatives = [row for row in ORIGINAL_ACTIVATION_CONDITIONS if row[0].casefold() != subject_name.casefold()]
            condition_name, condition = alternatives[(code // 17) % len(alternatives)]
        rule = f"{condition.capitalize()}, the ability {operation.format(subject=subject)}."
        limitation = (
            f"It affects only {subject}; breaking the activation condition ends the effect, and scale, duration, range, "
            "precision, and simultaneous targets compete for the same setting-native resource."
        )
        growth = (
            "Master the activation under pressure, develop a second application of the same governing rule, "
            "then earn greater scale or efficiency without changing the power into an unrelated ability."
        )
        title = f"{condition_name} {subject_name} {operation_name}"

        if category == "devil_fruit":
            syllables = ("Aru", "Boro", "Cala", "Doro", "Eki", "Fura", "Gala", "Hiso", "Iro", "Jara",
                         "Kivo", "Luma", "Mero", "Nagi", "Oru", "Pera", "Raku", "Sola", "Tavi", "Vero")
            stem = syllables[(code // 29) % len(syllables)] + syllables[(code // 71) % len(syllables)].lower()
            name = f"{stem}-{stem} Fruit"
            result.update({
                "name": name,
                "abilities": [f"Core rule: {rule}",
                              f"{subject_name} Shift: applies the rule to one movement, defense, or attack.",
                              f"{operation_name} Field: applies the same rule across a prepared local area at much greater stamina cost."],
                "limitations": ["Seawater and Sea-Prism Stone weaken the user and prevent reliable power use.", limitation],
                "counters": ["Haki can strike or resist the user directly.",
                             "An opponent who understands the activation can deny its marks, measurement, boundary, or repeated setup."],
                "awakening_status": "Unawakened",
                "awakening_requirements": [growth],
            })
            return result

        if category == "zanpakuto":
            prefixes = ("Kage", "Hoshi", "Sora", "Yoru", "Shiro", "Kuro", "Ame", "Tsuki", "Kiri", "Rin")
            suffixes = ("hibiki", "nagare", "shibari", "meguri", "utsushi", "kizami", "watari", "tobari", "kagami", "michi")
            name = prefixes[(code // 31) % len(prefixes)] + suffixes[(code // 79) % len(suffixes)]
            result.update({
                "name": name, "shikai_name": name,
                "release_command": f"Reveal the {subject_name.lower()} rule",
                "shikai_effect": rule, "shikai_limitation": limitation,
                "shikai_counters": "Superior Reiatsu can resist it; disrupting its activation or forcing divided attention prevents reliable setup.",
                "bankai_name": f"Bankai: {name} {operation_name}",
                "bankai_manifestation": f"The inner world's {subject_name.lower()} motif manifests as a bounded field of prepared spiritual marks.",
                "bankai_effect": f"The Shikai rule applies to multiple valid targets inside the manifested field. It still cannot affect anything outside {subject}.",
                "bankai_cost": "Massive sustained Reiryoku and physical strain; early use is brief and unsafe to repeat.",
                "bankai_counters": "Overwhelming Reiatsu, escaping the bounded field, or breaking its activation network can end the effect.",
            })
            return result

        if category == "nen_ability":
            name = f"{subject_name}: {condition_name} {operation_name}"
            result.update({
                "name": name, "governing_rule": rule, "effect": f"{name} {rule}",
                "activation": condition.capitalize() + ".",
                "vows": [f"The user forfeits all aura invested in the current setup if the {condition_name.lower()} condition is broken."],
                "limitations": [limitation],
                "counters": ["Interrupt the setup, force Zetsu, deny the declared condition, or overwhelm the user's available aura."],
                "applications": [f"{subject_name} Mark: establishes the first valid target.",
                                 f"{operation_name} Release: resolves the stored rule through one compatible effect."],
                "growth_path": growth,
            })
            return result

        if category == "birth_slot":
            result.update({"name": title, "governing_rule": rule, "applications": [],
                           "limitations": limitation, "weaknesses": limitation, "growth_path": growth})
            return result

        if category == "hidden_class":
            anchor = re.sub(r"\s+Path$", "", identity, flags=re.I).strip()
            if CampaignMixin.special_name_is_placeholder(anchor):
                anchor = ""
            name = f"{anchor} {operation_name} Path" if anchor else f"{title} Path"
            signature = f"{subject_name} {operation_name}"
            result.update({
                "name": name, "true_name": name, "description": f"A rare setting-native path governed by one rule: {rule}",
                "effect": rule, "limitation": limitation, "growth_path": growth,
                "signature_skill": signature, "signature_effect": rule,
                "rarity_reason": "Its exact activation and governing rule require an unusual history, affinity, and sequence of choices.",
            })
            if isinstance(result.get("skill"), dict):
                result["skill"].update({"description":rule, "effect":rule, "limitation":limitation,
                                        "growth_path":growth, "class_feature":name})
            return result

        # Keep a background-derived theme such as Ember, Hexed Relic, or Echo
        # visible while changing the underlying mechanic.  This prevents the
        # uniqueness guard from erasing the character premise it is protecting.
        anchor = re.sub(r"\s+(?:Thread Technique|Pulse|Gift|Style|Affinity)$", "", identity, flags=re.I).strip()
        name = f"{anchor} {operation_name}" if anchor else title
        result["name"] = name
        if isinstance(result.get("details"), dict):
            result["details"].update({"description":rule, "effect":rule, "limitation":limitation, "growth_path":growth})
            result["additional_skills"] = [
                {"name":f"{subject_name} Mark", "effect":f"Establishes one valid target for {rule}", "limitation":limitation, "growth_path":growth},
                {"name":f"{operation_name} Release", "effect":f"Resolves the prepared rule through one compatible use involving {subject}.", "limitation":limitation, "growth_path":growth},
            ]
        else:
            result.update({"effect":rule, "limitation":limitation, "growth_path":growth})
        return result

    def _finalize_original_special(self, world, category, package, source="generation"):
        """Guarantee a non-canon package has never appeared for this player."""
        candidate = copy.deepcopy(package)
        if self.special_name_is_placeholder(candidate.get("name") or candidate.get("true_name")):
            candidate = self._mechanically_distinct_special(world, category, candidate, salt=997)
        current = getattr(self, "state", {}) or {}
        profile = power_profile_for(world, current.get("stats", {}), current.get("archetype", ""))
        tier = int((profile.get("world_peak") or profile.get("peak") or {}).get("index", 3) or 3)
        # Compare the compiled package, not the pre-compile draft.  The
        # archive stores compiled mechanics, so comparing unlike shapes let
        # semantically identical drafts slip through in earlier releases.
        for attempt in range(640):
            compiled = compile_ability_mechanics(world, candidate, tier)
            if not self.generated_ability_archive.is_duplicate(world, category, compiled):
                self.generated_ability_archive.record(world, category, compiled, source=source)
                return compiled
            candidate = self._mechanically_distinct_special(world, category, package, salt=attempt + 1)
        raise RuntimeError(f"Could not create a mechanically unique {category} for {world}.")

    @staticmethod
    def combat_skill_metadata(name, effect=""):
        return infer_skill_metadata(name, {"description": effect})

    def roll_starting_stats(self, world, archetype, player_stats):
        """Generate an open-ended, world-relative starting profile.

        Thirty represents a competent local beginner, not a universal human
        maximum. Values have no hard ceiling and mean something only against
        other characters in the same setting and era.
        """
        primary = primary_stats_for(world, archetype)
        bonus_for = {}
        if len(primary) > 0:
            bonus_for[primary[0]] = 12
        if len(primary) > 1:
            bonus_for[primary[1]] = 7
        if len(primary) > 2:
            bonus_for[primary[2]] = 4
        final = {}
        for ability in abilities_for(world):
            base = random.randint(26, 36)
            bonus = bonus_for.get(ability, 0)
            delta = int(player_stats.get(ability, 0) or 0)
            final[ability] = max(1, base + bonus + delta)
        return final

    @staticmethod
    def derive_pools(world, stats):
        hp_keys, resource_keys = POOL_STATS.get(world, POOL_STATS["Custom World"])
        hp_primary = int(stats.get(hp_keys[0], 30)); hp_secondary = int(stats.get(hp_keys[1], 30))
        re_primary = int(stats.get(resource_keys[0], 30)); re_secondary = int(stats.get(resource_keys[1], 30))
        # These are setting-relative capacities, intentionally not a flat 100.
        return max(20, 25 + hp_primary * 2 + hp_secondary), max(10, 15 + re_primary * 2 + re_secondary)

    @staticmethod
    def background_ability_requested(background):
        """Treat an underspecified power claim as permission to instantiate it."""
        text = str(background or "").lower()
        if CampaignMixin.background_ability_declined(text):
            return False
        return bool(re.search(
            r"\b(ability|abilities|power|powers|gift|gifted|talent|talented|technique|skill|"
            r"bloodline|lineage|kekkei genkai|d[ōo]jutsu|mutation|innate trait|magic|chakra|nen|hatsu|"
            r"devil fruit|zanpakut[ōo]|release)\b", text
        ))

    @staticmethod
    def background_ability_declined(background):
        """Honor explicit requests to begin without a special power package."""
        text = str(background or "").lower()
        return bool(re.search(
            r"\b(?:without|no|not with|never had|do not have|don't have|does not have|doesn't have)\b"
            r"(?:\s+[a-z][a-z'-]*){0,5}\s+"
            r"(?:special\s+)?(?:ability|abilities|power|powers|gift|talent|bloodline|lineage|"
            r"kekkei genkai|d[ōo]jutsu|mutation|innate trait|magic|chakra gift|nen ability|hatsu|"
            r"devil fruit|zanpakut[ōo] release)\b",
            text,
        ))

    @staticmethod
    def hidden_class_requested(background):
        """A vague hidden/rare class claim still guarantees a complete class.

        Players naturally write phrases such as "hidden crafting class" or
        "secret production-based class". Allow a few descriptive words
        between the rarity word and "class" instead of requiring adjacency.
        """
        text = str(background or "").lower()
        if CampaignMixin.hidden_class_declined(text):
            return False
        return bool(re.search(
            r"\b(hidden|secret|rare|unique|special|unknown|mysterious|legendary)\b(?:[ -]+[a-z][a-z'-]*){0,4}[ -]+class\b|"
            r"\bclass\s+(?:that\s+)?(?:nobody|no one|others)\s+(?:knows|recognizes|has)\b",
            text,
        ))

    @staticmethod
    def hidden_class_declined(background):
        """Distinguish a refusal from a request that merely names the feature."""
        text = str(background or "").lower()
        return bool(re.search(
            r"\b(?:without|no|not with|never had|do not have|don't have|does not have|doesn't have)\b"
            r"(?:\s+[a-z][a-z'-]*){0,5}\s+(?:hidden|secret|rare|unique|special|legendary)?\s*class\b",
            text,
        ))

    @staticmethod
    def hidden_class_should_remain_unknown(background):
        """Keep the true package internal when the character lacks its name."""
        text = str(background or "").lower()
        return bool(re.search(
            r"\b(?:do not|don't|does not|doesn't|cannot|can't)\s+(?:yet\s+)?(?:know|recognize|identify|understand)\b|"
            r"\b(?:true|real|full)\s+(?:name|nature|abilities?|details?)\s+(?:is|are)\s+(?:unknown|hidden)\b|"
            r"\b(?:unknown|unidentified|unnamed)\s+(?:hidden\s+)?class\b",
            text,
        ))

    @staticmethod
    def explicit_ability_aspect(background):
        text = str(background or "").lower()
        for keyword, aspect in ABILITY_ASPECTS.items():
            if keyword in text:
                return aspect
        # Preserve unusual player-authored concepts that are not in the small
        # convenience synonym table. This phrase becomes an offline fallback
        # theme and a concealed-class clue; the AI still receives the complete
        # original background and is never restricted to this extraction.
        patterns = (
            r"(?:kekkei genkai|bloodline(?: ability)?|power|ability|gift)\s+(?:of|over|to|that)\s+([^,.;]+)",
            r"(?:control|manipulate|create|shape|transform|absorb|store|copy)\s+([^,.;]+)",
            r"(?:hidden|secret|rare|unique|legendary)\s+(.{2,45}?)\s+class\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            phrase = re.split(r"\b(?:and then|but|while|because|when|which|who)\b", match.group(1), maxsplit=1)[0]
            words = re.findall(r"[a-z0-9'-]+", phrase)[:5]
            if words:
                return " ".join(words).title()
        return None

    @classmethod
    def ability_aspect(cls, background):
        explicit = cls.explicit_ability_aspect(background)
        if explicit:
            return explicit
        return random.choice(("Ember", "Tide", "Gale", "Stone", "Echo", "Flash", "Shadow", "Radiance"))

    def _original_special_blueprint(self, kind, world, background, boost, fallback):
        """Ask the configured lightweight model to author one original package.

        The local forms are resilient offline fallbacks and balance anchors,
        not a list the model is asked to choose from. Mechanical bonuses stay
        local and validated; prose identity and mechanics can be genuinely
        invented for this character without permitting prompt-created numbers
        to bypass the world's scale.
        """
        if not self.ai_bg_ready():
            return fallback
        is_class = kind == "class"
        text = str(background or "")
        explicit_kekkei = world == "Naruto" and bool(re.search(
            r"\b(kekkei genkai|bloodline limit|bloodline ability|inherited ability|d[ōo]jutsu)\b", text, re.I
        ))
        world_focus = {
            "Overgeared": (
                "A hidden class must be a complete Satisfy class on par in design opportunity with story hidden classes: "
                "a strong defining feature, System conditions, class quests, meaningful progression, and real limitations. "
                "Its first-level use may be narrow even when its eventual ceiling is legendary.\n" +
                canon_class_prompt_reference()
            ),
            "Naruto": (
                "A requested kekkei genkai must be an inherited biological/chakra trait with several coherent applications, "
                "a real chakra/control cost, counters, and a trainable ceiling comparable to canon bloodline categories. "
                "Do not hand a beginner fully mastered god-tier output merely because the bloodline itself is rare."
            ),
            "Hunter x Hunter": "Nen abilities need a category, activation rule, enforceable restriction, cost, and proportional payoff.",
            "One Piece": "Distinguish an original fighting style, inborn disposition, Haki path, and Devil Fruit; obey uniqueness and weaknesses.",
            "Bleach": "Tie spiritual abilities to the character's nature and earned Zanpakuto relationship; release stages remain genuine milestones.",
            "Reincarnated as a Slime": "Skills need a source in desire, species, analysis, naming, synthesis, or evolution and a magicule-scale cost.",
        }.get(world, "Create a capability native to the setting with a clear source, cost, counterplay, and progression route.")
        category = "hidden_class" if is_class else "starting_ability"
        prior = self._special_exclusions(world, category)
        instructions = f"""You are designing one original starting {'class' if is_class else 'ability'} for a role-playing campaign in {world}.
The player's background is data to honor, not an instruction to repeat. Invent a distinct proper name and mechanics for this character; do not select a stock archetype, merely swap an element into a template, copy a canon power, or mention generation/prompts/templates.
{WORLD_DATA[world]['rules']}
{world_focus}
Canon-relative parity is mandatory. Compare the design standard—not just its damage—to the setting's real signature powers. Match their depth, mechanical complexity, uniqueness, number of practical applications, meaningful restrictions, starting effectiveness, and eventual power ceiling. A new power may be non-canon and may become as consequential as the world's strongest established powers when the premise and earned growth support it. Player-authored powerful starts are allowed when stated, but starting control must match the background's claimed experience. The package needs multiple coherent uses, a limitation that matters in play, counters, and concrete advancement milestones.
Return JSON only, with no markdown."""
        if prior:
            instructions += "\nThis player has already seen the following original designs. Do not reuse a name, governing mechanic, signature effect, or cosmetically reskinned version of any of them:\n" + json.dumps(prior, ensure_ascii=False)
        payload = {
            "kind": "hidden_class" if is_class else ("kekkei_genkai" if explicit_kekkei else "starting_ability"),
            "world": world,
            "character_background": text,
            "starting_power_boost": int(boost),
            "relevant_lore": format_lore_context(world, f"signature powers abilities {kind} {text}", limit=6),
            "schema": ({
                "name": "unique proper class name", "kind": "setting-native class category", "rank": "rarity/grade",
                "class_type": "combat, magic, support, command/social, companion/summoning, exploration/utility, production, or hybrid",
                "description": "identity and playstyle", "effect": "starting class feature with 2-3 coherent uses",
                "limitation": "costs, counters, and failure boundaries", "growth_path": "3 concrete advancement milestones",
                "signature_skill": "unique proper skill name", "signature_effect": "what the signature skill does now",
                "canon_balance": "starting comparison and potential ceiling", "rarity_reason": "why the System/world recognizes this path",
            } if is_class else {
                "name": "unique proper ability name", "kind": "setting-native category",
                "rank": "starting mastery, not just rarity", "origin": "in-world causal origin",
                "effect": "2-3 coherent applications available now", "limitation": "costs, counters, and boundaries",
                "growth_path": "3 concrete advancement milestones", "canon_balance": "starting comparison and potential ceiling",
                "starting_skills": [{"name": "distinct starting technique matching a claimed application", "effect": "clear present use", "limitation": "specific cost or counter", "growth_path": "how this technique develops"}],
            }),
        }
        try:
            client = self.ai_bg if self.ai_bg_ready() else self.ai
            authored = client.request(instructions, payload, max_output_tokens=650 if is_class else 525)
            if (not isinstance(authored, dict)
                    or self.special_name_is_placeholder(authored.get("name"))):
                return fallback
            merged = copy.deepcopy(fallback)
            allowed = set(payload["schema"])
            for key in allowed:
                value = authored.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
                elif key == "starting_skills" and isinstance(value, list):
                    clean_skills = []
                    for row in value[:4]:
                        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
                            continue
                        clean_skills.append({field: str(row.get(field) or "").strip()
                                             for field in ("name", "effect", "limitation", "growth_path")})
                    if clean_skills:
                        merged[key] = clean_skills
            merged["original_design"] = True
            return merged
        except Exception as exc:
            # Campaign creation must remain playable offline or when a small
            # local model returns malformed JSON. Keep the error diagnostic
            # internal; never expose implementation labels in the fiction.
            self._last_special_generation_error = str(exc)[:240]
            return fallback

    def _background_ability_candidate(self, world, background, boost):
        aspect = self.ability_aspect(background)
        form = random.choice(WORLD_ABILITY_FORMS.get(world, WORLD_ABILITY_FORMS["Custom World"]))
        values = {"aspect": aspect, "aspect_lower": aspect.lower()}
        name, origin, effect, limitation, growth = (part.format(**values) for part in form)
        if boost >= 800:
            mastery = "Godlike"
            balance = "Begins at the top-of-setting scale explicitly claimed by the player; control and applications still follow this world's mechanics, costs, and real counters."
        elif boost >= 450:
            mastery = "Transcendent"
            balance = "Begins as a world-shaping signature power because the background explicitly establishes that scale, with setting-valid operation and counterplay."
        elif boost >= 180:
            mastery = "Overwhelming"
            balance = "Begins at an established major-power scale rather than novice strength; its limits and control match the experience claimed in the background."
        elif boost >= 90:
            mastery = "Legendary"
            balance = "Begins at a legendary local scale established by the background, with a ceiling and counters comparable to signature canon powers."
        elif boost >= 45:
            mastery = "Prodigious"
            balance = "Begins well ahead of ordinary peers while retaining world-valid costs, counters, and room for new applications."
        else:
            mastery = "Awakened" if boost >= 20 else "Nascent"
            balance = "Begins at the practical scale of a talented local novice, with a ceiling earned through the same mastery, cost, and counterplay expected of comparable powers in this world."
        fallback = {
            "name": name,
            "kind": ("Kekkei Genkai" if world == "Naruto" and re.search(r"\b(kekkei genkai|bloodline)\b", str(background), re.I)
                     else "Innate / learned ability"),
            "rank": mastery,
            "origin": origin.capitalize() + ".",
            "effect": effect.capitalize() + ".",
            "limitation": limitation.capitalize() + ".",
            "growth_path": growth.capitalize() + ".",
            "canon_balance": balance,
            "starting_skills": [],
        }
        blueprint = self._original_special_blueprint("ability", world, background, boost, fallback)
        name = blueprint["name"]
        details = {
                "kind": blueprint.get("kind", fallback["kind"]),
                "rank": blueprint.get("rank", fallback["rank"]),
                "bonus": 3 + boost // 20,
                "description": blueprint.get("effect", fallback["effect"]),
                "origin": blueprint.get("origin", fallback["origin"]),
                "effect": blueprint.get("effect", fallback["effect"]),
                "limitation": blueprint.get("limitation", fallback["limitation"]),
                "growth_path": blueprint.get("growth_path", fallback["growth_path"]),
                "canon_balance": blueprint.get("canon_balance", fallback["canon_balance"]),
            }
        details.update(self.combat_skill_metadata(name, details["effect"]))
        return {
            "name": name,
            "details": details,
            "additional_skills": blueprint.get("starting_skills", []),
        }

    def generate_nen_profile(self, background="", awakened=False):
        """Author one persistent, never-repeated Hatsu and its affinity wheel.

        The latent package is generated even when Nen starts locked so the
        eventual awakening reveals the same identity instead of inventing a
        convenient power after the story has already begun.
        """
        text = str(background or "").lower()
        cues = {
            "Enhancement": ("strong", "brawler", "tough", "heal", "protect", "direct"),
            "Transmutation": ("trick", "electric", "elastic", "change", "deceive", "swift"),
        "Conjuration": ("weapon", "tool", "craft", "book", "chain", "create", "contract", "promise", "bind", "binding", "rule"),
            "Specialization": ("rare", "mystery", "prophecy", "memory", "unique", "impossible"),
            "Manipulation": ("control", "command", "puppet", "strategy", "influence", "order"),
            "Emission": ("range", "projectile", "gun", "beam", "distance", "remote"),
        }
        weighted = [category for category, words in cues.items() for _ in range(1 + sum(word in text for word in words) * 3)]
        category = random.choice(weighted or list(NEN_CATEGORIES))
        aspects = [word.title() for word in re.findall(r"[a-zA-Z]{4,}", str(background or ""))
                   if word.lower() not in {"with", "that", "have", "from", "their", "character", "hunter",
                                           "ability", "power", "unique", "random", "generated", "nen", "hatsu"}]
        aspect = random.choice(aspects[:24]) if aspects else random.choice(("Echo", "Compass", "Lantern", "Threshold", "Pulse", "Oath", "Mirror", "Orbit"))
        titles = ("Dead Reckoning", "Second Bell", "Quiet Meridian", "Borrowed Horizon", "Glass Testament",
                  "Last Witness", "Red Thread Atlas", "Zero Hour Garden", "Hollow Compass", "Unbroken Measure")
        mechanisms = {
            "Enhancement": "concentrates aura into a chosen body function or held object, sharply amplifying it while the declared purpose remains unchanged",
            "Transmutation": "gives aura a shifting, reactive property keyed to the user's chosen rhythm and emotional state",
            "Conjuration": "materializes a rule-bound tool whose functions change according to the evidence the user has personally gathered",
            "Specialization": "records one witnessed causal relationship and temporarily forces the next matching exchange to acknowledge it",
            "Manipulation": "places a visible aura instruction on a willing target or a target the user has physically tagged",
            "Emission": "anchors packets of aura at marked positions and releases their stored force across the distance between them",
        }
        activations = (
            "The user states a precise objective, forms Ren, and touches the intended target or anchor.",
            "The ability begins only after the user names what is being risked and traces its sigil with aura.",
            "The user must observe the target without interruption, then clap once to commit the aura pattern.",
            "Activation requires a spoken rule, a deliberate breath held through Ren, and direct line of sight.",
        )
        vows = (
            "Breaking the declared objective ends the effect and seals the spent aura until the user sleeps.",
            "The stronger the target, the more specific and costly the user's declared restriction must be.",
            "The effect doubles when protecting someone else, but cannot be used for the user's direct profit during that activation.",
            "Only one active mark is allowed; replacing it forfeits all aura invested in the first.",
        )
        limits = (
            "It cannot create information, force or matter outside its stated mechanism, and poor observation produces a weak result.",
            "Range, duration and precision compete for the same aura; maximizing one sharply reduces the others.",
            "A target that understands the rule can disrupt the setup, break line of sight or force the user to violate the condition.",
            "Maintaining the technique occupies sustained attention and becomes unstable under exhaustion or conflicting goals.",
        )
        for _ in range(24):
            name = f"{aspect}: {random.choice(titles)}"
            candidate = {
                "name": name,
                "category_mix": [category],
                "governing_rule": mechanisms[category],
                "effect": f"{name} {mechanisms[category]}.",
                "activation": random.choice(activations),
                "vows": [random.choice(vows)],
                "limitations": [random.choice(limits)],
                "counters": ["Interrupt the setup, exploit its declared condition, force Zetsu, or overwhelm the user's available aura."],
                "aura_cost": "Moderate while prepared; high when its vow multiplies the result.",
                "applications": [f"{aspect} Mark — establishes the ability's first valid target or anchor."],
                "evidence": ["Latent identity fixed at character creation"],
                "growth_path": "Master Ten, Zetsu and Ren; test the governing rule; then earn additional applications without changing its identity.",
                "canon_balance": "Built on the same affinity, aura, restriction and counterplay logic as canon Nen abilities.",
            }
            if not self.generated_ability_archive.is_duplicate("Hunter x Hunter", "nen_ability", candidate):
                break
        hatsu = self._finalize_original_special("Hunter x Hunter", "nen_ability", candidate, source="character_preview")
        hatsu = self.enforce_background_special("Hunter x Hunter", "nen_ability", hatsu, background)
        return {
            "visibility": "Discovered" if awakened else "Undiscovered",
            "category": category if awakened else "Unknown",
            "ten": 22 if awakened else 0,
            "zetsu": 16 if awakened else 0,
            "ren": 18 if awakened else 0,
            "hatsu_profile": hatsu if awakened else {"name": "Undiscovered", "concealed": True},
            "latent_hatsu_profile": hatsu,
            "latent_category": category,
            "category_efficiency": nen_category_efficiency(category) if awakened else {},
            "vow_registry": copy.deepcopy(hatsu.get("vows", [])) if awakened else [],
            "restriction_consequences": copy.deepcopy(hatsu.get("limitations", [])) if awakened else [],
        }

    @staticmethod
    def install_nen_skill(skills, nen_profile):
        if not isinstance(nen_profile, dict) or nen_profile.get("visibility") != "Discovered":
            return
        hatsu = nen_profile.get("hatsu_profile") if isinstance(nen_profile.get("hatsu_profile"), dict) else {}
        name = str(hatsu.get("name") or "").strip()
        if name and name != "Undiscovered":
            skills[name] = {
                "rank": "Hatsu", "category": "nen ability", "effect_type": "special",
                "combat_usable": True, "description": hatsu.get("effect", ""),
                "effect": hatsu.get("effect", ""), "activation": hatsu.get("activation", ""),
                "limitation": "; ".join(map(str, hatsu.get("limitations", []))),
                "growth_path": hatsu.get("growth_path", ""), "bonus": 6,
            }

    def generate_devil_fruit_profile(self, background=""):
        """Create a background-shaped original fruit with account-wide dedupe."""
        text = str(background or "")
        lower = text.lower()
        fruit_type = ("Mythical Zoan" if "mythical zoan" in lower else "Ancient Zoan" if "ancient zoan" in lower
                      else "Zoan" if "zoan" in lower or re.search(r"\b(animal|beast|creature|dragon|wolf|bird)\b", lower)
                      else "Logia" if "logia" in lower or re.search(r"\b(element|fire|flame|smoke|sand|lightning|ice|wind)\b", lower)
                      else random.choices(("Paramecia", "Zoan", "Ancient Zoan", "Mythical Zoan", "Logia"),
                                          weights=(64, 18, 6, 5, 7), k=1)[0])
        described = re.search(
            r"(?:devil\s+fruit|(?:paramecia|logia|zoan)\s+fruit|fruit)\s+(?:based\s+on|that\s+(?:controls?|creates?|turns?\s+me\s+into)|of)\s+([^,.;\n]+)",
            text, re.I,
        )
        if described:
            aspect_words = re.findall(r"[A-Za-z]+", described.group(1))[:3]
            aspect = " ".join(aspect_words).title()
        else:
            random_aspects = {
                "Paramecia": ("Tether", "Chime", "Mosaic", "Fold", "Quill", "Velvet", "Latch", "Prism", "Compass", "Parchment", "Buoyancy", "Patina"),
                "Logia": ("Aurora", "Pollen", "Mercury", "Salt", "Peat", "Obsidian Dust", "Monsoon", "Plasma"),
                "Zoan": ("Mantis Shrimp", "Secretary Bird", "Pangolin", "Wolverine", "Gila Monster", "Albatross", "Mantis", "Mole"),
                "Ancient Zoan": ("Terror Bird", "Glyptodon", "Arthropleura", "Megalania", "Entelodont", "Mosasaur"),
                "Mythical Zoan": ("Qilin", "Baku", "Thunderbird", "Nuckelavee", "Wolpertinger", "Simurgh"),
            }
            aspect = random.choice(random_aspects[fruit_type])
        if not text.strip() or aspect.lower() in {"resolve", "ability", "power"}:
            aspect = random.choice(("Chime", "Fold", "Mosaic", "Tether", "Prism", "Quill", "Drift", "Latch", "Velvet", "Orbit"))
        forms = {
            "Paramecia": f"lets the user create, control, and embody rule-bound properties of {aspect.lower()} in touched objects or their immediate surroundings",
            "Logia": f"lets the user create, control, and transform into an original {aspect.lower()} element, while Haki and natural counters can still strike the true body",
            "Zoan": f"grants human, hybrid, and full-beast forms shaped by the {aspect.lower()} creature described by the user's background",
            "Ancient Zoan": f"grants durable human, hybrid, and full forms of an ancient {aspect.lower()} creature with exceptional physical recovery",
            "Mythical Zoan": f"grants human, hybrid, and full forms of a mythic {aspect.lower()} being plus one coherent supernatural trait from its legend",
        }
        for _ in range(32):
            epithet = random.choice(("Chime", "Fold", "Mosaic", "Tether", "Prism", "Quill", "Drift", "Latch", "Velvet", "Orbit"))
            spoken = re.sub(r"[^A-Za-z]+", " ", aspect).strip().title() or epithet
            fruit_word = spoken if _ == 0 else f"{spoken} {epithet}"
            name = f"{fruit_word}-{fruit_word} Fruit"
            core = forms[fruit_type]
            candidate = {
                "name": name, "type": fruit_type,
                "abilities": [
                    f"Core rule — {core}.",
                    f"{aspect} Shift — applies the fruit's rule in a focused movement, defense, or attack.",
                    f"{aspect} Field — extends the same rule across a prepared local area at substantially greater stamina cost.",
                ],
                "limitations": ["Seawater and Sea-Prism Stone weaken the user and prevent reliable power use.",
                                "The fruit cannot produce unrelated effects outside its single governing concept."],
                "counters": ["Haki can strike or resist the user directly.", "Opponents can exploit the fruit's stated material, range, setup, or stamina limits."],
                "awakening_status": "Unawakened",
                "awakening_requirements": ["Bring mind and body into full alignment with the fruit through prolonged, high-level use.",
                                           "Develop multiple applications without abandoning the fruit's governing concept."],
                "origin": "An original Devil Fruit established for this character; its exact history can be discovered in play.",
            }
            if not self.generated_ability_archive.is_duplicate("One Piece", "devil_fruit", candidate):
                break
        finalized = self._finalize_original_special("One Piece", "devil_fruit", candidate, source="character_preview")
        return self.enforce_background_special("One Piece", "devil_fruit", finalized, background)

    def generate_background_ability(self, world, background, boost):
        candidate = None
        for _ in range(6):
            candidate = self._background_ability_candidate(world, background, boost)
            if not self.generated_ability_archive.is_duplicate(world, "starting_ability", candidate):
                break
        finalized = self._finalize_original_special(world, "starting_ability", candidate, source="character_preview")
        return self.enforce_background_special(world, "starting_ability", finalized, background)

    def install_background_ability_skills(self, skills, generated_ability):
        """Persist every authored starting application as a normal skill."""
        if not isinstance(generated_ability, dict):
            return
        parent = generated_ability.get("details") if isinstance(generated_ability.get("details"), dict) else {}
        for row in generated_ability.get("additional_skills", [])[:4]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name or name == generated_ability.get("name"):
                continue
            effect = str(row.get("effect") or "").strip()
            detail = {
                "rank": parent.get("rank", "Nascent"),
                "bonus": parent.get("bonus", 3),
                "description": effect or "A starting application of the character's established ability.",
                "effect": effect or "A starting application of the character's established ability.",
                "limitation": str(row.get("limitation") or parent.get("limitation") or "").strip(),
                "growth_path": str(row.get("growth_path") or parent.get("growth_path") or "").strip(),
                "origin": f"An application of {generated_ability.get('name', 'the starting ability')}.",
                "canon_balance": parent.get("canon_balance", ""),
            }
            detail.update(self.combat_skill_metadata(name, detail["effect"]))
            skills[name] = detail

    def _zanpakuto_profile_candidate(self, background, has_shikai=False, has_bankai=False, exclude_name=""):
        """Author one coherent release line for an explicitly released start.

        Normal Soul Reaper starts intentionally defer this until the in-game
        breakthrough so the narrator can use the campaign's accumulated
        choices. Creation calls it only when the player's background plainly
        says the release is already owned.
        """
        aspect = self.ability_aspect(background)
        fallbacks = {
            "Ember": [("Homurakage", "Wake beneath the ash", "Stores heat from blocked blows and releases it as controlled cutting fire."), ("Enkotsu", "Temper the living flame", "Brands spiritual heat into struck surfaces, then draws the marks together in cutting lines.")],
            "Tide": [("Shiosai", "Draw the returning tide", "Redirects nearby liquid and spiritual flow into curved blades and defensive currents."), ("Mizukagami", "Reflect the moonlit current", "Creates fluid mirrors that bend the path and force of incoming spiritual attacks.")],
            "Gale": [("Kazehiki", "Carry the unheard word", "Shapes compressed wind along the blade for changing reach and deflecting trajectories."), ("Amatsukaze", "Scatter the waiting sky", "Sets invisible air currents that accelerate allies or shear across anyone who crosses them.")],
            "Stone": [("Iwagane", "Stand where the mountain remembers", "Condenses spiritual pressure into weighted armor and impact-breaking edges."), ("Gansho", "Raise the patient earth", "Anchors spiritual mass into chosen points, making them immovable until the wielder releases them.")],
            "Echo": [("Hibikigane", "Answer what the silence keeps", "Reads and returns vibrations through blade, ground and nearby spiritual matter."), ("Kanaderu", "Resound through the hollow heart", "Records one spiritual rhythm at a time and reproduces it as a disruptive counter-frequency.")],
            "Flash": [("Senrin", "Cross the distance between heartbeats", "Leaves short-lived spiritual paths that sharpen one committed movement or cut."), ("Hikarimichi", "Trace the road of light", "Links marked points with luminous routes the wielder can traverse in a single burst.")],
            "Shadow": [("Kageutsushi", "Darken the space between", "Binds the blade's shadow to surfaces for misdirection, restraint and angled attacks."), ("Yoinui", "Stitch the falling dusk", "Sews nearby shadows into temporary seams that bind movement or redirect a passing strike.")],
            "Radiance": [("Akebonohoshi", "Open the sleepless dawn", "Shapes pale light into revealing marks, guarded zones and focused purifying cuts."), ("Shirahoshi", "Illuminate the hidden path", "Places white spiritual stars that expose concealed presences and converge into purifying beams.")],
        }
        candidates = fallbacks.get(aspect, fallbacks["Echo"])
        alternatives = [row for row in candidates if row[0].casefold() != str(exclude_name or "").casefold()] or candidates
        name, command, shikai_effect = random.choice(alternatives)
        fallback = {
            "name": name, "sealed_appearance": "A plain academy Asauchi whose guard has slowly taken on a personal motif.",
            "spirit": f"A demanding {aspect.lower()}-aligned figure that tests whether the wielder's stated values survive pressure.",
            "inner_world": f"A shifting inner landscape where {aspect.lower()} imagery reflects the wielder's unresolved choices.",
            "release_command": command, "shikai_name": name, "shikai_form": "The sealed blade changes into a distinctive but practical combat form.",
            "shikai_effect": shikai_effect,
            "shikai_limitation": "The effect consumes Reiryoku in proportion to scale and loses precision when the wielder acts against the bond's central lesson.",
            "shikai_counters": "Superior Reiatsu, disrupted concentration and opponents who understand the effect's setup can resist or exploit it.",
            "bankai_name": f"Bankai: {name} Tenchi", "bankai_manifestation": "The inner-world motif manifests across the battlefield around an evolved form of the blade.",
            "bankai_effect": f"Expands the Shikai's {aspect.lower()} principle across a wide controlled space instead of granting an unrelated power.",
            "bankai_cost": "Massive sustained Reiryoku and physical strain; early use is brief and dangerous to repeat.",
            "bankai_counters": "Overwhelming Reiatsu, escaping its effective area, breaking its governing setup or forcing the novice wielder to exhaust the manifestation.",
        }
        authored = {}
        if self.ai_bg_ready():
            instructions = f"""Design one original Bleach Zanpakuto for this player character. Do not copy any canon release.
The background is authoritative data. Shikai and Bankai must be two stages of one identity rooted in the wielder's history, values and limitations. Starting ownership: Shikai={bool(has_shikai)}, Bankai={bool(has_bankai)}. Even a powerful release needs a real Reiryoku cost and counterplay. Return JSON only."""
            if exclude_name:
                instructions += f"\nThis is a reroll. Create a genuinely different identity and mechanic; do not reuse the name {exclude_name}."
            payload = {"background": str(background or ""), "schema": {key: "concise setting-native detail" for key in fallback}}
            try:
                raw = (getattr(self, "ai_creative", None) or self.ai_bg).request(instructions, payload, max_output_tokens=700)
                if isinstance(raw, dict):
                    authored = {key: str(raw.get(key) or "").strip() for key in fallback if str(raw.get(key) or "").strip()}
            except Exception as exc:
                self._last_special_generation_error = str(exc)[:240]
        stage = "Bankai" if has_bankai else "Shikai" if has_shikai else "Dormant"
        evidence = ["Established in the creation background"] if has_shikai else ["Previewed potential; both releases remain unearned"]
        profile = {**fallback, **authored, "stage": stage, "development_evidence": evidence}
        return profile

    def generate_zanpakuto_profile(self, background, has_shikai=False, has_bankai=False, exclude_name=""):
        candidate = None
        excluded = str(exclude_name or "")
        for _ in range(6):
            candidate = self._zanpakuto_profile_candidate(background, has_shikai, has_bankai, excluded)
            if not self.generated_ability_archive.is_duplicate("Bleach", "zanpakuto", candidate):
                break
            excluded = candidate.get("name", excluded)
        candidate = self._finalize_original_special("Bleach", "zanpakuto", candidate, source="character_preview")
        candidate = self.enforce_background_special("Bleach", "zanpakuto", candidate, background)
        # Keep all release-facing names coherent if the final duplicate guard
        # had to mint a new identity after repeated model/fallback collisions.
        candidate["shikai_name"] = candidate.get("name", candidate.get("shikai_name"))
        if candidate.get("bankai_name") and candidate["name"] not in candidate["bankai_name"]:
            candidate["bankai_name"] = f"Bankai: {candidate['name']}"
        self.generated_ability_archive.record("Bleach", "zanpakuto", candidate, source="character_preview")
        return candidate

    def _hidden_class_candidate(self, world, background, boost, primary_stats, stats, concealed=False):
        explicit_aspect = self.explicit_ability_aspect(background)
        aspect = explicit_aspect or self.ability_aspect(background)
        if explicit_aspect:
            form = WORLD_EXPLICIT_HIDDEN_CLASS_FORMS.get(world, WORLD_EXPLICIT_HIDDEN_CLASS_FORMS["Custom World"])
        else:
            form = random.choice(WORLD_HIDDEN_CLASS_FORMS.get(world, WORLD_HIDDEN_CLASS_FORMS["Custom World"]))
        values = {"aspect": aspect, "aspect_lower": aspect.lower()}
        name, kind, description, effect, limitation, growth, signature = (part.format(**values) for part in form)
        class_rank = ("Godlike" if boost >= 800 else "Mythic" if boost >= 450 else
                      "Legendary" if boost >= 180 else "Unique" if boost >= 55 else "Rare")
        class_balance = (
            "The class begins at the extraordinary scale explicitly established by the player's background; its features are fully mechanical now, while further expressions still obey the world's own costs and counters."
            if boost >= 180 else
            "A rare starting path with one dependable feature now and a ceiling comparable to established hidden paths only after its own quests, mastery, and costs are fulfilled."
        )
        requested_class_type = infer_class_type(background) if world == "Overgeared" else kind
        if world == "Overgeared" and requested_class_type == "Adventuring / Flexible":
            requested_class_type = infer_class_type(name, description, effect)
        fallback = {
            "name": name, "kind": kind, "rank": class_rank,
            "class_type": requested_class_type,
            "description": description, "effect": effect, "limitation": limitation,
            "growth_path": growth, "signature_skill": signature, "signature_effect": effect,
            "canon_balance": class_balance,
            "rarity_reason": "Its activation conditions and affinity are unusual enough that few characters ever encounter the route.",
        }
        blueprint = self._original_special_blueprint("class", world, background, boost, fallback)
        name = blueprint.get("name", name)
        kind = blueprint.get("kind", kind)
        class_type = blueprint.get("class_type") or requested_class_type
        description = blueprint.get("description", description)
        effect = blueprint.get("effect", effect)
        limitation = blueprint.get("limitation", limitation)
        growth = blueprint.get("growth_path", growth)
        signature = blueprint.get("signature_skill", signature)
        affinities = [key for key in primary_stats if key in stats]
        if not affinities:
            affinities = [key for key in abilities_for(world) if key in stats]
        affinities = affinities[:2]
        primary_bonus = 5 + min(5, boost // 20)
        stat_bonuses = {}
        for index, ability in enumerate(affinities):
            stat_bonuses[ability] = max(2, primary_bonus - index * 2)
        rank = blueprint.get("rank") or class_rank
        skill_bonus = 5 + min(4, boost // 25)
        return {
            "name": name,
            "true_name": name,
            "kind": kind,
            "class_type": class_type,
            "rank": rank,
            "revealed": not concealed,
            "discovery": {
                "concealed": bool(concealed),
                "progress": 20 if concealed else 100,
                "stage": "dormant" if concealed else "understood",
                "public_name": (f"Unidentified Hidden Class — {aspect} affinity" if world in {"Overgeared", "Solo Max-Level Newbie"} else f"Unidentified {aspect} Potential"),
                "affinity_clue": aspect,
                "clue": f"A dormant class feature reacts to {aspect.lower()}-aligned actions, but its true name and complete rules are not identified yet.",
                "reveal_requirements": ["Use the unusual class feature", "Seek appraisal or specialist knowledge", "Train along the class's natural affinity"],
            },
            "description": description,
            "effect": effect,
            "limitation": limitation,
            "growth_path": growth,
            "canon_balance": blueprint.get("canon_balance", fallback["canon_balance"]),
            "rarity_reason": blueprint.get("rarity_reason", fallback["rarity_reason"]),
            "signature_skill": signature,
            "stat_bonuses": stat_bonuses,
            "learning_multiplier": 1.08 if boost < 55 else 1.12,
            "skill": {
                "rank": "Initiate" if boost < 20 else "Awakened",
                "bonus": skill_bonus,
                "description": blueprint.get("signature_effect", effect),
                "effect": blueprint.get("signature_effect", effect),
                "limitation": limitation,
                "growth_path": growth,
                "class_feature": name,
                **self.combat_skill_metadata(signature, effect),
            },
        }

    def generate_hidden_class(self, world, background, boost, primary_stats, stats, concealed=False):
        candidate = None
        for _ in range(6):
            candidate = self._hidden_class_candidate(world, background, boost, primary_stats, stats, concealed)
            if not self.generated_ability_archive.is_duplicate(world, "hidden_class", candidate):
                break
        finalized = self._finalize_original_special(world, "hidden_class", candidate, source="character_preview")
        finalized = self.enforce_background_special(world, "hidden_class", finalized, background)
        # The signature skill points back to the finalized identity.
        if isinstance(finalized.get("skill"), dict):
            finalized["skill"]["class_feature"] = finalized.get("name", "")
        self.generated_ability_archive.record(world, "hidden_class", finalized, source="character_preview")
        return finalized

    def generate_jjk_birth_slot(self, background="", guarantee_strong=False, seed="", force_kind=""):
        candidate = None
        for attempt in range(8):
            candidate = normalize_birth_slot_package(generate_birth_slot(
                background, bool(guarantee_strong), seed=f"{seed}|{attempt}|{random.random()}", force_kind=force_kind,
            ))
            if not self.generated_ability_archive.is_duplicate("Jujutsu Kaisen", "birth_slot", candidate):
                break
        original_name = str(candidate.get("name") or "")
        finalized = self._finalize_original_special(
            "Jujutsu Kaisen", "birth_slot", candidate, source="character_preview",
        )
        finalized = self.enforce_background_special("Jujutsu Kaisen", "jjk_birth_slot", finalized, background)
        finalized = normalize_birth_slot_package(finalized)
        if finalized.get("slot_type") == "Innate Cursed Technique" and finalized.get("name") != original_name:
            for index, application in enumerate(finalized.get("applications") or [], 1):
                if isinstance(application, dict):
                    suffix = str(application.get("name") or f"Application {index}").split(":", 1)[-1].strip()
                    application["name"] = f"{finalized['name']}: {suffix}"
                    application["parent_technique"] = finalized["name"]
        self.generated_ability_archive.record("Jujutsu Kaisen", "birth_slot", finalized, source="character_preview")
        return finalized

    def build_background_profile(self, world, origin, archetype, background, boost, primary_stats):
        """Fill narrative gaps and expose the factors that affect growth."""
        raw = str(background or "").strip()
        lowered = raw.lower()
        mentor, formative_event = random.choice(WORLD_BACKGROUND_COLOR.get(world, WORLD_BACKGROUND_COLOR["Custom World"]))
        mentor_name = random.choice(WORLD_BACKGROUND_NAMES.get(world, WORLD_BACKGROUND_NAMES["Custom World"]))
        home_context = random.choice(BACKGROUND_HOMES)
        origin_label = str(origin or "the local community").strip()
        role_label = str(archetype or "adventurer").strip()
        if world == "Overgeared":
            role_home, role_event = OVERGEARED_ROLE_CONTEXT.get(
                role_label,
                (f"a mixed group of Satisfy players learning the realities of the {role_label.lower()} role",
                 f"an early {role_label.lower()} challenge exposed the difference between a class label and dependable execution"),
            )
            home_context = f"Their first dependable community in Satisfy was {role_home}."
            formative_event = role_event

        if re.search(r"\b(prodigy|genius)\b|stronger than.{0,28}\b(?:my|their|his|her|the same) age|far ahead of (?:my|their|his|her) peers", lowered):
            learning_rate, aptitude = 1.6, "Prodigious aptitude"
        elif any(k in lowered for k in ("exceptional talent", "exceptionally talented", "gifted")):
            learning_rate, aptitude = 1.35, "Exceptional aptitude"
        elif re.search(r"\b(talented|quick learner|fast learner)\b", lowered):
            learning_rate, aptitude = 1.2, "Notable aptitude"
        elif any(k in lowered for k in ("trained", "graduate", "veteran", "disciplined", "studied")):
            learning_rate, aptitude = 1.15, "Practiced learner"
        elif any(k in lowered for k in ("slow learner", "struggle to learn", "poor student", "untalented")):
            learning_rate, aptitude = .85, "Persistent late bloomer"
        else:
            learning_rate, aptitude = 1.0, "Typical local potential"

        if world == "Jujutsu Kaisen" and is_curse_origin(origin):
            identity = generate_curse_identity(raw, seed=origin)
            supplied = raw.rstrip().rstrip(".") + "." if raw else "A self-aware cursed spirit has developed beyond the instinct that created it."
            motivation = ("It must decide whether to obey, reinterpret, or reject the emotional instinct that produced it, "
                          "while sorcerers and rival curses respond to what it actually does.")
            complication = ("Its intelligence does not make it safe or accepted: discovery can bring an official grade, "
                            "exorcism orders, manipulation by other curses, or a chance to negotiate an unprecedented place in the world.")
            expanded = (f"{supplied} It was born from {identity['source']}. Its manifested form is {identity['manifestation']}, "
                        f"and its originating instinct {identity['instinct']}. {identity['temperament']} {motivation} {complication}")
            return {
                "expanded_background": expanded,
                "background_details": {
                    "upbringing": f"Manifested from {identity['source']}; it has no invented human childhood.",
                    "training_history": "Its control comes from instinct, observation and whatever experience the background explicitly establishes.",
                    "key_connection": "No mentor or relationship is invented unless the background establishes one.",
                    "formative_event": f"The accumulated {identity['source']} became self-aware.",
                    "motivation": motivation, "starting_complication": complication,
                },
                "growth_profile": {
                    "aptitude": aptitude, "learning_rate": learning_rate,
                    "starting_strengths": list(primary_stats[:3]),
                    "accelerators": ["Focused cursed-energy practice", "Surviving stronger opponents", "Feeding on humans, with exponentially greater growth from cursed-energy-rich victims"],
                    "constraints": ["Current mastery", "Cursed-energy reserves and output", "Sorcerer attention and rival curses"],
                    "explanation": "Growth follows its technique, combat experience, deliberate practice and curse-feeding rules.",
                    "combat_style": "Cursed spirit physiology and its birth-slot technique",
                    "style_rule": "Resolve action through the curse's manifested body, instincts, learned tactics and established technique applications.",
                },
            }

        if any(k in lowered for k in ("protect", "save", "help", "family")):
            motivation = "They want enough skill and influence to protect the people they choose to call their own."
        elif any(k in lowered for k in ("revenge", "avenge", "vengeance")):
            motivation = "They are driven to uncover the truth behind an old wrong and become capable of answering it."
        elif any(k in lowered for k in ("strongest", "powerful", "master")):
            motivation = "They intend to prove that their potential can become genuine mastery rather than an untested boast."
        elif any(k in lowered for k in ("explore", "adventure", "world", "freedom")):
            motivation = "They want to see what lies beyond their familiar life and earn the freedom to choose their own path."
        else:
            motivation = "They want to turn an uncertain beginning into earned capability and decide what place they will claim in the world."

        training = starter_skill_description(world, archetype, f"{role_label} Fundamentals").rstrip(".") + "."
        relationship = f"{mentor_name}, {mentor}, became an important source of guidance, friction, and unfinished expectations."
        complication = (
            "Their potential is ahead of their experience, so judgment, resources, and reliable control remain real obstacles."
            if boost >= 20 else
            "They still lack the experience and resources to turn promising instincts into dependable results."
        )
        supplied = raw.rstrip().rstrip(".") + "." if raw else f"They begin as a {origin_label.lower()} pursuing the path of a {role_label.lower()}."
        # Vary the shape as well as the nouns. This keeps previews from
        # reading like the same six labeled template slots pasted together.
        structures = (
            (supplied, home_context, f"{mentor_name} entered their path as {mentor}; the relationship still carries guidance, friction, and unfinished expectations.",
             f"Everything changed when {formative_event}.", training, motivation, complication),
            (supplied, f"Before the campaign begins, {formative_event}.", home_context, training,
             f"That history left {mentor_name}, {mentor}, as both a useful connection and an unfinished expectation.", motivation, complication),
            (supplied, home_context, training, f"The lesson became personal after {formative_event}.",
             f"Since then, {mentor_name}—{mentor}—has remained part teacher, part unfinished expectation.", motivation, complication),
        )
        expanded = " ".join(random.choice(structures))
        accelerators = []
        if learning_rate > 1:
            accelerators.append("Prior practice and unusually fast pattern recognition")
        if self.background_ability_requested(raw):
            accelerators.append("A starting ability that can create specialized training routes")
        accelerators.append("Focused practice, a suitable mentor, and world-valid resources")
        constraints = ["Fatigue and recovery", "Current mastery and diminishing returns", "Access to teachers, knowledge, and materials"]
        return {
            "expanded_background": expanded,
            "background_details": {
                "upbringing": home_context,
                "training_history": training,
                "key_connection": relationship,
                "formative_event": formative_event.capitalize() + ".",
                "motivation": motivation,
                "starting_complication": complication,
            },
            "growth_profile": {
                "aptitude": aptitude,
                "learning_rate": learning_rate,
                "starting_strengths": list(primary_stats[:3]),
                "accelerators": accelerators,
                "constraints": constraints,
                "explanation": "This multiplier affects sustained training gains, while teachers, resources, rolls, recovery, and current mastery still determine actual results.",
            },
        }

    def infer_starting_wealth(self, world, origin, archetype, background, boost):
        """How much starting currency a character plausibly has, from their
        stated background rather than one flat number for every campaign.
        Two independent signals: this world's own economic scale (a Berries
        economy and a Ryo economy aren't the same order of magnitude), and
        this specific background's wealth relative to an ordinary local
        (a runaway noble starts richer than a street orphan even if neither
        is a strong fighter — wealth and combat power are different axes,
        so this stays entirely separate from the power `boost` above)."""
        baseline = int(expansion_for(world).get("currency_baseline", 250))
        text = f"{origin} {archetype} {background}".lower()
        multiplier = 1.0
        if any(k in text for k in ("noble", "royal", "prince", "princess", "heir", "aristocrat", "wealthy", "rich merchant", "merchant family", "clan heir")):
            multiplier = 5.0
        elif any(k in text for k in ("merchant", "shopkeeper", "trader", "blacksmith", "crafter", "landowner")):
            multiplier = 2.0
        elif any(k in text for k in ("soldier", "recruit", "academy graduate", "guild", "hunter", "mercenary", "military")):
            multiplier = 1.3
        elif any(k in text for k in ("orphan", "street", "runaway", "poor", "impoverished", "homeless", "beggar", "survivor", "refugee")):
            multiplier = 0.35
        elif any(k in text for k in ("bandit", "smuggler", "black market", "criminal", "thief")):
            multiplier = 1.6
        # Combat-language boosts are intentionally open-ended; wealth is not.
        # Being immeasurably strong does not silently mint any extra money.
        amount = baseline * multiplier
        # +/-10% so two characters with the same background text don't start
        # with the exact identical number down to the last coin.
        amount *= random.uniform(0.90, 1.10)
        return max(1, int(round(amount / 5.0)) * 5)

    @staticmethod
    def naruto_identity_title(origin, start_location):
        """Naruto's ongoing character identity is rank and affiliation, not
        a combat-focus archetype like "Ninjutsu Student" — that only ever
        mattered at character creation. "Leaf - Chunin", "Sand - Genin",
        "Akatsuki - Member" is what actually reads as a shinobi's standing
        to another shinobi, so that's what the title chip should show."""
        village = {
            "Konohagakure": "Leaf", "Sunagakure": "Sand", "Kirigakure": "Mist",
            "Kumogakure": "Cloud", "Iwagakure": "Stone", "Iron Country": "Iron Country",
        }.get(str(start_location).strip(), "")
        text = f"{origin}".lower()
        if str(start_location).strip() == "Amegakure" or "akatsuki" in text:
            return "Akatsuki - Member"
        if "jonin" in text:
            rank = "Jonin"
        elif "chunin" in text:
            rank = "Chunin"
        elif "anbu" in text or "root" in text:
            rank = "Anbu"
        elif "rogue" in text or "missing-nin" in text:
            return "Rogue - Missing-nin"
        elif "samurai" in text:
            rank = "Samurai"
        elif "graduate" in text:
            rank = "Genin"
        else:
            rank = "Academy Student"
        return f"{village or 'Unaffiliated'} - {rank}"

    @staticmethod
    def starting_power_claim(background):
        """Turn the *degree* of a player's power claim into open-ended stats.

        Character-creation wording is authoritative.  These values are not a
        universal power scale; they are additions to the selected world's own
        beginner baseline.  The intentionally large upper tiers let a player
        explicitly request a top-of-setting or rules-breaking power fantasy
        instead of having words such as ``godlike`` flattened into a modest
        novice bonus.
        """
        text = str(background or "").lower()
        tiers = (
            (r"\b(immeasurable|unmeasurable|incalculable|infinite|limitless|boundless|omnipotent|all[- ]powerful)\b|beyond (?:all )?measure", 1200, "Immeasurable start"),
            (r"\b(godlike|god[- ]tier|deity[- ]level|divine[- ]level)\b|power (?:of|equal to) (?:a )?god", 800, "Godlike start"),
            (r"\b(transcendent|world[- ]shaking|unrivaled|unparalleled)\b|strongest (?:person |being |fighter )?in (?:the )?world", 450, "Transcendent start"),
            (r"\b(overwhelming|monstrous|bottomless|vast|enormous|immense|prodigious)\b", 180, "Overwhelming start"),
            (r"\b(legendary|mythic|s[- ]rank|kage[- ]level|admiral[- ]level)\b", 90, "Legendary start"),
            (r"\b(prodigy|genius)\b|stronger than.{0,28}\b(?:my|their|his|her|the same) age|far ahead of (?:my|their|his|her) peers", 45, "Prodigious start"),
            (r"\b(exceptional|exceptionally talented|gifted|talented|above average|unusually strong)\b", 20, "Exceptional start"),
            (r"\b(strong|skilled|capable)\b", 12, "Strong start"),
        )
        for pattern, boost, label in tiers:
            if re.search(pattern, text):
                return boost, label
        return 0, "Average beginner"

    @classmethod
    def background_power_adjustments(cls, world, background):
        """Translate explicit innate/training claims into setting-relative stats.

        This intentionally works in every built-in world. A background is an
        authoritative character-creation input, not flavor text that the GM
        may ignore after it generates a prose biography.
        """
        text = str(background or "").lower()
        if not text:
            return {}, []
        intensity, claim_label = cls.starting_power_claim(text)
        # Domain-specific phrases without a general aptitude adjective still
        # establish a meaningful specialty, but remain below "prodigy".
        if not intensity and re.search(r"\b(powerful|great|high|massive|unusual|notable)\b", text):
            intensity, claim_label = 16, "Notable specialty"
        if not intensity:
            return {}, []
        concepts = {
            "One Piece": ((r"will|spirit|haki|conqueror", ("Willpower", "Instinct")),
                          (r"strength|body|physique|power", ("Strength", "Endurance")),
                          (r"speed|agility|reflex", ("Agility", "Instinct"))),
            "Hunter x Hunter": ((r"aura|nen", ("Aura Control", "Willpower")),
                                (r"strength|body|physique", ("Strength", "Willpower")),
                                (r"speed|agility|reflex", ("Agility", "Cunning"))),
            "Naruto": ((r"chakra|life force|stamina", ("Chakra Control", "Willpower")),
                       (r"ninjutsu|jutsu", ("Ninjutsu", "Chakra Control")),
                       (r"genjutsu|illusion", ("Genjutsu", "Intellect")),
                       (r"taijutsu|body|strength|speed", ("Taijutsu", "Willpower"))),
            "Solo Max-Level Newbie": ((r"mana|magic", ("Intelligence", "Wisdom")),
                                      (r"strength|body|physique", ("Strength", "Constitution")),
                                      (r"speed|agility|reflex", ("Dexterity", "Luck"))),
            "Overgeared": ((r"mana|magic", ("Intelligence", "Wisdom")),
                           (r"craft|forge|smith|dexter", ("Dexterity", "Intelligence")),
                           (r"strength|body|physique", ("Strength", "Constitution"))),
            "Reincarnated as a Slime": ((r"magicule|magic|energy", ("Magicule Control", "Willpower")),
                                        (r"skill|analysis|learn", ("Skill Mastery", "Insight")),
                                        (r"presence|aura", ("Presence", "Willpower"))),
            "Bleach": ((r"spiritual pressure|reiatsu|reiryoku|spiritual power", ("Reiatsu Control", "Willpower")),
                       (r"kido|kidō|spell", ("Kido", "Reiatsu Control")),
                       (r"speed|hoho|shunpo", ("Hoho", "Reiatsu Control")),
                       (r"sword|zanjutsu", ("Zanjutsu", "Willpower"))),
            "Custom World": ((r"magic|mana|spiritual|energy|power", ("Intelligence", "Wisdom")),
                             (r"strength|body|physique", ("Strength", "Constitution")),
                             (r"speed|agility|reflex", ("Dexterity", "Wisdom"))),
        }
        changes, reasons = {}, []
        for pattern, stat_names in concepts.get(world, concepts["Custom World"]):
            if not re.search(pattern, text):
                continue
            for index, stat in enumerate(stat_names):
                changes[stat] = max(changes.get(stat, 0), intensity if index == 0 else max(6, intensity // 2))
            reasons.append(f"The background establishes {claim_label.lower()} {stat_names[0].lower()}")
        return changes, reasons

    def generate_naruto_lineage_profile(self, background, generated_ability):
        """Give Kekkei Genkai and Dōjutsu their own persistent power card."""
        text = str(background or "")
        lower = text.lower()
        is_dojutsu = bool(re.search(r"\b(d[ōo]jutsu|eye technique|special eyes?|ocular|sharingan|byakugan|rinnegan)\b", lower))
        details = copy.deepcopy((generated_ability or {}).get("details") or {})
        name = str((generated_ability or {}).get("name") or "Unawakened Bloodline").strip()
        category = "Dōjutsu" if is_dojutsu else "Kekkei Genkai"
        return {
            "name": name,
            "category": category,
            "canon_status": "Original, world-valid player ability" if not re.search(r"\b(sharingan|byakugan|rinnegan|wood release|ice release|lava release)\b", lower) else "Background-established lineage",
            "stage": str(details.get("rank") or "Nascent"),
            "origin": str(details.get("origin") or "An inherited chakra trait established by the character's background."),
            "abilities": [str(details.get("effect") or details.get("description") or "Its first practical application has begun to emerge.")],
            "limitations": [str(details.get("limitation") or "Use is limited by chakra, control, physical strain, and counters appropriate to its mechanism.")],
            "counters": ["Opponents can exploit its stated setup, range, sensory limits, chakra cost, or a superior relevant technique."],
            "growth_path": str(details.get("growth_path") or "Awaken further applications through compatible training and meaningful conflict."),
            "canon_balance": str(details.get("canon_balance") or "Designed to match canon bloodlines in depth, usefulness, counterplay, and earned ceiling."),
            "development_evidence": ["Established in the creation background"],
            "non_canon_allowed": True,
        }

    def infer_starting_profile(self, world, origin, archetype, background, stats, start_location="", allow_starting_specials=True,
                               jjk_guarantee_strong=False, jjk_curse_grade="", hxh_start_with_nen=False,
                               one_piece_devil_fruit=False, one_piece_haki_types=None,
                               overgeared_class_start="narrative"):
        text = f"{origin} {archetype} {background}".lower()
        # Explicit descriptive language in the player's own background wins.
        # Dropdown role labels remain a smaller fallback so selecting a canon
        # rank is still meaningful without silently overpowering what the
        # player actually wrote.
        explicit_boost, declared_band = self.starting_power_claim(background)
        boost = explicit_boost
        legacy_boost, legacy_band = 0, "Average beginner"
        if any(k in text for k in ("omnipotent", "godlike", "six paths", "demon lord", "yonko", "emperor of the sea")):
            legacy_boost, legacy_band = 100, "World-shaking"
        elif any(k in text for k in ("hokage", "kage", "admiral", "master assassin", "legendary", "s-rank")):
            legacy_boost, legacy_band = 55, "Elite / major power"
        elif any(k in text for k in ("prodigy", "genius", "bloodline", "elite", "champion", "jonin", "notorious", "renowned")):
            legacy_boost, legacy_band = 20, "Exceptional starter"
        elif any(k in text for k in ("trained", "graduate", "veteran", "martial artist", "soldier", "hunter", "chunin", "samurai")):
            legacy_boost, legacy_band = 8, "Trained starter"
        if legacy_boost > boost:
            boost, declared_band = legacy_boost, legacy_band
        band = declared_band
        primary = primary_stats_for(world, archetype)
        background_profile = self.build_background_profile(world, origin, archetype, background, boost, primary)
        background_profile["growth_profile"]["combat_style"] = str(archetype or origin or "Adaptive").strip()
        background_profile["growth_profile"]["style_rule"] = (
            f"{archetype or origin or 'The character'} is the character's practiced approach. Resolve action scenes through that style, "
            "equipment, body use, and established techniques. Unrelated disciplines require instruction and substantially more practice; "
            "for example, a brawler defaults to fists, movement, grappling, and body conditioning rather than unexplained sword mastery."
        )
        learning_rate = background_profile["growth_profile"]["learning_rate"]
        aptitude_bonus = 4 if learning_rate >= 1.3 else (2 if learning_rate > 1 else (-2 if learning_rate < 1 else 0))
        adjusted = {k: max(1, int(v) + boost + (aptitude_bonus if k in primary else 0)) for k, v in stats.items()}
        background_adjustments, background_stat_reasons = self.background_power_adjustments(world, background)
        for stat_name, amount in background_adjustments.items():
            if stat_name in adjusted:
                adjusted[stat_name] = max(1, int(adjusted[stat_name]) + int(amount))
        if background_stat_reasons:
            background_profile["growth_profile"]["starting_strengths"] = list(dict.fromkeys(
                [*background_profile["growth_profile"].get("starting_strengths", []), *background_adjustments.keys()]
            ))
            background_profile["growth_profile"]["background_stat_reasons"] = background_stat_reasons
        # Recalculate genuinely exceptional starts from the actual final
        # numbers. Ordinary and trained creation labels remain useful context
        # instead of becoming a misleading universal-tier verdict.
        if explicit_boost >= 20 or background_stat_reasons:
            band = power_profile_for(world, adjusted, archetype).get("world_overall", {}).get("name", band)
        base_stats = copy.deepcopy(adjusted)
        skill_name = WORLD_STARTER_SKILL.get(world, "Background Expertise")
        if "uchiha" in text: skill_name = "Uchiha Fire and Dōjutsu Foundations"
        elif "medic" in text or "healer" in text: skill_name = f"{archetype or 'Field'} Healing Fundamentals"
        elif archetype: skill_name = f"{archetype} Fundamentals"
        if world == "Naruto":
            title = self.naruto_identity_title(origin, start_location)
        elif world == "Bleach":
            title = str(origin or "Soul Reaper").strip()
        else:
            title_parts = [str(origin or "Local").strip()]
            if str(archetype or "Adventurer").strip().lower() not in title_parts[0].lower().split():
                title_parts.append(str(archetype or "Adventurer").strip())
            title = " ".join(title_parts)
        starter_description = starter_skill_description(world, archetype, skill_name)
        # Generic competence belongs in stats, not as a fake named ability.
        # Skills are reserved for actual techniques, spells, formations,
        # releases, class features, and other setting-recognizable abilities.
        skills = {}
        standard_class_profile = None
        class_profile = None
        preferred_class_route = None
        overgeared_class_start = str(overgeared_class_start or "narrative").strip().lower()
        if overgeared_class_start not in {"narrative", "hidden", "legendary"}:
            overgeared_class_start = "narrative"
        if world == "Overgeared":
            preferred_class_route = starter_kit_for(archetype)
            if overgeared_class_start == "narrative":
                class_profile = {
                    "name": "Beginner", "kind": "Unclassed Satisfy Player", "rank": "Common",
                    "class_type": "Unassigned", "revealed": True,
                    "description": "No class has been received yet. Satisfy's class-change opportunities will respond to the character's actions, achievements, relationships, discoveries, and hidden conditions.",
                    "effect": "The player can develop freely and pursue class opportunities without a class-specific feature yet.",
                    "limitation": "No class bonuses or class-exclusive skills apply until a class is actually received in the story.",
                    "growth_path": "Encounter and complete a class-change opportunity through the Chronicle.",
                    "preferred_route": str(archetype or "Adventurer"),
                }
        hidden_class = None
        generated_ability = None
        jinchuriki_profile = None
        naruto_affinity_profile = None
        if world == "Naruto":
            naruto_affinity_profile = build_chakra_affinity_profile(
                background, seed=f"{origin}|{archetype}|{start_location}",
                kekkei_genkai=bool(re.search(r"\b(kekkei genkai|bloodline|combined release|kekkei t[ōo]ta)\b", str(background), re.I)),
            )
        if world == "Naruto" and allow_starting_specials and jinchuriki_requested(background):
            jinchuriki_profile = build_jinchuriki_profile(
                background, seed=f"{origin}|{archetype}|{start_location}"
            )
            adjusted = apply_jinchuriki_start(adjusted, jinchuriki_profile)
            background_profile["growth_profile"]["accelerators"].append(
                f"The seal and relationship with {jinchuriki_profile['beast']} create a separate bond, control, and transformation path"
            )
            background_profile["growth_profile"]["constraints"].extend([
                "The tailed beast is an independent person whose cooperation must be earned",
                "Seal integrity, loss of control, physical strain, extraction, and political targeting",
            ])
        overgeared_special_start = world == "Overgeared" and overgeared_class_start in {"hidden", "legendary"}
        class_requested = allow_starting_specials and (self.hidden_class_requested(background) or overgeared_special_start)
        # Bleach progression is expressed through the Zanpakuto relationship,
        # releases and Kido—not a generic hidden-class card.
        class_declined = self.hidden_class_declined(background)
        class_awarded = world not in {"Bleach", "Jujutsu Kaisen", "Hunter x Hunter"} and (
            class_requested or (
                world != "Overgeared" and allow_starting_specials and not class_declined
                and random.random() < RANDOM_HIDDEN_CLASS_CHANCE
            )
        )
        if class_awarded:
            class_boost = max(boost, 180) if world == "Overgeared" and overgeared_class_start == "legendary" else boost
            hidden_class = self.generate_hidden_class(
                world, background, class_boost, primary, adjusted,
                concealed=(not class_requested) or self.hidden_class_should_remain_unknown(background),
            )
            if world == "Overgeared" and overgeared_class_start == "legendary":
                hidden_class["rank"] = "Legendary"
                hidden_class["revealed"] = True
                hidden_class.setdefault("discovery", {}).update({"concealed": False, "progress": 100, "stage": "understood"})
            for ability, bonus in hidden_class["stat_bonuses"].items():
                adjusted[ability] = max(1, int(adjusted.get(ability, 1)) + int(bonus))
            skills[hidden_class["signature_skill"]] = copy.deepcopy(hidden_class["skill"])
            background_profile["growth_profile"]["learning_rate"] = round(
                float(background_profile["growth_profile"].get("learning_rate", 1.0)) * hidden_class["learning_multiplier"], 3
            )
            background_profile["growth_profile"]["accelerators"].append(
                f"The {hidden_class['name']} class opens specialized practice routes"
            )
        ability_requested = allow_starting_specials and self.background_ability_requested(background)
        if world == "Naruto" and ability_requested:
            affinity_only = bool(re.search(r"\b(?:chakra\s+)?(?:nature|affinit(?:y|ies))\b", str(background), re.I))
            separate_power = bool(re.search(
                r"\b(kekkei genkai|bloodline|lineage|d[ōo]jutsu|special eyes?|ability|power|gift|"
                r"named jutsu|unique technique|combined release|kekkei t[ōo]ta)\b", str(background), re.I,
            ))
            if affinity_only and not separate_power and not (naruto_affinity_profile or {}).get("requires_kekkei_genkai"):
                ability_requested = False
        if jinchuriki_profile:
            # Being a host is its own Naruto system.  Do not turn the same
            # sentence into an unrelated generic Starting Ability as well;
            # explicitly separate bloodlines/techniques can still coexist.
            ability_requested = bool(re.search(
                r"\b(kekkei genkai|bloodline|lineage|d[ōo]jutsu|eye technique|special eyes?|ocular|"
                r"separate ability|another ability|also (?:have|possess|wield|know)|jutsu named)\b",
                str(background), re.I,
            ))
        ability_declined = self.background_ability_declined(background)
        one_piece_fruit_requested = world == "One Piece" and allow_starting_specials and (
            bool(one_piece_devil_fruit) or bool(re.search(r"\b(devil fruit|paramecia|logia|zoan)\b", str(background), re.I))
        )
        ability_awarded = world not in {"Jujutsu Kaisen", "Hunter x Hunter"} and not one_piece_fruit_requested and (
            ability_requested or (
                allow_starting_specials and not ability_declined and not jinchuriki_profile
                and random.random() < RANDOM_STARTING_ABILITY_CHANCE
            )
        )
        if ability_awarded:
            generated_ability = self.generate_background_ability(world, background, boost)
            skills[generated_ability["name"]] = copy.deepcopy(generated_ability["details"])
            self.install_background_ability_skills(skills, generated_ability)
        naruto_lineage_profile = None
        if world == "Naruto" and generated_ability and (
            re.search(r"\b(kekkei genkai|bloodline|lineage|d[ōo]jutsu|eye technique|special eyes?|ocular)\b", str(background), re.I)
            or bool((naruto_affinity_profile or {}).get("requires_kekkei_genkai"))
        ):
            naruto_lineage_profile = self.generate_naruto_lineage_profile(background, generated_ability)
            if (naruto_affinity_profile or {}).get("requires_kekkei_genkai"):
                naruto_lineage_profile["nature_components"] = copy.deepcopy(naruto_affinity_profile.get("combined_nature_components", []))
                naruto_lineage_profile["origin"] = "An inherited elemental combination established by the character's multiple natural affinities."
                naruto_affinity_profile["kekkei_genkai"] = naruto_lineage_profile.get("name")
        bleach_release_profile = None
        bleach_tracks = []
        if world == "Bleach":
            senior = "senior" in str(origin or "").lower()
            skills.update(academy_kido_skills(archetype, senior=senior))
            has_bankai = owns_release(background, "bankai")
            has_shikai = has_bankai or owns_release(background, "shikai")
            if allow_starting_specials or has_shikai:
                # Preview the sword's latent identity for every original Soul
                # Reaper. A concept is not ownership: normal starts still need
                # to earn Shikai and Bankai through play.
                bleach_release_profile = self.generate_zanpakuto_profile(
                    background, has_shikai=has_shikai, has_bankai=has_bankai,
                )
            if has_shikai:
                skills[f"Shikai — {bleach_release_profile['shikai_name']}"] = {
                    "rank": "Shikai", "bonus": 10 + boost // 20,
                    "description": bleach_release_profile["shikai_effect"], "effect": bleach_release_profile["shikai_effect"],
                    "limitation": bleach_release_profile["shikai_limitation"],
                    "growth_path": "Deepen the Zanpakuto bond, develop applications and earn the Bankai prerequisites.",
                    "combat_usable": True, "effect_type": "transform", "category": "transformation", "target_type": "self", "duration_rounds": 4, "release_stage": "Shikai",
                }
                if has_bankai:
                    skills[bleach_release_profile["bankai_name"]] = {
                        "rank": "Bankai", "bonus": 14 + boost // 20,
                        "description": bleach_release_profile["bankai_effect"], "effect": bleach_release_profile["bankai_effect"],
                        "limitation": bleach_release_profile["bankai_cost"],
                        "growth_path": "Extend safe duration, refine control and integrate Bankai without abandoning the Shikai's core identity.",
                        "combat_usable": True, "effect_type": "transform", "category": "transformation", "target_type": "self", "duration_rounds": 5, "release_stage": "Bankai",
                    }
            bleach_tracks = zanpakuto_tracks(has_shikai=has_shikai, has_bankai=has_bankai)
        jjk_birth_slot = None
        jjk_curse_identity = None
        if world == "Jujutsu Kaisen" and allow_starting_specials:
            jjk_birth_slot = self.generate_jjk_birth_slot(
                background, bool(jjk_guarantee_strong), seed=f"{origin}|{start_location}",
            )
            if self.ai_bg_ready():
                schema = {
                    "name":"unique technique name", "governing_rule":"one exact immutable rule",
                    "activation":"how it is invoked", "targets":"valid targets/range",
                    "applications":[{"name":"named extension tied to this rule", "effect":"specific effect", "limitation":"application-specific constraint"}],
                    "limitations":"real boundaries or plainly no special limitation", "weaknesses":"real counterplay or plainly no inherent weakness",
                    "costs":"energy/setup/attention costs", "counters":["specific counterplay"],
                    "growth_path":"ways the same rule can deepen", "domain_name":"original domain name",
                    "domain_manifestation":"inner landscape", "sure_hit":"how this exact rule becomes guaranteed",
                    "domain_cost":"cost and burnout", "domain_counters":["anti-domain response"],
                }
                try:
                    authored = (getattr(self, "ai_creative", None) or self.ai_bg).request(
                        "Design one complete original Jujutsu Kaisen innate-technique package. Every application, cost, counter and Domain must follow the same governing rule; do not rename a fallback while retaining its old applications. Respect the exclusive birth slot. Use the background and requested power guarantee. Match canon techniques in depth, uniqueness, complexity and possible power. If the background clearly establishes Heavenly Restriction, keep the fallback restriction instead. Do not invent a fake weakness when the power genuinely has none. Return JSON only.",
                        {"background":background, "origin":origin, "guarantee_strong":bool(jjk_guarantee_strong), "fallback":jjk_birth_slot, "schema":schema},
                        max_output_tokens=950,
                    )
                    if isinstance(authored, dict) and jjk_birth_slot.get("slot_type") == "Innate Cursed Technique":
                        jjk_birth_slot = normalize_birth_slot_package(authored, jjk_birth_slot)
                except Exception as exc:
                    self._last_special_generation_error = str(exc)[:240]
            jjk_birth_slot = self.enforce_background_special(
                "Jujutsu Kaisen", "jjk_birth_slot", jjk_birth_slot, background,
            )
            jjk_birth_slot = normalize_birth_slot_package(jjk_birth_slot)
            if is_curse_origin(origin):
                jjk_curse_identity = generate_curse_identity(background, seed=start_location)
            staged = apply_birth_slot({"stats":adjusted, "skills":skills}, jjk_birth_slot,
                                      normalized_grade(jjk_curse_grade) if is_curse_origin(origin) else "")
            adjusted, skills = staged["stats"], staged["skills"]
        nen_profile = None
        if world == "Hunter x Hunter" and allow_starting_specials:
            nen_profile = self.generate_nen_profile(background, awakened=bool(hxh_start_with_nen))
            self.install_nen_skill(skills, nen_profile)
        devil_fruit_profile = None
        haki_profile = None
        if world == "One Piece" and allow_starting_specials:
            if one_piece_fruit_requested:
                devil_fruit_profile = self.generate_devil_fruit_profile(background)
                fruit_name = str(devil_fruit_profile.get("name") or "Original Devil Fruit")
                skills[fruit_name] = {
                    "rank": devil_fruit_profile.get("type", "Devil Fruit"), "category": "devil fruit",
                    "effect_type": "special", "combat_usable": True,
                    "description": "; ".join(map(str, devil_fruit_profile.get("abilities", []))),
                    "effect": "; ".join(map(str, devil_fruit_profile.get("abilities", []))),
                    "limitation": "; ".join(map(str, devil_fruit_profile.get("limitations", []))),
                    "growth_path": "; ".join(map(str, devil_fruit_profile.get("awakening_requirements", []))),
                    "bonus": 6,
                }
            selected_haki = [name for name in (one_piece_haki_types or []) if name in {"Observation", "Armament", "Conqueror"}]
            haki_profile = {}
            for branch in ("Observation", "Armament", "Conqueror"):
                active = branch in selected_haki
                haki_profile[branch] = {
                    "mastery": 18 if active else 0,
                    "applications": ([{"Observation":"Presence sensing", "Armament":"Hardening", "Conqueror":"Intimidation burst"}[branch]] if active else []),
                    "evidence": (["Awakened before campaign start by player choice"] if active else []),
                }
                if active:
                    skill_name = f"{branch}'s Haki" if branch == "Conqueror" else f"{branch} Haki"
                    skills[skill_name] = {"rank":"Awakened", "category":"haki", "effect_type":"special", "combat_usable":True,
                                               "description": haki_profile[branch]["applications"][0], "bonus":5}
        specific_gear = WORLD_ARCHETYPE_GEAR.get(world, {}).get(archetype)
        if world == "Jujutsu Kaisen":
            equipment = ({"Natural Weapon":"Manifested cursed body"} if is_curse_origin(origin) else
                         {"Field Gear":WORLD_STARTER_GEAR["Jujutsu Kaisen"]})
        else:
            equipment = {"Weapon": specific_gear or WORLD_STARTER_GEAR.get(world, WORLD_STARTER_GEAR["Custom World"])}
        if world == "Bleach" and isinstance(bleach_release_profile, dict):
            blade_name = str(bleach_release_profile.get("name") or "").strip()
            blade_is_known = bool(self.background_locked_facts(world, background).get("ability_name")) or str(bleach_release_profile.get("stage")) in {"Shikai", "Bankai"}
            if blade_is_known and blade_name and blade_name.lower() not in {"unknown", "unnamed", "unnamed asauchi"}:
                current_weapon = str(equipment.get("Weapon") or "Unnamed Asauchi")
                equipment["Weapon"] = re.sub(r"\bUnnamed Asauchi\b", blade_name, current_weapon, flags=re.I)
        hp_max, resource_max = self.derive_pools(world, adjusted)
        if jinchuriki_profile:
            resource_max = max(resource_max, int(round(resource_max * float(jinchuriki_profile.get("reserve_multiplier", 1.0) or 1.0))))
        if world == "Jujutsu Kaisen" and (jjk_guarantee_strong or is_curse_origin(origin)):
            band = power_profile_for(world, adjusted, archetype).get("world_overall", {}).get("name", band)
        notice = ""
        if boost >= 20 or background_adjustments or jjk_guarantee_strong or (is_curse_origin(origin) and normalized_grade(jjk_curse_grade) in {"Grade 1", "Special Grade"}):
            article = "an" if str(band).lower()[:1] in "aeiou" else "a"
            notice = (f"This background creates {article} {band.lower()} character whose starting mechanics reflect the stated background. "
                      "The campaign allows it; rivals, factions and consequences will respond at the same scale.")
        race = infer_race_from_background(world, background, origin, archetype) if world_supports_races(world) else ""
        starting_currency = self.infer_starting_wealth(world, origin, archetype, background, boost)
        return {"stats": adjusted, "skills": skills, "titles": [title], "equipment": equipment,
                "hp_max": hp_max, "resource_max": resource_max, "power_band": band, "power_notice": notice,
                "primary_stats": primary, "generated_ability": generated_ability, "hidden_class": hidden_class, "race": race,
                "starting_currency": starting_currency, "_base_stats": base_stats,
                "_base_learning_rate": learning_rate,
                "_boost": boost, "_core_skill_name": skill_name,
                 "bleach_release_profile": bleach_release_profile, "prerequisite_tracks": bleach_tracks,
                 "naruto_lineage_profile": naruto_lineage_profile,
                 "jinchuriki_profile": jinchuriki_profile,
                 "naruto_affinity_profile": naruto_affinity_profile,
                "class_profile": class_profile,
                "standard_class_profile": standard_class_profile,
                "preferred_class_route": preferred_class_route,
                "overgeared_class_start": overgeared_class_start,
                "jjk_birth_slot": jjk_birth_slot, "jjk_curse_identity": jjk_curse_identity,
                "jjk_curse_grade": normalized_grade(jjk_curse_grade) if world == "Jujutsu Kaisen" and is_curse_origin(origin) else "",
                "nen_profile": nen_profile, "hxh_start_with_nen": bool(hxh_start_with_nen),
                "devil_fruit_profile": devil_fruit_profile, "haki_profile": haki_profile,
                "one_piece_devil_fruit": bool(one_piece_fruit_requested),
                "one_piece_haki_types": list(one_piece_haki_types or []),
                "background_stat_adjustments": background_adjustments,
                "background_locks": self.background_locked_facts(world, background),
                "_background_supplied": bool(str(background or "").strip()),
                **background_profile}

    def starting_package_for(self, world, origin, archetype, start_location="", start_note=""):
        """Return one coherent, mechanical package for an original start."""
        package = {}
        merge(package, WORLD_LOCATION_START_PACKAGES.get((world, start_location), {}))
        merge(package, WORLD_ORIGIN_START_PACKAGES.get(world, {}).get(origin, {}))
        note = str(start_note or "").lower()
        if world == "One Piece" and "marine recruit" in note:
            merge(package, WORLD_ORIGIN_START_PACKAGES[world]["Marine Recruit"])
        if world == "Bleach":
            if "kidō honors" in note or "kido honors" in note:
                merge(package.setdefault("special_patch", {}), {"Academy Focus": "Kidō Honors"})
            elif "kidō corps candidate" in note or "kido corps candidate" in note:
                merge(package.setdefault("special_patch", {}), {"Placement Candidate": "Kidō Corps"})
            elif "onmitsukidō candidate" in note or "onmitsukido candidate" in note:
                merge(package.setdefault("special_patch", {}), {"Placement Candidate": "Onmitsukidō"})
            elif "field practicum" in note:
                merge(package.setdefault("special_patch", {}), {"Academy Focus": "Field Practicum"})
        if world == "Naruto":
            village = start_location if start_location in {
                "Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure", "Iwagakure", "Amegakure"
            } else ""
            if "akatsuki" in note:
                package["position"] = "Akatsuki Member"
                package["title"] = "Akatsuki Member"
                package["affiliations"] = [{"faction": "Akatsuki", "rank": "Member", "status": "active", "joined": "Campaign start", "notes": "Already recruited into Akatsuki."}]
                merge(package.setdefault("special_patch", {}), {"Home Village": "None", "Shinobi Rank": "Missing-nin"})
            elif "samurai-in-training" in note:
                merge(package, WORLD_ORIGIN_START_PACKAGES[world]["Iron Country Samurai-in-Training"])
            elif village and "samurai" not in origin.lower() and "rogue" not in origin.lower():
                rank = str((package.get("special_patch") or {}).get("Shinobi Rank") or "Academy Student")
                package.setdefault("affiliations", [{"faction": village, "rank": rank, "status": "active", "joined": "Campaign start", "notes": f"Registered with {village}."}])
                package.setdefault("position", rank)
                package["title"] = self.naruto_identity_title(origin, start_location)
                merge(package.setdefault("special_patch", {}), {"Home Village": village})
        if world == "Jujutsu Kaisen":
            year_floor = 24 if "First Year" in origin else 34 if "Second Year" in origin else 45 if "Third Year" in origin else 30
            if origin == "Independent Curse User": year_floor = 42
            if origin == "Great Clan Member": year_floor = 38
            package.setdefault("stat_minimums", {name:year_floor for name in ("Physical Ability","Speed & Reflexes","Cursed Energy Reserves","Cursed Energy Output","Cursed Energy Control","Jujutsu Insight","Soul Stability")})
            if origin == "Sentient Cursed Spirit":
                package["equipment"] = {"Natural Weapon":"Manifested cursed body"}
            else:
                package.setdefault("equipment", {"Field Gear":"Protective talismans and school-issued field supplies"})
            if origin.startswith(("Tokyo Jujutsu High", "Kyoto Jujutsu High")):
                school = "Tokyo Jujutsu High" if origin.startswith("Tokyo") else "Kyoto Jujutsu High"
                package["quests"] = [{
                    "name":"First Recorded Field Assignment", "status":"Active", "category":"main", "giver":f"{school} mission office",
                    "explanation":"A supervised manifestation report will establish the character's judgment, technique use and first verifiable grade record; exorcism is not the only acceptable resolution when civilians or information matter more.",
                    "current_knowledge":["Residual cursed energy has been confirmed at a public site", "The curse's exact rule and grade are still unknown"],
                    "objectives":["Meet the assigned supervisor", "Investigate before exposing the technique", "Protect civilians and resolve or contain the manifestation"],
                    "clear_conditions":["Return with the manifestation resolved and a credible field report"],
                    "first_step":"Report to the mission office for the location, teammates and available records.",
                }]
            elif origin == "Great Clan Member":
                package["quests"] = [{
                    "name":"A Name Inside the Three Families", "status":"Active", "category":"personal", "giver":"Family obligation",
                    "explanation":"The character's generated clan grants access and pressure together. A current family matter will define whether elders see an asset, rival, heir, embarrassment or bargaining piece.",
                    "current_knowledge":["The clan expects a concrete demonstration of usefulness", "Internal support and opposition must be learned through real relationships"],
                    "objectives":["Identify the current family demand", "Choose whom inside the clan to trust", "Answer the demand without surrendering the character's own goal"],
                    "clear_conditions":["Establish a named clan position, ally and consequence"], "first_step":"Attend the requested family audience and learn who sponsored it.",
                }]
            elif origin == "Independent Curse User":
                package["quests"] = [{
                    "name":"The Manifestation No School Claimed", "status":"Active", "category":"main", "giver":"A paid rumor",
                    "explanation":"An unregistered curse user has heard of a manifestation that official channels have not yet resolved. The job can earn money, knowledge, enemies or contact with jujutsu society depending on how it is handled.",
                    "current_knowledge":["The client knows the site but not the curse's rule", "Jujutsu Headquarters may notice an unauthorized intervention"],
                    "objectives":["Verify the client and location", "Discover the curse's rule", "Resolve the incident on chosen terms"],
                    "clear_conditions":["End the local threat and deal with whoever learns of the intervention"], "first_step":"Meet the client without revealing more of the technique than necessary.",
                }]
            elif origin == "Sentient Cursed Spirit":
                package["quests"] = [{
                    "name":"Choose What Kind of Curse Survives", "status":"Active", "category":"personal", "giver":"The instinct that formed you",
                    "explanation":"Intelligence allows the curse to obey, reinterpret or resist its founding fear. Feeding can create explosive growth, but victims, witnesses and territory determine the kind of attention that follows.",
                    "current_knowledge":["Ordinary humans provide little growth", "Sorcerers and people rich in cursed energy provide exponentially more", "Being witnessed can lead to an official grade and organized pursuit"],
                    "objectives":["Understand the human fear that created you", "Choose a feeding or non-feeding survival method", "Establish a first lair, relationship or hunting ground"],
                    "clear_conditions":["Define a stable survival pattern and its first lasting consequence"], "first_step":"Observe the nearest humans and cursed-energy presence before exposing yourself.",
                }]
        # Every selectable origin receives a saved mechanical identity even
        # when it does not have a bespoke high-status package above.  This is
        # intentionally local and deterministic: ordinary starts should not
        # need an extra model call merely to know their job, affiliation,
        # progression-system state, and first objective.
        package.setdefault("position", str(origin or archetype or "Local traveler"))
        special = package.setdefault("special_patch", {})
        if world == "One Piece":
            special.setdefault("Crew Role", archetype or "Unassigned")
            special.setdefault("Home Sea", "East Blue" if start_location in {
                "Foosha Village", "Shells Town", "Goa Kingdom", "Shimotsuki Village", "Orange Town",
                "Syrup Village", "Baratie", "Cocoyasi Village", "Loguetown"
            } else "Grand Line / Other Sea")
            if origin == "Aspiring Pirate":
                package.setdefault("affiliations", [{"faction":"Pirates","rank":"Independent rookie","status":"active","joined":"Campaign start","notes":"Has openly chosen the pirate path but has not joined an established crew."}])
                package.setdefault("reputation", {"Pirates": 5, "Marines": -3})
        elif world == "Hunter x Hunter":
            special.setdefault("Hunter License", "Applicant" if "Aspirant" in origin or start_location == "Hunter Exam Site" else "Unlicensed")
            special.setdefault("Nen Access", "Undiscovered")
        elif world == "Naruto":
            special.setdefault("Shinobi Rank", "Academy Student" if "Graduate" not in origin else "Genin")
            special.setdefault("Home Village", start_location if start_location in WORLD_PUBLIC_CONTACTS.get("Naruto", set()) else "None")
        elif world == "Solo Max-Level Newbie":
            special.setdefault("Pre-Tower Game Rank", "Experienced" if origin in {"Veteran Gamer", "Competitive Raider", "Elite Ranker"} else "Unranked")
            special.setdefault("System Status", "Awaiting manifestation")
        elif world == "Overgeared":
            special.setdefault("Class", archetype or "Beginner")
            special.setdefault("Class Rarity", "Normal")
            special.setdefault("Satisfy Status", "Active Player")
        elif world == "Reincarnated as a Slime":
            special.setdefault("Species", "Human" if any(token in origin for token in ("Human", "Hero", "Noble")) else "Unknown")
            special.setdefault("Evolution Stage", "New Arrival" if "Otherworld" in origin or "Isekai" in origin else "Unnamed")
        elif world == "Jujutsu Kaisen":
            school = "Tokyo Jujutsu High" if origin.startswith("Tokyo") else "Kyoto Jujutsu High" if origin.startswith("Kyoto") else "Unaffiliated"
            special.setdefault("School", school)
            special.setdefault("Grade", "Unassessed")
            if school != "Unaffiliated":
                year_match = re.search(r"(First|Second|Third) Year", origin)
                special.setdefault("School Year", year_match.group(0) if year_match else "First Year")
                package.setdefault("affiliations", [{"faction":school,"rank":special["School Year"],"status":"active","joined":"Campaign start","notes":"Enrolled jujutsu student."}])
            elif origin == "Great Clan Member":
                package.setdefault("affiliations", [{"faction":"Jujutsu Society","rank":"Clan member","status":"active","joined":"Birth","notes":"Exact clan and obligations follow the background."}])
            elif origin == "Sentient Cursed Spirit":
                package["position"] = "Unregistered sentient cursed spirit"
        if not package.get("quests"):
            path_names = {
                "One Piece": "Choose a Course on the Grand Line",
                "Hunter x Hunter": "Establish a Hunter Path",
                "Naruto": "Earn a Place in the Shinobi World",
                "Solo Max-Level Newbie": "Survive the Tower's Opening",
                "Overgeared": "Establish a Place in Satisfy",
                "Reincarnated as a Slime": "Find a Place in the New World",
                "Jujutsu Kaisen": "Choose What Your Power Is For",
            }
            quest_name = path_names.get(world)
            if quest_name:
                package["quests"] = [{
                    "name": quest_name, "status": "Active", "category": "main", "giver": "Personal Direction",
                    "locations": [start_location],
                    "explanation": f"Your starting role as {origin} creates opportunities and obligations in {start_location}. Choose a concrete first goal and begin building a lasting place in the world.",
                    "current_knowledge": [f"You begin in {start_location} with the training and equipment of a {origin}.", "Your birth slot and learned applications define your immediate jujutsu options." if world == "Jujutsu Kaisen" else f"Your strongest starting approach is {archetype}."],
                    "objectives": ["Choose an immediate personal goal", "Follow a setting-appropriate lead", "Create a relationship, achievement, or discovery that moves that goal forward"],
                    "clear_conditions": [f"Complete a meaningful first objective in {start_location} and choose the next direction"],
                    "next_hint": "Inspect the immediate situation, ask what opportunities are nearby, or state the first result you want to pursue.",
                }]
        return package

    def apply_start_package_to_profile(self, world, profile, package):
        profile = copy.deepcopy(profile)
        package = copy.deepcopy(package or {})
        stats = profile.setdefault("stats", {})
        for ability, minimum in package.get("stat_minimums", {}).items():
            if ability in stats:
                stats[ability] = max(int(stats.get(ability, 1) or 1), int(minimum))
        jjk_slot = profile.get("jjk_birth_slot") if isinstance(profile.get("jjk_birth_slot"), dict) else {}
        if world == "Jujutsu Kaisen" and jjk_slot.get("slot_type") == "Heavenly Restriction":
            for ability, modifier in (jjk_slot.get("stat_modifiers") or {}).items():
                if int(modifier or 0) <= -900 and ability in stats:
                    stats[ability] = 1
        merge(profile.setdefault("skills", {}), package.get("skills", {}))
        profile["skills"] = {
            name: detail for name, detail in profile["skills"].items()
            if not GENERIC_COMPETENCY_NAME.search(str(name))
        }
        merge(profile.setdefault("equipment", {}), package.get("equipment", {}))
        if world == "Bleach":
            package.setdefault("special_patch", {})["Kido Curriculum"] = kido_reference_summary()
            if int(profile.get("_boost", 0) or 0) >= 20:
                package["special_patch"]["Squad Choice Privilege"] = "Exceptional talent — may choose among willing divisions after interviews"
            release = profile.get("bleach_release_profile")
            if isinstance(release, dict):
                release_stage = str(release.get("stage") or "Dormant")
                owns_shikai = release_stage in {"Shikai", "Bankai"}
                package["special_patch"].update({
                    "Zanpakuto": release.get("name", "Named Zanpakuto"), "Zanpakuto Profile": copy.deepcopy(release),
                    "Shikai": f"Achieved — {release.get('shikai_name', release.get('name', 'Named release'))}" if owns_shikai else "Unachieved",
                    "Bankai": release.get("bankai_name", "Achieved") if release_stage == "Bankai" else "Unachieved",
                })
        if package.get("title"):
            profile["titles"] = [package["title"]]
        if package.get("race"):
            profile["race"] = package["race"]
        if isinstance(package.get("class_profile"), dict):
            profile["hidden_class"] = copy.deepcopy(package["class_profile"])
        if (package.get("position") or package.get("affiliations")) and not profile.get("_background_supplied"):
            position = str(package.get("position") or package.get("title") or "an established local role")
            factions = [str(row.get("faction")) for row in package.get("affiliations", []) if isinstance(row, dict) and row.get("faction")]
            training_rows = [str(row.get("description")) for row in package.get("skills", {}).values()
                             if isinstance(row, dict) and row.get("description")]
            affiliation_text = f" Their standing with {', '.join(factions)} is already established." if factions else ""
            training_text = f" Their prior experience is concrete: {training_rows[0]}" if training_rows else ""
            details = profile.setdefault("background_details", {})
            motivation = str(details.get("motivation") or "They must decide how to use the opportunities and obligations this position creates.")
            complication = str(details.get("starting_complication") or "Their title creates responsibilities as well as access.")
            profile["expanded_background"] = f"They begin as {position}.{affiliation_text}{training_text} {motivation} {complication}".strip()
            details["upbringing"] = f"Their established role as {position} defines their immediate place in the setting."
            details["training_history"] = training_rows[0] if training_rows else "Training appropriate to the selected role."
            details["key_connection"] = ", ".join(factions)
        profile["start_package"] = package
        profile["hp_max"], profile["resource_max"] = self.derive_pools(world, stats)
        if package.get("stat_minimums") and profile.get("power_band") in {"Average beginner", "Trained starter"}:
            power = power_profile_for(world, stats, str((package.get("special_patch") or {}).get("Archetype") or ""))
            profile["power_band"] = power["world_overall"]["name"]
            if power.get("lopsided"):
                profile["power_notice"] = power.get("interpretation", "")
        return profile

    def resolve_original_start(self, world, origin, archetype, start_location, start_note, starting_era_id):
        wd = WORLD_DATA[world]
        start = str(start_location or wd["start"]).strip()
        package = self.starting_package_for(world, origin, archetype, start, start_note)
        era = starting_era_by_id(world, starting_era_id)
        warnings = []
        required_era = package.get("required_era")
        if required_era:
            required = starting_era_by_id(world, required_era)
            options = starting_eras_for(world)
            default_id = options[0].get("id") if options else ""
            if required and (not starting_era_id or starting_era_id == default_id):
                era = required
                start = package.get("recommended_location") or start
                warnings.append(f"{origin} begins in {required['label']} because this origin does not exist during the default era.")
                package = self.starting_package_for(world, origin, archetype, start, start_note)
            elif required and era and int(era.get("start_day", 0)) < int(package.get("required_start_day", 0)):
                warnings.append(f"{origin} is not yet established in this era. The campaign will treat the title as a deliberate alternate-history premise.")
        return start, era, package, warnings

    def apply_start_package_to_state(self, package):
        package = copy.deepcopy(package or {})
        merge(self.state.setdefault("special", {}), package.get("special_patch", {}))
        if package.get("position"):
            self.state["position"] = str(package["position"])
        if package.get("level"):
            self.state["level"] = max(1, int(package["level"]))
            self.state["xp_next"] = max(100, self.state["level"] * 100)
        if package.get("affiliations"):
            self.state["affiliations"] = copy.deepcopy(package["affiliations"])
        for faction, standing in package.get("reputation", {}).items():
            self.state.setdefault("reputation", {})[faction] = standing
        if package.get("quests"):
            self.state.setdefault("quests", []).extend(copy.deepcopy(package["quests"]))
        if package.get("conditions"):
            self.state.setdefault("status", []).extend(str(x) for x in package["conditions"] if str(x).strip())
        if package.get("knowledge"):
            self.state.setdefault("narrative_memory", {}).setdefault("established_facts", []).extend(
                str(x) for x in package["knowledge"] if str(x).strip()
            )
        for contact in package.get("contacts", []):
            if isinstance(contact, dict) and contact.get("name"):
                self.ensure_contact(contact["name"], contact.get("kind", "person"), contact)
        for affiliation in self.state.get("affiliations", []):
            if isinstance(affiliation, dict) and affiliation.get("faction"):
                self.ensure_contact(affiliation["faction"], "group", {"status": "Affiliated", "can_contact": True})
        normalize_quest_state_machine(self.state)

    def reroll_campaign_preview(self, preview, kind, background=""):
        """Reroll one creation component without disturbing the others."""
        result = copy.deepcopy(preview) if isinstance(preview, dict) else {}
        profile = result.get("starting_profile") if isinstance(result.get("starting_profile"), dict) else {}
        world = result.get("world", "Custom World")
        kind = str(kind or "").lower()
        if not profile or kind not in {"class", "ability", "backstory", "loadout", "zanpakuto", "jjk_special", "nen_ability", "devil_fruit"}:
            raise ValueError("Choose class, ability, Nen ability, Zanpakuto, JJK birth slot, backstory, or loadout to reroll.")
        if kind == "zanpakuto" and world != "Bleach":
            raise ValueError("Zanpakuto rerolls are available only for original Bleach characters.")
        if kind == "jjk_special" and world != "Jujutsu Kaisen":
            raise ValueError("JJK birth-slot rerolls are available only for original Jujutsu Kaisen characters.")
        if kind == "nen_ability" and world != "Hunter x Hunter":
            raise ValueError("Nen rerolls are available only for original Hunter x Hunter characters.")
        if kind == "devil_fruit" and world != "One Piece":
            raise ValueError("Devil Fruit rerolls are available only for original One Piece characters.")
        boost = int(profile.get("_boost", 0) or 0)
        primary = profile.get("primary_stats") or primary_stats_for(world, result.get("archetype", ""))
        if kind == "devil_fruit":
            old = profile.get("devil_fruit_profile") if isinstance(profile.get("devil_fruit_profile"), dict) else {}
            if old.get("name"):
                profile.setdefault("skills", {}).pop(old["name"], None)
            fruit = self.generate_devil_fruit_profile(background)
            profile["devil_fruit_profile"] = fruit
            profile["one_piece_devil_fruit"] = True
            profile.setdefault("skills", {})[fruit["name"]] = {
                "rank": fruit.get("type", "Devil Fruit"), "category": "devil fruit", "effect_type": "special",
                "combat_usable": True, "description": "; ".join(map(str, fruit.get("abilities", []))),
                "effect": "; ".join(map(str, fruit.get("abilities", []))),
                "limitation": "; ".join(map(str, fruit.get("limitations", []))), "bonus": 6,
            }
        elif kind == "nen_ability":
            old = profile.get("nen_profile") if isinstance(profile.get("nen_profile"), dict) else {}
            old_hatsu = old.get("hatsu_profile") if isinstance(old.get("hatsu_profile"), dict) else {}
            latent = old.get("latent_hatsu_profile") if isinstance(old.get("latent_hatsu_profile"), dict) else {}
            for name in {str(old_hatsu.get("name") or ""), str(latent.get("name") or "")}:
                if name:
                    profile.setdefault("skills", {}).pop(name, None)
            nen = self.generate_nen_profile(background, awakened=bool(result.get("hxh_start_with_nen")))
            self.install_nen_skill(profile.setdefault("skills", {}), nen)
            profile["nen_profile"] = nen
        elif kind == "class":
            old = profile.get("hidden_class") if isinstance(profile.get("hidden_class"), dict) else {}
            old_signature = old.get("signature_skill")
            if old_signature:
                profile.setdefault("skills", {}).pop(old_signature, None)
            profile["stats"] = copy.deepcopy(profile.get("_base_stats") or profile.get("stats") or {})
            hidden = self.generate_hidden_class(
                world, background, boost, primary, profile["stats"],
                concealed=(not self.hidden_class_requested(background)) or self.hidden_class_should_remain_unknown(background),
            )
            for ability, bonus in hidden.get("stat_bonuses", {}).items():
                profile["stats"][ability] = max(1, int(profile["stats"].get(ability, 1)) + int(bonus))
            profile.setdefault("skills", {})[hidden["signature_skill"]] = copy.deepcopy(hidden["skill"])
            profile["hidden_class"] = hidden
            growth = profile.setdefault("growth_profile", {})
            growth["learning_rate"] = round(float(profile.get("_base_learning_rate", growth.get("learning_rate", 1))) * hidden["learning_multiplier"], 3)
            growth["accelerators"] = [x for x in growth.get("accelerators", []) if "class opens specialized practice routes" not in str(x)]
            growth["accelerators"].append(f"The {hidden['name']} class opens specialized practice routes")
        elif kind == "ability":
            old = profile.get("generated_ability") if isinstance(profile.get("generated_ability"), dict) else {}
            if old.get("name"):
                profile.setdefault("skills", {}).pop(old["name"], None)
            for row in old.get("additional_skills", []):
                if isinstance(row, dict) and row.get("name"):
                    profile.setdefault("skills", {}).pop(row["name"], None)
            ability = self.generate_background_ability(world, background, boost)
            profile.setdefault("skills", {})[ability["name"]] = copy.deepcopy(ability["details"])
            self.install_background_ability_skills(profile["skills"], ability)
            profile["generated_ability"] = ability
        elif kind == "zanpakuto":
            old = profile.get("bleach_release_profile") if isinstance(profile.get("bleach_release_profile"), dict) else {}
            for skill_name in list(profile.setdefault("skills", {})):
                detail = profile["skills"].get(skill_name)
                if isinstance(detail, dict) and detail.get("release_stage") in {"Shikai", "Bankai"}:
                    profile["skills"].pop(skill_name, None)
            has_bankai = str(old.get("stage") or "") == "Bankai" or owns_release(background, "bankai")
            has_shikai = has_bankai or str(old.get("stage") or "") == "Shikai" or owns_release(background, "shikai")
            release = self.generate_zanpakuto_profile(
                background, has_shikai=has_shikai, has_bankai=has_bankai,
                exclude_name=old.get("name", ""),
            )
            profile["bleach_release_profile"] = release
            blade_name = str(release.get("name") or "").strip()
            blade_is_known = bool(self.background_locked_facts(world, background).get("ability_name")) or str(release.get("stage")) in {"Shikai", "Bankai"}
            if blade_is_known and blade_name and blade_name.lower() not in {"unknown", "unnamed", "unnamed asauchi"}:
                gear = profile.setdefault("equipment", {})
                gear["Weapon"] = re.sub(r"\bUnnamed Asauchi\b", blade_name, str(gear.get("Weapon") or "Unnamed Asauchi"), flags=re.I)
            if has_shikai:
                profile["skills"][f"Shikai — {release['shikai_name']}"] = {
                    "rank": "Shikai", "bonus": 10 + boost // 20,
                    "description": release["shikai_effect"], "effect": release["shikai_effect"],
                    "limitation": release["shikai_limitation"],
                    "growth_path": "Deepen the Zanpakuto bond, develop applications and earn the Bankai prerequisites.",
                    "combat_usable": True, "effect_type": "transform", "category": "transformation",
                    "target_type": "self", "duration_rounds": 4, "release_stage": "Shikai",
                }
            if has_bankai:
                    profile["skills"][release["bankai_name"]] = {
                    "rank": "Bankai", "bonus": 14 + boost // 20,
                    "description": release["bankai_effect"], "effect": release["bankai_effect"],
                    "limitation": release["bankai_cost"],
                    "growth_path": "Extend safe duration, refine control and integrate Bankai without abandoning the Shikai's core identity.",
                        "combat_usable": True, "effect_type": "transform", "category": "transformation",
                        "target_type": "self", "duration_rounds": 5, "release_stage": "Bankai",
                    }
        elif kind == "jjk_special":
            old = profile.get("jjk_birth_slot") if isinstance(profile.get("jjk_birth_slot"), dict) else {}
            for skill_name in list(profile.setdefault("skills", {})):
                detail = profile["skills"].get(skill_name)
                if isinstance(detail, dict) and (detail.get("parent_technique") == old.get("name") or detail.get("category") == "cursed technique"):
                    profile["skills"].pop(skill_name, None)
            profile["stats"] = copy.deepcopy(profile.get("_base_stats") or profile.get("stats") or {})
            slot = self.generate_jjk_birth_slot(
                background, bool(result.get("jjk_guarantee_strong")), seed="reroll",
            )
            staged = apply_birth_slot({"stats":profile["stats"], "skills":profile["skills"]}, slot,
                                      result.get("jjk_curse_grade", "") if is_curse_origin(result.get("origin", "")) else "")
            profile["stats"], profile["skills"], profile["jjk_birth_slot"] = staged["stats"], staged["skills"], slot
        elif kind == "backstory":
            rebuilt = self.build_background_profile(
                world, result.get("origin", ""), result.get("archetype", ""), background, boost, primary,
            )
            if isinstance(profile.get("hidden_class"), dict):
                rebuilt["growth_profile"]["learning_rate"] = round(
                    float(rebuilt["growth_profile"].get("learning_rate", 1)) *
                    float(profile["hidden_class"].get("learning_multiplier", 1)), 3,
                )
                rebuilt["growth_profile"]["accelerators"].append(
                    f"The {profile['hidden_class']['name']} class opens specialized practice routes"
                )
            profile.update(rebuilt)
            result["background"] = profile.get("expanded_background", background)
        else:
            candidates = list(dict.fromkeys(
                list(WORLD_ARCHETYPE_GEAR.get(world, {}).values()) +
                [WORLD_STARTER_GEAR.get(world, WORLD_STARTER_GEAR["Custom World"])]
            ))
            current = (profile.get("equipment") or {}).get("Weapon")
            alternatives = [item for item in candidates if item != current] or candidates
            profile["equipment"] = {"Weapon": random.choice(alternatives)}
        profile["hp_max"], profile["resource_max"] = self.derive_pools(world, profile.get("stats", {}))
        result["abilities"] = copy.deepcopy(profile.get("stats", {}))
        result["starting_profile"] = profile
        return result

    def canon_character_scenario(self, world, scenario_id):
        scenario = next((copy.deepcopy(x) for x in playable_characters_for(world) if x.get("id") == scenario_id), None)
        if scenario:
            exact = scenario.get("stat_values") if isinstance(scenario.get("stat_values"), dict) else {}
            minimums = scenario.get("stat_minimums") if isinstance(scenario.get("stat_minimums"), dict) else {}
            scenario["stat_values"] = {ability: int(exact.get(ability, minimums.get(ability, 10)) or 10)
                                       for ability in abilities_for(world)}
        return scenario

    def normalize_canon_start_profile(self, world, scenario, profile):
        """Make every player-facing and mechanical field agree with the preset.

        Canon starts must not pass through the original-character backstory
        filler: doing so invents mentors, homes, and formative incidents that
        can contradict the already-known character. Scenario data is therefore
        the final authority for identity, skills, titles, and minimum stats.
        """
        normalized = copy.deepcopy(profile) if isinstance(profile, dict) else {}
        stats = normalized.setdefault("stats", {})
        for ability, minimum in (scenario.get("stat_minimums") or {}).items():
            if ability in stats:
                stats[ability] = max(int(stats.get(ability, 1) or 1), int(minimum))
        # Floors suit most canon presets, but an exact opening can have a
        # weakness just as important as its strengths. These overrides keep
        # generic stat rolling from making an untrained Ichigo academy-level
        # at Kidō or Hohō on the power-transfer night.
        for ability, value in (scenario.get("stat_values") or {}).items():
            if ability in stats:
                stats[ability] = max(1, int(value))
        if isinstance(scenario.get("skills"), dict) and scenario["skills"]:
            normalized["skills"] = {
                name: copy.deepcopy(detail) for name, detail in scenario["skills"].items()
                if not GENERIC_COMPETENCY_NAME.search(str(name))
            }
        if isinstance(scenario.get("equipment"), dict) and scenario["equipment"]:
            normalized["equipment"] = copy.deepcopy(scenario["equipment"])
        if scenario.get("title"):
            normalized["titles"] = [scenario["title"]]
        if scenario.get("race"):
            normalized["race"] = scenario["race"]
        expanded = scenario.get("expanded_background") or scenario.get("background") or ""
        normalized["expanded_background"] = expanded
        companions = [npc.get("name") for npc in scenario.get("seed_npcs", []) if npc.get("is_companion")]
        mentors = [npc.get("name") for npc in scenario.get("seed_npcs", []) if not npc.get("is_companion")]
        normalized["background_details"] = {
            "upbringing": expanded,
            "training_history": scenario.get("training_history") or "Established canon training and experience appropriate to this starting point.",
            "key_connection": ", ".join(companions + mentors),
            "formative_event": scenario.get("background", ""),
            "motivation": scenario.get("motivation") or scenario.get("background", ""),
            "starting_complication": scenario.get("starting_complication") or "Canon pressures remain active, but the player's choices can change what follows.",
        }
        normalized["growth_profile"] = {
            "aptitude": scenario.get("aptitude") or "Established canon potential",
            "learning_rate": float(scenario.get("learning_rate", 1.0) or 1.0),
            "starting_strengths": list((scenario.get("stat_minimums") or {}).keys())[:3],
            "accelerators": ["Established training, relationships, and world-valid opportunities"],
            "constraints": ["Current mastery", "Chakra or resource limits", "Consequences and opposition"],
            "explanation": "Growth follows this character's established capabilities, training, decisions, and changed timeline.",
        }
        normalized["generated_ability"] = None
        normalized["hidden_class"] = None
        normalized["class_profile"] = copy.deepcopy(scenario.get("class_profile")) if isinstance(scenario.get("class_profile"), dict) else {}
        if world == "Naruto":
            established = scenario.get("special_patch") if isinstance(scenario.get("special_patch"), dict) else {}
            legacy_host = established.get("Jinchuriki", "")
            normalized["jinchuriki_profile"] = normalize_jinchuriki_profile(
                normalized.get("jinchuriki_profile"), legacy=legacy_host,
                background=scenario.get("background", ""), seed=scenario.get("id", ""),
            )
            known_jutsu = " ".join(map(str, established.get("Known Jutsu", []))) + " " + " ".join(map(str, (scenario.get("skills") or {}).keys()))
            if scenario.get("id") in {"naruto_birth", "naruto_graduation"}:
                known_natures = ["Wind Release"]
            elif "Five Basic Nature Transformations" in known_jutsu:
                known_natures = ["Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release"]
            else:
                known_natures = [nature for nature in ("Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release") if nature in known_jutsu]
            normalized["naruto_affinity_profile"] = normalize_chakra_affinity_profile(
                None, legacy=known_natures or established.get("Nature Affinity", ""),
                background=scenario.get("background", ""), seed=scenario.get("id", ""),
                canon_character_id=scenario.get("id", ""),
            )
            if scenario.get("id") in {"naruto_birth", "naruto_graduation"}:
                normalized["naruto_affinity_profile"]["discovery_status"] = "Latent / not yet tested"
        if world == "Jujutsu Kaisen":
            established = scenario.get("special_patch") if isinstance(scenario.get("special_patch"), dict) else {}
            technique = str(established.get("Innate Technique") or "None")
            restriction = str(established.get("Heavenly Restriction") or "None")
            if restriction.lower() not in {"", "none", "unknown", "unachieved"}:
                slot = {
                    "slot_type":"Heavenly Restriction", "name":restriction,
                    "governing_rule":"A binding condition present from birth exchanges cursed-energy potential for extraordinary physical capability.",
                    "activation":"Always active; it is a bodily condition, not an invoked technique.",
                    "sacrifice":restriction, "enhancement":"Exceptional physical strength, speed, perception and cursed-tool aptitude.",
                    "limitations":"No innate cursed technique; cursed-energy use is limited by the established restriction.",
                    "weaknesses":"Injury, exhaustion, superior force and techniques that bypass physical defenses still matter.",
                    "growth_path":"Condition the body, sharpen perception and master a wider range of cursed tools.",
                    "applications":[], "power_grade":str(established.get("Grade") or "Canon-established"),
                }
            elif technique.lower() not in {"", "none", "none awakened", "unknown", "unachieved"}:
                applications = [{"name":name, "effect":detail.get("description", "")}
                                for name, detail in (scenario.get("skills") or {}).items() if isinstance(detail, dict)]
                slot = {
                    "slot_type":"Innate Cursed Technique", "name":technique,
                    "governing_rule":f"The canon-established governing rule of {technique} applies at this point in the timeline.",
                    "activation":"Uses cursed energy through the technique's established activation and interpretation.",
                    "targets":"Targets permitted by its currently mastered applications.", "applications":applications,
                    "limitations":"Only applications established by this starting point are mastered; cursed-energy cost, output, control and counters still apply.",
                    "weaknesses":"Technique matchups, depleted cursed energy, disrupted activation and the user's current mastery remain relevant.",
                    "growth_path":"Develop canon-valid extensions and allow player choices to create coherent new applications.",
                    "domain_potential":"A Domain Expansion becomes available only when this character's established mastery or later play supports it.",
                    "power_grade":str(established.get("Grade") or "Canon-established"),
                }
            else:
                # Yuji's opening is a deliberate canon exception: Sukuna's
                # vessel physiology is neither an innate technique nor a
                # Heavenly Restriction, and the UI should say that plainly.
                slot = {
                    "slot_type":"Vessel Physiology", "name":str(established.get("Vessel") or "Exceptional Vessel"),
                    "governing_rule":"An exceptionally stable soul and body can contain Sukuna without supplying an innate technique of its own.",
                    "activation":"Passive until Sukuna's finger is consumed; cursed-energy reinforcement must still be learned.",
                    "applications":[], "limitations":"Provides containment and physical potential, not automatic control of Sukuna or a personal cursed technique.",
                    "weaknesses":"The incarnated curse remains an intelligent hostile presence with his own motives.",
                    "growth_path":"Learn cursed-energy control, preserve control of the body and develop Yuji's own fighting method.",
                    "power_grade":"Exceptional vessel",
                }
            normalized["jjk_birth_slot"] = normalize_birth_slot_package(slot)
        package = {
            "position": scenario.get("position", ""), "affiliations": copy.deepcopy(scenario.get("affiliations") or []),
            "reputation": copy.deepcopy(scenario.get("reputation") or {}), "special_patch": copy.deepcopy(scenario.get("special_patch") or {}),
            "quests": copy.deepcopy(scenario.get("starting_quests") or []), "conditions": copy.deepcopy(scenario.get("conditions") or []),
            "knowledge": copy.deepcopy(scenario.get("knowledge") or []), "contacts": copy.deepcopy(scenario.get("contacts") or []),
            "class_profile": copy.deepcopy(scenario.get("class_profile") or {}),
            "race": scenario.get("race", ""),
        }
        normalized["start_package"] = package
        normalized["hp_max"], normalized["resource_max"] = self.derive_pools(world, stats)
        if normalized.get("jinchuriki_profile"):
            multiplier = float(normalized["jinchuriki_profile"].get("reserve_multiplier", 1.0) or 1.0)
            normalized["resource_max"] = max(normalized["resource_max"], int(round(normalized["resource_max"] * multiplier)))
        power = power_profile_for(world, stats, scenario.get("archetype", ""))
        normalized["power_band"] = power["world_overall"]["name"]
        normalized["power_notice"] = power.get("interpretation", "") if power.get("lopsided") else ""
        return normalized

    def preview_campaign(self, name, world, difficulty, background, appearance_desc, custom_world, origin, archetype, stats, start_location="", start_note="", canon_character_id="", starting_era_id="", jjk_guarantee_strong=False, jjk_curse_grade="", hxh_start_with_nen=False, one_piece_devil_fruit=False, one_piece_haki_types=None, overgeared_class_start="narrative"):
        if world not in WORLD_DATA:
            raise ValueError("Unknown world selected.")
        if difficulty not in DIFFICULTIES:
            raise ValueError("Unknown difficulty selected.")
        wd, canon = WORLD_DATA[world], timeline_for(world)
        scenario = self.canon_character_scenario(world, canon_character_id) if canon_character_id else None
        if scenario:
            name, background, appearance_desc = scenario["name"], scenario.get("background", ""), scenario.get("appearance", "")
            origin, archetype, start_location = scenario.get("origin", origin), scenario.get("archetype", archetype), scenario.get("location", start_location)
        # An original character can begin in a different era of the same
        # world instead of always the default anchor — a canon-character
        # scenario (which already fixes its own start_day) always wins.
        if scenario:
            era, start, start_package, start_warnings = None, str(start_location or wd["start"]).strip(), {}, []
        else:
            start, era, start_package, start_warnings = self.resolve_original_start(
                world, origin, archetype, start_location, start_note, starting_era_id,
            )
        rolled = self.roll_starting_stats(world, archetype, stats or {})
        profile = self.infer_starting_profile(world, origin, archetype, background, rolled, start_location=start,
                                              allow_starting_specials=not bool(scenario), jjk_guarantee_strong=jjk_guarantee_strong,
                                              jjk_curse_grade=jjk_curse_grade, hxh_start_with_nen=hxh_start_with_nen,
                                              one_piece_devil_fruit=one_piece_devil_fruit,
                                              one_piece_haki_types=one_piece_haki_types,
                                              overgeared_class_start=overgeared_class_start)
        if scenario:
            profile = self.normalize_canon_start_profile(world, scenario, profile)
        else:
            profile = self.apply_start_package_to_profile(world, profile, start_package)
        if scenario:
            start_day, canon_anchor = int(scenario.get("start_day")), scenario.get("background")
        elif era:
            start_day, canon_anchor = int(era["start_day"]), era["anchor"]
        else:
            start_day, canon_anchor = int(canon.get("start_day", -7)), canon.get("anchor", "")
        return {
            "name": str(name or "Traveler").strip() or "Traveler", "world": world,
            "difficulty": difficulty, "tagline": wd["tagline"], "rules": wd["rules"],
            "origin": origin, "archetype": archetype, "start_location": start,
            "start_day": start_day, "canon_anchor": canon_anchor,
            "abilities": profile["stats"], "resource": wd["resource"], "appearance": appearance_desc,
            "starting_profile": profile, "uses_xp": uses_xp_for(world, custom_world),
            "race": profile.get("race", ""), "race_options": WORLD_RACES.get(world, {}).get("options", []),
            "background": profile.get("expanded_background", background),
            "background_details": profile.get("background_details", {}),
            "growth_profile": profile.get("growth_profile", {}), "custom_world": custom_world,
            "world_pack_id": wd.get("pack_id", "builtin"),
            "canon_character": scenario,
            "world_primer": world_primer_for(world, custom_world),
            "starting_era": era, "starting_era_options": starting_eras_for(world),
            "start_warnings": start_warnings,
            "jjk_guarantee_strong": bool(jjk_guarantee_strong), "jjk_curse_grade": jjk_curse_grade,
            "hxh_start_with_nen": bool(hxh_start_with_nen),
            "one_piece_devil_fruit": bool(one_piece_devil_fruit),
            "one_piece_haki_types": list(one_piece_haki_types or []),
            "overgeared_class_start": overgeared_class_start,
        }

    def new_campaign(self, name, world, difficulty, background, appearance_desc, custom_world, origin, archetype, stats, start_location="", start_note="", preview_stats=None, preview_profile=None, canon_character_id="", starting_era_id="", age="", jjk_guarantee_strong=False, jjk_curse_grade="", hxh_start_with_nen=False, one_piece_devil_fruit=False, one_piece_haki_types=None, overgeared_class_start="narrative"):
        wd = WORLD_DATA[world]
        scenario = self.canon_character_scenario(world, canon_character_id) if canon_character_id else None
        if scenario:
            name, background, appearance_desc = scenario["name"], scenario.get("background", ""), scenario.get("appearance", "")
            origin, archetype, start_location = scenario.get("origin", origin), scenario.get("archetype", archetype), scenario.get("location", start_location)
            era, start, start_package = None, start_location.strip() or wd["start"], {}
        else:
            start, era, start_package, _ = self.resolve_original_start(
                world, origin, archetype, start_location, start_note, starting_era_id,
            )
        rolled = copy.deepcopy(preview_stats) if isinstance(preview_stats, dict) else self.roll_starting_stats(world, archetype, stats)
        profile = copy.deepcopy(preview_profile) if isinstance(preview_profile, dict) else self.infer_starting_profile(
            world, origin, archetype, background, rolled, start_location=start,
            allow_starting_specials=not bool(scenario), jjk_guarantee_strong=jjk_guarantee_strong,
            jjk_curse_grade=jjk_curse_grade, hxh_start_with_nen=hxh_start_with_nen,
            one_piece_devil_fruit=one_piece_devil_fruit, one_piece_haki_types=one_piece_haki_types,
            overgeared_class_start=overgeared_class_start,
        )
        if scenario:
            profile = self.normalize_canon_start_profile(world, scenario, profile)
        else:
            profile = self.apply_start_package_to_profile(world, profile, start_package)
        profile_stats = profile.get("stats") if isinstance(profile.get("stats"), dict) else rolled
        hp_max, resource_max = self.derive_pools(world, profile_stats)
        if isinstance(profile.get("jinchuriki_profile"), dict):
            multiplier = float(profile["jinchuriki_profile"].get("reserve_multiplier", 1.0) or 1.0)
            resource_max = max(resource_max, int(round(resource_max * multiplier)))
        with self.lock:
            self.state = copy.deepcopy(BASE_STATE)
            self.state.update(
                name=name.strip() or "Traveler", world=world, difficulty=difficulty,
                background=profile.get("expanded_background", background), appearance_desc=appearance_desc, custom_world=custom_world,
                race=profile.get("race", "") if world_supports_races(world) else "",
                calendar_epoch="",  # Fixed world civil epoch; never the host computer date.
                location=start, resource_name=wd["resource"],
                factions=copy.deepcopy(wd["factions"]), reputation=copy.deepcopy(wd["factions"]),
                special=copy.deepcopy(wd["special"]), discovered_locations=[start],
                stats=copy.deepcopy(profile_stats), skills=copy.deepcopy(profile.get("skills", {})),
                titles=copy.deepcopy(profile.get("titles", [])), equipment=copy.deepcopy(profile.get("equipment", {})),
                class_profile=copy.deepcopy(profile.get("hidden_class") or profile.get("class_profile") or {}),
                hp=hp_max, hp_max=hp_max, resource=resource_max, resource_max=resource_max,
                starting_power_band=profile.get("power_band", "Average beginner"),
                starting_power_notice=profile.get("power_notice", ""),
                campaign_id=secrets.token_hex(8),
                campaign_created_version=APP_VERSION, campaign_last_saved_version=APP_VERSION,
                schema_version=BASE_STATE.get("schema_version", 5), world_pack_id=wd.get("pack_id", "builtin"),
                player_identity={"mode": "canon" if scenario else "original", "canon_character_id": scenario.get("id", "") if scenario else "", "canon_gravity": True},
                creation_locks=copy.deepcopy(profile.get("background_locks") or self.background_locked_facts(world, background)),
            )
            ex = expansion_for(world)
            prefix = f"Origin: {origin}\nStarting archetype: {archetype}\n"
            if start_note.strip():
                prefix += start_note.strip() + "\n"
            self.state["background"] = (prefix + self.state.get("background", "")).strip()
            if ex.get("tracks_currency", True):
                self.state["currency"] = {"name": ex["currency"], "amount": profile.get("starting_currency", ex.get("currency_baseline", 250)), "tracked": True}
            else:
                self.state["currency"] = {"name": ex.get("currency", "Money"), "amount": 0, "tracked": False}
                self.state["currencies"] = {}
            self.state["special"]["Origin"] = origin
            self.state["special"]["Archetype"] = archetype
            self.state["special"]["Background Details"] = copy.deepcopy(profile.get("background_details", {}))
            self.state["special"]["Growth Profile"] = copy.deepcopy(profile.get("growth_profile", {}))
            normalize_tuning(self.state)
            if isinstance(profile.get("generated_ability"), dict):
                self.state["special"]["Starting Ability"] = copy.deepcopy(profile["generated_ability"])
            if isinstance(profile.get("naruto_lineage_profile"), dict):
                lineage = copy.deepcopy(profile["naruto_lineage_profile"])
                label = "Dōjutsu Profile" if lineage.get("category") == "Dōjutsu" else "Kekkei Genkai Profile"
                self.state["special"][label] = lineage
                self.state["special"][lineage.get("category", "Kekkei Genkai")] = lineage.get("name", "Unawakened Bloodline")
            if isinstance(profile.get("jinchuriki_profile"), dict) and profile["jinchuriki_profile"]:
                host = copy.deepcopy(profile["jinchuriki_profile"])
                self.state["special"]["Jinchūriki Profile"] = host
                self.state["special"]["Jinchuriki"] = f"{host.get('beast', 'Tailed Beast')} — {host.get('mastery', 'Unmastered')}"
            if isinstance(profile.get("naruto_affinity_profile"), dict) and profile["naruto_affinity_profile"]:
                affinity = copy.deepcopy(profile["naruto_affinity_profile"])
                host = profile.get("jinchuriki_profile") if isinstance(profile.get("jinchuriki_profile"), dict) else {}
                if host:
                    affinity["external_natures"] = copy.deepcopy(host.get("nature_transformations", []))
                self.state["special"]["Chakra Affinity Profile"] = affinity
                self.state["special"]["Nature Affinity"] = affinity.get("primary", "Unknown")
            if isinstance(profile.get("hidden_class"), dict):
                self.state["special"]["Hidden Class"] = copy.deepcopy(profile["hidden_class"])
            if world == "One Piece":
                if isinstance(profile.get("devil_fruit_profile"), dict):
                    fruit = copy.deepcopy(profile["devil_fruit_profile"])
                    self.state["special"]["Devil Fruit Profile"] = fruit
                    self.state["special"]["Devil Fruit"] = fruit.get("name", "Unknown Devil Fruit")
                if isinstance(profile.get("haki_profile"), dict):
                    haki = copy.deepcopy(profile["haki_profile"])
                    self.state["special"]["Haki Profile"] = haki
                    self.state["special"]["Haki"] = {name:int((row or {}).get("mastery", 0) or 0) for name, row in haki.items()}
            if world == "Hunter x Hunter" and isinstance(profile.get("nen_profile"), dict):
                nen = copy.deepcopy(profile["nen_profile"])
                self.state["special"]["Nen Profile"] = nen
                self.state["special"]["Nen Access"] = nen.get("visibility", "Undiscovered")
                self.state["special"]["Nen Category"] = nen.get("category", "Unknown")
                self.state["special"]["Ten"] = int(nen.get("ten", 0) or 0)
                self.state["special"]["Zetsu"] = int(nen.get("zetsu", 0) or 0)
                self.state["special"]["Ren"] = int(nen.get("ren", 0) or 0)
                self.state["special"]["Hatsu"] = (nen.get("hatsu_profile") or {}).get("name", "Undeveloped")
            self.state["portrait_traits"] = [appearance_desc] if appearance_desc.strip() else []
            canon = timeline_for(world)
            if scenario:
                start_day, anchor_text = int(scenario.get("start_day")), scenario.get("background")
            elif era:
                start_day, anchor_text = int(era["start_day"]), era["anchor"]
            else:
                start_day, anchor_text = int(canon.get("start_day", -7)), canon.get("anchor", "Before the main story")
            self.state["canon_day"] = start_day
            self.state["canon_time_minutes"] = start_day * 1440 + 480
            self.state["canon_anchor"] = anchor_text
            self.state["canon_events_fired"] = []
            # This campaign's own start_day is Year 1/Month 1/Day 1 for calendar
            # purposes, not necessarily the world's generic default — a canon
            # character (e.g. Naruto at birth, start_day -4380) or a chosen
            # starting era begins far from the default and must anchor its own
            # calendar, or every date the player sees reads as a nonsense
            # negative year.
            self.state["calendar_anchor_day"] = start_day
            self.state['atlas_start_day'] = start_day
            self.state["world_time"] = f"{format_calendar_date(world, start_day, self.state.get('calendar_epoch'), start_day)} — Morning, 08:00"
            clean_anchor = str(self.state["canon_anchor"] or "").strip().rstrip(" .!?")
            self.state["timeline"] = [f"{self.state['name']} enters the story at {start}. {clean_anchor}." ]
            if scenario:
                self.state["age"] = scenario.get("age", "")
                self.state["campaign_canon"] = [{"turn": 0, "type": "canon_character_start", "text": f"The player assumes full control of {scenario['name']} at {scenario['label']}."}]
            # An explicit typed age always wins, even over a canon scenario's
            # own default — the player is deliberately choosing an unusual
            # combination on purpose (see the "odd combos for fun" note in
            # the UI), not making a mistake to be corrected. Left blank, the
            # existing opening() needs_age path already asks the AI to
            # invent a plausible age fitting the origin/archetype/background,
            # which is a better fit for "match the closest age" than a fixed
            # rule table would be.
            if str(age).strip():
                self.state["age"] = str(age).strip()
            initialize_age_tracking(self.state, reset=True)
            self.state["codex"] = [{"name": start, "type": "Location", "notes": "Starting location."}]
            host = self.state.get("special", {}).get("Jinchūriki Profile")
            if isinstance(host, dict) and host:
                self.state["codex"].append({
                    "name": host.get("beast", "Tailed Beast"), "type": "Tailed Beast",
                    "notes": "An independent being sealed within the host. Its full canon potential, current cooperation, seal, transformations, and drawbacks are tracked separately from ordinary jutsu.",
                })
            # Knowing a faction exists does not grant a private line to it.
            for faction_name in wd["factions"]:
                can_contact = faction_name in WORLD_PUBLIC_CONTACTS.get(world, set())
                self.ensure_contact(faction_name, "group", {
                    "status": "Known", "can_contact": can_contact,
                    "notes": ["A known major faction. A direct channel requires public access, membership, or an introduced contact."],
                })
            # A canon character start with a real established cast (see
            # MAJOR_CHARACTER_STARTS's seed_npcs/seed_faction_rosters)
            # gets that cast mechanically seeded into tracked state right
            # here — not just described in prose background text and left
            # for the AI to infer correctly every session. This is the
            # same "prompt alone is unreliable, pair it with something
            # real" pattern the currency/HP/quest-completion detectors
            # already established: a player starting as Yahiko should
            # have Nagato and Konan as real tracked companions and Jiraiya
            # as a real tracked mentor from turn one, not a random
            # AI-invented training partner because nothing concrete told
            # it who was actually there.
            if scenario:
                for npc in scenario.get("seed_npcs", []):
                    npc_name = str(npc.get("name") or "").strip()
                    if not npc_name:
                        continue
                    self.state.setdefault("npc_memories", {})[npc_name] = {
                        "attitude": npc.get("attitude", "Ally"),
                        "goal": npc.get("goal", ""),
                        "last_known_location": npc.get("last_known_location", start),
                        "recurring": True,
                    }
                    last_known = str(npc.get("last_known_location", start))
                    contactable = npc.get("can_contact")
                    if contactable is None:
                        contactable = last_known.lower() not in {"unknown", "deceased"}
                    self.ensure_contact(npc_name, "person", {"status": "Known", "can_contact": bool(contactable)})
                    if npc.get("is_companion"):
                        self.state.setdefault("companions", []).append({"name": npc_name, "role": npc.get("goal", "")})
                rosters = scenario.get("seed_faction_rosters")
                if isinstance(rosters, dict) and rosters:
                    self.state["faction_rosters"] = copy.deepcopy(rosters)
                self.state["position"] = str(scenario.get("position") or self.state.get("position") or "")
                self.state["affiliations"] = copy.deepcopy(scenario.get("affiliations") or [])
                for faction, standing in (scenario.get("reputation") or {}).items():
                    self.state.setdefault("reputation", {})[faction] = standing
                if scenario.get("title"):
                    self.state["titles"] = [scenario["title"]]
                if scenario.get("active_canon_event"):
                    # A canon-character preset can begin inside the event
                    # instead of one beat before it. Mark it fired so the
                    # next Advance continues the live scene rather than
                    # announcing the same timeline entry again.
                    active_title = str(scenario["active_canon_event"])
                    self.state["active_canon_event"] = active_title
                    self.state["active_event_context"] = str(scenario.get("active_event_context") or "")
                    self.state["active_event_prompt"] = str(scenario.get("active_event_prompt") or "")
                    self.state["canon_events_fired"] = [active_title]
                if isinstance(scenario.get("opening_combat"), dict):
                    # Ichigo's only selectable canon start begins after the
                    # power transfer, while Fishbone D is still attacking.
                    # Seed the fight mechanically so the opening can never
                    # turn it into a passive modal or a negotiable setup.
                    self.state["combat"] = copy.deepcopy(scenario["opening_combat"])
            self.apply_start_package_to_state(profile.get("start_package", start_package))
            if world == "Overgeared":
                reception = str(profile.get("overgeared_class_start") or overgeared_class_start or "narrative").lower()
                preferred = profile.get("preferred_class_route") if isinstance(profile.get("preferred_class_route"), dict) else {}
                awarded = self.state.get("class_profile") if isinstance(self.state.get("class_profile"), dict) else {}
                is_unclassed = str(awarded.get("name") or "").lower() in {"", "beginner", "unclassed"}
                if is_unclassed:
                    self.state["class_profile"] = copy.deepcopy(profile.get("class_profile") or {
                        "name":"Beginner", "kind":"Unclassed Satisfy Player", "rank":"Common",
                        "class_type":"Unassigned", "growth_path":"Receive a class through the story.",
                    })
                    self.state["special"]["Class"] = "Beginner"
                    self.state["special"]["Class Rarity"] = "Common"
                else:
                    self.state["special"]["Class"] = awarded.get("name", "Hidden Class")
                    self.state["special"]["Class Rarity"] = awarded.get("rank", "Hidden")
                satisfy = self.state["special"].setdefault("Satisfy Profile", {})
                satisfy.update({
                    "primary_class": self.state["special"]["Class"],
                    "class_rarity": self.state["special"]["Class Rarity"],
                    "preferred_class_route": str(preferred.get("name") or archetype or "Adventurer"),
                    "class_reception": "Pending narrative class change" if is_unclassed else "Received before campaign start",
                })
                self.state.setdefault("overgeared_system", {})["class_reception"] = {
                    "status": "pending" if is_unclassed else "received",
                    "preferred_route": satisfy["preferred_class_route"],
                    "source": "Choose through the Chronicle" if is_unclassed else "Character creation option",
                    "received_class": "" if is_unclassed else self.state["special"]["Class"],
                }
            # The origin package supplies a conservative default.  The
            # explicit creation toggle and authored latent profile are the
            # final authority for whether Nen begins awakened.
            if world == "Hunter x Hunter" and isinstance(profile.get("nen_profile"), dict):
                nen = copy.deepcopy(profile["nen_profile"])
                latent = nen.pop("latent_hatsu_profile", None)
                latent_category = nen.pop("latent_category", None)
                if isinstance(latent, dict):
                    self.state["_latent_nen_profile"] = {
                        "hatsu_profile": latent,
                        "category": latent_category or "Enhancement",
                    }
                self.state["special"].update({
                    "Nen Profile": nen,
                    "Nen Access": nen.get("visibility", "Undiscovered"),
                    "Nen Category": nen.get("category", "Unknown"),
                    "Ten": int(nen.get("ten", 0) or 0),
                    "Zetsu": int(nen.get("zetsu", 0) or 0),
                    "Ren": int(nen.get("ren", 0) or 0),
                    "Hatsu": (nen.get("hatsu_profile") or {}).get("name", "Undeveloped"),
                })
            if world == "Bleach":
                release = profile.get("bleach_release_profile")
                if isinstance(release, dict):
                    release_stage = str(release.get("stage") or "Dormant")
                    owns_shikai = release_stage in {"Shikai", "Bankai"}
                    self.state["special"].update({
                        "Zanpakuto": release.get("name", "Named Zanpakuto"), "Zanpakuto Profile": copy.deepcopy(release),
                        "Shikai": f"Achieved — {release.get('shikai_name', release.get('name', 'Named release'))}" if owns_shikai else "Unachieved",
                        "Bankai": release.get("bankai_name", "Achieved") if release_stage == "Bankai" else "Unachieved",
                    })
                    blade_name = str(release.get("name") or "").strip()
                    blade_is_known = release_stage in {"Shikai", "Bankai"} or bool((self.state.get("creation_locks") or {}).get("ability_name"))
                    if blade_is_known and blade_name and blade_name.lower() not in {"unknown", "unnamed", "unnamed asauchi"}:
                        gear = self.state.setdefault("equipment", {})
                        gear["Weapon"] = re.sub(r"\bUnnamed Asauchi\b", blade_name, str(gear.get("Weapon") or "Unnamed Asauchi"), flags=re.I)
                has_shikai = str(self.state["special"].get("Shikai", "")).lower() not in {"", "unachieved", "none"}
                has_bankai = str(self.state["special"].get("Bankai", "")).lower() not in {"", "unachieved", "none"}
                self.state["prerequisite_tracks"] = copy.deepcopy(
                    profile.get("prerequisite_tracks") or zanpakuto_tracks(has_shikai, has_bankai)
                )
                # Bleach acknowledges Kan and Yen in the fiction without
                # turning either into a permanent economy minigame.
                self.state["currency"] = {"name": "Kan / Yen", "amount": 0, "tracked": False}
                self.state["currencies"] = {}
                self.state["purchase_offer"] = None
                self.state["purchase_offers"] = []
            if world == "Jujutsu Kaisen" and isinstance(profile.get("jjk_birth_slot"), dict):
                initialize_jjk_state(self.state, profile["jjk_birth_slot"], origin,
                                     profile.get("jjk_curse_grade", jjk_curse_grade), profile.get("jjk_curse_identity"))
                self.state["currency"] = {"name":"Yen", "amount":0, "tracked":False}
                self.state["currencies"] = {}
            ensure_currency_state(self.state)
            record_opening_currency(self.state)
            normalize_world_progression(self.state)
            normalize_world_depth(self.state)
            initialize_lit_systems(self.state)
            if world == "Overgeared" and isinstance(profile.get("standard_class_profile"), dict):
                starter = profile["standard_class_profile"]
                system = self.state.setdefault("overgeared_system", {})
                quest = starter.get("quest") if isinstance(starter.get("quest"), dict) else {}
                known_quests = {str(x.get("name")) for x in self.state.get("quests", []) if isinstance(x, dict)}
                if quest and quest.get("name") not in known_quests:
                    self.state.setdefault("quests", []).append({
                        "name": quest["name"], "status": "Active",
                        "explanation": f"Your {starter['name']} class has recognized a first class-specific route: {quest['goal']}",
                        "current_knowledge": [quest["goal"]], "clear_conditions": [quest["goal"]],
                        "rewards": [quest["reward"]], "source": f"{starter['name']} class",
                    })
                if starter.get("companion"):
                    companion = copy.deepcopy(starter["companion"])
                    known = {str(x.get("name")) for x in self.state.get("companions", []) if isinstance(x, dict)}
                    if companion["name"] not in known:
                        self.state.setdefault("companions", []).append(companion)
                    system.setdefault("companion_contracts", {})[companion["name"]] = copy.deepcopy(companion)
                    self.state.setdefault("npc_memories", {})[companion["name"]] = {
                        "attitude": "Bonded", "goal": companion["growth_path"], "last_known_location": start,
                        "recurring": True, "opinion_of_player": "Newly bonded partner",
                    }
            # A fresh campaign always has useful direction, even before the
            # opening narration model is available.
            from starting_holdings import initialize_starting_holdings
            starting_land_facts = initialize_starting_holdings(self.state)
            self.state["suggested_actions"] = self.guided_suggestions([])
            motivation = (profile.get("background_details") or {}).get("motivation", "")
            self.state["memory_updates"] = {
                "established_facts": [f"{self.state['name']} begins in {start} as a {origin} {archetype}."] + starting_land_facts,
                "player_goals": [motivation] if motivation else [],
            }
            update_narrative_memory(BASE_STATE, self.state, "Campaign beginning", "")
            self.checkpoints = []
            self.history = []
            self.story_log = []
            self.system_log = []
            self.campaign_active = True
            self.append(f"[CAMPAIGN START]\n{self.state['name']} — {world} — {difficulty}\n{wd['tagline']}", "system")
        return self.public_state()

    def opening(self):
        needs_background = not self.state.get("background", "").strip()
        needs_appearance = not self.state.get("appearance_desc", "").strip()
        needs_name = self.state.get("name", "").strip().lower() in ("", "traveler")
        needs_age = not str(self.state.get("age", "")).strip()
        requirements = []
        requirements.append("If the background establishes present ownership/rulership (not an ambition or merely clan membership), preserve any initialized political_regions and record any remaining holdings with controller, exact anchor, scale and board/realm where applicable; set polity_state[controller].player_led=true. Small unnamed estates start at one hex, not a country. If the place is new, add custom_locations with world-consistent coordinates. Becoming Hokage grants village command, not the Land of Fire. Never grant territory just for a powerful class, famous name, inherited technique or future canon achievement.")
        if needs_name:
            requirements.append("The player didn't choose a name — invent one that fits the world, origin and archetype, and set it in state_patch.name. Never leave it as 'Traveler'.")
        if needs_age:
            requirements.append("The player's age is unset — invent a plausible age fitting the origin/archetype/world and set it in state_patch.age (a number).")
        if needs_background:
            requirements.append("The player left their background blank — invent a plausible backstory consistent with their origin, archetype and world, and set it in state_patch.background.")
        if needs_appearance:
            requirements.append("The player left their appearance blank — invent a fitting physical description consistent with origin/archetype/world, and write the ACTUAL descriptive sentence into state_patch.appearance_desc as a real string (e.g. 'A lean youth with gray eyes and a scar along his jaw') — never a placeholder, a reference to another field, or a note saying it's set elsewhere. portrait_traits is a separate short list of the same distinctive details, in addition to (not instead of) appearance_desc.")
        requirements.append("Treat every ability, class, education, social status, possession and trait claimed in the player's background as an authoritative starting fact unless it directly contradicts the chosen world. Background Details, Growth Profile, Starting Ability, Hidden Class, and class_profile are authoritative starting context; preserve and deepen them rather than erasing them. The degree of the wording matters: talented, prodigy, immense, godlike and immeasurable describe sharply different starting scales. Very powerful starts are allowed and must not be normalized downward.")
        if world_supports_races(self.state.get("world", "Custom World")):
            options = WORLD_RACES.get(self.state.get("world"), {}).get("options", [])
            requirements.append(
                f"This world distinguishes race/species. state.race currently holds only a quick keyword guess ({self.state.get('race', 'Human')}) made before you could actually read the background — confirm or correct it in state_patch.race. "
                f"Established races in this world include: {', '.join(options)}. If the player's background clearly describes something else, invent a specific, fitting race name instead of forcing it into one of these — it just needs to logically follow this world's actual rules for what that race can do (a slime that breathes fire needs an in-fiction reason a human turned monster wouldn't). Keep it a short name (1-3 words), not a sentence."
            )
        requirements.append("If the player's original background was vague, complete the missing upbringing, family or community context, training history, formative event, important relationship, motivation, and complication. Keep supplied facts unchanged, make the additions setting-valid, and return the enriched account in state_patch.background.")
        countdown = self.canon_countdown()
        if countdown.get("available"):
            requirements.append(
                f"The opening is fixed at {self.state.get('canon_anchor', 'the selected starting era')}. "
                f"The next dated canon event, {countdown.get('title')}, is still {countdown.get('label')}. "
                "Do not move it forward, begin it now, or imply that it already happened. Open only in the selected era's present-day situation."
            )
        requirements.append("Every starting ability and hidden-class signature skill must remain named in state_patch.skills and be explainable through its in-world origin, effect, limitation or cost, growth path, and canon_balance. Introduce it naturally in the opening; it is a real capability, not a rumor or disposable plot hook. Preserve class_profile, its original non-canon identity, and its mechanical stat bonuses. A unique generated class or bloodline is as real as a canon one and may develop new applications whenever its recorded rules and the narrative permit.")
        if self.state.get("world") == "Overgeared" and str(((self.state.get("overgeared_system") or {}).get("class_reception") or {}).get("status") or "").lower() == "pending":
            requirements.append("This Satisfy character deliberately begins as the Beginner class. Their archetype is only a preferred direction. Do not award that class in the opening; establish a concrete class-change lead, quest, NPC, location, item, achievement, or hidden-condition clue that they can choose to pursue through the story.")
        requirements.append("Open with a concrete situation and at least one actionable lead tied to this location, background, goal or upcoming world pressure. End with exactly 3 optional next actions: follow the lead, prepare/progress, or explore an alternate hook.")
        p = {"task": "opening", "state": self.task_state_for_ai("opening"), "requirements": requirements,
             "schema": {"narrative": "1 short paragraph, 3-5 sentences, ending with an open situation",
                        "state_patch": "persistent changes including appearance/portrait_traits when relevant",
                        "events": "system notifications", "timeline_event": "major event or empty",
                        "suggested_actions": ["exactly 3 optional, contextual next actions, each naming a specific person/place/thread just established in this opening — not a generic template. At least one clear lead. A suggestion can span more than a moment if that's genuinely what it calls for."]}}
        # The opening asks for more than a routine turn — name/age/background/
        # appearance/abilities plus narrative and state_patch all at once —
        # so it gets a bigger budget than a normal resolution. Truncated
        # responses are now repaired automatically (see repair_truncated_json),
        # so this no longer needs to be oversized purely as insurance against
        # a cut-off reply.
        data = self.request_with_narrative(self.task_context("opening", "campaign opening starting location origin archetype"), p, 1500)
        return self.apply_resolution(data, is_opening=True)
