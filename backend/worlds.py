"""Static world/game data: ported 1:1 from the original Tkinter build's
WORLD_DATA / WORLD_EXPANSIONS / DIFFICULTIES / BASE_STATE so campaign
mechanics and AI prompt schemas stay identical."""
import datetime
import copy
import math
import re

from bleach_data import BLEACH_GM_RULES
from power_benchmarks import benchmark_tier, benchmark_context

DEFAULT_MODEL = "gpt-5.6-luna"
SECONDARY_MODEL = "gpt-4o-mini"
APP_VERSION = "3.64.0"
APP_NAME = "Worldwalker RPG"

# A world-agnostic power-level anchor for the Advisor. None of Worldwalker's
# worlds natively use a numeric power scale (Naruto has jutsu/rank, One Piece
# has bounty/Haki, Overgeared has level/class...), so this isn't shown to the
# player or injected into any world's own fiction — it exists purely so the
# Advisor's own power comparisons stay internally consistent turn to turn
# instead of improvising a different ad-hoc scale every time it's asked,
# and so a player-requested framing (DBZ power levels, whatever) has a
# stable internal reference to translate from.
POWER_TIERS = [
    (0, "Mundane", "An ordinary person with no combat training."),
    (1, "Trained", "A capable fighter or specialist — early-career adventurer, soldier, low-rank professional."),
    (2, "Skilled", "A seasoned professional — veteran soldier, competent mage, respected local talent."),
    (3, "Elite", "Among the best in a city or region — elite unit member, a minor noble house's champion."),
    (4, "Exceptional", "A nationally recognized talent — famous hero, high-ranking officer, renowned specialist."),
    (5, "Powerhouse", "Capable of single-handedly turning a battle — feared commander, master of their craft."),
    (6, "Superhuman", "Clearly beyond ordinary human limits — genuinely supernatural strength, speed, or power."),
    (7, "Legendary", "A living legend — decides the fate of nations, feared across a continent."),
    (8, "World-Class", "Among the strongest beings in the setting — can threaten a nation alone."),
    (9, "Cataclysmic", "Can reshape a region or end a war single-handedly."),
    (10, "Reality-Bending", "Power that strains or breaks the setting's normal rules entirely."),
]
POWER_TIER_THRESHOLDS = [20, 35, 50, 65, 90, 130, 200, 350, 600, 1000]


def power_tier_reference():
    thresholds = [0] + POWER_TIER_THRESHOLDS
    return "\n".join(
        f"{n}. {name} (balanced score {thresholds[n]}+) — {desc}"
        for n, name, desc in POWER_TIERS
    )

DIFFICULTIES = {
    "Story": {"difficulty_shift": -15, "dc_shift": -3, "enemy_edge": -2, "death": "rare", "freedom": "very high",
              "description": "Strong power-fantasy play. Possible plans succeed readily; drama comes from consequences and character reactions. Death is rare unless deliberately embraced."},
    "Adventurer": {"difficulty_shift": -6, "dc_shift": 0, "enemy_edge": 0, "death": "possible", "freedom": "high",
                   "description": "Heroic play with responsive opposition. Plausible actions and sustained growth succeed; danger and NPC countermoves still matter."},
    "Veteran": {"difficulty_shift": 5, "dc_shift": 3, "enemy_edge": 2, "death": "likely", "freedom": "high",
                "description": "Capable, dangerous opposition and meaningful risk of death, while logically possible player plans still receive decisive results."},
    "Nightmare": {"difficulty_shift": 15, "dc_shift": 6, "enemy_edge": 4, "death": "severe", "freedom": "total",
                  "description": "Brutal simulation. Contextual difficulties are much higher and fatal mistakes are common."},
}

# The Tower of Trials — Solo Max-Level Newbie's 50-floor structure, sourced
# from a canon-inspired floor map the user supplied. Each entry is the
# floor's real internal name/theme, used to keep the GM's choice of
# monsters/factions per floor canon-consistent (murim floors get martial
# sects, workshop floors get golems and empires, and so on) — but the
# PLAYER only ever sees "Floor N" (see tower_floor_display / map below);
# the theme is GM-context only, never surfaced as the location label.
TOWER_FLOOR_THEMES = [
    ("Hapjeong Station", "Opening Survival"), ("Mangrove, Tree of Greed", "Carnivorous Forest"),
    ("Goblin Warrens", "First Hunt"), ("Poison Swamp", "Venom and Traps"),
    ("Ruined Temple", "Relic Puzzle"), ("Underground Aqueduct", "Water Beasts"),
    ("Beast Colosseum", "Strength Trial"), ("Cursed Catacombs", "Undead Ambush"),
    ("Mirror Passage", "Illusion Trial"), ("Orc Stronghold", "Siege Test"),
    ("Desecrated Chapel", "Curse Rite"), ("Frozen Rift", "Endurance Trial"),
    ("Lava Crossing", "Flames of Trial"), ("Alchemist's Lab", "Mutant Experiments"),
    ("Library of Records", "Knowledge Trial"), ("Assassin's Alley", "Silent Killers"),
    ("Phantom Ballroom", "Hallucination Zone"), ("Clockwork Workshop", "Golems and Gears"),
    ("Hidden Place", "Ruined Cave Labyrinth"), ("Murim Gate", "Jianghu Opens"),
    ("Beggar Sect Streets", "Espionage Web"), ("Poison Valley", "Venom Masters"),
    ("Shaolin Grounds", "Discipline Trial"), ("Mount Hua Paths", "Sword Sect Ordeal"),
    ("Namgung Arena", "Duel of Clans"), ("Demonic Cult Border", "Blood and Ambush"),
    ("Black Market of Jianghu", "Schemes and Trade"), ("Murim Battlefield", "Clash of Sects"),
    ("Heavenly Demon Ascent", "Murim Endgame"), ("Workshop Battle", "Tournament of Relics"),
    ("Imperial Frontier", "War on the March"), ("Arcane Academy", "Magic Examination"),
    ("Noble District", "Court Conspiracy"), ("Spirit Catacombs", "Ancient Capital Depths"),
    ("Knight Order Barracks", "Chivalric Trial"), ("Imperial Palace", "Audience with the Throne"),
    ("Magic Tower", "High Sorcery"), ("Rebellion Front", "Empire in Flames"),
    ("Abyssal Gate", "Rift to the Lower Dark"), ("Ancient Throne", "Demon Monarch's Court"),
    ("Ancient Archive", "Forgotten Histories"), ("Titan Graveyard", "Colossi of the Past"),
    ("Celestial Observatory", "Stars and Prophecy"), ("World Tree Canopy", "Ancient Spirit Realm"),
    ("Void Corridor", "Nothingness Trial"), ("Guardian Sanctuary", "Keepers of the Summit"),
    ("Divine Mechanism Chamber", "Clockwork Heaven"), ("Administrator's Garden", "Realm of the Overseers"),
    ("Final Ascent", "Path to the Apex"), ("Top of the Tower", "Destia and the Last Trial"),
]
TOWER_FLOOR_COUNT = len(TOWER_FLOOR_THEMES)


def tower_floor_theme(floor):
    """The internal canon name/theme for a floor (GM context only, 1-indexed)."""
    idx = max(1, min(TOWER_FLOOR_COUNT, int(floor or 1))) - 1
    name, theme = TOWER_FLOOR_THEMES[idx]
    return f"{name} — {theme}"


def _tower_tier(floor):
    if floor <= 19: return 2 + floor // 7
    if floor <= 29: return 5
    if floor <= 40: return 6 if floor <= 35 else 7
    if floor <= 45: return 8
    return 9 if floor <= 49 else 10


# Ecological "band" identity per tier — each is a distinct, internally
# consistent biome of threat logic and environmental behavior that must not
# bleed into neighboring bands. Compressed from an 11-band/100+-floor
# generic Tower framework down to this Tower's real 9-tier/50-floor
# structure (floor 50 is the canon-established top of THIS Tower), so the
# escalation curve still completes by the true final floor instead of
# treating floor 50 as merely "mid-tier" the way the uncompressed framework
# would.
_TOWER_BANDS = {
    2: ("Initial Survival", "unstable, partially degraded systems; low-level anomalies and reactive hazards that respond directly to presence and noise"),
    3: ("Adaptive Response", "more structured, semi-self-regulating surroundings; coordinated threats and environmental traps that begin predicting simple behavior patterns"),
    4: ("Structured Hunting", "organized predators with group intelligence and territorial systems; survival requires strategy, not just reaction"),
    5: ("Systemic Complexity", "layered, multi-condition hazards; engineered systems and hybrid threats where the environment itself turns adversarial"),
    6: ("Predictive Ecosystem", "a responsive, semi-adaptive layout where entities learn and counter the player's own patterns across repeated encounters"),
    7: ("Fractured Reality", "localized, bounded instability in physical law and perception — logic bends but every shift must stay traceable within Tower rules, never arbitrary"),
    8: ("Pre-Transition / High Ecosystem", "elite variants of earlier threats and multi-domain coordination; cross-system interaction and layered, sometimes indirect conflict"),
    9: ("Advanced Anomaly", "high-tier anomalies bound by specific, discoverable rules; exceptions exist but are never lawless, and system-breaking attempts are contained and structured"),
    10: ("Final Ascent / Upper System", "apex, overseer-caliber entities operating with near-complete awareness of the Tower's own rules; foundational Tower logic is partially exposed here but never fully broken"),
}


def tower_band(floor):
    """(band_name, ecology_summary) for the ecological band this floor's
    tier belongs to — GM context only, same non-player-facing status as
    tower_floor_theme()."""
    return _TOWER_BANDS.get(_tower_tier(max(1, min(TOWER_FLOOR_COUNT, int(floor or 1)))), _TOWER_BANDS[2])


def _tower_map_nodes():
    """Player-facing map nodes for all 50 floors — deliberately just 'Floor
    N', never the internal theme name (see TOWER_FLOOR_THEMES)."""
    nodes = [("Earth — Tower Entrance", 50, 96, "hub", 1)]
    for floor in range(1, TOWER_FLOOR_COUNT + 1):
        x = 42 if floor % 2 == 0 else 58
        y = round(90 - (floor - 1) * (86 / (TOWER_FLOOR_COUNT - 1)), 1)
        nodes.append((f"Floor {floor}", x, y, "floor", _tower_tier(floor)))
    return nodes


WORLD_DATA = {
    "One Piece": {
        "tagline": "Pirates, Marines, Haki, Devil Fruits, crews, bounties, and a living sea.",
        "resource": "Stamina",
        "progression": ["Attributes","Haki","Combat Style","Bounty","Crew","Reputation","Titles"],
        "rules": "Honor One Piece world logic. Islands and seas matter. Marines, pirates, kingdoms and crews pursue their own motives. Devil Fruits are unique. Haki requires plausible awakening/training. Bounties respond to notoriety and government threat assessment. Canon may diverge permanently.",
        "start": "Foosha Village",
        # Yonko crews are this world's real polities, not just powerful
        # individuals — canon-confirmed territory each: Big Mom rules Totto
        # Land, Kaido conquered and rules Wano, Whitebeard formally placed
        # Fishman Island under his protection. Seeded here (not just added
        # to WORLD_TERRITORIES below) so they're live, tracked factions
        # with their own clock from turn one — contactable, able to gain or
        # lose ground, and protected from being casually wiped out by an
        # off-screen dice roll — the same as Marines/World Government
        # already were. The default campaign start (seven days before
        # Foosha) is well before Marineford, so Whitebeard is alive and at
        # full strength here, not a stale reference to a dead Yonko. Shanks
        # has no single canon-confirmed home territory the way the other
        # three do, so he's tracked as a faction without a matching map
        # entry, same as Marines/World Government already are.
        "factions": {"Marines": 0, "World Government": 0, "Revolutionary Army": 0, "Pirates": 0,
                     "Whitebeard Pirates": 0, "Big Mom Pirates": 0, "Kaido's Beasts Pirates": 0, "Shanks' Red Hair Pirates": 0},
        # Coordinates calibrated against a labeled canon-geography reference
        # map (player-supplied, in assets/generated_maps/One_Piece.*) now
        # used as this world's map background, the same treatment Naruto's
        # map already got. Also fills in several major canon locations that
        # UPCOMING CANON PRESSURES / CANON_TIMELINES already reference by
        # name (Marineford, Impel Down, Drum Island, Thriller Bark, Zou) but
        # that had no map node at all before — the vague catch-all "New
        # World" region node is retired in favor of these concrete ones.
        "map": [
            ("Foosha Village",82,27,"settlement",1), ("Goa Kingdom",79,25,"kingdom",2),
            ("Shells Town",87,30,"marine",2), ("Orange Town",74,31,"settlement",2),
            ("Syrup Village",70,34,"settlement",2), ("Baratie",66,38,"sea",3),
            ("Arlong Park",79,36,"enemy",4), ("Loguetown",59,39,"city",4),
            ("Reverse Mountain",27,48,"landmark",5), ("Whiskey Peak",31,48,"island",5),
            ("Little Garden",34,47,"island",6), ("Drum Island",38,46,"island",6),
            ("Alabasta",41,50,"kingdom",7), ("Jaya",43,45,"island",7),
            ("Skypiea",43,28,"sky",8), ("Water 7",46,48,"city",8),
            ("Enies Lobby",48,47,"government",9), ("Thriller Bark",49,51,"island",9),
            ("Sabaody",51,48,"archipelago",10), ("Zou",68,47,"island",10),
            ("Fishman Island",51,57,"island",11), ("Impel Down",48,57,"prison",12),
            ("Totto Land",73,46,"island",13), ("Marineford",49,55,"marine",13),
            ("Amazon Lily",41,61,"island",10), ("Punk Hazard",57,48,"island",11),
            ("Dressrosa",61,49,"kingdom",12), ("Mary Geoise",51,43,"government",15),
            ("Egghead Island",88,53,"island",14), ("Lulusia Kingdom",66,68,"kingdom",9),
            ("Ohara",18,34,"historical",8), ("Wano Country",81,50,"nation",14),
            ("Cocoyasi Village",78,34,"settlement",3), ("Shimotsuki Village",75,28,"settlement",2),
            ("Baltigo",24,74,"revolutionary",10), ("Kano Country",24,24,"kingdom",7),
            ("Sorbet Kingdom",66,75,"kingdom",6), ("Germa Kingdom",20,20,"mobile kingdom",9)
        ],
        "special": {"Haki":{"Observation":0,"Armament":0,"Conqueror":0}, "Bounty":0, "Devil Fruit":"None", "Crew":"None"}
    },
    "Hunter x Hunter": {
        "tagline": "Hunters, Nen, dangerous exams, criminal underworlds, and unexplored frontiers.",
        "resource": "Aura",
        "progression": ["Attributes","Aura","Nen","Hatsu","Hunter Status","Reputation","Titles"],
        "rules": "Honor Hunter x Hunter logic. Nen is not casually known by ordinary people and must be learned plausibly. Track Ten, Zetsu, Ren, Hatsu, aura and Nen category only after discovery. Vows and limitations can create power with real costs. Hunters, mafia, assassins and the Association act independently.",
        "start": "Yorknew City",
        "factions": {"Hunter Association":0,"Yorknew Mafia":0,"Phantom Troupe":0,"Zoldyck Family":0},
        "map": [
            ("Yorknew City",48,51,"city",4), ("Kukuroo Mountain",34,43,"estate",7),
            ("Whale Island",71,68,"island",1), ("Hunter Exam Site",58,61,"exam",3),
            ("Heavens Arena",58,43,"arena",6), ("Meteor City",31,60,"city",8),
            ("Greed Island",75,48,"island",9), ("NGL",67,32,"region",10),
            ("East Gorteau",61,27,"nation",11), ("Hunter Association HQ",47,35,"hq",7),
            ("Kakin Empire",52,68,"nation",12), ("Republic of Padokea",36,44,"nation",6),
            ("Yorbian Continent",48,53,"region",5), ("Mitene Union",64,29,"region",8),
            ("Dark Continent Expedition Route",18,14,"frontier",15), ("Zevil Island",62,51,"island",5)
        ],
        "special": {"Nen Category":"Unknown","Ten":0,"Zetsu":0,"Ren":0,"Hatsu":"Undeveloped"}
    },
    "Naruto": {
        "tagline": "Shinobi villages, chakra, missions, bloodlines, rival nations, and hidden techniques.",
        "resource": "Chakra",
        "progression": ["Attributes","Chakra","Jutsu","Rank","Village Reputation","Titles"],
        "rules": "Honor Naruto world logic. Chakra, elemental affinities, clan techniques, ranks, missions and village politics matter. Jutsu require training, inheritance, instruction or legitimate copying conditions. Powerful bloodlines are rare. Villages remember betrayal, service and classified knowledge.",
        "start": "Konohagakure",
        # Amegakure and Iron Country are already on this world's own map
        # below with their own sovereign governance in canon (Amegakure,
        # Land of Iron's samurai under Mifune) — tracked the same as the
        # five great villages instead of defaulting to "Unknown" on the map
        # and being invisible as factions until the story happened to
        # introduce them.
        "factions": {"Konohagakure":0,"Sunagakure":0,"Kirigakure":0,"Kumogakure":0,"Iwagakure":0,"Amegakure":0,"Iron Country":0,"Akatsuki":0},
        # Coordinates calibrated against a manga-sourced "Naruto World" map
        # (player-supplied) now used as this world's map background — most
        # placements are the confirmed canon locations from that reference,
        # not a generic/approximate layout. Iron Country and Forest of Death
        # aren't confirmed on that specific map (it flags Iron Country as
        # guesswork itself), so both use a reasonable nearby placement.
        "map": [
            ("Konohagakure",52,52,"village",3), ("Land of Fire",52,48,"region",2),
            ("Sunagakure",21,62,"village",5), ("Kirigakure",84,57,"village",6),
            ("Kumogakure",73,21,"village",7), ("Iwagakure",23,22,"village",7),
            ("Valley of the End",55,42,"landmark",6), ("Forest of Death",54,55,"training",5),
            ("Land of Waves",68,73,"region",4), ("Amegakure",31,47,"village",8),
            ("Iron Country",48,13,"nation",8), ("Kannabi Bridge",36,37,"landmark",7),
            ("Land of Rice Fields",62,35,"region",5), ("Kusagakure",47,29,"village",5),
            ("Takigakure",34,35,"village",6), ("Yugakure",67,45,"village",5),
            ("Otogakure",64,32,"village",7), ("Uzushiogakure Ruins",65,67,"historical",7),
            ("Five Kage Summit",48,14,"landmark",8), ("Fourth War Front",63,36,"battlefield",12),
            ("Kaguya's Dimension",92,8,"dimension",15)
        ],
        "special": {"Shinobi Rank":"Civilian","Nature Affinity":"Unknown","Known Jutsu":[],"Clan":"None"}
    },
    "Solo Max-Level Newbie": {
        "tagline": "Tower floors, hidden quests, achievements, copied abilities, artifacts, and exploitable secrets.",
        "resource": "Mana",
        "progression": ["Level","XP","Stats","Skills","Copied Abilities","Titles","Artifacts","Hidden Quests"],
        "rules": "Use Tower-progression logic inspired by Solo Max-Level Newbie. Floors have scenarios, administrators, hidden conditions, achievements, monsters, bosses and secret rewards. Clever foreknowledge can create enormous advantages when the player actually possesses or discovers it. System rewards must be explicit.",
        "start": "Earth — Tower Entrance",
        "factions": {"Players":0,"Major Guilds":0,"Tower Administrators":0,"Demons":0},
        "map": _tower_map_nodes(),
        "special": {"Unspent Stat Points":0,"Copied Abilities":[],"Achievements":[],"Floor":0,"Hidden Conditions Found":0}
    },
    "Overgeared": {
        "tagline": "A living Satisfy: limitless classes, raids, magic, companions, guilds, kingdoms, professions, and hidden paths.",
        "resource": "Mana",
        "progression": ["Level","XP","Class","Stats","Skills","Class Advancement","Affinity","Guild","Reputation","Titles","Optional Professions"],
        "rules": "Use the full Overgeared/Satisfy VRMMO framework. Satisfy supports ordinary, rare, epic, unique, legendary, growth-type and stranger classes across combat, weapons, magic, faith/support, command/social, companions, exploration, production and hybrids. Hidden classes arise from meaningful conditions and may be original when they match Satisfy's logic. Raids, quests, guilds, kingdoms, NPC relationships, player competition, equipment and professions all matter. Crafting is one optional route, not the assumed route. NPCs are persistent people with memories and interests. Grid and his canon arc continue elsewhere unless this player deliberately intersects them; never make an unrelated original character repeat Grid's debts, Pagma route, crafting identity, companions, or personal story beats.",
        "start": "Winston",
        "factions": {"Players":0,"Local Lords":0,"Church":0,"Guilds":0,"Kingdom":0},
        "map": [
            ("Winston",52,54,"city",2), ("Patrian",45,57,"city",4), ("Reidan",25,55,"city",6),
            ("Bairan",48,47,"city",5), ("Titan",56,43,"capital",8), ("Frontier",75,57,"region",8),
            ("Saharan Empire",59,35,"empire",10), ("Northern Frontier",43,18,"region",10),
            ("Kesan Canyon",29,58,"region",5), ("Temple of Yatan",39,68,"dungeon",7),
            ("Reinhardt",53,64,"capital",9), ("Pangea",69,61,"city",7),
            ("Talima",34,28,"city",8), ("Vatican",63,47,"holy city",9),
            ("Valhalla",73,43,"nation",10), ("Behen Archipelago",82,61,"dungeon",10)
        ],
        "special": {"Class":"Beginner","Secondary Class":"None","Crafting Mastery":0,"Guild":"None","NPC Affinity":{}}
    },
    "Reincarnated as a Slime": {
        "tagline": "Magicules, named skills, monster evolution, demon lords, and a newborn nation in the Great Jura Forest.",
        "resource": "Magicule",
        "progression": ["Attributes","Magicule Capacity","Named Skills","Evolution Stage","Reputation","Titles"],
        "rules": "Honor Tensura world logic. Magicules fuel skills and evolution. Named/Unique/Ultimate Skills are rare and earned through insight, naming, or extraordinary circumstance — never handed out casually. Monsters and demi-humans have species-based traits; evolution requires a genuine trigger (naming, mass magicule intake, a true crisis, or a Demon Lord's Seed/Awakening). Analytical skills akin to Great Sage, if present, must be foreshadowed and earned. Human kingdoms, demon lords and monster nations pursue independent agendas.",
        "start": "Great Jura Forest",
        "factions": {"Jura Forest Monsters": 0, "Kingdom of Falmuth": 0, "Demon Lords": 0, "Free Guild": 0},
        "map": [
            ("Great Jura Forest",52,45,"forest",1), ("Goblin Village",49,48,"settlement",2),
            ("Blumund",38,54,"town",2), ("Kingdom of Falmuth",70,50,"kingdom",3),
            ("Dwargon",53,24,"nation",5), ("Sorcerous Dynasty of Thalion",24,63,"nation",6),
            ("Jistav",72,31,"nation",8), ("Tempest",53,49,"nation",10),
            ("Great Jura Forest — Sealed Cave",50,42,"cave",4), ("Dragon Peak",66,22,"landmark",9),
            ("Holy Empire of Lubelius",27,30,"nation",9), ("Ingrassia",31,44,"nation",6),
            ("Eurazania",66,70,"nation",8), ("Milim's Domain",76,66,"territory",10),
            ("Walpurqis",88,76,"otherworld",14), ("El Dorado",12,79,"nation",12)
        ],
        "special": {"Named Skills":[], "Evolution Stage":"Unnamed", "Magicule Capacity":0, "Species":"Unknown"}
    },
    "Bleach": {
        "tagline": "Shinigami, Hollows, Zanpakuto, and the fragile boundary between the living world and Soul Society.",
        "resource": "Reiryoku",
        "progression": ["Reiryoku","Spiritual Arts","Kido","Zanpakuto Bond","Shikai","Bankai","Squad Rank","Standing","Titles"],
        # Aizen's true loyalties are this world's single biggest canon
        # secret at the campaign's default start — the actual instruction
        # protecting it lives in the "rules" string below (it has to, to
        # reach the model), not just here as a code comment.
        "rules": "Honor Bleach world logic. Ordinary humans cannot see spirits; a rare few can. Shinigami train Zanjutsu, Hakuda, Hoho and Kido and carry a living Zanpakuto whose earned releases reflect the wielder. Hollows are corrupted spirits Shinigami purify; Quincy destroy Hollows with reishi techniques, threatening the balance of souls. Soul Society, the Living World, Hueco Mundo and the Royal Realm are distinct spaces with gated travel. Rank is an institution, not a universal power number. Central 46 and division politics are active. Until this campaign's timeline or player actions genuinely uncover it, Sosuke Aizen is a respected 5th Division captain: never hint, foreshadow, or reveal his true nature, the Hogyoku or the hidden Visored prematurely. Canon may diverge permanently.\n" + BLEACH_GM_RULES,
        "start": "Shin'o Academy",
        "factions": {"Gotei 13": 0, "Central 46": 0, "Onmitsukido": 0, "Kido Corps": 0, "Noble Houses": 0, "Urahara Network": 0},
        "map": [
            ("Karakura Town",50,52,"settlement",1), ("Karakura High School",49,49,"settlement",1),
            ("Kurosaki Clinic",48,55,"landmark",1), ("Urahara Shop",54,54,"shop",3),
            ("Naruki City",53,50,"settlement",2), ("Urahara Training Grounds",53,57,"training",5),
            ("Senkaimon",37,48,"landmark",5), ("Dangai",39,43,"region",7),
            ("Rukongai",18,45,"region",4), ("North Rukongai",18,25,"region",4),
            ("East Rukongai",31,44,"region",4), ("South Rukongai",18,65,"region",4),
            ("West Rukongai",5,44,"region",4), ("Shin'o Academy",16,40,"training",4),
            ("Seireitei",18,44,"government",6), ("Gotei 13 Barracks",21,47,"hq",6),
            ("Kido Corps Headquarters",20,42,"hq",7), ("Onmitsukido Headquarters",15,45,"hq",8),
            ("Senzaikyu",16,48,"prison",7), ("Sokyoku Hill",21,38,"landmark",8),
            ("Central 46 Chambers",18,46,"government",8), ("Maggot's Nest",9,53,"prison",8),
            ("Muken",18,69,"prison",12), ("Hueco Mundo Desert",83,46,"region",10),
            ("Forest of Menos",82,57,"dungeon",11), ("Las Noches",84,36,"nation",14),
            ("Garganta",65,47,"region",9), ("Valley of Screams",36,36,"region",10),
            ("Soul King Palace",50,13,"government",16), ("Royal Guard Domains",57,14,"region",17),
            ("Silbern",18,43,"hidden realm",15), ("Wahrwelt",53,20,"nation",18), ("Gates of Hell",50,78,"landmark",18)
        ],
        "special": {"Spiritual Nature":"Soul Reaper","Shinigami Rank":"Academy Senior","Zanpakuto":"Unnamed Asauchi","Zanpakuto Profile":{"stage":"Sealed","name":"Unknown","development_evidence":[]},"Shikai":"Unachieved","Bankai":"Unachieved","Squad":"Unassigned","Kido Curriculum":{"Hadō":"#1-99 learnable","Bakudō":"#1-99 learnable","Unshown Numbers":"Generated once when discovered, then permanent"}}
    },
    "Jujutsu Kaisen": {
        "tagline": "Curses, sorcerers, binding vows, inherited techniques, and battles decided by insight as much as force.",
        "resource": "Cursed Energy",
        "progression": ["Attributes", "Cursed Energy", "Innate Technique or Heavenly Restriction", "Technique Applications", "Barrier Arts", "Grade", "Reputation", "Titles"],
        "rules": "Honor Jujutsu Kaisen world logic. Negative human emotion creates cursed energy and curses. Sorcerers reinforce their bodies, control cursed energy, use innate techniques and barriers, and may trade genuine conditions through binding vows. Every original character receives exactly one exclusive birth slot: either one Innate Cursed Technique or one Heavenly Restriction, never both. Technique applications are separate learned skills derived from the innate rule. Original techniques are welcome and should match canon techniques in depth, uniqueness, complexity and possible power while keeping their stated mechanics coherent. A technique may plainly be overwhelmingly powerful and may genuinely have no special weakness; do not invent a fake weakness, but ordinary requirements such as cursed energy, activation, range and the user's ability still apply unless the technique explicitly removes them. Heavenly Restriction replaces the technique slot and mechanically trades cursed-energy potential or another real capacity for extraordinary physical or sensory ability. Grades are assessments, not level locks. Black Flash is an exceptional timing phenomenon, not a button the character can guarantee. Domains, reverse cursed technique and maximum techniques require plausible development unless the background explicitly establishes them. Canon may diverge permanently through player action.",
        "start": "Tokyo Jujutsu High",
        "factions": {"Tokyo Jujutsu High":0, "Kyoto Jujutsu High":0, "Jujutsu Headquarters":0, "Gojo Clan":0, "Zenin Clan":0, "Kamo Clan":0, "Independent Curse Users":0, "Cursed Spirits":0},
        "map": [
            ("Tokyo Jujutsu High",66,61,"academy",4), ("Kyoto Jujutsu High",46,62,"academy",4),
            ("Shibuya",67,63,"city",6), ("Sendai",74,44,"city",5), ("Saitama Detention Center",67,57,"danger",5),
            ("Sugisawa High School",74,43,"school",2), ("Eishu Juvenile Detention Center",66,59,"danger",6),
            ("Star Religious Group Headquarters",66,62,"hq",7), ("Zenin Estate",47,63,"estate",8),
            ("Tombs of the Star Corridor",66,60,"barrier",10), ("Cursed Warehouse",66,61,"vault",7),
            ("Tokyo No. 1 Colony",66,58,"barrier",12), ("Tokyo No. 2 Colony",64,61,"barrier",12),
            ("Sendai Colony",74,44,"barrier",12), ("Aomori Colony",77,28,"barrier",12),
            ("Aichi Colony",55,61,"barrier",12), ("Kyoto Colony",46,62,"barrier",12),
            ("Osaka Colony",44,65,"barrier",12), ("Hiroshima Colony",35,65,"barrier",12),
            ("Sakurajima Colony",22,79,"barrier",12), ("Hokkaido Sacred Zone",86,16,"barrier",13)
        ],
        "special": {"Grade":"Unassessed", "Official Status":"Unregistered", "Birth Slot":"Pending generation", "Innate Technique":"Pending generation", "Heavenly Restriction":"None", "Domain Expansion":"Unachieved", "Reverse Cursed Technique":"Unachieved", "Black Flashes":0}
    },
    "Custom World": {
        "tagline": "A freeform world defined by you.",
        "resource": "Energy",
        "progression": ["Level","XP","Stats","Skills","Inventory","Reputation","Titles"],
        "rules": "Use the player's custom setting as the source of truth. Maintain internal consistency, persistent NPC motives, meaningful geography and consequences.",
        "start": "Starting Region",
        "factions": {"Local Faction":0},
        "map": [("Starting Region",50,55,"region",1),("Northern Reach",50,20,"region",4),("Western March",20,50,"region",4),("Eastern Reach",80,50,"region",4),("Southern Wilds",50,82,"region",5)],
        "special": {}
    }
}

