"""Server-owned location services, journeys and authored adventure contracts.

Read endpoints are pure. A timed action is a quoted server action, not trusted
client prose/costs. Writes run inside app.atomic_game_call and reuse the normal
clock/world simulation. The ordinary composer/standing itinerary is preserved.
"""
from __future__ import annotations
import copy
import hashlib
import heapq
import math
import re

from simulation_integrity import _map_nodes, build_travel_graph, canon_dependency_graph
from worlds import expansion_for, uses_xp_for, timeline_for
from world_calendar import view as calendar_view, time_label
from systems import currency_balance, record_currency_transaction, _shop_item_price, _shop_item_currency

VERSION = 1
SETTLEMENTS = {'settlement','city','town','village','hub','academy','kingdom','capital','guild','hq','island','floor','region','realm'}
UNAVAILABLE = {'dead','deceased','missing','away','absent','hostile','imprisoned'}
WORLD_FLAVOR = {
 'Naruto': ('Mission desk','Shinobi training ground','Medical station','Ninja tool stall','Ren, a local messenger','rogue scouts'),
 'One Piece': ('Harbor notices','Sparring yard','Rest house','Outfitter','Mara, a local courier','dockside raiders'),
 'Hunter x Hunter': ('Contract board','Practice hall','Clinic','Supplier','Tavi, a local investigator','relic smugglers'),
 'Bleach': ('Local duty desk','Practice court','Relief station','Supply counter','Aya, a local courier','spirit poachers'),
 'Jujutsu Kaisen': ('Assignment desk','Practice court','Recovery room','Equipment counter','Nao, a local assistant','renegade scavengers'),
 'Overgeared': ('Adventurer notices','Training yard','Inn','General merchant','Lysa, a local courier','roadside brigands'),
 'Solo Max-Level Newbie': ('Player requests','Practice area','Recovery station','Supply exchange','Min, a local runner','artifact scavengers'),
 'Reincarnated as a Slime': ('Community requests','Training clearing','Rest shelter','Trade post','Rell, a local messenger','forest raiders'),
 'Custom World': ('Local requests','Training area','Rest shelter','Supply stall','Ari, a local courier','local raiders'),
}
TEMPLATES = (
 {'kind':'retrieval','title':'The Missing Dispatch','description':'A courier’s dispatch case was taken to a nearby waystation. Recover it without losing the information inside.',
  'success':'The dispatch is returned intact. A local supply connection can operate again.', 'benefit':'safer_route'},
 {'kind':'protection','title':'A Light on the Road','description':'A relief crew is ready to signal a supply convoy, but raiders intend to destroy its beacon. Keep the beacon intact for four rounds or secure an agreement.',
  'success':'The relief beacon remains intact. A shelter is now available to travelers.', 'benefit':'shelter'},
 {'kind':'escape','title':'The Witness’s Passage','description':'A witness has entrusted you with testimony. Take it through a guarded checkpoint and reach the far exit; defeating everyone is unnecessary.',
  'success':'The testimony reaches its destination. The courier agrees to share future leads.', 'benefit':'contact'},
)


def obj(v): return v if isinstance(v,dict) else {}
def seq(v): return v if isinstance(v,list) else []
def text(v): return str(v or '').strip()
def key(*parts): return hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()[:20]
def balance(s,currency=None): return currency_balance(copy.deepcopy(s),currency)
def now(s): return int(s.get('canon_time_minutes',int(s.get('canon_day',0))*1440+480))
def store(s): return obj(s.get('adventures'))
def writable(s):
    value=s.setdefault('adventures',{})
    if not isinstance(value,dict): raise ValueError('Adventure state needs repair before it can be changed.')
    value.setdefault('version',VERSION)
    return value


def location_node(s,name=None):
    name=text(name or s.get('location')); nodes=_map_nodes(s.get('world','Custom World'))
    exact=next((n for n in nodes if n['name'].casefold()==name.casefold()),None)
    if exact:return exact
    # Sublocations remain attached to their unique established town, never to a
    # fuzzy unrelated place. Unknown map positions cannot become teleport exits.
    matches=[n for n in nodes if n['name'].casefold() in name.casefold()]
    if len(matches)==1:return matches[0]
    if name==text(s.get('location')) and name:
        return {'name':name,'kind':'unmapped','tier':1,'x':50,'y':50}
    raise ValueError('Choose an established location on the active world map.')


def available_people(s,place):
    people={}
    unavailable=set()
    for field in ('npc_memories','contacts','relationships'):
        for name,row in obj(s.get(field)).items():
            if isinstance(row,dict) and (text(row.get('status')).lower() in UNAVAILABLE or row.get('alive') is False):
                unavailable.add(name.casefold())
    for field in ('npc_memories','contacts','relationships'):
        for name,r in obj(s.get(field)).items():
            if not isinstance(r,dict):continue
            if text(r.get('status')).lower() in UNAVAILABLE or r.get('alive') is False:continue
            loc=text(r.get('last_known_location') or r.get('location'))
            present=name in seq(obj(s.get('scene_state')).get('present')) and place==location_node(s)['name']
            if loc.casefold()==place.casefold() or present:
                people[name]={'name':name,'location':place,'goal':text(r.get('known_goal') or r.get('public_goal')), 'basis':'present' if present else 'last known'}
    for r in seq(s.get('companions')):
        if not isinstance(r,dict) or not r.get('name'):continue
        if text(r.get('status')).lower() in UNAVAILABLE or r.get('alive') is False:continue
        loc=text(r.get('location') or s.get('location'))
        if loc.casefold()==place.casefold():people[r['name']]={'name':r['name'],'location':place,'goal':'','basis':'companion'}
    return [p for p in people.values() if p['name'].casefold() not in unavailable][:24]


