"""Deterministic character mastery paths layered onto established skills.

Paths never invent a second ability system. They attach readable goals and
small mechanical refinements to skills the character already owns, using the
same skill dictionaries consumed by normal and tactical combat.
"""
from __future__ import annotations
import copy, hashlib, re

STAGES=((0,'Familiar'),(20,'Developing'),(45,'Practiced'),(70,'Advanced'),(90,'Mastered'))
TRAINING_RE=re.compile(r"\b(train|training|practice|practise|study|drill|spar|master|refine|develop|experiment|use|used|cast|perform)\b",re.I)


def _text(v,limit=400): return re.sub(r"\s+"," ",str(v or "")).strip()[:limit]
def _id(*parts): return hashlib.sha256("|".join(map(str,parts)).encode()).hexdigest()[:18]
def _store(state):
    root=state.setdefault('character_paths',{})
    if not isinstance(root,dict): root=state['character_paths']={}
    root.setdefault('version',1); root.setdefault('pinned',''); root.setdefault('paths',{}); root.setdefault('history',[])
    return root

def _visible_skills(state):
    try:
        from reliability import visible_skills
        value=visible_skills(state)
        return value if isinstance(value,dict) else {}
    except Exception:
        return state.get('skills',{}) if isinstance(state.get('skills'),dict) else {}

def _skill_detail(state,name):
    row=(state.get('skills') or {}).get(name,{}) if isinstance(state.get('skills'),dict) else {}
    return copy.deepcopy(row) if isinstance(row,dict) else {'description':str(row or '')}

def _stage(value):
    value=float(value or 0)
    return next((label for threshold,label in reversed(STAGES) if value>=threshold),'Familiar')

def _mentor_candidates(state):
    out=[]
    records={}
    for field in ('npc_memories','contacts'):
        if isinstance(state.get(field),dict): records.update(state[field])
    life=state.get('life_simulation') if isinstance(state.get('life_simulation'),dict) else {}
    explicit={str(r.get('mentor') or '') for r in life.get('mentorships',[]) if isinstance(r,dict) and r.get('active',True)}
    for name,row in records.items():
        if not isinstance(row,dict): continue
        blob=' '.join(_text(row.get(k)) for k in ('role','profession','notes','relationship_reason','public_goal','known_goal'))
        if name in explicit or re.search(r'\b(mentor|sensei|teacher|master|instructor|captain|coach|trainer|senior)\b',blob,re.I): out.append(str(name))
    return list(dict.fromkeys(out))[:12]

def _next_steps(path):
    mastery=float(path.get('mastery',0) or 0)
    if mastery<20: return ['Practice the fundamentals in a focused session','Use the ability successfully in a relevant field situation']
    if mastery<45: return ['Refine efficiency through repeated controlled use','Work with a capable mentor or sparring partner']
    if mastery<70: return ['Develop a reliable alternate application','Test the ability under an objective-based encounter']
    if mastery<90: return ['Push the technique under serious but supported pressure','Seek advanced instruction or a difficult practical test']
    return ['Maintain mastery through meaningful use','Pursue a story-supported evolution when the world rules allow it']

def normalize(state):
    root=_store(state); visible=_visible_skills(state); paths=root['paths']
    # Never create paths for hidden/unowned skills, and do not delete historical paths.
    for name,detail in visible.items():
        d=_skill_detail(state,name); pid=_id(state.get('world'),name)
        row=paths.setdefault(pid,{'id':pid,'skill':name,'title':name,'mastery':0,'evidence':[],'upgrades':{},'created_turn':int(state.get('turn',0) or 0)})
        row['skill']=name; row['title']=name; row['available']=True
        if isinstance(d.get('mastery_percent'),(int,float)): row['mastery']=max(float(row.get('mastery',0) or 0),min(100,float(d['mastery_percent'])))
        row['mastery']=round(max(0,min(100,float(row.get('mastery',0) or 0))),1)
        row['stage']=_stage(row['mastery']); row['category']=d.get('category',''); row['effect_type']=d.get('effect_type','')
        row['next_steps']=_next_steps(row); row['mentor_candidates']=_mentor_candidates(state)
        _apply_upgrades(state,row)
    visible_names={str(x).casefold() for x in visible}
    for row in paths.values():
        if isinstance(row,dict): row['available']=str(row.get('skill','')).casefold() in visible_names
    if root.get('pinned') not in paths or not paths.get(root.get('pinned'),{}).get('available'): root['pinned']=''
    return root

def _apply_upgrades(state,path):
    name=path.get('skill'); mastery=float(path.get('mastery',0) or 0)
    detail=(state.get('skills') or {}).get(name) if isinstance(state.get('skills'),dict) else None
    if not isinstance(detail,dict): return {}
    bonus=2 if mastery>=20 else 0
    if mastery>=45: bonus=4
    if mastery>=70: bonus=7
    if mastery>=90: bonus=10
    efficiency=5 if mastery>=45 else 0
    if mastery>=70: efficiency=10
    if mastery>=90: efficiency=15
    effect=str(detail.get('effect_type','')).lower(); target=str(detail.get('target_type','')).lower()
    range_bonus=1 if mastery>=70 and target not in {'','self'} else 0
    duration_bonus=1 if mastery>=70 and effect in {'stealth','detect','debuff','shield','transform','control','buff'} else 0
    potency_bonus=5 if mastery>=90 and effect in {'heal','debuff','shield','control','buff'} else 0
    detail['mastery_bonus']=bonus; detail['resource_efficiency_pct']=efficiency; detail['mastery_rank']=path.get('stage',_stage(mastery))
    detail['mastery_range_bonus']=range_bonus; detail['mastery_duration_bonus']=duration_bonus; detail['mastery_potency_bonus']=potency_bonus
    upgrades={'combat_bonus':bonus,'resource_efficiency_pct':efficiency,'range_bonus':range_bonus,'duration_bonus':duration_bonus,'potency_bonus':potency_bonus}
    path['upgrades']=upgrades
    return upgrades

