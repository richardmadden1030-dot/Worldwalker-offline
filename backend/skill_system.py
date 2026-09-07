"""Shared skill taxonomy and backward-compatible metadata inference.

The GM may author rich metadata, but old saves and smaller models often only
provide a name and description.  This module gives every skill one stable,
mechanically meaningful interpretation without making an AI call.
"""
import copy
import re

from util import clamp


SKILL_CATEGORIES = (
    "offense", "defense", "healing", "support", "control", "mobility",
    "detection", "stealth", "summon", "transformation", "crafting",
    "knowledge", "social", "utility",
)
EFFECT_TYPES = (
    "damage", "heal", "buff", "debuff", "shield", "cleanse", "control",
    "summon", "movement", "detect", "stealth", "transform", "utility",
)
TARGET_TYPES = ("enemy", "enemies", "self", "ally", "allies", "area", "environment")

_NONCOMBAT = re.compile(
    r"\b(navigat|chart|craft|smith|cook|merchant|account|history|research|language|"
    r"lore|apprais|diplom|negot|leadership|profession|trade|fundamentals expected of this role)\b"
)
_COMBAT = re.compile(
    r"\b(attack|strike|kick|punch|combat|fight|weapon|jutsu|spell|blast|projectile|trap|bind|stun|"
    r"heal|restore|shield|barrier|guard|weaken|poison|haki|nen|chakra pulse|damage|sword|"
    r"blade|cut|zanjutsu|hakuda|shikai|bankai|had[ōo]|bakud[ōo]|summon|transform|"
    r"teleport|dash|sense|detect|stealth|invisible|cleanse|purif|buff|empower)\b"
)


def _blob(name, detail):
    if isinstance(detail, dict):
        pieces = [name, detail.get("description"), detail.get("effect"), detail.get("use"),
                  detail.get("activation"), detail.get("limitations")]
    else:
        pieces = [name, detail]
    return " ".join(str(piece or "") for piece in pieces).lower()


def _inferred_effect(blob):
    rules = (
        ("cleanse", r"\b(cleanse|purif\w*|remove (?:a )?(?:negative )?(?:status|effect)|cure poison|dispel)\b"),
        ("heal", r"\b(heal|healing|restore hp|mend wounds?|regenerat|recovery technique)\b"),
        ("shield", r"\b(shield|barrier|ward|protective field|damage absorption)\b"),
        ("summon", r"\b(summon|familiar|construct|companion|clone army|minion)\b"),
        ("transform", r"\b(transform|transformation|release form|mode|awakening|shikai|bankai)\b"),
        ("stealth", r"\b(stealth|invisib\w*|conceal\w*|camouflage|hide presence|suppress presence)\b"),
        ("detect", r"\b(detect|sense|track|scan|perception|true sight|clairvoy)\b"),
        ("movement", r"\b(dash|teleport|flash step|shunpo|mobility|movement|flight|blink|escape)\b"),
        ("control", r"\b(stun\w*|bind\w*|paraly\w*|sleep\w*|freez\w*|immobil\w*|silenc\w*|confus\w*|fear\w*|restrain\w*|crowd control|bakud[ōo])\b"),
        ("debuff", r"\b(debuff|weaken|slow|poison|burn|bleed|blind|curse|mark|drain|reduce)\b"),
        ("buff", r"\b(buff|empower|enhance|strengthen|haste|increas(?:e|es) (?:power|speed|defense)|inspiration|aura)\b"),
        ("damage", r"\b(attack|strike|kick|punch|damage|blast|projectile|slash|cut|pierc|crush|explod|fireball|had[ōo])\b"),
    )
    for effect, pattern in rules:
        if re.search(pattern, blob):
            return effect
    return "utility"


def _category_for(effect, blob):
    direct = {
        "damage": "offense", "heal": "healing", "buff": "support",
        "debuff": "control", "shield": "defense", "cleanse": "support",
        "control": "control", "summon": "summon", "movement": "mobility",
        "detect": "detection", "stealth": "stealth", "transform": "transformation",
    }
    if effect in direct:
        return direct[effect]
    if re.search(r"\b(craft|smith|forge|cook|alchemy)\b", blob):
        return "crafting"
    if re.search(r"\b(knowledge|research|history|lore|language|apprais)\b", blob):
        return "knowledge"
    if re.search(r"\b(diplom|negot|persuad|leadership|deception|intimidat)\b", blob):
        return "social"
    return "utility"


