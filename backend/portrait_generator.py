"""AI portrait generation, identity-preserving updates, and disk caching.

Portraits are deliberately keyed only by visually relevant campaign state.
Ordinary turns do not spend another image request; appearance, form, clothing,
equipment, age, or other major visual changes do.
"""
import base64
import copy
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import shutil
from pathlib import Path

from util import DATA_DIR, ASSET_ROOT, safe_filename, world_slug, ai_text


PORTRAIT_CACHE_DIR = DATA_DIR / "portraits"
PORTRAIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Rough $/image estimates for cloud portrait generation at 1024x1024, by
# quality tier. Unlike MODEL_PRICING_PER_1M in ai_client.py these are not
# pulled from a metered `usage` field (the Images API doesn't return one) —
# they're a flat per-call estimate, so treat the total as directional, not
# exact. Local image generation is always free.
PORTRAIT_COST_ESTIMATE_USD = {"low": 0.02, "medium": 0.07, "high": 0.19, "auto": 0.07}

_portrait_usage = {"generated": 0, "cost_usd": 0.0}

# Approved canon-start portraits ship with the game so selecting one of these
# characters never needs an image-model request.  Transformation portraits
# remain separate: once a special form is active the normal cache/generation
# path takes over until that form receives its own approved bundled asset.
CANON_START_PORTRAITS = {
    "luffy_departure": "luffy_departure.webp",
    "zoro_shells": "zoro_shells.webp",
    "gon_departure": "gon_departure.webp",
    "kurapika_exam": "kurapika_exam.webp",
    "naruto_birth": "naruto_birth.webp",
    "yahiko_akatsuki": "yahiko_akatsuki.webp",
    "pain_birth": "pain_birth.webp",
    "naruto_graduation": "naruto_graduation.webp",
    "jinhyeok_tower": "jinhyeok_tower.webp",
    "grid_pagma": "grid_pagma.webp",
    "rimuru_awakens": "rimuru_awakens.webp",
    "ichigo_series_start": "ichigo_series_start.webp",
    "yuji_finger": "yuji_finger.webp",
    "gojo_inventory": "gojo_inventory.webp",
    "yuta_enrolls": "yuta_enrolls.webp",
    "megumi_finger": "megumi_finger.webp",
    "maki_second_year": "maki_second_year.webp",
}

# Approved alternate-form art is deliberately narrow: each asset is tied to
# a canon identity and an explicit form family. Original characters using the
# same technique still keep their own appearance through the normal cached
# generation path instead of turning into the canon character pictured here.
CANON_FORM_PORTRAITS = {
    "naruto_birth": (
        (re.compile(r"\b(?:eighth|8th|death)\s+gate\b|\bgate\s+of\s+death\b", re.I), "forms/naruto/naruto_eighth_gate_death.png"),
        (re.compile(r"\b(?:sixth|6th|seventh|7th)\s+gate\b|\bgate\s+(?:six|6|seven|7)\b", re.I), "forms/naruto/naruto_eight_gates_6_to_7.png"),
        (re.compile(r"\b(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s+gate\b|\bgate\s+(?:one|1|two|2|three|3|four|4|five|5)\b|\beight\s+gates?\b", re.I), "forms/naruto/naruto_eight_gates_1_to_5.png"),
    ),
    "naruto_graduation": (
        (re.compile(r"\b(?:eighth|8th|death)\s+gate\b|\bgate\s+of\s+death\b", re.I), "forms/naruto/naruto_eighth_gate_death.png"),
        (re.compile(r"\b(?:sixth|6th|seventh|7th)\s+gate\b|\bgate\s+(?:six|6|seven|7)\b", re.I), "forms/naruto/naruto_eight_gates_6_to_7.png"),
        (re.compile(r"\b(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s+gate\b|\bgate\s+(?:one|1|two|2|three|3|four|4|five|5)\b|\beight\s+gates?\b", re.I), "forms/naruto/naruto_eight_gates_1_to_5.png"),
    ),
}


