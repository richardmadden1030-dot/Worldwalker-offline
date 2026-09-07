"""Small offline lore retrieval layer.

The game cannot silently browse the web from a packaged EXE. Instead it keeps
structured, source-conscious lore notes for the setting's important systems
and retrieves only the entries relevant to the current action. Additional JSON
packs can be placed in assets/lore without changing engine code.
"""
import json
import re
import copy
import hashlib
import html
import ipaddress
import socket
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse, urljoin, urldefrag, unquote, urlencode
from urllib.request import Request, urlopen
from util import DATA_DIR, safe_filename
from bleach_data import CANON_HADO, CANON_BAKUDO
from canon_integrity import canon_identity_context

LORE_DIR = Path(__file__).resolve().parent.parent / "assets" / "lore"
USER_LORE_DIR = DATA_DIR / "lore"
USER_LORE_DIR.mkdir(parents=True, exist_ok=True)
LORE_AUTOMATION_PATH = DATA_DIR / "lore_automation.json"

LORE_AUTOMATION_DEFAULTS = {
    "enabled": False,
    "interval_days": 30,
    "discover_related_pages": False,
    "max_pages_per_refresh": 8,
}

# One stable entry page per setting.  They are only downloaded after the
# player enables automatic coverage; related pages remain separately opt-in
# and bounded.  Fandom pages are fetched through their lightweight MediaWiki
# JSON API by _mediawiki_api_url below.
RECOMMENDED_LORE_SOURCES = {
    "One Piece": [("https://onepiece.fandom.com/wiki/One_Piece", "wiki")],
    "Hunter x Hunter": [("https://hunterxhunter.fandom.com/wiki/Hunter_%C3%97_Hunter", "wiki")],
    "Naruto": [("https://naruto.fandom.com/wiki/Naruto_(series)", "wiki")],
    "Solo Max-Level Newbie": [("https://koreanwebtoons.fandom.com/wiki/I%27m_the_Max-Level_Newbie", "wiki")],
    "Overgeared": [("https://overgeared.fandom.com/wiki/Grid", "wiki")],
    "Reincarnated as a Slime": [("https://tensura.fandom.com/wiki/Rimuru_Tempest", "wiki")],
    "Bleach": [("https://www.viz.com/bleach", "official_source"),
               ("https://bleach.fandom.com/wiki/Bleach", "wiki")],
    "Jujutsu Kaisen": [("https://www.viz.com/jujutsu-kaisen", "official_source"),
                       ("https://jujutsu-kaisen.fandom.com/wiki/Jujutsu_Kaisen", "wiki")],
}

# Higher-ranked evidence wins when two sources make incompatible claims.
# This is intentionally explicit instead of assuming every imported file is
# equally trustworthy merely because it contains confident prose.
SOURCE_AUTHORITY = {
    "official_source": 100, "official_reference": 95, "licensed_reference": 90,
    "curated": 82, "wiki": 65, "forum": 42, "fan_analysis": 38,
    "imported": 55, "custom": 50, "unknown": 30,
}

_LORE_CACHE = {}
_LORE_CACHE_STATS = {"hits": 0, "misses": 0, "generation": 0}
_LORE_FTS_PATH = DATA_DIR / "lore_search.sqlite3"
_LORE_FTS_LOCK = threading.RLock()
_LORE_FTS_GENERATION = -1

def _ensure_lore_fts():
    """Build a local full-text index; return False on SQLite builds without FTS5."""
    global _LORE_FTS_GENERATION
    if _LORE_FTS_GENERATION == _LORE_CACHE_STATS["generation"] and _LORE_FTS_PATH.exists():
        return True
    with _LORE_FTS_LOCK:
        db = None
        try:
            db = sqlite3.connect(_LORE_FTS_PATH)
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lore_fts USING fts5(world, title, keys, text, payload UNINDEXED)")
            db.execute("DELETE FROM lore_fts")
            for world_name in BUILTIN_LORE:
                for entry in all_lore_entries(world_name):
                    db.execute("INSERT INTO lore_fts(world,title,keys,text,payload) VALUES(?,?,?,?,?)",
                               (world_name, entry.get("title", ""), entry.get("keys", ""), entry.get("text", ""), json.dumps(entry, ensure_ascii=False)))
            db.commit()
            _LORE_FTS_GENERATION = _LORE_CACHE_STATS["generation"]
            return True
        except (sqlite3.Error, OSError):
            return False
        finally:
            if db is not None:
                db.close()

def _fts_retrieve(world, terms, current_day, limit):
    if not terms or not _ensure_lore_fts():
        return []
    expression = " OR ".join('"' + term.replace('"', '') + '"' for term in list(terms)[:16])
    try:
        db = sqlite3.connect(_LORE_FTS_PATH)
        try:
            rows = db.execute("SELECT payload FROM lore_fts WHERE world=? AND lore_fts MATCH ? ORDER BY bm25(lore_fts) LIMIT ?",
                              (world, expression, max(1, int(limit) * 3))).fetchall()
        finally:
            db.close()
        entries = [json.loads(row[0]) for row in rows]
        return [entry for entry in entries if int(entry.get("min_canon_day", -10**9) or -10**9) <= current_day][:limit]
    except (sqlite3.Error, ValueError, TypeError):
        return []