def _default_target(effect, blob):
    if re.search(r"\b(all enemies|wide area|area of effect|aoe|everyone nearby)\b", blob):
        return "enemies"
    if effect in ("damage", "debuff", "control", "detect"):
        return "enemy"
    if effect in ("heal", "buff", "shield", "cleanse", "movement", "stealth", "transform"):
        return "self"
    if effect == "summon":
        return "area"
    return "environment"


def _default_status(effect, blob):
    names = (
        ("Stunned", r"\bstun"), ("Bound", r"\bbind|restrain|immobil"),
        ("Paralyzed", r"\bparaly"), ("Asleep", r"\bsleep"),
        ("Frozen", r"\bfreez|frozen"), ("Silenced", r"\bsilenc"),
        ("Blinded", r"\bblind"), ("Slowed", r"\bslow"),
        ("Poisoned", r"\bpoison"), ("Burning", r"\bburn|flame|fire"),
        ("Bleeding", r"\bbleed"), ("Afraid", r"\bfear"),
        ("Confused", r"\bconfus"), ("Marked", r"\bmark"),
    )
    for name, pattern in names:
        if re.search(pattern, blob):
            return name
    return {"control": "Controlled", "debuff": "Weakened", "buff": "Empowered",
            "stealth": "Concealed", "transform": "Transformed", "detect": "Analyzed"}.get(effect)


def infer_skill_metadata(name, detail=None):
    """Return complete metadata while respecting any valid explicit fields."""
    explicit = detail if isinstance(detail, dict) else {}
    blob = _blob(name, detail)
    authored_effect = str(explicit.get("effect_type", "")).strip().lower()
    effect = authored_effect
    if effect not in EFFECT_TYPES:
        effect = _inferred_effect(blob)
    elif effect == "utility":
        # Early versions used "utility" as the catch-all for every
        # non-damage combat skill. Upgrade those legacy records when the
        # prose clearly identifies a richer effect.
        inferred = _inferred_effect(blob)
        if inferred != "utility":
            effect = inferred
    upgraded_legacy_utility = authored_effect == "utility" and effect != "utility"
    category = str(explicit.get("category", "")).strip().lower()
    if category not in SKILL_CATEGORIES or (upgraded_legacy_utility and category == "utility"):
        category = _category_for(effect, blob)
    target = str(explicit.get("target_type", explicit.get("target", ""))).strip().lower()
    if target not in TARGET_TYPES:
        target = _default_target(effect, blob)

    combat_usable = explicit.get("combat_usable")
    if not isinstance(combat_usable, bool) or (upgraded_legacy_utility and combat_usable is False):
        combat_usable = effect != "utility" or bool(_COMBAT.search(blob))
        if effect == "utility" and _NONCOMBAT.search(blob) and not _COMBAT.search(blob):
            combat_usable = False

    duration = explicit.get("duration_rounds", 0)
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0
    if effect in ("buff", "debuff", "control", "stealth", "transform", "detect") and duration <= 0:
        duration = 3
    duration = clamp(duration, 0, 10)

    area = bool(explicit.get("area", target in ("enemies", "allies", "area")))
    status = str(explicit.get("status_effect", "") or "").strip() or _default_status(effect, blob)
    potency = explicit.get("status_potency", 20)
    try:
        potency = int(potency)
    except (TypeError, ValueError):
        potency = 20

    defaults = {
        "heal_pct": 20, "shield_pct": 20, "power_pct": 20,
        "defense_pct": 20, "speed_pct": 15, "damage_over_time_pct": 0,
    }
    mechanics = copy.deepcopy(explicit.get("mechanics", {})) if isinstance(explicit.get("mechanics"), dict) else {}
    for key, default in defaults.items():
        value = mechanics.get(key, explicit.get(key, default))
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        mechanics[key] = clamp(value, 0, 60 if key != "damage_over_time_pct" else 15)
    if not mechanics.get("damage_over_time_pct") and re.search(r"\b(poison|burn|bleed)\w*\b", blob):
        mechanics["damage_over_time_pct"] = 5

    return {
        "combat_usable": combat_usable,
        "category": category,
        "effect_type": effect,
        "target_type": target,
        "area": area,
        "duration_rounds": duration,
        "status_effect": status,
        "status_potency": clamp(potency, 0, 60),
        "mechanics": mechanics,
    }