def companions_here(s,place):
    """Only agreed companions can accompany a journey; contacts are not party members."""
    known={p['name'].casefold():p for p in available_people(s,place)}
    companions=[]
    try:
        from organization_command import active_assignment_members
        delegated=active_assignment_members(s)
    except Exception: delegated=set()
    for row in seq(s.get('companions')):
        name=text(row.get('name') if isinstance(row,dict) else row)
        if name.casefold() in known and name.casefold() not in delegated and (not isinstance(row,dict) or (row.get('alive') is not False and text(row.get('status')).lower() not in UNAVAILABLE)):
            companions.append(known[name.casefold()])
    return companions


def catalog(s,place):
    """Use exactly the existing shop transaction's stock, price and currency rules."""
    if obj(s.get('currency')).get('tracked') is False:return []
    out=[];shops=seq(s.get('shops'));shop_names=[text(sh.get('name')).casefold() for sh in shops if isinstance(sh,dict)]
    for shop in shops:
        if not isinstance(shop,dict) or text(shop.get('location')).casefold()!=place.casefold():continue
        if not shop.get('name') or shop_names.count(text(shop['name']).casefold())!=1:continue
        items=seq(shop.get('inventory')) or seq(shop.get('items'));names=[text(i.get('name')).casefold() for i in items if isinstance(i,dict)]
        for index,item in enumerate(items):
            if not isinstance(item,dict) or not item.get('name') or names.count(text(item['name']).casefold())!=1:continue
            if isinstance(item.get('stock'),(int,float)) and item['stock']<=0:continue
            price=_shop_item_price(item)
            if price is None or not math.isfinite(price) or price<0:continue
            try:
                from property_economy import purchase_price
                price=purchase_price(s,shop.get('name'),item.get('name'),price)
            except Exception: pass
            out.append({'id':'purchase:'+key(shop.get('name'),item['name'],index),'shop':shop['name'],'item':item['name'],
                        'label':f"Buy {item['name']} from {shop['name']}", 'minutes':10,'cost':price,
                        'currency':_shop_item_currency(s,item),'stock':copy.deepcopy(item)})
    return out[:40]


def mission_offer(s,place):
    active=obj(store(s).get('active'))
    if active:return copy.deepcopy(active) if active.get('origin')==place else None
    flavor=WORLD_FLAVOR.get(s.get('world'),WORLD_FLAVOR['Custom World'])
    name=flavor[4].split(',')[0]+' of '+place
    if text(obj(obj(s.get('npc_memories')).get(name)).get('status')).lower() in UNAVAILABLE:return None
    resolved=obj(store(s).get('resolved'))
    for template in TEMPLATES:
        identity=key(s.get('campaign_id'),s.get('world'),place,template['kind'])
        if identity not in resolved:
            flavor=WORLD_FLAVOR.get(s.get('world'),WORLD_FLAVOR['Custom World'])
            return {**template,'id':identity,'origin':place,'status':'available','stage':'offered','contact':flavor[4].split(',')[0]+' of '+place, 'opposition':flavor[5],
                    'authorship':'Original Worldwalker adventure, not a canon event','investigated':False,'attempts':0}
    return None


def action_list(s,place):
    node=location_node(s,place);here=node['name']==location_node(s)['name']
    if not here:return []
    if obj(s.get('combat')).get('active') or not s.get('alive',True) or int(s.get('hp',1))<=0:return []
    active=obj(store(s).get('active'));journey=obj(store(s).get('journey'));pending=obj(store(s).get('pending_activity'))
    if journey:
        return [{'id':'journey:resume','label':f"Continue to {journey['destination']}", 'minutes':max(1,int(journey['remaining_minutes']))},
                {'id':'journey:cancel','label':'End the journey at the last reached waypoint','minutes':0}]
    if pending:
        return [{'id':'activity:resume','label':f"Continue: {pending['label']}", 'minutes':pending['remaining_minutes']},
                {'id':'activity:cancel','label':'Leave the unfinished activity','minutes':0}]
    flavor=WORLD_FLAVOR.get(s.get('world'),WORLD_FLAVOR['Custom World'])
    settlement=node.get('kind') in SETTLEMENTS or bool(obj(obj(s.get('location_details')).get(place)).get('services'))
    out=[{'id':'rest:60','label':'Rest and recover','minutes':60,'description':'Recover up to 12% of maximum health and energy; does not cure a special injury.'},
         {'id':'scout','label':'Survey the surrounding area','minutes':30,'description':'Identify connected routes and nearby landmarks; no forced random fight.'}]
    if settlement:
        out.append({'id':'rest:480','label':f'Recover at the {flavor[2].lower()}','minutes':480,'description':'A full rest restores ordinary health and energy, not unique conditions.'})
    for name in list(obj(s.get('stats')))[:12]:
        out.append({'id':'train:'+name,'label':f'Practice {name}','minutes':120,'description':'Uses the existing training progression rules and 10% of maximum energy.'})
    if settlement:
        out.append({'id':'prepare','label':'Study route reports and prepare a field kit','minutes':45,'description':'For the next journey: clearer route exposure and a smaller pursuit encounter if one is triggered. No automatic purchase.'})
        out.extend(catalog(s,place))
    for person in available_people(s,place):
        out.append({'id':'talk:'+person['name'],'label':'Check in with '+person['name'],'minutes':15,'description':'Discuss your established local connections; freeform chat remains available.'})
    mission=mission_offer(s,place)
    if mission and (settlement or active):
        if mission['status']=='available':out.append({'id':'mission:accept','label':'Accept: '+mission['title'],'minutes':15,'description':mission['description']})
        elif mission.get('status')=='active':
            if not mission.get('investigated'):out.append({'id':'mission:investigate','label':'Investigate the witness account','minutes':30,'description':'Learn the objective location and improve negotiation or infiltration preparation.'})
            out.extend([
                {'id':'mission:negotiate','label':'Negotiate a peaceful settlement','minutes':20,'description':'A failed negotiation exposes the encounter; it does not grant the objective.'},
                {'id':'mission:stealth','label':'Attempt a discreet approach','minutes':30,'description':'Use preparation and your strongest relevant technique to avoid a direct fight.'},
                {'id':'mission:confront','label':'Enter the objective encounter','minutes':15,'description':f"Starts a tactical battle against {min(60,20+node.get('tier',1)*5)}-power opponents. Damage can be lethal. Victory depends on the marked objective, not killing everyone."},
                {'id':'mission:withdraw','label':'Withdraw from this assignment','minutes':15,'description':'Closes this local adventure without rewards. No unrelated punishment.'},
            ])
    # Reusable systems extend the same confirmed timed-action surface.
    try:
        from character_paths import actions as path_actions
        out.extend(path_actions(s,available_people(s,place)))
    except Exception: pass
    try:
        from world_conflict import actions as conflict_actions
        out.extend(conflict_actions(s,place))
    except Exception: pass
    try:
        from expeditions import actions as expedition_actions
        out.extend(expedition_actions(s,place))
    except Exception: pass
    try:
        from property_economy import actions as property_actions
        out.extend(property_actions(s,place))
    except Exception: pass
    try:
        from reputation_system import public_view as reputation_view
        if any(float(j.get('heat',0) or 0)>0 for j in reputation_view(s).get('jurisdictions',[])):
            out.append({'id':'reputation:laylow','label':'Lay low and reduce public attention','minutes':240,'description':'Keep a low profile for four hours. This can cool local heat; it does not erase established faction standing.'})
    except Exception: pass
    return out


