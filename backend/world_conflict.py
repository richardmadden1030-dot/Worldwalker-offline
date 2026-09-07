"""Persistent faction operations that turn existing faction clocks into visible world conflict."""
from __future__ import annotations
import copy, hashlib, re
from simulation_integrity import _map_nodes
TERMINAL={'completed','failed','cancelled','resolved'}

def _text(value,limit=300): return re.sub(r'\s+',' ',str(value or '')).strip()[:limit]
def _hash(*parts): return int(hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:8],16)
def _operation_id(faction,operation):
    explicit=_text(operation.get('id'),120)
    if explicit:return explicit
    seed=f"{faction}|{operation.get('type')}|{operation.get('objective')}|{operation.get('started_turn',0)}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]
def _existing_store(state): return state.get('world_conflict') if isinstance(state.get('world_conflict'),dict) else {}
def _store(state):
    r=state.setdefault('world_conflict',{})
    if not isinstance(r,dict):r=state['world_conflict']={}
    r.setdefault('version',2);r.setdefault('history',[]);r.setdefault('interventions',[]);return r

def _controller(state,place):
    row=(state.get('location_details') or {}).get(place,{}) if isinstance(state.get('location_details'),dict) else {}
    return str(row.get('controlling_faction') or '') if isinstance(row,dict) else ''
def _target(state,faction,clock,operation):
    explicit=_text(operation.get('target_location') or clock.get('target_location'))
    nodes=[n.get('name') for n in _map_nodes(state.get('world','Custom World')) if isinstance(n,dict) and n.get('name')]
    if explicit and explicit in nodes:return explicit
    blob=' '.join(_text(x) for x in (operation.get('objective'),clock.get('immediate_goal'),clock.get('goal')))
    for n in sorted(nodes,key=len,reverse=True):
        if n.casefold() in blob.casefold():return n
    rivals=[_text(x) for x in clock.get('rivals',[]) if _text(x)]
    for n in nodes:
        if _controller(state,n) in rivals:return n
    return nodes[0] if nodes else ''
def _chance(clock,kind):
    resources=clock.get('resources') if isinstance(clock.get('resources'),dict) else {}
    key={'military':'capacity','economic':'logistics','intelligence':'intelligence','diplomatic':'influence','influence':'influence'}.get(kind,'capacity')
    return max(20,min(85,int(resources.get(key,50) or 50)))
def _history(state,row):
    root=_store(state);root['history'].append(copy.deepcopy(row));root['history']=root['history'][-160:]
    if row.get('summary'):
        state.setdefault('background_world_feed',[]).append({'turn':state.get('turn',0),'canon_day':state.get('canon_day'),'summary':row['summary']})
        state['background_world_feed']=state['background_world_feed'][-200:]

def _military_result(state,faction,target,success):
    details=state.setdefault('location_details',{}).setdefault(target,{}) if target else {}
    pressure=details.setdefault('conflict_pressure',{}) if isinstance(details,dict) else {}
    contested=details.setdefault('contested_by',[]) if isinstance(details,dict) else []
    controller=_controller(state,target)
    if not target:return f'{faction} completed its military operation.'
    if success:
        count=int(pressure.get(faction,0) or 0)+1;pressure[faction]=count
        if faction not in contested and controller not in {'',faction}:contested.append(faction)
        if controller in {'','Unknown','Unclaimed'} and count>=1:
            details['controlling_faction']=faction;details['controller_changed_turn']=int(state.get('turn',0) or 0);return f'{faction} established uncontested control of {target}.'
        if controller==faction:
            details['fortification']=min(5,int(details.get('fortification',0) or 0)+1);return f'{faction} strengthened its position at {target}.'
        if count>=2:
            previous=controller;details['previous_controller']=previous;details['controlling_faction']=faction;details['controller_changed_turn']=int(state.get('turn',0) or 0);details['contested_by']=[x for x in contested if x!=faction];pressure[faction]=0
            return f'After sustained pressure, control of {target} shifted from {previous or "unclaimed forces"} to {faction}.'
        return f'{faction} established a serious contest for {target}; {controller or "the current holder"} still controls it.'
    pressure[faction]=max(0,int(pressure.get(faction,0) or 0)-1)
    if controller and controller!=faction:details['fortification']=min(5,int(details.get('fortification',0) or 0)+1)
    return f'{controller or "Local defenders"} repelled {faction}\'s pressure at {target}.'

