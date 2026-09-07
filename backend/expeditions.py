"""Persistent multi-stage original expeditions and boss hunts."""
from __future__ import annotations
import copy,hashlib,re
from simulation_integrity import _map_nodes
WORLD_SITE={
 'Naruto':('Abandoned Shinobi Complex','forest ravines','Sealed War-Beast'),
 'One Piece':('Forgotten Pirate Vault','coastal ruins','Vault Guardian'),
 'Hunter x Hunter':('Unmapped Ruin','wild ruins','Territorial Chimera'),
 'Bleach':('Distorted Spirit Nest','fractured spirit passages','Ancient Hollow'),
 'Jujutsu Kaisen':('Sealed Cursed Site','urban underground','Special-Grade Manifestation'),
 'Overgeared':('Forgotten Raid Ruin','ancient dungeon','Relic Warden'),
 'Solo Max-Level Newbie':('Hidden Tower Annex','sealed floor fragment','Hidden Floor Boss'),
 'Reincarnated as a Slime':('Ancient Jura Ruin','monster forest ruins','Awakened Guardian'),
 'Custom World':('Forgotten Expedition Site','dangerous ruins','Site Guardian'),
}
def _text(v,limit=400):return re.sub(r'\s+',' ',str(v or '')).strip()[:limit]
def _id(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:18]
def _existing(s):return s.get('expeditions') if isinstance(s.get('expeditions'),dict) else {}
def _store(s):
    r=s.setdefault('expeditions',{})
    if not isinstance(r,dict):r=s['expeditions']={}
    r.setdefault('version',2);r.setdefault('sites',{});r.setdefault('completed',{});r.setdefault('history',[]);r.setdefault('boss_intel',{});return r
def site_for(s,origin,persist=True):
    root=_store(s) if persist else _existing(s);eid=_id(s.get('campaign_id'),s.get('world'),origin,'expedition');existing=_obj(root.get('sites')).get(eid)
    if isinstance(existing,dict):return copy.deepcopy(existing)
    title,terrain,boss=WORLD_SITE.get(s.get('world'),WORLD_SITE['Custom World']);tier=1
    try:tier=max(1,next((int(n.get('tier',1) or 1) for n in _map_nodes(s.get('world')) if n.get('name')==origin),1))
    except Exception:pass
    row={'id':eid,'origin':origin,'title':f'{title} near {origin}','terrain':terrain,'boss':boss,'tier':tier,'status':'available','authorship':'Original Worldwalker expedition, not a canon event'}
    if persist:_store(s)['sites'][eid]=copy.deepcopy(row)
    return row
def _obj(v):return v if isinstance(v,dict) else {}
def offer(s,place):
    root=_existing(s);active=root.get('active')
    if isinstance(active,dict) and active.get('origin')==place:return copy.deepcopy(active)
    site=site_for(s,place,persist=False);return None if site['id'] in _obj(root.get('completed')) else site
def actions(s,place):
    root=_existing(s);active=root.get('active');site=offer(s,place);out=[]
    if not site:return out
    if not isinstance(active,dict):return [{'id':'expedition:start:'+site['id'],'label':'Organize expedition: '+site['title'],'minutes':30,'description':'Prepare a persistent multi-stage expedition. The site is original local content, not a canon event.'}]
    if active.get('origin')!=place:return out
    if active.get('status')=='paused':out.append({'id':'expedition:start:'+active['id'],'label':'Resume expedition: '+active['title'],'minutes':30,'description':'Return to the saved expedition stage.'})
    stage=active.get('stage','approach')
    if stage in {'approach','exploration'}:
        out.append({'id':'expedition:scout:'+active['id'],'label':'Survey the expedition site','minutes':60,'description':'Gather boss and hazard intel before committing deeper.'})
        out.append({'id':'expedition:advance:'+active['id'],'label':'Advance deeper into the expedition','minutes':90,'description':'Explore the next section; hazards and an elite encounter become possible.'})
    if stage in {'exploration','elite_cleared','boss_ready'}:out.append({'id':'expedition:camp:'+active['id'],'label':'Establish a field camp','minutes':240,'description':'Recover part of ordinary health and energy before continuing; special injuries remain.'})
    if stage=='elite_ready':out.append({'id':'expedition:elite:'+active['id'],'label':'Engage the expedition elite','minutes':15,'description':'Enter a tactical encounter. The fight itself does not auto-resolve.'})
    if stage in {'elite_cleared','boss_ready'}:out.append({'id':'expedition:boss:'+active['id'],'label':'Confront '+active.get('boss','the boss'),'minutes':15,'description':'Begin the expedition boss hunt. Boss phases react to HP thresholds.'})
    out.append({'id':'expedition:withdraw:'+active['id'],'label':'Withdraw from the expedition','minutes':15,'description':'Leave safely if possible. Current expedition progress is recorded but the boss reward is not granted.'})
    return out
