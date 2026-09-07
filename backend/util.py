"""Shared helpers: state merging, dice math, asset path resolution, and the
scene/portrait keyword resolvers ported from the original Tkinter build."""
import os, re, copy, sys, hashlib, tempfile
from pathlib import Path

APP_DIR_NAME = "WorldwalkerRPG"


def data_dir():
    explicit = os.getenv("WORLDWALKER_DATA_DIR")
    if explicit:
        p = Path(explicit).expanduser()
        base = str(p.parent)
    elif "unittest" in sys.modules or "pytest" in sys.modules:
        # Automated tests must never load a player's live model keys, saves,
        # or settings. A configured live major-event model previously made
        # otherwise deterministic unit tests call the network.
        p = Path(tempfile.gettempdir()) / f"WorldwalkerRPG-tests-{os.getpid()}"
        base = str(p.parent)
    else:
        base = os.getenv("APPDATA") or str(Path.home())
        p = Path(base) / APP_DIR_NAME
    try:
        (p / "saves").mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # This runs at import time, before Flask (or anything else) is up —
        # an unhandled failure here crashes the whole process immediately on
        # every launch, which under a container's restart policy looks like
        # the server endlessly bouncing every few seconds rather than a
        # normal startup error. Surface a concrete, actionable cause instead
        # of a bare traceback: this is almost always the mounted data
        # volume's permissions, not an application bug.
        raise OSError(
            f"Cannot create/write to the data directory at {p}. If this is running in a "
            f"container, check that the volume mounted at $HOME (currently {base!r}) is "
            f"writable by the container's user (a bind-mounted host folder can end up "
            f"owned by a different UID than the process running inside the container). "
            f"Original error: {e}"
        ) from e
    return p


DATA_DIR = data_dir()
SAVE_DIR = DATA_DIR / "saves"
SETTINGS_PATH = DATA_DIR / "settings.json"

BACKEND_DIR = Path(__file__).resolve().parent
ASSET_ROOT = (Path(sys._MEIPASS) if getattr(sys, "frozen", False) else BACKEND_DIR.parent) / "assets"


def stat_mod(v):
    return (int(v) - 10) // 2


def clamp(n, a, b):
    return max(a, min(b, n))