def portrait_usage():
    return dict(_portrait_usage)


def _record_portrait_usage(provider, quality):
    _portrait_usage["generated"] += 1
    if provider == "cloud":
        _portrait_usage["cost_usd"] += PORTRAIT_COST_ESTIMATE_USD.get(quality, 0.07)

WORLD_PORTRAIT_STYLES = {
    "One Piece": (
        "the One Piece anime/manga's own house style: whimsical high-energy ocean adventure manga; "
        "exaggerated but appealing anatomy; eccentric readable silhouette; bold variable black ink; "
        "flat saturated cel colors; playful expressive facial construction"
    ),
    "Naruto": (
        "the Naruto anime/manga's own house style: dynamic hand-inked ninja action manga; angular "
        "clean silhouette; restrained earth colors with one vivid accent; crisp cel shading; "
        "expressive eyes and practical shinobi design"
    ),
    "Hunter x Hunter": (
        "the Hunter x Hunter anime/manga's own house style: crisp strategic adventure manga; clean "
        "variable ink lines; bold simple color shapes; natural expressive face; subtle crosshatching; "
        "energetic but grounded"
    ),
    "Solo Max-Level Newbie": (
        "a premium Korean action webtoon's house style, matching this series' own presentation: "
        "semi-realistic anatomy; precise digital linework; smooth layered cel shading; dramatic "
        "luminous system accents and polished finish"
    ),
    "Overgeared": (
        "a high-detail Korean fantasy webtoon's house style, matching this series' own presentation: "
        "heroic semi-realistic anatomy; richly rendered metal, leather, and cloth; crisp digital "
        "linework; warm cinematic highlights"
    ),
    "Reincarnated as a Slime": (
        "the Reincarnated as a Slime anime's own house style: vibrant modern isekai anime; friendly "
        "expressive character design; clean graceful linework; luminous soft cel shading; jewel-like "
        "magical color accents"
    ),
    "Bleach": (
        "an original high-contrast supernatural sword manga aesthetic suited to Bleach: elegant fashion-forward "
        "silhouette, spare confident black ink, sharp expressive eyes, flowing black-and-white cloth, restrained "
        "cel color and cool spiritual highlights; never copy a named canon character"
    ),
    "Jujutsu Kaisen": (
        "an original modern occult action-manga aesthetic: bold economical ink, sharp expressive anatomy, practical contemporary clothing, "
        "high-contrast cel shadows, unnerving curse motifs and restrained violet-black cursed-energy accents; never copy a canon character"
    ),
    "Custom World": (
        "cinematic anime-inspired RPG concept illustration; elegant ink contours; painterly cel "
        "shading; detailed materials; distinctive original silhouette"
    ),
}

WORLD_BACKDROPS = {
    "One Piece": "subdued turquoise ocean and bright sky with distant sails",
    "Naruto": "subdued mountain village rooftops, forest haze, and warm late-afternoon light",
    "Hunter x Hunter": "subdued wilderness trail meeting a distant modern city",
    "Solo Max-Level Newbie": "dark crystalline tower hall with faint cyan rings and no readable text",
    "Overgeared": "medieval forge workshop with amber furnace glow",
    "Reincarnated as a Slime": "great forest settlement with warm wooden roofs and magical motes",
    "Bleach": "white-walled spirit-city roofs beneath a dark sky with pale blue spiritual motes",
    "Jujutsu Kaisen": "a dim modern Japanese street or old jujutsu school courtyard with subtle violet-black cursed-energy traces",
    "Custom World": "misty crossroads where forest, city, mountains, and stars blend softly",
}

