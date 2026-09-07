"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from canon_integrity import repair_canon_text
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks)
from long_campaign import compact_checkpoint_state, compact_state_for_storage, pre_advance_health_check


DEFAULT_SETTINGS = {
    "provider": "local",
    "local_base_url": "http://localhost:1234/v1",
    "local_token": "",
    "api_key": "",
    "model": "",
    "secondary_model": "",
    "narration": "Concise",
    "autosave": True,
    "sound_enabled": True,
    "music_enabled": True,
    "music_volume": 0.35,
    "animations_enabled": True,
    "portrait_generation_enabled": True,
    "image_model": "gpt-image-2",
    "local_image_model": "",
    "portrait_quality": "low",
    "developer_mode": False,
}


WORLD_STARTER_GEAR = {
    "One Piece": "Travel-worn weapon and island supplies",
    "Hunter x Hunter": "Practical travel gear and training wraps",
    "Naruto": "Kunai pouch, shuriken and field supplies",
    "Solo Max-Level Newbie": "Beginner weapon and emergency potion",
    "Overgeared": "Beginner equipment set and trade tools",
    "Reincarnated as a Slime": "Species-appropriate natural weapon or focus",
    "Custom World": "Setting-appropriate weapon and travel kit",
}

WORLD_STARTER_SKILL = {
    "One Piece": "Foundation Combat Style", "Hunter x Hunter": "Conditioned Fundamentals",
    "Naruto": "Academy Fundamentals", "Solo Max-Level Newbie": "System Adaptation",
    "Overgeared": "Class Fundamentals", "Reincarnated as a Slime": "Intrinsic Species Trait",
    "Bleach": "Shinigami Fundamentals", "Custom World": "Background Expertise",
}

POOL_STATS = {
    "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
    "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
    "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
    "Solo Max-Level Newbie": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Overgeared": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
    "Bleach": (("Hakuda", "Willpower"), ("Reiatsu Control", "Willpower")),
    "Custom World": (("Constitution", "Strength"), ("Wisdom", "Intelligence")),
}

ABILITY_ASPECTS = {
    "fire": "Ember", "flame": "Ember", "heat": "Ember", "water": "Tide",
    "wind": "Gale", "air": "Gale", "lightning": "Storm", "electric": "Storm",
    "earth": "Stone", "ice": "Frost", "shadow": "Shadow", "dark": "Shadow",
    "light": "Radiance", "heal": "Renewal", "medical": "Renewal", "sense": "Echo",
    "sensor": "Echo", "speed": "Flash", "strong": "Titan", "strength": "Titan",
}

WORLD_ABILITY_FORMS = {
    "Naruto": [
        ("{aspect} Thread Technique", "a personal chakra transformation discovered during uneven early training",
         "forms fine {aspect_lower}-natured chakra threads for precise attacks, traps, sensing, or utility",
         "complex shapes quickly exhaust chakra and collapse when concentration breaks",
         "improve chakra control, learn the matching nature transformation, and develop larger stable patterns"),
        ("{aspect} Pulse", "an unusual chakra response first triggered during a formative moment",
         "releases a short pulse of {aspect_lower}-aligned chakra whose exact use adapts to the user's intent",
         "has short range and becomes unreliable when emotionally or physically exhausted",
         "practice controlled pulses, study sealing principles, and learn to sustain the effect"),
    ],
    "One Piece": [
        ("{aspect} Imprint Style", "an improvised island fighting art shaped by the character's environment",
         "imprints {aspect_lower}-themed force or motion into strikes, tools, and movement without ignoring physical limits",
         "requires preparation and stamina; stronger effects expose the user to retaliation",
         "condition the body, refine timing, and eventually combine the style with Haki if it is learned"),
        ("{aspect} Instinct", "a rare natural sensitivity that has not yet matured into formal Haki",
         "notices subtle {aspect_lower}-like patterns in danger, movement, and intent a moment earlier than normal",
         "provides impressions rather than certainty and fails amid overwhelming chaos",
         "survive demanding encounters, train awareness, and seek instruction in Observation Haki"),
    ],
    "Hunter x Hunter": [
        ("{aspect} Resonance", "a dormant Nen inclination expressed before the character understands aura",
         "causes aura to resonate with {aspect_lower}-themed conditions and hints at a future personal Hatsu",
         "remains inconsistent until the character properly opens and controls their aura nodes",
         "learn Ten, Ren, Zetsu and Hatsu, then define restrictions that strengthen the effect"),
        ("{aspect} Tell", "an exceptional learned instinct that may later become a Nen technique",
         "reads small bodily and environmental cues through a {aspect_lower}-themed mental association",
         "can be deceived and becomes noisy under stress or unfamiliar conditions",
         "test the instinct, study opponents, and later reinforce it with a suitable Nen category"),
    ],
    "Solo Max-Level Newbie": [
        ("Adaptive Skill: {aspect} Script", "a background-derived trait recognized when the System evaluates the player",
         "builds proficiency when the player repeats successful {aspect_lower}-aligned solutions",
         "starts at low rank and loses efficiency when the same trick is forced into unsuitable situations",
         "meet hidden conditions, diversify applications, and earn System achievements"),
    ],
    "Overgeared": [
        ("Rare Skill: {aspect} Method", "a personal knack translated into a Satisfy-compatible class skill",
         "applies a narrow {aspect_lower}-themed advantage to actions that genuinely fit the character's chosen class and playstyle",
         "the skill cannot replace missing levels, resources, prerequisites, cooldowns, or class compatibility",
         "use it in varied class-appropriate situations, complete related quests, and earn a specialization"),
    ],
    "Reincarnated as a Slime": [
        ("Extra Skill: {aspect} Weave", "a desire and prior-life inclination crystallized into a world-valid skill",
         "shapes magicules into controlled {aspect_lower}-themed effects suited to the user's species",
         "output is limited by magicule capacity, analysis, resistances, and control",
         "increase magicule capacity, analyze related phenomena, and combine compatible skills"),
    ],
    "Custom World": [
        ("{aspect} Gift", "a setting-consistent talent produced from the player's requested parameters",
         "creates a flexible {aspect_lower}-themed effect within the established rules of the custom world",
         "begins narrow in scope and cannot bypass costs, counters, or prerequisites established by the setting",
         "practice its core use, discover its source, and earn broader applications through play"),
    ],
}

