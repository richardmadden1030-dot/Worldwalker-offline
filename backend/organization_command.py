"""Delegation, field assignments, reports, and organization base command."""
from __future__ import annotations
import copy,hashlib,math,re
from organizations import ensure_organizations,membership_copy,command_chain,power_for,known_people,ACTIVE,group_id
VERSION=1
TASKS={
 'investigate':{'label':'Investigate','duration_minutes':1440,'risk':30,'resource':'intelligence'},
 'patrol':{'label':'Patrol / defend','duration_minutes':1440,'risk':35,'resource':'readiness'},
 'supply':{'label':'Secure supplies','duration_minutes':2160,'risk':25,'resource':'supplies'},
 'diplomacy':{'label':'Diplomatic outreach','duration_minutes':2880,'risk':35,'resource':'influence'},
 'escort':{'label':'Escort / protect','duration_minutes':2160,'risk':35,'resource':'readiness'},
 'training':{'label':'Team training','duration_minutes':2880,'risk':20,'resource':'readiness'},
 'raid':{'label':'Raid / strike','duration_minutes':2160,'risk':60,'resource':'readiness'},
}
FACILITY_PROJECTS={'quarters':'Member quarters','training_hall':'Training hall','infirmary':'Infirmary','intelligence_office':'Intelligence office','defenses':'Defenses','storage':'Storage wing','workshop':'Production floor'}
def _obj(v):return v if isinstance(v,dict) else {}
def _seq(v):return v if isinstance(v,list) else []
def _text(v):return str(v or '').strip()
def _num(v,d=0):
    try:
        n=float(v);return n if math.isfinite(n) else d
    except (TypeError,ValueError):return d
def _minute(s):return int(s.get('canon_time_minutes',int(s.get('canon_day',0) or 0)*1440+480))
def _id(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:18]
def _root(s):
    r=s.setdefault('organization_command',{})
    if not isinstance(r,dict):r=s['organization_command']={}
    r.setdefault('version',VERSION);r.setdefault('assignments',{});r.setdefault('reports',[]);r.setdefault('projects',{});return r
def _groups(s):
    local=membership_copy(s);return ensure_organizations(local)
def _authority(group,player):
    if _text(group.get('leader')).casefold()==_text(player).casefold():return 'leader'
    row=next((_obj(v) for n,v in _obj(group.get('members')).items() if n.casefold()==_text(player).casefold()),{})
    if re.search(r'captain|leader|master|commander|chief|ruler|officer|kage|director|manager|head',_text(row.get('position')),re.I):return 'officer'
    return ''
def active_assignment_members(s):
    names=set()
    for a in _obj(_obj(s.get('organization_command')).get('assignments')).values():
        if isinstance(a,dict) and a.get('status')=='active':names.update(_text(x).casefold() for x in _seq(a.get('members')) if _text(x))
    return names
def active_assignment_for(s,name):
    q=_text(name).casefold()
    return next((copy.deepcopy(a) for a in _obj(_obj(s.get('organization_command')).get('assignments')).values() if isinstance(a,dict) and a.get('status')=='active' and any(_text(x).casefold()==q for x in _seq(a.get('members')))),None)
def commandable_members(s,gid):
    groups=_groups(s);group=_obj(groups.get(gid));player=_text(s.get('name'));people=known_people(s);out=[]
    if not _authority(group,player):return out
    for name,row in _obj(group.get('members')).items():
        if name==player or not isinstance(row,dict) or row.get('status') not in ACTIVE or row.get('status')=='missing' or row.get('independent') is True:continue
        if not command_chain(group,name,player):continue
        p=power_for(s,name,row,people);busy=active_assignment_for(s,name)
        out.append({'name':name,'position':row.get('position','Member'),'power':p.get('score'),'power_label':p.get('label'),'unit':row.get('unit',''),'busy':bool(busy),'assignment_id':busy.get('id') if busy else ''})
    return out
