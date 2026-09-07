from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_action_deck_preserves_freeform_and_adds_contextual_actions():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = "\n".join((ROOT / "frontend" / "js" / name).read_text(encoding="utf-8") for name in ("app.js", "action-deck.js"))
    assert 'id="modal-action-deck"' in html
    assert 'id="action-deck-write"' in html
    assert "Rest and recover" in js
    assert "Get proper sleep" in js
    assert "Treat this as a standing instruction" in js
    assert "worldActionChoices" in js


def test_relationship_portraits_open_person_specific_actions():
    js = "\n".join((ROOT / "frontend" / "js" / name).read_text(encoding="utf-8") for name in ("app.js", "action-deck.js"))
    assert "data-interact-person" in js
    assert "personInteractionChoices" in js
    assert "openActionDeck(personName = \"\")" in js


def test_action_deck_is_phone_ready_and_accessible():
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".action-deck-backdrop{ align-items:flex-end" in css
    assert ".action-deck-trigger:focus-visible" in css
    assert "prefers-reduced-motion:reduce" in css