def location_view(s,place=None):
    node=location_node(s,place);name=node['name'];local=obj(obj(s.get('location_details')).get(name))
    flavor=WORLD_FLAVOR.get(s.get('world'),WORLD_FLAVOR['Custom World'])
    settlement=node['kind'] in SETTLEMENTS
    active=obj(store(s).get('active'))
    from util import scene_image_url
    picture,_=scene_image_url({**s,'location':name,'combat':{}})
    return {'scene_image':picture,'world':s.get('world'),'campaign_id':s.get('campaign_id'),'place':name,'kind':node['kind'],'current':name==location_node(s)['name'],
            'situation':text(local.get('notes') or local.get('description') or local.get('activity')) or 'No local crisis has been established. Explore, prepare, or follow an existing lead.',
            'services':seq(local.get('services')) or list(flavor[:4] if settlement else ['Camp','Survey point','Practice area']),
            'people':available_people(s,name),'actions':action_list(s,name),'mission':mission_offer(s,name) if settlement or active else None,
            'aftermath':[copy.deepcopy(r) for r in seq(store(s).get('aftermath')) if r.get('location')==name][-12:],
            'journey':copy.deepcopy(obj(store(s).get('journey'))),'calendar':calendar_view(s),
            'preparation':copy.deepcopy(obj(store(s).get('preparation'))),
            'conflict':(__import__('world_conflict').location_status(s,name)),
            'property_economy':({**__import__('property_economy').public_view(s),'market':__import__('property_economy').market_view(s,name)}),
            'reputation':__import__('reputation_system').public_view(s),
            'expedition':(__import__('expeditions').offer(s,name) or (__import__('expeditions').public_view(s).get('active') if obj(__import__('expeditions').public_view(s).get('active')).get('origin')==name else None)),
            'known':name in seq(s.get('discovered_locations')) or name==location_node(s)['name'],
            'warning':'Remote information is a reference. Travel here before using local services.' if name!=location_node(s)['name'] else ''}


def _permission(s,requirement,a,b,prep):
    if not requirement:return True
    if '; ' in requirement:return all(_permission(s,r,a,b,prep) for r in requirement.split('; '))
    # Explicit travel access records are the preferred contract. No regex
    # match against backstory or an unlearned spell can authorize a portal.
    granted=seq(s.get('travel_access'))
    if any(isinstance(r,dict) and r.get('active',True) and r.get('requirement')==requirement and
           (not r.get('origin') or r['origin']==a) and (not r.get('destination') or r['destination']==b) for r in granted):return True
    if 'intervening floor' in requirement.lower():
        floor=max([int(v) for v in re.findall(r'Floor (\d+)',a+' '+b)] or [1])
        return floor<=int(s.get('tower_floor',1))
    inventory=[r for r in seq(s.get('inventory')) if isinstance(r,dict)]
    if 'seaworthy' in requirement:
        return prep=='booked_passage' or any(r.get('seaworthy') is True or r.get('category')=='ship' for r in inventory) or bool(obj(s.get('ship')).get('seaworthy'))
    # Learned, explicitly named passage abilities are usable without a new
    # hidden grant flag. A mere backstory mention never satisfies this test.
    from reliability import visible_skills
    learned={name.casefold() for name in visible_skills(s)}
    if 'Garganta' in requirement and 'garganta' in learned:return True
    if 'Senkaimon' in requirement and 'senkaimon' in learned:return True
    if any(isinstance(item,dict) and item.get('category')=='travel_permit' and
           item.get('destination')==b and item.get('valid',True) for item in inventory):return True
    # A route previously traveled successfully establishes access to that edge.
    return any(isinstance(r,dict) and r.get('completed') is True and {r.get('origin'),r.get('destination')}=={a,b} for r in seq(s.get('travel_history')))


def _risk(s,node):
    local=obj(obj(s.get('location_details')).get(node['name']))
    explicit=local.get('danger_level')
    if isinstance(explicit,(int,float)) and math.isfinite(explicit):return max(0,min(100,int(explicit)))
    return min(85,max(5,int(node.get('tier',1))*9))