VISUAL_SPECIAL_KEYS = re.compile(
    r"species|race|form|transformation|evolution|clan|bloodline|devil fruit|body|eyes|hair|mark|curse|mutation|zanpakuto|shikai|bankai|spiritual nature|innate technique|heavenly restriction|cursed spirit",
    re.I,
)
VISIBLE_EQUIPMENT_KEYS = re.compile(
    r"weapon|sword|blade|bow|gun|armor|armour|outfit|clothing|robe|cloak|coat|shirt|pants|dress|uniform|head|hat|mask|glove|boot|shoe|shield|accessor|ring|neck|ear|waist|belt",
    re.I,
)
FORM_ACTIVATION_RE = re.compile(
    r"\b(?:activate|awaken|open|enter|invoke|manifest|unleash|release|assume|transform(?:ing)?\s+into|use|"
    r"draw\s+on|channel|cloak\s+myself\s+in|wrap\s+myself\s+in)\b",
    re.I,
)
FORM_NAME_RE = re.compile(
    r"\b(?:tailed beast mode|bijuu mode|baryon mode|version [12](?: cloak)?|chakra cloak|"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten)[- ]tails?(?: chakra)? cloak|tailed[- ]beast chakra cloak|"
    r"sharingan|mangeky[ōo] sharingan|eternal mangeky[ōo] sharingan|byakugan|rinnegan|d[ōo]jutsu|"
    r"shikai|bankai|domain expansion|heavenly restriction|released form|awakening|transformation)\b",
    re.I,
)
FORM_STOP_RE = re.compile(
    r"\b(?:return|revert|change)\s+(?:back\s+)?to\s+(?:normal|base form)|"
    r"\b(?:deactivate|dismiss|end|cancel|drop|close|suppress)\b.{0,35}\b(?:form|transformation|cloak|"
    r"d[ōo]jutsu|sharingan|byakugan|rinnegan|shikai|bankai|domain)\b",
    re.I,
)


def campaign_portrait_id(state):
    explicit = str(state.get("campaign_id", "")).strip()
    if explicit:
        return safe_filename(explicit)[:40]
    seed = "|".join(str(state.get(k, "")) for k in ("name", "world", "background"))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def affiliation_text_for(state):
    """Shared by visual_state (portrait regeneration trigger) and
    portrait_prompt (the actual prompt) so a change here is guaranteed to
    both describe AND actually redraw the portrait — an affiliation join
    that isn't part of the regeneration signature would silently never
    reach the art even with a correct prompt."""
    affiliations = state.get("affiliations", [])
    def _one(a):
        if isinstance(a, dict):
            faction = str(a.get("faction") or a.get("name") or "").strip()
            rank = str(a.get("rank") or "").strip()
            status = str(a.get("status") or "").strip()
            text = " — ".join(p for p in (faction, rank) if p)
            return f"{text} ({status})" if text and status and status.lower() != "active" else text
        return ai_text(a)
    text = "; ".join(t for t in (_one(a) for a in affiliations) if t) if isinstance(affiliations, list) else ""
    return text or "none recorded"


def visible_equipment_for(state):
    """Return only gear that can actually change a portrait silhouette.

    Narrative inventory updates such as ore, medicine, keys, quest items and
    carried supplies must not create a new paid portrait cache key.
    """
    equipment = state.get("equipment", {})
    if not isinstance(equipment, dict):
        return equipment if VISIBLE_EQUIPMENT_KEYS.search(str(equipment)) else {}
    visible = {}
    for slot, value in equipment.items():
        text = f"{slot} {ai_text(value)}"
        if VISIBLE_EQUIPMENT_KEYS.search(text):
            visible[str(slot)] = value
    return visible