# Relative canon calendars. Most source worlds do not publish a consistent
# Gregorian date for every arc, so Canon Day 0 is the honest, deterministic
# anchor: the main protagonist's story begins then. Campaigns start shortly
# before it and these events become world pressures, not immutable rails.
CANON_TIMELINES = {
    "One Piece": {"start_day": -7, "anchor": "Seven days before Luffy leaves Foosha Village", "events": [
        # Day numbers below are calibrated against The Library of Ohara's
        # One Piece Timeline (V5.0, through chapter 1103), converted from its
        # real Gregorian-style Kaienreki dates into day-offsets from Luffy's
        # departure (day 0), which this world already anchors its calendar
        # to. Pre-departure history is flagged historical_only — it exists
        # for CANON HISTORY context only and predates every playable start.
        {"major": False, "historical_only": True, "day": -7799, "title": "Gol D. Roger's execution", "location": "Loguetown", "summary": "Roger is executed at Loguetown, his final words sending the world into the Great Pirate Era in search of the One Piece."},
        {"major": False, "historical_only": True, "day": -7331, "title": "Portgas D. Ace is born", "location": "South Blue", "summary": "Ace is born to Roger and Portgas D. Rouge, who dies shortly after giving birth; Garp takes the infant into Dadan's care."},
        {"major": False, "historical_only": True, "day": -7180, "title": "The Ohara Incident", "location": "Ohara", "summary": "The World Government orders a Buster Call on Ohara after learning its scholars are researching the Poneglyphs; Nico Robin survives as the island's last scholar."},
        {"major": False, "historical_only": True, "day": -6450, "title": "The execution of Kozuki Oden", "location": "Wano — Onigashima", "summary": "Kaido executes Kozuki Oden by boiling after his attack fails; Oden's retainers are sent twenty years into the future to one day open Wano's borders."},
        {"major": False, "historical_only": True, "day": -6112, "title": "Monkey D. Luffy is born", "location": "East Blue", "summary": "Monkey D. Luffy is born, the son of revolutionary Monkey D. Dragon and grandson of Marine hero Monkey D. Garp."},
        {"major": False, "historical_only": True, "day": -3530, "title": "Fisher Tiger's death", "location": "Fish-Man Island", "summary": "Fisher Tiger, who once freed thousands of slaves from Mary Geoise, is killed by Marines after refusing to spill human blood."},
        {"major": False, "historical_only": True, "day": -975, "title": "Ace joins the Whitebeard Pirates", "location": "New World", "summary": "After years pursuing him, Ace is defeated by Whitebeard and joins his crew, eventually becoming Second Division Commander."},
        {"major": False, "historical_only": True, "day": -123, "title": "Marshall D. Teach betrays the Whitebeard Pirates", "location": "New World", "summary": "Teach murders his crewmate Thatch to steal the Yami Yami no Mi, then leaves to form the Blackbeard Pirates — setting Ace on his pursuit."},
        {"day": 0, "title": "Luffy leaves Foosha Village", "location": "Foosha Village", "summary": "Seventeen-year-old Monkey D. Luffy sets out alone to become King of the Pirates, beginning the East Blue voyage."},
        {"major": False, "day": 2, "title": "Shells Town upheaval", "location": "Shells Town", "summary": "Roronoa Zoro is freed and Captain Morgan and his son Helmeppo are overthrown, ending the base's corrupt rule; Zoro joins Luffy."},
        {"major": False, "day": 5, "title": "Orange Town crisis", "location": "Orange Town", "summary": "Buggy the Clown's pirates are defeated; Nami temporarily allies with the crew."},
        {"major": False, "day": 10, "title": "Syrup Village conspiracy", "location": "Syrup Village", "summary": "Captain Kuro's plot against Kaya is exposed and defeated."},
        {"major": False, "day": 11, "title": "Kaya's decision and the Going Merry", "location": "Syrup Village", "summary": "Kaya, newly free of Kuro's manipulation, gives Usopp and the crew the ship that becomes the Going Merry; Usopp joins."},
        {"day": 13, "title": "Baratie conflict", "location": "Baratie", "summary": "Don Krieg's armada is repelled at the floating restaurant; Sanji joins the crew and Dracule Mihawk marks Zoro as a rival worth surviving for."},
        {"day": 14, "title": "Arlong Park revolt", "location": "Arlong Park", "summary": "Arlong is defeated and Cocoyasi Village is freed; Nami formally joins the crew."},
        {"major": False, "day": 17, "title": "Loguetown and the first bounty", "location": "Loguetown", "summary": "Luffy is nearly executed in the same square where Gold Roger died, crosses paths with the revolutionary Dragon, and receives his first bounty as the crew departs for the Grand Line."},
        {"major": False, "day": 17, "title": "Reverse Mountain and Laboon's promise", "location": "Reverse Mountain", "summary": "The crew crosses into the Grand Line proper via Reverse Mountain, and Luffy promises the whale Laboon they'll return for a rematch after circling the world."},
        {"major": False, "day": 18, "title": "Little Garden and Vivi's true identity", "location": "Little Garden", "summary": "The crew befriends the giants Dorry and Brogy, and Vivi is revealed as Alabasta's princess, secretly infiltrating Baroque Works from within."},
        {"day": 20, "title": "Drum Island — Chopper joins", "location": "Drum Island", "summary": "Wapol's tyranny is overthrown with Dr. Kureha's help, and the reindeer doctor Tony Tony Chopper joins the crew."},
        {"day": 31, "title": "Operation Utopia and Crocodile's defeat", "location": "Alabasta", "summary": "Crocodile's plot to seize the kingdom through civil war is exposed and defeated; Vivi's homeland is saved, though she stays behind rather than continue the voyage."},
        {"day": 36, "title": "Skypiea's golden bell rings", "location": "Skypiea", "summary": "The self-proclaimed god Enel is defeated and driven from Skypiea; the ancient bell of Shandora is rung for the whole world to hear, ending a four-century war."},
        {"major": False, "day": 45, "title": "Water 7 — the search for Robin", "location": "Water 7", "summary": "Nico Robin's history as Ohara's last scholar and the government's fear of the Rio Poneglyph begin surfacing as CP9 closes in."},
        {"day": 47, "title": "Enies Lobby raid — war on the World Government", "location": "Enies Lobby", "summary": "The crew storms the Government's judicial island to rescue Robin, defeats CP9's Rob Lucci, and burns their own flag in open defiance of the World Government. Shipwright Franky joins the crew."},
        {"day": 52, "title": "Thriller Bark — Moria defeated", "location": "Thriller Bark", "summary": "The Warlord Gecko Moria is defeated after his zombie-army scheme is unraveled; the skeleton musician Brook joins the crew, completing the original Straw Hat lineup."},
        {"day": 59, "title": "Sabaody Archipelago incident", "location": "Sabaody", "summary": "A clash with a Celestial Dragon draws admiral-level attention; the Warlord Bartholomew Kuma disperses the entire crew across the world to save them from annihilation, ending Part 1 of the voyage."},
        {"major": False, "day": 67, "title": "Impel Down infiltration", "location": "Impel Down", "summary": "Luffy infiltrates the great undersea prison to save his brother Ace, breaking out an army of dangerous allies and enemies alike in the process."},
        {"day": 68, "title": "The Battle of Marineford", "location": "Marineford", "summary": "The Whitebeard Pirates clash with the full might of the Marines and Warlords to save Ace from execution, in the largest war the world has seen in decades."},
        {"day": 68, "title": "Ace's death", "location": "Marineford", "summary": "Portgas D. Ace dies shielding Luffy from Admiral Akainu's attack, moments after Whitebeard himself falls in the same battle — a loss that breaks Luffy and reshapes the balance of power in the world."},
        {"major": False, "day": 82, "title": "Luffy begins two years of training", "location": "Amazon Lily", "summary": "Still reeling from Ace's death, Luffy accepts Rayleigh's offer of two years of solitary training before the crew reunites."},
        {"major": False, "day": 733, "title": "Reunion at Sabaody", "location": "Sabaody", "summary": "After two years of separate training, the Straw Hat Pirates reunite at Sabaody Archipelago, each dramatically stronger and ready for the Grand Line's second half."},
        {"day": 734, "title": "Fishman Island saved", "location": "Fishman Island", "summary": "Hordy Jones's coup and his New Fishman Pirates are defeated; a lasting alliance between the surface and Fishman Island begins."},
        {"day": 735, "title": "Punk Hazard incident", "location": "Punk Hazard", "summary": "Caesar Clown's poison-gas weapons project is stopped and an alliance is formed with Trafalgar Law against Doflamingo and Kaido."},
        {"day": 736, "title": "Dressrosa liberated", "location": "Dressrosa", "summary": "The Warlord Donquixote Doflamingo is defeated and his decade-long tyranny over Dressrosa ends; the Straw Hat Grand Fleet is born from the allies made here."},
        {"major": False, "day": 748, "title": "The Alliance forms at Zou", "location": "Zou", "summary": "The Ninja–Pirate–Mink–Samurai Alliance forms against Kaido as the crew learns Sanji has been called to an arranged marriage on Whole Cake Island."},
        {"day": 758, "title": "Whole Cake Island — the Tea Party interrupted", "location": "Totto Land", "summary": "Sanji is pulled from his arranged wedding to the Big Mom Pirates in a narrow, costly escape that earns the crew Big Mom's undying wrath."},
        {"major": False, "day": 760, "title": "Landing in Wano", "location": "Wano Country", "summary": "The crew arrives in the isolated shogunate of Wano and begins secretly allying with the Kozuki retainers to bring down Kaido, just as the Reverie convenes overseas."},
        {"day": 763, "title": "Nefertari Cobra's death and Imu's reveal", "location": "Mary Geoise", "summary": "King Cobra is killed after stumbling onto the truth of Imu, the world's hidden ruler — a secret the Celestial Dragons have kept for 800 years."},
        {"day": 774, "title": "The Raid on Onigashima — Wano liberated", "location": "Wano Country", "summary": "The Alliance defeats Kaido and Big Mom in an all-night raid; Luffy awakens his Devil Fruit's true Nika form, the puppet shogun Orochi falls, and Momonosuke is restored as Wano's rightful shogun."},
        {"day": 792, "title": "Lulusia Kingdom is destroyed", "location": "Lulusia Kingdom", "summary": "Imu orders the Government's ancient weapon fired on Lulusia using the Mother Flame, erasing the entire kingdom without warning."},
        {"day": 797, "title": "Egghead Island incident", "location": "Egghead Island", "summary": "Dr. Vegapunk's hidden truths come to light as CP0, an Admiral, and the shadowy St. Saturn move directly against the Straw Hats — an unprecedented direct confrontation between the crew and the world's ruling powers."},
    ]},
    "Hunter x Hunter": {"start_day": -7, "anchor": "Seven days before Gon leaves Whale Island", "events": [
        {"day": 0, "title": "Departure from Whale Island", "location": "Whale Island", "summary": "Gon Freecss leaves home to pursue the Hunter Exam."},
        {"major": False, "day": 1, "title": "Mito's reluctant blessing", "location": "Whale Island", "summary": "Gon's aunt Mito lets him go despite her fear, unwilling to be the one who stops him from following his father's path."},
        {"major": False, "day": 3, "title": "Meeting Kurapika and Leorio", "location": "Route to the Exam", "summary": "Gon meets Kurapika and Leorio en route to the exam site; the four future companions' paths first cross."},
        {"major": False, "day": 4, "title": "Leorio and Kurapika's clash", "location": "Route to the Exam", "summary": "Leorio and Kurapika nearly come to blows over their different reasons for wanting to be Hunters, before an uneasy respect forms."},
        {"major": False, "day": 5, "title": "Hisoka's warning", "location": "Exam Ship", "summary": "Gon draws Hisoka's attention aboard the ship to the exam site after standing up for Leorio."},
        {"day": 7, "title": "Hunter Exam begins", "location": "Hunter Exam Site", "summary": "The annual Hunter Exam gathers applicants and begins its lethal phases, opening with a punishing navigation trial."},
        {"major": False, "day": 8, "title": "The marathon trial", "location": "Hunter Exam Site", "summary": "An 80-kilometer run through shifting wetlands and traps thins the field of applicants before the real trials even begin."},
        {"major": False, "day": 9, "title": "Menchi's gourmet trial", "location": "Hunter Exam Site", "summary": "Examiner Menchi's cooking-based Second Phase forces applicants to hunt exam-specific prey, nearly costing Gon his chance."},
        {"major": False, "day": 12, "title": "Trick Tower phase", "location": "Hunter Exam Site", "summary": "A treacherous multi-choice trial forces uneasy cooperation and betrayal among applicants."},
        {"major": False, "day": 13, "title": "The choice of tunnels", "location": "Hunter Exam Site", "summary": "Gon's group must gamble on one of three unmarked tunnels through Trick Tower, each with a different hidden risk."},
        {"major": False, "day": 15, "title": "A duel of mercy", "location": "Hunter Exam Site", "summary": "A one-on-one bridge duel forces an applicant to choose between a clean win and a crueler, more certain one."},
        {"major": False, "day": 17, "title": "The exam's survival phase", "location": "Hunter Exam Site", "summary": "A lethal hunting phase thins the remaining applicants before the final trial."},
        {"major": False, "day": 18, "title": "Zevil Island's numbered hunt", "location": "Zevil Island", "summary": "Applicants hunt one another for numbered tags, and Killua's unnervingly casual lethality becomes hard to ignore."},
        {"day": 24, "title": "Exam final phase", "location": "Hunter Exam Site", "summary": "One-on-one battles decide the last Hunters of the year, including Hisoka's brutal match; the survivors receive their licenses."},
        {"major": False, "day": 26, "title": "Hisoka's promise", "location": "Hunter Exam Site", "summary": "Hisoka spares Gon and Killua after the exam, promising a real fight once they've grown strong enough to be worth killing."},
        {"major": False, "day": 30, "title": "Gon and Killua's bond forms", "location": "Route to the Exam", "summary": "Fresh from the exam, Gon and Killua begin traveling and training together."},
        {"major": False, "day": 35, "title": "A call back to the Zoldyck estate", "location": "Route to the Exam", "summary": "Killua is quietly summoned home, forcing an early test of how much his new friendships actually mean to him."},
        {"day": 40, "title": "Kukuroo Mountain visit", "location": "Kukuroo Mountain", "summary": "New Hunters challenge the Testing Gate and the Zoldyck estate's defenses."},
        {"major": False, "day": 41, "title": "Silva and Kikyo size up the visitors", "location": "Kukuroo Mountain", "summary": "Killua's parents coldly assess Gon and his companions, unconvinced their son's new path is anything but a phase."},
        {"major": False, "day": 55, "title": "Zushi and the discovery of Nen", "location": "Heavens Arena", "summary": "A young floor climber named Zushi and his teacher Wing introduce Gon and Killua to Nen, a hidden discipline that changes everything about how they fight."},
        {"day": 70, "title": "Heaven's Arena ascent", "location": "Heavens Arena", "summary": "Rising fighters enter the arena's upper floors, where Nen becomes decisive."},
        {"major": False, "day": 85, "title": "Nen categories mastered", "location": "Heavens Arena", "summary": "Gon and Killua work through grueling basic Nen training, each edging toward discovering their own natural affinity."},
        {"major": False, "day": 100, "title": "Reunion before Yorknew", "location": "Yorknew City", "summary": "The four companions reunite ahead of the Yorknew auction, each pursuing their own goal in the city."},
        {"major": False, "day": 170, "title": "The Phantom Troupe converges", "location": "Yorknew City", "summary": "Members of the infamous Phantom Troupe quietly gather in Yorknew ahead of the auction, drawn by rumors of a Kurta-scarlet-eyed item on the block."},
        {"day": 180, "title": "Yorknew auction crisis", "location": "Yorknew City", "summary": "The underground auction and Phantom Troupe converge in Yorknew City."},
        {"day": 190, "title": "Greed Island recruitment", "location": "Yorknew City", "summary": "Battera's agents recruit capable Hunters to enter Greed Island, turning the game's scarce copies into the next major objective."},
        {"day": 230, "title": "Greed Island's final challenge", "location": "Greed Island", "summary": "The remaining players race to complete Greed Island while the Bomber crisis forces allies into a decisive confrontation."},
        {"day": 270, "title": "Chimera Ant outbreak", "location": "NGL", "summary": "The Hunter Association confirms a fast-evolving Chimera Ant threat in the NGL and deploys a small extermination team."},
        {"day": 330, "title": "East Gorteau palace invasion", "location": "East Gorteau", "summary": "Hunters assault the Royal Palace to separate the Chimera Ant Royal Guard from the King before a mass selection can begin."},
        {"day": 365, "title": "Chairman Election", "location": "Hunter Association HQ", "summary": "The Association holds a contentious election for its next chairman while Hunters confront the cost of the Chimera Ant campaign."},
        {"day": 430, "title": "Dark Continent preparations", "location": "Dark Continent Route", "summary": "V5, the Hunter Association, and Kakin begin competing preparations for an expedition beyond the known world."},
    ]},
    "Naruto": {"start_day": -7, "anchor": "Seven days before Naruto's Academy graduation", "events": [
        # Day numbers below are calibrated against the Narutopedia community
        # timeline (User:Seelentau/Naruto Timeline), converted onto this
        # engine's 30-day-month/360-day-year calendar and linearly scaled so
        # Naruto's birth and his Academy graduation land exactly on this
        # world's two pre-existing anchor days (-4380 and 0). Everything else
        # keeps that source's actual relative spacing, so it's meaningfully
        # more accurate than a flat guess — but still an explicit campaign
        # estimate, since the source itself reconstructs approximate dates
        # from scattered manga/databook/novel evidence.
        # These five predate every currently-defined starting era (the
        # earliest is the Third Shinobi World War at day -4900) — they exist
        # purely as CANON HISTORY context for gm_rules, never as something a
        # campaign could actually reach or need to catch up on. historical_only
        # tells fire_canon_events to always skip them, regardless of how
        # confident the anchor-day filter above is for a given save.
        {"major": False, "historical_only": True, "day": -22319, "title": "Konohagakure is founded", "location": "Konohagakure", "summary": "Hashirama Senju and Madara Uchiha end generations of clan warfare, founding Konohagakure together; Hashirama becomes its First Hokage."},
        {"major": False, "historical_only": True, "day": -19822, "title": "Hashirama defeats Madara Uchiha", "location": "Valley of the End", "summary": "Madara Uchiha attacks Konoha and is defeated by Hashirama Senju in their legendary battle, later commemorated by the carved cliffs of the Valley of the End."},
        {"major": False, "historical_only": True, "day": -16710, "title": "The First Shinobi World War ends", "location": "Konohagakure", "summary": "The war closes with Tobirama Senju's death; Hiruzen Sarutobi becomes the Third Hokage in the aftermath."},
        {"major": False, "historical_only": True, "day": -9323, "title": "The Second Shinobi World War begins", "location": "Amegakure", "summary": "War breaks out across the shinobi nations; Kurama, the Nine-Tails, is sealed into Kushina Uzumaki, making her its second jinchuriki."},
        {"major": False, "historical_only": True, "day": -6641, "title": "Sakumo Hatake's death", "location": "Konohagakure", "summary": "The White Fang of Konoha takes his own life after being condemned for choosing to save his comrades over completing a mission — a shadow that will hang over his son Kakashi for years."},
        {"day": -5220, "title": "The original Akatsuki is founded", "location": "Amegakure", "summary": "Yahiko, Nagato, and Konan establish the original Akatsuki as an Amegakure peace movement. The player's decisions can shape its charter, methods, allies, and relationship with Hanzō from its first day."},
        {"day": -4857, "title": "The Kannabi Bridge mission", "location": "Kannabi Bridge", "summary": "Rin Nohara dies and Obito Uchiha is believed killed during a mission gone wrong; Kakashi inherits Obito's Sharingan, and both awaken the Mangekyō Sharingan in their grief."},
        {"day": -4856, "title": "Yahiko's death and Akatsuki's transformation", "location": "Amegakure", "summary": "Yahiko dies after Hanzō and Danzō force a cruel choice on Nagato. The original peace movement survives under a grief-stricken Nagato, while the masked shinobi calling himself Madara begins steering it toward the darker organization later feared as Akatsuki."},
        {"day": -4380, "title": "Naruto's birth and the Nine-Tails attack", "location": "Konohagakure", "banner": "nine_tails_attack_on_konoha", "scope": "wide", "summary": "Naruto is born as Obito's attack breaks Kushina's seal; Minato and Kushina confront the Nine-Tails while Konoha fights for survival."},
        {"major": False, "day": -4233, "title": "Might Duy's sacrifice", "location": "Land of Fire", "summary": "Might Duy rescues Guy, Ebisu, and Genma from the Seven Swordsmen of the Mist, killing two of them before dying from opening the Eight Gates."},
        {"major": False, "day": -3233, "title": "The Hyūga Affair", "location": "Konohagakure", "summary": "After Hiashi Hyūga kills a Kumogakure envoy in retaliation for an attempted kidnapping, his twin brother Hizashi sacrifices his own life under the branch seal to satisfy the peace treaty."},
        {"day": -1603, "title": "The Uchiha Massacre", "location": "Konohagakure", "banner": "uchiha_massacre", "summary": "Itachi Uchiha kills nearly his entire clan in a single night under Konoha's own order to prevent a coup, sparing only his younger brother Sasuke. The truth behind why is hidden from the village for years."},
        {"day": 0, "title": "Academy graduation night — the Mizuki incident", "location": "Konohagakure", "summary": "Naruto's graduation is followed the same night by Mizuki's betrayal: he tricks Naruto into stealing the Forbidden Scroll of Seals before being stopped, and the new genin generation begins forming."},
        {"major": False, "day": 2, "title": "Ninja Registration Day", "location": "Konohagakure", "summary": "Naruto is formally registered as a shinobi of the Hidden Leaf, and meets Konohamaru for the first time."},
        {"major": False, "day": 3, "title": "The Graduation Ceremony", "location": "Konohagakure", "summary": "Twenty-seven students graduate into nine three-person genin teams."},
        {"major": False, "day": 4, "title": "Team 7 is formed", "location": "Konohagakure", "summary": "Kakashi Hatake accepts Naruto, Sasuke, and Sakura as Team 7, alongside the formation of Team 8 and Team 10."},
        {"major": False, "day": 20, "title": "D-rank missions begin", "location": "Konohagakure", "summary": "Team 7 starts a run of menial village chores and errands — the unglamorous reality before real missions are trusted to them."},
        {"major": False, "day": 40, "title": "The client's request", "location": "Konohagakure", "summary": "A traveling bridge-builder requests an escort mission undersold as routine, setting up a far more dangerous job than advertised."},
        {"day": 56, "title": "Land of Waves mission begins", "location": "Land of Waves", "banner": "land_of_waves_mission", "summary": "Team 7 begins the bridge-builder escort mission and is immediately ambushed, then confronted by the missing-nin Zabuza Momochi, revealing the client's true danger."},
        {"major": False, "day": 60, "title": "Zabuza's ambush", "location": "Land of Waves", "summary": "The Demon of the Hidden Mist attacks the escort team directly, aided by his masked companion Haku."},
        {"major": False, "day": 65, "title": "A quiet conversation in the woods", "location": "Land of Waves", "summary": "Haku speaks candidly about strength and precious people with Naruto in the forest, neither realizing they'll soon meet as enemies."},
        {"day": 70, "title": "Battle of the Great Naruto Bridge", "location": "Land of Waves", "summary": "Zabuza and Haku are confronted a final time; Haku dies protecting Zabuza, Zabuza kills Gato, and dies from Gato's men's wounds. The bridge battle reshapes Team 7's understanding of shinobi life and death."},
        {"major": False, "day": 76, "title": "Team 7 returns from the Land of Waves", "location": "Konohagakure", "summary": "Team 7 completes the Naruto Bridge and returns home, resuming routine missions."},
        {"major": False, "day": 100, "title": "Chūnin Exam nominations", "location": "Konohagakure", "summary": "Jōnin instructors across the village nominate their genin teams for the upcoming Chūnin Exams as foreign shinobi begin arriving in Konoha."},
        {"day": 161, "title": "Chūnin Exams begin", "location": "Konohagakure", "summary": "Genin from multiple villages gather for the written exam and the Forest of Death survival trial. Orochimaru infiltrates the exam and marks Sasuke with the cursed seal."},
        {"major": False, "day": 166, "title": "Chūnin Exam preliminaries", "location": "Konohagakure", "summary": "One-on-one preliminary matches thin the surviving genin ahead of the final tournament, revealing hidden strength and rivalries; Naruto meets Jiraiya the same night."},
        {"major": False, "day": 175, "title": "One month of final-round training", "location": "Konohagakure", "summary": "Finalists scatter to train intensively before the Chūnin Exam finals — Naruto with Jiraiya, Sasuke with Kakashi — each seeking an edge from a mentor or hidden technique."},
        {"major": False, "day": 185, "title": "The curse mark's temptation", "location": "Konohagakure", "summary": "Sasuke wrestles with the cursed seal's promised power as Kakashi works out a way to counter it before the finals."},
        {"day": 190, "title": "Chūnin Exam finals and the Konoha Crush", "location": "Konohagakure", "scope": "wide", "summary": "The exam finals become the cover for a coordinated invasion by Sunagakure and Otogakure; the Third Hokage, Hiruzen Sarutobi, dies sealing away Orochimaru's arms — unless prior divergences alter the outcome."},
        {"day": 192, "title": "The search for Tsunade begins", "location": "Konohagakure", "banner": "search_for_tsunade", "summary": "With Itachi and Kisame sighted entering the village, Jiraiya and Naruto set out to track down the Sannin Tsunade and convince her to become the Fifth Hokage."},
        {"major": False, "day": 229, "title": "Tsunade becomes Fifth Hokage", "location": "Konohagakure", "summary": "Tsunade returns to Konoha with Naruto and Jiraiya and formally accepts the title of Fifth Hokage."},
        {"day": 238, "title": "Sasuke's Departure", "location": "Konohagakure", "banner": "sasukes_departure", "summary": "Consumed by the pull of Orochimaru's power, Sasuke abandons Konoha in the night after clashing with Naruto on the hospital rooftop."},
        {"day": 241, "title": "Sasuke Retrieval Mission", "location": "Land of Rice Fields", "banner": "sasuke_retrieval_mission", "summary": "A team of genin pursues Sasuke to bring him back, each facing one of Orochimaru's Sound Four in a running battle that costs the team dearly; Naruto and Sasuke's confrontation at the Valley of the End ends with Sasuke continuing on to Orochimaru."},
        {"major": False, "day": 330, "title": "Naruto departs with Jiraiya", "location": "Konohagakure", "summary": "Naruto leaves Konoha with Jiraiya for two and a half years of training, after Jiraiya tells him of Akatsuki's true threat."},
        {"major": False, "day": 1069, "title": "Naruto returns after the training journey", "location": "Konohagakure", "summary": "Naruto and Jiraiya return to the village after roughly two and a half years, and Naruto retakes Kakashi's old bell test alongside Sakura."},
        {"day": 1076, "title": "Gaara's death and rescue", "location": "Sunagakure", "banner": "gaara_rescue", "summary": "Akatsuki's Deidara and Sasori extract Shukaku from Gaara, killing him; Sakura and Chiyo defeat Sasori, and Chiyo sacrifices her own life to revive Gaara — the crew's first direct confrontation with Akatsuki."},
        {"major": False, "day": 1337, "title": "Asuma Sarutobi's death", "location": "Land of Fire", "summary": "Hidan of Akatsuki kills Asuma Sarutobi before Shikamaru's team avenges him."},
        {"day": 1360, "title": "Jiraiya's death in Amegakure", "location": "Amegakure", "summary": "Jiraiya infiltrates Amegakure to learn the truth behind Pain, fights Pain and Konan, and dies delivering crucial intelligence back to Konoha with his final moments."},
        {"day": 1361, "title": "Itachi Uchiha's death", "location": "Land of Fire", "summary": "Sasuke finally confronts and kills Itachi in single combat; Itachi, already dying of illness, ensures his brother survives the fight."},
        {"day": 1400, "title": "Itachi's Truth", "location": "Land of Fire", "banner": "itachis_truth", "summary": "In the aftermath of Itachi's death, the truth of the Uchiha Massacre comes to light: Itachi acted under Konoha's own order to prevent a coup, sacrificing his name and his brother's hatred to protect the village he loved."},
        {"day": 1409, "title": "Pain's Assault on Konoha", "location": "Konohagakure", "banner": "pains_assault_on_konoha", "scope": "wide", "summary": "Pain launches a full assault on Konohagakure in pursuit of Naruto, leveling much of the village within minutes."},
        {"day": 1409, "title": "Naruto vs. Pain", "location": "Konohagakure", "banner": "naruto_vs_pain", "summary": "Naruto confronts Pain directly, ultimately learning Nagato's true identity and choosing to spare him — a choice that reshapes the Akatsuki leader's own resolve as he sacrifices himself to revive the villagers he killed."},
        {"major": False, "day": 1410, "title": "The Five Kage Summit", "location": "Iron Country", "summary": "The Five Kage meet to decide how to respond to Akatsuki, only for Sasuke to attack the summit himself; the masked Akatsuki leader declares the Fourth Shinobi World War in the chaos that follows."},
        {"day": 1420, "title": "Obito's Reveal", "location": "Fourth War Front", "banner": "obitos_reveal", "summary": "The masked man behind Akatsuki's true plan is revealed to be Obito Uchiha, Kakashi's presumed-dead teammate, radically reframing the entire war's cause."},
        {"day": 1684, "title": "The Fourth Shinobi World War begins", "location": "Fourth War Front", "scope": "wide", "summary": "The Allied Shinobi Forces mobilize against Akatsuki's reanimated army, opening the war that will decide the future of the shinobi world."},
        {"day": 1685, "title": "Kaguya's Appearance", "location": "Kaguya's Dimension", "banner": "kaguyas_appearance", "summary": "Obito casts the Infinite Tsukuyomi, but Black Zetsu's betrayal uses him to revive Kaguya Ōtsutsuki instead — a threat beyond anything the shinobi world has faced, who kills Obito himself moments later."},
        {"day": 1686, "title": "Naruto and Sasuke vs. Kaguya", "location": "Kaguya's Dimension", "banner": "naruto_and_sasuke_vs_kaguya", "summary": "Naruto and a reconciled Sasuke seal Kaguya away for good, ending the Fourth Shinobi World War and the immediate threat to the entire world; Madara dies as the Ten-Tails is removed from him."},
        {"day": 1687, "title": "Naruto vs. Sasuke — Final Valley", "location": "Valley of the End", "banner": "naruto_vs_sasuke_final_valley", "summary": "With the war won, Naruto and Sasuke settle their own long rivalry in a final, defining battle at the Valley of the End, each losing an arm before finally reconciling."},
        {"major": False, "day": 2064, "title": "Kakashi becomes Sixth Hokage", "location": "Konohagakure", "summary": "Kakashi Hatake is named the Sixth Hokage in the war's aftermath, the same month Sasuke leaves the village once more to atone for the past on his own terms."},
        {"major": False, "day": 2553, "title": "Naruto and Hinata marry", "location": "Konohagakure", "summary": "Naruto Uzumaki and Hinata Hyūga marry in Konohagakure, years after the war's end."},
        {"day": 4413, "title": "Naruto Becomes Hokage", "location": "Konohagakure", "banner": "naruto_becomes_hokage", "scope": "wide", "summary": "Naruto is formally named the Seventh Hokage, fulfilling his childhood dream and the village's recognition of everything he sacrificed to earn it."},
        {"major": False, "day": 6910, "title": "Momoshiki and Kinshiki's attack", "location": "Konohagakure", "summary": "During the Chūnin Exams hosted in Konoha, the Ōtsutsuki invaders Momoshiki and Kinshiki attack the village, forcing the next generation of shinobi into their first real crisis."},
    ]},
    "Solo Max-Level Newbie": {"start_day": -3, "anchor": "Three days before the Tower appears", "events": [
        {"day": 0, "title": "Tower manifestation", "location": "Earth — Tower Entrance", "summary": "The Tower of Trials manifests in reality and humanity receives its first scenario, with a deadline for every player to clear each floor or face annihilation."},
        {"day": 1, "title": "First-floor scenario", "location": "Floor 1", "summary": "Players enter the opening floor while hidden conditions and first achievements become available to those who know to look."},
        {"major": False, "day": 1, "title": "Park Hana's ambush", "location": "Floor 1", "summary": "A desperate rival named Park Hana tries to stab Kang Jinhyuk in the Floor 1 labyrinth and is instead beaten and drawn into his growing circle."},
        {"major": False, "day": 2, "title": "The National Museum incident", "location": "Earth — Tower Entrance", "summary": "Min Jeong-woo attempts to steal a priceless map while Yu-ri Lee moves to stop him; someone with full foreknowledge of the game quietly benefits without being drawn into the fight."},
        {"major": False, "day": 3, "title": "The first deaths", "location": "Floor 1", "summary": "Casual players who underestimate the Tower begin dying in earnest, and the scale of the threat becomes impossible to deny."},
        {"major": False, "day": 5, "title": "Old instincts, new stakes", "location": "Floor 1", "summary": "A former streamer's old audience-building instincts resurface, this time backed by real, lethal consequences instead of a game score."},
        {"day": 7, "title": "Guild consolidation", "location": "Earth — Tower Entrance", "summary": "Major guilds and governments compete to control information, recruits, and early rewards."},
        {"major": False, "day": 10, "title": "Corporate scouting begins", "location": "Earth — Tower Entrance", "summary": "Goinmul Corporation and rival organizations start quietly identifying and recruiting standout early clearers."},
        {"major": False, "day": 14, "title": "First real boss attempts", "location": "Floor 1", "summary": "The strongest early clearers begin serious attempts on the floor's boss, exposing mechanics ordinary players never find."},
        {"day": 20, "title": "Early boss race", "location": "Floor 5", "summary": "Leading players race for first-clear rewards and concealed boss conditions."},
        {"major": False, "day": 25, "title": "Hidden achievement hunting", "location": "Floor 2", "summary": "Someone with complete foreknowledge of the game methodically claims hidden achievements no ordinary player would think to look for."},
        {"major": False, "day": 30, "title": "The gap widens", "location": "Floor 2", "summary": "The fastest climbers reach Floor 2 well ahead of the pack, and the divide between top players and everyone else becomes stark public knowledge."},
    ]},
    "Overgeared": {"start_day": -3, "anchor": "Three days before Grid discovers Pagma's legacy", "events": [
        {"major": False, "day": -3, "title": "The Sun Sword bargain", "location": "Winston", "summary": "Desperate for a way to progress, Grid takes on a quest to find Pagma's Rare Book in exchange for a legendary-class weapon, the Sun Sword."},
        {"day": 0, "title": "Pagma's legacy changes hands", "location": "Winston", "summary": "Grid finds Pagma's Rare Book, triggers the SS-rank quest Earl Ashur's Anger, and chooses to use the book himself rather than surrender it — a legendary-class turning point in Satisfy."},
        {"major": False, "day": 2, "title": "Piaro's offer", "location": "Kesan Canyon", "summary": "Piaro, the disgraced former knight captain of the Red Knights hiding from the Saharan Empire, judges Grid's rapid growth and offers him a revenge quest — one Grid isn't yet strong enough to accept."},
        {"major": False, "day": 4, "title": "The Temple of Yatan", "location": "Temple of Yatan", "summary": "Grid is drawn into Doran's quest to rescue Irene inside the Temple of Yatan; Doran is killed by the cultist Yura before it ends."},
        {"day": 7, "title": "Winston class-quest pressure", "location": "Winston", "summary": "Local politics, crafting opportunities, and player competition intensify around Winston."},
        {"major": False, "day": 10, "title": "Failure after failure", "location": "Winston", "summary": "Grid grinds through repeated failed crafting attempts, his results still far below the legendary standard Pagma once set."},
        {"major": False, "day": 15, "title": "Kesan Canyon expedition", "location": "Kesan Canyon", "summary": "Searching for Pagma's Swordsmanship, Grid discovers how to combine Skills into new, more powerful fused techniques."},
        {"major": False, "day": 22, "title": "Whispers of an unusual player", "location": "Winston", "summary": "Rumors begin spreading among competing guilds of an oddly overpowered low-level player operating out of Winston."},
        {"day": 30, "title": "Guild attention grows", "location": "Winston", "summary": "Major players and guilds begin pursuing rumors of exceptional crafted equipment."},
        {"major": False, "day": 45, "title": "An ancient lich takes notice", "location": "Winston", "summary": "The arrogant, ancient lich Braham takes a distant, contemptuous interest in Grid's unorthodox mastery of Pagma's forbidden techniques."},
        {"major": False, "day": 60, "title": "Piaro's revenge, revisited", "location": "Kesan Canyon", "summary": "Now stronger, Grid returns to Piaro to finally take up the revenge quest he once had to refuse."},
        {"major": False, "day": 62, "title": "Piaro relocates to Reidan", "location": "Reidan", "summary": "Piaro leaves his hermitage in Kesan Canyon to train Grid directly at Reidan, the first of his knightly techniques passed on in earnest."},
        {"major": False, "day": 75, "title": "Guild recruitment pressure", "location": "Winston", "summary": "Large guilds attempt to recruit or quietly pressure the increasingly notable Grid into joining their ranks."},
        {"day": 90, "title": "Reidan frontier window", "location": "Reidan", "summary": "The neglected frontier becomes strategically important to emerging powers."},
    ]},
    "Reincarnated as a Slime": {"start_day": -7, "anchor": "Seven days before Satoru Mikami's reincarnation", "events": [
        {"day": 0, "title": "A new slime awakens", "location": "Great Jura Forest", "summary": "An otherworlder reincarnates as a slime inside the Sealed Cave."},
        {"major": False, "day": 1, "title": "Meeting Veldora", "location": "Great Jura Forest", "summary": "The newly reincarnated slime meets the imprisoned Storm Dragon Veldora, exchanging names and stories in the cave."},
        {"day": 2, "title": "Veldora disappears", "location": "Great Jura Forest", "summary": "The Storm Dragon's presence vanishes from the outside world, disturbing the Jura Forest's balance of power."},
        {"major": False, "day": 3, "title": "Naming a new Skill", "location": "Great Jura Forest", "summary": "The slime's analytical Skill takes on the name Great Sage, and cautious exploration of the cave's depths begins in earnest."},
        {"major": False, "day": 5, "title": "Ranga and the Direwolves", "location": "Great Jura Forest", "summary": "After an attack by goblin-hunting Direwolves, the slime becomes the pack's new leader, and Ranga emerges as a loyal companion."},
        {"major": False, "day": 8, "title": "Cautious goblin scouts", "location": "Goblin Village outskirts", "summary": "Goblin scouts spot the strange, talking slime and its new wolf pack, more curious than hostile."},
        {"day": 12, "title": "Goblin village crisis", "location": "Goblin Village", "summary": "Direwolf pressure forces a small goblin settlement toward a decisive alliance."},
        {"major": False, "day": 15, "title": "Shizu's final journey", "location": "Great Jura Forest", "summary": "The otherworlder Shizue Izawa is met in the forest; her death shortly after passes her Unique Skill and a promise on to the slime."},
        {"major": False, "day": 16, "title": "A new name taken up", "location": "Great Jura Forest", "summary": "Following Shizu's dying gift, the slime adopts the name she gave it — Rimuru Tempest — and starts being known by it."},
        {"major": False, "day": 20, "title": "The mass naming of the goblins", "location": "Goblin Village", "summary": "Naming the goblin tribe en masse evolves them into hobgoblins, at real cost to the namer's own magicule reserves."},
        {"major": False, "day": 30, "title": "Kaijin and the dwarven blacksmiths", "location": "Goblin Village", "summary": "Exiled dwarven craftsmen led by Kaijin are rescued and join the growing settlement, founding its early industry."},
        {"major": False, "day": 38, "title": "Rigurd takes up administration", "location": "Goblin Village", "summary": "A steady goblin elder named Rigurd begins organizing the growing settlement's daily affairs, freeing Rimuru to focus elsewhere."},
        {"day": 45, "title": "Dwargon contact window", "location": "Dwargon", "summary": "Crafting needs and diplomacy pull the growing monster community toward Dwargon."},
        {"major": False, "day": 52, "title": "A first cautious trade route", "location": "Dwargon", "summary": "A tentative trade relationship opens between the settlement and its dwarven neighbors, the first sign of real nationhood."},
        {"major": False, "day": 60, "title": "The Orc Disaster gathers", "location": "Great Jura Forest", "summary": "A starving Orc Lord's forces begin threatening every settlement in the forest, forcing old rivals into uneasy alliance."},
        {"major": False, "day": 65, "title": "Old rivals debate war", "location": "Great Jura Forest", "summary": "Leaders across the forest argue over how — or whether — to respond together to the swelling Orc threat."},
        {"major": False, "day": 70, "title": "The Orc Lord falls", "location": "Great Jura Forest", "summary": "The Orc Disaster is defeated and its surviving people are accepted into the growing alliance, dramatically expanding the settlement and drawing the attention of nearby powers."},
        {"major": False, "day": 74, "title": "A Demon Lord's idle curiosity", "location": "Dragon Peak", "summary": "Rumors of an upstart monster settlement and its unusual leader first reach Milim Nava, who finds the idea more entertaining than threatening."},
        {"major": False, "day": 80, "title": "Benimaru steps up", "location": "Tempest", "summary": "The hobgoblin Benimaru distinguishes himself organizing the settlement's defenders in the Orc Disaster's aftermath."},
        {"major": False, "day": 90, "title": "New specialists arrive", "location": "Tempest", "summary": "Additional dwarven craftsmen round out the settlement's early industry, from potion-brewing to construction."},
        {"day": 100, "title": "Tempest emerges", "location": "Tempest", "summary": "A multi-species settlement begins to become a recognized nation."},
        {"major": False, "day": 130, "title": "Demon Lord Milim visits", "location": "Tempest", "summary": "Milim Nava arrives in Tempest out of curiosity, creating both an extraordinary opportunity and a dangerous diplomatic test."},
        {"day": 180, "title": "Falmuth invades Tempest", "location": "Tempest", "summary": "Falmuth's army and allied otherworlders attack Tempest under an anti-monster barrier, turning political hostility into a national catastrophe."},
        {"day": 184, "title": "Harvest Festival", "location": "Tempest", "summary": "A Demon Lord awakening and mass resurrection transform Tempest's leadership, people, and standing among the world's great powers."},
        {"day": 200, "title": "Walpurgis", "location": "Demon Lord's Domain", "summary": "The Demon Lords convene as Clayman's schemes collapse and Tempest's new place in the balance of power is formally tested."},
    ]},
    # Day numbers below are the best available reconstruction, not a single
    # manga-stated day-by-day countdown — the source is precise about
    # Rukia's execution clock (a 35-day grace period shortened to 25 by
    # Central 46, later moved up further) but does not give one clean
    # total day-count from her arrival to the Soul Society infiltration.
    # Pre-day-0 historical_only entries (Masaki's death, Kaien's death) use
    # the same kind of explicit campaign-relative estimate the other
    # worlds' ancient-era entries already use, since canon gives ages and
    # rough eras here too, not exact dates.
    "Bleach": {"start_day": -7, "anchor": "One week before Rukia Kuchiki arrives in Karakura Town", "events": [
        {"major": True, "historical_only": True, "day": -40150, "title": "Turn Back the Pendulum", "location": "Seireitei", "scope": "wide", "summary": "Roughly 110 years before Ichigo's story, disappearances in Rukongai and secret Hollowfication experiments place several captains and lieutenants on the path that will drive them into exile.", "spoiler": True},
        {"major": False, "historical_only": True, "day": -2190, "title": "Masaki Kurosaki's death", "location": "Karakura Town", "summary": "A Hollow called Grand Fisher kills Ichigo's mother on a riverbank while she shields him — he was nine years old, and could not yet tell humans from spirits."},
        {"major": False, "historical_only": True, "day": -1460, "title": "Kaien Shiba's death", "location": "Seireitei", "summary": "The 13th Division's lieutenant, Kaien Shiba, and his wife Miyako are killed by a Hollow. No one has been promoted to fill the vacant lieutenant seat since."},
        {"day": 0, "title": "Rukia Kuchiki arrives in Karakura Town", "location": "Kurosaki Clinic", "scope": "personal", "summary": "A Hollow attacks the Kurosaki family; badly wounded fighting it, Rukia transfers her own Shinigami powers to Ichigo — an act forbidden by Soul Society law — so he can save his family and finish the Hollow himself.", "banner":"ichigo_receives_soul_reaper_powers"},
        {"major": False, "day": 20, "title": "Uryu Ishida makes himself known", "location": "Karakura Town", "summary": "The last known Quincy in the area confronts Ichigo over a Shinigami's duty versus a Quincy's, opening a rivalry rooted in a much older grudge between their two traditions."},
        {"major": False, "day": 40, "title": "Orihime and Chad's spiritual awareness grows", "location": "Karakura Town", "summary": "Prolonged proximity to Ichigo's now-considerable Reiryoku begins waking latent spiritual power in his closest friends."},
        {"day": 60, "title": "Renji and Byakuya come for Rukia", "location": "Karakura Town", "scope": "personal", "summary": "Lieutenant Renji Abarai and Captain Byakuya Kuchiki arrive under Soul Society orders to reclaim Rukia's powers and return her for trial.", "banner":"rukia_retrieval"},
        {"day": 61, "title": "Rukia is sentenced to execution", "location": "Seireitei", "scope": "wide", "summary": "Central 46 sentences Rukia to death for the forbidden transfer and accelerates the execution timetable.", "spoiler": True},
        {"major": False, "day": 71, "title": "Training with Urahara Kisuke", "location": "Urahara Shop", "summary": "Kisuke Urahara trains Ichigo for ten intensive days, restoring and strengthening his Shinigami powers and teaching him to physically open a path into Soul Society."},
        {"day": 74, "title": "The push into Seireitei", "location": "Seireitei", "scope": "wide", "summary": "Ichigo and his allies force their way into Soul Society and begin fighting through the Gotei 13 toward Rukia's execution.", "banner":"seireitei_invasion"},
        {"day": 88, "title": "Aizen's betrayal at Sokyoku Hill", "location": "Sokyoku Hill", "scope": "wide", "summary": "At the execution, Sosuke Aizen reveals that he manipulated Rukia's sentence to recover the Hogyoku before defecting with Gin Ichimaru and Kaname Tosen.", "spoiler": True, "banner":"aizen_betrayal", "requires":["Rukia is sentenced to execution"]},
        {"day": 175, "title": "Arrancar appear in Karakura", "location": "Karakura Town", "scope": "wide", "summary": "Arrancar scouts bring the threat of Hueco Mundo directly into the World of the Living.", "spoiler": True, "banner":"arrancar_arrival", "requires":["Aizen's betrayal at Sokyoku Hill"]},
        {"day": 185, "title": "The Visored approach Ichigo", "location": "Karakura Town", "scope": "personal", "summary": "Hidden exiles offer Ichigo a way to confront the Hollow power growing within him.", "spoiler": True, "requires":["Arrancar appear in Karakura"]},
        {"day": 205, "title": "Orihime is taken to Hueco Mundo", "location": "Karakura Town", "scope": "personal", "summary": "An Arrancar operation isolates Orihime and compels her to enter Hueco Mundo.", "spoiler": True, "requires":["Arrancar appear in Karakura"]},
        {"day": 214, "title": "Hueco Mundo rescue begins", "location": "Hueco Mundo Desert", "scope": "personal", "summary": "Ichigo's group enters Hueco Mundo and advances toward Las Noches.", "spoiler": True, "banner":"hueco_mundo_rescue", "requires":["Orihime is taken to Hueco Mundo"]},
        {"day": 226, "title": "Ichigo confronts Grimmjow", "location": "Las Noches", "scope": "personal", "summary": "The rivalry between Ichigo and Grimmjow reaches its decisive battle.", "spoiler": True, "requires":["Hueco Mundo rescue begins"]},
        {"day": 238, "title": "Ichigo confronts Ulquiorra", "location": "Las Noches", "scope": "personal", "summary": "A desperate confrontation atop Las Noches pushes Ichigo's Hollow power beyond his control.", "spoiler": True, "requires":["Hueco Mundo rescue begins"]},
        {"day": 252, "title": "The battle for Fake Karakura Town", "location": "Karakura Town", "scope": "wide", "summary": "The Gotei 13 confronts Aizen's forces over the fate of Karakura Town.", "spoiler": True, "banner":"fake_karakura_battle", "requires":["Aizen's betrayal at Sokyoku Hill"]},
        {"day": 278, "title": "Ichigo's final confrontation with Aizen", "location": "Karakura Town", "scope": "wide", "summary": "Ichigo returns from Dangai training for a battle whose cost can change his relationship with Shinigami power.", "spoiler": True, "banner":"ichigo_vs_aizen", "requires":["The battle for Fake Karakura Town"]},
        {"day": 795, "title": "Xcution enters Ichigo's life", "location": "Karakura Town", "scope": "personal", "summary": "Seventeen months later, Fullbringers offer Ichigo a route toward recovering the power he lost.", "spoiler": True, "requires":["Ichigo's final confrontation with Aizen"]},
        {"day": 850, "title": "Ichigo's Soul Reaper powers return", "location": "Karakura Town", "scope": "personal", "summary": "Soul Society intervenes as the conflict with Xcution reaches its decisive turn.", "spoiler": True, "banner":"soul_reaper_powers_restored", "requires":["Xcution enters Ichigo's life"]},
        {"day": 930, "title": "The Wandenreich declares war", "location": "Seireitei", "scope": "wide", "summary": "A hidden Quincy empire gives Soul Society five days before annihilation and begins its first invasion.", "spoiler": True, "banner":"wandenreich_invasion", "requires":["Ichigo's Soul Reaper powers return"]},
        {"day": 935, "title": "The first invasion of Soul Society", "location": "Seireitei", "scope": "wide", "summary": "Sternritter breach Seireitei, steal Bankai and inflict catastrophic losses on the Gotei 13.", "spoiler": True, "requires":["The Wandenreich declares war"]},
        {"day": 950, "title": "Royal Guard training", "location": "Soul King Palace", "scope": "personal", "summary": "Survivors are taken to the Royal Realm to heal, reforge and prepare for the next invasion.", "spoiler": True, "requires":["The first invasion of Soul Society"]},
        {"day": 970, "title": "The second Wandenreich invasion", "location": "Seireitei", "scope": "wide", "summary": "The Quincy empire replaces Seireitei with its own shadow domain and resumes the war.", "spoiler": True, "banner":"second_wandenreich_invasion", "requires":["The first invasion of Soul Society"]},
        {"day": 990, "title": "The Soul King crisis", "location": "Soul King Palace", "scope": "wide", "summary": "The war reaches the lynchpin holding the worlds together, threatening the balance of every realm.", "spoiler": True, "banner":"soul_king_crisis", "requires":["The second Wandenreich invasion"]},
        {"day": 1005, "title": "Wahrwelt final battle", "location": "Wahrwelt", "scope": "wide", "summary": "The remaining forces converge on Yhwach's transformed stronghold for the final struggle over the worlds' future.", "spoiler": True, "banner":"wahrwelt_final_battle", "requires":["The Soul King crisis"]},
    ]},
    "Jujutsu Kaisen": {"start_day": -7, "anchor": "One week before Yuji Itadori consumes Sukuna's finger", "events": [
        {"major": True, "historical_only": True, "day": -4018, "title": "Hidden Inventory mission", "location": "Tokyo Jujutsu High", "scope": "wide", "summary": "Satoru Gojo and Suguru Geto are assigned to protect the Star Plasma Vessel, a mission that changes both sorcerers and the modern jujutsu world.", "spoiler": True},
        {"major": True, "historical_only": True, "day": -281, "title": "Yuta Okkotsu enrolls", "location": "Tokyo Jujutsu High", "scope": "personal", "summary": "Yuta Okkotsu enters Tokyo Jujutsu High while bound to the extraordinarily powerful cursed spirit Rika.", "spoiler": True},
        {"major": True, "historical_only": True, "day": -81, "title": "Night Parade of a Hundred Demons", "location": "Tokyo", "scope": "wide", "summary": "Suguru Geto releases curses across Tokyo and Kyoto while pursuing Yuta and Rika.", "spoiler": True},
        {"day": 0, "title": "Yuji Itadori consumes Sukuna's finger", "location": "Sugisawa High School", "scope": "wide", "summary": "A cursed object draws curses to Yuji's school; to save others, Yuji swallows a finger of Ryomen Sukuna and survives as his vessel.", "banner":"sukuna_finger"},
        {"day": 3, "title": "The detention-center special grade", "location": "Eishu Juvenile Detention Center", "scope": "wide", "summary": "First-year students are sent into a detention center transformed by a special-grade cursed womb.", "spoiler": True, "requires":["Yuji Itadori consumes Sukuna's finger"]},
        {"day": 24, "title": "Mahito's transfigured humans", "location": "Tokyo", "scope": "wide", "summary": "Investigations expose a curse capable of reshaping souls and a human student drawn into its influence.", "spoiler": True, "requires":["The detention-center special grade"]},
        {"day": 60, "title": "Kyoto Sister-School Goodwill Event", "location": "Tokyo Jujutsu High", "scope": "wide", "summary": "Tokyo and Kyoto students meet for competition while factions inside jujutsu society pursue conflicting orders.", "spoiler": True, "requires":["Mahito's transfigured humans"]},
        {"day": 120, "title": "Death Painting investigation", "location": "Saitama", "scope": "wide", "summary": "A bridge curse and incarnated Death Paintings draw the students into a linked series of lethal confrontations.", "spoiler": True, "requires":["Kyoto Sister-School Goodwill Event"]},
        {"day": 183, "title": "The Shibuya Incident begins", "location": "Shibuya", "scope": "wide", "summary": "A curtain traps civilians in Shibuya and coordinated curse users move to seal Satoru Gojo.", "spoiler": True, "banner":"shibuya_incident", "requires":["Death Painting investigation"]},
        {"day": 184, "title": "Shibuya's balance collapses", "location": "Shibuya", "scope": "wide", "summary": "Multiple battles, domain clashes and mass casualties permanently alter the balance of the jujutsu world.", "spoiler": True, "requires":["The Shibuya Incident begins"]},
        {"day": 205, "title": "The Culling Game is declared", "location": "Japan", "scope": "wide", "summary": "Barrier colonies and compulsory rules turn much of Japan into a lethal ritual involving awakened and incarnated sorcerers.", "spoiler": True, "requires":["Shibuya's balance collapses"]},
    ]},
    "Custom World": {"start_day": -7, "anchor": "Seven days before the world's opening incident", "events": [
        {"day": 0, "title": "Opening incident", "location": "Starting Region", "summary": "The custom world's first major story pressure begins; adapt this event to the player's setting."},
    ]},
}