WORLD_BACKGROUND_COLOR = {
    "Naruto": ("a retired local shinobi", "a mission-era accident exposed the cost of acting without preparation"),
    "One Piece": ("a weathered island veteran", "a pirate raid forced the community to rely on anyone willing to stand up"),
    "Hunter x Hunter": ("a traveling specialist", "an encounter with a far stronger stranger revealed how large the world really was"),
    "Solo Max-Level Newbie": ("an obsessive strategy partner", "years spent mastering impossible game scenarios turned obscure knowledge into instinct"),
    "Overgeared": ("a demanding workshop senior", "a costly failure made persistence more important than easy talent"),
    "Reincarnated as a Slime": ("an elder familiar with local monsters", "a territorial crisis revealed both the value and danger of unusual abilities"),
    "Custom World": ("a locally respected mentor", "a dangerous incident revealed that talent without understanding creates consequences"),
}

WORLD_BACKGROUND_NAMES = {
    "Naruto": ("Mika Sato", "Daichi Mori", "Ren Aburame"),
    "One Piece": ("Mara Venn", "Old Corin", "Tessa Flint"),
    "Hunter x Hunter": ("Ilya Rook", "Mina Vale", "Toren Ash"),
    "Solo Max-Level Newbie": ("Seo Min-jae", "Han Yu-ri", "Park Do-jin"),
    "Overgeared": ("Elian Voss", "Mira Anvil", "Garron Pell"),
    "Reincarnated as a Slime": ("Rilsa", "Gelm", "Nemu"),
    "Custom World": ("Ari Vale", "Mara Stone", "Toren Reed"),
}

BACKGROUND_HOMES = (
    "A practical household taught them to contribute early, even when its members did not fully understand their ambitions.",
    "They were raised by a small circle of relatives and neighbors whose support came with duties they still feel responsible for.",
    "Their home life was modest and sometimes unstable, making preparation, loyalty, and self-reliance learned habits rather than slogans.",
)



def _save_dir(instance=None):
    """Reads game.SAVE_DIR live (falling back to util's) so tests — and any
    real caller — can redirect where saves land by patching game.SAVE_DIR,
    exactly like the original single-file game.py allowed. Deferred import:
    by the time this runs, game.py has already finished importing us."""
    if instance is not None and getattr(instance, "save_dir", None):
        return Path(instance.save_dir)
    import game
    return getattr(game, "SAVE_DIR", SAVE_DIR)