def _lookup(s,eid):
    active=_store(s).get('active')
    if not isinstance(active,dict) or active.get('id')!=eid:raise ValueError('That expedition is no longer active here.')
    return active
def resolve(s,action,elapsed,game=None):
    parts=str(action or '').split(':',2)
    if len(parts)<3 or parts[0]!='expedition':raise ValueError('Unknown expedition action.')
    mode,eid=parts[1],parts[2];root=_store(s)
    if mode=='start':
        if isinstance(root.get('active'),dict) and root['active'].get('id')!=eid:raise ValueError('Finish or withdraw from the current local adventure before beginning an expedition.')
        if isinstance(root.get('active'),dict):
            a=root['active'];a['status']='active';a['resumed_day']=s.get('canon_day');root['history'].append({'type':'resumed','id':eid,'day':s.get('canon_day'),'stage':a.get('stage')});return {'message':f"The expedition to {a['title']} resumes from {a.get('stage','approach').replace('_',' ')}.",'active':copy.deepcopy(a)}
        site=next((copy.deepcopy(v) for v in _obj(root.get('sites')).values() if isinstance(v,dict) and v.get('id')==eid),None) or site_for(s,s.get('location'))
        if site['id'] in _obj(root.get('completed')):raise ValueError('That expedition site is no longer available.')
        a={**site,'status':'active','stage':'approach','started_day':s.get('canon_day'),'intel':[],'sections_cleared':0,'section_log':[]};root['active']=a;root['sites'][eid]=copy.deepcopy(site);root['history'].append({'type':'started','id':eid,'day':s.get('canon_day'),'stage':'approach'});return {'message':f"The expedition to {a['title']} is underway.",'active':copy.deepcopy(a)}
    a=_lookup(s,eid)
    if mode=='scout':
        line=f"Confirmed: {a['boss']} guards the deepest section. Field signs suggest a pressure shift near two-thirds health and a desperation phase near one-third."
        if line not in a.setdefault('intel',[]):a['intel'].append(line)
        root.setdefault('boss_intel',{})[eid]={'confirmed':[line],'rumors':[f"Rumor: careful preparation may reduce attrition while crossing {a.get('terrain','the site')} hazards."],'unknown':['Exact phase effects','Unseen environmental reactions']};a['stage']='exploration';return {'message':line,'active':copy.deepcopy(a)}
    if mode=='advance':
        a['stage']='exploration';a['sections_cleared']=int(a.get('sections_cleared',0) or 0)+1;section=a['sections_cleared'];hazard=_id(s.get('campaign_id'),eid,section)
        relevant=any(re.search(r'(detect|sense|track|navigate|scout|mobility|stealth|knowledge)',str(name),re.I) for name in _obj(s.get('skills')))
        if relevant:note=f'Section {section}: a route-reading skill avoids the main hazard'
        else:
            maxr=float(s.get('resource_max',100) or 100);cost=max(1,round(maxr*.08));s['resource']=max(0,float(s.get('resource',0) or 0)-cost);note=f"Section {section}: careful progress through the {a.get('terrain','site')}; the crossing costs {cost:g} {s.get('resource_name','energy')}"
        if section>=2:note+=f"; you preserve enough attention to record a useful clue";a.setdefault('intel',[]).append(f"Observed route marker {section}: the deeper guardian has been maintaining this approach deliberately.")
        a.setdefault('section_log',[]).append({'section':section,'note':note,'hazard':hazard});a['section_log']=a['section_log'][-12:]
        if section>=3:a['stage']='elite_ready';tail='The route to an elite guardian is open.'
        else:tail='A deeper section remains.'
        return {'message':note+'. '+tail,'active':copy.deepcopy(a)}
    if mode=='camp':
        marker=f"{a.get('stage')}:{a.get('sections_cleared',0)}"
        if a.get('last_camp_marker')==marker:raise ValueError('You already recovered at this stage. Advance before establishing another camp.')
        a['last_camp_marker']=marker;s['hp']=min(int(s.get('hp_max',100)),int(s.get('hp',0))+round(int(s.get('hp_max',100))*.25));s['resource']=min(int(s.get('resource_max',100)),int(s.get('resource',0))+round(int(s.get('resource_max',100))*.35));return {'message':'The field camp restores ordinary strength before the next stage.','active':copy.deepcopy(a)}
    if mode=='withdraw':
        a['status']='paused';a['paused_day']=s.get('canon_day');root['history'].append({'type':'withdrawn','id':eid,'stage':a.get('stage'),'day':s.get('canon_day')});return {'message':'You withdraw from the expedition. Its current stage is saved and can be resumed later.','active':copy.deepcopy(a)}
    if mode in {'elite','boss'}:
        if game is None:raise ValueError('A tactical encounter needs the active game session.')
        start_combat(game,a,boss=mode=='boss');return {'message':'Tactical encounter started: '+(a['boss'] if mode=='boss' else 'elite guardian'),'active':copy.deepcopy(a)}
    raise ValueError('Unknown expedition action.')
