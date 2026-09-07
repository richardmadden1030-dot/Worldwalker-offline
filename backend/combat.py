"""Local, AI-cost-free combat resolver.

The rest of the engine (engine_turns.py) resolves every action — including
combat — through assess() + resolve(), each an AI call. That's fine for a
one-off action, but a fight is a *sequence* of exchanges, and paying for two
AI round-trips per swing makes combat slow and expensive without making it
more fun. This module resolves each exchange locally instead:

  1. The AI still decides when a fight starts and who's in it (as part of a
     normal resolve() call) — narrative judgment stays with the AI.
  2. Every subsequent round (attack/defend/flee) is resolved with plain
     Python: the SAME d100-vs-sampled-difficulty math engine_turns.roll()
     already uses, reusing the player's real stats/skills/titles, so a
     trained skill hits as hard here as it would narratively. No AI call,
     no wait, no cost.
  3. Only "relaying the results" costs anything: one AI call, made once
     (at combat's end, or on request), turns the accumulated mechanical
     log into narration and any loot/injury/consequence state_patch —
     exactly the existing resolve() contract, just fed a combat summary
     instead of a single action.

If the player does something the local engine can't model (negotiate,
improvise with the environment, a puzzle-boss mechanic), the frontend can
still fall back to a normal AI-costing take_turn() — that's a deliberate,
honest scope boundary, not a gap.
"""
import random
import re

from worlds import DIFFICULTIES, abilities_for, primary_stats_for, ability_resource_type_for, speed_stat_for, defense_stat_for, uses_xp_for
from power_benchmarks import benchmark_context
from util import clamp, ai_text
from systems import normalize_tuning
from skill_system import infer_skill_metadata, normalize_skill_map, build_combat_ability_options
from ai_client import AI
from simulation_core import companion_support_for_combat, normalize_encounter_state
from portrait_generator import set_active_portrait_form, clear_active_portrait_form

BASE_HIT_PCT = 0.13         # a bare-minimum successful hit does ~13% of the target's max HP
MARGIN_HIT_PCT = 0.09       # up to another 9% for a big margin over the difficulty
MARGIN_CAP = 60             # margin beyond this stops adding damage (avoids runaway one-shots)
SKILL_DAMAGE_SCALE = 50.0   # a skill_bonus of 50 roughly doubles damage dealt with it
BREAKTHROUGH_MULTIPLIER = 1.5
DEFEND_DAMAGE_REDUCTION = 0.5
MAX_ROUNDS_PER_CALL = 1     # resolve exactly one exchange per API call, so the UI can animate it

# A named ability spends real resource on every USE (hit or miss — you spent
# the chakra channeling the jutsu whether or not it landed), sized as a
# fraction of the player's own max pool so it scales with power level the
# same way damage does: a level-40 character with a 200-Chakra pool spends
# proportionally the same as a level-3 character with a 50-Chakra pool.
BASE_RESOURCE_COST_PCT = 0.15   # a plain named ability costs ~15% of max pool per use
SKILL_COST_SCALE = 150.0        # a skill_bonus of 30 adds ~20% more cost — a more mastered technique is a bigger spend
COOLDOWN_ROUNDS = 3             # cooldown-type abilities (e.g. Overgeared Skills) are unusable for this many rounds after use

# Raw stat-vs-power gaps (both on the same ~10-200 world-relative scale) that
# turn a real mismatch into a real tactical swing, instead of just a slightly
# better d100 bonus: a decisively faster combatant gets a bonus swing, a
# decisively harder-hitting one does drastically more damage, and a
# decisively tougher one can just shrug a hit off completely.
SPEED_GAP_THRESHOLD = 25         # player edge grants a chosen bonus turn; enemy edge grants its extra swing
MASSIVE_GAP_THRESHOLD = 30       # offense-vs-power gap at/above this triggers massive damage; the mirrored gap fully negates a hit
MASSIVE_DAMAGE_MULTIPLIER = 2.5

# A structured "overwhelm" action for canon instant-win-type abilities
# (Rimuru absorbing a foe, flaring Conqueror's Haki to drop weaker fighters,
# a hypnosis/domination effect, etc.) — same d100 math, just checked against
# a harder target than a normal hit unless the power gap already makes the
# outcome a foregone conclusion. Can be attempted every round, Pokéball-style
# — repeat attempts cost nothing extra locally, they just may not land.
OVERWHELM_DIFFICULTY_PADDING = 25


def _fallback_enemy_power(world, enemy):
    """Estimate an underspecified opponent from its own role, never the player.

    The narrator normally supplies canonical power. This only protects local
    combat when a smaller model omits the field; elastic player-level scaling
    would turn every random bandit into a Kage peer.
    """
    enemy = enemy if isinstance(enemy, dict) else {}
    text = " ".join(str(enemy.get(key) or "") for key in
                    ("name", "rank", "title", "role", "type", "description")).lower()
    # World-native tier names provide strong role anchors (Jonin, Captain,
    # Special Grade, Demon Lord, Admiral, and so on).
    ignored = {"class", "candidate", "typical", "ordinary", "combatant", "threat", "scale", "power", "player"}
    tiers = benchmark_context(world).get("tiers", [])
    exact = next((tier for tier in reversed(tiers)
                  if str(tier.get("name", "")).lower() in text), None)
    if exact:
        base = int(exact.get("threshold", 50) or 50)
    else:
        base = None
    for tier in reversed(tiers) if base is None else []:
        words = [word for word in re.findall(r"[a-z0-9'-]+", str(tier.get("name", "")).lower())
                 if len(word) >= 4 and word not in ignored]
        if words and any(word in text for word in words):
            base = int(tier.get("threshold", 50) or 50)
            break
    else:
        if base is not None:
            pass
        elif re.search(r"\b(civilian|bystander|merchant|farmer|child)\b", text):
            base = 15
        elif re.search(r"\b(bandit|thug|robber|mugger|street gang|common criminal|rookie)\b", text):
            base = 30
        elif re.search(r"\b(guard|soldier|enforcer|patrol|mercenary|trained fighter)\b", text):
            base = 50
        elif re.search(r"\b(veteran|elite|champion|assassin|commander|boss)\b", text):
            base = 90
        else:
            # Unknown does not mean "equal to the player." It means a stable
            # competent local baseline until the GM supplies better lore.
            base = 50
    try:
        group_size = max(1, int(enemy.get("group_size") or (2 if enemy.get("is_group") else 1)))
    except (TypeError, ValueError):
        group_size = 1
    return clamp(base + min(40, max(0, group_size - 1) * 5), 5, 2000)