def _automation_data():
    data = {"settings": dict(LORE_AUTOMATION_DEFAULTS), "sources": [], "history": []}
    try:
        loaded = json.loads(LORE_AUTOMATION_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data["settings"].update(loaded.get("settings") if isinstance(loaded.get("settings"), dict) else {})
            data["sources"] = loaded.get("sources") if isinstance(loaded.get("sources"), list) else []
            data["history"] = loaded.get("history") if isinstance(loaded.get("history"), list) else []
    except (OSError, ValueError, TypeError):
        pass
    data["settings"]["interval_days"] = max(1, min(365, int(data["settings"].get("interval_days", 30) or 30)))
    data["settings"]["max_pages_per_refresh"] = max(1, min(25, int(data["settings"].get("max_pages_per_refresh", 8) or 8)))
    return data


def _save_automation(data):
    LORE_AUTOMATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    LORE_AUTOMATION_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def configure_lore_automation(settings):
    data = _automation_data()
    allowed = {"enabled", "interval_days", "discover_related_pages", "max_pages_per_refresh"}
    for key in allowed:
        if key in (settings or {}):
            data["settings"][key] = settings[key]
    data["settings"]["enabled"] = bool(data["settings"].get("enabled"))
    data["settings"]["discover_related_pages"] = bool(data["settings"].get("discover_related_pages"))
    data["settings"]["interval_days"] = max(1, min(365, int(data["settings"].get("interval_days", 30) or 30)))
    data["settings"]["max_pages_per_refresh"] = max(1, min(25, int(data["settings"].get("max_pages_per_refresh", 8) or 8)))
    _save_automation(data)
    return lore_automation_status()


def seed_recommended_lore_sources(world=None):
    data = _automation_data()
    known = {(row.get("world"), row.get("url")) for row in data["sources"]}
    added = 0
    for world_name, rows in RECOMMENDED_LORE_SOURCES.items():
        if world and world_name != world:
            continue
        for url, source_type in rows:
            if (world_name, url) in known:
                continue
            source_id = hashlib.sha256(f"{world_name}|{url}".encode("utf-8")).hexdigest()[:16]
            data["sources"].append({"id": source_id, "url": url, "world": world_name,
                                    "source_type": source_type, "enabled": True, "discover": True,
                                    "recommended": True, "status": "queued"})
            known.add((world_name, url)); added += 1
    _save_automation(data)
    return added


def register_lore_source(url, world="Custom World", source_type="wiki", enabled=True, discover=False):
    source_url = _validate_public_url(url)
    data = _automation_data()
    source_id = hashlib.sha256(f"{world}|{source_url}".encode("utf-8")).hexdigest()[:16]
    existing = next((row for row in data["sources"] if row.get("id") == source_id), None)
    values = {"id": source_id, "url": source_url, "world": str(world or "Custom World")[:120],
              "source_type": source_type if source_type in SOURCE_AUTHORITY else "unknown",
              "enabled": bool(enabled), "discover": bool(discover)}
    if existing is None:
        existing = values
        data["sources"].append(existing)
    else:
        existing.update(values)
    _save_automation(data)
    return dict(existing)

BUILTIN_LORE = {
    "One Piece": [
        {"title":"Haki", "keys":"haki observation armament conqueror advanced coating future sight ryuo", "text":"Haki is trained willpower. Observation and Armament are broadly learnable through awakening, focused training, battle and instruction. Conqueror's Haki requires the rare inborn disposition; advanced applications require exceptional mastery and circumstances."},
        {"title":"Devil Fruits", "keys":"devil fruit ability awakening sea water seastone copy obtain", "text":"A Devil Fruit grants one unique power to one living user at a time. Eating another normally kills the user under accepted world rules; seawater and Seastone weaken users. Awakening demands deep synchronization and mastery, not XP alone."},
        {"title":"Rokushiki and combat arts", "keys":"rokushiki six powers soru geppo tekkai rankyaku shigan kami-e fishman karate", "text":"Rokushiki techniques and other martial schools are learnable physical disciplines when the player finds knowledge or a teacher and develops the required body. Faction secrecy can obstruct access but is not metaphysical exclusivity."},
        {"title":"Ships, navigation and world government", "keys":"ship sail navigator grand line log pose marine bounty government island", "text":"Grand Line travel requires appropriate navigation, supplies and often a Log Pose. Marines, pirates and governments respond to witnessed deeds; bounties measure perceived threat and notoriety, not a simple power level."},
    ],
    "Hunter x Hunter": [
        {"title":"Nen foundations", "keys":"nen aura ten zetsu ren hatsu awaken initiation", "text":"Nen is learnable by living beings with aura nodes, usually through training in Ten, Zetsu, Ren and Hatsu. Forced initiation is dangerous. Talent changes speed, not the basic possibility of learning."},
        {"title":"Nen categories", "keys":"enhancement emission transmutation conjuration manipulation specialization category water divination", "text":"A user's natural category shapes efficiency. Neighboring categories are easier; distant categories lose efficiency. Specialist abilities are exceptional and cannot be claimed merely by preference, though rare transformation or conditions can alter outcomes."},
        {"title":"Vows and limitations", "keys":"vow restriction condition covenant judgment chain power cost", "text":"Self-imposed restrictions can magnify Nen in proportion to genuine risk and resolve. A cosmetic promise grants little; severe enforceable limitations can produce extreme power and equally severe consequences."},
        {"title":"Hunter access", "keys":"hunter exam license association heavens arena greed island dark continent", "text":"Hunter privileges require passing the Exam or gaining equivalent access through the living world. Heaven's Arena, Greed Island, criminal networks and restricted frontiers each impose independent entry requirements."},
    ],
    "Naruto": [
        {"title":"Chakra and nature transformation", "keys":"chakra nature fire wind lightning earth water affinity transformation", "text":"Chakra combines physical and spiritual energy. Most shinobi have a natural elemental affinity but can train additional natures with greater effort; advanced transformations demand control, knowledge and time."},
        {"title":"Jutsu learning", "keys":"jutsu learn copy sharingan scroll teacher hand signs forbidden technique", "text":"Ordinary techniques can be learned through instruction, scrolls, observation and training. Copying does not bypass body, chakra, bloodline or comprehension requirements. Forbidden techniques remain possible but carry their stated costs and access risks."},
        {"title":"Bloodlines and dōjutsu", "keys":"kekkei genkai bloodline sharingan byakugan rinnegan wood release dojutsu transplant", "text":"Hereditary abilities require compatible biology, inheritance or a lore-valid transplant/experiment. Transplants can impose severe chakra and rejection costs. Training alone cannot simply manufacture a bloodline with no causal route."},
        {"title":"Ranks and village systems", "keys":"academy genin chunin jonin hokage mission village clan rank", "text":"Ranks and offices are social institutions earned through exams, appointments, reputation and politics. A player may diverge from canon and attain any office if its actual requirements and opposition are overcome."},
    ],
    "Solo Max-Level Newbie": [
        {"title":"Tower systems", "keys":"tower floor administrator scenario hidden condition achievement reward", "text":"Floors have explicit scenarios, administrators, hidden conditions and rewards. Knowledge can exploit them, but rewards still require satisfying the actual condition before its deadline."},
        {"title":"Copied abilities", "keys":"copy ability skill condition unique power", "text":"Ability copying follows the character's acquired skill and its stated conditions. It cannot copy outside those limits, but any demonstrated copy is reproducible when the same trigger and capacity are present."},
        {"title":"Artifacts and progression", "keys":"artifact item level stat mana boss raid", "text":"Artifacts, stats and skills are mechanically persistent. High-tier rewards require their encounter, achievement, ownership and compatibility conditions; foreknowledge changes the route, not the requirement."},
    ],
    "Overgeared": [
        {"title":"Classes and hidden classes", "keys":"class hidden class pagma successor quest satisfy", "text":"Classes arise through System-recognized choices, quests and items. A canon hidden class is not reserved by narrative privilege, but unique items or one-holder conditions may require reaching it first or causing a divergent route."},
        {"title":"Crafting", "keys":"craft forge blacksmith item rating legendary myth production mastery", "text":"Crafting quality depends on recipe knowledge, materials, tools, stats, mastery, time and inspiration. Legendary results are possible through the same mechanics demonstrated in-world, not arbitrary GM permission."},
        {"title":"NPC affinity and politics", "keys":"npc affinity guild kingdom lord reputation", "text":"Satisfy's NPCs are persistent people. Affinity, offices, territories and alliances follow relationships, achievements and politics; player status does not force compliance."},
    ],
    "Reincarnated as a Slime": [
        {"title":"Magicules and skills", "keys":"magicule skill extra unique ultimate great sage predator evolve", "text":"Skills emerge from desire, experience, naming, evolution and world-system synthesis. Unique and Ultimate Skills demand extraordinary causes; a demonstrated effect is possible if an equivalent causal path and capacity exist."},
        {"title":"Naming and evolution", "keys":"name naming monster evolve goblin ogre kijin magicules", "text":"Naming transfers magicules and can trigger monster evolution. The cost scales with the target and can exhaust or endanger the namer; mass naming requires exceptional reserves or recovery support."},
        {"title":"Demon Lord awakening", "keys":"demon lord seed harvest festival souls awakening", "text":"True Demon Lord awakening requires a valid seed plus the setting's soul/Harvest Festival conditions. Reputation or strength alone does not substitute, but a divergent player may fulfill those conditions."},
        {"title":"Resistances and analysis", "keys":"resistance immunity analysis great sage raphael consume predator", "text":"Resistance, analysis and absorption must come from acquired skills, species traits or evolution. Analysis does not grant knowledge beyond available observations and capabilities."},
    ],
    "Bleach": [
        {"title":"Souls, realms and balance", "keys":"soul plus hollow konso purification world living soul society hueco mundo balance", "text":"Pluses pass to Soul Society through Konso. Hollows are purified by a Soul Reaper's Zanpakuto unless their mortal crimes instead condemn them. Soul Society, the Living World and Hueco Mundo are distinct realms; destroying souls rather than purifying them can destabilize their balance.", "source_type":"curated", "source":"Bleach source-material reference"},
        {"title":"Reiryoku and Reiatsu", "keys":"reiryoku reiatsu spiritual pressure sensing capacity control suppress", "text":"Reiryoku is spiritual power held by a soul; Reiatsu is the pressure it exerts. Capacity, output and control are related but not identical. A severe pressure gap can impede movement or cause harm, while disciplined suppression can conceal strength.", "source_type":"curated", "source":"Bleach source-material reference"},
        {"title":"Four Shinigami arts", "keys":"zanjutsu hakuda hoho shunpo kido academy shinigami soul reaper", "text":"Soul Reapers train Zanjutsu swordsmanship, Hakuda unarmed combat, Hoho movement and Kido spellcraft. Skill and specialization differ by individual; rank is institutional and should not replace current mechanical stats when comparing power.", "source_type":"curated", "source":"Bleach source-material reference"},
        {"title":"Zanpakuto releases", "keys":"asauchi zanpakuto spirit inner world name command shikai bankai jinzen materialization", "text":"An Asauchi is imprinted by its wielder and becomes their Zanpakuto. Shikai follows communication and learning the true name; Bankai normally requires manifesting and subjugating the spirit and then years of mastery. A release expresses one coherent identity: Bankai evolves the established Shikai rather than becoming an unrelated power.", "source_type":"wiki", "source":"Bleach Wiki — Zanpakuto", "citation":"https://bleach.fandom.com/wiki/Zanpakut%C5%8D"},
        {"title":"Kido curriculum", "keys":"kido hado bakudo spell incantation chantless numbers 1 99 learn research", "text":"Kido uses Reiryoku and is divided chiefly into offensive Hado and binding/support Bakudo. Number broadly signals difficulty and power. Full incantations support proper output; skilled casters can omit them at reduced power. Every Soul Reaper can study compatible spells—the system is not class-locked.", "source_type":"wiki", "source":"Bleach Wiki — Kido", "citation":"https://bleach.fandom.com/wiki/Kid%C5%8D"},
        {"title":"Established numbered Hado", "keys":"hado sho byakurai tsuzuri raiden shakkaho okasen sokatsui haien tenran raikoho kurohitsugi", "text":"Established Hado: " + "; ".join(f"#{n} {name} — {effect}" for n, (name, effect) in sorted(CANON_HADO.items())) + " Numbers not shown in source material remain open campaign research slots: author one fitting permanent formula when discovered instead of declaring the number nonexistent.", "source_type":"wiki", "source":"Bleach Wiki — Kido", "citation":"https://bleach.fandom.com/wiki/Kid%C5%8D"},
        {"title":"Established numbered Bakudo", "keys":"bakudo sai hainawa seki geki sekienton kyokko shitotsu sansen tsuriboshi enkosen rikujokoro danku kin bankin", "text":"Established Bakudo: " + "; ".join(f"#{n} {name} — {effect}" for n, (name, effect) in sorted(CANON_BAKUDO.items())) + " Numbers not shown in source material remain open campaign research slots and must persist once authored.", "source_type":"wiki", "source":"Bleach Wiki — Kido", "citation":"https://bleach.fandom.com/wiki/Kid%C5%8D"},
        {"title":"Gotei 13 and squad placement", "keys":"gotei 13 squad division captain lieutenant seated officer graduate assignment academy", "text":"The Gotei 13 has thirteen divisions with captains, lieutenants, seated and unseated officers. Graduation does not mechanically dictate one division. Preferences, aptitude, recommendations, recruitment needs, interviews and captain decisions can all shape placement; exceptional candidates may receive competing offers.", "source_type":"wiki", "source":"Bleach Wiki — Gotei 13", "citation":"https://bleach.fandom.com/wiki/Gotei_13"},
        {"title":"Realm travel", "keys":"senkaimon dangai garganta hueco mundo royal realm soul king palace travel gate", "text":"Senkaimon passages cross between the Living World and Soul Society through the Dangai. Garganta provides a route involving Hueco Mundo. The Royal Realm and hidden enemy domains require their own exceptional access. Map proximity never substitutes for the required gate or method.", "source_type":"curated", "source":"Bleach source-material reference"},
        {"title":"Wandenreich war", "keys":"wandenreich sternritter quincy war invasion yhwach bankai steal soul king", "text":"The Wandenreich is a hidden Quincy empire led by Yhwach. Its invasion, Bankai theft and assault on the Soul King belong to the later Thousand-Year Blood War and must remain unrevealed to characters before discovery.", "source_type":"official_reference", "source":"Official BLEACH Thousand-Year Blood War story", "citation":"https://bleach-anime.com/en/story/story.html", "min_canon_day":930},
    ],
    "Jujutsu Kaisen": [
        {"title":"Cursed energy and curses", "keys":"cursed energy negative emotion curse spirit reinforcement residual", "text":"Negative human emotion produces cursed energy and can accumulate into cursed spirits. Sorcerers deliberately control cursed energy for reinforcement, techniques and barriers; raw reserves, output, control and efficiency are related but distinct."},
        {"title":"Innate techniques and applications", "keys":"innate cursed technique inherited extension lapse reversal maximum application", "text":"A sorcerer's innate technique supplies one governing rule. Named extensions, lapse/reversal uses and maximum techniques are applications or advanced expressions of that rule, not additional innate techniques. Original techniques should remain internally consistent once authored."},
        {"title":"Heavenly Restriction", "keys":"heavenly restriction zero cursed energy physical body maki toji sacrifice", "text":"A Heavenly Restriction is imposed at birth and exchanges one capacity for another. In this game it occupies the same exclusive birth slot as an innate technique. A physical restriction can greatly enhance body and senses in exchange for little or no cursed energy."},
        {"title":"Grades", "keys":"grade 4 grade 3 grade 2 grade 1 special grade sorcerer curse assessment", "text":"Sorcerers and curses can be assessed from Grade 4 through Special Grade. Grade informs expected assignment danger and institutional response, but matchup, information, technique rule and actual stats still decide encounters."},
        {"title":"Binding vows and barriers", "keys":"binding vow curtain barrier simple domain domain expansion sure hit", "text":"Binding vows gain power from real enforceable exchange. Barriers include curtains, anti-domain methods and complete domains; a domain manifests the user's technique and inner world through advanced barrier skill and enormous cost."},
        {"title":"Black Flash", "keys":"black flash impact timing cursed energy lightning zone", "text":"Black Flash occurs when cursed energy is applied within an extraordinarily narrow interval of a physical hit. It sharply amplifies the impact and deepens understanding, but even elite sorcerers cannot simply guarantee one on command."},
        {"title":"Cursed-spirit growth", "keys":"cursed spirit kill human grow cursed energy consume", "text":"Sentient curses may strengthen through fear, consumption and killing. This campaign grants growth for any killed human, with exponentially greater gains from victims who carry stronger cursed energy."},
    ],
    "Custom World": [
        {"title":"Setting consistency", "keys":"power magic technology learn copy ability rule", "text":"Treat demonstrated capabilities as reproducible when the custom world's stated prerequisites are met. Establish new restrictions consistently and record them in the codex rather than inventing one-off denials."},
    ],
}

_external_cache = None

def _external_entries():
    global _external_cache
    if _external_cache is not None:
        return _external_cache
    _external_cache = {}
    for directory in (LORE_DIR, USER_LORE_DIR):
      if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for world, entries in data.items():
                        if isinstance(entries, list):
                            for raw in entries:
                                if isinstance(raw, dict):
                                    entry = dict(raw)
                                    entry.setdefault("source", path.name)
                                    entry.setdefault("source_type", "imported")
                                    _external_cache.setdefault(world, []).append(entry)
            except Exception:
                continue
    return _external_cache


def reload_lore():
    _LORE_CACHE.clear()
    _LORE_CACHE_STATS["generation"] += 1
    global _external_cache
    _external_cache = None


def list_lore_sources():
    sources = [{"name": "Built-in Worldwalker notes", "kind": "builtin", "path": str(LORE_DIR),
                "source_type": "curated", "authority": SOURCE_AUTHORITY["curated"],
                "entries": sum(len(value) for value in BUILTIN_LORE.values())}]
    for path in sorted(USER_LORE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            count = sum(len(v) for v in data.values() if isinstance(v, list)) if isinstance(data, dict) else 0
            all_entries = [entry for values in data.values() if isinstance(values, list) for entry in values if isinstance(entry, dict)] if isinstance(data, dict) else []
            types = sorted(set(str(entry.get("source_type") or "imported") for entry in all_entries))
            sources.append({"name": path.name, "kind": "imported", "path": str(path), "entries": count,
                            "source_types": types, "authority": max([SOURCE_AUTHORITY.get(t, 30) for t in types] or [55]),
                            "worlds": [k for k, v in data.items() if isinstance(v, list)] if isinstance(data, dict) else []})
        except Exception as exc:
            sources.append({"name": path.name, "kind": "invalid", "path": str(path), "entries": 0, "error": str(exc)[:180]})
    return sources


def import_lore_pack(filename, raw, world="Custom World"):
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Lore files must be 2 MB or smaller.")
    suffix = Path(filename or "lore.json").suffix.lower()
    text = raw.decode("utf-8-sig")
    if suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("A JSON lore pack must map world names to lists of entries.")
        cleaned = {}
        for world_name, entries in data.items():
            if not isinstance(entries, list): continue
            valid = []
            for entry in entries[:500]:
                if not isinstance(entry, dict) or not str(entry.get("text", "")).strip(): continue
                source_type = str(entry.get("source_type") or entry.get("kind") or "imported").lower().strip()
                if source_type not in SOURCE_AUTHORITY: source_type = "unknown"
                claims = entry.get("claims") if isinstance(entry.get("claims"), dict) else {}
                valid.append({"title": str(entry.get("title") or "Imported lore")[:160],
                              "keys": str(entry.get("keys") or entry.get("keywords") or "")[:1000],
                              "text": str(entry.get("text"))[:8000],
                              "source": str(entry.get("source") or filename)[:500],
                              "source_type": source_type,
                              "citation": str(entry.get("citation") or entry.get("url") or "")[:1000],
                              "claims": {str(k)[:160]: str(v)[:1000] for k, v in claims.items()}})
            if valid: cleaned[str(world_name)[:120]] = valid
        if not cleaned: raise ValueError("The lore pack contained no usable entries with text.")
    elif suffix in {".md", ".txt"}:
        body = text.strip()
        if not body: raise ValueError("The lore file is empty.")
        title = next((line.lstrip("# ").strip() for line in body.splitlines() if line.strip()), Path(filename).stem)
        keywords = " ".join(re.findall(r"[A-Za-z0-9'-]{4,}", body[:5000])[:80])
        cleaned = {world: [{"title": title[:160], "keys": keywords[:1000], "text": body[:8000], "source": filename,
                            "source_type": "imported", "citation": "", "claims": {}}]}
    else:
        raise ValueError("Import JSON, Markdown, or plain-text lore files.")
    stem = safe_filename(Path(filename or "lore_pack").stem) or "lore_pack"
    target = USER_LORE_DIR / f"{stem}.json"
    index = 2
    while target.exists():
        target = USER_LORE_DIR / f"{stem}_{index}.json"; index += 1
    target.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    reload_lore()
    return {"name": target.name, "path": str(target), "entries": sum(len(v) for v in cleaned.values()), "worlds": list(cleaned)}


class _ReadablePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.parts, self.links, self._tag, self._skip = "", [], [], "", 0

    def handle_starttag(self, tag, attrs):
        self._tag = tag.lower()
        if self._tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(str(href))
        if self._tag in {"script", "style", "nav", "footer", "header", "form", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "nav", "footer", "header", "form", "svg"} and self._skip:
            self._skip -= 1
        self._tag = ""

    def handle_data(self, data):
        clean = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not clean or self._skip:
            return
        if self._tag == "title" and not self.title:
            self.title = clean
        elif self._tag in {"p", "li", "h1", "h2", "h3", "h4", "td", "th", "dt", "dd"} and len(clean) >= 12:
            self.parts.append(clean)


def _validate_public_url(url):
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a public HTTP or HTTPS source URL.")
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except OSError as exc:
        raise ValueError("The lore source hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Lore updating only accepts public internet sources.")
    return parsed.geturl()


def _related_links(base_url, links, limit=25):
    """Bounded, same-host discovery.  No unbounded wiki/forum crawling."""
    base = urlparse(base_url)
    out = []
    blocked = re.compile(r"(?:/login|/signup|/edit|/history|/special:|action=|oldid=|\.jpg$|\.png$|\.gif$|\.zip$|\.pdf$)", re.I)
    for href in links:
        candidate = urldefrag(urljoin(base_url, href))[0]
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != base.hostname or blocked.search(candidate):
            continue
        if candidate.rstrip("/") == base_url.rstrip("/") or candidate in out:
            continue
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


def _mediawiki_api_url(source_url):
    """Use the public JSON API for Fandom pages instead of ad-heavy HTML."""
    parsed = urlparse(source_url)
    if not parsed.hostname or not parsed.hostname.lower().endswith(".fandom.com") or not parsed.path.startswith("/wiki/"):
        return source_url
    title = unquote(parsed.path.split("/wiki/", 1)[1]).replace("_", " ").strip()
    if not title:
        return source_url
    query = urlencode({"action": "parse", "page": title, "prop": "wikitext|links",
                       "redirects": "1", "format": "json", "formatversion": "2"})
    return f"{parsed.scheme}://{parsed.netloc}/api.php?{query}"


def _fetch_lore_url(url, validators=None):
    source_url = _validate_public_url(url)
    headers = {"User-Agent": "WorldwalkerRPG/3.16 lore updater"}
    validators = validators or {}
    if validators.get("etag"):
        headers["If-None-Match"] = str(validators["etag"])
    if validators.get("last_modified"):
        headers["If-Modified-Since"] = str(validators["last_modified"])
    fetch_url = _mediawiki_api_url(source_url)
    request = Request(fetch_url, headers=headers)
    try:
        response_context = urlopen(request, timeout=20)
    except HTTPError as exc:
        if exc.code == 304:
            return {"not_modified": True, "url": source_url, "fetch_url": fetch_url, "etag": validators.get("etag", ""),
                    "last_modified": validators.get("last_modified", ""), "links": []}
        raise
    with response_context as response:
        final_url = _validate_public_url(response.geturl())
        raw = response.read(512 * 1024 + 1)
        content_type = str(response.headers.get("Content-Type") or "").lower()
        etag = str(response.headers.get("ETag") or "")[:500]
        last_modified = str(response.headers.get("Last-Modified") or "")[:500]
    if len(raw) > 512 * 1024:
        raise ValueError("Lore web sources must be 512 KB or smaller.")
    return {"not_modified": False, "url": source_url, "fetch_url": final_url, "raw": raw, "content_type": content_type,
            "etag": etag, "last_modified": last_modified}


def _entry_from_download(download, world, source_type):
    final_url = download["url"]
    raw = download["raw"]
    content_type = download["content_type"]
    decoded = raw.decode("utf-8", errors="replace")
    title = urlparse(final_url).path.rstrip("/").split("/")[-1].replace("_", " ") or urlparse(final_url).hostname
    links = []
    claim_source = ""
    if "json" in content_type or final_url.lower().endswith(".json"):
        try:
            data = json.loads(decoded)
            if isinstance(data, dict) and isinstance(data.get("extract"), str):
                text = data["extract"]
                title = str(data.get("title") or title)
            elif isinstance(data, dict) and isinstance(data.get("parse"), dict):
                page = data["parse"]
                text = str(page.get("wikitext") or "")
                claim_source = text
                title = str(page.get("title") or title)
                links = [urljoin(final_url, "/wiki/" + str(row.get("title") or "").replace(" ", "_"))
                         for row in (page.get("links") or []) if row.get("title") and int(row.get("ns", 0) or 0) == 0]
                links = _related_links(final_url, links)
                # Cheap local wikitext cleanup. Templates/tables are metadata
                # noise for retrieval; link labels and prose are preserved.
                text = re.sub(r"\{\{[^{}]{0,2000}\}\}", " ", text, flags=re.S)
                text = re.sub(r"\{\|.*?\|\}", " ", text, flags=re.S)
                text = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", text)
                text = re.sub(r"<ref\b[^>]*>.*?</ref>|<[^>]+>", " ", text, flags=re.S | re.I)
                text = re.sub(r"'{2,5}", "", text)
                text = re.sub(r"^[=|!#*:;\-]+|[=]+$", "", text, flags=re.M)
            elif isinstance(data, dict) and isinstance(data.get("query", {}).get("pages"), list) and data["query"]["pages"]:
                page = data["query"]["pages"][0]
                text = str(page.get("extract") or "")
                title = str(page.get("title") or title)
                links = [urljoin(final_url, "/wiki/" + str(row.get("title") or "").replace(" ", "_"))
                         for row in (page.get("links") or []) if row.get("title")]
                links = _related_links(final_url, links)
            else:
                text = json.dumps(data, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            raise ValueError("The source claimed to be JSON but was not valid JSON.") from exc
    elif "html" in content_type or "<html" in decoded[:1000].lower():
        parser = _ReadablePage(); parser.feed(decoded)
        title = parser.title or title
        text = "\n".join(dict.fromkeys(parser.parts))
        links = _related_links(final_url, parser.links)
    else:
        text = decoded
    text = re.sub(r"\n{3,}", "\n\n", text).strip()[:8000]
    if len(text) < 80:
        raise ValueError("The source did not expose enough readable text to import.")
    keywords = " ".join(dict.fromkeys(re.findall(r"[A-Za-z0-9'ōū-]{4,}", f"{title} {text[:5000]}")))[:1000]
    claims = _extract_local_claims(title, claim_source or text)
    entry = {"title": str(title)[:160], "keys": keywords, "text": text, "source": urlparse(final_url).hostname,
             "source_type": source_type, "citation": final_url, "claims": claims,
             "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return entry, links


def _extract_local_claims(title, text):
    """Extract only explicit fact-label rows; never ask AI to summarize."""
    allowed = {"status", "affiliation", "occupation", "rank", "class", "species", "race", "birthday",
               "age", "ability", "abilities", "debut", "location", "leader", "owner", "type"}
    claims = {}
    for line in str(text or "").splitlines():
        match = re.match(r"^\s*(?:\||\*\*)?\s*([A-Za-z][A-Za-z _-]{1,32})\s*(?:=|:)\s*(.{1,300})$", line.strip())
        if not match:
            continue
        field = re.sub(r"\s+", " ", match.group(1).strip().lower())
        if field not in allowed:
            continue
        value = re.sub(r"\{\{[^{}]*\}\}|<[^>]+>|'{2,5}", "", match.group(2))
        value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", value)
        value = re.sub(r"\s+", " ", value).strip(" |")
        if 1 < len(value) <= 240:
            claims[f"{str(title).strip().lower()}::{field}"] = value
        if len(claims) >= 20:
            break
    return claims


def _save_web_entry(entry, world):
    final_url = entry["citation"]
    digest = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:14]
    target = USER_LORE_DIR / f"web_{safe_filename(world)}_{digest}.json"
    target.write_text(json.dumps({world: [entry]}, indent=2, ensure_ascii=False), encoding="utf-8")
    reload_lore()
    return target


def import_lore_url(url, world="Custom World", source_type="wiki", auto_refresh=True, discover=False):
    """Download one approved source and register it for optional refresh."""
    source_type = str(source_type or "wiki").lower().strip()
    if source_type not in SOURCE_AUTHORITY:
        source_type = "unknown"
    download = _fetch_lore_url(url)
    entry, links = _entry_from_download(download, world, source_type)
    target = _save_web_entry(entry, world)
    record = register_lore_source(download["url"], world, source_type, enabled=auto_refresh, discover=discover)
    data = _automation_data()
    stored = next((row for row in data["sources"] if row.get("id") == record["id"]), None)
    if stored is not None:
        stored.update({"last_checked": entry["updated_at"], "last_updated": entry["updated_at"],
                       "etag": download.get("etag", ""), "last_modified": download.get("last_modified", ""),
                       "content_hash": hashlib.sha256(entry["text"].encode("utf-8")).hexdigest(),
                       "status": "updated", "error": "", "related_found": len(links)})
        _save_automation(data)
    return {"name": target.name, "path": str(target), "entries": 1, "worlds": [world],
            "citation": download["url"], "updated": True, "auto_source": record, "related_found": len(links)}


def _source_due(source, settings, now):
    if not source.get("enabled", True):
        return False
    try:
        checked = datetime.fromisoformat(str(source.get("last_checked") or "").replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return now - checked >= timedelta(days=int(settings.get("interval_days", 30)))


def refresh_lore_sources(force=False, world=None):
    """Refresh due approved sources with zero AI calls.

    HTML extraction, checksums, conditional requests, discovery and authority
    ranking are local.  Explicit claim conflicts stay visible and are included
    only in a later *relevant* normal GM prompt, avoiding a separate summary
    call for every downloaded page.
    """
    data = _automation_data()
    settings = data["settings"]
    now = datetime.now(timezone.utc)
    if not settings.get("enabled") and not force:
        return {"status": "disabled", "checked": 0, "updated": 0, "unchanged": 0, "failed": 0,
                "discovered": 0, "ai_calls": 0}
    candidates = [row for row in data["sources"] if (not world or row.get("world") == world)
                  and (force or _source_due(row, settings, now))]
    candidates = candidates[:int(settings.get("max_pages_per_refresh", 8))]
    result = {"status": "complete", "checked": 0, "updated": 0, "unchanged": 0, "failed": 0,
              "discovered": 0, "ai_calls": 0, "errors": []}
    known = {(row.get("world"), row.get("url")) for row in data["sources"]}
    for source in candidates:
        result["checked"] += 1
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            download = _fetch_lore_url(source.get("url"), source)
            source["last_checked"] = checked_at
            source["etag"] = download.get("etag", source.get("etag", ""))
            source["last_modified"] = download.get("last_modified", source.get("last_modified", ""))
            if download.get("not_modified"):
                source["status"] = "unchanged"
                source["error"] = ""
                result["unchanged"] += 1
                continue
            entry, links = _entry_from_download(download, source.get("world", "Custom World"), source.get("source_type", "wiki"))
            digest = hashlib.sha256(entry["text"].encode("utf-8")).hexdigest()
            if digest == source.get("content_hash"):
                source["status"] = "unchanged"
                result["unchanged"] += 1
            else:
                _save_web_entry(entry, source.get("world", "Custom World"))
                source.update({"last_updated": checked_at, "content_hash": digest, "status": "updated"})
                result["updated"] += 1
            source["error"] = ""
            source["related_found"] = len(links)
            if settings.get("discover_related_pages") and source.get("discover"):
                remaining = int(settings.get("max_pages_per_refresh", 8)) - result["discovered"]
                for link in links[:max(0, remaining)]:
                    key = (source.get("world"), link)
                    if key in known:
                        continue
                    source_id = hashlib.sha256(f"{key[0]}|{link}".encode("utf-8")).hexdigest()[:16]
                    data["sources"].append({"id": source_id, "url": link, "world": key[0],
                                            "source_type": source.get("source_type", "wiki"), "enabled": True,
                                            "discover": False, "discovered_from": source.get("url"), "status": "queued"})
                    known.add(key)
                    result["discovered"] += 1
        except Exception as exc:
            source.update({"last_checked": checked_at, "status": "error", "error": str(exc)[:300]})
            result["failed"] += 1
            result["errors"].append({"url": source.get("url"), "error": str(exc)[:300]})
    data["history"].append({"at": now.isoformat(timespec="seconds"), **{k: v for k, v in result.items() if k != "errors"}})
    data["history"] = data["history"][-25:]
    _save_automation(data)
    return result


def lore_automation_status(world=None):
    data = _automation_data()
    now = datetime.now(timezone.utc)
    sources = [dict(row) for row in data["sources"] if not world or row.get("world") == world]
    conflicts = detect_lore_conflicts([entry for world_name in ([world] if world else BUILTIN_LORE) for entry in all_lore_entries(world_name)])
    return {"settings": data["settings"], "sources": sources,
            "due": sum(_source_due(row, data["settings"], now) for row in sources),
            "conflict_queue": conflicts, "last_run": data["history"][-1] if data["history"] else None,
            "cost_policy": {"routine_refresh_ai_calls": 0,
                            "conflicts": "Authority-ranked locally; relevant disputed evidence is included in the next normal GM call only."}}

def _normalized_entry(entry, default_source="Source not recorded", default_type="unknown"):
    row = dict(entry)
    row["source"] = str(row.get("source") or default_source)
    row["source_type"] = str(row.get("source_type") or default_type).lower()
    row["authority"] = SOURCE_AUTHORITY.get(row["source_type"], SOURCE_AUTHORITY["unknown"])
    row["citation"] = str(row.get("citation") or row.get("url") or "")
    row["claims"] = row.get("claims") if isinstance(row.get("claims"), dict) else {}
    return row


def detect_lore_conflicts(entries):
    """Resolve explicit claim conflicts while retaining the losing evidence."""
    claims = {}
    for entry in entries:
        for key, value in entry.get("claims", {}).items():
            claims.setdefault(str(key).strip().lower(), []).append((str(value).strip(), entry))
    conflicts = []
    for claim, rows in claims.items():
        values = {value.lower() for value, _ in rows if value}
        if len(values) <= 1:
            continue
        ranked = sorted(rows, key=lambda row: (-row[1].get("authority", 0), row[1].get("source", "")))
        winner_value, winner = ranked[0]
        conflicts.append({"claim": claim, "resolution": winner_value, "authority": winner.get("authority", 0),
                          "source": winner.get("source", "Unknown"), "source_type": winner.get("source_type", "unknown"),
                          "alternatives": [{"value": value, "source": entry.get("source", "Unknown"),
                                            "source_type": entry.get("source_type", "unknown"), "authority": entry.get("authority", 0)}
                                           for value, entry in ranked[1:] if value.lower() != winner_value.lower()]})
    return conflicts


def all_lore_entries(world):
    entries = [_normalized_entry(entry, "Built-in Worldwalker notes", "curated") for entry in BUILTIN_LORE.get(world, BUILTIN_LORE["Custom World"])]
    entries.extend(_external_entries().get(world, []))
    return [_normalized_entry(entry, entry.get("source", "Imported lore"), entry.get("source_type", "imported")) for entry in entries]


def _cache_key(world, query, state, limit):
    location = str((state or {}).get("location", "")).strip().lower()
    skills = (state or {}).get("skills", {})
    skill_names = sorted(str(x).lower() for x in (skills.keys() if isinstance(skills, dict) else skills if isinstance(skills, list) else []))[:30]
    # Narrative wording varies wildly while retrieval meaning usually does
    # not. A normalized keyword key lets repeated questions/actions reuse the
    # same ranked evidence without retaining any campaign secrets globally.
    terms = sorted(set(re.findall(r"[a-z0-9'-]{3,}", str(query or "").lower())))[:40]
    canon_day = int((state or {}).get("canon_day", -10**9) or -10**9)
    return (str(world), tuple(terms), location, tuple(skill_names), canon_day, int(limit), _LORE_CACHE_STATS["generation"])


def retrieve_lore(world, query, state=None, limit=5):
    key = _cache_key(world, query, state, limit)
    if key in _LORE_CACHE:
        _LORE_CACHE_STATS["hits"] += 1
        return copy.deepcopy(_LORE_CACHE[key])
    _LORE_CACHE_STATS["misses"] += 1
    current_day = int((state or {}).get("canon_day", -10**9) or -10**9)
    entries = [entry for entry in all_lore_entries(world)
               if int(entry.get("min_canon_day", -10**9) or -10**9) <= current_day]
    query_blob = " ".join([str(query or ""), str((state or {}).get("location", "")), " ".join((state or {}).get("skills", {}).keys())]).lower()
    terms = set(re.findall(r"[a-z0-9'-]+", query_blob))
    fts_selected = _fts_retrieve(world, {term for term in terms if len(term) > 2}, current_day, limit)
    if fts_selected:
        _LORE_CACHE[key] = copy.deepcopy(fts_selected)
        return copy.deepcopy(fts_selected)
    ranked = []
    for index, entry in enumerate(entries):
        hay = f"{entry.get('title','')} {entry.get('keys','')} {entry.get('text','')}".lower()
        score = sum(3 if term in str(entry.get("keys", "")).lower() else 1 for term in terms if len(term) > 2 and term in hay)
        # Relevance dominates; authority breaks close calls and determines
        # conflict resolution. A forum can still surface when it is the only
        # relevant source, but it cannot silently overrule official material.
        ranked.append((score, entry.get("authority", 0), -index, entry))
    ranked.sort(reverse=True, key=lambda row: (row[0], row[1], row[2]))
    selected = [entry for score, _, _, entry in ranked if score > 0][:limit]
    if not selected:
        selected = [entry for _, _, _, entry in ranked[:min(2, limit)]]
    _LORE_CACHE[key] = copy.deepcopy(selected)
    # Bound memory even across very long sessions with many free-form queries.
    if len(_LORE_CACHE) > 256:
        _LORE_CACHE.pop(next(iter(_LORE_CACHE)))
    return copy.deepcopy(selected)

_LORE_SENSITIVE = re.compile(
    r"\b(?:canon|timeline|history|lore|rule|ability|technique|class|skill|power|haki|devil fruit|nen|hatsu|jutsu|chakra|kekkei|dojutsu|jinch|shikai|bankai|zanpak|kido|hado|bakudo|cursed technique|domain|binding vow|magicule|evolution|tower|floor|quest|faction|clan|division|village|island)\b",
    re.I,
)


def lore_retrieval_decision(world, query, state=None, purpose=""):
    """Estimate when source retrieval will add value instead of prompt bulk."""
    text = str(query or "").strip()
    score, reasons = 0, []
    if purpose in {"opening", "major_event", "advisor", "creative"}:
        score += 45; reasons.append(f"{purpose} task")
    if _LORE_SENSITIVE.search(text):
        score += 35; reasons.append("world-mechanics or canon language")
    proper = [name for name in re.findall(r"(?<![.!?]\s)\b[A-Z][A-Za-z'’-]{2,}(?:\s+[A-Z][A-Za-z'’-]{2,})*", text)
              if name not in {"The", "This", "That", "What", "When", "Where", "How", "Why", "Please"}]
    if proper:
        score += min(30, 10 + len(proper) * 5); reasons.append("named setting subject")
    memories = (state or {}).get("npc_memories") if isinstance((state or {}).get("npc_memories"), dict) else {}
    if any(str(name).casefold() in text.casefold() for name in memories):
        score += 15; reasons.append("tracked named character")
    if re.search(r"\b(?:create|invent|generate|awaken|learn|research|compare|explain)\b", text, re.I):
        score += 10; reasons.append("authorship or explanation")
    if not text:
        score -= 35; reasons.append("empty query")
    retrieve = score >= 35 or state is None
    decision = {"score": max(0, min(100, score)), "retrieve": retrieve,
                "confidence": "high" if score >= 70 else "medium" if score >= 35 else "campaign-state sufficient",
                "reasons": reasons[:4], "purpose": purpose or "unspecified"}
    if isinstance(state, dict):
        log = state.setdefault("lore_confidence_log", [])
        log.append({"turn": int(state.get("turn", 0) or 0), "query": text[:180], **decision})
        state["lore_confidence_log"] = log[-80:]
    return decision


def format_lore_context(world, query, state=None, limit=5, purpose="", force=False):
    decision = lore_retrieval_decision(world, query, state, purpose)
    entries = retrieve_lore(world, query, state, limit=limit) if force or decision["retrieve"] else []
    identity = canon_identity_context(world, query, state, limit=max(5, limit * 2))
    if not entries and not identity:
        return ""
    conflicts = detect_lore_conflicts(entries)
    lines = [identity] if identity else []
    if entries:
        lines.append("RETRIEVED LORE EVIDENCE (ranked by source authority; preserve uncertainty and never blend incompatible claims):")
        lines.extend(f"- {entry.get('title','Lore')} [{entry.get('source_type','unknown')} {entry.get('authority',0)}/100 · {entry.get('source','Source not recorded')}{' · ' + entry.get('citation') if entry.get('citation') else ''}]: {entry.get('text','')}" for entry in entries)
    if conflicts:
        lines.append("SOURCE CONFLICTS — use the authoritative resolution below and treat alternatives as disputed:")
        lines.extend(f"- {row['claim']}: {row['resolution']} ({row['source']}); disputed by " + ", ".join(x['source'] for x in row['alternatives']) for row in conflicts)
    return "\n".join(lines)


def lore_library_status(world=None, query=""):
    worlds = [world] if world else list(BUILTIN_LORE)
    entries = []
    for world_name in worlds:
        entries.extend(all_lore_entries(world_name))
    conflicts = detect_lore_conflicts(entries)
    return {"authority_scale": SOURCE_AUTHORITY, "conflicts": conflicts,
            "entry_count": len(entries), "highest_authority": max([e.get("authority", 0) for e in entries] or [0]),
            "cache": {**_LORE_CACHE_STATS, "entries": len(_LORE_CACHE), "full_text_index": _ensure_lore_fts()}}
