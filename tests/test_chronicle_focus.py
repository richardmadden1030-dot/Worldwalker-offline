from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_new_turn_focus_uses_geometry_from_same_scroll_coordinate_system():
    source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert "feed.scrollTop + beatRect.top - feedRect.top" in source
    assert "firstNewBeat.offsetTop - feed.offsetTop" not in source


def test_completed_turn_requests_focus_on_first_new_beat():
    source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert "appendStoryEntries(result.story, { focusNew: true });" in source
    assert "if (!firstNewBeat) firstNewBeat = beat;" in source