def _known_visual_forms(state):
    """Return authored form names and descriptions that can affect a portrait."""
    special = state.get("special", {}) if isinstance(state.get("special"), dict) else {}
    forms = []
    host = special.get("Jinchūriki Profile") if isinstance(special.get("Jinchūriki Profile"), dict) else {}
    if host.get("beast"):
        for label in ("Chakra Cloak", "Version 1", "Version 2", "Partial Transformation", "Tailed Beast Mode", "Baryon Mode"):
            forms.append((label, "Jinchūriki transformation", f"{label} powered by {host.get('beast')}; show the established chakra mantle, tails, markings, eyes, and beast traits appropriate to this exact stage."))
        beast = str(host.get("beast") or "Tailed Beast").strip()
        title = str(host.get("title") or "Tailed Beast").strip()
        cloak_details = f"A tailed-beast chakra cloak powered by {beast}; show the established chakra mantle, tails, markings, eyes, and beast traits appropriate to the current control stage."
        for alias in (f"{beast} Chakra Cloak", f"{beast} Cloak", f"{title} Chakra Cloak", f"{title} Cloak", "Tailed-Beast Chakra Cloak"):
            forms.append((alias, "Jinchūriki transformation", cloak_details))
    for key in ("Dōjutsu Profile", "Kekkei Genkai Profile"):
        profile = special.get(key) if isinstance(special.get(key), dict) else {}
        if profile.get("name"):
            forms.append((str(profile["name"]), str(profile.get("category") or key.replace(" Profile", "")), f"{profile['name']} is visibly active. Reflect its established physical or ocular appearance and current stage ({profile.get('stage', 'established')}) without adding a new ability."))
    zanpakuto = special.get("Zanpakuto Profile") if isinstance(special.get("Zanpakuto Profile"), dict) else {}
    for stage, name_key, detail_key in (("Shikai", "shikai_name", "shikai_form"), ("Bankai", "bankai_name", "bankai_manifestation")):
        name = str(zanpakuto.get(name_key) or special.get(stage) or "").strip()
        if name and not re.match(r"^(?:none|unknown|unachieved)$", name, re.I):
            details = ai_text(zanpakuto.get(detail_key)) or ai_text(zanpakuto.get(f"{stage.lower()}_effect"))
            forms.append((name, stage, f"{stage} is actively released as {name}. {details}".strip()))
            forms.append((stage, stage, f"{stage} is actively released as {name}. {details}".strip()))
    for skill_name, detail in (state.get("skills", {}) or {}).items():
        if not isinstance(detail, dict):
            continue
        effect = str(detail.get("effect_type") or "").lower()
        category = str(detail.get("category") or "").lower()
        if effect == "transform" or category == "transformation" or re.search(r"domain expansion", str(skill_name), re.I):
            forms.append((str(skill_name), "Domain Expansion" if re.search(r"domain expansion", str(skill_name), re.I) else "Transformation", ai_text(detail.get("description") or detail.get("effect") or detail.get("mechanics"))))
    return forms


def set_active_portrait_form(state, name, kind="Transformation", details="", source="story"):
    identity = state.setdefault("portrait_identity", {})
    incoming = {"name": str(name or kind).strip()[:160], "kind": str(kind or "Transformation").strip()[:80],
                "details": str(details or "").strip()[:700], "source": str(source or "story")[:40]}
    changed = identity.get("active_form") != incoming
    identity["active_form"] = incoming
    return changed


def clear_active_portrait_form(state):
    identity = state.setdefault("portrait_identity", {})
    changed = bool(identity.get("active_form"))
    identity["active_form"] = {}
    return changed