def pin(state,path_id):
    root=normalize(state); path_id=str(path_id or '')
    if path_id and (path_id not in root['paths'] or not root['paths'][path_id].get('available')): raise ValueError('That development path is not available to this character.')
    root['pinned']=path_id
    return public_view(state)

def _public_from_normalized(state):
    root=_store(state); rows=[]
    for pid,row in root['paths'].items():
        if not isinstance(row,dict) or not row.get('available'): continue
        rows.append({k:copy.deepcopy(row.get(k)) for k in ('id','skill','title','mastery','stage','category','next_steps','mentor_candidates','upgrades')}|{'pinned':pid==root.get('pinned')})
    rows.sort(key=lambda r:(not r['pinned'],r['title'].casefold()))
    return {'pinned':root.get('pinned',''),'paths':rows[:20]}
def public_view(state):
    """Pure read view: derive legacy path metadata on a copy, never mutate state."""
    local=copy.deepcopy(state); normalize(local); return _public_from_normalized(local)

def actions(state,people_here=None):
    # Location drawers are read views; derive any missing path records on a copy.
    local=copy.deepcopy(state); root=normalize(local); pid=root.get('pinned'); row=root['paths'].get(pid) if pid else None
    if not isinstance(row,dict) or not row.get('available'): return []
    skill=row['skill']; out=[
      {'id':f'path:fundamentals:{pid}','label':f'Practice {skill} fundamentals','minutes':120,'description':'Build reliable control and mastery using the existing ability. Costs 10% of maximum energy.'},
      {'id':f'path:efficiency:{pid}','label':f'Refine {skill} efficiency','minutes':180,'description':'Work specifically on reducing waste and improving repeatability. Costs 12% of maximum energy.'},
      {'id':f'path:application:{pid}','label':f'Experiment with {skill} applications','minutes':180,'description':'Develop practical flexibility without changing the ability’s established governing concept. Costs 15% of maximum energy.'},
    ]
    present={str(x.get('name') if isinstance(x,dict) else x) for x in (people_here or [])}
    for mentor in row.get('mentor_candidates',[]):
        if not present or mentor in present:
            out.append({'id':f'path:mentor:{pid}:{mentor}','label':f'Train {skill} with {mentor}','minutes':180,'description':'Instruction accelerates mastery only because an established mentor is actually present. Costs 12% of maximum energy.'})
    return out

def resolve_session(state,action,elapsed_minutes,complete=True,facility_bonus=0):
    parts=str(action or '').split(':')
    if len(parts)<3 or parts[0]!='path': raise ValueError('Unknown character-path session.')
    kind,pid=parts[1],parts[2]; root=normalize(state); path=root['paths'].get(pid)
    if not isinstance(path,dict) or not path.get('available'): raise ValueError('That development path is no longer available.')
    standard={'fundamentals':120,'efficiency':180,'application':180,'mentor':180}.get(kind)
    if not standard: raise ValueError('Unknown character-path focus.')
    ratio=max(0,min(1,float(elapsed_minutes or 0)/standard)); base={'fundamentals':5,'efficiency':6,'application':6,'mentor':9}[kind]
    if kind=='mentor' and len(parts)<4: base=6
    gain=round(base*ratio*(1+max(0,float(facility_bonus or 0))),1)
    previous=path.get('stage',_stage(path.get('mastery',0))); path['mastery']=round(min(100,float(path.get('mastery',0) or 0)+gain),1); path['stage']=_stage(path['mastery'])
    note=f"{kind.title()} work on {path['skill']}"; ev={'turn':state.get('turn',0),'canon_day':state.get('canon_day'),'kind':kind,'minutes':int(elapsed_minutes or 0),'gain':gain,'note':note}
    path.setdefault('evidence',[]).append(ev); path['evidence']=path['evidence'][-30:]; root.setdefault('history',[]).append({'path_id':pid,**ev}); root['history']=root['history'][-120:]
    _apply_upgrades(state,path); path['next_steps']=_next_steps(path)
    # Training cost is bounded and prorated; local activity flow handles time/interruption.
    cost_pct={'fundamentals':.10,'efficiency':.12,'application':.15,'mentor':.12}[kind]
    maximum=float(state.get('resource_max',100) or 100); cost=int(round(maximum*cost_pct*ratio)); state['resource']=max(0,int(state.get('resource',0) or 0)-cost)
    return {'path':copy.deepcopy(path),'mastery_gain':gain,'completed':bool(complete),'stage_changed':previous!=path['stage'],'previous_stage':previous}

def record_turn(before,state,actions,elapsed_minutes):
    root=normalize(state); text_blob=' '.join(map(str,actions or [])); results=[]
    if not TRAINING_RE.search(text_blob): return results
    for pid,path in root['paths'].items():
        if not isinstance(path,dict) or not path.get('available'): continue
        skill=str(path.get('skill',''))
        if skill and skill.casefold() in text_blob.casefold():
            gain=min(3,max(1,int(elapsed_minutes or 5)//60+1)); old=path['mastery']; path['mastery']=round(min(100,old+gain),1); path['stage']=_stage(path['mastery']); _apply_upgrades(state,path); path['next_steps']=_next_steps(path)
            results.append({'path_id':pid,'skill':skill,'gain':path['mastery']-old,'mastery':path['mastery'],'stage':path['stage']})
    return results
