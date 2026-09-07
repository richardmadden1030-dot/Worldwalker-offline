"""Deterministic world mechanics for the two explicit LitRPG settings.

The AI remains the narrator and author of unusual fiction.  This module keeps
the repeatable bookkeeping local: Satisfy class/production/social records and
Tower floors, copied abilities, achievements, artifacts, rivals, and reports.
It deliberately does *not* simulate crafting recipes.  Crafting happens in the
Chronicle; only reusable or otherwise memorable finished objects reach the Bag.
"""
from __future__ import annotations

import copy
import re

from worlds import tower_floor_theme
from overgeared_classes import infer_class_type, starter_kit_for


ITEM_RATING_ORDER = {
    "normal": 0, "common": 0, "uncommon": 1, "rare": 2, "epic": 3,
    "unique": 4, "legendary": 5, "myth": 6, "mythic": 6,
}
INGREDIENT_RE = re.compile(
    r"\b(?:ore|ingot|reagent|ingredient|herb|hide|pelt|lumber|timber|wood|"
    r"thread|cloth scrap|dust|powder|shard|fragment|monster core|metal scrap|"
    r"crafting material|raw material|unrefined|catalyst)\b", re.I,
)
REUSABLE_RE = re.compile(
    r"\b(?:sword|blade|dagger|axe|spear|bow|staff|wand|shield|armor|armour|"
    r"helmet|helm|boots|gloves|gauntlets|ring|necklace|amulet|cloak|coat|"
    r"accessory|tool|kit|artifact|relic|key|map|book|tome|device|potion|"
    r"letter|document|contract|badge|token|permit|journal|blueprint|recipe)\b", re.I,
)
CRAFT_RE = re.compile(
    r"\b(?:craft|forge|smith|smelt|sew|brew|enchant|repair|produce|fabricate)\b|"
    r"\b(?:make|create|build|construct)\b.{0,32}\b(?:item|weapon|armor|armour|gear|potion|tool|building|structure|machine|device|clothes|accessory)\b",
    re.I,
)
CLASS_RE = re.compile(r"\b(?:class|signature skill|class quest|specialization|successor)\b", re.I)
SOCIAL_RE = re.compile(r"\b(?:talk|help|gift|promise|befriend|support|save|betray|threaten|negotiate|relationship)\b", re.I)
GUILD_RE = re.compile(r"\b(?:guild|territory|lord|kingdom|settlement|reidan|govern|army)\b", re.I)
ADVENTURE_RE = re.compile(r"\b(?:quest|raid|dungeon|fight|attack|defend|hunt|explore|scout|travel|train|practice|study|heal|support|cast|summon|command|lead|negotiate|trade|perform|discover|investigate|protect)\b", re.I)
SOLO_INSPECT_RE = re.compile(r"\b(?:inspect|analy[sz]e|observe|study|search|scout|investigate|test|look for|hidden condition)\b", re.I)
SOLO_COPY_RE = re.compile(r"\b(?:copy|steal|replicate|acquire)\b.{0,45}\b(?:skill|ability|power|technique)\b", re.I)


FLOOR_ENVIRONMENTS = (
    "Cover and routes shift after loud combat.",
    "Light and sound attract stronger hunting packs.",
    "The terrain becomes more dangerous whenever a major mechanism is activated.",
    "Inactive mechanisms can become hazards, routes, or improvised weapons.",
    "The scenario rewards decisive action but punishes prolonged stalling.",
    "False routes repeat familiar details while the true route changes one clue.",
    "Exposure accumulates unless the party secures shelter or keeps moving.",
    "Movement and positioning are as dangerous as direct damage.",
)
FLOOR_BOSSES = (
    "Gate-Eater Garm", "Moonfang Matriarch", "Drowned Bell Keeper", "Brass Tyrant",
    "Cinder Champion", "The Reflected Judge", "White-Crown Warden", "Tempest Roc",
)
FLOOR_ADMINS = (
    "Administrator Orin", "Administrator Sable", "Administrator Mira", "Administrator Vex",
    "Administrator Cael", "Administrator Nox", "Administrator Ilyra", "Administrator Rook",
)
HIDDEN_CONDITIONS = (
    ("Merciful Route", "Reach the boss without killing an ordinary floor creature.", "Title: The Hand That Stayed"),
    ("Unbroken Tempo", "Complete every mandatory chamber without resting.", "Agility and stamina reward"),
    ("Rules Lawyer", "Use the administrator's exact wording to satisfy the clear condition indirectly.", "Administrator favor and a hidden key"),
    ("Untouched Challenger", "Defeat the guardian without receiving healing.", "Title and defensive stat reward"),
    ("Cartographer's Proof", "Identify the false route before entering it.", "Secret route map"),
    ("Borrowed Strength", "Clear the final mechanic using an enemy's own effect.", "Ability-copy condition progress"),
)

# Facts directly established or strongly anchored by the available floor
# references.  Everything else still receives a coherent package from the
# 50-floor theme table, but is labeled contextual rather than pretending an
# unrevealed canon detail was published fact.
SOLO_REVEALED_FLOORS = {
    1: {"canon_status":"revealed", "name":"Hapjeong Station", "scenario":"Survive the opening Tower manifestation and its first lethal rules.", "factions":["Newly awakened players", "Korean response organizations"], "mc_route":"Use veteran game knowledge to exploit the tutorial's hidden conditions."},
    2: {"canon_status":"revealed", "name":"Mangrove, Tree of Greed", "scenario":"Cross a carnivorous forest governed by the Mangrove of Greed.", "factions":["Forest monsters", "Competing player parties"], "mc_route":"Investigate the Tree of Greed and its non-obvious reward conditions."},
    5: {"canon_status":"revealed", "name":"Collapsed Civilization", "scenario":"Navigate the remnants of a civilization that already destroyed itself.", "factions":["Surviving residents", "Floor predators", "Player expeditions"], "mc_route":"Follow the canon route or pursue a different settlement and relic outcome."},
    19: {"canon_status":"revealed", "name":"The 19th Floor's Hidden Place", "scenario":"Find the concealed region and survive what was isolated there.", "factions":["Hidden-place guardians", "Competing high-rank players"], "mc_route":"Search for the same hidden entrance reached in canon or discover another route."},
    20: {"canon_status":"revealed", "name":"Murim Gate", "scenario":"Enter the Murim floor ecosystem of sects, martial politics, and territorial conflict.", "factions":["Murim Alliance", "Demonic Cult", "independent clans and sects"], "mc_route":"Engage the same faction struggle as Jinhyuk or form an original allegiance."},
    21: {"canon_status":"partially revealed", "name":"Giant's Fortress", "scenario":"Survive the fortress society and decide how to deal with its ruler and residents.", "factions":["Fortress residents", "outside challengers"], "mc_route":"Pursue fortress authority through the canon opportunity or reject rulership."},
    48: {"canon_status":"revealed location", "name":"48th Floor", "scenario":"Operate in an upper-floor domain where administrators and apex factions closely watch challengers.", "factions":["Upper-floor powers", "Administrator interests"], "mc_route":"Canon encounters are available if prerequisites and timing align."},
    50: {"canon_status":"revealed apex", "name":"Top of the Tower", "scenario":"Face the Tower's last trial and the consequences of reaching its apex.", "factions":["Destia's authority", "surviving apex challengers"], "mc_route":"Reach the same final opportunity as the canonical clear without forcing the same decision."},
}