def safe_filename(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', s).strip('_') or "save"


def ai_text(value):
    """Coerce one AI-authored list item into a readable string.

    Schemas that ask for a plain string list (suggested_actions, deferred/
    completed actions) sometimes get a richer object back instead — smaller
    or local models especially tend to generalize a dict shape they saw
    elsewhere in the schema. str()'ing a dict directly produces Python repr
    syntax ({'action': 'X', ...}), which is exactly what would otherwise end
    up rendered verbatim as a button label or queued action. This builds a
    readable sentence out of whatever shape actually came back instead of
    trusting the schema was followed.
    """
    if isinstance(value, dict):
        action = str(value.get("action") or value.get("verb") or "").strip()
        target = str(value.get("target") or value.get("goal") or value.get("objective") or "").strip()
        purpose = str(value.get("purpose") or value.get("reason") or value.get("why") or "").strip()
        text = " ".join(p for p in (action, target) if p)
        if purpose:
            text = f"{text} — {purpose}" if text else purpose
        if text.strip():
            return text.strip()
        # A different common shape: a short headline plus elaboration
        # (title/evidence, label/detail, name/description, ...).
        headline = str(value.get("title") or value.get("label") or value.get("name") or value.get("point") or "").strip()
        detail = str(value.get("evidence") or value.get("detail") or value.get("description") or value.get("explanation") or value.get("text") or "").strip()
        if headline or detail:
            return f"{headline}: {detail}" if headline and detail else (headline or detail)
        return ", ".join(f"{k}: {v}" for k, v in value.items() if v)
    return str(value).strip()


def merge(dst, patch):
    if not isinstance(dst, dict) or not isinstance(patch, dict):
        return copy.deepcopy(patch)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


WORLD_THEMES = {
    "One Piece": {"bg": "#071521", "panel": "#0C1E2F", "accent": "#D4A14A", "accent2": "#5FC3D7", "text": "#F3EAD8", "sub": "#ABC4CE", "kind": "ocean"},
    "Hunter x Hunter": {"bg": "#0B1711", "panel": "#14251C", "accent": "#BE9A52", "accent2": "#77B37D", "text": "#F1E9D8", "sub": "#A6B6AA", "kind": "forest"},
    "Naruto": {"bg": "#1B1210", "panel": "#2B1A15", "accent": "#C96D3F", "accent2": "#D5A45A", "text": "#F3E6D6", "sub": "#C3AE9A", "kind": "scroll"},
    "Solo Max-Level Newbie": {"bg": "#090C18", "panel": "#13192A", "accent": "#63E0F5", "accent2": "#9A7AFF", "text": "#EEF6FF", "sub": "#ABB6CF", "kind": "tower"},
    "Overgeared": {"bg": "#17100B", "panel": "#261B13", "accent": "#C7924B", "accent2": "#7999B4", "text": "#F2E4CF", "sub": "#B7A58E", "kind": "forge"},
    "Jujutsu Kaisen": {"bg":"#09090C","panel":"#15131B","accent":"#AD82FF","accent2":"#FF4F72","text":"#F2EFF6","sub":"#AAA2B5","kind":"cursed_ink"},
    "Custom World": {"bg": "#0C1622", "panel": "#162233", "accent": "#C7A15C", "accent2": "#75B6C8", "text": "#F2E7D1", "sub": "#A9B7C2", "kind": "mountains"},
}


def theme_for(world):
    return WORLD_THEMES.get(world, WORLD_THEMES["Custom World"])


def world_slug(world):
    return re.sub(r"[^A-Za-z0-9]+", "_", world or "Custom World").strip("_")


def world_asset_dir(world, user=False):
    return ASSET_ROOT / ("user" if user else "builtin") / world_slug(world)


def find_world_asset_rel(world, name):
    user = world_asset_dir(world, True) / name
    if user.exists():
        return f"/assets/user/{world_slug(world)}/{name}"
    built = world_asset_dir(world, False) / name
    if built.exists():
        return f"/assets/builtin/{world_slug(world)}/{name}"
    return None


SCENE_CATEGORIES = [
    "harbor_port", "tower_hub", "forest_path", "starry_sky", "mountain_castle",
    "battlefield_dusk", "kingdom", "monster_lair", "night_wilderness",
    "indoor_grandhall", "dungeon_cave", "town_square", "duel", "monster_battlefield",
    "merchant_shop", "tavern_inn", "academy_classroom", "residential_street",
    "training_ground", "ship_deck", "arena_floor", "hospital_clinic",
    "forest_village", "palace_chamber", "ruined_city", "snow_region",
    "desert_region", "rain_city", "underwater",
]

SCENE_FALLBACKS = {
    "merchant_shop": "town_square", "tavern_inn": "indoor_grandhall",
    "academy_classroom": "indoor_grandhall", "residential_street": "town_square",
    "training_ground": "forest_path", "ship_deck": "harbor_port",
    "arena_floor": "duel", "hospital_clinic": "indoor_grandhall",
    "forest_village": "forest_path", "palace_chamber": "kingdom",
    "ruined_city": "battlefield_dusk", "snow_region": "mountain_castle",
    "desert_region": "night_wilderness", "rain_city": "town_square",
    "underwater": "harbor_port",
}

# Recognizable setting anchors get their own art. These remain deliberately
# location-driven: combat and dungeon scenes still use the more informative
# action background, while ordinary exploration shows the canonical place.
LANDMARK_SCENES = {
    "One Piece": (
        (("foosha", "windmill village"), "one_piece_foosha_village"),
        (("baratie",), "one_piece_baratie"), (("loguetown", "logue town"), "one_piece_loguetown"),
        (("alabasta", "alubarna"), "one_piece_alabasta"), (("skypiea", "sky island"), "one_piece_skypiea"),
        (("water 7", "water seven"), "one_piece_water_7"), (("enies lobby",), "one_piece_enies_lobby"),
        (("sabaody",), "one_piece_sabaody"), (("arlong park",), "one_piece_arlong_park"),
    ),
    "Hunter x Hunter": (
        (("yorknew",), "hunter_x_hunter_yorknew_city"), (("heavens arena", "heaven's arena"), "hunter_x_hunter_heavens_arena"),
        (("kukuroo", "zoldyck estate"), "hunter_x_hunter_kukuroo_mountain"), (("greed island",), "hunter_x_hunter_greed_island"),
        (("whale island",), "hunter_x_hunter_whale_island"),
    ),
    "Naruto": (
        (("konohagakure", "hidden leaf", "konoha"), "naruto_konohagakure"),
        (("sunagakure", "hidden sand"), "naruto_sunagakure"), (("kirigakure", "hidden mist"), "naruto_kirigakure"),
        (("valley of the end",), "naruto_valley_of_the_end"), (("forest of death",), "naruto_forest_of_death"),
        (("amegakure", "hidden rain"), "naruto_amegakure"),
    ),
    "Solo Max-Level Newbie": ((("tower entrance", "earth — tower", "earth - tower"), "solo_tower_entrance"),),
    "Overgeared": ((("winston",), "overgeared_winston"),),
    "Reincarnated as a Slime": (
        (("tempest", "rimuru city"), "slime_tempest"), (("dwargon", "armed nation"), "slime_dwargon"),
    ),
    "Bleach": (
        (("karakura", "kurosaki clinic", "urahara shop", "naruki"), "bleach_karakura_town"),
        (("seireitei", "rukongai", "shin'o academy", "shino academy", "sokyoku", "gotei 13", "central 46", "muken"), "bleach_seireitei"),
        (("hueco mundo", "las noches", "forest of menos", "garganta"), "bleach_hueco_mundo"),
        (("soul king palace", "royal guard", "wahrwelt", "silbern"), "bleach_royal_realm"),
    ),
    "Jujutsu Kaisen": (
        (("tokyo jujutsu high", "tombs of the star corridor", "cursed warehouse"), "jjk_tokyo_high"),
        (("gojo estate", "zenin estate", "kamo estate", "great clan estate", "clan compound"), "jjk_clan_estate"),
        (("kyoto jujutsu high",), "jjk_kyoto_high"),
        (("subway", "metro station", "underground station", "service tunnel"), "jjk_subway_tunnel"),
        (("abandoned hospital", "cursed hospital"), "jjk_cursed_hospital"),
        (("shibuya", "tokyo", "colony"), "jjk_shibuya_night"),
    ),
}


def _category_from_place(text):
    """Classify a physical place without being distracted by story history."""
    text = str(text or "").lower()
    if not text or text in {"unknown", "somewhere", "starting location"}:
        return None
    # Small, concrete sub-locations intentionally outrank broad region words.
    if any(k in text for k in ["amegakure", "hidden rain", "rain village"]):
        return "rain_city"
    if any(k in text for k in ["underwater", "sea floor", "ocean floor", "sunken city", "coral palace"]):
        return "underwater"
    if any(k in text for k in ["merchant", "stall", "shop", "bazaar", "market booth", "store", "emporium"]):
        return "merchant_shop"
    if any(k in text for k in ["tavern", "inn", "restaurant", "canteen", "ramen shop", "baratie dining"]):
        return "tavern_inn"
    if any(k in text for k in ["academy", "classroom", "lecture room", "school room"]):
        return "academy_classroom"
    if any(k in text for k in ["training ground", "dojo", "practice field", "sparring yard", "gymnasium"]):
        return "training_ground"
    if any(k in text for k in ["arena floor", "fighting arena", "tournament ring", "colosseum", "stadium floor", "heavens arena ring"]):
        return "arena_floor"
    if any(k in text for k in ["hospital", "clinic", "infirmary", "medical ward", "healer's room"]):
        return "hospital_clinic"
    if any(k in text for k in ["ship deck", "quarterdeck", "main deck", "pirate ship", "marine ship"]):
        return "ship_deck"
    if any(k in text for k in ["palace chamber", "royal chamber", "audience chamber", "throne room"]):
        return "palace_chamber"
    if any(k in text for k in ["ruined city", "burned village", "destroyed town", "city ruins", "abandoned ruins"]):
        return "ruined_city"
    if any(k in text for k in ["snow", "frozen", "ice field", "winter village", "tundra", "blizzard"]):
        return "snow_region"
    if any(k in text for k in ["desert", "sand sea", "dune", "sunagakure outskirts", "wasteland"]):
        return "desert_region"
    if any(k in text for k in ["forest village", "woodland settlement", "tree village"]):
        return "forest_village"
    if any(k in text for k in ["residential", "neighborhood", "housing district", "apartment", "village street", "city street", "alley"]):
        return "residential_street"
    if any(k in text for k in ["market", "town square", "plaza", "village square"]):
        return "town_square"
    if any(k in text for k in ["dungeon", "cave", "crypt", "catacomb", "underground", "tunnel", "sewer", "mine"]):
        return "dungeon_cave"
    if any(k in text for k in ["lair", "nest", "beast den", "dragon den", "boss room"]):
        return "monster_lair"
    if any(k in text for k in ["port", "harbor", "dock", "wharf", "ship", "coast", "island", "beach"]):
        return "harbor_port"
    if any(k in text for k in ["forest", "woods", "grove", "jungle", "woodland trail"]):
        return "forest_path"
    if any(k in text for k in ["battlefield", "war camp", "front line", "siege line"]):
        return "battlefield_dusk"
    if any(k in text for k in ["castle", "capital", "palace", "citadel", "royal court"]):
        return "kingdom"
    if any(k in text for k in ["hall", "guild", "mansion", "temple"]):
        return "indoor_grandhall"
    if any(k in text for k in ["tower", "system hub"]):
        return "tower_hub"
    if any(k in text for k in ["mountain", "valley", "cliff", "peak"]):
        return "mountain_castle"
    if any(k in text for k in ["town", "city", "street", "alley", "district", "village", "avenue", "gate"]):
        return "town_square"
    if any(k in text for k in ["wilderness", "camp", "desert", "plain", "field"]):
        return "night_wilderness"
    return None


WORLD_NEUTRAL_SCENES = {
    "Overgeared": "kingdom", "One Piece": "harbor_port", "Hunter x Hunter": "forest_path",
    "Naruto": "town_square", "Solo Max-Level Newbie": "tower_hub", "Bleach": "bleach_seireitei",
    "Jujutsu Kaisen": "jjk_tokyo_high",
    "Reincarnated as a Slime": "forest_path", "Custom World": "starry_sky",
}


_INDOOR_WORDS = ("room", "chamber", "hall", "shop", "stall", "inn", "tavern", "restaurant", "academy", "classroom", "office", "clinic", "hospital", "forge", "workshop", "interior", "indoors", "cave", "dungeon", "crypt", "tunnel")
_OUTDOOR_WORDS = ("street", "square", "plaza", "forest", "woods", "field", "road", "harbor", "port", "deck", "village", "town", "city", "mountain", "valley", "desert", "beach", "island", "outdoors", "outside")


def scene_context(state):
    """Return the structured identity of the player's *current* scene.

    Location remains authoritative.  Optional location_details enrich it with
    a room/district, indoor state and live local conditions without letting an
    old Chronicle battle or a distant world event hijack the banner.
    """
    world = str(state.get("world") or "Custom World")
    location = str(state.get("location") or "").strip()
    details_by_location = state.get("location_details") if isinstance(state.get("location_details"), dict) else {}
    details = details_by_location.get(location) if isinstance(details_by_location.get(location), dict) else {}
    sublocation = str(details.get("sublocation") or details.get("room") or details.get("building") or details.get("district") or "").strip()
    setting = str(details.get("setting") or details.get("environment") or details.get("biome") or "").strip()
    place_blob = " · ".join(x for x in (sublocation, location, setting) if x)
    lowered = place_blob.lower()
    explicit_indoor = details.get("indoors")
    if isinstance(explicit_indoor, bool):
        indoors = explicit_indoor
    elif any(word in lowered for word in _INDOOR_WORDS):
        indoors = True
    elif any(word in lowered for word in _OUTDOOR_WORDS):
        indoors = False
    else:
        indoors = None
    calendar = state.get("calendar") if isinstance(state.get("calendar"), dict) else {}
    hour = calendar.get("hour")
    try:
        hour = int(hour)
    except (TypeError, ValueError):
        hour = None
    time_text = str(details.get("time") or state.get("world_time") or "").lower()
    if hour is not None:
        phase = "night" if hour < 5 or hour >= 20 else "dawn" if hour < 8 else "day" if hour < 17 else "dusk"
    elif any(word in time_text for word in ("night", "midnight", "moon", "star")):
        phase = "night"
    elif any(word in time_text for word in ("evening", "sunset", "dusk")):
        phase = "dusk"
    elif any(word in time_text for word in ("dawn", "sunrise")):
        phase = "dawn"
    else:
        phase = "day"
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    return {
        "world": world, "location": location, "sublocation": sublocation,
        "place": place_blob or location, "setting": setting, "indoors": indoors,
        "time": phase, "weather": str(details.get("weather") or state.get("weather") or "clear").lower(),
        "activity": str(details.get("activity") or state.get("current_activity") or "").strip(),
        "combat": bool(combat.get("active")), "combat_state": combat,
    }


def scene_category(state):
    context = scene_context(state)
    location = context["place"]
    combat = context["combat_state"]
    live_activity = " ".join([
        context["activity"],
        " ".join(str(x) for x in state.get("queued_actions", [])[-3:]),
        " ".join(str(x) for x in state.get("standing_orders", [])[-3:]),
    ]).lower()
    if state.get("world") == "Jujutsu Kaisen" and any(k in live_activity for k in ("domain expansion", "innate domain", "sure-hit", "sure hit")):
        return "jjk_domain_interior"
    # A completed fight intentionally keeps its mechanical log around until
    # the final narration pass can consume it.  That inactive record is not a
    # live scene signal: otherwise a character who fled, returned home and
    # trained could still receive battlefield art after a reload.
    active_combat = bool(combat.get("active"))
    enemy = combat.get("enemy") if active_combat else None
    enemy = enemy if isinstance(enemy, dict) else {}
    enemy_blob = str(enemy.get("name", "")).lower()
    monster_words = ("monster", "beast", "demon", "goblin", "orc", "undead", "slime", "dragon", "horde")
    if active_combat and enemy and not enemy.get("is_group") and not any(k in enemy_blob for k in monster_words):
        return "duel"
    if active_combat and enemy and (enemy.get("is_group") or any(k in enemy_blob for k in monster_words)):
        return "monster_battlefield"
    # Outside active combat, the player's current physical location is the
    # strongest signal. Old timeline entries may mention wars and monsters,
    # but those should never turn a merchant stall into a battlefield banner.
    place_category = _category_from_place(location)
    if place_category:
        return place_category
    weather = context["weather"]
    # Outdoor weather may change a generic city/region image.  It must never
    # replace a known interior (the old source of rainy shops and snowy halls).
    if context["indoors"] is not True and any(k in weather for k in ("heavy rain", "storm", "downpour", "monsoon")):
        return "rain_city"
    if context["indoors"] is not True and any(k in weather for k in ("snow", "blizzard", "sleet")):
        return "snow_region"
    # Only live player-facing activity is allowed to influence a vague
    # location. Old Chronicle/timeline prose often contains battles far away
    # from the character and was the source of merchant stalls receiving
    # battlefield art after unrelated world updates.
    blob = " ".join([
        context["activity"],
        " ".join(str(x) for x in state.get("queued_actions", [])[-3:]),
        " ".join(str(x) for x in state.get("standing_orders", [])[-3:]),
        context["time"],
    ]).lower()
    if any(k in blob for k in ["train", "practice", "study technique", "spar", "meditat"]):
        return "training_ground"
    if any(k in blob for k in ["craft", "forge", "smith", "workshop", "brew"]):
        return "merchant_shop"
    if any(k in blob for k in ["heal", "recover", "medical treatment", "infirmary"]):
        return "hospital_clinic"
    if any(k in blob for k in ["duel", "one-on-one", "one on one", "single combat", "sparring match"]):
        return "duel"
    if any(k in blob for k in ["monster horde", "army of monsters", "swarm of monsters", "monster battlefield"]):
        return "monster_battlefield"
    if any(k in blob for k in ["dungeon", "cave", "crypt", "catacomb", "underground", "tunnel"]):
        return "dungeon_cave"
    if any(k in blob for k in ["lair", "nest", "sleeping monster", "beast den", "dragon den", "boss room"]):
        return "monster_lair"
    if any(k in blob for k in ["port", "harbor", "dock", "ship", "coast", "island"]):
        return "harbor_port"
    if any(k in blob for k in ["forest", "woods", "grove", "trail", "path"]):
        return "forest_path"
    if any(k in blob for k in ["night", "midnight", "stars", "starry", "moon", "camp", "wilderness"]):
        return "starry_sky"
    if any(k in blob for k in ["battle", "war", "siege", "battlefield", "front line", "raid"]):
        return "battlefield_dusk"
    if any(k in blob for k in ["town", "square", "market", "city", "winston", "village", "plaza"]):
        return "town_square"
    if any(k in blob for k in ["kingdom", "castle", "capital", "palace", "citadel"]):
        return "kingdom"
    if any(k in blob for k in ["hall", "guild", "throne", "indoors", "mansion", "temple"]):
        return "indoor_grandhall"
    if any(k in blob for k in ["tower", "floor", "system hub"]):
        return "tower_hub"
    if any(k in blob for k in ["mountain", "valley", "cliff"]):
        return "mountain_castle"
    return WORLD_NEUTRAL_SCENES.get(state.get("world"), "starry_sky")


def scene_art_confidence(state, category=None):
    """Explain how strongly the selected art matches the live physical scene."""
    category = category or scene_category(state)
    context = scene_context(state)
    if str(category).startswith("jjk_"):
        return {"score": 90, "label": "Jujutsu scene match", "reason": "The active Jujutsu Kaisen scene selected dedicated setting art."}
    location = context["place"].strip()
    if state.get("active_canon_event"):
        return {"score": 100, "label": "Exact event", "reason": "A dedicated active-event banner has priority."}
    if isinstance(state.get("combat"), dict) and state.get("combat", {}).get("active"):
        return {"score": 98, "label": "Combat match", "reason": "Active combat and opponent type determine the scene."}
    lowered = location.lower()
    local_detail_words = ("merchant", "stall", "shop", "bazaar", "market", "alley", "street", "inn", "tavern", "restaurant")
    if not any(word in lowered for word in local_detail_words):
        for terms, landmark_name in LANDMARK_SCENES.get(state.get("world"), ()):
            if any(term in lowered for term in terms):
                return {"score": 95, "label": "Landmark match", "reason": f"'{location}' matches the {landmark_name} landmark art."}
    place = _category_from_place(location)
    if place:
        return {"score": 92, "label": "Location match", "reason": f"'{location}' directly matches the {place} environment."}
    activity = " ".join([
        str(state.get("current_activity", "")),
        " ".join(str(x) for x in state.get("queued_actions", [])[-3:]),
        " ".join(str(x) for x in state.get("standing_orders", [])[-3:]),
    ]).lower()
    activity_matches = {
        "training_ground": ("train", "practice", "spar", "meditat"),
        "merchant_shop": ("craft", "forge", "smith", "brew"),
        "hospital_clinic": ("heal", "recover", "medical", "infirmary"),
    }
    if category in activity_matches and any(word in activity for word in activity_matches[category]):
        return {"score": 84, "label": "Activity match", "reason": "The current player activity selected this environment."}
    weather = context["weather"]
    if category in {"rain_city", "snow_region"} and weather not in {"", "clear"}:
        return {"score": 78, "label": "Weather match", "reason": f"The current {weather} weather selected this environment."}
    time_blob = context["time"]
    if category == "starry_sky" and any(word in time_blob for word in ("night", "midnight", "evening")):
        return {"score": 76, "label": "Time-of-day match", "reason": "The current time explicitly indicates night."}
    return {"score": 48, "label": "World fallback", "reason": "The sub-location is too vague for a confident match; neutral world art is safer."}


def find_canon_event_banner(world, banner_slug):
    """A named canon event can carry its own dedicated banner (e.g. the
    Nine-Tails attack), distinct from the generic per-category scene art.
    Files are named {slug}_v{N}.{ext} so a replacement/upgrade just needs a
    higher version number dropped into the folder — no code change, same
    auto-upgrade spirit as the gif-before-png category lookup below. The
    highest version wins; among ties, gif/webp beat png."""
    if not banner_slug:
        return None
    directory = ASSET_ROOT / "canon_events" / world_slug(world)
    if not directory.is_dir():
        return None
    ext_rank = {"gif": 0, "webp": 1, "png": 2}
    pattern = re.compile(r"^" + re.escape(banner_slug) + r"_v(\d+)\.(gif|webp|png)$")
    best = None
    for f in directory.iterdir():
        m = pattern.match(f.name)
        if not m:
            continue
        key = (int(m.group(1)), -ext_rank[m.group(2)])
        if best is None or key > best[0]:
            best = (key, f.name)
    return f"/assets/canon_events/{world_slug(world)}/{best[1]}" if best else None


def scene_image_url(state):
    """Choose environment art by the live scene category.

    A currently-active major canon event (state.active_canon_event) with its
    own dedicated banner outranks everything else — the whole point is that
    the player can tell at a glance something huge is happening. User art is
    next highest priority. The shipped generated category set replaces the
    old mislabeled placeholder pack. GIF is checked first so an animated
    replacement can be dropped in later without code changes; PNG is the
    efficient default with canvas-based ambient motion.
    """
    cat = scene_category(state)
    confidence = scene_art_confidence(state, cat)
    active_combat = isinstance(state.get("combat"), dict) and bool(state.get("combat", {}).get("active"))
    if confidence["score"] < 60 and not active_combat and not state.get("active_canon_event"):
        cat = WORLD_NEUTRAL_SCENES.get(state.get("world"), "starry_sky")
    world = state.get("world", "Custom World")
    slug = world_slug(world)
    active_event = str(state.get("active_canon_event") or "").strip()
    if active_event:
        from worlds import timeline_for
        for event in timeline_for(world).get("events", []):
            if event.get("title") == active_event and event.get("banner"):
                banner_url = find_canon_event_banner(world, event["banner"])
                if banner_url:
                    return banner_url, "canon_event"
                break
    override = ASSET_ROOT / "user" / slug / "background.png"
    if override.exists():
        return f"/assets/user/{slug}/background.png", cat
    generated_dir = ASSET_ROOT / "generated_scenes"
    context = scene_context(state)
    location = context["place"].lower()
    landmarks = LANDMARK_SCENES.get(world, ())
    action_categories = {"duel", "monster_battlefield", "monster_lair", "dungeon_cave"}
    local_detail_words = ("merchant", "stall", "shop", "bazaar", "market", "alley", "street", "inn", "tavern", "restaurant")
    if not active_combat and cat != "jjk_domain_interior" and (cat not in action_categories or world == "Jujutsu Kaisen") and not any(word in location for word in local_detail_words):
        for terms, landmark_name in landmarks:
            if any(term in location for term in terms):
                for ext in ("gif", "webp", "png"):
                    generated = generated_dir / f"{landmark_name}.{ext}"
                    if generated.exists():
                        return f"/assets/generated_scenes/{landmark_name}.{ext}", cat
    for ext in ("gif", "webp", "png"):
        generated = generated_dir / f"{cat}.{ext}"
        if generated.exists():
            return f"/assets/generated_scenes/{cat}.{ext}", cat
    fallback_cat = SCENE_FALLBACKS.get(cat)
    if fallback_cat:
        for ext in ("gif", "webp", "png"):
            generated = generated_dir / f"{fallback_cat}.{ext}"
            if generated.exists():
                return f"/assets/generated_scenes/{fallback_cat}.{ext}", cat
    return None, cat


def scene_art_signature(state):
    """Stable cache key that changes only with place or scene type.

    Chronicle wording, routine time passage, stats, and distant events are
    deliberately absent so they cannot trigger needless environment-art
    churn. Weather only matters when it actually selects a weather scene.
    """
    url, category = scene_image_url(state)
    context = scene_context(state)
    payload = "|".join((context["world"], context["location"], context["sublocation"],
                        str(context["indoors"]), context["time"] if category == "starry_sky" else "",
                        context["weather"] if category in {"rain_city", "snow_region"} else "",
                        str(context["combat"]), str(category), str(url or ""),
                        str(state.get("active_canon_event", ""))))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def scene_display_label(state, image_url=None, category=None):
    """Return a truthful player-facing label without changing the semantic
    category used by ambient effects and compatibility callers."""
    if image_url is None or category is None:
        image_url, category = scene_image_url(state)
    if image_url and "/generated_scenes/" in image_url:
        stem = Path(image_url).stem
        landmark_names = {name for rows in LANDMARK_SCENES.values() for _terms, name in rows}
        if stem in landmark_names:
            return stem
    return category


def scene_selection_reason(state):
    match = scene_art_confidence(state)
    return f"{match['label']} ({match['score']}%): {match['reason']}"


def portrait_mode(state):
    blob = " ".join([
        str(state.get("appearance_desc", "")),
        " ".join(ai_text(x) for x in state.get("portrait_traits", [])),
        " ".join(str(x) for x in state.get("equipment", {}).values()) if isinstance(state.get("equipment"), dict) else "",
        " ".join(str(x) for x in state.get("titles", [])[:2]),
    ]).lower()
    if any(k in blob for k in ["armor", "armour", "plate", "mail", "knight", "helmet", "gauntlet"]):
        return "armored"
    if any(k in blob for k in ["hood", "cloak", "mantle", "cowl", "shadow", "masked", "mask"]):
        return "hooded"
    if any(k in blob for k in ["mage", "mystic", "aura", "glow", "rune", "sorcer", "spell"]):
        return "mystic"
    if any(k in blob for k in ["rogue", "thief", "dagger", "assassin", "stealth", "scarf"]):
        return "rogue"
    return "default"


def portrait_image_url(state):
    slug = world_slug(state.get("world", "Custom World"))
    mode = portrait_mode(state)
    p = ASSET_ROOT / "portraits" / slug / f"{mode}.png"
    if p.exists():
        return f"/assets/portraits/{slug}/{mode}.png"
    p = ASSET_ROOT / "portraits" / slug / "default.png"
    if p.exists():
        return f"/assets/portraits/{slug}/default.png"
    # A world with no packaged portrait folder of its own (e.g. one added
    # after the original art pack) falls back to Custom World's generic set
    # rather than showing no portrait at all.
    fallback = ASSET_ROOT / "portraits" / "Custom_World" / f"{mode}.png"
    if fallback.exists():
        return f"/assets/portraits/Custom_World/{mode}.png"
    fallback = ASSET_ROOT / "portraits" / "Custom_World" / "default.png"
    if fallback.exists():
        return "/assets/portraits/Custom_World/default.png"
    return None
