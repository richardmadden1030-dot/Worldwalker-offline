"""Player-visible receipts derived only from settled state, never narrative guesses.

A receipt reports net changes, not a second reward calculation. In particular,
XP rollover is shown as before/after progress rather than invented 'XP earned'.
"""
import copy
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from reliability import visible_skills, visible_class_profile
from worlds import uses_xp_for


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) else []


def text(value, limit=240):
    return str(value or "")[:limit]


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def name(value):
    return text(value.get('name') or value.get('title')) if isinstance(value, dict) else text(value)


def quantities(value):
    out = {}
    for item in rows(value):
        label = name(item)
        if not label:
            continue
        quantity = obj(item).get('quantity', obj(item).get('qty', obj(item).get('count', 1)))
        if not number(quantity):
            quantity = 1
        key = label.casefold()
        old = out.get(key, (label, 0))
        out[key] = (label, old[1] + max(0, quantity))
    return out


def quests(state):
    out = {}
    for row in rows(state.get('quest_archive')) + rows(state.get('quests')):
        if isinstance(row, dict) and name(row):
            out[name(row).casefold()] = row
    return out


def _money(currency):
    c = obj(currency)
    try:
        scale = Decimal(str(c.get('minor_per_major') or 1))
        value = Decimal(str(c['amount_minor'])) / scale if scale > 1 and 'amount_minor' in c else Decimal(str(c.get('amount', 0)))
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return None