def _text(value):
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or "").strip()
    return str(value or "").strip()


def _list(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _number(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def item_rating(value):
    if not isinstance(value, dict):
        return "Common"
    raw = str(value.get("rating") or value.get("grade") or value.get("rarity") or "Common").strip()
    return raw.title() or "Common"


def _is_ingredient(item):
    if isinstance(item, dict) and any(item.get(key) for key in ("quest_item", "artifact", "reusable", "memorable")):
        return False
    return bool(INGREDIENT_RE.search(_text(item)))


def memorable_item(item):
    """Whether an item deserves a persistent Bag record."""
    if _is_ingredient(item):
        return False
    if isinstance(item, dict):
        if any(item.get(key) for key in ("quest_item", "artifact", "reusable", "memorable", "equippable")):
            return True
        if ITEM_RATING_ORDER.get(item_rating(item).lower(), 0) >= 2:
            return True
        if _list(item.get("effects") or item.get("effect")):
            return True
    return bool(REUSABLE_RE.search(_text(item)))


def normalize_memorable_inventory(state, before=None):
    """Keep routine materials narrative while preserving meaningful objects."""
    inventory = state.get("inventory") if isinstance(state.get("inventory"), list) else []
    old_names = {_text(item).lower() for item in (before or {}).get("inventory", []) if _text(item)}
    kept, removed, enriched = [], [], []
    for raw in inventory:
        name = _text(raw)
        if not name:
            continue
        is_new = name.lower() not in old_names
        # Routine crafting materials never become inventory clutter. Other
        # newly acquired objects remain unless the narrator explicitly framed
        # them as a component; a letter, keepsake, or unfamiliar quest clue
        # should not disappear simply because it is not equipment.
        if is_new and _is_ingredient(raw):
            removed.append(name)
            continue
        item = copy.deepcopy(raw)
        if is_new and not isinstance(item, dict) and memorable_item(item):
            item = {
                "name": name, "rating": "Common", "category": "Reusable item",
                "effects": [], "restrictions": [], "source": "Established in the Chronicle",
            }
        if isinstance(item, dict) and memorable_item(item):
            item.setdefault("name", name)
            item.setdefault("rating", item_rating(item))
            item.setdefault("category", "Quest object" if item.get("quest_item") else ("Artifact" if item.get("artifact") else "Reusable item"))
            item["effects"] = [str(x) for x in _list(item.get("effects") or item.get("effect")) if str(x).strip()][:8]
            item["restrictions"] = [str(x) for x in _list(item.get("restrictions") or item.get("restriction")) if str(x).strip()][:6]
            item.setdefault("source", "Established in the Chronicle")
            if is_new:
                enriched.append(name)
        kept.append(item)
    state["inventory"] = kept[-120:]
    return {"removed_materials": removed, "memorable_items": enriched}


def build_floor_state(floor):
    floor = max(1, min(50, _number(floor, 1)))
    index = (floor - 1) % len(FLOOR_ENVIRONMENTS)
    canon_theme = tower_floor_theme(floor)
    environment = canon_theme.split(" — ", 1)[0]
    rule = FLOOR_ENVIRONMENTS[index]
    hidden = []
    for offset in range(2):
        name, condition, reward = HIDDEN_CONDITIONS[(floor + offset * 3 - 1) % len(HIDDEN_CONDITIONS)]
        hidden.append({
            "name": name, "condition": condition, "reward": reward,
            "discovered": False, "completed": False,
            "clue": f"A repeated detail in {environment} suggests the written objective is not the only valid route.",
        })
    recommended = 12 + floor * 9
    revealed = copy.deepcopy(SOLO_REVEALED_FLOORS.get(floor, {}))
    admin_traits = (
        ("Literalist", "Rewards exact compliance but respects airtight loopholes"),
        ("Spectator", "Favors dramatic solutions and punishes dull repetition"),
        ("Custodian", "Protects the floor's inhabitants and ecological balance"),
        ("Broker", "Trades information while concealing the true price"),
    )[index % 4]
    result = {
        "floor": floor,
        "name": f"Floor {floor} — {canon_theme}" + (f" · {revealed.get('name')}" if revealed.get("name") and revealed.get("name") not in canon_theme else ""),
        "canon_status": revealed.get("canon_status", "contextual reconstruction — unrevealed details may diverge"),
        "scenario": revealed.get("scenario") or f"Survive the scenario at {environment} and earn access to the ascent gate.",
        "clear_condition": f"Defeat or outmaneuver {FLOOR_BOSSES[index]} and activate the ascent gate.",
        "deadline_days": max(2, 9 - min(7, floor // 6)),
        "environment_rule": rule,
        "administrator": {
            "name": FLOOR_ADMINS[index], "disposition": 0, "interest": "Unproven challenger",
            "personality": admin_traits[0], "preference": admin_traits[1],
            "rivalries": [], "player_history": [],
            "rules": ["State rewards exactly", "Enforce the written scenario", "Permit earned loopholes"],
            "loopholes_found": 0,
        },
        "factions": revealed.get("factions") or [f"{environment} residents", "challenger expeditions", "the floor administrator's agents"],
        "ecosystem": {"day":"Ordinary threats patrol established territories", "night":"Temperature falls and monster aggression increases", "boss_influence":"The gatekeeper influences the floor beyond its arena"},
        "ordinary_enemies": [f"Floor {floor} scavenger pack", f"Floor {floor} scenario sentries"],
        "elite_enemy": f"Elite {environment.split()[0]} Stalker",
        "boss": {"name": FLOOR_BOSSES[index], "recommended_power": recommended, "defeated": False},
        "recommended_power": recommended,
        "hidden_conditions": hidden,
        "routes": [
            {"name": "Main route", "status": "Known", "risk": "Expected opposition"},
            {"name": "Alternate route", "status": "Undiscovered", "risk": "Unknown"},
        ],
        "mc_route": revealed.get("mc_route") or "A canon-parallel encounter may be generated when known context supports it; the player may choose a different route.",
        "rewards": {"main_clear":"XP, floor access, and a scenario-appropriate reward", "alternate_clear":"A distinct title, artifact, relationship, or administrator favor", "hidden":"Revealed only after its condition is discovered"},
        "status": "Active", "started_turn": 0,
    }
    return result


def _achievement_name(entry):
    return _text(entry)


def _normalize_copy(entry):
    if isinstance(entry, str):
        entry = {"name": entry}
    if not isinstance(entry, dict):
        return None
    name = _text(entry)
    if not name:
        return None
    result = copy.deepcopy(entry)
    result.update(name=name)
    result.setdefault("source", "Unknown")
    result.setdefault("rank", "Unranked")
    result.setdefault("effect", "Effect not fully analyzed")
    result.setdefault("copy_condition", "Discover and fulfill the target ability's System-recognized condition")
    result.setdefault("condition_progress", 0)
    result.setdefault("restriction", "Uses one copy slot and retains the copied ability's real limits")
    result.setdefault("slot_cost", 1)
    result["condition_progress"] = max(0, min(100, _number(result.get("condition_progress"), 0)))
    return result


def _production_path_for_text(text):
    text = str(text or "")
    if re.search(r"\b(?:blacksmith|forge|smith|smelt|metal|weapon|armor|blade|dagger|sword)\b", text, re.I):
        return "Blacksmithing"
    if re.search(r"\b(?:alchemist|brew|potion|alchemy|elixir)\b", text, re.I):
        return "Alchemy"
    if re.search(r"\b(?:tailor|sew|cloth|leather|garment)\b", text, re.I):
        return "Tailoring"
    if re.search(r"\b(?:wood|carve|bowyer|carpentry)\b", text, re.I):
        return "Woodworking"
    if re.search(r"\b(?:enchant|inscribe|rune|magic item)\b", text, re.I):
        return "Enchanting"
    return "General Production"


def _production_relevant(profile, special, class_profile):
    text = " ".join(str(x or "") for x in (
        profile.get("primary_class"), special.get("Class"), special.get("Archetype"),
        class_profile.get("name"), class_profile.get("class_type"), class_profile.get("description"),
    ))
    return bool(
        _number(profile.get("crafting_mastery", special.get("Crafting Mastery", 0))) > 0
        or _list(profile.get("production_specialties"))
        or "Production" in infer_class_type(text)
        or re.search(r"\b(?:craft|blacksmith|tailor|alchemist|architect|artisan|maker|miner|farmer|chef|scientist)\b", text, re.I)
    )


def _class_action_aligned(class_type, action_text):
    text = str(action_text or "")
    if not text.strip():
        return False
    patterns = {
        "Production": CRAFT_RE,
        "Support": re.compile(r"\b(?:heal|support|cleanse|buff|protect|aid|rescue|prayer|bless|restore)\b", re.I),
        "Command / Social": re.compile(r"\b(?:command|lead|plan|negotiate|speak|convince|organize|govern|guild|army|trade)\b", re.I),
        "Magic": re.compile(r"\b(?:cast|spell|magic|mana|ritual|enchant|study|research)\b", re.I),
        "Companion / Summoning": re.compile(r"\b(?:summon|contract|companion|pet|beast|minion|formation|command)\b", re.I),
        "Exploration / Utility": re.compile(r"\b(?:explore|scout|search|track|steal|infiltrate|map|discover|investigate|disarm)\b", re.I),
        "Combat": re.compile(r"\b(?:fight|attack|defend|duel|raid|hunt|block|strike|shoot|stab|train|practice)\b", re.I),
    }
    matched = any(regex.search(text) for label, regex in patterns.items() if label in str(class_type))
    # A flexible/unclassified adventurer can develop through broad activity;
    # a named role only advances its class track through that role's actual
    # contribution. Ordinary XP remains available for every meaningful act.
    return matched or ("Flexible" in str(class_type) and bool(ADVENTURE_RE.search(text)))


def _behavior_route(action_text):
    routes = (
        (r"\b(?:lead|command|govern|army|guild|organize|strategy)\b", "Commander"),
        (r"\b(?:protect|defend|shield|guard|rescue|endure)\b", "Guardian"),
        (r"\b(?:explore|scout|discover|track|map|infiltrate)\b", "Pathfinder"),
        (r"\b(?:heal|support|bless|restore|cleanse|aid)\b", "Luminary"),
        (r"\b(?:spell|magic|mana|ritual|research|arcane)\b", "Arcane"),
        (r"\b(?:summon|companion|contract|tame|beast)\b", "Pact"),
        (r"\b(?:negotiate|trade|merchant|diplom|social|convince)\b", "Broker"),
        (r"\b(?:craft|forge|smith|create|production)\b", "Artisan"),
        (r"\b(?:fight|attack|duel|hunt|raid|strike)\b", "Vanguard"),
    )
    return next((label for pattern, label in routes if re.search(pattern, str(action_text), re.I)), "Adaptive")


def _seed_overgeared(state):
    special = state.setdefault("special", {})
    profile = special.setdefault("Satisfy Profile", {})
    mastery = _number(profile.get("crafting_mastery", special.get("Crafting Mastery", 0)))
    class_profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
    profile_name = str(class_profile.get("name") or "").strip()
    profile_is_unclassed = profile_name.lower() in {"", "beginner", "unclassed"} or str(class_profile.get("class_type") or "").lower() == "unassigned"
    class_name = str((profile.get("primary_class") if profile_is_unclassed else profile_name)
                     or special.get("Class") or profile_name or "Beginner")
    is_unclassed = class_name.lower() in {"beginner", "unclassed"} or (profile_is_unclassed and str(profile.get("class_reception") or "").lower().startswith("pending"))
    class_type = str(profile.get("class_type") or class_profile.get("class_type") or infer_class_type(
        class_name, special.get("Archetype"), class_profile.get("description"), class_profile.get("effect")
    ))
    starter = starter_kit_for(special.get("Archetype") or class_name)
    if not class_profile and not is_unclassed:
        class_type = starter.get("class_type", class_type)
        skill_map = state.setdefault("skills", {})
        for skill_name, detail in starter.get("skills", {}).items():
            skill_map.setdefault(skill_name, copy.deepcopy(detail))
    if is_unclassed:
        class_name, class_type = "Beginner", "Unassigned"
    profile["primary_class"] = class_name
    profile["class_type"] = class_type
    production_relevant = _production_relevant(profile, special, class_profile)
    starting_path = _production_path_for_text(" ".join([
        class_name, str(special.get("Archetype", "")),
        " ".join(str(x) for x in _list(profile.get("production_specialties"))),
    ]))
    system = state.setdefault("overgeared_system", {})
    reception = system.setdefault("class_reception", {
        "status": "pending" if is_unclassed else "received", "preferred_route": str(profile.get("preferred_class_route") or special.get("Archetype") or "Adventurer"),
        "source": "Choose through the Chronicle" if is_unclassed else "Established class", "received_class": "" if is_unclassed else class_name,
    })
    if not is_unclassed and reception.get("status") != "received":
        reception.update({"status":"received", "received_class":class_name, "received_turn":state.get("turn", 0), "source":"Narrative class reception"})
        notice = f"[Class acquired]\n[{class_name}] has been received through the events of the Chronicle."
        system.setdefault("system_notifications", []).append({"turn":state.get("turn", 0), "type":"class", "message":notice})
    special["Class"] = class_name
    special["Class Rarity"] = str(class_profile.get("rank") or ("Common" if is_unclassed else profile.get("class_rarity") or "Normal"))
    paths = system.setdefault("production_paths", {})
    if production_relevant and not paths:
        paths[starting_path] = {"mastery": mastery, "rank": _production_rank(mastery), "progress": 0}
    elif not production_relevant and set(paths) == {"General Production"} and not _number(paths["General Production"].get("mastery"), 0):
        paths.clear()
    system.setdefault("class_progression", {
        "class": class_name,
        "class_type": class_type,
        "rarity": str(profile.get("class_rarity") or class_profile.get("rank") or "Normal"),
        "stage": "Awaiting class" if is_unclassed else "Foundation", "stage_progress": 0,
        "next_unlock": ("Find and fulfill a class-change opportunity in the story." if is_unclassed else str(class_profile.get("growth_path") or "Use the class successfully and complete a defining class quest.")),
        "unlocked_features": ([] if is_unclassed else ([str(class_profile.get("signature_skill"))] if class_profile.get("signature_skill")
                              else list(starter.get("features", [])))),
    })
    system["class_progression"]["class"] = class_name
    system["class_progression"]["class_type"] = class_type
    system.setdefault("role_development", {"aligned_actions": 0, "contribution_actions": 0, "major_achievements": [], "recent_growth": []})
    system.setdefault("companion_contracts", {})
    system.setdefault("system_notifications", [])
    system.setdefault("class_questlines", [])
    if class_name and not is_unclassed and not system["class_questlines"]:
        starter_quest = starter.get("quest", {}) if not class_profile else {}
        system["class_questlines"].append({
            "name": str(starter_quest.get("name") or f"The Path of {class_name}"), "class": class_name, "stage": "Foundation",
            "progress": 0, "goal": str(starter_quest.get("goal") or class_profile.get("growth_path") or "Prove the class through meaningful use."),
            "next_unlock": str(starter_quest.get("reward") or "A new class feature or specialization lead"), "status": "Active",
        })
    profile["class_features"] = list(dict.fromkeys(profile.get("class_features", []) + system["class_progression"].get("unlocked_features", [])))
    if is_unclassed:
        profile["advancement"] = "Receive a class through an in-world class-change opportunity, quest, item, achievement, or hidden condition."
    elif not profile.get("advancement") or profile.get("advancement") == "Develop the class through meaningful class-aligned actions and quests.":
        profile["advancement"] = class_profile.get("growth_path") or starter.get("growth_path")
    system.setdefault("npc_affinity", {})
    system.setdefault("affinity_history", {})
    system.setdefault("guild", {"name": str(profile.get("guild") or special.get("Guild") or "None"), "rank": "Unaffiliated", "resources": 0, "projects": [], "pressure": []})
    system.setdefault("territory", {"controlled": [], "population": 0, "morale": 50, "projects": [], "rival_pressure": []})
    system.setdefault("crafting_orders", [])
    system.setdefault("crafting_history", [])
    system.setdefault("equipment_legacies", {})
    system.setdefault("class_behavior", {"routes": {}, "evidence": []})
    system.setdefault("ranking_ecosystem", [
        {"name":"Leading public ranker", "kind":"Player", "rank_score":max(50, _number(state.get("level"),1)*12), "trend":"Rising", "reason":"Active in visible high-level content"},
        {"name":"Established top guild", "kind":"Guild", "rank_score":180, "trend":"Stable", "reason":"Controls raid access and veteran membership"},
        {"name":"Ambitious rival guild", "kind":"Guild", "rank_score":90, "trend":"Rising", "reason":"Recruiting and contesting regional influence"},
    ])
    rankings = system.setdefault("rankings", {})
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    level = _number(state.get("level"), 1)
    rankings.setdefault("Combat standing", {"score": level * 10 + max(stats.values(), default=0), "band": "Developing"})
    rankings.setdefault("Class standing", {"score": _number(system["class_progression"].get("stage_progress"), 0), "band": str(system["class_progression"].get("stage", "Foundation"))})
    rankings.setdefault("Adventure standing", {"score": level * 8, "band": "Developing"})
    if production_relevant:
        rankings.setdefault("Production standing", {"score": mastery, "band": _production_rank(mastery)})
    else:
        rankings.pop("Production standing", None)
    rankings.setdefault("NPC reputation", {"score": 0, "band": "Unknown"})
    rankings.setdefault("Guild influence", {"score": 0, "band": "Independent"})
    economy = system.setdefault("economy", {})
    currency = state.get("currency") if isinstance(state.get("currency"), dict) else {}
    economy.setdefault("personal_gold", _number(currency.get("amount"), 0))
    economy.setdefault("change_this_turn", 0)
    economy.setdefault("memorable_items", 0)
    economy.setdefault("workshop_income", 0)
    economy.setdefault("guild_funds", 0)
    economy.setdefault("territory_revenue", 0)
    economy.setdefault("important_effects", [])
    return system


def _production_rank(mastery):
    if mastery >= 1000: return "Legendary"
    if mastery >= 500: return "Master"
    if mastery >= 250: return "Expert"
    if mastery >= 100: return "Advanced"
    if mastery >= 35: return "Intermediate"
    return "Beginner"


def _seed_solo(state):
    special = state.setdefault("special", {})
    profile = special.setdefault("System Profile", {})
    floor = max(1, _number(state.get("tower_floor", profile.get("floor", 1)), 1))
    state["tower_floor"] = floor
    profile["floor"] = floor
    special["Floor"] = floor
    system = state.setdefault("solo_system", {})
    if not isinstance(system.get("floor_state"), dict) or _number(system["floor_state"].get("floor"), 0) != floor:
        system["floor_state"] = build_floor_state(floor)
        system["floor_state"]["started_turn"] = _number(state.get("turn"), 0)
    copied = [_normalize_copy(x) for x in _list(profile.get("copied_abilities", special.get("Copied Abilities", [])))]
    copied = [x for x in copied if x]
    profile["copied_abilities"] = copied
    special["Copied Abilities"] = copy.deepcopy(copied)
    system.setdefault("copy_attempts", [])
    system.setdefault("foreknowledge", {
        "remembered": [], "confirmed": [], "changed": [], "suspected_hidden_conditions": [],
        "spent_exploits": [],
    })
    system.setdefault("rivals", [
        {"name": "Leading public guild", "floor": max(0, floor - 1), "level": max(1, _number(state.get("level"), 1) - 2), "influence": 10, "current_goal": "Secure the next public first clear"},
        {"name": "Independent challenger", "floor": max(0, floor - 1), "level": max(1, _number(state.get("level"), 1) - 1), "influence": 4, "current_goal": "Find an overlooked hidden reward"},
    ])
    system.setdefault("party_roles", [])
    system.setdefault("floor_history", [])
    system.setdefault("achievement_chains", {})
    system.setdefault("artifact_index", [])
    system.setdefault("system_notifications", [])
    system.setdefault("build_synergies", [])
    return system


def initialize_lit_systems(state):
    if not isinstance(state, dict):
        return []
    world = state.get("world")
    if world == "Overgeared":
        existed = isinstance(state.get("overgeared_system"), dict) and bool(state.get("overgeared_system"))
        _seed_overgeared(state)
        return [] if existed else ["Initialized Satisfy simulation records"]
    if world == "Solo Max-Level Newbie":
        existed = isinstance(state.get("solo_system"), dict) and bool(state.get("solo_system"))
        _seed_solo(state)
        return [] if existed else ["Initialized Tower simulation records"]
    return []


def _overgeared_turn(before, state, action_text, narrative, elapsed_minutes):
    system = _seed_overgeared(state)
    special = state["special"]
    profile = special["Satisfy Profile"]
    starter = starter_kit_for(str(profile.get("starting_role") or special.get("Archetype") or "Adventurer"))
    notes = []
    days = max(1 / 24, max(1, _number(elapsed_minutes, 5)) / 1440)

    if CRAFT_RE.search(action_text):
        track_name = _production_path_for_text(action_text)
        track = system["production_paths"].setdefault(track_name, {"mastery": 0, "rank": "Beginner", "progress": 0})
        gain = max(1, round(days * (3 + max(1, _number(state.get("level"), 1)) ** .35)))
        track["mastery"] = _number(track.get("mastery"), 0) + gain
        track["progress"] = _number(track.get("progress"), 0) + gain
        track["rank"] = _production_rank(track["mastery"])
        profile["crafting_mastery"] = max(_number(profile.get("crafting_mastery"), 0), track["mastery"])
        special["Crafting Mastery"] = profile["crafting_mastery"]
        system["crafting_history"].append({
            "turn": _number(state.get("turn"), 0) + 1, "focus": track_name,
            "elapsed_days": round(days, 2), "mastery_gain": gain,
            "summary": "The Chronicle contains the actual materials, method, failures, and finished result.",
        })
        notes.append(f"[PRODUCTION]\n{track_name} proficiency increased: Mastery +{gain} → {track['mastery']} ({track['rank']}). Materials and routine components remain in the Chronicle.")
        for order in system["crafting_orders"]:
            if str(order.get("status")) == "Active":
                order["progress"] = min(100, _number(order.get("progress"), 0) + max(5, round(days * 18)))
                if order["progress"] >= 100:
                    order["status"] = "Ready for delivery"
                    notes.append(f"[Commission complete]\n[{order.get('name', 'Crafting commission')}] can now be delivered through the story.")

    if re.search(r"\b(?:accept|take|begin|start)\b.{0,35}\b(?:commission|crafting order|production order)\b", action_text, re.I):
        if not any(str(x.get("status")) == "Active" for x in system["crafting_orders"] if isinstance(x, dict)):
            system["crafting_orders"].append({
                "name": "Narrative Crafting Commission", "client": "Established through the Chronicle",
                "requirements": action_text[:300], "deadline": "As established in the scene",
                "reward": "As negotiated in the Chronicle", "progress": 0, "status": "Active",
            })
            notes.append("[New commission registered]\nIts materials, specifications, deadline, and payment remain governed by the Chronicle.")

    class_type = str(profile.get("class_type") or system["class_progression"].get("class_type") or "Adventuring / Flexible")
    reception = system.setdefault("class_reception", {})
    awaiting_class = str(reception.get("status") or "").lower() == "pending"
    if awaiting_class and re.search(r"\b(?:class|job|profession|trainer|master|quest|trial|achievement|hidden condition|class change)\b", action_text, re.I):
        old_progress = _number(reception.get("opportunity_progress"), 0)
        gain = max(2, round(days * 4))
        reception["opportunity_progress"] = min(100, old_progress + gain)
        reception["last_evidence"] = str(action_text)[:240]
        reception["preferred_route"] = str(reception.get("preferred_route") or special.get("Archetype") or "Adventurer")
        if old_progress < 25 <= reception["opportunity_progress"]:
            notes.append(f"[Class opportunity]\nYour actions have begun revealing a possible {reception['preferred_route']} class-change route. The actual class and conditions will be established through the Chronicle.")
    if (CLASS_RE.search(action_text) or _class_action_aligned(class_type, action_text)) and not awaiting_class:
        cp = system["class_progression"]
        gain = max(1, round(days * (5 if CLASS_RE.search(action_text) else 3)))
        cp["stage_progress"] = min(100, _number(cp.get("stage_progress"), 0) + gain)
        role = system["role_development"]
        role["aligned_actions"] = _number(role.get("aligned_actions"), 0) + 1
        role["contribution_actions"] = _number(role.get("contribution_actions"), 0) + 1
        role.setdefault("recent_growth", []).append({"turn": _number(state.get("turn"), 0) + 1, "class_type": class_type, "progress": gain, "action": str(action_text)[:180]})
        role["recent_growth"] = role["recent_growth"][-20:]
        route = _behavior_route(action_text)
        behavior = system["class_behavior"]
        behavior["routes"][route] = _number(behavior["routes"].get(route), 0) + gain
        behavior["evidence"] = [*behavior.get("evidence", []), {"turn":_number(state.get("turn"),0)+1,"route":route,"action":str(action_text)[:180]}][-30:]
        for quest in list(system["class_questlines"]):
            if quest.get("status") == "Active":
                quest["progress"] = min(100, _number(quest.get("progress"), 0) + gain)
                if quest["progress"] >= 100:
                    quest["status"] = "Milestone reached"
                    old_stage = str(cp.get("stage") or "Foundation")
                    cp["stage"] = "Specialization" if old_stage == "Foundation" else "Evolved"
                    dominant = max(behavior["routes"], key=behavior["routes"].get, default="Adaptive")
                    if cp["stage"] == "Specialization":
                        specialization = f"{dominant} Route"
                        if specialization not in profile.setdefault("specializations", []):
                            profile["specializations"].append(specialization)
                        cp.setdefault("unlocked_features", []).append(specialization)
                        legacy_specialization = (_list(starter.get("advancements")) or [None])[0]
                        if legacy_specialization and legacy_specialization not in profile["specializations"]:
                            profile["specializations"].append(legacy_specialization)
                    elif cp["stage"] == "Evolved":
                        base_class = str(cp.get("class") or profile.get("primary_class") or "Adventurer")
                        legacy_evolution = (_list(starter.get("advancements")) + [None, None])[1]
                        evolved = legacy_evolution or (f"{dominant} {base_class}" if not base_class.startswith(dominant) else base_class)
                        cp.update({"class": evolved, "stage": "Evolved", "stage_progress": 0,
                                   "next_unlock": "Develop the evolved class through high-level achievements and unique conditions."})
                        profile["primary_class"] = evolved
                        special["Class"] = evolved
                    role.setdefault("major_achievements", []).append(quest["name"])
                    next_name = f"{cp['class']} Specialization Trial" if cp["stage"] == "Specialization" else f"{cp['class']} Evolution Trial"
                    system["class_questlines"].append({"name": next_name, "class": cp["class"], "stage": cp["stage"],
                        "progress": 0, "goal": "Complete a defining class-aligned achievement that changes how the role is played.",
                        "next_unlock": "An earned specialization or class evolution", "status": "Active"})
                    notice = f"[Class quest complete]\n[{quest['name']}] has been completed. A new class quest, [{next_name}], is now available."
                    notes.append(notice)
                    system["system_notifications"].append({"turn": _number(state.get("turn"), 0) + 1, "type": "class", "message": notice})

    # Contracted companions are persistent actors, not flavor attached to the
    # Summoner label. Coordinated work improves the bond and their own level.
    for name, contract in system.get("companion_contracts", {}).items():
        if name.lower() in action_text.lower() or re.search(r"\b(?:companion|summon|contract|beast|pet)\b", action_text, re.I):
            gain = max(1, min(8, round(days * 2)))
            contract["loyalty"] = min(100, _number(contract.get("loyalty"), 40) + gain)
            contract["shared_actions"] = _number(contract.get("shared_actions"), 0) + 1
            if contract["shared_actions"] % 5 == 0:
                contract["level"] = _number(contract.get("level"), 1) + 1
                notice = f"[Contracted companion level up]\n[{name}] has reached level {contract['level']} through shared field experience."
                notes.append(notice)
                system["system_notifications"].append({"turn": _number(state.get("turn"), 0) + 1, "type": "companion", "message": notice})
            for companion in state.get("companions", []):
                if isinstance(companion, dict) and companion.get("name") == name:
                    companion.update(copy.deepcopy(contract))

    # Mirror player-facing affinity from already-authoritative relationship facts.
    relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    for name, raw in relationships.items():
        score = _number(raw.get("score", raw.get("trust", 0)) if isinstance(raw, dict) else raw, 0)
        label = "Hostile" if score <= -40 else "Wary" if score < 0 else "Acquainted" if score < 25 else "Trusted" if score < 60 else "Devoted"
        system["npc_affinity"][name] = {"score": max(-100, min(100, score)), "tier": label,
            "next_unlock": "A personal quest, commercial privilege, training route, or political favor earned through further trust."}
        prior = ((before or {}).get("relationships") or {}).get(name, 0)
        prior_score = _number(prior.get("score", prior.get("trust", 0)) if isinstance(prior, dict) else prior, 0)
        if score != prior_score:
            reason = raw.get("reason") if isinstance(raw, dict) else "Relationship changed through the latest shared event"
            system["affinity_history"].setdefault(name, []).append({"turn":_number(state.get("turn"),0)+1,"before":prior_score,"after":score,"reason":reason})
            system["affinity_history"][name] = system["affinity_history"][name][-30:]
    profile["npc_affinity"] = copy.deepcopy(system["npc_affinity"])
    special["NPC Affinity"] = copy.deepcopy(system["npc_affinity"])

    active_aff = next((x for x in state.get("affiliations", []) if isinstance(x, dict) and x.get("status", "active") == "active" and "guild" in str(x.get("faction", "")).lower()), None)
    if active_aff:
        system["guild"].update(name=active_aff.get("faction"), rank=active_aff.get("rank", "Member"))
    elif str(profile.get("guild") or "None") != "None":
        system["guild"]["name"] = profile.get("guild")
    profile["guild"] = system["guild"]["name"]
    special["Guild"] = system["guild"]["name"]
    if GUILD_RE.search(action_text):
        system["guild"]["resources"] = max(0, _number(system["guild"].get("resources"), 0) + round(days * 3))

    memorable = [x for x in state.get("inventory", []) if memorable_item(x)]
    for item in memorable:
        name = _text(item)
        if not name: continue
        detail = item if isinstance(item, dict) else {}
        legacy = system["equipment_legacies"].setdefault(name, {"name":name,"acquired_turn":_number(state.get("turn"),0),"history":[],"ownership_disputes":[],"upgrades":[],"class_synergy":[]})
        legacy["rating"] = item_rating(item); legacy["source"] = detail.get("source", legacy.get("source","Chronicle"))
        legacy["class_synergy"] = _list(detail.get("synergy") or detail.get("class_synergy") or legacy.get("class_synergy"))
        if name.lower() in action_text.lower():
            legacy["history"] = [*legacy.get("history", []), {"turn":_number(state.get("turn"),0)+1,"event":str(narrative or action_text)[:240]}][-30:]
        if re.search(rf"\b(?:upgrade|enhance|reforge|repair)\b.{{0,80}}{re.escape(name)}", action_text, re.I):
            legacy["upgrades"] = [*legacy.get("upgrades", []), {"turn":_number(state.get("turn"),0)+1,"change":str(narrative or action_text)[:220]}][-20:]
    best_rating = max((ITEM_RATING_ORDER.get(item_rating(x).lower(), 0) for x in memorable), default=0)
    mastery = _number(profile.get("crafting_mastery"), 0)
    level = _number(state.get("level"), 1)
    affinity_peak = max((_number(x.get("score"), 0) for x in system["npc_affinity"].values()), default=0)
    system["rankings"] = {
        "Combat standing": {"score": level * 10 + max(state.get("stats", {}).values(), default=0), "band": "Rising" if level >= 20 else "Developing"},
        "Class standing": {"score": level * 10 + _number(system["class_progression"].get("stage_progress"), 0), "band": str(system["class_progression"].get("stage", "Foundation"))},
        "Adventure standing": {"score": level * 8 + _number(system["role_development"].get("aligned_actions"), 0) * 2, "band": "Recognized" if level >= 20 else "Developing"},
        "NPC reputation": {"score": affinity_peak, "band": "Recognized" if affinity_peak >= 25 else "Unknown"},
        "Guild influence": {"score": _number(system["guild"].get("resources"), 0), "band": "Independent" if system["guild"].get("name") == "None" else "Affiliated"},
    }
    if _production_relevant(profile, special, state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}):
        system["rankings"]["Production standing"] = {"score": mastery + best_rating * 100, "band": _production_rank(mastery)}
    currency = state.get("currency") if isinstance(state.get("currency"), dict) else {}
    before_currency = (before or {}).get("currency") if isinstance((before or {}).get("currency"), dict) else {}
    system["economy"] = {
        "personal_gold": _number(currency.get("amount"), 0),
        "change_this_turn": _number(currency.get("amount"), 0) - _number(before_currency.get("amount"), _number(currency.get("amount"), 0)),
        "memorable_items": len(memorable), "workshop_income": _number(system["economy"].get("workshop_income"), 0),
        "guild_funds": _number(system["guild"].get("resources"), 0),
        "territory_revenue": _number(system["economy"].get("territory_revenue"), 0),
        "important_effects": _list(system["economy"].get("important_effects")),
    }
    if re.search(r"\b(?:major contract|guild resource|exclusive item|legendary item|market|auction|trade agreement|army equipment)\b", f"{action_text} {narrative}", re.I):
        effect = {"turn":_number(state.get("turn"),0)+1,"cause":str(action_text)[:180],"effect":str(narrative)[:220] or "The important transaction changed reputation, supply, or political leverage."}
        system["economy"]["important_effects"] = [*system["economy"].get("important_effects", []), effect][-30:]
    for rival in system.get("ranking_ecosystem", []):
        rival["rank_score"] = _number(rival.get("rank_score"), 0) + max(0, int(days // 2))
        if days >= 7:
            rival["trend"] = "Rising" if rival.get("kind") == "Player" or _number(rival.get("rank_score"),0) < 150 else "Stable"
    system["crafting_history"] = system["crafting_history"][-100:]
    system["system_notifications"] = system["system_notifications"][-80:]
    return notes


def _solo_turn(before, state, action_text, narrative, elapsed_minutes):
    system = _seed_solo(state)
    special = state["special"]
    profile = special["System Profile"]
    notes = []
    floor_state = system["floor_state"]
    days = max(1 / 24, max(1, _number(elapsed_minutes, 5)) / 1440)

    if SOLO_INSPECT_RE.search(action_text):
        clue = next((x for x in floor_state.get("hidden_conditions", []) if not x.get("discovered")), None)
        if clue:
            clue["discovered"] = True
            system["foreknowledge"]["suspected_hidden_conditions"].append({"floor": floor_state["floor"], "clue": clue["clue"], "status": "Suspected"})
            notes.append(f"[HIDDEN-CONDITION CLUE]\n{clue['clue']}")

    if re.search(r"\b(?:remember|recall|compare|game knowledge|foreknowledge)\b", action_text, re.I):
        entry = {"floor": floor_state["floor"], "fact": action_text[:300], "status": "Remembered; not yet confirmed"}
        if entry["fact"] not in {x.get("fact") for x in system["foreknowledge"]["remembered"] if isinstance(x, dict)}:
            system["foreknowledge"]["remembered"].append(entry)
        notes.append("[Foreknowledge recorded]\nThe remembered route remains provisional until observed in the Tower's lethal reality.")

    if re.search(r"\b(?:confirm|verify|test|compare)\b", action_text, re.I) and system["foreknowledge"].get("remembered"):
        remembered = system["foreknowledge"]["remembered"][-1]
        changed = bool(re.search(r"\b(?:different|changed|no longer|diverged|wrong|unexpected)\b", str(narrative), re.I))
        record = copy.deepcopy(remembered)
        record.update(status="Changed by the living Tower" if changed else "Confirmed in present reality", evidence=str(narrative)[:260])
        target = "changed" if changed else "confirmed"
        system["foreknowledge"][target].append(record)
        notes.append(f"[FOREKNOWLEDGE {target.upper()}]\n{record.get('fact', 'The remembered route')} — {record['status']}.")

    if SOLO_COPY_RE.search(action_text):
        target_match = re.search(r"(?:copy|steal|replicate|acquire)\s+(?:the\s+)?([^.;]{2,80}?)(?:\s+(?:skill|ability|power|technique)|$)", action_text, re.I)
        target = target_match.group(1).strip() if target_match else "Ability described in the current scene"
        attempt = {"target": target, "condition": "Observe the ability and discover its unique System condition", "missing_conditions":["Exact trigger not yet confirmed"], "capacity_cost":"Unknown until analyzed", "target_awareness":"Unknown", "progress": 10,
                   "evidence": action_text[:300], "status": "Investigating"}
        system["copy_attempts"].append(attempt)
        notes.append("[Ability-copy condition detected]\nThe attempt is being tracked, but the System's exact condition still has to be discovered and fulfilled.")

    admin = floor_state.get("administrator", {})
    if re.search(r"\b(?:loophole|wording|technicality|alternate clear|outsmart)\b", result_text := f"{action_text} {narrative}", re.I):
        admin["disposition"] = min(100, _number(admin.get("disposition"), 0) + 5)
        admin["loopholes_found"] = _number(admin.get("loopholes_found"), 0) + 1
        admin.setdefault("player_history", []).append({"turn":_number(state.get("turn"),0)+1,"reaction":"Recognized an earned loophole"})
        notes.append(f"[ADMINISTRATOR REACTION]\n{admin.get('name')} noticed the player's interpretation of the rules.")
    elif re.search(r"\b(?:break the rules|cheat the administrator|ignore the scenario)\b", result_text, re.I):
        admin["disposition"] = max(-100, _number(admin.get("disposition"), 0) - 6)
        admin.setdefault("player_history", []).append({"turn":_number(state.get("turn"),0)+1,"reaction":"Disapproved of an unsupported rules violation"})

    old_floor = max(1, _number((before or {}).get("tower_floor"), floor_state["floor"]))
    new_floor = max(1, _number(state.get("tower_floor"), floor_state["floor"]))
    if new_floor > old_floor:
        old_state = copy.deepcopy(
            ((before or {}).get("solo_system") or {}).get("floor_state")
            if isinstance((before or {}).get("solo_system"), dict) else None
        )
        if not isinstance(old_state, dict) or _number(old_state.get("floor"), 0) != old_floor:
            old_state = build_floor_state(old_floor)
        old_state["status"] = "Cleared"
        old_state["boss"]["defeated"] = True
        gained_achievements = [_achievement_name(x) for x in state.get("achievements", []) if _achievement_name(x) not in {_achievement_name(y) for y in (before or {}).get("achievements", [])}]
        gained_items = [_text(x) for x in state.get("inventory", []) if _text(x).lower() not in {_text(y).lower() for y in (before or {}).get("inventory", [])}]
        xp_gained = sum(
            max(0, _number(entry.get("xp_awarded"), 0))
            for entry in (state.get("progression_log", []) or [])
            if isinstance(entry, dict) and entry.get("type") == "xp"
            and _number(entry.get("turn"), 0) > _number((before or {}).get("turn"), 0)
        )
        prior_titles = {_text(title).lower() for title in (before or {}).get("titles", []) if _text(title)}
        gained_titles = [_text(title) for title in state.get("titles", [])
                         if _text(title) and _text(title).lower() not in prior_titles]
        report = {
            "floor": old_floor, "name": old_state.get("name"), "time_spent_days": round(days, 2),
            "main_objective": old_state.get("clear_condition"),
            "hidden_completed": [x["name"] for x in old_state.get("hidden_conditions", []) if x.get("completed")],
            "hidden_missed": [x["name"] for x in old_state.get("hidden_conditions", []) if not x.get("completed")],
            "xp_gained": xp_gained,
            "levels_gained": max(0, _number(state.get("level"), 1) - _number((before or {}).get("level"), 1)),
            "achievements": gained_achievements, "titles": gained_titles, "items": gained_items,
            "party_changes": [], "rival_snapshot": copy.deepcopy(system.get("rivals", [])),
            "earth_consequence": "The public ranking and organizations react according to how visible the clear was.",
        }
        system["floor_history"].append(report)
        system["floor_state"] = build_floor_state(new_floor)
        system["floor_state"]["started_turn"] = _number(state.get("turn"), 0) + 1
        floor_state = system["floor_state"]
        notes.append(f"[Floor {old_floor} cleared]\nAccess to Floor {new_floor} has opened. Hidden conditions completed: {len(report['hidden_completed'])}. Missed or undiscovered: {len(report['hidden_missed'])}.")

    # Rival groups move without requiring another model call, but never jump
    # beyond the player during a short routine turn.
    for rival in system["rivals"]:
        rival["level"] = max(1, _number(rival.get("level"), 1) + int(days // 3))
        if days >= 2 and _number(rival.get("floor"), 0) < max(1, new_floor):
            rival["floor"] = min(max(1, new_floor), _number(rival.get("floor"), 0) + max(1, int(days // 5)))
        rival["influence"] = _number(rival.get("influence"), 0) + int(days)

    roles = []
    for companion in state.get("companions", []):
        if isinstance(companion, dict):
            role = companion.get("role") or companion.get("archetype") or "Flexible support"
            roles.append({"name": companion.get("name", "Companion"), "role": role,
                          "contribution": companion.get("notes") or f"Contributes through {role}."})
    system["party_roles"] = roles

    artifacts = []
    for item in state.get("inventory", []):
        if isinstance(item, dict) and (item.get("artifact") or "artifact" in str(item.get("category", "")).lower()):
            artifacts.append({
                "name": _text(item), "grade": item_rating(item), "slot": item.get("slot", "Unassigned"),
                "main_effect": _list(item.get("effects") or item.get("effect")),
                "conditional_effect": item.get("conditional_effect", "None discovered"),
                "set": item.get("set", "None"), "upgrade_route": item.get("upgrade_route", "Unknown"),
                "binding": item.get("binding", "Unbound"), "provenance": item.get("source", "Unknown"),
            })
    system["artifact_index"] = artifacts

    achievements = [_achievement_name(x) for x in state.get("achievements", []) if _achievement_name(x)]
    for name in achievements:
        chain_key = "Scenario Defiance" if re.search(r"hidden|condition|defy|untouched|bloodless", name, re.I) else "Tower Conquest"
        chain = system["achievement_chains"].setdefault(chain_key, {"earned": [], "next": "Complete a related higher-risk condition", "tier": 0})
        if name not in chain["earned"]:
            chain["earned"].append(name)
            chain["tier"] = len(chain["earned"])

    copied = [_normalize_copy(x) for x in _list(profile.get("copied_abilities", []))]
    copied = [x for x in copied if x]
    profile["copied_abilities"] = copied
    special["Copied Abilities"] = copy.deepcopy(copied)
    # Explain real combinations instead of leaving the player to infer them
    # from three unrelated lists.
    titles = [_achievement_name(x) for x in state.get("titles", []) if _achievement_name(x)]
    artifacts_by_name = [row.get("name") for row in system.get("artifact_index", []) if isinstance(row, dict) and row.get("name")]
    skill_names = list((state.get("skills") or {}).keys())
    synergies = []
    if copied and skill_names:
        synergies.append({"name":f"{copied[0]['name']} + {skill_names[0]}","components":[copied[0]["name"],skill_names[0]],"effect":"The copied effect can create an opening or condition for the established skill; actual limits and costs still apply."})
    if artifacts_by_name and titles:
        synergies.append({"name":f"{artifacts_by_name[0]} + {titles[0]}","components":[artifacts_by_name[0],titles[0]],"effect":"The artifact's conditional effect is reinforced when the title's earned condition is relevant."})
    system["build_synergies"] = synergies[:8]
    profile["build_synergies"] = copy.deepcopy(system["build_synergies"])

    # Canon-shaped System notifications are deduplicated local facts rather
    # than another model request.
    notifications = system.setdefault("system_notifications", [])
    old_level, new_level = _number((before or {}).get("level"), 1), _number(state.get("level"), 1)
    old_xp, new_xp = _number((before or {}).get("xp"), 0), _number(state.get("xp"), 0)
    if new_xp != old_xp: notifications.append({"turn":_number(state.get("turn"),0)+1,"type":"xp","message":f"Experience changed: {old_xp} → {new_xp}"})
    if new_level > old_level: notifications.append({"turn":_number(state.get("turn"),0)+1,"type":"level","message":f"LEVEL UP — {old_level} → {new_level}"})
    old_titles = {_achievement_name(x).casefold() for x in (before or {}).get("titles", []) if _achievement_name(x)}
    for title in titles:
        if title.casefold() not in old_titles: notifications.append({"turn":_number(state.get("turn"),0)+1,"type":"title","message":f"New title acquired: {title}"})
    old_achievements = {_achievement_name(x).casefold() for x in (before or {}).get("achievements", []) if _achievement_name(x)}
    for achievement in achievements:
        if achievement.casefold() not in old_achievements: notifications.append({"turn":_number(state.get("turn"),0)+1,"type":"achievement","message":f"Achievement unlocked: {achievement}"})
    seen_notice, deduped = set(), []
    for notice in notifications:
        key = (notice.get("type"), notice.get("message"))
        if key in seen_notice: continue
        seen_notice.add(key); deduped.append(notice)
    system["system_notifications"] = deduped[-100:]
    system["copy_attempts"] = system["copy_attempts"][-30:]
    system["floor_history"] = system["floor_history"][-50:]
    system["foreknowledge"] = {k: _list(v)[-100:] for k, v in system["foreknowledge"].items()}
    return notes


def process_lit_turn(before, state, actions=None, narrative="", elapsed_minutes=5):
    """Advance zero-cost setting records and return Chronicle-ready notes."""
    initialize_lit_systems(state)
    inventory_result = normalize_memorable_inventory(state, before)
    action_text = "\n".join(str(x) for x in (actions or []) if str(x).strip())
    if state.get("world") == "Overgeared":
        notes = _overgeared_turn(before or {}, state, action_text, narrative, elapsed_minutes)
    elif state.get("world") == "Solo Max-Level Newbie":
        notes = _solo_turn(before or {}, state, action_text, narrative, elapsed_minutes)
    else:
        notes = []
    if inventory_result["removed_materials"]:
        notes.append("[MATERIALS]\nRoutine ingredients and components were handled narratively and kept out of the Bag.")
    if inventory_result["memorable_items"]:
        notes.append("[Bag updated]\n" + ", ".join(inventory_result["memorable_items"][:6]))
    return notes
