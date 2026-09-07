"""Application-owned public reputation, recognition, heat, and wanted status."""
from __future__ import annotations
import hashlib, math, copy

def _obj(v):return v if isinstance(v,dict) else {}
def _seq(v):return v if isinstance(v,list) else []
def _text(v):return str(v or '').strip()
def _num(v,default=0):
    try:
        n=float(v);return n if math.isfinite(n) else default
    except (TypeError,ValueError):return default
def _id(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:18]
def _minute(s):return int(s.get('canon_time_minutes',int(s.get('canon_day',0) or 0)*1440+480))
def _store(state):
    r=state.setdefault('public_reputation',{})
    if not isinstance(r,dict):r=state['public_reputation']={}
    r.setdefault('version',1);r.setdefault('fame',0.0);r.setdefault('infamy',0.0);r.setdefault('jurisdictions',{});r.setdefault('history',[]);r.setdefault('last_synced_reputation',{});r.setdefault('last_synced_bounty',0);return r

def _band(score):
    s=_num(score)
    return 'Revered' if s>=70 else 'Respected' if s>=40 else 'Recognized' if s>=15 else 'Hated' if s<=-70 else 'Hostile' if s<=-40 else 'Distrusted' if s<=-15 else 'Unknown'
def _wanted(heat,score,bounty=0):
    h=_num(heat);s=_num(score);b=_num(bounty)
    if b>=100_000_000 or h>=85 or s<=-80:return 'Most Wanted'
    if b>=30_000_000 or h>=65 or s<=-60:return 'Priority Target'
    if b>0 or h>=40 or s<=-40:return 'Wanted'
    if h>=20 or s<=-20:return 'Under Watch'
    return 'Clear'
def record_event(state,kind,magnitude,source,faction='',public=True,witnesses=None,infamy=None):
    if not public:return None
    root=_store(state);mag=max(0,min(100,_num(magnitude,5)));kind=_text(kind);faction=_text(faction)
    eid=_id(state.get('turn'),state.get('canon_day'),kind,source,faction)
    if any(r.get('id')==eid for r in root['history'] if isinstance(r,dict)):return None
    bad=kind.casefold() in {'betrayal','sabotage','crime','murder','theft','public_failure'} if infamy is None else bool(infamy)
    if bad:root['infamy']=round(_num(root.get('infamy'))+mag,2)
    else:root['fame']=round(_num(root.get('fame'))+mag,2)
    row={'id':eid,'turn':state.get('turn'),'canon_day':state.get('canon_day'),'kind':kind,'magnitude':mag,'source':_text(source),'faction':faction,'witnesses':copy.deepcopy(witnesses or []),'public':True};root['history'].append(row);root['history']=root['history'][-160:]
    if faction:
        j=root['jurisdictions'].setdefault(faction,{});j['heat']=round(min(100,max(0,_num(j.get('heat'))+mag*(.75 if bad else .2))),2)
    return row

def sync(before,state,source='',events=None):
    root=_store(state);notices=[];reps=state.get('reputation') if isinstance(state.get('reputation'),dict) else {}
    prior=root.setdefault('last_synced_reputation',{})
    for faction,value in reps.items():
        score=_num(value.get('score') if isinstance(value,dict) else value)
        old=_num(prior.get(faction),score);j=root['jurisdictions'].setdefault(faction,{})
        j['standing']=score;j['band']=_band(score)
        # Heat rises on new hostility, but does not reset merely because standing stayed hostile.
        delta=score-old
        if delta<0:j['heat']=round(min(100,_num(j.get('heat'))+abs(delta)*.35),2)
        if delta>0:root['fame']=round(_num(root.get('fame'))+min(10,delta*.3),2)
        if abs(delta)>=1:notices.append(f'{faction} standing changed ({delta:+g}).')
        prior[faction]=score
    bounty=_num(_obj(state.get('special')).get('Bounty'))
    old_bounty=_num(root.get('last_synced_bounty'))
    if bounty>old_bounty:
        record_event(state,'bounty_increase',min(25,max(1,(bounty-old_bounty)/1_000_000)),f'Bounty rose to {bounty:g}',faction='Marines',public=True,infamy=True)
        notices.append(f'Bounty: {bounty:,.0f}')
    root['last_synced_bounty']=bounty
    for faction,j in root['jurisdictions'].items():
        if not isinstance(j,dict):continue
        score=_num(j.get('standing'));heat=_num(j.get('heat'));j['band']=_band(score);j['wanted']=_wanted(heat,score,bounty if faction in {'World Government','Marines'} else 0);j['recognition']=round(min(100,_num(root.get('fame'))*.12+_num(root.get('infamy'))*.45+abs(score)*.2),2)
    return notices