def normalize_skill_detail(name, detail):
    """Copy one skill and add canonical metadata without discarding prose."""
    if isinstance(detail, dict):
        normalized = copy.deepcopy(detail)
    else:
        normalized = {"description": str(detail or "").strip()}
    meta = infer_skill_metadata(name, normalized)
    for key, value in meta.items():
        normalized[key] = value
    return normalized


def normalize_skill_map(skills):
    if not isinstance(skills, dict):
        return {}
    return {str(name): normalize_skill_detail(str(name), detail) for name, detail in skills.items()}


def _application_name(raw):
    if isinstance(raw, dict):
        return str(raw.get("name") or raw.get("title") or raw.get("ability") or raw.get("technique") or "").strip()
    return str(raw or "").strip()


def _application_snippet(name, detail):
    """Return only the sentence describing *name*, not the whole parent.

    Passing an umbrella ability's full prose to metadata inference makes a
    movement application look like a shield whenever the same paragraph also
    mentions a shield.  A sentence-sized snippet keeps every application's
    mechanics tied to its own words.
    """
    if not isinstance(detail, dict):
        return name
    values = []
    for key in ("description", "effect", "use", "activation", "limitation", "limitations", "cost", "drawback"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for value in values:
        parts = [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\s*;\s*", value) if part.strip()]
        found = next((part for part in parts if name.casefold() in part.casefold()), None)
        if found:
            return found[:700]
    return name


def extract_skill_applications(parent_name, detail):
    """Find established named moves inside an umbrella skill.

    Modern saves can store structured ``applications``.  Older/generated
    saves often list their moves only as emphasized names in the description
    or limits (``*Flame Flight*``, ``*Fiery Shield*``).  Both forms become
    selectable combat applications without adding duplicate Journal cards.
    """
    if not isinstance(detail, dict):
        return []
    found, seen = [], {str(parent_name).strip().casefold()}

    def add(raw):
        name = _application_name(raw).strip(" *_—–-:.")
        if not name or len(name) > 80 or len(name.split()) > 9 or name.casefold() in seen:
            return
        seen.add(name.casefold())
        if isinstance(raw, dict):
            app = copy.deepcopy(raw)
            app["name"] = name
        else:
            app = {"name": name, "description": _application_snippet(name, detail)}
        found.append(app)

    for key in ("applications", "developed_applications", "abilities", "techniques", "moves"):
        values = detail.get(key)
        if isinstance(values, dict):
            for name, value in values.items():
                app = copy.deepcopy(value) if isinstance(value, dict) else {"description": value}
                app["name"] = name
                add(app)
        elif isinstance(values, list):
            for value in values:
                add(value)

    prose = " ".join(str(detail.get(key) or "") for key in
                     ("description", "effect", "use", "activation", "limitation", "limitations", "cost", "drawback"))
    for match in re.finditer(r"(?<!\*)\*{1,2}([^*\n]{2,80}?)\*{1,2}(?!\*)", prose):
        add(match.group(1))
    return found[:24]


def build_combat_ability_options(skills):
    """Flatten learned skills and their named applications for combat UI.

    Keys are stable selection IDs.  Parent skill records remain untouched so
    the Journal stays clean; nested applications inherit the parent's rank,
    bonus and resource behavior while receiving their own inferred effect.
    """
    normalized = normalize_skill_map(skills)
    options = {}
    for parent_name, parent in normalized.items():
        if parent.get("combat_usable"):
            top = copy.deepcopy(parent)
            top.update({"id": parent_name, "name": parent_name, "parent_skill": parent_name})
            options[parent_name] = top
        for raw in extract_skill_applications(parent_name, parent):
            name = _application_name(raw)
            if not name:
                continue
            detail = copy.deepcopy(raw)
            detail.setdefault("description", _application_snippet(name, parent))
            for key in ("rank", "bonus", "resource_type", "growth_path", "origin"):
                if key not in detail and key in parent:
                    detail[key] = copy.deepcopy(parent[key])
            # Do not inherit a parent's effect/category: each named move has
            # its own (flight, shield, strike, etc.) mechanical purpose.
            detail.pop("effect_type", None)
            detail.pop("category", None)
            detail.pop("target_type", None)
            detail.pop("combat_usable", None)
            detail = normalize_skill_detail(name, detail)
            if not detail.get("combat_usable"):
                continue
            selection_id = f"{parent_name}::{name}"
            detail.update({"id": selection_id, "name": name, "parent_skill": parent_name})
            options[selection_id] = detail
    return options
