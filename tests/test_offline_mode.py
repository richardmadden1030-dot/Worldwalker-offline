import pathlib
import tempfile

import pytest

from game import GameSession
from worlds import WORLD_DATA, WORLD_EXPANSIONS
from tactical_combat import ensure_board


WORLDS = [
    "Naruto", "One Piece", "Hunter x Hunter", "Bleach", "Jujutsu Kaisen",
    "Overgeared", "Solo Max-Level Newbie", "Reincarnated as a Slime", "Custom World",
]


class ExplodingAI:
    def request(self, *args, **kwargs):
        raise AssertionError("Offline Mode must never call the AI client")
    def list_models(self, *args, **kwargs):
        raise AssertionError("Offline Mode must never inspect models during play")


def make_game(world="Naruto"):
    game = GameSession()
    tmp = tempfile.TemporaryDirectory()
    game._offline_test_tmp = tmp
    game.settings_path = pathlib.Path(tmp.name) / "settings.json"
    game.settings["offline_mode"] = True
    game.settings["autosave"] = False
    game.ai = ExplodingAI(); game.ai_bg = ExplodingAI(); game.ai_major = ExplodingAI()
    ex = WORLD_EXPANSIONS[world]
    origin = (ex.get("origins") or ["Local"])[0]
    archetype = (ex.get("archetypes") or [""])[0]
    game.new_campaign(
        name="Offline Tester", world=world, difficulty="Adventurer",
        background="A grounded character ready to live in this world.", appearance_desc="Dark hair and practical clothes.",
        custom_world="A grounded fantasy world." if world == "Custom World" else "",
        origin=origin, archetype=archetype, stats={}, start_location=WORLD_DATA[world]["start"],
    )
    game.autosave = lambda *a, **k: None
    return game


@pytest.mark.parametrize("world", WORLDS)
def test_offline_opening_and_activity_never_need_ai(world):
    game = make_game(world)
    result = game.offline_opening()
    assert result["offline"] is True
    assert result["state"]["opening_complete"] is True
    assert result["state"]["world"] == world
    action = "travel-explore"
    result = game.offline_action(action, "Explore nearby")
    assert result["offline"] is True
    assert result["state"]["turn"] >= 1


def test_board_is_stable_for_same_day_and_accepts_offer():
    game = make_game("Naruto")
    game.offline_opening()
    first = game.offline_action("naruto-mission", "Review mission opportunities")["state"]["offline_mode"]["mission_board"]
    second = game.offline_action("naruto-mission", "Review mission opportunities")["state"]["offline_mode"]["mission_board"]
    assert first == second
    offer = first[0]
    state = game.offline_action(f"offline-accept:{offer['id']}", f"Accept {offer['name']}")["state"]
    assert any((q.get("offline_data") or {}).get("id") == offer["id"] for q in state["quests"] if isinstance(q, dict))


def test_training_has_same_day_diminishing_returns():
    game = make_game("Naruto")
    game.offline_opening()
    for _ in range(5):
        game.offline_action("training-stats", "Condition the body")
    bucket = game.state["offline_mode"]["daily"][str(game.state["canon_day"])]
    assert bucket["training"] >= 5
    assert game.state["training_log"][-1]["effective"] is False


def test_relationship_spam_is_capped():
    game = make_game("Naruto")
    game.state.setdefault("contacts", {})["Kakashi"] = {"relationship": 0}
    game.state.setdefault("npc_memories", {})["Kakashi"] = {"relationship": 0, "last_known_location": game.state["location"]}
    for _ in range(5):
        game.offline_action("spend:Kakashi", "Spend time together", person="Kakashi")
    assert game.state["contacts"]["Kakashi"]["relationship"] <= 5


