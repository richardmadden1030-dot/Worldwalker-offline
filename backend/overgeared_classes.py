"""Canon-informed Satisfy class design without turning every turn into lore bloat.

The catalog is names-only design precedent gathered from the Overgeared class
index.  It is supplied to the model only when a class is actually being
created or transformed.  Ordinary turns use the compact family rules below.
"""
from __future__ import annotations

import re
import copy


# Excludes wiki administration/template pages.  Keep the broad and strange
# entries: the point is to teach the generator that Satisfy supports far more
# than blacksmiths and ordinary combat jobs.
CANON_CLASS_NAMES = tuple(x.strip() for x in """
Accessory Maker
Acrobat
Alchemist
Apostle of Justice's Partner
Archer
Architect
Artisan
Assassin
Asura
Aura Master
Baal's Contractor
Beast Master
Beginner
Beriache's Knight
Beriache's Warrior
Berserker
Black Knight (Yatan Church)
Black Magician
Blacksmith
Blood Warrior
Blue Sky Rider
Bow Saint
Braham's Descendant
Builder
Chef
Cleaner
Commander
Construction Worker
Contractor Freed From Baal's Curse
Crusher
Dancing Death Knight Who Speaks Ancient Languages
Dancing Lich Who Distorts Space
Dark Magician
Dark Sorcerer
Death God
Debirion's Envoy
Demon Slayer
Demon World Noble
Destroyer Skeleton Clown
Destroyer Skeleton Dancer
Destroyer Skeleton Dancing Smith
Destroyer Skeleton Miner
Destroyer Skeleton Swordsman
Destruction Warrior
Doctor
Dragon Slayer
Duke of Wisdom
Dungeon Maker
Duplicator
Explosion Sorcerer
Farmer
Fire Magician
Fisherman
Flow Master
Goddess' Agent
Great Magician
Guardian Knight
Guardian of Light
Gunman
Hidden Sword
Ice Mystic
Illusionist
Impregnable Fortress
Knight
Legendary Assassin
Legendary Blacksmith
Legendary Farmer
Legendary Great Magician
Legendary Knight
Legendary Martial Artist
Legendary Painter
Legendary Scientist
Legendary Spearman
Legendary Tailor
Lightning Swordsman
Linker
Magic Spearman
Magic Swordsman
Magic Swordsman of the Epics
Magician
Martial Artist
Martial God Follower
Master of Swiftness
Master of the Flow
Merchant
Miner
Mixed Magician
Monk
Monster Discerner
Mumud's Successor
Necromancer
Orator
Overgeared God
Overgeared God Church's Messenger
Pagma's Successor
Painter
Paladin
Pet Master
Povia's Successor
Priest (Rebecca Church)
Prince
Qigong Master
Quick Draw Swordsman
Red Flame Archer
Red Sage
Restorer Skeleton Clown
Restorer Skeleton Dancer
Restorer Skeleton Dancing Smith
Restorer Skeleton Mage
Restorer Skeleton Miner
Rider
Saintess
Saintess' Knight
Saurabi
Scholar
Scientist
Sculptor
Shadow Master
Shadow Master's Student
Skeleton Bishop
Skeleton Dancer
Skeleton Destroyer
Skeleton Miner
Skeleton Restorer
Skeleton Sword Dancer
Skin Maker
Soldier
Soul Predator
Spear Knight
Spearman
Spiritualist
Steel Farmer
Storm Magician
Summoner
Sword Saint
Swordsman
Tactician
Tailor
Thief
Tyrant
War Commander
Warrior
White Swordsman
Wind Magician
Woodcutter
""".strip().splitlines())


