"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, math, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, format_calendar_date
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view, sync_active_portrait_form
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from reliability import update_narrative_memory, record_progression_ledger, advance_hidden_class_discovery
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, ai_text
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks, uses_literal_quests,
                     quest_presentation_for, ensure_currency_state,
                     currency_balance, record_currency_transaction,
                     record_finance_debt)
from simulation import (deterministic_assessment, prioritize_updates,
                        advance_npc_intentions, record_simulation_events,
                        agency_bypasses_check, explicit_world_method,
                        player_favoring_difficulty)
from world_depth import normalize_world_depth, record_canon_ripples, record_downtime
from director import (build_cause_effect, ensure_productive_failures,
                      maybe_offer_relationship_scene, update_campaign_direction)
from simulation_integrity import (parse_action_goals, register_action_goals,
                                  reconcile_action_goals, travel_plan_for_actions,
                                  validate_turn_response, refresh_npc_schedules,
                                  transmit_information, canon_dependency_graph)
from lit_systems import process_lit_turn
from jjk_system import advance_jjk_state
from standing_intents import (advance_standing_intents, player_training_directives,
                              register_standing_intents, standing_intent_context)
from simulation_core import refresh_simulation_core, record_resolution_transaction, action_commits_violence
from canon_integrity import repair_canon_payload
from world_activity import advance_world_activity
from world_progression import normalize_world_progression
from age_system import advance_character_age
from campaign_features import downtime_surprise_prompt
from simulation_enhancements import (
    normalize_dated_updates, advance_companion_autonomy,
    advance_npc_development, record_ability_evolution,
    world_downtime_events, reactive_communication,
)
from campaign_reliability import (
    reconcile_narrated_consequences, consolidate_long_campaign_memory,
    refresh_scene_state, normalize_outcome_scale, reconcile_commitments_and_consequences,
    refresh_canon_divergence_impacts, record_pacing_beat,
)
from response_guard import normalize_assessment_response
from experience_systems import record_world_milestones, update_scenario_memory
from long_campaign import (compact_checkpoint_state, pre_advance_health_check,
                           sync_standing_order_lifecycle)
from gm_policy import (
    parse_player_intent, progression_plan, record_causal_outcome,
    temporal_budget,
)
from life_simulation import advance as advance_life_simulation


# The minimum in-game time a single "next major event" click is allowed to
# consume before its claimed stop is honored — see run_time_skip's event_mode
# branch.
EVENT_STEP_FLOOR_MINUTES = 1440

# Broad, rigorous combat blocks improve the whole fighting foundation on
# player-favoring difficulties. Nightmare intentionally keeps the old
# single-stat progression behavior.
WORLD_COMBAT_FOUNDATIONS = {
    "One Piece": ["Strength", "Agility", "Endurance", "Instinct", "Willpower"],
    "Hunter x Hunter": ["Strength", "Agility", "Aura Control", "Willpower"],
    "Naruto": ["Taijutsu", "Ninjutsu", "Chakra Control", "Willpower"],
    "Solo Max-Level Newbie": ["Strength", "Dexterity", "Constitution", "Wisdom"],
    "Overgeared": ["Strength", "Dexterity", "Constitution", "Wisdom"],
    "Reincarnated as a Slime": ["Instinct", "Magicule Control", "Skill Mastery", "Willpower"],
    "Bleach": ["Zanjutsu", "Hoho", "Reiatsu Control", "Willpower"],
    "Custom World": ["Strength", "Dexterity", "Constitution", "Willpower"],
}
WORLD_TRAINING_SYNERGIES = {
    "Naruto": {
        "Ninjutsu": {"Chakra Control": .28, "Willpower": .12, "Intellect": .10},
        "Taijutsu": {"Willpower": .24, "Chakra Control": .12, "Intellect": .08},
        "Genjutsu": {"Intellect": .28, "Chakra Control": .24, "Willpower": .10},
        "Chakra Control": {"Ninjutsu": .22, "Genjutsu": .12, "Willpower": .10},
        "Willpower": {"Taijutsu": .14, "Chakra Control": .14, "Ninjutsu": .08},
        "Intellect": {"Genjutsu": .18, "Chakra Control": .12, "Ninjutsu": .08},
    },
    "One Piece": {
        "Strength": {"Endurance": .24, "Agility": .12},
        "Agility": {"Instinct": .22, "Endurance": .12},
        "Instinct": {"Agility": .20, "Willpower": .12},
        "Willpower": {"Endurance": .16, "Instinct": .12},
    },
    "Hunter x Hunter": {
        "Aura Control": {"Willpower": .24, "Cunning": .12},
        "Strength": {"Agility": .16, "Willpower": .12},
        "Agility": {"Strength": .12, "Cunning": .14},
        "Cunning": {"Aura Control": .14, "Willpower": .10},
    },
    "Bleach": {
        "Zanjutsu": {"Hoho": .18, "Reiatsu Control": .16, "Willpower": .10},
        "Hoho": {"Zanjutsu": .14, "Reiatsu Control": .12},
        "Kido": {"Reiatsu Control": .28, "Willpower": .12},
        "Reiatsu Control": {"Kido": .18, "Willpower": .12},
    },
}
BROAD_TRAINING_RE = re.compile(
    r"\b(rigorous|comprehensive|all[- ]around|combat training|combat drills|every combat|"
    r"all combat|train(?:ing)? (?:myself|my body|all|every)|conditioning regimen)\b", re.I)
PLAIN_TRAINING_RE = re.compile(
    r"^\s*(?:i\s+)?(?:just\s+)?(?:train|practice|work\s*out)(?:\s+(?:hard|intensely|rigorously|"
    r"every\s+day|daily))?[.!]*\s*$", re.I)

WORLD_TRAINING_STAT_HINTS = {
    "Naruto": {
        "Chakra Control": r"\b(chakra control|precision|precise|sensor|sensing|medical|concentration|chakra threads?)\b",
        "Genjutsu": r"\b(genjutsu|illusion|mental interference|mind technique)\b",
        "Ninjutsu": r"\b(ninjutsu|jutsu|nature transformation|elemental|chakra technique)\b",
        "Taijutsu": r"\b(taijutsu|hand[- ]to[- ]hand|martial|melee|punch|kick|body conditioning)\b",
        "Intellect": r"\b(study|research|theory|tactic|strategy|formula|sealing theory)\b",
        "Willpower": r"\b(meditat|resolve|endurance of pain|mental discipline)\b",
    },
    "Bleach": {
        "Kido": r"\b(kid[ōo]|had[ōo]|bakud[ōo]|incantation|spell)\b",
        "Reiatsu Control": r"\b(reiatsu control|reiryoku control|spiritual pressure|energy control|precision)\b",
        "Zanjutsu": r"\b(zanjutsu|sword|blade|zanpakut[ōo])\b",
        "Hakuda": r"\b(hakuda|unarmed|hand[- ]to[- ]hand|martial)\b",
        "Hoho": r"\b(hoh[ōo]|shunpo|flash step|footwork|speed)\b",
    },
    "Overgeared": {
        "Dexterity": r"\b(craft|forge|smith|sew|engrave|precision|production)\b",
        "Intelligence": r"\b(design|research|study|analy[sz]e|spell|theory)\b",
        "Strength": r"\b(strength|lifting|strike|heavy weapon|power)\b",
        "Constitution": r"\b(endurance|stamina|conditioning|surviv)\b",
    },
    "Solo Max-Level Newbie": {
        "Dexterity": r"\b(dexterity|agility|speed|footwork|precision|trap)\b",
        "Intelligence": r"\b(intelligence|research|study|spell|magic|analy[sz]e)\b",
        "Wisdom": r"\b(wisdom|perception|sense|strategy|tactic|judgment)\b",
        "Strength": r"\b(strength|power|strike|melee|weapon)\b",
        "Constitution": r"\b(constitution|endurance|stamina|conditioning|surviv)\b",
    },
}

# These are accelerators, not prerequisites. A detailed player-authored method
# always helps on player-favoring difficulties; particularly effective methods
# that actually exist in the selected setting can support extraordinary growth.
WORLD_ACCELERATED_TRAINING_METHODS = {
    "Naruto": (
        (re.compile(r"\bshadow clone|kage bunshin\b", re.I), 4.5, "parallel shadow-clone experience"),
        (re.compile(r"\bsage training|natural energy|mount myoboku\b", re.I), 3.0, "sage-method training"),
        (re.compile(r"\bseal(?:ed)? training (?:room|space)|time dilation\b", re.I), 3.5, "time-compressed seal training"),
    ),
    "One Piece": (
        (re.compile(r"\bhaki-coated|haki mentor|rayleigh|near-death battle\b", re.I), 2.8, "high-pressure Haki development"),
        (re.compile(r"\bseastone|kairoseki\b", re.I), 2.2, "seastone resistance training"),
    ),
    "Hunter x Hunter": (
        (re.compile(r"\bnen vow|restriction and covenant|risk my life\b", re.I), 3.2, "a binding Nen condition"),
        (re.compile(r"\bbiscuit|bisky|nen master\b", re.I), 2.2, "expert Nen instruction"),
    ),
    "Bleach": (
        (re.compile(r"\bdangai|time-compressed|inner world\b", re.I), 3.5, "time-compressed spiritual training"),
        (re.compile(r"\bzanpakuto spirit|bankai method\b", re.I), 2.5, "direct Zanpakuto communion"),
    ),
    "Solo Max-Level Newbie": (
        (re.compile(r"\bhidden dungeon|experience multiplier|system exploit\b", re.I), 3.0, "a system-recognized accelerated route"),
    ),
    "Overgeared": (
        (re.compile(r"\bhidden quest|legendary class|production mastery\b", re.I), 2.5, "a class-aligned mastery route"),
    ),
    "Reincarnated as a Slime": (
        (re.compile(r"\bskill synthesis|predator|great sage|raphael|magicule-rich\b", re.I), 3.0, "skill-assisted accelerated development"),
    ),
}
AMBITIOUS_TRAINING_RE = re.compile(
    r"\b(astronomical|exponential|massive|enormous|rapid(?:ly)?|huge leap|breakthrough|"
    r"master|perfect|transcend|kage[- ]level|jonin[- ]level|yonko[- ]level|captain[- ]level)\b", re.I)

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



# Canon-timeline data always uses each hidden village's Japanese name
# ("Konohagakure"), but the narrator and the player routinely use the
# common English alias instead ("Leaf Village", "the Hidden Leaf") — the two
# share no substring, so a plain fuzzy match misses what is obviously the
# same place. Grouped so _same_place can treat any alias in a group as
# equivalent to any other.
_LOCATION_ALIAS_GROUPS = [
    {"konohagakure", "leaf village", "hidden leaf", "the leaf", "konoha"},
    {"sunagakure", "sand village", "hidden sand", "suna"},
    {"kirigakure", "mist village", "hidden mist", "kiri"},
    {"kumogakure", "cloud village", "hidden cloud", "kumo"},
    {"iwagakure", "stone village", "hidden stone", "iwa"},
    {"amegakure", "rain village", "hidden rain", "ame"},
    {"otogakure", "sound village", "hidden sound", "oto"},
    {"land of fire", "fire country"},
    {"land of wind", "wind country"},
    {"land of water", "water country"},
    {"land of lightning", "lightning country"},
    {"land of earth", "earth country"},
]


# Words that mark an order as reaching for a genuinely new capability
# ("learn Haki", "master the technique", "unlock my bloodline") rather than
# routine practice of something the character already has — see
# _check_power_goal_progress.
_POWER_GOAL_KEYWORDS = ("learn", "master", "unlock", "awaken", "achieve", "obtain", "attain")


