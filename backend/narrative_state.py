"""Cross-record consequences for explicitly settled outcomes, not free-text guesses."""
from npc_identity import resolve_records


def record_npc_death(state, target, evidence):
    """Keep historical membership; update only an unambiguous known identity."""
    matches = resolve_records(state, target)
    for _, row, membership in matches:
        row.update(status='dead', alive=False, death_reason=evidence)
        if membership:
            row['membership_status'] = 'dead'
    return bool(matches)
