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
from portrait_generator import portrait_view, sync_active_portrait_form
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from reliability import update_narrative_memory, record_progression_ledger, advance_hidden_class_discovery
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, ai_text
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks, record_purchase_offer,
                     uses_literal_quests, quest_presentation_for)
from simulation import (advance_npc_intentions, record_simulation_events,
                        normalize_assessment_for_agency)
from world_depth import contextual_opportunities, normalize_world_depth, record_canon_ripples, record_downtime
from simulation_integrity import (register_action_goals, reconcile_action_goals,
                                  validate_turn_response, refresh_npc_schedules,
                                  transmit_information)
from lit_systems import initialize_lit_systems, process_lit_turn
from overgeared_classes import starter_kit_for, class_action_bonus
from jjk_system import advance_jjk_state
from simulation_core import refresh_simulation_core, record_resolution_transaction
from canon_integrity import repair_canon_payload
from world_activity import advance_world_activity, normalize_world_activity
from life_simulation import advance as advance_life_simulation
from world_progression import normalize_world_progression
from campaign_reliability import (
    reconcile_narrated_consequences, consolidate_long_campaign_memory,
    refresh_scene_state, normalize_outcome_scale, reconcile_commitments_and_consequences,
    refresh_canon_divergence_impacts, record_pacing_beat,
)
from simulation_enhancements import record_ability_evolution
from experience_systems import record_world_milestones, update_scenario_memory
from long_campaign import compact_checkpoint_state
from gm_policy import (
    distinct_suggestions, parse_player_intent, record_causal_outcome,
    temporal_budget,
)
from standing_intents import register_standing_intents


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