def advance(state,elapsed_minutes):
    root=_store(state);hours=max(0,_num(elapsed_minutes)/60)
    if hours:
        for j in root['jurisdictions'].values():
            if isinstance(j,dict):j['heat']=round(max(0,_num(j.get('heat'))-hours*.08),2)
    sync(state,state)

def lay_low(state,place,hours):
    detail=_obj(_obj(state.get('location_details')).get(place));faction=_text(detail.get('controlling_faction') or detail.get('faction'))
    root=_store(state);j=root['jurisdictions'].get(faction) if faction else None
    if not isinstance(j,dict) or _num(j.get('heat'))<=0:return {'reduced':0,'summary':'No active public heat is established here.'}
    reduced=min(_num(j.get('heat')),max(2,_num(hours)*2));j['heat']=round(max(0,_num(j.get('heat'))-reduced),2);j['wanted']=_wanted(j['heat'],j.get('standing'),_num(_obj(state.get('special')).get('Bounty')) if faction in {'World Government','Marines'} else 0)
    return {'reduced':reduced,'summary':f'You keep a low profile around {place}; public heat falls by {reduced:.1f}.'}
def price_multiplier(state,place):
    detail=_obj(_obj(state.get('location_details')).get(place or state.get('location')));faction=_text(detail.get('controlling_faction') or detail.get('faction'));root=_obj(state.get('public_reputation'));j=_obj(_obj(root.get('jurisdictions')).get(faction));standing=_num(j.get('standing'));heat=_num(j.get('heat'))
    return round(max(.75,min(1.6,1-standing/500+heat/220)),3)
def travel_exposure_bonus(state,place):
    detail=_obj(_obj(state.get('location_details')).get(place or state.get('location')));faction=_text(detail.get('controlling_faction') or detail.get('faction'));root=_obj(state.get('public_reputation'));heat=_num(_obj(_obj(root.get('jurisdictions')).get(faction)).get('heat'));return min(.22,heat/100*.25)
def public_view(state):
    """Pure player-facing snapshot; synchronization happens on campaign ticks."""
    root=copy.deepcopy(_obj(state.get('public_reputation')))
    root.setdefault('fame',0.0);root.setdefault('infamy',0.0);root.setdefault('jurisdictions',{});root.setdefault('history',[])
    bounty=_num(_obj(state.get('special')).get('Bounty'));rows=[]
    # Show existing engine-owned rows. If an old save has not ticked this system
    # yet, derive current faction standing without writing it back.
    jurisdictions=copy.deepcopy(_obj(root.get('jurisdictions')))
    for faction,value in _obj(state.get('reputation')).items():
        score=_num(value.get('score') if isinstance(value,dict) else value)
        j=jurisdictions.setdefault(faction,{})
        j.setdefault('standing',score)
    for faction,j in jurisdictions.items():
        if not isinstance(j,dict):continue
        score=_num(j.get('standing'));heat=_num(j.get('heat'));rows.append({'faction':faction,'standing':score,'band':_band(score),'heat':round(heat,2),'wanted':_wanted(heat,score,bounty if faction in {'World Government','Marines'} else 0),'recognition':round(_num(j.get('recognition')),2)})
    rows.sort(key=lambda x:(-x['heat'],-abs(x['standing']),x['faction'].casefold()))
    fame=_num(root.get('fame'));infamy=_num(root.get('infamy'));identity='Notorious' if infamy>=30 and infamy>fame*1.25 else 'Celebrated' if fame>=30 and fame>infamy*1.25 else 'Controversial' if fame+infamy>=30 else 'Unknown'
    return {'fame':round(fame,2),'infamy':round(infamy,2),'identity':identity,'jurisdictions':rows,'history':copy.deepcopy(_seq(root.get('history'))[-20:]),'price_multiplier_here':price_multiplier(state,state.get('location'))}
