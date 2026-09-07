"""Flask application: serves the frontend, game assets, and the JSON API
that the browser-based UI drives the game engine through."""
import copy, io, json, os, secrets, threading, traceback, sys, time
from datetime import timedelta
from urllib.parse import quote
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file, g, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.local import LocalProxy

from worlds import APP_VERSION, WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, WORLD_PACKS_LOADED, WORLD_PACK_ERRORS, expansion_for, abilities_for, stat_style_for, start_options_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, starting_eras_for, power_profile_for
from release_notes import notes_for
from build_info import BUILD_ID, PATCH_NOTES
from chapter_recaps import chapter_view
from organizations import roster_view
from gm_refinements import fingerprint
from util import ASSET_ROOT, DATA_DIR, world_slug, scene_selection_reason
from game import GameSession
from portrait_generator import (PORTRAIT_CACHE_DIR, clear_active_portrait_form, generate_portrait,
                                save_reference, portrait_history, revert_portrait,
                                portrait_usage, portrait_view)
from lore import (list_lore_sources, import_lore_pack, import_lore_url, lore_library_status,
                  lore_automation_status, configure_lore_automation, refresh_lore_sources,
                  seed_recommended_lore_sources)
from content_audit import audit_all_worlds
from systems import (normalize_tuning, progression_preset_for, relationship_snapshot,
                     campaign_health, map_snapshot, quest_presentation_for,
                     normalize_quest_state_machine)
from reliability import narrative_memory_snapshot, canon_event_tracker, visible_class_profile, visible_skills
from knowledge import knowledge_snapshot
from causality import causality_snapshot
from simulation_integrity import (integrity_snapshot, campaign_search,
                                  apply_player_correction, build_travel_graph,
                                  travel_route, canon_dependency_graph)
from evaluations import list_evaluations, run_model_comparison, run_model_evaluation, run_local_simulation_evaluation
from support import repair_campaign_state, build_diagnostic_bundle
from friend_accounts import FriendAccountStore, FriendGameRegistry, persistent_secret
from multiplayer import (MultiplayerStore, character_from_state, player_view,
                         apply_character_update, split_player_results)
from multiplayer_combat import resolve_multiplayer_combat_round
from ai_client import AI
from overgeared_classes import class_encyclopedia
from long_campaign import record_runtime_error

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
MUSIC_ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT_DIR) / "music"
MUSIC_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".ogg", ".wav"}


def ensure_music_folders():
    MUSIC_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in ["Shared", *WORLD_DATA.keys()]:
        (MUSIC_ROOT / folder).mkdir(parents=True, exist_ok=True)
    return MUSIC_ROOT