def timeline_for(world):
    return CANON_TIMELINES.get(world, CANON_TIMELINES["Custom World"])


# Alternate starting points for an ORIGINAL (non-canon-character) campaign —
# distinct from MAJOR_CHARACTER_STARTS below, which is about playing a
# specific named canon character. This is about letting a player's own
# character begin in a meaningfully different era of the same world. Only
# added where a world actually has a well-known distant era to place a
# character in; not every world does, and these day offsets are the same
# kind of explicit campaign-relative estimate CANON_TIMELINES already uses
# for ancient-era entries — canon gives ages and rough eras, not a
# day-by-day calendar, so exact precision isn't the goal, a believable
# placement is. The first entry in each list is always the existing default.
WORLD_STARTING_ERAS = {
    "Naruto": [
        {"id": "academy_graduation", "label": "Academy Graduation (default)", "start_day": -7,
         "anchor": "Seven days before Naruto's Academy graduation."},
        {"id": "third_shinobi_war", "label": "The Third Shinobi World War", "start_day": -4900,
         "anchor": "During the closing stretch of the Third Shinobi World War, shortly before the Kannabi Bridge mission — Kakashi, Obito and Rin's generation are still on the front lines."},
        {"id": "before_naruto_birth", "label": "A week before Naruto's birth", "start_day": -4387,
         "anchor": "One week before Kushina gives birth to Naruto and the Nine-Tails attacks the village."},
        {"id": "uchiha_massacre_eve", "label": "Eve of the Uchiha Massacre", "start_day": -1604,
         "anchor": "One day before Itachi's mission destroys the Uchiha clan and permanently changes Konoha's political balance."},
        {"id": "shippuden_return", "label": "Naruto Returns to Konoha", "start_day": 1068,
         "anchor": "One day before Naruto returns from his training journey and the Akatsuki move openly against the jinchuriki."},
        {"id": "fourth_war_eve", "label": "Eve of the Fourth Shinobi World War", "start_day": 1683,
         "anchor": "The Allied Shinobi Forces are assembling one day before the Fourth Shinobi World War begins."},
    ],
    "One Piece": [
        {"id": "east_blue_departure", "label": "East Blue Departure (default)", "start_day": -7,
         "anchor": "Seven days before Luffy leaves Foosha Village."},
        {"id": "year_before_departure", "label": "One year before Luffy's departure", "start_day": -367,
         "anchor": "One year before Luffy leaves Foosha Village — still growing up there, well before the East Blue voyage begins."},
        {"id": "rogers_execution", "label": "Gold Roger's execution", "start_day": -7799,
         "anchor": "Twenty-two years before Luffy sets sail, on the day Gold Roger is executed at Loguetown and the Great Pirate Era begins."},
        {"id": "marineford_eve", "label": "Eve of the Summit War", "start_day": 67,
         "anchor": "The day before the Battle of Marineford, while Ace awaits execution and the world's great powers converge."},
        {"id": "new_world_reunion", "label": "Straw Hat Reunion", "start_day": 732,
         "anchor": "One day before the Straw Hats reunite at Sabaody after two years of training."},
    ],
    "Hunter x Hunter": [
        {"id": "hunter_exam", "label": "Hunter Exam Journey (default)", "start_day": -7,
         "anchor": "Seven days before Gon leaves Whale Island to pursue the Hunter Exam."},
        {"id": "yorknew_buildup", "label": "Yorknew Auction Buildup", "start_day": 160,
         "anchor": "Ten days before the Phantom Troupe converges on Yorknew and the underground auction crisis begins."},
        {"id": "greed_island", "label": "Greed Island Recruitment", "start_day": 190,
         "anchor": "As Hunters and collectors begin recruiting capable players for Greed Island."},
        {"id": "chimera_ant_outbreak", "label": "Chimera Ant Outbreak", "start_day": 270,
         "anchor": "At the first confirmed signs of the Chimera Ant threat in the NGL."},
    ],
    "Solo Max-Level Newbie": [
        {"id": "tower_manifestation", "label": "Tower Manifestation (default)", "start_day": -3,
         "anchor": "Three days before the Tower of Trials becomes reality."},
        {"id": "guild_race", "label": "Early Guild Race", "start_day": 7,
         "anchor": "A week after manifestation, as guilds and corporations compete for early-floor advantages."},
        {"id": "first_boss_race", "label": "First Major Boss Race", "start_day": 19,
         "anchor": "One day before the first major multi-group race for a floor boss and its rewards."},
    ],
    "Overgeared": [
        {"id": "pagma_legacy", "label": "Pagma's Legacy (default)", "start_day": -3,
         "anchor": "Three days before Grid discovers Pagma's legacy in Satisfy."},
        {"id": "satisfy_launch", "label": "Satisfy Launch", "start_day": -365,
         "anchor": "The worldwide launch of Satisfy, before its player economy and famous guilds are established."},
        {"id": "reidan_frontier", "label": "Reidan Frontier Era", "start_day": 89,
         "anchor": "One day before Reidan's neglected frontier becomes a major opportunity for players, soldiers, and crafters."},
    ],
    "Reincarnated as a Slime": [
        {"id": "reincarnation", "label": "Rimuru's Reincarnation (default)", "start_day": -7,
         "anchor": "Seven days before Satoru Mikami is reincarnated in the Great Jura Forest."},
        {"id": "orc_disaster_eve", "label": "Orc Disaster Eve", "start_day": 59,
         "anchor": "One day before the Orc Disaster's army becomes the forest's central crisis."},
        {"id": "tempest_established", "label": "Tempest Established", "start_day": 100,
         "anchor": "Tempest has emerged as a recognized monster nation with new specialists and trade ambitions."},
        {"id": "demon_lord_crisis", "label": "Demon Lord Crisis", "start_day": 179,
         "anchor": "As Falmuth's hostility and Demon Lord politics place Tempest on the edge of a transformative crisis."},
    ],
    "Bleach": [
        {"id": "week_before_arrival", "label": "One week before Ichigo receives Soul Reaper powers (default)", "start_day": -7,
         "anchor": "One week before Rukia Kuchiki's mission reaches the Kurosaki Clinic. The player is a Shin'o Academy senior or recent graduate awaiting division placement."},
        {"id": "year_before_arrival", "label": "One year before Ichigo receives Soul Reaper powers", "start_day": -365,
         "anchor": "One year before Rukia Kuchiki reaches Karakura. Soul Society appears stable, and the player is completing the academy or awaiting a first squad assignment."},
        {"id": "turn_back_pendulum", "label": "Turn Back the Pendulum — 110 years earlier", "start_day": -40157,
         "anchor": "One week before the disappearances that will become the Turn Back the Pendulum crisis. The player is an academy senior or recent graduate in the Gotei 13 of that era; future knowledge remains hidden unless the player enables full canon foreknowledge."},
    ],
    "Jujutsu Kaisen": [
        {"id":"week_before_yuji", "label":"One week before Yuji becomes Sukuna's vessel (default)", "start_day":-7, "anchor":"One week before Yuji Itadori consumes Sukuna's finger."},
        {"id":"year_before_yuji", "label":"One year before Yuji becomes Sukuna's vessel", "start_day":-365, "anchor":"One year before Yuji Itadori consumes Sukuna's finger; Yuta Okkotsu's generation is entering the modern story."},
        {"id":"hidden_inventory", "label":"Hidden Inventory era", "start_day":-4025, "anchor":"One week before Gojo and Geto receive the Star Plasma Vessel mission."},
        {"id":"jjk_zero", "label":"Jujutsu Kaisen 0 era", "start_day":-288, "anchor":"One week before Yuta Okkotsu enrolls at Tokyo Jujutsu High."},
    ],
}