def route_options(s,destination,preparation='normal',companion=''):
    if preparation not in {'normal','cautious','swift','booked_passage'}:raise ValueError('Choose a supported travel preparation.')
    graph=build_travel_graph(s);nodes={n['name']:n for n in graph['nodes']};origin=location_node(s)['name'];destination=location_node(s,destination)['name']
    if origin not in nodes or destination not in nodes:return {'routes':[],'reason':'No mapped connection exists for the current position.'}
    if companion and companion not in {p['name'] for p in companions_here(s,origin)}:raise ValueError('That companion is not currently available here.')
    if origin==destination:return {'routes':[],'reason':'You are already here.'}
    # Enumerate bounded simple paths over the actual graph; no fabricated
    # shortcuts across seas, sealed realms or uncleared Tower floors.
    if s.get('world')=='One Piece':
        same_island=({'Foosha Village','Goa Kingdom','Gray Terminal','Mt. Colubo'},
                     {'Water 7','Galley-La Company'}, {'Dressrosa','Corrida Colosseum'},
                     {'Wano Country','Flower Capital','Udon Prison'})
        for a,edges in graph['edges'].items():
            for edge in edges:
                if not any({a,edge['to']}<=group for group in same_island):
                    sea='A seaworthy boat, ship, or equivalent passage'
                    if 'seaworthy' not in edge['requirement']:
                        edge['requirement']=sea+('; '+edge['requirement'] if edge['requirement'] else '')
    candidates=[];heap=[(0,[origin],[])];seen=0
    while heap and len(candidates)<24 and seen<6000:
        score,path,steps=heapq.heappop(heap);seen+=1
        if path[-1]==destination:candidates.append((score,path,steps));continue
        if len(path)>min(24,len(nodes)):continue
        for edge in graph['edges'].get(path[-1],[]):
            if edge['to'] in path:continue
            heapq.heappush(heap,(score+edge['minutes'],path+[edge['to']],steps+[{'origin':path[-1],**edge}]))
    # Compare fastest, lower danger and a route through an established refuge.
    rated=[]
    for _,path,steps in candidates:
        risk=round(sum(_risk(s,nodes[n]) for n in path[1:])/max(1,len(path)-1))
        shelters=sum(1 for n in path[1:-1] if nodes[n]['kind'] in SETTLEMENTS and n in seq(s.get('discovered_locations')))
        rated.append((path,steps,risk,shelters))
    selected=[]
    for label,sortkey in [('Fastest mapped route',lambda r:sum(e['minutes'] for e in r[1])),
                           ('Lower-danger route',lambda r:(r[2],sum(e['minutes'] for e in r[1]))),
                           ('Via known shelter',lambda r:(-r[3],r[2],sum(e['minutes'] for e in r[1])))]:
        if not rated:break
        row=min(rated,key=sortkey)
        if any(r['route']==row[0] for r in selected):continue
        if label=='Via known shelter' and not row[3]:continue
        path,steps,risk,shelters=row
        factor={'normal':1,'cautious':1.3,'swift':.8,'booked_passage':1}[preparation]
        computed=[{**e,'minutes':max(1,math.ceil(e['minutes']*factor))} for e in steps]
        requirements=list(dict.fromkeys(e['requirement'] for e in steps if e['requirement']))
        locked=[e['requirement'] for e in steps if not _permission(s,e['requirement'],e['origin'],e['to'],preparation)]
        prepared=obj(store(s).get('preparation')).get('expires',-1)>=now(s)
        exposure=max(0,min(100,risk+({'normal':0,'cautious':-18,'swift':15,'booked_passage':-5}[preparation])- (10 if prepared else 0) -(5 if companion else 0)))
        cost=0
        if preparation=='booked_passage' and any('seaworthy' in r for r in requirements):
            if nodes[origin]['kind'] not in SETTLEMENTS|{'island','port','harbor'}:locked.append('Passage can only be booked from a settled port or island.')
            cost=max(.01,round(float(expansion_for(s.get('world')).get('currency_baseline',250))*.04,2)) if expansion_for(s.get('world')).get('tracks_currency',True) else 0
        selected.append({'id':key(*path,preparation,companion),'label':label,'origin':origin,'destination':destination,'route':path,'steps':computed,
                         'minutes':sum(e['minutes'] for e in computed),'risk':risk,'exposure':exposure,'risk_basis':'Campaign danger estimate from known geography; not a combat success probability.',
                         'requirements':requirements,'blocked_requirements':list(dict.fromkeys(locked)), 'available':not locked,'preparation':preparation,
                         'companion':companion,'cost':cost,'currency':obj(s.get('currency')).get('name'), 'shelters':shelters})
    return {'routes':selected,'companions':companions_here(s,origin),'reason':'' if selected else 'No connected mapped route was found.'}


def action_spec(s,payload):
    place=location_node(s,payload.get('place'))['name'];action=text(payload.get('action'))
    if place!=location_node(s)['name']:raise ValueError('You must be at this location before taking an action here.')
    if obj(s.get('combat')).get('active'):raise ValueError('Finish the active encounter before advancing time.')
    if not s.get('alive',True) or int(s.get('hp',1))<=0:raise ValueError('This character cannot take a new action.')
    if action=='journey:start':
        if store(s).get('journey') or store(s).get('pending_activity'):raise ValueError('Resume or cancel the existing activity first.')
        choices=route_options(s,payload.get('destination'),payload.get('preparation','normal'),payload.get('companion',''))['routes']
        choice=next((r for r in choices if r['id']==payload.get('route_id')),None)
        if not choice or not choice['available']:raise ValueError('That route is unavailable or its access requirements are not met.')
        return {**choice,'id':action,'label':'Travel to '+choice['destination'],'place':place}
    action_row=next((r for r in action_list(s,place) if r['id']==action),None)
    if action_row is None:raise ValueError('This activity is no longer available here. Refresh the location.')
    row={**action_row,'place':place}
    if action=='journey:resume':
        journey=obj(store(s).get('journey'))
        expected=journey['route'][journey.get('step_index',0)]
        if place!=expected:raise ValueError('You left the paused journey. Cancel it and plan from your new location.')
        if journey.get('companion') and journey['companion'] not in {p['name'] for p in companions_here(s,place)}:
            raise ValueError('The selected companion is no longer available. Cancel and replan the journey.')
    if action=='activity:resume':
        pending=obj(store(s).get('pending_activity')); original=copy.deepcopy(pending.get('spec',{}))
        if original.get('place')!=place:raise ValueError('Return to the activity location or cancel the unfinished activity.')
        if original.get('id','').startswith(('property:','craft:')):
            from property_economy import refresh_spec
            original=refresh_spec(s,original)
        if original.get('id','').startswith('purchase:'):
            item=next((a for a in catalog(s,place) if a['shop']==original.get('shop') and a['item']==original.get('item')),None)
            if item is None:raise ValueError('That item is no longer available. Cancel the unfinished purchase.')
            original={**item,'place':place}
        row.update(resume_spec=original,cost=original.get('cost',0),currency=original.get('currency'))
    if (action.startswith('train:') or action.startswith('path:')) and float(s.get('resource',0))<math.ceil(float(s.get('resource_max',100))*.1):raise ValueError('Recover energy before starting this training session.')
    if row.get('cost',0)>balance(s,row.get('currency')):raise ValueError('There is not enough currency for this action.')
    return row