def _resources(g):
    r=g.setdefault('command_resources',{})
    defaults={'supplies':50,'influence':50,'intelligence':40,'readiness':50}
    for k,d in defaults.items():r[k]=max(0,min(100,_num(r.get(k),d)))
    return r
def start_assignment(s,gid,task,members,target):
    if task not in TASKS:raise ValueError('Choose a supported organization assignment.')
    groups=ensure_organizations(s);g=_obj(groups.get(gid));player=_text(s.get('name'))
    if not _authority(g,player):raise ValueError('You do not have command authority in that organization.')
    allowed={m['name']:m for m in commandable_members(s,gid)};members=[_text(x) for x in members if _text(x)]
    if not members or any(n not in allowed for n in members):raise ValueError('Assign at least one available member under your authority.')
    root=_root(s)
    if any(a.get('status')=='active' and set(a.get('members',[]))&set(members) for a in root['assignments'].values() if isinstance(a,dict)):raise ValueError('One or more selected members are already on an assignment.')
    spec=TASKS[task];now=_minute(s);aid='assignment-'+_id(s.get('campaign_id'),gid,task,','.join(sorted(members)),target,now)
    a={'id':aid,'group_id':gid,'group':g.get('name'),'task':task,'label':spec['label'],'target':_text(target) or 'Current organizational priority','members':members,'started_minute':now,'due_minute':now+spec['duration_minutes'],'duration_minutes':spec['duration_minutes'],'progress':0,'risk':spec['risk'],'status':'active','report':''};root['assignments'][aid]=a;return copy.deepcopy(a)
def cancel_assignment(s,aid):
    a=_obj(_root(s)['assignments'].get(aid))
    if not a or a.get('status')!='active':raise ValueError('That assignment is not active.')
    a['status']='cancelled';a['report']='Recalled before completion.';return copy.deepcopy(a)
def _resolve(s,a):
    groups=ensure_organizations(s);g=_obj(groups.get(a.get('group_id')));people=known_people(s);scores=[]
    for n in a.get('members',[]):
        row=_obj(_obj(g.get('members')).get(n));p=power_for(s,n,row,people);scores.append(_num(p.get('score'),25))
    avg=sum(scores)/max(1,len(scores));resources=_resources(g);task=TASKS[a['task']]
    base=45+min(25,avg/8)+(_num(resources.get(task['resource']),50)-50)*.25-task['risk']*.25
    try:
        from property_economy import organization_base
        baseprop=organization_base(s,a.get('group_id'))
        fac=_obj(baseprop.get('facilities')) if isinstance(baseprop,dict) else {}
        if a['task']=='investigate':base+=int(fac.get('intelligence_office',0))*5
        if a['task'] in {'patrol','raid','escort'}:base+=int(fac.get('defenses',0))*3
        if a['task']=='supply':base+=int(fac.get('storage',0))*4
        if a['task']=='training':base+=int(fac.get('training_hall',0))*5
    except Exception:pass
    roll=int(_id(s.get('campaign_id'),a['id'],s.get('canon_day'))[:8],16)%100;success=roll<max(15,min(90,base));target=a.get('target')
    if success:
        if a['task']=='supply':resources['supplies']=min(100,resources['supplies']+12)
        elif a['task']=='investigate':resources['intelligence']=min(100,resources['intelligence']+8)
        elif a['task']=='diplomacy':resources['influence']=min(100,resources['influence']+8)
        elif a['task']=='training':resources['readiness']=min(100,resources['readiness']+8)
        report=f"{a['label']} succeeded at {target}. {', '.join(a['members'])} returned with a useful result."
    else:
        resources[task['resource']]=max(0,resources[task['resource']]-5);report=f"{a['label']} met resistance at {target}. The team returned without completing the objective; no off-screen death was invented."
    a['status']='completed' if success else 'failed';a['progress']=100;a['report']=report;a['resolved_minute']=_minute(s);root=_root(s);root['reports'].append({'id':a['id'],'group':a.get('group'),'task':a.get('task'),'target':target,'members':copy.deepcopy(a.get('members')),'success':success,'report':report,'turn':s.get('turn'),'canon_day':s.get('canon_day')});root['reports']=root['reports'][-80:]
    return report