def _normalize_builtin_timeline_contracts():
    """Add secrecy and causal ordering without adding or moving any event."""
    for world, timeline in CANON_TIMELINES.items():
        if world == "Custom World":
            continue
        previous_title = ""
        for event in timeline.get("events", []):
            if not event.get("historical_only"):
                # Timeline details are metagame spoilers until their date is
                # reached.  Players can still opt into canon foreknowledge.
                event.setdefault("spoiler", True)
                if previous_title:
                    event.setdefault("requires", [previous_title])
                previous_title = str(event.get("title") or previous_title)
            event.setdefault("scope", "wide" if event.get("major", False) else "personal")


_normalize_builtin_timeline_contracts()


def starting_eras_for(world):
    return WORLD_STARTING_ERAS.get(world, [])


def starting_era_by_id(world, era_id):
    return next((e for e in starting_eras_for(world) if e.get("id") == era_id), None)


# Named-month calendars for worlds without a rigorously documented in-canon
# calendar of their own (which is most of them — these series track ages and
# rough eras, not a day-by-day date system). These are consistent, world-
# flavored invented calendars replacing the mechanical "Canon Day +7" counter
# with something that reads like a real place's dates — not a claim that
# this is documented source-material canon. Every invented calendar uses a
# uniform 30-day month / 12-month year, matching the schema the app already
# uses internally for legacy age tracking (state.calendar). Player-facing dates
# now come from the fixed civil profiles in assets/data/world_calendars.json.
# calendar_anchor_day describes when a campaign began, never a per-era date reset.
_REAL_MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]
WORLD_CALENDARS = {
    "One Piece": _REAL_MONTHS,
    "Naruto": _REAL_MONTHS,
    "Hunter x Hunter": _REAL_MONTHS,
    "Overgeared": _REAL_MONTHS,
    "Reincarnated as a Slime": _REAL_MONTHS,
    "Bleach": _REAL_MONTHS,
    "Jujutsu Kaisen": _REAL_MONTHS,
}
_CAL_DAYS_PER_MONTH = 30
_CAL_MONTHS_PER_YEAR = 12
_CAL_DAYS_PER_YEAR = _CAL_DAYS_PER_MONTH * _CAL_MONTHS_PER_YEAR


def canon_day_to_calendar_parts(world, canon_day, anchor_day=None):
    from world_calendar import parts_for
    p = parts_for(world, canon_day, anchor_day=anchor_day)
    return (p['year'], p['month'], p['day']) if p else (0, 1, 1)


def format_calendar_date(world, canon_day, calendar_epoch=None, anchor_day=None):
    from world_calendar import format_date
    return format_date(world, canon_day, calendar_epoch, anchor_day)



# A spoiler-free, hand-written "what you're getting into" primer for each
# world — deliberately static rather than AI-generated, so it costs nothing
# per campaign and can never accidentally leak a later-arc twist the way a
# fresh AI generation might. Everything here describes only the setting's
# starting status quo and what's public knowledge from its earliest chapters.
WORLD_PRIMERS = {
    "One Piece": {
        "premise": "The Pirate King's dying words revealed that an ultimate treasure, One Piece, is out there somewhere — and that revelation kicked off a new Great Pirate Era. Countless crews now sail dangerous seas chasing fortune, freedom, or legend.",
        "tone": "High-adventure shonen: big personalities, wild power scaling, found-family crews, comedy mixed with real stakes and loss.",
        "power_system": "Training, swordsmanship and marksmanship all matter, but the setting's wildcard is the Devil Fruit — a rare, cursed fruit granting a unique supernatural power at the cost of never being able to swim again. Haki, a latent inner power most people can awaken with training, adds perception and combat abilities on top.",
        "factions": ["The World Government & the Marines — the law of the seas, enforcing order (and their own interests)", "Pirates — from small-time crews to powers that rival nations", "The Revolutionary Army — a shadow movement opposing the World Government"],
        "locations": ["East Blue — the calmest, weakest sea, where most journeys begin", "The Grand Line — a violent, unpredictable ocean split into two very different halves", "Countless ports, kingdoms and islands scattered between them"],
        "starting_note": "Most campaigns begin as a nobody with a big dream, sailing a calm sea where the real monsters are still ahead.",
    },
    "Naruto": {
        "premise": "Hidden ninja villages, each led by a Kage, compete for military and political influence through trained shinobi. Old wars have left an uneasy peace between the Five Great Nations, and ancient tailed-beasts still shape the balance of power.",
        "tone": "Coming-of-age shonen: teamwork, rivalry and generational trauma alongside high-flying elemental combat.",
        "power_system": "Shinobi mold chakra — physical and spiritual energy — to perform ninjutsu, genjutsu and taijutsu. Clans often carry inherited bloodline techniques, and rank (Genin, Chunin, Jonin, Kage) reflects both skill and trust.",
        "factions": ["Konohagakure and the other Hidden Villages — Suna, Kiri, Kumo, Iwa", "The Land of Fire and the other Great Nations each village serves", "Missing-nin and rogue organizations operating outside village law"],
        "locations": ["Konohagakure, the Hidden Leaf Village", "The other four Great Hidden Villages, each with its own culture and specialty", "The smaller, neutral nations and border territories between them"],
        "starting_note": "Campaigns typically begin around an academy graduation — the cast is young, untested, and just starting to earn real trust.",
    },
    "Hunter x Hunter": {
        "premise": "Hunters are a licensed elite — explorers, bounty hunters, researchers and fighters — who've passed a brutal exam granting access to privileges ordinary people don't have. Beneath the adventure lies a much larger, stranger world of hidden powers.",
        "tone": "Adventure with a sharp, strategic edge — a deceptively cheerful surface hiding genuinely dark stakes and clever, rules-based power systems.",
        "power_system": "Nen — the ability to manipulate one's own life energy — is the setting's core hidden power, split into six categories (Enhancement, Transmutation, Conjuration, Emission, Manipulation, Specialization). It's normally unknown to the public and must be personally taught or discovered.",
        "factions": ["The Hunter Association — licenses and organizes Hunters worldwide", "Independent Hunters, bounty hunters and researchers pursuing their own goals", "Assassin families and criminal organizations operating in the shadows"],
        "locations": ["Whale Island and similar quiet starting communities", "Yorknew City — a major hub of commerce and the criminal underworld", "The wider world's remote wilds, mountains and unexplored regions Hunters chase"],
        "starting_note": "Campaigns usually begin before or during the annual Hunter Exam — Nen itself is typically still an undiscovered secret at this point.",
    },
    "Solo Max-Level Newbie": {
        "premise": "The Tower of Trials — once only a popular VR game — manifests in the real world without warning, forcing humanity to climb its floors or die. Anyone who clears a floor's trial gains real power; anyone who fails or refuses often doesn't survive.",
        "tone": "High-stakes survival/progression fantasy — cutthroat competition, constant escalation, and the tension of real death replacing a game-over screen.",
        "power_system": "Players gain stats, skills and items exactly like an RPG — leveling up, equipping gear, and learning abilities that persist and strengthen over time. Floors hide achievements and secret conditions that reward players clever or informed enough to find them.",
        "factions": ["Major guilds and corporations racing to control resources, information and territory", "Governments scrambling to manage a population suddenly forced into a life-or-death game", "Independent players and small groups just trying to survive"],
        "locations": ["Earth's cities, now home to Tower entrances", "The Tower's floors themselves, each a distinct trial and environment"],
        "starting_note": "Campaigns begin right as the Tower first appears — nobody yet has more than a few days' experience with it.",
    },
    "Overgeared": {
        "premise": "Satisfy is a hyper-realistic virtual-reality MMO large enough to support nearly any fantasy life: adventurer, knight, magician, healer, commander, summoner, explorer, merchant, ruler, artisan, or an unprecedented path uncovered through play. Its NPCs live persistent lives and its hidden conditions can turn an overlooked choice into a world-famous class.",
        "tone": "Grounded MMO-fantasy power fantasy: mechanical depth, real relationships, tactical raids, political consequences, discovery and hard-earned growth—with crafting available to characters who actually choose it.",
        "power_system": "Levels, stats, equipment and Skills matter, but a class defines how they become a playstyle. Satisfy recognizes combat, magic, support, social, command, companion, exploration, production and hybrid paths; rare classes gain identity through distinctive features, quests, restrictions and evolutions rather than simply larger numbers.",
        "factions": ["Major player guilds competing through raids, territory, politics and server-wide accomplishments", "NPC kingdoms, churches, noble houses and communities with their own persistent agendas", "Independent adventurers, specialists, merchants, explorers, rulers and artisans establishing unique reputations"],
        "locations": ["Winston and similar starting kingdoms and towns", "Reidan and other contested or overlooked frontier territories", "The wider continent's dungeons, ruins and unclaimed wilderness"],
        "starting_note": "Campaigns typically begin with a character still finding their footing, long before anyone recognizes their name.",
    },
    "Reincarnated as a Slime": {
        "premise": "After death, an ordinary man wakes up reincarnated as a slime in another world — one where monsters can grow far beyond their humble start, and 'naming' a creature can radically change its fate.",
        "tone": "Optimistic, community-building isekai fantasy: diplomacy and found-family alongside real monster-world power scaling.",
        "power_system": "Monsters gain Skills and can evolve into stronger forms, often triggered by a major event or a name given by a sufficiently powerful being. Human-side magic draws on tangible magicules, channeled through spirits, techniques, or innate Unique/Ultimate Skills.",
        "factions": ["The scattered monster tribes and races of the Jura Forest and beyond, historically wary of each other", "Human nations, generally distrustful of monsters", "The world's Demon Lords — a handful of individually terrifying, world-shaping rulers"],
        "locations": ["The Great Jura Forest — a vast, monster-heavy wilderness", "Dwargon and other established dwarven and human kingdoms", "The wider continent's nations, both human- and monster-led"],
        "starting_note": "Campaigns begin at the very start of a new life in this world — before any settlement, alliance or reputation exists.",
    },
    "Bleach": {
        "premise": "Beneath the ordinary world lies Soul Society — the afterlife realm the dead pass into, governed by Shinigami (Soul Reapers) who guide lost souls and purify the corrupted spirits called Hollows. When a rare human who can see spirits crosses paths with a Shinigami on duty, the boundary between the two worlds stops being so clean.",
        "tone": "Shonen action with real weight: found-family bonds, loyalty tested against institutional authority, and a recurring theme of mercy versus duty.",
        "power_system": "Shinigami channel Reiryoku (spiritual power) through Zanjutsu (swordsmanship), Hakuda (unarmed combat), Hoho (speed — Shunpo is its signature technique) and Kido (incantation-based spells, split into offensive Hado and restraining Bakudo). Every Shinigami's Zanpakuto is a living, unique spirit blade; learning its true name unlocks Shikai, and a deep, hard-won bond with it can unlock the far more powerful Bankai. Hollows, Quincy (who destroy spirits outright with reishi-based archery) and later Vizard and Arrancar each represent a different relationship to the same spiritual power.",
        "factions": ["The Gotei 13 — Soul Society's thirteen Shinigami divisions, each led by a Captain", "Central 46 — Soul Society's judicial authority, nominally acting for the unseen Soul King", "The Onmitsukido (Stealth Force) and Kido Corps — Soul Society's covert-ops and spellcasting bodies"],
        "locations": ["Karakura Town — an ordinary Japanese town with unusually high spiritual activity", "Seireitei — the walled inner city housing the Gotei 13 and Central 46, surrounded by the sprawling Rukongai districts", "Hueco Mundo — the Hollows' harsh home dimension, and whatever lies within its fortress, Las Noches"],
        "starting_note": "Original campaigns begin as a Shin'o Academy senior or recent graduate before squad placement. The player helps choose a division through play; Shikai and Bankai are earned later unless explicitly established in the background.",
    },
    "Jujutsu Kaisen": {
        "premise": "Most people cannot see the curses born from fear, resentment and grief. Jujutsu sorcerers stand between those curses and ordinary society, while old clans and conservative authorities decide which lives and powers are acceptable.",
        "tone": "Modern occult action: inventive rule-based fights, institutional pressure, sharp humor, sudden brutality and personal ideals tested by loss.",
        "power_system": "Cursed energy reinforces the body and fuels barriers and one innate cursed technique. A Heavenly Restriction may occupy that birth slot instead, sacrificing one capacity for extreme physical or sensory potential. Learned applications, binding vows, reverse cursed technique, maximum techniques and domains grow from those foundations.",
        "factions": ["Tokyo and Kyoto Jujutsu High", "Jujutsu Headquarters and the three great clans", "Independent curse users and intelligent cursed spirits"],
        "locations": ["Tokyo Jujutsu High", "Kyoto Jujutsu High", "Modern Japanese cities concealed behind curtains and barriers"],
        "starting_note": "Original characters begin as a student, independent curse user, great-clan member or sentient cursed spirit. Each receives one generated innate technique or Heavenly Restriction shaped by the background.",
    },
}


# Worlds where species/race is a meaningful, canon-established axis of a
# character — not every setting has one (Naruto, Hunter x Hunter, Solo
# Max-Level Newbie and Overgeared are effectively human-only), so this is
# opt-in per world rather than a universal field.
WORLD_RACES = {
    "One Piece": {
        "options": ["Human", "Fishman", "Merman", "Giant", "Mink", "Skypiean"],
        "default": "Human",
    },
    "Reincarnated as a Slime": {
        "options": ["Human", "Slime", "Goblin", "Hobgoblin", "Orc", "Ogre", "Direwolf",
                    "Lizardman", "Dwarf", "Spirit", "Dragonoid", "Kijin", "Demon", "Angel"],
        "default": "Slime",
    },
}

# Keyword hints for the instant, no-AI preview guess — the authoritative
# assignment (including inventing a fitting custom race the background
# describes but this list doesn't name) happens during the actual opening,
# where the GM can really read and interpret the free-text background.
_RACE_KEYWORDS = {
    "One Piece": [
        (("fishman", "fish-man", "fish man"), "Fishman"),
        (("merman", "mermaid"), "Merman"),
        (("giant",), "Giant"),
        (("mink",), "Mink"),
        (("skypiean", "sky island", "birka", "shandia"), "Skypiean"),
    ],
    "Reincarnated as a Slime": [
        (("slime",), "Slime"),
        (("hobgoblin",), "Hobgoblin"),
        (("goblin",), "Goblin"),
        (("direwolf", "dire wolf"), "Direwolf"),
        (("lizardman", "lizard man"), "Lizardman"),
        (("dwarf",), "Dwarf"),
        (("spirit", "elemental"), "Spirit"),
        (("dragonoid", "dragon"), "Dragonoid"),
        (("kijin", "oni"), "Kijin"),
        (("demon",), "Demon"),
        (("angel",), "Angel"),
        (("ogre",), "Ogre"),
        (("orc",), "Orc"),
        (("human",), "Human"),
    ],
}


def world_supports_races(world):
    return world in WORLD_RACES


def infer_race_from_background(world, background="", origin="", archetype=""):
    """A fast, deterministic best-guess for the instant campaign-preview
    screen — no AI call needed yet. This is never the final word: the actual
    opening reads the full background with real comprehension and can
    override it with an established race that fits better, or invent a
    fitting custom one the keyword list doesn't know about."""
    if world not in WORLD_RACES:
        return ""
    text = f"{origin} {archetype} {background}".lower()
    for keywords, race in _RACE_KEYWORDS.get(world, []):
        if any(k in text for k in keywords):
            return race
    return WORLD_RACES[world]["default"]


def world_primer_for(world, custom_world_text=""):
    if world in WORLD_PRIMERS:
        return WORLD_PRIMERS[world]
    text = str(custom_world_text or "").strip()
    return {
        "premise": text or "An original setting the player is defining through play — there's no fixed lore to summarize yet.",
        "tone": "Whatever tone fits the player's own concept; the GM follows their lead.",
        "power_system": "Rules and power systems will be established and kept consistent as the campaign unfolds.",
        "factions": [],
        "locations": [],
        "starting_note": "As an original world, its rules, factions and locations take shape through play rather than being fixed in advance.",
    }


