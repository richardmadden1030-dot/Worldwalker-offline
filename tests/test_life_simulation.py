import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from life_simulation import advance, normalize, resolve_choice, record_legacy
from state_guard import migrate_state
from worlds import BASE_STATE


def state(world="Naruto"):
    value = copy.deepcopy(BASE_STATE)
    value.update({"world": world, "name": "Ari", "canon_day": 100, "turn": 12})
    return value


def test_old_save_migrates_life_engine_and_context():
    old = {"world": "One Piece", "name": "Mara", "schema_version": 20,
           "companions": [{"name": "Nami", "role": "Navigator"}]}
    migrated = migrate_state(old, "3.54.0")
    assert migrated["schema_version"] == 21
    assert migrated["life_simulation"]["version"] == 1
    assert migrated["life_context"]["world_terms"]["group"] == "crew"


def test_companion_goal_and_relationship_phase_are_shared_context():
    value = state()
    value["companions"] = [{"name": "Konan", "role": "Partner"}]
    value["npc_memories"] = {"Konan": {"goal": "Protect Amegakure", "recurring": True}}
    value["contacts"] = {"Konan": {"relationship": 70, "why": "Years of shared struggle"}}
    advance(value, [], [], 5)
    assert value["life_context"]["people"][0]["active_goal"] == "Protect Amegakure"
    relation = value["life_context"]["relationship_phases"][0]
    assert relation["phase"] == "Close"
    assert relation["why"] == "Years of shared struggle"


def test_standing_mentorship_develops_without_inventing_promotion():
    value = state()
    advance(value, ["Train Mirai in taijutsu every morning"], [], 5)
    value["canon_day"] += 90
    result = advance(value, [], [], 90 * 1440)
    assert any("Development" in event["title"] for event in result["events"])
    assert not any(event.get("kind") == "promotion" for event in value["life_simulation"]["event_history"])


def test_family_milestone_requires_choice_and_resolves_locally():
    value = state()
    value["contacts"] = {"Konan": {"relationship": 85, "notes": "romantic partner"}}
    result = advance(value, ["I ask Konan if she wants to start a family"], [], 5)
    choice = result["pending_choices"][0]
    assert choice["requires_player_choice"] is True
    assert not value["life_simulation"]["event_history"]
    event = resolve_choice(value, choice["id"], "wait")
    assert event["type"] == "life"
    assert not value["life_simulation"]["pending_choices"]
    assert value["life_simulation"]["event_history"][-1]["decision"] == "Not yet"


def test_only_explicit_authored_life_events_are_recorded():
    value = state("Bleach")
    value["companions"] = [{"name": "Rukia", "role": "Soul Reaper"}]
    ordinary = advance(value, [], [{"title": "Patrol", "narrative": "Rukia completes an ordinary patrol."}], 30 * 1440)
    assert not ordinary["events"]
    promoted = advance(value, [], [{"title": "Division Ceremony", "narrative": "Rukia was promoted after sustained service."}], 5)
    assert promoted["events"][0]["title"] == "Rukia — Promotion"


def test_world_specific_legacy_terms_and_deduplication():
    value = state("One Piece")
    first = record_legacy(value, "Freeing Dawn Island", "The crew broke the governor's rule.", "deed", ["Mina"])
    second = record_legacy(value, "Freeing Dawn Island", "The crew broke the governor's rule.", "deed", ["Mina"])
    assert first["world_term"] == "inherited will"
    assert second is None
    assert len(value["life_simulation"]["legacy_records"]) == 1