def sync_active_portrait_form(state, actions, narrative="", events=None):
    """Track visible special states without relying on the narrator to patch art.

    A form persists across turns until the player or story explicitly ends it.
    Returning to base form therefore reuses the cached original portrait at no
    image cost, while the first use of a new form creates one distinct cache key.
    """
    action_text = " ".join(str(x) for x in (actions if isinstance(actions, list) else [actions]) if str(x).strip())
    combined = f"{action_text}\n{narrative}".strip()
    if not combined:
        return False
    if FORM_STOP_RE.search(action_text) or re.search(r"\b(?:form|cloak|release|domain|d[ōo]jutsu)\b.{0,28}\b(?:fades?|ends?|deactivates?|drops?|closes?|reverts?)\b", narrative, re.I):
        return clear_active_portrait_form(state)
    failed = bool(re.search(r"\b(?:fails?|failed|cannot|could not|does not activate|did not activate)\b", narrative, re.I))
    known_forms = _known_visual_forms(state)
    if failed or not (FORM_ACTIVATION_RE.search(action_text) and (FORM_NAME_RE.search(combined) or any(name.lower() in combined.lower() for name, _, _ in known_forms))):
        return False
    candidates = sorted(known_forms, key=lambda row: len(row[0]), reverse=True)
    matched = next((row for row in candidates if row[0].lower() in combined.lower()), None)
    if matched:
        return set_active_portrait_form(state, *matched, source="story")
    raw = FORM_NAME_RE.search(action_text)
    name = raw.group(0).title() if raw else "Active Transformation"
    kind = "Domain Expansion" if "domain" in name.lower() else "Dōjutsu" if re.search(r"eye|d[ōo]jutsu|sharingan|byakugan|rinnegan", name, re.I) else name
    return set_active_portrait_form(state, name, kind, f"{name} is visibly active and should alter the portrait according to its established campaign description.", source="story")


def visual_state(state):
    special = state.get("special", {}) if isinstance(state.get("special"), dict) else {}
    visual_special = {k: v for k, v in special.items() if VISUAL_SPECIAL_KEYS.search(str(k))}
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    age = state.get("age", "")
    try:
        age_num = int(age)
        age_band = "child" if age_num < 13 else "teen" if age_num < 18 else "young adult" if age_num < 30 else "adult" if age_num < 50 else "older adult"
    except (TypeError, ValueError):
        age_band = str(age or "unspecified")
    raw_traits = state.get("portrait_traits", []) if isinstance(state.get("portrait_traits"), list) else []
    traits, seen = [], set()
    for value in raw_traits:
        text = ai_text(value)
        if text and text.lower() not in seen:
            traits.append(text); seen.add(text.lower())
    # The signature intentionally excludes narrative-only fields such as
    # position, reputation, class labels, and ordinary status changes. A new
    # paid portrait is warranted by a visible body/clothing/form change, not
    # by every mechanical update to the character sheet.
    return {
        "world": state.get("world", "Custom World"),
        "age_band": age_band,
        "appearance": state.get("appearance_desc", ""),
        "traits": traits,
        "equipment": visible_equipment_for(state),
        "affiliations": affiliation_text_for(state),
        "visual_special": visual_special,
        "canonical_identity": identity.get("canonical_description", ""),
        "temporary_traits": identity.get("temporary_traits", []),
        "active_form": identity.get("active_form", {}),
    }