# Optional player-controlled canon-character scenarios. Dates use each world's
# relative Canon Day clock; ancient-era starts are explicitly campaign-relative
# estimates where the source does not provide a complete day-by-day calendar.
MAJOR_CHARACTER_STARTS = {
    "One Piece": [
        {"id":"luffy_departure","name":"Monkey D. Luffy","label":"Luffy — leaving Foosha Village","start_day":0,"location":"Foosha Village","age":17,"origin":"Foosha Village","archetype":"Brawler","appearance":"A lean young pirate with black hair, a straw hat, red vest, shorts, sandals, and a small scar under one eye.","background":"The morning he intends to begin his pirate voyage.",
         "title":"Aspiring Pirate King","position":"Captain of a one-person pirate crew",
         "stat_minimums":{"Strength":42,"Agility":40,"Endurance":52,"Willpower":58,"Instinct":40,"Charisma":38},
         "equipment":{"Weapon":"Shanks' Straw Hat"},
         "special_patch":{"Devil Fruit":"Gum-Gum Fruit (rubber body)","Crew":"Luffy's unnamed starting crew","Bounty":0},
         "skills":{
             "Gum-Gum Fruit":{"rank":"Experienced","bonus":9,"description":"A rubber body resists ordinary blunt impacts and enables stretching attacks, rebounds, and unconventional movement; blades, piercing attacks, Haki, drowning, and Sea-Prism Stone remain dangerous."},
             "Gum-Gum Combat":{"rank":"Self-Taught","bonus":8,"description":"Uses named stretching punches, kicks, grapples, and elastic momentum developed through years of practice."},
             "Monstrous Determination":{"rank":"Exceptional","bonus":8,"description":"Keeps acting through fear, pain, and overwhelming opposition when a chosen friend or dream is at stake."}},
         "starting_quests":[{"name":"Begin the Journey to Pirate King","status":"Active","giver":"Personal Dream","locations":["Foosha Village"],"objectives":["Leave Foosha Village by sea","Recruit a first trusted crewmate"],"next_hint":"Secure a seaworthy departure and choose the first destination."}],
         # Ace and Sabo are real, alive relationships from Luffy's own
         # background, but neither is present at the dock this morning —
         # not seeded as npc_memories to avoid implying they're currently
         # trackable/contactable when the story hasn't put them back in
         # touch yet. Sabo is deliberately seeded as Luffy BELIEVES him
         # (dead, killed as a boy) rather than the truth the manga only
         # reveals decades later — the same spoiler discipline already
         # applied to Bleach's Aizen: seed the character's own knowledge,
         # never an omniscient future reveal.
         "seed_npcs":[
             {"name":"Shanks","attitude":"Beloved mentor figure, just departed","goal":"Sailing on toward the Grand Line himself — the reason Luffy is finally setting out today.","is_companion":False,"last_known_location":"Unknown"},
             {"name":"Sabo","attitude":"Beloved sworn brother, believed dead","goal":"As far as Luffy knows, Sabo died protecting him as a child — settled grief, not an open mystery.","is_companion":False,"last_known_location":"Unknown"},
         ]},
        {"id":"zoro_shells","name":"Roronoa Zoro","label":"Zoro — prisoner at Shells Town","start_day":3,"location":"Shells Town","age":19,"origin":"Bounty Hunter","archetype":"Swordsman","appearance":"A muscular green-haired swordsman wearing simple travel clothes and carrying three swords when armed.","background":"Imprisoned at the Marine base after protecting civilians.",
         "title":"Pirate Hunter","position":"Imprisoned bounty hunter",
         "stat_minimums":{"Strength":50,"Agility":45,"Endurance":52,"Willpower":58,"Instinct":38},
         "equipment":{"Weapon":"Wado Ichimonji and two katana (confiscated at the Marine base)"},
         "conditions":["Bound to the execution-yard post; weapons confiscated"],
         "skills":{
             "Three-Sword Style":{"rank":"Expert","bonus":10,"description":"Fights with a sword in each hand and a third in his mouth, combining unusual angles, powerful cuts, and relentless pressure."},
             "Single- and Two-Sword Style":{"rank":"Expert","bonus":9,"description":"Maintains formidable swordsmanship even when fewer than three blades are available."},
             "Iron Will":{"rank":"Exceptional","bonus":8,"description":"Endures injury, deprivation, and intimidation without abandoning his promise to become the world's greatest swordsman."}},
         "starting_quests":[{"name":"Survive Morgan's Sentence","status":"Active","giver":"Shells Town Crisis","locations":["Shells Town"],"objectives":["Escape or overturn the execution order","Recover the three swords"],"next_hint":"Watch the Marine yard and decide whether to trust the strange boy asking about you."}],
         "seed_npcs":[
             {"name":"Kuina","attitude":"Deceased childhood rival, deeply formative","goal":"Died young in an accidental fall; the vow they made — that one of them would become the world's greatest swordsman — is why Zoro carries Wado Ichimonji and why he fights at all.","is_companion":False,"last_known_location":"Deceased"},
             {"name":"Koshiro","attitude":"Respected old teacher","goal":"Runs his dojo back home; gave Zoro Kuina's sword when he set out.","is_companion":False,"last_known_location":"Unknown"},
         ]}
    ],
    "Hunter x Hunter": [
        {"id":"gon_departure","name":"Gon Freecss","label":"Gon — leaving Whale Island","start_day":0,"location":"Whale Island","age":12,"origin":"Whale Island","archetype":"Tracker","appearance":"A small athletic boy with spiky black-green hair, bright brown eyes, a green jacket and shorts, and sturdy boots.","background":"The morning he leaves Whale Island to pursue the Hunter Exam.",
         "title":"Whale Island Prodigy","stat_minimums":{"Strength":38,"Agility":44,"Cunning":34,"Willpower":48,"Charisma":34},
         "equipment":{"Weapon":"Gon's Fishing Rod"},
         "special_patch":{"Hunter License":"None","Nen Category":"Unknown"},
         "skills":{
             "Whale Island Fieldcraft":{"rank":"Prodigy","bonus":9,"description":"Tracks animals, reads forests and weather, climbs, fishes, and survives with senses sharpened by a wild island childhood."},
             "Exceptional Senses":{"rank":"Innate","bonus":8,"description":"Notices scents, sounds, movement, and emotional cues far beyond an ordinary child, though it is not omniscience or Nen."},
             "Fishing Rod Combat":{"rank":"Creative","bonus":7,"description":"Uses the rod's line, hook, reach, and leverage to retrieve objects, redirect movement, and surprise opponents."}},
         "starting_quests":[{"name":"Reach and Pass the Hunter Exam","status":"Active","giver":"Personal Promise","locations":["Whale Island","Route to the Exam","Hunter Exam Site"],"objectives":["Leave Whale Island","Find the hidden exam route","Pass the Hunter Exam"],"next_hint":"Board the departing ship and prove to its captain that the journey is serious."}],
         "seed_npcs":[
             {"name":"Mito Freecss","attitude":"Devoted guardian","goal":"Raised Gon on Whale Island; worries about him constantly but let him go.","is_companion":False,"last_known_location":"Whale Island"},
             {"name":"Ging Freecss","attitude":"Absent father, the reason for this whole journey","goal":"A legendary Hunter whose whereabouts Gon doesn't actually know — finding him is the real destination.","is_companion":False,"last_known_location":"Unknown"},
         ]},
        {"id":"kurapika_exam","name":"Kurapika","label":"Kurapika — Hunter Exam journey","start_day":1,"location":"Hunter Exam Site","age":17,"origin":"Kurta Survivor","archetype":"Strategist","appearance":"A slight blond teenager with gray-brown eyes and a blue-and-gold traditional tunic.","background":"Traveling toward the Hunter Exam while pursuing information about the Kurta eyes.",
         "title":"Last Known Kurta","stat_minimums":{"Strength":34,"Agility":38,"Cunning":46,"Willpower":52,"Charisma":36},
         "equipment":{"Weapon":"Paired Wooden Training Sticks"},
         "special_patch":{"Hunter License":"Applicant","Nen Category":"Unknown","Kurta Eyes":"Scarlet when emotionally agitated"},
         "skills":{
             "Kurta Scarlet Eyes":{"rank":"Latent","bonus":8,"description":"Intense emotion turns the eyes scarlet and heightens physical performance; Nen-specific effects are not available before Nen is learned."},
             "Analytical Combat":{"rank":"Exceptional","bonus":8,"description":"Studies rules, motives, terrain, and tells to construct precise plans and exploit contradictions."},
             "Kurta Cultural Knowledge":{"rank":"Last Survivor","bonus":7,"description":"Understands the Kurta clan's language, customs, taboos, and the significance of the stolen Scarlet Eyes."}},
         "knowledge":["The Phantom Troupe is responsible for the Kurta massacre, but individual members and their location are not yet known."],
         "starting_quests":[{"name":"Become a Hunter and Recover the Scarlet Eyes","status":"Active","giver":"Kurapika's Vow","locations":["Hunter Exam Site","Yorknew City"],"objectives":["Reach the Hunter Exam","Earn a Hunter License","Find a first reliable lead on the stolen Scarlet Eyes"],"next_hint":"Continue along the exam route while evaluating other applicants as possible allies or threats."}],
         "seed_npcs":[
             {"name":"Pairo","attitude":"Deceased childhood best friend","goal":"Killed in the Phantom Troupe's massacre of the Kurta clan — the reason Kurapika became a Hunter at all.","is_companion":False,"last_known_location":"Deceased"},
         ]}
    ],
    "Naruto": [
        {"id":"naruto_birth","name":"Naruto Uzumaki","label":"Naruto — night of his birth","start_day":-4380,"location":"Konohagakure","age":0,"origin":"Uzumaki newborn","archetype":"Unformed Potential","appearance":"A newborn boy with fine blond hair and three faint whisker-like marks on each cheek.","background":"The night of his birth, before the Nine-Tails attack reshapes the village and his life.",
         "title":"Newborn Uzumaki","position":"Newborn civilian",
         "stat_minimums":{"Willpower":20}, "equipment":{"Keepsake":"Newborn blanket"},
         "special_patch":{"Shinobi Rank":"Civilian","Clan":"Uzumaki","Jinchuriki":"Nine-Tails seal not yet completed","Known Jutsu":[],"Nature Affinity":"Unknown"},
         "conditions":["Newborn: cannot independently travel, train, fight, or speak"],
         "skills":{"Uzumaki Life Force":{"rank":"Dormant Heritage","bonus":4,"description":"Carries unusually strong vitality and chakra potential inherited from the Uzumaki line; as a newborn this is potential, not trained power."}},
         "starting_quests":[{"name":"Survive the Nine-Tails Attack","status":"Active","giver":"Immediate Crisis","locations":["Konohagakure"],"objectives":["Remain protected during the attack","Survive the sealing crisis"],"next_hint":"The adults responsible for Naruto must react as the masked intruder strikes."}],
         # Minato and Kushina are both alive for the first part of this very
         # night before the Reaper Death Seal and the Nine-Tails extraction
         # kill them — deliberately NOT seeded as ongoing npc_memories
         # entries (marking them "recurring" would be misleading when the
         # scene they're seeded into is the same one that kills them).
         # Hiruzen survives and becomes Naruto's real ongoing guardian
         # figure, so he's the one seeded here.
         "seed_npcs":[
             {"name":"Minato Namikaze","attitude":"Loving father and active Fourth Hokage","goal":"Protect Kushina, Naruto, and Konoha during the attack unfolding tonight.","is_companion":False,"last_known_location":"Konohagakure"},
             {"name":"Kushina Uzumaki","attitude":"Loving mother, alive at campaign start","goal":"Keep newborn Naruto alive while the Nine-Tails seal is attacked.","is_companion":False,"last_known_location":"Konohagakure"},
             {"name":"Hiruzen Sarutobi","attitude":"Steps in as guardian figure","goal":"The Third Hokage, present in the village tonight — becomes the closest thing Naruto has to a guardian going forward.","is_companion":False,"last_known_location":"Konohagakure"},
         ]},
        {"id":"yahiko_akatsuki","name":"Yahiko","label":"Yahiko — founding the Akatsuki","start_day":-5221,"location":"Amegakure","age":17,"origin":"Amegakure War Orphan","archetype":"Ninjutsu Student","appearance":"A lean orange-haired young shinobi with determined eyes, rain gear, and a forehead protector worn openly.","background":"On the eve of founding the original Akatsuki, Yahiko works beside Nagato and Konan to turn their shared dream of peace into an organization that can protect Amegakure without serving the great villages.",
          "expanded_background":"Orphaned by the wars that consumed Amegakure, Yahiko survived alongside Nagato and Konan before the three trained under Jiraiya for three years. Jiraiya has since returned to Konoha, leaving Yahiko to put those lessons into practice. Now Yahiko is preparing to found the original Akatsuki as a peace movement: protecting civilians, uniting ordinary people, and breaking Amegakure's cycle of exploitation without surrendering its independence.",
          "title":"Akatsuki Founder","position":"Founder and Leader of the Akatsuki",
          "equipment":{"Weapon":"Amegakure Kunai Set and Rain Cloak"},
          "special_patch":{"Shinobi Rank":"Akatsuki Leader","Home Village":"Amegakure","Known Jutsu":["Water Release Ninjutsu"]},
          "affiliations":[{"faction":"Akatsuki","rank":"Founder and Leader","status":"active","joined":"Campaign start","notes":"Co-founded the original Amegakure peace movement with Nagato and Konan."}],
          "reputation":{"Akatsuki":80,"Amegakure":20},
          "stat_minimums":{"Taijutsu":40,"Ninjutsu":48,"Genjutsu":30,"Chakra Control":42,"Willpower":45,"Intellect":38},
          "skills":{
              "Water Release Ninjutsu":{"rank":"Proficient","bonus":7,"description":"Shapes water-nature chakra into practical offensive and defensive techniques suited to Amegakure's rain-soaked terrain.","limitation":"Strong techniques still require chakra, control, and available water or additional chakra to create it.","growth_path":"Refine nature transformation, learn larger formations, and coordinate techniques with Nagato and Konan."},
              "Amegakure Fieldcraft":{"rank":"Veteran Survivor","bonus":6,"description":"Navigates the Hidden Rain's towers, pipes, flooded alleys, patrol routes, and civilian networks while recognizing the dangers created by prolonged war.","limitation":"Local knowledge does not guarantee safe passage through territory controlled by Hanzō's forces.","growth_path":"Build a trusted intelligence network and learn how rival cells operate."},
              "Shinobi Fundamentals":{"rank":"Trained","bonus":5,"description":"Uses chakra control, hand seals, taijutsu, shinobi tools, stealth, and team tactics at the level expected after Jiraiya's instruction.","limitation":"Fundamentals support advanced techniques but do not replace specialized mastery.","growth_path":"Apply the fundamentals under pressure and develop techniques suited to Yahiko's leadership and Water Release."}
          },
          "starting_quests":[{"name":"Found the Original Akatsuki","status":"Active","giver":"Yahiko's Dream","locations":["Amegakure"],"objectives":["Establish the movement's founding principles","Protect Amegakure civilians without serving a great village","Recruit the first trustworthy supporters"],"next_hint":"Meet with Nagato and Konan to decide the organization's first public act."}],
         # The original Akatsuki was a three-person operation — Yahiko,
         # Nagato, and Konan — trained together for three years by Jiraiya
         # after being orphaned in the Second Shinobi World War. Kakuzu and
         # (black) Zetsu are NOT founding members: Kakuzu joins only after
         # Yahiko's death once Nagato/Obito reshape Akatsuki into the
         # criminal organization, and Zetsu was never a rank-and-file
         # member at all — he's Madara/Obito's own planted spy watching
         # Nagato from outside the group. Seeding the wrong roster here
         # would be exactly the kind of ungrounded, non-canon detail this
         # feature exists to prevent.
         "seed_npcs":[
             {"name":"Nagato","attitude":"Devoted ally","goal":"Build a world without the suffering Amegakure has known, alongside Yahiko and Konan.","is_companion":True},
             {"name":"Konan","attitude":"Devoted ally","goal":"Support Yahiko's vision of peace for Amegakure.","is_companion":True},
             {"name":"Jiraiya","attitude":"Respected mentor, distant","goal":"Returned to Konoha after three years training the three of them; still watches his former students' progress from afar.","is_companion":False,"last_known_location":"Konohagakure"},
         ],
         "seed_faction_rosters":{"Akatsuki":["Yahiko","Nagato","Konan"]}},
        {"id":"pain_birth","name":"Pain","label":"Pain — birth of Pain","start_day":-4855,"location":"Amegakure","age":18,"origin":"Amegakure War Orphan","archetype":"Rinnegan Wielder",
         "appearance":"Yahiko's orange-haired body newly bears black chakra-receiver piercings and the Rinnegan as the first public face of Pain; Nagato's scarred red-haired true body remains concealed nearby.",
         "background":"The morning after Yahiko's death. Nagato has survived Hanzō's ambush, summoned the Demonic Statue, lost the use of his legs, and adopted the identity of Pain, but the future form and doctrine of Akatsuki are still his to decide.",
         "expanded_background":"Yahiko died to save Konan when Hanzō and Danzō trapped the original Akatsuki. Nagato answered with the Rinnegan and the Demonic Statue of the Outer Path, destroying their attackers at a terrible physical cost: black receivers remain embedded in his back and his legs are crippled. Konan has escaped with him and Yahiko's body. Nagato has just taken the name Pain and begun using Yahiko as the Deva Path, the first public body of a remote Rinnegan network. The remaining five Paths have not yet been assembled, Hanzō still rules Amegakure, and the masked man calling himself Madara is waiting to exploit Nagato's grief. The player has full control over whether Pain follows canon, preserves more of Yahiko's ideals, or creates a different Akatsuki entirely.",
         "motivation":"End the cycle of war that destroyed Yahiko, whether through shared pain, Yahiko's original ideals, or a new path chosen by the player.",
         "starting_complication":"Nagato is newly crippled and grieving, only the Deva Path is operational, Hanzō remains in power, and the masked man's offer carries concealed motives.",
         "title":"Pain — Akatsuki Leader","position":"Leader of the transformed Akatsuki",
         "equipment":{"Weapon":"Black Chakra Receivers and concealed life-support frame"},
         "special_patch":{"Shinobi Rank":"Akatsuki Leader","Home Village":"Amegakure","Clan":"Uzumaki","True Identity":"Nagato","Public Body":"Yahiko — nascent Deva Path","Rinnegan":"Active in both eyes","Six Paths of Pain":"Deva Path operational; five Paths not yet assembled","Known Jutsu":["Rinnegan Six Paths Techniques","Summoning: Demonic Statue of the Outer Path","Black Chakra Receivers","Remote Body Control","Five Basic Nature Transformations"]},
         "conditions":["Nagato's legs are crippled and his true body requires support for travel","Black receivers from the Demonic Statue impose constant pain and chakra strain","Only the Deva Path is currently operational; the remaining Paths must be created or replaced through play","Fresh grief after Yahiko's death can shape judgment without removing player control"],
         "affiliations":[{"faction":"Akatsuki","rank":"Leader","status":"active","joined":"Original founding","notes":"Nagato now leads the surviving organization through the identity of Pain, beside Konan."}],
         "reputation":{"Akatsuki":90,"Amegakure":-20},
         "stat_minimums":{"Taijutsu":75,"Ninjutsu":170,"Genjutsu":75,"Chakra Control":145,"Willpower":120,"Intellect":105},
         "skills":{
             "Rinnegan — Six Paths Techniques":{"rank":"Extraordinary","bonus":16,"description":"Uses the Rinnegan's gravitational, summoning, absorption, soul, restoration, mechanized and Outer Path capabilities directly or through prepared bodies.","limitation":"Only the Deva body is ready at campaign start; large techniques have severe chakra, cooldown and bodily costs, and unfamiliar applications still require experimentation.","growth_path":"Stabilize Nagato's body, refine remote control, assemble or redesign the other Paths, and master each Rinnegan discipline."},
             "Deva Path — Yahiko":{"rank":"Nascent Path","bonus":13,"description":"Controls Yahiko's preserved body through black receivers, sharing Rinnegan vision and channeling attractive and repulsive force while presenting Pain to the world.","limitation":"The body has only just been prepared, shared vision is limited to one Path, and powerful gravity techniques require recovery intervals.","growth_path":"Improve receiver placement, movement, range and gravity control while deciding what Yahiko's body will represent."},
             "Demonic Statue of the Outer Path":{"rank":"Catastrophic Summoning","bonus":15,"description":"Summons the Gedō Statue and channels its chakra-draining power, as demonstrated during the escape from Hanzō's ambush.","limitation":"Its rods have already crippled Nagato; continued use can consume life force and worsen his condition.","growth_path":"Learn the statue's true function and establish strict conditions for using it without sacrificing Nagato's life."},
             "Black Receiver Network":{"rank":"Developing Mastery","bonus":11,"description":"Creates and implants chakra receivers to transmit Nagato's chakra, commands and Rinnegan perception into prepared targets at range.","limitation":"Range, signal stability, chakra cost and the number of active bodies remain practical constraints.","growth_path":"Build secure relay positions, increase range, and develop the complete shared-vision formation."},
             "Jiraiya's Ninjutsu Training":{"rank":"Mastered Foundation","bonus":9,"description":"Applies the survival, chakra control, teamwork and elemental ninjutsu taught to Nagato, Yahiko and Konan during their childhood in Amegakure."}},
         "knowledge":["Hanzō collaborated with Danzō's Root forces to destroy the original Akatsuki.","The masked man calling himself Madara previously offered to guide Nagato and is likely to return now that Yahiko is dead.","The other five bodies of the future Six Paths of Pain have not yet been selected or prepared."],
         "starting_quests":[{"name":"Decide What Pain Will Become","status":"Active","giver":"Yahiko's Death","locations":["Amegakure"],"objectives":["Stabilize Nagato and secure a hidden base","Decide whether Yahiko will remain the Deva Path or be honored another way","Choose the transformed Akatsuki's doctrine and immediate response to Hanzō","Accept, reject, deceive, or investigate the masked man's offer","Create, redesign, or abandon the remaining Paths of Pain"],"next_hint":"Speak with Konan beside Yahiko's body and decide the first order issued in the name of Pain."}],
         "seed_npcs":[
             {"name":"Konan","attitude":"Grieving, fiercely loyal partner","goal":"Protect Nagato, preserve what remains of Yahiko's dream, and help decide what Akatsuki becomes.","is_companion":True,"last_known_location":"Amegakure"},
             {"name":"Yahiko","attitude":"Deceased best friend and moral center","goal":"His dream of peace survives only through the meaning Nagato and Konan give his sacrifice.","is_companion":False,"last_known_location":"Deceased"},
             {"name":"Masked Man ('Madara')","attitude":"Manipulative would-be patron","goal":"Exploit Nagato's Rinnegan, grief, and Akatsuki for the Eye of the Moon Plan.","is_companion":False,"last_known_location":"Unknown","can_contact":False},
             {"name":"Hanzō","attitude":"Mortal enemy and ruler of Amegakure","goal":"Destroy the surviving Akatsuki before it can threaten his rule.","is_companion":False,"last_known_location":"Amegakure","can_contact":False},
             {"name":"Jiraiya","attitude":"Former mentor, distant and unaware of the full tragedy","goal":"Protect the shinobi world while believing his former students may still realize their dream of peace.","is_companion":False,"last_known_location":"Konohagakure","can_contact":False}
         ],
         "seed_faction_rosters":{"Akatsuki":["Pain","Konan"]}},
        {"id":"naruto_graduation","name":"Naruto Uzumaki","label":"Naruto — Academy graduation night","start_day":0,"location":"Konohagakure","age":12,"origin":"Academy Student","archetype":"Ninjutsu Student","appearance":"A short blond academy student with blue eyes, whisker-like cheek marks, goggles, and an orange-and-blue outfit.","background":"The day of the Academy graduation and the Scroll of Seals incident.",
         "title":"Academy Student","position":"Academy Student awaiting the graduation test",
         "affiliations":[{"faction":"Konohagakure","rank":"Academy Student","status":"active","joined":"Before campaign start","notes":"Enrolled in Konoha's Academy and awaiting the graduation test."}],
         "stat_minimums":{"Taijutsu":28,"Ninjutsu":24,"Genjutsu":12,"Chakra Control":14,"Willpower":48,"Intellect":22},
         "equipment":{"Weapon":"Goggles and Academy practice pouch"},
         "special_patch":{"Shinobi Rank":"Academy Student","Clan":"Uzumaki","Jinchuriki":"Nine-Tails (identity concealed)","Known Jutsu":["Transformation Technique","Substitution Technique"],"Chakra Reserve":"Exceptional"},
         "skills":{
             "Uzumaki Chakra Reserves":{"rank":"Exceptional Potential","bonus":9,"description":"Possesses enormous stamina and chakra reserves, but poor control makes ordinary techniques inefficient and unreliable."},
             "Transformation Technique":{"rank":"Creative","bonus":6,"description":"Uses the basic transformation with unusual creativity and enthusiasm."}},
         "knowledge":["Mizuki has not yet revealed his plan, and Naruto has not yet learned the Shadow Clone Technique from the Forbidden Scroll."],
         "starting_quests":[{"name":"Graduate from the Academy","status":"Active","giver":"Naruto's Goal","locations":["Konohagakure"],"objectives":["Complete or overcome the graduation test","Respond to Mizuki's manipulation","Earn recognition as a genin"],"next_hint":"Attend the graduation test and react to the instructors' decision."}],
         # Sasuke and Sakura are known classmates at this point but NOT yet
         # teammates — Team 7 doesn't form until a few days after this, so
         # they're deliberately left unseeded rather than implied to
         # already be companions.
         "seed_npcs":[
             {"name":"Iruka Umino","attitude":"Devoted teacher","goal":"His Academy instructor, central to this exact day's events — protects Naruto during the Scroll of Seals incident and gives him his own forehead protector.","is_companion":False,"last_known_location":"Konohagakure"},
             {"name":"Mizuki","attitude":"Friendly instructor masking selfish intent","goal":"Manipulate Naruto into stealing the Forbidden Scroll later tonight.","is_companion":False,"last_known_location":"Konohagakure"},
         ]}
    ],
    "Solo Max-Level Newbie": [
        {"id":"jinhyeok_tower","name":"Kang Jinhyeok","label":"Jinhyeok — Tower manifestation","start_day":0,"location":"Earth — Tower Entrance","age":27,"origin":"Veteran Gamer","archetype":"All-Rounder","appearance":"A sharp-eyed young Korean man with dark hair, practical modern clothing, and a calm calculating expression.","background":"The day the Tower of Trials becomes reality.",
         "title":"Only Player to Clear the Game","position":"Independent player with complete pre-manifestation game knowledge",
         "stat_minimums":{"Strength":30,"Dexterity":34,"Constitution":28,"Intelligence":52,"Wisdom":48,"Luck":36},
         "equipment":{"Weapon":"Practical Survival Knife and Smartphone Notes"},
         "special_patch":{"Pre-Tower Game Rank":"Sole Clearer","Hidden Conditions Found":0,"Copied Abilities":[],"Achievements":[],"Floor":0},
         "skills":{
             "Tower Encyclopedia":{"rank":"Complete Game Knowledge","bonus":12,"description":"Remembers floor layouts, bosses, NPC routes, items, hidden conditions, and exploits from the completed game, while tracking any differences in reality."},
             "Adaptive Combat":{"rank":"Elite Gamer","bonus":9,"description":"Reads patterns quickly, switches tactics and equipment, and turns System feedback into efficient combat decisions."},
             "Hidden Route Planning":{"rank":"Master","bonus":11,"description":"Sequences prerequisites and timing windows to pursue alternate clears and rare rewards before rivals understand they exist."}},
         "knowledge":["The Tower's former game routes, including many hidden conditions and boss patterns, are remembered but must be revalidated in lethal reality."],
         "starting_quests":[{"name":"Exploit the First Scenario","status":"Active","giver":"Personal Foreknowledge","locations":["Earth — Tower Entrance","Floor 1"],"objectives":["Enter the Tower before the crowd consolidates","Secure a high-value hidden condition","Survive the first-floor scenario"],"next_hint":"Compare the manifested entrance and System notice against the remembered opening route."}]}
    ],
    "Overgeared": [
        {"id":"grid_pagma","name":"Grid","label":"Grid — Pagma's legacy turning point","start_day":0,"location":"Winston","age":26,"origin":"New Player","archetype":"Blacksmith","appearance":"A dark-haired young man with a stubborn expression, novice adventuring gear, and worn blacksmith tools.","background":"Immediately after choosing to use Pagma's Rare Book and becoming Pagma's Descendant.",
         "title":"Pagma's Descendant","position":"Legendary-class production player",
         "stat_minimums":{"Strength":32,"Dexterity":24,"Constitution":30,"Intelligence":28,"Wisdom":20,"Luck":18},
         "equipment":{"Weapon":"Beginner Smithing Hammer","Quest Item":"Pagma's Rare Book (consumed)"},
         "special_patch":{"Class":"Pagma's Descendant","Crafting Mastery":35,"Secondary Class":"None","Guild":"None"},
         "class_profile":{"name":"Pagma's Descendant","kind":"Successor Class","rank":"Legendary","description":"A legendary successor class carrying Pagma's blacksmithing legacy and the potential to unite production with swordsmanship.","effect":"Unlocks legendary production growth, class quests, and Pagma-linked techniques as their real prerequisites are met.","limitation":"Grid begins inexperienced, financially desperate, and far below Pagma's mastery; class potential is not instant mastery.","growth_path":"Forge rated equipment, complete class quests, discover Pagma's techniques, and build relationships with craftsmen and NPCs.","signature_skill":"Legendary Blacksmithing","stat_bonuses":{},"learning_multiplier":1.15},
         "skills":{
             "Legendary Blacksmithing":{"rank":"Newly Awakened","bonus":9,"description":"Uses Pagma's production framework to create rated equipment with exceptional long-term potential; present output still depends on Grid's materials, designs, and execution."},
             "Blacksmith's Appraisal":{"rank":"Beginner","bonus":5,"description":"Reads an item's materials, condition, rating, and production clues through the Satisfy interface."}},
         "starting_quests":[{"name":"Earl Ashur's Anger","status":"Active","giver":"Class Turning Point","locations":["Winston"],"objectives":["Survive the consequences of keeping Pagma's legacy","Forge a first item as Pagma's Descendant","Find a viable route out of immediate debt"],"next_hint":"Inspect the newly unlocked class information and prepare for Earl Ashur's response."}]}
    ],
    "Reincarnated as a Slime": [
        {"id":"rimuru_awakens","name":"Rimuru Tempest","label":"Rimuru — awakening in the cave","start_day":0,"location":"Great Jura Forest — Sealed Cave","age":0,"origin":"Reincarnated Otherworlder","archetype":"Skill Analyst","appearance":"A small translucent blue slime with a soft internal glow and an expressive, fluid silhouette.","background":"The first moments after reincarnating inside the Sealed Cave.",
         "title":"Newly Reincarnated Slime","position":"Unaligned monster in the Sealed Cave","race":"Slime",
         "stat_minimums":{"Magicule Control":38,"Skill Mastery":48,"Instinct":28,"Insight":44,"Willpower":38,"Presence":18},
         "equipment":{"Natural Trait":"Slime Body"},
         "special_patch":{"Species":"Slime","Evolution Stage":"Newborn Slime","Magicule Capacity":55,"Named Skills":["Great Sage","Predator"]},
         "skills":{
             "Great Sage":{"rank":"Unique Skill","bonus":11,"description":"Analyzes observed phenomena, manages thought acceleration, and provides clear internal answers when sufficient information exists; it cannot invent missing facts."},
             "Predator":{"rank":"Unique Skill","bonus":11,"description":"Stores absorbed targets in an internal space, analyzes compatible matter or abilities, and may reproduce valid results after successful analysis."},
             "Slime Physiology":{"rank":"Intrinsic","bonus":8,"description":"A shapeless body does not need ordinary breathing, food, or sleep and can alter form within its current mass and control."}},
         "starting_quests":[{"name":"Understand the Sealed Cave","status":"Active","giver":"New Existence","locations":["Great Jura Forest — Sealed Cave"],"objectives":["Learn how the slime body moves and senses","Test Great Sage and Predator safely","Discover another presence within the cave"],"next_hint":"Move through the cave while asking Great Sage what can be confirmed about the new body."}]}
    ],
    "Bleach": [
        {"id":"ichigo_series_start","name":"Ichigo Kurosaki","label":"Ichigo — the night he receives Soul Reaper powers","start_day":0,"location":"Kurosaki Clinic","age":15,"origin":"Substitute Soul Reaper","archetype":"Zanjutsu Specialist","appearance":"A tall, lean first-year high schooler with spiky orange hair and a fierce scowl, his living body now separated from a black-robed Soul Reaper form carrying an oversized blade.","background":"The exact night Ichigo receives Rukia Kuchiki's Soul Reaper power. Fishbone D has broken into the Kurosaki home and injured Rukia. Ichigo has just accepted her blade through his chest to protect his family; the transfer takes far more power than either expected. He now stands in an unfamiliar Soul Reaper body with an oversized unnamed Zanpakuto while the Hollow is still attacking.",
         "expanded_background":"Ichigo has seen spirits since childhood and entered this night as a protective but otherwise living Karakura High student. Rukia Kuchiki arrived hunting Fishbone D, was wounded shielding him, and transferred her power as the only immediate way for Ichigo to protect his family. The transfer has just happened. Ichigo has enormous raw spiritual capacity but no formal Shinigami education, no Kidō, no release and almost no control. The player takes control before the first fight is decided.",
         "title":"New Substitute Soul Reaper","position":"Unregistered Substitute Soul Reaper",
         "active_canon_event":"Rukia Kuchiki arrives in Karakura Town",
         "active_event_context":"The power transfer has already happened inside the shattered Kurosaki home. Fishbone D is attacking, Rukia is wounded, and Ichigo's family is down nearby. Continue as an immediate combat scene in the normal Chronicle.",
         "active_event_prompt":"Fishbone D lunges through the ruined wall. What does Ichigo do with the oversized blade?",
         "stat_minimums":{"Zanjutsu":36,"Hakuda":42,"Hoho":24,"Kido":5,"Reiatsu Control":22,"Willpower":58},
         "stat_values":{"Zanjutsu":36,"Hakuda":42,"Hoho":24,"Kido":5,"Reiatsu Control":22,"Willpower":58},
         "equipment":{"Weapon":"Oversized unnamed Zanpakuto formed from borrowed Soul Reaper power","Clothing":"Newly manifested black shihakusho"},
         "special_patch":{"Spiritual Nature":"Living Human / Substitute Soul Reaper","Shinigami Rank":"Unregistered Substitute","Zanpakuto":"Oversized unnamed borrowed-power blade","Zanpakuto Profile":{"stage":"Borrowed power — sealed","name":"Unknown","development_evidence":["Accepted Rukia's power to protect the Kurosaki family"]},"Shikai":"Unachieved","Bankai":"Unachieved","Squad":"None","Kido Curriculum":{"Hadō":"Not yet trained","Bakudō":"Not yet trained","Unshown Numbers":"May be researched after Kidō fundamentals are learned"}},
         "skills":{
             "Spiritual Sight":{"rank":"Innate","bonus":8,"description":"Sees, hears and physically interacts with spirits that ordinary living humans cannot perceive.","combat_usable":False,"effect_type":"utility"},
             "Borrowed Soul Reaper Power":{"rank":"Newly Transferred","bonus":7,"description":"Manifests a Soul Reaper body, black shihakusho and oversized blade using power transferred by Rukia; output is high but control is almost nonexistent.","limitation":"Ichigo has no formal training, release or reliable control and does not yet understand the body's techniques.","growth_path":"Survive the opening attack, learn Soul Reaper fundamentals and develop his own relationship with the power.","combat_usable":True,"effect_type":"utility"},
             "Instinctive Zanpakuto Strike":{"rank":"Untrained Power","bonus":6,"description":"Commits raw strength and spiritual pressure through the oversized blade in a direct cut.","limitation":"Poor footwork and control leave openings and waste considerable Reiryoku.","growth_path":"Learn Zanjutsu structure, control spiritual output and understand the blade.","combat_usable":True,"effect_type":"damage"}
         },
         "conditions":["Rukia Kuchiki is badly wounded nearby","Fishbone D is actively attacking the Kurosaki family","Ichigo has never fought as a Soul Reaper before"],
         "opening_combat":{"active":True,"round":1,"non_lethal":False,"location":"Kurosaki Clinic","enemy":{"name":"Fishbone D","is_group":False,"group_size":None,"hp":95,"hp_max":95,"difficulty_min":28,"difficulty_max":42,"attack_min":30,"attack_max":44,"power":34,"alive":True},"player_defense_ability":"Hoho","log":[],"narrated_through":0,"outcome":None,"cooldowns":{},"ally_support":0,"enemy_debuffs":[],"spare_enemy":False},
         "starting_quests":[{"name":"Protect the Kurosaki Family","status":"Active","category":"main","giver":"Immediate Crisis","locations":["Kurosaki Clinic"],"explanation":"Fishbone D attacked the clinic and Rukia's power transfer has given Ichigo one immediate chance to stop it.","current_knowledge":["The Hollow is after Ichigo's unusually visible soul","Rukia is too injured to finish the fight","Ichigo's family is still in immediate danger"],"objectives":["Defeat or drive off Fishbone D","Keep the Kurosaki family alive","Learn what happened to Rukia's power"],"clear_conditions":["Fishbone D can no longer threaten the clinic","The family survives the attack"],"next_hint":"Take control of the oversized blade and answer Fishbone D's next attack."}],
         # Isshin is seeded as he actually presents at this point in canon —
         # a goofy, purely human clinic doctor. His real past as a former
         # Squad 10 Captain is a Thousand-Year Blood War-era reveal, more
         # than a decade of story away from this start; seeding the truth
         # here would spoil it the same way seeding Aizen's true nature
         # into this world's factions would.
         "seed_npcs":[
             {"name":"Rukia Kuchiki","attitude":"Wounded ally shocked by the scale of the transfer","goal":"Keep Ichigo alive long enough to defeat Fishbone D and contain the consequences of her forbidden act.","is_companion":True,"last_known_location":"Kurosaki Clinic"},
             {"name":"Isshin Kurosaki","attitude":"Loving, embarrassing father","goal":"Runs the family clinic; presents as an ordinary, if eccentric, human doctor.","is_companion":False,"last_known_location":"Kurosaki Clinic"},
             {"name":"Yuzu Kurosaki","attitude":"Devoted younger sister","goal":"Keeps the household running — cooking, cleaning — and worries over everyone.","is_companion":False,"last_known_location":"Kurosaki Clinic"},
             {"name":"Karin Kurosaki","attitude":"Sharp-tongued younger sister","goal":"Plays soccer and, unlike Yuzu, has her own latent ability to see spirits.","is_companion":False,"last_known_location":"Kurosaki Clinic"},
         ]}
    ],
    "Jujutsu Kaisen": [
        {"id":"yuji_finger","name":"Yuji Itadori","label":"Yuji — the night he consumes Sukuna's finger","start_day":0,"location":"Sugisawa High School","age":15,"origin":"Tokyo Jujutsu High — First Year","archetype":"Jujutsu Sorcerer","appearance":"An athletic teenage boy with short pink hair, a dark school uniform and a red hood.","background":"The cursed finger has drawn curses to Sugisawa High. Yuji is seconds from the choice that makes him Sukuna's vessel.","title":"Sukuna's Vessel","position":"Newly recruited Tokyo first-year","stat_minimums":{"Physical Ability":95,"Speed & Reflexes":82,"Cursed Energy Reserves":70,"Cursed Energy Output":62,"Cursed Energy Control":25,"Jujutsu Insight":22,"Soul Stability":105},"equipment":{"Weapon":"None","Cursed Object":"Sukuna's finger"},"special_patch":{"Grade":"Unassessed","Birth Slot":"Vessel Physiology","Innate Technique":"None awakened","Heavenly Restriction":"None","Vessel":"Ryomen Sukuna"},"skills":{"Superhuman Physique":{"rank":"Innate","bonus":12,"description":"Exceptional natural strength, speed and durability even before cursed-energy training."},"Divergent Fist":{"rank":"Unlearned potential","bonus":0,"description":"A future application caused by cursed energy lagging behind a physical strike."}},"starting_quests":[{"name":"Save the Occult Club","status":"Active","giver":"Immediate Crisis","objectives":["Reach Sasaki and Iguchi","Survive the curses drawn to the finger","Decide whether to consume Sukuna's finger"],"next_hint":"Megumi is fighting above while the seal fails; act before the curse reaches Yuji's friends."}]},
        {"id":"gojo_inventory","name":"Satoru Gojo","label":"Gojo — Hidden Inventory mission","start_day":-4018,"location":"Tokyo Jujutsu High","age":17,"origin":"Great Clan Member","archetype":"Jujutsu Sorcerer","appearance":"A tall white-haired student wearing a dark uniform and small round sunglasses.","background":"Gojo and Geto have just received the Star Plasma Vessel protection assignment.","title":"The Strongest Student","position":"Tokyo second-year and Gojo clan heir","stat_minimums":{"Physical Ability":150,"Speed & Reflexes":210,"Cursed Energy Reserves":190,"Cursed Energy Output":210,"Cursed Energy Control":320,"Jujutsu Insight":190,"Soul Stability":160},"equipment":{"Eyewear":"Six Eyes sunglasses","Weapon":"None"},"special_patch":{"Grade":"Special Grade","Birth Slot":"Innate Cursed Technique","Innate Technique":"Limitless","Heavenly Restriction":"None","Dōjutsu":"Six Eyes"},"skills":{"Infinity":{"rank":"Mastered Application","bonus":18,"description":"Applies Limitless to divide approaching space so attacks slow before contact."},"Cursed Technique Lapse: Blue":{"rank":"Advanced Application","bonus":17,"description":"Creates an attractive spatial effect through amplified negative cursed energy."}},"starting_quests":[{"name":"Protect the Star Plasma Vessel","status":"Active","giver":"Master Tengen's Assignment","objectives":["Meet Riko Amanai","Keep her alive through the bounty period","Escort her to Tengen"],"next_hint":"Coordinate with Geto and collect the mission details before the bounty network moves."}]},
        {"id":"yuta_enrolls","name":"Yuta Okkotsu","label":"Yuta — enrolling at Tokyo Jujutsu High","start_day":-281,"location":"Tokyo Jujutsu High","age":16,"origin":"Tokyo Jujutsu High — First Year","archetype":"Jujutsu Sorcerer","appearance":"A slim, tired-looking teenage boy with dark hair, a white uniform and a sword case.","background":"Yuta enters Jujutsu High while Rika's overwhelming manifestation threatens anyone who harms him.","title":"Special Grade Cursed Human","position":"New Tokyo first-year","stat_minimums":{"Physical Ability":55,"Speed & Reflexes":48,"Cursed Energy Reserves":310,"Cursed Energy Output":120,"Cursed Energy Control":28,"Jujutsu Insight":38,"Soul Stability":80},"equipment":{"Weapon":"Training katana"},"special_patch":{"Grade":"Special Grade","Birth Slot":"Innate Cursed Technique","Innate Technique":"Copy — not yet understood","Heavenly Restriction":"None","Bound Spirit":"Rika"},"skills":{"Rika's Protection":{"rank":"Uncontrolled","bonus":18,"description":"Rika manifests automatically and violently when Yuta is threatened; Yuta cannot yet direct her safely."}},"starting_quests":[{"name":"Break Rika's Curse Without Hurting Anyone","status":"Active","giver":"Yuta's Decision to Live","objectives":["Meet the second-year students","Learn to channel cursed energy through the katana","Understand the bond with Rika"],"next_hint":"Gojo is introducing Yuta to Maki, Toge and Panda; decide how honestly to explain Rika."}]},
        {"id":"megumi_finger","name":"Megumi Fushiguro","label":"Megumi — sent to retrieve Sukuna's finger","start_day":0,"location":"Sugisawa High School","age":15,"origin":"Tokyo Jujutsu High — First Year","archetype":"Jujutsu Sorcerer","appearance":"A lean black-haired teenager in a dark high-collared uniform.","background":"Megumi arrives in Sendai searching for a missing special-grade cursed object.","title":"Ten Shadows Sorcerer","position":"Tokyo first-year","stat_minimums":{"Physical Ability":60,"Speed & Reflexes":67,"Cursed Energy Reserves":82,"Cursed Energy Output":70,"Cursed Energy Control":76,"Jujutsu Insight":88,"Soul Stability":72},"equipment":{"Weapon":"None","Supplies":"Protective talismans and mission uniform"},"special_patch":{"Grade":"Grade 2","Birth Slot":"Innate Cursed Technique","Innate Technique":"Ten Shadows Technique","Heavenly Restriction":"None"},"skills":{"Divine Dogs":{"rank":"Shikigami Application","bonus":10,"description":"Summons paired tracking and combat shikigami through shadow hand signs."},"Nue":{"rank":"Shikigami Application","bonus":9,"description":"Summons a winged shikigami capable of flight and electrical attacks."}},"starting_quests":[{"name":"Recover Sukuna's Finger","status":"Active","giver":"Satoru Gojo","objectives":["Locate the finger's current holder","Protect nearby civilians","Retrieve or contain the special-grade object"],"next_hint":"The cursed presence leads toward Sugisawa High and an unusually athletic student has information."}]},
        {"id":"maki_second_year","name":"Maki Zenin","label":"Maki — Tokyo second-year","start_day":-281,"location":"Tokyo Jujutsu High","age":16,"origin":"Great Clan Member","archetype":"Jujutsu Sorcerer","appearance":"An athletic teenage girl with dark green hair, glasses and a dark school uniform carrying a polearm.","background":"Maki begins another year determined to earn rank and disprove the Zenin clan that rejected her.","title":"Cursed Tool Specialist","position":"Tokyo second-year","stat_minimums":{"Physical Ability":105,"Speed & Reflexes":92,"Cursed Energy Reserves":3,"Cursed Energy Output":2,"Cursed Energy Control":8,"Jujutsu Insight":72,"Soul Stability":90},"equipment":{"Weapon":"Cursed naginata","Eyewear":"Glasses that reveal curses"},"special_patch":{"Grade":"Grade 4","Birth Slot":"Heavenly Restriction","Innate Technique":"None","Heavenly Restriction":"Low cursed energy exchanged for extraordinary physical potential"},"skills":{"Cursed Tool Mastery":{"rank":"Expert","bonus":13,"description":"Uses diverse cursed weapons with exceptional reach, timing and tactical adaptation."}},"starting_quests":[{"name":"Force Jujutsu Headquarters to Recognize Maki","status":"Active","giver":"Maki's Own Ambition","objectives":["Complete missions above the expectations of Grade 4","Refine cursed-tool mastery","Build a record the Zenin clan cannot erase"],"next_hint":"A new special-grade student is arriving; decide whether training him can also sharpen Maki's own case for promotion."}]},
    ],
}


