"""Bleach-specific mechanical reference data.

This module deliberately separates established numbered Kido from the empty
slots the source material never defined.  Empty slots remain valid research
targets: the narrator authors one persistent, setting-consistent spell when a
campaign first discovers it instead of pretending the number cannot exist.
"""
from __future__ import annotations

import re


CANON_HADO = {
    1: ("Sho", "Pushes a target away with concentrated spiritual force."),
    4: ("Byakurai", "Fires a concentrated bolt of white lightning from a fingertip."),
    11: ("Tsuzuri Raiden", "Conducts an electrical current through a touched object."),
    31: ("Shakkaho", "Launches an orb of red spiritual fire that explodes on impact."),
    32: ("Okasen", "Projects a broad arc of yellow spiritual energy."),
    33: ("Sokatsui", "Fires a focused torrent of blue spiritual flame."),
    54: ("Haien", "Projects purple spiritual fire that burns away what it strikes."),
    58: ("Tenran", "Releases a widening tornado-like blast from the caster's hand or weapon."),
    63: ("Raikoho", "Discharges a powerful wave of yellow lightning."),
    73: ("Soren Sokatsui", "Launches a much stronger paired blue-fire blast."),
    88: ("Hiryu Gekizoku Shinten Raiho", "Unleashes an immense electrical blast from both hands."),
    90: ("Kurohitsugi", "Encloses a target in a black spiritual coffin before piercing and crushing it."),
    91: ("Senju Koten Taiho", "Forms multiple points of light that converge in a devastating explosion."),
    96: ("Itto Kaso", "Sacrifices part of the caster's body to create a vast blade-shaped inferno."),
    99: ("Goryutenmetsu", "Raises enormous spiritual dragons that violently tear through the surrounding area."),
}

CANON_BAKUDO = {
    1: ("Sai", "Locks a target's arms behind their back."),
    4: ("Hainawa", "Forms a rope of spiritual energy that entangles a target."),
    8: ("Seki", "Creates a small repulsive shield of spiritual force."),
    9: ("Geki", "Surrounds and paralyzes a target in red light."),
    21: ("Sekienton", "Creates a burst of concealing red smoke."),
    26: ("Kyokko", "Bends light to conceal a target and its spiritual presence."),
    30: ("Shitotsu Sansen", "Pins a target with three triangular points of spiritual force."),
    37: ("Tsuriboshi", "Creates a star-shaped net that catches or supports falling targets."),
    39: ("Enkosen", "Forms a round shield of condensed spiritual energy."),
    58: ("Kakushitsuijaku", "Tracks known spiritual signatures over a broad area."),
    61: ("Rikujokoro", "Immobilizes a target between six bars of light."),
    62: ("Hyapporankan", "Projects a rod that multiplies into many binding rods."),
    63: ("Sajo Sabaku", "Binds a target in heavy chains of spiritual energy."),
    73: ("Tozansho", "Creates an inverted-pyramid barrier around an area."),
    75: ("Gochutekkan", "Drops five immense spiritual pillars to pin a target."),
    77: ("Tenteikura", "Transmits a spoken message to multiple spiritually marked recipients."),
    79: ("Kuyo Shibari", "Pins a target with eight black holes and a ninth central seal."),
    81: ("Danku", "Creates a high-grade defensive wall against incoming techniques."),
    99: ("Kin and Bankin", "Uses layered restraints, bolts, cloth and a final crushing seal."),
}


def kido_skill(branch: str, number: int) -> dict:
    """Return an established spell or a persistent-generation specification."""
    branch = "Hado" if str(branch).lower().startswith("h") else "Bakudo"
    catalog = CANON_HADO if branch == "Hado" else CANON_BAKUDO
    number = max(1, min(99, int(number)))
    if number in catalog:
        name, effect = catalog[number]
        return {
            "name": f"{branch} #{number}: {name}", "branch": branch, "number": number,
            "source_status": "established", "effect": effect,
            "difficulty_band": kido_difficulty_band(number),
        }
    return {
        "name": f"{branch} #{number}: Undiscovered Formula", "branch": branch, "number": number,
        "source_status": "open_slot",
        "effect": "The source material establishes the numbered curriculum but does not reveal this formula. Author it once when researched, then preserve its name, incantation, effect, cost, counters and history for the campaign.",
        "difficulty_band": kido_difficulty_band(number),
    }


def kido_difficulty_band(number: int) -> str:
    number = int(number)
    if number <= 20:
        return "Academy"
    if number <= 49:
        return "Seated-officer study"
    if number <= 69:
        return "Advanced"
    if number <= 89:
        return "Expert"
    return "Forbidden or captain-class study"


def kido_reference_summary() -> dict:
    return {
        "range": "Hadō #1-99 and Bakudō #1-99",
        "established_hado": [f"#{n} {row[0]}" for n, row in sorted(CANON_HADO.items())],
        "established_bakudo": [f"#{n} {row[0]}" for n, row in sorted(CANON_BAKUDO.items())],
        "open_slot_rule": "Unshown numbers are valid research targets. Generate one world-fitting spell on first discovery and persist it thereafter.",
    }


def owns_release(background: str, release: str) -> bool:
    """Require an ownership claim, not merely a goal to eventually learn it."""
    text = str(background or "")
    release = re.escape(release)
    return bool(re.search(
        rf"\b(?:already\s+)?(?:have|has|possess|possesses|know|knows|unlocked|achieved|mastered|can\s+use|start(?:s|ing)?\s+with)\b[^.!?]{{0,55}}\b{release}\b|"
        rf"\b{release}\b[^.!?]{{0,55}}\b(?:is\s+already\s+unlocked|is\s+achieved|from\s+the\s+start)\b",
        text, re.I,
    ))


