"""Civil world dates, independent of elapsed campaign/age counters.

The simulation's canon offsets remain stable across saves and starting eras.
Precision/provenance accompanies dates rather than inventing a universal canon
calendar. Calendar math is Gregorian and timezone-free in both Python and JS.
"""
from __future__ import annotations
import calendar
import copy
import datetime as dt
import json
import math
from pathlib import Path
import sys

_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
PROFILES = json.loads((_ROOT / 'assets' / 'data' / 'world_calendars.json').read_text(encoding='utf-8'))
MONTHS = ('January','February','March','April','May','June','July','August','September','October','November','December')


def profile_for(world, epoch=None, anchor_day=None):
    profile = copy.deepcopy(PROFILES.get(str(world), PROFILES['Custom World']))
    # Existing Earth/custom saves deliberately used a player-local start date.
    # Preserve it; new campaigns use the fixed world epoch by leaving it empty.
    if world in {'Solo Max-Level Newbie', 'Custom World'} and epoch:
        try:
            date = dt.date.fromisoformat(str(epoch))
            profile.update(epoch=date.isoformat(), anchor_day=int(anchor_day if anchor_day is not None else (-3 if world == 'Solo Max-Level Newbie' else -7)), era='', year_offset=0,
                           precision='saved campaign epoch', note='Preserved explicit date from this campaign save.')
        except (ValueError, TypeError, OverflowError):
            pass
    return profile


def date_for(world, canon_day, epoch=None, anchor_day=None):
    p = profile_for(world, epoch, anchor_day)
    try:
        day = int(canon_day)
        return dt.date.fromisoformat(p['epoch']) + dt.timedelta(days=day - p['anchor_day'])
    except (ValueError, TypeError, OverflowError):
        return None


def parts_for(world, canon_day, epoch=None, anchor_day=None):
    date = date_for(world, canon_day, epoch, anchor_day)
    if date is None:
        return None
    p = profile_for(world, epoch, anchor_day)
    return {'year':date.year + p['year_offset'], 'month':date.month, 'day':date.day,
            'iso':date.isoformat(), 'era':p['era'], 'calendar':p['label'], 'precision':p['precision']}


def format_date(world, canon_day, epoch=None, anchor_day=None):
    p = parts_for(world, canon_day, epoch, anchor_day)
    if p is None:
        return 'Date outside supported calendar range'
    suffix = f"{p['era']} {p['year']}" if p['era'] else str(p['year'])
    return f"{MONTHS[p['month']-1]} {p['day']}, {suffix}"


def view(state, at_minutes=None):
    minute = int(at_minutes if at_minutes is not None else state.get('canon_time_minutes', int(state.get('canon_day', 0))*1440+480))
    day, tod = divmod(minute, 1440)
    world = state.get('world','Custom World')
    p = profile_for(world, state.get('calendar_epoch'), state.get('calendar_anchor_day'))
    return {**(parts_for(world, day, state.get('calendar_epoch'), state.get('calendar_anchor_day')) or {}),
            'date':format_date(world,day,state.get('calendar_epoch'),state.get('calendar_anchor_day')),
            'hour':tod//60, 'minute':tod%60, 'canon_day':day, 'note':p['note'], 'sources':p['sources'],
            'elapsed_days':(minute-int(state.get('calendar_anchor_day', day) if state.get('calendar_anchor_day') is not None else day)*1440-480)//1440}


def time_label(state, at_minutes=None):
    v=view(state,at_minutes)
    h=v['hour']; period='Night' if h<5 or h>=21 else 'Morning' if h<12 else 'Afternoon' if h<17 else 'Evening'
    return f"{v['date']} — {period}, {h:02d}:{v['minute']:02d}"


def duration_minutes(state, amount, unit):
    """Whole civil months clamp to month-end; fractions use that next month.

    Fixed units remain elapsed time. No wall-clock, timezone or DST enters
    simulation arithmetic. Preserve the historical 30-day fallback only for
    dates outside Python's representable civil range.
    """
    try: amount=float(amount)
    except (ValueError,TypeError): raise ValueError('A finite nonnegative duration is required.')
    if not math.isfinite(amount) or amount < 0: raise ValueError('A finite nonnegative duration is required.')
    if unit != 'months':
        factors={'moment':1,'minutes':1,'hours':60,'days':1440,'weeks':10080}
        if unit not in factors: raise ValueError('Unsupported time unit.')
        return round(amount*factors[unit])
    start=date_for(state.get('world'), state.get('canon_day',0), state.get('calendar_epoch'),state.get('calendar_anchor_day'))
    if start is None: return round(amount*43200)
    whole=int(amount); index=start.year*12+start.month-1+whole
    year,month0=divmod(index,12)
    if not 1<=year<=9999: raise ValueError('The selected duration exceeds the supported calendar.')
    end=dt.date(year,month0+1,min(start.day,calendar.monthrange(year,month0+1)[1]))
    return (end-start).days*1440 + round((amount-whole)*calendar.monthrange(end.year,end.month)[1]*1440)
