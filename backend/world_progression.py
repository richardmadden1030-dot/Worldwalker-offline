"""Structured, zero-cost presentation and persistence for built-in power systems.

The narrator may still invent setting-valid abilities.  This module keeps the
result in a stable shape so the Journal, Advisor, combat resolver, and later
turns all read the same facts instead of interpreting loose prose differently.
"""
import copy
import re

from overgeared_classes import COMPACT_CLASS_GENERATION_RULE, infer_class_type
from naruto_system import (CHAKRA_NATURES, apply_jinchuriki_start,
                           dojutsu_profile_from_evidence,
                           dojutsu_story_evidence,
                           jinchuriki_story_evidence,
                           normalize_chakra_affinity_profile,
                           normalize_jinchuriki_profile)


def _safe_int(value, default=0):
    """Coerce AI/save values without letting descriptive placeholders crash turns."""
    if isinstance(value, bool):
        return int(default)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
            return int(float(cleaned))
    return int(default)


WORLD_PROGRESSION_LABELS = {
    "One Piece": "Devil Fruit, Haki & Crew",
    "Hunter x Hunter": "Nen Development",
    "Naruto": "Shinobi Record",
    "Solo Max-Level Newbie": "System Status",
    "Overgeared": "Satisfy Class & Adventure",
    "Reincarnated as a Slime": "Evolution & Skills",
    "Bleach": "Zanpakuto Releases",
    "Jujutsu Kaisen": "Innate Technique or Heavenly Restriction",
}


NARRATIVE_CRAFTING_RULE = """
CRAFTING AND INVENTORY: Crafting in every world is resolved through the Chronicle, not a separate recipe calculator. Narrate the method, available materials, time, expertise, useful failures and finished result. Routine ingredients and small components such as ore, ingots, reagents, herbs, scraps and monster cores remain narrative facts and MUST NOT be added to inventory. Add a finished product to state_patch.inventory only when the player is likely to reuse it or deliberately remember owning it: equipment, tools, artifacts, quest objects, named creations, consumables with meaningful future use, or a Rare-or-better result. Such an item records name, rating/grade, category, effects, restrictions, creator/source and why the achieved quality was plausible. Ordinary batch output may remain solely in the Chronicle.
"""