def academy_kido_skills(archetype: str, senior: bool = False) -> dict:
    """Concrete spells a capable academy student/graduate can begin knowing."""
    spells = [("Hado", 1), ("Hado", 4), ("Bakudo", 1), ("Bakudo", 4)]
    if senior:
        spells.extend([("Bakudo", 8), ("Bakudo", 9)])
    if "kido" in str(archetype or "").lower():
        spells.extend([("Hado", 11), ("Hado", 31), ("Bakudo", 21), ("Bakudo", 30)])
    result = {}
    for branch, number in spells:
        row = kido_skill(branch, number)
        result[row["name"]] = {
            "rank": "Academy Proficient" if number <= 9 else "Academy Trained",
            "bonus": 5 if number <= 9 else 4,
            "description": row["effect"],
            "effect": row["effect"],
            "limitation": "Full power requires sufficient Reiryoku, control and the incantation; chantless casting is weaker until mastered.",
            "growth_path": f"Improve Kidō control and learn progressively harder {branch} formulae.",
            "combat_usable": branch == "Hado" or number not in {21, 58, 77},
            "effect_type": "damage" if branch == "Hado" else "debuff",
            "kido": {"branch": branch, "number": number, "source_status": "established"},
        }
    return result


def zanpakuto_tracks(has_shikai: bool = False, has_bankai: bool = False) -> list[dict]:
    tracks = []
    if not has_shikai:
        tracks.append({
            "name": "Learn the Zanpakutō's Name", "source_feat": "A Shinigami earns Shikai through recognition and communion with their blade spirit.",
            "status": "in_progress", "met_requirements": ["Received an Asauchi", "Completed foundational academy training"],
            "missing_requirements": ["Establish communication with the blade spirit", "Discover its true name", "Pass a character-specific inner-world trial"],
            "next_steps": ["Practice Jinzen", "Fight and train with the sealed blade", "Record how the spirit answers the character's choices"],
            "notes": "At the breakthrough, the GM generates one original name, release command, spirit, inner world, ability, cost and counterplay from the complete campaign history.",
        })
    if not has_bankai:
        tracks.append({
            "name": "Develop Bankai", "source_feat": "Bankai is a later evolution of the same Zanpakutō identity, not an unrelated second power.",
            "status": "locked" if not has_shikai else "in_progress",
            "met_requirements": (["Shikai achieved"] if has_shikai else []),
            "missing_requirements": (["Achieve Shikai first"] if not has_shikai else []) + ["Manifest the Zanpakutō spirit", "Reach the required spiritual capacity", "Complete its personal mastery trial"],
            "next_steps": ["Deepen Shikai mastery", "Learn materialization or another lore-valid method", "Resolve the blade spirit's central conflict"],
            "notes": "The eventual Bankai must evolve the established Shikai theme and reflect everything learned since its awakening.",
        })
    return tracks


BLEACH_GM_RULES = """
BLEACH MECHANICAL CONTRACT
- Currency is background lore, not a tracked Bleach resource. Kan and Yen may be mentioned when a scene genuinely involves them, but never maintain balances, routine wages, costs, debts or price-gated purchases. Ordinary expenses and reasonable mundane purchases simply happen. Gate important equipment and scarce supplies through squad rank, authorization, favors, requisitions, availability and narrative consequences instead.
- Spiritual Nature is authoritative. Do not give Shinigami-only fields or techniques to another nature unless a recorded transformation or hybrid state justifies them.
- Every original Soul Reaper begins with an unnamed Asauchi, academy fundamentals and a real Kidō curriculum. They do not begin with Shikai or Bankai unless the creation background explicitly says they already possess that release.
- Squad placement is a narrative decision. Academy seniors first graduate; recent graduates attend division interviews or assignment proceedings. Let the player express preferences. Exceptional talent, patronage or a division's active interest can give a genuine choice; otherwise captains and institutional needs answer in character and offer concrete placements or conditions.
- Shikai is earned by learning the Zanpakutō spirit's identity and true name. At the exact breakthrough, author one original Zanpakutō Profile from the character's background plus their full recorded actions, relationships, training, wounds, values and choices. Record name, sealed appearance, spirit, inner world, release command, Shikai form/effect, costs, limitations, counters and growth route in special.Zanpakuto Profile and add the release as a normal skill. Never copy a canon character's release.
- Bankai evolves that same established identity after its prerequisites. At its breakthrough, add a Bankai name, manifestation, evolved mechanics, cost, counterplay and mastery path to the existing profile and skills. Never generate an unrelated second theme.
- Kidō is learnable rather than class-locked. Canon Hadō and Bakudō retain their established number, name and function. Any number from 1-99 that the manga/anime/filler material never defined still logically exists: when the player researches or learns one, create a fitting original spell for that exact branch/number, scaled broadly by its number and the character's Kidō/control, with a unique name, incantation, effect, cost and counter. Mark it campaign-original, add it to skills and codex, and never regenerate it differently later.
- Release and high-number Kidō attempts are progression goals, not automatic refusals. Focused training always produces meaningful progress. Use a difficult roll only for an extreme time compression, a dangerous forced awakening, or a genuine leap beyond current capacity.
- Realm travel has gates: Senkaimon/Dangai connect the Living World and Soul Society, Garganta connects Hueco Mundo, and Royal Realm/Wandenreich access requires its established special route. Do not treat the map as ordinary walkable geography.
""".strip()
