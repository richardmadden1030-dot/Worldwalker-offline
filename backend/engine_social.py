"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, power_tier_reference, power_profile_for
from ai_client import AI
from standing_intents import active_standing_intents
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, ai_text
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks)
from simulation import refresh_npc_intentions, background_ai_due
from power_benchmarks import benchmark_context
from canon_integrity import active_canon_identities, canon_identity_context, repair_canon_payload
from response_guard import normalize_object_response


LOCAL_CANON_POWER_ESTIMATES = {
    "Naruto": {
        "early naruto": 45, "naruto": 65, "kakashi": 210, "average jonin": 140,
        "typical jonin": 140, "minato namikaze": 620, "minato": 620,
        "hiruzen sarutobi": 470, "hiruzen": 470, "jiraiya": 390,
        "orochimaru": 410, "tsunade": 360, "might guy": 430,
        "killer bee": 470, "hashirama": 760, "madara": 780,
        "pain": 600, "nagato": 650, "itachi": 420,
        "kisame": 300, "konan": 175, "sasori": 190, "deidara": 180,
        "kakuzu": 205, "hidan": 125, "hanzo": 380, "obito": 610,
    },
    "One Piece": {"luffy": 210, "zoro": 190, "nami": 75, "shanks": 700, "garp": 650, "average marine": 35, "marine captain": 90},
    "Hunter x Hunter": {"gon": 90, "killua": 105, "hisoka": 220, "chrollo": 250, "netero": 610, "average hunter": 90},
    "Bleach": {"ichigo": 130, "rukia": 90, "renji": 135, "byakuya": 360, "aizen": 650, "average lieutenant": 130, "average captain": 350},
    "Jujutsu Kaisen": {"yuji": 90, "megumi": 95, "maki": 140, "yuta": 600, "gojo": 900, "sukuna": 900, "average grade 1": 140},
    "Overgeared": {"grid": 210, "kraugel": 220, "average ranker": 90, "top ranker": 200},
    "Solo Max-Level Newbie": {"kang jinhyeok": 210, "alice": 200, "average player": 50, "high-rank player": 90},
    "Reincarnated as a Slime": {"rimuru": 350, "veldora": 650, "shion": 200, "benimaru": 210, "average majin": 90},
}

WORLD_ROLE_POWER_ESTIMATES = {
    "Naruto": ((r"six paths|otsutsuki|ōtsutsuki", 1000), (r"hokage|major kage|kage class", 620),
               (r"akatsuki|s[- ]?rank|elite jonin|elite jōnin", 300), (r"jonin|jōnin", 140),
               (r"chunin|chūnin", 65), (r"genin", 45), (r"academy", 20)),
    "One Piece": ((r"emperor|yonko|admiral", 700), (r"commander|warlord", 400),
                  (r"vice admiral", 250), (r"supernova|notorious captain", 180),
                  (r"marine captain|officer", 90), (r"rookie|crew member", 65)),
    "Hunter x Hunter": ((r"chairman", 610), (r"royal guard", 600), (r"zodiac|phantom troupe|master nen", 240),
                        (r"veteran hunter|professional assassin", 150), (r"hunter|nen user", 90), (r"applicant", 35)),
    "Bleach": ((r"captain.commander|transcendent", 650), (r"captain", 350), (r"lieutenant", 130),
               (r"seated officer|substitute soul reaper", 90), (r"unseated|academy", 45)),
    "Jujutsu Kaisen": ((r"king of curses|special.grade", 650), (r"elite grade 1", 220),
                       (r"grade 1", 140), (r"grade 2", 65), (r"grade 3", 45), (r"grade 4|student", 25)),
    "Overgeared": ((r"absolute|transcendent", 650), (r"legendary", 350), (r"top.rank", 220),
                   (r"national rank", 140), (r"ranker", 90), (r"beginner", 25)),
    "Solo Max-Level Newbie": ((r"administrator", 700), (r"transcendent", 600), (r"named power", 220),
                              (r"high.rank", 90), (r"player", 50)),
    "Reincarnated as a Slime": ((r"true dragon", 700), (r"true demon lord|oldest demon lord", 600),
                                (r"demon lord seed", 250), (r"majin|kijin commander", 140), (r"named monster", 65)),
}


def _role_power_estimate(world, role):
    text = str(role or "").lower()
    for pattern, score in WORLD_ROLE_POWER_ESTIMATES.get(world, ()):
        if re.search(pattern, text, re.I):
            return float(score)
    return None


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

