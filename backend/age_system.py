"""Deterministic character-age tracking tied to the campaign calendar."""
import re


_WHOLE_AGE_RE = re.compile(r"^\s*(\d{1,5})(?:\s*(?:years?|yrs?)\s*(?:old)?)?\s*$", re.I)


def numeric_age(value):
    """Return a whole chronological age, or None for unknown/descriptive ages."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None
    match = _WHOLE_AGE_RE.match(str(value or ""))
    return int(match.group(1)) if match else None


def _calendar_year(state):
    calendar = state.get("calendar") if isinstance(state.get("calendar"), dict) else {}
    try:
        return max(1, int(calendar.get("year", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _store_age_like(state, original, value):
    state["age"] = str(value) if isinstance(original, str) else value


def initialize_age_tracking(state, repair_elapsed=False, reset=False):
    """Seed age anchors and optionally repair saves from before age tracking.

    Old saves stored the starting age unchanged even when their calendar had
    reached Year 2 or later. For those saves, the current calendar year is the
    only deterministic evidence available, so each completed 360-day campaign
    year is applied once and the new anchor prevents a second adjustment.
    """
    current_year = _calendar_year(state)
    raw_age = state.get("age", "")
    age = numeric_age(raw_age)
    if reset or state.get("age_at_campaign_start", "") in (None, ""):
        state["age_at_campaign_start"] = raw_age if age is not None else ""
    if repair_elapsed and age is not None:
        _store_age_like(state, raw_age, age + max(0, current_year - 1))
    if reset or state.get("age_anchor_year") in (None, "") or repair_elapsed:
        state["age_anchor_year"] = current_year


def advance_character_age(state, before):
    """Advance chronological age for every campaign-year boundary crossed."""
    raw_age = state.get("age", "")
    age = numeric_age(raw_age)
    if age is None:
        return None
    if state.get("age_at_campaign_start", "") in (None, ""):
        state["age_at_campaign_start"] = raw_age
    before_year = _calendar_year(before)
    after_year = _calendar_year(state)
    try:
        anchor_year = max(1, int(state.get("age_anchor_year", before_year) or before_year))
    except (TypeError, ValueError):
        anchor_year = before_year
    completed_years = max(0, after_year - anchor_year)
    state["age_anchor_year"] = max(anchor_year, after_year)
    if not completed_years:
        return None
    new_age = age + completed_years
    _store_age_like(state, raw_age, new_age)
    return {"previous_age": age, "age": new_age, "years": completed_years}