WORLD_MECHANIC_RULES = {
    "One Piece": """
WORLD-SYSTEM RECORD: Keep special['Devil Fruit Profile'] as a structured profile with name, type, abilities, limitations, counters, awakening_status and awakening_requirements. Keep special['Haki Profile'] with Observation, Armament and Conqueror entries containing mastery, applications and evidence. Never grant Conqueror's Haki casually. Crew role, ship and bounty are separate from combat power. Any original Devil Fruit must be unique, permanent once introduced, unable to bypass seawater/Sea-Prism weaknesses, and comparable to established fruits of its type rather than copied from one.
""",
    "Hunter x Hunter": """
WORLD-SYSTEM RECORD: Keep special['Nen Profile'] with visibility, category, Ten, Zetsu, Ren and Hatsu Profile. Before Nen is plausibly learned, visibility is Undiscovered and public characters must not know its terminology. Once authored, an original Hatsu is permanent and records name, category_mix, effect, activation, vows, limitations, counters, aura_cost, evidence and growth_path. Strength comes from personality-fit, skill, aura and real restrictions—not a generic spell list.
""",
    "Naruto": """
 WORLD SYSTEM: Keep rank separate from power and preserve the structured Naruto profiles. Native elemental jutsu learn about twice as readily as off-affinity natures; others remain possible with more training. Combined releases keep special prerequisites; beast natures are external access.
 JINCHŪRIKI: The beast is independent. Track full canon potential separately from current access and enforce the profile's unmastered dangers. Mastery removes only recorded loss-of-control/corrosion—not agency, cost, collateral, suppression, seal/extraction, or political risks. Change bond, control, seal, access, and forms only through play.
 """,
    "Solo Max-Level Newbie": """
WORLD-SYSTEM RECORD: Keep special['System Profile'] with floor, unspent_stat_points, copied_abilities, copy_capacity, achievements and hidden_conditions. System rewards, copied skills, titles, conditions and floor clears must be explicit and persistent. A copied ability records source, rank, effect, copy_condition, condition_progress, restriction and slot_cost. Foreknowledge separates remembered game information from facts confirmed in lethal reality; it reveals routes only when the character knows them and never silently completes their conditions. When a floor is truly cleared, update tower_floor. Present important rewards as concise System notices in the prose. Rivals, administrators and party roles remain independent actors rather than passive flavor.
""",
    "Overgeared": """
WORLD-SYSTEM RECORD: Keep special['Satisfy Profile'] with primary_class, secondary_class, class_type, class_rarity, class_features, specializations, advancement, guild and npc_affinity. Crafting fields (crafting_mastery, production_specialties and known_recipes) exist only for characters who actually pursue production. Combat level, class development, party contribution, reputation and any chosen profession are separate progress tracks. Support, defense, scouting, command, commerce and companion contributions earn XP and class credit on equal footing with damage and crafting. A generated class must have a unique identity, rarity, class features, signature skill, restrictions, advancement route and persistent class-quest milestones. At least one of the three suggested actions should use or develop the current class through a specific person, place, companion, quest, or obstacle rather than generic weapon training. Present significant class, contract, level, title and quest changes as brief Satisfy System notices. Contracted companions are independent, persistent actors with condition, loyalty, abilities and growth. NPC affinity unlocks story-valid training, prices, quests, loyalty, romance, workshop or political access; NPC personality still controls consent. Guild, territory, economy and public rankings respond to actual accomplishments. Legendary potential is not instant mastery. Grid's canon story continues independently unless the player deliberately intersects it; never assign his debts, Pagma route, crafting identity or companions to an unrelated character.
""" + COMPACT_CLASS_GENERATION_RULE + """
""",
    "Reincarnated as a Slime": """
WORLD-SYSTEM RECORD: Keep special['Evolution Profile'] with species, stage, named_status, magicule_capacity, resistances, intrinsic_skills, extra_skills, unique_skills, ultimate_skills and evolution_requirements. Original Skills are allowed but must follow the setting's hierarchy, record effect, magicule cost, limitations, resistances/counters, acquisition cause and synthesis/evolution route. Naming, species evolution and Demon Lord awakening require their real triggers and remain distinct from ordinary training.
""",
    "Jujutsu Kaisen": """
WORLD-SYSTEM RECORD: Every original character has exactly one exclusive Birth Slot: an Innate Cursed Technique OR a Heavenly Restriction. Never grant both. Treat it as one atomic package: name, immutable governing rule, activation, targets, applications, limitations, weaknesses, costs, counters, growth, evidence and Domain expression must all describe the same concept. A new interpretation extends the rule; it never quietly replaces it. Original powers may equal canon powers in depth, uniqueness, complexity, versatility and possible scale when the narrative supports it. If a technique is overwhelmingly powerful, say so. If it genuinely has no special weakness, say so instead of inventing one; ordinary energy, output, control, range and activation still apply unless the package explicitly removes them.
JUJUTSU DEVELOPMENT: Applications, Maximum Techniques, Reverse Cursed Technique, barriers, anti-domain arts and Domain Expansion are persistent earned tracks, not generic spells. A complete Domain manifests the user's innate world, applies a sure-hit derived from the same rule, costs immense energy and has real barrier counterplay. A Heavenly Restriction develops its exchanged body, senses, tactics and cursed-tool use; never grant it an innate technique, RCT or Domain when its sacrifice makes those impossible.
BINDING VOWS: A vow records the exact promise, proportional benefit, real price, breach consequence and status. Never grant a benefit without an enforceable exchange, and never forget an active vow on later turns. Store confirmed structured vows in state_patch.special['Binding Vows'].
TECHNIQUE INTEL: Fights are information contests. NPCs begin knowing only public, witnessed or explained rules. Store per-person confirmed facts, suspicions, unknowns and evidence in state_patch.special['Technique Intel']; do not let narrator knowledge become character knowledge.
BLACK FLASH: It can occur only when a physical impact and cursed energy align exceptionally; declaring it is not success. Award it only as a confirmed combat result, then portray the temporary heightened understanding without making future Black Flashes guaranteed.
GRADE AND SOCIETY: Maintain official grade separately from raw power. Missions, witnessed exorcisms, reliability, recommendations and politics determine promotion. Great-clan membership carries specific duties, favors, sanctions and internal rivals; it is not free authority. Cursed spirits gain power from killing humans, with exponentially greater growth from high-cursed-energy victims, and become officially assessed only after credible discovery or infamy. Souls, vessels, incarnation and possession involve independent occupants and contested control; never treat a resident soul as a passive skill. Record confirmed changes through state_patch.special['Clan Record'], ['Curse Development'] or ['Soul Record']; the application preserves the mechanical ledgers.
""",
}


def _profile(value):
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _skill_names(state, ranks=()):
    result = []
    skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name, detail in skills.items():
        rank = str(detail.get("rank", "")) if isinstance(detail, dict) else ""
        if not ranks or any(token.lower() in rank.lower() for token in ranks):
            result.append(str(name))
    return result


