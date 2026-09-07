"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, power_profile_for
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, scene_art_confidence, scene_selection_reason, scene_display_label, scene_art_signature, scene_context
from reliability import visible_class_profile, visible_skills
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks, tension_level,
                     resolve_shop_purchase, resolve_purchase_offer,
                     resolve_finance_debt)
from simulation_integrity import integrity_snapshot
from campaign_reliability import learn_player_style


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
    "Bleach": "Zanpakuto (or, before awakened powers, an ordinary student's belongings)",
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



class JournalMixin:
    def quest_note(self, name, note):
        needle = str(name or "").strip().lower()
        for collection in (self.state.get("quests", []), self.state.get("quest_archive", [])):
            for quest in collection:
                if isinstance(quest, dict) and str(quest.get("name", "")).lower() == needle:
                    quest["player_notes"] = str(note or "")[:4000]
                    self.autosave()
                    return quest
        raise KeyError("Quest not found.")

    def buy_shop_item(self, shop_name, item_name):
        ok, message, price = resolve_shop_purchase(self.state, shop_name, item_name)
        if not ok:
            raise ValueError(message)
        self.append(message, "meta")
        self.autosave()
        return {"message": message, "price": price, "currency": self.state.get("currency"), "inventory": self.state.get("inventory"), "story": self._flush_story()}

    def buy_purchase_offer(self, offer_id):
        ok, message, price = resolve_purchase_offer(self.state, offer_id)
        if not ok:
            raise ValueError(message)
        self.append(message, "meta")
        self.autosave()
        return {"message": message, "price": price, "currency": self.state.get("currency"), "inventory": self.state.get("inventory"), "story": self._flush_story()}

    def pay_finance_debt(self, debt_id, amount=None):
        ok, message, paid = resolve_finance_debt(self.state, debt_id, amount)
        if not ok:
            raise ValueError(message)
        self.append(message, "meta")
        self.autosave()
        return {"message": message, "paid": paid, "currency": self.state.get("currency"),
                "finance_debts": self.state.get("finance_debts", []), "story": self._flush_story()}

    def rate_last_turn_good(self):
        """Snapshots the most recent resolved turn ({turn, action, outcome},
        already recorded in campaign_canon) into rated_good_turns — a small,
        player-curated pool resolve() draws from to show the model a real
        example from THIS campaign instead of a hand-written generic one.
        Snapshotting (not just referencing a turn number) means the example
        survives even if campaign_canon later trims that entry off."""
        canon = self.state.get("campaign_canon") or []
        if not canon:
            raise ValueError("There's no turn to rate yet.")
        last = canon[-1]
        rated = [r for r in (self.state.get("rated_good_turns") or []) if r.get("turn") != last.get("turn")]
        rated.append({"turn": last.get("turn"), "action": str(last.get("action") or "")[:500], "outcome": str(last.get("outcome") or "")[:1200]})
        self.state["rated_good_turns"] = rated[-5:]
        learn_player_style(self.state)
        self.autosave()
        return {"rated_turn": last.get("turn")}

    def visible_schedule(self):
        visible = []
        for event in self.state.get("scheduled_events", []):
            if not isinstance(event, dict):
                continue
            visibility = str(event.get("visibility", "confirmed")).lower()
            if visibility == "hidden":
                continue
            item = copy.deepcopy(event)
            if visibility == "rumor":
                item.pop("secret_conditions", None)
                item["certainty"] = "Rumor"
            else:
                item["certainty"] = item.get("certainty", "Confirmed")
            visible.append(item)
        for quest in self.state.get("quests", []):
            if isinstance(quest, dict) and quest.get("deadline"):
                visible.append({"title": quest.get("name"), "when": quest.get("deadline"), "type": "quest_deadline", "certainty": "Confirmed"})
        return visible

    def diagnostics_snapshot(self):
        scene_url, scene_category_name = scene_image_url(self.state)
        return {
            "app_version": APP_VERSION, "schema_version": self.state.get("schema_version"),
            "campaign": {"name": self.state.get("name"), "world": self.state.get("world"), "turn": self.state.get("turn")},
            "scene": {"category": scene_category_name, "label": scene_display_label(self.state, scene_url, scene_category_name), "image": scene_url, "location": self.state.get("location"), "weather": self.state.get("weather"), "context": scene_context(self.state),
                      "confidence": scene_art_confidence(self.state), "reason": scene_selection_reason(self.state)},
            "portrait": portrait_view(self.state, self.settings), "last_assessment": self.last_assessment,
            "last_lore_context": self.last_lore_context, "validation_log": self.state.get("validation_log", [])[-30:],
            "continuity": self.state.get("continuity_ledger", {}), "system_log": self.system_log[-100:],
            "world_pack_id": self.state.get("world_pack_id", "builtin"), "last_autosave": self.state.get("last_autosave", ""),
            "turn_recovery": {"last_failed": {k: copy.deepcopy(v) for k, v in self.state.get("last_failed_turn", {}).items() if k != "work"},
                              "timeline": copy.deepcopy((self.state.get("recovery_timeline") or [])[-12:])},
            "active_scenario": copy.deepcopy((self.state.get("scenario_memory") or {}).get("active", {})),
            "recent_milestones": copy.deepcopy((self.state.get("world_milestones") or [])[-12:]),
            "last_ai_route": copy.deepcopy(self.state.get("last_ai_route", {})),
            "simulation": {"profile": self.simulation_profile(),
                           "npc_intentions": len(self.state.get("npc_intentions", {})),
                           "event_records": len(self.state.get("simulation_events", [])),
                           "local_background_turn": self.state.get("local_background_turn", 0),
                           "integrity": integrity_snapshot(self.state)},
        }

    def _flush_story(self):
        out = self.story_log
        self.story_log = []
        return out

    def public_state(self):
        s = copy.deepcopy(self.state)
        from world_calendar import view as calendar_view, time_label
        s['_world_calendar'] = calendar_view(self.state)
        s['world_time'] = time_label(self.state)
        s.pop("_request_receipts", None)
        from turn_recovery import guard
        s["_recovery_guard"] = guard(self.state)
        from build_info import BUILD_ID
        s["_build_id"] = BUILD_ID
        from organizations import roster_view
        s["_organization_roster"] = roster_view(self.state)
        s.pop("organizations", None)
        s.pop("organization_lives", None)
        from chapter_recaps import chapter_view
        s["chapter_summaries"] = [chapter_view(row, s.get("name", "")) for row in s.get("chapter_summaries", []) if isinstance(row, dict)]
        if isinstance(s.get("last_failed_turn"), dict):
            s["last_failed_turn"].pop("work", None)
        # Governance bookkeeping powers narrative reports and map changes,
        # but is intentionally not a visible management dashboard.
        s.pop("polity_state", None)
        s.pop('world_plans',None)
        s.pop('relationship_life',None)
        s.pop('world_benefits',None)
        # Latent Nen is fixed at creation so later awakening is consistent,
        # but its category/name/mechanics must not leak through the state API
        # before the character discovers Nen in the story.
        s.pop("_latent_nen_profile", None)
        try:
            s["_canon_countdown"] = self.canon_countdown()
        except Exception:
            s["_canon_countdown"] = {"available": False}
        scene_url, cat = scene_image_url(self.state)
        s["_scene_image"] = scene_url
        s["_scene_category"] = cat
        s["_scene_label"] = scene_display_label(self.state, scene_url, cat)
        s["_scene_confidence"] = scene_art_confidence(self.state, cat)
        s["_scene_reason"] = scene_selection_reason(self.state)
        s["_scene_context"] = scene_context(self.state)
        s["_scene_signature"] = scene_art_signature(self.state)
        s["_scene_regeneration_policy"] = "Reuse cached art until the physical location, encounter type, or active major event changes."
        s["class_profile"] = visible_class_profile(self.state)
        s["skills"] = visible_skills(self.state)
        if isinstance(s.get("special", {}).get("Hidden Class"), dict):
            s["special"]["Hidden Class"] = copy.deepcopy(s["class_profile"])
        s.update(portrait_view(self.state, self.settings))
        s["_stat_style"] = stat_style_for(self.state.get("world", "Custom World"))
        s["_uses_xp"] = uses_xp_for(self.state.get("world", "Custom World"), self.state.get("custom_world", ""))
        s["_tracks_currency"] = bool(expansion_for(self.state.get("world", "Custom World")).get("tracks_currency", True))
        s["_gear_style"] = gear_style_for(self.state.get("world", "Custom World"))
        s["_power_profile"] = power_profile_for(
            self.state.get("world", "Custom World"), self.state.get("stats", {}),
            self.state.get("special", {}).get("Archetype", ""),
        )
        s["_app_version"] = APP_VERSION
        s["_last_autosave"] = self.state.get("last_autosave", self.last_autosave)
        deadline = self.state.get("tower_floor_deadline_day")
        if self.state.get("world") == "Solo Max-Level Newbie" and isinstance(deadline, (int, float)) and not self.state.get("tower_over"):
            s["_tower_days_left"] = max(0, int(deadline - self.state.get("canon_day", 0)))
        s["_tension"] = tension_level(self.state)
        return s