CLASS_DESIGN_FAMILIES = {
    "Martial and weapon": "warriors, knights, martial artists, weapon specialists, riders, saints and growth-type successors",
    "Magic and supernatural": "elemental magicians, mystics, necromancers, spiritualists, illusionists and mixed magic paths",
    "Support and faith": "priests, healers, guardians, envoys, linkers, doctors and party-enabling specialists",
    "Command and society": "commanders, tacticians, nobles, merchants, orators, guild leaders and territorial rulers",
    "Companions and control": "summoners, pet masters, beast masters, contractors and minion-development paths",
    "Exploration and utility": "thieves, acrobats, monster discerners, scholars, fishermen and unusual condition-based jobs",
    "Production and creation": "blacksmiths, tailors, alchemists, architects, builders, artists, farmers, miners and scientists",
    "Hybrid and transformational": "magic swordsmen, production-combat hybrids, evolving classes, successors and classes born from exceptional deeds",
}


def infer_class_type(*values):
    text = " ".join(str(v or "") for v in values).lower()
    production = r"blacksmith|smith|craft|artific|tailor|alchem|architect|build|farmer|miner|paint|sculpt|chef|scient|maker|woodcut|production|wright"
    support = r"saintess|priest|healer|doctor|support|guardian|linker|envoy|messenger|restore|bishop"
    command = r"commander|tactician|prince|duke|noble|merchant|orator|leader|lord|king|guild|govern"
    magic = r"magic|magician|sorcer|mystic|necrom|spiritual|illusion|sage|caster|spell|element"
    companion = r"summon|pet master|beast master|contractor|minion|skeleton"
    utility = r"thief|acrobat|discerner|scholar|fisher|cleaner|duplicator|tracker|scout|explor"
    martial = r"warrior|knight|sword|spear|archer|assassin|martial|monk|gunman|crusher|rider|fighter|tank|paladin|berserker"
    matches = []
    for label, pattern in (("Production", production), ("Support", support),
                           ("Command / Social", command), ("Magic", magic),
                           ("Companion / Summoning", companion),
                           ("Exploration / Utility", utility), ("Combat", martial)):
        if re.search(pattern, text, re.I):
            matches.append(label)
    if len(matches) > 1:
        return "Hybrid: " + " + ".join(matches[:2])
    return matches[0] if matches else "Adventuring / Flexible"


def canon_class_prompt_reference():
    """Detailed reference used only during class authorship, not normal turns."""
    families = "; ".join(f"{name}: {detail}" for name, detail in CLASS_DESIGN_FAMILIES.items())
    names = ", ".join(CANON_CLASS_NAMES)
    return (
        "Satisfy class design families: " + families + ".\n"
        "Complete canon class-name precedent catalog (design inspiration only): " + names + ".\n"
        "Study the full range and structural variety, but do not copy a canon class, its signature mechanics, "
        "or acquisition story unless the player explicitly chose that canon class. Create a new class whose "
        "identity, rarity, features, limitations, quests, and evolution fit this character. Production is optional. "
        "Do not force crafting onto a combat, magic, support, command, social, summoning, or exploration concept."
    )


COMPACT_CLASS_GENERATION_RULE = (
    "Satisfy supports combat, weapon, magic, faith/support, command/social, companion/summoning, exploration/utility, "
    "production, and unusual hybrid or growth-type classes. Generated classes may combine these when the background "
    "supports it. Give every original class a distinct playstyle, class type, rarity, 2-4 coherent features, a named "
    "signature skill, limitations, class quests, advancement conditions, and later specializations. Crafting is never "
    "assumed unless the character actually follows a production path."
)