class TimeSkipMixin:
    def _infer_training_ability(self, action, current_stats):
        """Map named techniques to the stat their actual mechanics use."""
        text = str(action or "")
        lowered = text.lower()
        for skill_name, detail in (self.state.get("skills", {}) or {}).items():
            if str(skill_name).lower() not in lowered:
                continue
            if isinstance(detail, dict):
                text += " " + " ".join(
                    ai_text(detail.get(key)) for key in
                    ("description", "effect", "growth_path", "limitation", "kind")
                    if ai_text(detail.get(key))
                )
            else:
                text += " " + ai_text(detail)
        scores = {}
        for stat, pattern in WORLD_TRAINING_STAT_HINTS.get(self.state.get("world"), {}).items():
            if stat not in current_stats:
                continue
            matches = re.findall(pattern, text, re.I)
            if matches:
                scores[stat] = len(matches)
        if not scores:
            return None
        return max(scores, key=lambda stat: (scores[stat], -list(current_stats).index(stat)))

    @staticmethod
    def _same_place(player_location, event_location):
        """Fuzzy same-place check used to force a canon-event interruption
        when the player is obviously right where it's happening, rather than
        leaving that obvious case to model compliance alone (see canon_stop
        handling in run_time_skip)."""
        a, b = str(player_location or "").strip().lower(), str(event_location or "").strip().lower()
        if not a or not b:
            return False
        a_core = re.split(r"[—,-]", a)[0].strip()
        b_core = re.split(r"[—,-]", b)[0].strip()
        if not a_core or not b_core:
            return False
        if a_core == b_core or a_core in b_core or b_core in a_core:
            return True
        for group in _LOCATION_ALIAS_GROUPS:
            if (any(alias in a_core or a_core in alias for alias in group)
                    and any(alias in b_core or b_core in alias for alias in group)):
                return True
        return False

    def _event_action_prompt(self, event):
        """Fallback when a narrator recognizes presence but omits the
        requested position-aware next decision."""
        event = event if isinstance(event, dict) else {}
        name = self.state.get("name") or "the player"
        title = event.get("title") or "this major event"
        location = self.state.get("location") or event.get("location") or "their current position"
        position = self.state.get("position") or "their present role"
        return (f"What does {name} do from {location}, given their current standing as {position}, "
                f"as {title} reaches the part of the situation they can actually affect?")

    def _event_notice_payload(self, data, canon_stop=None):
        """Deterministic, display-only context for the informational event sheet.

        The narrator still owns the prose and intervention prompt. These rows
        are calculated locally so the notice cannot forget the player's real
        location, claim they teleported into a distant event, or spend another
        AI call merely formatting facts the game already tracks.
        """
        canon_stop = canon_stop if isinstance(canon_stop, dict) else {}
        world = self.state.get("world", "Custom World")
        player_location = str(self.state.get("location") or "Unknown")
        event_location = str(canon_stop.get("location") or data.get("major_event_location") or "Unknown")
        same_place = self._same_place(player_location, event_location)

        nodes = list(WORLD_DATA.get(world, {}).get("map", []) or [])
        for entry in self.state.get("custom_locations", []) or []:
            if isinstance(entry, dict) and entry.get("name"):
                nodes.append((entry.get("name"), entry.get("x", 50), entry.get("y", 50), entry.get("kind", "landmark"), entry.get("tier", 1)))

        def find_node(location):
            return next((node for node in nodes if self._same_place(location, node[0])), None)

        travel_time = "Already in the event area" if same_place else "Requires travel from the current location"
        start, destination = find_node(player_location), find_node(event_location)
        if not same_place and start and destination:
            distance = math.dist((float(start[1]), float(start[2])), (float(destination[1]), float(destination[2])))
            scale = float(progression_preset_for(world).get("travel_scale", 1.0) or 1.0)
            minutes = max(30, int(round(distance * 38 * scale + max(0, int(destination[4] or 1) - 1) * 12)))
            if minutes < 120:
                travel_time = f"About {max(30, int(round(minutes / 15) * 15))} minutes by an ordinary route"
            elif minutes < 1440:
                travel_time = f"About {max(1, round(minutes / 60))} hours by an ordinary route"
            else:
                days = max(1, round(minutes / 1440, 1))
                travel_time = f"About {days:g} days by an ordinary route"

        combat_active = bool(isinstance(self.state.get("combat"), dict) and self.state.get("combat", {}).get("active"))
        if combat_active:
            involvement = "Direct: combat has already begun"
        elif same_place:
            involvement = "Direct: the event has reached your current area"
        elif data.get("interrupted"):
            involvement = "Indirect but actionable: your ties, authority, or access give you a meaningful response"
        else:
            involvement = "Indirect: information and access are limited by distance"

        scene_state = copy.deepcopy(self.state)
        if data.get("active_major_event"):
            scene_state["active_canon_event"] = data.get("active_major_event")
        scene_image, _ = scene_image_url(scene_state)
        return {
            "title": str(data.get("major_event_title") or canon_stop.get("title") or "Major event"),
            "location": event_location,
            "player_location": player_location,
            "travel_time": travel_time,
            "involvement": involvement,
            "scope": str(canon_stop.get("scope") or data.get("major_event_scope") or "personal"),
            "canon_day": int(canon_stop.get("canon_day", self.state.get("canon_day", 0)) or 0),
            "scene_image": scene_image or "",
        }

    @staticmethod
    def _power_goal_chance(days_invested):
        """Two checkpoints, matching what sustained commitment should
        realistically buy: ~80% after a month (30 days) of continuous
        focused effort toward the SAME stated goal, guaranteed after one
        further week (37 days). Ramps linearly toward each rather than
        jumping, so a shorter but still real attempt has a real, smaller
        shot instead of an all-or-nothing cliff at exactly day 30."""
        if days_invested <= 0:
            return 0.0
        if days_invested <= 30:
            return 0.8 * (days_invested / 30)
        if days_invested <= 37:
            return 0.8 + 0.2 * ((days_invested - 30) / 7)
        return 1.0

    def _check_power_goal_progress(self, orders, requested_days, roll_results=None):
        """Mechanically pushes an explicitly-stated power/ability goal
        toward success the longer the player stays committed to that exact
        goal, rather than leaving a full month of stated focused effort
        entirely to a model that tends to under-reward it as unrealistic.
        Tracked by the goal's own text (not the model's own judgment of
        whether it's "the same goal"), so accumulation survives even if a
        turn's response never mentions continuity explicitly. Only ever
        pushes toward success — see the resolve_time_skip requirement that
        reads this — never away from it."""
        keyword_order = next((o for o in orders if any(k in str(o).lower() for k in _POWER_GOAL_KEYWORDS)), None)
        if not keyword_order or requested_days <= 0:
            return None
        key = re.sub(r"\s+", " ", str(keyword_order).strip().lower())
        tracker = self.state.get("power_goal_tracker")
        if not isinstance(tracker, dict) or tracker.get("key") != key:
            tracker = {"key": key, "days_invested": 0.0}
        tracker["days_invested"] = float(tracker.get("days_invested", 0) or 0) + requested_days
        self.state["power_goal_tracker"] = tracker
        chance = self._power_goal_chance(tracker["days_invested"])
        matching_roll = next((row for row in (roll_results or []) if isinstance(row, dict)
                              and row.get("major_event") and str(row.get("action") or "").strip().lower() == key), None)
        planned_method = explicit_world_method(keyword_order)
        favoring_mode = player_favoring_difficulty(self.state)
        # A player who supplies a real in-world route on a lower difficulty
        # is promising a progression story, not requesting repeated permission
        # to progress. The thresholds are intentionally generous while still
        # giving the fiction enough elapsed time to show the work.
        assured_days = {"Story": 3, "Adventurer": 7, "Veteran": 14}.get(
            self.state.get("difficulty"), 37
        )
        assured_success = bool(
            favoring_mode and planned_method and tracker["days_invested"] >= assured_days
        )
        mechanical_success = (
            assured_success or
            (bool(matching_roll.get("success")) if matching_roll else random.random() < chance)
        )
        return {"order": keyword_order, "days_invested": round(tracker["days_invested"], 1), "chance": round(chance, 3),
                "mechanical_success": mechanical_success, "roll_based": bool(matching_roll),
                "planned_method": planned_method, "assured_by_agency_policy": assured_success,
                "assured_days": assured_days if favoring_mode and planned_method else None,
                "roll_total": matching_roll.get("total") if matching_roll else None,
                "roll_difficulty": matching_roll.get("difficulty") if matching_roll else None}

    @staticmethod
    def estimate_action_minutes(action):
        text = str(action).lower()
        if any(k in text for k in ("sleep", "overnight", "full rest")): return 480
        if any(k in text for k in ("train", "practice", "study", "research", "craft", "forge")): return 60
        if any(k in text for k in ("travel", "journey", "sail", "cross the", "climb")): return 90
        if any(k in text for k in ("fight", "duel", "battle", "hunt")): return 30
        if any(k in text for k in ("buy", "sell", "shop", "ask around", "interview")): return 15
        if any(k in text for k in ("talk", "speak", "question", "eat")): return 10
        if any(k in text for k in ("look", "inspect", "check", "read")): return 5
        return 15

    def time_budget(self, amount, unit, orders):
        available = max(1, self.duration_minutes(amount, unit))
        estimates = [{"action": action, "estimated_minutes": self.estimate_action_minutes(action)} for action in orders]
        used, reachable, deferred = 0, [], []
        for item in estimates:
            if used + item["estimated_minutes"] <= available:
                reachable.append(item["action"]); used += item["estimated_minutes"]
            else:
                deferred.append(item["action"])
        total = sum(x["estimated_minutes"] for x in estimates)
        ratio = available / max(1, total)
        modifier = 0 if ratio >= 1 else 2 if ratio >= .75 else 3 if ratio >= .5 else 5 if ratio >= .25 else 8
        return {"available_minutes": available, "estimated_minutes": total, "estimated_actions": estimates,
                "time_ratio": round(ratio, 3), "time_dc_modifier": modifier,
                "reachable_actions": reachable, "deferred_actions": deferred}

    def assess_time_skip(self, amount, unit, orders_text, intensity, use_model=True):
        from naruto_tactics import require_narrative_available
        require_narrative_available(self.state)
        pre_advance_health_check(self.state, source="before_time_assessment")
        event_mode = unit == "next_event"
        if unit in {"moment", "next_event"}:
            amount = 1
        if isinstance(orders_text, list):
            clean_orders = [str(x).strip(" •\t") for x in orders_text if str(x).strip(" •\t")]
        else:
            clean_orders = [x.strip(" •\t") for x in str(orders_text or "").splitlines() if x.strip(" •\t")]
        queued = list(self.state.get("queued_actions", []))
        clean_orders = queued + [x for x in clean_orders if x not in queued]
        continuing_previous_orders = False
        if not clean_orders:
            clean_orders = [str(x).strip() for x in self.state.get("standing_orders", []) if str(x).strip()]
            continuing_previous_orders = bool(clean_orders)
        standing_orders = list(clean_orders)
        structured_goals = parse_action_goals(clean_orders, self.state.get("turn", 0))
        travel_plans = travel_plan_for_actions(self.state, clean_orders)
        moment_deferred = []
        if unit == "moment" and len(clean_orders) > 1:
            moment_deferred = clean_orders[1:]
            clean_orders = clean_orders[:1]
        if event_mode:
            horizon_minutes = 180 * 1440
            canon_stop = self.next_canon_stop(horizon_minutes, "minutes")
            available_minutes = canon_stop["minutes_until"] if canon_stop else horizon_minutes
            budget = self.time_budget(available_minutes, "minutes", clean_orders)
            budget.update({"event_driven_major": True, "max_elapsed_minutes": available_minutes,
                           "safety_horizon_days": 180})
        else:
            canon_stop = None
            budget = self.time_budget(24, "hours", clean_orders) if unit == "moment" else self.time_budget(amount, unit, clean_orders)
        if unit == "moment":
            budget.update({"event_driven_moment": True, "max_elapsed_minutes": 1440,
                           "deferred_actions": moment_deferred + [x for x in budget.get("deferred_actions", []) if x not in moment_deferred]})
        if not event_mode:
            canon_stop = self.next_canon_stop(24, "hours") if unit == "moment" else self.next_canon_stop(amount, unit)
        if canon_stop:
            budget["requested_minutes"] = budget["available_minutes"]
            budget["available_minutes"] = canon_stop["minutes_until"]
            budget["canon_stop"] = canon_stop
        budget["travel_plans"] = travel_plans
        budget["structured_goals"] = structured_goals
        with self.lock:
            self.state["standing_orders"] = standing_orders
            sync_standing_order_lifecycle(self.state, standing_orders, source="time_assessment")
            self.state["time_mode"] = unit
            self.checkpoints.append(compact_checkpoint_state(self.state))
            self.checkpoints = self.checkpoints[-12:]
        payload = {
            "task": "assess_time_skip", "duration": {"amount": amount, "unit": unit},
            "planned_actions": clean_orders, "intensity": intensity, "state": self.trimmed_state_for_ai(" ".join(clean_orders)),
            "time_budget": budget, "continuing_previous_orders": continuing_previous_orders,
            "requirements": [
                "On Nightmare, create a d100 check only for an extremely difficult/seemingly impossible attempt, lethal undertaking, or major power-tier leap. On every lower difficulty, a diplomatic action or a specifically explained setting-valid method receives no arbitrary check unless a literal world-rule contradiction or lethal danger remains.",
                "Ordinary political, strategic, social, investigative, travel, crafting, and focused training actions receive no check and accomplish their plausible player-controlled objective; challenge comes from concrete NPC/faction/world responses.",
                "Do not roll any dice yourself.",
                "Routine or long repetitive training receives no roll. Nightmare retains major checks for extraordinary power leaps. Below Nightmare, a named effect plus a plausible in-world training method progresses automatically and completes once the allocated time is sufficient.",
                "Treat planned_actions as an ordered itinerary. Carry them out in listed order across the available duration; do not flatten them into one repeated activity.",
                "Compare the concrete time_budget against the itinerary. Insufficient time makes rushed attempts harder and leaves later actions deferred rather than magically completed.",
                "Apply time_difficulty_modifier to checks affected by rushing. If an action cannot even begin in sequence, list it in deferred_actions and create no roll for it.",
                "If continuing_previous_orders is true, treat these as ongoing standing instructions and continue them naturally rather than restarting them from zero.",
                "If the list is truly empty, advance the world naturally without forcing a character action; NPCs, factions, travel, rumors, markets and scheduled pressures still move.",
                "When time_budget.event_driven_moment is true, assess only the single next immediate meaningful story beat. That beat may plausibly consume minutes or several hours, but never more than 24 hours. Do not resolve later queued actions in the same moment.",
                "When time_budget.event_driven_major is true, assess the standing plan across the horizon until the earliest major personal development or major canon event — a genuine tier-of-power change, transformation, or class/form change, a real battle, a world-changing event, or a major canon event, and nothing smaller. An ordinary stat or skill increase is NOT enough by itself, no matter how large the number — only stop for a stat/power change when it actually pushes the character into a different tier of power altogether. Routine beats (conversations, small skirmishes, incremental gains, rumors, errands) are updates, not stopping points, no matter how many of them occur across the horizon. The eventual major event ends naturally without asking whether to intervene. EXCEPTION: if planned_actions itself names an explicit wait condition (\"wait until the attack,\" \"hold until she returns,\" \"watch until someone comes\"), that named condition IS the stopping point for this skip, overriding the generic taxonomy above even if it wouldn't otherwise qualify as major — the player was explicit about what they're waiting for, so honor exactly that instead of substituting a different, bigger event. If the named condition doesn't plausibly occur within the available horizon, say so explicitly in the resulting narrative rather than silently stopping for something else.",
                "Difficulty ranges follow world lore and what is realistic for an average relevant character at this time; never scale them to the player.",
                "Mark major_event for every evolution, transformation, climactic confrontation or irreversible major turning point so the player rolls manually.",
                "Extreme schedules can cause injury, burnout, resource depletion, or death if genuinely plausible; flag lethal checks.",
                "If any planned_action explicitly aims to acquire, unlock, or master a significant new power, ability, technique, or tier of strength for this world (not routine stat/skill practice — a genuine capability the character does not have yet), set power_jump_warning to one short in-character sentence, spoken the way a mentor, elder, or the world's own lore would frame it — never a system/meta voice, never mention percentages, mechanics, or 'this game'. It should read as real in-world foreshadowing (a warning about the cost or weight of such power, or a promise that sustained dedication can genuinely get them there), not a UI disclaimer wearing a costume."
            ],
            "schema": {
                "checks": [{"id": "short id", "action_index": "zero-based planned_actions index", "reason": "under 10 words", "ability": self.ability_enum(), "skill": "name or null", "difficulty_min": "1-100 contextual lower edge", "difficulty_max": "1-100 contextual upper edge", "relevant_average_stat": "average relevant world-relative stat", "situational_bonus": "-20 to 20", "time_difficulty_modifier": "0-25 from time pressure", "major_event": "bool", "major_reason": "short reason or empty", "lethal_risk": "none|low|moderate|high|extreme", "lethal_warning": "warning or empty, under 20 words"}],
                "fixed_facts": "under 30 words",
                "simulation_notes": "under 30 words", "reachable_actions": "ordered list",
                "deferred_actions": "ordered actions that cannot be reached in the allotted time",
                "power_jump_warning": "one in-character sentence per the requirement above, or empty if nothing planned reaches for a new power/ability"
            }
        }
        rules = self.task_context("time_plan", " ".join(clean_orders))
        # Production UI requests use the deterministic planner so a normal
        # Advance spends one model call on the actual story, not a second
        # planning prompt. ``use_model=True`` remains for direct/legacy
        # engine integrations and comparison tests.
        assessment = normalize_assessment_response(
            self.ai.request(rules, payload, max_output_tokens=700) if use_model
            else deterministic_assessment(self.state, clean_orders, budget, self.simulation_mode())
        )
        assessment.setdefault("time_budget", budget)
        if canon_stop:
            assessment["canon_stop"] = canon_stop
        assessment.setdefault("reachable_actions", budget["reachable_actions"])
        assessment.setdefault("deferred_actions", budget["deferred_actions"])
        assessment["structured_goals"] = structured_goals
        assessment["travel_plans"] = travel_plans
        assessment["standing_plan"] = standing_orders
        assessment["continuing_previous_orders"] = continuing_previous_orders
        if moment_deferred:
            authored_deferred = assessment.get("deferred_actions") if isinstance(assessment.get("deferred_actions"), list) else []
            assessment["deferred_actions"] = moment_deferred + [x for x in authored_deferred if x not in moment_deferred]
        checks = assessment.get("checks", []) if isinstance(assessment.get("checks"), list) else []
        if player_favoring_difficulty(self.state):
            retained_checks = []
            for check_index, check in enumerate(checks):
                if not isinstance(check, dict):
                    continue
                try:
                    authored_index = int(check.get("action_index", check_index))
                except (TypeError, ValueError):
                    authored_index = check_index
                authored_index = max(0, min(authored_index, max(0, len(clean_orders) - 1)))
                authored_action = clean_orders[authored_index] if clean_orders else str(check.get("reason") or "")
                if agency_bypasses_check(self.state, authored_action, check):
                    continue
                retained_checks.append(check)
            checks = retained_checks
            assessment["checks"] = checks
        previews = []
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                continue
            try:
                action_index = int(check.get("action_index", index))
            except (TypeError, ValueError):
                action_index = index
            action_index = max(0, min(action_index, max(0, len(clean_orders) - 1)))
            check["action_index"] = action_index
            action = clean_orders[action_index] if clean_orders else ""
            previews.append(self.preview_check(check, assessment, action))
        assessment["check_previews"] = previews
        # A confrontation receives one blocking danger warning, not one for
        # every difficult beat inside it.  Checks still roll normally after
        # the acknowledgement; only the repeated confirmation gate is
        # suppressed.  A newly lethal action is never suppressed and will be
        # routed through the explicit death-risk confirmation below.
        warned_scenario = self.danger_scenario_active()
        for preview in previews:
            risk = str(preview.get("risk") or "none").lower()
            preview["warning_suppressed"] = bool(
                warned_scenario and preview.get("difficult") and risk not in {"high", "extreme"}
            )
        assessment["danger_scenario_active"] = warned_scenario
        assessment["difficult_checks"] = [
            preview for preview in previews
            if preview.get("difficult") and not preview.get("warning_suppressed")
        ]
        assessment["requires_difficulty_confirmation"] = bool(assessment["difficult_checks"])
        return {"assessment": assessment, "amount": amount, "unit": unit, "orders": clean_orders, "intensity": intensity,
                "time_budget": budget}

    def run_time_skip(self, amount, unit, orders, intensity, assessment, confirmed_lethal=False, confirmed_power_goal=False, manual_rolls=None, challenge_modes=None, challenge_resolution_mode="continue", danger_warning_acknowledged=False):
        if isinstance(self.state.get('combat'),dict) and self.state['combat'].get('active') and self.state['combat'].get('adventure_objective'):
            raise ValueError('Resolve the active tactical objective before advancing campaign time.')
        from naruto_tactics import require_narrative_available
        require_narrative_available(self.state)
        assessment = assessment if isinstance(assessment, dict) else {}
        event_mode = unit == "next_event"
        if unit in {"moment", "next_event"}:
            amount = 1
        checks = [row for row in (assessment.get("checks", []) or []) if isinstance(row, dict)]
        canon_stop = assessment.get("canon_stop") if isinstance(assessment.get("canon_stop"), dict) else None
        moment_mode = unit == "moment"
        event_horizon = int(assessment.get("time_budget", {}).get("max_elapsed_minutes", 180 * 1440) or 180 * 1440)
        simulation_amount = canon_stop.get("minutes_until", 0) if canon_stop else (event_horizon if event_mode else 1440 if moment_mode else amount)
        simulation_unit = "minutes" if canon_stop or moment_mode or event_mode else unit
        for chk in checks:
            if chk.get("lethal_risk") in ("high", "extreme") and not confirmed_lethal:
                return {"status": "lethal_confirm_required", "check": chk}
        if assessment.get("power_jump_warning") and not confirmed_power_goal:
            return {"status": "power_goal_confirm_required", "warning": assessment["power_jump_warning"]}
        manual_rolls = manual_rolls if isinstance(manual_rolls, dict) else {}
        challenge_modes = challenge_modes if isinstance(challenge_modes, dict) else {}
        challenge_resolution_mode = "stop" if challenge_resolution_mode == "stop" and challenge_modes else "continue"
        for chk in checks:
            check_id = str(chk.get("id") or chk.get("reason") or "major")
            if chk.get("major_event") and check_id not in manual_rolls:
                return {"status": "manual_roll_required", "check": chk, "check_id": check_id,
                        "theme": self.state.get("world", "Custom World")}
        active_goals = register_action_goals(self.state, orders)
        intent_registration = register_standing_intents(self.state, orders)
        projected_intent_minutes = self.duration_minutes(simulation_amount, simulation_unit)
        persistent_intents = standing_intent_context(self.state, projected_intent_minutes)
        # A "moment" is exactly one action (see assess_time_skip's truncation)
        # — this is the live path every single normal turn actually resolves
        # through, so the action's own Chronicle line belongs here, with any
        # roll for it attaching right underneath (see appendStoryEntries).
        # Deliberately placed AFTER both early-return gates above: a lethal
        # or major-event check re-enters this same function on the SAME
        # orders once the player confirms/rolls, and appending here first
        # would otherwise write the player's action line to the Chronicle
        # once per gate hit — twice over, for the exact same single action.
        if moment_mode and orders:
            self.append("> " + str(orders[0]), "player")
        results = []
        for check_index, chk in enumerate(checks):
            normalized = copy.deepcopy(chk)
            try:
                action_index = int(chk.get("action_index", check_index))
            except (TypeError, ValueError):
                action_index = check_index
            action_index = max(0, min(action_index, max(0, len(orders) - 1)))
            action_label = orders[action_index] if orders else chk.get("reason", "Time-skip milestone")
            normalized["action"] = action_label
            time_modifier = int(chk.get("time_difficulty_modifier", 0) or 0)
            if not time_modifier:
                time_modifier = int(chk.get("time_dc_modifier", assessment.get("time_budget", {}).get("time_dc_modifier", 0)) or 0) * 3
            if normalized.get("difficulty_min") is not None: normalized["difficulty_min"] = int(normalized["difficulty_min"]) + time_modifier
            if normalized.get("difficulty_max") is not None: normalized["difficulty_max"] = int(normalized["difficulty_max"]) + time_modifier
            check_id = str(chk.get("id") or chk.get("reason") or "major")
            res = self.roll(normalized, manual_rolls.get(check_id) if check_id in manual_rolls else None)
            res.update({"id": chk.get("id"), "reason": chk.get("reason"), "action_index": action_index,
                        "action": action_label, "major_event": bool(chk.get("major_event")),
                        "time_difficulty_modifier": time_modifier, "challenge_mode": challenge_modes.get(check_id, "")})
            results.append(res)
            breakdown = self.format_bonus_breakdown(res.get("bonus_breakdown"))
            roll_detail = f"Action: {action_label}" + (f" · {breakdown}" if breakdown else "")
            self.append(self.format_roll_summary(action_label, res), "roll", detail=roll_detail)

        # A month of genuinely stated, sustained commitment to one explicit
        # power/ability goal ("train until I learn Haki") kept reading as a
        # near-miss or partial result far more often than not — a model
        # left entirely to its own judgment tends to under-reward "realism"
        # over the player actually getting the power fantasy they asked
        # for. This mechanically pushes toward success as accumulated,
        # continuous days on the SAME stated goal cross real thresholds,
        # rather than leaving it purely to narrative taste — but only ever
        # pushes toward success, never away from it, and only for plain
        # explicit-duration skips (not moment/event/canon-interrupted ones,
        # where "how many days was this" isn't a clean question).
        power_goal = None
        if not moment_mode and not event_mode and not canon_stop:
            power_goal = self._check_power_goal_progress(orders, self.duration_minutes(amount, unit) / 1440.0, results)
        downtime_hint = downtime_surprise_prompt(
            self.state, self.duration_minutes(simulation_amount, simulation_unit), orders
        )

        payload = {
            "task": "resolve_time_skip", "duration": {"amount": simulation_amount, "unit": simulation_unit},
            "original_requested_duration": {"amount": amount, "unit": unit}, "planned_actions": orders,
            "intent_contracts": [parse_player_intent(row, self.state) for row in orders],
            "temporal_budget": temporal_budget("time_skip", simulation_amount, simulation_unit),
            "progression_plan": progression_plan(
                self.state, orders, self.duration_minutes(simulation_amount, simulation_unit), intensity,
            ),
            "standing_plan": assessment.get("standing_plan", orders),
            "continuing_previous_orders": bool(assessment.get("continuing_previous_orders")),
            "intensity": intensity, "assessment": assessment, "dice_results": results,
            "state_before": self.task_state_for_ai("time_skip", " ".join(str(x) for x in orders or [])),
            "simulation_profile": self.simulation_profile(),
            "structured_action_goals": active_goals,
            "persistent_intents": persistent_intents,
            "authoritative_travel_plans": assessment.get("travel_plans", []),
            "moment_mode": {"enabled": moment_mode, "max_elapsed_minutes": 1440, "instruction": "Resolve only the next immediate meaningful beat"},
            "live_event_scene": bool(moment_mode and self.state.get("active_canon_event")),
            "active_event_context": self.state.get("active_event_context", ""),
            "active_event_prompt": self.state.get("active_event_prompt", ""),
            "danger_scenario": self.state.get("danger_scenario", {}),
            "challenge_resolution_mode": challenge_resolution_mode,
            "next_major_event_mode": {"enabled": event_mode, "max_elapsed_minutes": event_horizon,
                "canon_boundary": canon_stop or {},
                "instruction": "Continue through routine beats and stop ONLY at the earliest genuinely major personal development or the canon boundary — see the requirements below for exactly what qualifies. End naturally; never ask whether the player intervenes."},
            "power_goal_progress": power_goal or {},
            "downtime_surprise_hint": downtime_hint or {},
            "requirements": [
                "Simulate the ENTIRE skipped period, not just its ending scene.",
                "Any period longer than a single moment should cover several distinct notable beats/events spread across the timespan (e.g. across a day: morning training, an afternoon encounter, an evening development), not one flattened event. Only moment-to-moment turns focus on a single thing at a time.",
                "When moment_mode.enabled is true, resolve exactly one immediate meaningful story beat based on current context and the first active action. standing_plan contains the complete ongoing itinerary: preserve its later instructions as deferred work instead of forgetting them or pretending the player abandoned them. Let the beat consume a believable amount of time—even several hours—but never more than 24 hours, then stop at the next decision point.",
                "When live_event_scene is true, the player is personally living through a major canon event through the NORMAL Chronicle and Action Chat, one beat at a time — there is no separate event chat. Use active_event_context and active_event_prompt to keep their exact position, distance, involvement, status and access grounded. Write immediate, present, moment-to-moment sensory experience, react directly to what the player chose, and end at a genuine situation-specific fork. Do not force a check merely because the event is important; reserve checks for the rare extreme/impossible actions that actually warrant them.",
                "danger_scenario records that the player already received and accepted the current confrontation's danger warning. While it is active, continue moment-to-moment without manufacturing another danger decision or permission prompt for each difficult move. Only introduce a new warning when the new action itself creates a credible risk of the character dying. Set danger_scenario_concluded=true once the confrontation is genuinely over or the player successfully leaves it.",
                "When challenge_resolution_mode is 'stop', use the supplied minigame rolls to resolve ONLY the challenged action or obstacle and stop immediately after its outcome, at the first point where the player can take control again. Do not continue through the rest of the originally requested time. Return the believable time actually consumed, set interrupted=true with interruption_kind='challenge_complete', and keep every later or unfinished planned action in deferred_actions. When it is 'continue', incorporate the same minigame result and continue simulating toward the originally requested endpoint unless another legitimate stop condition is reached.",
                "When next_major_event_mode.enabled is true, keep simulating through routine decisions and include clear chronological updates, but do not stop for ordinary prompts. The bar for stopping is deliberately high — this mode exists to skip PAST the small stuff and run until the intended goal is reached or the available time fully elapses, not pause partway through for anything less. Stop ONLY when something on this scale actually happens: the character moving into a genuinely different tier of power (not just a stat/skill increase — an actual breakthrough, transformation, or class/form change), a real battle or life-threatening confrontation, a world-changing event (a war, disaster, regime change, a faction destroyed or founded), or a major canon timeline event. A defining goal being fully completed also qualifies. None of the following are ever, by themselves, a reason to stop — narrate them as an ordinary update and keep going: a routine conversation or social call, a minor non-lethal scuffle or scare, an ordinary stat tick or incremental skill/level gain (even a large one, as long as it's the same tier of power as before), a passing rumor or piece of news, a small transaction or errand, meeting or running into someone without real stakes, or anything that would read as one line in a history feed rather than a headline. If you are genuinely unsure whether something clears this bar, it does not — keep simulating past it, all the way to the requested goal or the end of the available time, whichever comes first. Return no intervention_prompt and do not ask Yes/No.",
                "Present world updates with information fog: distinguish what objectively changed, why it matters, and what the character can actually know through witnesses, messages, evidence, travel time, or rumor. The world is not omniscient and information never teleports.",
                "Treat structured_action_goals as authoritative stop conditions. Report the matching action verbatim in goal_status.action so the local tracker can close the correct goal.",
                "Treat authoritative_travel_plans as the physical route and minimum ordinary travel time. Do not move the player farther than the elapsed time permits unless an already-established instant-travel power is actually used.",
                "Respect canon_dependency_graph. When an earlier cause became impossible, do not replay its downstream canon beat unchanged; delay it, replace its cause, or record the event as impossible through canon_divergences.",
                "NPC schedules are commitments, not flavor. A character cannot attend two incompatible places at once, and a missed or due commitment must have a visible consequence.",
                "When information reaches named NPCs, add a concise information_events record with its fact, source, channel, recipients, delay, and confidence. Do not teach an NPC a fact merely because the narrator knows it.",
                "Treat the player as one actor inside an independently moving world, not as its automatic protagonist. Keep the current simulation scale grounded in the character's actual reach while still advancing distant NPC and faction agendas.",
                "The player's planned actions are an ordered itinerary: attempt each in sequence and distribute the available time sensibly.",
                "Below Nightmare, accomplish every logically possible player-controlled action. Diplomacy and strategy may end in straightforward agreement, cooperation or progress. Use conditions, counteroffers, obligations, suspicion, countermoves or betrayal only when a specific informed NPC/faction motive or established conflict causes them. NPCs retain their canon motives and may still reject an ultimate demand in character after the player's move meaningfully lands.",
                "Never complete a deferred action. If time expires during an action, describe partial progress and keep the unfinished or unstarted action in deferred_actions.",
                "Training intensity must affect gains, fatigue, injury risk, resources, and sustainability.",
                ("Respect travel times, sleep, recovery, food, healing, social obligations, faction responses, lore, and world chronology. Bleach uses narrative supply access—rank, authorization, favors, requisitions and availability—instead of tracking money." if self.state.get("world") == "Bleach" else "Respect travel times, sleep, recovery, money, food, healing, social obligations, faction responses, lore, and world chronology."),
                "Use supplied dice results exactly for uncertain milestones.",
                ("If an action begins or accepts a quest/mission/job/contract, give a complete readable briefing and add a structured active quest: name, giver/cause, objective, known location, known risks, first actionable step, current knowledge, and clear completion conditions. Keep literal objective progress synchronized with events."
                 if uses_literal_quests(self.state.get("world")) else
                 "If an action begins or accepts a mission, job, promise, investigation, or personal goal, establish a narrative Agenda entry with its situation, cause or commitment, current knowledge, relevant people and places, immediate pressures, developments, and a useful lead. Do not present a percentage, checklist, locked route, mandatory order, or fixed solution; alternate story-valid resolutions remain possible."),
                "Write skills in plain language with effect, use/activation, limitation or cost, and growth path; never expose raw arrays, internal identifiers, or calculation traces as descriptions.",
                "Advance NPCs, factions, canon events, quests, relationships, markets, wars, organizations, and rumors independently.",
                "Use simulation_profile as a hard detail budget. Fully resolve people and threads in state_before.simulation_context.detail_bubble; summarize distant actors unless their action crosses into the local scene or becomes a major event.",
                "This is the turn's one combined narration pass. Resolve the player itinerary, relevant NPC reactions, quests, canon pressure, and wider-world consequences together. Never request or assume a later narrator pass will repair omissions.",
                "Return no more than simulation_profile.max_updates update cards. Keep every major reaction distinct, but combine routine distant movement into one concise wider-world update instead of repeating the same development through quests, leads, clocks, advisor language, and world feed.",
                "Generate meaningful world movement on EVERY Advance, including turns with no new player action or turns that merely continue standing orders. Significant personal story beats and major world events are hard stop points. If one reaches the player's actual position or reasonably requires their decision, stop there and return a concrete, in-character intervention_prompt for the normal Chronicle/Action Chat.",
                "Prior player actions and promises continue affecting outcomes.",
                "persistent_intents are durable background outcomes, duties, policies and routines already ordered by the player. Treat them as continuously in force without making the player repeat them. Preserve the intended outcome rather than mechanically repeating the original sentence. Reflect routine maintenance silently; mention it only when it causes a meaningful result, milestone, obstacle, interruption or consequence.",
                "A delegated persistent intent does not consume the player's whole turn. Its responsible NPCs or organization continue it off-screen when able. A personal routine uses a believable share of the player's schedule alongside other actions.",
                "If a persistent intent becomes temporarily impossible, completed, cancelled by circumstances, or permanently impossible, return a standing_intent_updates entry. Temporary obstacles pause rather than erase the instruction; resume it when circumstances allow.",
                "Care and protection intents preserve ordinary food, shelter, supervision, healing and safety arrangements when available. Training/education intents accumulate across the full elapsed period; use teacher quality, talent, age, resources, health and interruptions, and only narrate meaningful development rather than a repetitive daily report.",
                "If power_goal_progress.order is present and power_goal_progress.mechanical_success is true, conclude with the character genuinely gaining that power/ability. This may be an agency-assured result rather than a roll. Give a concrete lore-consistent cause grounded in accumulated training, set goal_status.achieved=true, and persist the capability. If it is false, award substantial foundation/proficiency; mention a failed roll only when roll_based is true, otherwise explain that the elapsed time has not yet reached the supplied route's next concrete milestone.",
                "If an interruption is important enough that the player would reasonably stop and choose what to do, end the skip EARLY and return interrupted=true with the amount of time actually elapsed.",
                "Treat action wording such as 'until', 'master', 'learn', 'find', 'reach', 'finish', 'complete', or another clear result as a goal condition. If that goal is achieved before the requested duration ends, stop immediately on the day/minute of completion, set goal_status.achieved=true, and return only the actual elapsed time.",
                "If a stated goal is not achieved by the end of the requested duration, set goal_status.achieved=false and explain the concrete in-world cause: insufficient insight, teacher/resources, injury, interruption, failed milestone, difficulty, or another setting-valid reason. Include a useful next_hint grounded in what the character learned.",
                "If assessment.canon_stop exists, simulate only through that stop boundary and do not grant progress, travel, recovery or consequences from time after it.",
                "When stopping at canon_boundary/assessment.canon_stop specifically, decide plausible involvement in exactly two steps, in order. STEP 1 — check the player's own current status: location, travel time from the event, rank/standing, and any established affiliation with its participants. STEP 2 — check the event's own scale: canon_stop.scope is 'wide' when the event affects an entire location/population (a village under attack, a war, a public ceremony) and 'personal' when it's a small-cast incident that merely happens to be tagged with a village-level location for convenience (most of them). Only a wide-scope event lets simply being in the same broad location justify presence; for a personal-scope event, sharing that location proves nothing. If both steps support involvement, set interrupted=true and write intervention_prompt as the SPECIFIC immediate decision the character actually faces from their real vantage — never a generic Yes/No 'intervene?' question. Account for distance, access, affiliation, rank, duty, knowledge, event scale and whether they are central, peripheral, caught in public fallout, or only observing. Otherwise set interrupted=false, leave intervention_prompt empty, and deliver only what could plausibly reach them as a report, rumor, messenger account or documentation (often nothing for a secret personal event). Never ask a prompt of a player who could not possibly be there. A wide event can catch an ordinary person in public chaos without teleporting them into a private named-character confrontation; only an established tie or duty can put them in that private room. Default to the report or nothing whenever presence is not clearly established.",
                "For uninterrupted training, treat every training day/session as real accumulated practice; a month is roughly 30 daily sessions, never one generic reward.",
                "In non-System worlds do not award XP or levels. Show progress through open-ended stats, knowledge, techniques, ranks and titles. Use XP only if state._uses_xp is true.",
                "Every breakthrough result requires a concrete lore-based cause and a substantially larger but world-valid gain.",
                "Record all meaningful changes mechanically."
                ,"Return separate chronological updates for every queued action that begins, every major reaction by an NPC/faction/world system, every interruption, and every major consequence. Do not combine unrelated reactions into one paragraph.",
                "Each update should be decently detailed: normally 2-5 sentences covering the action and its direct result. Include a reaction, consequence or unresolved pressure only when it actually exists and has a concrete causal basis; never add one merely to fill an update template.",
                "Give every update its own canon_day so multi-day skips read as a dated sequence of beats, not one undated blob — like a history feed, not a single diary entry. A single day may reasonably contain more than one update when multiple things happen.",
                "Bold the proper names of every character, faction, and named location the first time each appears within an update's narrative (e.g. **Kaito Moriyama**, **Hueco Mundo**), the way a wiki or timeline entry would — this is for readability, not emphasis of importance.",
                "Fill in each update's map_changes only on the rare beat that actually shifts who controls a territory/settlement/map node, and quote only on the rare beat with a real, attributable spoken line worth surfacing on its own — both are empty on most updates, and forcing either in when nothing warrants it is worse than leaving them empty.",
                "If simulating this period reaches real physical danger, stop the skip so it cannot be silently auto-resolved. If violence has NOT started and negotiation, retreat or another response is still genuinely possible, stop immediately before it and write a concrete intervention_prompt for the character's actual options. If the player initiated a real fight, or an attacker has already committed to violence with no meaningful chance to negotiate, do NOT add another permission/intervention choice: begin structured combat immediately in state_patch.combat, set interrupted=true and interruption_kind='danger', narrate the opening clash, and give a combat-grounded prompt. The normal combat panel is the next interaction surface."
                ,"End at a clear decision point. Preserve or reveal at least one actionable journey lead and return exactly 3 optional suggested actions grounded in current knowledge."
            ],
            "schema": {
                "narrative": "brief overall summary used only as fallback", "updates": [{"sequence":"number", "type":"action|npc_reaction|faction_reaction|world_event|canon_event|interruption|consequence", "title":"specific short heading", "canon_day":"integer canon day this beat occurred on", "related_action":"queued action or empty", "narrative":"2-5 substantive sentences, proper nouns bolded with **double asterisks** on first mention", "why_it_matters":"one short plain sentence on the stakes, phrased the way a narrator would actually say it out loud, not a labeled report line", "player_knowledge":"one short plain sentence on what the character can verify, infer, or only heard as rumor, phrased the same natural way, or empty if nothing new", "next_pressure":"one short plain sentence naming the unresolved pressure, phrased the same natural way, or empty", "map_changes": "empty list unless this SPECIFIC beat changed who controls/holds a territory, settlement, or map node — then a short list of what changed, e.g. 'The Empire of the End gains control of the Rift Node'. Most beats have none.", "quote": "empty unless this beat naturally includes one short, genuinely quotable spoken line — then {\"text\": the line, \"speaker\": who said it}. Use sparingly, only when a line actually lands; never invent dialogue just to fill this in."}], "state_patch": "ALL persistent changes",
                "consequence_manifest": [{"kind":"skill|title|item|quest|location|condition|reputation|affiliation|other", "target":"exact name", "change":"gained|lost|started|completed|changed", "evidence":"short sentence identifying the beat", "details":"complete skill mechanics only when kind is skill"}],
                "commitment_updates": [{"owner":"who made the promise/debt", "owed_to":"who expects it", "promise":"specific commitment", "due_canon_day":"integer or empty", "trigger":"condition or empty", "status":"active|fulfilled|broken|cancelled", "consequence":"what follows if relevant"}],
                "delayed_consequences": [{"effect":"specific later consequence", "source":"decision/event causing it", "horizon":"days|weeks|months|conditional", "due_canon_day":"integer or empty", "trigger":"condition or empty"}],
                "causal_outcome": {"direct_result":"overall accomplishment before reactions", "witnesses":["actual witnesses or information channels"], "reactions":[{"actor":"named informed person/faction", "response":"causal response", "knowledge_source":"witness|conversation|message|report|rumor|research|ability"}], "costs":[{"cost":"real cost", "cause":"why it was paid"}], "complications":[{"effect":"supported setback", "cause":"specific established cause"}]},
                "events": "system notifications", "timeline_events": "list of major events",
                "elapsed": {"amount": "number", "unit": "same or sensible normalized unit"},
                "interrupted": "boolean", "interruption_kind": "canon_event|goal_complete|world_event|danger|other or empty", "interruption_reason": "string or empty",
                "danger_scenario_concluded": "boolean; true only when the current dangerous confrontation has ended or the player has left it",
                "interruption_context": "full context grounded in the player's distance, involvement, status, access and event scale", "intervention_prompt": "specific immediate in-character decision for the normal Chronicle; never generic Yes/No, or empty",
                "goal_status": {"action": "goal-bearing action or empty", "achieved": "boolean", "elapsed": {"amount": "number", "unit": "unit"}, "explanation": "in-world result or obstacle", "next_hint": "actionable hint when incomplete"},
                "major_event_reached": "boolean; required in next major event mode", "major_event_kind": "personal|canon|empty", "major_event_title": "specific title or empty",
                "active_major_event": "the EXACT title of a major canon event (matching one listed under UPCOMING CANON PRESSURES/CANON HISTORY) if this update is still directly part of that event's unfolding scene, or empty once it has concluded and the story has moved past it — this drives which banner art the player sees, so keep it set for as long as the scene is genuinely still that event and clear it the moment it resolves.",
                "new_contacts": "EVERY named character or group the player had a real, individual interaction with this update — talked to, fought, helped, was helped by, was noticed by, negotiated with, or was introduced to. Not just plot-important figures — a shopkeeper who remembers the player, a rival genin, a rank-and-file guard who let something slip. If they're worth naming in the update at all, they belong here with {name, kind: person|group}.",
                "incoming_chats": [{"thread": "contact/group", "sender": "sender", "message": "message"}],
                "ability_developments": [{"ability":"existing ability name", "kind":"application|mastery|breakthrough|evolution", "development":"specific lasting development", "application":"new named or practical application, or empty", "evidence":"what caused it"}]
                ,"information_events": [{"fact":"what was learned", "source":"who or what supplied it", "channel":"witness|conversation|letter|rumor|broadcast|ability|research", "recipients":["named recipients"], "delay_minutes":"nonnegative integer", "confidence":"0-100"}]
                ,"completed_actions": "ordered actions completed or meaningfully attempted",
                "deferred_actions": "unfinished/unstarted actions retained for the next Advance",
                "standing_intent_updates": [{"id":"exact persistent_intents id", "status":"active|temporarily_blocked|completed|cancelled|failed|impossible", "reason":"short in-world reason; omit unchanged intents"}],
                "world_plan_updates": "Optional commands following world_plan_context; omit unchanged plans.",
                "suggested_actions": ["exactly 3 concrete optional actions written as verb + target + purpose: strongest lead, growth/preparation, alternate hook. Each must name a SPECIFIC person, place, faction, item, or thread that actually exists in this campaign right now — never generic filler like 'look for rumors' or 'train' with no real target. Vary the scale honestly: one can be a single moment, another can openly span several days or a longer project ('spend the next few days...', 'seek out ... over the coming weeks') when that's genuinely what the lead calls for — don't force everything into an instant."]
            }
        }
        # The detailed behavior lives in task_rules("time_skip"). Keep only
        # per-request switches here instead of resending a second 40-item
        # rulebook inside the user payload on every Advance.
        payload["requirements"] = [
            "Honor planned_actions in order and retain every unfinished action in deferred_actions.",
            "Use the supplied assessment, travel plans, dice/minigame results, canon boundary, danger state and action goals exactly.",
            "Moment resolves one beat (maximum 24 hours); longer skips cover the whole allowed interval with dated chronological updates.",
            "Stop at the earliest achieved explicit goal, committed combat, significant personal decision, or supplied major/canon boundary.",
            "List every lasting narrated gain, loss, condition, quest, title, item, skill, affiliation or location change in consequence_manifest even when state_patch also contains it.",
            "Resolve any due obligation or delayed consequence whose trigger/date falls inside this interval; return new or changed promises in commitment_updates and later echoes in delayed_consequences.",
            "Next Major Event ignores routine conversations, errands, rumors and incremental growth; stop only for a real tier change, defining goal, lethal conflict, world-changing event or major canon event.",
            "Training gains scale with actual sessions, intensity, aptitude, instruction, resources and recovery; do not compress a month into one session.",
            "Return sparse JSON: omit empty optional fields, empty arrays and empty objects.",
        ]
        if downtime_hint:
            payload["requirements"].append(
                "This skip has a downtime_surprise_hint. Weave one optional, world-fitting personal surprise into the existing chronological updates if it naturally fits; do not make an extra AI pass and do not force it to become a major interruption."
            )
        multiplayer_context = getattr(self, "multiplayer_context", None)
        if isinstance(multiplayer_context, dict) and multiplayer_context.get("participants"):
            payload["multiplayer"] = copy.deepcopy(multiplayer_context)
            payload["requirements"].extend([
                "This is one shared multiplayer turn. Every planned action begins with its controlling character's name. Resolve each ready character as an independent protagonist; characters marked passes=true or connected=false take no deliberate action and must never repeat old standing orders.",
                "Tag every relevant update title or related_action with the acting character. Preserve one shared clock and world continuity even if the characters are in different scenes.",
                "Enforce information boundaries between player characters. A local/private scene is visible only to its actor and characters physically present at that location. A distant character learns it only through a modeled conversation, witness, letter, message, rumor, report, broadcast, research or established perception ability. Never make both players omniscient merely because they share a campaign.",
                "For EVERY update, return actor_user_id (or empty for a world-only event), the event location/sublocation, information_scope, delivery_channel and audience_user_ids using ONLY the exact supplied multiplayer user IDs. audience_user_ids must list every player who can perceive or has plausibly received that information, and nobody else. Use information_scope local/private for firsthand scenes, reported/rumor for delivered information, and shared/global only for events both genuinely know.",
                "If an interruption or decision point concerns only one separated character, list only that character in interruption_user_ids. The other player's simulation may stop on the shared clock but must not receive the hidden context or prompt.",
                "Return multiplayer_character_updates keyed by the supplied user_id. Include only that character's changed mechanical fields (stats, pools, status, location, skills, titles, inventory, equipment, special abilities, level/XP and activity); never put shared world facts there.",
            ])
            updates_schema = payload.setdefault("schema", {}).get("updates")
            if isinstance(updates_schema, list) and updates_schema and isinstance(updates_schema[0], dict):
                updates_schema[0].update({
                    "actor_user_id": "exact multiplayer user_id responsible/centered in this beat, or empty for a world-only event",
                    "location": "exact place where the beat occurs",
                    "sublocation": "room/district/site when known, or empty",
                    "information_scope": "private|local|reported|rumor|shared|global",
                    "delivery_channel": "firsthand|conversation|witness|letter|message|rumor|report|news|broadcast|ability|research",
                    "audience_user_ids": "exact supplied user IDs who can currently know this update",
                })
            payload.setdefault("schema", {})["multiplayer_character_updates"] = {
                "user_id": "changed character fields only; one object per participant"
            }
            payload["schema"]["interruption_user_ids"] = "exact supplied user IDs who personally receive the interruption context/prompt"
        use_major_model = bool(event_mode or canon_stop or any(bool(chk.get("major_event")) for chk in checks))
        narrator_client = self.ai_major if use_major_model and self.settings.get("major_event_model") else self.ai
        task = "major_event" if (event_mode or canon_stop) else ("moment" if moment_mode else "time_skip")
        max_tokens = 1400 if moment_mode else (2400 if task == "major_event" else 2200)
        request_args = (self.task_context(task, " ".join(str(x) for x in orders or [])), payload, max_tokens)
        # Preserve compatibility with test and plug-in sessions that override
        # request_with_narrative using the original three-argument signature.
        data = (self.request_with_narrative(*request_args, client=narrator_client)
                if narrator_client is not self.ai else self.request_with_narrative(*request_args))
        if canon_stop and not event_mode:
            data["elapsed"] = {"amount": canon_stop.get("minutes_until", 0), "unit": "minutes"}
            # Whether reaching this boundary becomes a real "will you personally
            # engage" moment or just a narrated report the player reads about
            # depends on whether they could plausibly be there. When the
            # player's own tracked location obviously matches the event's
            # location, that's hardcoded rather than left to model compliance
            # — a model has repeatedly proven unreliable at reliably noticing
            # this on its own, and this is exactly the kind of moment that
            # must actually be played out live, not silently summarized.
            # BUT: location alone only justifies that hardcode for a "wide"
            # scope event (a village under attack, a war, a public event) —
            # for anything else (the default, "personal": a small-cast
            # incident that happens to be tagged with a village-level
            # location for convenience) sharing that broad location proves
            # nothing. "Same village as Mizuki and Naruto that night" is not
            # "in the room when he steals the scroll." Check status/location
            # against the event's own scale first; only a wide-scope match
            # skips straight to forced presence.
            # Otherwise (a real judgment call — different location, travel
            # time, standing, or a personal-scope event regardless of
            # location) trust the narrator's own interrupted call, per the
            # gm_rules instruction. Defaulting to ABSENCE, not presence,
            # when the model leaves the field genuinely unset: a player who
            # was never established as being anywhere near a canon event has
            # no plausible way to attend it, and silently forcing them into
            # a live scene with named canon figures they were never actually
            # near is a worse failure than the reverse — a missed live scene
            # just reads as a report instead, which is what should happen by
            # default anyway for anyone not already involved.
            if canon_stop.get("scope") == "wide" and self._same_place(self.state.get("location"), canon_stop.get("location")):
                player_present = True
            else:
                player_present = bool(data.get("interrupted")) if isinstance(data.get("interrupted"), bool) else False
            data["interrupted"] = player_present
            if player_present:
                data["interruption_kind"] = "canon_event"
                data["interruption_reason"] = data.get("interruption_reason") or f"Major canon event reached: {canon_stop.get('title', 'Timeline event')}."
                data["interruption_context"] = (data.get("interruption_context") or
                    f"{canon_stop.get('title', 'Timeline event')} is unfolding at {canon_stop.get('location', 'an unknown location')}. "
                    f"{canon_stop.get('summary', 'The situation has reached a point where the player may intervene.')}")
                data["intervention_prompt"] = (data.get("intervention_prompt") or
                    self._event_action_prompt(canon_stop))
                # Hardcoded, not left to model compliance: the banner art for
                # a major event the player is actually present for must show
                # while it's unfolding, matching interrupted=True exactly.
                data["active_major_event"] = canon_stop.get("title", "")
            else:
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
                data["interruption_context"] = ""
                data["intervention_prompt"] = ""
        elif event_mode:
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_minutes = self.duration_minutes(elapsed.get("amount", 0), elapsed.get("unit", "minutes"))
            # A model that reports a suspiciously tiny elapsed time for a claimed
            # "major personal event" turns this mode into pausing every few
            # minutes of simulated time instead of skipping ahead meaningfully —
            # which also silently starves any real canon event further out from
            # ever being reached, since each click only closes a sliver of the
            # remaining distance. Floor the accepted elapsed time to at least a
            # day (or the exact canon boundary, if that's actually closer) so
            # real forward progress happens on every single call regardless of
            # how eager the model is to call something major.
            min_event_step = min(EVENT_STEP_FLOOR_MINUTES, canon_stop["minutes_until"]) if canon_stop else EVENT_STEP_FLOOR_MINUTES
            personal_stop = bool(data.get("major_event_reached")) and data.get("major_event_kind") == "personal" and min_event_step <= elapsed_minutes < simulation_amount
            if personal_stop:
                data["elapsed"] = {"amount": elapsed_minutes, "unit": "minutes"}
                stop_title = str(data.get("major_event_title") or "Major personal development")
                stop_kind = "personal"
            elif canon_stop:
                data["elapsed"] = {"amount": canon_stop.get("minutes_until", simulation_amount), "unit": "minutes"}
                stop_title = canon_stop.get("title", "Major canon event")
                stop_kind = "canon"
            else:
                safe_elapsed = elapsed_minutes if min_event_step <= elapsed_minutes <= event_horizon else event_horizon
                data["elapsed"] = {"amount": safe_elapsed, "unit": "minutes"}
                stop_title = str(data.get("major_event_title") or "Major personal turning point")
                stop_kind = str(data.get("major_event_kind") or "personal")
            data["major_event_reached"] = True
            data["major_event_kind"] = stop_kind
            data["major_event_title"] = stop_title
            # "Skip to next major event" existing to save time narrating routine
            # beats between now and the goal doesn't mean a real canon-timeline
            # event the player is actually standing in the middle of should be
            # flattened into a plain report — it deserves the same live scene
            # (banner art, "take part" vs "let it play out") that reaching the
            # same boundary via a normal multi-day skip already gets, via the
            # canon_stop-and-not-event_mode branch above. A personal
            # development never gets this treatment either way, per this
            # mode's own "never ask whether the player intervenes" contract.
            player_present = False
            if stop_kind == "canon" and canon_stop:
                # Same reasoning as the canon_stop-and-not-event_mode branch
                # above: only a wide-scope event lets shared location alone
                # force presence; everything else defaults to absence when
                # the model leaves this unset.
                if canon_stop.get("scope") == "wide" and self._same_place(self.state.get("location"), canon_stop.get("location")):
                    player_present = True
                else:
                    player_present = bool(data.get("interrupted")) if isinstance(data.get("interrupted"), bool) else False
            data["interrupted"] = player_present
            if player_present:
                data["interruption_kind"] = "canon_event"
                data["interruption_reason"] = data.get("interruption_reason") or f"Major canon event reached: {canon_stop.get('title', 'Timeline event')}."
                data["interruption_context"] = (data.get("interruption_context") or
                    f"{canon_stop.get('title', 'Timeline event')} is unfolding at {canon_stop.get('location', 'an unknown location')}. "
                    f"{canon_stop.get('summary', 'The situation has reached a point where the player may intervene.')}")
                data["intervention_prompt"] = (data.get("intervention_prompt") or
                    self._event_action_prompt(canon_stop))
                data["active_major_event"] = canon_stop.get("title", "")
            else:
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
                data["interruption_context"] = ""
                data["intervention_prompt"] = ""
                # Only add the flat "reached this and stopped" note when there
                # isn't already a full interactive scene covering the same
                # event — otherwise the player sees this note, the intervention
                # banner, AND the [MAJOR CANON EVENT] chronicle entry all for
                # the same single moment.
                if not isinstance(data.get("updates"), list): data["updates"] = []
                data["updates"].append({"sequence": 9998, "type": "canon_event" if stop_kind == "canon" else "consequence",
                    "title": f"Major Event Reached — {stop_title}", "related_action": "",
                    "narrative": "The advance stops here naturally, at the next real turning point for the campaign — decide how your character responds before time moves again.",
                    "why_it_matters": "", "player_knowledge": "", "next_pressure": ""})
        if challenge_resolution_mode == "stop" and not data.get("interrupted"):
            challenged_indices = []
            for index, check in enumerate(checks):
                check_id = str(check.get("id") or check.get("reason") or "major")
                if check_id not in challenge_modes:
                    continue
                try:
                    challenged_indices.append(int(check.get("action_index", index)))
                except (TypeError, ValueError):
                    challenged_indices.append(index)
            stop_index = max(0, min(challenged_indices or [0]))
            later_actions = orders[stop_index + 1:] if orders else []
            existing_deferred = data.get("deferred_actions") if isinstance(data.get("deferred_actions"), list) else []
            data["deferred_actions"] = list(dict.fromkeys([*existing_deferred, *later_actions]))
            data["completed_actions"] = [action for action in data.get("completed_actions", []) if action in orders[:stop_index + 1]]
            data["interrupted"] = True
            data["interruption_kind"] = "challenge_complete"
            data["interruption_reason"] = data.get("interruption_reason") or "The challenged result has been resolved. The remaining simulation is paused."
            data["interruption_context"] = data.get("interruption_context") or "The minigame result is now part of the story, but no later queued action or unused portion of the requested skip has been simulated."
            data["intervention_prompt"] = data.get("intervention_prompt") or f"What does {self.state.get('name') or 'the player'} do next?"
        goal_status = data.get("goal_status") if isinstance(data.get("goal_status"), dict) else {}
        if not goal_status and active_goals and not moment_mode:
            goal = active_goals[0]
            goal_action = ai_text(goal.get("action") or (orders[0] if orders else "the stated goal"))
            condition = ai_text(goal.get("condition") or goal_action)
            stopped_early = bool(canon_stop or data.get("interrupted"))
            if stopped_early:
                explanation = f"The interruption ended the available work before {condition} could be completed."
                next_hint = f"Handle the immediate interruption, then resume: {goal_action}"
            else:
                explanation = f"The available time ended without confirming that {condition} was complete."
                next_hint = f"Continue with a focused method, teacher, or resource aimed at: {condition}"
            goal_status = data["goal_status"] = {
                "action": goal_action, "achieved": False,
                "elapsed": copy.deepcopy(data.get("elapsed") or {"amount": amount, "unit": unit}),
                "explanation": explanation, "next_hint": next_hint,
            }
        if goal_status.get("achieved"):
            goal_elapsed = goal_status.get("elapsed") if isinstance(goal_status.get("elapsed"), dict) else {}
            if goal_elapsed.get("amount") is not None and goal_elapsed.get("unit"):
                data["elapsed"] = goal_elapsed
            effective_elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            achieved_minutes = self.duration_minutes(effective_elapsed.get("amount", 0), effective_elapsed.get("unit", "minutes"))
            requested_minutes = self.duration_minutes(amount, unit)
            if event_mode:
                data["major_event_reached"] = True
                data["major_event_kind"] = "personal"
                data["major_event_title"] = data.get("major_event_title") or "Defining goal completed"
                data["interrupted"] = False
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
            elif requested_minutes > 0 and achieved_minutes >= requested_minutes:
                # Completing the exact work requested at the natural end of
                # its allotted time is a successful time skip, not an
                # interruption. Reserve the interruption card for genuine
                # early stops where unused time remains.
                data["interrupted"] = False
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
                data["interruption_context"] = ""
                data["intervention_prompt"] = ""
            else:
                data["interrupted"] = True
                data["interruption_kind"] = data.get("interruption_kind") or "goal_complete"
                data["interruption_reason"] = data.get("interruption_reason") or goal_status.get("explanation") or "The stated goal was achieved early."
        elif goal_status and goal_status.get("action"):
            explanation = str(goal_status.get("explanation") or "The goal was not completed within the available time.").strip()
            next_hint = str(goal_status.get("next_hint") or "Review the obstacle and choose a more focused next step.").strip()
            if not isinstance(data.get("updates"), list): data["updates"] = []
            if not isinstance(data.get("suggested_actions"), list): data["suggested_actions"] = []
            data["updates"].append({"sequence": 9990, "type": "consequence", "title": "Goal not yet complete",
                                    "related_action": goal_status.get("action"),
                                    "narrative": f"{explanation} Next lead: {next_hint}"})
            data["suggested_actions"].insert(0, next_hint)
        if moment_mode:
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_minutes = self.duration_minutes(elapsed.get("amount", 0), elapsed.get("unit", "minutes"))
            if elapsed_minutes <= 0:
                elapsed_minutes = min(1440, self.estimate_action_minutes(orders[0]) if orders else 5)
            data["elapsed"] = {"amount": min(1440, elapsed_minutes), "unit": "minutes"}
        authored_deferred = data.get("deferred_actions") if isinstance(data.get("deferred_actions"), list) else []
        assessed_deferred = assessment.get("deferred_actions") if isinstance(assessment.get("deferred_actions"), list) else []
        completed = set(ai_text(x) for x in data.get("completed_actions", []) if ai_text(x))
        # Assessment is the authoritative time-budget gate. The narrator may
        # add deferrals, but it cannot silently erase actions the planning pass
        # already proved were unreachable (especially later Moment actions).
        data["deferred_actions"] = list(dict.fromkeys(
            ai_text(x) for x in [*authored_deferred, *assessed_deferred]
            if ai_text(x) and ai_text(x) not in completed
        ))
        combat_was_active = bool(isinstance(self.state.get("combat"), dict) and self.state.get("combat", {}).get("active"))
        data["danger_warning_acknowledged"] = bool(danger_warning_acknowledged and self.dangerous_plan(orders, checks))
        self.ensure_immediate_combat_patch(data, orders)
        combat_patch = data.get("state_patch", {}).get("combat", {}) if isinstance(data.get("state_patch"), dict) else {}
        combat_begins = not combat_was_active and isinstance(combat_patch, dict) and bool(combat_patch.get("active"))
        if combat_begins:
            data["interrupted"] = True
            data["interruption_kind"] = "danger"
            enemy = combat_patch.get("enemy")
            enemy_name = str(enemy.get("name") or "the opposition") if isinstance(enemy, dict) else str(enemy or "the opposition")
            data["interruption_reason"] = data.get("interruption_reason") or f"Combat has begun against {enemy_name}."
            data["interruption_context"] = data.get("interruption_context") or "Violence is already under way; there is no extra intervention decision between this opening clash and combat control."
            data["intervention_prompt"] = data.get("intervention_prompt") or f"How does {self.state.get('name') or 'the player'} handle the opening exchange with {enemy_name}?"
            fight_index = next((index for index, order in enumerate(orders)
                                if self._FIGHT_START_RE.search(str(order))
                                and action_commits_violence(order)
                                and not self._FIGHT_NEGATION_RE.search(str(order))), None)
            if fight_index is not None:
                opening_result = next((row for row in results if isinstance(row, dict)
                                       and (row.get("action_index") == fight_index
                                            or ai_text(row.get("action")).lower() == ai_text(orders[fight_index]).lower())), None)
                if opening_result:
                    combat_patch["opening_check"] = {
                        "success": bool(opening_result.get("success")),
                        "roll": int(opening_result.get("roll", 0) or 0),
                        "total": int(opening_result.get("total", 0) or 0),
                        "difficulty": int(opening_result.get("difficulty", 0) or 0),
                        "margin": max(0, int(opening_result.get("total", 0) or 0) - int(opening_result.get("difficulty", 0) or 0)),
                        "ability": ai_text(opening_result.get("ability")),
                        "breakthrough": bool(opening_result.get("breakthrough")),
                    }
                # An explicit queued attack begins when its place in the
                # itinerary is reached; it cannot be followed by the rest of
                # a week/month skip before the player sees combat controls.
                elapsed_cap = max(1, sum(self.estimate_action_minutes(order) for order in orders[:fight_index + 1]))
                elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
                authored_minutes = self.duration_minutes(elapsed.get("amount", elapsed_cap), elapsed.get("unit", "minutes"))
                data["elapsed"] = {"amount": min(max(1, authored_minutes), elapsed_cap), "unit": "minutes"}
                data["deferred_actions"] = list(dict.fromkeys([*data.get("deferred_actions", []), *orders[fight_index + 1:]]))
                data["completed_actions"] = [action for action in data.get("completed_actions", []) if action in orders[:fight_index + 1]]
        requested_boundary = self.duration_minutes(simulation_amount, simulation_unit)
        data, integrity_report = validate_turn_response(
            self.state, data, orders, results, requested_boundary,
            assessment.get("travel_plans", []),
            exact_duration=not moment_mode and not event_mode and challenge_resolution_mode != "stop",
        )
        actual_elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
        training_amount = actual_elapsed.get("amount", simulation_amount)
        training_unit = actual_elapsed.get("unit", simulation_unit)
        # Training gains use the validator-approved duration, so a narrator
        # cannot accidentally turn a requested month into a few hours of
        # growth (or award a month for a goal completed on day thirteen).
        persistent_training = player_training_directives(self.state)
        progression_actions = list(dict.fromkeys([*orders, *persistent_training]))
        self.enforce_training_progress(data, results, training_amount, training_unit, progression_actions, intensity)
        ensure_productive_failures(data, results)
        if data.get("interrupted") and str(data.get("interruption_kind") or "").lower() in {"canon_event", "world_event"}:
            data["event_notice"] = self._event_notice_payload(data, canon_stop)
        return self.apply_time_skip(data, amount, unit, progression_context={
            "actions": orders, "rolls": results,
            "progression_actions": progression_actions,
            "standing_intent_directives": intent_registration.get("consumed_directives", []),
            "elapsed_minutes": self.duration_minutes(training_amount, training_unit),
            "intensity": intensity, "model_used": getattr(narrator_client, "model", ""),
            "downtime_surprise_used": bool(downtime_hint),
        })

    def next_canon_stop(self, amount, unit):
        """The next dated commitment that should force a skip to stop early
        and let the player decide — either from this world's fixed canon
        timeline, or from a scheduled_events entry the GM itself created for
        a promised/threatened future confrontation (a rival vowing to come
        for the player, a character approaching on a specific day, etc.).
        Both are treated identically once they have a resolvable day."""
        before = int(self.state.get("canon_time_minutes", self.state.get("canon_day", -7) * 1440 + 480))
        after = before + self.duration_minutes(amount, unit)
        fired = set(self.state.get("canon_events_fired", []))
        candidates = []
        dependency_rows = {row["id"]: row for row in canon_dependency_graph(self.state).get("events", [])}
        try:
            from canon_divergence import active as active_canon_interventions
            targeted_minor = {str(row.get("event_id")) for row in active_canon_interventions(self.state) if isinstance(row, dict)}
        except Exception:
            targeted_minor = set()
        for event in timeline_for(self.state.get("world", "Custom World")).get("events", []):
            if event.get("historical_only"):
                continue
            # Only a "major" fixed-timeline event forces a full stop-and-ask;
            # the many smaller scripted beats still fire (see
            # fire_canon_events) as background texture without interrupting
            # a skip over something the player may not even be present for.
            event_id = str(event.get("id") or f"day:{event.get('day', 0)}:{event.get('title', 'event')}")
            # A player-targeted future minor event is intentionally promoted to
            # a stop boundary. Targeting does not guarantee success or presence;
            # it only prevents a long skip/narrative from silently passing it.
            if not event.get("major", True) and event_id not in targeted_minor:
                continue
            dependency = dependency_rows.get(event_id, {})
            if dependency.get("status") in {"impossible", "replaced"}:
                continue
            minute = int(dependency.get("effective_day", event.get("day", 0)) or 0) * 1440 + 480
            if before <= minute <= after and event_id not in fired:
                candidates.append((minute, {**event, "id": event_id, "day": dependency.get("effective_day", event.get("day", 0)),
                                             "dependency_status": dependency.get("status", "upcoming"),
                                             "targeted_minor": event_id in targeted_minor}))
        for index, sched in enumerate(self.state.get("scheduled_events", [])):
            if not isinstance(sched, dict) or str(sched.get("visibility", "confirmed")).lower() == "hidden":
                continue
            if sched.get("resolved") or sched.get("due_canon_day") is None:
                continue
            try:
                day = int(sched["due_canon_day"])
            except (TypeError, ValueError):
                continue
            minute = day * 1440 + 480
            sched_id = f"scheduled:{index}:{sched.get('title', 'event')}"
            if before <= minute <= after and sched_id not in fired:
                candidates.append((minute, {"day": day, "title": sched.get("title", "Scheduled event"),
                                             "location": sched.get("location", "Unknown"),
                                             "summary": sched.get("when") or sched.get("notes") or "",
                                             "_scheduled_index": index}))
        if not candidates: return None
        minute, event = min(candidates, key=lambda item: item[0])
        return {"title": event.get("title", "Major canon event"), "location": event.get("location", "Unknown"),
                "summary": event.get("summary", ""), "canon_day": int(event.get("day", 0)),
                "minutes_until": max(1, minute - before), "scheduled_index": event.get("_scheduled_index"),
                # "wide" (a village under attack, a war, a public coronation) is
                # the only scope where merely sharing the event's broad location
                # justifies forcing presence — see the scope check in
                # run_time_skip. Everything else (the default) is a small-cast
                # incident that happens to be tagged with a village-level
                # location for convenience, not because the whole village
                # witnesses it — "same village" was never a reasonable proxy
                # for "in the room when Mizuki tricks Naruto into stealing the
                # scroll."  GM-created scheduled_events (a specific NPC's
                # threatened confrontation) default to personal for the same
                # reason: they name one person's action toward the player, not
                # a location-wide catastrophe.
                "scope": event.get("scope", "personal")}

    def _training_method_profile(self, action):
        """Return a transparent acceleration factor for a concrete method.

        Generic detail earns a modest benefit. Large multipliers require a
        method recognized in the active world's own rules, keeping spectacular
        growth available without treating a bare wish as a training engine.
        """
        text = str(action or "")
        if not player_favoring_difficulty(self.state) or not explicit_world_method(text):
            return {"multiplier": 1.0, "reason": "ordinary training"}
        multiplier, reason = 1.45, "a specific player-authored training method"
        if AMBITIOUS_TRAINING_RE.search(text):
            multiplier, reason = 1.75, "a specific method aimed at an exceptional result"
        for pattern, candidate, candidate_reason in WORLD_ACCELERATED_TRAINING_METHODS.get(
                self.state.get("world"), ()):
            if pattern.search(text) and candidate > multiplier:
                multiplier, reason = candidate, candidate_reason
        if multiplier >= 2.2 and AMBITIOUS_TRAINING_RE.search(text):
            multiplier = min(6.0, multiplier * 1.25)
            reason += " aligned to the named high-level goal"
        return {"multiplier": round(multiplier, 2), "reason": reason}

    def enforce_training_progress(self, data, results, amount, unit, orders, intensity):
        """Guarantee that long training represents repeated daily work even if
        a narrator model under-awards the mechanical state patch."""
        training_words = ("train", "practice", "study", "research", "drill", "meditat", "spar", "learn", "master")
        training_orders = [str(x) for x in (orders or []) if any(k in str(x).lower() for k in training_words)]
        if not training_orders: return
        days = max(.05, self.duration_minutes(amount, unit) / 1440.0) / max(1, len(training_orders))
        rates = {"light": .25, "normal": .45, "intense": .75, "extreme": 1.05}
        base_rate = rates.get(str(intensity).lower(), .45)
        tuning = normalize_tuning(self.state)
        base_rate *= float(tuning.get("training_rate", 1.0) or 1.0)
        if player_favoring_difficulty(self.state):
            base_rate *= {"Story": 1.35, "Adventurer": 1.25, "Veteran": 1.10}.get(
                self.state.get("difficulty"), 1.0
            )
        growth_profile = self.state.get("special", {}).get("Growth Profile", {})
        try:
            learning_rate = clamp(float(growth_profile.get("learning_rate", 1.0)), .6, 1.75)
        except (TypeError, ValueError):
            learning_rate = 1.0
        checks = results or []
        patch = data.setdefault("state_patch", {})
        stat_patch = patch.setdefault("stats", {})
        progress_patch = patch.setdefault("ability_progress", {})
        xp_mode = uses_xp_for(self.state.get("world"), self.state.get("custom_world", ""))
        progression_events = []
        for index, action in enumerate(training_orders):
            result = next((row for row in checks if isinstance(row, dict)
                           and str(row.get("action") or "").strip().lower() == action.strip().lower()), None)
            current_stats = self.state.get("stats", {})
            plain_training = bool(PLAIN_TRAINING_RE.match(action))
            mentioned_stat = next(
                (name for name in current_stats if name.lower() in action.lower()), None
            )
            suggested_ability = (result or {}).get("ability")
            if suggested_ability not in current_stats:
                suggested_ability = None
            if plain_training and current_stats:
                # A bare "I train" means general development. Start with the
                # weakest foundation, then distribute meaningful work to every
                # other stat below instead of silently treating it as Ninjutsu.
                ability = min(current_stats, key=lambda name: float(current_stats.get(name, 0) or 0))
            else:
                inferred_ability = self._infer_training_ability(action, current_stats)
                ability = (mentioned_stat or inferred_ability or suggested_ability or
                           (primary_stats_for(self.state.get("world"), self.state.get("special", {}).get("Archetype", ""))
                            or list(current_stats))[0])
            factor = 1.25 if not result else 1.55 if result.get("success") else .70
            focused = 1.2 if re.search(r"\b(until|daily|every day|focus|specific|master|learn|improve)\b", action, re.I) else 1.0
            breakthrough = bool((result or {}).get("breakthrough"))
            # Every training day also carries a small independent discovery
            # chance; aggregating it makes a month meaningfully different.
            per_day_breakthrough = max(.002, min(.04, .01 * float(tuning.get("breakthrough_rate", 1.0) or 1.0)))
            if not breakthrough and random.random() < 1 - ((1 - per_day_breakthrough) ** max(1, days)):
                breakthrough = True
            multiplier = random.uniform(2.2, 4.0) if breakthrough else 1.0
            method_profile = self._training_method_profile(action)
            method_multiplier = float(method_profile["multiplier"])
            current = int(current_stats.get(ability, 1) or 1)
            # Weak foundations improve somewhat faster, while very high stats
            # still advance instead of hitting a hidden wall. A credible
            # accelerated method can overwhelm this gentle mastery curve.
            current_skill_modifier = (clamp((80.0 / max(20.0, current)) ** .08, .78, 1.18)
                                      if player_favoring_difficulty(self.state) else 1.0)
            gained_points = (days * base_rate * factor * focused * multiplier *
                             learning_rate * current_skill_modifier * method_multiplier)
            if player_favoring_difficulty(self.state):
                # Daily work stays fully counted, but mastery naturally
                # broadens and slows instead of adding the same whole stat
                # amount forever. This keeps a six-month Naruto regimen near
                # the intended jōnin benchmark rather than catapulting an
                # ordinary fighter beyond the world's greatest characters.
                intensity_curve = {"light": .70, "normal": 1.0, "intense": 1.10, "extreme": 1.25}.get(
                    str(intensity).lower(), 1.0
                )
                long_term_cap = 20.0 * ((max(.05, days) / 30.0) ** .62) * intensity_curve
                long_term_cap *= max(.8, learning_rate ** .5)
                long_term_cap *= method_multiplier
                if breakthrough:
                    long_term_cap *= 2.5
                gained_points = min(gained_points, long_term_cap)
            old_fraction = float(self.state.get("ability_progress", {}).get(ability, 0) or 0)
            total_points = old_fraction + gained_points
            if xp_mode:
                # System worlds retain proficiency progress, but base stats are
                # awarded only by the deterministic level-up routine.
                progress_patch[ability] = round(total_points, 3)
                applied_stat_gain = 0
            else:
                stat_gain = int(total_points)
                progress_patch[ability] = round(total_points - stat_gain, 3)
                proposed = int(stat_patch.get(ability, current) or current)
                stat_patch[ability] = max(proposed, current + stat_gain)
                applied_stat_gain = stat_patch[ability] - current
            support_gains = {}
            broad_training = plain_training or bool(BROAD_TRAINING_RE.search(action))
            if player_favoring_difficulty(self.state) and not xp_mode:
                # Even narrow practice uses the rest of the character: base
                # conditioning and experience move every stat a little, while
                # direct prerequisites receive a much larger share. Broad
                # combat regimens raise the whole fighting foundation.
                support_weights = {}
                current_values = [float(value or 0) for value in current_stats.values()]
                current_center = sorted(current_values)[len(current_values) // 2] if current_values else 1.0
                for name in current_stats:
                    if name == ability:
                        continue
                    if plain_training:
                        # General practice is deliberately balanced. Lagging
                        # stats catch up a little faster; specialties still
                        # receive maintenance growth proportional to time.
                        relative = clamp((max(1.0, current_center) /
                                          max(1.0, float(current_stats.get(name, 1) or 1))) ** .18,
                                         .75, 1.35)
                        support_weights[name] = .55 * relative
                    else:
                        support_weights[name] = .12 if broad_training else .06
                if broad_training and not plain_training:
                    for name in WORLD_COMBAT_FOUNDATIONS.get(self.state.get("world"), []):
                        if name != ability:
                            support_weights[name] = max(support_weights.get(name, 0), .38)
                elif not plain_training:
                    for name, weight in WORLD_TRAINING_SYNERGIES.get(self.state.get("world"), {}).get(ability, {}).items():
                        if name != ability:
                            support_weights[name] = max(support_weights.get(name, 0), weight)
                for support, weight in support_weights.items():
                    if support not in self.state.get("stats", {}):
                        continue
                    support_fraction = float(self.state.get("ability_progress", {}).get(support, 0) or 0)
                    support_total = support_fraction + gained_points * weight
                    support_gain = int(support_total)
                    progress_patch[support] = round(support_total - support_gain, 3)
                    support_current = int(self.state.get("stats", {}).get(support, 1) or 1)
                    support_proposed = int(stat_patch.get(support, support_current) or support_current)
                    stat_patch[support] = max(support_proposed, support_current + support_gain)
                    support_gains[support] = stat_patch[support] - support_current
            entry = {"action": action, "ability": ability, "effective_training_days": round(days, 2),
                     "stat_gain": applied_stat_gain, "breakthrough": breakthrough,
                     "learning_rate_multiplier": round(learning_rate, 2),
                     "current_skill_modifier": round(current_skill_modifier, 2),
                     "training_method_multiplier": round(method_multiplier, 2),
                     "training_method": method_profile["reason"],
                     "balanced_training": plain_training,
                     "explanation": (f"Sustained {ability} repetition produced a lore-valid insight that multiplied the training return."
                                     if breakthrough else
                                     (f"{round(days, 1)} effective daily sessions built proficiency; System XP and levels govern base stats."
                                      if xp_mode else f"{round(days, 1)} effective daily sessions accumulated at the character's {learning_rate:.2f}× aptitude rate."))}
            if support_gains:
                entry["support_stat_gains"] = support_gains
            progression_events.append(entry)
            if (self.state.get("world") == "Naruto" and broad_training and days >= 150
                    and player_favoring_difficulty(self.state)):
                patch.setdefault("special", {})["Combat Benchmark"] = {
                    "tier": "Jōnin-level combatant",
                    "official_rank": False,
                    "basis": f"{round(days, 1)} days of rigorous, broad shinobi training",
                    "description": "Combat capability comparable to a capable jōnin; this does not itself grant an official village appointment.",
                }
                data.setdefault("events", []).append({
                    "type": "training",
                    "message": "Combat benchmark reached: jōnin-level capability (not an automatic official rank).",
                })
            if breakthrough:
                data.setdefault("updates", []).append({"sequence": 900 + index, "type": "consequence",
                    "title": "Lore Breakthrough", "related_action": action,
                    "narrative": f"Repeated {ability} practice aligned technique, conditioning and timing at once. The resulting insight produced an unusually large but setting-consistent leap in power."})
                data.setdefault("events", []).append({"type": "training", "message": f"Breakthrough: {ability} surged through sustained training."})
        patch.setdefault("progression_log", list(self.state.get("progression_log", [])) + progression_events)

    def sync_derived_pools(self, before):
        hp_max, resource_max = self.derive_pools(self.state.get("world", "Custom World"), self.state.get("stats", {}))
        for current_key, max_key, derived in (("hp", "hp_max", hp_max), ("resource", "resource_max", resource_max)):
            old_max = int(before.get(max_key, derived) or derived)
            authored_max = int(self.state.get(max_key, derived) or derived)
            new_max = max(authored_max, derived)
            delta = max(0, new_max - old_max)
            self.state[max_key] = new_max
            self.state[current_key] = min(new_max, max(0, int(self.state.get(current_key, new_max) or 0) + delta))

    def duration_minutes(self, amount, unit):
        from world_calendar import duration_minutes
        return duration_minutes(self.state, amount, unit)

    def advance_clock(self, before, amount, unit):
        from world_calendar import duration_minutes
        minutes = duration_minutes(before, amount, unit)
        base_total = int(before.get("world_clock_minutes", 480) or 0)
        total = base_total + minutes
        self.state["world_clock_minutes"] = total
        cal_before = before.get("calendar", {}) if isinstance(before.get("calendar"), dict) else {}
        absolute = (
            (((int(cal_before.get("year", 1)) - 1) * 12 + (int(cal_before.get("month", 1)) - 1)) * 30
             + (int(cal_before.get("day", 1)) - 1)) * 1440
            + int(cal_before.get("hour", 8)) * 60 + int(cal_before.get("minute", 0)) + minutes
        )
        day_total, minute_of_day = divmod(absolute, 1440)
        month_total, day_index = divmod(day_total, 30)
        year_index, month_index = divmod(month_total, 12)
        hour, minute = divmod(minute_of_day, 60)
        self.state["calendar"] = {"day": day_index + 1, "month": month_index + 1, "year": year_index + 1, "hour": hour, "minute": minute}
        period = "Night" if hour < 5 or hour >= 21 else "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
        canon_before = int(before.get("canon_time_minutes", int(before.get("canon_day", -7)) * 1440 + 480))
        canon_after = canon_before + minutes
        self.state["canon_time_minutes"] = canon_after
        canon_day = canon_after // 1440
        self.state["canon_day"] = canon_day
        date_str = format_calendar_date(self.state.get("world", "Custom World"), canon_day, self.state.get("calendar_epoch"), self.state.get("calendar_anchor_day"))
        from world_calendar import time_label
        self.state["world_time"] = time_label(self.state)
        pending_canon_appends = self.fire_canon_events(canon_before, canon_after)
        age_change = advance_character_age(self.state, before)
        if age_change:
            years = age_change["years"]
            elapsed_note = f" after {years} completed campaign years" if years > 1 else ""
            pending_canon_appends.append({
                "text": f"[BIRTHDAY]\n{self.state.get('name', 'The character')} is now {age_change['age']}{elapsed_note}.",
                "tag": "growth", "canon_day": canon_day, "major": False, "event_title": "",
            })
        # A full status-window popup every ~3 in-game months (90 days),
        # regardless of how time was spent getting there — a periodic
        # check-in on the character's overall progress.
        self.state["minutes_since_status_window"] = int(self.state.get("minutes_since_status_window", 0) or 0) + minutes
        if self.state["minutes_since_status_window"] >= 90 * 1440:
            self.state["minutes_since_status_window"] = 0
            self.state["status_window_due"] = True
        return pending_canon_appends

    def fire_canon_events(self, before_minutes, after_minutes):
        """Returns pending Chronicle entries rather than appending them
        directly — the caller (apply_time_skip) merges these with the
        narrator's own per-day updates and appends everything together in
        one chronological pass, so a canon event's note lands in its actual
        day order instead of always jumping to the top of the batch."""
        if after_minutes <= before_minutes:
            return []
        fired = self.state.setdefault("canon_events_fired", [])
        pending_appends = []
        world = self.state.get("world", "Custom World")
        anchor_day = self.state.get("calendar_anchor_day")
        dependency_rows = {row["id"]: row for row in canon_dependency_graph(self.state).get("events", [])}
        # This campaign's own start (not the world's generic default) is what
        # separates "already history before the story began" from "due to
        # happen during this campaign" — see the CANON HISTORY/UPCOMING split
        # in gm_rules. Only apply this filter when we actually KNOW the real
        # start (a save from before calendar_anchor_day existed has it as
        # None) — guessing the world's generic default here is wrong for any
        # save that actually began at a canon-character start or a chosen
        # starting era, and guessing wrong in this direction is much worse
        # than guessing wrong the other way: it would wrongly reclassify a
        # genuinely-upcoming event as already-historical and permanently
        # suppress it, exactly the "never actually happens" bug this exists
        # to prevent. When we don't know, don't filter at all.
        campaign_start_minute = int(anchor_day) * 1440 + 480 if anchor_day is not None else None
        for event in timeline_for(world).get("events", []):
            if event.get("historical_only"):
                continue
            event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
            dependency = dependency_rows.get(event_id, {})
            event_minute = int(dependency.get("effective_day", event.get("day", 0)) or 0) * 1440 + 480
            if campaign_start_minute is not None and event_minute < campaign_start_minute:
                continue
            # Catch-up, not just a same-turn crossing: fire the moment we've
            # reached or passed its day even if an earlier turn should have
            # already caught it and, for whatever reason, didn't — a canon
            # event's day is a firm commitment and must never be left
            # permanently stuck as "still pending" once it's actually behind
            # the player. Minor and major events are both delivered as an
            # ordinary Chronicle update here; only major events additionally
            # get a chance to pause the skip and be played out live, via
            # next_canon_stop/canon_stop elsewhere — that's a separate,
            # unaffected mechanism.
            if event_minute <= after_minutes and event_id not in fired:
                fired.append(event_id)
                if dependency.get("status") in {"impossible", "replaced"}:
                    replacement = dependency.get("replacement") or "The surviving motives must now produce a different consequence."
                    detail = (f"{event.get('title', 'Canon event')} no longer occurs in its original form. "
                              f"{dependency.get('reason', 'An earlier required cause was removed.')} Replacement pressure: {replacement}")
                    self.state.setdefault("canon_event_states", {})[event_id] = {
                        "status": dependency.get("status"), "reason": dependency.get("reason", ""),
                        "replacement": replacement, "resolved_day": self.state.get("canon_day", 0),
                    }
                    self.state.setdefault("world_events", []).append(detail)
                    self.state.setdefault("timeline", []).append(detail)
                    self.state.setdefault("background_world_feed", []).append(detail)
                    pending_appends.append({"text": "[CANON DIVERGENCE]\n" + detail, "tag": "system",
                                             "canon_day": int(dependency.get("effective_day", event.get("day", 0)) or 0),
                                             "major": False, "event_title": event.get("title", "")})
                    continue
                effective_day = int(dependency.get("effective_day", event.get("day", 0)) or 0)
                label = f"{format_calendar_date(world, effective_day, self.state.get('calendar_epoch'), anchor_day)} — {event.get('title', 'World event')}"
                divergence_note = (" This campaign already contains divergences, so the event's motive and pressure remain active even if its participants or outcome change."
                                   if self.state.get("canon_divergences") else
                                   " The player may engage with, avoid, redirect, or fundamentally alter what follows.")
                detail = f"{label}\nLocation: {event.get('location', 'Unknown')}. {event.get('summary', '')}{divergence_note}"
                self.state.setdefault("world_events", []).append(detail)
                self.state.setdefault("timeline", []).append(detail)
                # A canon-timeline beat delivered through this mechanical
                # backstop (as opposed to the interactive canon_stop path) is
                # by definition something the player is reading ABOUT, not
                # living through — see the docstring above. Mirrored into its
                # own list so the World Feed can show "the wider world" moved
                # on its own, distinct from the player's own scenes, without
                # touching the existing world_events/timeline shape anything
                # else already reads.
                self.state.setdefault("background_world_feed", []).append(detail)
                major = event.get("major", True)
                pending_appends.append({
                    "text": "[CANON TIMELINE]\n" + detail + "\nPrior divergences may alter how this event unfolds.",
                    "tag": "canon_event" if major else "system", "canon_day": effective_day,
                    "major": bool(major), "event_title": event.get("title", ""),
                })
                self.state.setdefault("canon_event_states", {})[event_id] = {
                    "status": dependency.get("status", "occurred"), "reason": dependency.get("reason", ""),
                    "replacement": dependency.get("replacement", ""), "resolved_day": effective_day,
                }
        # Mechanical backstop for GM-created scheduled_events (a promised
        # confrontation, a character due to approach the player, etc.): even
        # if the AI's own narrative update forgets to cover it, this always
        # leaves a concrete note the moment its date is crossed (or, per the
        # same catch-up guarantee above, the first time we notice it's
        # already behind us), so a commitment the player was told about can
        # never just silently pass.
        for index, sched in enumerate(self.state.get("scheduled_events", [])):
            if not isinstance(sched, dict) or sched.get("resolved") or sched.get("due_canon_day") is None:
                continue
            try:
                day = int(sched["due_canon_day"])
            except (TypeError, ValueError):
                continue
            event_minute = day * 1440 + 480
            sched_id = f"scheduled:{index}:{sched.get('title', 'event')}"
            if event_minute <= after_minutes and sched_id not in fired:
                fired.append(sched_id)
                sched["resolved"] = True
                label = f"{format_calendar_date(world, day, self.state.get('calendar_epoch'), anchor_day)} — {sched.get('title', 'Scheduled event')}"
                detail = f"{label}\n{sched.get('when') or ''} {sched.get('notes') or ''}".strip()
                pending_appends.append({"text": "[SCHEDULED EVENT]\n" + detail, "tag": "system", "canon_day": day,
                                         "major": True, "event_title": sched.get("title", "")})
        self.state["canon_events_fired"] = fired
        pending_appends.extend(self._pay_recurring_finances(after_minutes))
        if any(p["major"] for p in pending_appends):
            self.state["active_canon_event"] = next(p["event_title"] for p in pending_appends if p["major"])
        return pending_appends

    def _pay_recurring_finances(self, after_minutes):
        """Mechanical backstop for GM-established recurring income/expenses
        (a job, a shop's take, rent, staff wages, a stipend): pays each one
        out automatically as canon_day crosses its next_due_day, the same
        catch-up-safe pattern as the scheduled_events backstop above, so an
        established source is never silently lost to context drift over a
        long campaign and never needs the AI to remember to re-apply it."""
        world = self.state.get("world", "Custom World")
        if world == "Bleach" or not expansion_for(world).get("tracks_currency", True):
            return []
        entries = self.state.get("recurring_finances")
        if not isinstance(entries, list) or not entries:
            return []
        currency = ensure_currency_state(self.state)
        anchor_day = self.state.get("calendar_anchor_day")
        appends = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("active") is False:
                continue
            try:
                interval = max(1, int(entry.get("interval_days", 30)))
                next_due = int(entry["next_due_day"])
                amount = abs(float(entry.get("amount", 0)))
            except (TypeError, ValueError, KeyError):
                continue
            if not amount:
                continue
            kind = str(entry.get("kind", "income")).lower()
            if kind not in {"income", "expense"}:
                continue
            sign = -1 if kind == "expense" else 1
            due_minute = next_due * 1440 + 480
            if due_minute > after_minutes:
                continue
            # Calculate catch-up in constant time.  The old defensive loop
            # stopped after 240 payments, so a daily income over a one-year
            # skip paid only 240 days and left the rest to leak into later
            # turns.  Arithmetic is both safer and exact for long campaigns.
            paid_cycles = ((after_minutes - due_minute) // (interval * 1440)) + 1
            total = amount * paid_cycles
            next_due += interval * paid_cycles
            if not paid_cycles:
                continue
            entry["next_due_day"] = next_due
            entry["last_paid_day"] = next_due - interval
            label = str(entry.get("label") or ("Recurring income" if sign > 0 else "Recurring expense"))
            date_str = format_calendar_date(world, entry["last_paid_day"], self.state.get("calendar_epoch"), anchor_day)
            cycle_note = f" (x{paid_cycles} cycles)" if paid_cycles > 1 else ""
            currency_name = str(entry.get("currency") or currency.get("name", "Currency"))
            if sign > 0:
                record_currency_transaction(self.state, total, label, "recurring_income", currency_name, "world_clock",
                                            {"cycles": paid_cycles})
                detail = f"{date_str} — {label}: +{total:g} {currency_name}{cycle_note}"
            else:
                available = max(0, currency_balance(self.state, currency_name))
                paid = min(available, total)
                if paid:
                    record_currency_transaction(self.state, -paid, label, "recurring_expense", currency_name, "world_clock",
                                                {"cycles": paid_cycles})
                shortfall = max(0, total - paid)
                if shortfall:
                    record_finance_debt(self.state, label, shortfall, currency_name, str(entry.get("notes") or ""))
                detail = f"{date_str} — {label}: {paid:g} {currency_name} paid"
                if shortfall:
                    detail += f"; {shortfall:g} remains outstanding"
                detail += cycle_note
            appends.append({
                "text": "[FINANCES]\n" + detail, "tag": "system", "canon_day": entry["last_paid_day"],
                "major": False, "event_title": "",
            })
        return appends

    def request_continuity_correction(self, new_warnings, narrative):
        """Continuity warnings used to just sit in the Journal for the player
        to notice eventually. Now a newly-detected contradiction gets one
        immediate, cheap correction pass instead — the same background model
        used for memory maintenance, asked to fix only what conflicts rather
        than re-narrate the scene. Best-effort: any failure here is silently
        swallowed, since a missed correction just falls back to the old
        passive-warning behavior."""
        if not new_warnings or not self.ai_bg_ready() or self.busy:
            return None
        payload = {
            "task": "continuity_correction", "role": "Continuity Auditor",
            "last_narrative": narrative, "detected_conflicts": new_warnings, "state": self.trimmed_state_for_ai(),
            "requirements": "The last response conflicts with established continuity. Reconcile it minimally: "
                            "either correct the specific state fields to match established facts, or write a brief "
                            "in-fiction addendum explaining the discrepancy (a correction, a rumor was wrong, a "
                            "misremembering) — never rewrite or repeat the original scene.",
            "schema": {"state_patch": "corrected fields only, or {}", "addendum": "1-3 sentences reconciling the conflict, or empty"},
        }
        rules = self.task_rules("continuity_audit")
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=350)
        except Exception as e:
            self.log("Continuity correction failed: " + str(e))
            return None
        patch = data.get("state_patch") if isinstance(data.get("state_patch"), dict) else {}
        if patch:
            apply_guarded_patch(self.state, patch, allow_time=False, source="continuity_correction")
        addendum = str(data.get("addendum", "")).strip()
        if addendum:
            self.append("[CONTINUITY NOTE]\n" + addendum, "meta")
        self.log("Continuity correction applied: " + "; ".join(new_warnings))
        return {"addendum": addendum, "patched": bool(patch)}

    def _beat_detail(self, update, narrative_text):
        """Structured extras for a dated time-skip beat, riding along on the
        story entry's existing free-form `detail` field: the entities the
        GM already bolded (same convention the Codex-linking already reads),
        plus the AI's own rare map_changes/quote flags — sanitized here so a
        malformed or overzealous response can't reach the Chronicle UI. A
        moment-to-moment single action never has canon_day set and never
        reaches this at all, so richer per-day cards fall out naturally from
        longer skips instead of needing a separate length check."""
        entities = []
        for name in re.findall(r"\*\*(.+?)\*\*", narrative_text):
            name = name.strip()
            if name and name not in entities:
                entities.append(name)
        map_changes = [ai_text(m) for m in (update.get("map_changes") or []) if ai_text(m)][:4]
        quote = update.get("quote")
        clean_quote = None
        if isinstance(quote, dict):
            text = ai_text(quote.get("text") or "")
            speaker = ai_text(quote.get("speaker") or "")
            if text:
                clean_quote = {"text": text, "speaker": speaker}
        delivery = ai_text(update.get("delivery_channel") or update.get("information_source") or "")
        special = (update.get("type") in {"canon_event", "interruption", "discovery", "reward", "achievement"}
                   or update.get("significance") in {"milestone", "decision"} or bool(update.get("rewards")))
        if not entities and not map_changes and not clean_quote and not delivery and not special:
            return None
        return {"entities": entities[:6], "map_changes": map_changes, "quote": clean_quote, "delivery": delivery,
                "chronicle_tone": "special" if special else "standard"}

    def apply_time_skip(self, data, requested_amount, requested_unit, progression_context=None):
        with self.lock:
            data, canon_repairs = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
            before = copy.deepcopy(self.state)
            context = progression_context if isinstance(progression_context, dict) else {}
            danger_was_active = self.danger_scenario_active(before)
            validation = apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="time_skip")
            self.ensure_combat_numbers()
            if not uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")):
                self.state["xp"], self.state["level"], self.state["xp_next"] = before.get("xp", 0), before.get("level", 1), before.get("xp_next", 100)
            elif not context.get("local_rules") or context.get("local_award_xp"):
                self.apply_system_xp(before, context.get("actions", []), context.get("rolls", []),
                                     context.get("elapsed_minutes", self.duration_minutes(requested_amount, requested_unit)),
                                     context.get("intensity", "normal"), data.get("events", []))
            self.reconcile_title_events(data.get("events", []))
            self.sync_derived_pools(before)
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_amount = elapsed.get("amount", requested_amount)
            elapsed_unit = elapsed.get("unit", requested_unit)
            from world_calendar import duration_minutes
            elapsed_minutes = duration_minutes(before, elapsed_amount, elapsed_unit)
            pending_canon_appends = self.advance_clock(before, elapsed_amount, elapsed_unit)
            jjk_notes = advance_jjk_state(
                self.state, before, context.get("actions", []), data.get("narrative", ""),
                data.get("events", []), elapsed_minutes,
            )
            # Advance is the game's normal turn path. Visible releases and
            # transformations must update the portrait here just as they do
            # in the direct single-resolution path.
            sync_active_portrait_form(
                self.state, context.get("actions", []), data.get("narrative", ""), data.get("events", []),
            )
            lit_notes = process_lit_turn(
                before, self.state, context.get("actions", []), data.get("narrative", ""),
                elapsed_minutes,
            )
            activity_notes = advance_world_activity(
                self.state, before, context.get("actions", []), data.get("narrative", ""),
                data.get("events", []), elapsed_minutes,
            )
            consequence_report = reconcile_narrated_consequences(
                before, self.state, data, context.get("actions", []), elapsed_minutes,
            )
            for ev in data.get("timeline_events", []) or []:
                self.state.setdefault("timeline", []).append(ev)
            for c in data.get("new_contacts", []) or []:
                if isinstance(c, dict):
                    self.ensure_contact(c.get("name"), c.get("kind", "person"), c)
                else:
                    self.ensure_contact(str(c))
            from organizations import process_organizations
            organization_events = process_organizations(before, self.state, data, elapsed_minutes)
            autonomy_events = advance_companion_autonomy(self.state, elapsed_minutes)
            npc_growth_events = advance_npc_development(self.state, elapsed_minutes)
            downtime_events = world_downtime_events(self.state, elapsed_minutes, context.get("actions", []))
            from living_world import advance as advance_living_world, record_outcome as record_living_outcome
            living = advance_living_world(self.state, context.get("actions", []), elapsed_minutes, data.get("updates", []), data.get('world_plan_updates'))
            record_living_outcome(self.state, data, context.get("actions", []))
            from arc_director import advance as advance_campaign_arcs
            arc_result = advance_campaign_arcs(self.state, context.get("actions", []), [*data.get("updates", []), *living.get("events", [])], elapsed_minutes)
            life_result = advance_life_simulation(
                self.state, context.get("actions", []),
                [*data.get("updates", []), *data.get("events", []), *autonomy_events, *npc_growth_events, *organization_events, *living.get("events", []), *arc_result.get("beats", [])],
                elapsed_minutes,
            )
            from gm_consistency import coalesce_routine_updates
            updates = coalesce_routine_updates(data.get("updates", []))
            updates = prioritize_updates(
                [u for u in [*updates, *autonomy_events, *npc_growth_events, *downtime_events, *organization_events, *living.get("events", []), *arc_result.get("beats", []), *life_result.get("events", [])]
                 if isinstance(u, dict) and str(u.get("narrative", "")).strip()],
                self.simulation_mode(),
            )
            updates = normalize_dated_updates(
                updates, int(before.get("canon_day", 0) or 0),
                int(self.state.get("canon_day", before.get("canon_day", 0)) or 0), elapsed_minutes,
            )
            incoming_chats = [m for m in (data.get("incoming_chats", []) or []) if isinstance(m, dict)]
            from relationship_life import resolve as resolve_relationships
            incoming_chats.extend(resolve_relationships(before, self.state, data))
            incoming_chats.extend(living.get("incoming_chats", []))
            incoming_chats.extend(reactive_communication(self.state, updates, elapsed_minutes, incoming_chats))
            for m in incoming_chats:
                thread = m.get("thread") or m.get("sender")
                if not thread:
                    continue
                self.ensure_contact(thread)
                self.add_chat_message(thread, m.get("sender"), m.get("message", ""), "incoming", m.get("metadata"))
            record_simulation_events(self.state, updates, "narrator")
            # Canon-event notes (from fire_canon_events, day-anchored but not
            # authored by this turn's narrator) are merged into the SAME
            # chronological pass as the narrator's own per-day updates —
            # sorted together by canon_day — instead of always being appended
            # first regardless of where their day actually falls among them.
            # A canon note gets sequence -1 so it reads as that day's opening
            # headline when it shares a day with a narrator update.
            # If the narrator omits a date, the update describes the result at
            # the end of the resolved span. Sorting it as literal day 0 made a
            # final-day action card appear before canon events from earlier in
            # the same skip, even though its displayed header used the final
            # date. Anchor undated updates to the clock we just advanced to.
            final_canon_day = int(self.state.get("canon_day", before.get("canon_day", 0)) or 0)
            def update_canon_day(update):
                try:
                    value = update.get("canon_day")
                    return int(value) if value is not None and str(value).strip() else final_canon_day
                except (TypeError, ValueError):
                    return final_canon_day
            entries = [{
                "canon_day": update_canon_day(u),
                "sequence": int(u.get("sequence", 0) or 0), "kind": "update", "data": u,
            } for u in updates]
            entries += [{"canon_day": p["canon_day"], "sequence": -1, "kind": "canon", "data": p} for p in (pending_canon_appends or [])]
            entries.sort(key=lambda e: (e["canon_day"], e["sequence"]))
            if entries:
                for entry in entries:
                    if entry["kind"] == "canon":
                        p = entry["data"]
                        self.append(p["text"], p["tag"], canon_day=p["canon_day"])
                        continue
                    update = entry["data"]
                    title = str(update.get("title") or update.get("type") or "Update").replace("_", " ").upper()
                    from chronicle_prose import beat_body
                    canon_day = entry["canon_day"]
                    try: canon_day = int(canon_day) if canon_day is not None else None
                    except (TypeError, ValueError): canon_day = None
                    body = beat_body(update)
                    self.append(f"[{title}]\n" + body, "system" if update.get("type") != "action" else "narrative",
                                canon_day=canon_day, detail=self._beat_detail(update, body))
            else:
                self.append("[TIME SKIP]\n" + data.get("narrative", "Time passes."), "system")
            if lit_notes:
                heading = "SATISFY SYSTEM" if self.state.get("world") == "Overgeared" else "TOWER SYSTEM"
                self.append(f"[{heading}]\n" + "\n".join(lit_notes), "system")
            if activity_notes:
                self.append("[WORLD DEVELOPMENT]\n" + "\n".join(activity_notes), "system")
            if jjk_notes:
                self.append("[JUJUTSU RECORD]\n" + "\n".join(jjk_notes), "system")
            self.append_growth_deltas(before)
            interrupted = bool(data.get("interrupted"))
            interruption_kind = str(data.get("interruption_kind") or "").lower()
            combat_now = bool(isinstance(self.state.get("combat"), dict) and self.state.get("combat", {}).get("active"))
            danger_words = " ".join(str(data.get(key) or "") for key in (
                "interruption_reason", "interruption_context", "intervention_prompt", "narrative"
            ))
            danger_triggered = bool(
                combat_now
                or interruption_kind == "danger"
                or (interruption_kind in {"canon_event", "world_event"} and self._DANGER_SCENE_RE.search(danger_words))
            )
            warning_was_shown = bool(danger_was_active or data.get("danger_warning_acknowledged"))
            danger_notice_required = bool(danger_triggered and not warning_was_shown)
            actions_text = " ".join(str(x) for x in context.get("actions", []) if str(x).strip())
            location_changed = str(before.get("location") or "").strip().lower() != str(self.state.get("location") or "").strip().lower()
            if data.get("danger_scenario_concluded") and not combat_now:
                self.clear_danger_scenario()
            elif danger_triggered:
                self.acknowledge_danger_scenario(data.get("interruption_reason") or data.get("major_event_title") or "")
            elif data.get("danger_warning_acknowledged"):
                self.acknowledge_danger_scenario(data.get("narrative") or "Dangerous confrontation")
            elif self.danger_scenario_active(before) and not combat_now and (
                location_changed or self._DANGER_EXIT_RE.search(actions_text)
            ):
                self.clear_danger_scenario()
            if interrupted:
                is_canon = data.get("interruption_kind") == "canon_event"
                heading = "MAJOR CANON EVENT" if is_canon else "TIME SKIP INTERRUPTED"
                reason = data.get("interruption_reason", "Something requires your attention.")
                event_context = str(data.get("interruption_context") or "").strip()
                event_prompt = str(data.get("intervention_prompt") or "").strip()
                sections = [reason]
                if event_context and event_context != reason:
                    sections.append(event_context)
                if event_prompt:
                    sections.append("YOUR NEXT DECISION\n" + event_prompt)
                self.append(f"[{heading}]\n" + "\n\n".join(sections), "canon_event" if is_canon else "danger")
            # Drives which banner shows behind the scene (see scene_image_url)
            # — defaults to clearing rather than getting stuck on if a turn's
            # response ever omits it, since a banner reverting a beat early is
            # far less broken than one stuck on a resolved event forever.
            new_active_event = str(data.get("active_major_event") or "").strip()
            if new_active_event and new_active_event != self.state.get("active_canon_event"):
                # A fresh engagement (not a continuation of the same one) —
                # see the engagement-count comment in assess_time_skip for
                # why this resets rather than just incrementing.
                self.state["canon_event_engagement_count"] = 0
            elif new_active_event:
                self.state["canon_event_engagement_count"] = int(self.state.get("canon_event_engagement_count", 0) or 0) + 1
            self.state["active_canon_event"] = new_active_event
            if new_active_event:
                self.state["active_event_context"] = str(data.get("interruption_context") or self.state.get("active_event_context") or "").strip()
                self.state["active_event_prompt"] = str(data.get("intervention_prompt") or self.state.get("active_event_prompt") or "").strip()
            else:
                self.state["active_event_context"] = ""
                self.state["active_event_prompt"] = ""
            context = progression_context if isinstance(progression_context, dict) else {}
            self.ensure_quest_briefings(before, " ".join(part for part in (
                "; ".join(str(x) for x in context.get("actions", [])), str(data.get("narrative") or "")
            ) if part.strip()))
            completed_quests = normalize_quest_state_machine(self.state)
            advance_standing_intents(self.state, elapsed_minutes, data.get("standing_intent_updates"))
            adopted_directives = {ai_text(row).lower() for row in context.get("standing_intent_directives", []) if ai_text(row)}
            if adopted_directives:
                self.state["standing_orders"] = [row for row in self.state.get("standing_orders", [])
                                                   if ai_text(row).lower() not in adopted_directives]
            self.append_training_summary(before, context.get("progression_actions", context.get("actions", [])), elapsed_minutes, context.get("rolls", []))
            integrity_report = data.get("integrity_report") if isinstance(data.get("integrity_report"), dict) else {}
            if canon_repairs:
                integrity_report.setdefault("repairs", []).extend(canon_repairs)
            if integrity_report:
                self.state.setdefault("simulation_validation", []).append(copy.deepcopy(integrity_report))
                self.state["simulation_validation"] = self.state["simulation_validation"][-100:]
            reconcile_action_goals(self.state, [], data, elapsed_minutes)
            transmit_information(self.state, data, elapsed_minutes)
            record_causal_outcome(self.state, data, context.get("actions", []), elapsed_minutes)
            self.check_tower_deadline(before, elapsed_minutes)
            if data.get("major_event_reached"):
                self.state["last_major_beat_day"] = int(self.state.get("canon_day", 0) or 0)
            clock_events = tick_world_clocks(self.state, elapsed_minutes)
            intention_events = advance_npc_intentions(self.state, elapsed_minutes, self.simulation_mode())
            schedule_events = refresh_npc_schedules(self.state, elapsed_minutes)
            local_world_events = prioritize_updates(clock_events + intention_events + schedule_events, self.simulation_mode())
            record_simulation_events(self.state, local_world_events, "deterministic_world")
            for event in local_world_events:
                message = event.get("message") or event.get("narrative") or "World agenda advanced."
                self.state.setdefault("world_events", []).append(message)
                # NPC/faction clocks are, by construction, agendas moving
                # independently of the player — same background-feed mirror
                # as the canon catch-up backstop above.
                self.state.setdefault("background_world_feed", []).append(message)
                # These used to sit in the collapsed meta strip, tagged like
                # an engine notice — but this is the one channel that makes
                # the world visibly keep moving when the player isn't doing
                # anything, and hiding it defeated that. Back in the main
                # Chronicle as a real beat; the underlying message strings in
                # systems.py were also reworded off "[BRACKETED] status
                # report" phrasing into something closer to news reaching
                # the player, since visible-but-still-robotic wouldn't have
                # actually fixed the original complaint.
                self.append("[ELSEWHERE]\n" + message, "system")
            for name in completed_quests:
                if uses_literal_quests(self.state.get("world")):
                    message = f"[QUEST COMPLETE — {name}]\nAll required objectives have been completed."
                else:
                    label = quest_presentation_for(self.state.get("world"))["entry_label"].upper()
                    message = f"[{label} CONCLUDED — {name}]\nThe situation reached a story-established outcome and has moved into campaign history."
                self.append(message, "meta")
            notifications = self.notify(before, self.state, list(data.get("events", []) or []) + local_world_events)
            if interrupted and data.get("interruption_kind") == "canon_event":
                notifications.append({"message": "MAJOR CANON EVENT: " + data.get("interruption_reason", "A major canon event is unfolding."),
                                       "tag": "danger", "cinematic": "canon_event"})
            self.state.setdefault("time_skip_history", []).append({
                "turn": self.state.get("turn", 0), "elapsed": data.get("elapsed"),
                "orders": self.state.get("standing_orders", []), "interrupted": interrupted
            })
            self.state["turn"] = before.get("turn", 0) + 1
            if context.get("downtime_surprise_used"):
                self.state["downtime_surprise_state"] = {
                    "last_turn": self.state["turn"], "last_canon_day": self.state.get("canon_day", 0)
                }
            self.state["time_mode"] = "moment"
            self.state["queued_actions"] = [ai_text(x) for x in data.get("deferred_actions", []) if ai_text(x)]
            self.state["suggested_actions"] = self.guided_suggestions(data.get("suggested_actions"))
            action_summary = "Advance: " + "; ".join(context.get("actions", []) or self.state.get("standing_orders", []))
            advance_hidden_class_discovery(self.state, action_summary)
            progression_summary = "Advance: " + "; ".join(context.get("progression_actions", context.get("actions", [])) or self.state.get("standing_orders", []))
            record_progression_ledger(before, self.state, progression_summary, elapsed_minutes, context.get("rolls", []))
            record_ability_evolution(before, self.state, data, context.get("actions", []))
            relationship_offer = maybe_offer_relationship_scene(self.state, updates)
            if relationship_offer:
                self.state["suggested_actions"] = self.guided_suggestions([relationship_offer["prompt"], *self.state.get("suggested_actions", [])])
                self.append(f"[OPTIONAL CHARACTER MOMENT — {relationship_offer['npc']}]\n{relationship_offer['reason']} This is optional; time will not move until you choose and Advance.", "meta")
            update_campaign_direction(self.state, context.get("actions", []), updates + local_world_events, elapsed_minutes)
            normalize_world_depth(self.state, before)
            record_downtime(self.state, context.get("progression_actions", context.get("actions", [])), elapsed_minutes)
            record_canon_ripples(self.state, updates + local_world_events)
            cause_effect = build_cause_effect(before, self.state, context.get("actions", []), context.get("rolls", []))
            self.state["last_ai_route"] = {"role": "Major Event GM" if context.get("model_used") and context.get("model_used") == self.settings.get("major_event_model") else "Main GM",
                                           "model": context.get("model_used") or self.settings.get("model", ""), "turn": self.state.get("turn", 0),
                                           **copy.deepcopy(getattr(self, "_last_request_usage", {}))}
            if self.settings.get("developer_mode"):
                self.append(f"[AI ROUTE]\n{self.state['last_ai_route']['role']}: {self.state['last_ai_route']['model']}", "meta")
            update_narrative_memory(before, self.state, action_summary, data.get("narrative", ""))
            reconcile_commitments_and_consequences(self.state, data, elapsed_minutes)
            refresh_canon_divergence_impacts(self.state)
            refresh_scene_state(self.state, data, context.get("actions", []))
            record_pacing_beat(self.state, data, context.get("actions", []))
            normalize_outcome_scale(before, self.state, data, elapsed_minutes)
            refresh_simulation_core(self.state, context.get("actions", []), elapsed_minutes, action_summary)
            update_scenario_memory(before, self.state, context.get("actions", []), data)
            for milestone in record_world_milestones(self.state, data):
                self.append(f"[{milestone['heading']}]\n{milestone['title']}: {milestone['detail']}", "system")
            record_resolution_transaction(
                self.state, before, context.get("actions", []), elapsed_minutes,
                data.get("narrative", ""), context.get("rolls", []),
            )
            prior_warnings = set(before.get("continuity_ledger", {}).get("warnings", []))
            continuity_warnings = update_continuity(before, self.state, action_summary, data.get("narrative", ""))
            normalize_world_progression(self.state, before)
            for note in self.state.pop("_pending_chronicle_notes", []):
                self.append(note, "meta")
            new_warnings = [w for w in continuity_warnings if w not in prior_warnings]
            if new_warnings and not context.get("local_rules"):
                self.request_continuity_correction(new_warnings, data.get("narrative", ""))
            from turn_recovery import remember_commands
            remember_commands(self.state, data)
            chapter_prose = "\n".join(str(row.get("narrative", "")) for row in data.get("updates", []) if isinstance(row, dict) and row.get("type") not in {"system", "meta"}) or data.get("narrative", "")
            chapter = update_chapter_memory(before, self.state, "Advance: " + "; ".join(context.get("actions", [])), chapter_prose, data.get("chapter_recap"))
            if chapter:
                self.append(f"[CHAPTER RECORDED]\n{chapter['title']} is now available in Journal → Chapters.", "meta")
            consolidate_long_campaign_memory(self.state)
            sync_standing_order_lifecycle(
                self.state, self.state.get("standing_orders", []),
                data.get("completed_actions", []), data.get("deferred_actions", []),
                source="time_resolution",
            )
            self.archive_finished_quests()
            # A time skip can end the character's life just as surely as a
            # single action or a combat round can (a failed extreme-danger
            # roll, or the Tower deadline below) — this path never checked
            # for it, so death during an ordinary Advance silently had no
            # death modal at all. Same check apply_resolution already uses.
            died = False
            if self.state.get("hp", 1) <= 0 or not self.state.get("alive", True):
                self.state["hp"] = 0
                self.state["alive"] = False
                died = True
            self.autosave()
        return {"status": "resolved", "narrative": data.get("narrative", ""), "interrupted": interrupted,
                "died": died, "can_rewind": died and bool(self.checkpoints),
                "elapsed": data.get("elapsed", {"amount": requested_amount, "unit": requested_unit}),
                "interruption_reason": data.get("interruption_reason", ""),
                "interruption_kind": data.get("interruption_kind", ""),
                "interruption_user_ids": copy.deepcopy(data.get("interruption_user_ids"))
                if isinstance(data.get("interruption_user_ids"), list) else None,
                "interruption_context": data.get("interruption_context", ""),
                "intervention_prompt": data.get("intervention_prompt", ""),
                "event_notice": copy.deepcopy(data.get("event_notice", {})) if isinstance(data.get("event_notice"), dict) else {},
                "danger_notice_required": danger_notice_required,
                "major_event_reached": bool(data.get("major_event_reached")),
                "consequence_report": consequence_report,
                "major_event_kind": data.get("major_event_kind", ""),
                "major_event_title": data.get("major_event_title", ""),
                "goal_status": data.get("goal_status", {}),
                "rolls": copy.deepcopy(context.get("rolls", [])),
                "notifications": notifications, "state": self.public_state(), "story": self._flush_story(),
                "validation": validation, "continuity_warnings": continuity_warnings,
                "integrity_report": integrity_report,
                "deferred_actions": self.state.get("queued_actions", []),
                "completed_actions": data.get("completed_actions", []), "updates": updates + local_world_events,
                "multiplayer_character_updates": copy.deepcopy(data.get("multiplayer_character_updates", {}))
                if isinstance(data.get("multiplayer_character_updates"), dict) else {}}

    TOWER_FLOOR_DEADLINE_DAYS = 90

    def check_tower_deadline(self, before, elapsed_minutes):
        """Solo Max-Level Newbie only: each floor carries a hard 90-day
        countdown. Resets the moment the AI actually advances tower_floor
        (mechanically, not left to the AI to also self-report the reset —
        the same reasoning as every other hardcoded guarantee in this file).
        Hitting zero is an unavoidable, application-forced death: the doom
        itself must never depend on the AI choosing to narrate/apply it."""
        if self.state.get("world") != "Solo Max-Level Newbie" or self.state.get("tower_over"):
            return
        floor = max(1, int(self.state.get("tower_floor", 1) or 1))
        prior_floor = max(1, int(before.get("tower_floor", 1) or 1))
        deadline = self.state.get("tower_floor_deadline_day")
        if floor > prior_floor or not isinstance(deadline, (int, float)):
            self.state["tower_floor_deadline_day"] = self.state.get("canon_day", 0) + self.TOWER_FLOOR_DEADLINE_DAYS
            return
        if elapsed_minutes >= 1440:
            days_left = max(0, int(deadline - self.state.get("canon_day", 0)))
            self.append(f"[TOWER COUNTDOWN]\n{days_left} day(s) remain before this floor's countdown reaches zero.", "meta")
        if self.state.get("canon_day", 0) >= deadline:
            self.state["tower_over"] = True
            self.state["alive"] = False
            self.state["hp"] = 0
            self.append(
                "[FLOOR COUNTDOWN EXPIRED]\nThe Tower's judgment falls due. Without warning, the floor itself turns against "
                "everyone still standing on it — a purge no strength, plan, or plea can turn aside. There was no surviving this.",
                "danger",
            )

    def canon_countdown(self):
        now = int(self.state.get("canon_time_minutes", self.state.get("canon_day", -7) * 1440 + 480))
        fired = set(self.state.get("canon_events_fired", []))
        upcoming = []
        for event in timeline_for(self.state.get("world", "Custom World")).get("events", []):
            event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
            minute = int(event.get("day", 0)) * 1440 + 480
            if minute > now and event_id not in fired: upcoming.append((minute, event))
        if not upcoming: return {"available": False, "label": "No fixed major canon event remains on the loaded timeline."}
        minute, event = min(upcoming, key=lambda item: item[0])
        delta = minute - now
        days, remainder = divmod(delta, 1440); hours = remainder // 60
        date_str = format_calendar_date(self.state.get("world", "Custom World"), event.get("day", 0), self.state.get("calendar_epoch"), self.state.get("calendar_anchor_day"))
        return {"available": True, "title": event.get("title"), "location": event.get("location"),
                "canon_day": int(event.get("day", 0)), "minutes_until": delta,
                "label": f"{days} days, {hours} hours until {event.get('title')} ({date_str})"}