_CANON_START_NORMALIZATION = {
    "luffy_departure": {
        "affiliations":[{"faction":"Pirates","rank":"Independent Captain","status":"active","joined":"Campaign start","notes":"Luffy has declared himself a pirate captain but has not recruited a crew."}],
        "reputation":{"Pirates":8,"Marines":-3},
        "active_canon_event":"Luffy leaves Foosha Village",
        "active_event_context":"Luffy's supplies and tiny boat are ready at Foosha Village. The sea, weather and consequences are live; the voyage has not yet been decided.",
        "active_event_prompt":"The shore is behind him and the East Blue is open ahead. What course does Luffy choose?",
        "special_patch":{"Devil Fruit":"Gum-Gum Fruit (rubber body)","Crew":"Luffy's unnamed starting crew","Bounty":0,"Devil Fruit Profile":{"name":"Gum-Gum Fruit (rubber body)","type":"Paramecia (understood at this point as the Gum-Gum Fruit)","abilities":["Rubber physiology","Stretching strikes","Elastic momentum and rebounds"],"limitations":["Cannot swim","Seawater and Sea-Prism Stone suppress the user","Cuts and piercing attacks remain dangerous"],"counters":["Bladed weapons","Restraint","Haki once encountered"],"awakening_status":"Unawakened","awakening_requirements":["Far greater physical and mental mastery","A future story-valid awakening crisis"]}},
    },
    "zoro_shells": {
        "reputation":{"Marines":-10,"Pirates":5},
        "active_canon_event":"Shells Town upheaval",
        "active_event_context":"Zoro remains restrained at the Marine base under Captain Morgan's corrupt rule. His execution pressure and the civilians around the base are active, not background flavor.",
        "active_event_prompt":"The base is tightening around Zoro. How does he answer the immediate threat?",
    },
    "gon_departure": {
        "position":"Hunter Exam applicant leaving Whale Island",
        "special_patch":{"Hunter License":"Applicant","Nen Access":"Undiscovered"},
        "active_canon_event":"Departure from Whale Island",
        "active_event_context":"Gon has earned Mito's reluctant permission and is ready to leave Whale Island for the Hunter Exam. Nen remains completely unknown to him.",
        "active_event_prompt":"The departing ship is taking passengers. What does Gon do before Whale Island disappears behind it?",
    },
    "kurapika_exam": {
        "position":"Hunter Exam applicant",
        "special_patch":{"Hunter License":"Applicant","Nen Access":"Undiscovered"},
    },
    "naruto_birth": {
        "affiliations":[{"faction":"Konohagakure","rank":"Civilian dependent","status":"protected","joined":"Birth","notes":"A newborn under Konoha's protection during the Nine-Tails crisis."}],
        "reputation":{"Konohagakure":0},
        "active_canon_event":"Naruto's birth and the Nine-Tails attack",
        "active_event_context":"Naruto has just been born while an attack develops around Kushina's seal. His agency is necessarily newborn-scale—attention, emotion, chakra response and survival—while adults act according to their own knowledge and priorities.",
        "active_event_prompt":"Noise and violent chakra press into Naruto's first sensations. How does the newborn respond?",
    },
    "naruto_graduation": {
        "reputation":{"Konohagakure":5},
        "active_canon_event":"Academy graduation night — the Mizuki incident",
        "active_event_context":"The graduation test and Mizuki's manipulation are now live. Naruto has not yet stolen the Forbidden Scroll or learned the Shadow Clone Technique.",
        "active_event_prompt":"The instructors' decision has landed and Mizuki is waiting for an opening. What does Naruto do?",
    },
    "jinhyeok_tower": {
        "active_canon_event":"Tower manifestation",
        "active_event_context":"The former game has become lethal reality. Jinhyeok's knowledge is exceptional, but every remembered route must now be verified against a world where death is real.",
        "active_event_prompt":"The first System notice is appearing and the crowd has not organized. What route does Jinhyeok take?",
    },
    "grid_pagma": {
        "affiliations":[{"faction":"Players","rank":"Independent Player","status":"active","joined":"Account creation","notes":"An independent Satisfy player with no guild."}],
        "reputation":{"Players":0,"Local Lords":-5},
        "active_canon_event":"Pagma's legacy changes hands",
        "active_event_context":"Pagma's Rare Book has been consumed and the legendary successor class is mechanically active. Earl Ashur's anger, Grid's debt and his lack of mastery all remain immediate pressures.",
        "active_event_prompt":"The class window has changed and the consequences are already moving. What does Grid do first as Pagma's Descendant?",
    },
    "rimuru_awakens": {
        "active_canon_event":"A new slime awakens",
        "active_event_context":"Rimuru has only just become conscious as a slime. Great Sage and Predator exist, but the cave, body, senses and nearby presence are not yet understood.",
        "active_event_prompt":"Sight is absent, the new body feels unfamiliar, and Great Sage can answer bounded questions. What does Rimuru test first?",
    },
}


def _normalize_canon_character_starts():
    for scenarios in MAJOR_CHARACTER_STARTS.values():
        for scenario in scenarios:
            patch = _CANON_START_NORMALIZATION.get(scenario.get("id"), {})
            for key, value in patch.items():
                if key == "special_patch":
                    merged = dict(value)
                    merged.update(scenario.get("special_patch") or {})
                    # Structured additions are allowed to refine an existing
                    # legacy field without replacing the preset's facts.
                    if isinstance(value.get("Devil Fruit Profile"), dict):
                        merged["Devil Fruit Profile"] = dict(value["Devil Fruit Profile"])
                    scenario["special_patch"] = merged
                else:
                    scenario.setdefault(key, value)
            # Canon starts use exact deterministic sheets.  Their previous
            # minimums are the curated values, not a floor beneath a random
            # original-character roll.
            scenario.setdefault("stat_values", dict(scenario.get("stat_minimums") or {}))
            scenario.setdefault("expanded_background", scenario.get("background", ""))
            scenario.setdefault("affiliations", [])
            scenario.setdefault("reputation", {})
            for quest in scenario.get("starting_quests", []):
                quest.setdefault("category", "main")
                quest.setdefault("explanation", scenario.get("background", "The character begins at an established canon turning point."))
                quest.setdefault("current_knowledge", list(scenario.get("knowledge") or [])[:5])
                quest.setdefault("clear_conditions", list(quest.get("objectives") or [])[-1:])


_normalize_canon_character_starts()


def playable_characters_for(world):
    return MAJOR_CHARACTER_STARTS.get(world, [])