# Ordinary Satisfy classes are real playstyles, not placeholder labels. These
# packages stay local so creating or advancing a character costs no extra AI
# request. The narrator can still invent rarer evolutions when play earns one.
ROLE_STARTER_KITS = {
    "Warrior": ("Driving Slash", "Guarded Advance", "Press an enemy line without abandoning defense."),
    "Knight": ("Shield Intercept", "Vanguard Oath", "Protect an ally and hold the party's safest route."),
    "Swordsman": ("Measured Cut", "Flowing Footwork", "Study a skilled swordsman's timing in live combat."),
    "Spearman": ("Piercing Thrust", "Reach Control", "Use reach and formation spacing to deny an approach."),
    "Archer": ("Aimed Shot", "High-Ground Eye", "Scout a firing position before committing to a fight."),
    "Mage": ("Mana Bolt", "Spell Analysis", "Research a spell interaction at the local magic guild."),
    "Magic Swordsman": ("Mana Edge", "Arcane Rhythm", "Alternate a weapon technique and spell without breaking tempo."),
    "Assassin": ("Vital Mark", "Silent Step", "Observe a guarded route and identify a clean opening."),
    "Martial Artist": ("Revolving Strike", "Breath Control", "Challenge a local fighter to a technique-focused spar."),
    "Tank": ("Provoking Guard", "Unbroken Stance", "Hold enemy attention while an ally completes an objective."),
    "Priest/Healer": ("Minor Recovery", "Purifying Prayer", "Treat an injured resident and learn what caused the wound."),
    "Support": ("Quickening Chorus", "Shared Focus", "Coordinate two allies so their strengths cover each other."),
    "Summoner": ("Call Lumen Wisp", "Contract Command", "Train a formation with Lumen Wisp against a moving target."),
    "Tactician": ("Marked Formation", "Battlefield Read", "Draft a plan for a nearby party facing a known obstacle."),
    "Beast Master": ("Call Greyhorn Cub", "Pack Signal", "Track with Greyhorn Cub and reinforce the bond through a shared task."),
    "Explorer": ("Trail Sense", "Hazard Probe", "Map an overlooked route and record one concrete environmental clue."),
    "Merchant/Orator": ("Fair Appraisal", "Binding Pitch", "Negotiate a mutually useful deal with a named local contact."),
    "Blacksmith": ("Tempered Strike", "Material Reading", "Complete a practical commission whose result will be reused."),
    "Alchemist": ("Field Tonic", "Reaction Control", "Develop a reusable tonic for a specific local problem."),
    "Tailor": ("Reinforced Stitch", "Pattern Reading", "Create or improve gear for a named adventurer's actual needs."),
    "Architect": ("Rapid Brace", "Structural Survey", "Survey a damaged structure and propose a safe repair."),
}

ROLE_TYPES = {
    "Warrior": "Combat", "Knight": "Combat", "Swordsman": "Combat", "Spearman": "Combat",
    "Archer": "Combat", "Assassin": "Combat", "Martial Artist": "Combat", "Tank": "Combat",
    "Mage": "Magic", "Magic Swordsman": "Hybrid: Combat + Magic",
    "Priest/Healer": "Support", "Support": "Support", "Summoner": "Companion / Summoning",
    "Tactician": "Command / Social", "Beast Master": "Companion / Summoning",
    "Explorer": "Exploration / Utility", "Merchant/Orator": "Command / Social",
    "Blacksmith": "Production", "Alchemist": "Production", "Tailor": "Production", "Architect": "Production",
}

ROLE_ADVANCEMENTS = {
    "Warrior": ("Relentless Vanguard", "Warfront Champion"), "Knight": ("Guardian Oath", "Aegis Knight"),
    "Swordsman": ("Flow Duelist", "Blade Master"), "Spearman": ("Formation Lancer", "Sky-Piercing Spear"),
    "Archer": ("Terrain Marksman", "Far-Horizon Archer"), "Mage": ("Spell Architect", "Grand Magician"),
    "Magic Swordsman": ("Arcane Tempo", "Runeblade Master"), "Assassin": ("Patient Executioner", "Shadow Reaper"),
    "Martial Artist": ("Adaptive Striker", "Unbound Martial Master"), "Tank": ("Party Bulwark", "Living Fortress"),
    "Priest/Healer": ("Battlefield Saint", "Miracle Shepherd"), "Support": ("Resonant Conductor", "Grand Harmonist"),
    "Summoner": ("Contract Marshal", "Concord Summoner"), "Tactician": ("Field Commander", "War-Script Sovereign"),
    "Beast Master": ("Pack Warden", "Mythic Beast Marshal"), "Explorer": ("Hidden-Route Seeker", "Worldpath Pioneer"),
    "Merchant/Orator": ("Trust Broker", "Golden Voice"), "Blacksmith": ("Purpose Smith", "Master Equipment Forger"),
    "Alchemist": ("Adaptive Compounder", "Grand Alchemist"), "Tailor": ("Living Pattern", "Legendary Tailor"),
    "Architect": ("Battlefield Builder", "Grand Architect"),
}