def refresh(state,elapsed_minutes=0):
    root=_store(state); elapsed=max(0,int(elapsed_minutes or 0));
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not isinstance(clock,dict):continue
        ops=clock.setdefault('operations',[])
        if not ops:
            # Existing faction clock becomes one operation rather than a parallel agenda.
            ops.append({'type':'influence','objective':clock.get('immediate_goal') or clock.get('goal') or f'Advance {faction}\'s current agenda','progress':int(clock.get('progress',0) or 0),'status':'active','started_turn':int(state.get('turn',0) or 0)})
        for op in ops:
            if not isinstance(op,dict):continue
            op.setdefault('id',_operation_id(faction,op));op.setdefault('type','influence');op.setdefault('target_location',_target(state,faction,clock,op));op.setdefault('status','active')
            if op.get('status')!='active':continue
            if elapsed:
                pace=max(1,elapsed//360);op['progress']=min(100,int(op.get('progress',clock.get('progress',0)) or 0)+pace)
            if int(op.get('progress',0) or 0)<100:continue
            chance=_chance(clock,op.get('type','influence'));success=(_hash(state.get('campaign_id'),op['id'],state.get('canon_day'))%100)<chance
            target=op.get('target_location') or _target(state,faction,clock,op);kind=op.get('type','influence');changes=[]
            if kind=='military':summary=_military_result(state,faction,target,success);changes.append(summary)
            elif success and kind=='economic':
                res=clock.setdefault('resources',{});res['logistics']=min(100,int(res.get('logistics',50) or 50)+8);summary=f"{faction}'s economic operation at {target or 'its current front'} succeeded: logistics improved."
            elif success and kind=='intelligence':
                clock.setdefault('known_intel',[]).append({'target':target,'turn':state.get('turn'),'result':'Useful intelligence gathered'});clock['known_intel']=clock['known_intel'][-12:];summary=f"{faction}'s intelligence operation at {target or 'its current front'} succeeded; useful intelligence was gathered."
            elif success and kind=='diplomatic':summary=f"{faction}'s diplomatic initiative at {target or 'its current front'} gained ground."
            elif success:summary=f"{faction}'s {kind} operation at {target or 'its current front'} gained influence."
            else:summary=f"{faction}'s {kind} operation at {target or 'its current front'} stalled: the operation met resistance and lost momentum."
            op['status']='completed' if success else 'failed';op['resolution']='success' if success else 'setback';op['recent_outcome']=summary;op['worldwalker_settled']=True
            row={'id':op['id'],'turn':state.get('turn'),'canon_day':state.get('canon_day'),'faction':faction,'kind':kind,'target':target,'success':success,'summary':summary,'changes':changes};_history(state,row);clock.setdefault('recent_outcomes',[]).append(row);clock['recent_outcomes']=clock['recent_outcomes'][-12:]
    return public_view(state)

def operations_at(state,place):
    out=[]
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not isinstance(clock,dict):continue
        for op in clock.get('operations',[]) or []:
            if not isinstance(op,dict) or op.get('status','active')!='active':continue
            target=op.get('target_location') or _target(state,faction,clock,op)
            if target!=place:continue
            out.append({'faction':faction,'id':_operation_id(faction,op),'type':op.get('type','influence'),'objective':op.get('objective') or clock.get('immediate_goal') or clock.get('goal'),'progress':int(op.get('progress',0) or 0),'target':target})
    return out[:8]
def actions(state,place):
    out=[]
    for op in operations_at(state,place):
        token=f"{op['faction']}:{op['id']}"
        out += [
          {'id':'conflict:investigate:'+token,'label':f"Investigate {op['faction']} activity",'minutes':90,'description':'Gather local intelligence without automatically helping either side.'},
          {'id':'conflict:assist:'+token,'label':f"Support {op['faction']} operation",'minutes':120,'description':'Commit time and influence to this operation; the operation still resolves from its own resources and opposition.'},
          {'id':'conflict:sabotage:'+token,'label':f"Disrupt {op['faction']} operation",'minutes':180,'description':'Attempt to slow the operation locally. This can create faction consequences.'},]
    return out[:12]
def resolve_intervention(state,action,elapsed):
    parts=str(action or '').split(':',3)
    if len(parts)<4 or parts[0]!='conflict':raise ValueError('Unknown faction intervention.')
    mode,faction,oid=parts[1],parts[2],parts[3];clock=(state.get('faction_clocks') or {}).get(faction)
    if not isinstance(clock,dict):raise ValueError('That faction operation no longer exists.')
    op=next((o for o in clock.get('operations',[]) if isinstance(o,dict) and _operation_id(faction,o)==oid),None)
    if not op or op.get('status','active')!='active':raise ValueError('That faction operation is no longer active.')
    if mode=='assist':op['progress']=min(99,int(op.get('progress',0) or 0)+max(2,int(elapsed or 0)//30));summary=f"You materially supported {faction}'s operation."
    elif mode=='sabotage':
        op['progress']=max(0,int(op.get('progress',0) or 0)-max(2,int(elapsed or 0)//30));res=clock.setdefault('resources',{});res['capacity']=max(0,int(res.get('capacity',50) or 50)-8);summary=f"You disrupted {faction}'s operation."
    elif mode=='investigate':
        clock.setdefault('known_intel',[]).append({'target':op.get('target_location'),'turn':state.get('turn'),'result':op.get('objective') or clock.get('immediate_goal')});clock['known_intel']=clock['known_intel'][-12:];summary=f"You learned more about {faction}'s current operation."
    else:raise ValueError('Unknown faction intervention.')
    _store(state)['interventions'].append({'turn':state.get('turn'),'canon_day':state.get('canon_day'),'faction':faction,'operation_id':oid,'mode':mode,'summary':summary});_store(state)['interventions']=_store(state)['interventions'][-100:]
    return {'message':summary,'world_conflict':public_view(state)}
def public_view(state):
    operations=[]
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not isinstance(clock,dict):continue
        for op in clock.get('operations',[]) or []:
            if not isinstance(op,dict):continue
            operations.append({'faction':faction,'id':_operation_id(faction,op),'type':op.get('type','influence'),'objective':op.get('objective') or clock.get('immediate_goal'),'target':op.get('target_location') or _target(state,faction,clock,op),'progress':int(op.get('progress',0) or 0),'status':op.get('status','active'),'resolution':op.get('resolution',''),'recent_outcome':op.get('recent_outcome','')})
    root=_existing_store(state)
    return {'operations':operations[:40],'history':copy.deepcopy(root.get('history',[])[-30:]),'interventions':copy.deepcopy(root.get('interventions',[])[-20:])}
def location_status(state,place):
    detail=(state.get('location_details') or {}).get(place,{}) if isinstance(state.get('location_details'),dict) else {}
    return {'controller':detail.get('controlling_faction','') if isinstance(detail,dict) else '', 'contested_by':copy.deepcopy(detail.get('contested_by',[]) if isinstance(detail,dict) else []),'conflict_pressure':copy.deepcopy(detail.get('conflict_pressure',{}) if isinstance(detail,dict) else {}),'fortification':int(detail.get('fortification',0) or 0) if isinstance(detail,dict) else 0,'operations':operations_at(state,place)}
