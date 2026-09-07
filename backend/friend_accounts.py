"""Small, self-contained account layer for a private Worldwalker server.

This is deliberately not a public SaaS identity system.  It gives a group of
friends durable usernames, hashed passwords, and completely separate game
folders while keeping the existing file-based campaign format intact.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from game import GameSession
from util import DATA_DIR, SETTINGS_PATH


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,24}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def persistent_secret() -> str:
    """Return a stable signing key without baking one into the repository."""
    configured = os.getenv("WORLDWALKER_SECRET_KEY", "").strip()
    if configured:
        return configured
    path = DATA_DIR / "friend_server_secret.txt"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
    return value


class FriendAccountStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or (DATA_DIR / "friend_accounts"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "accounts.sqlite3"
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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT NOT NULL
                );
            """)

    def public_user(self, user_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT id, username, created_at, last_login_at FROM users WHERE id=?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def register(self, username: str, password: str, invite_code: str = ""):
        username = str(username or "").strip()
        password = str(password or "")
        required_invite = os.getenv("WORLDWALKER_INVITE_CODE", "").strip()
        if required_invite and not secrets.compare_digest(str(invite_code or ""), required_invite):
            raise ValueError("That friend invite code is not valid.")
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("Username must be 3–24 letters, numbers, underscores, or dashes.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        maximum = max(1, int(os.getenv("WORLDWALKER_MAX_ACCOUNTS", "25") or 25))
        now = utc_now()
        user_id = uuid.uuid4().hex
        try:
            with self._connect() as db:
                count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                if count >= maximum:
                    raise ValueError("This friend server has reached its account limit.")
                db.execute(
                    "INSERT INTO users(id, username, password_hash, created_at, last_login_at) VALUES(?,?,?,?,?)",
                    (user_id, username, generate_password_hash(password), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username is already taken.") from exc
        self.user_root(user_id)
        return self.public_user(user_id)

    def authenticate(self, username: str, password: str):
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (str(username or "").strip(),)).fetchone()
            if not row or not check_password_hash(row["password_hash"], str(password or "")):
                raise ValueError("Username or password is incorrect.")
            now = utc_now()
            db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, row["id"]))
        return self.public_user(row["id"])

    def user_root(self, user_id: str) -> Path:
        # IDs come only from our UUID column.  The explicit validation keeps a
        # future caller from ever turning this into a path traversal primitive.
        if not re.fullmatch(r"[0-9a-f]{32}", str(user_id or "")):
            raise ValueError("Invalid account identifier.")
        root = self.root / "players" / user_id
        (root / "saves").mkdir(parents=True, exist_ok=True)
        return root


class FriendGameRegistry:
    """One independent GameSession per signed-in friend, within one process."""
    def __init__(self, accounts: FriendAccountStore):
        self.accounts = accounts
        self._lock = threading.RLock()
        self._games: dict[str, GameSession] = {}
        self._room_games: dict[str, GameSession] = {}

    def _seed_settings(self, destination: Path):
        if destination.exists():
            return
        configured = {}
        if SETTINGS_PATH.exists():
            try:
                configured.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                pass
        # Provider/model preferences are safe defaults. Credentials are never
        # copied from desktop/global settings into a new friend account: each
        # player owns the api_key/local_token stored under their UUID folder.
        configured.pop("api_key", None)
        configured.pop("local_token", None)
        environment = {
            "provider": os.getenv("WORLDWALKER_AI_PROVIDER", "cloud" if os.getenv("OPENAI_API_KEY") else ""),
            "model": os.getenv("WORLDWALKER_AI_MODEL", ""),
            "secondary_model": os.getenv("WORLDWALKER_SECONDARY_MODEL", ""),
            "major_event_model": os.getenv("WORLDWALKER_MAJOR_MODEL", ""),
        }
        configured.update({key: value for key, value in environment.items() if value})
        destination.write_text(json.dumps(configured, indent=2), encoding="utf-8")

    def get(self, user_id: str) -> GameSession:
        with self._lock:
            existing = self._games.get(user_id)
            if existing is not None:
                return existing
            root = self.accounts.user_root(user_id)
            settings_path = root / "settings.json"
            self._seed_settings(settings_path)
            game = GameSession(save_dir=root / "saves", settings_path=settings_path, account_id=user_id)
            self._games[user_id] = game
            return game

    def remove(self, user_id: str):
        with self._lock:
            self._games.pop(user_id, None)

    def get_room(self, room, room_root: Path) -> GameSession:
        """Return the one authoritative engine session for a shared room."""
        room_id = str(room["id"])
        with self._lock:
            existing = self._room_games.get(room_id)
            if existing is not None:
                return existing
            host_root = self.accounts.user_root(str(room["host_user_id"]))
            settings_path = host_root / "settings.json"
            self._seed_settings(settings_path)
            game = GameSession(save_dir=Path(room_root), settings_path=settings_path, account_id=f"room:{room_id}")
            game.shared_save_path = Path(room_root) / "shared_campaign.json"
            if game.shared_save_path.exists():
                game.load("shared_campaign")
            self._room_games[room_id] = game
            return game

    def remove_room(self, room_id: str):
        with self._lock:
            self._room_games.pop(str(room_id), None)
