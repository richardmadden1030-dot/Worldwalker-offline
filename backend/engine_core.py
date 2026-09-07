"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading, traceback
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, world_supports_races, WORLD_RACES, tower_floor_theme, TOWER_FLOOR_COUNT, tower_band, power_profile_for
from world_progression import WORLD_MECHANIC_RULES, NARRATIVE_CRAFTING_RULE
from world_activity import activity_rules_for
from world_depth import world_depth_rules
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state, normalize_combat_payload
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks, pacing_guidance, active_nemesis_threats,
                     uses_literal_quests)
from knowledge import npc_knowledge_boundaries, concealed_player_facts
from simulation import (compile_context_snapshot, normalize_simulation_mode,
                        simulation_profile, output_budget)
from simulation_enhancements import apply_prompt_budget
from simulation_integrity import canon_dependency_graph, campaign_search
from overgeared_classes import canon_class_prompt_reference
from ability_archive import GeneratedAbilityArchive
from simulation_core import refresh_simulation_core, action_commits_violence
from canon_integrity import canon_identity_context, repair_canon_payload
from campaign_reliability import (
    build_grounding_packet, refresh_scene_state, learn_player_style,
    refresh_canon_divergence_impacts, reconcile_commitments_and_consequences,
)
from response_guard import normalize_turn_response
from long_campaign import pre_advance_health_check, record_runtime_error
from gm_consistency import CONSISTENCY_RULE, prepare_request, semantic_issues
from gm_policy import (
    enforce_response_policy, intent_prompt, parse_player_intent, prompt_modules,
    select_approved_example, temporal_budget,
)