def boundary(s,minutes):
    """Only an actual local wide event or player appointment interrupts a service."""
    start=now(s);end=start+minutes;fired=set(seq(s.get('canon_events_fired')));found=[]
    here=location_node(s)['name'];statuses={r['id']:r for r in canon_dependency_graph(s).get('events',[])}
    for e in timeline_for(s.get('world')).get('events',[]):
        ident=f"day:{e.get('day',0)}:{e.get('title','event')}";resolved=obj(statuses.get(ident))
        if e.get('historical_only') or not e.get('major') or e.get('scope')!='wide' or e.get('location')!=here:continue
        if ident in fired or resolved.get('status') in {'impossible','replaced'}:continue
        minute=int(resolved.get('effective_day',e.get('day',0)))*1440+480
        if start<minute<end:found.append((minute, e.get('title','Local event')))
    for i,e in enumerate(seq(s.get('scheduled_events'))):
        if not isinstance(e,dict) or e.get('resolved') or e.get('visibility')=='hidden' or e.get('due_canon_day') is None:continue
        if e.get('location') not in {None,'',here,s.get('location')}:continue
        if f"scheduled:{i}:{e.get('title','event')}" in fired:continue
        minute=int(e['due_canon_day'])*1440+480
        if start<minute<end:found.append((minute,e.get('title','Appointment')))
    # A player-targeted future minor canon event becomes a real intervention stop
    # when its established time falls inside this activity window.
    try:
        from canon_divergence import next_target_in_window
        target=next_target_in_window(s,start,end)
        if target:
            minute,row=target
            if not row.get('location') or row.get('location') in {here,s.get('location')}: found.append((minute,row.get('title','Targeted canon event')))
    except Exception: pass
    # The Tower deadline cannot be bypassed by a long journey/rest.
    deadline=s.get('tower_floor_deadline_day')
    if s.get('world')=='Solo Max-Level Newbie' and isinstance(deadline,(int,float)) and start<int(deadline)*1440<end:
        found.append((int(deadline)*1440,'Tower floor deadline'))
    return min(found) if found else None


def quote(s,payload):
    spec=action_spec(s,payload);duration=int(spec['minutes']);stop=boundary(s,duration)
    return {'spec':spec,'minutes':duration,'start':time_label(s),'end':time_label(s,now(s)+duration),
            'interruption':{'after_minutes':stop[0]-now(s),'title':stop[1]} if stop else None,
            'warnings':(['This approach may begin a potentially lethal encounter; the battle will not auto-resolve.'] if (spec['id'] in {'mission:confront','mission:stealth','mission:negotiate'} or spec['id'].startswith(('expedition:elite:','expedition:boss:')))  else [])+
                       (['Any queued actions and standing plans remain unchanged.'] if s.get('queued_actions') or s.get('standing_orders') else []),
            'calendar':calendar_view(s)}


def _local_turn(game,label,minutes,patch=None,training=False,interrupted='',effects=None):
    """Exercise the same calendar, clocks, XP and world maintenance as Advance."""
    queue=copy.deepcopy(game.state.get('queued_actions',[]));standing=copy.deepcopy(game.state.get('standing_orders',[]))
    data={'narrative':label,'updates':[{'title':'Local activity','type':'action','narrative':label}],
          'state_patch':patch or {},'elapsed':{'amount':minutes,'unit':'minutes'},'deferred_actions':queue,
          'completed_actions':[], 'interrupted':bool(interrupted),'interruption_kind':'world_event' if interrupted else '',
          'interruption_reason':interrupted,'events':[]}
    if training and minutes:game.enforce_training_progress(data,[],minutes,'minutes',[label],'normal')
    if effects:effects()
    result=game.apply_time_skip(data,minutes,'minutes',progression_context={'actions':[label],'elapsed_minutes':minutes,'local_rules':True,'local_award_xp':training})
    game.state['queued_actions']=queue;game.state['standing_orders']=standing
    result.update(state=game.public_state(),generated_locally=True)
    return result