def portrait_signature(state):
    raw = json.dumps(visual_state(state), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def derived_appearance(state):
    appearance = str(state.get("appearance_desc", "")).strip()
    if appearance:
        return appearance
    special = state.get("special", {}) if isinstance(state.get("special"), dict) else {}
    origin = special.get("Origin") or "local traveler"
    archetype = special.get("Archetype") or "adventurer"
    age = state.get("age") or "young adult"
    return (
        f"A {age} {origin} beginning as a {archetype}. Invent a coherent original face, hair, body type, "
        "and practical clothing that fit those traits and the setting; preserve them in later edits."
    )


def portrait_prompt(state, preserve_identity=False):
    world = state.get("world", "Custom World")
    style = WORLD_PORTRAIT_STYLES.get(world, WORLD_PORTRAIT_STYLES["Custom World"])
    backdrop = WORLD_BACKDROPS.get(world, WORLD_BACKDROPS["Custom World"])
    traits = "; ".join(ai_text(x) for x in state.get("portrait_traits", []) if ai_text(x)) or "none recorded"
    equipment = visible_equipment_for(state)
    if isinstance(equipment, dict):
        equipment_text = "; ".join(f"{k}: {v}" for k, v in equipment.items()) or "ordinary setting-appropriate clothing"
    else:
        equipment_text = str(equipment) or "ordinary setting-appropriate clothing"
    affiliations_text = affiliation_text_for(state)
    special = visual_state(state)["visual_special"]
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    canonical = identity.get("canonical_description") or derived_appearance(state)
    temporary = "; ".join(str(x) for x in identity.get("temporary_traits", [])) or "none"
    active_form = identity.get("active_form") if isinstance(identity.get("active_form"), dict) else {}
    active_form_text = json.dumps(active_form, ensure_ascii=False, default=str) if active_form else "none; render the normal base appearance"
    identity_rule = (
        "Use the supplied previous portrait as the same person. Preserve facial identity, apparent age, body type, "
        "skin tone, and all unchanged features; edit only what the current description requires."
        if preserve_identity else
        "Create one consistent, memorable original player character identity from the description."
    )
    return f"""Create a polished square RPG character portrait.
WORLD: {world}
CHARACTER: {state.get('name') or 'Traveler'}
CANONICAL IDENTITY / APPEARANCE: {canonical}
ADDITIONAL VISIBLE TRAITS: {traits}
TEMPORARY VISIBLE CHANGES: {temporary}
ACTIVE SPECIAL FORM: {active_form_text}
CURRENT CLOTHING / EQUIPMENT: {equipment_text}
AFFILIATIONS / FACTIONS: {affiliations_text}
VISIBLE WORLD-SYSTEM TRAITS: {json.dumps(special, ensure_ascii=False, default=str)}
POSITION / ROLE: {state.get('position') or 'new adventurer'}

IDENTITY: {identity_rule}
STYLE: Render fully and unmistakably in {style}. Commit completely to it — line weight, shading technique, color saturation, proportions, and rendering approach should all read as drawn in that exact style, not a generic anime/fantasy-art default that merely gestures at it. The goal is a portrait that would look at home next to official art for this series. The only boundaries: never depict an actual named canon character's likeness, never reproduce a specific existing panel/cover/official artwork, and never copy a franchise logo or exact insignia design — the ORIGINAL character described above, drawn fully in the series' own visual style.
AFFILIATION MARKERS: If AFFILIATIONS / FACTIONS lists an active membership in a known in-world faction/order/village, dress the character with that group's ordinary everyday visual identifiers, fitting their actual rank/role — e.g. a shinobi affiliated with a hidden village wears a forehead-protector-style headband, an Akatsuki-type organization's member wears its signature dark cloak, a knight order's member wears its house colors or sigil-bearing surcoat. Render these as generic in-fiction garments/props appropriate to the affiliation (a plain metal-plate headband, a cloud-patterned cloak) rather than reproducing any franchise's exact official logo or insignia design.
COMPOSITION: one character only, waist-up, centered three-quarter view, face unobstructed, safe margins, made for a compact game portrait card.
BACKDROP: {backdrop}; atmospheric and subdued so the character dominates.
CONSTRAINTS: no text, captions, logo, watermark, border, UI, split panel, extra person, canon character likeness, or franchise emblem. Reflect every major physical, clothing, equipment, and transformation detail that is currently recorded. Show a Dōjutsu, tailed-beast cloak/form, Shikai, Bankai, Domain Expansion, release, or transformation ONLY when ACTIVE SPECIAL FORM names it. When ACTIVE SPECIAL FORM is none, show the character's normal base appearance even if their profile records powers they can activate."""


def fallback_url(state):
    slug = world_slug(state.get("world", "Custom World"))
    for candidate in (slug, "Custom_World"):
        for extension in ("webp", "png"):
            p = ASSET_ROOT / "generated_portraits" / f"{candidate}.{extension}"
            if p.exists():
                return f"/assets/generated_portraits/{candidate}.{extension}"
    return None


def canon_start_portrait_url(state):
    identity = state.get("player_identity") if isinstance(state.get("player_identity"), dict) else {}
    canon_id = identity.get("canon_character_id") or state.get("canon_character_id")
    filename = CANON_START_PORTRAITS.get(str(canon_id or ""))
    if not filename:
        return None
    path = ASSET_ROOT / "canon_portraits" / filename
    return f"/assets/canon_portraits/{filename}" if path.exists() else None


def canon_form_portrait_url(state, active_form=None):
    identity = state.get("player_identity") if isinstance(state.get("player_identity"), dict) else {}
    canon_id = str(identity.get("canon_character_id") or state.get("canon_character_id") or "")
    if active_form is None:
        portrait_identity = state.get("portrait_identity") if isinstance(state.get("portrait_identity"), dict) else {}
        form = portrait_identity.get("active_form") if isinstance(portrait_identity.get("active_form"), dict) else {}
    else:
        form = active_form if isinstance(active_form, dict) else {}
    form_text = " ".join(str(form.get(key) or "") for key in ("name", "kind", "details"))
    if not form_text.strip():
        return None
    for pattern, filename in CANON_FORM_PORTRAITS.get(canon_id, ()):
        if pattern.search(form_text):
            path = ASSET_ROOT / "canon_portraits" / Path(filename)
            if path.exists():
                return f"/assets/canon_portraits/{filename}"
    return None


def cached_path(state):
    p = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    return p if p.exists() else None


def latest_path(state):
    candidates = [p for p in PORTRAIT_CACHE_DIR.glob(f"{campaign_portrait_id(state)}-*.*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def reference_path(state):
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    name = Path(str(identity.get("reference_file", ""))).name
    if not name:
        return None
    path = PORTRAIT_CACHE_DIR / name
    return path if path.exists() else None


def portrait_ready(settings):
    if not settings.get("portrait_generation_enabled", True):
        return False
    provider = settings.get("image_provider") if settings.get("image_provider") in {"local", "cloud"} else settings.get("provider", "local")
    if provider == "cloud":
        return bool(settings.get("api_key") and settings.get("image_model", "gpt-image-2"))
    return bool(settings.get("local_image_model"))


def portrait_view(state, settings):
    signature = portrait_signature(state)
    cached = cached_path(state)
    reference = reference_path(state)
    # A visible transformation/effect deliberately changes the cache key.
    # Generation is asynchronous, so there is a short period where the new
    # key has no file yet.  Keep the newest portrait for this campaign on
    # screen during that period instead of returning only generic art (or
    # None) and making the character vanish between turns.
    previous = latest_path(state) if not cached and not reference else None
    active_form = copy.deepcopy((state.get("portrait_identity") or {}).get("active_form", {})) if isinstance(state.get("portrait_identity"), dict) else {}
    # A user-provided reference remains authoritative.  Otherwise the
    # approved base portrait outranks old generated cache files for canon
    # starts, giving every new and existing save the same correct likeness.
    canon_url = canon_form_portrait_url(state, active_form) if active_form else canon_start_portrait_url(state)
    image = cached or reference or previous
    if reference:
        image_url = f"/portrait-cache/{reference.name}"
    elif canon_url:
        image_url = canon_url
    elif image:
        image_url = f"/portrait-cache/{image.name}"
    else:
        image_url = fallback_url(state)
    return {
        "_portrait_signature": signature,
        "_portrait_image": image_url,
        "_portrait_generated": bool(cached and not canon_url and not reference),
        "_portrait_reference": bool(reference),
        "_portrait_canon": bool(canon_url and not reference),
        "_portrait_previous": bool(previous and not canon_url and not reference),
        "_portrait_active_form": active_form,
        "_portrait_generation_enabled": bool(settings.get("portrait_generation_enabled", True)),
        "_portrait_auto_generate": bool(settings.get("portrait_auto_generate", False) and not canon_url),
        "_portrait_generation_ready": portrait_ready(settings),
        "_portrait_regeneration_policy": "Only significant visible appearance, equipment, affiliation clothing, or transformation changes create a new cache key; the last valid portrait remains visible until its replacement loads.",
    }


def _request_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _multipart(fields, image_path):
    boundary = "----Worldwalker" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    suffix = image_path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image[]"; filename="portrait{suffix or ".png"}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(), image_path.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return boundary, b"".join(chunks)


def _decode_image(data):
    items = data.get("data", [])
    if not items:
        raise RuntimeError("The image server returned no portrait.")
    item = items[0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"], validate=True)
    elif item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=120) as response:
            raw = response.read()
    else:
        raise RuntimeError("The image server response did not contain image data.")
    if len(raw) < 1000 or len(raw) > 40 * 1024 * 1024:
        raise RuntimeError("The image server returned an invalid portrait file.")
    return raw


def generate_portrait(state, settings, force=False):
    if not settings.get("portrait_generation_enabled", True):
        raise RuntimeError("Automatic AI portraits are disabled in Settings.")
    provider = settings.get("image_provider") if settings.get("image_provider") in {"local", "cloud"} else settings.get("provider", "local")
    if provider == "cloud":
        key = settings.get("api_key", "")
        if not key:
            raise RuntimeError("OpenAI Cloud portrait generation needs an API key in Settings.")
        base_url = "https://api.openai.com/v1"
        token = key
        model = settings.get("image_model") or "gpt-image-2"
    else:
        base_url = str(settings.get("local_image_base_url") or settings.get("local_base_url") or "http://localhost:1234/v1").rstrip("/")
        token = settings.get("local_token", "")
        model = str(settings.get("local_image_model") or "").strip()
        if not model:
            raise RuntimeError("Set a Local Image Model in Settings, or use the included world portrait.")

    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    if target.exists() and not force:
        return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "cached": True}

    previous = latest_path(state)
    quality = settings.get("portrait_quality", "low")
    if quality not in ("low", "medium", "high", "auto"):
        quality = "low"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        if previous and previous.exists():
            fields = {"model": model, "prompt": portrait_prompt(state, True), "size": "1024x1024", "quality": quality}
            boundary, body = _multipart(fields, previous)
            edit_headers = {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
            req = urllib.request.Request(base_url + "/images/edits", data=body, headers=edit_headers, method="POST")
            with urllib.request.urlopen(req, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        else:
            body = {"model": model, "prompt": portrait_prompt(state, False), "size": "1024x1024", "quality": quality}
            data = _request_json(base_url + "/images/generations", body, {**headers, "Content-Type": "application/json"})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Portrait generation HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not contact the configured image server: " + str(exc.reason)) from None

    raw = _decode_image(data)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)
    _record_portrait_usage(provider, quality)
    return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "cached": False}


def save_reference(state, raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 1000 or len(raw) > 12 * 1024 * 1024:
        raise ValueError("Reference portrait must be an image smaller than 12 MB.")
    if raw.startswith(b"\x89PNG"):
        ext = ".png"
    elif raw.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise ValueError("Reference portrait must be PNG, JPEG, or WebP.")
    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-reference{ext}"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)
    identity = state.setdefault("portrait_identity", {})
    identity["reference_file"] = target.name
    return {"image_url": f"/portrait-cache/{target.name}", "filename": target.name}


def portrait_history(state):
    prefix = campaign_portrait_id(state) + "-"
    items = []
    for p in sorted(PORTRAIT_CACHE_DIR.glob(prefix + "*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            items.append({"image_url": f"/portrait-cache/{p.name}", "filename": p.name,
                          "saved_at": int(p.stat().st_mtime), "reference": "-reference" in p.stem})
    return items[:20]


def revert_portrait(state):
    history = portrait_history(state)
    current = cached_path(state)
    candidates = [item for item in history if not current or item["filename"] != current.name]
    if not candidates:
        raise FileNotFoundError("No previous portrait exists for this campaign.")
    source = PORTRAIT_CACHE_DIR / candidates[0]["filename"]
    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    shutil.copyfile(source, target)
    return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "reverted_from": source.name}