def test_hunt_uses_existing_legacy_combat_and_completes_after_victory():
    game = make_game("Custom World")
    game.offline_opening()
    game.offline_action("missions-work", "Review opportunities")
    # Force a hunt offer so the test is deterministic about the combat route.
    offer = {"id":"hunt-test","name":"Hunt: Bandit Captain","kind":"hunt","giver":"Local contact","destination":game.state["location"],"target":"Bandit Captain","objective":"Find and defeat Bandit Captain.","reward":50,"expires_day":game.state["canon_day"]+3}
    game.state["offline_mode"]["mission_board"] = [offer]
    game.offline_action("offline-accept:hunt-test", "Accept hunt")
    result = game.offline_action("quest:Hunt: Bandit Captain", "Work on Hunt: Bandit Captain")
    assert result["combat_active"] is True
    assert game.state["combat"]["offline_generated"] is True
    game.end_combat("victory")
    completed = game.offline_sync_combat_missions()
    assert "Hunt: Bandit Captain" in completed
    assert not any(q.get("name") == "Hunt: Bandit Captain" for q in game.state["quests"] if isinstance(q, dict))
    quest = next(q for q in game.state["quest_archive"] if q.get("name") == "Hunt: Bandit Captain")
    assert quest["status"] == "Completed"


@pytest.mark.parametrize("world", ["Naruto", "One Piece", "Bleach"])
def test_offline_combat_enters_existing_tactical_board(world):
    game = make_game(world)
    game.offline_opening()
    result = game.offline_action("combat-patrol", "Patrol for danger")
    assert result["combat_active"] is True
    assert game.state["combat"]["tactical_enabled"] is True
    board = ensure_board(game.state)
    assert board and any(unit.get("player") for unit in board["units"])
    assert any(unit.get("side") == "enemy" for unit in board["units"])


def test_storylet_choice_persists_and_clears_pending_event():
    game = make_game("Naruto")
    # Install an event directly so the choice resolver can be tested without relying on the 24% trigger.
    event = {"id":"evt","title":"Development","prompt":"A report conflicts with local claims.","person":"Kakashi","options":[{"id":"evt:0","label":"Investigate"},{"id":"evt:1","label":"Report it"},{"id":"evt:2","label":"Ignore it"}]}
    game._offline_root()["pending_event"] = event
    result = game.offline_event_choice("evt", "evt:0")
    assert result["offline"] is True
    assert game.state["offline_mode"]["pending_event"] is None
    assert game.state["offline_mode"]["storylet_history"][-1]["choice"] == "Investigate"


def test_public_state_exposes_real_world_map_destinations_only_in_offline_mode():
    game = make_game("Naruto")
    state = game.public_state()
    assert "_offline_locations" in state
    assert "Konohagakure" in state["_offline_locations"]


def test_offline_build_defaults_to_offline_mode():
    from engine_core import DEFAULT_SETTINGS as CORE_DEFAULTS
    assert CORE_DEFAULTS["offline_mode"] is True


def test_existing_story_authored_quest_gets_safe_offline_progress_contract():
    game = make_game("Naruto")
    game.state["quests"] = [{
        "name": "Protect the bridge builder",
        "status": "Active",
        "description": "Keep the bridge builder safe through the current assignment.",
        "objectives": [{"id":"obj-1", "text":"Protect the bridge builder", "status":"active", "progress":0, "optional":False}],
    }]
    before_day = game.state["canon_day"]
    result = game.offline_action("quest:Protect the bridge builder", "Work on Protect the bridge builder")
    quest = next(q for q in game.state["quests"] if q.get("name") == "Protect the bridge builder")
    assert quest["offline_data"]["converted_from_story_quest"] is True
    assert 0 < quest["offline_data"]["progress"] < 100
    assert game.state["canon_day"] >= before_day
    assert result["offline"] is True


def test_active_canon_event_has_local_resolution_without_ai():
    game = make_game("Naruto")
    game.state["active_canon_event"] = "Academy graduation night — the Mizuki incident"
    game.state["active_event_context"] = "A dangerous betrayal is unfolding around the village archive."
    result = game.offline_action("offline-canon:protect", "Protect people and limit harm")
    assert result["offline"] is True
    assert game.state["active_canon_event"] == ""
    assert any("EVENT CONCLUDED" in str(row.get("text") or row.get("outcome") or "") for row in result["story"])
