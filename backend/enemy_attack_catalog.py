"""Prewritten NPC attack presets. No model call, per-fight text generation or
player-ability archive access is involved in selecting these records.

These names describe actions, not newly granted canon powers. An established
named technique keeps its own name and borrows the matching mechanical preset.
"""
from __future__ import annotations
import copy

GRADE_NAMES = ('Basic', 'Practiced', 'Advanced', 'Elite', 'Master', 'Exceptional')
POWER_THRESHOLDS = (35, 90, 200, 600, 1000)
PATTERNS = {
    'strike': ({'shape': 'single', 'range': 1, 'origin': 'target'},
               ('Quick strike', 'Firm strike', 'Driving strike', 'Crushing strike', 'Decisive strike', 'Overwhelming strike')),
    'projectile': ({'shape': 'single', 'range': 5, 'origin': 'target'},
                   ('Quick shot', 'Aimed shot', 'Precision shot', 'Piercing shot', 'Decisive shot', 'Overwhelming shot')),
    'sweep': ({'shape': 'arc', 'range': 1, 'width': 3, 'origin': 'self'},
              ('Short sweep', 'Wide sweep', 'Driving sweep', 'Crushing sweep', 'Decisive sweep', 'Overwhelming sweep')),
    'beam': ({'shape': 'line', 'length': 5, 'width': 1, 'origin': 'self'},
             ('Narrow beam', 'Focused beam', 'Piercing beam', 'Heavy beam', 'Concentrated beam', 'Overwhelming beam')),
    'breath': ({'shape': 'cone', 'length': 3, 'origin': 'self'},
               ('Short breath', 'Directed breath', 'Broad breath', 'Heavy breath', 'Concentrated breath', 'Overwhelming breath')),
    'blast': ({'shape': 'burst', 'range': 4, 'radius': 1, 'origin': 'target'},
              ('Small blast', 'Focused blast', 'Heavy blast', 'Spreading blast', 'Devastating blast', 'Overwhelming blast')),
    'pulse': ({'shape': 'burst', 'range': 0, 'radius': 2, 'origin': 'self'},
              ('Short pulse', 'Driving pulse', 'Heavy pulse', 'Expanding pulse', 'Crushing pulse', 'Overwhelming pulse')),
    'binding': ({'shape': 'single', 'range': 4, 'origin': 'target'},
                ('Brief restraint', 'Binding restraint', 'Firm restraint', 'Heavy restraint', 'Layered restraint', 'Overwhelming restraint')),
    'weakening': ({'shape': 'single', 'range': 4, 'origin': 'target'},
                  ('Disrupting hit', 'Weakening hit', 'Crippling hit', 'Debilitating hit', 'Severe disruption', 'Overwhelming disruption')),
    'shield': ({'shape': 'self', 'range': 0, 'origin': 'self'},
               ('Brief barrier', 'Focused barrier', 'Reinforced barrier', 'Heavy barrier', 'Layered barrier', 'Overwhelming barrier')),
    'heal': ({'shape': 'self', 'range': 0, 'origin': 'self'},
             ('Minor recovery', 'Focused recovery', 'Restorative recovery', 'Major recovery', 'Deep recovery', 'Exceptional recovery')),
}

# Built once on import from fixed authoring data; identical ID means identical
# mechanics in every fight. Power comes from the NPC, never from the player.
ATTACK_LIBRARY = {}
for _family, (_shape, _names) in PATTERNS.items():
    for _grade, _name in enumerate(_names):
        _id = f'{_family}-{_grade}'
        _effect = {'binding': 'control', 'weakening': 'debuff', 'shield': 'shield', 'heal': 'heal'}.get(_family, 'damage')
        ATTACK_LIBRARY[_id] = {
            'id': _id, 'name': _name, 'family': _family, 'grade': _grade,
            'grade_label': GRADE_NAMES[_grade], 'effect_type': _effect,
            'tactical': {**_shape, 'effect': _effect},
            'damage_multiplier': (.85, 1, 1.1, 1.2, 1.35, 1.5)[_grade],
            'resource_cost': 0 if _family == 'strike' else (5, 8, 11, 14, 18, 22)[_grade],
            'cooldown': 0 if _family in {'strike', 'projectile', 'sweep'} else 2,
            'duration_rounds': 1 if _grade < 3 else 2,
            'status_potency': (10, 15, 20, 25, 30, 35)[_grade],
            'status_effect': 'Restrained' if _family == 'binding' else 'Weakened' if _family == 'weakening' else '',
            'source': 'prewritten enemy attack library',
        }


def grade_for(power):
    return sum(float(power or 0) >= threshold for threshold in POWER_THRESHOLDS)


def attack_for(family, power, established_name=''):
    row = copy.deepcopy(ATTACK_LIBRARY[f'{family}-{grade_for(power)}'])
    if established_name:
        row['name'] = established_name
        row['source'] = 'established technique; prewritten mechanics'
    return row
