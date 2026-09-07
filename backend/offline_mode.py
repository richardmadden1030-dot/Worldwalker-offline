"""Model-free Worldwalker activity resolution.

Offline Mode is deliberately additive: it mutates the same campaign state used
by the normal GM, map, Chronicle, progression, relationships, organizations and
combat UI.  It never calls an AI client.  The Action Deck supplies structured
activity ids; this module resolves only those bounded, game-native actions.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re
import secrets

from systems import tick_world_clocks, normalize_quest_state_machine, uses_literal_quests
from world_progression import normalize_world_progression
from worlds import WORLD_DATA, abilities_for, uses_xp_for


WORLD_ACTIVITY_FLAVOR = {
    "Naruto": {
        "patrol": ("Border Patrol", "missing-nin", "Konohagakure"),
        "hunt": ("Bingo Book Lead", "rogue shinobi", "Konohagakure"),
        "investigation": ("Suspicious Chakra Traces", "unknown operative", "Konohagakure"),
        "retrieval": ("Field Supply Retrieval", "medicinal herbs", "Konohagakure"),
        "delivery": ("Sealed Dispatch", "mission scroll", "Konohagakure"),
        "escort": ("Civilian Escort", "client", "Konohagakure"),
        "training": ("Specialist Training Request", "training partner", "Konohagakure"),
    },
    "One Piece": {
        "patrol": ("Harbor Watch", "raiders", "Foosha Village"),
        "hunt": ("Wanted Pirate Lead", "wanted pirate", "Foosha Village"),
        "investigation": ("Smuggling Rumor", "smuggler", "Foosha Village"),
        "retrieval": ("Lost Cargo", "cargo crate", "Foosha Village"),
        "delivery": ("Island Delivery", "supplies", "Foosha Village"),
        "escort": ("Merchant Passage", "merchant", "Foosha Village"),
        "training": ("Fighting Style Challenge", "sparring partner", "Foosha Village"),
    },
    "Hunter x Hunter": {
        "patrol": ("Field Survey", "dangerous fauna", "Hunter Exam Site"),
        "hunt": ("Blacklist Lead", "wanted target", "Yorknew City"),
        "investigation": ("Information Job", "unknown broker", "Yorknew City"),
        "retrieval": ("Rare Specimen", "rare specimen", "Hunter Exam Site"),
        "delivery": ("Sensitive Delivery", "sealed package", "Yorknew City"),
        "escort": ("Protected Client", "client", "Yorknew City"),
        "training": ("Nen Practice Contract", "training partner", "Heavens Arena"),
    },
    "Bleach": {
        "patrol": ("Soul Reaper Patrol", "Hollow", "Karakura Town"),
        "hunt": ("Hollow Signature", "Hollow", "Karakura Town"),
        "investigation": ("Spiritual Disturbance", "unknown spirit", "Karakura Town"),
        "retrieval": ("Recovered Soul Phone", "lost device", "Karakura Town"),
        "delivery": ("Division Dispatch", "sealed report", "Seireitei"),
        "escort": ("Soul Escort", "vulnerable soul", "Karakura Town"),
        "training": ("Division Drill", "training partner", "Seireitei"),
    },
    "Jujutsu Kaisen": {
        "patrol": ("Curse Sweep", "low-grade curse", "Tokyo Jujutsu High"),
        "hunt": ("Registered Curse", "curse", "Tokyo Jujutsu High"),
        "investigation": ("Cursed Incident", "curse user", "Tokyo Jujutsu High"),
        "retrieval": ("Cursed Object Recovery", "cursed object", "Tokyo Jujutsu High"),
        "delivery": ("Barrier Talisman Delivery", "talisman case", "Tokyo Jujutsu High"),
        "escort": ("Civilian Extraction", "civilian", "Tokyo Jujutsu High"),
        "training": ("Technique Evaluation", "training partner", "Tokyo Jujutsu High"),
    },
    "Overgeared": {
        "patrol": ("Territory Patrol", "field monsters", "Winston"),
        "hunt": ("Guild Hunt", "elite monster", "Winston"),
        "investigation": ("NPC Request", "unknown culprit", "Winston"),
        "retrieval": ("Material Commission", "rare material", "Winston"),
        "delivery": ("Trade Delivery", "commissioned goods", "Winston"),
        "escort": ("Caravan Contract", "merchant caravan", "Winston"),
        "training": ("Class Challenge", "training partner", "Winston"),
    },
    "Solo Max-Level Newbie": {
        "patrol": ("Floor Recon", "floor monsters", "Floor 1"),
        "hunt": ("Hidden Monster Hunt", "elite monster", "Floor 1"),
        "investigation": ("Hidden Condition Search", "unknown mechanism", "Floor 1"),
        "retrieval": ("System Collection Quest", "quest material", "Floor 1"),
        "delivery": ("Administrator Request", "quest item", "Floor 1"),
        "escort": ("Survivor Escort", "survivor", "Floor 1"),
        "training": ("System Training Trial", "training target", "Floor 1"),
    },
    "Reincarnated as a Slime": {
        "patrol": ("Jura Patrol", "hostile monsters", "Great Jura Forest"),
        "hunt": ("Monster Threat", "dangerous monster", "Great Jura Forest"),
        "investigation": ("Unusual Magicules", "unknown being", "Great Jura Forest"),
        "retrieval": ("Settlement Materials", "building materials", "Great Jura Forest"),
        "delivery": ("Trade Caravan", "trade goods", "Tempest"),
        "escort": ("Diplomatic Escort", "envoy", "Tempest"),
        "training": ("Skill Analysis Exercise", "training target", "Tempest"),
    },
    "Custom World": {
        "patrol": ("Local Patrol", "local threat", "Starting Region"),
        "hunt": ("Threat Hunt", "dangerous target", "Starting Region"),
        "investigation": ("Local Mystery", "unknown culprit", "Starting Region"),
        "retrieval": ("Resource Retrieval", "needed material", "Starting Region"),
        "delivery": ("Important Delivery", "package", "Starting Region"),
        "escort": ("Escort Work", "client", "Starting Region"),
        "training": ("Training Challenge", "training partner", "Starting Region"),
    },
}

WORLD_STORYLETS = {
    "Naruto": [
        ("A messenger hawk arrives", "A village dispatch asks for volunteers before the roster closes.", [("volunteer", "Volunteer", "missions"), ("study", "Study the dispatch first", "training"), ("decline", "Let it pass", "personal")]),
        ("A rival notices your training", "Someone your age lingers at the edge of the training ground, clearly measuring your progress.", [("spar", "Offer a spar", "combat"), ("talk", "Talk instead", "people"), ("ignore", "Keep training", "training")]),
    ],
    "One Piece": [
        ("A newspaper causes a stir", "A fresh paper reaches port with a headline that has sailors arguing over the next safe route.", [("read", "Read every detail", "world"), ("crew", "Discuss it with allies", "people"), ("move", "Use the distraction to explore", "travel")]),
        ("A suspicious crate washes ashore", "No owner is visible, but the markings are deliberately scraped away.", [("open", "Open it carefully", "world"), ("report", "Ask locals who lost it", "people"), ("leave", "Leave it alone", "personal")]),
    ],
    "Hunter x Hunter": [
        ("A broker offers a lead", "The information is useful enough to matter, but the broker clearly wants something in return.", [("trade", "Trade information", "world"), ("verify", "Verify the lead first", "training"), ("walk", "Walk away", "personal")]),
    ],
    "Bleach": [
        ("A faint spiritual cry cuts through the area", "It is weak, distant, and easy for ordinary people to miss.", [("trace", "Trace the reiatsu", "travel"), ("report", "Report it through proper channels", "world"), ("guard", "Stay with nearby souls", "people")]),
    ],
    "Jujutsu Kaisen": [
        ("Residual cursed energy stains a nearby structure", "The residue is fresh enough to study before it fades.", [("inspect", "Inspect the residue", "training"), ("contain", "Secure the area", "world"), ("report", "Report it", "missions")]),
    ],
    "Overgeared": [
        ("A player crowd forms around a new notice", "The reward looks ordinary, but several veteran players seem unusually interested.", [("accept", "Take the quest", "missions"), ("research", "Research why they care", "world"), ("trade", "Use the crowd to trade", "personal")]),
    ],
    "Solo Max-Level Newbie": [
        ("The System flashes an unusual notification", "The message vanishes before displaying the full condition.", [("reconstruct", "Reconstruct the hidden condition", "training"), ("test", "Test a likely trigger", "world"), ("ignore", "Save the clue for later", "personal")]),
    ],
    "Reincarnated as a Slime": [
        ("A subordinate asks for a decision", "Two useful projects need the same limited group of specialists.", [("growth", "Prioritize growth", "organization"), ("defense", "Prioritize defense", "organization"), ("delegate", "Ask them to propose a compromise", "people")]),
    ],
    "Custom World": [
        ("A local opportunity appears", "Something small has changed nearby, creating a chance to get involved.", [("investigate", "Investigate", "world"), ("ask", "Ask around", "people"), ("continue", "Keep to your plans", "personal")]),
    ],
}


def _stable_rng(state, salt=""):
    key = f"{state.get('campaign_id','')}|{state.get('turn',0)}|{state.get('canon_day',0)}|{salt}"
    seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _world_locations(state):
    names = []
    for row in WORLD_DATA.get(state.get("world"), WORLD_DATA["Custom World"]).get("map", []):
        if row and row[0] not in names:
            names.append(str(row[0]))
    for name in state.get("location_details", {}) if isinstance(state.get("location_details"), dict) else {}:
        if name not in names:
            names.append(name)
    for row in state.get("custom_locations", []) if isinstance(state.get("custom_locations"), list) else []:
        name = row.get("name") if isinstance(row, dict) else row
        if name and name not in names:
            names.append(str(name))
    return names


def _number(value, fallback=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _relationship_score(state, name):
    memory = state.setdefault("npc_memories", {}).setdefault(name, {})
    contact = state.setdefault("contacts", {}).setdefault(name, {})
    candidates = [memory.get("relationship"), memory.get("affinity"), contact.get("relationship"), contact.get("affinity")]
    vals = [_number(x, 0) for x in candidates if x is not None]
    return int(round(max(vals) if vals else 0))


def _change_relationship(state, name, delta, reason):
    score = max(-100, min(100, _relationship_score(state, name) + int(delta)))
    memory = state.setdefault("npc_memories", {}).setdefault(name, {})
    contact = state.setdefault("contacts", {}).setdefault(name, {})
    memory["relationship"] = score
    memory.setdefault("chain", []).append({"turn": int(state.get("turn", 0)) + 1, "change": int(delta), "reason": reason})
    memory["chain"] = memory["chain"][-30:]
    contact["relationship"] = score
    return score


def _difficulty_multiplier(state):
    return {"Story": .75, "Adventurer": 1.0, "Veteran": 1.2, "Nightmare": 1.45}.get(state.get("difficulty"), 1.0)


class OfflineMixin:
    def offline_enabled(self):
        return bool(self.settings.get("offline_mode", True))

    def background_ai_due(self):
        if self.offline_enabled():
            return False
        return super().background_ai_due()

    def ensure_offline_state(self):
        row = self.state.setdefault("offline_mode", {})
        row.setdefault("version", 2)
        row.setdefault("mission_offers", [])
        row.setdefault("completed_generated_quests", 0)
        row.setdefault("pending_event", None)
        row.setdefault("event_history", [])
        row.setdefault("daily", {})
        row.setdefault("last_result", {})
        row["travel_options"] = _world_locations(self.state)[:80]
        return row

    def offline_opening(self):
        if not self.campaign_active:
            raise ValueError("Start or load a campaign first.")
        row = self.ensure_offline_state()
        if not self.state.get("opening_complete"):
            self.state["opening_complete"] = True
            world = self.state.get("world", "Custom World")
            where = self.state.get("location") or WORLD_DATA.get(world, {}).get("start") or "the starting area"
            self.append(
                f"[OFFLINE CAMPAIGN]\n{self.state.get('name','Your character')} begins in {where}. "
                "The world will advance through Activities, missions, travel, relationships, training, combat, expeditions and existing Worldwalker systems. No AI model is required.",
                "system",
            )
            self.state["suggested_actions"] = ["Open Activities", "Explore nearby", "Look for work"]
        row["active"] = True
        self.autosave()
        return {"state": self.public_state(), "story": self._flush_story(), "offline_mode": True}

    def _offline_minutes(self, duration, category):
        if duration == "week": return 10080
        if duration == "month": return 43200
        if duration == "day": return 1440
        if duration == "hour": return 60
        if category in {"training", "missions", "travel", "combat", "world", "organization"}: return 60
        return 15

    def _offline_gain_stat(self, label, amount, reason):
        stats = self.state.setdefault("stats", {})
        if label not in stats:
            return None
        before = _number(stats.get(label), 0)
        stats[label] = round(before + max(.1, float(amount)), 2)
        self.state.setdefault("training_log", []).append({"turn": int(self.state.get("turn", 0)) + 1, "stat": label, "gain": round(stats[label] - before, 2), "reason": reason})
        self.state["training_log"] = self.state["training_log"][-100:]
        return label, before, stats[label]

    def _offline_train(self, action_id, label, rng, minutes):
        stats = self.state.setdefault("stats", {})
        world = self.state.get("world", "Custom World")
        skill_name = action_id.split(":", 1)[1] if action_id.startswith("skill:") else ""
        gain = max(.25, min(2.4, (minutes / 60.0) ** .45 * .55))
        # Longer sessions help, but do not allow one click to skip whole arcs.
        gain *= {"Story":1.1,"Adventurer":1.0,"Veteran":.9,"Nightmare":.8}.get(self.state.get("difficulty"),1.0)
        daily = self.ensure_offline_state().setdefault("daily", {})
        day_key = str(self.state.get("canon_day", 0))
        day = daily.setdefault(day_key, {"training":0,"social":{},"board":0})
        training_count = int(day.get("training", 0) or 0)
        if training_count >= 3:
            gain *= .35
        elif training_count == 2:
            gain *= .65
        day["training"] = training_count + 1
        # Keep only a short recent daily ledger.
        if len(daily) > 14:
            for old in list(daily)[:-14]: daily.pop(old, None)
        if skill_name:
            skills = self.state.setdefault("skills", {})
            row = skills.get(skill_name)
            if isinstance(row, dict):
                key = "level" if "level" in row else "bonus"
                prior = _number(row.get(key), 0)
                row[key] = round(prior + gain, 2)
            elif isinstance(row, (int, float)):
                prior = float(row); skills[skill_name] = round(prior + gain, 2)
            else:
                prior = 0.0; skills[skill_name] = {"level": round(gain, 2), "source": "offline training"}
            return f"You spend focused time practicing **{skill_name}**. Repetition becomes cleaner and more reliable.", [f"{skill_name} +{gain:.1f}"]
        hints = {
            "Naruto": ["Ninjutsu","Taijutsu","Genjutsu","Chakra Control","Willpower"],
            "One Piece": ["Strength","Agility","Endurance","Instinct","Willpower"],
            "Hunter x Hunter": ["Aura Control","Willpower","Agility","Strength","Cunning"],
            "Bleach": ["Zanjutsu","Hakuda","Hoho","Kido","Reiatsu Control"],
            "Jujutsu Kaisen": ["Cursed Energy Control","Physical Ability","Technique Mastery","Barrier Technique","Willpower"],
            "Overgeared": ["Dexterity","Strength","Intelligence","Constitution","Wisdom"],
            "Solo Max-Level Newbie": ["Dexterity","Strength","Intelligence","Wisdom","Constitution"],
            "Reincarnated as a Slime": ["Magicule Control","Skill Mastery","Instinct","Willpower"],
        }.get(world, list(stats))
        choices = [x for x in hints if x in stats] or list(stats)
        if not choices:
            return "You train deliberately, but this character has no numerical discipline available to advance yet.", []
        target = choices[0]
        low = action_id.lower() + " " + label.lower()
        for name in choices:
            if name.lower() in low:
                target = name; break
        if action_id in {"training-stats", "combat-spar"} and len(choices) > 1:
            target = sorted(choices, key=lambda n: _number(stats.get(n), 0))[0]
        changed = self._offline_gain_stat(target, gain, label)
        note = f"{target} +{gain:.1f}" if changed else ""
        return f"You commit the session to **{target}**, working on a weakness instead of chasing a generic level bar.", [note] if note else []

    def _generate_mission_offers(self):
        row = self.ensure_offline_state()
        existing = [x for x in row.get("mission_offers", []) if isinstance(x, dict) and x.get("status", "offered") == "offered"]
        if len(existing) >= 3:
            return existing[:3]
        rng = _stable_rng(self.state, "mission-board")
        world = self.state.get("world", "Custom World")
        palette = WORLD_ACTIVITY_FLAVOR.get(world, WORLD_ACTIVITY_FLAVOR["Custom World"])
        archetypes = list(palette)
        rng.shuffle(archetypes)
        locations = _world_locations(self.state)
        here = self.state.get("location") or (locations[0] if locations else "Starting Region")
        offers = []
        for index, archetype in enumerate(archetypes[:3]):
            base_title, target, fallback = palette[archetype]
            destinations = [x for x in locations if x != here]
            destination = rng.choice(destinations) if destinations and archetype in {"delivery","escort","hunt","investigation","retrieval"} else here
            difficulty = rng.choice([1,1,2,2,3])
            reward = int((65 + difficulty * 45 + rng.randint(0, 45)) * _difficulty_multiplier(self.state))
            offers.append({
                "id": secrets.token_hex(6), "name": f"{base_title}: {destination}", "title": f"{base_title}: {destination}",
                "archetype": archetype, "target": target, "origin": here, "destination": destination,
                "difficulty": difficulty, "reward": reward, "status": "offered", "progress": 0,
                "objectives": [{"id":"main", "text": self._quest_objective(archetype, target, destination), "status":"active", "progress":0, "optional":False}],
                "generated_offline": True,
            })
        merged = [*existing, *offers]
        seen = set(); clean = []
        for offer in merged:
            key = (offer.get("title"), offer.get("destination"), offer.get("archetype"))
            if key in seen: continue
            seen.add(key); clean.append(offer)
        row["mission_offers"] = clean[:3]
        return row["mission_offers"]

    @staticmethod
    def _quest_objective(archetype, target, destination):
        return {
            "patrol": f"Complete a meaningful patrol around {destination}",
            "hunt": f"Track down and defeat or otherwise resolve the threat posed by {target} near {destination}",
            "investigation": f"Gather enough evidence to explain the situation involving {target} at {destination}",
            "retrieval": f"Recover {target} from {destination}",
            "delivery": f"Deliver {target} safely to {destination}",
            "escort": f"Escort {target} safely to {destination}",
            "training": f"Complete the required training challenge at {destination}",
        }.get(archetype, f"Resolve the assignment at {destination}")

    def _accept_offer(self, offer_id):
        row = self.ensure_offline_state()
        offer = next((x for x in row.get("mission_offers", []) if x.get("id") == offer_id), None)
        if not offer:
            raise ValueError("That mission offer is no longer available.")
        quest = copy.deepcopy(offer); quest["status"] = "active"
        self.state.setdefault("quests", []).append(quest)
        row["mission_offers"] = [x for x in row["mission_offers"] if x.get("id") != offer_id]
        normalize_quest_state_machine(self.state)
        return f"You accept **{quest['title']}**. The assignment is now tracked in your existing Worldwalker agenda.", ["Mission accepted"]

    def _work_quest(self, name, rng):
        quests = [q for q in self.state.get("quests", []) if isinstance(q, dict) and str(q.get("status", "active")).lower() not in {"complete","completed","failed","cancelled","abandoned"}]
        quest = next((q for q in quests if (q.get("name") or q.get("title")) == name), None)
        if not quest:
            return "That assignment is no longer active.", []
        destination = quest.get("destination") or quest.get("location") or self.state.get("location")
        if destination and destination != self.state.get("location") and quest.get("archetype") not in {"delivery","escort"}:
            return f"The next concrete step is at **{destination}**. Travel there before attempting to finish this assignment.", []
        archetype = quest.get("archetype", "investigation")
        progress = int(quest.get("progress", 0) or 0)
        # A combat spawned by this assignment resolves through Worldwalker's
        # existing combat/tactical systems.  Credit that authoritative result
        # exactly once instead of inventing a second fight on the next click.
        combat = self.state.get("combat") if isinstance(self.state.get("combat"), dict) else {}
        if not combat.get("quest_name"):
            combat = self.state.get("last_combat") if isinstance(self.state.get("last_combat"), dict) else combat
        if (not combat.get("active") and combat.get("quest_name") == (quest.get("title") or quest.get("name"))
                and combat.get("outcome") in {"victory", "overwhelmed"} and not combat.get("offline_quest_credit_applied")):
            progress = min(100, progress + 60)
            quest["progress"] = progress
            combat["offline_quest_credit_applied"] = True
            for obj in quest.get("objectives", []):
                if isinstance(obj, dict): obj["progress"] = progress
        step = rng.randint(34, 58)
        if archetype in {"hunt","patrol"} and progress < 100 and not self.combat_active() and rng.random() < .45:
            self._start_offline_combat(quest.get("target") or "mission threat", spar=False, quest_name=quest.get("title") or quest.get("name"))
            return f"The assignment turns dangerous. **{quest.get('target') or 'A hostile threat'}** blocks further progress; the mission continues through Worldwalker's combat system.", ["Combat started"]
        progress = min(100, progress + step)
        quest["progress"] = progress
        for obj in quest.get("objectives", []):
            if isinstance(obj, dict): obj["progress"] = progress
        if progress < 100:
            return f"You make concrete progress on **{quest.get('title') or quest.get('name')}**. The situation is clearer, but the assignment is not finished yet.", [f"Mission {progress}%"]
        quest["status"] = "complete"
        for obj in quest.get("objectives", []):
            if isinstance(obj, dict): obj["status"] = "complete"; obj["progress"] = 100
        reward = int(quest.get("reward", 0) or 0)
        if reward:
            currency = self.state.setdefault("currency", {"name":"Currency","amount":0})
            currency["amount"] = _number(currency.get("amount"), 0) + reward
        row = self.ensure_offline_state(); row["completed_generated_quests"] = int(row.get("completed_generated_quests", 0)) + 1
        if uses_xp_for(self.state.get("world"), self.state.get("custom_world", "")):
            before = copy.deepcopy(self.state)
            self.apply_system_xp(before, [f"Complete {quest.get('title') or quest.get('name')}"], [], 120, "normal", [{"type":"quest_complete"}])
        return f"**{quest.get('title') or quest.get('name')}** is complete. The result is recorded by the same campaign state used by the Chronicle and Journal.", [f"Reward +{reward:g} {self.state.get('currency',{}).get('name','Currency')}" if reward else "Mission complete"]

    def _start_offline_combat(self, target, spar=False, quest_name=""):
        if self.combat_active():
            return
        world = self.state.get("world", "Custom World")
        stats = [float(v) for v in self.state.get("stats", {}).values() if isinstance(v, (int,float))]
        avg = sum(stats)/len(stats) if stats else 35
        # Mission threats have a bounded role-based baseline. Spars are safer.
        power = int(max(20, min(180, avg * (.72 if spar else .92))))
        hp = max(25, power * 2)
        self.state["combat"] = {
            "active": True,
            "round": 1,
            "enemy": {"name": str(target or "Opponent"), "role": "sparring partner" if spar else "field threat", "power": power,
                      "hp": hp, "hp_max": hp, "alive": True},
            "log": [], "non_lethal": bool(spar), "spare_enemy": bool(spar),
            "offline_generated": True, "quest_name": quest_name,
            "tactical_enabled": world in {"Naruto","One Piece","Bleach"} and not spar,
        }
        self.ensure_combat_numbers()

    def _maybe_storylet(self, category):
        row = self.ensure_offline_state()
        if row.get("pending_event") or category == "combat" or self.combat_active():
            return None
        rng = _stable_rng(self.state, "storylet")
        # Roughly one interesting interruption every 4-6 meaningful actions.
        if rng.random() > .24:
            return None
        pool = WORLD_STORYLETS.get(self.state.get("world"), WORLD_STORYLETS["Custom World"])
        title, text, raw_choices = rng.choice(pool)
        event = {"id": secrets.token_hex(6), "title": title, "text": text,
                 "choices": [{"id": cid, "label": label, "category": cat} for cid,label,cat in raw_choices]}
        row["pending_event"] = event
        return event

    def _resolve_storylet_choice(self, event_id, choice_id):
        row = self.ensure_offline_state(); event = row.get("pending_event")
        if not event or event.get("id") != event_id:
            return "That opportunity has already passed.", []
        choice = next((x for x in event.get("choices", []) if x.get("id") == choice_id), None)
        if not choice:
            raise ValueError("That event choice is unavailable.")
        effects = []
        cat = choice.get("category")
        if cat == "training":
            text, more = self._offline_train("training-study", choice.get("label","Study"), _stable_rng(self.state,"event-train"), 60); effects += more
        elif cat == "people":
            people = [x for x in self.state.get("contacts", {})]
            if people:
                who = people[0]; score = _change_relationship(self.state, who, 3, event.get("title", "shared event")); effects.append(f"{who} relationship → {score}")
        elif cat == "missions":
            self._generate_mission_offers(); effects.append("New work available")
        elif cat == "combat":
            self._start_offline_combat("Rival", spar=True); effects.append("Spar started")
        elif cat == "travel":
            locations = [x for x in _world_locations(self.state) if x != self.state.get("location")]
            if locations:
                self.state["location"] = locations[0]; effects.append(f"Traveled to {locations[0]}")
        elif cat == "organization":
            self.state.setdefault("reputation", 0); self.state["reputation"] = int(self.state.get("reputation",0) or 0) + 1; effects.append("Reputation +1")
        row["event_history"].append({"turn": int(self.state.get("turn",0))+1, "title":event.get("title"), "choice":choice.get("label")})
        row["event_history"] = row["event_history"][-60:]
        row["pending_event"] = None
        return f"**{event.get('title')}** — You choose: **{choice.get('label')}**. The opportunity resolves and the world moves on.", effects

    def resolve_offline_activity(self, payload):
        if not self.offline_enabled():
            raise ValueError("Offline Mode is disabled in Settings.")
        if not self.campaign_active:
            raise ValueError("Start or load a campaign first.")
        self.ensure_offline_state()["active"] = True
        action_id = str(payload.get("id") or "").strip()
        label = str(payload.get("label") or action_id or "Activity").strip()
        category = str(payload.get("category") or "personal").strip()
        duration = str(payload.get("duration") or "moment").strip()
        person = str(payload.get("person") or "").strip()
        if not action_id:
            raise ValueError("Choose an activity first.")
        if self.combat_active() and category != "combat" and not action_id.startswith("offline-event:"):
            raise ValueError("Finish the current battle before doing another world activity.")
        before = copy.deepcopy(self.state)
        rng = _stable_rng(self.state, action_id)
        minutes = self._offline_minutes(duration, category)
        effects = []

        if action_id.startswith("offline-event:"):
            _, event_id, choice_id = action_id.split(":", 2)
            narrative, effects = self._resolve_storylet_choice(event_id, choice_id)
            minutes = 15
        elif action_id.startswith("offline-accept:"):
            narrative, effects = self._accept_offer(action_id.split(":",1)[1]); minutes = 5
        elif action_id.startswith("quest:"):
            narrative, effects = self._work_quest(action_id.split(":",1)[1], rng)
        elif action_id.startswith("travel:"):
            destination = action_id.split(":",1)[1]
            if destination not in _world_locations(self.state):
                raise ValueError("That destination is not established on this campaign's map yet.")
            origin = self.state.get("location")
            self.state["location"] = destination
            if destination not in self.state.setdefault("discovered_locations", []): self.state["discovered_locations"].append(destination)
            self.state.setdefault("travel_history", []).append({"from":origin,"to":destination,"turn":int(self.state.get("turn",0))+1})
            narrative = f"You travel from **{origin}** to **{destination}** using an established route. The Living Map and location-dependent activities now treat {destination} as your real position."
            effects = [f"Location → {destination}"]
        elif action_id == "travel-explore":
            known = set(self.state.setdefault("discovered_locations", [])); candidates = [x for x in _world_locations(self.state) if x not in known and x != self.state.get("location")]
            if candidates:
                found = rng.choice(candidates); known.add(found); self.state["discovered_locations"] = list(known)
                narrative = f"You explore beyond the familiar routes and learn enough about **{found}** to mark it as a destination in your campaign knowledge."
                effects = [f"Discovered {found}"]
            else:
                narrative = "You explore the current area thoroughly, gathering local context and checking for anything your established abilities or contacts would reasonably reveal."
                effects = ["Local knowledge improved"]
        elif action_id in {"missions-work","naruto-mission","hxh-work","jjk-mission","og-opportunity"}:
            offers = self._generate_mission_offers(); narrative = f"You review current opportunities. **{len(offers)} assignments** fit your present location and world state."; effects=["Mission board refreshed"]
        elif action_id.startswith("skill:") or category == "training" or action_id in {"training-stats","training-study","naruto-chakra","hxh-nen","bleach-kido","jjk-technique","og-class","solo-synergy","slime-analysis"}:
            narrative, effects = self._offline_train(action_id, label, rng, minutes)
        elif action_id.startswith(("talk:","spend:","advice:","help:","train:","gift:","protect:","order:")) or person:
            who = person or action_id.split(":",1)[1]
            delta = 1 if action_id.startswith("advice:") else 2 if action_id.startswith(("talk:","order:")) else 3 if action_id.startswith(("spend:","help:","train:")) else 4 if action_id.startswith(("gift:","protect:")) else 2
            daily = self.ensure_offline_state().setdefault("daily", {})
            day = daily.setdefault(str(self.state.get("canon_day", 0)), {"training":0,"social":{},"board":0})
            social = day.setdefault("social", {}); count = int(social.get(who, 0) or 0)
            if count >= 3: delta = 0
            elif count >= 1: delta = max(1, delta - 1)
            social[who] = count + 1
            score = _change_relationship(self.state, who, delta, label)
            narrative = f"You **{label.lower()}**. {who}'s relationship with you changes because of an actual shared interaction rather than an AI-authored assumption."
            effects = [f"{who} relationship → {score}"]
            if score >= 35 and not any((c.get("name") if isinstance(c,dict) else c)==who for c in self.state.get("companions", [])) and action_id.startswith("help:"):
                self.state.setdefault("relationship_opportunities", []).append({"npc":who,"kind":"companion","reason":"Repeated trust and mutual help have created a plausible invitation opportunity."})
                effects.append("Companion opportunity unlocked")
        elif action_id in {"personal-rest","personal-sleep","personal-recover"}:
            heal = max(1, round(_number(self.state.get("hp_max"),100) * (.22 if action_id=="personal-rest" else .5 if action_id=="personal-sleep" else .35)))
            self.state["hp"] = min(_number(self.state.get("hp_max"),100), _number(self.state.get("hp"),0)+heal)
            self.state["resource"] = min(_number(self.state.get("resource_max"),100), _number(self.state.get("resource"),0)+round(heal*.8))
            narrative = "You take recovery seriously instead of treating downtime as empty time. Injuries, fatigue and your world-specific resource are given room to recover."
            effects = [f"HP recovered +{heal}"]
        elif action_id in {"personal-meal","personal-relax","personal-reflect","personal-maintain","personal-finances","personal-celebrate","personal-shop"}:
            narrative = f"You **{label.lower()}**. It is a small roleplay beat, but it still consumes believable time and can feed later relationship, economy or world opportunities."
            effects = ["Downtime recorded"]
        elif action_id in {"combat-spar","spar:Rival"} or action_id.startswith("spar:"):
            target = person or (action_id.split(":",1)[1] if ":" in action_id else "Sparring Partner")
            self._start_offline_combat(target, spar=True); narrative=f"You arrange a nonlethal spar with **{target}**. The encounter now uses Worldwalker's existing combat controls."; effects=["Spar started"]
        elif action_id in {"combat-patrol","combat-hunt"}:
            target = WORLD_ACTIVITY_FLAVOR.get(self.state.get("world"), WORLD_ACTIVITY_FLAVOR["Custom World"])["hunt"][1]
            if rng.random() < .68:
                self._start_offline_combat(target, spar=False); narrative=f"Your search turns up a credible **{target}**. The encounter moves into Worldwalker's combat system instead of being auto-resolved in prose."; effects=["Combat started"]
            else:
                narrative="You patrol carefully. No convenient enemy appears just because you clicked a combat activity; the quiet itself becomes useful reconnaissance."; effects=["Area checked"]
        elif category == "organization" or action_id.startswith("group-"):
            self.state["reputation"] = int(self.state.get("reputation",0) or 0) + 1
            narrative = f"You **{label.lower()}** through the organization structures already present in the campaign. Members keep their own identities and authority relationships."
            effects=["Organizational standing +1"]
        else:
            narrative = f"You **{label.lower()}**. The activity resolves locally from the current campaign facts, advances believable time, and leaves the same Worldwalker state available to every existing panel."
            effects = ["Activity completed"]

        # Advance the same civil/canon clock used by normal Worldwalker.
        pending_canon = self.advance_clock(before, minutes, "minutes") if minutes > 0 else []
        for event in tick_world_clocks(self.state, minutes):
            if isinstance(event, dict) and event.get("message"):
                self.append(f"[WORLD MOVEMENT]\n{event['message']}", "system", canon_day=self.state.get("canon_day"))
        self.state["turn"] = int(before.get("turn", 0) or 0) + 1
        normalize_world_progression(self.state, before)
        normalize_quest_state_machine(self.state)
        try:
            self.archive_finished_quests()
        except Exception:
            pass
        try:
            self.sync_derived_pools(before)
        except Exception:
            pass
        for item in pending_canon:
            self.append(item.get("text", ""), item.get("tag"), canon_day=item.get("canon_day"), detail=item.get("detail"))
        effect_text = "\n".join(f"• {x}" for x in effects if x)
        self.append(f"{narrative}{'\n\n'+effect_text if effect_text else ''}", "narrative", canon_day=self.state.get("canon_day"))
        storylet = None if action_id.startswith("offline-event:") else self._maybe_storylet(category)
        if storylet:
            self.append(f"[OPPORTUNITY — {storylet['title']}]\n{storylet['text']}", "system", canon_day=self.state.get("canon_day"))
        self.state["suggested_actions"] = ["Open Activities", "Review current agenda", "Explore the world"]
        self.ensure_offline_state()["last_result"] = {"turn":self.state["turn"],"activity":label,"effects":effects}
        self.autosave()
        return {"state": self.public_state(), "story": self._flush_story(), "offline_mode": True,
                "result": {"title": label, "narrative": narrative, "effects": effects, "storylet": storylet},
                "combat_started": self.combat_active() and not bool(before.get("combat",{}).get("active"))}