class PersistenceMixin:
    def savepath(self):
        shared = getattr(self, "shared_save_path", None)
        if shared:
            return Path(shared)
        return _save_dir(self) / (safe_filename(self.state.get("name", "Traveler")) + "_" + safe_filename(self.state.get("world", "World")) + ".json")

    def save_bundle(self, kind="manual"):
        self.state["campaign_last_saved_version"] = APP_VERSION
        pre_advance_health_check(self.state, source=f"before_{kind}_save")
        checkpoint_limit = 2 if kind == "autosave" else 4
        return {
            "version": APP_VERSION,
            "schema_version": self.state.get("schema_version", 4),
            "save_kind": kind,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "campaign": {"name": self.state.get("name", "Traveler"), "world": self.state.get("world", "World"), "turn": self.state.get("turn", 0), "world_time": self.state.get("world_time", "")},
            "state": compact_state_for_storage(self.state), "history": self.history[-600:],
            "checkpoints": [compact_checkpoint_state(row) for row in self.checkpoints[-checkpoint_limit:]],
            "story_log": self.story_log[-1200:], "system_log": self.system_log[-400:],
        }

    def write_save_atomic(self, path, kind="manual"):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        bundle = self.save_bundle(kind)
        encoded = (json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
                   if kind == "autosave" else json.dumps(bundle, indent=2, ensure_ascii=False))
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)

    def save(self):
        p = self.savepath()
        self.write_save_atomic(p, "manual")
        return str(p)

    def autosave_candidates(self, stem):
        auto_dir = _save_dir(self) / "_autosaves"
        candidates = list(auto_dir.glob(stem + "_autosave_*.json"))
        current = auto_dir / f"{stem}_autosave.json"
        if current.exists(): candidates.append(current)
        return sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)

    def autosave(self):
        if self.settings.get("autosave", True):
            try:
                auto_dir = _save_dir(self) / "_autosaves"
                auto_dir.mkdir(parents=True, exist_ok=True)
                stem = self.savepath().stem
                target = auto_dir / f"{stem}_autosave.json"
                self.write_save_atomic(target, "autosave")
                # v2.5.1 uses one rolling autosave per campaign. Remove older
                # numbered rotations after the new atomic save is safely in place.
                for legacy in auto_dir.glob(stem + "_autosave_*.json"):
                    legacy.unlink(missing_ok=True)
                self.last_autosave = datetime.now().isoformat(timespec="seconds")
                self.state["last_autosave"] = self.last_autosave
            except Exception as e:
                self.log("Autosave failed: " + str(e))

    def _save_entry(self, p, kind):
        try:
            bundle = json.loads(p.read_text(encoding="utf-8"))
            campaign = bundle.get("campaign", {})
            version = str(bundle.get("version") or bundle.get("state", {}).get("campaign_created_version") or "Legacy")
            prefix = "Autosave — " if kind == "autosave" else ""
            label = f"{prefix}{campaign.get('name', p.stem)} · {campaign.get('world', 'World')} · Turn {campaign.get('turn', 0)}"
            return {"id": ("autosave/" + p.name) if kind == "autosave" else p.stem,
                    "label": label, "kind": kind, "saved_at": bundle.get("saved_at", ""),
                    "version": version, "schema_version": bundle.get("schema_version", 1),
                    "corrupt": False, "recoverable": kind == "manual" and bool(self.autosave_candidates(p.stem))}
        except Exception as exc:
            return {"id": ("autosave/" + p.name) if kind == "autosave" else p.stem,
                    "label": f"Unreadable save — {p.stem}", "kind": kind,
                    "saved_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes"),
                    "version": "Unknown", "corrupt": True, "error": str(exc)[:180],
                    "recoverable": kind == "manual" and bool(self.autosave_candidates(p.stem))}

    def list_saves(self):
        items = []
        for p in sorted(_save_dir(self).glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            items.append(self._save_entry(p, "manual"))
        auto_dir = _save_dir(self) / "_autosaves"
        if auto_dir.exists():
            newest_by_campaign = {}
            for p in sorted(auto_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
                campaign_key = re.sub(r"_autosave(?:_\d+)?$", "", p.stem)
                newest_by_campaign.setdefault(campaign_key, p)
            for p in newest_by_campaign.values():
                items.append(self._save_entry(p, "autosave"))
        return items

    def save_path_for_id(self, name):
        raw = str(name or "")
        if raw.startswith("autosave/"):
            return _save_dir(self) / "_autosaves" / Path(raw.split("/", 1)[1]).name
        return _save_dir(self) / f"{safe_filename(raw)}.json"

    def delete_save(self, name):
        p = self.save_path_for_id(name)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError("That campaign save no longer exists.")
        p.unlink()
        if not str(name or "").startswith("autosave/"):
            for autosave in self.autosave_candidates(p.stem):
                autosave.unlink(missing_ok=True)
        return {"deleted": str(name), "recoverable": False}

    def import_bundle(self, bundle):
        if not isinstance(bundle, dict) or not isinstance(bundle.get("state"), dict):
            raise ValueError("This is not a Worldwalker campaign export.")
        source_version = str(bundle.get("version", "Legacy"))
        imported_state = migrate_state(bundle["state"], source_version)
        normalize_quest_state_machine(imported_state)
        base = safe_filename(imported_state.get("name", "Imported") + "_" + imported_state.get("world", "World"))
        target = _save_dir(self) / f"{base}.json"
        suffix = 2
        while target.exists():
            target = _save_dir(self) / f"{base}_{suffix}.json"; suffix += 1
        clean = {
            "version": APP_VERSION, "schema_version": imported_state.get("schema_version", 4),
            "save_kind": "imported", "saved_at": datetime.now().isoformat(timespec="seconds"),
            "campaign": {"name": imported_state.get("name", "Traveler"), "world": imported_state.get("world", "World"),
                         "turn": imported_state.get("turn", 0), "world_time": imported_state.get("world_time", "")},
            "state": imported_state, "history": bundle.get("history", [])[-1000:],
            "checkpoints": [compact_checkpoint_state(row) for row in bundle.get("checkpoints", [])[-4:] if isinstance(row, dict)],
            "story_log": bundle.get("story_log", [])[-1200:],
            "system_log": bundle.get("system_log", [])[-400:], "imported_from_version": source_version,
        }
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(target)
        return {"id": target.stem, "version": source_version}

    def recover_save(self, name):
        stem = safe_filename(str(name).removesuffix(".json"))
        candidates = self.autosave_candidates(stem)
        if not candidates:
            raise FileNotFoundError("No autosave recovery snapshot exists for that campaign.")
        return self.load("autosave/" + candidates[0].name)

    # How long the player has to have actually been away before a "since you
    # left" recap is worth generating — short reload-mid-session gaps (a
    # crash recovery, switching saves to check something) shouldn't trigger
    # an AI call just because the exact save timestamp is a few minutes old.
    REENTRY_RECAP_THRESHOLD_HOURS = 4

    def load(self, name):
        p = self.save_path_for_id(name)
        b = json.loads(p.read_text(encoding="utf-8"))
        with self.lock:
            had_canon_clock = "canon_time_minutes" in b.get("state", {})
            self.state = migrate_state(b["state"], b.get("version", "Legacy"))
            normalize_quest_state_machine(self.state)
            self.history = b.get("history", [])[-600:]
            self.checkpoints = [compact_checkpoint_state(row) for row in b.get("checkpoints", [])[-4:] if isinstance(row, dict)]
            self.story_log = b.get("story_log", [])[-1200:]
            self.system_log = b.get("system_log", [])[-400:]
            # Visible Chronicle rows live outside state in the save bundle.
            # Scan them after state migration, retain the historical text,
            # and surface one transparent correction immediately on load.
            known_repairs = set(self.state.setdefault("canon_integrity_repairs", []))
            external_repairs = []
            for row in self.story_log[-250:]:
                if not isinstance(row, dict):
                    continue
                _, notes = repair_canon_text(self.state.get("world", "Custom World"), row.get("text", ""), self.state)
                external_repairs.extend(note for note in notes if note not in known_repairs)
            if external_repairs:
                self.state.setdefault("_pending_chronicle_notes", []).append(
                    "[CANON CORRECTION]\n" + "; ".join(dict.fromkeys(external_repairs)) +
                    ". Future narration will use the corrected assignment."
                )
                known_repairs.update(external_repairs)
                self.state["canon_integrity_repairs"] = sorted(known_repairs)[-100:]
            for note in self.state.pop("_pending_chronicle_notes", []):
                self.append(note, "meta")
            if not had_canon_clock:
                canon = timeline_for(self.state.get("world", "Custom World"))
                day = int(canon.get("start_day", -7))
                self.state["canon_day"] = day
                self.state["canon_time_minutes"] = day * 1440 + 480
                self.state["canon_anchor"] = canon.get("anchor", "Before the main story")
            self.campaign_active = True
            # Purely a real-world-clock signal, not in-game time — ordinary
            # player inaction can never advance world_time/canon_day (that's
            # a hard rule elsewhere), so "the world moves while I'm doing
            # nothing" can only ever mean "while I was away from the app."
            # Flagged here, generated on demand via generate_reentry_recap()
            # so a plain load stays fast instead of blocking on an AI call.
            saved_at = str(b.get("saved_at") or "").strip()
            self._pending_reentry_hours = None
            if saved_at:
                try:
                    gap_hours = (datetime.now() - datetime.fromisoformat(saved_at)).total_seconds() / 3600.0
                    if gap_hours >= self.REENTRY_RECAP_THRESHOLD_HOURS:
                        self._pending_reentry_hours = round(gap_hours, 1)
                except ValueError:
                    pass
        result = self.public_state()
        result["_reentry_gap_hours"] = self._pending_reentry_hours
        return result
