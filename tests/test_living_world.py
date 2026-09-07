import copy

from living_world import advance, interpretation, record_outcome
from worlds import BASE_STATE


def state():
    value = copy.deepcopy(BASE_STATE)
    value.update(world="Naruto", turn=1, name="Aiko", location="Konoha")
    return value


def test_interpretation_exposes_duration_target_and_standing_intent():
    view = interpretation("Keep training with Kakashi for one month", state())
    assert view["activity"] == ["training"]
    assert view["targets"] == ["Kakashi"]
    assert view["duration"] == "one month"
    assert view["standing"] is True


def test_ambiguous_general_action_requires_confirmation():
    view = interpretation("Do something about it", state())
    assert view["ambiguous"] is True
    assert view["ambiguity_reasons"]


def test_repeated_behavior_creates_causal_follow_up_not_random_crisis():
    value = state()
    results = []
    for turn in range(1, 4):
        value["turn"] = turn
        results.append(advance(value, ["Train taijutsu"], 60, []))
    assert not results[0]["events"] and not results[1]["events"]
    event = results[2]["events"][0]
    assert event["pattern"] == "training"
    assert event["source_action"] == "Train taijutsu"
    assert "sustained practice" in event["why_it_matters"]


def test_outcome_variety_is_recorded_locally():
    value = state()
    assert record_outcome(value, {"narrative": "The lesson succeeds."}, ["Train"]) == "clean_success"
    assert record_outcome(value, {"causal_outcome": {"direct_result": "You succeed", "complications": ["Late"]}}, ["Train"]) == "mixed"
    assert [row["kind"] for row in value["living_world"]["outcome_history"]] == ["clean_success", "mixed"]


def test_recorded_goal_is_not_pasted_into_fabricated_dialogue():
    value = state()
    value["turn"] = 4
    value["npc_memories"] = {"Kakashi": {"recurring": True, "goal": "your next team exercise"}}
    result = advance(value, [], 5, [])
    assert result["incoming_chats"] == []
    # v3.62 uses shared-experience candidates in the existing narrator call.
    # A generic goal, without a resolved exchange or delivery route, is not one.
    from relationship_life import candidates
    assert candidates(value) == []