def start_combat(game,active,boss=False):
    s=game.state
    if isinstance(s.get('combat'),dict) and s['combat'].get('active'):raise ValueError('Resolve the current encounter first.')
    tier=int(active.get('tier',1) or 1);power=min(90,28+tier*8+(12 if boss else 0));hp=max(50,power*(4 if boss else 2));kind='boss' if boss else 'expedition_elite';name=active.get('boss') if boss else active.get('title','Expedition')+' Elite'
    s['combat']={'active':True,'tactical_enabled':True,'cause':active.get('title'),'enemy':{'name':name,'power':power,'hp':hp,'hp_max':hp,'alive':True},'adventure_objective':{'kind':kind,'expedition_id':active.get('id')},'expedition':{'id':active.get('id'),'boss':bool(boss),'phase':1,'thresholds_triggered':[],'terrain':active.get('terrain')},'round':0,'log':[]}
def objective_public(state,board=None):
    c=_obj(state.get('combat'));o=_obj(c.get('adventure_objective'))
    if o.get('kind') not in {'expedition_elite','boss'}:return None
    ex=_obj(c.get('expedition'));enemy=_obj(c.get('enemy'));boss=o.get('kind')=='boss'
    return {'kind':o['kind'],'title':'Defeat the expedition boss' if boss else 'Defeat the expedition elite','instructions':'Win the tactical encounter. Bosses change behavior as their health falls.' if boss else 'Defeat the elite guardian to open the deeper route.','enemy_intents':[{'name':enemy.get('name'),'intent':f"Boss phase {ex.get('phase',1)}: pressure the closest threat"}],'boss_phase':ex.get('phase',1),'can_interact':False}
def tactical_tick(state,board):
    c=_obj(state.get('combat'));ex=_obj(c.get('expedition'))
    if not ex.get('boss'):return None
    enemy=_obj(c.get('enemy'));hp=max(0,float(enemy.get('hp',0) or 0));mx=max(1,float(enemy.get('hp_max',1) or 1));ratio=hp/mx;phase=3 if ratio<=.3 else 2 if ratio<=.65 else 1
    old=int(ex.get('phase',1) or 1)
    if phase<=old:return None
    ex['phase']=phase;ex.setdefault('thresholds_triggered',[]).append(phase);c.setdefault('enemy_buffs',[]).append({'name':f'Boss Phase {phase}','rounds_left':9999,'power_pct':12 if phase==2 else 18,'speed_pct':12 if phase==2 else 18})
    msg=f"{enemy.get('name','The boss')} enters phase {phase}; its pressure and speed increase."
    c.setdefault('log',[]).append({'actor':enemy.get('name'),'action':'boss phase','phase':phase,'message':msg,'round':c.get('round')});root=_store(state);intel=root.setdefault('boss_intel',{}).setdefault(ex.get('id'),{'confirmed':[],'rumors':[],'unknown':[]});intel.setdefault('confirmed',[]).append(msg);return msg
def combat_finished(game,outcome):
    s=game.state;c=_obj(s.get('combat'));o=_obj(c.get('adventure_objective'));eid=o.get('expedition_id')
    if not eid:return
    root=_store(s);a=root.get('active')
    if not isinstance(a,dict) or a.get('id')!=eid:return
    won=outcome in {'victory','objective_complete','overwhelmed'}
    if o.get('kind')=='expedition_elite':a['stage']='elite_cleared' if won else 'exploration';a['elite_result']=outcome
    elif o.get('kind')=='boss':
        a['boss_result']=outcome
        if won:
            a['status']='completed';root['completed'][eid]=copy.deepcopy(a);root.pop('active',None);s.setdefault('titles',[]).append('Explorer of '+a.get('origin','Unknown'))
            try:game.apply_system_xp(copy.deepcopy(s),['Complete expedition: '+a['title']],[],0,'normal',[{'message':'Expedition boss defeated'}])
            except Exception:pass
            if hasattr(game,'append'):game.append(f"[EXPEDITION COMPLETE — {a['title']}]\n{a['boss']} was defeated after a multi-stage expedition.",'system',canon_day=s.get('canon_day'))
        else:a['stage']='boss_ready'
    root['history'].append({'type':'combat_result','id':eid,'kind':o.get('kind'),'outcome':outcome,'day':s.get('canon_day')});root['history']=root['history'][-120:]
def public_view(s):
    r=_existing(s);active=copy.deepcopy(r.get('active')) if isinstance(r.get('active'),dict) else None;available=[]
    if s.get('location'):
        offer_row=offer(s,s.get('location'))
        if offer_row and (not active or offer_row.get('id')!=active.get('id')):available.append(offer_row)
    return {'active':active,'available':available[:20],'completed':list(copy.deepcopy(_obj(r.get('completed'))).values())[-20:],'boss_intel':copy.deepcopy(_obj(r.get('boss_intel'))),'history':copy.deepcopy(r.get('history',[])[-30:])}