def advance(s,elapsed_minutes):
    root=_root(s);now=_minute(s)
    for a in root['assignments'].values():
        if not isinstance(a,dict) or a.get('status')!='active':continue
        start=int(a.get('started_minute',now));due=max(start+1,int(a.get('due_minute',start+1)));a['progress']=min(99,max(0,round((now-start)/(due-start)*100)))
        if now>=due:_resolve(s,a)
    advance_projects(s);return public_view(s)
def start_project(s,gid,property_id,facility):
    if facility not in FACILITY_PROJECTS:raise ValueError('Unknown organization facility project.')
    groups=ensure_organizations(s);g=_obj(groups.get(gid));
    if _authority(g,s.get('name'))!='leader':raise ValueError('Only established organization leadership can start a base project.')
    from property_economy import bootstrap_established_holdings,attach_organization_base
    eco=bootstrap_established_holdings(s);p=next((x for x in eco['properties'] if x.get('id')==property_id),None)
    if not p:raise ValueError('That property does not exist.')
    if p.get('location')!=s.get('location'):raise ValueError('Be at the organization base to begin this project.')
    res=_resources(g)
    if res['supplies']<12:raise ValueError('The organization needs at least 12 supply points for this project.')
    lvl=int(_obj(p.get('facilities')).get(facility,0) or 0)+1
    if lvl>3:raise ValueError('That facility is already fully developed.')
    root=_root(s)
    if any(x.get('status')=='active' and x.get('property_id')==property_id and x.get('facility')==facility for x in root['projects'].values() if isinstance(x,dict)):raise ValueError('That facility already has an active organization project.')
    attach_organization_base(s,property_id,gid);res['supplies']-=12;now=_minute(s);pid='org-project-'+_id(s.get('campaign_id'),gid,property_id,facility,lvl,now);root['projects'][pid]={'id':pid,'group_id':gid,'property_id':property_id,'facility':facility,'level':lvl,'status':'active','started_minute':now,'due_minute':now+2880,'supply_cost':12};return copy.deepcopy(root['projects'][pid])
def advance_projects(s):
    root=_root(s);now=_minute(s);eco=_obj(s.get('property_economy'))
    for p in root['projects'].values():
        if not isinstance(p,dict) or p.get('status')!='active' or now<int(p.get('due_minute',10**18)):continue
        prop=next((x for x in _seq(eco.get('properties')) if isinstance(x,dict) and x.get('id')==p.get('property_id')),None)
        if not prop:p['status']='cancelled';continue
        prop.setdefault('facilities',{})[p['facility']]=max(int(prop['facilities'].get(p['facility'],0) or 0),int(p['level']));p['status']='completed';root['reports'].append({'id':p['id'],'group_id':p['group_id'],'success':True,'report':f"{FACILITY_PROJECTS[p['facility']]} completed at {prop.get('name')} for {p.get('group_id')}."})
def public_view(s):
    groups=_groups(s);root=_root(s);rows=[]
    try:
        from property_economy import organization_base
    except Exception:organization_base=lambda *_:None
    for gid,g in groups.items():
        if not isinstance(g,dict):continue
        authority=_authority(g,s.get('name'));members=commandable_members(s,gid) if authority else [];base=organization_base(s,gid);rows.append({'id':gid,'name':g.get('name'),'leader':g.get('leader'),'authority':authority,'resources':copy.deepcopy(_resources(g)) if authority else {},'members':members,'facilities':copy.deepcopy(_obj(base.get('facilities'))) if isinstance(base,dict) else {}})
    tasks=[{'id':k,'label':v['label'],'duration_minutes':v['duration_minutes'],'risk':v['risk']} for k,v in TASKS.items()]
    return {'groups':rows,'assignments':list(copy.deepcopy(root['assignments']).values()),'reports':copy.deepcopy(root['reports'][-20:]),'projects':list(copy.deepcopy(root['projects']).values()),'task_types':tasks}
