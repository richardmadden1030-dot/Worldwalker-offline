"""Jujutsu Kaisen creation and progression helpers.

The birth slot is deliberately exclusive: one innate technique OR one
Heavenly Restriction. Applications remain ordinary skills so they can be
trained, rolled and displayed without pretending each is a second technique.
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
import re


GRADES = ("Grade 4", "Grade 3", "Grade 2", "Grade 1", "Special Grade")
GRADE_BASELINES = {"Grade 4": 20, "Grade 3": 34, "Grade 2": 52, "Grade 1": 82, "Special Grade": 135}

CONCEPTS = (
    ("Threshold", "Imposes a chosen boundary between two measurable states", "Crossing the declared threshold triggers the stored change"),
    ("Afterimage Ledger", "Records the last movement made inside the user's cursed-energy field", "The recorded movement can be imposed once on a marked target"),
    ("Hollow Measure", "Removes a chosen quantity from one object and preserves it as an invisible measure", "The preserved quantity may be restored to a touched target"),
    ("Faultline Script", "Writes short cursed-energy seams into solid surfaces", "A seam redirects force along its written path when struck"),
    ("Borrowed Silence", "Collects sound that fails to reach the user", "Stored silence can erase a sound or erupt as compressed vibration"),
    ("Pale Orbit", "Binds small objects into cursed-energy orbits around a selected center", "Orbit speed and radius determine impact and defense"),
    ("Witness Mark", "A witnessed action leaves a temporary symbolic mark", "The user may strengthen, delay or interrupt that exact action once"),
    ("Mercy Debt", "Converts deliberately spared harm into cursed-energy credit", "The credit can reinforce protection or healing-like stabilization"),
)

# Generic JJK techniques are assembled from a governing subject, an operation,
# and an activation condition.  The old eight-entry CONCEPTS table remains as
# migration/reference material, but new original characters do not simply
# cycle through it.  This gives the duplicate archive thousands of coherent
# combinations to choose from before a technique ever reaches the player.
TECHNIQUE_THEMES = (
    {"key":"momentum", "keywords":("momentum", "kinetic", "impact", "motion"),
     "names":("Kinetic", "Impulse", "Vector", "Falling Star"),
     "subject":"momentum carried by movement and impact"},
    {"key":"space", "keywords":("space", "spatial", "distance", "boundary"),
     "names":("Threshold", "Parallax", "Nearside", "Horizon"),
     "subject":"distance and adjacency between marked points"},
    {"key":"sound", "keywords":("sound", "music", "voice", "vibration", "silence"),
     "names":("Resonant", "Mute", "Echo", "Hushed"),
     "subject":"sound and vibration inside the user's cursed-energy reach"},
    {"key":"shadow", "keywords":("shadow", "dark", "eclipse", "night"),
     "names":("Umbral", "Eclipsed", "Nightglass", "Black Lantern"),
     "subject":"the relationship between a body and its cast shadow"},
    {"key":"blood", "keywords":("blood", "wound", "scar", "vein"),
     "names":("Scarlet", "Vein", "Red", "Sanguine"),
     "subject":"cursed signatures carried by the user's willingly shed blood"},
    {"key":"memory", "keywords":("memory", "remember", "forget", "witness"),
     "names":("Witness", "Mnemonic", "Last Scene", "Recalled"),
     "subject":"the sensory memory of actions the user directly witnesses"},
    {"key":"heat", "keywords":("heat", "cold", "temperature", "flame", "ice"),
     "names":("Thermal", "Ashen", "Winter", "Cinder"),
     "subject":"heat transferred through cursed-energy contact"},
    {"key":"friction", "keywords":("friction", "traction", "slip", "grip"),
     "names":("Friction", "Slipstone", "Still Road", "Rough Current"),
     "subject":"friction between marked surfaces, bodies, and cursed constructs"},
    {"key":"weight", "keywords":("weight", "mass", "gravity", "heavy", "light"),
     "names":("Graven", "Ballast", "Weightless", "Iron Scale"),
     "subject":"effective weight borne by marked targets"},
    {"key":"reflection", "keywords":("mirror", "reflection", "glass", "light"),
     "names":("Mirror", "Glass", "Refraction", "Silver Image"),
     "subject":"reflections that contain a complete image of a target"},
    {"key":"direction", "keywords":("direction", "angle", "turn", "redirect"),
     "names":("Compass", "Crooked", "Turning", "Northless"),
     "subject":"direction carried by movement, force, and cursed-energy flow"},
    {"key":"attention", "keywords":("attention", "notice", "gaze", "seen", "focus"),
     "names":("Unseen", "Gaze", "Blind Audience", "Attention"),
     "subject":"attention consciously directed toward a person or action"},
)

TECHNIQUE_OPERATIONS = (
    {"title":("Ledger", "Archive", "Testament"),
     "rule":"Records one instance of {subject} when {condition}; the record can be imposed once on a valid marked target.",
     "application":"Spend a recorded instance of {subject} to repeat, redirect, or interrupt its original behavior."},
    {"title":("Partition", "Bisection", "Twin Seal"),
     "rule":"Divides {subject} into two linked portions when {condition}; a change applied to one portion is transferred to the other.",
     "application":"Split {subject} across two marks, then transfer one compatible change between them."},
    {"title":("Exchange", "Barter", "Equivalent Pact"),
     "rule":"Exchanges equal measured amounts of {subject} between two marked targets after {condition}.",
     "application":"Trade a measured amount of {subject} between two prepared targets without creating any from nothing."},
    {"title":("Reversal", "Countercurrent", "Inverse Law"),
     "rule":"Inverts the next valid change in {subject} after {condition}, turning increase into decrease or approach into separation.",
     "application":"Reverse one compatible change in {subject}; the technique cannot invert an unrelated property."},
    {"title":("Deferred Beat", "Afterclock", "Second Hand"),
     "rule":"Delays one change in {subject} after {condition}, preserving it until the user releases it or the short limit expires.",
     "application":"Suspend a compatible change in {subject}, then release it later with its original magnitude and direction intact."},
    {"title":("Measure", "Calibration", "Known Quantity"),
     "rule":"Measures {subject} when {condition} and declares that amount as a temporary cursed standard for later comparisons.",
     "application":"Compare a target against the stored standard and reinforce or suppress only the measured difference."},
    {"title":("Covenant", "Binding Script", "Rule Chain"),
     "rule":"Binds {subject} to one plainly declared rule when {condition}; breaking that rule triggers the stored consequence.",
     "application":"Write one narrow behavior for {subject} and trigger a proportional consequence if the marked target violates it."},
    {"title":("Accrual", "Compound Interest", "Gathering"),
     "rule":"Accumulates small changes in {subject} each time {condition}; the total may be released only through one compatible effect.",
     "application":"Build a reserve from repeated valid changes in {subject}, then spend it on one amplified expression of the same property."},
    {"title":("Compression", "Narrowing", "Singular Point"),
     "rule":"Compresses a distributed amount of {subject} toward one marked point after {condition}, increasing intensity while reducing area.",
     "application":"Concentrate existing {subject} into one smaller target or point; nothing unrelated is added to the effect."},
    {"title":("Relay", "Passing Rite", "Successor Mark"),
     "rule":"Passes an active change in {subject} from one marked target to the next when {condition}.",
     "application":"Move one compatible ongoing effect involving {subject} to another prepared target instead of strengthening it."},
)

TECHNIQUE_CONDITIONS = (
    "the user touches the target with cursed energy",
    "a target crosses a boundary the user drew",
    "the same action occurs twice within the user's sight",
    "the user correctly predicts the target's next movement",
    "a marked target breaks line of sight with the user",
    "the user accepts the same effect on their own body first",
    "the target acknowledges a short spoken condition",
    "the user maintains an unbroken hand sign for one breath",
    "two prepared marks enter the same cursed-energy field",
    "the user deliberately withholds an immediate counterattack",
)

RESTRICTION_NAMES = (
    "Iron Silence", "Narrow Gate", "Still Current", "Hollow Furnace",
    "Sealed Horizon", "Quiet Pulse", "Empty Circuit", "Stone Nerve",
)

CURSE_SOURCES = (
    ("Fear of abandonment", "a long-limbed figure with empty doorways opening across its body", "isolates targets and turns distance between allies into cursed pressure"),
    ("Fear of public humiliation", "a masked humanoid covered in staring glass eyes", "weaponizes attention, exposure and remembered embarrassment"),
    ("Fear of drowning", "a waterlogged shape whose outline drips upward", "creates crushing pressure and false currents without needing real water"),
    ("Fear of hospitals", "a pale stitched spirit trailing bent instrument-shadows", "distorts pain, diagnosis and the boundary between treatment and injury"),
    ("Fear of being forgotten", "a paper-thin spirit whose features vanish when unobserved", "erodes recognition, names and immediate memory"),
)

PROGRESSION_TRACKS = (
    "Reinforcement", "Energy Control", "Birth Slot Mastery", "Barrier Arts",
    "Reverse Cursed Technique", "Maximum Technique", "Domain Expansion", "Cursed Tool Mastery",
)

TRACK_PATTERNS = {
    "Reinforcement": re.compile(r"\b(reinforc|hand.to.hand|melee|physical|strength|speed|spar|combat drill)\w*", re.I),
    "Energy Control": re.compile(r"\b(cursed energy control|energy efficiency|output timing|ce control|aura control)\b", re.I),
    "Birth Slot Mastery": re.compile(r"\b(innate technique|cursed technique|technique application|heavenly restriction|birth slot|extension)\b", re.I),
    "Barrier Arts": re.compile(r"\b(barrier|curtain|simple domain|domain amplification)\b", re.I),
    "Reverse Cursed Technique": re.compile(r"\b(reverse cursed technique|reverse technique|positive energy|rct|heal(?:ing)? with cursed)\b", re.I),
    "Maximum Technique": re.compile(r"\b(maximum technique|maximum output|ultimate application)\b", re.I),
    "Domain Expansion": re.compile(r"\b(domain expansion|innate domain|sure.hit|barrier domain)\b", re.I),
    "Cursed Tool Mastery": re.compile(r"\b(cursed tool|weapon drill|weapon mastery|katana|staff|spear|blade)\b", re.I),
}

GRADE_ORDER = {name: index for index, name in enumerate(GRADES)}


def _rng(*parts):
    digest = hashlib.sha256("|".join(str(x or "") for x in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def is_curse_origin(origin):
    return "sentient cursed spirit" in str(origin or "").lower()


def normalized_grade(value, default="Grade 3"):
    text = str(value or "").strip().title()
    return text if text in GRADES else default


def generate_curse_identity(background, seed=""):
    text = str(background or "").strip()
    chooser = _rng(text, seed, "curse")
    source, form, instinct = chooser.choice(CURSE_SOURCES)
    explicit = re.search(r"(?:born from|curse of|fear of|fear surrounding)\s+([^,.;\n]{3,80})", text, re.I)
    if explicit:
        source = explicit.group(1).strip().rstrip(" ,")
    return {
        "source": source,
        "manifestation": form,
        "instinct": instinct,
        "temperament": "Self-aware; its choices can resist or embrace the instinct that created it.",
        "feeding_rule": "Killing any human can increase power. Victims with greater cursed energy grant exponentially more growth.",
    }


def _background_concept(background):
    text = str(background or "").lower()
    mappings = (
        (("shadow", "dark"), ("Eclipsed Interval", "Stores actions performed while the user is hidden from direct sight", "A stored action can repeat from the nearest connected shadow")),
        (("sound", "music", "voice"), ("Borrowed Silence", "Collects sound that fails to reach the user", "Stored silence can erase a sound or erupt as compressed vibration")),
        (("time", "delay"), ("Deferred Second", "Assigns a short delay to one touched transfer of force", "The delayed force resumes at the declared beat without changing its original direction")),
        (("memory", "forget"), ("Witness Mark", "A witnessed action leaves a temporary symbolic mark", "The user may strengthen, delay or interrupt that exact action once")),
        (("space", "spatial", "distance"), ("Threshold", "Imposes a chosen boundary between two measurable states", "Crossing the declared threshold triggers the stored change")),
        (("blood", "wound"), ("Red Testament", "Cursed energy records the shape and intent of blood the user willingly sheds", "Recorded blood becomes controllable seals, threads or projectiles")),
    )
    for words, concept in mappings:
        if any(word in text for word in words):
            return concept
    return None


def _procedural_technique(background, chooser):
    """Build one coherent original technique instead of selecting a finished
    ability from a short list.  Background words select a broad subject only;
    operation and condition remain generative unless the player explicitly
    authored the full governing rule (which CampaignMixin locks afterward)."""
    text = str(background or "").lower()
    matching = [theme for theme in TECHNIQUE_THEMES
                if any(keyword in text for keyword in theme["keywords"])]
    theme = chooser.choice(matching or list(TECHNIQUE_THEMES))
    operation = chooser.choice(TECHNIQUE_OPERATIONS)
    condition = chooser.choice(TECHNIQUE_CONDITIONS)
    name = f"{chooser.choice(theme['names'])} {chooser.choice(operation['title'])}"
    rule = operation["rule"].format(subject=theme["subject"], condition=condition)
    application = operation["application"].format(subject=theme["subject"])
    return name, rule, application


def _procedural_restriction(text, chooser, guarantee_strong=False):
    """Create a physical Heavenly Restriction with a real, variable exchange.
    Explicit zero-cursed-energy backgrounds still receive the canon-comparable
    complete exchange; vague starts vary in sacrifice, physical emphasis, and
    sensory payoff so rerolls are not renamed copies."""
    total_loss = bool(re.search(r"no cursed energy|zero cursed energy|complete heavenly restriction", text, re.I))
    total_loss = total_loss or (guarantee_strong and chooser.random() < .62)
    if total_loss:
        name = "Heavenly Restriction: Liberated Body"
        reserve_loss = output_loss = -999
        physical, speed, soul = 95, 80, 35
        sacrifice = "Cursed Energy Reserves and Output are effectively zero"
        enhancement = "An overwhelmingly enhanced body with extreme strength, speed, resilience, perception, and freedom from ordinary cursed-energy detection."
    else:
        name = f"Heavenly Restriction: {chooser.choice(RESTRICTION_NAMES)}"
        reserve_loss = -chooser.randint(24, 48)
        output_loss = -chooser.randint(18, 42)
        physical = chooser.randint(42, 72) + (18 if guarantee_strong else 0)
        speed = chooser.randint(34, 66) + (14 if guarantee_strong else 0)
        soul = chooser.randint(18, 42)
        sacrifice = f"Severely reduced cursed-energy reserves ({abs(reserve_loss)}) and output ({abs(output_loss)})"
        emphasis = chooser.choice(("explosive acceleration", "impact tolerance", "predatory perception", "fine motor precision", "sustained physical efficiency"))
        enhancement = f"An exceptional body emphasizing {emphasis}, backed by strength, speed, resilience, and curse perception beyond sorcerers of similar experience."
    return {
        "slot_type":"Heavenly Restriction", "name":name,
        "governing_rule":"Cursed-energy capacity is exchanged at birth for physical perception, strength, speed, resilience, and bodily efficiency.",
        "sacrifice":sacrifice, "enhancement":enhancement,
        "activation":"Always active; this is the body's condition, not a technique.", "applications":[],
        "limitations":"Cannot use an innate cursed technique. Barriers and cursed-energy arts requiring personal output are unavailable or sharply limited by the exact sacrifice.",
        "weaknesses":"No invented special weakness. Injury, exhaustion, superior force, and suitable enemy techniques still matter.",
        "growth_path":"Condition the exchanged body, master cursed tools, sharpen perception, and develop tactics that exploit the restriction's exact physical advantages.",
        "power_grade":"Exceptional" if guarantee_strong else "High potential", "overwhelming":bool(guarantee_strong), "no_inherent_weakness":False,
        "stat_modifiers":{"Physical Ability":physical, "Speed & Reflexes":speed, "Soul Stability":soul,
                          "Cursed Energy Reserves":reserve_loss, "Cursed Energy Output":output_loss},
    }


def _as_list(value):
    if isinstance(value, list):
        return copy.deepcopy(value)
    if value in (None, ""):
        return []
    return [copy.deepcopy(value)]


def _technique_applications(name, rule, application_hint=""):
    """Create applications from the final technique identity, never from a
    discarded fallback.  These are intentionally useful but narrow; play can
    reinterpret the same rule into much stronger extensions later."""
    name = str(name or "Innate Technique").strip()
    rule = str(rule or "Channels cursed energy through one coherent governing rule.").strip()
    lowered = f"{name} {rule} {application_hint}".lower()
    if any(word in lowered for word in ("space", "distance", "boundary", "threshold", "interval")):
        rows = (
            ("Boundary Step", "Defines one short spatial boundary and applies the technique's rule when a target crosses it.", "One prepared boundary at a time; range and precision follow current mastery."),
            ("Interval Collapse", "Compresses the technique's spatial rule around one chosen target for a sudden movement, impact or restraint.", "High output and exact target awareness are required."),
        )
    elif any(word in lowered for word in ("sound", "silence", "voice", "vibration", "music")):
        rows = (
            ("Mute Seal", "Applies the technique's rule to suppress and store sound inside a controlled area.", "The stored volume and area are limited by cursed-energy control."),
            ("Resonance Break", "Releases the technique's stored sound rule as a focused vibration through a marked target or surface.", "Power depends on sound genuinely collected or affected beforehand."),
        )
    elif any(word in lowered for word in ("shadow", "dark", "eclipse", "hidden")):
        rows = (
            ("Blind-Side Record", "Applies the technique's rule to an action performed outside direct observation and preserves its cursed imprint.", "Fails when the relevant action is clearly witnessed from beginning to end."),
            ("Eclipse Replay", "Releases one preserved imprint through a connected shadow as a delayed repeat of its original motion.", "Cannot exceed the force, shape or condition of the recorded action."),
        )
    elif any(word in lowered for word in ("blood", "wound", "testament")):
        rows = (
            ("Crimson Inscription", "Applies the technique's rule to willingly shed blood, shaping it into a short-lived cursed seal or thread.", "Requires the user's real blood and careful control of blood loss."),
            ("Testament Release", "Triggers a prepared blood inscription to bind, cut, redirect or warn according to its written intent.", "Only previously prepared inscriptions can be released."),
        )
    else:
        rows = (
            ("Focused Interpretation", f"Applies the core rule—{rule.rstrip('.')}—to one valid target with controlled output.", "One target and one direct interpretation at a time until further mastery."),
            ("Extended Interpretation", f"Broadens the same core rule of {name} across an area, chain of targets or stronger effect without changing what the technique fundamentally does.", "Requires substantially more cursed energy, control and concentration."),
        )
    return [{"name": f"{name}: {suffix}", "effect": effect, "limitation": limit}
            for suffix, effect, limit in rows]


def domain_profile_for(slot):
    if not isinstance(slot, dict) or slot.get("slot_type") != "Innate Cursed Technique":
        return {}
    name = str(slot.get("name") or "Innate Technique")
    rule = str(slot.get("governing_rule") or "the technique's governing rule")
    seed = _rng(name, rule, "domain")
    first = re.sub(r"[^A-Za-z0-9' -]", "", name).strip() or "Innate"
    nouns = ("Unbroken Court", "Silent Mandala", "Hollow Sanctuary", "Terminal Gallery", "Boundless Reliquary")
    return {
        "name": str(slot.get("domain_name") or f"Domain Expansion: {first} — {seed.choice(nouns)}"),
        "status": "Unachieved",
        "manifestation": str(slot.get("domain_manifestation") or f"An enclosed innate landscape organized around {rule.rstrip('.').lower()}."),
        "sure_hit": str(slot.get("sure_hit") or f"A valid target inside the completed barrier is automatically subjected to the governing rule of {name}; the domain does not create an unrelated power."),
        "cost": str(slot.get("domain_cost") or "Consumes immense cursed energy and temporarily destabilizes ordinary technique use after collapse."),
        "counterplay": _as_list(slot.get("domain_counters") or ["A stronger or more refined domain", "Simple Domain or another anti-domain method", "Breaking or escaping an imperfect barrier"]),
        "mastery": 0,
        "evidence": [],
    }


def normalize_birth_slot_package(slot, fallback=None):
    """Return one internally coherent birth-slot package.

    AI-authored values may replace a fallback, but a renamed technique cannot
    retain applications, a domain or counters that describe the discarded
    technique.  This also migrates older saves into the richer v3.23 shape.
    """
    authored_apps = isinstance(slot, dict) and isinstance(slot.get("applications"), list) and bool(slot.get("applications"))
    base = copy.deepcopy(fallback or {}) if isinstance(fallback, dict) else {}
    if isinstance(slot, dict):
        for key, value in slot.items():
            if value not in (None, "", [], {}):
                base[key] = copy.deepcopy(value)
    slot = base
    kind = str(slot.get("slot_type") or "Innate Cursed Technique")
    slot["slot_type"] = kind
    slot.setdefault("name", "Unrevealed Birth Slot")
    slot.setdefault("power_grade", "Setting-comparable")
    slot.setdefault("evidence", [])
    if kind == "Heavenly Restriction":
        slot["applications"] = []
        slot.pop("domain_profile", None)
        slot.setdefault("activation", "Always active; this is a bodily condition, not a technique.")
        slot.setdefault("growth_path", "Condition the exchanged body or senses and master tactics that exploit the restriction's exact benefit.")
        slot.setdefault("restrictions", [slot.get("sacrifice") or "A real capacity was exchanged at birth."])
        return slot
    if kind != "Innate Cursed Technique":
        slot.setdefault("applications", [])
        return slot
    name = str(slot.get("name") or "Innate Technique").strip()
    rule = str(slot.get("governing_rule") or "Channels cursed energy through one coherent governing rule.").strip()
    apps = slot.get("applications")
    cleaned = []
    if isinstance(apps, list):
        for row in apps[:8]:
            if isinstance(row, str) and row.strip():
                cleaned.append({"name": f"{name}: Application {len(cleaned)+1}", "effect": row.strip(), "limitation": slot.get("limitations", "Uses the parent technique's established conditions.")})
            elif isinstance(row, dict) and str(row.get("name") or "").strip() and str(row.get("effect") or row.get("description") or "").strip():
                clean = copy.deepcopy(row)
                clean["name"] = str(clean["name"]).strip()
                clean["effect"] = str(clean.get("effect") or clean.get("description")).strip()
                clean.setdefault("limitation", slot.get("limitations", "Uses the parent technique's established conditions."))
                cleaned.append(clean)
    # Generic fallback names prove that the applications were created before
    # a later AI rename. Rebuild them from the final rule as one atomic unit.
    stale = bool(cleaned and any("First Application" in row["name"] or "Reinforced Application" in row["name"] for row in cleaned))
    foreign = bool(not authored_apps and cleaned and all(name.lower() not in row["name"].lower() for row in cleaned))
    if not cleaned or stale or foreign:
        cleaned = _technique_applications(name, rule, slot.get("application_rule", ""))
    slot["applications"] = cleaned
    slot.setdefault("costs", "Cursed-energy cost scales with output, area, duration and the number of targets.")
    slot.setdefault("counters", _as_list(slot.get("weaknesses")))
    slot["domain_profile"] = domain_profile_for(slot)
    return slot


def generate_birth_slot(background="", guarantee_strong=False, seed="", force_kind=""):
    text = str(background or "")
    chooser = _rng(text, seed, guarantee_strong, force_kind)
    explicit_hr = bool(re.search(r"heavenly restriction|no cursed energy|zero cursed energy|toji|maki", text, re.I))
    explicit_technique = bool(re.search(r"innate technique|cursed technique|technique that|power to|ability to", text, re.I))
    kind = str(force_kind or "").lower()
    heavenly = kind == "heavenly_restriction" or explicit_hr or (not explicit_technique and chooser.random() < .16)
    if heavenly:
        return _procedural_restriction(text, chooser, guarantee_strong)
    name, rule, application_rule = _procedural_technique(text, chooser)
    overwhelming = bool(guarantee_strong or re.search(r"overwhelming|godlike|limitless|strongest|immeasurable", text, re.I))
    no_weakness = bool(re.search(r"no weakness|without weakness|unconditional", text, re.I))
    applications = [
        {"name": f"{name}: First Application", "effect": application_rule, "limitation": "Requires the technique's rule, a valid target and controlled cursed-energy output."},
        {"name": f"{name}: Reinforced Application", "effect": f"Pushes {application_rule[:1].lower() + application_rule[1:]} across a larger or more forceful target.", "limitation": "Costs substantially more cursed energy and precision than the first application."},
    ]
    return {
        "slot_type":"Innate Cursed Technique", "name":name, "governing_rule":rule,
        "activation":"The user deliberately channels cursed energy through the governing rule; gestures or words may improve control but are not mandatory unless established in play.",
        "targets":"Self, touched targets or targets inside the user's controlled cursed-energy reach, depending on the application.",
        "applications":applications,
        "limitations":"No special built-in limitation beyond cursed-energy cost, output, control, range and comprehension." if overwhelming else "The governing rule cannot create effects unrelated to its concept; scale and simultaneous targets increase cost sharply.",
        "weaknesses":"No inherent technique-specific weakness. It is still limited by the user's energy, output, control and ability to satisfy activation." if no_weakness else "Opponents can exploit incomplete information, range, setup, divided attention, depleted cursed energy or a more favorable technique interaction.",
        "growth_path":"Invent and master additional applications, improve efficiency and interpretation, then pursue a maximum technique or domain that expresses the same rule.",
        "domain_potential":f"A future domain could make the central rule of {name} unavoidable within a completed barrier.",
        "power_grade":"Overwhelming" if overwhelming else "Setting-comparable", "overwhelming":overwhelming, "no_inherent_weakness":no_weakness,
        "stat_modifiers":{"Cursed Energy Reserves":30 if overwhelming else 8,"Cursed Energy Output":36 if overwhelming else 10,"Cursed Energy Control":20 if overwhelming else 6,"Jujutsu Insight":18 if overwhelming else 5},
    }


def apply_birth_slot(profile, slot, curse_grade=""):
    profile = copy.deepcopy(profile)
    slot = normalize_birth_slot_package(slot)
    stats = profile.setdefault("stats", {})
    if curse_grade:
        baseline = GRADE_BASELINES[normalized_grade(curse_grade)]
        for stat in stats:
            stats[stat] = max(int(stats[stat]), baseline + (8 if "Cursed Energy" in stat else 0))
    for stat, amount in (slot.get("stat_modifiers") or {}).items():
        if stat not in stats:
            continue
        stats[stat] = 1 if amount <= -900 else max(1, int(stats.get(stat, 1)) + int(amount))
    skills = profile.setdefault("skills", {})
    for row in slot.get("applications", [])[:3]:
        skills[row["name"]] = {"rank":"Technique Application", "bonus":9 if slot.get("overwhelming") else 6,
            "description":row["effect"], "effect":row["effect"], "limitation":row.get("limitation", ""),
            "growth_path":slot.get("growth_path", ""), "parent_technique":slot.get("name", ""),
            "combat_usable":True, "effect_type":"utility", "category":"cursed technique"}
    profile["jjk_birth_slot"] = slot
    return profile


def initialize_jjk_state(state, slot, origin, curse_grade="", curse_identity=None):
    slot = normalize_birth_slot_package(slot)
    special = state.setdefault("special", {})
    is_curse = is_curse_origin(origin)
    grade = normalized_grade(curse_grade, "Grade 3") if is_curse else str(special.get("Grade") or "Unassessed")
    special.update({"Birth Slot":slot["slot_type"], "Innate Technique":slot["name"] if slot["slot_type"] == "Innate Cursed Technique" else "None",
                    "Heavenly Restriction":slot["name"] if slot["slot_type"] == "Heavenly Restriction" else "None", "Grade":grade})
    profile_key = ("Innate Technique Profile" if slot["slot_type"] == "Innate Cursed Technique"
                   else "Heavenly Restriction Profile" if slot["slot_type"] == "Heavenly Restriction"
                   else "Birth Slot Profile")
    special[profile_key] = copy.deepcopy(slot)
    origin_text = str(origin or "")
    year_floor = 18 if "First Year" in origin_text else 30 if "Second Year" in origin_text else 42 if "Third Year" in origin_text else 24
    background = str(state.get("background") or "")
    clan_match = re.search(r"\b(Gojo|Zenin|Kamo)\s+Clan\b", background, re.I)
    clan_name = clan_match.group(1).title() + " Clan" if clan_match else (_rng(state.get("name"), background, "clan").choice(("Gojo Clan", "Zenin Clan", "Kamo Clan")) if origin_text == "Great Clan Member" else "None")
    clan_obligations = {
        "Gojo Clan":["Protect the clan's political position without assuming the authority or abilities of its head"],
        "Zenin Clan":["Navigate a hierarchy that prizes inherited techniques, combat utility and internal rank"],
        "Kamo Clan":["Answer lineage expectations and the clan's close relationship with conservative headquarters"],
    }.get(clan_name, [])
    occupants = []
    vessel = special.get("Vessel")
    if vessel:
        occupants.append({"name":str(vessel), "type":"incarnated curse", "control":"Hostile and independent", "known":True})
    state["jjk_system"] = {
        "birth_slot":copy.deepcopy(slot), "grade":grade,
        "official_status":"Unregistered" if is_curse else str(special.get("Official Status") or "Student / unaffiliated"),
        "progression":{name:{"mastery":year_floor if name in {"Reinforcement", "Energy Control", "Birth Slot Mastery"} else max(0, year_floor - 18) if name in {"Barrier Arts", "Cursed Tool Mastery"} else 0, "evidence":[]}
                       for name in PROGRESSION_TRACKS},
        "application_mastery":{str(row.get("name")):{"mastery":year_floor, "uses":0, "evidence":[]}
                               for row in slot.get("applications", []) if isinstance(row, dict) and row.get("name")},
        "unlocks":[], "technique_intel":{}, "technique_exposure":{"public_facts":[], "witnesses":{}, "rumors":[]},
        "technique_disclosure":{"opponents":{}, "active_bonus":0, "active_opponent":"None"},
        "grade_record":{"missions_completed":0, "confirmed_exorcisms":0, "difficult_exorcisms":0,
                        "mission_reliability":0, "political_support":[], "headquarters_recognition":"Unassessed",
                        "promotion_recommendation":"No recommendation yet", "review_progress":0, "evidence":[]},
        "curse_identity":copy.deepcopy(curse_identity or {}), "humans_killed":0, "feeding_growth":0,
        "curse_development":{"fear_resonance":0, "territory":"None", "infamy":0, "public_assessment":"Unregistered", "evidence":[]},
        "black_flash_count":0, "black_flash":{"eligible_attempts":0, "confirmed":0, "in_the_zone_turns":0, "last_result":"None"},
        "binding_vows":[], "mission_dossiers":[], "domain_clashes":[], "barrier_mastery":"Foundational", "domain_status":"Unachieved",
        "domain":domain_profile_for(slot), "reverse_cursed_technique":"Unachieved", "maximum_technique":"Unachieved",
        "heavenly_restriction_mastery":{"body":year_floor if slot.get("slot_type") == "Heavenly Restriction" else 0,
                                         "perception":year_floor if slot.get("slot_type") == "Heavenly Restriction" else 0,
                                         "tool_fluency":max(0, year_floor - 8) if slot.get("slot_type") == "Heavenly Restriction" else 0,
                                         "adaptations":[], "evidence":[]},
        "clan":{"name":clan_name, "standing":0, "obligations":clan_obligations, "favors":[], "sanctions":[], "inheritance_claim":"None", "evidence":[]},
        "soul":{"integrity":100, "self_control":100, "occupants":occupants, "possession_risk":"None" if not occupants else "Active", "evidence":[]},
    }
    if is_curse:
        special["Cursed Spirit Nature"] = copy.deepcopy(curse_identity or {})
    if clan_name != "None":
        state["affiliations"] = [row for row in (state.get("affiliations") or []) if not isinstance(row, dict) or row.get("faction") != "Jujutsu Society"]
        if not any(isinstance(row, dict) and row.get("faction") == clan_name for row in state["affiliations"]):
            state["affiliations"].append({"faction":clan_name, "rank":"Clan member", "status":"active", "joined":"Birth", "notes":"Family standing and obligations develop through play."})
        state.setdefault("reputation", {}).setdefault(clan_name, 0)
    normalize_jjk_state(state)


def feeding_growth_for_target(target_kind):
    text = str(target_kind or "ordinary human").lower()
    if "special grade" in text: return 220
    if "grade 1" in text: return 85
    if "grade 2" in text: return 34
    if "grade 3" in text: return 13
    if "grade 4" in text or "sorcerer" in text: return 6
    return 1


def _safe_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _track(system, name):
    progression = system.setdefault("progression", {})
    row = progression.setdefault(name, {"mastery":0, "evidence":[]})
    if not isinstance(row, dict):
        row = progression[name] = {"mastery":_safe_number(row), "evidence":[]}
    row["mastery"] = max(0, min(100, _safe_number(row.get("mastery"))))
    row.setdefault("evidence", [])
    return row


def sync_jjk_special(state):
    system = state.setdefault("jjk_system", {})
    special = state.setdefault("special", {})
    slot = normalize_birth_slot_package(system.get("birth_slot") or special.get("Innate Technique Profile") or special.get("Heavenly Restriction Profile") or {})
    system["birth_slot"] = slot
    if slot.get("slot_type") == "Innate Cursed Technique":
        special["Innate Technique"] = slot.get("name", "Unrevealed")
        special["Heavenly Restriction"] = "None"
        special["Innate Technique Profile"] = copy.deepcopy(slot)
        special.pop("Heavenly Restriction Profile", None)
    elif slot.get("slot_type") == "Heavenly Restriction":
        special["Innate Technique"] = "None"
        special["Heavenly Restriction"] = slot.get("name", "Heavenly Restriction")
        special["Heavenly Restriction Profile"] = copy.deepcopy(slot)
        special.pop("Innate Technique Profile", None)
    special["Birth Slot"] = slot.get("slot_type", "Unrevealed")
    special["Grade"] = system.get("grade", special.get("Grade", "Unassessed"))
    special["Official Status"] = system.get("official_status", special.get("Official Status", "Unregistered"))
    special["Black Flashes"] = int(system.get("black_flash_count", 0) or 0)
    special["Domain Expansion"] = system.get("domain_status", "Unachieved")
    special["Reverse Cursed Technique"] = system.get("reverse_cursed_technique", "Unachieved")
    special["Maximum Technique"] = system.get("maximum_technique", "Unachieved")
    special["Binding Vows"] = copy.deepcopy(system.get("binding_vows", []))
    special["Technique Intel"] = copy.deepcopy(system.get("technique_intel", {}))
    special["Clan Record"] = copy.deepcopy(system.get("clan", {}))
    special["Soul Record"] = copy.deepcopy(system.get("soul", {}))
    special["Curse Development"] = copy.deepcopy(system.get("curse_development", {}))


def normalize_jjk_state(state, before=None):
    """Migrate and reconcile JJK state without trusting narrator-authored
    app ledgers.  The narrator may add facts through special/skills; this
    function turns those facts into one persistent mechanical record."""
    if not isinstance(state, dict) or state.get("world") != "Jujutsu Kaisen":
        return []
    repairs = []
    system = state.setdefault("jjk_system", {})
    special = state.setdefault("special", {})
    slot_before = copy.deepcopy(system.get("birth_slot") or {})
    authored_slot = special.get("Innate Technique Profile") or special.get("Heavenly Restriction Profile") or slot_before
    slot = normalize_birth_slot_package(authored_slot, slot_before)
    if slot != slot_before:
        repairs.append("Reconciled the complete innate power package")
    system["birth_slot"] = slot
    old_name, new_name = str(slot_before.get("name") or ""), str(slot.get("name") or "")
    if old_name and new_name and old_name != new_name:
        for skill_name, detail in list((state.get("skills") or {}).items()):
            if isinstance(detail, dict) and detail.get("parent_technique") == old_name:
                state["skills"].pop(skill_name, None)
        repairs.append("Removed applications belonging to the discarded technique identity")
    if slot.get("slot_type") == "Innate Cursed Technique":
        for app in slot.get("applications", []):
            if not isinstance(app, dict) or not app.get("name"):
                continue
            state.setdefault("skills", {}).setdefault(app["name"], {
                "rank":"Technique Application", "bonus":6, "description":app.get("effect", ""), "effect":app.get("effect", ""),
                "limitation":app.get("limitation", slot.get("limitations", "")), "growth_path":slot.get("growth_path", ""),
                "parent_technique":new_name, "combat_usable":True, "effect_type":"utility",
                "category":"cursed technique", "target_type":"enemy",
            })
    old_name, new_name = str(slot_before.get("name") or ""), str(slot.get("name") or "")
    if old_name and new_name and old_name != new_name:
        for skill_name, detail in list((state.get("skills") or {}).items()):
            if isinstance(detail, dict) and detail.get("parent_technique") == old_name:
                state["skills"].pop(skill_name, None)
        repairs.append("Removed applications belonging to the discarded technique identity")
    if slot.get("slot_type") == "Innate Cursed Technique":
        for app in slot.get("applications", []):
            if not isinstance(app, dict) or not app.get("name"):
                continue
            state.setdefault("skills", {}).setdefault(app["name"], {
                "rank":"Technique Application", "bonus":6, "description":app.get("effect", ""), "effect":app.get("effect", ""),
                "limitation":app.get("limitation", slot.get("limitations", "")), "growth_path":slot.get("growth_path", ""),
                "parent_technique":new_name, "combat_usable":True, "effect_type":"utility",
                "category":"cursed technique", "target_type":"enemy",
            })
    system.setdefault("grade", special.get("Grade", "Unassessed"))
    system.setdefault("official_status", special.get("Official Status", "Unregistered"))
    system.setdefault("progression", {})
    for name in PROGRESSION_TRACKS:
        _track(system, name)
    system.setdefault("application_mastery", {})
    for app in slot.get("applications", []):
        if isinstance(app, dict) and app.get("name"):
            system["application_mastery"].setdefault(app["name"], {"mastery":0, "uses":0, "evidence":[]})
    system.setdefault("unlocks", [])
    intel = special.get("Technique Intel")
    if isinstance(intel, dict):
        for person, row in intel.items():
            if not str(person).strip():
                continue
            if isinstance(row, str):
                row = {"confirmed":[row], "suspected":[], "unknowns":[], "evidence":[]}
            if isinstance(row, dict):
                clean = system.setdefault("technique_intel", {}).setdefault(str(person), {"confirmed":[], "suspected":[], "unknowns":[], "evidence":[]})
                for key in ("confirmed", "suspected", "unknowns", "evidence"):
                    for item in _as_list(row.get(key)):
                        text = str(item).strip()
                        if text and text not in clean[key]:
                            clean[key].append(text)
                    clean[key] = clean[key][-20:]
    system.setdefault("technique_intel", {})
    system.setdefault("technique_exposure", {"public_facts":[], "witnesses":{}, "rumors":[]})
    system.setdefault("technique_disclosure", {"opponents":{}, "active_bonus":0, "active_opponent":"None"})
    system["technique_disclosure"].setdefault("opponents", {})
    system["technique_disclosure"].setdefault("active_bonus", 0)
    system["technique_disclosure"].setdefault("active_opponent", "None")
    system.setdefault("grade_record", {"missions_completed":0, "confirmed_exorcisms":0, "difficult_exorcisms":0, "promotion_recommendation":"No recommendation yet", "review_progress":0, "evidence":[]})
    system["grade_record"].setdefault("mission_reliability", 0)
    system["grade_record"].setdefault("political_support", [])
    system["grade_record"].setdefault("headquarters_recognition", "Unassessed")
    system.setdefault("curse_identity", copy.deepcopy(special.get("Cursed Spirit Nature") or {}))
    system.setdefault("humans_killed", 0); system.setdefault("feeding_growth", 0)
    system.setdefault("curse_development", {"fear_resonance":0, "territory":"None", "infamy":0, "public_assessment":"Unregistered", "evidence":[]})
    system.setdefault("black_flash_count", int(special.get("Black Flashes", 0) or 0))
    system.setdefault("black_flash", {"eligible_attempts":0, "confirmed":system["black_flash_count"], "in_the_zone_turns":0, "last_result":"None"})
    system.setdefault("binding_vows", [])
    system.setdefault("mission_dossiers", [])
    system.setdefault("domain_clashes", [])
    authored_vows = special.get("Binding Vows")
    if isinstance(authored_vows, list):
        for vow in authored_vows:
            if isinstance(vow, dict) and str(vow.get("name") or vow.get("promise") or "").strip():
                clean = copy.deepcopy(vow)
                clean.setdefault("name", f"Binding Vow {len(system['binding_vows']) + 1}")
                clean.setdefault("promise", "An explicit restriction accepted in play")
                clean.setdefault("benefit", "A proportional cursed-energy benefit")
                clean.setdefault("price", clean.get("restriction") or "The stated restriction")
                clean.setdefault("breach", "The benefit ends and the established backlash applies")
                clean.setdefault("status", "Active")
                if not any(str(old.get("name")) == str(clean.get("name")) for old in system["binding_vows"] if isinstance(old, dict)):
                    system["binding_vows"].append(clean)
    system.setdefault("barrier_mastery", "Foundational")
    system.setdefault("domain_status", special.get("Domain Expansion", "Unachieved"))
    system.setdefault("domain", domain_profile_for(slot))
    if not system.get("domain") and slot.get("slot_type") == "Innate Cursed Technique":
        system["domain"] = domain_profile_for(slot)
    system.setdefault("reverse_cursed_technique", special.get("Reverse Cursed Technique", "Unachieved"))
    system.setdefault("maximum_technique", special.get("Maximum Technique", "Unachieved"))
    system.setdefault("heavenly_restriction_mastery", {"body":0, "perception":0, "tool_fluency":0, "adaptations":[], "evidence":[]})
    system.setdefault("clan", {"name":"None", "standing":0, "obligations":[], "favors":[], "sanctions":[], "inheritance_claim":"None", "evidence":[]})
    system.setdefault("soul", {"integrity":100, "self_control":100, "occupants":[], "possession_risk":"None", "evidence":[]})
    for source_key, system_key, allowed in (
        ("Clan Record", "clan", {"name","standing","obligations","favors","sanctions","inheritance_claim","evidence"}),
        ("Soul Record", "soul", {"integrity","self_control","occupants","possession_risk","evidence"}),
        ("Curse Development", "curse_development", {"fear_resonance","territory","infamy","public_assessment","evidence"}),
    ):
        authored = special.get(source_key)
        if isinstance(authored, dict):
            for key, value in authored.items():
                if key in allowed and value not in (None, ""):
                    system[system_key][key] = copy.deepcopy(value)
    sync_jjk_special(state)
    return repairs


def _add_skill(state, name, rank, description, **extra):
    skills = state.setdefault("skills", {})
    if name in skills:
        return False
    detail = {"rank":rank, "bonus":int(extra.pop("bonus", 8)), "description":description, "effect":description,
              "limitation":extra.pop("limitation", "Requires sufficient cursed energy, control and the established activation conditions."),
              "growth_path":extra.pop("growth_path", "Improve efficiency, reliability, range and tactical interpretation through use."),
              "combat_usable":True, "effect_type":extra.pop("effect_type", "utility"),
              "category":extra.pop("category", "cursed technique"), "target_type":extra.pop("target_type", "area")}
    detail.update(extra)
    skills[name] = detail
    return True


def _add_unlock(system, label):
    if label not in system.setdefault("unlocks", []):
        system["unlocks"].append(label)
        return True
    return False


def _binding_vow_from_turn(actions, narrative, turn):
    action = next((str(x).strip() for x in actions if re.search(r"\bbinding vow\b|\bvow\b.{0,30}\b(exchange|sacrifice|give up|restrict)", str(x), re.I)), "")
    if not action or re.search(r"\b(fails?|refused|cannot|impossible|not formed|does not form)\b", str(narrative), re.I):
        return None
    price_match = re.search(r"\b(?:give up|sacrifice|forbid|restrict|in exchange for|at the cost of)\s+([^.;]{3,140})", action, re.I)
    benefit_match = re.search(r"\b(?:to gain|so that|in return for|in exchange for|for)\s+([^.;]{3,140})", action, re.I)
    price = price_match.group(1).strip() if price_match else "The exact restriction stated in the player's declared vow"
    benefit = benefit_match.group(1).strip() if benefit_match else "A proportional increase tied only to the declared purpose"
    return {"name":f"Declared Vow — Turn {turn}", "promise":action[:300], "benefit":benefit[:240], "price":price[:240],
            "breach":"The benefit ends; a self-imposed vow loses what it granted, while a mutual vow may carry severe setting-valid consequences.",
            "status":"Active", "formed_turn":turn, "evidence":[str(narrative)[:300]] if narrative else []}


def _promotion_recommendation(state, record):
    stats = [float(value) for value in (state.get("stats") or {}).values() if isinstance(value, (int, float))]
    peak = max(stats, default=0); balanced = sum(stats) / max(1, len(stats))
    missions = int(record.get("missions_completed", 0) or 0)
    hard = int(record.get("difficult_exorcisms", 0) or 0)
    if peak >= 135 and balanced >= 95 and hard >= 3: return "Special Grade review justified — requires an exceptional strategic threat profile, not stats alone"
    if peak >= 82 and balanced >= 62 and missions >= 5: return "Grade 1 promotion review justified"
    if peak >= 52 and balanced >= 42 and missions >= 3: return "Grade 2 promotion review justified"
    if peak >= 34 and missions >= 1: return "Grade 3 promotion review justified"
    return "Build a verified mission and exorcism record"


def resolve_domain_clash(player, enemy):
    """Compare the five parts that decide a domain contest in the setting."""
    def score(domain):
        return (
            _safe_number(domain.get("refinement"), domain.get("mastery", 0)) * .34
            + _safe_number(domain.get("barrier_integrity"), domain.get("barrier", 0)) * .24
            + _safe_number(domain.get("output"), 0) * .22
            + min(100, _safe_number(domain.get("range"), 10)) * .10
            + _safe_number(domain.get("compatibility"), 50) * .10
        )
    player_score, enemy_score = score(player), score(enemy)
    interaction = "Closed barriers contest normally"
    if player.get("open_barrier") and not enemy.get("open_barrier"):
        player_score += 12; interaction = "The player's open barrier attacks the opposing shell from outside"
    elif enemy.get("open_barrier") and not player.get("open_barrier"):
        enemy_score += 12; interaction = "The enemy's open barrier attacks the player's shell from outside"
    margin = round(player_score - enemy_score, 1)
    outcome = "Player domain prevails" if margin >= 8 else "Enemy domain prevails" if margin <= -8 else "Domains remain contested"
    return {"player_score":round(player_score, 1), "enemy_score":round(enemy_score, 1), "margin":margin, "outcome":outcome,
            "factors":{"refinement":"34%", "barrier":"24%", "output":"22%", "range":"10%", "compatibility":"10%"},
            "barrier_interaction":interaction}


def advance_jjk_state(state, before, actions, narrative, events, elapsed_minutes=5):
    """Apply deterministic JJK consequences after a narrator result.

    This does not decide the story for the model. It records what the story
    established, advances explicitly trained tracks by elapsed time, and
    grants setting-native milestones only when their prerequisites are met.
    """
    if state.get("world") != "Jujutsu Kaisen":
        return []
    normalize_jjk_state(state, before)
    notes = []
    system = state["jjk_system"]
    special = state.setdefault("special", {})
    actions = [str(x).strip() for x in (actions or []) if str(x).strip()]
    event_texts = [str((event or {}).get("message") or (event or {}).get("narrative") or "") for event in (events or []) if isinstance(event, dict)]
    result_text = " ".join([str(narrative or ""), *event_texts])
    all_text = " ".join([*actions, result_text])
    days = max(1 / 288, float(elapsed_minutes or 5) / 1440.0)
    training = bool(re.search(r"\b(train|practice|study|drill|meditat|spar|develop|master|learn)\w*\b", " ".join(actions), re.I))
    gain = max(1, min(28, round((math.sqrt(days) * (5.2 if training else 1.6)) + (1 if len(actions) > 1 else 0))))
    for track_name, pattern in TRACK_PATTERNS.items():
        if not pattern.search(all_text):
            continue
        if system["birth_slot"].get("slot_type") == "Heavenly Restriction" and track_name in {"Reverse Cursed Technique", "Maximum Technique", "Domain Expansion"}:
            continue
        row = _track(system, track_name)
        before_value = row["mastery"]
        row["mastery"] = min(100, round(before_value + gain, 1))
        evidence = next((x for x in actions if pattern.search(x)), result_text[:220])
        if evidence:
            row["evidence"] = [*row.get("evidence", []), evidence][-12:]
        if row["mastery"] > before_value:
            notes.append(f"{track_name} {int(before_value)}→{int(row['mastery'])}")

    # Mature applications through actual use, preserving one parent rule.
    for skill_name, detail in list((state.get("skills") or {}).items()):
        if not isinstance(detail, dict) or detail.get("parent_technique") != system["birth_slot"].get("name"):
            continue
        if skill_name.lower() not in all_text.lower():
            continue
        row = system.setdefault("application_mastery", {}).setdefault(skill_name, {"mastery":0, "uses":0, "evidence":[]})
        row["uses"] = int(row.get("uses", 0) or 0) + 1
        row["mastery"] = min(100, round(_safe_number(row.get("mastery")) + max(2, gain), 1))
        row["evidence"] = [*row.get("evidence", []), result_text[:220]][-12:]
        combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
        enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
        witness = str(enemy.get("name") or "").strip()
        if witness:
            observed = system.setdefault("technique_exposure", {}).setdefault("witnesses", {}).setdefault(witness, [])
            fact = f"Observed {skill_name} in use; effect witnessed, full governing rule not automatically known"
            if fact not in observed: observed.append(fact)

    # Revealing one's hand creates a real, named matchup modifier. Correct
    # inference grants a smaller version; merely seeing an effect is not the
    # same as understanding its governing rule.
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
    opponent = str(enemy.get("name") or "").strip()
    disclosure = system.setdefault("technique_disclosure", {"opponents":{}, "active_bonus":0, "active_opponent":"None"})
    if opponent:
        row = disclosure.setdefault("opponents", {}).setdefault(opponent, {"known":False, "source":"Unknown", "bonus":0, "evidence":[]})
        deliberate = bool(re.search(r"\b(?:explain|reveal|tell|declare|disclose)\w*\b.{0,80}\b(?:technique|ability|rule|how it works)\b", " ".join(actions), re.I))
        intel = system.get("technique_intel", {}).get(opponent, {})
        inferred = bool((intel.get("confirmed") if isinstance(intel, dict) else []) or re.search(r"\b(?:understood|figured out|deduced|learned)\b.{0,80}\b(?:technique|rule|ability)\b", result_text, re.I))
        if deliberate or inferred:
            row["known"] = True
            row["source"] = "Deliberately revealed" if deliberate else "Correctly inferred"
            row["bonus"] = 10 if deliberate else 5
            evidence = (next((x for x in actions if deliberate and re.search(r"explain|reveal|tell|declare|disclose", x, re.I)), "") or result_text)[:260]
            if evidence and evidence not in row.setdefault("evidence", []): row["evidence"].append(evidence)
        disclosure["active_opponent"] = opponent
        disclosure["active_bonus"] = int(row.get("bonus", 0) or 0) if row.get("known") else 0
        if disclosure["active_bonus"]:
            notes.append(f"REVEALING ONE'S HAND — {opponent} knows the rule; +{disclosure['active_bonus']} technique bonus")
    else:
        disclosure["active_opponent"] = "None"
        disclosure["active_bonus"] = 0

    barrier = _track(system, "Barrier Arts")["mastery"]
    if barrier >= 25 and _add_unlock(system, "Curtain"):
        _add_skill(state, "Curtain", "Barrier Art", "Raises a configurable barrier that conceals or controls entry according to established conditions.", category="control", effect_type="control")
        notes.append("UNLOCKED — Curtain")
    if barrier >= 55 and _add_unlock(system, "Simple Domain"):
        _add_skill(state, "Simple Domain", "Anti-Domain Art", "Creates a compact barrier that interferes with a domain's guaranteed-hit function while maintained.", category="defense", effect_type="shield", limitation="Its protection is limited in area and can be stripped by superior refinement or disrupted stance.")
        notes.append("UNLOCKED — Simple Domain")

    rct = _track(system, "Reverse Cursed Technique")["mastery"]
    if rct >= 60 and system.get("reverse_cursed_technique") == "Unachieved":
        system["reverse_cursed_technique"] = "Awakened — self-healing"
        _add_skill(state, "Reverse Cursed Technique", "Advanced Jujutsu", "Multiplies cursed energy against itself to produce positive energy capable of repairing the user's body.", category="healing", effect_type="heal", target_type="self", limitation="Extremely demanding control and energy cost; healing others is a separate higher mastery.")
        notes.append("AWAKENED — Reverse Cursed Technique")

    slot = system["birth_slot"]
    maximum = _track(system, "Maximum Technique")["mastery"]
    if slot.get("slot_type") == "Innate Cursed Technique" and maximum >= 70 and system.get("maximum_technique") == "Unachieved":
        maximum_name = f"Maximum Technique: {slot.get('name', 'Innate Technique')} — Absolute Interpretation"
        system["maximum_technique"] = maximum_name
        _add_skill(state, maximum_name, "Maximum Technique", f"Pushes the governing rule of {slot.get('name')} to its greatest non-domain output without adding an unrelated effect.", category="offense", effect_type="damage", target_type="area", bonus=15, limitation="Consumes extreme cursed energy and leaves ordinary applications less stable afterward.")
        notes.append(f"UNLOCKED — {maximum_name}")

    domain_track = _track(system, "Domain Expansion")["mastery"]
    if slot.get("slot_type") == "Innate Cursed Technique" and domain_track >= 100 and system.get("domain_status") == "Unachieved":
        domain = system.setdefault("domain", domain_profile_for(slot))
        domain["status"] = "Awakened"
        domain["mastery"] = 1
        system["domain_status"] = domain.get("name", "Awakened")
        _add_skill(state, domain["name"], "Domain Expansion", f"Manifests {domain.get('manifestation')} Sure-hit: {domain.get('sure_hit')}", category="control", effect_type="control", target_type="area", bonus=18, limitation=domain.get("cost"))
        notes.append(f"DOMAIN AWAKENED — {domain['name']}")

    # Heavenly Restrictions progress through body/perception/tool practice,
    # not cursed-technique milestones they cannot possess.
    if slot.get("slot_type") == "Heavenly Restriction":
        hr = system.setdefault("heavenly_restriction_mastery", {"body":0, "perception":0, "tool_fluency":0, "adaptations":[], "evidence":[]})
        if re.search(r"\b(train|condition|spar|physical|body|speed|strength)\w*", all_text, re.I): hr["body"] = min(100, round(_safe_number(hr.get("body")) + gain, 1))
        if re.search(r"\b(sense|perceive|track|detect|awareness|reflex)\w*", all_text, re.I): hr["perception"] = min(100, round(_safe_number(hr.get("perception")) + gain, 1))
        if TRACK_PATTERNS["Cursed Tool Mastery"].search(all_text): hr["tool_fluency"] = min(100, round(_safe_number(hr.get("tool_fluency")) + gain, 1))
        if hr.get("body", 0) >= 70 and "Air-Step Footwork" not in hr.setdefault("adaptations", []):
            hr["adaptations"].append("Air-Step Footwork")
            _add_skill(state, "Air-Step Footwork", "Heavenly Restriction Adaptation", "Uses overwhelming physical control and environmental footholds for abrupt three-dimensional movement without cursed energy.", category="mobility", effect_type="movement", target_type="self", limitation="Requires real surfaces, momentum and an unobstructed physical route.")
            notes.append("ADAPTATION — Air-Step Footwork")

    # A vow is formed only after a declared exchange resolves without the
    # story rejecting it. Existing structured vows authored by the GM were
    # already imported by normalize_jjk_state.
    vow = _binding_vow_from_turn(actions, result_text, state.get("turn", 0))
    if vow and not any(old.get("promise") == vow["promise"] for old in system.get("binding_vows", []) if isinstance(old, dict)):
        system.setdefault("binding_vows", []).append(vow)
        notes.append(f"BINDING VOW FORMED — {vow['name']}")
    for existing in system.get("binding_vows", []):
        if not isinstance(existing, dict) or existing.get("status", "Active") != "Active":
            continue
        if re.search(r"\b(?:break|broke|breach|violat|betray)\w*\b.{0,100}\b(?:vow|promise|restriction)\b", all_text, re.I):
            existing["status"] = "Breached"
            existing["breached_turn"] = state.get("turn", 0)
            existing.setdefault("evidence", []).append(result_text[:260] or "Violation declared in the player's action")
            conditions = state.setdefault("conditions", [])
            if not any(isinstance(c, dict) and c.get("name") == "Binding Vow Backlash" for c in conditions):
                conditions.append({"name":"Binding Vow Backlash", "duration_rounds":3, "effect":"The vow's benefit is removed and its recorded consequence applies."})
            notes.append(f"BINDING VOW BREACHED — {existing.get('name', 'Recorded vow')}")
            break

    # Black Flash requires both a confirmed outcome and a physically eligible
    # cursed-energy impact. Merely typing its name or receiving decorative
    # prose can no longer award the record.
    physical = bool(re.search(r"\b(punch|kick|strike|hit|slam|elbow|knee|weapon blow|physical attack|melee)\w*", " ".join(actions), re.I))
    energy = bool(re.search(r"\b(cursed energy|black flash|reinforc|energy timing)\w*", " ".join(actions), re.I))
    combat_active = bool((state.get("combat") or {}).get("active") or (before.get("combat") or {}).get("active"))
    black = system.setdefault("black_flash", {"eligible_attempts":0, "confirmed":0, "in_the_zone_turns":0, "last_result":"None"})
    if physical and (energy or combat_active):
        black["eligible_attempts"] = int(black.get("eligible_attempts", 0) or 0) + 1
    confirmed = bool(re.search(r"\bblack flash\b", result_text, re.I) and physical and (energy or combat_active))
    if confirmed:
        system["black_flash_count"] = int(system.get("black_flash_count", 0) or 0) + 1
        black["confirmed"] = system["black_flash_count"]
        black["in_the_zone_turns"] = 3
        black["last_result"] = "Confirmed"
        for stat, amount in (("Cursed Energy Control", 2), ("Jujutsu Insight", 2)):
            if stat in state.get("stats", {}): state["stats"][stat] = int(state["stats"][stat]) + amount
        notes.append(f"BLACK FLASH RECORDED — lifetime total {system['black_flash_count']}; entered the zone")
    elif int(black.get("in_the_zone_turns", 0) or 0) > 0:
        black["in_the_zone_turns"] = max(0, int(black["in_the_zone_turns"]) - 1)

    # Mission/grade records use actual quest transitions and resolved fights.
    old_quests = {str(q.get("name")):str(q.get("status", "")).lower() for q in (before.get("quests") or []) if isinstance(q, dict)}
    newly_completed = [q for q in (state.get("quests") or []) if isinstance(q, dict) and str(q.get("status", "")).lower() in {"complete", "completed", "resolved"} and old_quests.get(str(q.get("name"))) not in {"complete", "completed", "resolved"}]
    record = system.setdefault("grade_record", {})
    record["missions_completed"] = int(record.get("missions_completed", 0) or 0) + len(newly_completed)
    if newly_completed:
        record["mission_reliability"] = min(100, int(record.get("mission_reliability", 0) or 0) + 5 * len(newly_completed))
        record["headquarters_recognition"] = "Established" if record["missions_completed"] >= 5 else "Documented"
        for quest in newly_completed:
            system.setdefault("mission_dossiers", []).append({
                "name":quest.get("name", "Jujutsu mission"),
                "human_cause":quest.get("human_cause", "The human source of the curse remains part of the case"),
                "manifestations":quest.get("manifestations", ["Initial anomaly", "Escalation", "Resolved manifestation"]),
                "unknowns":quest.get("unknowns", []),
                "civilians":quest.get("civilians", "Civilians affected or placed at risk"),
                "outcome":quest.get("outcome", "Resolved with consequences beyond exorcism"), "status":"Resolved",
            })
        system["mission_dossiers"] = system["mission_dossiers"][-30:]
    exorcisms = len(re.findall(r"\b(?:exorcis(?:e|ed)|destroy(?:ed)?|defeat(?:ed)?)\b[^.]{0,60}\bcurse(?:d spirit)?\b", result_text, re.I))
    if exorcisms:
        record["confirmed_exorcisms"] = int(record.get("confirmed_exorcisms", 0) or 0) + exorcisms
        if re.search(r"\b(?:grade 1|special grade)\b", result_text, re.I):
            record["difficult_exorcisms"] = int(record.get("difficult_exorcisms", 0) or 0) + exorcisms
    recommendation = _promotion_recommendation(state, record)
    if recommendation != record.get("promotion_recommendation"):
        record["promotion_recommendation"] = recommendation
        notes.append(f"GRADE RECORD — {recommendation}")

    if re.search(r"\bdomain expansion\b", " ".join(actions), re.I) and re.search(r"\b(?:enemy|opponent|curse|sorcerer).{0,100}\bdomain\b|\bdomain clash\b", result_text, re.I):
        player_domain = copy.deepcopy(system.get("domain") or {})
        player_domain.setdefault("refinement", _track(system, "Domain Expansion")["mastery"])
        player_domain.setdefault("barrier_integrity", _track(system, "Barrier Arts")["mastery"])
        player_domain.setdefault("output", _safe_number((state.get("stats") or {}).get("Cursed Energy Output", 0)))
        player_domain.setdefault("range", 20)
        enemy_domain = enemy.get("domain") if isinstance(enemy.get("domain"), dict) else {
            "name":f"{opponent or 'Enemy'} Domain", "refinement":enemy.get("domain_refinement", enemy.get("power", 50)),
            "barrier_integrity":enemy.get("domain_barrier", enemy.get("power", 50)),
            "output":enemy.get("power", 50), "range":enemy.get("domain_range", 20),
        }
        clash = resolve_domain_clash(player_domain, enemy_domain)
        clash.update({"turn":state.get("turn", 0), "player_domain":player_domain.get("name", "Player Domain"), "enemy_domain":enemy_domain.get("name", "Enemy Domain")})
        system.setdefault("domain_clashes", []).append(clash)
        system["domain_clashes"] = system["domain_clashes"][-20:]
        notes.append(f"DOMAIN CLASH — {clash['outcome']} ({clash['player_score']} vs {clash['enemy_score']})")

    # Sentient curses gain exponentially more from high-energy prey, accrue
    # infamy, and become formally assessed only once witnesses know enough.
    origin = str(special.get("Origin") or "")
    killed = bool(re.search(r"\b(kill(?:ed|s)?|devour(?:ed|s)?|consum(?:e|ed)|drain(?:ed)?)\b[^.]{0,100}\b(humans?|civilians?|sorcerers?|curse users?|people|persons?)\b", result_text, re.I))
    if is_curse_origin(origin) and killed:
        count_match = re.search(r"\b(?:kill(?:ed|s)?|devour(?:ed|s)?|consum(?:e|ed)|drain(?:ed)?)\s+(\d{1,3})\b", result_text, re.I)
        victims = max(1, min(100, int(count_match.group(1)))) if count_match else 1
        target = "special grade" if re.search(r"special[- ]grade", result_text, re.I) else "grade 1" if re.search(r"grade[ -]1", result_text, re.I) else "grade 2" if re.search(r"grade[ -]2", result_text, re.I) else "grade 3" if re.search(r"grade[ -]3", result_text, re.I) else "grade 4 sorcerer" if re.search(r"sorcerer|curse user", result_text, re.I) else "ordinary human"
        per_target = feeding_growth_for_target(target)
        growth = round(per_target * victims * (1 + math.log10(victims)))
        system["humans_killed"] = int(system.get("humans_killed", 0) or 0) + victims
        system["feeding_growth"] = int(system.get("feeding_growth", 0) or 0) + growth
        for stat, scale in (("Cursed Energy Reserves", 1.0), ("Cursed Energy Output", .55), ("Cursed Energy Control", .18)):
            if stat in state.get("stats", {}): state["stats"][stat] = int(state["stats"][stat]) + max(1, round(growth * scale))
        curse = system.setdefault("curse_development", {})
        curse["infamy"] = int(curse.get("infamy", 0) or 0) + victims * (5 if target != "ordinary human" else 1)
        curse["fear_resonance"] = int(curse.get("fear_resonance", 0) or 0) + max(1, round(growth / 3))
        if curse["infamy"] >= 10 and curse.get("public_assessment") == "Unregistered":
            curse["public_assessment"] = system.get("grade", "Grade 3")
            system["official_status"] = f"Known cursed spirit — assessed {curse['public_assessment']}"
        notes.append(f"CURSE FEEDING — {victims} {target} target(s) yielded {growth} growth")

    # Clan and soul changes remain narrative in cause but structured in state.
    clan = system.setdefault("clan", {})
    if clan.get("name") not in {"", "None"}:
        faction_score = state.get("reputation", {}).get(clan.get("name"))
        if isinstance(faction_score, (int, float)): clan["standing"] = int(faction_score)
        if re.search(r"\b(clan order|clan obligation|elder(?:s)? ordered|family duty)\b", result_text, re.I):
            item = result_text[:240]
            if item not in clan.setdefault("obligations", []): clan["obligations"].append(item)
    soul = system.setdefault("soul", {})
    if re.search(r"\b(possess(?:ed|ion)?|take(?:s)? control|seize(?:s)? the body|incarnat(?:e|ion))\b", result_text, re.I):
        soul["self_control"] = max(0, round(_safe_number(soul.get("self_control"), 100) - 10))
        soul["possession_risk"] = "High" if soul["self_control"] < 50 else "Active"
        soul.setdefault("evidence", []).append(result_text[:240])
    elif re.search(r"\b(resist(?:ed|s)? possession|retain(?:ed|s)? control|suppress(?:ed|es)? the incarnated)\b", result_text, re.I):
        soul["self_control"] = min(100, round(_safe_number(soul.get("self_control"), 100) + 5))
        soul.setdefault("evidence", []).append(result_text[:240])

    sync_jjk_special(state)
    return notes