def _finish(game,mission,method,successful=True):
    s=game.state;ad=writable(s);resolved=ad.setdefault('resolved',{})
    before_reward=copy.deepcopy(s)
    if mission['id'] in resolved:return
    mission.update(status='completed' if successful else 'withdrawn',method=method,finished_minute=now(s))
    resolved[mission['id']]=copy.deepcopy(mission)
    quest=next((q for q in seq(s.get('quests')) if isinstance(q,dict) and q.get('id')==mission['id']),None)
    if quest:
        quest['status']='Completed' if successful else 'Abandoned'
        for objective in seq(quest.get('objectives')):objective.update(status='complete' if successful else 'failed',progress=100 if successful else 0)
    place=mission['origin'];description=mission['success'] if successful else 'The assignment was left unfinished. The existing situation remains; no reward was issued.'
    changes=[]
    if successful:
        xp=game.apply_system_xp(before_reward,['Complete local quest: '+mission['title']],[],0,'normal',[{'message':'Quest completed'}])
        if xp.get('xp_awarded'):changes.append(f"{xp['xp_awarded']} XP awarded by the existing progression rules")

        if expansion_for(s.get('world')).get('tracks_currency',True):
            reward=max(.01,round(float(expansion_for(s.get('world')).get('currency_baseline',250))*.12,2))
            record_currency_transaction(s,reward,mission['title'],'adventure_reward',source='living_adventures')
            changes.append(f"{reward:g} {obj(s.get('currency')).get('name','currency')} received")
        contact=mission['contact'];s.setdefault('npc_memories',{}).setdefault(contact,{'person_id':key(s.get('campaign_id'),place,contact),'status':'active','last_known_location':place})
        relation=s.setdefault('relationships',{}).setdefault(contact,{'score':0})
        if isinstance(relation,dict):relation['score']=min(100,int(relation.get('score',0))+(15 if method=='Negotiated agreement' else 10))
        local=s.setdefault('location_details',{}).setdefault(place,{})
        if mission['benefit']=='safer_route':
            edges=build_travel_graph(s)['edges'].get(place,[])
            if edges:
                dest=min(edges,key=lambda r:r['minutes'])['to']
                s.setdefault('world_benefits',{})['adventure:'+mission['id']]={'active':True,'kind':'safer_route','origin':place,'destination':dest,'factor':.85,'source':mission['id']}
                changes.append(f"Supply link to {dest} restored: 15% shorter mapped travel")
        elif mission['benefit']=='shelter':
            local.setdefault('services',[])
            if 'Relief shelter' not in local['services']:local['services'].append('Relief shelter')
            local['adventure_shelter']=True;changes.append('Relief shelter opened: rest recovers 25% more per hour here')
        else:
            local.setdefault('adventure_contacts',[])
            if contact not in local['adventure_contacts']:local['adventure_contacts'].append(contact)
            s['npc_memories'][contact]['public_goal']='Help you prepare for future local journeys.'
            changes.append('Courier contact established: future preparation lasts three days')
    message=f"{mission['title']} — {method}. {description}"+(' '+ '; '.join(changes)+'.' if changes else '')
    if successful and text(obj(obj(s.get('npc_memories')).get(mission['contact'])).get('status')).lower() not in UNAVAILABLE:
        game.add_chat_message(mission['contact'],mission['contact'],description+' '+('; '.join(changes)),metadata={'generated_locally':True,'adventure_id':mission['id']})
    game.append(message,'narrative',canon_day=s.get('canon_day'),detail={'adventure_id':mission['id'],'aftermath':True})
    entry=game.story_log[-1]
    row={'id':mission['id'],'location':place,'title':mission['title'],'description':description,'changes':changes,'method':method,'success':successful,
         'canon_day':s.get('canon_day'),'story_id':entry['id'],'world_time':s.get('world_time')}
    ad.setdefault('aftermath',[]).append(row);ad['aftermath']=ad['aftermath'][-100:]
    ad.pop('active',None)
    game.archive_finished_quests()


def combat_finished(game,outcome):
    combat=obj(game.state.get('combat'));objective=obj(combat.get('adventure_objective'))
    if not objective or objective.get('settled'):return
    if objective.get('expedition_id'):
        from expeditions import combat_finished as expedition_combat_finished
        expedition_combat_finished(game,outcome)
        objective['settled']=True
        return
    objective['settled']=True
    mission=obj(store(game.state).get('active'))
    if mission and mission.get('id')==objective.get('mission_id'):
        _finish(game,mission,'Objective secured' if outcome=='objective_complete' else 'Retreated' if outcome=='fled' else 'Objective lost',outcome=='objective_complete')
    journey=obj(store(game.state).get('journey'))
    if objective.get('journey_id')==journey.get('id') and journey:
        journey['encounter_resolved']=True
        if outcome in {'defeat','objective_failed'}:journey['blocked']='Recover or cancel this journey before continuing.'


def start_encounter(game,mission=None,journey=None):
    s=game.state
    if obj(s.get('combat')).get('active'):raise ValueError('An encounter is already active.')
    world=s.get('world');flavor=WORLD_FLAVOR.get(world,WORLD_FLAVOR['Custom World'])
    prepared=obj(store(s).get('preparation')).get('expires',-1)>=now(s)
    power=min(60,20+location_node(s).get('tier',1)*5)
    count=1 if prepared else 2
    kind=mission['kind'] if mission else 'escape'
    s['combat']={'active':True,'tactical_enabled':True,'cause':mission['title'] if mission else 'Exposed journey route',
                 'enemy':{'name':flavor[5].title()+' — '+(mission['title'] if mission else 'Journey pursuit'),'power':power,'hp':power*2*count,'hp_max':power*2*count,'is_group':count>1,'group_size':count},
                 'adventure_objective':{'kind':kind,'mission_id':mission.get('id') if mission else None,'journey_id':journey.get('id') if journey else None,
                    'rounds_required':4,'rounds_survived':0,'target_hp':60,'target_hp_max':60,'carried_by':None,'settled':False},'log':[]}
    game.ensure_combat_numbers()
    from tactical_combat import ensure_board
    ensure_board(s)
    game.acknowledge_danger_scenario(s['combat']['cause'])
    game.append(f"{s['combat']['cause']}. Your objective is {'to retrieve the dispatch and return to the marked exit' if kind=='retrieval' else 'to protect the relief beacon for four rounds' if kind=='protection' else 'to reach the marked far exit with the testimony'}. Killing every opponent is not required.",'narrative',canon_day=s.get('canon_day'))


