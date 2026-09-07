"""Player-targeted minor canon intervention flags."""
from __future__ import annotations
import copy, hashlib
from worlds import timeline_for
from simulation_integrity import canon_dependency_graph

def _id(world,day,title): return hashlib.sha256(f'{world}|{day}|{title}'.encode()).hexdigest()[:18]
def _store(s):
    r=s.setdefault('canon_interventions',{})
    if not isinstance(r,dict): r=s['canon_interventions']={}
    r.setdefault('version',1);r.setdefault('targets',{});r.setdefault('history',[]);return r

def _read_store(s):
    r=s.get('canon_interventions')
    if not isinstance(r,dict): return {'version':1,'targets':{},'history':[]}
    targets=r.get('targets') if isinstance(r.get('targets'),dict) else {}
    history=r.get('history') if isinstance(r.get('history'),list) else []
    return {'version':r.get('version',1),'targets':targets,'history':history}

def _events(s):
    dep={e.get('id'):e for e in canon_dependency_graph(s).get('events',[]) if isinstance(e,dict)}
    rows=[]
    for e in timeline_for(s.get('world')).get('events',[]):
        if e.get('historical_only'): continue
        eid=e.get('id') or f"day:{e.get('day',0)}:{e.get('title','event')}"
        d=dep.get(eid,{})
        rows.append((eid,e,int(d.get('effective_day',e.get('day',0)) or 0),str(d.get('status') or 'upcoming')))
    return rows

def target(s,event_id):
    found=next((x for x in _events(s) if x[0]==event_id),None)
    if not found: raise ValueError('That canon event is not in this campaign timeline.')
    eid,e,day,status=found
    if e.get('major',True): raise ValueError('Major canon events already stop for direct intervention. Use this control for a future minor event.')
    if day<=int(s.get('canon_day',0) or 0): raise ValueError('Only a future minor canon event can be targeted for intervention.')
    if status in {'impossible','replaced'}: raise ValueError('That event is already impossible or replaced in this campaign.')
    row={'id':_id(s.get('world'),day,e.get('title')),'event_id':eid,'title':e.get('title'),'location':e.get('location',''),'summary':e.get('summary',''),'day':day,'status':'targeted','created_turn':int(s.get('turn',0) or 0),'created_day':s.get('canon_day'),'priority':'player_intervention'}
    root=_store(s); root['targets'][eid]=row; root['history'].append({'action':'targeted',**copy.deepcopy(row)});root['history']=root['history'][-80:];return row

def cancel(s,event_id):
    root=_store(s); row=root['targets'].pop(event_id,None)
    if row: root['history'].append({'action':'cancelled',**copy.deepcopy(row)});root['history']=root['history'][-80:]
    return row

def active(s):
    root=_read_store(s); status={eid:(day,st) for eid,e,day,st in _events(s)}; out=[]
    for eid,row in list(root['targets'].items()):
        if not isinstance(row,dict): continue
        day,st=status.get(eid,(row.get('day',0),'missing'))
        r=copy.deepcopy(row);r['day']=day;r['status']='missed' if day<int(s.get('canon_day',0) or 0) and st not in {'impossible','replaced'} else st if st in {'impossible','replaced'} else 'targeted';out.append(r)
    return sorted(out,key=lambda r:r.get('day',0))
def is_targeted(s,event_id): return event_id in _read_store(s)['targets']
def next_target_in_window(s,before,after):
    hits=[]
    for r in active(s):
        minute=int(r.get('day',0))*1440+480
        if int(before)<minute<=int(after) and r.get('status')=='targeted': hits.append((minute,r))
    return min(hits,key=lambda x:x[0]) if hits else None

def gm_context(s):
    lines=[]
    for r in active(s)[:5]:
        if r.get('status')!='targeted': continue
        lines.append(f"- PLAYER CANON INTERVENTION TARGET: {r.get('title')} at {r.get('location') or 'its established location'} on canon day {r.get('day')}. The player explicitly wants a fair chance to reach and affect this normally-minor event. Preserve prerequisites and travel, but do not silently skip, background-resolve, or steer away from it; shape reasonable leads, timing, and scene access toward an actual intervention opportunity. This is player meta-reference knowledge only; NPCs do not gain foreknowledge from this flag.")
    return '\n'.join(lines)
def mark_resolved(s,event_id,outcome,reason=''):
    root=_store(s);r=root['targets'].get(event_id)
    if not r:return
    r['status']=str(outcome);r['resolved_day']=s.get('canon_day');r['reason']=reason;root['history'].append({'action':'resolved','outcome':outcome,**copy.deepcopy(r)});root['history']=root['history'][-80:]
def public_view(s): return {'active':active(s),'history':copy.deepcopy(_read_store(s)['history'][-30:])}
