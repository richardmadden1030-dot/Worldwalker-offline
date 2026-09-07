import copy

from arc_director import advance, discover, snapshot
from worlds import BASE_STATE


def campaign():
    state = copy.deepcopy(BASE_STATE)
    state.update(world="One Piece", name="Aiko", turn=1, location="Dawn Island")
    state["quests"] = [{"name": "Free Dawn Island", "status": "Active", "progress_percent": 10}]
    return state


def test_active_quest_becomes_optional_campaign_arc():
    state = campaign()
    arcs = discover(state)
    assert arcs[0]["title"] == "Free Dawn Island"
    assert arcs[0]["available_approaches"] == [
        "pursue it directly", "investigate before committing", "seek allies or negotiate", "withdraw or let the opportunity pass"
    ]


def test_unrelated_action_does_not_advance_arc():
    state = campaign(); discover(state)
    before = state["campaign_arcs"][0]["progress"]
    advance(state, ["Eat breakfast with the crew"], [], 60)
    assert state["campaign_arcs"][0]["progress"] == before


def test_relevant_choices_move_arc_only_when_they_touch_it():
    state = campaign(); discover(state)
    for turn in range(1, 6):
        state["turn"] = turn
        result = advance(state, ["Investigate how to free Dawn Island"], [], 60)
    assert state["campaign_arcs"][0]["phase"] in {"developing", "escalating"}
    assert any(beat["type"] == "arc_transition" for beat in result["beats"])


def test_explicit_resolution_creates_epilogue_and_quiet_period():
    state = campaign(); discover(state)
    state["campaign_arcs"][0]["progress"] = 80
    state["turn"] = 10
    result = advance(state, ["Negotiate peace to free Dawn Island"],
                     [{"title": "Agreement", "narrative": "Free Dawn Island is completed through a binding peace agreement."}], 60)
    assert result["beats"][0]["type"] == "arc_resolution"
    assert state["campaign_arc_archive"][-1]["resolution"]["method"] == "agreement"
    assert snapshot(state)["quiet_period"] is True
    assert "unrelated punishment" in state["campaign_arc_archive"][-1]["resolution"]["epilogue"]


def test_repeated_training_can_become_development_arc_without_ai():
    state = campaign(); state["quests"] = []
    state["living_world"] = {"patterns": {"training": 3}}
    discover(state)
    arc = state["campaign_arcs"][0]
    assert arc["kind"] == "development"
    assert "instruction" in " ".join(arc["available_approaches"])


def test_quest_completed_elsewhere_still_closes_its_arc():
    state = campaign(); discover(state)
    state["quests"] = []
    state["quest_archive"] = [{"name": "Free Dawn Island", "status": "Completed"}]
    state["turn"] = 7
    result = advance(state, [], [], 0)
    assert result["beats"][0]["type"] == "arc_resolution"
    assert state["campaign_arc_archive"][-1]["resolution"]["method"] == "completion"