def _mission_effect(game,action):
    s=game.state;ad=writable(s);place=location_node(s)['name'];mission=mission_offer(s,place)
    if not mission:raise ValueError('There is no available local adventure.')
    if action=='mission:accept':
        mission.update(status='active',stage='briefed');ad['active']=mission
        s.setdefault('quests',[]).append({'id':mission['id'],'name':mission['title'],'status':'Active','giver':mission['contact'],'location':place,
          'description':mission['description'],'explanation':mission['description'],'next_hint':'Investigate the witness, negotiate, infiltrate, or enter the encounter.',
          'objectives':[{'id':'objective','text':mission['description'],'status':'active','progress':0}], 'adventure_id':mission['id']})
        s.setdefault('npc_memories',{}).setdefault(mission['contact'],{'person_id':key(s.get('campaign_id'),place,mission['contact']),'last_known_location':place,'status':'active','public_goal':'Recover the local supply connection.'})
        return 'The local assignment is accepted. '+mission['description']
    mission=ad['active']
    if action=='mission:investigate':
        mission.update(investigated=True,stage='investigated')
        return 'The witness identifies an overlooked approach to the waystation. Preparation improves your negotiation and discreet approach; the objective and opposition are now confirmed.'
    if action=='mission:withdraw':_finish(game,mission,'Voluntary withdrawal',False);return 'You withdraw from the assignment. Its outcome is recorded without an invented punishment.'
    if action in {'mission:negotiate','mission:stealth'}:
        mission['attempts']=int(mission.get('attempts',0))+1
        names=('charisma','wisdom','intelligence','charm','presence') if action.endswith('negotiate') else ('dexterity','agility','speed','control','perception')
        stats=obj(s.get('stats'));relevant=[float(v) for k,v in stats.items() if any(n in k.casefold() for n in names) and isinstance(v,(int,float))]
        best=max(relevant or [20]);chance=max(15,min(90,25+int(best/3)+(25 if mission.get('investigated') else 0)))
        roll=int(key(s.get('campaign_id'),mission['id'],mission['attempts'],action),16)%100+1
        mission['approach_check']={'chance':chance,'roll':roll,'success':roll<=chance,'method':action}
        if roll<=chance:
            _finish(game,mission,'Negotiated agreement' if action.endswith('negotiate') else 'Discreet recovery')
            return f"Your approach succeeds ({roll} against {chance}). The local objective is secured without a battle."
        start_encounter(game,mission)
        return f"Your approach is discovered ({roll} against {chance}). The objective is still in reach, but the opposition now contests it. The tactical encounter awaits your decisions."
    start_encounter(game,mission)
    return 'You enter the contested waystation. The tactical objective is marked; prepare your first move.'


def resolve(game,payload,spec):
    s=game.state;ad=writable(s);action=spec['id'];duration=int(spec['minutes']);place=spec['place']
    if duration>366*1440:raise ValueError('Plan this journey in shorter stages.')
    if action=='journey:cancel':
        ad.pop('journey',None);game.append('The journey ends at the last reached waypoint. Untraveled distance is not counted.','narrative')
        return {'state':game.public_state(),'story':game._flush_story(),'status':'resolved','elapsed':{'amount':0,'unit':'minutes'}}
    if action=='activity:cancel':
        ad.pop('pending_activity',None);game.append('The unfinished activity is left behind. No unearned completion reward was granted.','narrative')
        return {'state':game.public_state(),'story':game._flush_story(),'status':'resolved','elapsed':{'amount':0,'unit':'minutes'}}
    if action in {'journey:start','journey:resume'}:return resolve_journey(game,spec)
    if action=='activity:resume':
        pending=ad.pop('pending_activity');spec=spec['resume_spec'];action=spec['id'];duration=pending['remaining_minutes']
    stop=boundary(s,duration);elapsed=stop[0]-now(s) if stop else duration
    complete=elapsed==duration;patch={};label=spec['label'];training=action.startswith('train:')
    if action.startswith('rest:'):
        rate=.12*(1.25 if obj(obj(s.get('location_details')).get(place)).get('adventure_shelter') else 1)
        for field in ('hp','resource'):
            cap=max(1,int(s.get(field+'_max',100)));patch[field]=min(cap,float(s.get(field,0))+round(cap*rate*elapsed/60))
        label=f"You rest at {place} for {elapsed} minutes, recovering ordinary health and {s.get('resource_name','energy')}. Special injuries remain unchanged."
    elif training:
        cost=math.ceil(int(s.get('resource_max',100))*.1*elapsed/max(1,int(spec['minutes'])))
        if cost>int(s.get('resource',0)):raise ValueError('Recover energy before resuming training.')
        patch['resource']=max(0,int(s.get('resource',0))-cost)
        label=f"Practice {action.split(':',1)[1]} at {place} for {elapsed} minutes. The session uses {cost} {s.get('resource_name','energy')}."
    elif action.startswith(('path:','conflict:','expedition:','property:','craft:','reputation:')):
        label=f"{spec['label']} progresses for {elapsed} minutes." if not complete else spec['label']
    elif not complete:label=f"{spec['label']} is interrupted after {elapsed} minutes by {stop[1]}. The unfinished part can be resumed; no completion reward is granted yet."
    # Apply ordinary world time first. Only a fully completed service gets its
    # purchase, information or mission effect; the transaction protects both.
    result=_local_turn(game,label,elapsed,patch,training,stop[1] if stop else '')
    s=game.state;ad=writable(s)
    if not complete:
        ad['pending_activity']={'label':spec['label'],'spec':copy.deepcopy(spec),'remaining_minutes':duration-elapsed}
    elif action.startswith('path:'):
        from character_paths import resolve_session
        from property_economy import training_bonus
        outcome=resolve_session(s,action,elapsed,complete,training_bonus(s,place))
        game.append(f"{spec['label']} — mastery +{outcome['mastery_gain']:g}; {outcome['path']['stage']}.",'narrative',canon_day=s.get('canon_day'))
    elif action.startswith('conflict:'):
        from world_conflict import resolve_intervention
        game.append(resolve_intervention(s,action,elapsed)['message'],'narrative',canon_day=s.get('canon_day'))
    elif action.startswith('expedition:'):
        from expeditions import resolve as resolve_expedition
        game.append(resolve_expedition(s,action,elapsed,game).get('message','Expedition advanced.'),'narrative',canon_day=s.get('canon_day'))
    elif action.startswith(('property:','craft:')):
        from property_economy import resolve as resolve_property
        game.append(resolve_property(s,spec)['message'],'narrative',canon_day=s.get('canon_day'))
    elif action=='reputation:laylow':
        from reputation_system import lay_low
        game.append(lay_low(s,place,elapsed/60).get('summary','You keep a low profile.'),'narrative',canon_day=s.get('canon_day'))
    elif action=='scout':
        neighbors=build_travel_graph(s)['edges'].get(place,[])
        discovered=s.setdefault('discovered_locations',[])
        for edge in neighbors:
            if edge['to'] not in discovered:discovered.append(edge['to'])
        game.append('The survey identifies mapped connections: '+(', '.join(e['to'] for e in neighbors) or 'no additional mapped route')+'. This is geographic information, not permission to enter a sealed area.','narrative',canon_day=s.get('canon_day'))
    elif action=='prepare':
        days=3 if obj(obj(s.get('location_details')).get(place)).get('adventure_contacts') else 1
        ad['preparation']={'origin':place,'expires':now(s)+days*1440,'prepared_minute':now(s)}
        game.append(f"You review the local route reports. Field preparation is ready for the next journey and remains current for {days} day(s).",'narrative',canon_day=s.get('canon_day'))
    elif action.startswith('talk:'):
        name=action.split(':',1)[1];goal=next((r['goal'] for r in available_people(s,place) if r['name']==name),'')
        mission=obj(ad.get('active'))
        if mission.get('contact')==name:
            response=('You know the overlooked approach now. A peaceful settlement or a discreet recovery could work; the marked objective remains the priority.'
                      if mission.get('investigated') else mission.get('description','')+' Speak to the witness before committing to an approach.')
        elif goal:response='My current concern is '+goal.rstrip('.')+'.'
        else:response='I can confirm our current point of contact. Ask about a specific known matter when you are ready.'
        game.add_chat_message(name,name,response,metadata={'generated_locally':True,'activity':'local_checkin'})
        ad.setdefault('conversation_history',[]).append({'person':name,'minute':now(s),'summary':response})
        ad['conversation_history']=ad['conversation_history'][-80:]
        game.append(f"You check in with {name}. {response}",'narrative',canon_day=s.get('canon_day'))
    elif action.startswith('purchase:'):
        from systems import resolve_shop_purchase
        ok,message,_=resolve_shop_purchase(s,spec['shop'],spec['item'])
        if not ok:raise ValueError(message)
        game.append(message,'narrative',canon_day=s.get('canon_day'))
    elif action.startswith('mission:'):
        message=_mission_effect(game,action)
        game.append(message,'narrative',canon_day=s.get('canon_day'))
    result['story']=list(result.get('story',[]))+game._flush_story();result['state']=game.public_state()
    result['adventure_view']=location_view(s,place)
    return result