# Worlds where the source material actually supports starting somewhere
# (or with someone) different — a shonen world has multiple villages/crews/
# factions to begin in or with. Worlds without a lore reason for variety
# (an MMO tutorial city, a single tower entrance) are simply omitted here,
# and the New Campaign form falls back to that world's single wd["start"].
WORLD_START_OPTIONS = {
    "One Piece": [
        {"label": "Foosha Village (East Blue civilian)", "location": "Foosha Village", "note": "Starting in a quiet East Blue village as a local, traveler, dock worker, would-be sailor, or young adventurer preparing to leave home."},
        {"label": "Shells Town (Marine recruit)", "location": "Shells Town", "note": "Starting posted as a Marine recruit at Shells Town."},
        {"label": "Goa Kingdom (kingdom-born)", "location": "Goa Kingdom", "note": "Starting life in the Goa Kingdom."},
        {"label": "Shimotsuki Village (swordsman village)", "location": "Shimotsuki Village", "note": "Starting in an East Blue village known for its sword dojo and Wano-descended traditions."},
        {"label": "Orange Town (small port)", "location": "Orange Town", "note": "Starting in a rebuilding East Blue port vulnerable to pirate raids."},
        {"label": "Syrup Village (quiet island)", "location": "Syrup Village", "note": "Starting in a peaceful East Blue village with little protection from outside threats."},
        {"label": "Baratie (sea restaurant)", "location": "Baratie", "note": "Starting aboard the floating restaurant Baratie as staff, a customer, or a traveler seeking passage."},
        {"label": "Cocoyasi Village (occupied village)", "location": "Cocoyasi Village", "note": "Starting under the Arlong Pirates' control, where resistance and survival shape daily life."},
        {"label": "Loguetown (Grand Line gateway)", "location": "Loguetown", "note": "Starting in the city of Gold Roger's execution, the final major East Blue port before the Grand Line."},
        {"label": "Reverse Mountain (Grand Line crossing)", "location": "Reverse Mountain", "note": "Starting as a traveler, guide, castaway, or crew member near the dangerous entrance to the Grand Line."},
        {"label": "Drum Island (winter kingdom)", "location": "Drum Island", "note": "Starting in a winter kingdom known for medicine, harsh terrain, and political upheaval."},
        {"label": "Alabasta (desert kingdom)", "location": "Alabasta", "note": "Starting in the desert kingdom of Alabasta amid royal, criminal, military, and civilian interests."},
        {"label": "Jaya (pirate port)", "location": "Jaya", "note": "Starting in a lawless pirate port where information, violence, and impossible dreams collide."},
        {"label": "Skypiea (sky island)", "location": "Skypiea", "note": "Starting above the Blue Sea among sky-island cultures, dials, and conflicts over sacred land."},
        {"label": "Water 7 (shipwright city)", "location": "Water 7", "note": "Starting in the waterborne city famous for shipwrights, sea trains, commerce, and hidden government activity."},
        {"label": "Enies Lobby (government service)", "location": "Enies Lobby", "note": "Starting inside a restricted World Government judicial stronghold as an official, guard, prisoner, or infiltrator."},
        {"label": "Sabaody Archipelago (world crossroads)", "location": "Sabaody", "note": "Starting at the crowded gateway to the New World among pirates, Marines, merchants, nobles, and traffickers."},
        {"label": "Amazon Lily (Kuja homeland)", "location": "Amazon Lily", "note": "Starting within the secluded Kuja homeland; outsiders require a specific background explaining how they arrived or were accepted."},
        {"label": "Fishman Island (undersea kingdom)", "location": "Fishman Island", "note": "Starting in the undersea kingdom as a resident, visitor, guard, merchant, or traveler preparing for the New World."},
        {"label": "Marineford (Marine headquarters)", "location": "Marineford", "note": "Starting at Marine headquarters as enlisted personnel, an officer, government visitor, prisoner, or infiltrator."},
        {"label": "Impel Down (great prison)", "location": "Impel Down", "note": "Starting within the great undersea prison as an inmate, guard, official, or covert infiltrator."},
        {"label": "Baltigo (Revolutionary base)", "location": "Baltigo", "note": "Starting at the Revolutionary Army's hidden base with a background that establishes membership, sponsorship, or capture."},
        {"label": "Kano Country (West Blue kingdom)", "location": "Kano Country", "note": "Starting in a West Blue nation shaped by martial traditions, politics, and the Happo Navy."},
        {"label": "Sorbet Kingdom (South Blue kingdom)", "location": "Sorbet Kingdom", "note": "Starting in the South Blue's Sorbet Kingdom as a citizen, traveler, royal subject, or revolutionary contact."},
        {"label": "Germa Kingdom (mobile North Blue kingdom)", "location": "Germa Kingdom", "note": "Starting aboard Germa's mobile kingdom as a subject, soldier, scientist, guest, captive, or infiltrator."},
        {"label": "Dressrosa (New World kingdom)", "location": "Dressrosa", "note": "Starting in Dressrosa under Doflamingo's rule, amid royal secrets, criminal trade, and public spectacle."},
        {"label": "Totto Land (Big Mom territory)", "location": "Totto Land", "note": "Starting within Big Mom's territory as a resident, guest, subordinate, political hostage, or trespasser."},
        {"label": "Zou (Mink homeland)", "location": "Zou", "note": "Starting on the wandering elephant Zunesha among the Mink Tribe; non-Mink characters need a plausible route there."},
        {"label": "Wano Country (closed nation)", "location": "Wano Country", "note": "Starting inside isolated Wano as a native, captive, smuggler, pirate, samurai, or covert visitor."},
        {"label": "Egghead Island (future island)", "location": "Egghead Island", "note": "Starting on Dr. Vegapunk's restricted island as a researcher, government asset, test subject, visitor, or infiltrator."},
        {"label": "Mary Geoise (seat of government)", "location": "Mary Geoise", "note": "Starting at the World Government's most restricted capital with a background establishing status, service, captivity, or infiltration."},
        {"label": "Arlong Park (occupied territory)", "location": "Arlong Park", "note": "Starting in Arlong-controlled territory as a prisoner, collaborator, infiltrator, local resister, or stranded traveler."},
        {"label": "Whiskey Peak (bounty-hunter town)", "location": "Whiskey Peak", "note": "Starting in the apparent welcoming town whose hidden economy revolves around bounty hunters and newly arrived pirates."},
        {"label": "Thriller Bark (haunted ship-island)", "location": "Thriller Bark", "note": "Starting aboard Thriller Bark with a background explaining capture, infiltration, service, or accidental arrival."},
        {"label": "Punk Hazard (forbidden research island)", "location": "Punk Hazard", "note": "Starting on the restricted island as a survivor, captive, researcher, government asset, or infiltrator in a compatible era."},
    ],
    "Hunter x Hunter": [
        {"label": "Whale Island (rural start)", "location": "Whale Island", "note": "Starting in a close-knit fishing community as a local, visitor, wilderness-trained youth, or Hunter hopeful preparing to see the wider world."},
        {"label": "Yorknew City (urban start)", "location": "Yorknew City", "note": "Starting in the streets of Yorknew City."},
        {"label": "Hunter Exam Site (already an applicant)", "location": "Hunter Exam Site", "note": "Already en route to sit the Hunter Exam."},
        {"label": "Heavens Arena (fighter or spectator)", "location": "Heavens Arena", "note": "Starting around the fighting tower as a competitor, worker, trainer, or visitor; Nen knowledge still depends on the background and era."},
        {"label": "Kukuroo Mountain (testing gate region)", "location": "Kukuroo Mountain", "note": "Starting near the Zoldyck estate with a background explaining work, travel, training, or a deliberate attempt to reach the Testing Gate."},
        {"label": "Greed Island (qualified entrant)", "location": "Greed Island", "note": "Starting as a qualified Greed Island player; choose a compatible era or accept the start as a deliberate divergence."},
        {"label": "Meteor City (discarded city)", "location": "Meteor City", "note": "Starting in Meteor City as a resident, visitor, recruit, aid worker, criminal contact, or outsider under scrutiny."},
        {"label": "NGL (isolated nation)", "location": "NGL", "note": "Starting inside NGL with a background that accounts for its strict borders and limited technology."},
        {"label": "Hunter Association HQ (professional start)", "location": "Hunter Association HQ", "note": "Starting at Association headquarters as an applicant, staff member, licensed Hunter, client, or escorted visitor."},
        {"label": "Zevil Island (field trial)", "location": "Zevil Island", "note": "Starting during or around a Hunter Exam field phase, expedition, recovery operation, or independent survival test."},
    ],
    "Naruto": [
        {"label": "Konohagakure", "location": "Konohagakure", "note": "Starting in the Hidden Leaf with family ties, rank, training, duties, and village access determined by the chosen origin and background."},
        {"label": "Sunagakure", "location": "Sunagakure", "note": "A shinobi of Sunagakure, the Hidden Sand Village."},
        {"label": "Kirigakure", "location": "Kirigakure", "note": "A shinobi of Kirigakure, the Hidden Mist Village."},
        {"label": "Kumogakure", "location": "Kumogakure", "note": "A shinobi of Kumogakure, the Hidden Cloud Village."},
        {"label": "Iwagakure", "location": "Iwagakure", "note": "A shinobi of Iwagakure, the Hidden Stone Village."},
        {"label": "Akatsuki (Amegakure)", "location": "Amegakure", "note": "Starting already recruited into the Akatsuki, an international criminal organization operating out of Amegakure — not affiliated with any Hidden Village."},
        {"label": "Iron Country", "location": "Iron Country", "note": "A samurai-in-training of Iron Country — chakra plays little part in daily life here; skill is earned through the blade and discipline, not jutsu."},
        {"label": "Forest of Death (field exercise)", "location": "Forest of Death", "note": "Starting during a sanctioned exercise, Chunin Exam phase, patrol, research assignment, or unauthorized entry."},
        {"label": "Land of Waves (frontier mission)", "location": "Land of Waves", "note": "Starting in the Land of Waves as a local, traveler, mercenary, missing-nin, or shinobi assigned to a regional mission."},
        {"label": "Land of Rice Fields (borderland)", "location": "Land of Rice Fields", "note": "Starting in the border region as a local, wandering shinobi, investigator, merchant escort, or future Sound contact."},
        {"label": "Kannabi Bridge (wartime start)", "location": "Kannabi Bridge", "note": "Starting near Kannabi Bridge during a compatible wartime era or as a deliberate alternate-history premise."},
    ],
    "Bleach": [
        {"label": "Shin'o Academy (senior student)", "location": "Shin'o Academy", "note": "A final-year Soul Reaper academy student preparing for graduation and division placement."},
        {"label": "Seireitei (recent graduate)", "location": "Seireitei", "note": "A newly graduated Soul Reaper awaiting interviews, recommendations and assignment to one of the thirteen divisions."},
        {"label": "Shin'o Academy (Kidō honors senior)", "location": "Shin'o Academy", "note": "A final-year Soul Reaper academy student with a Kidō focus, preparing for graduation and possible Kidō Corps or squad interviews."},
        {"label": "Shin'o Academy (field practicum senior)", "location": "Shin'o Academy", "note": "A final-year Soul Reaper academy student beginning supervised field practicum before graduation and division placement."},
        {"label": "Seireitei (Kidō Corps candidate)", "location": "Seireitei", "note": "A recent Soul Reaper graduate invited to interview with the Kidō Corps while retaining a narrative say in final placement."},
        {"label": "Seireitei (Onmitsukidō candidate)", "location": "Seireitei", "note": "A recent Soul Reaper graduate under consideration for covert service while retaining a narrative say in final placement."},
    ],
    "Jujutsu Kaisen": [
        {"label":"Tokyo Jujutsu High — First Year","location":"Tokyo Jujutsu High","origin":"Tokyo Jujutsu High — First Year","note":"A first-year Tokyo student learning field survival, cursed-energy control and the practical rules of their birth slot."},
        {"label":"Tokyo Jujutsu High — Second Year","location":"Tokyo Jujutsu High","origin":"Tokyo Jujutsu High — Second Year","note":"A second-year Tokyo student with completed missions, established relationships and a developing technique application set."},
        {"label":"Tokyo Jujutsu High — Third Year","location":"Tokyo Jujutsu High","origin":"Tokyo Jujutsu High — Third Year","note":"A senior Tokyo student with meaningful field history and approaching professional assessment."},
        {"label":"Kyoto Jujutsu High — First Year","location":"Kyoto Jujutsu High","origin":"Kyoto Jujutsu High — First Year","note":"A first-year Kyoto student entering a more traditional jujutsu institution."},
        {"label":"Kyoto Jujutsu High — Second Year","location":"Kyoto Jujutsu High","origin":"Kyoto Jujutsu High — Second Year","note":"A second-year Kyoto student with field experience and school responsibilities."},
        {"label":"Kyoto Jujutsu High — Third Year","location":"Kyoto Jujutsu High","origin":"Kyoto Jujutsu High — Third Year","note":"A senior Kyoto student preparing for professional sorcerer work."},
        {"label":"Independent Curse User","location":"Tokyo","origin":"Independent Curse User","note":"An unaffiliated curse user operating beyond school authority; contacts, legality and motive come from the background."},
        {"label":"Great Clan Member","location":"Tokyo","origin":"Great Clan Member","note":"A member of the Gojo, Zenin, Kamo or a generated lesser clan, with access and obligations shaped by the background."},
        {"label":"Sentient Cursed Spirit","location":"Tokyo","origin":"Sentient Cursed Spirit","note":"A self-aware curse whose source, form, temperament and technique are generated from the background when unspecified."},
    ],
    "Solo Max-Level Newbie": [
        {"label":"Earth — Tower Entrance (manifestation)","location":"Earth — Tower Entrance","note":"Starting outside the newly manifested Tower before the first clear routes are established."},
        {"label":"Floor 1 (opening scenario)","location":"Floor 1","note":"Starting inside the first live Tower scenario as a registered player."},
        {"label":"Floor 5 (experienced climber)","location":"Floor 5","note":"Starting as an established early climber with preceding clears, equipment, XP and knowledge generated to match the background."},
        {"label":"Floor 10 (advanced early climber)","location":"Floor 10","note":"Starting at an early boss threshold with prior progression generated to match the claimed route and achievements."},
    ],
    "Overgeared": [
        {"label":"Winston (starting city)","location":"Winston","note":"Starting among Winston's players, craftspeople and local political pressures."},
        {"label":"Patrian (military city)","location":"Patrian","note":"Starting in the fortified city as a player, mercenary, crafter or traveler."},
        {"label":"Reidan (frontier)","location":"Reidan","note":"Starting in the neglected frontier; select a compatible era or treat early access as a deliberate divergence."},
        {"label":"Bairan (regional city)","location":"Bairan","note":"Starting in Bairan among guild, trade and adventuring opportunities."},
        {"label":"Titan (capital)","location":"Titan","note":"Starting in the capital with access and obligations appropriate to the background."},
        {"label":"Kesan Canyon (dangerous route)","location":"Kesan Canyon","note":"Starting on the canyon route as an explorer, mercenary, quest hunter or stranded traveler."},
        {"label":"Temple of Yatan (dangerous start)","location":"Temple of Yatan","note":"Starting near an active Yatan-related danger; the background must explain why the character is there."},
        {"label":"Frontier (settlement opportunity)","location":"Frontier","note":"Starting where undeveloped territory creates construction, production, monster-hunting and political opportunities."},
        {"label":"Saharan Empire (imperial society)","location":"Saharan Empire","note":"Starting within the empire with status, access and obligations determined by the background."},
        {"label":"Northern Frontier (harsh expedition)","location":"Northern Frontier","note":"Starting on a cold frontier as an explorer, soldier, crafter, settler, quest party member, or stranded player."},
    ],
    "Reincarnated as a Slime": [
        {"label":"Great Jura Forest (new arrival)","location":"Great Jura Forest","note":"Starting unaligned in the Great Jura Forest."},
        {"label":"Sealed Cave (isolated awakening)","location":"Great Jura Forest — Sealed Cave","note":"Starting inside the sealed cave with no automatic knowledge of its inhabitants or secrets."},
        {"label":"Goblin Village (small settlement)","location":"Goblin Village","note":"Starting in or near the early goblin settlement as a resident, guest, captive or traveler."},
        {"label":"Dwargon (armed nation)","location":"Dwargon","note":"Starting in Dwargon with legal access and status determined by the background."},
        {"label":"Blumund (human town)","location":"Blumund","note":"Starting in the human town as a resident, adventurer, merchant, demi-human or concealed monster."},
        {"label":"Tempest (established nation)","location":"Tempest","note":"Starting in established Tempest; select a compatible era or accept an alternate-history premise."},
        {"label":"Kingdom of Falmuth (human power)","location":"Kingdom of Falmuth","note":"Starting in Falmuth as a citizen, soldier, adventurer, official, merchant, demi-human, or concealed monster."},
        {"label":"Sorcerous Dynasty of Thalion (magical nation)","location":"Sorcerous Dynasty of Thalion","note":"Starting in Thalion with social access, magical education and official scrutiny determined by the background."},
        {"label":"Milim's Domain (dangerous court)","location":"Milim's Domain","note":"Starting in a demon lord's territory with allegiance, invitation, captivity, infiltration or exceptional survival explained by the background."},
        {"label":"Dragon Peak (remote frontier)","location":"Dragon Peak","note":"Starting near Dragon Peak as an explorer, monster, pilgrim, researcher or survivor with risks scaled to the background."},
    ],
    "Custom World": [
        {"label":"Starting Region (central start)","location":"Starting Region","note":"Starting in the setting's central region with details generated from the custom-world description."},
        {"label":"Northern Reach (remote frontier)","location":"Northern Reach","note":"Starting on the northern frontier with climate, factions and opportunities generated from the custom setting."},
        {"label":"Western March (contested border)","location":"Western March","note":"Starting in a western borderland shaped by the custom setting's active conflicts and trade."},
        {"label":"Eastern Reach (distant crossroads)","location":"Eastern Reach","note":"Starting at an eastern crossroads with cultures and pressures grounded in the custom setting."},
        {"label":"Southern Wilds (dangerous wilderness)","location":"Southern Wilds","note":"Starting in the southern wilderness with survival conditions and inhabitants generated from the custom setting."},
    ],
}


def start_options_for(world):
    return WORLD_START_OPTIONS.get(world, [])


BASE_STATE = {
    "name":"Traveler","age":"","age_at_campaign_start":"","age_anchor_year":1,"position":"","world":"Custom World","difficulty":"Adventurer","background":"","custom_world":"","race":"","calendar_epoch":"","calendar_anchor_day":None,"last_protagonist_tick_day":None,"active_canon_event":"","active_event_context":"","active_event_prompt":"","player_identity":{"mode":"original","canon_character_id":"","canon_gravity":True},
    "level":1,"xp":0,"xp_next":100,"hp":100,"hp_max":100,"resource_name":"Energy","resource":100,"resource_max":100,
    "stats":{"Strength":10,"Dexterity":10,"Constitution":10,"Intelligence":10,"Wisdom":10,"Charisma":10},"hidden_stats":{},
    "skills":{},"titles":[],"class_profile":{},"inventory":[],"equipment":{},"quests":[],"relationships":{},"reputation":{},
    # faction_chain is mechanically maintained (see continuity.py) — a
    # {faction: [{event, turn, canon_day}, ...]} trail of why reputation
    # actually moved, parallel to how npc_memories[name].chain already
    # works. reputation_chain_events is the transient AI-facing input: a
    # one-turn {faction: "one-line reason"} the GM writes alongside a
    # reputation change, consumed and cleared by continuity.py the same
    # turn it's written.
    "faction_chain":{}, "reputation_chain_events":{},
    "factions":{},"affiliations":[],"companions":[],"companion_combinations":[],"codex":[],"location":"Starting Region","discovered_locations":[],"custom_locations":[],"political_regions":[],"polity_state":{},
    "tower_floor":1,"tower_floor_deadline_day":None,"tower_over":False,"canon_event_engagement_count":0,"background_world_feed":[],
    "last_major_beat_day":None,"director_notes":"","simulation_scale":"Individual",
    "world_time":"Day 1 — Morning","status":[],"alive":True,"turn":0,"timeline":[],"special":{},
    "canon_divergences":[],"canon_integrity_repairs":[],"campaign_canon":[],"world_events":[],"currency":{"name":"Currency","amount":250},"currencies":{},
    # Application-owned accounting history. The GM changes currency through
    # normal state patches; local code records the resulting reason and
    # balance here so players can always see where important money went.
    "currency_ledger":[],"finance_debts":[],
    "npc_memories":{},"npc_relationships":{},"shops":[],
    # purchase_offer is the transient AI-facing input (one narrative buy
    # opportunity per turn: {item, price, vendor}); purchase_offers is the
    # permanent, app-owned list systems.record_purchase_offer builds from
    # it — each entry gets a real id and resolved flag so the Chronicle's
    # inline Buy button always transacts against the app's own stored
    # price, never anything a client could echo back.
    "purchase_offer":None,"purchase_offers":[],
    # rated_good_turns is app-owned (see engine_journal.rate_last_turn_good):
    # a small snapshot list of {turn, action, outcome} the player explicitly
    # thumbs-upped, fed back into resolve()'s prompt as a real, campaign-
    # specific "match this quality" example instead of a hand-written one.
    "rated_good_turns":[],
    # faction_rosters tracks WHO is actually in a named group ({faction:
    # [member names]}) — factions/reputation only ever tracked a standing
    # score, never membership, so the GM had nothing concrete to check
    # before narrating "who's in the Akatsuki right now" and would invent
    # plausible-sounding filler instead. Canon-character starts with a
    # real established roster (see MAJOR_CHARACTER_STARTS) seed this at
    # creation; the GM keeps it updated as membership actually changes.
    "faction_rosters":{},
    "organizations":{}, "organization_lives":{},
    "jjk_system":{},
    "known_recipes":[],"training_log":[],"combat":{},"danger_scenario":{},"active_encounters":[],"hidden_quests":[],"quest_archive":[],"achievements":[],"overgeared_system":{},"solo_system":{},"world_depth":{},"world_clock_minutes":480,"location_details":{},"travel_history":[],"loot_history":[],"ability_progress":{},"contacts":{},"chat_threads":{},"unread_chats":[],"group_chats":{},"time_mode":"moment","queued_actions":[],"standing_orders":[],"standing_intents":[],"time_skip_history":[],"current_activity":None,"calendar":{"day":1,"month":1,"year":1,"hour":8,"minute":0},"scheduled_events":[],
    # A regularly-recurring income or expense (a job, a shop's take, rent,
    # staff wages, a stipend) the GM has established — see
    # process_recurring_finances() in engine_time.py, which pays these out
    # automatically as canon_day advances instead of relying on the AI to
    # remember and manually re-apply a lump sum every time it recurs.
    # {label, kind:"income"|"expense", amount (positive), interval_days,
    #  next_due_day (canon_day), active, notes} — see task_rules() for the
    # GM-facing schema.
    "recurring_finances":[],"long_term_projects":[],"appearance_desc":"","creation_locks":{},"portrait_traits":[],"portrait_identity":{"locked":False,"canonical_description":"","temporary_traits":[],"active_form":{},"history":[],"reference_file":""},"campaign_id":"","campaign_created_version":"","campaign_last_saved_version":"","schema_version":21,"world_pack_id":"builtin","last_autosave":"","opening_complete":False,"suggested_actions":[],"advisor_thread":[],"prerequisite_tracks":[],"continuity_ledger":{"facts":[],"warnings":[],"last_checked_turn":0},"validation_log":[],"diagnostics":{},"weather":"clear","canon_day":-7,"canon_time_minutes":-9600,"canon_anchor":"","canon_events_fired":[],"pending_minor_events":[],"minutes_since_status_window":0,"status_window_due":False,"progression_log":[],"progression_ledger":[],"starting_power_band":"Average","starting_power_notice":"","chapter_summaries":[],"chapter_buffer":[],"verified_memory_archive":[],"memory_consolidation":{"last_turn":0,"archived_through_turn":0,"runs":0},"consequence_ledger":[],"npc_clocks":{},"faction_clocks":{},"causality_ledger":[],"knowledge_audit":[],"health_repairs":[],"npc_intentions":{},"simulation_events":[],"local_background_turn":0,"difficulty_controls":{},"progression_preset":{},"planned_route":[],"lore_sources":[],"action_goals":[],"correction_log":[],"authoritative_corrections":[],"information_packets":[],"npc_schedules":{},"canon_event_states":{},"simulation_validation":[],
    # memory_updates is a transient GM suggestion; reliability.py folds it
    # into the app-owned, deduplicated long-term narrative memory.
    "memory_updates":{},"narrative_memory":{"established_facts":[],"player_goals":[],"unresolved_mysteries":[],"promises":[],"relationships":[],"consequences":[]},
    "campaign_direction":{},"relationship_opportunities":[],"last_cause_effect":[],"last_training_summary":{},"last_ai_route":{},"campaign_arcs":[],"campaign_arc_archive":[],"campaign_arc_director":{"quiet_until_turn":0,"last_beat_turn":-1,"last_resolution_turn":-1,"history":[]},"campaign_arc_context":{"active_arcs":[],"quiet_period":False,"quiet_until_turn":0,"recent_resolutions":[]},
    "world_plans":{},"world_benefits":{},
    "life_simulation":{"version":1,"last_processed_day":0,"people":{},"relationships":{},"households":[],"mentorships":[],"event_history":[],"pending_choices":[],"legacy_records":[],"succession":{},"processed_evidence":[]},"life_context":{},
    "trophy_proposals":[],"legacy_trophies":[],"dismissed_trophy_ids":[],"downtime_surprise_state":{},"message_delivery_state":{},
    "capability_profile":{},"ability_registry":{},"progression_calibration":{},"npc_continuity":{},
    "encounter_state":{"version":1,"phase":"idle","negotiation_possible":True,"violence_committed":False},
    "story_threads":{},"scenario_memory":{"active":{},"history":[]},"world_milestones":[],"resolution_ledger":[],"simulation_core_version":1,"world_activity":{},
    "last_failed_turn":{},"recovery_timeline":[],"last_combat":{},
    "standing_order_state":{},"memory_tiers":{"hot":[],"warm":[],"cold":[]},
    "scene_state":{},"scene_history":[],"last_outcome_scale":{},"outcome_scale_ledger":[],
    "obligation_ledger":[],"delayed_consequences":[],"canon_divergence_impacts":{},
    "pacing_profile":{"recent_beats":[],"counts":{},"last_guidance":""},
    "player_style_profile":{},"lore_confidence_log":[],
    "companion_autonomy":{},"npc_development":{},"ability_evolution":{},
    "world_downtime_cycles":{},"prompt_budget_log":[]
}