ROLE_EFFECTS = {
    "Combat": ("A practiced opening gains +4 on an extreme combat check when the action fits the class.", "Class Skills use cooldowns rather than Mana unless explicitly magical."),
    "Magic": ("Spell analysis or prepared casting gains +4 on a matching extreme check.", "Spells consume Mana and remain bound by learned effects and range."),
    "Support": ("Meaningful healing, cleansing, protection, or party support earns full class and XP credit.", "Support cannot erase an established wound, curse, or cooldown without a fitting ability."),
    "Command / Social": ("Concrete plans, negotiations, leadership, and trade earn full class and XP credit.", "Success creates leverage or an offer; it never deletes another character's motives."),
    "Companion / Summoning": ("Coordinated actions with a contracted companion gain +4 on a matching extreme check.", "A companion has its own condition, loyalty, abilities, and limits."),
    "Exploration / Utility": ("Scouting, discovery, infiltration, mapping, and hazard work earn full class and XP credit.", "The feature reveals earned clues rather than granting omniscience."),
    "Production": ("Creating, repairing, or improving a useful object earns full class and XP credit.", "Quality still follows materials, mastery, time, and the narrated method."),
}


def _skill(name, role_type, active=True):
    effect_type = "damage" if role_type in {"Combat", "Magic"} and active else (
        "heal" if "Recovery" in name else "buff" if active else "utility"
    )
    magical = role_type == "Magic" or name in {"Mana Edge", "Minor Recovery", "Purifying Prayer", "Quickening Chorus", "Call Lumen Wisp"}
    return {
        "rank": "Beginner", "bonus": 4,
        "description": f"A learned Satisfy technique: {name}. It provides a reliable beginner-scale {role_type.lower()} effect when used as described.",
        "effect": f"Applies {name} to a fitting {role_type.lower()} problem at the character's current level.",
        "limitation": "Its effect, target, cooldown, range, and current mastery remain real constraints.",
        "growth_path": "Use it in varied meaningful situations, improve its mastery, and pursue the class quest that develops it.",
        "combat_usable": bool(active), "effect_type": effect_type,
        "category": "spell" if magical else "class skill",
        "resource_type": "pool" if magical else "cooldown",
        "target_type": "enemy" if effect_type == "damage" else "ally" if effect_type in {"heal", "buff"} else "self",
        "duration_rounds": 1 if effect_type in {"damage", "heal"} else 2,
    }