def resolve_journey(game,spec):
    s=game.state;ad=writable(s)
    if spec['id']=='journey:start':
        if spec.get('cost',0)>currency_balance(s):raise ValueError('There is not enough currency to book passage.')
        if spec.get('cost'):record_currency_transaction(s,-spec['cost'],'Booked journey passage','travel',source='living_adventures')
        journey=copy.deepcopy(spec);journey.update(id=key(s.get('campaign_id'),now(s),spec['destination'],s.get('turn')),step_index=0,step_progress=0,
             remaining_minutes=spec['minutes'],encounter_resolved=False,encounter_triggered=False)
        ad['journey']=journey
    else:journey=ad['journey']
    if journey.get('blocked'):
        if float(s.get('hp',0))<float(s.get('hp_max',100))*.25:raise ValueError(journey['blocked'])
        journey.pop('blocked',None)
    start=now(s);remaining=int(journey['remaining_minutes']);stop=boundary(s,remaining)
    elapsed=min(remaining,stop[0]-start) if stop else remaining
    # A high-exposure route may create one seeded pursuit, never one fight per
    # mile. Cautious routing/preparation actually changes eligibility.
    pursuit=False
    if not journey.get('encounter_triggered') and journey.get('exposure',0)>=55:
        sample=int(key(s.get('campaign_id'),journey['id'],'pursuit'),16)%100
        if sample<journey['exposure']-35:
            at=max(1,remaining//2)
            if at<elapsed:elapsed=at;pursuit=True;stop=None
    budget=elapsed;reached=location_node(s)['name'];history=[]
    while budget and journey['step_index']<len(journey['steps']):
        edge=journey['steps'][journey['step_index']];need=edge['minutes']-journey['step_progress'];spent=min(need,budget)
        budget-=spent;journey['step_progress']+=spent;journey['remaining_minutes']-=spent
        if journey['step_progress']==edge['minutes']:
            history.append({'origin':edge['origin'],'destination':edge['to'],'minutes':edge['minutes'],'completed':True,'journey_id':journey['id']})
            reached=edge['to'];journey['step_index']+=1;journey['step_progress']=0
    finished=journey['remaining_minutes']==0
    note=f"You travel toward {journey['destination']} via {' → '.join(journey['route'])}. {elapsed} minutes pass. "
    note+=f"You arrive at {reached}." if finished else f"Your last reached waypoint is {reached}; the remaining distance is retained."
    result=_local_turn(game,note,elapsed,{'location':reached},interrupted='Pursuit on an exposed route' if pursuit else stop[1] if stop else '')
    ad=writable(game.state);ad['journey']=journey
    companion=journey.get('companion')
    if companion:
        for row in seq(game.state.get('companions')):
            if isinstance(row,dict) and row.get('name')==companion:row['location']=reached
        for field in ('npc_memories','contacts'):
            record=obj(game.state.get(field)).get(companion)
            if isinstance(record,dict):record['last_known_location']=reached
    game.state.setdefault('travel_history',[]).extend(history)
    game.state['travel_history']=game.state['travel_history'][-200:]
    known=game.state.setdefault('discovered_locations',[])
    for row in history:
        if row['destination'] not in known:known.append(row['destination'])
    if finished:
        ad.pop('journey',None);ad.pop('preparation',None)
    elif pursuit:
        journey['encounter_triggered']=True;start_encounter(game,journey=journey)
    result['story']=list(result.get('story',[]))+game._flush_story();result['state']=game.public_state()
    result['adventure_view']=location_view(game.state,reached)
    return result
