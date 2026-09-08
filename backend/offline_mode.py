"""Deterministic Offline Mode for Worldwalker.

This module does not replace Worldwalker's existing game state.  It resolves
structured activities directly against the same state, combat, maps,
relationships, progression, quests, clocks and Chronicle used by normal play.
No AI client is called from this module.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re
from datetime import datetime

from worlds import WORLD_DATA, WORLD_EXPANSIONS, abilities_for, uses_xp_for
from systems import tick_world_clocks, normalize_quest_state_machine, quest_presentation_for, uses_literal_quests
from simulation import advance_npc_intentions, record_simulation_events
from world_activity import advance_world_activity
from life_simulation import advance as advance_life_simulation
from world_progression import normalize_world_progression
from skill_system import normalize_skill_map


OFFLINE_WORLD = {
    "Naruto": {"mission":"mission", "authority":"village", "enemy":"rogue shinobi", "training":"shinobi training"},
    "One Piece": {"mission":"opportunity", "authority":"local contact", "enemy":"hostile pirate", "training":"combat training"},
    "Hunter x Hunter": {"mission":"Hunter job", "authority":"client", "enemy":"dangerous target", "training":"Hunter training"},
    "Bleach": {"mission":"division assignment", "authority":"division", "enemy":"Hollow", "training":"Soul Reaper training"},
    "Jujutsu Kaisen": {"mission":"jujutsu mission", "authority":"supervisor", "enemy":"cursed spirit", "training":"jujutsu training"},
    "Overgeared": {"mission":"quest", "authority":"quest giver", "enemy":"elite monster", "training":"Satisfy training"},
    "Solo Max-Level Newbie": {"mission":"System opportunity", "authority":"System", "enemy":"floor monster", "training":"Tower training"},
    "Reincarnated as a Slime": {"mission":"request", "authority":"local leader", "enemy":"hostile monster", "training":"skill training"},
    "Custom World": {"mission":"job", "authority":"local contact", "enemy":"hostile threat", "training":"training"},
}

MISSION_KINDS = ("patrol", "investigate", "retrieve", "escort", "training", "hunt", "delivery")


def _clean(value, limit=180):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _stable_int(*parts, mod=10_000_000):
    raw = "|".join(str(p or "") for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16) % mod


def _map_locations(state):
    names = []
    for row in WORLD_DATA.get(state.get("world"), {}).get("map", []):
        if isinstance(row, (list, tuple)) and row:
            names.append(str(row[0]))
    names.extend(str(x) for x in state.get("discovered_locations", []) if x)
    names.extend(str(x) for x in (state.get("location_details") or {}).keys())
    for row in state.get("custom_locations", []) if isinstance(state.get("custom_locations"), list) else []:
        if isinstance(row, dict) and row.get("name"):
            names.append(str(row["name"]))
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def _known_people(state):
    names = []
    for source in (state.get("contacts") or {}, state.get("npc_memories") or {}):
        for name in source:
            if str(name).strip() and str(name).strip() != state.get("name"):
                names.append(str(name).strip())
    for row in state.get("companions", []) or []:
        name = row.get("name") if isinstance(row, dict) else row
        if name:
            names.append(str(name))
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def _skill_bonus(detail):
    if isinstance(detail, (int, float)):
        return int(detail)
    if not isinstance(detail, dict):
        return 0
    try:
        return int(detail.get("bonus", detail.get("level", detail.get("mastery", 0))) or 0)
    except (TypeError, ValueError):
        return 0


def _difficulty_shift(state):
    return {"Story": -12, "Adventurer": -4, "Veteran": 5, "Nightmare": 12}.get(state.get("difficulty"), 0)


def _world_rank_label(world):
    return {
        "Naruto":"Shinobi Standing", "One Piece":"Reputation", "Hunter x Hunter":"Hunter Standing",
        "Bleach":"Division Standing", "Jujutsu Kaisen":"Sorcerer Standing", "Overgeared":"Level",
        "Solo Max-Level Newbie":"Level", "Reincarnated as a Slime":"Evolution & Nation Standing",
        "Custom World":"Standing",
    }.get(world, "Standing")


class OfflineMixin:
    """Structured, model-free activity resolver mixed into GameSession."""

    def offline_mode_enabled(self):
        return bool(self.settings.get("offline_mode", False))

    def _offline_root(self):
        root = self.state.setdefault("offline_mode", {})
        root.setdefault("version", 1)
        root.setdefault("daily", {})
        root.setdefault("mission_board", [])
        root.setdefault("mission_board_day", None)
        root.setdefault("activity_history", [])
        root.setdefault("storylet_history", [])
        root.setdefault("pending_event", None)
        root.setdefault("last_combat_sync", "")
        return root

    def _offline_day_bucket(self):
        root = self._offline_root()
        day = str(int(self.state.get("canon_day", 0) or 0))
        bucket = root["daily"].setdefault(day, {"training":0, "people":{}, "board_refreshes":0, "storylets":0})
        # Keep save growth bounded.
        if len(root["daily"]) > 45:
            for old in sorted(root["daily"], key=lambda x: int(x))[:-45]:
                root["daily"].pop(old, None)
        return bucket

    def _offline_roll(self, action_id, stat_names=(), skill_name="", difficulty=48):
        stats = self.state.get("stats") or {}
        values = [float(stats.get(name, 0) or 0) for name in stat_names if name in stats]
        stat = sum(values) / len(values) if values else (sum(float(v or 0) for v in stats.values()) / max(1, len(stats)))
        skill = _skill_bonus((self.state.get("skills") or {}).get(skill_name)) if skill_name else 0
        seed = _stable_int(self.state.get("campaign_id"), self.state.get("turn"), self.state.get("canon_time_minutes"), action_id, len(self._offline_root().get("activity_history", [])))
        raw = 1 + (seed % 100)
        target = max(12, min(92, int(difficulty + _difficulty_shift(self.state))))
        total = raw + min(35, stat / 4) + min(25, skill / 2)
        return {"raw":raw, "total":round(total,1), "difficulty":target, "success":total >= target, "margin":round(total-target,1)}

    def _offline_append(self, title, body, tag="system", detail=None):
        text = f"[{title}]\n{body}" if title else body
        self.append(text, tag, canon_day=self.state.get("canon_day"), detail=detail)
        return text

    def _offline_advance_time(self, minutes, action_text=""):
        minutes = max(0, int(minutes or 0))
        if not minutes:
            return []
        before = copy.deepcopy(self.state)
        pending = self.advance_clock(before, minutes, "minutes")
        for row in pending or []:
            if isinstance(row, dict) and row.get("text"):
                self.append(row["text"], row.get("tag", "canon_event"), canon_day=row.get("canon_day"), detail=row.get("detail"))
        events = []
        try:
            events += tick_world_clocks(self.state, minutes) or []
            events += advance_npc_intentions(self.state, minutes, "balanced") or []
            record_simulation_events(self.state, events, "offline_mode")
        except Exception:
            events = []
        for event in events[:3]:
            if not isinstance(event, dict):
                continue
            message = _clean(event.get("message") or event.get("narrative"), 500)
            if message:
                self.state.setdefault("world_events", []).append(message)
                self.state.setdefault("background_world_feed", []).append(message)
        try:
            advance_life_simulation(self.state, actions=[action_text] if action_text else [], elapsed_minutes=minutes)
        except Exception:
            pass
        return events

    def offline_opening(self):
        """Create a grounded first scene using only facts already in the new save."""
        if not self.campaign_active:
            raise ValueError("Start a campaign first.")
        state = self.state
        world = state.get("world", "Custom World")
        if not state.get("opening_complete"):
            state["opening_complete"] = True
        person = next(iter(_known_people(state)), "")
        place = state.get("location", "the starting area")
        role = (state.get("special") or {}).get("Archetype") or state.get("position") or "new arrival"
        label = OFFLINE_WORLD.get(world, OFFLINE_WORLD["Custom World"])["mission"]
        lead = f"Review available {label}s"
        if world == "One Piece": lead = "Explore the island and listen for opportunities"
        elif world == "Hunter x Hunter": lead = "Check for Hunter work and useful leads"
        elif world == "Bleach": lead = "Report for duty and review the current spiritual situation"
        elif world == "Reincarnated as a Slime": lead = "Meet the people nearby and learn what the settlement needs"
        state["suggested_actions"] = [lead, f"Train as a {role}", f"Explore {place}"]
        body = f"{state.get('name','Traveler')} begins in **{place}** as a {role}. The world is already moving around them; local work, training, relationships, exploration and danger can all be pursued from the Activities menu."
        if person:
            body += f" **{person}** is one of the people already connected to this campaign."
        body += " Offline Mode resolves those choices directly through Worldwalker's existing mechanics without contacting an AI model."
        self._offline_append("OFFLINE CAMPAIGN READY", body, "system")
        self.autosave()
        return {"status":"ok", "narrative":body, "story":self._flush_story(), "state":self.public_state(), "offline":True}

    def _offline_training_target(self, action_id, label=""):
        stats = self.state.get("stats") or {}
        skills = self.state.get("skills") or {}
        text = f"{action_id} {label}".lower()
        if action_id.startswith("skill:"):
            name = action_id.split(":",1)[1]
            if name in skills:
                return ("skill", name)
        # World/system-native keywords first.
        for name in stats:
            key = name.lower()
            if key in text or any(piece in text for piece in key.split() if len(piece) >= 5):
                return ("stat", name)
        world = self.state.get("world")
        preferences = {
            "Naruto":["Chakra Control","Ninjutsu","Taijutsu","Genjutsu","Willpower"],
            "One Piece":["Willpower","Instinct","Strength","Agility","Endurance"],
            "Hunter x Hunter":["Aura Control","Willpower","Agility","Strength"],
            "Bleach":["Reiatsu Control","Zanjutsu","Kido","Hakuda","Hoho","Willpower"],
            "Jujutsu Kaisen":["Cursed Energy Control","Physical Ability","Cursed Energy Reserves","Soul Stability"],
            "Overgeared":["Dexterity","Strength","Intelligence","Constitution"],
            "Solo Max-Level Newbie":["Dexterity","Strength","Intelligence","Wisdom","Constitution"],
            "Reincarnated as a Slime":["Magicule Control","Skill Mastery","Instinct","Willpower"],
        }.get(world, [])
        for name in preferences:
            if name in stats:
                return ("stat", name)
        if skills:
            return ("skill", next(iter(skills)))
        return ("stat", next(iter(stats), "Strength"))

    def _offline_train(self, action_id, label=""):
        bucket = self._offline_day_bucket()
        bucket["training"] = int(bucket.get("training", 0) or 0) + 1
        kind, target = self._offline_training_target(action_id, label)
        # Same-day repetition remains useful, but quickly becomes inefficient.
        session = bucket["training"]
        effective = session <= 2
        gain = 1 if effective else 0
        if kind == "stat":
            current = float((self.state.get("stats") or {}).get(target, 0) or 0)
            marks = self._offline_root().setdefault("training_marks", {})
            marks[target] = float(marks.get(target, 0) or 0) + (1.0 if effective else .35)
            raised = 0
            threshold = max(2.5, 3.5 + current / 45.0)
            if marks[target] >= threshold:
                marks[target] -= threshold
                self.state.setdefault("stats", {})[target] = current + 1
                raised = 1
            detail = f"Focused on {target}. " + (f"{target} increased by {raised}." if raised else "Progress accumulated toward the next lasting improvement.")
        else:
            self.state["skills"] = normalize_skill_map(self.state.get("skills", {}))
            row = self.state["skills"].setdefault(target, {"description":f"Established practice in {target}."})
            row["mastery"] = min(100, int(row.get("mastery", row.get("level", row.get("bonus", 0))) or 0) + gain)
            row["bonus"] = max(int(row.get("bonus", 0) or 0), int(row["mastery"] / 4))
            detail = f"Practiced {target}. Mastery is now {row['mastery']}."
        self.state.setdefault("training_log", []).append({"turn":self.state.get("turn"), "canon_day":self.state.get("canon_day"), "focus":target, "effective":effective})
        self.state["training_log"] = self.state["training_log"][-160:]
        self._offline_advance_time(90, f"Train {target}")
        if not effective:
            detail += " Additional same-day repetition has sharply diminishing returns; varied activity or rest will help more."
        self._offline_append("TRAINING", detail, "growth")
        return detail

    def _offline_relationship(self, action_id, person, advance_time=True):
        if not person:
            people = _known_people(self.state)
            person = people[0] if people else "Local acquaintance"
        person = _clean(person, 120)
        bucket = self._offline_day_bucket()
        count = int(bucket["people"].get(person, 0) or 0)
        bucket["people"][person] = count + 1
        contacts = self.state.setdefault("contacts", {})
        row = contacts.setdefault(person, {})
        memory = self.state.setdefault("npc_memories", {}).setdefault(person, {})
        before = float(row.get("relationship", memory.get("relationship", memory.get("affinity", 0))) or 0)
        kind = action_id.split(":",1)[0]
        base = {"talk":1, "spend":3, "advice":1, "help":4, "train":2, "gift":3, "protect":2, "spar":1}.get(kind, 1)
        gain = base if count == 0 else max(0, base - 2*count)
        score = max(-100, min(100, before + gain))
        row["relationship"] = score
        memory["relationship"] = score
        memory["last_known_location"] = memory.get("last_known_location") or self.state.get("location")
        if advance_time:
            self._offline_advance_time(45 if kind in {"talk","advice"} else 90, f"{kind} with {person}")
        detail = f"You spend time with {person}. Relationship: {round(before)} → {round(score)}."
        if gain <= 0:
            detail += " More repeated attention today would feel forced; meaningful growth now needs time or a real shared event."
        self._offline_append("RELATIONSHIP", detail, "social")
        return detail

    def _offline_travel(self, destination):
        destination = _clean(destination, 160)
        locations = _map_locations(self.state)
        if destination not in locations:
            raise ValueError("That destination has not been established on this world's map yet.")
        if destination == self.state.get("location"):
            return f"You are already in {destination}."
        origin = self.state.get("location")
        self.state["location"] = destination
        if destination not in self.state.setdefault("discovered_locations", []):
            self.state["discovered_locations"].append(destination)
        self.state.setdefault("travel_history", []).append({"from":origin, "to":destination, "destination":destination, "canon_day":self.state.get("canon_day"), "turn":self.state.get("turn")})
        self.state["travel_history"] = self.state["travel_history"][-120:]
        self.state["scene_state"] = {"location":destination, "turn":int(self.state.get("turn",0) or 0), "present":[], "current_objective":"Explore the new location"}
        self._offline_advance_time(180, f"Travel from {origin} to {destination}")
        detail = f"You travel from {origin} to {destination}. The Atlas and Chronicle now reflect your new location."
        self._offline_append("TRAVEL", detail, "location")
        return detail

    def _offline_generate_board(self):
        root = self._offline_root(); bucket = self._offline_day_bucket(); day = int(self.state.get("canon_day", 0) or 0)
        if root.get("mission_board_day") == day and root.get("mission_board"):
            return root["mission_board"], False
        if int(bucket.get("board_refreshes", 0) or 0) >= 1 and root.get("mission_board"):
            return root["mission_board"], False
        bucket["board_refreshes"] = int(bucket.get("board_refreshes", 0) or 0) + 1
        world = self.state.get("world", "Custom World")
        ex = WORLD_EXPANSIONS.get(world, WORLD_EXPANSIONS["Custom World"])
        locations = [x for x in _map_locations(self.state) if x != self.state.get("location")] or [self.state.get("location")]
        encounters = ex.get("encounters", []) or [OFFLINE_WORLD["Custom World"]["enemy"]]
        loot = ex.get("loot", []) or ["useful supplies"]
        training = ex.get("training", []) or ["Field Training"]
        giver_pool = _known_people(self.state)
        offers = []
        for i in range(3):
            seed = _stable_int(self.state.get("campaign_id"), day, world, i)
            kind = MISSION_KINDS[seed % len(MISSION_KINDS)]
            destination = locations[(seed // 7) % len(locations)]
            enemy = encounters[(seed // 13) % len(encounters)]
            item = loot[(seed // 19) % len(loot)]
            train = training[(seed // 23) % len(training)]
            giver = giver_pool[(seed // 29) % len(giver_pool)] if giver_pool else OFFLINE_WORLD.get(world, OFFLINE_WORLD["Custom World"])["authority"]
            title_map = {
                "patrol":f"Patrol: {destination}", "investigate":f"Investigate trouble near {destination}",
                "retrieve":f"Recover {item}", "escort":f"Escort a contact to {destination}",
                "training":f"Training Assignment: {train}", "hunt":f"Hunt: {enemy}", "delivery":f"Deliver supplies to {destination}",
            }
            objective_map = {
                "patrol":f"Complete two patrol beats around {destination}.", "investigate":f"Find two credible clues around {destination}.",
                "retrieve":f"Secure the requested {item} and return safely.", "escort":f"Reach {destination} while keeping the client safe.",
                "training":f"Complete two focused sessions of {train}.", "hunt":f"Find and defeat {enemy}.", "delivery":f"Reach {destination} with the supplies intact.",
            }
            qid = hashlib.sha1(f"{self.state.get('campaign_id')}|{day}|{i}|{kind}".encode()).hexdigest()[:12]
            offers.append({"id":qid, "name":title_map[kind], "kind":kind, "giver":giver, "destination":destination, "target":enemy if kind=="hunt" else item if kind=="retrieve" else train if kind=="training" else "", "objective":objective_map[kind], "reward":35 + (seed % 46), "expires_day":day+3})
        root["mission_board"] = offers
        root["mission_board_day"] = day
        return offers, True

    def _offline_accept_mission(self, qid):
        offers = self._offline_root().get("mission_board", [])
        offer = next((x for x in offers if isinstance(x, dict) and x.get("id") == qid), None)
        if not offer:
            raise ValueError("That opportunity is no longer available.")
        if any((q.get("offline_data") or {}).get("id") == qid for q in self.state.get("quests", []) if isinstance(q, dict)):
            return "That mission is already active."
        objective = {"id":"offline-main", "text":offer["objective"], "status":"active", "optional":False, "progress":0}
        quest = {"name":offer["name"], "status":"Active", "giver":offer["giver"], "explanation":offer["objective"], "objectives":[objective], "clear_conditions":[offer["objective"]], "next_hint":offer["objective"], "rewards":[f"Standing +{max(1,offer['reward']//20)}", f"Progress reward {offer['reward']}"], "locations":[offer["destination"]], "offline_data":{**copy.deepcopy(offer), "progress":0, "stage":"active"}}
        self.state.setdefault("quests", []).append(quest)
        normalize_quest_state_machine(self.state)
        self._offline_root()["mission_board"] = [x for x in offers if x.get("id") != qid]
        detail = f"Accepted {offer['name']} from {offer['giver']}. {offer['objective']}"
        self._offline_append("MISSION ACCEPTED", detail, "quest")
        return detail

    def _offline_complete_quest(self, quest):
        data = quest.get("offline_data") or {}
        quest["status"] = "Completed"
        for obj in quest.get("objectives", []):
            if isinstance(obj, dict) and not obj.get("optional"):
                obj.update(status="complete", progress=100)
        world = self.state.get("world")
        reward = int(data.get("reward", 40) or 40)
        if uses_xp_for(world):
            self.state["xp"] = int(self.state.get("xp", 0) or 0) + reward
            # Reuse Worldwalker's literal-level structure without runaway jumps.
            while int(self.state.get("xp",0)) >= int(self.state.get("xp_next",100) or 100):
                self.state["xp"] -= int(self.state.get("xp_next",100) or 100)
                self.state["level"] = int(self.state.get("level",1) or 1) + 1
                self.state["xp_next"] = round(int(self.state.get("xp_next",100) or 100) * 1.18 + 25)
                self._offline_append("LEVEL UP", f"Level {self.state['level']} reached through completed objectives.", "growth")
        else:
            faction = data.get("giver")
            if faction in (self.state.get("reputation") or {}):
                self.state["reputation"][faction] = int(self.state["reputation"].get(faction,0) or 0) + max(1, reward//25)
        # Reuse Worldwalker's normal archive behavior so completed offline
        # missions leave the active list and appear exactly once in history.
        data["archived"] = True
        self.archive_finished_quests()
        self._offline_append("MISSION COMPLETE", f"{quest.get('name','Mission')} completed. The result is recorded in mission history.", "quest")
        return True

    def offline_sync_combat_missions(self):
        """Recognize a finished local/tactical fight as mission progress once."""
        root = self._offline_root()
        last = self.state.get("last_combat") if isinstance(self.state.get("last_combat"), dict) else {}
        if not last:
            return []
        marker = _clean(last.get("id") or last.get("ended_at") or f"{last.get('outcome')}|{last.get('enemy')}|{last.get('rounds')}|{self.state.get('turn')}", 240)
        if not marker or marker == root.get("last_combat_sync"):
            return []
        outcome = str(last.get("outcome") or "").lower()
        won = any(word in outcome for word in ("victory", "won", "defeated", "win")) or last.get("victory") is True
        if not won:
            root["last_combat_sync"] = marker
            return []
        completed = []
        for quest in self.state.get("quests", []):
            if not isinstance(quest, dict) or str(quest.get("status","")).lower() in {"completed","complete","failed"}:
                continue
            data = quest.get("offline_data") if isinstance(quest.get("offline_data"), dict) else None
            if not data or data.get("kind") != "hunt" or data.get("combat_cleared"):
                continue
            data["combat_cleared"] = True; data["progress"] = 100
            for obj in quest.get("objectives", []):
                if isinstance(obj, dict) and not obj.get("optional"):
                    obj.update(progress=100, status="complete")
            self._offline_complete_quest(quest)
            completed.append(quest.get("name"))
            break
        root["last_combat_sync"] = marker
        if completed:
            self.autosave()
        return completed

    def _offline_start_combat(self, target="", non_lethal=False, mission_id=""):
        if self.combat_active():
            return "A fight is already active."
        world = self.state.get("world", "Custom World")
        ex = WORLD_EXPANSIONS.get(world, WORLD_EXPANSIONS["Custom World"])
        enemy_name = _clean(target) or str((ex.get("encounters") or [OFFLINE_WORLD["Custom World"]["enemy"]])[0])
        avg = sum(float(v or 0) for v in (self.state.get("stats") or {}).values()) / max(1, len(self.state.get("stats") or {}))
        power = max(18, min(180, int(avg * (0.8 if non_lethal else 1.05) + 18)))
        hp = max(35, power * 2)
        enemy = {"name":enemy_name, "role":"sparring partner" if non_lethal else "local threat", "power":power, "hp":hp, "hp_max":hp, "alive":True}
        self.state["combat"] = {"active":True, "enemy":enemy, "opponents":[copy.deepcopy(enemy)], "round":1, "log":[], "non_lethal":bool(non_lethal), "tactical_enabled": world in {"Naruto","One Piece","Bleach"}, "offline_generated":True, "offline_mission_id":mission_id}
        self.state["encounter_state"] = {"version":1, "phase":"combat", "negotiation_possible":not non_lethal, "violence_committed":not non_lethal}
        self.ensure_combat_numbers()
        detail = f"{'A spar' if non_lethal else 'Combat'} begins against {enemy_name}. Use Worldwalker's existing {'tactical battlefield' if world in {'Naruto','One Piece','Bleach'} else 'combat controls'} to resolve it."
        self._offline_append("COMBAT", detail, "combat")
        return detail

    def _offline_work_quest(self, quest):
        data = quest.get("offline_data") if isinstance(quest.get("offline_data"), dict) else None
        if not data:
            # Existing online saves can enter Offline Mode without losing their
            # current objective. Convert the established quest text into a
            # conservative local progress contract: no new target, reward or
            # lore fact is invented; the player simply works the objective
            # already present in the save through bounded checks.
            objectives = [obj for obj in (quest.get("objectives") or []) if isinstance(obj, dict) and not obj.get("optional")]
            active = next((obj for obj in objectives if str(obj.get("status", "active")).lower() not in {"complete", "completed", "failed"}), objectives[0] if objectives else None)
            existing_progress = int(active.get("progress", 0) or 0) if active else int(quest.get("progress", 0) or 0)
            objective_text = _clean((active or {}).get("text") or quest.get("next_hint") or quest.get("description") or quest.get("name") or "Current objective", 320)
            data = {
                "id": "legacy-" + hashlib.sha1(f"{self.state.get('campaign_id')}|{quest.get('name')}".encode()).hexdigest()[:10],
                "kind": "legacy", "target": objective_text, "destination": "",
                "progress": max(0, min(95, existing_progress)), "reward": 0,
                "converted_from_story_quest": True,
            }
            quest["offline_data"] = data
            quest["next_hint"] = f"Offline objective: {objective_text}"
        kind = data.get("kind"); destination = data.get("destination")
        progress = int(data.get("progress", 0) or 0)
        if kind == "hunt":
            if data.get("combat_cleared"):
                return "The hunt has already been resolved."
            return self._offline_start_combat(data.get("target"), False, data.get("id",""))
        if kind in {"escort", "delivery"} and destination and self.state.get("location") != destination:
            self._offline_travel(destination)
            progress = 100
        elif kind == "retrieve":
            check = self._offline_roll(f"quest:{data.get('id')}", difficulty=50 + progress//10)
            progress += 55 if check["success"] else 25
            self._offline_advance_time(100, quest.get("name"))
            self._offline_append("MISSION PROGRESS", f"You search for {data.get('target')}. {'You secure a strong lead.' if check['success'] else 'The search costs time but narrows the possibilities.'}", "quest")
        elif kind == "investigate":
            check = self._offline_roll(f"quest:{data.get('id')}", stat_names=("Intelligence","Wisdom","Cunning","Instinct"), difficulty=48 + progress//12)
            progress += 50 if check["success"] else 24
            self._offline_advance_time(90, quest.get("name"))
            self._offline_append("INVESTIGATION", "A credible clue is added to the case." if check["success"] else "A false lead is eliminated; the case still advances slowly.", "quest")
        elif kind == "training":
            self._offline_train(f"training:{data.get('target','')}", str(data.get("target") or ""))
            progress += 50
        elif kind == "patrol":
            check = self._offline_roll(f"quest:{data.get('id')}", stat_names=("Instinct","Wisdom","Dexterity","Agility"), difficulty=45)
            progress += 50 if check["success"] else 30
            self._offline_advance_time(80, quest.get("name"))
            self._offline_append("PATROL", "The patrol stays alert and produces useful local intelligence." if check["success"] else "The route is quiet, but the patrol still satisfies part of the assignment.", "quest")
        elif kind == "legacy":
            check = self._offline_roll(f"quest:{data.get('id')}", difficulty=50 + progress//20)
            progress += 38 if check["success"] else 16
            self._offline_advance_time(90, quest.get("name"))
            target = _clean(data.get("target") or quest.get("name"), 240)
            note = (f"You make concrete progress on the established objective: {target}." if check["success"]
                    else f"You spend time on the established objective — {target} — and learn what is still blocking it.")
            self._offline_append("OBJECTIVE PROGRESS", note, "quest")
        else:
            progress += 50
            self._offline_advance_time(90, quest.get("name"))
        data["progress"] = min(100, progress)
        for obj in quest.get("objectives", []):
            if isinstance(obj, dict) and not obj.get("optional"):
                obj["progress"] = data["progress"]
                if data["progress"] >= 100:
                    obj["status"] = "complete"
        if data["progress"] >= 100:
            self._offline_complete_quest(quest)
            return f"{quest.get('name')} is complete."
        quest["next_hint"] = f"Continue {quest.get('name')} ({data['progress']}%)."
        return f"{quest.get('name')} is now {data['progress']}% complete."

    def _offline_storylet(self, source_action):
        bucket = self._offline_day_bucket(); root = self._offline_root()
        if int(bucket.get("storylets",0) or 0) >= 2 or root.get("pending_event"):
            return None
        # Roughly one in four substantive activities. Deterministic per campaign/action.
        roll = _stable_int(self.state.get("campaign_id"), self.state.get("turn"), source_action, len(root.get("activity_history",[])), mod=100)
        if roll >= 24:
            return None
        world = self.state.get("world", "Custom World"); people = _known_people(self.state); person = people[roll % len(people)] if people else "a local contact"
        templates = {
            "Naruto": ("A mission report conflicts with what people in the village are saying.", ["Investigate the discrepancy", "Report it through official channels", "Leave it alone for now"]),
            "One Piece": ("A fresh rumor spreads through the port about an opportunity nobody fully trusts.", ["Chase the rumor", "Ask the crew or locals first", "Ignore the bait"]),
            "Hunter x Hunter": ("A contact offers information that could be valuable, but the source is uncertain.", ["Verify the information", "Trade for the full lead", "Decline"]),
            "Bleach": ("A spiritual disturbance appears on the edge of normal patrol reports.", ["Investigate personally", "Notify the division", "Observe from a distance"]),
            "Jujutsu Kaisen": ("A minor curse report contains details that do not fit the expected pattern.", ["Inspect the site", "Research the pattern", "Escalate it to a supervisor"]),
            "Overgeared": ("An NPC mentions an unusual opportunity that may have hidden conditions.", ["Follow the NPC lead", "Research the requirement", "Focus on current priorities"]),
            "Solo Max-Level Newbie": ("A System-adjacent anomaly suggests there may be an alternate condition nearby.", ["Test the anomaly", "Study it first", "Avoid wasting resources"]),
            "Reincarnated as a Slime": ("A local concern reaches you before it becomes a larger problem.", ["Handle it personally", "Delegate to a trusted person", "Gather more information"]),
            "Custom World": ("Something small but potentially important changes around your current location.", ["Investigate", "Ask someone you trust", "Ignore it"]),
        }
        prompt, options = templates.get(world, templates["Custom World"])
        eid = hashlib.sha1(f"{self.state.get('campaign_id')}|{self.state.get('turn')}|{source_action}".encode()).hexdigest()[:12]
        event = {"id":eid, "title":"A New Development", "prompt":prompt, "person":person, "options":[{"id":f"{eid}:{i}", "label":label} for i,label in enumerate(options)]}
        root["pending_event"] = event; bucket["storylets"] = int(bucket.get("storylets",0) or 0)+1
        return copy.deepcopy(event)

    def _offline_resolve_canon_event(self, stance):
        title = _clean(self.state.get("active_canon_event") or "", 240)
        if not title:
            raise ValueError("No major event is currently active.")
        context = _clean(self.state.get("interruption_context") or self.state.get("active_event_context") or "", 420)
        labels = {
            "engage": "Get involved directly",
            "protect": "Protect people and limit harm",
            "observe": "Stay out of the center and observe",
        }
        if stance not in labels:
            raise ValueError("Choose how you want to approach the active event.")
        difficulty = {"engage": 58, "protect": 52, "observe": 42}[stance]
        check = self._offline_roll(f"canon:{title}:{stance}", difficulty=difficulty)
        if stance == "engage":
            summary = (f"You intervene directly in **{title}** and your actions materially help your side of the immediate situation." if check["success"]
                       else f"You intervene directly in **{title}**, but resistance forces you to withdraw from the center after a difficult exchange.")
        elif stance == "protect":
            summary = (f"During **{title}**, you focus on protecting people, stabilizing the immediate area and preventing avoidable harm." if check["success"]
                       else f"During **{title}**, you try to protect people and reduce harm; the situation remains chaotic, but your effort still limits some consequences.")
        else:
            summary = f"You avoid taking a central role in **{title}** and observe only what your current location and access would plausibly reveal."
        if context:
            summary += f" The event had been framed by: {context}"
        self.state["active_canon_event"] = ""
        self.state["canon_event_engagement_count"] = 0
        self.state["active_event_context"] = ""
        self.state["active_event_prompt"] = ""
        try:
            if not self.combat_active():
                self.clear_danger_scenario()
        except Exception:
            pass
        self._offline_append("EVENT CONCLUDED", summary, "canon_event")
        return summary

    def offline_event_choice(self, event_id, option_id):
        root = self._offline_root(); event = root.get("pending_event")
        if not isinstance(event, dict) or event.get("id") != event_id:
            raise ValueError("That development is no longer waiting for a decision.")
        option = next((x for x in event.get("options",[]) if x.get("id") == option_id), None)
        if not option:
            raise ValueError("Choose one of the available responses.")
        index = event.get("options",[]).index(option)
        check = self._offline_roll(option_id, difficulty=48 + index*4)
        result = option["label"] + (" works out cleanly." if check["success"] else " creates a complication, but gives you useful information.")
        if index == 0 and check["success"]:
            self.state.setdefault("achievements", []).append({"name":"Followed a developing lead", "turn":self.state.get("turn")})
        elif index == 1:
            person = event.get("person")
            if person and person != "a local contact":
                self._offline_relationship("talk", person, advance_time=False)
        self._offline_advance_time(45, option["label"])
        self._offline_append("DEVELOPMENT", result, "world")
        root.setdefault("storylet_history", []).append({**copy.deepcopy(event), "choice":option["label"], "success":check["success"], "canon_day":self.state.get("canon_day")})
        root["storylet_history"] = root["storylet_history"][-80:]
        root["pending_event"] = None
        self.state["turn"] = int(self.state.get("turn",0) or 0)+1
        self.autosave()
        return {"status":"ok", "message":result, "state":self.public_state(), "story":self._flush_story(), "event":None, "offline":True}

    def offline_action(self, action_id, label="", person="", duration="moment"):
        if not self.campaign_active:
            raise ValueError("Start or load a campaign first.")
        self.offline_sync_combat_missions()
        if self.combat_active() and not str(action_id).startswith("combat-current"):
            raise ValueError("Finish the active combat before starting another world activity.")
        action_id = _clean(action_id, 220); label = _clean(label, 220); person = _clean(person, 120)
        before_state = copy.deepcopy(self.state)
        root = self._offline_root(); message = ""

        if action_id.startswith("offline-canon:"):
            message = self._offline_resolve_canon_event(action_id.split(":",1)[1])
        elif action_id.startswith("offline-accept:"):
            message = self._offline_accept_mission(action_id.split(":",1)[1])
        elif action_id.startswith("travel:"):
            message = self._offline_travel(action_id.split(":",1)[1])
        elif action_id.startswith("quest:"):
            name = action_id.split(":",1)[1]
            quest = next((q for q in self.state.get("quests",[]) if isinstance(q,dict) and q.get("name") == name and str(q.get("status","")).lower() not in {"completed","complete","failed","cancelled","abandoned"}), None)
            if not quest:
                raise ValueError("That active mission could not be found.")
            message = self._offline_work_quest(quest)
        elif action_id in {"missions-work","naruto-mission","hxh-work","jjk-mission","og-opportunity"}:
            offers, refreshed = self._offline_generate_board()
            message = ("New opportunities are available." if refreshed else "Today's available opportunities are unchanged.") + f" {len(offers)} option(s) are on the Activities list."
            self._offline_append("OPPORTUNITIES", message, "quest")
            self._offline_advance_time(20, "Review opportunities")
        elif action_id.startswith(("skill:","training-")) or action_id in {"naruto-chakra","hxh-nen","bleach-zan","bleach-kido","jjk-technique","og-class","solo-synergy","slime-analysis"}:
            message = self._offline_train(action_id, label)
        elif action_id.startswith(("talk:","spend:","advice:","help:","train:","gift:","protect:","spar:")):
            kind, name = action_id.split(":",1)
            if kind == "spar":
                message = self._offline_start_combat(name, True)
            else:
                message = self._offline_relationship(action_id, name)
        elif action_id.startswith("person:"):
            raise ValueError("Choose how you want to interact with that person.")
        elif action_id in {"personal-rest","personal-sleep","personal-meal","personal-relax","personal-recover"}:
            hpmax = int(self.state.get("hp_max",100) or 100); rmax = int(self.state.get("resource_max",100) or 100)
            self.state["hp"] = min(hpmax, int(self.state.get("hp",hpmax) or 0) + max(8, hpmax//3))
            self.state["resource"] = min(rmax, int(self.state.get("resource",rmax) or 0) + max(8, rmax//2))
            minutes = 480 if action_id == "personal-sleep" else 90
            self._offline_advance_time(minutes, label or action_id)
            message = "You recover naturally. Health and your primary resource are restored toward their current maximums."
            self._offline_append("RECOVERY", message, "growth")
        elif action_id == "personal-maintain":
            self._offline_advance_time(45, "Maintain equipment"); message="You clean, organize and maintain your established equipment without inventing new items."; self._offline_append("EQUIPMENT",message,"system")
        elif action_id in {"personal-reflect","training-study","missions-investigate","travel-explore"}:
            check = self._offline_roll(action_id, stat_names=("Intelligence","Wisdom","Instinct","Cunning"), difficulty=44)
            self._offline_advance_time(75, label or action_id)
            message = "You uncover a useful local detail and clarify a next step." if check["success"] else "You rule out an unhelpful lead and better understand what remains uncertain."
            self._offline_append("DISCOVERY", message, "world")
        elif action_id in {"combat-patrol","combat-hunt"}:
            target = OFFLINE_WORLD.get(self.state.get("world"),OFFLINE_WORLD["Custom World"])["enemy"]
            message = self._offline_start_combat(target, False)
        elif action_id == "combat-spar":
            message = self._offline_start_combat("Willing sparring partner", True)
        elif action_id == "combat-current":
            message = "Continue with the existing Worldwalker combat controls."
        elif action_id.startswith("group-"):
            members = (self.state.get("_organization_roster") or {}).get("members") or []
            if not members and not self.state.get("organizations"):
                raise ValueError("You do not currently have an established group to manage.")
            self._offline_advance_time(60, label or action_id)
            message = "The organization reviews current duties, resources and priorities. Existing authority and membership are preserved."
            self._offline_append("ORGANIZATION", message, "world")
        elif action_id in {"people-socialize","people-mentor","people-recruit","people-message"}:
            people = _known_people(self.state)
            if not people:
                self._offline_advance_time(45, label or action_id); message="You spend time among the people in the current area and make ordinary social contact."; self._offline_append("SOCIAL",message,"social")
            else:
                message = self._offline_relationship("talk", people[0])
        else:
            # World-specific activities without a dedicated mechanic still use a grounded local check.
            check = self._offline_roll(action_id, difficulty=46)
            self._offline_advance_time(60, label or action_id)
            message = (f"{label or 'The activity'} produces a useful result grounded in your current situation." if check["success"] else f"{label or 'The activity'} costs time and reveals a limitation or complication without inventing a new fact.")
            self._offline_append("ACTIVITY", message, "world")

        # Shared state maintenance after every substantive offline action.
        self.state["turn"] = int(self.state.get("turn",0) or 0) + 1
        try:
            normalize_world_progression(self.state)
            normalize_quest_state_machine(self.state)
            advance_world_activity(self.state, before_state, actions=[label or action_id], narrative=message, events=[], elapsed_minutes=0)
        except Exception:
            pass
        root.setdefault("activity_history", []).append({"id":action_id, "label":label, "person":person, "canon_day":self.state.get("canon_day"), "turn":self.state.get("turn"), "time":datetime.now().isoformat(timespec="seconds")})
        root["activity_history"] = root["activity_history"][-180:]
        event = None if self.combat_active() or action_id.startswith("offline-canon:") else self._offline_storylet(action_id)
        self.state["suggested_actions"] = self.offline_suggestions()
        self.autosave()
        return {"status":"ok", "message":message, "state":self.public_state(), "story":self._flush_story(), "event":event, "offline":True, "combat_active":self.combat_active()}

    def offline_locations(self):
        return _map_locations(self.state)

    def offline_suggestions(self):
        suggestions = []
        active = [q for q in self.state.get("quests",[]) if isinstance(q,dict) and str(q.get("status","")).lower() not in {"completed","complete","failed","cancelled","abandoned"}]
        if active:
            suggestions.append(f"Work on {active[0].get('name','your current assignment')}")
        else:
            suggestions.append("Review available opportunities")
        skills = list((self.state.get("skills") or {}).keys())
        if skills:
            suggestions.append(f"Practice {skills[0]}")
        people = _known_people(self.state)
        suggestions.append(f"Spend time with {people[0]}" if people else "Explore the current area")
        return suggestions[:3]