def normalize_world_progression(state, before=None):
    """Populate structured mirrors while preserving every established value."""
    if not isinstance(state, dict):
        return []
    world = state.get("world")
    special = state.setdefault("special", {})
    if not isinstance(special, dict):
        special = state["special"] = {}
    repairs = []
    old_special = (before or {}).get("special", {}) if isinstance((before or {}).get("special", {}), dict) else {}

    def sync(profile, profile_key, legacy_key, default):
        old_profile_name = {
            "One Piece": "Haki Profile", "Hunter x Hunter": "Nen Profile", "Naruto": "Shinobi Profile",
            "Solo Max-Level Newbie": "System Profile", "Overgeared": "Satisfy Profile",
            "Reincarnated as a Slime": "Evolution Profile",
        }.get(world, "")
        old_profile = old_special.get(old_profile_name, {}) if isinstance(old_special.get(old_profile_name), dict) else {}
        structured_changed = profile_key in profile and profile.get(profile_key) != old_profile.get(profile_key)
        legacy_changed = legacy_key in special and special.get(legacy_key) != old_special.get(legacy_key)
        chosen = profile.get(profile_key, default) if structured_changed and not legacy_changed else special.get(legacy_key, profile.get(profile_key, default))
        profile[profile_key] = copy.deepcopy(chosen)
        special[legacy_key] = copy.deepcopy(chosen)
        return chosen

    if world == "One Piece":
        fruit = _profile(special.get("Devil Fruit Profile"))
        legacy_fruit = special.get("Devil Fruit", "None")
        old_fruit = old_special.get("Devil Fruit Profile", {}) if isinstance(old_special.get("Devil Fruit Profile"), dict) else {}
        fruit_changed = fruit.get("name") != old_fruit.get("name")
        legacy_changed = legacy_fruit != old_special.get("Devil Fruit", "None")
        fruit_name = fruit.get("name", legacy_fruit) if fruit_changed and not legacy_changed else legacy_fruit
        fruit["name"] = fruit_name
        special["Devil Fruit"] = fruit_name
        fruit.setdefault("type", "Unknown" if str(legacy_fruit).lower() not in {"none", "unknown", ""} else "None")
        fruit.setdefault("abilities", [])
        fruit.setdefault("limitations", ["Seawater and Sea-Prism Stone suppress Devil Fruit users"] if fruit["type"] != "None" else [])
        fruit.setdefault("counters", [])
        fruit.setdefault("awakening_status", "Unawakened" if fruit["type"] != "None" else "Not applicable")
        fruit.setdefault("awakening_requirements", [])
        haki = _profile(special.get("Haki Profile"))
        legacy_haki = special.get("Haki") if isinstance(special.get("Haki"), dict) else {}
        for branch in ("Observation", "Armament", "Conqueror"):
            entry = _profile(haki.get(branch))
            old_haki = old_special.get("Haki Profile", {}) if isinstance(old_special.get("Haki Profile"), dict) else {}
            old_entry = old_haki.get(branch, {}) if isinstance(old_haki.get(branch), dict) else {}
            structured_changed = entry.get("mastery") != old_entry.get("mastery")
            branch_legacy_changed = legacy_haki.get(branch, 0) != (old_special.get("Haki", {}) or {}).get(branch, 0)
            mastery = entry.get("mastery", 0) if structured_changed and not branch_legacy_changed else legacy_haki.get(branch, entry.get("mastery", 0))
            entry["mastery"] = _safe_int(mastery)
            legacy_haki[branch] = entry["mastery"]
            entry.setdefault("applications", [])
            entry.setdefault("evidence", [])
            haki[branch] = entry
        special["Devil Fruit Profile"], special["Haki Profile"] = fruit, haki
        special["Haki"] = legacy_haki
        special.setdefault("Crew Role", special.get("Archetype", "Unassigned"))
        special.setdefault("Ship", "None")
        crew = _profile(special.get("Crew Profile"))
        crew.setdefault("name", special.get("Crew", "None"))
        crew.setdefault("role", special.get("Crew Role", "Unassigned"))
        crew.setdefault("members", copy.deepcopy(state.get("companions", [])))
        crew.setdefault("shared_dreams", [])
        crew.setdefault("bonds", {})
        crew.setdefault("current_voyage", "")
        ship = _profile(special.get("Ship Profile"))
        ship.setdefault("name", special.get("Ship", "None"))
        ship.setdefault("condition", "Serviceable" if ship["name"] not in {"", "None"} else "No ship")
        ship.setdefault("capabilities", [])
        ship.setdefault("upgrades", [])
        ship.setdefault("needs", [])
        special["Crew Profile"], special["Ship Profile"] = crew, ship
        special.setdefault("Public Reputation", {"bounty": _safe_int(special.get("Bounty", 0)), "fame": 0, "infamy": 0})
        repairs.append("Synchronized One Piece progression profile")

    elif world == "Hunter x Hunter":
        nen = _profile(special.get("Nen Profile"))
        category = special.get("Nen Category", "Unknown")
        access = str(special.get("Nen Access") or nen.get("visibility") or "Undiscovered")
        learned = (access.lower() not in {"undiscovered", "unknown", "none", ""} or
                   any(_safe_int(special.get(key, 0)) > 0 for key in ("Ten", "Zetsu", "Ren")) or
                   str(category).lower() not in {"unknown", "none", ""})
        nen["visibility"] = "Discovered" if learned else "Undiscovered"
        latent = state.get("_latent_nen_profile") if isinstance(state.get("_latent_nen_profile"), dict) else {}
        if learned and isinstance(latent.get("hatsu_profile"), dict):
            category = str(latent.get("category") or category or "Enhancement")
            special["Nen Category"] = category
            nen["category"] = category
            nen["hatsu_profile"] = copy.deepcopy(latent["hatsu_profile"])
            special["Hatsu"] = latent["hatsu_profile"].get("name", "Developing Hatsu")
            state.pop("_latent_nen_profile", None)
            repairs.append("Revealed the character's persistent latent Nen identity")
        category = sync(nen, "category", "Nen Category", category)
        for key in ("Ten", "Zetsu", "Ren"):
            nen.setdefault(key.lower(), _safe_int(special.get(key, 0)))
        hatsu = _profile(nen.get("hatsu_profile"))
        legacy_hatsu = special.get("Hatsu", "Undeveloped")
        hatsu.setdefault("name", legacy_hatsu)
        hatsu.setdefault("category_mix", [category] if learned and category not in {"Unknown", "None"} else [])
        hatsu.setdefault("effect", "")
        hatsu.setdefault("activation", "")
        hatsu.setdefault("vows", [])
        hatsu.setdefault("limitations", [])
        hatsu.setdefault("counters", [])
        hatsu.setdefault("aura_cost", "")
        hatsu.setdefault("evidence", [])
        hatsu.setdefault("growth_path", "Learn the four major principles and define an ability that reflects the user's nature.")
        nen["hatsu_profile"] = hatsu
        if learned and not isinstance(nen.get("category_efficiency"), dict):
            nen["category_efficiency"] = {}
        nen.setdefault("category_efficiency", {})
        nen["category_efficiency"].setdefault("primary", category)
        nen["category_efficiency"].setdefault("note", "Affinity improves natural efficiency but does not prohibit creative mixed-category techniques.")
        nen.setdefault("vow_registry", copy.deepcopy(hatsu.get("vows", [])))
        nen.setdefault("restriction_consequences", copy.deepcopy(hatsu.get("limitations", [])))
        if hatsu.get("name"):
            special["Hatsu"] = hatsu["name"]
            if learned and hatsu.get("name") not in {"Undiscovered", "Undeveloped"}:
                state.setdefault("skills", {}).setdefault(hatsu["name"], {
                    "rank": "Hatsu", "category": "nen ability", "effect_type": "special",
                    "combat_usable": True, "description": hatsu.get("effect", ""),
                    "effect": hatsu.get("effect", ""), "activation": hatsu.get("activation", ""),
                    "limitation": "; ".join(map(str, hatsu.get("limitations", []))),
                    "growth_path": hatsu.get("growth_path", ""), "bonus": 6,
                })
        special.setdefault("Hunter Career", {
            "license": special.get("Hunter License", "Unlicensed"),
            "specialties": [], "completed_work": [], "professional_access": [], "verified_intelligence": [],
        })
        special["Nen Profile"] = nen
        special["Nen Access"] = nen["visibility"]
        repairs.append("Synchronized Nen progression profile")

    elif world == "Naruto":
        profile = _profile(special.get("Shinobi Profile"))
        sync(profile, "home_village", "Home Village", "None")
        sync(profile, "rank", "Shinobi Rank", "Civilian")
        sync(profile, "clan", "Clan", "None")
        affinities = special.get("Nature Affinity", "Unknown")
        affinity_profile = normalize_chakra_affinity_profile(
            special.get("Chakra Affinity Profile"), legacy=affinities,
            background=state.get("background", ""), seed=state.get("campaign_id", ""),
            canon_character_id=(state.get("player_identity") or {}).get("canon_character_id", ""),
            kekkei_genkai=bool(_profile(special.get("Kekkei Genkai Profile")) or str(special.get("Kekkei Genkai", "None")).lower() not in {"", "none", "unknown"}),
        )
        kekkei_profile = _profile(special.get("Kekkei Genkai Profile"))
        dojutsu_profile = _profile(special.get("Dōjutsu Profile"))
        legacy_kekkei = special.get("Kekkei Genkai", "None")
        legacy_dojutsu = special.get("Dōjutsu", "None")
        if not dojutsu_profile and str(legacy_dojutsu).lower() in {"", "none", "unknown", "unawakened"}:
            eye_evidence = dojutsu_story_evidence(state)
            recovered_eye = dojutsu_profile_from_evidence(eye_evidence)
            if recovered_eye:
                dojutsu_profile = recovered_eye
                legacy_dojutsu = recovered_eye["name"]
                special["Dōjutsu"] = legacy_dojutsu
                special["Dōjutsu Profile"] = copy.deepcopy(recovered_eye)
                repairs.append(f"Recovered {legacy_dojutsu} profile from established campaign play")
        if kekkei_profile:
            kekkei_profile.setdefault("name", legacy_kekkei)
            kekkei_profile.setdefault("category", "Kekkei Genkai")
            kekkei_profile.setdefault("abilities", [])
            kekkei_profile.setdefault("limitations", [])
            kekkei_profile.setdefault("counters", [])
            kekkei_profile.setdefault("growth_path", "Develop additional world-valid applications through training and conflict.")
            kekkei_profile.setdefault("non_canon_allowed", True)
            special["Kekkei Genkai"] = kekkei_profile.get("name", legacy_kekkei)
            special["Kekkei Genkai Profile"] = kekkei_profile
        if dojutsu_profile:
            dojutsu_profile.setdefault("name", legacy_dojutsu)
            dojutsu_profile.setdefault("category", "Dōjutsu")
            dojutsu_profile.setdefault("abilities", [])
            dojutsu_profile.setdefault("limitations", [])
            dojutsu_profile.setdefault("counters", [])
            dojutsu_profile.setdefault("growth_path", "Awaken and master further ocular stages through compatible experience.")
            dojutsu_profile.setdefault("non_canon_allowed", True)
            special["Dōjutsu"] = dojutsu_profile.get("name", legacy_dojutsu)
            special["Dōjutsu Profile"] = dojutsu_profile
        profile["kekkei_genkai"] = copy.deepcopy(kekkei_profile or legacy_kekkei)
        profile["dojutsu"] = copy.deepcopy(dojutsu_profile or legacy_dojutsu)
        had_jinchuriki = bool(_profile(special.get("Jinchūriki Profile")) or str(special.get("Jinchuriki", "")).strip())
        story_host = jinchuriki_story_evidence(state) if not had_jinchuriki else {}
        host_background = " ".join(filter(None, [state.get("background", ""), story_host.get("text", "")]))
        jinchuriki = normalize_jinchuriki_profile(
            special.get("Jinchūriki Profile"), legacy=special.get("Jinchuriki", ""),
            background=host_background, seed=state.get("campaign_id", ""),
        )
        if jinchuriki:
            if story_host and not had_jinchuriki and not jinchuriki.get("mechanics_applied"):
                before_stats = copy.deepcopy(state.get("stats", {}))
                state["stats"] = apply_jinchuriki_start(before_stats, jinchuriki)
                old_max = max(1, _safe_int(state.get("resource_max"), 100))
                old_current = max(0, _safe_int(state.get("resource"), old_max))
                ratio = min(1.0, old_current / old_max)
                new_max = max(old_max, int(round(old_max * float(jinchuriki.get("reserve_multiplier", 1.0) or 1.0))))
                state["resource_max"] = new_max
                state["resource"] = max(0, min(new_max, int(round(new_max * ratio))))
                jinchuriki["acquired_turn"] = story_host.get("turn", state.get("turn", 0))
                jinchuriki["mechanics_applied"] = {
                    "source": story_host.get("source", "campaign_canon"),
                    "stat_boosts": copy.deepcopy(jinchuriki.get("stat_boosts", {})),
                    "resource_max_before": old_max, "resource_max_after": new_max,
                }
                repairs.append(f"Recovered {jinchuriki.get('beast', 'tailed beast')} host mechanics from established campaign canon")
            special["Jinchūriki Profile"] = jinchuriki
            special["Jinchuriki"] = f"{jinchuriki.get('beast', 'Tailed Beast')} — {jinchuriki.get('mastery', 'Unmastered')}"
            profile["jinchuriki"] = copy.deepcopy(jinchuriki)
            affinity_profile["external_natures"] = copy.deepcopy(jinchuriki.get("nature_transformations", []))
        else:
            profile.setdefault("jinchuriki", {})
        profile.setdefault("summons", special.get("Summons", []))
        profile.setdefault("transformations", special.get("Transformations", []))
        profile["known_jutsu"] = copy.deepcopy(special.get("Known Jutsu", profile.get("known_jutsu", [])))
        starting = special.get("Starting Ability") if isinstance(special.get("Starting Ability"), dict) else {}
        if starting.get("name") and starting["name"] not in profile["known_jutsu"]:
            profile["known_jutsu"].append(starting["name"])
        special["Known Jutsu"] = copy.deepcopy(profile["known_jutsu"])
        learned_text = " ".join([*map(str, profile["known_jutsu"]), *map(str, (state.get("skills") or {}).keys())])
        for nature in CHAKRA_NATURES:
            if nature.lower() in learned_text.lower() and nature not in affinity_profile["mastered_natures"]:
                affinity_profile["mastered_natures"].append(nature)
                affinity_profile.setdefault("training_evidence", []).append(f"Established a learned {nature} technique")
            if (nature in affinity_profile["mastered_natures"] and
                    nature not in affinity_profile.get("natural_affinities", []) and
                    nature not in affinity_profile.setdefault("proficiencies", [])):
                affinity_profile["proficiencies"].append(nature)
                affinity_profile.setdefault("learning_rates", {})[nature] = 1.0
        special["Chakra Affinity Profile"] = affinity_profile
        special["Nature Affinity"] = affinity_profile["primary"]
        profile["nature_affinities"] = copy.deepcopy(affinity_profile.get("natural_affinities", []))
        profile["nature_proficiencies"] = copy.deepcopy(affinity_profile.get("proficiencies", []))
        profile["chakra_affinity"] = copy.deepcopy(affinity_profile)
        profile.setdefault("mission_record", {})
        profile.setdefault("team", [])
        profile.setdefault("mentors", [])
        profile.setdefault("clan_relationships", {})
        profile.setdefault("jutsu_research", [])
        profile.setdefault("elemental_notes", [])
        special["Shinobi Profile"] = profile
        repairs.append("Synchronized shinobi progression profile")

    elif world == "Solo Max-Level Newbie":
        profile = _profile(special.get("System Profile"))
        profile["floor"] = _safe_int(sync(profile, "floor", "Floor", state.get("tower_floor", 0)))
        profile["unspent_stat_points"] = _safe_int(sync(profile, "unspent_stat_points", "Unspent Stat Points", 0))
        profile["copied_abilities"] = copy.deepcopy(sync(profile, "copied_abilities", "Copied Abilities", []))
        profile.setdefault("copy_capacity", max(1, len(profile["copied_abilities"]) or 1))
        profile["achievements"] = copy.deepcopy(special.get("Achievements", state.get("achievements", profile.get("achievements", []))))
        profile["hidden_conditions"] = _safe_int(special.get("Hidden Conditions Found", profile.get("hidden_conditions", 0)))
        profile.setdefault("active_system_notices", [])
        profile.setdefault("build_synergies", [])
        profile.setdefault("rival_progress", {})
        profile.setdefault("floor_ecology", {
            "known_factions": [], "known_rules": [], "alternate_clears": [], "confirmed_hazards": [],
        })
        special["System Profile"] = profile
        repairs.append("Synchronized System progression profile")

    elif world == "Overgeared":
        profile = _profile(special.get("Satisfy Profile"))
        class_profile = state.get("class_profile") if isinstance(state.get("class_profile"), dict) else {}
        if class_profile.get("name") and class_profile.get("name") not in {"Unidentified Hidden Class", "Unidentified Class Signature"}:
            special["Class"] = class_profile["name"]
        profile["primary_class"] = sync(profile, "primary_class", "Class", class_profile.get("name", "Beginner"))
        profile["secondary_class"] = sync(profile, "secondary_class", "Secondary Class", "None")
        profile["class_rarity"] = class_profile.get("rank", profile.get("class_rarity", "Normal"))
        profile["class_type"] = class_profile.get("class_type") or profile.get("class_type") or infer_class_type(
            profile["primary_class"], special.get("Archetype"), class_profile.get("description"), class_profile.get("effect")
        )
        profile["class_features"] = copy.deepcopy(profile.get("class_features") or ([class_profile.get("signature_skill")] if class_profile.get("signature_skill") else []))
        profile.setdefault("specializations", [])
        profile.setdefault("advancement", class_profile.get("growth_path") or "Develop the class through meaningful class-aligned actions and quests.")
        profile["crafting_mastery"] = _safe_int(sync(profile, "crafting_mastery", "Crafting Mastery", 0))
        profile.setdefault("production_specialties", [])
        profile["known_recipes"] = copy.deepcopy(state.get("known_recipes", profile.get("known_recipes", [])))
        profile["guild"] = special.get("Guild", profile.get("guild", "None"))
        profile["npc_affinity"] = copy.deepcopy(special.get("NPC Affinity", profile.get("npc_affinity", {})))
        profile.setdefault("equipment_synergies", [])
        profile.setdefault("skill_combinations", [])
        profile.setdefault("rankings", {"overall": "Unranked", "class": "Unranked", "guild": "None"})
        special["Satisfy Profile"] = profile
        repairs.append("Synchronized Satisfy progression profile")

    elif world == "Reincarnated as a Slime":
        profile = _profile(special.get("Evolution Profile"))
        profile["species"] = sync(profile, "species", "Species", state.get("race", "Unknown"))
        profile["stage"] = sync(profile, "stage", "Evolution Stage", "Unnamed")
        profile.setdefault("named_status", "Named" if "named" in str(profile["stage"]).lower() else "Unnamed")
        profile["magicule_capacity"] = _safe_int(sync(profile, "magicule_capacity", "Magicule Capacity", 0))
        profile.setdefault("resistances", copy.deepcopy(special.get("Resistances", [])))
        profile.setdefault("intrinsic_skills", _skill_names(state, ("Intrinsic",)))
        named = copy.deepcopy(special.get("Named Skills", []))
        profile.setdefault("extra_skills", [])
        profile.setdefault("unique_skills", [x for x in named if "unique" in str(x).lower()] or named)
        profile.setdefault("ultimate_skills", [])
        starting = special.get("Starting Ability") if isinstance(special.get("Starting Ability"), dict) else {}
        if starting.get("name"):
            detail = starting.get("details") if isinstance(starting.get("details"), dict) else {}
            rank = str(detail.get("rank") or starting.get("rank") or "Extra Skill").lower()
            bucket = "ultimate_skills" if "ultimate" in rank else "unique_skills" if "unique" in rank else "extra_skills"
            if starting["name"] not in profile[bucket]:
                profile[bucket].append(starting["name"])
        special["Named Skills"] = list(dict.fromkeys(profile["unique_skills"] + profile["ultimate_skills"] + named))
        profile.setdefault("evolution_requirements", [])
        profile.setdefault("skill_synthesis", [])
        profile.setdefault("subordinate_evolutions", {})
        profile.setdefault("nation_development", {
            "settlements": [], "specialists": [], "alliances": [], "pressures": [],
        })
        special["Evolution Profile"] = profile
        repairs.append("Synchronized evolution progression profile")

    elif world == "Bleach":
        profile = _profile(special.get("Zanpakuto Profile"))
        previous_blade_name = str(special.get("Zanpakuto") or "").strip()
        profile.setdefault("name", special.get("Zanpakuto", "Unnamed Asauchi"))
        release_owned = str(special.get("Shikai", "")).lower() not in {"", "none", "unknown", "unachieved"} or str(special.get("Bankai", "")).lower() not in {"", "none", "unknown", "unachieved"}
        recorded_name = str(profile.get("name") or "").strip()
        if release_owned and recorded_name.lower() in {"", "unknown", "unnamed", "unnamed asauchi"}:
            shikai_name = str(profile.get("shikai_name") or "").strip()
            if not shikai_name:
                shikai_text = str(special.get("Shikai") or "")
                shikai_name = re.sub(r"^(?:achieved\s*[—:-]?\s*|shikai\s*[—:-]?\s*)", "", shikai_text, flags=re.I).strip()
            if not shikai_name or shikai_name.lower() in {"achieved", "unachieved", "unknown", "none"}:
                # Older saves often retained the release's real name only on
                # the learned skill after the loose profile was overwritten.
                for skill_name, detail in (state.get("skills") or {}).items():
                    rank = str(detail.get("rank", "")) if isinstance(detail, dict) else ""
                    stage = str(detail.get("release_stage", "")) if isinstance(detail, dict) else ""
                    if "shikai" not in f"{rank} {stage} {skill_name}".lower():
                        continue
                    candidate = re.sub(r"^shikai\s*[—:-]?\s*", "", str(skill_name), flags=re.I).strip()
                    if candidate and candidate.lower() not in {"achieved", "unachieved", "unknown", "none"}:
                        shikai_name = candidate
                        break
            if shikai_name and shikai_name.lower() not in {"achieved", "unachieved", "unknown", "none"}:
                profile["name"] = shikai_name
                special["Zanpakuto"] = shikai_name
                if str((state.get("equipment") or {}).get("Weapon", "")).lower().startswith("unnamed asauchi"):
                    state.setdefault("equipment", {})["Weapon"] = shikai_name
                repairs.append("Recovered the Zanpakuto name from its achieved release")
        # A sword's true name is one identity shared by equipment, releases,
        # portrait context and narrative memory.  Do this even for a dormant
        # creation preview; waiting until an old save repair caused the UI to
        # show a named Shikai beside an "Unnamed Asauchi" weapon.
        blade_name = str(profile.get("name") or profile.get("shikai_name") or "").strip()
        blade_is_known = release_owned or bool((state.get("creation_locks") or {}).get("ability_name"))
        if blade_is_known and blade_name and blade_name.lower() not in {"unknown", "unnamed", "unnamed asauchi", "none"}:
            profile["name"] = blade_name
            profile["shikai_name"] = str(profile.get("shikai_name") or blade_name)
            special["Zanpakuto"] = blade_name
            equipment = state.setdefault("equipment", {})
            weapon = str(equipment.get("Weapon") or "Unnamed Asauchi")
            if (re.search(r"\bunnamed asauchi\b", weapon, re.I)
                    or (previous_blade_name and previous_blade_name.lower() not in {"unknown", "unnamed", "unnamed asauchi"}
                        and previous_blade_name.lower() in weapon.lower())):
                equipment["Weapon"] = re.sub(
                    re.escape(previous_blade_name) if previous_blade_name.lower() not in {"", "unknown", "unnamed", "unnamed asauchi"} else r"\bUnnamed Asauchi\b",
                    blade_name, weapon, count=1, flags=re.I,
                )
                repairs.append(f"Synchronized Zanpakuto equipment as {blade_name}")
            portrait = state.setdefault("portrait_identity", {})
            portrait["zanpakuto_name"] = blade_name
            facts = state.setdefault("continuity_ledger", {}).setdefault("facts", [])
            memory = f"The player's Zanpakuto is named {blade_name}."
            if not any(isinstance(row, dict) and row.get("text") == memory for row in facts):
                facts.append({"turn": int(state.get("turn", 0) or 0), "type": "identity", "text": memory})
                state["continuity_ledger"]["facts"] = facts[-200:]
        profile.setdefault("spirit", "Not yet understood")
        profile.setdefault("inner_world", "Not yet reached")
        profile.setdefault("relationship", "Distant" if str(special.get("Shikai", "Unachieved")).lower() in {"unachieved", "none", "unknown", ""} else "Recognized")
        profile.setdefault("relationship_evidence", [])
        profile.setdefault("shikai_applications", [])
        profile.setdefault("bankai_mastery", "Unachieved" if str(special.get("Bankai", "Unachieved")).lower() in {"unachieved", "none", "unknown", ""} else "Awakened")
        special["Zanpakuto Profile"] = profile
        special.setdefault("Soul Reaper Record", {
            "academy_status": special.get("Academy Status", "Graduate"),
            "division": special.get("Squad", "Awaiting placement"),
            "duty": special.get("Current Duty", "Awaiting assignment"),
            "discipline_progress": {"Zanjutsu": 0, "Hakuda": 0, "Hoho": 0, "Kido": 0, "Reiatsu Control": 0},
            "mentors": [], "patrol_record": [], "division_relationships": {},
        })
        repairs.append("Synchronized Soul Reaper progression profile")

    elif world == "Jujutsu Kaisen":
        from jjk_system import normalize_jjk_state
        repairs.extend(normalize_jjk_state(state, before))
        system = state.setdefault("jjk_system", {})
        slot = _profile(system.get("birth_slot"))
        if not slot:
            slot = _profile(special.get("Innate Technique Profile") or special.get("Heavenly Restriction Profile"))
        system["birth_slot"] = slot
        system.setdefault("grade", special.get("Grade", "Unassessed"))
        system.setdefault("official_status", special.get("Official Status", "Unregistered"))
        system.setdefault("humans_killed", 0)
        system.setdefault("feeding_growth", 0)
        system.setdefault("black_flash_count", _safe_int(special.get("Black Flashes", 0)))
        system.setdefault("binding_vows", [])
        system.setdefault("barrier_mastery", "Foundational")
        system.setdefault("domain_status", special.get("Domain Expansion", "Unachieved"))
        system.setdefault("reverse_cursed_technique", special.get("Reverse Cursed Technique", "Unachieved"))
        special["Grade"] = system["grade"]
        special["Official Status"] = system["official_status"]
        special["Black Flashes"] = system["black_flash_count"]
        repairs.append("Synchronized jujutsu birth-slot and grade profile")

    return repairs


def identity_label(state):
    special = state.get("special") if isinstance(state.get("special"), dict) else {}
    world = state.get("world")
    if world == "One Piece":
        return special.get("Crew Role") or special.get("Archetype") or "Seafarer"
    if world == "Hunter x Hunter":
        license_status = special.get("Hunter License", "Unlicensed")
        category = special.get("Nen Category", "Unknown")
        return f"{license_status} · {category} Nen" if category not in {"", "Unknown", "None"} else str(license_status)
    if world == "Naruto":
        return special.get("Shinobi Rank") or special.get("Archetype") or "Shinobi"
    if world == "Solo Max-Level Newbie":
        return special.get("System Class") or special.get("Archetype") or "Player"
    if world == "Overgeared":
        return special.get("Class") or "Player"
    if world == "Reincarnated as a Slime":
        return special.get("Species") or state.get("race") or "Otherworlder"
    if world == "Bleach":
        return special.get("Shinigami Rank") or special.get("Archetype") or "Soul Reaper"
    if world == "Jujutsu Kaisen":
        return special.get("Grade") or "Unassessed Sorcerer"
    return (state.get("class_profile") or {}).get("name") or special.get("Archetype") or "Adventurer"