def starter_kit_for(archetype):
    """Concrete normal-class package used at creation and by migrations."""
    archetype = str(archetype or "Warrior")
    active_name, feature_name, suggestion = ROLE_STARTER_KITS.get(archetype, ROLE_STARTER_KITS["Warrior"])
    role_type = ROLE_TYPES.get(archetype, infer_class_type(archetype))
    base_type = next((key for key in ROLE_EFFECTS if key in role_type), "Combat")
    effect, limitation = ROLE_EFFECTS[base_type]
    skills = {active_name: _skill(active_name, base_type, True), feature_name: _skill(feature_name, base_type, False)}
    companion = None
    if archetype == "Summoner":
        companion = {"name": "Lumen Wisp", "kind": "Contracted spirit", "role": "Scout and magical support", "loyalty": 45, "condition": "Stable", "level": 1, "abilities": ["Guiding Light", "Distracting Flash"], "growth_path": "Share successful encounters, honor the contract, and develop coordinated commands."}
    elif archetype == "Beast Master":
        companion = {"name": "Greyhorn Cub", "kind": "Bonded beast", "role": "Tracker and close support", "loyalty": 50, "condition": "Healthy", "level": 1, "abilities": ["Scent Trail", "Warning Growl"], "growth_path": "Care for it, train through real fieldwork, and let the bond develop without treating it as equipment."}
    return {
        "name": archetype, "kind": "Standard Satisfy Class", "rank": "Normal", "class_type": role_type,
        "description": f"A complete beginning {archetype} path in Satisfy with its own techniques, contribution rules, quests, and advancement.",
        "effect": effect, "limitation": limitation,
        "growth_path": f"Complete The {archetype}'s First Proof, develop both starter techniques, then choose an earned specialization.",
        "signature_skill": active_name, "features": [active_name, feature_name], "skills": skills,
        "quest": {"name": f"The {archetype}'s First Proof", "goal": suggestion, "reward": "Class stage progress and a specialization lead"},
        "suggestions": [suggestion], "companion": companion, "mechanical_bonus": 4,
        "advancements": list(ROLE_ADVANCEMENTS.get(archetype, (f"Focused {archetype}", f"Master {archetype}"))),
        "contribution_tags": [base_type.lower(), role_type.lower()],
    }


def class_encyclopedia():
    """Compact player-facing reference; no AI call and no copied wiki prose."""
    families = []
    family_type = {"Martial and weapon": "Combat", "Magic and supernatural": "Magic", "Support and faith": "Support",
                   "Command and society": "Command", "Companions and control": "Companion",
                   "Exploration and utility": "Exploration", "Production and creation": "Production"}
    for family, description in CLASS_DESIGN_FAMILIES.items():
        marker = family_type.get(family, "Hybrid")
        examples = [name for name in CANON_CLASS_NAMES if marker.lower() in infer_class_type(name).lower()][:12]
        families.append({"name": family, "description": description, "examples": examples})
    return {"starter_classes": [copy.deepcopy(starter_kit_for(name)) for name in ROLE_STARTER_KITS],
            "families": families, "canon_name_count": len(CANON_CLASS_NAMES),
            "note": "Canon classes establish Satisfy's breadth. Original classes can be equally deep when earned by compatible choices and conditions."}


def class_action_bonus(state, action):
    """Automatic normal-class feature bonus for rare checks that reach dice."""
    if not isinstance(state, dict) or state.get("world") != "Overgeared":
        return 0
    special = state.get("special") if isinstance(state.get("special"), dict) else {}
    reception = ((state.get("overgeared_system") or {}).get("class_reception") or {})
    if str(reception.get("status") or "").lower() == "pending":
        return 0
    profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
    class_name = profile.get("name") or special.get("Class")
    kit = starter_kit_for(class_name)
    class_type = profile.get("class_type") or infer_class_type(
        class_name, profile.get("description"), profile.get("effect"), kit.get("class_type"),
    )
    mechanical_bonus = int(profile.get("mechanical_bonus", kit.get("mechanical_bonus", 4)) or 0)
    text = str(action or "").lower()
    patterns = {
        "Combat": r"\b(?:fight|attack|strike|guard|defend|duel|shoot|stab|block|weapon)\b",
        "Magic": r"\b(?:cast|spell|magic|mana|ritual|enchant|analy[sz]e)\b",
        "Support": r"\b(?:heal|cleanse|support|aid|protect|buff|restore|rescue)\b",
        "Command / Social": r"\b(?:plan|command|lead|coordinate|negotiate|trade|deal|convince|organize)\b",
        "Companion / Summoning": r"\b(?:summon|contract|companion|beast|pet|formation|command)\b",
        "Exploration / Utility": r"\b(?:explore|scout|search|track|map|infiltrate|discover|investigate|disarm)\b",
        "Production": r"\b(?:craft|forge|smith|brew|sew|build|repair|create|produce)\b",
    }
    return mechanical_bonus if any(
        label in str(class_type) and re.search(pattern, text, re.I)
        for label, pattern in patterns.items()
    ) else 0