ensure_music_folders()

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False  # preserve dict insertion order (ability lists, skills, etc. are meaningfully ordered)
ACCOUNTS_ENABLED = os.getenv("WORLDWALKER_ACCOUNTS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
app.secret_key = persistent_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("WORLDWALKER_SECURE_COOKIES", "1" if ACCOUNTS_ENABLED else "0").strip().lower() in {"1", "true", "yes", "on"},
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

_single_game = GameSession()
_account_store = FriendAccountStore() if ACCOUNTS_ENABLED else None
_game_registry = FriendGameRegistry(_account_store) if _account_store else None
_multiplayer_store = MultiplayerStore(_account_store) if _account_store else None


def _request_game():
    if not ACCOUNTS_ENABLED:
        return _single_game
    bound = getattr(g, "worldwalker_game", None)
    if bound is None:
        raise RuntimeError("Sign in before using the game API.")
    return bound


# Existing routes can keep referring to `game`; in friend-server mode this
# resolves to the signed-in user's isolated session for the current request.
game = LocalProxy(_request_game)


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
    return token


@app.before_request
def bind_friend_account():
    if not ACCOUNTS_ENABLED:
        g.worldwalker_game = _single_game
        return None
    # HTML, built-in art/music and the auth bootstrap remain public so the
    # sign-in screen can render. Generated portraits and every game API are
    # bound to an authenticated friend.
    public_api = {"/api/version", "/api/auth/session", "/api/auth/login", "/api/auth/register"}
    needs_account = request.path.startswith("/api/") or request.path.startswith("/portrait-cache/")
    bearer = _bearer_identity()
    user_id = str(session.get("user_id") or (bearer or {}).get("user_id") or "")
    user = _account_store.public_user(user_id) if user_id else None
    if not user:
        session.pop("user_id", None)
        if needs_account and request.path not in public_api:
            return jsonify({"error": "Sign in to play.", "authentication_required": True}), 401
        return None
    g.worldwalker_user = user
    g.worldwalker_bearer_csrf = str((bearer or {}).get("csrf_token") or "") if not session.get("user_id") else ""
    g.worldwalker_personal_game = _game_registry.get(user["id"])
    room = _multiplayer_store.active_room(user["id"]) if _multiplayer_store else None
    if room:
        g.worldwalker_room = room
        g.worldwalker_game = _game_registry.get_room(room, _multiplayer_store.room_root(room["id"]))
    else:
        g.worldwalker_room = None
        g.worldwalker_game = g.worldwalker_personal_game
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.path not in {"/api/auth/login", "/api/auth/register"}:
        provided = request.headers.get("X-Worldwalker-CSRF", "")
        expected = g.worldwalker_bearer_csrf or _csrf_token()
        if not expected or not secrets.compare_digest(provided, expected):
            return jsonify({"error": "Your login session needs to be refreshed."}), 403
    return None


def _cache_control_for(path, version=""):
    """Return a cache policy that is safe for desktop and resilient on LAN phones.

    The HTML shell and APIs must revalidate, but versioned code can be kept
    indefinitely.  This matters on iOS: Safari may discard an inactive tab
    and reconstruct it later, while plain HTTP LAN pages cannot install a
    service worker.  Keeping the versioned shell assets locally prevents a
    brief sleeping-PC or Wi-Fi interruption from turning the restored page
    into unstyled HTML.
    """
    if path.startswith("/api/"):
        return "no-store, no-cache, must-revalidate, max-age=0"
    if path in {"/", "/sw.js", "/manifest.webmanifest"}:
        return "no-cache, max-age=0, stale-if-error=86400"
    if path.startswith(("/css/", "/js/")):
        if version in {APP_VERSION, BUILD_ID}:
            return "public, max-age=31536000, immutable"
        return "public, max-age=300, stale-while-revalidate=86400, stale-if-error=86400"
    if path.startswith("/assets/"):
        return "public, max-age=604800, stale-while-revalidate=2592000, stale-if-error=2592000"
    if path.startswith("/portrait-cache/"):
        return "private, max-age=86400, stale-if-error=604800"
    if path.startswith("/music/"):
        return "private, max-age=3600, stale-if-error=86400"
    return "no-cache, max-age=0, stale-if-error=86400"


@app.after_request
def apply_client_cache_policy(response):
    """Cache immutable presentation files without caching game/account data."""
    policy = _cache_control_for(request.path, request.args.get("v", ""))
    response.headers["Cache-Control"] = policy
    if policy.startswith("no-store"):
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    response.headers["X-Worldwalker-Version"] = APP_VERSION
    response.headers["X-Worldwalker-Build"] = BUILD_ID
    return response

_bg_lock = threading.Lock()
_bg_state = {}

_busy_lock = threading.Lock()
_evaluation_lock = threading.Lock()
_portrait_lock = threading.Lock()
_lore_refresh_lock = threading.Lock()
_lore_refresh_started = False

AUTH_TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _auth_serializer():
    """Sign a mobile-safe fallback token with the server's session secret."""
    return URLSafeTimedSerializer(app.secret_key, salt="worldwalker-friend-auth-v1")


def _issue_auth_token(user_id, csrf_token):
    return _auth_serializer().dumps({"user_id": str(user_id), "csrf_token": str(csrf_token)})


def _bearer_identity():
    """Recover an account when a phone browser refuses the session cookie.

    The normal first-party, HttpOnly cookie remains the preferred path.  A
    signed bearer token is returned only after a successful login/register
    and gives installed PWAs and privacy-heavy mobile browsers an equivalent
    30-day session without weakening account isolation.
    """
    header = str(request.headers.get("Authorization") or "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = _auth_serializer().loads(token, max_age=AUTH_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or not payload.get("user_id"):
        return None
    return {"user_id": str(payload["user_id"]), "csrf_token": str(payload.get("csrf_token") or "")}


def _start_due_lore_refresh_once():
    """Launch one non-blocking due-source pass on app startup/first use."""
    global _lore_refresh_started
    with _lore_refresh_lock:
        if _lore_refresh_started:
            return
        _lore_refresh_started = True
    status = lore_automation_status()
    if not status.get("settings", {}).get("enabled") or not status.get("due"):
        return
    threading.Thread(target=refresh_lore_sources, kwargs={"force": False}, daemon=True,
                     name="worldwalker-lore-refresh").start()


@app.before_request
def start_background_lore_refresh():
    _start_due_lore_refresh_once()
    _start_multiplayer_worker_once()


def acquire_busy():
    """Guards against two AI-calling requests racing on the shared GameSession
    (e.g. an accidental double-submit) — first one in wins, the second gets a
    clean 409 instead of corrupting shared state via concurrent apply_resolution."""
    with _busy_lock:
        if game.busy:
            return False
        game.busy = True
        return True


def release_busy():
    game.busy = False


TACTICAL_COMBAT_WORLDS = frozenset({'Naruto', 'One Piece', 'Bleach'})


def tactical_feature_enabled():
    """Compatibility helper: tactical combat is now mandatory where shipped."""
    return True


def request_public_state():
    """Shared world plus the signed-in member's own character and plan."""
    tactical_local=((game.state.get('world') in TACTICAL_COMBAT_WORLDS or (game.state.get('combat') or {}).get('adventure_objective')) and game.combat_active())
    if tactical_local:
        game.state['combat']['tactical_enabled']=True
    state = game.public_state()
    if tactical_local:
        state['_tactical_battle_url']='/tactical-preview/designs/campaign.html'
    room = getattr(g, "worldwalker_room", None)
    user = getattr(g, "worldwalker_user", None)
    if room and user and _multiplayer_store:
        member = _multiplayer_store.member(room["id"], user["id"])
        if member:
            state = player_view(state, member.get("character", {}),
                                _multiplayer_store.actions(room["id"], user["id"], room["round_number"]))
            settings_game = getattr(g, "worldwalker_personal_game", None) or game
            state.update(portrait_view(state, settings_game.settings))
            state["_power_profile"] = power_profile_for(
                state.get("world", "Custom World"), state.get("stats", {}),
                state.get("special", {}).get("Archetype", "") if isinstance(state.get("special"), dict) else "",
            )
            state["_multiplayer"] = _multiplayer_store.status(room["id"], user["id"], heartbeat=False)
            state["_multiplayer_chronicle"] = _multiplayer_store.chronicle(room["id"], user["id"])
    return state


def request_portrait_state():
    """Mutable character-shaped state for per-player multiplayer portraits."""
    room = getattr(g, "worldwalker_room", None)
    user = getattr(g, "worldwalker_user", None)
    if room and user and _multiplayer_store:
        member = _multiplayer_store.member(room["id"], user["id"])
        if member:
            merged = dict(game.state)
            merged.update(member.get("character", {}))
            return merged, member["character"]
    return game.state, game.state


def busy_error():
    return jsonify({"error": "Another AI request is already in progress."}), 409


def err(e, code=500):
    traceback.print_exc()
    try:
        row = record_runtime_error(
            game.state, e, request.path if request else "api",
            request.get_json(silent=True) if request else None, traceback.format_exc(),
        )
        return jsonify({"error": str(e), "error_id": row.get("id"),
                        "recovery": "The campaign was preserved. Retry the turn or export Diagnostics with this error ID."}), code
    except Exception:
        return jsonify({"error": str(e)}), code


def atomic_game_call(route, payload, callback):
    """Resolve once, retain a receipt, and preserve a resumable failure snapshot."""
    from request_receipts import completed, remember, campaign
    from turn_recovery import guard
    payload = payload if isinstance(payload, dict) else {}
    request_id = str(payload.get("request_id") or "")
    if len(request_id) > 100:
        raise ValueError("Request ID is too long.")
    if not game.lock.acquire(blocking=False):
        raise ValueError("Another campaign update is still resolving.")
    transaction = None
    try:
        cached = completed(game, request_id, route, payload) if request_id else None
        if cached is not None:
            return cached
        if payload.get("expected_campaign") and payload["expected_campaign"] != campaign(game.state):
            raise ValueError("This request belongs to another campaign. Reload before submitting it.")
        if payload.get("expected_guard") and payload["expected_guard"] != guard(game.state):
            failed = game.state.get("last_failed_turn") or {}
            recoverable = (failed.get("route") == route and failed.get("payload") == payload and
                           (failed.get("work") or {}).get("guard") == guard(game.state))
            if not recoverable:
                raise ValueError("The campaign changed since this action was prepared. Reload and review it before submitting again.")
        game._inflight_request = {"id": request_id, "route": route}
        transaction = game.begin_turn_transaction(route, payload)
        from ai_budget import turn_budget
        with turn_budget(game.settings.get("max_ai_cost_per_turn_usd", 0),
                         game.settings.get("max_ai_retries_per_turn", 2)):
            result = callback()
        is_confirmation = isinstance(result, dict) and str(result.get("status", "")).endswith("_required")
        entry = game.complete_turn_transaction(transaction, save=False, include_receipt=not is_confirmation)
        if isinstance(result, dict):
            if entry is not None:
                result["story"] = list(result.get("story") or []) + [copy.deepcopy(entry)]
            if "state" in result:
                result["state"] = game.public_state()
            remember(game, request_id, route, payload, result)
        game.autosave()
        if isinstance(result, dict):
            if "state" in result:
                result["state"] = game.public_state()
            result["_recovery_guard"] = guard(game.state)
        return result
    except Exception as exc:
        if transaction is not None:
            game.rollback_turn_transaction(transaction, exc)
        raise
    finally:
        game._inflight_request = None
        game.lock.release()


@app.route("/api/action/status")
def api_action_status():
    """Read a request's result without starting another simulation or AI call."""
    from request_receipts import status
    request_id = request.args.get("request_id", "")
    route = request.args.get("route", "")
    if not request_id or len(request_id) > 100 or route not in {"time_resolve", "combat_action", "combat_narrate", "event_respond", "adventure_resolve"}:
        return jsonify({"error": "A valid request ID and operation are required."}), 400
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Shared rounds use the multiplayer coordinator."}), 409
    try:
        return jsonify(status(game, request_id, route))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409


# ---------- shared two-player campaign coordinator ----------
_multiplayer_worker_lock = threading.Lock()
_multiplayer_worker_started = False


def _room_game(room_id):
    # The intentionally plain DB lookup below avoids depending on a request
    # context; timer resolutions run in a daemon thread.
    with _multiplayer_store._connect() as db:
        row = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
    if not row:
        raise ValueError("Multiplayer room no longer exists.")
    room = dict(row)
    return room, _game_registry.get_room(room, _multiplayer_store.room_root(room_id))


def _resolve_multiplayer_room(room_id, force=False):
    if tactical_feature_enabled() and _multiplayer_store:
        _, candidate=_room_game(room_id)
        if (candidate.state.get('combat') or {}).get('tactical_enabled') and candidate.combat_active():
            return False  # tactical ownership/timer, never the legacy text-action resolver
    if not _multiplayer_store or not _multiplayer_store.claim(room_id, force=force):
        return False
    target_game = None
    try:
        plan = _multiplayer_store.resolution_plan(room_id)
        if not plan:
            raise ValueError("Multiplayer room is no longer active.")
        room, target_game = _room_game(room_id)
        if target_game.busy:
            raise RuntimeError("The shared campaign is already processing another request.")
        target_game.busy = True
        participants = []
        for person in plan["participants"]:
            # Imported/older multiplayer rows can contain the JSON string
            # value itself (or a legacy display name) instead of a decoded
            # character object.  Repair the boundary here so one malformed
            # member cannot lock every combat control for the whole room.
            character = person.get("character", {})
            if isinstance(character, str):
                try:
                    decoded = json.loads(character)
                    character = decoded if isinstance(decoded, dict) else {}
                except (TypeError, ValueError):
                    character = {}
            elif not isinstance(character, dict):
                character = {}
            person["character"] = character
            participants.append({
                "user_id": person["user_id"], "character_name": character.get("name", person["username"]),
                "location": character.get("location", target_game.state.get("location", "")),
                "sublocation": character.get("sublocation", target_game.state.get("sublocation", "")),
                "stats": character.get("stats", {}), "skills": character.get("skills", {}),
                "status": character.get("status", "Normal"), "connected": person["connected"],
                "ready": person["ready"], "passes": person["passes"], "actions": person["actions"],
            })
        no_ready_actions = not any(not person["passes"] and person["actions"] for person in plan["participants"])
        amount = 1 if no_ready_actions else int(room["time_amount"])
        unit = "moment" if no_ready_actions else room["time_unit"]
        intensity = room["intensity"]
        orders = plan["orders"]
        target_game.state["queued_actions"] = []
        target_game.state["standing_orders"] = []
        target_game.multiplayer_context = {"round": int(room["round_number"]), "participants": participants}
        combat_result = resolve_multiplayer_combat_round(target_game.state, plan["participants"], int(room["round_number"]))
        if combat_result:
            target_game.state = combat_result["state"]
            characters = combat_result["characters"]
            host_id = room["host_user_id"]
            if host_id in characters:
                for key, value in characters[host_id].items():
                    if key in {"hp", "hp_max", "resource", "resource_max", "alive", "status", "conditions"}:
                        target_game.state[key] = copy.deepcopy(value)
            result = combat_result["result"]
            player_results = split_player_results(result, plan["participants"], characters, host_id)
            _multiplayer_store.save_characters(room_id, characters)
            target_game.save(); _multiplayer_store.complete(room_id, result, player_results)
            return True
        assessed = target_game.assess_time_skip(amount, unit, orders, intensity, use_model=False)
        manual_rolls = {}
        result = target_game.run_time_skip(
            amount, unit, assessed.get("orders", orders), intensity, assessed.get("assessment", {}),
            confirmed_lethal=True, confirmed_power_goal=True, manual_rolls=manual_rolls,
            danger_warning_acknowledged=True,
        )
        # Timeout resolution cannot wait for a browser-only dice modal. The
        # server rolls the same d100 entropy and records it in the Chronicle.
        for _ in range(20):
            if result.get("status") != "manual_roll_required":
                break
            manual_rolls[str(result.get("check_id") or "major")] = secrets.randbelow(100) + 1
            result = target_game.run_time_skip(
                amount, unit, assessed.get("orders", orders), intensity, assessed.get("assessment", {}),
                confirmed_lethal=True, confirmed_power_goal=True, manual_rolls=manual_rolls,
                danger_warning_acknowledged=True,
            )
        if result.get("status") != "resolved":
            raise RuntimeError("The shared turn could not pass its resolution gate.")

        updates = result.pop("multiplayer_character_updates", {})
        characters = {}
        host_id = room["host_user_id"]
        for person in plan["participants"]:
            user_id = person["user_id"]
            if user_id == host_id:
                characters[user_id] = character_from_state(target_game.state)
            else:
                characters[user_id] = apply_character_update(person["character"], updates.get(user_id, {}))
        player_results = split_player_results(result, plan["participants"], characters, host_id)
        _multiplayer_store.save_characters(room_id, characters)
        target_game.state["queued_actions"] = []
        target_game.state["standing_orders"] = []
        target_game.save()
        _multiplayer_store.complete(room_id, result, player_results)
        return True
    except Exception as exc:
        traceback.print_exc()
        _multiplayer_store.fail(room_id, exc)
        return False
    finally:
        if target_game is not None:
            target_game.multiplayer_context = None
            target_game.busy = False


def _multiplayer_timer_loop():
    while True:
        try:
            if tactical_feature_enabled():
                from naruto_tactical_room import tick,persist_members
                with _multiplayer_store._connect() as db:
                    active_ids=[r['id'] for r in db.execute("SELECT id FROM multiplayer_rooms WHERE status='active'").fetchall()]
                for rid in active_ids:
                    _, active_game=_room_game(rid)
                    if not active_game.combat_active() or not (active_game.state.get('combat') or {}).get('tactical_enabled'):continue
                    with _busy_lock:
                        if active_game.busy:continue
                        active_game.busy=True
                    try:
                        plan=_multiplayer_store.resolution_plan(rid)
                        if tick(active_game,plan['participants']):
                            persist_members(active_game,_multiplayer_store,rid,plan['participants'])
                            active_game.save()
                    finally:active_game.busy=False
            for room_id in _multiplayer_store.due_rooms():
                _resolve_multiplayer_room(room_id, force=False)
        except Exception:
            traceback.print_exc()
        time.sleep(5)


def _start_multiplayer_worker_once():
    global _multiplayer_worker_started
    if not _multiplayer_store:
        return
    with _multiplayer_worker_lock:
        if _multiplayer_worker_started:
            return
        _multiplayer_worker_started = True
        threading.Thread(target=_multiplayer_timer_loop, daemon=True,
                         name="worldwalker-multiplayer-clock").start()


# ---------- static / frontend ----------
def _render_index():
    """Serve index.html with its CSS/JS hrefs tagged to APP_VERSION.

    A desktop build's own no-store headers only stop the plain HTTP cache —
    they do nothing about a browser engine's Cache Storage / service-worker
    cache, which can keep answering with a snapshot from a much older
    version indefinitely. A version-stamped URL sidesteps the question of
    which cache layer is misbehaving: every cache treats it as a brand new
    resource it has never seen, so there is nothing stale left to serve.
    """
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/css/style.css"', f'href="/css/style.css?v={APP_VERSION}"')
    html = html.replace('src="/js/app.js"', f'src="/js/app.js?v={APP_VERSION}"')
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/")
def index():
    return _render_index()


@app.route("/<path:path>")
def frontend_files(path):
    full = FRONTEND_DIR / path
    if full.exists() and full.is_file():
        return send_from_directory(FRONTEND_DIR, path)
    return _render_index()


@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory(ASSET_ROOT, path)


@app.route("/music/<path:path>")
def music_file(path):
    return send_from_directory(MUSIC_ROOT, path, conditional=True)


@app.route("/portrait-cache/<path:filename>")
def portrait_cache(filename):
    return send_from_directory(PORTRAIT_CACHE_DIR, filename)


# ---------- private friend accounts ----------
@app.route("/api/auth/session")
def api_auth_session():
    user = getattr(g, "worldwalker_user", None)
    bearer_csrf = str(getattr(g, "worldwalker_bearer_csrf", "") or "")
    return jsonify({
        "accounts_enabled": ACCOUNTS_ENABLED,
        "authenticated": bool(user),
        "user": user,
        "csrf_token": (bearer_csrf or _csrf_token()) if ACCOUNTS_ENABLED else "",
        "invite_required": bool(os.getenv("WORLDWALKER_INVITE_CODE", "").strip()) if ACCOUNTS_ENABLED else False,
    })


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    if not ACCOUNTS_ENABLED:
        return jsonify({"error": "Friend accounts are not enabled on this copy."}), 400
    d = request.get_json(silent=True) or {}
    try:
        user = _account_store.register(d.get("username", ""), d.get("password", ""), d.get("invite_code", ""))
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        token = _csrf_token()
        return jsonify({"ok": True, "user": user, "csrf_token": token,
                        "auth_token": _issue_auth_token(user["id"], token)}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    if not ACCOUNTS_ENABLED:
        return jsonify({"error": "Friend accounts are not enabled on this copy."}), 400
    d = request.get_json(silent=True) or {}
    try:
        user = _account_store.authenticate(d.get("username", ""), d.get("password", ""))
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        token = _csrf_token()
        return jsonify({"ok": True, "user": user, "csrf_token": token,
                        "auth_token": _issue_auth_token(user["id"], token)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    user_id = str(session.get("user_id") or "")
    if getattr(g, "worldwalker_game", None) is not None and game.campaign_active:
        try:
            game.save()
        except Exception:
            traceback.print_exc()
    session.clear()
    # Dropping the in-memory copy ensures the next login starts from durable
    # saves rather than inheriting unsaved transient UI/session state.
    if _game_registry and user_id:
        _game_registry.remove(user_id)
    return jsonify({"ok": True})


@app.route("/api/ability-archive")
def api_ability_archive():
    """Return this account's non-canon creation history for later reuse."""
    world = str(request.args.get("world") or "").strip()
    category = str(request.args.get("category") or "").strip()
    entries = game.generated_ability_archive.entries(world=world, category=category)
    return jsonify({"count": len(entries), "entries": entries})


# ---------- private two-player rooms ----------
@app.route("/api/multiplayer/status")
def api_multiplayer_status():
    if not _multiplayer_store:
        return jsonify({"active": False, "available": False})
    user = g.worldwalker_user
    room = _multiplayer_store.active_room(user["id"])
    if not room:
        return jsonify({"active": False, "available": True})
    since = request.args.get("since_round")
    try:
        since = int(since) if since is not None else None
    except ValueError:
        since = None
    return jsonify(_multiplayer_store.status(room["id"], user["id"], heartbeat=True, since_round=since))


@app.route("/api/multiplayer/create", methods=["POST"])
def api_multiplayer_create():
    if not _multiplayer_store:
        return jsonify({"error": "Friend accounts are required for multiplayer."}), 400
    personal = getattr(g, "worldwalker_personal_game", None)
    if not personal or not personal.campaign_active:
        return jsonify({"error": "Start, load, or import the campaign you want to copy first."}), 400
    try:
        status = _multiplayer_store.create_room(g.worldwalker_user, personal.save_bundle("multiplayer-copy"))
        return jsonify(status), 201
    except Exception as exc:
        return err(exc, 400)


@app.route("/api/multiplayer/join", methods=["POST"])
def api_multiplayer_join():
    if not _multiplayer_store:
        return jsonify({"error": "Friend accounts are required for multiplayer."}), 400
    data = request.get_json(silent=True) or {}
    try:
        status = _multiplayer_store.join_room(
            g.worldwalker_user, data.get("join_code", ""), data.get("character_name", ""),
            data.get("background", ""),
        )
        return jsonify(status)
    except Exception as exc:
        return err(exc, 400)


@app.route("/api/multiplayer/leave", methods=["POST"])
def api_multiplayer_leave():
    room = getattr(g, "worldwalker_room", None)
    if room:
        try:
            game.save()
        except Exception:
            traceback.print_exc()
        _multiplayer_store.leave(room["id"], g.worldwalker_user["id"])
        if room["host_user_id"] == g.worldwalker_user["id"]:
            _game_registry.remove_room(room["id"])
    return jsonify({"ok": True})


@app.route("/api/multiplayer/ready", methods=["POST"])
def api_multiplayer_ready():
    room = getattr(g, "worldwalker_room", None)
    if not room:
        return jsonify({"error": "Join a multiplayer campaign first."}), 400
    data = request.get_json(silent=True) or {}
    status = _multiplayer_store.set_ready(room["id"], g.worldwalker_user["id"], bool(data.get("ready", True)))
    if _multiplayer_store.all_connected_ready(room["id"]):
        threading.Thread(target=_resolve_multiplayer_room, args=(room["id"], True), daemon=True,
                         name=f"worldwalker-room-{room['id'][:8]}").start()
        status["resolving"] = True
    return jsonify(status)


@app.route("/api/multiplayer/time", methods=["POST"])
def api_multiplayer_time():
    room = getattr(g, "worldwalker_room", None)
    if not room:
        return jsonify({"error": "Join a multiplayer campaign first."}), 400
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(_multiplayer_store.set_time(
            room["id"], g.worldwalker_user["id"], data.get("amount", 1),
            data.get("unit", "moment"), data.get("intensity", "normal"),
        ))
    except Exception as exc:
        return err(exc, 400)


@app.route("/api/multiplayer/resolve", methods=["POST"])
def api_multiplayer_resolve():
    room = getattr(g, "worldwalker_room", None)
    if not room:
        return jsonify({"error": "Join a multiplayer campaign first."}), 400
    if room["host_user_id"] != g.worldwalker_user["id"]:
        return jsonify({"error": "Only the host can advance before the ten-minute timer expires."}), 403
    threading.Thread(target=_resolve_multiplayer_room, args=(room["id"], True), daemon=True,
                     name=f"worldwalker-room-{room['id'][:8]}").start()
    return jsonify({"ok": True, "resolving": True}), 202


# ---------- world / campaign data ----------
@app.route("/api/version")
def api_version():
    return jsonify({"version": APP_VERSION, "build_id": BUILD_ID, "patch_notes": PATCH_NOTES})


@app.route("/api/worlds")
def api_worlds():
    out = {}
    for name, wd in WORLD_DATA.items():
        ex = expansion_for(name)
        out[name] = {
            "tagline": wd["tagline"], "resource": wd["resource"], "start": wd["start"],
            "origins": ex["origins"], "archetypes": ex["archetypes"], "currency": ex["currency"],
            "abilities": abilities_for(name), "stat_style": stat_style_for(name),
            "start_options": start_options_for(name) or [
                {"label": wd["start"], "location": wd["start"], "note": "Default starting location for this world."}
            ],
            "playable_characters": playable_characters_for(name),
            "starting_eras": starting_eras_for(name) or [{
                "id": "default", "label": "Main story opening",
                "start_day": int(timeline_for(name).get("start_day", -7)),
                "anchor": timeline_for(name).get("anchor", "Shortly before the main story."),
            }],
        }
    return jsonify({"worlds": out, "difficulties": DIFFICULTIES, "order": list(WORLD_DATA.keys())})


@app.route("/api/campaign/new", methods=["POST"])
def api_campaign_new():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Leave multiplayer before starting a different campaign. The shared copy will remain separate."}), 409
    d = request.get_json(force=True)
    try:
        world = d.get("world", "Custom World")
        stats = {k: int(d.get("stats", {}).get(k, 0)) for k in abilities_for(world)}
        state = game.new_campaign(
            name=d.get("name", "Traveler"), world=world,
            difficulty=d.get("difficulty", "Adventurer"), background=d.get("background", ""),
            appearance_desc=d.get("appearance", ""), custom_world=d.get("custom_world", ""),
            origin=d.get("origin", ""), archetype=d.get("archetype", ""), stats=stats,
            start_location=d.get("start_location", ""), start_note=d.get("start_note", ""),
            preview_stats=d.get("preview_stats"),
            preview_profile=d.get("preview_profile"),
            canon_character_id=d.get("canon_character_id", ""),
            starting_era_id=d.get("starting_era_id", ""),
            age=d.get("age", ""),
            jjk_guarantee_strong=bool(d.get("jjk_guarantee_strong", False)),
            jjk_curse_grade=d.get("jjk_curse_grade", ""),
            hxh_start_with_nen=bool(d.get("hxh_start_with_nen", False)),
            one_piece_devil_fruit=bool(d.get("one_piece_devil_fruit", False)),
            one_piece_haki_types=d.get("one_piece_haki_types", []),
            overgeared_class_start=d.get("overgeared_class_start", "narrative"),
        )
        return jsonify({"state": state, "story": game._flush_story()})
    except Exception as e:
        return err(e)


@app.route("/api/campaign/preview", methods=["POST"])
def api_campaign_preview():
    d = request.get_json(force=True)
    try:
        preview = game.preview_campaign(
            d.get("name", "Traveler"), d.get("world", "Custom World"), d.get("difficulty", "Adventurer"),
            d.get("background", ""), d.get("appearance", ""), d.get("custom_world", ""),
            d.get("origin", ""), d.get("archetype", ""), d.get("stats", {}),
            d.get("start_location", ""), d.get("start_note", ""),
            d.get("canon_character_id", ""), d.get("starting_era_id", ""),
            bool(d.get("jjk_guarantee_strong", False)), d.get("jjk_curse_grade", ""),
            bool(d.get("hxh_start_with_nen", False)),
            bool(d.get("one_piece_devil_fruit", False)), d.get("one_piece_haki_types", []),
            d.get("overgeared_class_start", "narrative"),
        )
        return jsonify({"preview": preview})
    except Exception as e:
        return err(e, 400)


@app.route("/api/campaign/preview/reroll", methods=["POST"])
def api_campaign_preview_reroll():
    d = request.get_json(force=True)
    try:
        preview = game.reroll_campaign_preview(
            d.get("preview", {}), d.get("kind", ""), d.get("background", ""),
        )
        return jsonify({"preview": preview})
    except Exception as e:
        return err(e, 400)


@app.route("/api/campaign/opening", methods=["POST"])
def api_campaign_opening():
    if not game.ai_ready():
        return jsonify({"error": "AI not configured. Open Settings and select a model."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.opening()
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


# ---------- turn loop ----------
@app.route("/api/state")
def api_state():
    return jsonify({"state": request_public_state(), "busy": game.busy, "campaign_active": game.campaign_active,
                     "tactical_story":game.story_log[-300:] if tactical_feature_enabled() and game.state.get('world') in {'Naruto','One Piece','Bleach'} and not getattr(g,'worldwalker_room',None) else [],
                     "ai_ready": game.ai_ready(), "ai_connection_status": game.settings.get("ai_connection_status", "untested"),
                     "local_mode": game.local_mode()})


@app.route("/api/action/submit", methods=["POST"])
def api_action_submit():
    d = request.get_json(force=True)
    action = (d.get("action") or "").strip()
    if not action:
        return jsonify({"error": "No action given."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        # Legacy endpoint kept for older frontends, but v2.4's contract is
        # strict: submitting plans only queues them. Advance is the sole
        # resolution/time/world-response endpoint.
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.queue_action(room["id"], user["id"], action)
                  if room and user else game.queue_action(action))
        return jsonify({"status": "queued", "queued_actions": queued, "state": request_public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/event/respond", methods=["POST"])
def api_event_respond():
    """One beat of an already-active major event — resolved as a scoped,
    ordinary action (no time/calendar movement, no world-clock ticking),
    so the player can go back and forth inside the event for as long as it
    takes without the wider campaign silently simulating forward."""
    d = request.get_json(force=True)
    action = (d.get("action") or "").strip()
    if not action:
        return jsonify({"error": "No action given."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        return jsonify(atomic_game_call("event_respond", {**d, "action": action}, lambda: game.respond_to_event(action)))
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/queue", methods=["POST"])
def api_actions_queue():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        payload = request.get_json(force=True)
        action = payload.get("action") or ""
        from living_world import interpretation as interpret_action
        interpreted = interpret_action(action, game.state)
        if interpreted.get("ambiguous") and not payload.get("confirmed_interpretation"):
            return jsonify({"status": "interpretation_required", "interpretation": interpreted,
                            "queued_actions": list(game.state.get("queued_actions", []))})
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.queue_action(room["id"], user["id"], action)
                  if room and user else game.queue_action(action))
        return jsonify({"queued_actions": queued, "interpretation": interpreted})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/remove", methods=["POST"])
def api_actions_remove():
    try:
        index = request.get_json(force=True).get("index", -1)
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.remove_action(room["id"], user["id"], index)
                  if room and user else game.remove_queued_action(index))
        return jsonify({"queued_actions": queued})
    except Exception as e:
        return err(e, 400)


@app.route("/api/combat/tactical", methods=["GET", "POST"])
def api_naruto_tactical():
    """Server-authoritative tactical endpoint for supported worlds."""
    room=getattr(g,'worldwalker_room',None)
    user=getattr(g,'worldwalker_user',None)
    if room and (not user or not _multiplayer_store):
        return jsonify({'error':'Sign in to the shared room first.'}),409
    if not game.campaign_active or (game.state.get('world') not in TACTICAL_COMBAT_WORLDS and not (game.state.get('combat') or {}).get('adventure_objective')):
        return jsonify({'error':'Load a supported tactical test campaign first.'}),400
    from tactical_combat import ensure_board, board_view, submit_naruto_action
    if not acquire_busy(): return busy_error()
    try:
        participants=[]
        if room:
            from naruto_tactical_room import initialize,snapshot,submit,tick,persist_members
            _multiplayer_store.status(room['id'],user['id'],heartbeat=True)
            participants=_multiplayer_store.resolution_plan(room['id'])['participants']
        if request.method=='GET':
            if game.combat_active():game.state['combat']['tactical_enabled']=True
            if not (game.state.get('combat') or {}).get('tactical_enabled'):
                return jsonify({'enabled':False})
            game.ensure_combat_numbers()
            if room:
                initialize(game,participants,room['host_user_id'])
                if tick(game,participants):persist_members(game,_multiplayer_store,room['id'],participants)
                return jsonify({'enabled':True,**snapshot(game,user['id'])})
            board=board_view(game.state)
            return jsonify({'enabled':True,'world':game.state.get('world'),'board':board,'viewer_id':board.get('active_id','player'),'combat':game.state['combat'],
                            'portrait_identity':game.state.get('portrait_identity',{})})
        payload=request.get_json(force=True)
        def apply():
            if payload.get('action')=='enable':
                if room and user['id']!=room['host_user_id']:raise ValueError('Only the host can enable this local test encounter.')
                if not game.combat_active(): raise ValueError('Start an encounter first.')
                game.ensure_combat_numbers()
                game.state['combat']['tactical_enabled']=True
                ensure_board(game.state); game.autosave()
                if room:
                    initialize(game,participants,room['host_user_id']);game.autosave()
                    return {'enabled':True,**snapshot(game,user['id'])}
                return {'world':game.state.get('world'),'combat':game.state['combat'],'board':board_view(game.state)}
            if room:
                result=submit(game,user['id'],payload)
                persist_members(game,_multiplayer_store,room['id'],participants)
                return result
            return submit_naruto_action(game,payload)
        return jsonify(atomic_game_call('naruto_tactical',payload,apply))
    except Exception as e:
        return err(e,400)
    finally:
        release_busy()


@app.route('/tactical-preview/<path:filename>')
def local_tactical_preview(filename):
    # Preserve the approved preview URL while serving files included in every build.
    if filename.startswith('designs/'):filename=filename[len('designs/'):]
    return send_from_directory(FRONTEND_DIR/'tactical',filename)


@app.route("/api/combat/state")
def api_combat_state():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    game.ensure_combat_numbers()
    return jsonify({"combat": game.state.get("combat") or {}, "hp": game.state.get("hp"), "hp_max": game.state.get("hp_max"),
                     "resource": game.state.get("resource"), "resource_max": game.state.get("resource_max"),
                     "skills": game.state.get("skills", {})})


@app.route("/api/combat/mercy", methods=["POST"])
def api_combat_mercy():
    """Toggles combat.spare_enemy — a player choice, independent of the AI's
    own combat.non_lethal (spar/test) flag. Sparing the enemy only protects
    THEM from dying to the player's hits; it does nothing for the player's
    own HP, which stays fully at risk if the fight goes the other way."""
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not game.combat_active():
        return jsonify({"error": "Not in combat."}), 400
    if game.state.get("world") in TACTICAL_COMBAT_WORLDS or (game.state.get("combat") or {}).get("adventure_objective"):
        return jsonify({"error": "Use the tactical battlefield for this combat.",
                        "tactical_url": "/tactical-preview/designs/campaign.html"}), 409
    d = request.get_json(force=True)
    game.state["combat"]["spare_enemy"] = bool(d.get("spare"))
    return jsonify({"combat": game.state["combat"]})


@app.route("/api/combat/action", methods=["POST"])
def api_combat_action():
    """Resolves exactly one exchange locally — no AI call, near-instant.
    Only /api/combat/narrate spends an AI call, and only when asked to."""
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not game.combat_active():
        return jsonify({"error": "Not in combat."}), 400
    if game.state.get("world") in TACTICAL_COMBAT_WORLDS or (game.state.get("combat") or {}).get("adventure_objective"):
        return jsonify({"error": "Legacy combat is unavailable in this world. Continue on the tactical battlefield.",
                        "tactical_url": "/tactical-preview/designs/campaign.html"}), 409
    d = request.get_json(force=True)
    action = (d.get("action") or "attack").strip().lower()
    if action not in ("attack", "defend", "flee", "overwhelm"):
        action = "attack"
    try:
        result = atomic_game_call("combat_action", {**d, "action": action, "ability": d.get("ability")},
                                  lambda: game.resolve_combat_round(action, ability_name=d.get("ability")))
        return jsonify(result)
    except Exception as e:
        return err(e, 400)


@app.route("/api/combat/narrate", methods=["POST"])
def api_combat_narrate():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = atomic_game_call("combat_narrate", request.get_json(silent=True) or {}, lambda: game.narrate_combat())
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/usage")
def api_usage():
    """Session-total estimated AI spend, for the topbar cost indicator.
    Numbers only get more accurate as calls happen — nothing here is
    predictive, it's a running tally of what's already been spent."""
    main_u, bg_u, major_u, portrait_u = game.ai.usage, game.ai_bg.usage, game.ai_major.usage, portrait_usage()
    unique_clients = list({id(client): client for client in (game.ai, game.ai_bg, game.ai_major, game.ai_advisor, game.ai_creative)}.values())
    cost_known = not any(client.usage.get("cost_unknown") for client in unique_clients)
    total_cost = sum(client.usage.get("cost_usd", 0.0) for client in unique_clients) + portrait_u.get("cost_usd", 0.0)
    by_task = {}
    for client in unique_clients:
        for task, row in (client.usage.get("by_task") or {}).items():
            merged = by_task.setdefault(task, {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            for key in merged:
                merged[key] += row.get(key, 0)
    warning_at = max(0.0, float(game.settings.get("session_budget_warning_usd", 0) or 0))
    return jsonify({
        "provider": game.settings.get("provider", "local"),
        "main": main_u, "background": bg_u, "major": major_u, "advisor": game.ai_advisor.usage,
        "creative": game.ai_creative.usage, "portraits": portrait_u,
        "major_model": game.settings.get("major_event_model", ""),
        "major_is_separate": game.ai_major is not game.ai,
        "total_cost_usd": round(total_cost, 4),
        "session_budget_warning_usd": warning_at,
        "over_session_budget": bool(warning_at and total_cost >= warning_at),
        "cost_estimate_complete": cost_known,
        "cost_is_conservative": any(client.usage.get("cost_is_conservative") for client in unique_clients),
        "cached_input_tokens": sum(client.usage.get("cached_input_tokens", 0) for client in unique_clients),
        "total_calls": sum(client.usage.get("calls", 0) for client in unique_clients),
        "by_task": by_task,
    })


@app.route("/api/status_window/dismiss", methods=["POST"])
def api_status_window_dismiss():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    game.state["status_window_due"] = False
    game.autosave()
    return jsonify({"ok": True})


@app.route("/api/action/rewind_death", methods=["POST"])
def api_rewind_death():
    result = game.rewind_death()
    if result is None:
        return jsonify({"error": "No checkpoint available."}), 400
    return jsonify(result)


@app.route("/api/action/undo", methods=["POST"])
def api_undo():
    result = game.undo()
    if result is None:
        return jsonify({"error": "No checkpoint available."}), 400
    return jsonify(result)


# ---------- time skip ----------
@app.route("/api/time/assess", methods=["POST"])
def api_time_assess():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Multiplayer actions resolve through Ready and the shared ten-minute round."}), 409
    d = request.get_json(force=True)
    if not game.ai_ready():
        return jsonify({"error": "AI not configured."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.assess_time_skip(d.get("amount", 1), d.get("unit", "moment"), d.get("orders", ""),
                                       d.get("intensity", "normal"), use_model=False)
        # Assessment records standing orders. Return its post-assessment guard
        # so the subsequent resolving request is not based on stale UI state.
        from turn_recovery import guard
        result["_recovery_guard"] = guard(game.state)
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/time/resolve", methods=["POST"])
def api_time_resolve():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Multiplayer actions resolve through Ready and the shared ten-minute round."}), 409
    d = request.get_json(force=True)
    if not acquire_busy():
        return busy_error()
    try:
        result = atomic_game_call("time_resolve", d, lambda: game.run_time_skip(
                                     d.get("amount", 1), d.get("unit", "moment"), d.get("orders", []),
                                     d.get("intensity", "normal"), d.get("assessment", {}),
                                     confirmed_lethal=bool(d.get("confirmed_lethal")),
                                     confirmed_power_goal=bool(d.get("confirmed_power_goal")),
                                     manual_rolls=d.get("manual_rolls", {}),
                                     challenge_modes=d.get("challenge_modes", {}),
                                     challenge_resolution_mode=d.get("challenge_resolution_mode", "continue"),
                                     danger_warning_acknowledged=bool(d.get("danger_warning_acknowledged"))))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/action/retry_failed", methods=["POST"])
def api_retry_failed_turn():
    failed = game.state.get("last_failed_turn") if isinstance(game.state.get("last_failed_turn"), dict) else {}
    route, payload = failed.get("route"), failed.get("payload")
    if not route or not isinstance(payload, dict):
        return jsonify({"error": "There is no failed turn waiting to retry."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        if route == "time_resolve":
            d = payload
            result = atomic_game_call(route, d, lambda: game.run_time_skip(
                d.get("amount", 1), d.get("unit", "moment"), d.get("orders", []), d.get("intensity", "normal"),
                d.get("assessment", {}), confirmed_lethal=bool(d.get("confirmed_lethal")),
                confirmed_power_goal=bool(d.get("confirmed_power_goal")), manual_rolls=d.get("manual_rolls", {}),
                challenge_modes=d.get("challenge_modes", {}), challenge_resolution_mode=d.get("challenge_resolution_mode", "continue"),
                danger_warning_acknowledged=bool(d.get("danger_warning_acknowledged"))))
        elif route == "event_respond":
            result = atomic_game_call(route, payload, lambda: game.respond_to_event(payload.get("action", "")))
        elif route == "combat_action":
            result = atomic_game_call(route, payload, lambda: game.resolve_combat_round(payload.get("action", "attack"), ability_name=payload.get("ability")))
        elif route == "combat_narrate":
            result = atomic_game_call(route, payload, lambda: game.narrate_combat())
        else:
            return jsonify({"error": "That older failed operation cannot be retried automatically."}), 400
        return jsonify(result)
    except Exception as exc:
        return err(exc)
    finally:
        release_busy()


@app.route("/api/dice/d100", methods=["POST"])
def api_dice_d100():
    """Server-authored entropy for the animated major-event roll UI."""
    return jsonify({"roll": secrets.randbelow(100) + 1})


# ---------- chat ----------
@app.route("/api/chats")
def api_chats():
    s = game.state
    return jsonify({"contacts": s.get("contacts", {}), "chat_threads": s.get("chat_threads", {}), "unread": s.get("unread_chats", [])})


@app.route("/api/chats/read", methods=["POST"])
def api_chats_read():
    d = request.get_json(force=True)
    thread = d.get("thread")
    game.state["unread_chats"] = [x for x in game.state.get("unread_chats", []) if x.get("thread") != thread]
    game.autosave()
    return jsonify({"ok": True})


@app.route("/api/chats/send", methods=["POST"])
def api_chats_send():
    d = request.get_json(force=True)
    thread, message = d.get("thread"), (d.get("message") or "").strip()
    if not thread or not message:
        return jsonify({"error": "Thread and message are required."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.resolve_side_chat(thread, message)
        return jsonify(result)
    except Exception as e:
        return err(e, 400)
    finally:
        release_busy()


# ---------- advisor ----------
@app.route("/api/advisor")
def api_advisor_get():
    return jsonify({"thread": game.state.get("advisor_thread", [])})


@app.route("/api/advisor/ask", methods=["POST"])
def api_advisor_ask():
    d = request.get_json(force=True)
    question = (d.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Ask the Advisor something first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.ask_advisor(question, fourth_wall=bool(d.get("fourth_wall")))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


# ---------- background world simulation (non-blocking) ----------
def _background_key():
    user = getattr(g, "worldwalker_user", None)
    return user["id"] if user else "single-player"


def _run_background_jobs(key, target_game):
    try:
        local = target_game.run_local_background()
        # Economy and Balanced never spend an extra background-model call.
        # Deep mode opts into at most one such call every four resolved
        # turns, alternating communications and wider-world narration.
        if target_game.background_ai_due():
            if int(target_game.state.get("turn", 0) or 0) % 8:
                chat = target_game.maybe_generate_incoming_chat()
                if chat:
                    with _bg_lock:
                        _bg_state[key]["pending"].append({"type": "chat", **chat, "state": target_game.public_state()})
            else:
                tick = target_game.create_world_event_if_due()
                if tick and tick.get("heard_event"):
                    with _bg_lock:
                        _bg_state[key]["pending"].append({"type": "world_event", "message": tick["heard_event"], "state": target_game.public_state()})
        with _bg_lock:
            _bg_state[key]["pending"].append({"type": "maintenance", **local, "state": target_game.public_state()})
    except Exception:
        traceback.print_exc()
    finally:
        with _bg_lock:
            _bg_state.setdefault(key, {"running": False, "pending": []})["running"] = False


@app.route("/api/background/run", methods=["POST"])
def api_background_run():
    key = _background_key()
    target_game = _request_game()
    with _bg_lock:
        state = _bg_state.setdefault(key, {"running": False, "pending": []})
        if state["running"] or target_game.busy:
            return jsonify({"started": False})
        state["running"] = True
    threading.Thread(target=_run_background_jobs, args=(key, target_game), daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/background/poll")
def api_background_poll():
    key = _background_key()
    with _bg_lock:
        state = _bg_state.setdefault(key, {"running": False, "pending": []})
        items = state["pending"][:]
        state["pending"].clear()
    return jsonify({"events": items})


# ---------- shops / training / codex snapshots (derived, no AI call) ----------
@app.route("/api/panels")
def api_panels():
    s = game.state
    normalize_quest_state_machine(s)
    ex = expansion_for(s.get("world", "Custom World"))
    world = s.get("world", "Custom World")
    world_map = WORLD_DATA.get(world, {}).get("map", [])
    canon_events = timeline_for(world).get("events", [])
    tracker = canon_event_tracker(s, canon_events)
    dependencies = canon_dependency_graph(s)
    dep_by_id = {str(row.get("id")): row for row in dependencies.get("events", []) if isinstance(row, dict)}
    canon_events_view = []
    for event in canon_events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or f"day:{event.get('day', 0)}:{event.get('title', 'event')}")
        row = copy.deepcopy(event); row["id"] = event_id
        resolved = dep_by_id.get(event_id, {})
        for key in ("status", "reason", "replacement", "effective_day", "requires"):
            if key in resolved: row[key] = copy.deepcopy(resolved[key])
        canon_events_view.append(row)
    from character_paths import public_view as character_paths_view
    from canon_divergence import public_view as canon_interventions_view
    from world_conflict import public_view as world_conflict_view
    from organization_command import public_view as organization_command_view
    from reputation_system import public_view as public_reputation_view
    from property_economy import public_view as property_economy_view, market_shops_view
    # Player reference is intentionally spoiler-visible. Character/NPC knowledge
    # and narrator foreknowledge settings remain independent of this read view.
    return jsonify({
        "currency": s.get("currency", {"name": ex["currency"], "amount": 0}),
        "currencies": s.get("currencies", {}),
        "currency_ledger": s.get("currency_ledger", []),
        "finance_debts": s.get("finance_debts", []),
        "tracks_currency": bool(ex.get("tracks_currency", True)),
        "gear_style": gear_style_for(s.get("world", "Custom World")),
        "shops": market_shops_view(s),
        "shop_types": ex["shop_types"],
        "training_options": ex["training"],
        "ability_progress": s.get("ability_progress", {}),
        "progression_log": s.get("progression_log", []),
        "progression_ledger": s.get("progression_ledger", []),
        "uses_xp": uses_xp_for(s.get("world", "Custom World"), s.get("custom_world", "")),
        "level": s.get("level", 1), "xp": s.get("xp", 0), "xp_next": s.get("xp_next", 100),
        "stats": s.get("stats", {}),
        "quests": s.get("quests", []),
        "quest_presentation": quest_presentation_for(world),
        "hidden_quests_count": len(s.get("hidden_quests", [])),
        "codex": s.get("codex", []),
        "inventory": s.get("inventory", []),
        "equipment": s.get("equipment", {}),
        "companions": s.get("companions", []),
        "organization_roster": roster_view(s),
        "companion_combinations": s.get("companion_combinations", []),
        "titles": s.get("titles", []),
        "skills": visible_skills(s),
        "special": s.get("special", {}),
        "overgeared_system": s.get("overgeared_system", {}),
        "class_encyclopedia": class_encyclopedia() if world == "Overgeared" else {},
        "solo_system": s.get("solo_system", {}),
        "jjk_system": s.get("jjk_system", {}),
        "world_activity": s.get("world_activity", {}),
        "world_depth": s.get("world_depth", {}),
        "class_profile": visible_class_profile(s),
        "combat": s.get("combat", {}),
        "world_events": s.get("world_events", []),
        "timeline": s.get("timeline", []),
        "background_world_feed": s.get("background_world_feed", []),
        "achievements": s.get("achievements", []),
        "trophy_proposals": s.get("trophy_proposals", []),
        "legacy_trophies": s.get("legacy_trophies", []),
        "map": world_map,
        "map_data": map_snapshot(s, world_map, world),
        "map_image": f"/assets/generated_maps/{world_slug(s.get('world', 'Custom World'))}.webp",
        "world": s.get("world", "Custom World"),
        "discovered_locations": s.get("discovered_locations", []),
        "location": s.get("location", ""),
        "prerequisite_tracks": s.get("prerequisite_tracks", []),
        "canon_day": s.get("canon_day", -7),
        "calendar_view": __import__("world_calendar").view(s),
        "canon_reference_visible": True,
        "canon_anchor": s.get("canon_anchor", ""), "calendar_epoch": s.get("calendar_epoch", ""),
        "calendar_anchor_day": s.get("calendar_anchor_day"),
        "canon_events": canon_events_view,
        "canon_interventions": canon_interventions_view(s),
        "canon_event_tracker": tracker,
        "canon_events_fired": s.get("canon_events_fired", []),
        "scheduled_events": game.visible_schedule(),
        "quest_archive": s.get("quest_archive", []),
        "continuity": s.get("continuity_ledger", {}),
        "campaign_canon": s.get("campaign_canon", []),
        "chapter_summaries": [chapter_view(row, s.get("name", "")) for row in s.get("chapter_summaries", []) if isinstance(row, dict)], "chapter_buffer": s.get("chapter_buffer", []),
        "npc_clocks": s.get("npc_clocks", {}), "faction_clocks": s.get("faction_clocks", {}),
        "character_paths": character_paths_view(s),
        "world_conflict": world_conflict_view(s),
        "organization_command": organization_command_view(s),
        "public_reputation": public_reputation_view(s),
        "property_economy": property_economy_view(s),
        "relationships_view": relationship_snapshot(s),
        "progression_preset": progression_preset_for(world), "difficulty_controls": normalize_tuning(s),
        "campaign_health": campaign_health(s), "lore_sources": list_lore_sources(),
        "lore_automation": lore_automation_status(s.get("world", "Custom World")),
        "director_notes": s.get("director_notes", ""),
        "narrative_memory": narrative_memory_snapshot(s),
        "npc_knowledge": knowledge_snapshot(s),
        "causality": causality_snapshot(s),
        "lore_status": lore_library_status(s.get("world", "Custom World")),
        "evaluations": list_evaluations(),
        "evaluation_models": [model for model in dict.fromkeys([
            game.settings.get("model", ""), game.settings.get("major_event_model", "")
        ]) if model],
        "simulation": {"profile": game.simulation_profile(),
                       "intentions": s.get("npc_intentions", {}),
                       "campaign_direction": s.get("campaign_direction", {}),
                       "relationship_opportunities": s.get("relationship_opportunities", []),
                       "recent_events": s.get("simulation_events", [])[-40:],
                       "integrity": integrity_snapshot(s)},
        "travel_graph": build_travel_graph(s),
        "canon_dependencies": dependencies,
    })


@app.route("/api/trophies/resolve", methods=["POST"])
def api_resolve_trophy():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    d = request.get_json(silent=True) or {}
    proposal_id = str(d.get("id") or "").strip()
    proposals = game.state.get("trophy_proposals") if isinstance(game.state.get("trophy_proposals"), list) else []
    proposal = next((row for row in proposals if isinstance(row, dict) and str(row.get("id")) == proposal_id), None)
    if not proposal:
        return jsonify({"error": "That trophy proposal is no longer pending."}), 404
    game.state["trophy_proposals"] = [row for row in proposals if row is not proposal]
    accepted = bool(d.get("accepted"))
    if accepted:
        saved = dict(proposal)
        saved["accepted_turn"] = int(game.state.get("turn", 0) or 0)
        game.state.setdefault("legacy_trophies", []).append(saved)
        game.append(f"[LEGACY KEPT]\n{saved.get('title')} was added to the campaign's trophy collection.", "meta")
    else:
        game.state.setdefault("dismissed_trophy_ids", []).append(proposal_id)
    game.autosave()
    return jsonify({"ok": True, "accepted": accepted, "state": game.public_state(), "story": game._flush_story()})


@app.route("/api/campaign/search")
def api_campaign_search():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    query = str(request.args.get("q") or "").strip()
    return jsonify({"query": query, "results": campaign_search(game.state, query, request.args.get("limit", 30))})


@app.route('/api/campaign/review')
def api_campaign_review():
    if not game.campaign_active: return jsonify({'error':'Start or load a campaign first.'}),400
    from campaign_review import review_candidates
    return jsonify({'candidates':review_candidates(game.state)})


def correction_preview(payload):
    scratch = copy.deepcopy(game.state)
    record = apply_player_correction(scratch, payload.get("type"), payload.get("target"), payload.get("value"), payload.get("explanation", ""))
    changes = []
    for key in ("location", "inventory", "currency", "hp", "resource", "quests", "skills", "location_details", "political_regions"):
        if scratch.get(key) != game.state.get(key):
            changes.append({"field": key, "before": copy.deepcopy(game.state.get(key)), "after": copy.deepcopy(scratch.get(key))})
    if payload.get('type') == 'npc_status':
        target = str(payload.get('target') or '').casefold()
        for key in ('npc_memories', 'contacts', 'organizations'):
            old = game.state.get(key) if isinstance(game.state.get(key), dict) else {}
            new = scratch.get(key) if isinstance(scratch.get(key), dict) else {}
            for name, value in new.items():
                if old.get(name) != value:
                    changes.append({'field': f'{key}.{name}', 'before': copy.deepcopy(old.get(name)), 'after': copy.deepcopy(value)})
        if scratch.get('companions') != game.state.get('companions'):
            matching = lambda rows: [r for r in rows or [] if isinstance(r, dict) and str(r.get('name', '')).casefold() == target]
            changes.append({'field':'companions', 'before':matching(game.state.get('companions')), 'after':matching(scratch.get('companions'))})
    from turn_recovery import guard
    return {"fact": record["fact"], "changes": changes,
            "preview_token": fingerprint([guard(game.state), game.state.get('location_details'), game.state.get('political_regions'),
                                           [game.state.get(k) for k in ('npc_memories','contacts','organizations','companions')] if payload.get('type') == 'npc_status' else None,
                                           {k: v for k, v in payload.items() if k != "preview_token"}])}


@app.route("/api/campaign/correct/preview", methods=["POST"])
def api_campaign_correct_preview():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        return jsonify(correction_preview(request.get_json(force=True)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/campaign/correct", methods=["POST"])
def api_campaign_correct():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    d = request.get_json(force=True)
    if game.state.get("world") == "Bleach" and d.get("type") == "currency":
        return jsonify({"error": "Bleach does not maintain a tracked currency balance."}), 400
    try:
        if game.busy:
            return busy_error()
        if d.get('type') in {'territory', 'npc_status'} and not d.get('preview_token'):
            return jsonify({'error':'Preview this correction before applying it.'}),409
        if d.get("preview_token") and d["preview_token"] != correction_preview(d)["preview_token"]:
            return jsonify({"error": "The campaign or correction changed. Preview it again before applying."}), 409
        record = apply_player_correction(game.state, d.get("type"), d.get("target"), d.get("value"), d.get("explanation", ""))
        source = d.get("source")
        if isinstance(source, dict):
            record["source_entry"] = {"text": str(source.get("text", ""))[:1600], "time": str(source.get("time", ""))[:100]}
        game.append("[PLAYER CORRECTION]\n" + record["fact"], "meta")
        game.autosave()
        return jsonify({"ok": True, "correction": record, "state": game.public_state(), "story": game._flush_story()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/character-paths/pin", methods=["POST"])
def api_character_path_pin():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        from character_paths import pin
        view = pin(game.state, (request.get_json(silent=True) or {}).get("path_id", ""))
        game.autosave()
        return jsonify({"ok": True, "character_paths": view, "state": game.public_state()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/canon-interventions", methods=["POST"])
def api_canon_interventions():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    d = request.get_json(silent=True) or {}
    try:
        from canon_divergence import target, cancel, public_view
        action = str(d.get("action") or "target")
        if action == "target": target(game.state, d.get("event_id"))
        elif action == "cancel": cancel(game.state, d.get("event_id"))
        else: raise ValueError("Unknown canon-intervention action.")
        game.autosave()
        return jsonify({"ok": True, "canon_interventions": public_view(game.state), "state": game.public_state()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/organization-command", methods=["POST"])
def api_organization_command():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    d = request.get_json(silent=True) or {}
    try:
        from organization_command import start_assignment, cancel_assignment, start_project, public_view
        action = str(d.get("action") or "start")
        if action == "start":
            result = start_assignment(game.state, d.get("group_id"), d.get("task"), d.get("members") or [], d.get("target", ""))
        elif action == "cancel": result = cancel_assignment(game.state, d.get("assignment_id"))
        elif action == "project": result = start_project(game.state, d.get("group_id"), d.get("property_id"), d.get("facility"))
        else: raise ValueError("Unknown organization-command action.")
        game.autosave()
        return jsonify({"ok": True, "result": result, "organization_command": public_view(game.state), "state": game.public_state()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/travel/route")
def api_travel_route():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    destination = str(request.args.get("destination") or "").strip()
    return jsonify(travel_route(game.state, destination))


@app.route("/api/campaign/tuning", methods=["POST"])
def api_campaign_tuning():
    d = request.get_json(force=True)
    controls = game.state.setdefault("difficulty_controls", {})
    for key in ("check_warning_threshold", "xp_rate", "training_rate", "breakthrough_rate", "combat_danger", "resource_pressure"):
        if key in d: controls[key] = d[key]
    if "director_notes" in d:
        game.state["director_notes"] = str(d["director_notes"] or "")[:500]
    clean = normalize_tuning(game.state)
    game.autosave()
    return jsonify({"difficulty_controls": clean, "state": game.public_state()})


@app.route("/api/lore")
def api_lore_sources():
    return jsonify({"sources": list_lore_sources(), "folder": str(DATA_DIR / "lore"),
                    "status": lore_library_status(game.state.get("world", "Custom World")),
                    "automation": lore_automation_status(game.state.get("world", "Custom World"))})


@app.route("/api/lore/import", methods=["POST"])
def api_lore_import():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "Choose a JSON, Markdown, or text lore file."}), 400
    try:
        result = import_lore_pack(uploaded.filename or "lore.json", uploaded.read(2 * 1024 * 1024 + 1), request.form.get("world", "Custom World"))
        return jsonify({"imported": result, "sources": list_lore_sources()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/update-url", methods=["POST"])
def api_lore_update_url():
    d = request.get_json(silent=True) or {}
    try:
        result = import_lore_url(
            d.get("url", ""), d.get("world") or game.state.get("world", "Custom World"),
            d.get("source_type", "wiki"), auto_refresh=bool(d.get("auto_refresh", True)),
            discover=bool(d.get("discover", False)),
        )
        return jsonify({"updated": result, "sources": list_lore_sources(),
                        "status": lore_library_status(game.state.get("world", "Custom World")),
                        "automation": lore_automation_status(game.state.get("world", "Custom World"))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/automation", methods=["GET", "POST"])
def api_lore_automation():
    world = game.state.get("world", "Custom World")
    if request.method == "GET":
        return jsonify(lore_automation_status(world))
    try:
        settings = request.get_json(silent=True) or {}
        status = configure_lore_automation(settings)
        if settings.get("enabled") and settings.get("recommended_sources", True):
            seed_recommended_lore_sources()
            status = lore_automation_status(world)
        return jsonify(status)
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/refresh", methods=["POST"])
def api_lore_refresh():
    d = request.get_json(silent=True) or {}
    try:
        result = refresh_lore_sources(force=bool(d.get("force", True)),
                                      world=d.get("world") or game.state.get("world", "Custom World"))
        return jsonify({"refresh": result, "automation": lore_automation_status(game.state.get("world", "Custom World")),
                        "sources": list_lore_sources(), "status": lore_library_status(game.state.get("world", "Custom World"))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/content-audit")
def api_content_audit():
    return jsonify(audit_all_worlds())


@app.route("/api/quick_action", methods=["POST"])
def api_quick_action():
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    try:
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.queue_action(room["id"], user["id"], text)
                  if room and user else game.queue_action(text))
        return jsonify({"status": "queued", "queued_actions": queued, "state": request_public_state()})
    except Exception as e:
        return err(e, 400)

# ---------- settings ----------
@app.route("/api/music")
def api_music():
    ensure_music_folders()
    requested = request.args.get("world") or game.state.get("world", "Custom World")
    world = requested if requested in WORLD_DATA else "Custom World"
    tracks = []
    for folder, source in ((MUSIC_ROOT / world, world), (MUSIC_ROOT / "Shared", "Shared")):
        for file in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if file.is_file() and file.suffix.lower() in MUSIC_EXTENSIONS:
                rel = file.relative_to(MUSIC_ROOT).as_posix()
                tracks.append({"name": file.stem, "filename": file.name, "source": source,
                               "url": "/music/" + quote(rel, safe="/")})
    return jsonify({"world": world, "folder": str(MUSIC_ROOT / world), "root": str(MUSIC_ROOT), "tracks": tracks,
                    "supported": sorted(MUSIC_EXTENSIONS)})


@app.route("/api/music/open_folder", methods=["POST"])
def api_music_open_folder():
    ensure_music_folders()
    d = request.get_json(silent=True) or {}
    requested = d.get("world") or game.state.get("world", "Custom World")
    world = requested if requested in WORLD_DATA else "Custom World"
    target = MUSIC_ROOT / world
    if sys.platform == "win32":
        os.startfile(str(target))
    return jsonify({"ok": True, "folder": str(target)})


@app.route("/api/portrait/generate", methods=["POST"])
def api_portrait_generate():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign before generating a portrait."}), 400
    d = request.get_json(silent=True) or {}
    if not _portrait_lock.acquire(blocking=False):
        return jsonify({"error": "A portrait is already being generated."}), 409
    try:
        portrait_state, _ = request_portrait_state()
        settings_game = getattr(g, "worldwalker_personal_game", None) or game
        result = generate_portrait(portrait_state, settings_game.settings, force=bool(d.get("force")))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        _portrait_lock.release()


@app.route("/api/portrait/identity", methods=["POST"])
def api_portrait_identity():
    d = request.get_json(force=True)
    portrait_state, character = request_portrait_state()
    identity = character.setdefault("portrait_identity", {})
    history = identity.setdefault("history", [])
    history.append({"appearance_desc": portrait_state.get("appearance_desc", ""),
                    "portrait_traits": list(portrait_state.get("portrait_traits", [])),
                    "canonical_description": identity.get("canonical_description", ""),
                    "temporary_traits": list(identity.get("temporary_traits", [])),
                    "turn": game.state.get("turn", 0)})
    identity["history"] = history[-20:]
    if "canonical_description" in d:
        identity["canonical_description"] = str(d.get("canonical_description") or "")[:2000]
    if "temporary_traits" in d:
        value = d.get("temporary_traits")
        identity["temporary_traits"] = [str(x)[:300] for x in value] if isinstance(value, list) else []
    if "locked" in d:
        identity["locked"] = bool(d.get("locked"))
    room = getattr(g, "worldwalker_room", None)
    user = getattr(g, "worldwalker_user", None)
    if room and user:
        _multiplayer_store.save_character(room["id"], user["id"], character)
    else:
        game.autosave()
    return jsonify({"identity": identity, "state": request_public_state()})


@app.route("/api/portrait/reference", methods=["POST"])
def api_portrait_reference():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    uploaded = request.files.get("image")
    if not uploaded:
        return jsonify({"error": "Choose a portrait image first."}), 400
    try:
        portrait_state, _ = request_portrait_state()
        result = save_reference(portrait_state, uploaded.read(12 * 1024 * 1024 + 1))
        game.autosave()
        return jsonify({**result, "state": request_public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/portrait/history")
def api_portrait_history():
    portrait_state, character = request_portrait_state()
    return jsonify({"history": portrait_history(portrait_state), "identity": character.get("portrait_identity", {})})


@app.route("/api/portrait/form/end", methods=["POST"])
def api_portrait_form_end():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    portrait_state, character = request_portrait_state()
    changed = clear_active_portrait_form(portrait_state)
    if character is not portrait_state:
        clear_active_portrait_form(character)
    for target in {id(portrait_state): portrait_state, id(character): character}.values():
        combat = target.get("combat") if isinstance(target.get("combat"), dict) else None
        if combat:
            combat["player_buffs"] = [row for row in combat.get("player_buffs", [])
                                      if not (isinstance(row, dict) and row.get("effect_type") == "transform")]
    room = getattr(g, "worldwalker_room", None)
    user = getattr(g, "worldwalker_user", None)
    if room and user and _multiplayer_store:
        _multiplayer_store.save_character(room["id"], user["id"], character)
    else:
        game.autosave()
    return jsonify({"ok": True, "changed": changed, "state": request_public_state()})


@app.route("/api/portrait/revert", methods=["POST"])
def api_portrait_revert():
    try:
        portrait_state, _ = request_portrait_state()
        return jsonify({**revert_portrait(portrait_state), "state": request_public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    settings_game = getattr(g, "worldwalker_personal_game", None) or game
    s = dict(settings_game.settings)
    s.pop("api_key", None)
    s["has_api_key"] = bool(settings_game.settings.get("api_key"))
    return jsonify(s)


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    d = request.get_json(force=True)
    patch = {k: d[k] for k in [
        "provider", "local_base_url", "local_token", "api_key", "model", "secondary_model", "major_event_model",
        "advisor_model", "advisor_provider", "creative_model", "creative_provider",
        "max_ai_cost_per_request_usd", "max_ai_cost_per_turn_usd", "max_ai_retries_per_turn", "session_budget_warning_usd",
        "narration", "autosave", "sound_enabled", "music_enabled", "music_volume", "animations_enabled",
        "portrait_generation_enabled", "portrait_auto_generate", "image_model", "image_provider", "local_image_base_url", "local_image_model", "portrait_quality", "developer_mode",
        "onboarding_seen", "simulation_mode", "canon_foreknowledge", "local_reentry_recap", "local_combat_recap", "local_message_gate"
    ] if k in d}
    settings_game = getattr(g, "worldwalker_personal_game", None) or game
    if any(key in patch for key in ("provider", "local_base_url", "local_token", "api_key", "model", "secondary_model", "major_event_model", "advisor_model", "advisor_provider", "creative_model", "creative_provider")):
        patch.update(ai_connection_status="untested", ai_validated_model="", ai_validated_provider="")
    try:
        settings_game.update_settings(patch)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.route("/api/settings/test_ai", methods=["POST"])
def api_test_ai():
    d = request.get_json(force=True)
    settings_game = getattr(g, "worldwalker_personal_game", None) or game
    current = settings_game.settings
    provider = str(d.get("provider") or current.get("provider") or "local")
    model = str(d.get("model") or current.get("model") or "").strip()
    key = str(d.get("api_key") or current.get("api_key") or "").strip()
    base_url = str(d.get("base_url") or current.get("local_base_url") or "http://localhost:1234/v1").strip()
    token = str(d.get("token") or current.get("local_token") or "").strip()
    if not model:
        return jsonify({"error": "Choose a Main GM model before testing."}), 400
    if provider == "cloud" and not key:
        return jsonify({"error": "Enter an OpenAI API key before testing cloud AI."}), 400
    try:
        client = AI(key=key, model=model, provider=provider, base_url=base_url, local_token=token)
        models = client.list_models(timeout=10)
        if model not in models:
            raise RuntimeError(f"Connected, but {model} is not available to this account/server.")
        settings_game.update_settings({"ai_connection_status": "valid", "ai_validated_model": model,
                                       "ai_validated_provider": provider})
        return jsonify({"ok": True, "model": model, "provider": provider, "models_found": len(models)})
    except Exception as exc:
        settings_game.update_settings({"ai_connection_status": "invalid", "ai_validated_model": "",
                                       "ai_validated_provider": provider})
        return jsonify({"error": f"AI connection failed: {exc}"}), 400


@app.route("/api/settings/detect_models", methods=["POST"])
def api_detect_models():
    d = request.get_json(force=True)
    try:
        settings_game = getattr(g, "worldwalker_personal_game", None) or game
        models = settings_game.detect_models(d.get("base_url", ""), d.get("token", ""))
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------- save / load ----------
@app.route("/api/saves")
def api_saves():
    return jsonify({"saves": game.list_saves()})


@app.route("/api/save", methods=["POST"])
def api_save():
    path = game.save()
    return jsonify({"path": path})


@app.route("/api/save/delete", methods=["POST"])
def api_save_delete():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Leave multiplayer before deleting personal campaign files."}), 409
    try:
        return jsonify(game.delete_save((request.get_json(force=True).get("name") or "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/save/recover", methods=["POST"])
def api_save_recover():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Leave multiplayer before recovering a personal save."}), 409
    try:
        state = game.recover_save(request.get_json(force=True).get("name", ""))
        return jsonify({"state": state, "story": game.story_log})
    except Exception as e:
        return err(e, 400)


@app.route("/api/save/export")
def api_save_export():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    raw = json.dumps(game.save_bundle("export"), indent=2, ensure_ascii=False).encode("utf-8")
    filename = world_slug(game.state.get("name", "Traveler") + "_" + game.state.get("world", "World")) + ".worldwalker.json"
    return send_file(io.BytesIO(raw), mimetype="application/json", as_attachment=True, download_name=filename)


@app.route("/api/save/import", methods=["POST"])
def api_save_import():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Leave multiplayer before importing another campaign."}), 409
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "Choose a Worldwalker JSON export."}), 400
    try:
        raw = uploaded.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise ValueError("Campaign exports must be smaller than 15 MB.")
        return jsonify(game.import_bundle(json.loads(raw.decode("utf-8"))))
    except Exception as e:
        return err(e, 400)


@app.route("/api/load", methods=["POST"])
def api_load():
    if getattr(g, "worldwalker_room", None):
        return jsonify({"error": "Leave multiplayer before loading a personal campaign."}), 409
    d = request.get_json(force=True)
    try:
        state = game.load(d.get("name", ""))
        return jsonify({"state": state, "story": game.story_log})
    except Exception as e:
        return err(e)


@app.route("/api/reentry_recap", methods=["POST"])
def api_reentry_recap():
    try:
        result = game.generate_reentry_recap()
        if not result:
            return jsonify({"recap": "", "state": game.public_state(), "story": []})
        return jsonify(result)
    except Exception as e:
        return err(e)


@app.route("/api/quests/note", methods=["POST"])
def api_quest_note():
    d = request.get_json(force=True)
    try:
        return jsonify({"quest": game.quest_note(d.get("name", ""), d.get("note", ""))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/shop/buy", methods=["POST"])
def api_shop_buy():
    d = request.get_json(force=True)
    try:
        return jsonify(game.buy_shop_item(d.get("shop", ""), d.get("item", "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/purchase_offer/buy", methods=["POST"])
def api_purchase_offer_buy():
    d = request.get_json(force=True)
    try:
        return jsonify(game.buy_purchase_offer(d.get("id", "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/finance/debt/pay", methods=["POST"])
def api_finance_debt_pay():
    d = request.get_json(force=True)
    try:
        return jsonify(game.pay_finance_debt(d.get("id", ""), d.get("amount")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/turn/rate_good", methods=["POST"])
def api_turn_rate_good():
    try:
        return jsonify(game.rate_last_turn_good())
    except Exception as e:
        return err(e, 400)


@app.route("/api/diagnostics")
def api_diagnostics():
    data = game.diagnostics_snapshot()
    data["scene"]["reason"] = scene_selection_reason(game.state)
    data["campaign_health"] = campaign_health(game.state)
    data["npc_knowledge"] = knowledge_snapshot(game.state)
    data["causality"] = causality_snapshot(game.state)
    data["lore_status"] = lore_library_status(game.state.get("world", "Custom World"))
    data["content_audit"] = audit_all_worlds()["summary"]
    return jsonify(data)


@app.route("/api/diagnostics/export")
def api_diagnostics_export():
    data = game.diagnostics_snapshot()
    data["scene"]["reason"] = scene_selection_reason(game.state)
    raw = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(io.BytesIO(raw), mimetype="application/json", as_attachment=True, download_name="worldwalker-diagnostics.json")


@app.route("/api/diagnostics/bundle")
def api_diagnostics_bundle():
    return send_file(build_diagnostic_bundle(game), mimetype="application/zip", as_attachment=True,
                     download_name=f"worldwalker-support-{APP_VERSION}.zip")


@app.route("/api/campaign/health/repair", methods=["POST"])
def api_campaign_health_repair():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign before repairing it."}), 400
    d = request.get_json(silent=True) or {}
    try:
        result = repair_campaign_state(game.state, str(d.get("repair_id") or "safe_all"))
        game.autosave()
        return jsonify({"repair": result, "campaign_health": campaign_health(game.state), "state": game.public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/update", methods=["POST"])
def api_actions_update():
    try:
        d = request.get_json(force=True)
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.update_action(room["id"], user["id"], d.get("index", -1), d.get("action", ""))
                  if room and user else game.update_queued_action(d.get("index", -1), d.get("action", "")))
        return jsonify({"queued_actions": queued})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/move", methods=["POST"])
def api_actions_move():
    try:
        d = request.get_json(force=True)
        room = getattr(g, "worldwalker_room", None)
        user = getattr(g, "worldwalker_user", None)
        queued = (_multiplayer_store.move_action(room["id"], user["id"], d.get("index", -1), d.get("to_index", -1))
                  if room and user else game.move_queued_action(d.get("index", -1), d.get("to_index", -1)))
        return jsonify({"queued_actions": queued})
    except Exception as e:
        return err(e, 400)


@app.route("/api/evaluations")
def api_evaluations():
    return jsonify(list_evaluations())


@app.route("/api/evaluations/local", methods=["POST"])
def api_evaluations_local():
    return jsonify(run_local_simulation_evaluation())


@app.route("/api/evaluations/run", methods=["POST"])
def api_evaluations_run():
    if not _evaluation_lock.acquire(blocking=False):
        return jsonify({"error": "A model evaluation is already running."}), 409
    try:
        d = request.get_json(silent=True) or {}
        ids = d.get("scenario_ids") if isinstance(d.get("scenario_ids"), list) else []
        return jsonify(run_model_evaluation(game, ids))
    except Exception as e:
        return err(e, 400)
    finally:
        _evaluation_lock.release()


@app.route("/api/evaluations/compare", methods=["POST"])
def api_evaluations_compare():
    if not _evaluation_lock.acquire(blocking=False):
        return jsonify({"error": "A model evaluation is already running."}), 409
    try:
        d = request.get_json(silent=True) or {}
        ids = d.get("scenario_ids") if isinstance(d.get("scenario_ids"), list) else []
        models = d.get("models") if isinstance(d.get("models"), list) else []
        return jsonify(run_model_comparison(game, models, ids))
    except Exception as e:
        return err(e, 400)
    finally:
        _evaluation_lock.release()


@app.route("/api/world-packs")
def api_world_packs():
    return jsonify({"loaded": WORLD_PACKS_LOADED, "errors": WORLD_PACK_ERRORS,
                    "folder": str(DATA_DIR / "world_packs")})




# ---------- Living Adventures: server-quoted, confirmed timed actions ----------
def _adventure_identity():
    return str((getattr(g, 'worldwalker_user', None) or {}).get('id') or 'local')


def _adventure_allowed():
    if not game.campaign_active:
        raise ValueError('Start or load a campaign first.')
    if getattr(g, 'worldwalker_room', None):
        raise ValueError('Timed location actions currently use a single-player clock. Shared campaigns must use the multiplayer plan coordinator.')


@app.get('/api/adventures/location')
def api_adventure_location():
    from living_adventures import location_view
    try:
        _adventure_allowed()
        with game.lock:
            return jsonify(location_view(game.state, request.args.get('place')))
    except ValueError as exc:
        return err(exc,400)


@app.get('/api/adventures/routes')
def api_adventure_routes():
    from living_adventures import route_options
    try:
        _adventure_allowed()
        with game.lock:
            return jsonify(route_options(game.state, request.args.get('destination'),request.args.get('preparation','normal'),request.args.get('companion','')))
    except ValueError as exc:
        return err(exc,400)


@app.get('/api/adventures/aftermath')
def api_adventure_aftermath():
    try:
        _adventure_allowed()
        ident=request.args.get('story_id','')
        with game.lock:
            linked=next((r for r in (game.state.get('adventures') or {}).get('aftermath',[]) if r.get('story_id')==ident),None)
            if not linked:raise ValueError('This aftermath does not belong to the current campaign.')
            entry=next((r for r in game.story_log if r.get('id')==ident),None)
            if entry is None:
                entry={'id':ident,'text':linked.get('description','')+' '+ '; '.join(linked.get('changes',[])),'world_time':linked.get('world_time','')}
            return jsonify({'entry':entry})
    except ValueError as exc:return err(exc,400)


@app.post('/api/adventures/preview')
def api_adventure_preview():
    from living_adventures import quote
    from turn_recovery import guard
    from request_receipts import campaign
    try:
        _adventure_allowed()
        raw=request.get_json(force=True)
        if not isinstance(raw,dict):raise ValueError('An activity object is required.')
        payload={k:raw[k] for k in ('place','action','destination','route_id','preparation','companion') if k in raw}
        with game.lock:
            result=quote(game.state,payload)
            ticket={'account':_adventure_identity(),'campaign':campaign(game.state),'guard':guard(game.state),'payload':payload,'spec':result['spec']}
            result['token']=URLSafeTimedSerializer(app.secret_key,salt='adventure-confirmation-v1').dumps(ticket)
            result['expected_campaign']=ticket['campaign'];result['expected_guard']=ticket['guard']
        return jsonify(result)
    except (ValueError,TypeError) as exc:
        return err(exc,400)


@app.post('/api/adventures/resolve')
def api_adventure_resolve():
    from living_adventures import action_spec, resolve
    from request_receipts import campaign, completed
    from turn_recovery import guard
    if not acquire_busy():return busy_error()
    try:
        _adventure_allowed()
        payload=request.get_json(force=True)
        if not isinstance(payload,dict) or payload.get('confirmed') is not True or not payload.get('request_id'):
            raise ValueError('Confirm the preview and supply a request ID before resolving.')
        # Receipt recovery must work even after the confirmation ticket expires.
        with game.lock:
            cached=completed(game,payload['request_id'],'adventure_resolve',payload)
            if cached is not None:return jsonify(cached)
            try:ticket=URLSafeTimedSerializer(app.secret_key,salt='adventure-confirmation-v1').loads(payload.get('token',''),max_age=600)
            except (BadSignature,SignatureExpired):raise ValueError('This confirmation expired. Review the activity again.')
            if ticket.get('account')!=_adventure_identity() or ticket.get('campaign')!=campaign(game.state):
                raise ValueError('This confirmation belongs to another player or campaign.')
            failed=game.state.get('last_failed_turn') or {}
            resumable=(failed.get('route')=='adventure_resolve' and failed.get('payload')==payload and
                       (failed.get('work') or {}).get('guard')==guard(game.state))
            if ticket.get('guard')!=guard(game.state) and not resumable:
                raise ValueError('The campaign changed after this quote. Review the activity again.')
            if payload.get('expected_campaign')!=ticket['campaign'] or payload.get('expected_guard')!=ticket['guard']:
                raise ValueError('The confirmation does not match the prepared campaign state.')
            spec=action_spec(game.state,ticket['payload'])
            if spec!=ticket['spec']:raise ValueError('The available activity changed. Review it again.')
            return jsonify(atomic_game_call('adventure_resolve',payload,lambda:resolve(game,ticket['payload'],spec)))
    except (ValueError,TypeError) as exc:
        return err(exc,400)
    except Exception as exc:
        return err(exc)
    finally:
        release_busy()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=True, threaded=True, use_reloader=False)
