"""Naruto-specific Jinchuriki creation, migration, and mechanics.

A tailed beast is an independent character and a sealed power system, not a
generic skill.  The profile records the host's current access separately from
the beast's full canon potential so an unmastered host receives the reserve,
social consequences, seal pressure, and loss-of-control risks without being
treated as a perfect Jinchuriki on day one.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re


TAILED_BEASTS = {
    1: {
        "name": "Shukaku", "title": "One-Tail", "nature": ["Wind Release", "Magnet Release"],
        "traits": ["Sand manipulation and defense", "Cursed seal markings", "Exceptional sealing techniques"],
    },
    2: {
        "name": "Matatabi", "title": "Two-Tails", "nature": ["Fire Release"],
        "traits": ["Blue-flame generation", "Extreme feline speed and agility", "Claw and pounce combat"],
    },
    3: {
        "name": "Isobu", "title": "Three-Tails", "nature": ["Water Release"],
        "traits": ["Coral generation", "Armored shell defense", "High-speed rolling charges and aquatic combat"],
    },
    4: {
        "name": "Son Goku", "title": "Four-Tails", "nature": ["Fire Release", "Earth Release", "Lava Release"],
        "traits": ["Lava Release chakra", "Enormous physical strength", "Volcanic heat and terrain attacks"],
    },
    5: {
        "name": "Kokuo", "title": "Five-Tails", "nature": ["Fire Release", "Water Release", "Boil Release"],
        "traits": ["Boil Release steam pressure", "Explosive physical acceleration", "Horn and charge combat"],
    },
    6: {
        "name": "Saiken", "title": "Six-Tails", "nature": ["Water Release"],
        "traits": ["Corrosive alkali and acid", "Adhesive slime", "Bubble techniques and fluid body defense"],
    },
    7: {
        "name": "Chomei", "title": "Seven-Tails", "nature": ["Wind Release"],
        "traits": ["True flight", "Scale powder and blinding dust", "Cocoon and insect-body techniques"],
    },
    8: {
        "name": "Gyuki", "title": "Eight-Tails", "nature": ["Lightning Release"],
        "traits": ["Ink generation and sealing ink", "Eight prehensile tentacles", "Exceptional strength and durable regeneration"],
    },
    9: {
        "name": "Kurama", "title": "Nine-Tails", "nature": ["Fire Release", "Wind Release"],
        "traits": ["Vast chakra and rapid recovery", "Chakra arms and protective cloaks", "Negative-emotion sensing after sufficient synchronization", "Chakra sharing with allies at high mastery"],
    },
    10: {
        "name": "Ten-Tails", "title": "Ten-Tails", "nature": ["All five basic nature transformations", "Yin-Yang Release"],
        "traits": ["Six Paths-level chakra", "Truth-Seeking Ball potential", "Flight and extreme regeneration", "World-scale sensory and destructive power"],
    },
}

NAME_TO_TAILS = {
    "shukaku": 1, "one tail": 1, "one tails": 1, "one tailed": 1, "ichibi": 1,
    "matatabi": 2, "two tail": 2, "two tails": 2, "two tailed": 2, "nibi": 2,
    "isobu": 3, "three tail": 3, "three tails": 3, "three tailed": 3, "sanbi": 3,
    "son goku": 4, "four tail": 4, "four tails": 4, "four tailed": 4, "yonbi": 4,
    "kokuo": 5, "five tail": 5, "five tails": 5, "five tailed": 5, "gobi": 5,
    "saiken": 6, "six tail": 6, "six tails": 6, "six tailed": 6, "rokubi": 6,
    "chomei": 7, "chōmei": 7, "seven tail": 7, "seven tails": 7, "seven tailed": 7, "nanabi": 7,
    "gyuki": 8, "gyūki": 8, "eight tail": 8, "eight tails": 8, "eight tailed": 8, "hachibi": 8,
    "kurama": 9, "nine tail": 9, "nine tails": 9, "nine tailed": 9, "kyubi": 9, "kyuubi": 9,
    "ten tail": 10, "ten tails": 10, "ten tailed": 10, "juubi": 10, "jubi": 10,
}

GENERAL_CANON_ABILITIES = [
    "Access to the tailed beast's immense chakra reserve",
    "Tailed-beast chakra cloak and progressive tail manifestations",
    "Version 1 and Version 2 transformations when sufficient chakra and control are reached",
    "Partial transformation into the beast's limbs or traits",
    "Full tailed-beast transformation after genuine cooperation or overpowering control",
    "Tailed Beast Ball and derived variants after the necessary ratio and control are mastered",
    "Telepathic communication and combat coordination with the sealed beast",
]

UNMASTERED_DRAWBACKS = [
    "The tailed beast is an independent person and may resist, deceive, withhold chakra, or attempt to seize control.",
    "Fear, rage, injury, exhaustion, or seal damage can trigger involuntary chakra leakage and escalating transformations.",
    "Dense cloaks can burn or tear the host's body, distort judgment, and injure nearby allies.",
    "Forcing more tails than the host can control can cause berserk behavior, memory loss, and a weakened seal.",
    "Villages may fear, isolate, monitor, weaponize, or politically control a known host; Akatsuki and other hunters may target them.",
    "Extraction of the tailed beast is normally fatal to the host without extraordinary intervention.",
]

MASTERED_LIMITS = [
    "The tailed beast remains an independent ally rather than an inventory item; cooperation can be strained by betrayal or conflicting goals.",
    "Large transformations and Tailed Beast Balls still consume immense chakra and can devastate allies, civilians, and terrain.",
    "Sealing disruption, specialized suppression, extraction, and sufficiently powerful opponents remain real threats.",
]

CHAKRA_NATURES = ("Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release")
_NATURE_ALIASES = {
    "fire": "Fire Release", "katon": "Fire Release",
    "wind": "Wind Release", "futon": "Wind Release", "fuuton": "Wind Release",
    "lightning": "Lightning Release", "raiton": "Lightning Release",
    "earth": "Earth Release", "doton": "Earth Release",
    "water": "Water Release", "suiton": "Water Release",
}

# Natural affinity and learned nature transformation are deliberately separate.
# Canon frequently shows experienced shinobi using more than one element; that
# does not retroactively give them several natural affinities.  Multiple innate
# elemental affinities are reserved for an established bloodline/combined
# nature, while special systems such as the Rinnegan are recorded as an explicit
# external mastery source rather than mislabeled as a Kekkei Genkai.
CANON_CHAKRA_PROFILES = {
    "naruto_birth": {
        "primary": "Wind Release", "natural_affinities": ["Wind Release"],
        "proficiencies": [], "mastered_natures": [],
        "discovery_status": "Latent / not yet tested",
        "affinity_source": "Canon: Naruto's natural transformation affinity is Wind Release.",
    },
    "naruto_graduation": {
        "primary": "Wind Release", "natural_affinities": ["Wind Release"],
        "proficiencies": [], "mastered_natures": [],
        "discovery_status": "Latent / not yet tested",
        "affinity_source": "Canon: the Wind affinity exists, but Naruto has not discovered or trained it at graduation.",
    },
    "yahiko_akatsuki": {
        "primary": "Water Release", "natural_affinities": ["Water Release"],
        "proficiencies": [], "mastered_natures": ["Water Release"],
        "discovery_status": "Known and trained",
        "affinity_source": "Canon-established Water Release user.",
    },
    "pain_birth": {
        "primary": "Unconfirmed", "natural_affinities": [],
        "proficiencies": list(CHAKRA_NATURES), "mastered_natures": list(CHAKRA_NATURES),
        "discovery_status": "Natural affinity unconfirmed; all five basic transformations mastered",
        "affinity_source": "Nagato's Rinnegan-enabled mastery and training; not five separate natural affinities.",
        "special_mastery_source": "Rinnegan",
    },
}


def _stated_natures(text):
    lowered = str(text or "").lower().replace("ū", "u").replace("ō", "o")
    found = []
    # Support natural-language lists such as "dual natural Fire and Wind
    # affinities" or "my affinities are Earth and Water".  Keep the capture
    # local to the affinity claim so a later goal like "I want to learn
    # Lightning" is not mistaken for another innate nature.
    listed_claims = []
    for pattern in (
        r"\b(?:dual|multiple|two|three|several)\s+(?:natural\s+)?(.{1,70}?)\s+(?:chakra\s+)?(?:affinities|natures)\b",
        r"\b(?:natural\s+)?(?:chakra\s+)?(?:affinities|natures)\s+(?:are|include|includes)\s+(.{1,70}?)(?:[.;]|$)",
    ):
        listed_claims.extend(match.group(1) for match in re.finditer(pattern, lowered))
    for claim in listed_claims:
        for token, nature in _NATURE_ALIASES.items():
            if re.search(rf"\b{re.escape(token)}\b", claim) and nature not in found:
                found.append(nature)
    for token, nature in _NATURE_ALIASES.items():
        patterns = (
            rf"\b{token}\s+(?:chakra\s+)?(?:nature|affinity|release)\b",
            rf"\b(?:nature|chakra)\s+affinity\s+(?:for|to|with)\s+{token}\b",
            rf"\b(?:natural|innate|primary|secondary)\s+{token}\b",
            rf"\b(?:affinity|affinities|natures?)\s+(?:is|are|include|includes)?\s*.{{0,30}}\b{token}\b",
        )
        matches = [match for pattern in patterns for match in re.finditer(pattern, lowered)]
        # "I want to learn Water Release" describes a goal, not a natural
        # Water affinity. The learned nature will be added later when a real
        # technique/training record establishes it.
        matches = [match for match in matches if not re.search(
            r"(?:want|hope|plan|try|trying|seek|seeking|learn|learning|study|studying|train|training)\s+(?:to\s+)?$",
            lowered[max(0, match.start() - 24):match.start()],
        )]
        if matches and nature not in found:
            found.append(nature)
    return found


def _learning_rates(primary, natural_affinities, proficiencies, special_source=""):
    rates = {}
    for nature in CHAKRA_NATURES:
        if nature == primary:
            rates[nature] = 1.35
        elif nature in natural_affinities:
            rates[nature] = 1.3
        elif nature in proficiencies:
            rates[nature] = 1.0 if not special_source else 1.15
        else:
            rates[nature] = 0.6
    return rates


def build_chakra_affinity_profile(background="", seed="", established=None,
                                  canon_character_id="", kekkei_genkai=False):
    """Create one natural affinity plus distinct learned proficiencies."""
    canon = copy.deepcopy(CANON_CHAKRA_PROFILES.get(str(canon_character_id or ""), {}))
    if canon:
        primary = canon["primary"]
        natural = list(canon.get("natural_affinities", []))
        proficiencies = list(canon.get("proficiencies", []))
        mastered = list(canon.get("mastered_natures", []))
        source = canon.get("special_mastery_source", "")
    else:
        explicit = _stated_natures(background)
        established_primary, established_proficiencies, established_mastered = "", [], []
        if isinstance(established, dict):
            established_primary = str(established.get("primary") or "")
            established_proficiencies = [str(row) for row in established.get("proficiencies", []) if str(row) in CHAKRA_NATURES]
            established_mastered = [str(row) for row in established.get("mastered_natures", []) if str(row) in CHAKRA_NATURES]
        elif isinstance(established, list):
            known = [str(row) for row in established if str(row) in CHAKRA_NATURES]
            established_primary = known[0] if known else ""
            established_proficiencies = known[1:]
            established_mastered = known
        elif str(established or "").strip().lower() not in {"", "unknown", "none", "unconfirmed"}:
            known = [nature for nature in CHAKRA_NATURES if nature.lower() in str(established).lower()]
            established_primary = known[0] if known else ""
        if explicit:
            primary = explicit[0]
        elif established_primary in CHAKRA_NATURES:
            primary = established_primary
        else:
            digest = hashlib.sha256(f"{background}|{seed}|chakra-affinity".encode("utf-8")).digest()
            primary = random.Random(int.from_bytes(digest[:8], "big")).choice(CHAKRA_NATURES)
        multiple_natural_claim = len(explicit) > 1 and bool(re.search(
            r"\b(?:dual|multiple|two|three|several)\b.{0,25}\b(?:affinit|nature)|"
            r"\b(?:affinities|natural natures)\b", str(background), re.I,
        ))
        natural = list(dict.fromkeys([primary, *(explicit[1:] if (multiple_natural_claim or kekkei_genkai) else [])]))
        proficiencies = list(dict.fromkeys([*established_proficiencies,
                                            *(explicit[1:] if not multiple_natural_claim and not kekkei_genkai else [])]))
        mastered = list(dict.fromkeys(established_mastered))
        source = ""
        canon = {
            "discovery_status": "Known" if explicit or established_primary else "Latent / not yet tested",
            "affinity_source": "Character background" if explicit else "Latent nature established at creation",
        }
    additional_natural = [row for row in natural if row != primary]
    requires_kekkei = bool(additional_natural and not canon.get("special_mastery_source"))
    rates = _learning_rates(primary, natural, proficiencies, source)
    profile = {
        "primary": primary,
        "natural_affinities": natural,
        # Legacy alias retained for old saves/UI integrations, but it now means
        # additional *natural* affinities only, never ordinary learned elements.
        "secondary": additional_natural,
        "proficiencies": proficiencies,
        "mastered_natures": mastered,
        "discovery_status": canon.get("discovery_status", "Known"),
        "affinity_source": canon.get("affinity_source", ""),
        "special_mastery_source": source,
        "learning_rates": rates,
        "native_rule": "The natural affinity is the easiest basic nature to discover, learn, stabilize and refine. It does not automatically grant a mastered jutsu.",
        "off_affinity_rule": "Other basic natures remain learnable through sufficient control, instruction and practice. They become proficiencies, not additional natural affinities.",
        "combined_nature_rule": "Using two learned basic natures does not create a combined release. A true elemental combination requires the matching Kekkei Genkai, Kekkei Tōta, or another explicitly established canon-valid mechanism.",
        "requires_kekkei_genkai": requires_kekkei,
        "combined_nature_components": additional_natural and natural or [],
        "external_natures": [],
        "training_evidence": [],
    }
    return profile


def normalize_chakra_affinity_profile(profile=None, legacy="", background="", seed="",
                                      canon_character_id="", kekkei_genkai=False):
    current = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    established = current if current else legacy
    base = build_chakra_affinity_profile(background, seed, established=established,
                                         canon_character_id=canon_character_id,
                                         kekkei_genkai=kekkei_genkai)
    for key, value in current.items():
        if value not in (None, "", [], {}):
            base[key] = copy.deepcopy(value)
    canon_unconfirmed = (
        str(canon_character_id or "") == "pain_birth"
        or (
            str(base.get("primary") or "") == "Unconfirmed"
            and str(base.get("special_mastery_source") or "").lower() == "rinnegan"
        )
    )
    primary = base.get("primary") if base.get("primary") in CHAKRA_NATURES or (canon_unconfirmed and base.get("primary") == "Unconfirmed") else build_chakra_affinity_profile(background, seed, legacy)["primary"]
    base["primary"] = primary
    natural = [row for row in base.get("natural_affinities", []) if row in CHAKRA_NATURES]
    if primary in CHAKRA_NATURES and primary not in natural:
        natural.insert(0, primary)
    base["natural_affinities"] = list(dict.fromkeys(natural))
    base["secondary"] = [row for row in base["natural_affinities"] if row != primary]
    base["proficiencies"] = list(dict.fromkeys(row for row in base.get("proficiencies", []) if row in CHAKRA_NATURES and row not in base["natural_affinities"]))
    base["mastered_natures"] = list(dict.fromkeys(row for row in base.get("mastered_natures", []) if row in CHAKRA_NATURES))
    base["learning_rates"] = _learning_rates(primary, base["natural_affinities"], base["proficiencies"], base.get("special_mastery_source", ""))
    base["requires_kekkei_genkai"] = bool(base["secondary"] and not base.get("special_mastery_source"))
    base["combined_nature_components"] = base["natural_affinities"] if base["requires_kekkei_genkai"] else []
    return base


def jinchuriki_requested(background):
    text = str(background or "").lower()
    return bool(re.search(r"\bjinch[uū]riki\b|\b(?:host|vessel|sealed within me|sealed inside me)\b.{0,35}\b(?:tailed beast|tails?|kurama|shukaku|matatabi|isobu|gy[uū]ki|ch[oō]mei|saiken|koku[oō]|son goku|juubi|j[uū]bi)\b", text))


def jinchuriki_story_evidence(state):
    """Recover a player host transformation that prose established without a patch.

    Older narrators could correctly describe a mid-campaign transfer while
    failing to write ``special['Jinchūriki Profile']``.  This deliberately
    requires language that makes the *player* the recipient; a normal mention
    of Naruto, a tailed-beast attack, or another host cannot trigger it.
    """
    if not isinstance(state, dict) or state.get("world") != "Naruto":
        return {}
    player = str(state.get("name") or "").strip()
    recipient = r"(?:you|your body|me|myself|the player)"
    if player:
        recipient = rf"(?:{recipient}|{re.escape(player)})"
    beast = (r"(?:kurama|shukaku|matatabi|isobu|gy[uū]ki|ch[oō]mei|saiken|koku[oō]|son goku|"
             r"juubi|j[uū]bi|(?:one|two|three|four|five|six|seven|eight|nine|ten)[ -]?tails?|tailed beast)")
    host_patterns = (
        re.compile(rf"{beast}.{{0,90}}(?:sealed|transferred|placed).{{0,35}}(?:into|inside|within).{{0,25}}{recipient}", re.I | re.S),
        re.compile(rf"(?:seal|transfer|extract).{{0,100}}{beast}.{{0,90}}(?:into|inside|within).{{0,25}}{recipient}", re.I | re.S),
        re.compile(rf"{recipient}.{{0,80}}(?:became|becomes|remain(?:s)?|is|as).{{0,30}}(?:the|a)?\s*{beast}.{{0,25}}(?:jinch[uū]riki|host|vessel)", re.I | re.S),
        re.compile(rf"{recipient}.{{0,90}}(?:jinch[uū]riki|host|vessel).{{0,45}}{beast}", re.I | re.S),
    )
    rows = state.get("campaign_canon") if isinstance(state.get("campaign_canon"), list) else []
    acquisition = None
    acquisition_turn = None
    evidence_source = "campaign_canon"
    evidence = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get(key) or "") for key in ("action", "outcome", "summary", "text"))
        if acquisition is None and any(pattern.search(text) for pattern in host_patterns):
            acquisition = index
            acquisition_turn = int(row.get("turn", state.get("turn", 0)) or 0)
        if acquisition is not None and index >= acquisition and re.search(beast + r"|jinch[uū]riki|inner (?:seal|cage)|chakra cloak", text, re.I):
            evidence.append(text)
    if acquisition is None:
        # Compacted campaigns may preserve the decisive transfer only in a
        # chapter summary. Apply the same recipient-bound rule there.
        for row in state.get("chapter_summaries", []) or []:
            text = str(row.get("summary") or "") if isinstance(row, dict) else str(row or "")
            if any(pattern.search(text) for pattern in host_patterns):
                evidence.append(text)
                acquisition = -1
                turns = row.get("turns", []) if isinstance(row, dict) else []
                acquisition_turn = int((turns[0] if turns else state.get("turn", 0)) or 0)
                evidence_source = "chapter_summaries"
                break
    if acquisition is None:
        return {}
    return {
        "text": " ".join(evidence)[-24000:],
        "turn": int(acquisition_turn if acquisition_turn is not None else state.get("turn", 0) or 0),
        "source": evidence_source,
    }


_DOJUTSU_NAME_RE = re.compile(
    r"\b(eternal mangeky[ōo] sharingan|mangeky[ōo] sharingan|sharingan|byakugan|rinnegan|tenseigan|"
    r"[A-Z][A-Za-z'’ -]{1,45}(?:eye|eyes|d[ōo]jutsu))\b", re.I,
)
_DOJUTSU_ACQUIRE_RE = re.compile(
    r"\b(?:awaken(?:s|ed|ing)?|unlock(?:s|ed|ing)?|gain(?:s|ed|ing)?|receive(?:s|d|ing)?|"
    r"obtain(?:s|ed|ing)?|inherit(?:s|ed|ing)?|transplant(?:s|ed|ing)?|manifest(?:s|ed|ing)?|"
    r"activate(?:s|d|ing)?|open(?:s|ed|ing)?|use(?:s|d|ing)?|possess(?:es|ed|ing)?|has|have)\b",
    re.I,
)


def dojutsu_story_evidence(state):
    """Find an ocular power the player has actually acquired during play.

    A mere lore mention is insufficient.  Evidence must be a player-owned
    skill/special field, the player's submitted action using the eye, or prose
    explicitly tying an acquisition/activation to the player.
    """
    if not isinstance(state, dict) or state.get("world") != "Naruto":
        return {}
    player = str(state.get("name") or "").strip()
    skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name, detail in skills.items():
        match = _DOJUTSU_NAME_RE.search(str(name))
        if match:
            return {"name": match.group(1), "text": f"{name}: {detail}", "turn": int(state.get("turn", 0) or 0), "source": "skills", "details": copy.deepcopy(detail)}

    identity = rf"(?:you|your|the player|{re.escape(player)})" if player else r"(?:you|your|the player)"
    rows = state.get("campaign_canon") if isinstance(state.get("campaign_canon"), list) else []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "")
        outcome = " ".join(str(row.get(key) or "") for key in ("outcome", "summary", "text"))
        action_match = _DOJUTSU_NAME_RE.search(action)
        outcome_match = _DOJUTSU_NAME_RE.search(outcome)
        owned_action = bool(action_match and _DOJUTSU_ACQUIRE_RE.search(action))
        owned_outcome = bool(outcome_match and _DOJUTSU_ACQUIRE_RE.search(outcome)
                             and re.search(identity, outcome, re.I))
        if owned_action or owned_outcome:
            match = action_match if owned_action else outcome_match
            return {"name": match.group(1), "text": f"{action} {outcome}"[-8000:],
                    "turn": int(row.get("turn", state.get("turn", 0)) or 0), "source": "campaign_canon"}
    summaries = state.get("chapter_summaries") if isinstance(state.get("chapter_summaries"), list) else []
    for row in reversed(summaries):
        text = str(row.get("summary") or "") if isinstance(row, dict) else str(row or "")
        match = _DOJUTSU_NAME_RE.search(text)
        if match and _DOJUTSU_ACQUIRE_RE.search(text) and re.search(identity, text, re.I):
            return {"name": match.group(1), "text": text[-8000:], "turn": int(state.get("turn", 0) or 0), "source": "chapter_summaries"}
    return {}


def dojutsu_profile_from_evidence(evidence):
    """Create a truthful panel record from a narratively earned ocular power."""
    if not isinstance(evidence, dict) or not evidence.get("name"):
        return {}
    raw_name = str(evidence.get("name") or "Dōjutsu").strip()
    lowered = raw_name.lower()
    if "eternal" in lowered and "sharingan" in lowered:
        name, stage = "Eternal Mangekyō Sharingan", "Eternal Mangekyō"
    elif "mangeky" in lowered and "sharingan" in lowered:
        name, stage = "Mangekyō Sharingan", "Mangekyō"
    elif "sharingan" in lowered:
        name = "Sharingan"
        text = str(evidence.get("text") or "")
        tomoe = re.search(r"\b([123]|one|two|three)[ -]?tomoe\b", text, re.I)
        stage = f"{tomoe.group(1).title()}-Tomoe" if tomoe else "Awakened"
    elif "byakugan" in lowered:
        name, stage = "Byakugan", "Awakened"
    elif "rinnegan" in lowered:
        name, stage = "Rinnegan", "Awakened"
    elif "tenseigan" in lowered:
        name, stage = "Tenseigan", "Awakened"
    else:
        name, stage = raw_name, "Awakened"

    if "sharingan" in name.lower():
        abilities = ["Reads chakra flow and visually perceives fine movement", "Predicts motion from visible muscle and chakra cues", "Copies compatible observed techniques after understanding their execution", "Supports ocular genjutsu that scales with mastery"]
        limits = ["Continuous use consumes chakra and strains the eyes", "It cannot copy bloodline, body, species, or prerequisite-locked abilities", "Prediction can be overwhelmed by speed, obscured vision, or unfamiliar mechanics"]
        counters = ["Break line of sight", "Overwhelm perception with speed or simultaneous threats", "Exploit high chakra cost or physical incompatibility"]
        growth = "Develop tomoe and ocular control through meaningful use; Mangekyō requires a story-valid awakening and introduces unique abilities plus severe eye strain unless later overcome canonically."
    elif name == "Byakugan":
        abilities = ["Near-panoramic vision", "Long-range focus", "Direct perception of chakra pathways and tenketsu"]
        limits = ["Has a small blind spot", "Range and detail depend on training", "Extended focus consumes chakra and concentration"]
        counters = ["Exploit the blind spot", "Use barriers or concealment that specifically disrupt chakra sight"]
        growth = "Extend range, precision, battlefield coverage, and Gentle Fist applications through training."
    elif name == "Rinnegan":
        abilities = ["Perceives chakra at an exceptional level", "Can develop the Six Paths Techniques and other bearer-specific applications"]
        limits = ["Its highest techniques demand enormous chakra and mastery", "Possession does not grant instant command of every path"]
        counters = ["Pressure the bearer before complex techniques are prepared", "Exploit individual path limitations and chakra expenditure"]
        growth = "Master each path separately and discover any bearer-specific applications through world-valid experience."
    else:
        detail = evidence.get("details") if isinstance(evidence.get("details"), dict) else {}
        effect = str(detail.get("effect") or detail.get("description") or "The established ocular effect remains exactly as gained in the campaign.")
        abilities = [effect]
        limits = [str(detail.get("limitation") or "Use follows the chakra cost, bodily strain, and counters established when the eye was gained.")]
        counters = ["Use the established limits of the eye rather than granting an automatic counter."]
        growth = str(detail.get("growth_path") or "Develop new applications without changing the eye's established governing rule.")
    return {
        "name": name, "category": "Dōjutsu", "canon_status": "Canon ocular ability" if name in {"Sharingan", "Mangekyō Sharingan", "Eternal Mangekyō Sharingan", "Byakugan", "Rinnegan", "Tenseigan"} else "Campaign-original world-valid ocular ability",
        "stage": stage, "origin": f"Gained during campaign play; recovered from {evidence.get('source', 'established narrative')}.",
        "abilities": abilities, "limitations": limits, "counters": counters, "growth_path": growth,
        "canon_balance": "Uses the same prerequisites, applications, limits, and attainable ceiling as comparable Naruto ocular abilities.",
        "development_evidence": [str(evidence.get("text") or "Narratively established acquisition")[:1200]],
        "acquired_turn": int(evidence.get("turn", 0) or 0), "non_canon_allowed": True,
    }


def _tails_from_text(text, seed=""):
    lowered = str(text or "").lower().replace("-", " ")
    for token, tails in sorted(NAME_TO_TAILS.items(), key=lambda row: len(row[0]), reverse=True):
        if token in lowered:
            return tails
    digest = hashlib.sha256(f"{text}|{seed}|jinchuriki".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).choice(tuple(range(1, 10)))


def _mastery_from_text(text):
    lowered = str(text or "").lower()
    if re.search(r"\b(perfect jinch[uū]riki|fully mastered|complete mastery|full cooperation|befriended|perfect sync|total control)\b", lowered):
        return "Perfect Jinchuriki", 100
    if re.search(r"\b(cooperative|friends? with|partnered with|partnership|synchronized|shared combat timing|chakra sharing|controlled transformation|bijuu mode|tailed beast mode)\b", lowered):
        return "Cooperative", 72
    if re.search(r"\b(partial control|training with|can use.{0,35}cloak|first tail|one tail cloak|developing(?: control)?)\b", lowered):
        return "Developing", 38
    return "Unmastered", 8


def _jinchuriki_stat_boosts(control, pending=False):
    """Return the exact persistent stat increases granted at creation.

    Transformation-only combat modifiers are intentionally not included here:
    this is the durable increase that ``apply_jinchuriki_start`` writes into
    the save, so the progression panel can never advertise a fictional bonus.
    """
    if pending:
        return {}
    control = max(0, int(control or 0))
    boosts = {"Willpower": 6 + control // 12}
    chakra_control = 12 if control >= 100 else 5 if control >= 70 else 0
    if chakra_control:
        boosts["Chakra Control"] = chakra_control
    return boosts


def build_jinchuriki_profile(background, seed="", legacy=""):
    text = " ".join(str(x or "") for x in (background, legacy)).strip()
    tails = _tails_from_text(text, seed)
    beast = copy.deepcopy(TAILED_BEASTS[tails])
    pending = bool(re.search(r"not yet (?:sealed|completed)|seal not yet|before.{0,30}(?:seal|attack)", text, re.I))
    mastery, control = _mastery_from_text(text)
    if pending:
        mastery, control = "Seal Pending", 0
    mastered = mastery == "Perfect Jinchuriki"
    cooperative = mastery in {"Perfect Jinchuriki", "Cooperative"}
    available = []
    if not pending:
        available.append("Passive access to an abnormally large chakra reserve, limited by the seal and the beast's willingness")
        if mastery in {"Developing", "Cooperative", "Perfect Jinchuriki"}:
            available.extend(["Controlled tailed-beast chakra cloak", "Version 1 transformation", *beast["traits"][:2]])
        if cooperative:
            available.extend(["Version 2 transformation", "Partial transformation", *beast["traits"]])
        if mastered:
            available.extend(["Full tailed-beast transformation", "Tailed Beast Ball", "Tailed-beast chakra sharing and coordinated combat where the beast supports it"])
    drawbacks = list(MASTERED_LIMITS if mastered else UNMASTERED_DRAWBACKS)
    if pending:
        drawbacks = ["The sealing event has not happened yet; the character has no tailed-beast chakra access until it occurs.", *UNMASTERED_DRAWBACKS]
    reserve_multiplier = 1.0 if pending else 1.65 if tails >= 8 else 1.45 if tails >= 4 else 1.35
    if mastered:
        reserve_multiplier += .25
    stat_boosts = _jinchuriki_stat_boosts(control, pending)
    return {
        "name": f"{beast['name']} Jinchuriki",
        "beast": beast["name"], "title": beast["title"], "tails": tails,
        "status": "Awaiting sealing" if pending else "Sealed host",
        "seal": "Not yet completed" if pending else "Established seal; exact design follows the background and campaign canon",
        "mastery": mastery, "control": control,
        "relationship": "Trusted partnership" if mastered else "Working alliance" if cooperative else "Unstable / undeveloped",
        "nature_transformations": beast["nature"],
        "beast_traits": beast["traits"],
        "canonical_abilities": [*GENERAL_CANON_ABILITIES, *beast["traits"]],
        "available_abilities": list(dict.fromkeys(available)),
        "locked_by_mastery": [ability for ability in [*GENERAL_CANON_ABILITIES, *beast["traits"]] if ability not in available],
        "drawbacks": drawbacks,
        "mastered_drawbacks_removed": list(UNMASTERED_DRAWBACKS) if mastered else [],
        "reserve_multiplier": round(reserve_multiplier, 2),
        "chakra_reserve_bonus_percent": round((reserve_multiplier - 1.0) * 100),
        "stat_boosts": stat_boosts,
        "bond_progress": 100 if mastered else 70 if cooperative else 20 if mastery == "Developing" else 0,
        "transformation_stage": "Full Tailed Beast Mode" if mastered else "Version 2 / partial transformation" if cooperative else "Version 1 cloak" if mastery == "Developing" else "Uncontrolled chakra leakage" if not pending else "Unavailable",
        "progression": ["Communicate with the tailed beast as an independent person", "Improve seal knowledge and chakra control", "Survive controlled cloak practice", "Build trust or establish legitimate control", "Achieve coordinated full transformation and Tailed Beast Ball mastery"],
        "independent_beast": True,
        "canon": True,
    }


def normalize_jinchuriki_profile(profile=None, legacy="", background="", seed=""):
    current = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    text = f"{legacy} {background}".strip()
    if not current:
        # A value read from the legacy ``special['Jinchuriki']`` field is
        # already explicit evidence; it often contains only "Nine-Tails
        # (identity concealed)" and therefore has no second host keyword.
        if not str(legacy or "").strip() and not jinchuriki_requested(text) and not re.search(r"(?:tails?|kurama|shukaku|matatabi|isobu|gy[uū]ki|ch[oō]mei|saiken|koku[oō]|son goku).{0,20}(?:seal|host|jinch)", text, re.I):
            return {}
        return build_jinchuriki_profile(text, seed=seed, legacy=legacy)
    beast_text = f"{current.get('beast', '')} {current.get('title', '')} {current.get('tails', '')} {current.get('mastery', '')} {current.get('relationship', '')} {text}"
    base = build_jinchuriki_profile(beast_text, seed=seed, legacy=legacy)
    derived = {"canonical_abilities", "available_abilities", "locked_by_mastery", "drawbacks",
               "mastered_drawbacks_removed", "reserve_multiplier", "chakra_reserve_bonus_percent",
               "stat_boosts", "transformation_stage"}
    for key, value in current.items():
        if key not in derived and value not in (None, "", [], {}):
            base[key] = copy.deepcopy(value)
    # Preserve story-earned original applications while recomputing the canon
    # mastery gates and drawbacks from the current mastery stage.
    base["available_abilities"] = list(dict.fromkeys([*base["available_abilities"], *current.get("available_abilities", [])]))
    base["locked_by_mastery"] = [row for row in base["canonical_abilities"] if row not in base["available_abilities"]]
    custom_drawbacks = [row for row in current.get("drawbacks", []) if row not in UNMASTERED_DRAWBACKS and row not in MASTERED_LIMITS]
    base["drawbacks"] = list(dict.fromkeys([*base["drawbacks"], *custom_drawbacks]))
    base["independent_beast"] = True
    base["canon"] = True
    return base


def apply_jinchuriki_start(stats, profile):
    """Reflect sealed chakra/vitality without pretending it is jutsu mastery."""
    stats = copy.deepcopy(stats)
    if not isinstance(profile, dict) or profile.get("mastery") == "Seal Pending":
        return stats
    boosts = profile.get("stat_boosts") if isinstance(profile.get("stat_boosts"), dict) else _jinchuriki_stat_boosts(profile.get("control", 0))
    for stat, amount in boosts.items():
        if stat in stats and isinstance(amount, (int, float)):
            stats[stat] = max(1, int(stats[stat]) + int(amount))
    return stats
