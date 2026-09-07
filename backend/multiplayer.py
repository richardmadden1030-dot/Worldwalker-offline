"""Durable two-player rooms for the private friend server.

The campaign engine remains authoritative for the shared world.  This module
owns membership, per-player plans/readiness, character snapshots, heartbeats,
and the ten-minute round clock.  Keeping those facts in SQLite means a browser
refresh, phone sleep, or server restart cannot reset the turn.
"""
from __future__ import annotations

import copy
import json
import re
import secrets
import sqlite3
import string
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROUND_SECONDS = 10 * 60
CONNECTED_SECONDS = 45
MAX_PLAYERS = 2
CHRONICLE_LIMIT = 600


def _now():
    return datetime.now(timezone.utc)


def _stamp(value=None):
    return (value or _now()).isoformat(timespec="seconds")


def _parse(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return datetime.fromtimestamp(0, timezone.utc)


CHARACTER_FIELDS = {
    "name", "age", "race", "origin", "archetype", "position", "background",
    "appearance", "appearance_desc", "location", "sublocation", "status",
    "conditions", "current_activity", "stats", "hidden_stats", "skills",
    "titles", "inventory", "equipment", "special", "class_profile", "hp",
    "hp_max", "resource", "resource_max", "level", "xp", "xp_next", "alive",
    "portrait_identity", "portrait_traits", "growth_profile", "affiliations",
}


def character_from_state(state, name=""):
    character = {key: copy.deepcopy(state.get(key)) for key in CHARACTER_FIELDS if key in state}
    if name:
        character["name"] = str(name).strip()[:80]
    return character


def new_friend_character(state, name, background=""):
    """Create a conservative world-valid second protagonist without an AI call."""
    character = character_from_state(state, name or "Second Traveler")
    character["background"] = str(background or "A newly arrived ally whose history will be established through play.")[:3000]
    character["appearance"] = ""
    character["appearance_desc"] = ""
    character["position"] = "Player Character"
    character["current_activity"] = "Joining the shared journey"
    # The main game models visible status effects as a list.  Keeping the
    # joined character on that contract prevents renderers from treating a
    # plain string as a collection of status entries.
    character["status"] = ["Normal"]
    character["conditions"] = []
    character["titles"] = []
    character["inventory"] = []
    character["equipment"] = {}
    character["affiliations"] = []
    # Keep the world's stat vocabulary and sensible starting scale, but do not
    # clone the original hero's earned end-game power into a newly joined PC.
    source_stats = state.get("stats", {}) if isinstance(state.get("stats"), dict) else {}
    character["stats"] = {key: max(1, min(60, int(value or 1))) for key, value in source_stats.items()}
    character["skills"] = {}
    character["special"] = {}
    character["class_profile"] = {}
    max_hp = max(20, min(300, int(state.get("hp_max", 100) or 100)))
    max_resource = max(20, min(300, int(state.get("resource_max", 100) or 100)))
    character.update({"hp": max_hp, "hp_max": max_hp, "resource": max_resource,
                      "resource_max": max_resource, "level": 1, "xp": 0,
                      "xp_next": 100, "alive": True})
    character.pop("portrait_identity", None)
    character.pop("portrait_traits", None)
    return character


def player_view(shared_state, character, queued_actions):
    view = copy.deepcopy(shared_state)
    for key, value in (character or {}).items():
        if key in CHARACTER_FIELDS:
            view[key] = copy.deepcopy(value)
    if isinstance(view.get("status"), str):
        view["status"] = [view["status"]] if view["status"] else []
    view["queued_actions"] = list(queued_actions or [])
    return view


def apply_character_update(character, patch):
    clean = copy.deepcopy(character or {})
    if not isinstance(patch, dict):
        return clean
    for key, value in patch.items():
        if key not in CHARACTER_FIELDS:
            continue
        if key in {"hp", "hp_max", "resource", "resource_max", "level", "xp", "xp_next"}:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[key] = int(value)
        elif key in {"stats", "hidden_stats", "skills", "equipment", "special", "class_profile", "portrait_identity", "growth_profile"}:
            if isinstance(value, dict):
                clean[key] = copy.deepcopy(value)
        elif key in {"titles", "inventory", "conditions", "affiliations", "status"}:
            if isinstance(value, list):
                clean[key] = copy.deepcopy(value[:500])
        elif key == "alive":
            if isinstance(value, bool):
                clean[key] = value
        elif isinstance(value, (str, int, float)) or value is None:
            clean[key] = copy.deepcopy(value)
    clean["hp_max"] = max(1, int(clean.get("hp_max", 100) or 100))
    clean["resource_max"] = max(1, int(clean.get("resource_max", 100) or 100))
    clean["hp"] = max(0, min(clean["hp_max"], int(clean.get("hp", clean["hp_max"]) or 0)))
    clean["resource"] = max(0, min(clean["resource_max"], int(clean.get("resource", clean["resource_max"]) or 0)))
    return clean


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _same_place(left, right):
    """Conservative proximity check for two character/location records."""
    left_location, right_location = _norm(left.get("location")), _norm(right.get("location"))
    if not left_location or not right_location or left_location != right_location:
        return False
    left_sub, right_sub = _norm(left.get("sublocation")), _norm(right.get("sublocation"))
    return not left_sub or not right_sub or left_sub == right_sub


def _at_event(character, location="", sublocation=""):
    if not _norm(location):
        return False
    return _same_place(character, {"location": location, "sublocation": sublocation})


def _participant_records(participants, characters_after):
    records = {}
    for person in participants or []:
        user_id = str(person.get("user_id") or "")
        before = copy.deepcopy(person.get("character") or {})
        after = copy.deepcopy((characters_after or {}).get(user_id) or before)
        records[user_id] = {
            "user_id": user_id,
            "username": str(person.get("username") or ""),
            "name": str(after.get("name") or before.get("name") or person.get("username") or ""),
            "before": before, "after": after,
        }
    return records


def _actor_for(update, records):
    explicit = str(update.get("actor_user_id") or "")
    if explicit in records:
        return explicit
    actor_name = _norm(update.get("actor_character") or update.get("actor") or "")
    related = _norm(update.get("related_action") or "")
    narrative = _norm(update.get("narrative") or "")
    for user_id, record in records.items():
        name = _norm(record["name"])
        username = _norm(record["username"])
        if actor_name and actor_name in {name, username}:
            return user_id
        if name and (related.startswith(name + " ") or related == name or narrative.startswith(name + " ")):
            return user_id
    return ""


def _co_located(actor_id, records):
    if actor_id not in records:
        return set()
    actor = records[actor_id]["after"]
    return {user_id for user_id, record in records.items() if _same_place(actor, record["after"])}


def _event_audience(update, records):
    """Resolve who can know one narrated update without leaking omniscience.

    AI-supplied audience IDs are authoritative.  The remaining rules are a
    deterministic safety net for older/local models that omit the new fields.
    """
    all_users = set(records)
    explicit = update.get("audience_user_ids")
    if isinstance(explicit, list):
        audience = {str(user_id) for user_id in explicit if str(user_id) in records}
        if audience or explicit == []:
            return audience
    scope = _norm(update.get("information_scope") or update.get("visibility"))
    channel = _norm(update.get("delivery_channel") or update.get("channel"))
    if scope in {"global", "shared", "broadcast", "public"} or channel in {"broadcast", "world broadcast", "system broadcast"}:
        return all_users
    actor_id = _actor_for(update, records)
    if scope in {"private", "personal"} and actor_id:
        return {actor_id}
    location = update.get("location") or update.get("event_location") or ""
    sublocation = update.get("sublocation") or update.get("event_sublocation") or ""
    if _norm(location):
        present = {
            user_id for user_id, record in records.items()
            if _at_event(record["before"], location, sublocation) or _at_event(record["after"], location, sublocation)
        }
        if present:
            return present
    if actor_id:
        return {actor_id} if scope in {"private", "personal"} else (_co_located(actor_id, records) or {actor_id})
    # Explicit report/message channels must name recipients; an omitted list
    # reveals nothing rather than broadcasting a private letter by accident.
    if channel in {"message", "letter", "conversation", "witness", "ability", "research"}:
        return set()
    # Backward compatibility for models predating visibility metadata: broad
    # world/canon cards remain shared unless they supplied a concrete place.
    if _norm(update.get("type")) in {"world event", "canon event"}:
        return all_users
    return all_users


def _heading(text):
    match = re.match(r"^\[([^\]]+)\]", str(text or "").strip())
    return _norm(match.group(1)) if match else ""


def _scope_label(update, audience, all_users):
    scope = _norm(update.get("information_scope") or update.get("visibility"))
    channel = _norm(update.get("delivery_channel") or update.get("channel"))
    if scope in {"private", "personal", "local"}:
        return "local"
    if scope in {"global", "shared", "public"}:
        return "shared"
    if channel in {"message", "letter", "rumor", "report", "news", "broadcast", "research"} or scope in {"report", "rumor"}:
        return "reported"
    return "shared" if audience == all_users else "local"


def _entry_actor(entry, records):
    text = str(entry.get("text") or "")
    detail = str(entry.get("detail") or "") if isinstance(entry.get("detail"), str) else ""
    haystack = _norm(detail + " " + text)
    for user_id, record in records.items():
        name = _norm(record["name"])
        username = _norm(record["username"])
        if name and (haystack.startswith(name + " ") or f"action {name} " in haystack or _norm(text).startswith(name + " ")):
            return user_id
        if username and (haystack.startswith(username + " ") or f"action {username} " in haystack):
            return user_id
    return ""


def split_player_results(result, participants, characters_after, host_user_id=""):
    """Create one non-omniscient result/Chronicle payload per player."""
    records = _participant_records(participants, characters_after)
    all_users = set(records)
    if not records:
        return {}
    updates = [u for u in (result.get("updates") or []) if isinstance(u, dict)]
    audiences = [_event_audience(update, records) for update in updates]
    update_queues = {}
    for index, update in enumerate(updates):
        key = _norm(update.get("title") or update.get("type") or "update")
        update_queues.setdefault(key, []).append(index)
    story_by_user = {user_id: [] for user_id in records}
    story_audiences = []
    private_mechanical = re.compile(r"^(growth|training|xp|level|skill|class|title|stat|power|quest|agenda|breakthrough)")
    for raw_entry in (result.get("story") or []):
        if not isinstance(raw_entry, dict) or not str(raw_entry.get("text") or "").strip():
            continue
        entry = copy.deepcopy(raw_entry)
        key = _heading(entry.get("text"))
        linked_index = None
        if key and update_queues.get(key):
            linked_index = update_queues[key].pop(0)
        if linked_index is not None:
            update = updates[linked_index]
            audience = audiences[linked_index]
            scope_label = _scope_label(update, audience, all_users)
            source = str(update.get("delivery_channel") or update.get("channel") or "")
        else:
            actor_id = _entry_actor(entry, records)
            if actor_id:
                audience = _co_located(actor_id, records) or {actor_id}
                scope_label, source = "local", ""
            elif key and private_mechanical.match(key):
                audience = {str(host_user_id)} if str(host_user_id) in records else {next(iter(records))}
                scope_label, source = "local", ""
            else:
                audience, scope_label, source = all_users, "shared", ""
        story_audiences.append((entry, audience))
        for user_id in audience:
            if user_id not in story_by_user:
                continue
            visible = copy.deepcopy(entry)
            visible["multiplayer_scope"] = scope_label
            if source:
                visible["multiplayer_source"] = source
            story_by_user[user_id].append(visible)

    explicit_interrupt = result.get("interruption_user_ids")
    if isinstance(explicit_interrupt, list):
        interruption_audience = {str(user_id) for user_id in explicit_interrupt if str(user_id) in records}
    else:
        interruption_audience = set()
        for entry, audience in story_audiences:
            if entry.get("tag") in {"canon_event", "danger"}:
                interruption_audience.update(audience)
        if result.get("interrupted") and not interruption_audience:
            interruption_audience = all_users

    per_player = {}
    for user_id in records:
        compact = {key: copy.deepcopy(result.get(key)) for key in (
            "status", "elapsed", "danger_notice_required", "goal_status", "validation",
            "continuity_warnings", "integrity_report") if key in result}
        compact["story"] = story_by_user[user_id]
        compact["updates"] = [copy.deepcopy(update) for update, audience in zip(updates, audiences) if user_id in audience]
        compact["rolls"] = []
        for roll in result.get("rolls") or []:
            actor_id = _entry_actor({"text": str(roll.get("action") or roll.get("reason") or "")}, records) if isinstance(roll, dict) else ""
            if not actor_id or user_id in (_co_located(actor_id, records) or {actor_id}):
                compact["rolls"].append(copy.deepcopy(roll))
        compact["notifications"] = []
        for note in result.get("notifications") or []:
            note_audience = note.get("audience_user_ids") if isinstance(note, dict) else None
            if not isinstance(note_audience, list) or user_id in {str(value) for value in note_audience}:
                compact["notifications"].append(copy.deepcopy(note))
        involved = user_id in interruption_audience
        compact["interrupted"] = bool(result.get("interrupted") and involved)
        compact["interruption_kind"] = result.get("interruption_kind", "") if involved else ""
        compact["interruption_reason"] = result.get("interruption_reason", "") if involved else ""
        compact["intervention_prompt"] = result.get("intervention_prompt", "") if involved else ""
        compact["major_event_reached"] = bool(result.get("major_event_reached") and involved)
        compact["major_event_title"] = result.get("major_event_title", "") if involved else ""
        character = records[user_id]["after"]
        compact["died"] = bool(not character.get("alive", True) or int(character.get("hp", 1) or 0) <= 0)
        compact["narrative"] = "\n\n".join(
            str(entry.get("text") or "") for entry in story_by_user[user_id] if entry.get("tag") in {"narrative", "system", "canon_event"}
        )[-6000:]
        per_player[user_id] = compact
    return per_player


class MultiplayerStore:
    def __init__(self, account_store):
        self.accounts = account_store
        self.root = Path(account_store.root) / "multiplayer"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = account_store.db_path
        self._schema_lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._schema_lock, self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS multiplayer_rooms (
                    id TEXT PRIMARY KEY,
                    join_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    host_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    save_name TEXT NOT NULL DEFAULT 'shared_campaign',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    round_number INTEGER NOT NULL DEFAULT 1,
                    round_deadline TEXT NOT NULL,
                    time_amount INTEGER NOT NULL DEFAULT 1,
                    time_unit TEXT NOT NULL DEFAULT 'moment',
                    intensity TEXT NOT NULL DEFAULT 'normal',
                    resolving INTEGER NOT NULL DEFAULT 0,
                    last_result_round INTEGER NOT NULL DEFAULT 0,
                    last_result_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS multiplayer_members (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'player',
                    character_json TEXT NOT NULL DEFAULT '{}',
                    ready INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    joined_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id),
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS multiplayer_actions (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    action_index INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id, round_number, action_index),
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS multiplayer_results (
                    room_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(room_id, round_number, user_id),
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS multiplayer_chronicle (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    entry_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_multiplayer_active ON multiplayer_members(user_id, active);
                CREATE INDEX IF NOT EXISTS idx_multiplayer_deadline ON multiplayer_rooms(status, resolving, round_deadline);
                CREATE INDEX IF NOT EXISTS idx_multiplayer_chronicle_user ON multiplayer_chronicle(room_id,user_id,id);
            """)

    def room_root(self, room_id):
        if not str(room_id).replace("-", "").isalnum():
            raise ValueError("Invalid multiplayer room.")
        root = self.root / str(room_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _join_code(self, db):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(30):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not db.execute("SELECT 1 FROM multiplayer_rooms WHERE join_code=?", (code,)).fetchone():
                return code
        raise RuntimeError("Could not allocate a multiplayer invite code.")

    def create_room(self, user, bundle):
        state = bundle.get("state") if isinstance(bundle, dict) else None
        if not isinstance(state, dict):
            raise ValueError("Start, load, or import a campaign before creating multiplayer.")
        room_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as db:
            db.execute("UPDATE multiplayer_members SET active=0 WHERE user_id=?", (user["id"],))
            code = self._join_code(db)
            db.execute("""INSERT INTO multiplayer_rooms
                (id,join_code,host_user_id,title,created_at,round_deadline)
                VALUES(?,?,?,?,?,?)""",
                (room_id, code, user["id"], f"{state.get('name', 'Traveler')} · {state.get('world', 'World')}",
                 _stamp(now), _stamp(now + timedelta(seconds=ROUND_SECONDS))))
            db.execute("""INSERT INTO multiplayer_members
                (room_id,user_id,username,role,character_json,ready,active,joined_at,last_seen_at)
                VALUES(?,?,?,?,?,0,1,?,?)""",
                (room_id, user["id"], user["username"], "host",
                 json.dumps(character_from_state(state), ensure_ascii=False), _stamp(now), _stamp(now)))
        target = self.room_root(room_id) / "shared_campaign.json"
        clean_bundle = copy.deepcopy(bundle)
        clean_bundle["save_kind"] = "multiplayer"
        clean_bundle["multiplayer_room_id"] = room_id
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean_bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(target)
        return self.status(room_id, user["id"], heartbeat=False)

    def join_room(self, user, code, character_name="", background=""):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE join_code=? COLLATE NOCASE AND status='active'", (str(code or "").strip(),)).fetchone()
            if not room:
                raise ValueError("That multiplayer invite code is not active.")
            existing = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room["id"], user["id"])).fetchone()
            count = db.execute("SELECT COUNT(*) FROM multiplayer_members WHERE room_id=?", (room["id"],)).fetchone()[0]
            if not existing and count >= MAX_PLAYERS:
                raise ValueError("That campaign already has two players.")
            db.execute("UPDATE multiplayer_members SET active=0 WHERE user_id=?", (user["id"],))
            if existing:
                db.execute("UPDATE multiplayer_members SET active=1,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(now), room["id"], user["id"]))
            else:
                bundle = json.loads((self.room_root(room["id"]) / "shared_campaign.json").read_text(encoding="utf-8"))
                character = new_friend_character(bundle.get("state", {}), character_name or user["username"], background)
                db.execute("""INSERT INTO multiplayer_members
                    (room_id,user_id,username,role,character_json,ready,active,joined_at,last_seen_at)
                    VALUES(?,?,?,?,?,0,1,?,?)""",
                    (room["id"], user["id"], user["username"], "player",
                     json.dumps(character, ensure_ascii=False), _stamp(now), _stamp(now)))
        return self.status(room["id"], user["id"], heartbeat=False)

    def active_room(self, user_id):
        with self._connect() as db:
            row = db.execute("""SELECT r.* FROM multiplayer_rooms r
                JOIN multiplayer_members m ON m.room_id=r.id
                WHERE m.user_id=? AND m.active=1 AND r.status='active' LIMIT 1""", (user_id,)).fetchone()
        return dict(row) if row else None

    def member(self, room_id, user_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room_id, user_id)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["character"] = json.loads(data.pop("character_json") or "{}")
        return data

    def actions(self, room_id, user_id, round_number=None):
        with self._connect() as db:
            if round_number is None:
                round_number = db.execute("SELECT round_number FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()[0]
            rows = db.execute("""SELECT action FROM multiplayer_actions
                WHERE room_id=? AND user_id=? AND round_number=? ORDER BY action_index""",
                (room_id, user_id, int(round_number))).fetchall()
        return [row["action"] for row in rows]

    def queue_action(self, room_id, user_id, text):
        action = str(text or "").strip()
        if not action:
            raise ValueError("Type an action before adding it to the queue.")
        if len(action) > 800:
            raise ValueError("Queued actions must be under 800 characters each.")
        with self._connect() as db:
            room = db.execute("SELECT round_number,resolving FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["resolving"]:
                raise ValueError("The shared turn is currently resolving.")
            next_index = db.execute("""SELECT COALESCE(MAX(action_index),-1)+1 FROM multiplayer_actions
                WHERE room_id=? AND user_id=? AND round_number=?""", (room_id, user_id, room["round_number"])).fetchone()[0]
            if next_index >= 50:
                raise ValueError("A player can queue at most 50 actions per round.")
            db.execute("INSERT INTO multiplayer_actions VALUES(?,?,?,?,?)", (room_id, user_id, room["round_number"], next_index, action))
            db.execute("UPDATE multiplayer_members SET ready=0,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(), room_id, user_id))
        return self.actions(room_id, user_id)

    def replace_actions(self, room_id, user_id, actions):
        clean = [str(x).strip()[:800] for x in (actions or []) if str(x).strip()][:50]
        with self._connect() as db:
            room = db.execute("SELECT round_number,resolving FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["resolving"]:
                raise ValueError("The shared turn is currently resolving.")
            db.execute("DELETE FROM multiplayer_actions WHERE room_id=? AND user_id=? AND round_number=?", (room_id, user_id, room["round_number"]))
            db.executemany("INSERT INTO multiplayer_actions VALUES(?,?,?,?,?)",
                           [(room_id, user_id, room["round_number"], index, action) for index, action in enumerate(clean)])
            db.execute("UPDATE multiplayer_members SET ready=0,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(), room_id, user_id))
        return clean

    def remove_action(self, room_id, user_id, index):
        actions = self.actions(room_id, user_id)
        index = int(index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        actions.pop(index)
        return self.replace_actions(room_id, user_id, actions)

    def update_action(self, room_id, user_id, index, text):
        actions = self.actions(room_id, user_id)
        index = int(index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        actions[index] = str(text or "").strip()
        return self.replace_actions(room_id, user_id, actions)

    def move_action(self, room_id, user_id, index, to_index):
        actions = self.actions(room_id, user_id)
        index, to_index = int(index), int(to_index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        action = actions.pop(index)
        actions.insert(max(0, min(to_index, len(actions))), action)
        return self.replace_actions(room_id, user_id, actions)

    def set_ready(self, room_id, user_id, ready):
        with self._connect() as db:
            db.execute("UPDATE multiplayer_members SET ready=?,last_seen_at=? WHERE room_id=? AND user_id=?",
                       (1 if ready else 0, _stamp(), room_id, user_id))
        return self.status(room_id, user_id, heartbeat=False)

    def set_time(self, room_id, user_id, amount, unit, intensity):
        allowed = {"moment", "hours", "days", "weeks", "months", "next_event"}
        unit = str(unit or "moment")
        if unit not in allowed:
            raise ValueError("Invalid time unit.")
        amount = 1 if unit in {"moment", "next_event"} else max(1, min(999, int(amount or 1)))
        intensity = str(intensity or "normal")
        if intensity not in {"light", "normal", "intense", "extreme"}:
            intensity = "normal"
        with self._connect() as db:
            room = db.execute("SELECT host_user_id FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["host_user_id"] != user_id:
                raise ValueError("Only the host chooses the shared time advance.")
            db.execute("UPDATE multiplayer_rooms SET time_amount=?,time_unit=?,intensity=? WHERE id=?",
                       (amount, unit, intensity, room_id))
        return self.status(room_id, user_id, heartbeat=False)

    def leave(self, room_id, user_id):
        with self._connect() as db:
            room = db.execute("SELECT host_user_id FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room:
                return
            if room["host_user_id"] == user_id:
                db.execute("UPDATE multiplayer_rooms SET status='closed' WHERE id=?", (room_id,))
                db.execute("UPDATE multiplayer_members SET active=0,ready=0 WHERE room_id=?", (room_id,))
            else:
                db.execute("UPDATE multiplayer_members SET active=0,ready=0 WHERE room_id=? AND user_id=?", (room_id, user_id))

    def status(self, room_id, user_id, heartbeat=True, since_round=None):
        now = _now()
        with self._connect() as db:
            if heartbeat:
                db.execute("UPDATE multiplayer_members SET last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(now), room_id, user_id))
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            membership = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room_id, user_id)).fetchone()
            if not room or not membership:
                return {"active": False}
            rows = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? ORDER BY CASE role WHEN 'host' THEN 0 ELSE 1 END, joined_at", (room_id,)).fetchall()
            members = []
            for row in rows:
                character = json.loads(row["character_json"] or "{}")
                connected = (now - _parse(row["last_seen_at"])).total_seconds() <= CONNECTED_SECONDS
                members.append({"user_id": row["user_id"], "username": row["username"], "role": row["role"],
                                "character_name": character.get("name", row["username"]), "ready": bool(row["ready"]),
                                "connected": connected, "is_you": row["user_id"] == user_id})
            deadline = _parse(room["round_deadline"])
            result = {
                "active": room["status"] == "active" and bool(membership["active"]),
                "room_id": room["id"], "join_code": room["join_code"], "title": room["title"],
                "is_host": room["host_user_id"] == user_id, "round": int(room["round_number"]),
                "deadline": room["round_deadline"], "seconds_left": max(0, int((deadline - now).total_seconds())),
                "resolving": bool(room["resolving"]), "time_amount": int(room["time_amount"]),
                "time_unit": room["time_unit"], "intensity": room["intensity"], "members": members,
                "your_actions": self.actions(room_id, user_id, room["round_number"]),
                "your_ready": bool(membership["ready"]), "last_result_round": int(room["last_result_round"]),
                "last_error": room["last_error"],
            }
            if since_round is not None and int(room["last_result_round"]) > int(since_round or 0):
                personal = db.execute("""SELECT result_json FROM multiplayer_results
                    WHERE room_id=? AND round_number=? AND user_id=?""",
                    (room_id, int(room["last_result_round"]), user_id)).fetchone()
                result["result"] = json.loads(personal["result_json"] if personal else (room["last_result_json"] or "{}"))
            return result

    def chronicle(self, room_id, user_id, limit=300):
        limit = max(1, min(CHRONICLE_LIMIT, int(limit or 300)))
        with self._connect() as db:
            rows = db.execute("""SELECT round_number,entry_json FROM multiplayer_chronicle
                WHERE room_id=? AND user_id=? ORDER BY id DESC LIMIT ?""",
                (room_id, user_id, limit)).fetchall()
        entries = []
        for row in reversed(rows):
            try:
                entry = json.loads(row["entry_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if isinstance(entry, dict):
                entry.setdefault("multiplayer_round", int(row["round_number"]))
                entries.append(entry)
        return entries

    def resolution_plan(self, room_id):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["status"] != "active":
                return None
            rows = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? ORDER BY joined_at", (room_id,)).fetchall()
            participants, orders = [], []
            for row in rows:
                character = json.loads(row["character_json"] or "{}")
                connected = (now - _parse(row["last_seen_at"])).total_seconds() <= CONNECTED_SECONDS
                actions = self.actions(room_id, row["user_id"], room["round_number"])
                acts = bool(row["ready"] and connected)
                participant = {"user_id": row["user_id"], "username": row["username"],
                               "character": character, "ready": bool(row["ready"]),
                               "connected": connected, "actions": actions if acts else [], "passes": not acts}
                participants.append(participant)
                if acts:
                    for action in actions:
                        orders.append(f"{character.get('name', row['username'])}: {action}")
            if not orders:
                orders = ["All player characters pass and take no deliberate action during this moment."]
            return {"room": dict(room), "participants": participants, "orders": orders}

    def all_connected_ready(self, room_id):
        plan = self.resolution_plan(room_id)
        connected = [p for p in (plan or {}).get("participants", []) if p["connected"]]
        return len(connected) >= 2 and all(p["ready"] for p in connected)

    def claim(self, room_id, force=False):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["status"] != "active" or room["resolving"]:
                return False
            if not force and _parse(room["round_deadline"]) > now:
                return False
            changed = db.execute("UPDATE multiplayer_rooms SET resolving=1,last_error='' WHERE id=? AND resolving=0", (room_id,)).rowcount
        return bool(changed)

    def due_rooms(self):
        with self._connect() as db:
            rows = db.execute("SELECT id FROM multiplayer_rooms WHERE status='active' AND resolving=0 AND round_deadline<=?", (_stamp(),)).fetchall()
        return [row["id"] for row in rows]

    def save_characters(self, room_id, characters):
        with self._connect() as db:
            for user_id, character in characters.items():
                db.execute("UPDATE multiplayer_members SET character_json=? WHERE room_id=? AND user_id=?",
                           (json.dumps(character, ensure_ascii=False), room_id, user_id))

    def save_character(self, room_id, user_id, character):
        self.save_characters(room_id, {user_id: character})

    def complete(self, room_id, result, player_results=None):
        compact = {key: copy.deepcopy(result.get(key)) for key in (
            "status", "narrative", "interrupted", "died", "elapsed", "interruption_reason",
            "interruption_kind", "intervention_prompt", "major_event_reached", "major_event_title",
            "notifications", "story", "updates", "rolls") if key in result}
        with self._connect() as db:
            room = db.execute("SELECT round_number FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room:
                return
            completed_round = int(room["round_number"])
            next_round = completed_round + 1
            personal_results = player_results if isinstance(player_results, dict) else {}
            now = _stamp()
            for user_id, personal_result in personal_results.items():
                if not isinstance(personal_result, dict):
                    continue
                db.execute("""INSERT OR REPLACE INTO multiplayer_results
                    (room_id,round_number,user_id,result_json,created_at) VALUES(?,?,?,?,?)""",
                    (room_id, completed_round, str(user_id),
                     json.dumps(personal_result, ensure_ascii=False, separators=(",", ":")), now))
                for entry in personal_result.get("story") or []:
                    if isinstance(entry, dict) and str(entry.get("text") or "").strip():
                        db.execute("""INSERT INTO multiplayer_chronicle
                            (room_id,user_id,round_number,entry_json,created_at) VALUES(?,?,?,?,?)""",
                            (room_id, str(user_id), completed_round,
                             json.dumps(entry, ensure_ascii=False, separators=(",", ":")), now))
            db.execute("""UPDATE multiplayer_rooms SET round_number=?,round_deadline=?,resolving=0,
                last_result_round=?,last_result_json=?,last_error='' WHERE id=?""",
                (next_round, _stamp(_now() + timedelta(seconds=ROUND_SECONDS)), completed_round,
                 json.dumps(compact, ensure_ascii=False, separators=(",", ":")), room_id))
            db.execute("UPDATE multiplayer_members SET ready=0 WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM multiplayer_actions WHERE room_id=? AND round_number<=?", (room_id, completed_round))
            for user_id in personal_results:
                excess = db.execute("""SELECT id FROM multiplayer_chronicle WHERE room_id=? AND user_id=?
                    ORDER BY id DESC LIMIT -1 OFFSET ?""", (room_id, str(user_id), CHRONICLE_LIMIT)).fetchall()
                if excess:
                    db.executemany("DELETE FROM multiplayer_chronicle WHERE id=?", [(row["id"],) for row in excess])
            db.execute("DELETE FROM multiplayer_results WHERE room_id=? AND round_number<?", (room_id, max(0, completed_round - 20)))

    def fail(self, room_id, error):
        with self._connect() as db:
            db.execute("UPDATE multiplayer_rooms SET resolving=0,round_deadline=?,last_error=? WHERE id=?",
                       (_stamp(_now() + timedelta(seconds=60)), str(error)[:500], room_id))