class SocialMixin:
    def _advisor_evidence(self, question, task_state=None, limit=5):
        """Give every answer a short, inspectable local evidence trail."""
        task_state = task_state if isinstance(task_state, dict) else self.task_state_for_ai("advisor", question)
        rows = []
        profile = task_state.get("mechanical_power_profile") if isinstance(task_state.get("mechanical_power_profile"), dict) else {}
        combat = profile.get("world_combat") or profile.get("combat") or {}
        if combat:
            rows.append({"label": "Current character sheet", "detail": f"{combat.get('name', 'World-relative')} · balanced score {combat.get('score', 'unknown')}", "source": "live mechanics"})
        for row in task_state.get("question_evidence", []) if isinstance(task_state.get("question_evidence"), list) else []:
            if not isinstance(row, dict): continue
            rows.append({"label": ai_text(row.get("title") or row.get("kind"))[:100],
                         "detail": ai_text(row.get("text"))[:260],
                         "source": f"{row.get('kind', 'campaign')} · turn {row.get('turn') if row.get('turn') is not None else 'unknown'}"})
            if len(rows) >= limit: break
        if len(rows) < 2:
            scene = (task_state.get("grounding_packet") or {}).get("current_truth", {})
            if scene:
                rows.append({"label": "Current campaign state", "detail": f"{scene.get('location', 'Unknown location')} · {scene.get('time', 'current time')}", "source": "live save"})
        return rows[:max(1, int(limit or 5))]

    def run_local_background(self):
        """Maintain recurring actors without a background-model request.

        Turn resolution already advances clocks and intentions. This pass
        only normalizes the persistent intention view, compacts duplicate
        memory-chain rows, and syncs contact metadata. It is intentionally
        quiet: routine maintenance should not manufacture Chronicle filler.
        """
        with self.lock:
            refresh_npc_intentions(self.state)
            for memory in (self.state.get("npc_memories") or {}).values():
                if not isinstance(memory, dict) or not isinstance(memory.get("chain"), list):
                    continue
                clean, seen = [], set()
                for item in memory["chain"]:
                    key = str(item).strip().lower()
                    if key and key not in seen:
                        clean.append(item); seen.add(key)
                memory["chain"] = clean[-16:]
            self.state["local_background_turn"] = int(self.state.get("turn", 0) or 0)
            self.autosave()
        return {"maintained": True, "intentions": len(self.state.get("npc_intentions", {}))}

    def background_ai_due(self):
        return background_ai_due(self.state, self.simulation_mode())

    def ask_advisor(self, question, fourth_wall=False):
        """A Pax Historia-style Advisor: an out-of-character, meta-aware
        guide the player can consult any time for power-level assessments,
        world-state summaries, and strategic advice — NOT an in-fiction NPC,
        so it isn't bound by 'only knows what they'd plausibly know', and it
        never touches game state (no dice, no state_patch, no turn cost)."""
        with self.lock:
            self.state.setdefault("advisor_thread", []).append({"role": "player", "text": question, "turn": self.state.get("turn", 0)})
        comparison_entry = self._local_power_comparison(question, fourth_wall)
        if comparison_entry:
            comparison_entry.setdefault("evidence", self._advisor_evidence(question))
            with self.lock:
                self.state["advisor_thread"].append(comparison_entry)
                self.autosave()
            return {"entry": comparison_entry, "state": self.public_state(), "local_answer": True}
        local_entry = self._local_advisor_answer(question, fourth_wall) if isinstance(self.ai, AI) else None
        if local_entry:
            local_entry.setdefault("evidence", self._advisor_evidence(question))
            with self.lock:
                self.state["advisor_thread"].append(local_entry)
                self.autosave()
            return {"entry": local_entry, "state": self.public_state(), "local_answer": True}
        if not self.ai_ready():
            entry = {"role": "advisor", "summary": "The Advisor is unavailable — configure a model in AI & Portrait Setup first.", "points": [], "follow_ups": [], "turn": self.state.get("turn", 0)}
            with self.lock:
                self.state["advisor_thread"].append(entry)
            return {"entry": entry, "state": self.public_state()}
        # Brevity is about intent, not word count. "What happened to Konan?"
        # is short but may require the whole campaign record; only genuine
        # acknowledgements receive the one-sentence/low-token path.
        concise = bool(re.fullmatch(r"\s*(thanks|thank you|okay|ok|got it|understood|cool|never mind|nevermind)[.!?\s]*",
                                    str(question), re.I))
        comparison_requested = bool(re.search(
            r"\b(compare[ds]?|comparison|versus|vs\.?|against|relative to|stack up|other members?|"
            r"stronger than|weaker than|where do i rank|among the)\b", str(question), re.I))
        wants_chart = bool(re.search(r"\b(graph|chart|plot|visuali[sz]e|bar\s*chart)\b", str(question), re.I)) or comparison_requested
        named_character_power_question = bool(re.search(
            r"\b(how strong (?:is|was|are)|power (?:level|tier|of)|strength of|could .* beat|who (?:wins|is stronger))\b",
            str(question), re.I))
        advisor_state = self.task_state_for_ai("advisor", question)
        payload = {
            "task": "advisor_question", "question": question, "state": advisor_state,
            "advisor_mode": "fourth_wall" if fourth_wall else "strategic", "next_canon_event": self.canon_countdown(),
            "canon_divergences": self.state.get("canon_divergences", []),
            "canon_identity_evidence": canon_identity_context(self.state.get("world", "Custom World"), question, self.state, limit=16),
            "comparison_requested": comparison_requested,
            "named_character_power_question": named_character_power_question,
            "power_comparison_guardrail": {
                "rule": "Use the player's mechanical_power_profile. Never compare against their stock-canon self or a stale starting label.",
                "relative_language": "Do not say much weaker/stronger without a same-scale opponent estimate and an axis-by-axis explanation.",
                "unknown_opponents": "Estimate every named character from campaign narrative, tracked feats/status and current canon baseline. Exact numeric sheets are never required; label confidence instead of refusing.",
            },
            # The current question was appended above and is already present
            # in payload.question. Excluding it here prevents the model from
            # treating the same message as two separate conversational turns.
            "thread_history": self.state.get("advisor_thread", [])[:-1][-10:],
            "schema": {
                "summary": ("ONE direct sentence answering the question — nothing more" if concise else
                            "2-4 direct sentences answering the question with a bottom line and important context"),
                "points": ([] if concise else
                           ["4-8 substantive supporting points with evidence, comparison, timing, odds, tradeoffs or concrete next steps"]),
                "follow_ups": ([] if concise else
                               ["2-3 short natural follow-up questions the player might want to ask next, phrased as the PLAYER would ask them"]),
                "chart": ("null unless the player explicitly asked for a graph/chart/visual comparison, or the answer is fundamentally "
                          "a numeric comparison across 3+ things a chart would communicate faster than prose — in which case: "
                          '{"title": "short chart title", "unit": "what the numbers mean, e.g. \'DBZ Power Level\'", '
                          '"items": [{"label": "name", "value": number}, ...2-8 entries, highest first]}'),
            },
        }
        rules = f"""You are "The Advisor" for {self.state.get('world','the world')} — a Dungeon Master the player can lean over and ask a question any time play pauses. You are NOT an in-fiction character and not bound by "NPCs only know what they'd plausibly know" — you know everything tracked plus this world's full canon.
Voice: talk TO the player, like a DM answering a question at the table — direct, plain, second person ("you're", "they've"), a real opinion when asked for one. Not a report, not a wiki article. This applies to every kind of question, not just rules questions — a strategy or world-state answer should still sound like a person talking, just with more to say.
ANSWER THE QUESTION FIRST: the opening sentence must directly answer the player's actual question. Do not substitute a nearby topic, repeat a generic campaign briefing, or lead with a disclaimer. Use prior thread messages only to resolve references such as "that," "he," or "why"; the newest payload.question always controls what you answer.
EVIDENCE ORDER: authoritative player corrections and current state override recent campaign records; recent records override chapter summaries; recorded divergences override stock canon. question_evidence contains local search matches from the full campaign, not guesses. Before answering, silently check the proposed answer against current stats/status/location, campaign_canon, continuity_facts, NPC/faction chains, and relevant question_evidence. If two records genuinely conflict, state the conflict instead of choosing whichever is convenient.
GROUNDING PACKET: state.grounding_packet is the mandatory short evidence set assembled specifically for this question. Answer from its current_truth, locked_facts, relevant people/factions, commitments and verified history before searching for a broader explanation. Never contradict it with a generic canon assumption.
CANON IDENTITY DISCIPLINE: treat canon_identity_evidence as opening-era identity/office grounding. Apply the current campaign date and every recorded succession, death, defection, promotion, or divergence before answering; never swap similarly placed characters or silently assign one character another's office.
TIME DISCIPLINE: distinguish what is true now from what used to be true. Never describe a completed, prevented, or diverged event as pending. Never erase something merely because it falls outside the recent-turn tail; use question_evidence and chapter summaries for older events.
AMBIGUITY: if the question cannot be resolved because two tracked people/events share the reference, ask one precise clarifying question. Do not invent a target or answer a different question.
You may freely:
- Assess relative power levels of the player, companions, rivals, factions and known threats, using terms appropriate to this world (bounty/Haki tier, Nen category/rank, jutsu/village rank, class/level, etc.) by default.
- For the player, state.mechanical_power_profile and the current raw state.stats are mechanically authoritative. Never substitute the canon version of a player-controlled character, their starting rank, their old title, or an earlier Advisor estimate. An extreme peak stat means extreme output in that discipline; it does not erase the separately listed speed, defense, or overall foundation.
- When comparing the player with a canon opponent who has no tracked numeric sheet, estimate that opponent on the SAME balanced-score ladder and label it as a canon-based estimate. Compare offense, speed, defense, special techniques, experience and matchup hazards separately. If the player's tracked axis exceeds a reasonable estimate, say so plainly even when the opponent remains dangerous on other axes; never summarize them as simply 'much weaker' in contradiction with the numbers.
- You can estimate the current strength of ANY named character that has appeared, been mentioned, or exists in this campaign. First use their tracked NPC memory, current condition, relationships, faction/rank, recent narrative actions and question_evidence; then use demonstrated campaign feats; finally use their canon strength at the current date as a baseline. If the campaign has changed them, the campaign version wins. A missing numeric character sheet is not a reason to refuse and you must never say you can only provide a canon estimate. Give a practical low/middle/high estimate or world-appropriate tier, explain the feats and assumptions behind it, and label confidence when evidence is thin.
- If the player asks for a specific comparison framework instead — a numeric scale, tiers, percentages, or even a well-known scale borrowed from another series (e.g. "give me this in DBZ power levels") — use exactly the framing they asked for as a communication device to convey relative strength, even when it isn't native to this world. It's a translation aid, not a claim that this world works that way.
- When you need your OWN internal sense of "how strong is strong" — placing the player, a companion, or a threat on a scale, deciding whether a fight is winnable, judging if a request for a graph makes sense numerically — anchor to this reference ladder instead of improvising a different scale each time:
{power_tier_reference()}
  This ladder is scaffolding for your own consistency, never shown to the player unless they specifically ask for a numbered/tiered framing. A tier is based on BALANCED score, not the highest single stat or a flat arithmetic average. Once you've placed a named character at a tier, stay consistent with that placement unless current mechanical stats, a real power-up, or new information supersedes it.
- Summarize the current state of the world: active threats, opportunities, unresolved plot threads, faction tensions, quest status.
- When asked why an NPC feels a certain way or why a faction's standing is what it is, answer from that NPC's npc_memories[name].chain or the faction's faction_chain[name] entries in state if present — they're the real recorded reasons, not something to re-guess from scratch. Only fall back to reasoning from campaign_canon/narrative history when no chain entry exists yet (an older campaign predating this feature, or a relationship that's never had a real turning point).
- Give honest strategic advice, including risks and trade-offs. Never decide for the player — lay out the options.
- Reference next_canon_event when the player asks about timing, planning, readiness, future events, or what to do next. Do not force an unrelated canon countdown into factual, relationship, rules, or retrospective answers.
- ASKED ABOUT SOMETHING NOT IN THE TRACKED STATE (an off-screen character, faction, or event the player hasn't personally touched): don't deflect to "I don't know" or "that's not tracked." Answer it — reason from this world's canon AT THE CURRENT POINT IN THE TIMELINE (the tracked world_time/canon day, never spoiling events still ahead of it), the same way a DM who knows the source material would. First check canon_divergences: if a recorded divergence changed that person/place/event, the divergence is the truth and overrides stock canon — say so plainly ("in this campaign, X happened instead, because..."). BAD: "That's not something I have tracked information on." GOOD: "He's not someone you've crossed paths with, but canonically he'd still be running the western trade routes at this point in the story — reasoning from that, here's what he's probably doing..." Only hedge when canon genuinely never reveals the answer even in principle — and even then, give your best-reasoned read before admitting the limit, don't lead with the disclaimer.
- When the question is really a rules/mechanics clarifying question (how something works, what's allowed, what would happen if...), walk through it directly with an example if that helps — never a dry analytical report.
- When the player explicitly asks for a graph/chart/visual comparison, or the honest best answer to their question is fundamentally "here's how N things stack up numerically," fill in the chart field per the schema instead of (or alongside) explaining it in prose — don't just describe numbers in a sentence when they asked to see them.
{"FOURTH-WALL MODE IS ON. You may additionally expose and analyze the simulation's d100 math, generated difficulty range, stat/title bonuses, queue/time-budget behavior, canon-stop boundaries, AI uncertainty, save/rewind behavior, and clever ways to exploit those rules without falsifying state or changing it. Clearly distinguish engine facts from speculative model behavior." if fourth_wall else "FOURTH-WALL MODE IS OFF. Stay focused on story-world strategy and tracked facts; do not discuss software or hidden engine implementation."}
{"THE PLAYER'S MESSAGE WAS SHORT/LOW-EFFORT — MIRROR THAT. Answer in exactly one direct sentence. Leave points and follow_ups empty. Do not pad a quick question into a full structured briefing, even if you could say more — the only exception is if the question is truly impossible to answer in one sentence, in which case answer as briefly as the question actually allows." if concise else "Give a real briefing: enough to support a decision, organized and concrete, but still sounds like someone talking to you, not a form being filled out."}
{"THE PLAYER'S WORDING SUGGESTS THEY WANT A VISUAL (graph/chart/plot) — populate the chart field; don't just describe the numbers in prose instead." if wants_chart else ""}
You never alter game state; this is a conversation only. Return ONLY valid JSON, no markdown fences."""
        # The Advisor is a high-context reasoning role. Falling back to the
        # cheap background/event model made it noticeably less coherent. An
        # explicit Advisor override still wins; otherwise use the same main
        # model as the GM. Advisor calls are player-triggered, so this does not
        # increase normal per-turn call count.
        routed = bool(self.settings.get("advisor_model") or self.settings.get("advisor_provider") in {"local", "cloud"})
        advisor_client = self.ai_advisor if routed else self.ai
        data = normalize_object_response(advisor_client.request(rules, payload, max_output_tokens=200 if concise else 1000), "summary")
        data, _ = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
        entry = {
            "role": "advisor",
            "summary": (data.get("summary") or "").strip() or "...",
            "points": [ai_text(p) for p in (data.get("points") or []) if ai_text(p)][:8],
            "follow_ups": [ai_text(q) for q in (data.get("follow_ups") or []) if ai_text(q)][:3],
            "chart": self._sanitize_advisor_chart(data.get("chart")),
            "evidence": self._advisor_evidence(question, advisor_state),
            "fourth_wall": bool(fourth_wall), "canon_countdown": self.canon_countdown(),
            "turn": self.state.get("turn", 0),
        }
        with self.lock:
            self.state.setdefault("advisor_thread", []).append(entry)
            self.autosave()
        return {"entry": entry, "state": self.public_state()}

    def _local_power_comparison(self, question, fourth_wall=False):
        """Guarantee a direct, same-scale comparison before AI compliance can
        become a factor.  Tracked campaign evidence wins; the compact canon
        table and world-role baseline are transparent estimates, not sheets."""
        raw = str(question or "").strip()
        text = raw.lower()
        comparison_requested = bool(re.search(
            r"\b(compare[ds]?|comparison|versus|vs\.?|against|relative to|stack up|stronger than|weaker than|"
            r"how strong am i compared|where do i rank among)\b", text,
        ))
        if not comparison_requested:
            return None
        world = self.state.get("world", "Custom World")
        profile = power_profile_for(world, self.state.get("stats", {}), (self.state.get("special") or {}).get("Archetype", ""))
        player_score = float((profile.get("world_combat") or profile.get("combat") or {}).get("score", 0) or 0)
        candidates = {}
        evidence = {}

        for name, memory in (self.state.get("npc_memories") or {}).items():
            if not name or str(name).lower() not in text or not isinstance(memory, dict):
                continue
            score = memory.get("power_score", memory.get("power"))
            if not isinstance(score, (int, float)) and isinstance(memory.get("stats"), dict):
                score = (power_profile_for(world, memory["stats"], memory.get("archetype", "")).get("world_combat") or {}).get("score")
            if not isinstance(score, (int, float)):
                role_text = " ".join(str(memory.get(key) or "") for key in ("role", "position", "rank", "status", "affiliation", "goal"))
                score = _role_power_estimate(world, role_text)
            if isinstance(score, (int, float)):
                candidates[str(name)] = float(score)
                evidence[str(name)] = "tracked campaign estimate" if memory.get("power_score") is not None or memory.get("stats") else "tracked world-role estimate"

        canon = LOCAL_CANON_POWER_ESTIMATES.get(world, {})
        for key in sorted(canon, key=len, reverse=True):
            if key in text and not any(key in existing.lower() for existing in candidates):
                label = " ".join(part.capitalize() for part in key.split())
                candidates[label] = float(canon[key])
                evidence[label] = "canon/role estimate at this story scale"

        # The identity registry is much broader than the hand-tuned headline
        # score table.  A named canon figure therefore falls back to their
        # current-era office/role, not a generic Chūnin/Officer midpoint.
        for record in active_canon_identities(world, self.state):
            aliases = [record.get("name"), *(record.get("aliases") or [])]
            if not any(alias and re.search(rf"(?<!\w){re.escape(str(alias).lower())}(?!\w)", text)
                       for alias in aliases):
                continue
            record_names = [str(alias).lower() for alias in aliases if alias]
            if any(any(alias == existing.lower() or alias in existing.lower() or existing.lower() in alias
                       for alias in record_names) for existing in candidates):
                continue
            score = _role_power_estimate(world, " ".join(str(record.get(key) or "") for key in ("role", "affiliation", "duty_title")))
            if score is not None:
                label = str(record.get("name") or aliases[0])
                candidates[label] = score
                evidence[label] = "current-era canon role estimate"

        if "akatsuki" in text and world == "Naruto":
            for key in ("pain", "itachi", "kisame", "kakuzu", "sasori", "deidara", "konan", "hidan"):
                label = key.capitalize()
                candidates.setdefault(label, float(canon[key])); evidence.setdefault(label, "canon Akatsuki estimate")

        # A request for a fictional/custom scale (for example DBZ power
        # levels) is a presentation choice rather than a world benchmark.
        # Let the model translate it unless the question also names concrete
        # targets that the deterministic comparison engine can identify.
        if not candidates and re.search(r"\b(?:dbz|dragon ball|custom scale|my own scale)\b", text):
            return None

        if not candidates:
            tail = re.search(r"(?:compared (?:to|with)|versus|vs\.?|against|relative to)\s+(.+?)[?.!]*$", raw, re.I)
            if tail:
                names = [re.sub(r"^(?:an?|the)\s+", "", item.strip(), flags=re.I)
                         for item in re.split(r"\s*,\s*|\s+and\s+", tail.group(1))]
                names = [name for name in names if name and name.lower() not in {"others", "everyone", "them"}]
                if names:
                    tiers = benchmark_context(world).get("tiers", [])
                    baseline = float(tiers[min(4, len(tiers) - 1)]["threshold"] if tiers else 65)
                    for name in names[:6]:
                        candidates[name[:60]] = baseline
                        evidence[name[:60]] = "low-confidence world-role estimate; no tracked feats yet"
        if not candidates:
            return None

        tiers = benchmark_context(world).get("tiers", [])
        def tier_name(score):
            valid = [row for row in tiers if float(row.get("threshold", 0)) <= score]
            return (valid[-1]["name"] if valid else (tiers[0]["name"] if tiers else "world-relative"))
        rows = [(self.state.get("name") or "You", player_score, "current mechanical stats")]
        rows.extend((name, score, evidence.get(name, "estimate")) for name, score in candidates.items())
        rows = rows[:9]
        points = []
        for name, score, source in rows[1:]:
            ratio = player_score / max(1.0, score)
            verdict = ("decisively stronger" if ratio >= 1.75 else "stronger" if ratio >= 1.2 else
                       "roughly comparable" if ratio >= .84 else "weaker" if ratio >= .57 else "decisively weaker")
            points.append(f"Against {name}: you are {verdict} on balanced combat ({player_score:.1f} vs {score:.1f}); {name} is estimated as {tier_name(score)} from {source}.")
        strongest = max(rows[1:], key=lambda row: row[1])
        weakest = min(rows[1:], key=lambda row: row[1])
        if len(rows) == 2:
            bottom_line = points[0].split(";", 1)[0] + "."
        else:
            bottom_line = f"On current balanced combat, you range from {('above' if player_score > weakest[1] else 'below')} {weakest[0]} to {('above' if player_score > strongest[1] else 'below')} {strongest[0]}; the exact matchups still depend on speed, defense, experience, and special abilities."
        return {
            "role": "advisor", "summary": bottom_line, "points": points,
            "follow_ups": ["Which matchup is most dangerous for me?", "What stat would improve these matchups most?"],
            "chart": {"title": f"Current {world} power comparison", "unit": "Balanced combat estimate",
                      "items": [{"label": name, "value": round(score, 1)} for name, score, _ in sorted(rows, key=lambda row: row[1], reverse=True)]},
            "fourth_wall": bool(fourth_wall), "canon_countdown": self.canon_countdown(),
            "turn": self.state.get("turn", 0), "answered_locally": True,
        }

    def _local_advisor_answer(self, question, fourth_wall=False):
        """Answer factual dashboard questions locally instead of paying AI."""
        text = str(question or "").strip().lower()
        turn = self.state.get("turn", 0)
        profile = power_profile_for(self.state.get("world", "Custom World"), self.state.get("stats", {}),
                                    (self.state.get("special") or {}).get("Archetype", ""))
        comparison_requested = bool(re.search(
            r"\b(compare[ds]?|comparison|versus|vs\.?|against|relative to|stack up|other members?|"
            r"stronger than|weaker than|where do i rank|among the)\b", text))
        player_power_question = bool(re.search(
            r"\b(how strong am i|how powerful am i|my (?:current )?(?:strength|power|power level|power tier|stats)|where do i rank)\b",
            text))
        if player_power_question and not comparison_requested:
            combat = profile.get("world_combat") or profile.get("combat", {})
            peak = profile.get("peak", {})
            axes = profile.get("axes", {})
            summary = f"Your balanced combat profile is {combat.get('name')} ({combat.get('score')}); your peak is {peak.get('stat')} {peak.get('value')}, which does not replace your speed and defense values."
            points = [f"Offense: {axes.get('offense', {}).get('stat')} {axes.get('offense', {}).get('value')}",
                      f"Speed: {axes.get('speed', {}).get('stat')} {axes.get('speed', {}).get('value')}",
                      f"Defense: {axes.get('defense', {}).get('stat')} {axes.get('defense', {}).get('value')}"]
        elif re.search(r"\b(next (?:canon|major) event|how long until|countdown)\b", text):
            countdown = self.canon_countdown() or {}
            if not countdown:
                summary, points = "No known major canon boundary is currently scheduled.", []
            else:
                title = countdown.get("title") or countdown.get("event") or "the next major event"
                remaining = countdown.get("label") or countdown.get("time_until") or countdown.get("days_until") or "an unknown interval"
                summary, points = f"{title} is {remaining} away on the current campaign timeline.", []
        elif re.fullmatch(r"\s*(what should i do next|what(?:'s| is) my (?:current )?(?:quest|agenda|objective)|show me my (?:current )?(?:quest|agenda|objective))[?!.\s]*", text):
            quests = [q for q in self.state.get("quests", []) if isinstance(q, dict) and str(q.get("status", "active")).lower() == "active"]
            if not quests: return None
            quest = quests[0]; title = quest.get("title") or quest.get("name") or "Current objective"
            summary = f"Your clearest active lead is {title}: {quest.get('description') or quest.get('objective') or 'follow its current lead'}."
            points = [str(quest.get("first_step") or quest.get("next_step") or "Review the known clues and choose the next concrete step.")]
        elif re.search(r"\b(standing (?:order|instruction|intent)|ongoing (?:order|instruction|duty|routine)|what (?:is|are) still being done)\b", text):
            intents = active_standing_intents(self.state)
            if not intents:
                summary, points = "You have no continuing instructions recorded right now.", []
            else:
                summary = f"{len(intents)} continuing instruction{'s are' if len(intents) != 1 else ' is'} still in force."
                points = [f"{row.get('directive')}" + (f" — paused: {row.get('blocked_reason')}" if row.get("status") == "temporarily_blocked" else "") for row in intents[:8]]
        elif fourth_wall and re.search(r"\b(ai cost|token|cost|calls?)\b", text):
            clients = {id(client): client for client in (self.ai, self.ai_bg, self.ai_major)}.values()
            calls = sum(client.usage.get("calls", 0) for client in clients); cost = sum(client.usage.get("cost_usd", 0) for client in clients)
            summary, points = f"This session has used {calls} text-AI calls for an estimated ${cost:.4f}; this answer used none.", []
        else:
            return None
        return {"role": "advisor", "summary": summary, "points": points, "follow_ups": [],
                "chart": None, "fourth_wall": bool(fourth_wall), "canon_countdown": self.canon_countdown(),
                "turn": turn, "answered_locally": True}

    @staticmethod
    def _sanitize_advisor_chart(raw):
        """The model sometimes returns chart items with a non-numeric value,
        a missing label, or more entries than the schema asked for — none of
        that should be able to break rendering, so coerce or drop rather
        than trusting the shape."""
        if not isinstance(raw, dict):
            return None
        items = []
        for item in (raw.get("items") or [])[:8]:
            if not isinstance(item, dict):
                continue
            label = ai_text(item.get("label") or item.get("name") or "")
            value = item.get("value")
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if not label:
                continue
            items.append({"label": label, "value": value})
        if not items:
            return None
        return {
            "title": ai_text(raw.get("title") or "") or "Comparison",
            "unit": ai_text(raw.get("unit") or ""),
            "items": items,
        }

    def ensure_contact(self, name, kind="person", details=None):
        if not name:
            return
        contacts = self.state.setdefault("contacts", {})
        if not isinstance(contacts, dict):
            contacts = self.state["contacts"] = {}
        if not isinstance(contacts.get(name), dict):
            contacts[name] = {
                "name": name, "kind": kind, "status": "Known", "relationship": 0, "last_known_location": "Unknown",
                "notes": [], "can_contact": True, "first_met_turn": self.state.get("turn", 0)
            }
        c = contacts[name]
        if details and isinstance(details, dict):
            c.update(details)
        threads = self.state.setdefault("chat_threads", {})
        if not isinstance(threads, dict):
            threads = self.state["chat_threads"] = {}
        if not isinstance(threads.get(name), list):
            threads[name] = []

    def add_chat_message(self, thread, sender, text, direction="incoming", metadata=None):
        self.ensure_contact(thread, "group" if thread in self.state.get("group_chats", {}) else "person")
        msg = {"time": self.state.get("world_time", "Unknown"), "turn": self.state.get("turn", 0),
               "sender": sender, "text": text, "direction": direction, "metadata": metadata or {}}
        self.state["chat_threads"][thread].append(msg)
        if direction == "incoming":
            self.state.setdefault("unread_chats", []).append({"thread": thread, "turn": self.state.get("turn", 0)})
            deliveries = self.state.setdefault("message_delivery_state", {})
            if not isinstance(deliveries, dict):
                deliveries = self.state["message_delivery_state"] = {}
            if not isinstance(deliveries.get(thread), dict):
                deliveries[thread] = {}
            delivery = deliveries[thread]
            delivery["last_incoming_turn"] = int(self.state.get("turn", 0) or 0)
        elif direction == "outgoing":
            deliveries = self.state.setdefault("message_delivery_state", {})
            if not isinstance(deliveries, dict):
                deliveries = self.state["message_delivery_state"] = {}
            if not isinstance(deliveries.get(thread), dict):
                deliveries[thread] = {}
            delivery = deliveries[thread]
            delivery["last_outgoing_turn"] = int(self.state.get("turn", 0) or 0)
        return msg

    def resolve_side_chat(self, thread, message):
        from campaign_reliability import build_grounding_packet
        from gm_consistency import CHAT_CONSISTENCY_RULE, prepare_request, semantic_issues, record_fact_changes
        with self.lock:
            self.add_chat_message(thread, self.state.get("name", "You"), message, "outgoing")
        if not self.ai_ready():
            return {"state": self.public_state(), "story": self._flush_story()}
        contact = self.state.get("contacts", {}).get(thread, {})
        # Same effort-matching as the Advisor's concise mode: a one-line
        # text doesn't need the same output budget as a real negotiation
        # attempt, and asking for less also reinforces the length-matching
        # instruction below rather than leaving the model room to pad anyway.
        concise = len(str(message).split()) <= 6
        payload = {
            "task": "side_chat_reply", "role": "Narrator + NPC dialogue", "thread": thread, "player_message": message,
            "state": self.trimmed_state_for_ai(f"{thread}: {message}", "chat"), "thread_history": self.state.get("chat_threads", {}).get(thread, [])[-20:],
            "grounding_packet": build_grounding_packet(self.state, f"{thread}: {message}", "chat", 8),
            "contact": contact, "reputation": self.state.get("reputation", {}), "affiliations": self.state.get("affiliations", []),
            "requirements": [
                "Respond naturally as the contacted NPC/group if they are able and willing to respond — this is real-time back-and-forth, not a narrated summary of the conversation.",
                "Independent people may refuse, delay, disagree or end the conversation when their actual motives support it. Loyal subordinates follow clear feasible orders under recognized authority; do not rewrite their objective or invent reluctance. Advice may accompany compliance.",
                "Base tone, willingness to help, and honesty on the player's actual reputation/standing with this specific person or group and any relevant affiliation/rank — a hostile or unfamiliar faction should be curt, guarded, or refuse outright; a trusted contact or fellow member should be warmer and more forthcoming. Never treat the player as automatically trusted or important.",
                "Text the player wrote in [brackets] is a physical action attempted during the conversation (a gesture, handing something over, drawing a weapon, leaving), not something said aloud — react to it as an action with real in-fiction weight, not as dialogue.",
                "Use lore-appropriate communication methods for this contact — an individual might text/message/scry/etc., but a large faction/polity typically replies through a representative, herald, official channel, or delay appropriate to their scale, not as if the whole organization is one person instantly texting back.",
                "Do not pause or replace the main adventure scene.",
                "Before responding, check campaign_canon (recent turn history) and this contact's npc_memories entry for anything the player and this contact have already done, discussed, or resolved together — including in the main scene, not just prior chat messages. Never have them ask about, re-propose, or act surprised by something already settled; reference it as already known instead.",
                "Any meaningful promise, information, relationship change, quest lead, or arrangement must be represented in state_patch.",
                "If this conversation creates a promise, deadline, grudge, standing order, or new agenda item for the contacted person or group, record it in state_patch.scheduled_events (with due_canon_day) and/or update their entry in npc_clocks/faction_clocks — a commitment made here must be able to resurface naturally in a future world update, the same as one made in the main scene.",
                "Keep the reply's length roughly proportional to the player's message — a short line deserves a short reply, not a paragraph; match their register and effort rather than always writing at maximum length."
            ],
            "schema": {"reply": "string or empty if no immediate reply", "sender": "speaker",
                       "state_patch": "contacts, npc_memories, relationships, quests, scheduled_events, npc_clocks, faction_clocks or other side-chat consequences",
                       "events": "system notifications if needed"}
        }
        payload = prepare_request(self.state, payload)
        rules = self.core_rules() + CHAT_CONSISTENCY_RULE
        budget = (250 if concise else 600) if payload.get("command_contracts") else (150 if concise else 500)
        data = normalize_object_response(self.ai.request(rules, payload, max_output_tokens=budget), "reply")
        issues = semantic_issues(self.state, {**data, "narrative": f"{thread} {data.get('reply', '')}"}, payload)
        if issues:
            data = normalize_object_response(self.ai.request(rules + "\nRepair only the listed contradictions; preserve all valid content.",
                {**payload, "repair_draft": data, "repair_issues": issues}, max_output_tokens=budget), "reply")
            if semantic_issues(self.state, {**data, "narrative": f"{thread} {data.get('reply', '')}"}, payload):
                raise ValueError("The NPC reply contradicted established campaign facts and was not applied. Retry the message.")
        data, _ = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="side_chat")
            from organizations import process_organizations
            process_organizations(before, self.state, data, 0)
            record_fact_changes(before, self.state)
            from turn_recovery import remember_commands
            remember_commands(self.state, data)
            reply = data.get("reply", "").strip()
            if reply:
                sender = data.get("sender") or thread
                self.add_chat_message(thread, sender, reply, "incoming")
            notifications = self.notify(before, self.state, data.get("events", []))
            update_continuity(before, self.state, f"Message to {thread}: {message}", data.get("reply", ""))
            self.autosave()
        return {"reply": data.get("reply", ""), "notifications": notifications, "state": self.public_state(), "story": self._flush_story()}

    def maybe_generate_incoming_chat(self):
        if self.busy or not self.ai_bg_ready() or not self.state.get("contacts"):
            return None
        if self.state.get("turn", 0) % 2 != 0:
            return None
        if self.settings.get("local_message_gate", True) and not self._incoming_message_candidates():
            return None
        payload = {
            "task": "incoming_chat_check", "role": "World/NPC Simulator", "state": self.trimmed_state_for_ai(),
            "requirements": [
                "Determine whether any known contact or group would plausibly message the player right now.",
                "Do not force a message. If nobody has a reason, return send=false.",
                "Base motivation on current events, relationship, quests, prior promises, faction activity, danger, rumors, or the NPC's own goals.",
                "The sender may only know information they could realistically know.",
                "Keep messages natural and in-character.",
                "Major recurring canon/world characters should be favored when they have a strong reason to contact the player.",
                "Current companions who are not physically present this turn are especially plausible senders — they have an ongoing stake in the player's life and should check in, share news, or follow up on their own initiative, not only when the player messages first.",
                "Before proposing any plan, activity, question, or piece of news, check campaign_canon (recent turn history) and this contact's npc_memories entry for whether it has already happened, been discussed, or been resolved with the player. Never pitch something already done together as a new idea, ask about something already answered, or act surprised by something the player already told them — if it's already settled, either don't send a message about it at all, or reference it as something already known (a follow-up, a thank-you, a next step) rather than raising it as if for the first time."
            ],
            "schema": {"send": "boolean", "thread": "contact/group name", "sender": "speaker name",
                       "message": "short natural chat message", "contact_patch": "optional contact/group metadata updates"}
        }
        rules = self.core_rules(extra="You are checking for an unsolicited communication event, not advancing the main scene.\n"
                                      "Messages are asynchronous side communications. Preserve lore, technology, communication methods, distance, and world rules.\n"
                                      "If the world has no modern phones, interpret 'chat' as the nearest lore-appropriate medium: Den Den Mushi, messenger, letter, radio, courier, system message, guild chat, etc.")
        try:
            data = normalize_object_response(self.ai_bg.request(rules, payload, max_output_tokens=350), "message")
            data, _ = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
        except Exception as e:
            self.log("Background chat check failed: " + str(e))
            return None
        if not data.get("send"):
            return None
        with self.lock:
            thread = data.get("thread") or data.get("sender")
            sender = data.get("sender") or thread
            from relationship_life import route
            if not route(self.state, str(sender or '')):
                return None
            self.ensure_contact(thread, "group" if data.get("contact_patch", {}).get("kind") == "group" else "person", data.get("contact_patch") or {})
            self.add_chat_message(thread, sender, data.get("message", ""), "incoming")
            self.append(f"[MESSAGE — {thread}]\n{sender}: {data.get('message', '')}", "system")
            self.log(f"Incoming message from {sender} in {thread}")
            self.autosave()
        return {"thread": thread, "sender": sender, "message": data.get("message", "")}

    def _incoming_message_candidates(self):
        """Zero-cost relevance gate before asking a model to compose a message."""
        turn = int(self.state.get("turn", 0) or 0); candidates = []
        delivery = self.state.get("message_delivery_state") if isinstance(self.state.get("message_delivery_state"), dict) else {}
        memories = self.state.get("npc_memories") if isinstance(self.state.get("npc_memories"), dict) else {}
        schedules = self.state.get("npc_schedules") if isinstance(self.state.get("npc_schedules"), dict) else {}
        for name, contact in (self.state.get("contacts") or {}).items():
            if not isinstance(contact, dict):
                continue
            sent = delivery.get(name, {}) if isinstance(delivery.get(name), dict) else {}
            if turn - int(sent.get("last_incoming_turn", -99) or -99) < 3:
                continue
            due = contact.get("next_contact_turn")
            if contact.get("urgent") or contact.get("pending_reply") or contact.get("message_due") or (isinstance(due, (int, float)) and due <= turn):
                candidates.append(str(name))
                continue
            thread = (self.state.get("chat_threads") or {}).get(name, [])
            if isinstance(thread, list) and thread:
                last = thread[-1] if isinstance(thread[-1], dict) else {}
                if last.get("direction") == "outgoing" and turn - int(last.get("turn", turn) or turn) <= 6:
                    candidates.append(str(name)); continue
            memory = memories.get(name, {}) if isinstance(memories.get(name), dict) else {}
            if memory.get("recurring") and (memory.get("goal") or memory.get("immediate_goal")):
                candidates.append(str(name)); continue
            schedule = schedules.get(name, {}) if isinstance(schedules.get(name), dict) else {}
            due_turn = schedule.get("due_turn") or schedule.get("next_turn")
            if isinstance(due_turn, (int, float)) and due_turn <= turn + 1:
                candidates.append(str(name))
        for companion in self.state.get("companions", []) or []:
            if isinstance(companion, dict) and companion.get("name") and companion.get("location") and companion.get("location") != self.state.get("location"):
                candidates.append(str(companion["name"]))
        recent = " ".join(str(row.get("text") or row.get("summary") or row) for row in (self.state.get("world_events") or [])[-3:] if isinstance(row, (dict, str))).lower()
        if recent:
            candidates.extend(str(name) for name in (self.state.get("contacts") or {}) if str(name).lower() in recent)
        from relationship_life import route
        return [name for name in dict.fromkeys(candidates) if route(self.state, name)][:8]

    def create_world_event_if_due(self):
        current_day = int(self.state.get("canon_day", 0) or 0)
        last_tick_day = self.state.get("last_protagonist_tick_day")
        if last_tick_day is None:
            # First time this runs for a campaign — establish the baseline
            # without firing immediately (there's no "since last time" yet).
            self.state["last_protagonist_tick_day"] = current_day
            last_tick_day = current_day
        due_by_day = (current_day - int(last_tick_day)) >= 30
        due_by_turn = bool(self.state.get("turn", 0) and self.state["turn"] % 4 == 0)
        if not ((due_by_day or due_by_turn) and self.ai_bg_ready() and not self.busy):
            return None
        world = self.state.get("world", "Custom World")
        canon_cast = playable_characters_for(world)
        protagonist = canon_cast[0].get("name") if canon_cast else None
        payload = {"task": "background_world_tick", "state": self.trimmed_state_for_ai(), "protagonist": protagonist or "",
                   "requirements": [
                       "Advance off-screen NPC/faction activity by a modest amount. Do not teleport anyone. Do not force the player into a scene.",
                       (f"This world's canon protagonist is {protagonist}. Advance their own canon-consistent arc by roughly a month's worth of activity in the background — training, missions, relationships, canon plot beats — and record it via npc_memories or other justified state_patch fields, whether or not the player currently knows any of it. Their story keeps moving forward on its own timeline even when the player never crosses paths with them."
                        if protagonist else "This world has no single canon protagonist to track — just advance the wider world as usual."),
                       "Only return a player-visible heard_event when this tick's changes would actually reach or affect the player or a portion of the world connected to them — never for the protagonist's own routine, unconnected progress. Most ticks should leave heard_event empty."
                   ],
                   "schema": {"state_patch": "world_events, npc_memories, factions, canon_divergences or other justified world-state changes", "heard_event": "brief rumor/news/observation or empty"}}
        rules = self.core_rules(extra="This is a background simulation tick. Preserve geography, travel time, NPC knowledge and causality. Do not resolve a player action.")
        try:
            data = normalize_object_response(self.ai_bg.request(rules, payload, max_output_tokens=450), "heard_event")
            data, _ = repair_canon_payload(self.state.get("world", "Custom World"), data, self.state)
        except Exception as e:
            self.log("World tick failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="world_tick")
            self.state["last_protagonist_tick_day"] = current_day
            heard = data.get("heard_event", "").strip()
            if heard:
                self.append("[WORLD UPDATE]\n" + heard, "system")
                self.log("World update: " + heard)
            update_continuity(before, self.state, "Background world tick", heard)
            self.autosave()
        return {"heard_event": data.get("heard_event", "")}

    # allow_time=False (apply_guarded_patch) only blocks time/calendar
    # fields — it was never meant to be a general "background-tick-safe"
    # filter, so a reentry recap needs its own explicit whitelist to
    # actually guarantee it can't touch the player's own stats, inventory,
    # currency, or location, matching what the prompt asks for with a real
    # mechanical backstop instead of trusting the model to comply.
    REENTRY_RECAP_ALLOWED_PATCH_FIELDS = {"npc_memories", "factions", "canon_divergences", "npc_relationships", "faction_clocks", "npc_clocks"}

    def generate_reentry_recap(self):
        """A short narrated "since you've been away" paragraph, triggered
        from load() detecting a real-world gap (see
        REENTRY_RECAP_THRESHOLD_HOURS) — the one place the world visibly
        keeps moving purely because time passed for the PLAYER, not because
        they took any action. Deliberately narrative-only: no canon_day/
        world_time movement (ordinary player absence can never advance
        those, same rule as an ordinary turn), and the allowed state_patch
        is restricted the same way the background world tick's already is,
        so this can record real off-screen developments (an NPC's goal
        advancing, a faction's fortunes shifting) without ever touching the
        player's own stats, inventory, currency, or location."""
        hours = self._pending_reentry_hours
        self._pending_reentry_hours = None
        if not hours or self.busy:
            return None
        if self.settings.get("local_reentry_recap", True) and isinstance(self.ai_bg, AI):
            feed = []
            for row in (self.state.get("background_world_feed") or [])[-3:]:
                text = (row.get("text") or row.get("summary")) if isinstance(row, dict) else str(row)
                if text:
                    feed.append(str(text).strip())
            active_clocks = []
            clocks = {**(self.state.get("faction_clocks") or {}), **(self.state.get("npc_clocks") or {})}
            for name, clock in clocks.items():
                if isinstance(clock, dict) and clock.get("status", "active") == "active":
                    active_clocks.append(f"{name} remains focused on {clock.get('goal') or 'its existing plans'}")
            details = feed[-2:] or active_clocks[:2]
            recap = ("While you were away, " + " ".join(details)) if details else ""
            if recap:
                recap = recap.rstrip(". ") + ". No in-world time passed while the campaign was closed."
                self.append("[WHILE YOU WERE AWAY]\n" + recap, "narrative")
                self.autosave()
            return {"recap": recap, "state": self.public_state(), "story": self._flush_story(), "generated_locally": True}
        if not self.ai_bg_ready():
            return None
        payload = {
            "task": "reentry_recap", "hours_away": hours, "state": self.trimmed_state_for_ai(),
            "recent_background_feed": (self.state.get("background_world_feed") or [])[-10:],
            "requirements": [
                f"The player was away from the app for about {hours:.0f} hours of real time — not in-game time, which has not moved (ordinary absence never advances world_time/canon_day, exactly like an ordinary turn never does).",
                "Write ONE short narrated paragraph (3-6 sentences) of what plausibly stirred elsewhere while the player wasn't looking, grounded in recent_background_feed and any tracked npc_clocks/faction_clocks/npc_relationships — build on threads already in motion rather than inventing disconnected new ones.",
                "This is atmosphere reaching the player on return (a messenger, a notice, something a companion mentions), not something that happened TO the player — never move the player's own location, stats, currency, inventory, or HP, and never advance canon_day/world_time/calendar.",
                "Keep it proportional to the gap — a few hours away is a quiet aside, not a war concluding. Modest off-screen movement (npc_memories, factions, canon_divergences) may still be recorded via state_patch the same way the regular background world tick can, but nothing time- or player-state-related.",
                "If genuinely nothing worth narrating has moved, return an empty recap rather than manufacturing filler.",
            ],
            "schema": {"recap": "the paragraph, or empty", "state_patch": "npc_memories, factions, canon_divergences or other justified non-time, non-player-state changes only"},
        }
        rules = self.core_rules(extra="This is a reentry recap, not a scene and not a time skip. Do not resolve a player action. Do not advance time.")
        try:
            data = normalize_object_response(self.ai_bg.request(rules, payload, max_output_tokens=350), "recap")
        except Exception as e:
            self.log("Reentry recap failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            # allow_time=False on its own only blocks time/calendar fields,
            # not general player-state ones — the requirements above ask
            # the model nicely not to touch hp/currency/location, but
            # nothing enforced that until this whitelist. A real turn earns
            # the right to touch player state; a background recap the
            # player didn't act to trigger does not.
            raw_patch = data.get("state_patch", {})
            safe_patch = {k: v for k, v in raw_patch.items() if k in self.REENTRY_RECAP_ALLOWED_PATCH_FIELDS} if isinstance(raw_patch, dict) else {}
            apply_guarded_patch(self.state, safe_patch, allow_time=False, source="reentry_recap")
            recap = str(data.get("recap", "")).strip()
            if recap:
                self.append("[WHILE YOU WERE AWAY]\n" + recap, "narrative")
                self.log("Reentry recap generated.")
            update_continuity(before, self.state, "Reentry recap", recap)
            self.autosave()
        return {"recap": recap, "state": self.public_state(), "story": self._flush_story()}

    def run_memory_manager(self):
        if not self.ai_bg_ready() or self.busy:
            return None
        payload = {"task": "memory_manager", "role": "Memory Manager", "state": self.trimmed_state_for_ai(),
                   "requirements": "Compress/update recurring NPC memories, relationship facts, promises, debts, suspicions, discovered facts, and last-known locations. Preserve uncertainty and delete nothing important. Do not narrate a scene.",
                   "schema": {"state_patch": "npc_memories, contacts, chat_threads metadata, relationships, codex, location_details, ability_progress or other memory-oriented changes only", "memory_note": "brief maintenance note or empty"}}
        rules = self.core_rules(extra="You are the MEMORY MANAGER. Be conservative. Never invent player actions, secret knowledge, or relationship changes unsupported by the state.")
        try:
            data = normalize_object_response(self.ai_bg.request(rules, payload, max_output_tokens=450), "memory_note")
        except Exception as e:
            self.log("Memory manager failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="memory_manager")
            note = data.get("memory_note", "").strip()
            if note:
                self.log("Memory: " + note)
            update_continuity(before, self.state, "Continuity audit", note)
            self.autosave()
        return {"memory_note": data.get("memory_note", "")}

    def sync_contacts_from_state(self):
        with self.lock:
            for name, mem in self.state.get("npc_memories", {}).items():
                if not isinstance(mem, dict):
                    continue
                significance = mem.get("importance", mem.get("significance", ""))
                recurring = mem.get("recurring", False) or significance in ("major", "important", "high")
                can_contact = mem.get("can_contact", False) or mem.get("contact_method")
                if recurring or can_contact:
                    self.ensure_contact(name, "person", {
                        "last_known_location": mem.get("last_known_location", "Unknown"),
                        "can_contact": bool(can_contact),
                        "contact_method": mem.get("contact_method", "Lore-appropriate"),
                        "notes": mem.get("notes", [])
                    })
            self.autosave()