def build_turn_receipt(before, after, route, request_id='', story_changed=False):
    """Return None for an uncommitted/no-op confirmation, else one bounded record."""
    before, after = obj(before), obj(after)
    changes = []
    def add(kind, label, old, new):
        if old != new:
            changes.append({'kind': kind, 'label': text(label), 'before': old, 'after': new})
    literal = uses_xp_for(after.get('world', 'Custom World'), after.get('custom_world', ''))
    for key, label in [('hp', 'HP'), ('hp_max', 'Maximum HP'), ('resource', after.get('resource_name') or 'Energy'),
                       ('resource_max', 'Maximum ' + text(after.get('resource_name') or 'Energy'))]:
        if number(before.get(key)) and number(after.get(key)):
            add(key, label, before[key], after[key])
    if literal:
        if number(before.get('level')) and number(after.get('level')):
            add('level', 'Level', before['level'], after['level'])
        if number(before.get('xp')) and number(after.get('xp')):
            if before.get('level') == after.get('level'):
                add('xp', 'XP progress', before['xp'], after['xp'])
            elif before.get('xp') != after.get('xp') or before.get('level') != after.get('level'):
                add('xp_rollover', 'XP progress (level changed)',
                    f"Level {before.get('level', '?')}: {before['xp']}", f"Level {after.get('level', '?')}: {after['xp']}")
    for label, value in obj(after.get('stats')).items():
        old = obj(before.get('stats')).get(label)
        if number(old) and number(value):
            add('stat', label, old, value)
    old_skills, new_skills = visible_skills(before), visible_skills(after)
    old_names = {k.casefold(): k for k in old_skills}
    new_names = {k.casefold(): k for k in new_skills}
    for key in sorted(old_names.keys() | new_names.keys()):
        if key not in old_names:
            add('skill', new_names[key], 'Not learned', 'Learned')
        elif key not in new_names:
            add('skill', old_names[key], 'Learned', 'No longer available')
        else:
            old, new = obj(old_skills[old_names[key]]), obj(new_skills[new_names[key]])
            for field in ('rank', 'level', 'mastery'):
                if field in old and field in new and isinstance(old[field], (str, int, float)) and isinstance(new[field], (str, int, float)):
                    add('skill_progress', new_names[key] + ' · ' + field, old[field], new[field])
    old_titles = {name(t).casefold(): name(t) for t in rows(before.get('titles')) if name(t)}
    new_titles = {name(t).casefold(): name(t) for t in rows(after.get('titles')) if name(t)}
    for key in sorted(new_titles.keys() - old_titles.keys()):
        add('title', new_titles[key], 'Not held', 'Earned')
    old_class, new_class = visible_class_profile(before), visible_class_profile(after)
    add('class', 'Class', text(obj(old_class).get('name')) or 'None revealed', text(obj(new_class).get('name')) or 'None revealed')
    old_items, new_items = quantities(before.get('inventory')), quantities(after.get('inventory'))
    for key in sorted(old_items.keys() | new_items.keys()):
        old = old_items.get(key, (new_items.get(key, ('Item', 0))[0], 0))
        new = new_items.get(key, (old[0], 0))
        add('item', new[0], old[1], new[1])
    for slot in sorted(obj(before.get('equipment')).keys() | obj(after.get('equipment')).keys()):
        add('equipment', slot, name(obj(before.get('equipment')).get(slot)) or 'Empty', name(obj(after.get('equipment')).get(slot)) or 'Empty')
    old_money, new_money = obj(before.get('currency')), obj(after.get('currency'))
    if new_money.get('tracked') is not False and old_money.get('name') == new_money.get('name'):
        old, new = _money(old_money), _money(new_money)
        if old is not None and new is not None:
            add('currency', new_money.get('name') or 'Currency', format(old, "f"), format(new, "f"))
    old_quests, new_quests = quests(before), quests(after)
    for key, row in new_quests.items():
        old = old_quests.get(key)
        label = name(row)
        if old is None:
            add('quest', label, 'Not recorded', text(row.get('status') or 'Active'))
        elif text(old.get('status') or 'Active').casefold() != text(row.get('status') or 'Active').casefold():
            add('quest', label, text(old.get('status') or 'Active'), text(row.get('status') or 'Active'))
        elif number(old.get('progress_percent')) and number(row.get('progress_percent')):
            add('quest_progress', label, old['progress_percent'], row['progress_percent'])
    add('location', 'Location', text(before.get('location')), text(after.get('location')))
    for who, record in obj(after.get('relationships')).items():
        old = obj(before.get('relationships')).get(who)
        old_score = obj(old).get('score') if isinstance(old, dict) else old
        new_score = obj(record).get('score') if isinstance(record, dict) else record
        if number(old_score) and number(new_score):
            add('relationship', who, old_score, new_score)
    # canon_time_minutes is an absolute campaign clock, not minutes within a day.
    elapsed = None
    if number(before.get('canon_time_minutes')) and number(after.get('canon_time_minutes')):
        elapsed = max(0, after['canon_time_minutes'] - before['canon_time_minutes'])
    turn_changed = before.get('turn') != after.get('turn')
    if not changes and not elapsed and not turn_changed and not story_changed:
        return None
    attention = []
    question = text(obj(after.get('scene_state')).get('unresolved_question'), 360)
    if question:
        attention.append(question)
    for obligation in rows(after.get('obligation_ledger')):
        owner = text(obj(obligation).get('owner')).casefold()
        if owner not in {text(after.get('name')).casefold(), 'player', 'you'}:
            continue
        if obj(obligation).get('status') == 'due':
            attention.append('Due: ' + text(obligation.get('text') or obligation.get('promise')))
    result = {'schema': 1, 'turn': after.get('turn', 0), 'world': after.get('world', 'Custom World'),
              'label': 'System results' if literal else 'Recorded outcome', 'route': text(route, 80),
              'world_time': text(after.get('world_time')), 'elapsed_minutes': elapsed,
              'changes': changes[:80], 'additional_changes': max(0, len(changes)-80), 'attention': attention[:3],
              'note': 'Net recorded changes. No extra rewards are awarded by this summary.'}
    signature = json.dumps([after.get('campaign_id'), request_id, result], sort_keys=True, ensure_ascii=False, default=str)
    result['id'] = hashlib.sha256(signature.encode('utf-8')).hexdigest()[:24]
    return result