class CombatMixin:
    # ---------- setup / backfill ----------
    def ensure_combat_numbers(self):
        """Combat is always exactly player vs. one opposing entity — a
        single person, or a whole group represented as one aggregate (see
        gm_rules). The AI is asked to give that entity numeric
        difficulty_min/max, attack_min/max and power; if it ever
        under-specifies one (a smaller model skipping a field is common),
        fill it from the opponent's own stated role and world benchmark so
        combat stays resolvable without ever level-scaling to the player."""
        combat = self.state.get("combat")
        if not isinstance(combat, dict) or not combat.get("active"):
            return
        world = self.state.get("world", "Custom World")
        combat.setdefault("round", 1)
        combat.setdefault("player_defense_ability", (primary_stats_for(world, self.state.get("special", {}).get("Archetype", "")) or abilities_for(world))[0])

        # Backward compat: a save/in-flight fight from before combat became
        # strictly 1v1-or-1-group may still carry an old-style "enemies"
        # list. Collapse it into one aggregate opponent instead of breaking.
        if not combat.get("enemy") and combat.get("enemies"):
            legacy = [e for e in combat["enemies"] if isinstance(e, dict)]
            if legacy:
                # Keep individuals for the tactical renderer/resolver; the
                # aggregate remains only as a compatibility summary.
                import copy
                combat.setdefault("opponents", copy.deepcopy(legacy))
                combat["enemy"] = {
                    "name": legacy[0].get("name", "Enemy") if len(legacy) == 1 else f"{legacy[0].get('name', 'Enemy')} and allies",
                    "is_group": len(legacy) > 1, "group_size": len(legacy) if len(legacy) > 1 else None,
                    "hp": sum(int(e.get("hp", 0) or 0) for e in legacy),
                    "hp_max": sum(int(e.get("hp_max", 0) or 0) for e in legacy),
                    "power": int(sum(int(e.get("power") or _fallback_enemy_power(world, e)) for e in legacy) / len(legacy)) + min(40, (len(legacy) - 1) * 5),
                    "difficulty_min": min(int(e.get("difficulty_min", 30) or 30) for e in legacy),
                    "difficulty_max": max(int(e.get("difficulty_max", 50) or 50) for e in legacy),
                    "attack_min": min(int(e.get("attack_min", 25) or 25) for e in legacy),
                    "attack_max": max(int(e.get("attack_max", 45) or 45) for e in legacy),
                    "alive": True,
                }
            combat.pop("enemies", None)

        enemy = combat.get("enemy")
        if not isinstance(enemy, dict):
            enemy = {"name": "Enemy"}
            combat["enemy"] = enemy
        enemy.setdefault("alive", enemy.get("hp", 1) > 0)
        power = enemy.get("power")
        if power is None:
            power = _fallback_enemy_power(world, enemy)
            enemy["power_source"] = "world_role_fallback"
        else:
            enemy.setdefault("power_source", "narrator_or_canon")
        enemy["power"] = int(power)
        hp_max = int(enemy.get("hp_max") or enemy.get("hp") or max(20, int(enemy["power"]) * 2))
        enemy["hp_max"] = hp_max
        enemy["hp"] = int(enemy.get("hp", hp_max))
        if enemy.get("difficulty_min") is None or enemy.get("difficulty_max") is None:
            center = clamp(int(enemy["power"] * 1.0), 15, 90)
            enemy["difficulty_min"], enemy["difficulty_max"] = clamp(center - 10, 1, 100), clamp(center + 10, 1, 100)
        if enemy.get("attack_min") is None or enemy.get("attack_max") is None:
            center = clamp(int(enemy["power"] * 0.9), 15, 90)
            enemy["attack_min"], enemy["attack_max"] = clamp(center - 10, 1, 100), clamp(center + 10, 1, 100)

        combat.setdefault("log", [])
        opening = combat.get("opening_check")
        if isinstance(opening, dict) and not combat.get("opening_check_applied"):
            if opening.get("success"):
                margin = max(0, int(opening.get("margin", 0) or 0))
                pct = min(.24, .10 + margin / 500.0 + (.04 if opening.get("breakthrough") else 0))
                damage = max(1, int(round(hp_max * pct)))
                enemy["hp"] = max(1, int(enemy.get("hp", hp_max)) - damage)
                combat["opening_advantage"] = {
                    "damage": damage, "remaining_hp": enemy["hp"],
                    "total": opening.get("total"), "difficulty": opening.get("difficulty"),
                }
                combat["log"].append({
                    "actor": "player", "action": "opening advantage",
                    "ability": opening.get("ability") or combat.get("player_defense_ability"),
                    "success": True, "damage": damage,
                    "total": opening.get("total"), "difficulty": opening.get("difficulty"),
                    "enemy_hp": enemy["hp"], "enemy_hp_max": hp_max,
                })
            combat["opening_check_applied"] = True
        combat.setdefault("narrated_through", 0)
        combat.setdefault("outcome", None)
        combat.setdefault("cooldowns", {})
        combat.setdefault("ally_support", 0)
        supporters = companion_support_for_combat(self.state)
        if supporters:
            # Preserve an explicitly stronger narrator-authored group bonus,
            # while making existing companion combat-support flags functional.
            flagged_bonus = min(30, sum(int(row.get("bonus", 0) or 0) for row in supporters))
            combat["ally_support"] = max(int(combat.get("ally_support", 0) or 0), flagged_bonus)
            combat["supporting_companions"] = supporters
        combat.setdefault("enemy_debuffs", [])
        combat.setdefault("player_buffs", [])
        combat.setdefault("player_debuffs", [])
        combat.setdefault("player_statuses", [])
        combat.setdefault("enemy_statuses", [])
        combat.setdefault("summons", [])
        combat.setdefault("player_shield", 0)
        combat.setdefault("non_lethal", False)
        self.state["skills"] = normalize_skill_map(self.state.get("skills", {}))
        # A broad power may contain several explicitly named applications.
        # Keep those applications out of the top-level Journal while exposing
        # every established move to structured combat.
        combat["ability_options"] = build_combat_ability_options(self.state["skills"])
        # Player-controlled, independent of combat.non_lethal: choosing to
        # spare a real, dangerous opponent only protects THEM from dying to
        # the player's own hits — it does nothing for the player's own HP.
        # Lose this fight and the enemy still kills you; this is mercy you
        # extend, not a safety net you get.
        combat.setdefault("spare_enemy", False)
        normalize_encounter_state(self.state)

    def combat_active(self):
        combat = self.state.get("combat")
        return isinstance(combat, dict) and bool(combat.get("active"))

    # ---------- shared d100 check (same shape as engine_turns.roll(), just parameterized) ----------
    def _combat_check(self, actor_bonus, difficulty_min, difficulty_max):
        shift = int(DIFFICULTIES[self.state["difficulty"]].get("difficulty_shift", 0))
        tuning = normalize_tuning(self.state)
        shift += int(round((tuning.get("combat_danger", 1.0) - 1.0) * 10))
        low, high = clamp(int(difficulty_min) + shift, 1, 100), clamp(int(difficulty_max) + shift, 1, 100)
        if low > high:
            low, high = high, low
        from turn_recovery import stage
        saved_roll = stage(self, "combat_dice", [actor_bonus, low, high])
        if "difficulty" not in saved_roll:
            saved_roll.update(difficulty=random.randint(low, high), raw=random.randint(1, 100))
        difficulty, raw = saved_roll["difficulty"], saved_roll["raw"]
        breakthrough = raw >= 99
        total = raw + actor_bonus + (15 if breakthrough else 0)
        success = total > difficulty
        if raw == 1:
            success = False
        margin = max(0, total - difficulty)
        return {"roll": raw, "total": total, "difficulty": difficulty, "success": success,
                "margin": margin, "breakthrough": breakthrough}

    def _player_offense_bonus(self, ability, skill):
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        benchmark = 30
        stat_bonus = int(round((stat - benchmark) / 4.0))
        detail = self._combat_skill_detail(skill)
        parent = str((detail or {}).get("parent_skill") or skill or "")
        sb = self.skill_bonus(parent) if parent else 0
        if isinstance(detail, dict) and isinstance(detail.get("bonus"), (int, float)):
            sb = int(detail["bonus"])
        tb = self.title_bonus()
        disclosure_bonus = 0
        if self.state.get("world") == "Jujutsu Kaisen" and skill:
            detail = self._combat_skill_detail(skill)
            system = self.state.get("jjk_system") or {}
            technique = (system.get("birth_slot") or {}).get("name")
            if isinstance(detail, dict) and detail.get("parent_technique") == technique:
                disclosure_bonus = int((system.get("technique_disclosure") or {}).get("active_bonus", 0) or 0)
        mastery_bonus = int((detail or {}).get('mastery_bonus', 0) or 0) if isinstance(detail, dict) else 0
        return stat_bonus + sb + tb + disclosure_bonus + mastery_bonus, sb

    def _player_defense_bonus(self, combat):
        ability = combat.get("player_defense_ability") or abilities_for(self.state.get("world", "Custom World"))[0]
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        return int(round((stat - 30) / 4.0))

    def _damage(self, target_hp_max, margin, skill_bonus_used, breakthrough, massive=False):
        pct = BASE_HIT_PCT + (clamp(margin, 0, MARGIN_CAP) / MARGIN_CAP) * MARGIN_HIT_PCT
        multiplier = 1.0 + max(0, skill_bonus_used) / SKILL_DAMAGE_SCALE
        if breakthrough:
            multiplier *= BREAKTHROUGH_MULTIPLIER
        if massive:
            multiplier *= MASSIVE_DAMAGE_MULTIPLIER
        return max(1, round(target_hp_max * pct * multiplier))

    # ---------- resource / cooldown cost, and effect type, of a named ability ----------
    def _combat_skill_detail(self, skill):
        if not skill:
            return None
        detail = (self.state.get("skills") or {}).get(skill)
        if isinstance(detail, dict):
            return detail
        options = (self.state.get("combat") or {}).get("ability_options") or {}
        detail = options.get(skill) if isinstance(options, dict) else None
        return detail if isinstance(detail, dict) else None

    def _combat_skill_known(self, skill):
        return bool(skill and self._combat_skill_detail(skill))

    def _ability_resource_type(self, skill):
        """'pool' (spends the world resource — Chakra/Mana/Aura/Magicule/
        Stamina/Energy), 'cooldown' (no resource cost, but locked out for a
        few rounds), or 'free' (no cost at all). Honors an explicit
        resource_type on the skill if the GM set one (see gm_rules' skill
        authoring guidance), otherwise falls back to the world's default —
        this is what makes an untagged legacy skill still behave sensibly."""
        detail = self._combat_skill_detail(skill)
        explicit = str((detail or {}).get("resource_type", "")).strip().lower() if isinstance(detail, dict) else ""
        if explicit in ("pool", "cooldown", "free"):
            return explicit
        world = self.state.get("world", "Custom World")
        archetype = (self.state.get("special", {}) or {}).get("Archetype", "")
        return ability_resource_type_for(world, archetype)

    def _ability_resource_cost(self, skill_bonus_used):
        tuning = normalize_tuning(self.state)
        pct = BASE_RESOURCE_COST_PCT + max(0, skill_bonus_used) / SKILL_COST_SCALE
        pct *= float(tuning.get("resource_pressure", 1.0) or 1.0)
        resource_max = max(1, int(self.state.get("resource_max", 100) or 100))
        return max(1, round(resource_max * pct))

    def _ability_effect_type(self, skill):
        """Return the normalized mechanical effect of a named skill."""
        detail = self._combat_skill_detail(skill)
        return infer_skill_metadata(skill or "Attack", detail).get("effect_type", "damage") if skill else "damage"

    def _ability_metadata(self, skill):
        detail = self._combat_skill_detail(skill)
        return infer_skill_metadata(skill or "Attack", detail)

    @staticmethod
    def _active_status(rows, names):
        wanted = {str(name).lower() for name in names}
        return next((row for row in rows if str(row.get("name", "")).lower() in wanted and int(row.get("rounds_left", 0)) > 0), None)

    @staticmethod
    def _status_blocks_action(row):
        """Hard control is semantic, not dependent on one exact UI label."""
        if not isinstance(row, dict) or int(row.get("rounds_left", 0) or 0) <= 0:
            return False
        if isinstance(row.get("blocks_action"), bool):
            return row["blocks_action"]
        name = str(row.get("name") or row.get("status") or "").lower()
        return bool(re.search(
            r"\b(stun(?:ned)?|paraly(?:zed|sis)|asleep|sleeping|frozen|freeze|"
            r"immobili[sz]ed|incapacitated|unconscious|petrified|restrained|bound|controlled)\b",
            name,
        ))

    @classmethod
    def _active_disabling_status(cls, rows):
        return next((row for row in rows if cls._status_blocks_action(row)), None)

    @staticmethod
    def _add_or_refresh_effect(rows, incoming):
        """Keep one mechanical row per named condition and refresh it.

        Reapplying Paralysis should extend/refresh Paralysis, not create a
        pile of identical chips.  For percentage effects the stronger value
        wins, which also prevents repeated weakening from multiplying without
        limit while still allowing a stronger technique to replace a weaker
        one.
        """
        name = str(incoming.get("name") or "Effect").strip()
        existing = next((row for row in rows if str(row.get("name") or "").lower() == name.lower()), None)
        if existing is None:
            rows.append(incoming)
            return incoming
        existing["rounds_left"] = max(int(existing.get("rounds_left", 0) or 0), int(incoming.get("rounds_left", 0) or 0))
        for key, value in incoming.items():
            if key in {"name", "rounds_left"}:
                continue
            if key.endswith("_pct") and isinstance(value, (int, float)):
                old = float(existing.get(key, 0) or 0)
                existing[key] = min(old, value) if value < 0 else max(old, value)
            elif key == "blocks_action":
                existing[key] = bool(existing.get(key)) or bool(value)
            else:
                existing[key] = value
        return existing

    def _apply_enemy_attack_effect(self, combat, enemy):
        """Apply an optional authored on-hit condition to the player."""
        effect = enemy.get("attack_effect")
        if not isinstance(effect, dict):
            return None
        kind = str(effect.get("type") or effect.get("effect_type") or "").strip().lower()
        name = str(effect.get("name") or effect.get("status_effect") or ("Weakened" if kind == "debuff" else "Controlled")).strip()
        duration = max(1, int(effect.get("duration_rounds", effect.get("rounds", 2)) or 2))
        if kind == "control":
            existing = next((row for row in combat.setdefault("player_statuses", [])
                             if str(row.get("name") or "").lower() == name.lower()
                             and int(row.get("rounds_left", 0) or 0) > 0), None)
            # A guaranteed on-hit paralysis must not refresh itself forever
            # while the victim is unable to act. The existing duration plays
            # out; a later hit after recovery may inflict it again.
            if existing is not None and not effect.get("refresh_while_active"):
                return None
            row = {
                "name": name, "rounds_left": duration,
                "blocks_action": self._status_blocks_action({"name": name, "rounds_left": duration,
                                                               "blocks_action": effect.get("blocks_action")}),
            }
            self._add_or_refresh_effect(combat.setdefault("player_statuses", []), row)
            return row
        if kind == "debuff":
            raw_potency = float(effect.get("potency_pct", effect.get("potency", 20)) or 20)
            potency = clamp(raw_potency / 100.0 if abs(raw_potency) > 1 else abs(raw_potency), .05, .6)
            row = {
                "name": name, "rounds_left": duration,
                "power_pct": -potency,
                "accuracy_pct": -clamp(float(effect.get("accuracy_pct", potency * 100)) / 100.0, .05, .6),
                "defense_pct": -clamp(float(effect.get("defense_pct", potency * 100)) / 100.0, .05, .6),
                "speed_pct": -clamp(float(effect.get("speed_pct", potency * 75)) / 100.0, .05, .6),
            }
            self._add_or_refresh_effect(combat.setdefault("player_debuffs", []), row)
            return row
        return None

    @staticmethod
    def _tick_effects(combat):
        for key in ("enemy_debuffs", "player_buffs", "player_debuffs", "player_statuses", "enemy_statuses", "summons"):
            for row in combat.get(key, []):
                row["rounds_left"] = int(row.get("rounds_left", 1)) - 1
            combat[key] = [row for row in combat.get(key, []) if int(row.get("rounds_left", 0)) > 0]

    def _player_effect_bonuses(self, combat):
        rows = [*combat.get("player_buffs", []), *combat.get("player_debuffs", [])]
        power = sum(float(row.get("power_pct", 0)) for row in rows)
        defense = sum(float(row.get("defense_pct", 0)) for row in rows)
        speed = sum(float(row.get("speed_pct", 0)) for row in rows)
        accuracy = sum(float(row.get("accuracy_pct", row.get("power_pct", 0))) for row in combat.get("player_debuffs", []))
        return {"power_pct": clamp(power, -.6, .75), "defense_pct": clamp(defense, -.6, .75),
                "speed_pct": clamp(speed, -.6, .75), "accuracy_pct": clamp(accuracy, -.6, 0)}

    def _effective_enemy_numbers(self, enemy, combat):
        """The enemy's combat numbers after active debuffs — power, hit
        difficulty and attack strength all scale down together while a
        debuff is live; hp/hp_max are never touched by this, only how
        dangerous and how hittable the opponent currently is."""
        debuffs = combat.get("enemy_debuffs", [])
        power_pct = clamp(sum(float(d.get("power_pct", 0)) for d in debuffs), -0.6, 0.0)
        defense_pct = clamp(sum(float(d.get("defense_pct", 0)) for d in debuffs), -0.6, 0.0)
        speed_pct = clamp(sum(float(d.get("speed_pct", 0)) for d in debuffs), -0.6, 0.0)
        accuracy_pct = clamp(sum(float(d.get("accuracy_pct", d.get("power_pct", 0))) for d in debuffs), -0.6, 0.0)
        power_mult, defense_mult = 1.0 + power_pct, 1.0 + defense_pct
        return {
            "power": max(1, int(enemy["power"] * power_mult)),
            "difficulty_min": max(1, int(enemy["difficulty_min"] * defense_mult)),
            "difficulty_max": max(1, int(enemy["difficulty_max"] * defense_mult)),
            # These are the resistance thresholds for the enemy's own attack
            # check. Lowering them made a weakened enemy easier to succeed,
            # cancelling its reduced power. Keep them fixed and penalize the
            # enemy total and damage instead.
            "attack_min": int(enemy["attack_min"]),
            "attack_max": int(enemy["attack_max"]),
            "speed": max(1, int(enemy.get("speed", enemy["power"]) * (1.0 + speed_pct))),
            "accuracy_penalty": max(0, round(abs(accuracy_pct) * 25)),
            "damage_multiplier": clamp(power_mult, .4, 1.0),
        }

    # ---------- one swing of a named ability or plain attack ----------
    def _resolve_swing(self, combat, enemy, ability, swing_skill, resource_type, ally_support,
                        player_offense_stat_value, enemy_power, extra_swing):
        """Resolves exactly one use of an ability within a round — damage,
        heal, or debuff, whichever the selected ability actually is. Raises
        on the FIRST swing if the ability can't be paid for (blocks the
        whole action before anything happens); a bonus extra swing (from a
        decisive speed edge) that can't be paid for is simply skipped by the
        caller instead, since the first swing already landed."""
        bonus, sb_used = self._player_offense_bonus(ability, swing_skill)
        display_skill = str((self._combat_skill_detail(swing_skill) or {}).get("name") or swing_skill or "Attack")
        player_effects = self._player_effect_bonuses(combat)
        bonus += round(25 * player_effects["power_pct"])
        bonus -= round(abs(player_effects["accuracy_pct"]) * 25)
        resource_cost = 0
        if swing_skill and resource_type == "cooldown":
            ready_at = combat["cooldowns"].get(swing_skill, 0)
            if combat["round"] < ready_at:
                raise RuntimeError(f"{display_skill} is still recovering — usable again in {ready_at - combat['round']} more round(s).")
        elif swing_skill and resource_type == "pool":
            resource_cost = self._ability_resource_cost(sb_used)
            skill_detail = self._combat_skill_detail(swing_skill) or {}
            efficiency = max(0, min(40, float(skill_detail.get('resource_efficiency_pct', 0) or 0)))
            resource_cost = max(1, round(resource_cost * (1 - efficiency / 100.0)))
            available = int(self.state.get("resource", 0) or 0)
            if resource_cost > available:
                raise RuntimeError(f"Not enough {self.state.get('resource_name', 'Energy')} to use {display_skill} ({resource_cost} needed, {available} available).")

        metadata = self._ability_metadata(swing_skill) if swing_skill else self._ability_metadata(None)
        effect_type = metadata.get("effect_type", "damage") if swing_skill else "damage"
        mechanics = dict(metadata.get("mechanics", {}) or {})
        skill_detail = self._combat_skill_detail(swing_skill) or {}
        potency = max(0, min(25, int(skill_detail.get('mastery_potency_bonus', 0) or 0)))
        for key in ('heal_pct','shield_pct','power_pct','defense_pct','speed_pct','status_potency'):
            if key in mechanics and isinstance(mechanics[key], (int, float)): mechanics[key] = mechanics[key] + potency
        duration = max(1, int(metadata.get("duration_rounds", 0) or 3) + int(skill_detail.get('mastery_duration_bonus', 0) or 0))
        status_name = metadata.get("status_effect")
        eff = self._effective_enemy_numbers(enemy, combat)
        event = {"actor": "player", "ability": display_skill, "target": enemy["name"],
                  "resource_cost": resource_cost, "extra_swing": extra_swing, "effect": effect_type,
                  "category": metadata.get("category"), "duration": duration}

        if effect_type == "heal":
            # A reliability check, not an opposed one — you're not fighting
            # the enemy's stats to heal yourself, just executing correctly.
            check = self._combat_check(bonus, 20, 40)
            healed = 0
            if check["success"]:
                heal_pct = clamp(float(mechanics.get("heal_pct", 20)) / 100.0, .05, .6)
                healed = max(1, round(self.state.get("hp_max", 100) * heal_pct * (1 + min(50, check["margin"]) / 200)))
                self.state["hp"] = min(int(self.state.get("hp_max", 100)), int(self.state.get("hp", 0)) + healed)
            event.update({"action": "heal", "healed": healed, **check})
        elif effect_type == "debuff":
            check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            applied = False
            if check["success"]:
                potency = clamp(float(metadata.get("status_potency", 20)) / 100.0, .05, .6)
                self._add_or_refresh_effect(combat.setdefault("enemy_debuffs", []), {
                    "name": status_name or "Weakened", "rounds_left": duration,
                    "power_pct": -potency,
                    "accuracy_pct": -clamp(float(mechanics.get("accuracy_pct", potency * 100)) / 100.0, 0, .6),
                    "defense_pct": -clamp(float(mechanics.get("defense_pct", 20)) / 100.0, 0, .6),
                    "speed_pct": -clamp(float(mechanics.get("speed_pct", 15)) / 100.0, 0, .6),
                })
                applied = True
            event.update({"action": "debuff", "status": status_name or "Weakened", "applied": applied,
                          "potency_pct": round(potency * 100) if applied else 0, **check})
        elif effect_type == "control":
            check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            applied = bool(check["success"])
            if applied:
                self._add_or_refresh_effect(combat.setdefault("enemy_statuses", []), {
                    "name": status_name or "Controlled", "rounds_left": duration,
                    "blocks_action": self._status_blocks_action({
                        "name": status_name or "Controlled", "rounds_left": duration,
                        "blocks_action": mechanics.get("blocks_action") if isinstance(mechanics.get("blocks_action"), bool) else None,
                    }),
                    "damage_over_time_pct": clamp(float(mechanics.get("damage_over_time_pct", 0)) / 100.0, 0, .15),
                })
            event.update({"action": "control", "status": status_name or "Controlled", "applied": applied, **check})
        elif effect_type == "buff":
            check = self._combat_check(bonus, 20, 40)
            applied = bool(check["success"])
            if applied:
                potency = clamp(float(metadata.get("status_potency", 20)) / 100.0, .05, .6)
                combat.setdefault("player_buffs", []).append({
                    "name": status_name or "Empowered", "rounds_left": duration,
                    "power_pct": potency,
                    "defense_pct": clamp(float(mechanics.get("defense_pct", 20)) / 100.0, 0, .6),
                    "speed_pct": clamp(float(mechanics.get("speed_pct", 15)) / 100.0, 0, .6),
                })
            event.update({"action": "buff", "status": status_name or "Empowered", "applied": applied, **check})
        elif effect_type == "shield":
            check = self._combat_check(bonus, 20, 40)
            shield = 0
            if check["success"]:
                shield_pct = clamp(float(mechanics.get("shield_pct", 20)) / 100.0, .05, .6)
                shield = max(1, round(int(self.state.get("hp_max", 100)) * shield_pct))
                combat["player_shield"] = int(combat.get("player_shield", 0) or 0) + shield
            event.update({"action": "shield", "shield": shield, "applied": bool(shield), **check})
        elif effect_type == "cleanse":
            check = self._combat_check(bonus, 15, 35)
            removed = []
            if check["success"]:
                removed = [row.get("name", "negative effect") for row in combat.get("player_statuses", [])]
                removed.extend(row.get("name", "debuff") for row in combat.get("player_debuffs", []))
                combat["player_statuses"] = []
                combat["player_debuffs"] = []
            event.update({"action": "cleanse", "removed": removed, "applied": bool(check["success"]), **check})
        elif effect_type == "summon":
            check = self._combat_check(bonus, 25, 45)
            applied = bool(check["success"])
            if applied:
                support = max(2, min(15, 3 + sb_used // 3))
                combat.setdefault("summons", []).append({"name": status_name or display_skill or "Summoned Ally",
                                                          "rounds_left": duration, "support_bonus": support})
            event.update({"action": "summon", "summon": status_name or display_skill, "applied": applied, **check})
        elif effect_type in ("movement", "detect", "stealth", "transform"):
            check = self._combat_check(bonus, 20, 45)
            applied = bool(check["success"])
            if applied:
                presets = {
                    "movement": (0.0, .15, .25), "detect": (.15, .05, .05),
                    "stealth": (.10, .25, .15), "transform": (.30, .20, .15),
                }
                power_pct, defense_pct, speed_pct = presets[effect_type]
                combat.setdefault("player_buffs", []).append({
                    "name": status_name or effect_type.title(), "rounds_left": duration,
                    "power_pct": power_pct, "defense_pct": defense_pct, "speed_pct": speed_pct,
                    "effect_type": effect_type,
                })
                if effect_type == "transform":
                    details = ai_text((self._combat_skill_detail(swing_skill) or {}).get("description")) if swing_skill else ""
                    set_active_portrait_form(self.state, display_skill or status_name or "Combat Transformation",
                                             status_name or "Transformation", details, source="combat")
            event.update({"action": effect_type, "status": status_name or effect_type.title(), "applied": applied, **check})
        elif effect_type == "utility":
            # A combat-tagged utility creates a modest tactical opening.  It
            # must never silently become an attack and deal damage.
            check = self._combat_check(bonus, 20, 45)
            applied = bool(check["success"])
            if applied:
                combat.setdefault("player_buffs", []).append({
                    "name": status_name or "Tactical Advantage", "rounds_left": 2,
                    "power_pct": .10, "defense_pct": .10, "speed_pct": .10,
                })
            event.update({"action": "utility", "status": status_name or "Tactical Advantage", "applied": applied, **check})
        else:
            check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            massive = (player_offense_stat_value - enemy_power) >= MASSIVE_GAP_THRESHOLD
            shrugged = (enemy_power - player_offense_stat_value) >= MASSIVE_GAP_THRESHOLD
            dmg = 0
            if check["success"] and not shrugged:
                dmg = self._damage(enemy["hp_max"], check["margin"], sb_used, check["breakthrough"], massive)
                dmg = max(1, round(dmg * (1 + min(0, player_effects["power_pct"]))))
                # The enemy is spared from actually dying either when this is
                # a non-lethal spar/test (floors both sides — see
                # resolve_combat_round) or when the player has personally
                # chosen to spare THIS opponent (combat.spare_enemy floors
                # only the enemy; it does nothing for the player's own HP).
                enemy_floor = 1 if (combat.get("non_lethal") or combat.get("spare_enemy")) else 0
                enemy["hp"] = max(enemy_floor, int(enemy["hp"]) - dmg)
                if enemy["hp"] <= enemy_floor:
                    enemy["alive"] = False
                if status_name and effect_type == "damage":
                    dot = clamp(float(mechanics.get("damage_over_time_pct", 0)) / 100.0, 0, .15)
                    if dot > 0:
                        combat.setdefault("enemy_statuses", []).append({"name": status_name,
                            "rounds_left": duration, "damage_over_time_pct": dot})
            event.update({"action": "attack", "damage": dmg, "massive": massive,
                          "shrugged": shrugged and check["success"], **check})

        if swing_skill and resource_type == "pool":
            self.state["resource"] = max(0, int(self.state.get("resource", 0)) - resource_cost)
        elif swing_skill and resource_type == "cooldown":
            combat["cooldowns"][swing_skill] = combat["round"] + COOLDOWN_ROUNDS
        return event

    # ---------- the actual round ----------
    def resolve_combat_round(self, action, ability_name=None):
        """One full exchange (player action, then the opponent's retaliation
        if it's still alive), resolved entirely locally. Always exactly
        player vs. the single combat.enemy entity — a lone foe or a whole
        group represented as one aggregate (see gm_rules). Returns a plain
        dict describing exactly what happened — no prose, no AI call."""
        from naruto_tactics import require_narrative_available
        require_narrative_available(self.state)
        self.ensure_combat_numbers()
        combat = self.state["combat"]
        log_start = len(combat.get("log", []))
        enemy = combat.get("enemy") or {}
        # A spar, test, or supervised duel (combat.non_lethal) is won or lost
        # on points — HP is floored at 1 for both sides instead of 0, so
        # neither combatant can actually be killed by it.
        floor = 1 if combat.get("non_lethal") else 0
        if not enemy.get("alive", True) or int(enemy.get("hp", 0)) <= 0:
            return self.end_combat("victory", log_start)

        bonus_action = bool(combat.get("bonus_turn_pending"))

        # Persistent status damage is resolved locally at the start of the
        # exchange. New effects therefore last for their advertised future
        # rounds instead of damaging a target immediately a second time. A
        # speed-earned bonus action is still part of the same exchange, so it
        # must not tick damage or duration a second time.
        for status in ([] if bonus_action else combat.get("enemy_statuses", [])):
            dot = float(status.get("damage_over_time_pct", 0) or 0)
            if dot > 0:
                damage = max(1, round(int(enemy.get("hp_max", 1)) * dot))
                enemy["hp"] = max(0, int(enemy.get("hp", 0)) - damage)
                combat["log"].append({"round": combat["round"], "actor": "status", "target": "enemy",
                                      "action": "status damage", "status": status.get("name", "Lingering effect"),
                                      "damage": damage})
        for status in ([] if bonus_action else combat.get("player_statuses", [])):
            dot = float(status.get("damage_over_time_pct", 0) or 0)
            if dot > 0:
                damage = max(1, round(int(self.state.get("hp_max", 1)) * dot))
                self.state["hp"] = max(floor, int(self.state.get("hp", 0)) - damage)
                combat["log"].append({"round": combat["round"], "actor": "status", "target": "player",
                                      "action": "status damage", "status": status.get("name", "Lingering effect"),
                                      "damage": damage})
        if int(enemy.get("hp", 0)) <= 0:
            enemy["alive"] = False
            return self.end_combat("victory", log_start)

        world = self.state.get("world", "Custom World")
        primary = primary_stats_for(world, self.state.get("special", {}).get("Archetype", "")) or [abilities_for(world)[0]]
        ability = primary[0]
        # Only applied when the GM judged this a coordinated group action
        # (an ambush, a party assault) — see gm_rules; 0 for any solo fight.
        summon_support = sum(int(row.get("support_bonus", 0) or 0) for row in combat.get("summons", []))
        ally_support = int(combat.get("ally_support", 0) or 0) + summon_support
        effective_enemy = self._effective_enemy_numbers(enemy, combat)
        enemy_power = effective_enemy["power"]
        player_effects = self._player_effect_bonuses(combat)
        player_speed = int(self.state.get("stats", {}).get(speed_stat_for(world), 30) or 30)
        player_speed = round(player_speed * (1 + player_effects["speed_pct"]))
        player_defense_stat_value = int(self.state.get("stats", {}).get(defense_stat_for(world), 30) or 30)
        player_defense_stat_value = round(player_defense_stat_value * (1 + player_effects["defense_pct"]))
        player_offense_stat_value = int(self.state.get("stats", {}).get(ability, 30) or 30)
        player_offense_stat_value = round(player_offense_stat_value * (1 + player_effects["power_pct"]))
        events = []
        earned_bonus_turn = False
        player_disabling = self._active_disabling_status(combat.get("player_statuses", []))

        if player_disabling:
            events.append({"actor": "player", "action": "controlled", "name": self.state.get("name", "You"),
                           "status": player_disabling.get("name", "Controlled")})
        elif action == "flee":
            bonus, _ = self._player_offense_bonus(ability, None)
            eff = self._effective_enemy_numbers(enemy, combat)
            check = self._combat_check(bonus + ally_support, eff["attack_min"], eff["attack_max"])
            if check["success"]:
                combat["log"].append({"round": combat["round"], "actor": "player", "action": "flee", **check, "result": "escaped"})
                return self.end_combat("fled", log_start)
            events.append({"actor": "player", "action": "flee", **check, "result": "failed to escape"})
        elif action == "defend":
            events.append({"actor": "player", "action": "defend", "result": "braced"})
        elif action == "overwhelm":
            # A canon instant-win-type move (absorption, Conqueror's Haki,
            # domination, ...) — same math, just a harder target unless the
            # power gap already makes the outcome a foregone conclusion.
            # Failing costs nothing but the attempt; try again next round.
            bonus, _ = self._player_offense_bonus(ability, ability_name if self._combat_skill_known(ability_name) else None)
            eff = self._effective_enemy_numbers(enemy, combat)
            gap = player_offense_stat_value - enemy_power
            if gap >= MASSIVE_GAP_THRESHOLD:
                check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            else:
                check = self._combat_check(bonus + ally_support,
                                            eff["difficulty_min"] + OVERWHELM_DIFFICULTY_PADDING,
                                            eff["difficulty_max"] + OVERWHELM_DIFFICULTY_PADDING)
            conquerors_haki = bool(
                self.state.get("world") == "One Piece"
                and re.search(r"\b(?:conqueror(?:'s)?|haoshoku)\b.*\bhaki\b|\bhaoshoku\b", str(ability_name or ""), re.I)
            )
            events.append({"actor": "player", "action": "overwhelm", "ability": ability_name or "Overwhelm",
                            "target": enemy["name"], "cinematic": "conquerors_haki" if conquerors_haki else None,
                            "visual_outcome": "victory" if check["success"] else "resisted", **check})
            if check["success"]:
                combat["log"].extend([{"round": combat["round"], **e} for e in events])
                return self.end_combat("overwhelmed", log_start)
        else:
            requested_skill = ability_name if self._combat_skill_known(ability_name) else None
            requested_type = self._ability_resource_type(requested_skill) if requested_skill else "free"
            event = self._resolve_swing(combat, enemy, ability, requested_skill, requested_type, ally_support,
                                        player_offense_stat_value, enemy_power, bonus_action)
            events.append(event)

        # A decisive speed edge used to duplicate an attacking move. It now
        # grants another full player choice after any valid first action. A
        # disabling effect still consumes the character's opportunity to act.
        earned_bonus_turn = (
            not bonus_action and not player_disabling and enemy.get("alive", True)
            and (player_speed - effective_enemy["speed"]) >= SPEED_GAP_THRESHOLD
        )

        combat["log"].extend([{"round": combat["round"], **e} for e in events])

        if not enemy.get("alive", True):
            return self.end_combat("victory", log_start)

        if earned_bonus_turn:
            reason = f"Speed advantage: {player_speed} vs {effective_enemy['speed']}"
            combat["bonus_turn_pending"] = True
            combat["bonus_turn_reason"] = reason
            combat["bonus_turn_first_action"] = action
            bonus_event = {"round": combat["round"], "actor": "system", "action": "bonus_turn", "reason": reason}
            combat["log"].append(bonus_event)
            self.autosave()
            return {"combat": combat, "hp": self.state.get("hp"), "hp_max": self.state.get("hp_max"),
                    "resource": self.state.get("resource"), "resource_max": self.state.get("resource_max"),
                    "log_tail": combat["log"][log_start:], "player_died": False, "awaiting_bonus_action": True}

        # Newly used movement, stealth, buff and transformation skills affect
        # the retaliation in this same exchange, not one round late.
        player_effects = self._player_effect_bonuses(combat)
        player_speed = int(self.state.get("stats", {}).get(speed_stat_for(world), 30) or 30)
        player_speed = round(player_speed * (1 + player_effects["speed_pct"]))
        player_defense_stat_value = int(self.state.get("stats", {}).get(defense_stat_for(world), 30) or 30)
        player_defense_stat_value = round(player_defense_stat_value * (1 + player_effects["defense_pct"]))

        disabling = self._active_disabling_status(combat.get("enemy_statuses", []))
        defended_this_exchange = action == "defend" or (
            bonus_action and combat.get("bonus_turn_first_action") == "defend"
        )
        retaliation_due = action != "flee" or bool(player_disabling)
        if retaliation_due and disabling:
            combat["log"].append({"round": combat["round"], "actor": "enemy", "action": "controlled",
                                   "name": enemy["name"], "status": disabling.get("name")})
        elif retaliation_due:
            eff = self._effective_enemy_numbers(enemy, combat)
            retaliation_power = eff["power"]
            enemy_swings = 2 if (eff["speed"] - player_speed) >= SPEED_GAP_THRESHOLD else 1
            for swing_index in range(enemy_swings):
                defense_bonus = self._player_defense_bonus(combat) + ally_support
                defense_bonus += round(abs(self._player_defense_bonus(combat)) * player_effects["defense_pct"])
                check = self._combat_check(int(eff["power"] * 0.35), eff["attack_min"], eff["attack_max"])
                # defense_bonus reduces the enemy's effective total by raising the threshold they must beat
                check["total"] -= defense_bonus + eff["accuracy_penalty"]
                check["success"] = check["total"] > check["difficulty"] and check["roll"] != 1
                check["margin"] = max(0, check["total"] - check["difficulty"])
                massive = (retaliation_power - player_defense_stat_value) >= MASSIVE_GAP_THRESHOLD
                shrugged = (player_defense_stat_value - retaliation_power) >= MASSIVE_GAP_THRESHOLD
                dmg = 0
                if check["success"] and not shrugged:
                    dmg = self._damage(self.state.get("hp_max", 100), check["margin"], 0, check["breakthrough"], massive)
                    dmg = max(1, round(dmg * eff["damage_multiplier"]))
                    if defended_this_exchange:
                        dmg = max(1, round(dmg * DEFEND_DAMAGE_REDUCTION))
                    shield_before = int(combat.get("player_shield", 0) or 0)
                    absorbed = min(shield_before, dmg)
                    combat["player_shield"] = max(0, shield_before - absorbed)
                    hp_damage = max(0, dmg - absorbed)
                    self.state["hp"] = max(floor, int(self.state.get("hp", 100)) - hp_damage)
                    inflicted = self._apply_enemy_attack_effect(combat, enemy)
                else:
                    absorbed = 0
                    hp_damage = dmg
                    inflicted = None
                combat["log"].append({"round": combat["round"], "actor": "enemy", "action": "attack",
                                       "name": enemy["name"], "damage": hp_damage, "absorbed": absorbed,
                                       "extra_swing": swing_index > 0,
                                       "debuff_penalty": eff["accuracy_penalty"],
                                       "damage_multiplier": eff["damage_multiplier"],
                                       "inflicted_status": inflicted.get("name") if inflicted else None,
                                       "massive": massive, "shrugged": shrugged and check["success"], **check})
                if self.state.get("hp", 1) <= floor:
                    break

        combat.pop("bonus_turn_pending", None)
        combat.pop("bonus_turn_reason", None)
        combat.pop("bonus_turn_first_action", None)
        self._tick_effects(combat)
        active_form = (self.state.get("portrait_identity") or {}).get("active_form", {})
        if isinstance(active_form, dict) and active_form.get("source") == "combat" and not any(
            row.get("effect_type") == "transform" for row in combat.get("player_buffs", [])
        ):
            clear_active_portrait_form(self.state)

        combat["round"] += 1
        self.autosave()

        if self.state.get("hp", 1) <= floor:
            return self.end_combat("defeat" if not combat.get("non_lethal") else "yielded", log_start)

        return {"combat": self.state["combat"], "hp": self.state.get("hp"), "hp_max": self.state.get("hp_max"),
                "resource": self.state.get("resource"), "resource_max": self.state.get("resource_max"),
                "log_tail": combat["log"][log_start:], "player_died": False}

    def end_combat(self, outcome, log_start=None):
        combat = self.state.get("combat") or {}
        enemy = combat.get("enemy") if isinstance(combat.get("enemy"), dict) else {}
        mercy_shown = bool(combat.get("non_lethal") or combat.get("spare_enemy"))
        death_prevented = bool(enemy.get("death_prevented") or enemy.get("immortal") or enemy.get("cannot_die"))
        enemy_died = outcome in {"victory", "overwhelmed"} and not mercy_shown and not death_prevented
        tactical = combat.get('tactical_enabled') and (self.state.get('world') in {'Naruto','One Piece','Bleach'} or combat.get('adventure_objective'))
        if tactical:
            enemy_died = any(r.get('side')=='enemy' and r.get('outcome')=='killed' for r in combat.get('casualties',[]))
        if outcome in {"victory", "overwhelmed"} and not tactical:
            if enemy_died:
                enemy["hp"] = 0
                enemy["alive"] = False
                name = str(enemy.get("name") or "").strip()
                if name and isinstance(self.state.get("npc_memories", {}).get(name), dict):
                    self.state["npc_memories"][name]["status"] = "deceased"
            else:
                enemy["hp"] = max(1, int(enemy.get("hp", 1) or 1))
                enemy["alive"] = True
        combat["enemy_died"] = enemy_died
        combat["death_prevented"] = death_prevented
        combat["active"] = False
        combat["outcome"] = outcome
        normalize_encounter_state(self.state)
        # The round-by-round fight is the dangerous scenario.  Once it has a
        # mechanical outcome, later unrelated hard actions must be allowed to
        # receive their own warning instead of inheriting stale consent.
        self.clear_danger_scenario()
        from living_adventures import combat_finished
        combat_finished(self, outcome)
        self.autosave()
        log = combat.get("log", [])
        # The frontend mirrors this tail into the Chronicle.  Returning the
        # last N cumulative rows made round two repeat round one's lines, and
        # the final escape/victory repeated several rounds again.  A caller
        # resolving a round supplies the pre-round index so only new events
        # are returned; direct/legacy callers retain a small useful tail.
        fresh_log = log[int(log_start):] if isinstance(log_start, int) else log[-5:]
        result = {"combat": combat, "hp": self.state.get("hp"), "hp_max": self.state.get("hp_max"),
                  "resource": self.state.get("resource"), "resource_max": self.state.get("resource_max"),
                  "log_tail": fresh_log, "player_died": outcome == "defeat"}
        if outcome == "defeat" and self.state.get("hp", 1) <= 0:
            self.state["alive"] = False
        return result

    # ---------- relaying the results (the one paid call) ----------
    def narrate_combat(self):
        """Turn everything since the last narration into prose + a normal
        state_patch (loot, injuries, quest/XP consequences) — one AI call
        covering the whole exchange, not one per round."""
        from naruto_tactics import require_narrative_available
        require_narrative_available(self.state)
        combat = self.state.get("combat") or {}
        log = combat.get("log", [])
        start = combat.get("narrated_through", 0)
        pending = log[start:]
        if not pending:
            return {"narrative": "", "story": self._flush_story()}
        if self.settings.get("local_combat_recap", True) and isinstance((self.ai_bg if getattr(self, "ai_bg", None) else self.ai), AI):
            return self._local_combat_recap(combat, pending)
        mercy_shown = bool(combat.get("non_lethal") or combat.get("spare_enemy"))
        payload = {
            "task": "narrate_combat", "state": self.task_state_for_ai("combat_summary"), "combat_outcome": combat.get("outcome"),
            "mercy_shown": mercy_shown, "enemy_died": bool(combat.get("enemy_died")), "mechanical_log": pending,
            "tactical_result": combat.get("result_receipt"),
            "schema": {"narrative": "2-6 sentences turning the mechanical log into a real combat scene — do not re-roll or contradict any result",
                       "state_patch": "loot, injuries, XP, quest/codex/companion consequences of this fight",
                       "events": "system notifications", "timeline_event": "major event or empty",
                       "suggested_actions": ["3 concise next actions"]}}
        rules = self.task_context("combat_summary") + (
            "\nYou are narrating a fight that has ALREADY been mechanically resolved by the application. "
            "Every roll, hit, miss and HP change in mechanical_log already happened — narrate them faithfully, "
            "do not add extra unlisted hits or change any outcome. This is the same MAIN GM role as any other turn."
        )
        if mercy_shown and combat.get("outcome") in ("victory", "yielded"):
            rules += (
                " mercy_shown is true: narrate the defeated enemy's ending as knocked unconscious, restrained, "
                "or forced to yield — never killed — regardless of how much damage the mechanical log shows. "
                "If combat_outcome is 'yielded', the PLAYER is the one who was brought to the floor and conceded "
                "the bout, not defeated at risk of real harm — narrate it as the player yielding a spar/test, "
                "not a life-threatening loss."
            )
        elif combat.get("enemy_died"):
            rules += (
                " enemy_died is true: this was a lethal fight and the defeated enemy died. State that plainly in the scene. "
                "Do not soften the result into subdued, unconscious, merely defeated, captured, or escaped."
            )
        narrator = self.ai_bg if getattr(self, "ai_bg", None) and self.settings.get("secondary_model") else self.ai
        data = narrator.request(rules, payload, max_output_tokens=650)
        combat["narrated_through"] = len(log)
        if not combat.get("active"):
            self.state["combat"] = {}
        result = self.apply_resolution(data, is_opening=False, pending_action=f"[combat] {combat.get('outcome') or 'ongoing'}")
        return result

    def _local_combat_recap(self, combat, pending):
        """Readable deterministic recap and rewards with zero AI calls."""
        enemy = (combat.get("enemy") or {}).get("name", "the opponent")
        phrases = []
        for row in pending:
            actor, action = row.get("actor"), row.get("action")
            if action == "attack":
                if row.get("success") and row.get("damage"):
                    subject = row.get('name') or (self.state.get("name", "You") if actor == "player" else enemy)
                    target = row.get('target') or (enemy if actor == "player" else self.state.get("name", "you"))
                    phrases.append(f"{subject} struck {target} for {row.get('damage')} damage.")
                else:
                    phrases.append(f"{self.state.get('name', 'You') if actor == 'player' else enemy} missed the attack.")
            elif action == "controlled":
                phrases.append(f"{row.get('name') or actor} could not act while {row.get('status', 'controlled')}.")
            elif action == "status damage":
                phrases.append(f"{row.get('status', 'A lingering effect')} dealt {row.get('damage', 0)} damage.")
            elif action == "flee":
                phrases.append("The escape succeeded." if row.get("success") else "The escape attempt was cut off.")
            elif action in {"heal", "shield", "buff", "debuff", "control", "summon", "cleanse", "movement", "detect", "stealth", "transform", "utility"}:
                phrases.append(f"{row.get('ability') or row.get('status') or action.title()} took effect." if row.get("success", row.get("applied", True)) else f"{row.get('ability') or action.title()} failed to take hold.")
        outcome = str(combat.get("outcome") or "ongoing")
        lethal_ending = f"{enemy} was killed." if combat.get("enemy_died") else f"{enemy} was defeated but survived."
        if combat.get('tactical_enabled'):
            lethal_ending=' '.join(f"{r['name']} was {r['outcome']}." for r in combat.get('casualties',[]) if r.get('side')=='enemy') or 'The encounter ended.'
        endings = {"objective_complete":"The encounter objective was secured; surviving opponents remain alive.", "objective_failed":"The encounter objective was lost.", "victory": lethal_ending, "overwhelmed": lethal_ending,
                   "fled": "You escaped the fight.", "defeat": "You were defeated.", "yielded": "You yielded the nonlethal bout."}
        if outcome in endings:
            phrases.append(endings[outcome])
        narrative = " ".join(phrases[-10:]) or f"The fight with {enemy} reached its {outcome} outcome."
        notifications = []
        if outcome in {"victory", "overwhelmed"} and uses_xp_for(self.state.get("world")):
            gained = max(10, min(5000, 12 + int((combat.get("enemy") or {}).get("power", 30) or 30) // 3))
            self.state["xp"] = int(self.state.get("xp", 0) or 0) + gained
            levels = 0
            while self.state["xp"] >= int(self.state.get("xp_next", 100) or 100):
                self.state["xp"] -= int(self.state.get("xp_next", 100) or 100)
                self.state["level"] = int(self.state.get("level", 1) or 1) + 1; levels += 1
                self.state["xp_next"] = max(100, round(int(self.state.get("xp_next", 100) or 100) * 1.18))
            notification = f"Combat reward: +{gained} XP" + (f" · Level increased by {levels}" if levels else "")
            notifications.append({"type": "xp", "message": notification})
            narrative += " " + notification + "."
        combat["narrated_through"] = len(combat.get("log", []))
        if not combat.get("active"):
            self.state["combat"] = {}
        self.append("[COMBAT RESULT]\n" + narrative, "narrative")
        self.autosave()
        return {"status": "resolved", "narrative": narrative, "notifications": notifications,
                "suggested_actions": ["Check your condition and equipment", "Assess the immediate area", "Continue your current objective"],
                "state": self.public_state(), "story": self._flush_story(), "generated_locally": True}