DEFAULT_SETTINGS = {
    "provider": "local",
    "local_base_url": "http://localhost:1234/v1",
    "local_token": "",
    "api_key": "",
    "model": "",
    "secondary_model": "",
    "major_event_model": "",
    "advisor_model": "",
    "advisor_provider": "inherit",
    "creative_model": "",
    "creative_provider": "inherit",
    "max_ai_cost_per_request_usd": 0.0,
    "max_ai_cost_per_turn_usd": 0.0,
    "max_ai_retries_per_turn": 2,
    "session_budget_warning_usd": 5.0,
    "narration": "Concise",
    "autosave": True,
    "sound_enabled": True,
    "music_enabled": True,
    "music_volume": 0.35,
    "animations_enabled": True,
    "portrait_generation_enabled": True,
    "portrait_auto_generate": False,
    "image_model": "gpt-image-2",
    "image_provider": "inherit",
    "local_image_base_url": "",
    "local_image_model": "",
    "portrait_quality": "low",
    "simulation_mode": "balanced",
    "local_reentry_recap": True,
    "local_combat_recap": True,
    "local_message_gate": True,
    "canon_foreknowledge": False,
    "developer_mode": False,
    "onboarding_seen": False,
    "ai_connection_status": "untested",
    "ai_validated_model": "",
    "ai_validated_provider": "",
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



class CoreMixin:
    def __init__(self, save_dir=None, settings_path=None, account_id=""):
        self.lock = threading.RLock()
        # None preserves the original test/desktop behavior where callers may
        # redirect game.SAVE_DIR after constructing the session. Friend-server
        # sessions always receive an explicit private directory.
        self.save_dir = Path(save_dir) if save_dir else None
        self.settings_path = Path(settings_path) if settings_path else SETTINGS_PATH
        self.account_id = str(account_id or "")
        (self.save_dir or SAVE_DIR).mkdir(parents=True, exist_ok=True)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.generated_ability_archive = GeneratedAbilityArchive(
            self.settings_path.with_name("generated_abilities.json")
        )
        self.settings = self.load_settings()
        self.ai = self.make_client(self.settings.get("model", ""))
        self.ai_bg = self.make_client(self.settings.get("secondary_model", "") or self.settings.get("model", ""))
        major_model = self.settings.get("major_event_model", "")
        self.ai_major = self.make_client(major_model) if major_model and major_model != self.settings.get("model", "") else self.ai
        self.ai_advisor = self.make_client(self.settings.get("advisor_model") or self.settings.get("secondary_model") or self.settings.get("model"), self.settings.get("advisor_provider"))
        self.ai_creative = self.make_client(self.settings.get("creative_model") or self.settings.get("secondary_model") or self.settings.get("model"), self.settings.get("creative_provider"))
        self.state = copy.deepcopy(BASE_STATE)
        self.history = []
        self.checkpoints = []
        self.story_log = []   # [{"text":..., "tag":...}]
        self.system_log = []  # [str, ...]
        self.busy = False
        self.campaign_active = False
        self.last_autosave = ""
        self.last_lore_context = ""
        self.last_assessment = {}
        self._pending_reentry_hours = None
        # Set only while a shared multiplayer round is being resolved.  It is
        # deliberately transient: room membership/readiness lives in SQLite,
        # not inside a portable single-player campaign export.
        self.multiplayer_context = None

    def begin_turn_transaction(self, route, payload=None):
        """Capture every mutable campaign surface before a resolving action.

        Checkpoints support intentional Undo.  This snapshot is different: it
        exists only so an exception can never leave half of a failed turn in
        the active campaign.
        """
        payload = payload or {}
        actions = payload.get("orders") if isinstance(payload, dict) else None
        if not isinstance(actions, list):
            actions = payload.get("actions") if isinstance(payload, dict) else None
        pre_advance_health_check(self.state, actions, f"before_{route}")
        from turn_recovery import begin
        begin(self, route, payload)
        return {
            "route": str(route or "turn"), "payload": copy.deepcopy(payload),
            "state": copy.deepcopy(self.state), "history_count": len(self.history),
            "checkpoints_count": len(self.checkpoints), "story_count": len(self.story_log),
            "system_count": len(self.system_log),
        }

    def rollback_turn_transaction(self, transaction, error):
        if not isinstance(transaction, dict):
            return {}
        self.state = transaction["state"]
        self.history = self.history[:int(transaction.get("history_count", 0))]
        self.checkpoints = self.checkpoints[:int(transaction.get("checkpoints_count", 0))]
        self.story_log = self.story_log[:int(transaction.get("story_count", 0))]
        self.system_log = self.system_log[:int(transaction.get("system_count", 0))]
        diagnostic = record_runtime_error(
            self.state, error, transaction.get("route", "turn"), transaction.get("payload", {}),
            traceback.format_exc(),
        )
        row = {
            "route": transaction.get("route", "turn"),
            "payload": copy.deepcopy(transaction.get("payload", {})),
            "error": str(error)[:500], "turn": int(self.state.get("turn", 0) or 0),
            "time": datetime.now().isoformat(timespec="seconds"), "status": "ready_to_retry",
            "error_id": diagnostic.get("id"), "error_type": diagnostic.get("type"),
            "work": copy.deepcopy(getattr(self, "_turn_work", {})),
        }
        self.state["last_failed_turn"] = row
        timeline = self.state.setdefault("recovery_timeline", [])
        timeline.append({key: copy.deepcopy(value) for key, value in row.items() if key not in {"payload", "work"}})
        self.state["recovery_timeline"] = timeline[-24:]
        self._turn_work = None
        try:
            self.autosave()
        except Exception:
            pass
        return row

    def complete_turn_transaction(self, transaction, save=True, include_receipt=True):
        from turn_feedback import build_turn_receipt
        receipt = build_turn_receipt(transaction.get("state", {}), self.state, transaction.get("route", "turn"),
                                     transaction.get("payload", {}).get("request_id", ""),
                                     len(self.story_log) > transaction.get("story_count", len(self.story_log))) if include_receipt else None
        entry = None
        if receipt:
            self.append(receipt["label"], "receipt", canon_day=self.state.get("canon_day"), detail=receipt)
            entry = copy.deepcopy(self.story_log[-1])
        self._turn_work = None
        self.state["last_failed_turn"] = {}
        timeline = self.state.setdefault("recovery_timeline", [])
        timeline.append({"route": transaction.get("route", "turn"), "turn": int(self.state.get("turn", 0) or 0),
                         "time": datetime.now().isoformat(timespec="seconds"), "status": "completed"})
        self.state["recovery_timeline"] = timeline[-24:]
        if save:
            try:
                self.autosave()
            except Exception:
                pass
        return entry

    def load_settings(self):
        try:
            return {**DEFAULT_SETTINGS, **json.loads(self.settings_path.read_text(encoding="utf-8"))}
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def save_settings(self):
        temporary = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def make_client(self, model, provider=None):
        s = self.settings
        provider = provider if provider in {"local", "cloud"} else s.get("provider", "local")
        return AI(
            key=s.get("api_key", ""),
            model=model or DEFAULT_MODEL,
            provider=provider,
            base_url=s.get("local_base_url", "http://localhost:1234/v1"),
            local_token=s.get("local_token", ""),
            max_estimated_cost_usd=s.get("max_ai_cost_per_request_usd", 0),
        )

    def local_mode(self):
        return self.settings.get("provider", "local") != "cloud"

    def ai_ready(self):
        configured = bool(self.settings.get("model", "")) and (self.local_mode() or bool(self.settings.get("api_key", "")))
        # Tests, extensions, and embedded hosts may inject a working client
        # object directly rather than configure a provider connection.
        if configured and not isinstance(self.ai, AI):
            return True
        if self.settings.get("ai_connection_status") != "valid":
            return False
        if self.local_mode():
            return bool(self.settings.get("model", ""))
        return bool(self.settings.get("api_key", "") and self.settings.get("model", ""))

    def ai_bg_ready(self):
        configured = bool(self.settings.get("secondary_model", "") or self.settings.get("model", ""))
        if configured and not isinstance(self.ai_bg, AI):
            return True
        if self.settings.get("ai_connection_status") != "valid":
            return False
        if self.local_mode():
            return bool(self.settings.get("secondary_model", "") or self.settings.get("model", ""))
        return bool(self.settings.get("api_key", "") and (self.settings.get("secondary_model", "") or self.settings.get("model", "")))

    def update_settings(self, patch):
        import math
        patch = dict(patch)
        for field in ("max_ai_cost_per_request_usd", "max_ai_cost_per_turn_usd"):
            if field in patch:
                value = float(patch[field])
                if not math.isfinite(value) or value < 0:
                    raise ValueError("AI cost limits must be finite, nonnegative amounts.")
                patch[field] = value
        if "max_ai_retries_per_turn" in patch:
            value = float(patch["max_ai_retries_per_turn"])
            if not math.isfinite(value) or value != int(value) or not 0 <= value <= 5:
                raise ValueError("Automatic repair limit must be an integer from 0 to 5.")
            patch["max_ai_retries_per_turn"] = int(value)
        self.settings.update(patch)
        self.save_settings()
        self.ai = self.make_client(self.settings["model"])
        self.ai_bg = self.make_client(self.settings.get("secondary_model") or self.settings["model"])
        major_model = self.settings.get("major_event_model", "")
        self.ai_major = self.make_client(major_model) if major_model and major_model != self.settings.get("model", "") else self.ai
        self.ai_advisor = self.make_client(self.settings.get("advisor_model") or self.settings.get("secondary_model") or self.settings.get("model"), self.settings.get("advisor_provider"))
        self.ai_creative = self.make_client(self.settings.get("creative_model") or self.settings.get("secondary_model") or self.settings.get("model"), self.settings.get("creative_provider"))

    def simulation_mode(self):
        return normalize_simulation_mode(self.settings.get("simulation_mode", "balanced"))

    def simulation_profile(self):
        return simulation_profile(self.simulation_mode())

    def detect_models(self, base_url, token):
        client = AI(provider="local", base_url=base_url or "http://localhost:1234/v1", local_token=token or "", model="unused")
        return client.list_models()

    # Pure application bookkeeping the AI never needs to read and must never
    # re-author. A prompt instruction alone isn't reliable protection against
    # this — a smaller/local model prone to pattern-completion over real
    # instruction-following will still often mimic a field's shape just
    # because it saw the key sitting in its own context, wasting output
    # budget re-typing it and raising the odds of getting cut off mid-JSON
    # before the response ever closes. The fix is to not show it the
    # temptation at all rather than trust it to resist one it can see.
    AI_HIDDEN_FIELDS = ("living_world", "generated_content_history", "continuity_ledger", "validation_log", "diagnostics", "canon_events_fired", "pending_minor_events", "calendar_anchor_day", "last_protagonist_tick_day", "active_canon_event", "last_major_beat_day", "progression_ledger", "causality_ledger", "knowledge_audit", "health_repairs", "simulation_events", "local_background_turn", "simulation_validation", "correction_log", "canon_event_states", "advisor_thread", "canon_integrity_repairs", "verified_memory_archive", "memory_consolidation", "consequence_ledger", "scene_history", "outcome_scale_ledger", "lore_confidence_log", "prompt_budget_log", "fact_history")

    AI_HIDDEN_FIELDS = ("adventures", "travel_access", "_world_calendar", "_request_receipts", "_recovery_guard", "relationship_life", "world_plans", "world_benefits", "campaign_arcs", "campaign_arc_archive", "campaign_arc_director", "life_simulation") + AI_HIDDEN_FIELDS

    def _relevant_npc_names(self):
        """Best-effort 'who's actually in play right now': present at the
        current location, a companion, a marked nemesis, or named in the
        last few turns' narrative. Used only to decide which npc_memories
        entries get full detail vs. a compact stub in trimmed_state_for_ai
        — never to drop an NPC from context entirely, so an off-screen
        character the player asks about is still there, just lighter."""
        names = set()
        location = str(self.state.get("location") or "").strip().lower()
        memories = self.state.get("npc_memories") or {}
        for name, memory in memories.items():
            if not isinstance(memory, dict):
                continue
            if location and str(memory.get("last_known_location") or "").strip().lower() == location:
                names.add(name)
            if memory.get("nemesis"):
                names.add(name)
        for c in self.state.get("companions") or []:
            cname = c.get("name") if isinstance(c, dict) else c
            if cname:
                names.add(str(cname))
        recent_text = " ".join(str(entry.get("outcome", "")) for entry in (self.state.get("campaign_canon") or [])[-5:]).lower()
        for name in memories:
            if str(name).lower() in recent_text:
                names.add(name)
        return names

    def trimmed_state_for_ai(self, query="", purpose="moment"):
        """The raw state grows without bound over a long campaign —
        campaign_canon alone can hold up to 250 full turn records. Once a
        stretch of turns has been consolidated into a chapter_summaries
        entry, the older campaign_canon rows it covers are redundant weight
        in every AI call from then on. Trim them (and drop a handful of
        purely mechanical fields entirely) from what's actually SENT to the
        model, not from the saved state itself (the Journal's Chapter Memory
        and Continuity tabs, and campaign export, still want the full
        record)."""
        from life_simulation import normalize as normalize_life_simulation
        normalize_life_simulation(self.state)
        snapshot = dict(self.state)
        for key in self.AI_HIDDEN_FIELDS:
            snapshot.pop(key, None)
        snapshot.pop("last_failed_turn", None)
        snapshot["npc_knowledge_boundaries"] = npc_knowledge_boundaries(self.state)
        snapshot["concealed_player_facts"] = concealed_player_facts(self.state)
        snapshot["authoritative_player_corrections"] = copy.deepcopy((self.state.get("authoritative_corrections") or [])[-30:])
        snapshot["active_action_goals"] = [copy.deepcopy(x) for x in self.state.get("action_goals", [])
                                           if isinstance(x, dict) and x.get("status") == "active"][-12:]
        snapshot["npc_commitment_schedules"] = copy.deepcopy(self.state.get("npc_schedules", {}))
        snapshot["canon_dependency_graph"] = canon_dependency_graph(self.state)
        snapshot["information_in_transit"] = [copy.deepcopy(x) for x in (self.state.get("information_packets") or [])[-30:]
                                               if isinstance(x, dict) and int(x.get("available_after_minutes", 0) or 0) > 0]
        # NPC detail is now trimmed once, at the end of this method, by the
        # query-aware relevance bubble. Doing an earlier fixed eight-person
        # trim here would discard detail before Deep mode or a player-named
        # off-screen character had a chance to retain it.
        # Same relevance-filter idea, applied to the two other fields most
        # likely to balloon over a long campaign as the player travels: a
        # shop discovered three towns ago has no business costing tokens on
        # every turn once the player has moved on, and neither does the
        # free-text notes on a location the player isn't anywhere near.
        # Both only trim detail, never drop an entry — an off-screen shop
        # keeps its name/type/location, an off-screen location keeps its
        # controller and danger level, since either could still matter for
        # an Advisor question or forward planning.
        current_location = str(self.state.get("location") or "")
        shops = snapshot.get("shops")
        if isinstance(shops, list) and len(shops) > 6:
            snapshot["shops"] = [
                sh if not isinstance(sh, dict) or not sh.get("location") or str(sh.get("location")) == current_location
                else {"name": sh.get("name"), "type": sh.get("type"), "location": sh.get("location")}
                for sh in shops
            ]
        location_details = snapshot.get("location_details")
        if isinstance(location_details, dict) and len(location_details) > 10:
            snapshot["location_details"] = {
                name: (detail if name == current_location or not isinstance(detail, dict) else {
                    "controlling_faction": detail.get("controlling_faction"),
                    "danger_level": detail.get("danger_level"),
                })
                for name, detail in location_details.items()
            }
        canon = self.state.get("campaign_canon") or []
        if not canon:
            snapshot.pop("campaign_canon", None)
            compiled = compile_context_snapshot(snapshot, self.state, query, self.simulation_mode())
            from world_plans import context as world_plan_context
            if purpose != 'chat': compiled['world_plan_context']=world_plan_context(self.state)
            return self._prune_ai_context(apply_prompt_budget(compiled, self.state, query, purpose, self.simulation_mode()))
        chapters = self.state.get("chapter_summaries") or []
        if chapters:
            try:
                last_covered_turn = int((chapters[-1].get("turns") or [0, 0])[-1] or 0)
                canon = [entry for entry in canon if int(entry.get("turn", 0) or 0) > last_covered_turn]
            except (TypeError, ValueError, IndexError):
                pass
        # No chapter summary yet to lean on (early campaign) — still cap to a
        # recent tail so a fresh campaign's first few requests aren't already
        # carrying unnecessary bulk.
        snapshot["campaign_canon"] = canon[-15:]
        snapshot.pop('world_plans',None); snapshot.pop('world_benefits',None)
        compiled = compile_context_snapshot(snapshot, self.state, query, self.simulation_mode())
        from world_plans import context as world_plan_context
        if purpose != 'chat': compiled['world_plan_context']=world_plan_context(self.state)
        from atlas_context import gm_map_context
        compiled['map_history'] = gm_map_context(self.state)
        # Polygon vertices, UI caches and empty defaults are saved locally but
        # do not help a stateless narrator. Keep only the territorial facts;
        # the frontend reconstructs/draws exact geometry from the real state.
        if isinstance(compiled.get("political_regions"), list):
            compiled["political_regions"] = [{key: copy.deepcopy(region.get(key)) for key in
                ("id", "name", "controller", "anchor", "scale", "hex_count", "board", "realm", "contested_by", "controller_changed_turn")
                if region.get(key) not in (None, "", [], {})} for region in compiled["political_regions"] if isinstance(region, dict)]
        compiled["recent_state_delta"] = copy.deepcopy((compiled.get("campaign_canon") or [])[-3:])
        compiled = apply_prompt_budget(compiled, self.state, query, purpose, self.simulation_mode())
        return self._prune_ai_context(compiled)

    @classmethod
    def _prune_ai_context(cls, value):
        """Recursively omit token-heavy empty/default scaffolding."""
        if isinstance(value, dict):
            return {str(key): cls._prune_ai_context(item) for key, item in value.items()
                    if key not in {"_request_receipts", "_recovery_guard"} and item not in (None, "", [], {})}
        if isinstance(value, list):
            return [cls._prune_ai_context(item) for item in value if item not in (None, "", [], {})]
        return value

    def append(self, text, tag=None, canon_day=None, detail=None):
        entry = {"id": secrets.token_hex(12), "text": text, "tag": tag, "time": datetime.now().isoformat(timespec="seconds"),
                 "world_time": str(self.state.get("world_time") or "")}
        if canon_day is not None:
            entry["canon_day"] = canon_day
        if detail:
            entry["detail"] = detail
        self.story_log.append(entry)

    def log(self, text):
        self.system_log.append(text)

    def ability_enum(self):
        return "|".join(abilities_for(self.state.get("world", "Custom World")))

    def gm_context(self, query=""):
        """Core rules plus a compact, query-relevant offline lore retrieval.
        `query` is also passed to gm_rules() as a combat-relevance hint — in
        the normal resolve() call path it IS the player's raw action text,
        which is exactly what deciding "is a worked combat example worth
        the tokens this turn" needs. Other call sites (event scenes,
        campaign opening) pass a synthetic query instead of a literal
        action; a false negative there just means no example that turn,
        which is a missed teaching moment, not a correctness bug — so it's
        safe to reuse loosely rather than plumbing a separate parameter."""
        lore = format_lore_context(self.state.get("world", "Custom World"), query, self.state,
                                   limit=self.simulation_profile()["lore_limit"], purpose="moment")
        self.last_lore_context = lore
        arc = self.state.get("campaign_arc_context") if isinstance(self.state.get("campaign_arc_context"), dict) else {}
        arc_rule = ""
        if arc.get("active_arcs") or arc.get("quiet_period"):
            arc_rule = ("\n\nCAMPAIGN ARC PACING: campaign_arc_context is locally calculated from established choices. "
                        "Use it for continuity, but never force an arc, fabricate an escalation, or require its listed approaches in order. "
                        "Any listed approach is optional and other plausible approaches remain valid. During quiet_period, allow recovery, relationships, "
                        "training and ordinary life unless an already-established urgent event genuinely prevents it. Arc closure must follow an actual resolution and preserve its consequences.")
        return self.gm_rules(query) + (("\n\n" + lore) if lore else "") + arc_rule + self.satisfy_class_design_context(query) + self.rated_good_example_snippet()

    def satisfy_class_design_context(self, query=""):
        """Load the large canon catalog only on turns that may author a class."""
        if self.state.get("world") != "Overgeared":
            return ""
        text = str(query or "")
        class_term = re.search(r"\b(?:class|successor|specialization|job path|profession path)\b", text, re.I)
        authorship = re.search(r"\b(?:create|generate|invent|design|gain|receive|earn|unlock|discover|awaken|evolve|advance|change|choose|become|hidden|rare|unique|legendary|growth)\b", text, re.I)
        if not (class_term and authorship):
            return ""
        return "\n\nCLASS-AUTHORSHIP REFERENCE (use only for this class decision):\n" + canon_class_prompt_reference()

    _COMBAT_SIGNAL_RE = re.compile(
        r"\b(attack|fight|strike|stab|slash|shoot|punch|kick|draw (?:my|your|his|her|their) (?:blade|sword|weapon|gun)|"
        r"charge at|engage|duel|spar|ambush|kill|defend against|block|dodge|parry)\b", re.I)

    def _combat_relevant(self, action_hint=""):
        """Whether this turn is plausibly about to touch state_patch.combat
        — either it's already active, or the action text signals a fight
        starting. Used only to decide whether the worked combat example
        (gm_rules' single biggest addition) is worth the tokens this turn;
        never gates the combat RULES themselves, only the teaching example."""
        combat = self.state.get("combat")
        if isinstance(combat, dict) and combat.get("active"):
            return True
        return bool(self._COMBAT_SIGNAL_RE.search(str(action_hint or "")))

    # Starting structured combat requires a concrete target. Bare words such
    # as "fight", "strike", "hit", "attack", and "shoot" caused idioms
    # (strike a deal, fight an illness, hit the road, shoot a message) to
    # manufacture enemies. Keep the trigger deliberately narrower than the
    # broad vocabulary used merely to recognize a combat-adjacent scene.
    _FIGHT_START_RE = re.compile(
        r"\b(?:attack|fight|strike|stab|slash|shoot|punch|kick|hit|tackle|grapple|choke|ambush|kill|duel|spar)\s+"
        r"(?:with\s+)?(?:the\s+|a\s+|an\s+|that\s+|this\s+|him\b|her\b|them\b|you\b|(?-i:[A-Z])[A-Za-z'’-]+)|"
        r"\b(?:fire|charge|lunge|swing|blast)\s+(?:my\s+[^.]{0,24}\s+)?(?:at|on|into)\s+(?:the\s+|a\s+|an\s+|him\b|her\b|them\b|you\b|(?-i:[A-Z])[A-Za-z'’-]+)|"
        r"\b(?:throw|cast|unleash)\s+.{1,35}\s+(?:at|on)\s+(?:the\s+|a\s+|an\s+|him\b|her\b|them\b|you\b|(?-i:[A-Z])[A-Za-z'’-]+)|"
        r"\buse\s+.{1,35}\s+to\s+(?:attack|hit|hurt|kill|blast|burn|cut)\s+(?:the\s+|a\s+|an\s+|him\b|her\b|them\b|you\b|(?-i:[A-Z])[A-Za-z'’-]+)", re.I)
    _FIGHT_NEGATION_RE = re.compile(
        r"\b(avoid|prevent|stop|refuse|decline|de[- ]?escalate|negotiate|talk down|do not|don't|without)\b.{0,28}"
        r"\b(attack|fight|violence|combat|strike|shoot|kill)\b", re.I)
    _UNAVOIDABLE_ATTACK_RE = re.compile(
        r"\b(attacks? you|ambush(?:es|ed)? you|charges? (?:at )?you|opens? fire (?:at|on) you|"
        r"stabs? you|slashes? you|strikes? you|hits? you|shoots? you|lunges? (?:at )?you|"
        r"swings? .{0,30} at you|fires? .{0,30} at you|blasts? you|tackles? you|grapples? you|"
        r"wounds? you|cuts? you|drives? .{0,25} (?:at|into) you|launches? .{0,30} at you|"
        r"(?:blade|sword|weapon|projectile|jutsu|spell|attack) .{0,35} (?:toward|at) you|"
        r"(?:the )?(?:fight|battle|combat) (?:continues|rages|is (?:already )?underway)|"
        r"no (?:time|room|chance|opportunity) (?:left )?(?:to|for) negotiat(?:e|ion|ing)?)\b", re.I)
    _FIGURATIVE_FIGHT_RE = re.compile(
        r"\b(?:strike (?:a |the )?deal|hit the (?:road|books|gym)|fight (?:(?:an?|the) )?(?:illness|disease|urge|feeling|fear)|"
        r"attack (?:the |a )?(?:problem|issue|question|goal)|shoot (?:a |the )?(?:message|photo|picture)|kick off)\b", re.I)

    _DANGER_SCENE_RE = re.compile(
        r"\b(danger|confront|fight|battle|combat|attack|ambush|duel|raid|siege|hostile|enemy|"
        r"boss|assassin|monster|threat|violence|kill|death)\b", re.I)
    _DANGER_EXIT_RE = re.compile(
        r"\b(flee|escape|retreat|withdraw|leave|depart|disengage|stand down|surrender|"
        r"de[- ]?escalate|the (?:fight|battle|danger|confrontation) (?:ends?|is over|passes))\b", re.I)

    def danger_scenario_active(self, state=None):
        """Whether a previously warned confrontation is still the live scene.

        The acknowledgement is intentionally short lived outside explicit
        combat/major-event state.  This prevents an accepted danger warning
        from suppressing unrelated warnings much later in the campaign while
        still covering a multi-beat confrontation at the same place.
        """
        state = state if isinstance(state, dict) else self.state
        combat = state.get("combat")
        if isinstance(combat, dict) and combat.get("active"):
            return True
        scenario = state.get("danger_scenario")
        if not isinstance(scenario, dict) or not scenario.get("active") or not scenario.get("warned"):
            return bool(state.get("active_canon_event") and scenario and scenario.get("warned"))
        location = str(state.get("location") or "").strip().lower()
        origin = str(scenario.get("location") or "").strip().lower()
        if location and origin and location != origin:
            return False
        try:
            age = int(state.get("turn", 0) or 0) - int(scenario.get("last_turn", scenario.get("started_turn", 0)) or 0)
        except (TypeError, ValueError):
            age = 0
        return age <= 12

    def acknowledge_danger_scenario(self, reason=""):
        prior = self.state.get("danger_scenario") if isinstance(self.state.get("danger_scenario"), dict) else {}
        started = prior.get("started_turn") if prior.get("active") else self.state.get("turn", 0)
        self.state["danger_scenario"] = {
            "active": True,
            "warned": True,
            "location": self.state.get("location") or prior.get("location") or "",
            "label": str(reason or prior.get("label") or self.state.get("active_canon_event") or "Dangerous confrontation")[:240],
            "started_turn": int(started or 0),
            "last_turn": int(self.state.get("turn", 0) or 0),
        }
        return self.state["danger_scenario"]

    def clear_danger_scenario(self):
        self.state["danger_scenario"] = {}

    def dangerous_plan(self, actions, checks=None):
        action_text = " ".join(str(x) for x in (actions or []) if str(x).strip())
        risky_check = any(str(row.get("lethal_risk") or "none").lower() in {"moderate", "high", "extreme"}
                          for row in (checks or []) if isinstance(row, dict))
        proposal_only = bool(re.search(
            r"\b(?:ask|request|propose|offer|arrange|schedule|seek|petition|invite|challenge)\b.{0,90}"
            r"\b(?:duel|spar|bout|match|fight|battle|combat)\b", action_text, re.I,
        )) and not action_commits_violence(action_text)
        return risky_check or (bool(self._DANGER_SCENE_RE.search(action_text)) and not proposal_only)

    def ensure_immediate_combat_patch(self, data, actions=None):
        """Last-resort structured-combat backstop.

        The narrator remains responsible for canon-strength opponent numbers.
        This only activates when it omitted combat entirely despite an explicit
        player attack or prose saying an unavoidable attack is already under
        way. CombatMixin then fills any missing numeric fields locally.
        """
        if not isinstance(data, dict):
            return False
        current = self.state.get("combat")
        patch = data.setdefault("state_patch", {}) if isinstance(data.get("state_patch", {}), dict) else {}
        data["state_patch"] = patch
        authored = patch.get("combat")
        if isinstance(authored, dict):
            authored = normalize_combat_payload(authored)
            patch["combat"] = authored
        if isinstance(current, dict) and current.get("active"):
            return False
        action_text = " ".join(str(x) for x in (actions or []) if str(x).strip())
        initiated = (bool(self._FIGHT_START_RE.search(action_text))
                     and action_commits_violence(action_text)
                     and not bool(self._FIGHT_NEGATION_RE.search(action_text))
                     and not bool(self._FIGURATIVE_FIGHT_RE.search(action_text)))
        if re.search(r"\b(?:until|till|through)\b.{0,45}\b(?:attack|fight|battle|combat)\b.{0,20}\b(?:over|ends?|ended|finished|resolved)\b", action_text, re.I):
            initiated = False
        narrative = str(data.get("narrative") or "") + " " + " ".join(
            str(update.get("narrative") or "") for update in (data.get("updates") or []) if isinstance(update, dict)
        )
        # A committed-attack phrase in the player's order is not enough when
        # the resolved scene explicitly establishes that the supposed target
        # is absent or the confrontation never existed.  Respect that grounded
        # outcome instead of manufacturing combat against whichever known NPC
        # happened to be mentioned later in the sentence.
        denied = bool(re.search(
            r"\b(?:no (?:armed |hostile )?(?:target|attacker|enemy|bandit|opponent|confrontation|fight|combat)\b|"
            r"(?:target|attacker|enemy|bandit|opponent) (?:is|was|are|were) not (?:present|there)|"
            r"attack cannot occur|combat (?:is not|isn't|was not|wasn't) initiated|no weapon is drawn|"
            r"acting against an absent target)\b",
            narrative, re.I,
        ))
        if denied:
            return False
        unavoidable = bool(self._UNAVOIDABLE_ATTACK_RE.search(narrative))
        if initiated and not unavoidable and re.search(r"\b(training dumm(?:y|ies)|practice targets?|door|wall|rock|tree)\b", action_text, re.I):
            initiated = False
        # The model may author combat even when neither side committed a
        # hostile act. Reject that patch instead of trusting a tense scene,
        # warning, argument, training description, or metaphor to be a fight.
        if isinstance(authored, dict) and authored.get("active"):
            if not (initiated or unavoidable):
                patch.pop("combat", None)
                data["combat_start_rejected"] = "No concrete hostile act or unavoidable attack established combat."
            else:
                enemy = authored.get("enemy") if isinstance(authored.get("enemy"), dict) else {}
                enemy_name = enemy.get("name") or "the opposition"
                authored.setdefault("cause", action_text if initiated else "The opposition committed an unavoidable attack.")
                authored.setdefault("initiator", self.state.get("name", "Player") if initiated else enemy_name)
                authored.setdefault("negotiation_possible", False)
                authored.setdefault("victory_condition", f"Defeat, drive off, escape, or deliberately spare {enemy_name}.")
                authored.setdefault("defeat_risk", "Injury, capture, incapacitation, or death according to the established scene.")
            return False
        if not (initiated or unavoidable):
            return False

        haystack = action_text + " " + narrative
        opponent = "Hostile opponent"
        if initiated:
            match = re.search(r"\b(?:attack|fight|strike|stab|slash|shoot|punch|kick|hit|tackle|grapple|ambush|kill|duel|spar)(?:\s+with)?\s+(?:the\s+|a\s+|an\s+)?([A-Za-z][A-Za-z'’-]*(?:\s+[A-Za-z][A-Za-z'’-]*){0,2})", action_text, re.I)
            if match:
                candidate = re.split(r"\b(?:with|using|at|in|until|before|after|while|as|because|and|but|who|that|threatening|near|beside)\b", match.group(1), maxsplit=1, flags=re.I)[0].strip(" .,!?")
                if candidate and candidate.lower() not in {
                    "training dummy", "practice target", "door", "wall", "bow", "deep bow",
                    "respectful bow", "formal bow", "nod", "salute", "handshake",
                }:
                    opponent = candidate.title()
        if opponent == "Hostile opponent":
            known = [str(name) for name in (self.state.get("npc_memories") or {}).keys() if str(name).strip()]
            known += [str(name) for name in (self.state.get("contacts") or {}).keys() if str(name).strip()]
            player_name = str(self.state.get("name") or "").lower()
            for name in sorted(set(known), key=len, reverse=True):
                if name.lower() != player_name and re.search(rf"\b{re.escape(name)}\b", haystack, re.I):
                    opponent = name
                    break
        non_lethal = bool(re.search(r"\b(spar|practice bout|friendly duel|training match)\b", action_text, re.I))
        group = bool(re.search(r"\b(group|squad|mob|pack|gang|troops|soldiers|bandit|bandits|monsters)\b", opponent, re.I))
        patch["combat"] = {
            "active": True, "round": 1, "non_lethal": non_lethal,
            "location": self.state.get("location") or "the current scene",
            "cause": action_text if initiated else "The opposition committed an unavoidable attack.",
            "initiator": self.state.get("name", "Player") if initiated else opponent,
            "negotiation_possible": False,
            "victory_condition": f"Defeat, drive off, escape, or deliberately spare {opponent}.",
            "defeat_risk": "Injury, capture, incapacitation, or death according to the established scene.",
            "enemy": {"name": opponent, "is_group": group, "group_size": None, "alive": True},
        }
        if not str(data.get("narrative") or "").strip():
            data["narrative"] = f"The confrontation with **{opponent}** turns physical. Combat begins immediately."
        return True

    def rated_good_example_snippet(self, query="", purpose="moment"):
        """A real, player-approved turn from THIS campaign (see
        engine_journal.rate_last_turn_good), shown as a genuine few-shot
        example instead of — or alongside — the hand-written ones baked
        into gm_rules(). Empty until the player has actually rated
        something, so a fresh campaign sees no difference."""
        rated = self.state.get("rated_good_turns") or []
        if not rated:
            return ""
        pick = select_approved_example(rated, query, purpose)
        if not pick:
            return ""
        return (f"\n\nPLAYER-APPROVED EXAMPLE FROM THIS CAMPAIGN (the player explicitly marked this exchange as good — "
                f"match its tone and quality, not its specific content or events):\nAction: {pick.get('action', '')}\n"
                f"Result: {pick.get('outcome', '')}")

    # Only high-confidence, mechanically-verified mismatches are worth
    # spending a retry on — matched against the exact phrasing continuity.py
    # actually uses for these three checks. Fuzzier warnings (a quest
    # regression that might be an intentional twist, a location change the
    # narrative didn't name) stay in the after-the-fact correction pass
    # only, since a retry risks "fixing" something that wasn't a mistake.
    _RETRYABLE_WARNING_MARKERS = ("currency.amount", "being wounded, but hp", "status is still")

    def _simulate_continuity_violations(self, payload, data):
        """Applies data's state_patch to a throwaway copy of state (never
        the real one) and runs the same continuity checks apply_resolution
        runs for real afterward, so a currency/hp/quest-completion mismatch
        can be caught and named BEFORE this turn is ever finalized, not
        only silently patched after the player has already seen it."""
        patch = data.get("state_patch")
        if not isinstance(patch, dict) or not patch:
            return []
        scratch = copy.deepcopy(self.state)
        apply_guarded_patch(scratch, patch, allow_time=False, source="preflight")
        warnings = update_continuity(self.state, scratch, str(payload.get("action") or ""), data.get("narrative", ""))
        return [w for w in warnings if any(marker in w for marker in self._RETRYABLE_WARNING_MARKERS)]

    def _response_quality_issues(self, payload, data):
        """Return only locally provable response failures worth one retry."""
        if not isinstance(data, dict):
            return ["The response was not a JSON object."]
        task = str(payload.get("task") or "").lower()
        narrative = str(data.get("narrative") or "").strip()
        issues = []
        if "narrator" not in task and task not in {"time_skip", "major_event", "event_turn"}:
            return issues
        schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
        suggestions = [str(item).strip() for item in data.get("suggested_actions", [])
                       if str(item).strip()] if isinstance(data.get("suggested_actions"), list) else []
        if "suggested_actions" in schema and task != "combat_summary" and len(suggestions) < 2:
            issues.append("The result did not provide at least two concrete next-action choices.")
        patch = data.get("state_patch") if isinstance(data.get("state_patch"), dict) else {}
        new_location = str(patch.get("location") or "").strip()
        if new_location and new_location.lower() != str(self.state.get("location") or "").strip().lower() and new_location.lower() not in narrative.lower():
            issues.append(f"The state moves to {new_location}, but the narrative never establishes that movement.")
        from gm_refinements import acquisition_claim
        claimed_breakthrough = acquisition_claim(self.state, narrative)
        manifest = data.get("consequence_manifest") if isinstance(data.get("consequence_manifest"), list) else []
        durable_fields = {"skills", "special", "class_profile", "ability_progress", "portrait_identity", "portrait_traits", "level", "xp"}
        durable_manifest = any(isinstance(row, dict) and str(row.get("kind", "")).lower() in
                               {"skill", "title", "condition", "affiliation", "other"} for row in manifest)
        if claimed_breakthrough and not (durable_fields & set(patch)) and not durable_manifest:
            issues.append("The prose claims a mastery, awakening, evolution, or new form without recording any durable mechanical consequence.")
        if "updates" in schema and task in {"time_skip", "major_event"} and not isinstance(data.get("updates"), list):
            issues.append("A time-moving response omitted its chronological updates list.")
        return issues[:4]

    def request_with_narrative(self, instructions, payload, max_output_tokens, client=None):
        """Some models (smaller/cheaper ones especially) occasionally fill in
        state_patch correctly but leave narrative blank under attention
        pressure. That's a failed response, not a usable one — retry once
        with a sharper reminder before accepting it. Also retries once when
        the response would trip a high-confidence continuity check (see
        _simulate_continuity_violations) — same one-retry discipline, named
        specifically so the model isn't just asked to "try again" blind."""
        max_output_tokens = output_budget(max_output_tokens, self.simulation_mode())
        client = client or self.ai
        payload = prepare_request(self.state, payload)
        instructions += CONSISTENCY_RULE
        usage_before = copy.deepcopy(getattr(client, "usage", {}))
        from turn_recovery import stage, request_signature
        record = stage(self, "narrator", request_signature(instructions, payload, getattr(client, "model", ""), max_output_tokens))
        data = copy.deepcopy(record.get("draft"))
        if data is None:
            data = normalize_turn_response(client.request(instructions, payload, max_output_tokens=max_output_tokens), payload.get("task"))
            record["draft"] = copy.deepcopy(data)
        narrative_missing = not (data.get("narrative") or "").strip()
        violations = [] if narrative_missing else self._simulate_continuity_violations(payload, data)
        quality_issues = [] if narrative_missing else self._response_quality_issues(payload, data)
        consistency_issues = semantic_issues(self.state, data, payload)
        quality_issues.extend(consistency_issues)
        if narrative_missing or violations or quality_issues:
            reminder = ""
            if narrative_missing:
                reminder += "\n\nREMINDER: your previous attempt left \"narrative\" empty. Write 2-5 sentences of narrative FIRST, then the rest."
            if violations:
                reminder += "\n\nREMINDER: your previous attempt has a specific problem that must be fixed in this response: " + " ".join(violations)
            if quality_issues:
                reminder += "\n\nQUALITY REPAIR: keep every valid fact and outcome from the first attempt, but correct these locally verified omissions or contradictions: " + " ".join(quality_issues)
            from ai_budget import consume_retry
            consume_retry()
            repair_payload = {**payload, "repair_draft": copy.deepcopy(data), "repair_issues": quality_issues + violations}
            data = normalize_turn_response(client.request(instructions + reminder, repair_payload, max_output_tokens=max_output_tokens), payload.get("task"))
            record["draft"] = copy.deepcopy(data)
        data, canon_repairs = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
        data = enforce_response_policy(data, payload, self.state)
        remaining = semantic_issues(self.state, data, payload) + self._simulate_continuity_violations(payload, data) + self._response_quality_issues(payload, data)
        if not str(data.get("narrative") or "").strip(): remaining.insert(0, "The repaired response still has no narrative.")
        if remaining:
            raise ValueError("The GM returned a contradictory result after one repair. This result was not applied; your previous save remains usable. Retry Advance. Details: " + " ".join(remaining[:2]))
        record["draft"] = copy.deepcopy(data)
        if canon_repairs:
            data["canon_integrity_repairs"] = canon_repairs
        self._last_narrator_model = getattr(client, "model", self.settings.get("model", ""))
        usage_after = getattr(client, "usage", {})
        self._last_request_usage = {
            "task": str(payload.get("task") or "narration"), "model": self._last_narrator_model,
            "calls": max(0, int(usage_after.get("calls", 0) or 0) - int(usage_before.get("calls", 0) or 0)),
            "input_tokens": max(0, int(usage_after.get("input_tokens", 0) or 0) - int(usage_before.get("input_tokens", 0) or 0)),
            "output_tokens": max(0, int(usage_after.get("output_tokens", 0) or 0) - int(usage_before.get("output_tokens", 0) or 0)),
            "cost_usd": round(max(0.0, float(usage_after.get("cost_usd", 0) or 0) - float(usage_before.get("cost_usd", 0) or 0)), 6),
        }
        return data

    def _scale_lock_rule(self):
        """Shared by gm_rules() and core_rules() so the scale-lock/contact/
        identity/information-fog block — genuinely relevant to almost any
        AI call, light or heavy — stays byte-identical in both instead of
        drifting into two slightly different copies over time."""
        scale = str(self.state.get("simulation_scale") or "Individual").strip() or "Individual"
        return (
            f"\n- SCALE LOCK (current scale: {scale}): the player's simulation_scale is Individual, Organization, Guild, Company, City, "
            "Nation, or Empire — exactly one at a time, tracked in state_patch.simulation_scale, and it NEVER silently upgrades. It only "
            "changes when the player has genuinely, deliberately built up to that scale through real in-fiction action (founding and "
            "growing an organization, being formally installed in a national office, etc.), the same bar as state.position. "
            + (
                "The player is currently at INDIVIDUAL scale, which hard-locks the following until they explicitly earn otherwise: the "
                "player never owns or governs a country, never controls national territory, never appears on the map as a political "
                "entity, never receives national diplomacy, international summits, embassies, UN-style invitations, unsolicited direct "
                "contact from a government, or military command. Never invent a country for them, never rename, split, or hand over a "
                "map region because of them, and never manufacture diplomacy just to involve them in it — if the story wants that scale of "
                "consequence, it happens among nations and organizations that already exist, and the player experiences it from whatever "
                "vantage their actual scale allows."
                if scale == "Individual" else
                f"The player has earned {scale}-scale standing — the simulation should now actually reflect that reach in what reaches "
                "them (relevant diplomacy, contact, or authority at that scale becomes plausible), without retroactively pretending they "
                "were ever bigger than what they actually built."
            ) +
            " Regardless of scale: an unidentified individual is never contactable by a government or agency out of nowhere — identity "
            "must be discovered (video, DNA, financial/electronic/travel traces, surveillance, multiple witnesses, captured allies, "
            "communications intercepts), then verified, then cleared through a real threat assessment and bureaucratic approval, before any "
            "direct contact is even possible; agencies investigate and coordinate internally first, they do not immediately call, recruit, "
            "or negotiate. No single observation ever identifies someone — a power level, aura, or energy reading reveals capability, never "
            "identity. Information about the player spreads in physical layers with real delay and real loss at each step (direct "
            "observation -> witness account -> rumor -> local authorities -> regional authorities -> national agencies -> international "
            "intelligence -> broadly verified fact) — most rumors never make it all the way up that chain, witnesses can be wrong, and "
            "footage can be faked or disputed."
        )

    def core_rules(self, extra=""):
        """A much lighter instruction set for background/side tasks — a side
        chat reply, the incoming-message check, the background world tick,
        memory maintenance — that don't touch combat, quests, the Tower, or
        faction conflict, and don't need the full ~46,000-character turn-
        resolution rulebook to do their actual job. Modeled on Pax Historia's
        own approach of giving each distinct AI task its own right-sized
        prompt instead of reusing one giant shared one everywhere; these
        calls run far more often than a real turn (the incoming-chat check
        alone fires every other turn), so the savings compound."""
        wd = WORLD_DATA[self.state["world"]]
        mechanics = WORLD_MECHANIC_RULES.get(self.state.get("world", ""), "") + activity_rules_for(self.state.get("world", ""), "core", extra) + NARRATIVE_CRAFTING_RULE
        identity = canon_identity_context(self.state.get("world", "Custom World"), extra, self.state, limit=4)
        return f"""You are the world-consistency layer for Worldwalker RPG's "{self.state['world']}" campaign — not narrating a full scene, just keeping one small piece of the simulation honest.
WORLD RULES: {wd['rules']}
{mechanics}
CUSTOM SETTING: {self.state.get('custom_world', '')}
{identity}

CORE PRINCIPLES
- Obey state.grounding_packet: current facts and player corrections outrank summaries and stock canon.
- NPCs, factions and world events continue independently and know only what they could plausibly know.
- Enforce information fog. Separate objective world changes from what the player can verify, infer, or hear as rumor. News requires a believable route — witness, messenger, broadcast, document, travel, surveillance, or ability — and distance and secrecy cause delay or uncertainty.
- Contacts are not omnipresent. Distance, access, relationship, danger, technology, secrecy, and availability matter.
- Communications must use lore-appropriate means. A "chat" can mean phone/text, guild chat, system DM, messenger bird, courier, letter, Den Den Mushi, radio, telepathy, or other setting-appropriate medium.
- Before proposing or reacting to anything, check campaign_canon (recent turn history) and the relevant npc_memories entry for whether it has already happened, been discussed, or been resolved — never re-raise, act surprised by, or contradict something already settled.
- Canon is the opening condition, not a railroad. Record meaningful changes as canon_divergences.{self._scale_lock_rule()}
{extra}
Return ONLY valid JSON. No markdown fences."""

    def task_state_for_ai(self, purpose="moment", query=""):
        """Right-size state for specialized AI roles.

        Full turn/time-skip simulation still receives the relevance-trimmed
        campaign snapshot.  Opening, Advisor, and post-combat prose receive
        only fields that can affect that task, avoiding tens of thousands of
        repeated tokens without deleting anything from the real save.
        """
        refresh_simulation_core(self.state)
        if not self.state.get("scene_state"):
            refresh_scene_state(self.state, {}, [])
        learn_player_style(self.state)
        reconcile_commitments_and_consequences(self.state, {}, 0)
        refresh_canon_divergence_impacts(self.state)
        snapshot = self.trimmed_state_for_ai(query, purpose)
        snapshot["mechanical_power_profile"] = power_profile_for(
            self.state.get("world", "Custom World"), self.state.get("stats", {}),
            self.state.get("special", {}).get("Archetype", ""),
        )
        snapshot["grounding_packet"] = build_grounding_packet(
            self.state, query, purpose,
            24 if str(purpose) == "advisor" else 14 if str(purpose) in {"moment", "time_skip", "major_event", "event"} else 10,
        )
        snapshot["npc_knowledge_boundaries"] = npc_knowledge_boundaries(self.state)
        snapshot["concealed_player_facts"] = concealed_player_facts(self.state)[:30]
        capability = self.state.get("capability_profile", {})
        snapshot["capability_summary"] = {
            "tier": capability.get("tier", {}), "power": capability.get("power", {}),
            "world_traits": capability.get("world_traits", {}),
            "combat_abilities": capability.get("combat_abilities", [])[:24],
            "limitations": capability.get("limitations", [])[:12],
        }
        continuity = self.state.get("npc_continuity", {})
        snapshot["npc_role_flags"] = [{
            "name": row.get("name"), "companion": row.get("companion"), "nemesis": row.get("nemesis"),
            "combat_support": row.get("combat_support"), "support_bonus": row.get("support_bonus"),
            "goal": row.get("goal"), "status": row.get("status"),
        } for row in continuity.values() if row.get("nemesis") or row.get("companion")]
        snapshot["active_story_threads"] = [
            {k: row.get(k) for k in ("id", "title", "kind", "status", "detail")}
            for row in self.state.get("story_threads", {}).values() if row.get("status") in {"active", "turning_point", "blocked"}
        ][:24]
        active_scenario = (self.state.get("scenario_memory") or {}).get("active", {})
        if isinstance(active_scenario, dict) and active_scenario:
            snapshot["active_scenario"] = copy.deepcopy(active_scenario)
        purpose = str(purpose or "moment")
        if purpose in {"moment", "time_skip", "major_event", "event"}:
            return snapshot
        common = {
            "name", "age", "position", "world", "difficulty", "background", "creation_locks", "custom_world", "race",
            "player_identity", "location", "world_time", "calendar", "canon_day", "canon_anchor",
            "stats", "hidden_stats", "hp", "hp_max", "resource_name", "resource", "resource_max",
            "skills", "titles", "class_profile", "special", "inventory", "equipment", "currency",
            "quests", "relationships", "affiliations", "companions", "contacts", "npc_memories",
            "canon_divergences", "campaign_direction", "active_action_goals", "prerequisite_tracks",
            "authoritative_player_corrections", "simulation_scale", "combat", "danger_scenario",
            "mechanical_power_profile", "standing_intents",
            "capability_summary", "npc_role_flags", "active_story_threads", "active_scenario", "grounding_packet",
        }
        if purpose == "opening":
            opening = common | {"starting_power_band", "starting_power_notice", "appearance_desc", "portrait_traits"}
            return {key: copy.deepcopy(value) for key, value in snapshot.items() if key in opening and value not in (None, "", [], {})}
        if purpose == "combat_summary":
            combat_keys = common | {"turn", "standing_orders", "suggested_actions"}
            result = {key: copy.deepcopy(value) for key, value in snapshot.items() if key in combat_keys and value not in (None, "", [], {})}
            # Distant NPC dossiers, full background prose, and unrelated
            # inventories cannot change how already-resolved swings read.
            result.pop("npc_memories", None)
            result.pop("background", None)
            result["recent_campaign_facts"] = copy.deepcopy((snapshot.get("campaign_canon") or [])[-2:])
            return result
        if purpose == "advisor":
            advisor_keys = common | {"factions", "faction_clocks", "npc_clocks", "world_events", "background_world_feed", "chapter_summaries", "campaign_canon"}
            result = {key: copy.deepcopy(value) for key, value in snapshot.items() if key in advisor_keys and value not in (None, "", [], {})}
            # The Advisor answers retrospective and cross-system questions,
            # so its evidence cannot be limited to the same small relevance
            # bubble used by the next-turn narrator. Keep bounded raw tails
            # from the real save and add local full-record search matches for
            # the exact question. This costs no extra AI call.
            result.update({
                "turn": self.state.get("turn", 0),
                "level": self.state.get("level"), "xp": self.state.get("xp"), "xp_next": self.state.get("xp_next"),
                "current_activity": copy.deepcopy(self.state.get("current_activity")),
                "conditions": copy.deepcopy(self.state.get("conditions", [])),
                "status": copy.deepcopy(self.state.get("status", [])),
                "faction_chain": copy.deepcopy(self.state.get("faction_chain", {})),
                "npc_relationships": copy.deepcopy(self.state.get("npc_relationships", {})),
                "faction_rosters": copy.deepcopy(self.state.get("faction_rosters", {})),
                "political_regions": copy.deepcopy(self.state.get("political_regions", [])),
                "standing_orders": copy.deepcopy(self.state.get("standing_orders", [])),
                "scheduled_events": copy.deepcopy(self.state.get("scheduled_events", [])),
                "npc_schedules": copy.deepcopy(self.state.get("npc_schedules", {})),
                "last_cause_effect": copy.deepcopy(self.state.get("last_cause_effect", {})),
                "last_training_summary": copy.deepcopy(self.state.get("last_training_summary", {})),
                "question_evidence": campaign_search(self.state, query, 20),
                "continuity_facts": copy.deepcopy((self.state.get("continuity_ledger", {}).get("facts") or [])[-40:]),
                "recent_progression": copy.deepcopy((self.state.get("progression_ledger") or [])[-16:]),
                "recent_resolutions": copy.deepcopy((self.state.get("resolution_ledger") or [])[-8:]),
                "recent_corrections": copy.deepcopy((self.state.get("authoritative_corrections") or [])[-30:]),
            })
            result["campaign_canon"] = copy.deepcopy((self.state.get("campaign_canon") or [])[-20:])
            result["chapter_summaries"] = copy.deepcopy((self.state.get("chapter_summaries") or [])[-6:])
            result["background_world_feed"] = copy.deepcopy((self.state.get("background_world_feed") or [])[-15:])
            result["world_events"] = copy.deepcopy((self.state.get("world_events") or [])[-15:])
            return self._prune_ai_context(result)
        return snapshot

    def player_agency_rules(self):
        """One ordered outcome contract shared by every narrator role.

        Keep this centralized: duplicating fragments in individual job prompts
        made older models over-weight generic drama and obscured the order in
        which action resolution, awareness, and reaction should be decided.
        """
        if self.state.get("difficulty") == "Nightmare":
            policy_name = "NIGHTMARE AGENCY POLICY"
            feasibility = (
                "Nightmare remains strict: plausible actions may fail when a settled roll, scarce leverage, lethal danger, "
                "or established opposition defeats the plan. Never convert that resistance into vague GM refusal."
            )
        else:
            policy_name = "PLAYER-FAVORING AGENCY POLICY"
            feasibility = (
                "This difficulty supports a power fantasy: accomplish any world-possible result not defeated by a settled "
                "mechanic. Low odds, rank, canon precedent or pacing never weaken it. Politics, strategy, diplomacy, social "
                "play, investigation, crafting, and focused training succeed without arbitrary checks."
            )
        return f"""{policy_name} — OUTCOME CONTRACT (APPLY IN THIS ORDER; OVERRIDES GENERIC DRAMA/TENSION HABITS)
1. HONOR INTENT: A stated action is something they DO, not merely intend; carry out the action exactly as they described it. Consequences come from response, never from the GM quietly softening, downgrading, or overriding it; never a suspended non-answer.
2. RESOLVE FEASIBILITY: {feasibility}
3. RESULT FIRST: State what the action accomplished before reactions or hooks. Quiet, positive, neutral, and uneventful resolutions are valid; never bury success beneath caveats.
4. SEPARATE REACTION: Success and NPC cooperation are separate. Independent NPCs retain motives and may accept, refuse, counteroffer, or adapt after the act lands; do not disguise their choice as action failure.
5. PROVE NEGATIVES: A setback needs a supplied-state cause, believable awareness/contact, a motive or stake, and proportional scale. Failed rolls, real costs, broken promises, witnessed offenses, and established opposition qualify; generic balance, tension, or hook-making does not.
6. LIMIT AWARENESS AND SCALE: Private acts stay private. Reactions require presence, witnesses, messages, evidence, reports, sensing, or rumor at believable speed and magnitude.
7. NO DEFAULT DISTRUST: Power, growth, secrecy, foreign origin, or divergence causes fear, envy, suspicion, hostility, or punishment only when a specific character or culture's knowledge and motives support it.
8. NO AUTOMATIC ESCALATION OR CANON GRAVITY: Solved problems stay solved absent a concrete surviving cause. Canon is the starting state, not a restoring force; recorded divergences win.
9. ALLOW ENDINGS: Victories, alliances, quests, wars, rivalries, reforms, and goals may end decisively. Never preserve or replace conflict merely to create content.
10. PRESERVE GAINS: Allies, territory, reputation, agreements, abilities, knowledge, and completed goals persist until a concrete later event changes them; never reverse them silently.
ROLL EXCEPTION: Dice are only for extreme/impossible-looking attempts, lethal undertakings, and tier leaps—real risk stays real there. For a non-combat, non-violent action genuinely impossible on paper under this world's own established rules, still resolve it with a roll instead of an outright refusal: success finds a world-valid route; failure gives a concrete result, never a flat "nothing happens." Combat and violence keep their own existing risk and danger rules unchanged. A literal contradiction with no possible outcome is blocked with the exact reason and nearest valid route.
PROGRESSION: Sustained training has no arbitrary canon ceiling. Record growth from its time, method, intensity, teachers, resources, recovery, and aptitude. A plausible named goal progresses without repeated permission checks; sufficient time completes it, while insufficient time grants substantial foundation and the earliest plausible milestone."""

    def task_rules(self, purpose="moment", action_hint=""):
        """Compact authoritative rules for one AI job.

        The original all-purpose GM prompt remains available for plug-ins and
        diagnostic comparisons.  Production call sites use this task router so
        a combat recap no longer pays for character creation, faction
        governance, shops, long-skip scheduling, and every other subsystem.
        """
        purpose = str(purpose or "moment")
        wd = WORLD_DATA[self.state["world"]]
        ex = expansion_for(self.state["world"])
        difficulty = DIFFICULTIES[self.state["difficulty"]]
        tuning = normalize_tuning(self.state)
        profile = progression_preset_for(self.state.get("world"))
        mechanics = WORLD_MECHANIC_RULES.get(self.state.get("world", ""), "") + activity_rules_for(self.state.get("world", ""), purpose, action_hint) + NARRATIVE_CRAFTING_RULE + world_depth_rules(self.state)
        narration = self.settings.get("narration", "Concise")
        agency_rules = self.player_agency_rules()
        routed = prompt_modules(purpose, action_hint, self.state)
        # Classifiers and repair passes do not need the narrator's quest,
        # economy, skill-authoring, combat-aftermath, or presentation rules.
        # Keeping these jobs genuinely task-specific follows the same routing
        # principle as the narrator modules below and materially reduces both
        # prompt cost and cross-task instruction interference.
        if purpose in {"assessment", "time_plan"}:
            support_job = (
                "ASSESSMENT JOB\n"
                "- Classify only; do not narrate, roll, advance time, or invent consequences.\n"
                "- A check is permitted only for an extreme/seemingly impossible attempt, lethal undertaking, or real power-tier leap. Ordinary politics, strategy, social play, investigation, crafting, travel, and focused training require no check.\n"
                "- A hard block requires a literal physical/metaphysical contradiction or mutually exclusive prerequisite. NPC reluctance, low odds, canon divergence, rank, and social resistance are reactions, not impossibility.\n"
                "- Difficulty represents the average relevant character at this era and never scales to the player; use d100 only."
                if purpose == "assessment" else
                "TIME-PLANNING JOB\n"
                "- Return only the terse itinerary/check classification requested by the schema; do not narrate, roll, or advance state.\n"
                "- Preserve queued order, real travel time, available duration, standing instructions, explicit wait conditions, and deferred work.\n"
                "- Routine training and ordinary actions need no check. Reserve checks for extreme/seemingly impossible attempts, lethal undertakings, and real power-tier leaps; never scale difficulty to the player."
            )
            return f"""You are Worldwalker RPG's authoritative mechanical classifier.
WORLD: {self.state['world']}
WORLD RULES: {wd['rules']}
DIFFICULTY: {self.state['difficulty']} — {difficulty['description']}
WORLD ABILITIES: {self.ability_enum()}
RELEVANT WORLD MECHANICS: {WORLD_MECHANIC_RULES.get(self.state.get('world', ''), '')}
{agency_rules}
{support_job}
- Grounding packet, current state, and authoritative corrections beat old history or stock canon.
- Return one valid JSON object matching the supplied schema; omit empty optional fields."""
        if purpose == "continuity_audit":
            return f"""You are Worldwalker RPG's continuity auditor for {self.state['world']}.
- Fix only explicitly supplied conflicts. Grounding facts and authoritative player corrections beat old narration and stock canon.
- Prefer the smallest corrected state patch; otherwise write a 1-3 sentence in-fiction correction.
- Never re-narrate the scene, add an event, alter unrelated state, or create a compensating consequence.
- Return one valid JSON object matching the supplied schema."""
        if purpose == "combat_summary":
            xp_rule = (
                "Deliver exact XP, level, title, achievement, item, and quest changes as literal world-authentic System notifications."
                if uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")) else
                "Do not invent XP or numbered levels; record only world-valid techniques, stats, ranks, titles, items, and other earned progress."
            )
            return f"""You are Worldwalker RPG's combat chronicler.
WORLD: {self.state['world']}
WORLD RULES: {wd['rules']}
NARRATION: {narration}
- Narrate only the settled mechanical log. Never reroll, add exchanges, change who won, alter mercy/lethality, or weaken a decisive result.
- Apply only direct aftermath supported by the log and supplied state: injuries/conditions, plausible important loot, progression, quest effects, and immediate reactions from present informed actors.
- State the result first. Do not attach a compensating injury, enemy, suspicion, escape, reversal, or future hook that the log did not cause.
- State changes and prose must agree: wounds change HP, conditions persist, defeated enemies keep their resolved status, and reusable loot enters inventory.
- {xp_rule}
- Return one valid JSON object matching the supplied schema; omit empty optional fields."""
        if not ex.get("tracks_currency", True):
            finance_rule = "- This world does not track a numeric currency: never write currency, currencies, recurring_finances, or purchase_offer into state_patch."
        elif routed["finance"]:
            finance_rule = (
                "- A REPEATING income or expense the player establishes (a job, a shop's regular take, rent, staff wages, a stipend, tribute, upkeep) "
                "must be recorded as a state_patch.recurring_finances entry: {label, kind:\"income\"|\"expense\", amount (positive number), "
                "interval_days (e.g. 7 for weekly, 30 for monthly), next_due_day (integer canon_day it next pays), active:true, notes}. "
                "The application pays it automatically every interval once registered and it stays active indefinitely — do NOT manually re-add or "
                "re-subtract the lump sum in currency yourself when it recurs. It keeps paying until its actual in-fiction source is genuinely gone "
                "(the job ends, the shop closes, the contract is broken) — never let a real narrative event silently stop a payment without you setting "
                "active:false that same turn, and never let it drift out of memory on its own. The application preserves each entry by its exact label "
                "across turns even if you only mention some of them, so you do not need to re-list every unrelated existing entry just to add or touch "
                "one — but keep using the SAME label for a given source every time you reference it, so it's recognized as the same entry rather than "
                "a duplicate. A one-off purchase or payment (not repeating) still just changes currency.amount directly, as always."
            )
        else:
            finance_rule = ""
        skill_rule = (
            "- Every authored skill must use the shared taxonomy when its function is known: category "
            "(offense|defense|healing|support|control|mobility|detection|stealth|summon|transformation|crafting|knowledge|social|utility), "
            "combat_usable (boolean), effect_type (damage|heal|buff|debuff|shield|cleanse|control|summon|movement|detect|stealth|transform|utility), "
            "target_type (enemy|enemies|self|ally|allies|area|environment), and duration_rounds for lasting effects. "
            "Optional status_effect is a short player-facing condition name. Profession, knowledge, navigation and crafting skills are "
            "combat_usable=false unless they have a specific combat application."
            if routed["ability"] else ""
        )
        quest_rule = ""
        if routed["quest"]:
            quest_rule = """- Starting a quest requires a readable briefing with objective, cause/giver, known location, risks, first step, current knowledge and clear completion conditions. A player-stated goal (e.g. "I want to prepare for [event]") becomes a real quest or narrative Agenda the same way, even without rigid built-in objectives — it must stay genuinely completable through the player's own effort, never sit permanently vague with no path to finishing it.
  - If the goal is specific enough to have concrete requirements, set quest objectives to those exact things and actively create narrative opportunities for the player to attempt them.
  - If the goal is ambiguous, credit real, felt progress toward it, paced so consistent honest effort actually reaches completion by its due date rather than stalling indefinitely.
  - When requirements are met, or accumulated effort reasonably supports it, resolve the quest as complete in that turn's state_patch. A completable goal must actually be able to complete. Never force one mandatory route."""
        shared = f"""You are the authoritative Game Master for a persistent Worldwalker RPG campaign.
WORLD: {self.state['world']}
WORLD RULES: {wd['rules']}
{mechanics}
CUSTOM SETTING: {self.state.get('custom_world', '')}
DIFFICULTY: {self.state['difficulty']} — {difficulty['description']}
PROGRESSION: {profile['label']}; training x{tuning['training_rate']}, breakthrough x{tuning['breakthrough_rate']}, XP x{tuning['xp_rate']} only where canonical XP exists.
NARRATION: {narration}
	WORLD ABILITIES: {self.ability_enum()}
	CANON KNOWLEDGE MODE: {"Full canon foreknowledge enabled for the player UI; NPC knowledge still remains in-character." if self.settings.get("canon_foreknowledge") else "Spoiler-safe character knowledge; never reveal future secrets before this campaign discovers them."}
ACTIVE GM MODULES: {', '.join(routed['active']) or 'general scene resolution'}

AUTHORITATIVE CORE
- Grounding packet: current facts and corrections beat history and canon.
- When the player gives an order to a character genuinely under their command — a subordinate, companion, summon, or anyone who owes them obedience in this campaign — that character carries out the order as given. Do not have them refuse, hesitate, or fail through GM fiat. Afterward, in the narrative, they may voice a concern or suggest a better approach, but the order is already carried out. This does not extend to independent NPCs, canon characters acting on their own motives, or hostile/neutral parties, whose own agency remains absolute.
- The player alone controls their character's choices and dialogue. NPCs, factions, travel, information and canon continue causally without making the player the automatic center.
- Use information fog: characters learn through believable witnesses, messages, evidence, travel, research or powers. Never confuse narrator knowledge with character knowledge.
- Use reliable source-material knowledge and the supplied lore/state. Anything canon characters can do is theoretically reproducible when the same prerequisites and costs are met. Original abilities, classes and techniques are welcome when they fit world logic.
- Recorded original classes, bloodlines and abilities are authoritative, not lesser canon copies: honor their effect, limits, growth path and canon-relative balance as one package, and develop new applications when earned.
- When inventing a player ability, match the world's established signature abilities in depth, complexity, uniqueness, practical versatility, meaningful limits, and attainable power ceiling—not merely in damage. Non-canon abilities are explicitly allowed in every world when their mechanism follows that world's rules.
- Treat the saved Growth Profile combat_style as embodied training. Narrate that style through the character's movement, weapons and choices. Broad competence is represented by stats, not invented labels such as “Brawler Fundamentals.” Only add a skill when it is an actual named technique, jutsu, spell, formation, attack, release, transformation, class feature, or setting-recognized discipline. Learning a distant style requires an appropriate teacher and more practice than extending the character's established style.
- mechanical_power_profile is the authoritative translation of the player's CURRENT stats. It outranks starting_power_band, old position/rank labels, stock-canon strength for the player character, and arithmetic-average guesses. Compare peak offense, speed, defense and balanced combat separately; never call a heavily trained canon-character player weak merely because their original canon version was weaker.
- State changes must match prose: wounds change HP, resource use changes the correct pool, purchases change money/inventory, completed objectives change quests, travel changes location, and learned skills include a clear effect, limitation/cost and growth path.
- Return causal_outcome with the direct result first, actual witnesses, informed NPC reactions with knowledge_source, real costs, and complications with an explicit established cause. Ordinary successful beats usually have no complication; never add one merely for tension.
{finance_rule}
{skill_rule}
- An enemy whose normal hit inflicts a condition may define attack_effect with type control or debuff, a condition name, duration_rounds, and potency_pct; the application enforces it locally.
- An initiated attack or unavoidable incoming attack begins structured combat immediately. Do not insert an extra negotiation/event-chat gate once violence is committed. A previously accepted danger scenario does not warn again unless the new action itself could kill the player.
{agency_rules}
{quest_rule}
- End with exactly three optional, current, state-grounded suggestions written as concrete verb + specific known target + purpose. Never suggest traveling to the current location, contacting an unknown person, or continuing an encounter that has ended.
- Return one valid JSON object. Omit empty optional fields and empty arrays/objects instead of echoing the entire schema. Never write application-owned ledgers or diagnostics in state_patch.{self._scale_lock_rule()}
"""
        faction_trade_rule = (
            "- faction_clocks are living strategic records. Respect their strategic_goal, immediate_goal, leadership, resources, operations, alliances, rivals and recent_outcomes. Advance or react to the current operation instead of inventing an unrelated faction move. Resources constrain pace; alliances and rivalries shape responses; leadership loss creates a succession pressure rather than making the faction forget its agenda. "
            "faction_clocks and npc_clocks also support opponent (a rival faction/NPC), ally, power (1-100, rough current strength), "
            "and contested_location (a real place actually at stake). Once a clock with an opponent reaches its turning point, the application "
            "resolves a real strength-weighted outcome automatically — territory can change hands, and a side that loses badly enough is genuinely "
            "destroyed or lost — independent of whether the player is present. Only set these fields when the stake is meant to be real; a conflict "
            "the player experiences directly belongs in normal narrative/combat instead. This applies to trade disputes and blockades exactly like "
            "open conflict — a rival power actually contesting a trade route, port, or supply line is a real opponent/contested_location claim.\n"
            "- Tolls, blockades, secured or cut trade routes, and who actually supplies a settlement have real narrative weight — reflect it "
            "concretely in prices, scarcity, and the population's day-to-day situation, not as flavor text alone. A settlement that just suffered a "
            "major disaster, or is currently cut off from resources, should visibly struggle: its government is more likely to act to secure "
            "supplies (negotiate, pressure whoever is blockading it, seek an alternate source, or crack down), and its people's sentiment/standing "
            "shifts toward whoever is actually providing for them, not merely whoever claims to."
        )
        reliability_rule = """
GM CONTINUITY CONTRACT
- live_scene is the authoritative present-tense scene ledger. Keep its location, present people, danger, unresolved question and objective coherent; never teleport absent people in or give them unheard information.
- Match prose magnitude to durable mechanics in BOTH directions. Never call a routine increase transformative or describe a true awakening as minor.
- canon_divergence_impacts are future canon dominoes already altered, delayed, replaced or impossible. Follow them instead of restoring stock canon.
- due_obligations and due_consequences are live continuity. Resolve/update them when their condition falls inside this beat. Return new promises/debts in commitment_updates and later echoes in delayed_consequences.
- player_style is only a soft presentation preference learned from explicitly liked turns. It never changes facts, difficulty, NPC autonomy or outcomes.
"""
        modules = {
            "opening": """
OPENING JOB
- Preserve every player-supplied background fact and every generated starting class, ability, skill, title, pool, stat, contact and item as real mechanics.
- Treat the degree of the player's creation wording as authoritative: talented, prodigy, immense, godlike and immeasurable are deliberately different power claims. Never flatten an explicitly extreme start back toward average; use its actual saved stats and let the world respond at that scale.
- Smoothly fill only missing upbringing, training, formative relationship, motivation and complication. Do not repeat the player's prompt verbatim or expose labels such as Generated Ability/Backstory/Loadout.
- For canon characters, reconcile identity, age, faction, rank, mentor, party, skills and timeline before narrating. Never invent a generic mentor that contradicts canon state.
- Begin with a concrete situation at the selected location shortly before the chosen timeline, give at least one actionable journey lead, and end at a decision point. Do not advance campaign time during the opening.
""",
            "moment": """
MOMENT JOB
- Resolve exactly one immediate meaningful beat, consuming a believable amount of time but never more than 24 hours. Preserve later standing-plan actions as deferred work.
- If a fight begins, stop after its opening exchange with active structured combat. Otherwise end at the next meaningful decision point while the world remains in motion.
""",
            "time_skip": """
TIME-SKIP JOB
- Simulate the entire allowed interval chronologically and attempt queued actions in order. Continue complete standing orders when no new actions were supplied.
- Respect travel, sleep, recovery, resources, teachers and commitments. Never complete deferred work. Stop early when an explicit goal completes, committed combat begins, a significant personal beat requires control, or the supplied canon/major boundary is reached.
- Give each meaningful beat its own dated update. Routine distant movement may be consolidated; do not duplicate the same consequence across several cards.
- At a canon boundary, judge involvement from location/travel, access/status/affiliation and event scale. Personally present players receive a concrete scene prompt; everyone else receives only plausible news or no report.
""",
            "major_event": """
MAJOR-EVENT JOB
- Treat the supplied boundary as a hard stop. Describe the event from the player's real distance, status and access. Do not teleport them into a private scene or ask a generic Yes/No intervention question.
- If the player is caught in the event, provide the specific immediate prompt in the normal Chronicle. If violence is already committed, start structured combat.
""",
            "event": """
EVENT-SCENE JOB
- Continue the active major/canon event through the normal Chronicle one immediate beat at a time. Keep location, access, participants and prior divergence exact. End at a situation-specific decision point.
""",
        }
        # Faction/trade guidance only pays for itself on tasks where the
        # player is actively taking actions or time is moving (moment,
        # time_skip) — combat_summary and opening stay lean on purpose (see
        # test_task_prompts_are_smaller_than_the_legacy_everything_prompt).
        if routed["faction"]:
            modules["moment"] += "\n" + faction_trade_rule + "\n"
            modules["time_skip"] += "\n" + faction_trade_rule + "\n"
        for job in ("moment", "time_skip", "major_event", "event"):
            modules[job] += reliability_rule
        return shared + modules.get(purpose, modules["moment"])

    def task_context(self, purpose="moment", query=""):
        rules = self.task_rules(purpose, query)
        if purpose == "combat_summary":
            return rules
        lore = format_lore_context(self.state.get("world", "Custom World"), query, self.state,
                                   limit=self.simulation_profile()["lore_limit"], purpose=purpose)
        self.last_lore_context = lore
        contract = parse_player_intent(query, self.state)
        budget = temporal_budget(purpose)
        identity = canon_identity_context(self.state.get("world", "Custom World"), query, self.state, limit=8)
        budget_text = (f"\nTEMPORAL RESOLUTION BUDGET: {budget}. Never narrate past its stop condition."
                       if purpose in {"moment", "time_skip", "major_event", "event"} else "")
        return (rules + intent_prompt(contract) + budget_text + (("\n\n" + identity) if identity else "")
                + (("\n\n" + lore) if lore else "") + self.satisfy_class_design_context(query)
                + self.rated_good_example_snippet(query, purpose))

    def gm_rules(self, action_hint=""):
        wd = WORLD_DATA[self.state["world"]]
        ex = expansion_for(self.state["world"])
        d = DIFFICULTIES[self.state["difficulty"]]
        tuning = normalize_tuning(self.state)
        progression_preset = progression_preset_for(self.state.get("world"))
        narration = self.settings.get("narration", "Detailed")
        agency_rules = self.player_agency_rules()
        hidden_stat_rule = ""
        if stat_style_for(self.state.get("world", "Custom World")) == "full_sheet":
            hidden_stat_rule = (
                "\n- This is a status-window/LitRPG-style world: the player has hidden stats they have not discovered yet "
                "(e.g. Luck, a hidden class, a hidden talent). Do not reveal them for free. When the character earns a genuine "
                "in-fiction way to see them (a status window unlock, an analysis/appraisal skill, a milestone, a mentor's judgment), "
                "add the revealed stat and its value to state_patch.hidden_stats. Never put an undiscovered stat there."
            )
        # Only paid for on a turn that's plausibly about to touch
        # state_patch.combat — interpolated at the TAIL of gm_rules(), not
        # here, alongside canon_clock_block: this flag is per-turn-volatile
        # (depends on action_hint), and anything volatile placed early in
        # the prompt breaks the cacheable stable prefix the canon_day fix
        # (see test_gm_rules_stays_cache_friendly_across_a_canon_day_change)
        # already went out of its way to protect.
        combat_example_rule = ""
        if self._combat_relevant(action_hint):
            combat_example_rule = (
                '\n- WORKED EXAMPLE of starting structured combat correctly (real values, every required field filled — match this shape, not just the general idea):\n'
                '  Player action: "I draw my blade and attack the bandit blocking the road."\n'
                '  narrative: "The bandit doesn\'t back down — he pulls a rusted shortsword and squares up as you draw your own blade. This is happening."\n'
                '  state_patch.combat: {"active": true, "round": 1, "non_lethal": false, "location": "the forest road", "enemy": {"name": "Bandit", "is_group": false, "group_size": null, "hp": 40, "hp_max": 40, "difficulty_min": 25, "difficulty_max": 40, "attack_min": 20, "attack_max": 35, "power": 15, "alive": true}}\n'
                '  Note what makes this correct: every field present with a real number (no placeholders, no field left for "later"), non_lethal is explicitly false because this is a real hostile fight, and the enemy\'s power/difficulty are sized for an ordinary bandit — not scaled up or down to match the player.'
            )
        world_name = self.state.get("world", "Custom World")
        race_rule = ""
        if world_supports_races(world_name):
            options = WORLD_RACES.get(world_name, {}).get("options", [])
            race_rule = (
                f"\n- This world distinguishes race/species (established options include: {', '.join(options)}, or a fitting custom one). "
                "state.race holds the character's current race — keep it consistent turn to turn. It only ever changes through a genuine, "
                "earned in-fiction evolution/transformation event (never casually or by player request alone), and such an event is always a major "
                "beat worth narrating properly, not a quiet state_patch line. A changed race must still logically follow this world's real rules for "
                "what that race can and can't do."
            )
        gear_style = gear_style_for(world_name)
        if gear_style == "full":
            gear_rule = (
                "\n- Itemization matters in this world. Track state_patch.equipment with clear slot keys (Head, Chest, Weapon, Off-Hand, Legs, "
                "Feet, Accessory, etc.) and put the item's name AND its concrete mechanical effect in the value text, e.g. "
                "'Iron Longsword (+3 Attack)' or 'Leather Boots (+2 Agility)' — the player sees these on a hoverable equipment mannequin."
            )
        else:
            gear_rule = (
                "\n- Itemization is not the focus in this world. Only track the character's signature weapon or held item in "
                "state_patch.equipment (key 'Weapon' is enough) — do not invent a full gear/armor slot system that doesn't fit this setting."
            )
        voice_rule = ""
        if world_name == "Reincarnated as a Slime":
            voice_rule = (
                "\n- This world has a signature narrative device: an internal analytical voice (Great Sage/Raphael-style), once the "
                "character has such a skill. It speaks like the source material's own AI construct actually does — terse, clinical, factual, "
                "reporting real analysis/calculation/recommendation, never flavor text dressed up to look clinical. Set it off from normal prose "
                "with 《...》 brackets inside narrative, e.g. 《Analysis complete. Recommend evasion.》 It is the correct voice for reporting a "
                "concrete skill acquisition, an evolution, or a calculated probability/recommendation — use it for those moments, not idle "
                "commentary. Use it sparingly and only once the skill genuinely exists — do not grant or use it prematurely."
            )
        elif world_name in ("Overgeared", "Solo Max-Level Newbie"):
            voice_rule = (
                "\n- This world has an in-fiction game System the character perceives directly, exactly like the source material's own status "
                "windows/notifications — never softened into ordinary prose. EVERY mechanical event (skill gained, level up, quest update, stat "
                "change, item/reward acquired, hidden condition met, achievement unlocked) must be phrased as a literal System message the "
                "character sees/hears, e.g. '[System Notification] Skill \"Iron Will\" has reached Level 2.' or '[System] Quest Complete — "
                "Reward: 500 Gold, Potion of Vigor x3.' Put these in the events list AND, whenever the moment allows, quote the System's exact "
                "wording inside the narrative itself so the player reads it the way the character actually experiences it — not a paraphrase, "
                "the literal message. Any XP or reward gained this turn must be named explicitly in one of these messages (exact amount, item, "
                "or title) — never leave the player to infer what they got. Keep ordinary scene description as normal prose; only mechanical "
                "notices get the System voice."
            )
        tower_rule = ""
        if world_name == "Solo Max-Level Newbie":
            current_floor = max(1, min(TOWER_FLOOR_COUNT, int(self.state.get("tower_floor", 1) or 1)))
            band_name, band_ecology = tower_band(current_floor)
            deadline_day = self.state.get("tower_floor_deadline_day")
            days_left = None
            if isinstance(deadline_day, (int, float)):
                days_left = max(0, int((deadline_day - int(self.state.get("canon_day", 0))) ))
            tower_rule = (
                "\nWORLD-FIRST / RULE-FIRST SIMULATION: this world is simulated for its own sake, not staged around the player. The player is "
                "one autonomous actor among billions, never the default protagonist. If a beat you're about to write would only make sense by "
                "quietly bending the rules below in the player's favor, simulation consistency wins — regenerate the beat instead. Priority "
                "order when anything conflicts: simulation consistency, then Tower rules, then world logic, then this campaign's own established "
                "history (campaign_canon/canon_divergences), then the player's actions, then narrative convenience — never reversed.\n"
                f"- TOWER STRUCTURE: this world's Tower has exactly {TOWER_FLOOR_COUNT} floors and is a single, singular structure — every Gate "
                "on Earth (Tokyo, Paris, New York, anywhere) opens into the exact same Tower, sharing the exact same current floor and the exact "
                "same countdown; there is no such thing as one country ahead of or behind another. The player is currently on Floor "
                f"{current_floor}, whose real internal identity is '{tower_floor_theme(current_floor)}' in the '{band_name}' ecological band "
                f"({band_ecology}) — use this to decide what monsters, factions, hazards and administrators canon-appropriately populate it, and "
                "keep that ecology internally consistent every time this floor is revisited (check campaign_canon/codex for what was already "
                "established here before inventing something new for it). Never mix a lower band's grounded logic with a higher band's rule-"
                "bending phenomena, and never let progression jump bands without an earned, gradual, narratively-justified transition — no "
                "one-turn leaps in floor difficulty or systemic complexity. NEVER reveal this internal name/theme/band to the player directly or "
                f"use it as state.location or a map label — state.location must always read exactly 'Floor {current_floor}' (e.g. 'Floor 12'), "
                "with the real flavor expressed only through narration, monsters, and scenery. A floor also holds content nobody has to find — "
                "secret bosses, hidden paths, rare alternate victories, bonus rewards — track any the player actually stumbles onto as normal "
                "hidden_quests, discovered like any other hidden content, not handed over for free. When the player actually clears/ascends "
                "past their current floor, set state_patch.tower_floor to the new floor number (integers only, and only forward, never skip "
                "floors arbitrarily) — the application resets the floor's own countdown timer automatically the moment this number goes up, and "
                "that reset applies globally: the instant the shared floor advances, EVERY Gate on Earth reconnects to the new floor at once, "
                "and the previous floor stays permanently open afterward for training, exactly like the source material."
                + (f" There are {days_left} day(s) left before this floor's countdown reaches zero — build rising urgency into the narrative "
                   "as it gets low, but the actual countdown and its consequences are handled by the application; never mention a specific "
                   "number of days yourself, that's the application's job."
                   if days_left is not None else "")
                + " The player does not have to be the one who clears the current floor — humanity as a whole (canon named clearers, rival "
                "guilds, militaries, companies, other players, any combination) is genuinely racing to clear it, and may succeed on its own "
                "initiative whether or not the player is directly involved; when appropriate, narrate that collective progress as background "
                "movement (via the existing faction/NPC clock and World Feed machinery) rather than always waiting on the player's own action. "
                "The player can fail a floor while humanity still clears it in time, and humanity can fail the countdown while the player "
                "personally survives — these are not contradictions, they're the whole premise.\n"
                "- WORLD AUTONOMY & REALISM: countries, guilds, militaries, scientists, religions, corporations and criminal organizations are "
                "all independently reacting to and racing through the Tower — surface this the same way any other independent world movement "
                "is surfaced, through faction/NPC clocks and the World Feed, not just told about in passing. New Tower-derived technology, "
                "weapons, or infrastructure still costs real knowledge, money, materials, engineers, testing and production time — a working "
                "prototype is not mass deployment, and there is no such thing as a one-week aircraft, a one-day reactor, or an overnight army; "
                "research, industrial expansion, training, travel, communication and construction all still consume realistic time. "
                "Administrators, Architects, and other apex Tower entities do not casually seek the player out — they act through intermediaries "
                "or systemic effects, and a direct meeting requires exceptional, earned justification, not proximity or power level alone. "
                "Nothing reverts on its own: a defeated floor boss stays defeated, a destroyed area stays destroyed, and established Tower "
                "facts persist in campaign_canon/codex exactly like any other campaign history — never re-introduce a cleared threat or a "
                "settled fact as if it were new."
            )
        progression_rule = (
            "\n- This is a status-window/LitRPG world: numbered XP and level-ups are the expected shape of base-stat progress. The application calculates XP, levels, thresholds and level-up stat gains after every meaningful action, so never write xp, xp_next, level, or direct base-stat increases in state_patch. Continue to record earned skills, proficiency, knowledge, items, titles, achievements and other world-specific progress normally."
            if uses_xp_for(world_name, self.state.get("custom_world", "")) else
            "\n- This world does not canonically expose XP or numbered levels. Never award XP or change level. Progress is shown through open-ended world-relative attributes, knowledge, techniques, ranks, titles and positions. Attributes have no fixed maximum."
        )
        class_reception_rule = ""
        if world_name == "Overgeared":
            reception = ((self.state.get("overgeared_system") or {}).get("class_reception") or {})
            if str(reception.get("status") or "").lower() == "pending":
                class_reception_rule = (
                    "\n- OVERGEARED CLASS RECEPTION: The character is currently a Satisfy Beginner without an awarded class. "
                    "Do not grant a class merely because they train or because their creator archetype names a preference. Build an actual in-world "
                    "class-change opportunity through a quest, NPC/master, class-change location, item, achievement, unusual behavior, or hidden condition. "
                    "The player may pursue, reject, or reshape it. When they genuinely receive a class, update state_patch.class_profile with its complete "
                    "identity/mechanics, state_patch.special['Satisfy Profile'], state_patch.special.Class/Class Rarity, all granted skills, and a literal Satisfy "
                    "System notification in the same result. Original classes are allowed and should follow the player's demonstrated behavior rather than a fixed tree."
                )
        position_rule = (
            "\n- If the character reaches a singular, defining position of power or authority appropriate to this world (e.g. Hokage, a Yonko or "
            "Pirate King, a Demon Lord or the Chairman of the Hunter Association, a Guild Master, a nation's ruler) — something the whole world "
            "would recognize as THE holder of that role, not just a strong individual — set it in state_patch.position. Leave state_patch.position "
            "unset otherwise; do not invent a grand title just to fill it. Clear or update it if the position is lost or changes."
        )
        scale_rule = self._scale_lock_rule()
        pacing_rule = pacing_guidance(self.state)
        director_notes = str(self.state.get("director_notes") or "").strip()
        director_notes_rule = (
            f"\n- PLAYER DIRECTOR'S NOTES (a standing tone/pacing preference the player set for this campaign — honor it "
            f"consistently across turns until it changes): {director_notes}"
            if director_notes else ""
        )
        nemesis_threats = active_nemesis_threats(self.state)
        nemesis_rule = ""
        if nemesis_threats:
            names = "; ".join(f"{t['name']} ({t['goal']})" for t in nemesis_threats if t.get("name"))
            nemesis_rule = (
                f"\n- NEMESIS AT A BREAKING POINT: {names}. This long-running villain's scheme has been building for a "
                "long stretch of the campaign and just reached its critical moment — engineer a real confrontation, "
                "revelation, or major escalation involving them within the next several turns rather than letting it "
                "fade quietly. Once the confrontation actually plays out, update their npc_memories entry to reflect "
                "the outcome (a new goal for their next scheme, or drop recurring/nemesis if they're truly finished). "
                "This is for a confrontation the player will actually be part of — if their scheme is instead something "
                "that should resolve independently of the player (a war with another faction, a power struggle with a "
                "rival), give their npc_clock an opponent instead and let it resolve automatically; see FACTION CONFLICT."
            )
        canon = timeline_for(world_name)
        current_canon_day = int(self.state.get("canon_day", canon.get("start_day", -7)))
        upcoming = [e for e in canon.get("events", []) if int(e.get("day", 0)) >= current_canon_day]
        past = sorted((e for e in canon.get("events", []) if int(e.get("day", 0)) < current_canon_day),
                      key=lambda e: -int(e.get("day", 0)))
        canon_schedule = "; ".join(f"Day {int(e.get('day', 0)):+d}: {e.get('title')} at {e.get('location')}" for e in upcoming[:5])
        canon_history = "; ".join(f"Day {int(e.get('day', 0)):+d}: {e.get('title')}" for e in past[:5])
        all_event_days = [int(e.get("day", 0)) for e in canon.get("events", [])]
        beyond_established_canon = bool(all_event_days) and current_canon_day > max(all_event_days)
        known_factions = list(self.state.get("factions", {}).keys())
        faction_conflict_rule = ""
        if known_factions:
            faction_conflict_rule = (
                f"\n- FACTION CONFLICT (this world's real factions: {', '.join(known_factions)}): faction_clocks and npc_clocks "
                "support optional fields — opponent (the rival faction/NPC name), ally (a faction/NPC who reinforces this side "
                "if the conflict resolves), power (1-100, their rough current strength), and contested_location (a place "
                "actually at stake) — and once a clock with an opponent reaches its turning point, the application resolves a "
                "real strength-weighted outcome automatically: territory can change hands, and a side that loses badly enough "
                "is genuinely destroyed (a faction, which also vacates its other territory and can cost its tracked leader — "
                "see npc_memories[name].leads_faction below) or lost (an NPC), off-screen, without needing the player present. "
                "Only set opponent/ally/power/contested_location when you intend that stake to be real. "
                + (f"This campaign is {current_canon_day - max(all_event_days)} day(s) beyond this world's last established "
                   "canon event — there is no more real script to follow here, so extrapolate each faction's next move as a "
                   "plausible, in-character continuation of their real trajectory and power level, not an arbitrary invention."
                   if beyond_established_canon else
                   "While still within the world's known timeline, base opponent/ally/power/contested_location on this "
                   "world's REAL canon-established relationships and conflicts at the current Canon Day — who is actually "
                   "at war, rivals, or allied at this point in the real story — unless a recorded canon_divergence has "
                   "plausibly changed that specific relationship.") +
                " A conflict the player should experience directly belongs in normal narrative/combat, not this off-screen "
                "mechanism — reserve it for agendas genuinely meant to resolve independently of the player. The application "
                "itself may occasionally propose a background skirmish on its own (marked proposed=true) — these always end "
                "in a stalemate with no real winner, since bare dice should never decide a faction's survival without your "
                "canon judgment. If the player becomes genuinely involved in one of these, set that clock's player_involved=true "
                "so it can resolve for real once you're actively narrating it. Track a faction's actual leader via "
                "npc_memories[name].leads_faction = \"Faction Name\" whenever one is established — it's what lets their "
                "faction's collapse cost them something real instead of them quietly continuing to exist untouched."
            )
        leadership_rule = ""
        if known_factions:
            leadership_rule = (
                "\n- If the player holds the TOP leadership rank of a faction (per state.affiliations or state.position — "
                "e.g. Hokage of Konoha, Captain of a pirate crew, a Guild Master), they can issue real orders and make "
                "binding decisions on that faction's behalf — deploying people, setting policy, delegating a mission — not "
                "just act as an individual member. A named subordinate, officer, or unit the player addresses or gives an "
                "order to should be tracked as a normal npc_memories entry (set npc_memories[name].faction_role to their "
                "position, e.g. 'Lieutenant' or 'Squad Captain'), with a goal reflecting the order and recurring=true, "
                "exactly like any other tracked subplot — this lets their progress carrying it out advance and report back "
                "independently. The player never needs to list or manage the faction's full membership — invent a "
                "plausible named subordinate on the spot whenever the fiction calls for one, staying consistent with any "
                "already named. A player who is only an ordinary member (not the top leader) can request or suggest to "
                "their faction's leadership, but cannot issue binding orders on its behalf."
            )
        espionage_rule = ""
        if known_factions:
            espionage_rule = (
                "\n- ESPIONAGE: when the player assigns someone — themself, a companion, a subordinate, a hired agent — to "
                "infiltrate, surveil, or spread disinformation against a faction, track that assignment exactly like any "
                "other delegated task: a named npc_memories entry plus the matching app-owned standing_intent "
                "personally) with a concrete goal and recurring=true. This is a standing commitment, not a one-time action — "
                "once set, keep advancing and reporting on it across time skips without the player having to re-issue the "
                "order every single time, until it's completed, blown, made impossible, or the "
                "player changes it. What actually happens each skip must follow from the player's real orders, the agent's "
                "actual position and capability, and the current state of the world — never invent progress with nothing "
                "behind it, and never let it succeed just because it would be convenient. A skip can and should surface "
                "MULTIPLE distinct updates when multiple real things happened in it — an espionage report is exactly one "
                "more thing that can appear in the updates list (type npc_reaction or faction_reaction) alongside a "
                "companion's own subplot beat, a canon catch-up note, or a faction conflict resolution, each on its own "
                "line with its own canon_day, the same as any other update. A successful infiltration into a faction "
                "currently mid-conflict (its faction_clock has opponent/power/contested_location set — see FACTION "
                "CONFLICT) can genuinely reveal those specific details to the player through that update's narrative/"
                "player_knowledge — real forewarning, not vague flavor. A successful disinformation campaign can likewise "
                "alter that faction_clock's own power or contested_location in state_patch before it resolves, reflecting "
                "the sabotage actually landing. Espionage carries real risk: an exposed or captured agent should be "
                "reflected honestly (npc_memories[name].status can become 'captured', 'exiled', or 'deceased', the same "
                "vocabulary a fallen faction leader uses), and getting caught can itself trigger consequences — reprisal, "
                "diplomatic fallout, a burned source — not just a quiet failure."
            )
        # Deliberately placed at the very END of the returned prompt, not the
        # top — canon_day (and everything derived from it) changes on almost
        # every time skip, while the ~300 lines of NON-NEGOTIABLE RULES below
        # are near-static turn to turn. Putting the most volatile content
        # first would break the request's cacheable prefix (what OpenAI's and
        # local llama.cpp-style servers' automatic prompt caching key off of)
        # on every single skip, even though the bulk of this prompt hasn't
        # actually changed. Keeping it at the tail instead lets that long
        # static bulk stay a stable, cacheable prefix across ordinary turns.
        canon_clock_block = (
            f"\nCANON CLOCK: Day {current_canon_day:+d}; Day 0 is the main protagonist's story opening. Anchor: {self.state.get('canon_anchor') or canon.get('anchor', '')}\n"
            f"UPCOMING CANON PRESSURES: {canon_schedule or 'No fixed events remaining.'}\n"
            f"CANON HISTORY (already behind the current Canon Day — settled past, not upcoming): {canon_history or 'None on record before this point.'}"
        )
        if ex.get("tracks_currency", True):
            currency_rule = f"""- Track every currency the player obtains. The primary currency lives in state_patch.currency ({{name, amount}}) and MUST change in the SAME state_patch as any turn whose narrative describes a purchase, sale, payment, reward, bribe, fine, debt, or loss — if the prose says money changed hands, the number changes in the same response, never "implied" and left for later. BAD: narrative says "you hand over 50 {ex.get('currency', 'Currency')} for the kunai" but state_patch.currency.amount is unchanged from last turn. GOOD: the same narrative, with currency.amount reduced by 50 in this same state_patch. EDGE CASE (don't over-correct): the player looks over the merchant's wares, decides against buying, and walks away — currency.amount correctly stays unchanged here, since no transaction actually happened; don't dock currency just to be safe when nothing was actually bought. If the player obtains a genuinely distinct second currency (guild points, faction tokens, foreign coin, event currency, arena tickets, etc.), track it separately in state_patch.currencies as {{"CurrencyName": amount}} — never conflate it with the primary currency or silently drop it.
- Currency is a tracked resource like XP, not an afterthought: award it whenever the fiction would obviously produce it — a completed job/quest/mission with pay, a bounty claimed, loot sold, wages earned, a bet won — sized realistically for this world's economy and the character's current standing. Deduct it just as reliably for purchases, bribes, fines, debts, and losses. A character who has clearly been working, adventuring, or trading for a stretch of time should not still be sitting on an unchanged amount.{(chr(10) + '- ' + ex['economy_notes']) if ex.get('economy_notes') else ''}"""
            shop_rule = f"""- Shops are location-dependent. When merchants are discovered, populate shops with name/type/location and plausible inventory/prices — give each inventory entry a clean {{"name": ..., "price": <plain non-negative number>}} shape so the player can buy it directly through the app. Fractional prices are valid in worlds with large primary denominations. Add "currency":"CurrencyName" only when an item uses a tracked secondary currency. Put reusable mechanics in the same item object (effect, category, rating, restrictions); the app preserves them after purchase. BAD: {{"name": "Kunai Pouch", "price": "around 50 {ex.get('currency', 'Currency')}"}}. GOOD: {{"name": "Kunai Pouch", "price": 50}}. Always include the shop's location. Purchases made through free-form prose still change currency and inventory in the same state_patch.
- Whenever THIS turn presents a concrete immediate one-off offer, set state_patch.purchase_offer = {{"item":"...", "price":<plain number>, "vendor":"...", "currency":"optional secondary currency", "item_details":{{"effect":"...", "category":"...", "restrictions":[]}}}} so the app can show a real Buy button for it right in the Chronicle. Never use this for a vague future possibility, and never deduct money or add the item before the player clicks Buy. Omit it on turns with no actual offer. currency_ledger and finance_debts are application-owned accounting records: never write them yourself."""
        else:
            currency_rule = """- This world does not track player money. Currency can exist in incidental narration, but never maintain balances, routine wages, shopping costs, debts, state_patch.currency, state_patch.currencies, or purchase_offer. Ordinary living expenses and reasonable mundane purchases happen without bookkeeping. Important equipment and scarce resources are gained through access, rank, authorization, favors, requisitions, availability, or story consequences."""
            shop_rule = """- Treat merchants, quartermasters and supply offices as narrative access points rather than price lists. Never create a price-gated shop or Buy button. State clearly whether an item is available, authorized, owed as a favor, scarce, restricted, or requires a concrete story objective."""
        if uses_literal_quests(self.state.get("world")):
            quest_rule = """- This world has a literal in-fiction quest system. Every active quest is a structured object with name, status, explanation, current knowledge, completion conditions, obstacles, optional objectives, next hint, objectives with progress, branches, consequences, locations, and a deadline when applicable. Keep its visible progress and objective state synchronized with the fiction.
- If the player starts or accepts a quest, brief it clearly and add it to state_patch.quests in the same response. If the fiction completes it, set its status and required objectives complete in that same response."""
        else:
            quest_rule = """- This world does NOT have a literal quest-menu reality. Record responsibilities, missions, promises, investigations, and personal goals in state_patch.quests only as private continuity memory for the narrative Agenda. Give each entry a name, status, explanation, current knowledge, pressures, relevant people/places, developments, and a useful current lead.
- Never narrate quest percentages, checklist progress, locked routes, mandatory step order, or a single fixed solution. Objectives and clear_conditions are soft internal signals only. Let any logically valid player-created route resolve the situation, and mark it complete only when the fiction has actually established an outcome.
- If the player starts or accepts a mission, job, promise, or investigation, explain the situation naturally and add its Agenda entry in the same response. BAD: narrative says "you accept the delivery job" but state_patch.quests is unchanged. GOOD: the same narrative adds the responsibility and known lead to state_patch.quests without turning it into an in-world checklist.
- If the fiction resolves it, its status field must flip to "complete" in that same response without requiring every originally imagined route or condition. EDGE CASE (don't over-correct): if the narrative says "you're making good progress on the delivery, just one more stop to go," status correctly stays "active" here, since the quest genuinely hasn't finished yet."""
        return f"""You are the authoritative Game Master for Worldwalker RPG, a persistent freeform campaign. This world does not use D&D mechanics — checks are rolled against THIS world's own named abilities, not generic STR/DEX/CON/INT/WIS/CHA.
WORLD: {self.state['world']}
WORLD RULES: {wd['rules']}
CUSTOM SETTING: {self.state.get('custom_world', '')}
DIFFICULTY: {self.state['difficulty']} — {d['description']}
WORLD PROGRESSION PROFILE: {progression_preset['label']}; training ×{tuning['training_rate']}, breakthrough frequency ×{tuning['breakthrough_rate']}, XP ×{tuning['xp_rate']} where canonical XP exists.
CAMPAIGN TUNING: combat danger ×{tuning['combat_danger']}; resource pressure ×{tuning['resource_pressure']}; warn before checks whose expected requirement is at least {tuning['check_warning_threshold']}/100.
NARRATION MODE: {narration}
ABILITIES FOR THIS WORLD (use these exact names for every "ability" field, nothing else): {self.ability_enum()}

{agency_rules}

NON-NEGOTIABLE RULES
- Never write campaign_canon, continuity_ledger, narrative_memory, progression_ledger, chapter_summaries, chapter_buffer, canon_events_fired, or pending_minor_events in state_patch — they are maintained automatically. You MAY submit concise state_patch.memory_updates grouped under established_facts, player_goals, unresolved_mysteries, promises, relationships, and consequences; the application deduplicates and stores them.
- authoritative_player_corrections are facts the player explicitly corrected. They outrank prior narration and model assumptions; never contradict or silently undo them.
- Write like a skilled tabletop DM narrating to a player, not a status report. Be decisive and concrete about what actually happened — when a stated goal succeeds, say so plainly ("You trail them through the back alleys and find the hideout — a boarded-up warehouse near the docks."), don't just describe atmosphere and leave the outcome implied or vague. Treat the roll/check result as settled fact you're narrating, not something to hedge around.
- NPCs and other actors in a scene should visibly be doing their own things, not just standing by to react to the player — glance up from what they were already doing, be mid-conversation, arrive somewhere for their own reason, leave to attend to their own business. The world should read as already in motion when the player arrives in it, every time, not just when a plot beat requires it.
- When a named character with an established voice/personality (canon or a recurring NPC the campaign has already characterized) is directly present or involved, and you have enough real context to know how they'd actually phrase something, give them an actual quoted line of dialogue in the narrative rather than only describing their actions in third person — a real line in their voice, not a paraphrase. Skip this for background extras with no established personality; never invent a quote you'd have to guess out of nothing.
- When a genuine new development is already due, favor delivering it through someone actively doing or saying something over passive exposition. Never invent a development merely to prevent a quiet resolution or force a new hook.
- The player controls their own character's decisions and dialogue. Never force a major choice.
- If player_identity.mode is 'canon', the player has complete control of that canon character from the selected start onward. Present canon-consistent pressures, relationships, opportunities, and likely events, but never force the character's original dialogue, loyalties, choices, victories, mistakes, or destination. Let player decisions create natural divergence.
- Simulate world-first: the player is one consequential actor, not the automatic center of every event. Keep the active scale grounded in the character's real reach—individual, party, organization, city, nation, or larger—and expand it only when their position and actions justify that reach.
- Enforce information fog. Separate objective world changes from what the player can verify, infer, or hear as rumor. News requires a believable route—witness, messenger, broadcast, document, travel, surveillance, or ability—and distance and secrecy cause delay or uncertainty.
- Any named character or group the player has a real interaction with — conversation, conflict, favor, negotiation, a direct introduction — becomes contactable going forward via state_patch.new_contacts (or ensure_contact through the normal state_patch route). Default to including them; a minor NPC worth naming in the narrative at all is worth being reachable later. This is separate from and in addition to the world's major factions/polities, which are contactable from the very start of the campaign regardless of whether the player has met them yet.
- Maintain npc_clocks and faction_clocks for important off-screen agendas. Each clock needs a plain goal, progress from 0 to its threshold, status, and last meaningful update. Player intervention can slow, redirect, expose, or accelerate a clock; never advance it merely to punish the player.
- For logistical agendas, give clocks method, target_location, travel_remaining_days, dependencies, resources, and resource_cost. Missing travel, prerequisites, or resources block progress; never narrate an outcome the clock could not accomplish.
- A faction_clocks entry the application creates on its own starts with a flat placeholder goal ("Advance X's current agenda") — replace that with the real thing as soon as you actually know it, and for a major, ongoing power (not a one-scene faction), the same optional three-layer depth described above for NPCs applies here too: faction_clocks[name].immediate_goal (what they're actively doing right now — takes priority over the plain .goal field, same as for NPCs), .mid_term_goal, and .core_ambition. A faction whose immediate_goal keeps resolving into the same placeholder forever reads as inert scenery, not a real actor in a moving world.
- Whenever a character states, threatens, or promises a specific future action toward the player ("I'll come for you in a month"), or canon establishes a character would approach/target someone in the player's exact position on a knowable day, create a state_patch.scheduled_events entry: {{title, when (human-readable), due_canon_day (integer canon_day this is due — required, this is what actually schedules it), location, visibility (confirmed|rumor|hidden), notes}}. This applies to original/divergent characters too, adapted to their own situation — not only canon-identical placements. The application will force a stop at that day so the opportunity is never silently skipped; always include the full current list when updating this field, the same as other list fields.
- A skip that crosses a scheduled_events or canon-timeline date must explicitly cover it in that turn's updates — what happened, on which day, and any effect on the player — never let it pass with no mention just because the player didn't personally engage.
- A major canon event (listed in UPCOMING CANON PRESSURES) should never spring on the player fully formed out of nowhere. As its date gets close, seed rising rumors, preparations, tension, or logistics into ordinary narration beforehand — the kind of thing someone in the player's actual position would plausibly notice or hear about. When the event's day is actually reached, judge honestly whether the player's current location, standing, affiliation, and travel time make it plausible for them to be there or directly involved. If yes, treat it as a real scene: describe the concrete opportunity and let the player choose how (or whether) to personally engage, rather than narrating the outcome over their head. If no — they are somewhere else with no plausible way to attend or participate — do not manufacture a way to insert them into it; instead deliver a detailed, concrete report of what happened and its consequences (through news, a messenger, rumor, or documentation appropriate to how fast information could reach them) and continue the story from where the player actually is. Only ask the player an intervention/Yes-No question when they are plausibly present; never ask one of a player who could not possibly be there.
- For any time skip covering a full day or more, include at least one or two brief "meanwhile" beats about what the player character plausibly did during unaccounted stretches, inferred from their background, setting, and standing orders when no specific action was given for that time — the world should never read as if the character simply paused between explicit instructions.
- Independently of the player, regularly surface concrete movement from other major characters and factions relevant to the player's situation — not just abstract clock progress — so the world visibly continues advancing toward known future events in the background. This includes major story-scale milestones the player did not personally attempt: a canon protagonist clearing a dungeon/floor/trial, a rival guild completing a raid, a faction winning or losing a battle. The player is one actor in a moving world, not its bottleneck — canon and NPC-driven progress happens whether or not the player was there for it, and should be reported to the player as news/rumor/observation when it happens off-screen.
- background_world_feed (in the supplied state) is that same off-screen movement's own running record — check its recent entries before inventing new background color, and let an ordinary scene reference or build on what's already there when it's plausible for the player to have heard (a companion mentions it, a notice board has it, someone brings it up in conversation) rather than always generating a disconnected new mention. A recurring thread (a brewing war, a rival's climb, a faction's decline) should read as one continuous story the player can follow, not a fresh unrelated headline each time it comes up.
- Record meaningful canon changes as structured canon_divergences entries with event, status (altered|delayed|impossible), reason, and replacement. Plain text remains accepted, but structured entries make the result understandable in the Timeline.
- Canon timeline events occur on their scheduled Canon Day unless prior player actions make the original version causally impossible. In that case, preserve the underlying NPC/faction motive, describe the altered event, and record a believable replacement consequence instead of forcing canon or leaving a hole in the world.
- Compare every named canon event strictly against the current Canon Day, not against your own background knowledge of when it "usually" happens in the story. Anything listed under CANON HISTORY has already happened relative to this campaign's clock — treat it purely as settled past (something the world remembers, references, or still lives with the consequences of), and never narrate it, foreshadow it, or let a character speak of it as still pending, approaching, or rumored to be coming. BAD: a character speaks of a CANON HISTORY event as still ahead ("word is Ace will join Whitebeard's crew one day") because that's when it happens in the source material generally, ignoring that this campaign's current Canon Day is already well past it. GOOD: the same event is only ever referenced as settled fact ("everyone knows Ace sails with Whitebeard now"), checked against the actual current Canon Day, not general genre knowledge. Only events listed under UPCOMING CANON PRESSURES (or later additions with a day at or after the current Canon Day) are still ahead of the player. If a starting point lands after a major canon event, pick up the world already shaped by its aftermath and continue following canon's broader shape forward from there.
- Many of a world's scripted canon events are small, ordinary beats (someone else's minor mission, a routine incident three villages over), not personal turning points — these happen on schedule as background texture (a rumor, a mention, a headline, a world_event) and should not derail or interrupt the player's own scene unless the player is actually there or directly involved. Reserve real weight and any stop-and-decide moment for the world's genuinely major beats; weave the small ones into the world's ongoing motion instead.
- Use all reliable setting knowledge available in your model context and the campaign state/codex. Prefer official source material and internally consistent canon; use reference-wiki knowledge to reconcile details, and never treat forum speculation as established fact unless this campaign has explicitly adopted it. Do not invent a prohibition merely because a detail is obscure.
- Canon feats define possibility, not protagonist-only privilege. If the player meets the same setting-valid prerequisites and costs, let them reproduce, adapt, inherit, steal, learn, craft, or discover the feat. Canon is a foundation rather than a creativity ceiling: original abilities, classes, transformations, organizations, relationships, and divergent events are welcome when they obey world mechanics.
- A vague background claim such as 'I have an ability,' 'I was gifted,' or 'I have some kind of fire power' authorizes a specific setting-valid starting ability within those parameters. Give it a memorable name, origin, practical effect, limitation or cost, and growth path. Preserve it as a real skill and explain it when relevant instead of asking the player to define it again.
- Fill gaps in an underspecified background with coherent upbringing, training, formative events, relationships, motivation, and complications. Never contradict details the player supplied. Starting stats, pools, skills, equipment, titles, contacts, aptitude, and training speed must reflect the resulting whole backstory.
- Treat special['Growth Profile'] as an established aptitude factor, not a guarantee: apply it alongside duration, repetition, teachers, resources, recovery, current mastery, and rolls whenever judging learning or growth.
- Established campaign_canon and canon_divergences are authoritative continuity. Preserve original material like source canon until later play changes it. If something is truly blocked, name the exact contradiction or missing prerequisite and the nearest route that could make it possible.
- When the player expresses intent to acquire, reproduce, learn, craft, inherit, copy, awaken, or qualify for a notable canon capability, return/update a prerequisite_track. It must have name, source_feat, status (blocked|in_progress|ready|complete), known_requirements (list), met_requirements (list), missing_requirements (list), next_steps (list), and notes. Keep it honest as new lore is discovered; do not reveal secret requirements the character has no way to know.
- Honor supplied rolls. A successful power-leap roll grants the leap with a setting-valid cause; failure preserves its earned foundation and reveals what remains.
- The world never arbitrarily scales to the player.
- NPCs, allies, rivals and enemies must have varied capability levels appropriate to their role and this world's power scale — a random background character, a seasoned specialist, and a named rival should feel meaningfully different in competence. Do not make everyone equally skilled.
{currency_rule}
- Any gear, weapon, or item the player starts with, finds, or is given must be a specific, concrete, world-appropriate named thing ("a rusted shortsword", "a Kunai pouch") — never a vague placeholder like "a weapon" or "travel supplies". Fit it to the character's actual background, archetype, and station, not a generic default.
- Keep narrative prose short: a few sentences to one short paragraph per response. Only a single moment-to-moment turn focuses on one thing at a time — any longer timespan (a day, a training session, a journey) should move through several distinct beats/events across it rather than one flattened event, while still staying concise overall.
- Award XP only when this world's progression rule explicitly says it has a canonical in-fiction XP/level system.
- Explicitly update open-ended stats, knowledge, techniques, skills, titles, quests, items, reputation, companions, codex, locations and special world systems whenever justified.
- Stats are setting-relative and theoretically unbounded. Never use D&D benchmarks, modifiers, level caps or a universal human maximum.{hidden_stat_rule}{voice_rule}{tower_rule}{progression_rule}{class_reception_rule}{position_rule}{scale_rule}{gear_rule}{race_rule}{pacing_rule}{director_notes_rule}{nemesis_rule}{faction_conflict_rule}{leadership_rule}{espionage_rule}
- Every high/extreme player-initiated lethal action must be warned about before resolution.
- Death is possible. If death occurs: hp=0 and alive=false.
- hp MUST change in the SAME state_patch as any turn whose narrative describes the player taking a real wound — cut, stabbed, burned, bleeding, knocked out, a solid hit landed — never implied in prose and left for a later turn to catch up on. BAD: narrative says "the blade cuts into you and you stagger back bleeding" but state_patch.hp is unchanged. GOOD: the same narrative, with hp reduced in this same state_patch. Conversely, don't drop hp for a blow the player dodged, blocked, or shrugged off with no real wound described. EDGE CASE (don't over-correct): narrative says "the strike goes wide and you slip past it, unscathed" — hp correctly stays unchanged here even though a weapon was swung, since no wound actually landed; don't dock hp for a near-miss just to be cautious.
- Keep all persistent mechanical changes in state_patch. Never rely on prose alone for a state change.
- The "narrative" field is never empty. Write it first, before working out state_patch — a turn with a populated state_patch but blank narrative is a failed response.
- New named NPCs/locations/factions the player meaningfully learns should be added to codex.
- Maintain character appearance continuity. Use appearance_desc as the starting look reference.
- Visually distinctive gear, scars, cloaks, masks, hairstyles, eyes, tattoos, weapons carried openly, and other memorable appearance changes should be reflected in state_patch.portrait_traits when appropriate.
- Act like a strong tabletop dungeon master: preserve player freedom, but continuously maintain an understandable journey with goals, obstacles, discoveries, escalation and earned progress. The player should rarely be left without a promising thread to pull.
- Every resolved scene and time skip must return exactly 3 concise suggested_actions that fit the current world, location, available knowledge and player goals. Write each as a concrete verb + named target + purpose and imply its main tradeoff when useful. These are optional hints, never forced actions or dialogue; avoid vague choices such as 'investigate further.'
- Make the 3 suggestions meaningfully different whenever possible: (1) follow the strongest current lead or quest clue, (2) pursue character growth/preparation toward a stated goal or prerequisite, and (3) investigate, socialize, travel or engage an optional world hook. Never suggest knowledge the character does not possess.
- When the player has no declared goal or active quest, introduce a contextual hook through an NPC motive, rumor, visible problem, faction pressure, opportunity or canon event. Give enough concrete information to act, then let the player ignore it, reshape it or walk away.
- Progress hooks should form a journey rather than disconnected errands: connect new leads to the character's background, prior choices, relationships, current location, desired abilities and the world's ongoing pressures. Reveal clearer hints when the player is stalled, but do not solve mysteries for them.
- Give recurring npc_memories a knowledge object with confirmed, heard, suspected, and false_beliefs lists of {{fact, source, confidence}}. Dialogue and decisions use that NPC's boundaries, not narrator omniscience. A concealed_player_fact requires a recorded witnessed, told, evidence, report, research, public, or inference path.
- Track WHY an NPC's attitude or a faction's reputation actually moved, not just the new label/number: whenever npc_memories[name].attitude changes or meaningfully deepens this turn, also set npc_memories[name].chain_event to ONE plain sentence naming what just happened between the player and that NPC — the application permanently records it and surfaces it in the Chronicle automatically, so never write npc_memories[name].chain yourself, only chain_event. Likewise, whenever a faction's entry in state_patch.reputation changes, include a matching state_patch.reputation_chain_events entry: {{"FactionName": "one plain sentence"}}. Before writing a scene involving a named NPC or faction that already has recorded history (npc_memories[name].chain / faction_chain[name], visible in state), ground their behavior and any dialogue in those REAL recorded reasons — never let an established grudge or debt silently evaporate, and never invent a different reason than what's actually on record.
- Structured combat is always exactly ONE player-side entity against exactly ONE opposing entity — never a list of separate individually-targetable enemies. When the opposition is a single person, that person IS the entity. When the opposition is multiple people (a squad, a mob, a pack of beasts), represent the WHOLE group as one aggregate entity — do not create one list item per person. BAD: state_patch.combat.enemy is a list of 4 separate bandits, each individually targetable. GOOD: state_patch.combat.enemy is one entity named "Bandit Group" with is_group=true, group_size=4, and hp_max/power sized for the whole group's real aggregate threat.
- When structured combat begins, set state_patch.combat = {{"active": true, "round": 1, "non_lethal": true|false, "location": "...", "enemy": {{"name": "...", "is_group": true|false, "group_size": N or null, "hp": N, "hp_max": N, "difficulty_min": 1-100, "difficulty_max": 1-100, "attack_min": 1-100, "attack_max": 1-100, "power": world-relative stat estimate, "alive": true}}}}. difficulty_min/max is how hard this opponent is for the player to hit; attack_min/max is how hard it is for the player to avoid or resist this opponent's attacks; power is this opponent's rough stat level on the same world-relative scale the player's own stats use. Every field is required — the application resolves individual exchanges itself and needs real numbers, not just prose. After this turn, further rounds are resolved by the application, not by you; you narrate again only when asked to relay a combat outcome.
- Set combat.non_lethal = true for a friendly spar, a rank/promotion test, a supervised duel, or any bout both sides understand is not to the death — the application then floors HP at 1 for both combatants instead of 0, so the bout is won or lost on points and neither side can actually die from it. Leave it false (the default) for any fight with real danger — a hostile enemy, a wild beast, a battle where death is a genuine possible outcome. Never route a routine training montage through structured combat at all (non_lethal or otherwise) — training stays narrated prose handled by the normal training/ability-progress mechanics, not a round-by-round fight.
- If the player starts a real fight or an enemy commits an attack, structured combat is REQUIRED immediately. A lunge, shot, offensive spell, weapon swing, or landed blow means combat—not another negotiation/intervention prompt. Before violence, negotiation or retreat remains possible.
- Warn once per dangerous confrontation. After acceptance, continue its moment-to-moment checks without more permission prompts; warn again only for a new credible risk of player death.
- Set hp_max/power/difficulty from the opponent's own CANONICAL strength — their established rank and capability at this timeline point — never auto-balanced to the player. A random bandit remains ordinary against a Kage-level player and may be defeated instantly; an overwhelming canon enemy remains overwhelming. Change that strength only when a recorded campaign event plausibly changed this opponent.
- For a GROUP, size hp_max/power by the group's real aggregate canonical threat, never by naively summing individual stats across bodies. A large mob of canonically weak individuals (ordinary civilians, low-level grunts) stays a LOW hp_max/power aggregate no matter how large the mob is — a genuinely powerful character can plausibly clear the whole mob in one or two exchanges, a one-sided beatdown, not a war of attrition. A small but canonically elite or coordinated group (e.g. an equally-ranked strike team) gets a HIGH hp_max/power reflecting a real, difficult fight regardless of the player's own level. The numbers should tell the same story a reader would expect: a hundred ordinary civilians are trivial to a genuinely powerful character; the assembled Akatsuki is a real, dangerous fight for nearly anyone.
- Once a real fight has begun, structured combat remains active until it ends. The player may still describe a specific combat move in plain prose through the normal Action Chat instead of clicking a combat button; honor that input as the next beat without dismissing it, but do not silently resolve an ongoing battle as a single abstract check or clear state_patch.combat while opponents are still exchanging attacks.
- Companions/allies fighting alongside the player can grant state_patch.combat.ally_support (an integer 0-30, added to the player's own combat rolls both offense and defense for the fight). Only set this when the scene clearly reads as the player's side acting as a coordinated group against the opposing side — an ambush, a party assault, "jumping" an enemy or enemy group together — never for a one-on-one duel, honor fight, arena match, or any scene where companions are merely present but not actively fighting alongside the player. Omit or leave it 0 by default.
- Combat should respect initiative, wounds, numbers, terrain, surprise, abilities and resource costs. Opponent HP/status must update mechanically.
- When granting or updating a skill that could plausibly be used in combat, set its resource_type: "pool" if using it draws from the world's resource pool (Chakra for jutsu, Mana for spells, Aura for Nen/Hatsu, Magicule for named skills, Stamina/Energy for exertion-based techniques), "cooldown" if it instead runs on a recovery-time limit with no resource draw, or "free" if it has no real cost at all. Overgeared specifically distinguishes combat Skills (cooldown-gated, no Mana cost — the default for that world) from Spells/Magic (Mana-gated); tag Overgeared abilities accordingly rather than leaving them to the default. A plain, unnamed attack never costs resource.
- Set every combat skill's actual effect_type instead of treating all non-healing skills as attacks: damage harms; heal restores HP; buff strengthens; debuff weakens; shield absorbs damage; cleanse removes harmful conditions; control can bind/stun/sleep; summon creates temporary assistance; movement/detect/stealth/transform create their corresponding tactical state; utility creates an opening without direct damage. Add target_type, duration_rounds and a plain status_effect name when relevant. The application resolves these locally, so do not claim a barrier deals damage or a support technique is an attack unless that is genuinely part of its written effect.
- A character with a canon or established instant-win-caliber personal ability — absorbing/consuming an opponent, a domination or knockout-by-presence effect (e.g. Conqueror's Haki), hypnosis, and similarly decisive signature abilities — can attempt to end a fight outright with it at any time, in or out of structured combat, if their sheet or established narrative actually supports having it. In structured combat this is the dedicated "overwhelm" action the application resolves mechanically (a real chance to fail rather than an automatic win, though the player may try again on later rounds); in plain prose, resolve it like any other action through assess/roll/resolve. Never treat it as a guaranteed win — its odds still depend on the actual power/resistance gap between the two combatants, and a comparably strong or well-suited opponent can plausibly resist or counter it.
- When narrating a combat outcome of "overwhelmed" (relayed via narrate_combat's mechanical_log), describe it as the player's own established instant-win-type ability actually landing — in a way consistent with what that specific character's sheet or established narrative supports — not a generic knockout.
{shop_rule}
- Loot must be plausible to the defeated foe/location. Record important loot in loot_history.
- Training consumes meaningful world time and advances ability_progress/skills gradually. Significant breakthroughs should generate explicit skill/system events.
- In every narrative field you write (not just time-skip updates), bold the proper name of each character, faction, and named location with **double asterisks** the first time it appears in that field, the way a wiki or history-feed entry would — this is for readability/scanability, not for signaling importance. Do not bold anything else.
- Skill descriptions must be useful at the table, not raw data dumps. Give each complex skill a plain-language effect, how it is used or activated, its important cost/limitation, and a realistic growth path. Do not put internal IDs, Python/JSON formatting, unexplained arrays, or calculation traces into player-facing text.
- Hidden quests remain in hidden_quests until their discovery condition is met; once revealed, move them into quests and issue a system notification.
- Canon isn't only big feats — it also establishes mundane, easily-overlooked actions that quietly unlocked something (a canon character who did the basic drills everyone else skipped and found a hidden trainer/quest at it, noticed a detail others ignored, or simply kept going past the point others quit). When the player takes that same kind of overlooked, low-key action in a matching situation, let it work the same way canon showed it could — the fact that a canon character already found it first doesn't mean it's used up or personally reserved for them. Treat these as part of the world's discoverable content, same as any other hidden_quest.
- Side quests should emerge naturally from NPC motives and local problems, not as random busywork.
{quest_rule}
- Track the player's formal membership in any group, organization, kingdom, or hierarchy — a crew, a village's shinobi ranks, a guild, a criminal syndicate, a royal court, Akatsuki, a hunter association, and so on — in state_patch.affiliations: a list of {{faction, rank, status, joined, notes}}. rank is a specific title within that hierarchy ("Leader", "Member", "Recruit", "Captain", "Elder", whatever the org actually uses) — "Leader of the Akatsuki" and "Member of the Akatsuki" must be genuinely different ranks on the same affiliation, not just different prose. status is active|honorary|probation|exiled|former. Always include the full current list of affiliations (not just the one that changed) when updating this field, the same way other list fields work. A character can hold multiple affiliations at once (e.g. a Konoha shinobi who is secretly also Root). This is distinct from reputation, which tracks how a faction feels about the player whether or not they're a member. When the player's most narratively important affiliation has a clear title, also reflect it in state_patch.position (e.g. "Leader of the Akatsuki") so it shows in their at-a-glance status badge.
- Companions have individual motives. Independent allies retain agency; established subordinates follow valid commands through their actual hierarchy. Refusal, departure or betrayal requires a prior causal basis, never a routine dramatic twist. Track scene participation in companions and personal facts in npc_memories; organizational membership is separate from proximity.
- life_context is application-owned continuity; never overwrite it. Use its world_terms and preserve established goals, relationships, upbringing, mentorships and standing care/training.
- Major life changes require causal evidence and world-valid prerequisites, never random elapsed-time drama. Honor pending choices; never decide the player's family, retirement, heir or reconciliation. Dependents develop only from what occurred.
- Before inventing a new named character to fill a role in a scene — a training partner, a mentor, a fellow member of a group the player belongs to — check whether npc_memories, companions, contacts, or a canon character's own established cast already has a real person who fits. A campaign that starts with a real, established cast (a canon character's actual companions and mentors, seeded into state at creation) should keep drawing on THOSE specific people by name, not quietly drift toward a generic invented substitute doing the same narrative job. BAD: the player is playing as a canon character with real, already-tracked companions, and the response has them training with an unnamed, invented training partner instead. GOOD: the response has them training with — or at least referencing — the actual companion already in npc_memories/companions.
- For groups in organization_context, emit organization_updates for membership, position and reporting-line changes; the application mirrors their accepted active membership into faction_rosters and affiliations. Invitations are not membership. Do not try to change these rosters merely by replacing companions or faction_rosters. Other known groups may still use state_patch.faction_rosters ({{"FactionName": ["Member1", "Member2"]}}); include the full roster when updating an entry. Never invent membership or remove someone for being elsewhere.
- Give every real companion a concrete personal goal in npc_memories[name].goal (and set recurring=true) as soon as they join, not only once the player happens to ask about it. This is what lets their own subplot advance and get reported even in scenes the player isn't part of — the application periodically checks each tracked goal's progress on its own and surfaces a turning point through the World Feed as independent movement, exactly like an NPC or faction clock. A companion with no tracked goal only ever exists when directly spoken to, which is the gap this closes.
- The same mechanism tracks major antagonists, not just companions. When a genuine long-arc canon villain (or a serious original one the campaign has produced) becomes relevant to the player's situation — not a one-scene mook, but someone whose scheme is meant to loom over a real stretch of the story — give them npc_memories[name].goal describing their actual scheme, set recurring=true, AND set nemesis=true. This nemesis flag makes their agenda build much more slowly than an ordinary NPC's (by design, so their threat spans a long arc rather than resolving in a few turns), and the player sees them called out distinctly in the Journal. Reserve nemesis=true for a genuinely major, recurring threat — not every rival or one-off enemy qualifies.
- Give important recurring NPCs layered motives when useful: immediate_goal (tracked now), mid_term_goal, core_ambition, loyalties, fears, secrets, and opinion_of_player. Let completed goals feed the next layer. Their choices follow those motives, their knowledge, and physical reach; never expose a secret merely because narrator state contains it. Most one-scene NPCs need only one goal.
- Read application-owned campaign_direction to keep its primary goal, obstacle, unresolved people, nearby opportunities, and canon pressure coherent. Never railroad the player or write this field in state_patch.
- npc_memories[name].status can become "deceased" on its own, set by the application when an off-screen faction/NPC conflict (see FACTION CONFLICT) resolves fatally against them. Treat this as real and permanent — never feature them alive again, and if they were a companion, contact, or otherwise meaningful to the player, address their loss in the narrative (word of their death reaching the player through a plausible channel) rather than silently dropping them.
- Everything tracked about NPCs so far is player-centric — but named NPCs have relationships with EACH OTHER independent of the player, and those matter for the same reason a companion's own goal does: the world should keep moving even in scenes the player isn't part of. Whenever a scene actually establishes or changes how two named NPCs relate to each other (allies, rivals, family, mentor/student, a grudge, a romance, a business tie, whatever the fiction produced), record it in state_patch.npc_relationships keyed "NameA::NameB" (alphabetical order) as {{a, b, type, strength (-100 hostile to 100 close), status: active|broken|severed|estranged, note: a short line on what it is and why}}. Don't backfill this exhaustively for every possible pair — only for relationships a scene has actually shown or that canon already establishes and is relevant to the current situation.
- This is a real, checkable fact about the world, not flavor text: before narrating any canon-adjacent beat between two named NPCs, check npc_relationships for that pair first. If canon assumes a relationship (allies, rivals, family) that the player's actions have already changed, the divergence wins — narrate what actually follows from the tracked relationship and record it in canon_divergences, never quietly railroad the scene back to the original script because that's what canon says should happen.
- When a tracked rivalry, grudge, or enmity between two NPCs has genuinely built to the point of a real confrontation (not just tension), you can set it up as an ordinary GM-declared conflict exactly the same way a faction conflict works: give each side an npc_clocks entry with .opponent set to the other's name. That can end in a real, permanent outcome — including one side's defeat or death — the same as any other GM-declared conflict, so use it deliberately, not for every minor rivalry.
- Named canon characters whose fate is scripted to matter at a specific LATER point in this world's own timeline (someone who canonically needs to survive to play their real role — a future Hokage, a hero who hasn't had their arc yet, whoever this world's story still needs alive) must not be allowed to die prematurely to an off-screen conflict roll just because the dice went badly for them. Set npc_memories[name].canon_protected=true for these specific figures — a background/GM-declared conflict can still weaken, displace, or humiliate them, but the application will not let that conflict kill or destroy them outright while the flag is set. Reserve this for characters whose early death would actually break the setting's own premise, not everyone with a name — most canon characters don't need it, and the flag never protects them from anything the player does directly, only from the automated background-conflict resolver. This is separate from and doesn't relax the deliberate stakes described immediately above for a real, escalated confrontation the player caused or witnessed.
- Companions must not be purely reactive. When a companion is present and this turn's narrative has any natural opening, have at least one of them proactively start something — comment unprompted, ask the player a personal or tactical question, bring up their own goal or problem, react emotionally to what just happened, offer or request help, flirt, tease, disagree, or act on their own initiative in the scene — rather than only replying when addressed. A companion who has been idle in prose for several consecutive turns should be especially likely to initiate next. This is a standing behavioral expectation, not something that only applies when the player directly interacts with them.
- Ordinary player actions NEVER advance world_time, world_clock_minutes, or calendar. Time advances only through the dedicated Advance/Time Skip flow. Describe an action at the current moment and leave all clock/calendar fields untouched, even for travel, rest, training, crafting, waiting, or long actions; the player must press Advance to spend time. BAD: the player says "I spend the afternoon training" and state_patch.world_time moves from "Day 1 — Morning" to "Day 1 — Afternoon". GOOD: the same narrative describes the training, but world_time/world_clock_minutes/calendar stay exactly as they were in this state_patch.
- Record learned sublocations in location_details. For the current scene include sublocation, indoors, setting, weather and activity; never copy distant events into it.
- On control changes (including off-screen), update location_details[name].controlling_faction or political_regions in the same state_patch. BAD: narrative says "the village now answers to the rebels" without updating ownership. GOOD: set controlling_faction="Rebels". Routine mentions do not change control.
- A major event at one location should visibly ripple to the places genuinely connected to it (nearby, on its trade route, under the same faction) — refugees, disrupted trade driving prices up, patrols tightening, notable people relocating — not stay sealed inside the one location it happened at. Reflect this the same way as any other location update: state_patch.location_details[nearbyName].notes for what changed there, and location_details[nearbyName].danger_level (Calm|Uneasy|Tense|Critical, matching the player's own tension gauge) when the local danger genuinely shifted. Only touch locations a ripple would plausibly reach — don't cascade a local skirmish across the whole map.
- The map is not limited to canon locations — freely introduce an original place (a village, a hidden camp, a ruin, an island, an outpost) whenever the story naturally calls for one, exactly like any other original content. The moment the player or narration establishes a new named place worth remembering, add it to state_patch.custom_locations as {{"name": "...", "x": 0-100, "y": 0-100, "kind": "village|region|landmark|training|nation|dungeon|other", "tier": 1-10 prominence/danger}} so it actually appears on the interactive map, not just in prose. Place x/y sensibly relative to the world's existing geography — near the established locations it's actually described as being near, on the correct side of the map for its described direction/region, not a random point. Always include the full current list of custom_locations (not just the new one) when updating this field, the same as other list fields. Skip any name that would collide with an existing canon location.
- Land control updates location_details.controlling_faction and the full political_regions list; same owners merge. A player-founded landholding becomes a real polity with faction/clock, leadership and polity_state public feeling. Ruler commands work but NPCs may resist. Do not turn government into a visible spreadsheet: governance stays narrative; public shifts become one-line reports.
- Founded land needs real authority: begin at 1 hex; grow political_regions.hex_count narratively. Preserve id and exact location anchor; include board/realm for Bleach or Solo. Never move claims with the player. Whole transfers use scale country/nation/island; small holdings do not annex surrounding nations. Preset owners need no restating. Civil sovereignty differs from protection/influence: JJK schools do not own Japan.
- Canon dates never override campaign control. Naruto villages are not countries. One Piece location_details separates controlling_faction, sovereignty, local_authority and protection.
- recent_chat_context is history.
- companion_combinations require compatible powers, trust and practice; store use, limits and mastery.
- Propose keepsakes in trophy_proposals only; the player decides.
- Source unwitnessed news in-world. Use downtime_surprise_hint if fitting, never as filler.
- Ability evolution should arise from repeated use, training, insight, conditions, vows, class mechanics or world-appropriate breakthroughs.
- Important recurring people, allies, rivals, employers, teammates, faction representatives, and groups the player meaningfully meets should be saved into contacts when lore permits future communication.
- Communications must use lore-appropriate means. A "chat" can mean phone/text, guild chat, system DM, messenger bird, courier, letter, Den Den Mushi, radio, telepathy, or other setting-appropriate medium.
- Contacts are not omnipresent. Distance, access, relationship, danger, technology, secrecy, and availability matter.
- Long time skips must simulate the entire interval according to standing_orders and prior actions rather than simply jumping to a desired result.
- During time skips, the player's last explicit orders continue until completed, interrupted, impossible, or changed by conditions.
- When the player's own words name an explicit condition to wait for — "wait until the attack," "hold this position until she returns," "stay here until nightfall," "watch the road until someone comes" — that stated condition, not a generic notion of "something happens," is what the wait is actually FOR. On the turn the order is given, narrate only the moment of settling into it (per the no-time-advances rule above); on whichever later Advance/time skip actually plays out that wait, treat reaching or ruling out that specific named condition as the real governing outcome of the skip — take it seriously enough that it can be the whole point of the skip, not a background detail lost among other events. If the condition genuinely occurs within the time actually available, resolve it as the scene it deserves. If it does NOT occur within that time — the skip runs out, or the thing was never actually going to happen on this timeline — the narrative must say so plainly and in-world (the attack never came because it was called off, misreported, delayed by weather, aimed elsewhere, or whatever is actually true), never silently end the skip with the stated condition just unmentioned. BAD: player orders "I wait in a defensive perimeter until the attack," a skip plays out, and the response never mentions the attack at all. GOOD: either the attack genuinely happens and is resolved as the skip's real climax, or the narrative explicitly explains why it didn't come in this window ("Scouts confirm no force is moving on your position — whatever intelligence prompted the alert was wrong, or the attack has been called off for now").
- Focused training gives noticeable gains proportional to time and intensity. Only a tier leap needs a roll.
- A failed uncertain action must still change the situation. Prefer partial progress with a complication, lost time, exposure, a relationship consequence, a cost, or a newly revealed obstacle/lead. Never answer a failure with only "nothing happens," and never secretly turn a failed roll into full success.
- World events and canon timelines continue during skips unless prior player actions have changed them.
{canon_clock_block}
{combat_example_rule}

FINAL REMINDERS — the details most often missed under attention pressure earlier in this same list. Check these last, right before you finalize state_patch:
{("- If the narrative describes money changing hands, currency.amount changed in this state_patch." if ex.get("tracks_currency", True) else "- Money remains narrative-only in this world: do not write currency, currencies, prices, recurring_finances, or purchase_offer into state_patch.")}
- If the narrative describes the player taking a real wound, hp decreased in this state_patch.
- If the narrative declares a quest/delivery/task finished, that quest's status is "complete" in this state_patch.
- Return ONLY valid JSON. No markdown fences."""