class TurnsMixin:
    def assess(self, action):
        p = {"task": "assess_action", "action": action, "state": self.trimmed_state_for_ai(),
             "schema": {"requires_check": "bool", "impossible": "bool", "hard_rule_block": "true only for a literal physical, metaphysical, prerequisite, or established-state contradiction; never for NPC reluctance, low odds, canon divergence, rank, or social resistance", "reason": "exact blocking prerequisite/rule and, if fixable, what must change; under 28 words",
                        "prerequisite_track": "object with name/source_feat/status/known_requirements/met_requirements/missing_requirements/next_steps/notes when pursuing a notable capability, otherwise null",
                        "ability": self.ability_enum(), "skill": "name or null",
                        "difficulty_min": "1-100 lower edge for an average relevant character", "difficulty_max": "1-100 upper edge; application randomly samples this range",
                        "relevant_average_stat": "world-relative attribute value of an average relevant character at this era",
                        "situational_bonus": "-20 to 20 for concrete preparation/conditions only",
                        "major_event": "true only for evolutions, transformations, climactic confrontations or irreversible major events",
                        "major_reason": "short reason or empty",
                        "lethal_risk": "none|low|moderate|high|extreme", "lethal_warning": "specific warning or empty, under 20 words",
                        "stakes": "success/failure stakes, under 25 words total"}}
        extra = self.task_context("assessment", action)
        assessment = normalize_assessment_for_agency(
            self.state, action, self.ai.request(extra, p, max_output_tokens=700)
        )
        assessment["action"] = str(action)
        self.last_assessment = copy.deepcopy(assessment)
        return assessment

    def action_explanation(self, action, assessment):
        track = assessment.get("prerequisite_track") if isinstance(assessment.get("prerequisite_track"), dict) else {}
        return {
            "action": action,
            "possible": not bool(assessment.get("impossible")),
            "requires_check": bool(assessment.get("requires_check")),
            "ability": assessment.get("ability") or "None",
            "skill": assessment.get("skill"),
            "difficulty_range": [assessment.get("difficulty_min"), assessment.get("difficulty_max")] if assessment.get("requires_check") else None,
            "relevant_average_stat": assessment.get("relevant_average_stat"),
            "major_event": bool(assessment.get("major_event")),
            "stakes": assessment.get("stakes") or "No exceptional risk identified.",
            "risk": assessment.get("lethal_risk") or "none",
            "reason": assessment.get("reason") or "The action fits the currently known rules.",
            "requirements_met": track.get("met_requirements", []),
            "requirements_missing": track.get("missing_requirements", []),
            "next_steps": track.get("next_steps", []),
            "track_name": track.get("name", ""),
        }

    def preview_action(self, action):
        assessment = self.assess(action)
        self.upsert_prerequisite_track(assessment.get("prerequisite_track"))
        explanation = self.action_explanation(action, assessment)
        self.state.setdefault("diagnostics", {})["last_assessment"] = copy.deepcopy(explanation)
        if assessment.get("impossible"):
            self.autosave()
        return {"assessment": assessment, "explanation": explanation}

    def skill_bonus(self, skill):
        sv = self.state.get("skills", {}).get(skill) if skill else None
        if isinstance(sv, (int, float)): return int(sv)
        if isinstance(sv, dict): return int(sv.get("bonus", sv.get("level", 0)) or 0)
        return 0

    def title_bonus(self):
        titles = self.state.get("titles", [])
        score = 0
        for title in titles:
            if isinstance(title, dict): score += int(title.get("bonus", 2) or 2)
            elif str(title).strip(): score += 2
        return min(30, score)

    @staticmethod
    def bonus_breakdown(ability, stat_bonus, skill, skill_bonus, title_bonus, situational_bonus, lucky_bonus=0, class_bonus=0):
        """Every component feeding a check's total, in the order it's most
        useful to read — only the ones actually doing something, so a
        breakdown never pads itself out with '+0 Luck'."""
        parts = []
        if stat_bonus: parts.append({"label": ability or "Attribute", "value": stat_bonus})
        if skill and skill_bonus: parts.append({"label": skill, "value": skill_bonus})
        if title_bonus: parts.append({"label": "Titles", "value": title_bonus})
        if class_bonus: parts.append({"label": "Class feature", "value": class_bonus})
        if situational_bonus: parts.append({"label": "Situation", "value": situational_bonus})
        if lucky_bonus: parts.append({"label": "Breakthrough", "value": lucky_bonus})
        return parts

    @staticmethod
    def format_bonus_breakdown(parts):
        if not parts: return ""
        return " · ".join(f"{p['label']} {p['value']:+d}" for p in parts)

    def roll(self, assessment, manual_roll=None):
        ability = assessment.get("ability") or abilities_for(self.state.get("world", "Custom World"))[0]
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        benchmark = max(1, int(assessment.get("relevant_average_stat", 30) or 30))
        stat_bonus = int(round((stat - benchmark) / 4.0))
        sk = assessment.get("skill")
        sb, tb = self.skill_bonus(sk), self.title_bonus()
        situational = clamp(int(assessment.get("situational_bonus", 0) or 0), -20, 20)
        class_bonus = class_action_bonus(self.state, assessment.get("action", ""))
        low = assessment.get("difficulty_min")
        high = assessment.get("difficulty_max")
        if low is None or high is None:  # migrate cached v2.4 assessments safely
            legacy = int(assessment.get("base_dc", 15) or 15)
            low, high = legacy * 3 - 5, legacy * 3 + 5
        shift = int(DIFFICULTIES[self.state["difficulty"]].get("difficulty_shift", 0))
        tuning = normalize_tuning(self.state)
        if assessment.get("major_event") or assessment.get("lethal_risk") in {"moderate", "high", "extreme"}:
            shift += int(round((tuning.get("combat_danger", 1.0) - 1.0) * 10))
        low, high = clamp(int(low) + shift, 1, 100), clamp(int(high) + shift, 1, 100)
        if low > high: low, high = high, low
        from turn_recovery import stage
        saved_roll = stage(self, "dice", {"assessment": assessment, "manual": manual_roll, "range": [low, high]})
        if "difficulty" not in saved_roll:
            saved_roll["difficulty"] = random.randint(low, high)
            saved_roll["raw"] = clamp(int(manual_roll), 1, 100) if manual_roll is not None else random.randint(1, 100)
        difficulty, raw = saved_roll["difficulty"], saved_roll["raw"]
        breakthrough = raw >= 99
        lucky_bonus = 15 if breakthrough else 0
        total = raw + stat_bonus + sb + tb + situational + class_bonus + lucky_bonus
        success = total > difficulty
        return {"roll": raw, "chosen": raw, "mode": "manual" if manual_roll is not None else "automatic",
                "ability": ability, "ability_value": stat, "relevant_average_stat": benchmark,
                "stat_bonus": stat_bonus, "skill": sk, "skill_bonus": sb, "title_bonus": tb,
                "situational_bonus": situational, "class_feature_bonus": class_bonus, "lucky_bonus": lucky_bonus, "total": total,
                "difficulty": difficulty, "difficulty_range": [low, high], "success": success,
                "breakthrough": breakthrough,
                "bonus_breakdown": self.bonus_breakdown(ability, stat_bonus, sk, sb, tb, situational, lucky_bonus, class_bonus)}

    @staticmethod
    def format_roll_summary(action, result):
        """One readable d100 line that can never lose its associated action."""
        bonus = int(result.get("total", 0)) - int(result.get("roll", 0))
        needed = int(result.get("difficulty", 0)) + 1  # checks succeed strictly above difficulty
        outcome = "SUCCESS" if result.get("success") else "FAILURE"
        if result.get("breakthrough") and result.get("success"):
            outcome = "BREAKTHROUGH"
        mode = str(result.get("challenge_mode") or "").lower()
        prefix = "Timing " if mode == "timing" else "Tactical " if mode == "tactical" else ""
        action_text = re.sub(r"([.!?])\1+$", r"\1", str(action or "Uncertain action").strip())
        return (f"{action_text} — {prefix}{int(result.get('roll', 0))} {bonus:+d} = "
                f"{int(result.get('total', 0))}/100 vs. {needed} needed — {outcome}")

    def preview_check(self, check, assessment=None, action=""):
        """Explain expected d100 pressure before the simulation can advance."""
        assessment = assessment if isinstance(assessment, dict) else {}
        ability = check.get("ability") or abilities_for(self.state.get("world", "Custom World"))[0]
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        benchmark = max(1, int(check.get("relevant_average_stat", 30) or 30))
        stat_bonus = int(round((stat - benchmark) / 4.0))
        skill_bonus = self.skill_bonus(check.get("skill"))
        title_bonus = self.title_bonus()
        situational = clamp(int(check.get("situational_bonus", 0) or 0), -20, 20)
        class_bonus = class_action_bonus(self.state, action or check.get("action", ""))
        known_bonus = stat_bonus + skill_bonus + title_bonus + situational + class_bonus
        low, high = check.get("difficulty_min"), check.get("difficulty_max")
        if low is None or high is None:
            legacy = int(check.get("base_dc", 15) or 15)
            low, high = legacy * 3 - 5, legacy * 3 + 5
        time_modifier = int(check.get("time_difficulty_modifier", 0) or 0)
        if not time_modifier:
            time_modifier = int(check.get("time_dc_modifier", assessment.get("time_budget", {}).get("time_dc_modifier", 0)) or 0) * 3
        shift = int(DIFFICULTIES[self.state["difficulty"]].get("difficulty_shift", 0))
        tuning = normalize_tuning(self.state)
        if check.get("major_event") or check.get("lethal_risk") in {"moderate", "high", "extreme"}:
            shift += int(round((tuning.get("combat_danger", 1.0) - 1.0) * 10))
        low, high = clamp(int(low) + time_modifier + shift, 1, 100), clamp(int(high) + time_modifier + shift, 1, 100)
        if low > high: low, high = high, low
        raw_needed = max(1, min(101, int(round(((low + high) / 2) + 1 - known_bonus))))
        breakdown = self.bonus_breakdown(ability, stat_bonus, check.get("skill"), skill_bonus, title_bonus, situational, 0, class_bonus)
        return {"id": str(check.get("id") or check.get("reason") or "check"), "action": str(action or check.get("reason") or "Uncertain action"),
                "reason": str(check.get("reason") or "Uncertain outcome"), "ability": ability, "skill": check.get("skill"),
                "difficulty_range": [low + 1, high + 1], "known_bonus": known_bonus, "expected_raw_needed": raw_needed,
                "bonus_breakdown": breakdown,
                "risk": check.get("lethal_risk", "none"), "major_event": bool(check.get("major_event")),
                "difficult": raw_needed >= int(tuning.get("check_warning_threshold", 65)),
                "odds_percent": max(0, min(100, round((101 - raw_needed))))}

    def resolve(self, action, assessment, roll_result):
        p = {"task": "narrator_and_resolution", "role": "Narrator + Rules Referee", "action": action,
             "assessment": assessment, "dice_result": roll_result, "state_before": self.task_state_for_ai("moment", action),
             "intent_contract": parse_player_intent(action, self.state),
             "temporal_budget": temporal_budget("moment"),
             "schema": {"narrative": "1 short paragraph, 2-5 sentences — a few sentences is enough, only go longer for a genuinely major moment",
                        "world_plan_updates": "Optional commands following world_plan_context; omit unchanged plans.",
                        "state_patch": "ALL persistent changes including combat, npc_memories, shops, hidden_quests, ability_progress, world time, sublocations, and portrait_traits when applicable",
                        "consequence_manifest": [{"kind":"skill|title|item|quest|location|condition|reputation|affiliation|other", "target":"exact name", "change":"gained|lost|started|completed|changed", "evidence":"short sentence from this result", "details":"complete skill mechanics only when kind is skill"}],
                        "commitment_updates": [{"owner":"who made the promise/debt", "owed_to":"who expects it", "promise":"specific commitment", "due_canon_day":"integer or empty", "trigger":"condition or empty", "status":"active|fulfilled|broken|cancelled", "consequence":"what follows if relevant"}],
                        "delayed_consequences": [{"effect":"specific later consequence", "source":"decision/event causing it", "horizon":"days|weeks|months|conditional", "due_canon_day":"integer or empty", "trigger":"condition or empty"}],
                        "ability_developments": [{"ability":"existing ability name", "kind":"application|mastery|breakthrough|evolution", "development":"specific lasting development", "application":"new named or practical application, or empty", "evidence":"what caused it"}],
                        "causal_outcome": {"direct_result":"what the action accomplished before reactions", "witnesses":["only people or channels that actually perceived it"], "reactions":[{"actor":"named informed person/faction", "response":"their causal response", "knowledge_source":"witness|conversation|message|report|rumor|research|ability"}], "costs":[{"cost":"real cost", "cause":"why it was paid"}], "complications":[{"effect":"one supported setback at most", "cause":"specific established cause"}]},
                        "information_events": [{"fact":"what became known", "source":"actual source", "channel":"witness|conversation|letter|message|rumor|report|broadcast|ability|research", "recipients":["named recipients"], "delay_minutes":"nonnegative integer", "confidence":"0-100"}],
                        "danger_scenario_concluded": "boolean; true only when the current confrontation ended or the player left it",
                        "events": [{"type": "xp|level_up|skill|title|quest|hidden_quest|item|loot|reputation|companion|codex|location|training|combat|injury|death|discovery|world", "message": "notification"}],
                        "timeline_event": "major event or empty", "suggested_actions": ["exactly 3 optional contextual actions: strongest lead, growth/preparation, alternate hook. Each must name a real, specific person/place/faction/thread already in this campaign, not a generic template. Scale honestly — a longer-term lead can openly say so ('over the next few days...') rather than being forced into an instant."]}}
        rules = self.task_context("moment", action) + " Resolve strictly from dice_result when present. Never hide progression in narration. List every lasting narrated gain, loss, condition, quest, title, item, skill, affiliation or location change in consequence_manifest even when state_patch also contains it. Set danger_scenario_concluded=true only when the confrontation is truly over or the player leaves it."
        return self.request_with_narrative(rules, p, 1300)

    def take_turn(self, action, confirmed_lethal=False, cached_assessment=None):
        """Full assess -> (maybe roll) -> resolve pipeline for one player action.
        Returns a dict describing what happened, including a lethal-confirmation
        gate the frontend must resolve before the turn is allowed to proceed.
        When the player confirms a lethal action, the frontend sends back the
        exact assessment it was shown so we never silently re-roll the GM's
        judgement of the danger."""
        from naruto_tactics import require_narrative_available
        require_narrative_available(self.state)
        register_standing_intents(self.state, [action])
        assessment = normalize_assessment_for_agency(
            self.state, action, cached_assessment or self.assess(action)
        )
        assessment["action"] = str(action)
        self.last_assessment = copy.deepcopy(assessment)
        self.upsert_prerequisite_track(assessment.get("prerequisite_track"))
        if assessment.get("impossible"):
            self.append("> " + str(action), "player")
            self.append("[ACTION NOT POSSIBLE]\n" + assessment.get("reason", "Impossible under current conditions."), "meta")
            self.autosave()
            return {"status": "impossible", "reason": assessment.get("reason", ""),
                    "action_explanation": self.action_explanation(action, assessment), "story": self._flush_story()}
        if assessment.get("lethal_risk") in ("high", "extreme") and not confirmed_lethal:
            return {"status": "lethal_confirm_required", "assessment": assessment}
        with self.lock:
            self.checkpoints.append(compact_checkpoint_state(self.state))
            self.checkpoints = self.checkpoints[-12:]
        # The action always gets its own Chronicle line first — a roll (if
        # any) attaches to it visually as a compact inline result, and the
        # narrative that follows never has to re-state what was attempted.
        self.append("> " + str(action), "player")
        roll_result = None
        if assessment.get("requires_check"):
            roll_result = self.roll(assessment)
            self.append(self.format_roll_summary(action, roll_result), "roll")
        data = self.resolve(action, assessment, roll_result)
        result = self.apply_resolution(data, is_opening=False, pending_action=action,
                                       progression_context={"actions": [action], "rolls": [roll_result] if roll_result else [], "elapsed_minutes": 5})
        result["assessment"] = assessment
        result["action_explanation"] = self.action_explanation(action, assessment)
        result["roll"] = roll_result
        result["status"] = "resolved"
        return result

    def event_window_rules(self):
        """Scoped GM instructions for one beat inside an already-active major
        event — the player still needs the full world/ability/combat rules
        to narrate consistently, but the SCENE must stay sealed to this
        event: no wider-world advancement, no unrelated locations, and
        critically, no time/calendar movement at all (this is a single
        in-the-moment exchange, resolved exactly like any ordinary action)."""
        title = str(self.state.get("active_canon_event") or "this event").strip()
        context = str(self.state.get("interruption_context") or "").strip()
        return f"""

YOU ARE CURRENTLY RESOLVING A LIVE MAJOR EVENT SCENE, ONE BEAT AT A TIME — NOT A TIME SKIP.
EVENT: {title}
EVENT CONTEXT: {context or 'The player is directly engaged in this unfolding event.'}
- Stay entirely inside this event's scene — its location, its immediate participants, its unfolding action. Do not narrate unrelated locations, unrelated threads, or the wider world advancing; the rest of the world resumes only once this event concludes.
- This is a real choose-your-own-adventure exchange: present what is happening concretely, react directly and specifically to exactly what the player just said or did, and always offer real, situation-specific suggested_actions — never generic filler.
- Resolve the player's stated action as something that actually happens this beat, not something merely attempted or prepared — a fast-moving live scene like this one is exactly where hedging ("you prepare to...", "you move to try...") reads worst. If it can plausibly succeed outright, it does; if something genuinely stops it, say concretely what happened instead. Never end a beat with the player's clear action left unresolved.
- This should read as a substantial scene, not a one-shot — expect several back-and-forth exchanges before it naturally concludes. Do not set event_concluded after a single beat unless the player's own action genuinely ends it right there.
- If the player's stated action itself declares an intent to carry through to this event's actual end — "I do X until the attack is over," "I keep helping until things settle," "I hold this position for the rest of the fight" — that is explicit authorization to advance straight through the scene's remaining beats and resolve it to its real conclusion in THIS response, not one more incremental check-in. Narrate the intervening span at a summary pace (what they did, what changed, how it wound down) the same way a time skip would, then land on the actual ending and set event_concluded=true. Manufacturing another "what do you do now?" prompt when the player already told you to keep going until a specific endpoint is a failure to honor their input, not thoroughness.
- Never repeat or lightly reword a beat the player has already been given — if their input doesn't change anything material, that itself is a reason to move the scene forward (time passing, the situation shifting, a new development) rather than re-presenting the same moment.
- Set event_concluded=true only when: (a) the scene has genuinely reached its real conclusion (the confrontation/moment is resolved, one way or another), or (b) the player's stated action clearly disengages from the event — fleeing, leaving the area, refusing to get involved, hiding, or similar. For (b), event_conclusion_summary must plainly state that the player left or avoided the event and how, so the very next turn picks up from exactly that reality (they were not present for whatever happened next, and only learn of the outcome secondhand later, if at all).
- If the scene turns physical, use structured combat (state_patch.combat) exactly as you normally would — the player can also flee a fight via the combat controls, which should likewise end the event.
- Never advance world_time, world_clock_minutes, canon_day, or the calendar here — the application does not permit it for this exchange regardless of what you write.
Return ONLY valid JSON."""

    @staticmethod
    def _wants_event_resolution(action_text):
        """Detects a player explicitly signaling they want to keep acting
        all the way through to this event's actual conclusion ("I help
        people until the attack is over") rather than getting one more
        incremental beat. A general instruction buried in event_window_rules
        proved unreliable on its own — the same lesson already learned from
        _same_place and the power-goal mechanic — so this drives an
        explicit, unambiguous per-turn directive instead of hoping the
        model notices a general rule on its own."""
        text = str(action_text or "").lower()
        if "until" not in text and "till" not in text and "for the rest of" not in text:
            return False
        endpoint_words = ("over", "done", "end", "ends", "ended", "settle", "settled", "resolved",
                           "resolves", "safe", "clear", "clears", "passes", "subsides", "finished", "through")
        return "for the rest of" in text or any(w in text for w in endpoint_words)

    def respond_to_event(self, action):
        """Resolve one beat of the currently active major event. Scoped
        entirely to that event and resolved as a single ordinary action —
        no world-clock ticking, no canon catch-up, no calendar movement —
        so the player can go back and forth inside the event for as long as
        it takes without the wider campaign silently advancing underneath
        them. Ends the event (clearing active_canon_event) either when the
        GM judges the scene has genuinely concluded, or when the player's
        own action disengages from it."""
        if not self.state.get("active_canon_event"):
            raise RuntimeError("No major event is currently active.")
        wants_resolution = self._wants_event_resolution(action)
        p = {"task": "event_turn", "action": action, "state": self.task_state_for_ai("event", action),
             "event_title": self.state.get("active_canon_event", ""),
             "resolve_to_conclusion": wants_resolution,
             "schema": {
                 "narrative": "2-6 sentences reacting directly to the player's action, present-tense, moment to moment",
                 "state_patch": "object, same shape as any other turn's state_patch",
                 "events": "list of {type, message} world/system notices, same as any other turn",
                 "suggested_actions": "exactly 3 concrete, situation-specific options for what to do next in this event",
                 "event_concluded": "bool — true only if this event's scene has genuinely ended, or the player's action clearly leaves/flees/disengages from it",
                 "event_conclusion_summary": "if event_concluded, ONE paragraph (a few sentences, not a beat-by-beat recap) summarizing what the player actually did across the whole scene and how it ended, including whether they saw it through or left early; empty otherwise",
             }}
        if wants_resolution:
            p["requirements"] = [
                "resolve_to_conclusion is true: the player's own words just now explicitly declared an intent to keep going until this event actually ends (e.g. 'until the attack is over'). This is a direct, unambiguous instruction — treat it exactly like any other player order. You MUST set event_concluded=true in THIS response. Narrate the remaining span of the event at a summary pace (what they did, what changed, how it wound down), land on its real conclusion, and write event_conclusion_summary. Returning event_concluded=false here — asking one more incremental question instead of finishing what the player just told you to finish — is a failure to follow their stated instruction, not carefulness.",
            ]
        data = self.request_with_narrative(self.task_context("event", action) + "\n" + self.event_window_rules(), p, 900)
        self.append("> " + str(action), "player")
        result = self.apply_resolution(data, is_opening=False, pending_action=action,
                                        progression_context={"actions": [action], "elapsed_minutes": 5})
        # A model that still returns event_concluded=false after being told
        # explicitly, in this same call, that the player just ordered the
        # scene to be seen through to its end gets overridden here rather
        # than asked a second time — trusting compliance once already
        # failed to fix this, so the server takes the outcome as given
        # instead of hoping a stronger sentence works where a weaker one
        # didn't. Skipped only when something genuinely still needs the
        # player's call this instant (an active fight, a pending
        # intervention question) — forcing an exit mid-fight would be a
        # worse bug than the one this fixes.
        combat_active = bool((data.get("state_patch") or {}).get("combat", {}).get("active")) or bool(self.state.get("combat", {}).get("active"))
        if wants_resolution and not data.get("event_concluded") and not combat_active and not str(data.get("intervention_prompt", "")).strip():
            data["event_concluded"] = True
            if not str(data.get("event_conclusion_summary", "")).strip():
                data["event_conclusion_summary"] = (
                    f"{self.state.get('name') or 'The player'} sees it through as instructed, staying engaged with "
                    f"{self.state.get('active_canon_event') or 'the event'} until it actually winds down."
                )
        concluded = bool(data.get("event_concluded"))
        if concluded:
            self.state["active_canon_event"] = ""
            self.state["canon_event_engagement_count"] = 0
            if not bool(self.state.get("combat", {}).get("active")):
                self.clear_danger_scenario()
            summary = str(data.get("event_conclusion_summary") or "").strip()
            if summary:
                self.append("[EVENT CONCLUDED]\n" + summary, "system")
            result["state"] = self.public_state()
            result["story"] = self._flush_story()
        result["event_concluded"] = concluded
        return result

    def upsert_prerequisite_track(self, track):
        if not isinstance(track, dict) or not str(track.get("name", "")).strip():
            return
        clean = copy.deepcopy(track)
        clean["name"] = str(clean["name"]).strip()
        clean.setdefault("source_feat", clean["name"])
        clean.setdefault("status", "in_progress")
        for key in ("known_requirements", "met_requirements", "missing_requirements", "next_steps"):
            value = clean.get(key, [])
            clean[key] = value if isinstance(value, list) else [str(value)] if value else []
        clean.setdefault("notes", "")
        tracks = self.state.setdefault("prerequisite_tracks", [])
        needle = clean["name"].lower()
        for index, existing in enumerate(tracks):
            if isinstance(existing, dict) and str(existing.get("name", "")).lower() == needle:
                tracks[index] = clean
                break
        else:
            tracks.append(clean)
        self.state["prerequisite_tracks"] = tracks[-24:]

    def append_growth_deltas(self, before):
        """Inline Chronicle callout for stat/pool growth, e.g. 'Strength
        44->46' — the same visibility a d100 roll line already gets. Without
        this, training/growth only shows up buried in Journal -> Progression,
        which is easy to miss turn-to-turn."""
        def fmt(n):
            return int(n) if float(n) == int(n) else round(float(n), 1)
        lines = []
        before_stats, after_stats = before.get("stats", {}) or {}, self.state.get("stats", {}) or {}
        for name, after_val in after_stats.items():
            prior = before_stats.get(name)
            try:
                prior, after_val = float(prior), float(after_val)
            except (TypeError, ValueError):
                continue
            if after_val > prior:
                lines.append(f"{name} {fmt(prior)}→{fmt(after_val)} (+{fmt(after_val - prior)})")
        for label, key in (("Max HP", "hp_max"), (f"Max {self.state.get('resource_name', 'Resource')}", "resource_max")):
            prior, after_val = before.get(key), self.state.get(key)
            if prior is None or after_val is None or after_val <= prior:
                continue
            lines.append(f"{label} {fmt(prior)}→{fmt(after_val)} (+{fmt(after_val - prior)})")
        if lines:
            self.append("[GROWTH]\n" + "\n".join(lines), "meta")

    def append_training_summary(self, before, actions, elapsed_minutes, rolls=None):
        """Readable proportional report for any meaningful training span."""
        actions = [str(x).strip() for x in (actions or []) if str(x).strip()]
        training = [x for x in actions if re.search(r"\b(train|practice|study|research|craft|forge|learn|master)\b", x, re.I)]
        if not training or int(elapsed_minutes or 0) < 360:
            return None
        days = max(.25, float(elapsed_minutes) / 1440.0)
        changes = []
        for name, value in (self.state.get("stats", {}) or {}).items():
            try:
                delta = float(value) - float((before.get("stats", {}) or {}).get(name, value))
            except (TypeError, ValueError):
                continue
            if delta > 0:
                changes.append(f"{name} increased by {round(delta, 1)}")
        gained = sorted(set(self.state.get("skills", {})) - set(before.get("skills", {})))
        failures = [r for r in (rolls or []) if isinstance(r, dict) and not r.get("success")]
        breakthroughs = [x for x in (self.state.get("progression_log", []) or [])[-len(training):] if isinstance(x, dict) and x.get("breakthrough")]
        lines = [f"{round(days, 1)} day(s) of sustained effort were simulated across {len(training)} training goal(s)."]
        lines += [f"• {x}" for x in changes[:8]]
        lines += [f"• Learned: {x}" for x in gained[:6]]
        if failures:
            lines.append(f"• Remaining weakness: {failures[0].get('reason') or failures[0].get('action') or 'the failed milestone exposed a gap in execution'}")
        if breakthroughs:
            lines.append("• Unexpected development: a lore-consistent breakthrough accelerated the normal gain.")
        if len(lines) == 1:
            lines.append("• The work accumulated as partial proficiency even though no visible stat crossed its next threshold yet.")
        self.state["last_training_summary"] = {"days": round(days, 2), "actions": training, "lines": lines[1:]}
        self.append("[TRAINING REPORT]\n" + "\n".join(lines), "meta")
        return self.state["last_training_summary"]

    def apply_jjk_turn_effects(self, before, actions, narrative, events, elapsed_minutes=5):
        """Persist the complete JJK development record after a resolved beat."""
        return advance_jjk_state(self.state, before, actions, narrative, events, elapsed_minutes)

    def apply_resolution(self, data, is_opening=False, pending_action=None, progression_context=None):
        with self.lock:
            data, canon_repairs = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
            before = copy.deepcopy(self.state)
            danger_was_active = self.danger_scenario_active(before)
            context = progression_context if isinstance(progression_context, dict) else {}
            turn_actions = context.get("actions", []) if isinstance(context.get("actions", []), list) else []
            if pending_action and not turn_actions: turn_actions = [pending_action]
            if not is_opening:
                register_action_goals(self.state, turn_actions)
                self.ensure_immediate_combat_patch(data, turn_actions)
                data, integrity_report = validate_turn_response(
                    before, data, turn_actions, context.get("rolls", []),
                    int(context.get("elapsed_minutes", 5) or 5), [],
                )
            else:
                integrity_report = {}
            validation = apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="opening" if is_opening else "turn")
            self.ensure_combat_numbers()
            combat_now = bool(isinstance(self.state.get("combat"), dict) and self.state.get("combat", {}).get("active"))
            if not is_opening and data.get("danger_scenario_concluded") and not combat_now:
                self.clear_danger_scenario()
            elif not is_opening and combat_now:
                self.acknowledge_danger_scenario(data.get("narrative") or "Combat")
            elif not is_opening and danger_was_active:
                action_text = " ".join(str(x) for x in turn_actions if str(x).strip())
                location_changed = str(before.get("location") or "").strip().lower() != str(self.state.get("location") or "").strip().lower()
                if location_changed or self._DANGER_EXIT_RE.search(action_text):
                    self.clear_danger_scenario()
            # A narrator may enrich an original character during the opening, but a
            # canon start already has authoritative identity and mechanical facts.
            # Reapply the trusted pre-opening values so a generic response cannot
            # quietly turn Yahiko into a different age, mentor, faction, class, or
            # starting location while still allowing scene/lead additions.
            if is_opening and (before.get("player_identity", {}) or {}).get("mode") == "canon":
                canon_locked = (
                    "name", "age", "background", "appearance_desc", "portrait_traits",
                    "origin", "race", "location", "canon_day", "start_day", "position",
                    "affiliations", "reputation", "skills", "titles", "stats",
                    "hp", "hp_max", "resource", "resource_max", "companions",
                    "npc_memories", "contacts", "faction_rosters", "class_profile",
                    "special", "player_identity",
                )
                for field in canon_locked:
                    if field in before:
                        self.state[field] = copy.deepcopy(before[field])
            if not uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")):
                self.state["xp"], self.state["level"], self.state["xp_next"] = before.get("xp", 0), before.get("level", 1), before.get("xp_next", 100)
            else:
                self.apply_system_xp(before, context.get("actions", []) if not is_opening else [], context.get("rolls", []),
                                     context.get("elapsed_minutes", 5), context.get("intensity", "normal"), data.get("events", []))
            if not is_opening:
                self.reconcile_title_events(data.get("events", []))
                for note in self.apply_jjk_turn_effects(before, turn_actions, data.get("narrative", ""), data.get("events", []), context.get("elapsed_minutes", 5)):
                    self.append(f"[JUJUTSU RECORD]\n{note}", "system")
                sync_active_portrait_form(self.state, turn_actions, data.get("narrative", ""), data.get("events", []))
            self.sync_derived_pools(before)
            if is_opening:
                initialize_lit_systems(self.state)
                normalize_world_activity(self.state)
                lit_notes = []
            else:
                lit_notes = process_lit_turn(
                    before, self.state, turn_actions, data.get("narrative", ""),
                    context.get("elapsed_minutes", 5),
                )
            activity_notes = [] if is_opening else advance_world_activity(
                self.state, before, turn_actions, data.get("narrative", ""), data.get("events", []),
                context.get("elapsed_minutes", 5),
            )
            consequence_report = {"checked": 0, "repairs": 0, "warnings": []} if is_opening else reconcile_narrated_consequences(
                before, self.state, data, turn_actions, context.get("elapsed_minutes", 5),
            )
            # "turn" is an app-controlled counter, never an AI-authored field —
            # a state_patch that happens to include one (models sometimes do)
            # must not be allowed to set it.
            self.state["turn"] = before.get("turn", 0) if is_opening else before.get("turn", 0) + 1
            if is_opening:
                self.state["opening_complete"] = True
            tev = data.get("timeline_event", "")
            if tev:
                self.state.setdefault("timeline", []).append(tev)
            self.state["suggested_actions"] = self.guided_suggestions(data.get("suggested_actions"))
            offer_detail = record_purchase_offer(self.state)
            self.append(data.get("narrative", "The scene advances."), detail=({"purchase_offer": offer_detail} if offer_detail else None))
            if lit_notes:
                heading = "SATISFY SYSTEM" if self.state.get("world") == "Overgeared" else "TOWER SYSTEM"
                self.append(f"[{heading}]\n" + "\n".join(lit_notes), "system")
            if activity_notes:
                self.append("[WORLD DEVELOPMENT]\n" + "\n".join(activity_notes), "system")
            record_simulation_events(self.state,
                                     [{"type": "action", "narrative": data.get("narrative", "")}]
                                     + list(data.get("events", []) or []), "narrator")
            advance_npc_intentions(self.state, 5, self.simulation_mode())
            refresh_npc_schedules(self.state, 5)
            transmit_information(self.state, data, 5)
            record_causal_outcome(self.state, data, turn_actions, int(context.get("elapsed_minutes", 5) or 5))
            if not is_opening:
                from living_world import advance as advance_living_world, record_outcome as record_living_outcome
                from relationship_life import resolve as resolve_relationships
                relationship_messages = resolve_relationships(before, self.state, data)
                living = advance_living_world(self.state, turn_actions, int(context.get("elapsed_minutes", 5) or 5), data.get("events", []), data.get('world_plan_updates'))
                record_living_outcome(self.state, data, turn_actions)
                for event in living.get("events", []):
                    data.setdefault("events", []).append(event)
                    from chronicle_prose import beat_body
                    self.append(f"[LIVING WORLD — {event.get('title', 'FOLLOW-UP')}]\n{beat_body(event)}", "system")
                for message in [*living.get("incoming_chats", []), *relationship_messages]:
                    thread = message.get("thread") or message.get("sender")
                    if thread:
                        self.ensure_contact(thread)
                        self.add_chat_message(thread, message.get("sender"), message.get("message", ""), "incoming", message.get("metadata"))
                from arc_director import advance as advance_campaign_arcs
                arc_result = advance_campaign_arcs(self.state, turn_actions, data.get("events", []), int(context.get("elapsed_minutes", 5) or 5))
                for beat in arc_result.get("beats", []):
                    data.setdefault("events", []).append(beat)
                    self.append(f"[{beat.get('title', 'CAMPAIGN ARC')}]\n{beat.get('narrative', '')}", "system")
                life_result = advance_life_simulation(
                    self.state, turn_actions,
                    [*data.get("events", []), *living.get("events", []), *arc_result.get("beats", [])],
                    int(context.get("elapsed_minutes", 5) or 5),
                )
                for beat in life_result.get("events", []):
                    data.setdefault("events", []).append(beat)
                    self.append(f"[LIFE — {beat.get('title', 'DEVELOPMENT')}]\n{beat.get('narrative', '')}", "system")
            if canon_repairs:
                integrity_report.setdefault("repairs", []).extend(canon_repairs)
            if integrity_report:
                self.state.setdefault("simulation_validation", []).append(copy.deepcopy(integrity_report))
                self.state["simulation_validation"] = self.state["simulation_validation"][-100:]
                reconcile_action_goals(self.state, [], data, 5)
            if not is_opening:
                self.append_growth_deltas(before)
            self.ensure_quest_briefings(before, " ".join(
                part for part in (str(pending_action or "").strip(), str(data.get("narrative") or "").strip()) if part
            ))
            normalize_quest_state_machine(self.state)
            if not is_opening:
                advance_hidden_class_discovery(self.state, pending_action or "")
                record_progression_ledger(
                    before, self.state, pending_action or "Story development",
                    context.get("elapsed_minutes", 5), context.get("rolls", []),
                )
                record_ability_evolution(before, self.state, data, turn_actions)
            from director import build_cause_effect, maybe_offer_relationship_scene, update_campaign_direction
            relationship_offer = None if is_opening else maybe_offer_relationship_scene(self.state, data.get("events", []))
            if relationship_offer:
                self.state["suggested_actions"] = self.guided_suggestions([relationship_offer["prompt"], *self.state.get("suggested_actions", [])])
                self.append(f"[OPTIONAL CHARACTER MOMENT — {relationship_offer['npc']}]\n{relationship_offer['reason']} This is optional; time will not move until you choose and Advance.", "meta")
            update_campaign_direction(self.state, turn_actions, data.get("events", []), 0 if is_opening else int(context.get("elapsed_minutes", 5) or 5))
            normalize_world_depth(self.state, before)
            record_canon_ripples(self.state, data.get("events", []))
            if not is_opening:
                record_downtime(self.state, turn_actions, int(context.get("elapsed_minutes", 5) or 5))
            build_cause_effect(before, self.state, turn_actions, context.get("rolls", []))
            update_narrative_memory(
                before, self.state,
                pending_action or ("Campaign opening" if is_opening else "Story development"),
                data.get("narrative", ""),
            )
            reconcile_commitments_and_consequences(
                self.state, data, 0 if is_opening else int(context.get("elapsed_minutes", 5) or 5),
            )
            from organizations import process_organizations
            for organization_event in process_organizations(before, self.state, data, 0 if is_opening else int(context.get("elapsed_minutes", 5) or 5)):
                self.append(organization_event["narrative"], "narrative")
            refresh_canon_divergence_impacts(self.state)
            refresh_scene_state(self.state, data, turn_actions)
            if not is_opening:
                record_pacing_beat(self.state, data, turn_actions)
                normalize_outcome_scale(before, self.state, data, int(context.get("elapsed_minutes", 5) or 5))
            prior_warnings = set(before.get("continuity_ledger", {}).get("warnings", []))
            continuity_warnings = update_continuity(before, self.state, pending_action or ("campaign opening" if is_opening else ""), data.get("narrative", ""))
            # The current result has now entered campaign_canon.  Re-run the
            # zero-cost world mirror so a narratively acquired Sharingan (or
            # another dedicated world-system power) appears in its panel on
            # this same response instead of waiting for a reload/next turn.
            normalize_world_progression(self.state, before)
            for note in self.state.pop("_pending_chronicle_notes", []):
                self.append(note, "meta")
            # apply_time_skip has always acted on these (see its own call to
            # request_continuity_correction below); a regular single-action
            # turn computed the exact same warnings but never did anything
            # with them beyond returning them in the response, which nothing
            # on the frontend even reads — a real transaction/state slip on
            # an ordinary turn (the far more common turn type) silently went
            # uncorrected forever. Same new-warnings-only diff as the skip
            # path, so an already-known, still-unresolved warning doesn't
            # trigger a fresh correction call on every subsequent turn.
            new_warnings = [w for w in continuity_warnings if w not in prior_warnings]
            if new_warnings:
                self.request_continuity_correction(new_warnings, data.get("narrative", ""))
            self.archive_finished_quests()
            refresh_simulation_core(
                self.state, turn_actions,
                0 if is_opening else int(context.get("elapsed_minutes", 5) or 5),
                pending_action or "",
            )
            if not is_opening:
                usage = copy.deepcopy(getattr(self, "_last_request_usage", {}))
                self.state["last_ai_route"] = {"role": "Main GM", "model": usage.get("model") or self.settings.get("model", ""),
                                               "turn": self.state.get("turn", 0), **usage}
                update_scenario_memory(before, self.state, turn_actions, data)
                for milestone in record_world_milestones(self.state, data):
                    self.append(f"[{milestone['heading']}]\n{milestone['title']}: {milestone['detail']}", "system")
                record_resolution_transaction(
                    self.state, before, turn_actions,
                    int(context.get("elapsed_minutes", 5) or 5),
                    data.get("narrative", ""), context.get("rolls", []),
                )
            notifications = self.notify(before, self.state, data.get("events", []))
            if not is_opening:
                self.history.append({"turn": self.state["turn"], "action": pending_action, "time": datetime.now().isoformat(timespec="seconds")})
                from turn_recovery import remember_commands
                remember_commands(self.state, data)
                chapter = update_chapter_memory(before, self.state, pending_action, data.get("narrative", ""), data.get("chapter_recap"))
                if chapter:
                    self.append(f"[CHAPTER RECORDED]\n{chapter['title']} is now available in Journal → Chapters.", "meta")
                consolidate_long_campaign_memory(self.state)
            self.autosave()
            died = False
            if self.state.get("hp", 1) <= 0 or not self.state.get("alive", True):
                self.state["hp"] = 0
                self.state["alive"] = False
                died = True
        return {
            "narrative": data.get("narrative", ""),
            "notifications": notifications,
            "state": self.public_state(),
            "died": died,
            "can_rewind": died and bool(self.checkpoints),
            "story": self._flush_story(),
            "validation": validation,
            "integrity_report": integrity_report,
            "continuity_warnings": continuity_warnings,
            "consequence_report": consequence_report,
        }

    def _suggestion_is_current(self, value):
        """Reject locally provable stale/impossible suggestion text.

        The model still writes the interesting options.  This guard only
        removes contradictions the application can know with certainty:
        traveling to the place already occupied, continuing a combat that has
        mechanically ended, or contacting a person never established in the
        campaign.  It prevents old campaign-direction hints from becoming a
        self-reinforcing loop across later turns.
        """
        text = ai_text(value)
        if not text:
            return False
        lower = text.lower()
        location = str(self.state.get("location") or "").strip()
        if location and re.search(rf"\b(?:travel|return|go|sail|walk|head)\s+to\s+(?:the\s+)?{re.escape(location)}\b", text, re.I):
            return False

        combat = self.state.get("combat") if isinstance(self.state.get("combat"), dict) else {}
        if combat and not combat.get("active") and combat.get("outcome"):
            enemy = str((combat.get("enemy") or {}).get("name") or "").strip().lower()
            immediate_combat = bool(re.search(
                r"\b(win or escape|escape the fight|continue the fight|rush|finish off|defeat|attack|strike|disable)\b",
                lower,
            ))
            reframed = bool(re.search(r"\b(return|re-?engage|prepare|plan|recover|recruit|track|negotiate|investigate)\b", lower))
            if immediate_combat and not reframed and (not enemy or enemy in lower or "fight" in lower):
                return False

        # "Reach out to X" should only survive when X is a real known contact,
        # companion, or remembered NPC.  Generic invented names were otherwise
        # able to appear as confident next-step buttons.
        match = re.match(r"\s*(?:reach out to|contact|message|call)\s+(.+?)(?:\s+and\b|\s+to\b|[.,;]|$)", text, re.I)
        if match:
            target = match.group(1).strip().lower()
            known = {str(name).strip().lower() for name in (self.state.get("contacts") or {}).keys()}
            known.update(str(name).strip().lower() for name in (self.state.get("npc_memories") or {}).keys())
            known.update(str(row.get("name") if isinstance(row, dict) else row).strip().lower()
                         for row in (self.state.get("companions") or []))
            if target and target not in known:
                return False
        return True

    def guided_suggestions(self, authored=None):
        """Guarantee three optional, state-grounded leads even when a model
        forgets or truncates its suggestion field."""
        suggestions = []
        for value in authored or []:
            text = ai_text(value)
            if self._suggestion_is_current(text) and text.lower() not in {x.lower() for x in suggestions}:
                suggestions.append(text[:180])
        for opportunity in reversed(self.state.get("relationship_opportunities", [])):
            if isinstance(opportunity, dict) and opportunity.get("status") == "available" and opportunity.get("prompt"):
                suggestions.append(str(opportunity["prompt"])[:180])
                break
        direction = self.state.get("campaign_direction") if isinstance(self.state.get("campaign_direction"), dict) else {}
        for lead in direction.get("nearby_opportunities", [])[:2]:
            if self._suggestion_is_current(lead): suggestions.append(ai_text(lead)[:180])
        for quest in self.state.get("quests", []):
            if not isinstance(quest, dict): continue
            conditions = quest.get("clear_conditions", []) or quest.get("current_knowledge", [])
            if conditions:
                suggestions.append(f"Follow the {quest.get('name', 'quest')} lead: {conditions[0]}")
                break
            if quest.get("name"):
                suggestions.append(f"Investigate the next lead in {quest['name']}")
                break
        for track in self.state.get("prerequisite_tracks", []):
            if isinstance(track, dict) and track.get("next_steps"):
                suggestions.append(f"Progress toward {track.get('name', 'your goal')}: {track['next_steps'][0]}")
                break
        for lead in contextual_opportunities(self.state)[:1]:
            if self._suggestion_is_current(lead):
                suggestions.append(lead)
        # Prefer a SPECIFIC, already-established name over a generic template
        # whenever one exists — a known contact or an unexplored discovered
        # location beats "ask around" every time this data is available.
        contacts = [name for name, c in self.state.get("contacts", {}).items() if isinstance(c, dict) and c.get("can_contact", True)]
        if contacts:
            suggestions.append(f"Reach out to {contacts[-1]} and see what they know or need")
        other_locations = [loc for loc in self.state.get("discovered_locations", []) if loc and loc != self.state.get("location")]
        if other_locations:
            suggestions.append(f"Travel to {other_locations[-1]} and see what's changed there")
        world = self.state.get("world", "Custom World")
        training = expansion_for(world).get("training", [])
        archetype = (self.state.get("special", {}) or {}).get("Archetype", "")
        if world == "Overgeared" and archetype:
            starter = starter_kit_for(archetype)
            location = self.state.get("location", "the current area")
            for lead in starter.get("suggestions", []):
                lead = str(lead).strip()
                if lead:
                    suggestions.append(f"At {location}, {lead[:1].lower() + lead[1:]}")
        elif training:
            suggestions.append(f"Spend real time training in {training[0]}{f' as a {archetype}' if archetype else ''}")
        suggestions.append(f"Ask around {self.state.get('location', 'the area')} for relevant rumors and opportunities")
        suggestions.append("Pursue whatever your background and goals would realistically point you toward next")
        unique = []
        for text in suggestions:
            text = str(text).strip()
            if self._suggestion_is_current(text) and text.lower() not in {x.lower() for x in unique}:
                unique.append(text[:180])
            if len(unique) == 3: break
        return distinct_suggestions(unique, self.state, 3)

    def archive_finished_quests(self):
        active, archive = [], self.state.setdefault("quest_archive", [])
        for quest in self.state.get("quests", []):
            status = str(quest.get("status", "") if isinstance(quest, dict) else "").lower()
            if status in {"complete", "completed", "failed", "abandoned"}:
                if isinstance(quest, dict):
                    quest = copy.deepcopy(quest)
                    quest.setdefault("archived_turn", self.state.get("turn", 0))
                archive.append(quest)
            else:
                active.append(quest)
        self.state["quests"] = active
        self.state["quest_archive"] = archive[-200:]

    def ensure_quest_briefings(self, before, trigger_text=""):
        """Normalize new quests and guarantee a readable Chronicle briefing.

        AI-authored state is still preferred, but an explicit player request to
        begin a quest cannot disappear merely because a model omitted the
        structured quest patch.
        """
        trigger = re.sub(r"\s+", " ", str(trigger_text or "")).strip()
        literal_quests = uses_literal_quests(self.state.get("world"))
        presentation = quest_presentation_for(self.state.get("world"))
        prior_names = {
            str(q.get("name", "")).strip().lower() for q in before.get("quests", [])
            if isinstance(q, dict) and str(q.get("name", "")).strip()
        }
        quests = self.state.setdefault("quests", [])
        is_start_request = bool(re.search(r"\b(?:start|begin|accept|take(?:\s+on)?)\b.{0,50}\b(?:quest|mission|job|contract)\b", trigger, re.I))
        new_quests = [q for q in quests if isinstance(q, dict) and str(q.get("name", "")).strip().lower() not in prior_names]
        if is_start_request and not new_quests:
            match = re.search(r"\b(?:quest|mission|job|contract)\b\s*(?:to\s+)?(.+)$", trigger, re.I)
            goal = (match.group(1).strip(" .") if match else "")[:240]
            if not goal or goal.lower() in {"a", "one", "the", "new"}:
                goal = "Find a concrete local problem and see it through"
            name = goal[:72].title()
            quest = {
                "name": name,
                "status": "Active",
                "category": "personal",
                "giver": "Self-directed",
                "explanation": f"You committed to this goal at {self.state.get('location', 'your current location')}: {goal}.",
                "current_knowledge": [f"Starting point: {self.state.get('location', 'current location')}"],
                "clear_conditions": [goal],
                "completion_conditions": [goal],
                "discovered_clues": [f"Starting point: {self.state.get('location', 'current location')}"],
                "optional_objectives": [],
                "current_obstacles": ["Unknown until the first lead is investigated"],
                "locations": [self.state.get("location", "Current location")],
                "risks": ["Unknown until the first lead is investigated"],
                "first_step": "Identify the nearest reliable lead, witness, patron, or location connected to the objective.",
                "agenda_mode": "literal" if literal_quests else "narrative",
            }
            quests.append(quest)
            new_quests.append(quest)

        for quest in new_quests:
            quest_name = str(quest.get("name") or "New Quest").strip()
            placeholder_phrases = (
                "no additional explanation", "no briefing recorded", "no explanation recorded",
                "advance this quest", f"advance {quest_name.lower()}",
            )
            def _placeholder(value):
                text = ai_text(value).strip().lower()
                return (not text or text in {"none", "null", "unknown", "n/a", "not set", "tbd"}
                        or any(text.startswith(phrase) for phrase in placeholder_phrases))

            def _fact_key(value):
                return re.sub(r"[^a-z0-9]+", " ", ai_text(value).casefold()).strip()

            def _duplicates(value, *others):
                key = _fact_key(value)
                if not key:
                    return True
                for other in others:
                    other_key = _fact_key(other)
                    if other_key and (key == other_key or (len(key) > 35 and (key in other_key or other_key in key))):
                        return True
                return False

            source_sentence = ""
            if trigger:
                keywords = [word.lower() for word in re.findall(r"[A-Za-z]{4,}", quest_name)
                            if word.lower() not in {"that", "this", "with", "from", "quest"}]
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", trigger) if s.strip()]
                source_sentence = next((s for s in sentences if any(word in s.lower() for word in keywords)), "")
                if not source_sentence and sentences:
                    source_sentence = sentences[0]
            conditions = quest.get("clear_conditions") or quest.get("objectives") or quest.get("objective") or []
            if isinstance(conditions, str):
                conditions = [conditions]
            knowledge = quest.get("current_knowledge") or quest.get("knowledge") or []
            if isinstance(knowledge, str):
                knowledge = [knowledge]
            locations = quest.get("locations") or []
            if isinstance(locations, str):
                locations = [locations]
            risks = quest.get("risks") or quest.get("known_risks") or []
            if isinstance(risks, str):
                risks = [risks]
            clean_conditions = [ai_text(x)[:500] for x in conditions[:40] if ai_text(x)]
            if len(clean_conditions) == 1 and _placeholder(clean_conditions[0]):
                clean_conditions = []
            objective = (clean_conditions[0] if clean_conditions else
                         f"Investigate {quest_name}, resolve its central problem, and confirm the outcome.")
            explanation = ai_text(quest.get("explanation") or quest.get("description"))
            if _placeholder(explanation):
                explanation = (f"At {self.state.get('location', 'the current location')}, this objective emerged: {source_sentence}"
                               if source_sentence else f"A concrete objective has begun at {self.state.get('location', 'the current location')}: {quest_name}.")
            quest["explanation"] = explanation[:2000]
            clean_knowledge = [ai_text(x)[:500] for x in knowledge[:40] if ai_text(x)]
            if len(clean_knowledge) == 1 and re.match(r"(?i)^the quest begins at\b", clean_knowledge[0]):
                clean_knowledge = []
            clean_knowledge = [item for item in clean_knowledge
                               if not _duplicates(item, explanation, source_sentence, objective)]
            quest["current_knowledge"] = clean_knowledge
            quest["clear_conditions"] = clean_conditions or [objective[:500]]
            quest["locations"] = [ai_text(x)[:500] for x in locations[:40] if ai_text(x)] or [str(self.state.get("location", "Current location"))]
            clean_risks = [ai_text(x)[:500] for x in risks[:20] if ai_text(x) and not _placeholder(x)]
            clean_risks = [risk for risk in clean_risks if not re.match(
                r"(?i)^(?:no (?:specific|immediate|known) (?:danger|risk|pressure)|unknown until)", risk)]
            quest["risks"] = clean_risks or ["No immediate pressure is known yet."]
            quest["giver"] = str(quest.get("giver") or quest.get("cause") or "Circumstances")[:200]
            first_step = ai_text(quest.get("first_step") or quest.get("next_step"))
            if re.match(r"(?i)^follow the first known lead:\s*the quest begins at\b", first_step):
                first_step = f"Examine the evidence tied to {quest_name} at {quest['locations'][0]} and speak with the people directly involved."
            elif _placeholder(first_step):
                first_step = ((f"Examine the evidence tied to {quest_name} at {quest['locations'][0]} and speak with the people directly involved.")
                              if literal_quests else "")
            if _duplicates(first_step, explanation, source_sentence, objective):
                first_step = ""
            quest["first_step"] = first_step[:500]
            quest["discovered_clues"] = [ai_text(x)[:500] for x in (quest.get("discovered_clues") or quest["current_knowledge"])[:40] if ai_text(x)]
            quest["completion_conditions"] = [ai_text(x)[:500] for x in (quest.get("completion_conditions") or quest["clear_conditions"])[:40] if ai_text(x)]
            quest["optional_objectives"] = [ai_text(x)[:500] for x in (quest.get("optional_objectives") or [])[:20] if ai_text(x)]
            quest["current_obstacles"] = [ai_text(x)[:500] for x in (quest.get("current_obstacles") or quest["risks"])[:20] if ai_text(x)]
            quest["next_hint"] = str(quest.get("next_hint") or quest["first_step"])[:500]
            quest["agenda_mode"] = "literal" if literal_quests else "narrative"
            if literal_quests:
                first_step = quest["first_step"] or f"Act on the clearest lead connected to {quest_name}."
                known_risk = quest["risks"][0] if quest["risks"] else "No confirmed risk yet."
                briefing = (
                    f"[QUEST STARTED — {quest.get('name', 'New Quest')}]\n"
                    f"{quest['explanation']}\n"
                    f"Objective: {quest['clear_conditions'][0]}\n"
                    f"First step: {first_step}\n"
                    f"Known risk: {known_risk}"
                )
                self.append(briefing, "system")
            else:
                lines = [f"[{presentation['entry_label'].upper()} ADDED — {quest.get('name', 'New Direction')}]",
                         quest["explanation"]]
                if quest["first_step"]:
                    lines.append(f"Next: {quest['first_step']}")
                if quest["current_knowledge"]:
                    lines.append(f"Confirmed: {quest['current_knowledge'][0]}")
                if quest["risks"] and not re.match(r"(?i)^no (?:immediate|specific|known) (?:pressure|danger|risk)", quest["risks"][0]):
                    lines.append(f"Pressure: {quest['risks'][0]}")
                briefing = "\n".join(line for line in lines if line)
                self.append(briefing, "system")
        return new_quests

    @staticmethod
    def xp_threshold_for_level(level):
        """XP needed to advance from *level* to the next level."""
        return max(100, 100 + (max(1, int(level)) - 1) * 50)

    def calculate_xp_award(self, actions, rolls=None, elapsed_minutes=5, intensity="normal", events=None):
        """Return a bounded, explainable XP award for literal-System worlds.

        The narrator may describe why something mattered, but it cannot forget
        the reward or inflate it arbitrarily. Duration matters most for repeated
        practice; challenge and outcome matter most for risky actions.
        """
        if not uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")):
            return 0, []
        actions = [str(x).strip() for x in (actions or []) if str(x).strip()]
        if not actions:
            return 0, []
        rolls = [x for x in (rolls or []) if isinstance(x, dict)]
        minutes = max(1, int(elapsed_minutes or 1))
        minutes_each = minutes / max(1, len(actions))
        training_words = ("train", "practice", "study", "research", "drill", "meditat", "spar", "learn", "master", "craft")
        danger_words = ("fight", "battle", "defeat", "boss", "dungeon", "raid", "quest", "mission", "survive", "hunt")
        contribution_words = ("heal", "cleanse", "support", "protect", "tank", "guard", "scout", "map", "track", "investigate", "negotiate", "trade", "lead", "command", "coordinate", "summon", "companion", "appraise", "escort")
        modest_words = ("rest", "sleep", "wait", "eat", "talk", "ask", "walk", "travel")
        daily_rates = {"light": 6, "normal": 10, "intense": 15, "extreme": 20}
        total, reasons = 0, []
        for index, action in enumerate(actions):
            lowered = action.lower()
            if any(word in lowered for word in training_words):
                effective_days = max(.05, minutes_each / 1440.0)
                earned = max(1, round(effective_days * daily_rates.get(str(intensity).lower(), 5)))
                reason = f"{round(effective_days, 2)} effective days of sustained practice"
            elif any(word in lowered for word in danger_words):
                earned, reason = 12, "meaningful combat, mission, or dangerous objective"
            elif any(word in lowered for word in contribution_words):
                effective_days = max(.05, minutes_each / 1440.0)
                earned = max(10, round(effective_days * daily_rates.get(str(intensity).lower(), 10)))
                reason = "meaningful support, defense, scouting, social, command, or companion contribution"
            elif any(word in lowered for word in modest_words):
                earned, reason = 3, "minor but relevant character activity"
            else:
                earned, reason = 6, "meaningful character action"
            if index < len(rolls):
                result = rolls[index]
                difficulty = clamp(int(result.get("difficulty", 50) or 50), 1, 100)
                challenge = 2 + difficulty // 12
                if not result.get("success", False):
                    challenge = max(1, round(challenge * .6))
                if result.get("major_event"):
                    challenge *= 2
                if result.get("breakthrough"):
                    challenge += 15
                earned += challenge
                reason += f"; contextual challenge {difficulty}/100"
            total += earned
            reasons.append({"action": action, "xp": earned, "reason": reason})
        event_text = " ".join(
            str(event.get("message", "") if isinstance(event, dict) else event).lower()
            for event in (events or [])
        )
        if any(term in event_text for term in ("quest complete", "quest completed", "boss defeated", "achievement unlocked")):
            total += 25
            reasons.append({"action": "Milestone", "xp": 25, "reason": "completed quest, boss, or System achievement"})
        tuning = normalize_tuning(self.state)
        xp_rate = float(tuning.get("xp_rate", 1.0) or 1.0)
        if xp_rate != 1.0:
            for reason in reasons:
                reason["xp"] = max(1, int(round(int(reason.get("xp", 0) or 0) * xp_rate)))
            total = sum(int(reason.get("xp", 0) or 0) for reason in reasons)
        return max(0, int(total)), reasons

    def apply_system_xp(self, before, actions, rolls=None, elapsed_minutes=5, intensity="normal", events=None):
        """Apply XP, carry overflow, and grant automatic level-up stats."""
        if not uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")):
            return {"xp_awarded": 0, "levels_gained": 0, "stat_gains": {}, "reasons": []}
        # XP, levels and base stats are application-controlled in System worlds.
        self.state["xp"] = max(0, int(before.get("xp", 0) or 0))
        self.state["level"] = max(1, int(before.get("level", 1) or 1))
        self.state["xp_next"] = max(1, int(before.get("xp_next", self.xp_threshold_for_level(self.state["level"])) or 1))
        self.state["stats"] = copy.deepcopy(before.get("stats", self.state.get("stats", {})))
        award, reasons = self.calculate_xp_award(actions, rolls, elapsed_minutes, intensity, events)
        self.state["xp"] += award
        levels_gained = 0
        stat_gains = {name: 0 for name in self.state.get("stats", {})}
        primary = primary_stats_for(self.state.get("world"), self.state.get("special", {}).get("Archetype", ""))
        while self.state["xp"] >= self.state["xp_next"]:
            self.state["xp"] -= self.state["xp_next"]
            self.state["level"] += 1
            levels_gained += 1
            for name in self.state.get("stats", {}):
                gain = 1 + (2 if primary and name == primary[0] else 1 if len(primary) > 1 and name == primary[1] else 0)
                self.state["stats"][name] = max(1, int(self.state["stats"].get(name, 1) or 1) + gain)
                stat_gains[name] += gain
            self.state["xp_next"] = self.xp_threshold_for_level(self.state["level"])
        stat_gains = {name: gain for name, gain in stat_gains.items() if gain}
        if award:
            entry = {"type": "xp", "turn": int(before.get("turn", 0)) + 1, "xp_awarded": award,
                     "levels_gained": levels_gained, "stat_gains": stat_gains, "reasons": reasons}
            self.state.setdefault("progression_log", []).append(entry)
            self.state["progression_log"] = self.state["progression_log"][-300:]
        return {"xp_awarded": award, "levels_gained": levels_gained, "stat_gains": stat_gains, "reasons": reasons}

    def reconcile_title_events(self, events):
        """Persist title announcements even when a model omits titles patch."""
        titles = self.state.setdefault("titles", [])
        known = {ai_text(title).strip().lower() for title in titles if ai_text(title).strip()}
        earned = []
        patterns = (
            r"(?:title acquired|title earned|earned the title|unlocked (?:the )?title)\s*[:—-]?\s*[\"']?([^\n\"']+)",
        )
        for event in events or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "").strip().lower()
            raw_label = event.get("title") or event.get("name")
            raw_message = event.get("message") or event.get("narrative")
            label = ai_text(raw_label).strip() if raw_label is not None else ""
            message = ai_text(raw_message).strip() if raw_message is not None else ""
            if not label:
                for pattern in patterns:
                    match = re.search(pattern, message, re.I)
                    if match:
                        label = match.group(1).strip(" .!—-\")")
                        break
            if event_type in {"title", "title_acquired", "title_earned"} and not label:
                label = message
            if not label or label.lower() in known:
                continue
            known.add(label.lower())
            titles.append(label[:160])
            earned.append(label[:160])
        self.state["titles"] = titles[-200:]
        return earned

    def notify(self, b, a, events):
        msgs = []
        cinematic = []
        expected_turn = int(b.get("turn", 0) or 0) + 1
        latest_progress = next((row for row in reversed(a.get("progression_log") or [])
                                if isinstance(row, dict) and row.get("type") == "xp"
                                and int(row.get("turn", 0) or 0) >= expected_turn), None)
        if a.get("xp") != b.get("xp") or latest_progress:
            earned = latest_progress.get("xp_awarded") if isinstance(latest_progress, dict) and latest_progress.get("type") == "xp" else None
            if earned is None:
                earned = a.get("xp", 0) - b.get("xp", 0)
            msgs.append(f"XP {int(earned):+d}  → {a.get('xp')}/{a.get('xp_next')}")
        if a.get("level") != b.get("level"):
            msgs.append(f"LEVEL UP!  {b.get('level')} → {a.get('level')}")
        stat_changes = []
        for stat, value in a.get("stats", {}).items():
            old = b.get("stats", {}).get(stat)
            if isinstance(value, (int, float)) and isinstance(old, (int, float)) and value != old:
                stat_changes.append((stat, int(value) - int(old), int(value)))
        if stat_changes and uses_xp_for(a.get("world"), a.get("custom_world", "")) and a.get("level") != b.get("level"):
            msgs.append("LEVEL STATS: " + ", ".join(f"{name} {delta:+d}" for name, delta, _ in stat_changes))
        else:
            msgs.extend(f"{stat.upper()} {delta:+d}  → {value}" for stat, delta, value in stat_changes)
        bs, as_ = b.get("skills", {}), a.get("skills", {})
        def _skill_summary(value):
            if not isinstance(value, dict):
                return ai_text(value)
            rank = ai_text(value.get("rank"))
            description = ai_text(value.get("description") or value.get("effect"))
            parts = [part for part in (rank, description) if part]
            return " — ".join(parts)

        def _skill_change(old, new):
            if not isinstance(old, dict) or not isinstance(new, dict):
                return _skill_summary(new) or "details refined"
            changes = []
            if old.get("rank") != new.get("rank") and new.get("rank"):
                changes.append(f"rank {ai_text(old.get('rank') or 'unknown')} → {ai_text(new.get('rank'))}")
            if old.get("bonus") != new.get("bonus") and isinstance(new.get("bonus"), (int, float)):
                changes.append(f"bonus {int(new.get('bonus') or 0):+d}")
            for key, label in (("description", "use"), ("effect", "effect"),
                               ("limitation", "limit"), ("growth_path", "growth path")):
                if old.get(key) != new.get(key) and ai_text(new.get(key)):
                    changes.append(f"{label}: {ai_text(new.get(key))}")
            # Origin/source metadata is useful to the engine but should not
            # spill a raw structure—or generation provenance—into play.
            return "; ".join(changes[:3]) or "details clarified"

        for k, v in as_.items():
            if k not in bs:
                summary = _skill_summary(v)
                msgs.append(f"NEW SKILL: {k}{f' — {summary}' if summary else ''}")
            elif bs[k] != v:
                msgs.append(f"SKILL REFINED: {k} — {_skill_change(bs[k], v)}")
        new_titles = set(ai_text(t) for t in a.get("titles", []) if ai_text(t))
        old_titles = set(ai_text(t) for t in b.get("titles", []) if ai_text(t))
        old_title_keys = {title.strip().lower() for title in old_titles}
        for t in new_titles - old_titles:
            msgs.append("TITLE ACQUIRED: " + t)
        def _achievement_name(entry):
            return entry.get("name", entry.get("title", "Achievement")) if isinstance(entry, dict) else str(entry)
        old_achievements = {_achievement_name(x) for x in b.get("achievements", [])}
        for entry in a.get("achievements", []):
            name = _achievement_name(entry)
            if name and name not in old_achievements:
                msgs.append("ACHIEVEMENT UNLOCKED: " + name)
        for q in a.get("quests", []):
            if q not in b.get("quests", []):
                msgs.append("QUEST UPDATED: " + (q.get("name", "Quest") if isinstance(q, dict) else str(q)))
        for ev in events or []:
            # XP and level notices are emitted from the authoritative state
            # delta above; narrator-authored versions may be inaccurate.
            if isinstance(ev, dict) and str(ev.get("type", "")).lower() in {"xp", "level", "level_up"}:
                continue
            m = ev.get("message", "") if isinstance(ev, dict) else str(ev)
            # The persistence pass correctly rejects an already-owned title,
            # but the raw narrator event used to survive and announce it on
            # every Solo/Tower turn.  Suppress the event at presentation too.
            if isinstance(ev, dict):
                event_type = str(ev.get("type") or "").strip().lower()
                title_label = ai_text(ev.get("title") or ev.get("name") or "").strip()
                if not title_label and m:
                    match = re.search(
                        r"(?:title acquired|title earned|earned the title|unlocked (?:the )?title)\s*[:—-]?\s*[\"']?([^\n\"']+)",
                        m, re.I,
                    )
                    if match:
                        title_label = match.group(1).strip(" .!—-\")")
                if title_label and title_label.lower() in old_title_keys and (
                    event_type in {"title", "title_acquired", "title_earned"}
                    or re.search(r"title acquired|title earned|earned the title|unlocked (?:the )?title", m, re.I)
                ):
                    continue
            if m and not any(m.lower() in x.lower() or x.lower() in m.lower() for x in msgs):
                msgs.append(m)
        try:
            hp_delta = int(a.get("hp", 0)) - int(b.get("hp", 0))
        except (TypeError, ValueError):
            hp_delta = 0
        damage_msg = None
        if hp_delta < 0 and a.get("alive", True) and not any("damage" in m.lower() or "hurt" in m.lower() or "wound" in m.lower() for m in msgs):
            damage_msg = f"Took {-hp_delta} damage"
            msgs.append(damage_msg)
        position_msg = None
        if a.get("position") and a.get("position") != b.get("position"):
            position_msg = f"New position: {a.get('position')}"
            msgs.append(position_msg)
        out = []
        world_system = "satisfy" if a.get("world") == "Overgeared" else "tower" if a.get("world") == "Solo Max-Level Newbie" else "world"
        system_heading = "SATISFY SYSTEM" if world_system == "satisfy" else "SYSTEM MESSAGE" if world_system == "tower" else "SYSTEM"

        def _canon_system_notice(message):
            """Render mechanical deltas in the native language of each LitRPG world."""
            if world_system not in {"satisfy", "tower"}:
                return message
            xp_match = re.match(r"XP\s+([+-]?\d+)\s+→\s+(\d+)/(\d+)", message, re.I)
            level_match = re.match(r"LEVEL UP!\s+(\d+)\s+→\s+(\d+)", message, re.I)
            stat_match = re.match(r"LEVEL STATS:\s*(.+)", message, re.I)
            skill_match = re.match(r"NEW SKILL:\s*([^—]+?)(?:\s+—\s+(.+))?$", message, re.I)
            refined_match = re.match(r"SKILL REFINED:\s*([^—]+?)(?:\s+—\s+(.+))?$", message, re.I)
            title_match = re.match(r"TITLE ACQUIRED:\s*(.+)", message, re.I)
            achievement_match = re.match(r"ACHIEVEMENT UNLOCKED:\s*(.+)", message, re.I)
            quest_match = re.match(r"QUEST UPDATED:\s*(.+)", message, re.I)
            if xp_match:
                gained, current, needed = xp_match.groups()
                amount = abs(int(gained))
                if world_system == "satisfy":
                    return f"You have acquired {amount} experience.\nExperience: {current} / {needed}"
                return f"[Experience acquired: {amount}]\nCurrent EXP: {current} / {needed}"
            if level_match:
                old, new = level_match.groups()
                if world_system == "satisfy":
                    return f"Your level has risen.\nLevel: {old} → {new}"
                return f"[LEVEL UP]\nYour level has increased from {old} to {new}."
            if stat_match:
                gains = stat_match.group(1)
                if world_system == "satisfy":
                    return f"Your stats have increased with your new level.\n{gains}"
                return f"[Stat increase applied]\n{gains}"
            if skill_match:
                name, detail = skill_match.groups()
                lead = f"You have learned the skill [{name.strip()}]." if world_system == "satisfy" else f"[New skill acquired: {name.strip()}]"
                return lead + (f"\n{detail.strip()}" if detail else "")
            if refined_match:
                name, detail = refined_match.groups()
                lead = f"The skill [{name.strip()}] has developed." if world_system == "satisfy" else f"[Skill proficiency increased: {name.strip()}]"
                return lead + (f"\n{detail.strip()}" if detail else "")
            if title_match:
                name = title_match.group(1).strip()
                return f"You have acquired the title [{name}]." if world_system == "satisfy" else f"[New title acquired: {name}]"
            if achievement_match:
                name = achievement_match.group(1).strip()
                return f"You have achieved [{name}]." if world_system == "satisfy" else f"[Achievement unlocked: {name}]"
            if quest_match:
                name = quest_match.group(1).strip()
                return f"The quest [{name}] has been registered or updated." if world_system == "satisfy" else f"[Quest information updated: {name}]"
            return message

        for m in msgs:
            presented = _canon_system_notice(m)
            tag = "danger" if "death" in m.lower() else "meta"
            self.append(f"[{system_heading}]\n" + presented, tag)
            self.log(presented)
            ml = m.lower()
            ctype = None
            if m == position_msg:
                ctype = "position"
            elif "achievement unlocked" in ml:
                ctype = "achievement"
            elif "level up" in ml:
                ctype = "level_up"
            elif ml.startswith("xp ") or "xp +" in ml:
                ctype = "xp"
            elif "title acquired" in ml or "new skill" in ml or "skill updated" in ml:
                ctype = "notify"
            elif m == damage_msg:
                ctype = "damage"
            elif "death" in ml or "injury" in ml:
                ctype = "danger"
            out.append({"message": m, "display_message": presented, "tag": tag,
                        "cinematic": ctype, "world_system": world_system})
        return out

    def rewind_death(self):
        with self.lock:
            if not self.checkpoints:
                return None
            self.state = self.checkpoints.pop()
            self.state["alive"] = True
            self.append("[TIMELINE REWOUND]\nThe lethal action has been undone. You are back at the decision point.", "meta")
            self.autosave()
        return {"state": self.public_state(), "story": self._flush_story()}

    def undo(self):
        with self.lock:
            if not self.checkpoints:
                return None
            self.state = self.checkpoints.pop()
            self.state["alive"] = True
            self.append("[TURN REVERTED]\nThe last action has been undone.", "meta")
            self.autosave()
        return {"state": self.public_state(), "story": self._flush_story()}

    def queue_action(self, text):
        action = str(text or "").strip()
        if not action:
            raise ValueError("Type an action before adding it to the queue.")
        if len(action) > 800:
            raise ValueError("Queued actions must be under 800 characters each.")
        with self.lock:
            self.state.setdefault("queued_actions", []).append(action)
            self.state["queued_actions"] = self.state["queued_actions"][-50:]
            self.autosave()
        return copy.deepcopy(self.state["queued_actions"])

    def remove_queued_action(self, index):
        with self.lock:
            actions = self.state.setdefault("queued_actions", [])
            index = int(index)
            if index < 0 or index >= len(actions):
                raise IndexError("Queued action no longer exists.")
            actions.pop(index)
            self.autosave()
        return copy.deepcopy(actions)

    def update_queued_action(self, index, text):
        action = str(text or "").strip()
        if not action:
            raise ValueError("A queued action cannot be empty.")
        if len(action) > 800:
            raise ValueError("Queued actions must be under 800 characters each.")
        with self.lock:
            actions = self.state.setdefault("queued_actions", [])
            index = int(index)
            if index < 0 or index >= len(actions):
                raise IndexError("Queued action no longer exists.")
            actions[index] = action
            self.autosave()
        return copy.deepcopy(actions)

    def move_queued_action(self, index, to_index):
        with self.lock:
            actions = self.state.setdefault("queued_actions", [])
            index, to_index = int(index), int(to_index)
            if index < 0 or index >= len(actions):
                raise IndexError("Queued action no longer exists.")
            to_index = max(0, min(to_index, len(actions) - 1))
            action = actions.pop(index)
            actions.insert(to_index, action)
            self.autosave()
        return copy.deepcopy(actions)