WORLD_EXPANSIONS = {
    "One Piece": {
        "currency":"Berries", "currency_baseline":5000,
        "economy_notes":"Canon reference scale: a cheap meal or basic supplies run tens to low hundreds of Berries; a decent weapon or a few days' lodging is in the low thousands; a serious ship upgrade or rare item reaches the tens of thousands to low millions. Bounties (not liquid cash, but the setting's main power/wealth signal) scale from ~30,000,000 for a newly-dangerous rookie into the hundreds of millions for known threats, and Yonko-tier figures sit at 4,000,000,000+ Berries. A Yonko or a World Government-backed noble's actual liquid wealth is billions; an ordinary adventurer's is not — keep the player's own numbers grounded in their actual station even as the setting's upper end is enormous.",
        "origins":["East Blue Civilian","Island Martial Artist","Dockworker","Bounty-Hunter Trainee","Runaway Noble","Aspiring Pirate","Marine Recruit",
                   "Veteran Crew Member","Notorious Bounty-Head"],
        "archetypes":["Brawler","Swordsman","Marksman","Navigator","Shipwright","Medic","Roguish Fighter","Archaeologist"],
        "training":["Physical Conditioning","Weapon Mastery","Observation Drills","Armament Conditioning","Navigation","Seamanship"],
        "shop_types":["General Store","Weapon Shop","Ship Supply","Tavern","Black Market"],
        "loot":["Berries","Rations","Weapon Materials","Log Pose Lead","Rare Ingredient","Treasure Map Fragment"],
        "encounters":["Bandit Crew","Pirate Scouts","Marine Patrol","Sea Beast","Bounty Hunter","Island Wildlife"],
        "systems":["Bounty","Haki","Devil Fruit","Crew","Ship","Wanted Status"]
    },
    "Hunter x Hunter": {
        "currency":"Jenny", "currency_baseline":3000,
        "economy_notes":"Canon reference scale: Jenny tracks roughly 1:1 with real-world yen, so treat amounts like everyday yen prices — a meal or simple supplies run hundreds to a few thousand Jenny, ordinary lodging or gear in the low thousands to tens of thousands. Licensed Hunters receive major government stipends and access, worth a lifetime total in the billions — becoming a Hunter is itself treated as a life-changing financial event, not just a title. High-stakes rewards, auction items, and major bounties can reach into the hundreds of millions to billions of Jenny for the setting's biggest names.",
        "origins":["Yorknew Local","Rural Prodigy","Martial-Arts Student","Street Survivor","Merchant Family","Exam Aspirant",
                   "Licensed Hunter","Veteran Hunter"],
        "archetypes":["Martial Artist","Tracker","Strategist","Infiltrator","Medic","Treasure Hunter","Information Broker","Beast Hunter","Blacklist Hunter"],
        "training":["Ten Practice","Zetsu Practice","Ren Endurance","Gyo Focus","Combat Conditioning","Hatsu Theory"],
        "shop_types":["General Market","Auction Contact","Martial-Arts Supplier","Information Broker","Hunter Shop"],
        "loot":["Jenny","Medical Supplies","Auction Lead","Rare Material","Hunter Intel","Training Notes"],
        "encounters":["Exam Rival","Criminal Crew","Wild Beast","Arena Fighter","Mafia Enforcer","Nen User"],
        "systems":["Nen Category","Aura","Ten","Zetsu","Ren","Hatsu","Hunter License"]
    },
    "Naruto": {
        "currency":"Ryo", "currency_baseline":500,
        "economy_notes":"Canon reference scale (databook mission pay): D-rank missions pay 5,000-50,000 Ryo, C-rank 30,000-100,000 Ryo, B-rank 80,000-200,000 Ryo — A-rank and S-rank scale well beyond that, into the hundreds of thousands to low millions for a village's most sensitive work. Everyday purchases (a meal, basic supplies, kunai/shuriken restock) run tens to a few hundred Ryo. A shinobi actively taking missions should see their Ryo move with real frequency; a genin's finances and a jonin's or a clan head's are entirely different scales.",
        "origins":["Civilian Academy Hopeful","Shinobi Clan Child","Orphan Trainee","Merchant Family","Border-Village Youth","Academy Graduate",
                   "Uchiha Clan Child","Iron Country Samurai-in-Training","Rogue Ninja (Missing-nin)","Anbu Root Recruit",
                   "Chunin on Active Duty","Jonin Squad Leader"],
        "archetypes":["Taijutsu Specialist","Ninjutsu Student","Genjutsu Student","Scout","Medic","Weapon Specialist","Tactician","Samurai","Sealing Specialist","Sensor","Puppet User"],
        "training":["Chakra Control","Tree Walking","Water Walking","Taijutsu Drills","Shurikenjutsu","Nature Transformation"],
        "shop_types":["Ninja Tools","General Store","Medic Supplies","Scroll Shop","Black Market"],
        "loot":["Ryo","Kunai","Shuriken","Explosive Tags","Medic Supplies","Technique Notes"],
        "encounters":["Bandits","Rogue Ninja","Wildlife","Rival Genin","Missing-nin Scouts","Enemy Patrol"],
        "systems":["Chakra","Nature Affinity","Jutsu","Rank","Village Standing","Mission Record"]
    },
    "Solo Max-Level Newbie": {
        "currency":"Coins", "currency_baseline":300,
        "economy_notes":"Tower/gamer-fiction economy: nominal numbers run much higher than a real-world equivalent — early floors deal in tens to low hundreds of Coins for basic gear and potions, but drops, clears, and player-market trades scale fast, reaching the thousands to tens of thousands by mid-tower and far beyond at high floors and for named/unique gear. A player actively clearing floors, selling drops, or completing floor quests should see Coins move often and in escalating amounts as they climb, not stay flat.",
        "origins":["Veteran Gamer","Competitive Raider","Puzzle Specialist","Martial Artist","Streamer","Ordinary Survivor","Elite Ranker"],
        "archetypes":["All-Rounder","Melee","Ranged","Caster","Assassin","Tank","Support","Trap Specialist"],
        "training":["Stat Optimization","Weapon Mastery","Mana Control","Skill Repetition","Boss Pattern Study","Hidden-Condition Research"],
        "shop_types":["Tower Shop","Player Market","Artifact Broker","Potion Merchant","Secret Merchant"],
        "loot":["Coins","Potions","Skill Stone","Artifact Fragment","Monster Core","Hidden-Key Fragment"],
        "encounters":["Goblin Pack","Elite Monster","Rival Player","Floor Guardian","Trap Room","Hidden Boss"],
        "systems":["Floor","Stats","Skills","Copied Abilities","Achievements","Hidden Conditions","Artifacts"]
    },
    "Overgeared": {
        "currency":"Gold", "currency_baseline":200,
        "economy_notes":"Canon reference scale: this is a VRMMO economy with real, large numbers — basic potions/repairs/travel run single-to-low-double-digit Gold, decent crafted gear reaches the hundreds to low thousands, and a genuinely notable item or a solid raid/dungeon haul can be worth millions of Gold (canon examples: a single named weapon valued around 8,000,000 Gold; a guild's raid haul around 21,000,000 Gold). A crafter, trader, or active dungeon-clearer should see Gold swing by real, escalating amounts — a beginning adventurer's numbers and a renowned blacksmith's or top guild's are different orders of magnitude entirely.",
        "origins":["New Player","Guild Recruit","Mercenary Player","Quest Hunter","Magic Academy Student","Temple Initiate","Beast Tamer","Merchant","Crafter","Blacksmith Apprentice","Veteran Adventurer","Renowned Craftsman"],
        "archetypes":["Warrior","Knight","Swordsman","Spearman","Archer","Mage","Magic Swordsman","Assassin","Martial Artist","Tank","Priest/Healer","Support","Summoner","Tactician","Beast Master","Explorer","Merchant/Orator","Blacksmith","Alchemist","Tailor","Architect"],
        "training":["Weapon Proficiency","Spell Mastery","Party Coordination","Raid Practice","Class Quest Research","Companion Training","Leadership","Exploration","NPC Affinity","Blacksmithing","Alchemy","Production Mastery"],
        "shop_types":["General Store","Weapon Shop","Magic Shop","Temple Quartermaster","Auction House","Potion Shop","Companion Market","Guild Market","Smithy"],
        "loot":["Gold","Equipment","Spellbook","Class Quest Clue","Companion Contract","Quest Item","Recipe","Memorable Material"],
        "encounters":["Field Monsters","Bandits","Rival Players","Dungeon Party","Guild Conflict","NPC Crisis","Political Dispute","Elite Monster","Raid Boss","Hidden Class Trial"],
        "systems":["Class","Class Advancement","Skills","Level","Guild","Party Role","NPC Affinity","Reputation","Item Rating","Optional Production"]
    },
    "Bleach": {
        "currency":"Yen", "currency_baseline":0, "tracks_currency":False,
        "economy_notes":"Kan exists in Soul Society and Yen exists in the Living World, but neither is a persistent player resource in this campaign. Mention money only when a particular scene makes it narratively important. Ordinary living costs and reasonable purchases happen without bookkeeping; meaningful gear and scarce resources depend on rank, authorization, favors, requisitions, availability, or story consequences.",
        "origins":["Shin'o Academy Senior","Recent Shin'o Academy Graduate"],
        "archetypes":["Zanjutsu Specialist","Kido Caster","Hakuda Fighter","Hoho Specialist","Kaidō Healer","Tactical Officer"],
        "training":["Zanjutsu Drills","Kido Incantation Practice","Hakuda Conditioning","Shunpo Practice","Reiatsu Control","Zanpakuto Communication"],
        "shop_types":["Urahara Shop","Squad Quartermaster","Division Requisition Office","Academy Supply Office","Rukongai Artisan"],
        "loot":["Soul Candy","Gikongan","Spirit Medicine","Reishi Training Material","Official Mission Supply","Authorized Equipment"],
        "encounters":["Hollow incursion","Unquiet Plus","Academy rival","Division patrol","Training accident","Rare Menos-class emergency"],
        "systems":["Reiryoku","Reiatsu","Zanpakuto","Shikai","Bankai","Squad Rank","Soul Society Standing"]
    },
    "Jujutsu Kaisen": {
        "currency":"Yen", "currency_baseline":12000, "tracks_currency":False,
        "economy_notes":"Money exists normally but is not a progression system. Handle routine expenses narratively; track only a purchase, debt or resource when the scene makes it matter.",
        "origins":["Tokyo Jujutsu High — First Year","Tokyo Jujutsu High — Second Year","Tokyo Jujutsu High — Third Year","Kyoto Jujutsu High — First Year","Kyoto Jujutsu High — Second Year","Kyoto Jujutsu High — Third Year","Independent Curse User","Great Clan Member","Sentient Cursed Spirit"],
        "archetypes":[],
        "training":["Cursed Energy Control","Body Reinforcement","Technique Application","Barrier Fundamentals","Binding Vow Study","Cursed Tool Practice","Reverse Cursed Technique Theory","Domain Theory"],
        "shop_types":["Jujutsu High Storehouse","Cursed Tool Broker","Clan Armory","Independent Curse-User Contact"],
        "loot":["Cursed Tool","Cursed Object","Protective Talisman","Mission Intelligence","Technique Record"],
        "encounters":["Cursed spirit manifestation","Curse-user ambush","Barrier anomaly","School mission","Clan pressure","Special-grade emergency"],
        "systems":["Cursed Energy","Innate Technique","Heavenly Restriction","Technique Applications","Binding Vows","Barrier Arts","Domain Expansion","Sorcerer Grade"]
    },
    "Custom World": {
        "currency":"Currency", "currency_baseline":250,
        "origins":["Local","Traveler","Soldier","Scholar","Outcast","Artisan"],
        "archetypes":["Warrior","Scout","Scholar","Mage","Rogue","Healer"],
        "training":["Physical Training","Weapon Training","Study","Meditation","Crafting","Social Practice"],
        "shop_types":["General Store","Weapon Shop","Apothecary","Market","Specialist"],
        "loot":["Currency","Supplies","Equipment","Crafting Material","Clue","Rare Item"],
        "encounters":["Bandits","Wildlife","Rival","Patrol","Elite Enemy","Boss"],
        "systems":["Level","Skills","Reputation","Titles"]
    },
    "Reincarnated as a Slime": {
        "currency":"Gold Coin", "currency_baseline":150,
        "economy_notes":"Canon reference scale: one Gold Coin is worth roughly $1000 — most ordinary people never handle one directly, transacting instead in smaller silver/copper-equivalent amounts for daily life. Treat routine purchases (a meal, simple supplies, a night's lodging) as costing a small fraction of a Gold Coin or a handful at most; only real purchases — good gear, trade goods, services from a named merchant or nation — should move whole Gold Coins, and a large transaction (a guild/nation-level deal, rare materials, a significant commission) can run into the hundreds or thousands.",
        "origins":["Reincarnated Otherworlder","Native Monster","Isekai'd Human","Orphaned Demi-Human","Failed Hero Candidate","Displaced Noble",
                   "Veteran Tempest Officer","Named Monster of Renown"],
        "archetypes":["Brawler Monster","Skill Analyst","Elementalist","Beast-kin Warrior","Diplomat/Leader","Support/Healer","Assassin-type Monster","Magic Crafter"],
        "training":["Magicule Circulation","Skill Synthesis Practice","Combat Instinct Drills","Insight Meditation","Leadership & Diplomacy","Elemental Control"],
        "shop_types":["Goblin Village Market","Dwarven Craftsmen","Blumund Trade Post","Black Market Artifacts","Tempest Bazaar"],
        "loot":["Gold Coin","Magic Crystal","Monster Core","Dwarven-forged Gear","Rare Ingredient","Demon Lord Insignia"],
        "encounters":["Rogue Monster","Human Adventurer Party","Demon Lord Subordinate","Orc Lord Remnant","Bandit Crew","Awakened Beast"],
        "systems":["Named Skills","Evolution","Magicule Capacity","Demon Lord Seed","Nation Reputation"]
    }
}

def expansion_for(world):
    return WORLD_EXPANSIONS.get(world, WORLD_EXPANSIONS["Custom World"])


# Each world rolls checks against its OWN named abilities instead of being
# forced through generic D&D stats — a Naruto check calls on Taijutsu/
# Ninjutsu/Genjutsu, not raw STR/INT. These names are used directly as the
# state.stats dict keys, as the GM's roll-schema enum, and as the Attributes
# panel labels — one source of truth for "what this world's checks are about."
WORLD_ABILITIES = {
    "One Piece": ["Strength", "Agility", "Endurance", "Willpower", "Instinct", "Charisma"],
    "Hunter x Hunter": ["Strength", "Agility", "Aura Control", "Cunning", "Willpower", "Charisma"],
    "Naruto": ["Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect"],
    "Solo Max-Level Newbie": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck"],
    "Overgeared": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck"],
    "Custom World": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"],
    "Reincarnated as a Slime": ["Magicule Control", "Skill Mastery", "Instinct", "Insight", "Willpower", "Presence"],
    "Bleach": ["Zanjutsu", "Hakuda", "Hoho", "Kido", "Reiatsu Control", "Willpower"],
    "Jujutsu Kaisen": ["Physical Ability", "Speed & Reflexes", "Cursed Energy Reserves", "Cursed Energy Output", "Cursed Energy Control", "Jujutsu Insight", "Soul Stability"],
}

# "full_sheet" worlds are status-window/LitRPG genres where the classic
# stat sheet — including stats the player hasn't discovered yet — is a core
# genre convention. "narrative" worlds just show their named abilities plainly.
WORLD_STAT_STYLE = {
    "One Piece": "narrative",
    "Hunter x Hunter": "narrative",
    "Naruto": "narrative",
    "Solo Max-Level Newbie": "full_sheet",
    "Overgeared": "full_sheet",
    "Custom World": "full_sheet",
    "Reincarnated as a Slime": "narrative",
    "Bleach": "narrative",
    "Jujutsu Kaisen": "narrative",
}

# Numbered XP/levels remain available only where the source world presents
# them as a literal in-fiction system. Narrative worlds progress through
# open-ended attributes, techniques, knowledge, ranks and titles instead.
WORLD_XP_MODE = {"Solo Max-Level Newbie": True, "Overgeared": True}


def uses_xp_for(world, custom_world_text=""):
    if world == "Custom World":
        return bool(re.search(r"\b(xp|experience points?|level(?:s|ing|led| up)?)\b", str(custom_world_text or ""), re.I))
    return bool(WORLD_XP_MODE.get(world, False))

# How much itemization matters to this world. "full" worlds (gear-driven
# LitRPGs) show the whole equipped set; "weapon_only" worlds only surface
# the character's signature weapon/held item, not a full loadout.
WORLD_GEAR_STYLE = {
    "One Piece": "weapon_only",
    "Hunter x Hunter": "weapon_only",
    "Naruto": "weapon_only",
    "Solo Max-Level Newbie": "full",
    "Overgeared": "full",
    "Custom World": "full",
    "Reincarnated as a Slime": "weapon_only",
    "Bleach": "weapon_only",
    "Jujutsu Kaisen": "weapon_only",
}


def abilities_for(world):
    return WORLD_ABILITIES.get(world, WORLD_ABILITIES["Custom World"])


def gear_style_for(world):
    return WORLD_GEAR_STYLE.get(world, "full")


# A character who has already chosen to specialize should not start
# statistically identical to everyone else. Each archetype gets a primary
# (and sometimes secondary) ability from that world's own ability set that
# starts noticeably higher — applied on top of a randomized, non-flat
# baseline in game.new_campaign's stat rolling.
ARCHETYPE_PRIMARY_STAT = {
    "One Piece": {
        "Brawler": ["Strength"], "Swordsman": ["Agility", "Strength"], "Marksman": ["Instinct", "Agility"],
        "Navigator": ["Instinct", "Willpower"], "Shipwright": ["Endurance", "Strength"],
        "Medic": ["Willpower", "Instinct"], "Roguish Fighter": ["Agility", "Instinct"],
        "Archaeologist": ["Instinct", "Charisma"],
    },
    "Hunter x Hunter": {
        "Martial Artist": ["Strength", "Agility"], "Tracker": ["Cunning", "Agility"],
        "Strategist": ["Cunning", "Willpower"], "Infiltrator": ["Agility", "Cunning"],
        "Medic": ["Willpower", "Cunning"], "Treasure Hunter": ["Cunning", "Agility"],
        "Information Broker": ["Charisma", "Cunning"], "Beast Hunter": ["Cunning", "Strength"],
        "Blacklist Hunter": ["Cunning", "Willpower"],
    },
    "Naruto": {
        "Taijutsu Specialist": ["Taijutsu"], "Ninjutsu Student": ["Ninjutsu"], "Genjutsu Student": ["Genjutsu"],
        "Scout": ["Intellect", "Chakra Control"], "Medic": ["Chakra Control", "Intellect"],
        "Weapon Specialist": ["Taijutsu", "Chakra Control"], "Tactician": ["Intellect", "Willpower"],
        "Sealing Specialist": ["Chakra Control", "Intellect"], "Sensor": ["Chakra Control", "Intellect"],
        "Puppet User": ["Chakra Control", "Intellect"], "Samurai": ["Taijutsu", "Willpower"],
    },
    "Solo Max-Level Newbie": {
        "All-Rounder": ["Strength", "Dexterity", "Intelligence"], "Melee": ["Strength", "Constitution"],
        "Ranged": ["Dexterity", "Wisdom"], "Caster": ["Intelligence", "Wisdom"], "Assassin": ["Dexterity", "Luck"],
        "Tank": ["Constitution", "Strength"], "Support": ["Wisdom", "Intelligence"],
        "Trap Specialist": ["Intelligence", "Luck"],
    },
    "Overgeared": {
        "Warrior": ["Strength", "Constitution"], "Swordsman": ["Dexterity", "Strength"],
        "Knight": ["Constitution", "Strength"], "Spearman": ["Strength", "Dexterity"],
        "Archer": ["Dexterity", "Wisdom"], "Mage": ["Intelligence", "Wisdom"],
        "Magic Swordsman": ["Strength", "Intelligence"], "Assassin": ["Dexterity", "Luck"],
        "Martial Artist": ["Strength", "Dexterity"], "Tank": ["Constitution", "Strength"],
        "Priest/Healer": ["Wisdom", "Intelligence"], "Support": ["Wisdom", "Intelligence"],
        "Summoner": ["Intelligence", "Wisdom"], "Tactician": ["Wisdom", "Intelligence"],
        "Beast Master": ["Wisdom", "Dexterity"], "Explorer": ["Luck", "Dexterity"],
        "Merchant/Orator": ["Luck", "Wisdom"], "Blacksmith": ["Strength", "Constitution"],
        "Alchemist": ["Intelligence", "Wisdom"], "Tailor": ["Dexterity", "Wisdom"],
        "Architect": ["Intelligence", "Wisdom"],
    },
    "Custom World": {
        "Warrior": ["Strength", "Constitution"], "Scout": ["Dexterity", "Wisdom"], "Scholar": ["Intelligence"],
        "Mage": ["Intelligence", "Wisdom"], "Rogue": ["Dexterity", "Charisma"], "Healer": ["Wisdom", "Intelligence"],
    },
    "Reincarnated as a Slime": {
        "Brawler Monster": ["Instinct", "Magicule Control"], "Skill Analyst": ["Insight", "Skill Mastery"],
        "Elementalist": ["Magicule Control", "Skill Mastery"], "Beast-kin Warrior": ["Instinct", "Willpower"],
        "Diplomat/Leader": ["Presence", "Willpower"], "Support/Healer": ["Insight", "Presence"],
        "Assassin-type Monster": ["Instinct", "Insight"], "Magic Crafter": ["Skill Mastery", "Insight"],
    },
    "Bleach": {
        "Zanjutsu Specialist": ["Zanjutsu", "Hoho"], "Kido Caster": ["Kido", "Reiatsu Control"],
        "Hakuda Fighter": ["Hakuda", "Hoho"], "Hoho Specialist": ["Hoho", "Zanjutsu"],
        "Healer": ["Kido", "Willpower"], "Tactician": ["Willpower", "Reiatsu Control"],
        "Quincy Marksman": ["Reiatsu Control", "Hoho"],
    },
}


def primary_stats_for(world, archetype):
    return ARCHETYPE_PRIMARY_STAT.get(world, {}).get(archetype, [])


# Whether a world's named abilities draw from the world resource pool
# (Chakra/Mana/Aura/Magicule/Stamina/Energy) when used, or run on a cooldown
# instead. Every world here defaults to pool-based costs — jutsu cost
# Chakra, Solo Max-Level Newbie skills cost Mana, Nen/Hatsu cost Aura, named
# skills cost Magicule — except Overgeared, which by genre convention splits
# combat Skills (cooldown-gated, no mana cost) from Spells/Magic
# (mana-gated); see ability_resource_type_for.
WORLD_DEFAULT_ABILITY_RESOURCE = {
    "Overgeared": "cooldown",
}


# Speed and defense analogs per world, used by the local combat resolver to
# turn a large stat mismatch into a real tactical swing — extra attacks for
# a decisive speed edge, damage negation for a decisive defense edge — the
# same way MASSIVE_GAP_THRESHOLD turns a decisive offense edge into a much
# bigger hit. Independent of POOL_STATS (which sizes HP/resource pools):
# these are specifically "how quick" and "how tough in a fight" for a
# world's genre, and deliberately distinct from each other and from the
# archetype's primary offense stat so the three axes can pull apart.
WORLD_SPEED_STAT = {
    "One Piece": "Agility", "Hunter x Hunter": "Agility", "Naruto": "Taijutsu",
    "Solo Max-Level Newbie": "Dexterity", "Overgeared": "Dexterity",
    "Reincarnated as a Slime": "Instinct", "Custom World": "Dexterity", "Bleach": "Hoho",
    "Jujutsu Kaisen": "Speed & Reflexes",
}
WORLD_DEFENSE_STAT = {
    "One Piece": "Endurance", "Hunter x Hunter": "Willpower", "Naruto": "Willpower",
    "Solo Max-Level Newbie": "Constitution", "Overgeared": "Constitution",
    "Reincarnated as a Slime": "Willpower", "Custom World": "Constitution", "Bleach": "Willpower",
    "Jujutsu Kaisen": "Physical Ability",
}


def speed_stat_for(world):
    return WORLD_SPEED_STAT.get(world, "Dexterity")


def defense_stat_for(world):
    return WORLD_DEFENSE_STAT.get(world, "Constitution")


def _power_tier_row(value):
    numeric = max(0.0, float(value or 0))
    index = sum(1 for threshold in POWER_TIER_THRESHOLDS if numeric >= threshold)
    index = min(index, len(POWER_TIERS) - 1)
    number, name, description = POWER_TIERS[index]
    return {"index": number, "name": name, "description": description, "score": round(numeric, 1)}


def power_profile_for(world, stats, archetype=""):
    """One stat interpretation shared by UI, Advisor, GM, and combat prose.

    A single extreme specialty remains mechanically extraordinary without
    pretending it also grants speed, defense, stamina, judgment, or political
    authority. Geometric means keep an 800/40/40 specialist legible rather
    than letting an arithmetic average erase every weak axis.
    """
    clean = {str(name): max(1.0, float(value)) for name, value in (stats or {}).items()
             if isinstance(value, (int, float))}
    if not clean:
        empty = _power_tier_row(0)
        return {"overall": empty, "combat": empty, "peak": {**empty, "stat": ""},
                "axes": {}, "lopsided": False, "interpretation": "No usable stats are recorded."}
    values = list(clean.values())
    overall_score = len(values) / sum(1.0 / value for value in values)
    peak_name, peak_value = max(clean.items(), key=lambda row: row[1])
    primary = [name for name in primary_stats_for(world, archetype) if name in clean]
    offense_name = max(primary, key=lambda name: clean[name]) if primary else peak_name
    speed_name = speed_stat_for(world)
    defense_name = defense_stat_for(world)
    offense = clean.get(offense_name, peak_value)
    speed = clean.get(speed_name, overall_score)
    defense = clean.get(defense_name, overall_score)
    combat_score = 3.0 / ((1.0 / offense) + (1.0 / speed) + (1.0 / defense))
    ordered = sorted(values)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2 - 1] + ordered[len(ordered)//2]) / 2
    lopsided = peak_value >= max(80, median * 2.5)
    interpretation = (
        f"{peak_name} is an extreme specialty, but {speed_name} and {defense_name} still govern speed and defense."
        if lopsided else "The character's highest capability and supporting combat attributes are broadly aligned."
    )
    profile = {
        "overall": _power_tier_row(overall_score),
        "combat": _power_tier_row(combat_score),
        "peak": {**_power_tier_row(peak_value), "stat": peak_name, "value": int(peak_value),
                 "note": "Peak specialty only; never use this as the character's overall tier."},
        "axes": {
            "offense": {"stat": offense_name, "value": int(offense)},
            "speed": {"stat": speed_name, "value": int(speed)},
            "defense": {"stat": defense_name, "value": int(defense)},
        },
        "arithmetic_average": round(sum(values) / len(values), 1),
        "lopsided": lopsided,
        "interpretation": interpretation,
        "scale_rule": "Current mechanical stats outrank starting labels and stock-canon assumptions about the player character.",
    }
    profile["world_overall"] = benchmark_tier(world, overall_score)
    profile["world_combat"] = benchmark_tier(world, combat_score)
    profile["world_peak"] = benchmark_tier(world, peak_value)
    # Generic rows remain available for old internal calculations, but the
    # single player-facing view is explicitly world-native so UI/AI consumers
    # cannot present "Legendary", "Elite Jonin" and "Kage Candidate" as three
    # competing answers.
    profile["player_facing"] = {
        "balanced": copy.deepcopy(profile["world_combat"]),
        "foundation": copy.deepcopy(profile["world_overall"]),
        "peak_specialty": {**copy.deepcopy(profile["world_peak"]), "stat": peak_name, "value": int(peak_value)},
        "rule": "Show balanced as the primary rating and peak_specialty separately. Do not display generic tier names.",
    }
    profile["benchmark_reference"] = benchmark_context(world)
    return profile


def ability_resource_type_for(world, archetype=""):
    """Default resource_type for a skill that hasn't explicitly tagged one
    (see the skill-authoring rules in engine_core.gm_rules). Overgeared's
    Mage archetype is the one common case where a character's *default*
    combat ability is actually a mana-spending Spell rather than a
    cooldown Skill, so it gets its own default; everything else falls back
    to the world-level default above."""
    if world == "Overgeared" and archetype == "Mage":
        return "pool"
    return WORLD_DEFAULT_ABILITY_RESOURCE.get(world, "pool")


def stat_style_for(world):
    return WORLD_STAT_STYLE.get(world, "full_sheet")


# Load user-installed worlds after every built-in registry exists. Invalid
# packs are isolated and reported through /api/world-packs.
import os as _os
from pathlib import Path as _Path
from world_packs import load_world_packs as _load_world_packs

_pack_root = _Path(_os.getenv("APPDATA") or _Path.home()) / "WorldwalkerRPG" / "world_packs"
WORLD_PACKS_LOADED, WORLD_PACK_ERRORS = _load_world_packs(_pack_root, {
    "data": WORLD_DATA, "expansions": WORLD_EXPANSIONS, "abilities": WORLD_ABILITIES,
    "stat_style": WORLD_STAT_STYLE, "gear_style": WORLD_GEAR_STYLE,
    "starts": WORLD_START_OPTIONS, "timelines": CANON_TIMELINES,
    "primary": ARCHETYPE_PRIMARY_STAT, "characters": MAJOR_CHARACTER_STARTS,
})
