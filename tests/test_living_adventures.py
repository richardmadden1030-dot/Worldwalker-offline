"""Real rules and authenticated request contracts; all model/network calls forbidden."""
import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from test_reliability_update import session, state
from living_adventures import (action_list, action_spec, boundary, catalog, companions_here, location_node,
    location_view, mission_offer, route_options, start_encounter, combat_finished, available_people)
from world_calendar import PROFILES, date_for, parts_for, duration_minutes, view
from worlds import WORLD_DATA, abilities_for, format_calendar_date
from simulation_integrity import _map_nodes, build_travel_graph
from tactical_combat import ensure_board, board_view, submit_tactical_action
from encounter_objectives import outcome, npc_action
from state_guard import apply_guarded_patch


@pytest.fixture(autouse=True)
def forbid_models(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('A timed local action must not call a model')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)


def quote(client,action,place='Winston',**extra):
    r=client.post('/api/adventures/preview',json={'action':action,'place':place,**extra})
    assert r.status_code==200,r.get_json()
    return r.get_json()


def payload(q):
    return {'confirmed':True,'token':q['token'],'expected_campaign':q['expected_campaign'],
            'expected_guard':q['expected_guard'],'request_id':str(uuid4())}


def commit(client,q):
    r=client.post('/api/adventures/resolve',json=payload(q));assert r.status_code==200,r.get_json();return r.get_json()


def local(client,action,place='Winston',**extra):return commit(client,quote(client,action,place,**extra))


def mission(game,kind='retrieval'):
    from living_adventures import TEMPLATES,key
    template=next(t for t in TEMPLATES if t['kind']==kind)
    row={**template,'id':key(game.state['campaign_id'],kind),'origin':game.state['location'],'status':'active','contact':'Local courier','investigated':False}
    game.state['adventures']={'active':row}
    game.state['quests']=[{'id':row['id'],'adventure_id':row['id'],'name':row['title'],'status':'Active','objectives':[]}]
    start_encounter(game,row)
    return game.state['combat']['tactical'],game.state['combat']['adventure_objective']


def command(game,action,**kw):
    b=game.state['combat']['tactical']
    return submit_tactical_action(game,{'request_id':str(uuid4()),'revision':b['revision'],'action':action,**kw})


@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_every_world_has_fixed_calendar_and_real_local_clock(session,world):
    app,game,client=session
    game.state=state(world);game.state['location']=_map_nodes(world)[0]['name']
    before=copy.deepcopy(game.state)
    q=quote(client,'rest:60',game.state['location'])
    assert game.state==before
    result=commit(client,q)
    assert result['state']['canon_time_minutes']==before['canon_time_minutes']+60
    assert result['state']['_world_calendar']['date']==view(game.state)['date']
    assert 'January 1, Year 1' not in result['state']['world_time']
    assert result['elapsed']=={'amount':60,'unit':'minutes'}
    assert result['generated_locally']


@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_world_calendar_never_restarts_for_another_starting_era(world):
    assert format_calendar_date(world,0,None,-700)==format_calendar_date(world,0,None,400)
    assert date_for(world,10)-date_for(world,-10)==dt.timedelta(days=20)
    assert PROFILES[world]['precision'] and PROFILES[world]['note']


def test_calendar_anchors_and_legacy_epoch():
    assert date_for('Jujutsu Kaisen',183)==dt.date(2018,10,31)
    assert date_for('One Piece',17)==dt.date(1522,2,18)
    assert date_for('Hunter x Hunter',7)==dt.date(1999,1,7)
    assert parts_for('Naruto',-4380)['month']==10
    assert parts_for('Naruto',-4380)['day']==10
    assert date_for('Custom World',2,'2024-01-31',0)==dt.date(2024,2,2)
    assert date_for('Solo Max-Level Newbie',-3,'2026-08-06',-3)==dt.date(2026,8,6)
    assert parts_for('Custom World',10**12) is None


def test_month_end_leap_year_and_clock_alignment(session):
    _,game,_=session;game.state.update(world='Custom World',canon_day=0,canon_time_minutes=480,calendar_epoch='2024-01-31',calendar_anchor_day=0)
    assert duration_minutes(game.state,1,'months')==29*1440
    before=copy.deepcopy(game.state);game.advance_clock(before,1,'months')
    assert view(game.state)['date']=='February 29, 2024'
    before=copy.deepcopy(game.state);game.advance_clock(before,1,'months')
    assert view(game.state)['date']=='March 29, 2024'
    assert game.state['canon_time_minutes']==(29+29)*1440+480


@pytest.mark.parametrize('amount,unit',[(float('nan'),'hours'),(float('inf'),'days'),(-1,'minutes'),(1,'nonsense')])
def test_invalid_durations_do_not_enter_calendar(amount,unit):
    with pytest.raises(ValueError):duration_minutes(state(),amount,unit)


def test_javascript_python_calendar_parity():
    script=(Path(__file__).parents[1]/'frontend/js/world-calendar.js').read_text()
    cases=[(world,day) for world in PROFILES for day in (-4900,-4380,-365,-7,0,17,183,365,1500)]
    result=subprocess.check_output(['node','-e',script+';console.log(JSON.stringify('+json.dumps(cases)+'.map(([world,day])=>WorldCalendar.format(world,day))));'],text=True)
    assert json.loads(result)==[format_calendar_date(w,d) for w,d in cases]


def test_read_views_and_cancel_change_nothing(session):
    _,game,client=session;before=copy.deepcopy(game.state);history=copy.deepcopy(game.story_log)
    assert client.get('/api/adventures/location?place=Winston').status_code==200
    q=quote(client,'scout');assert q['minutes']==30
    assert game.state==before and game.story_log==history
    r=client.post('/api/adventures/resolve',json={**payload(q),'confirmed':False})
    assert r.status_code==400 and game.state['canon_time_minutes']==before['canon_time_minutes']
    assert game.state['inventory']==before['inventory']


def test_timed_action_keeps_draft_plans_and_replays_once(session):
    _,game,client=session
    game.state['queued_actions']=['Explore later','Visit my friend'];game.state['standing_orders']=['Watch for messages']
    q=quote(client,'rest:60');body=payload(q);t=game.state['canon_time_minutes']
    r=client.post('/api/adventures/resolve',json=body);assert r.status_code==200,r.get_json()
    r=client.post('/api/adventures/resolve',json=body);assert r.status_code==200 and r.get_json()['replayed_request']
    assert game.state['canon_time_minutes']==t+60
    assert game.state['queued_actions']==['Explore later','Visit my friend']
    assert game.state['standing_orders']==['Watch for messages']
    assert len([e for e in game.story_log if e['tag']=='receipt'])==1
    game.save();game.load(Path(game.savepath()).stem)
    r=client.get('/api/action/status',query_string={'route':'adventure_resolve','request_id':body['request_id']})
    assert r.get_json()['status']=='completed'
    assert game.state['canon_time_minutes']==t+60


def test_quote_rejects_tampering_stale_state_and_remote_activity(session):
    _,game,client=session;q=quote(client,'rest:60');t=game.state['canon_time_minutes']
    assert client.post('/api/adventures/resolve',json={**payload(q),'token':q['token']+'x'}).status_code==400
    game.state['hp']-=1
    assert client.post('/api/adventures/resolve',json=payload(q)).status_code==400
    assert client.post('/api/adventures/preview',json={'place':'Reidan','action':'rest:60'}).status_code==400
    assert client.post('/api/adventures/preview',json={'place':'Winston','action':'invent_new_reward'}).status_code==400
    assert game.state['canon_time_minutes']==t


def test_busy_action_rejected_and_quote_bound_to_campaign(session):
    _,game,client=session;q=quote(client,'rest:60');game.busy=True
    assert client.post('/api/adventures/resolve',json=payload(q)).status_code==409
    game.busy=False;game.state['campaign_id']='different'
    assert client.post('/api/adventures/resolve',json=payload(q)).status_code==400


def test_real_purchase_cost_stock_and_retry(session):
    _,game,client=session
    game.state['shops']=[{'name':'Supply stall','location':'Winston','inventory':[{'name':'Bandage','price':'2 Gold','stock':1,'healing':10}]}]
    action=catalog(game.state,'Winston')[0];q=quote(client,action['id']);t=game.state['canon_time_minutes']
    assert q['spec']['cost']==2
    body=payload(q);r=client.post('/api/adventures/resolve',json=body);assert r.status_code==200,r.get_json()
    assert game.state['canon_time_minutes']==t+10
    assert any(i['name']=='Bandage' for i in game.state['inventory'])
    assert not game.state['shops'][0]['inventory']
    assert client.post('/api/adventures/resolve',json=body).get_json()['replayed_request']
    assert len([i for i in game.state['inventory'] if i['name']=='Bandage'])==1


def test_missing_stock_rolls_back_time(session,monkeypatch):
    _,game,client=session
    game.state['shops']=[{'name':'Stall','location':'Winston','inventory':[{'name':'Potion','price':2,'stock':1}]}]
    q=quote(client,catalog(game.state,'Winston')[0]['id']);t=game.state['canon_time_minutes']
    monkeypatch.setattr('systems.resolve_shop_purchase',lambda *a:(False,'Stock unavailable',None))
    r=client.post('/api/adventures/resolve',json=payload(q));assert r.status_code==400
    assert game.state['canon_time_minutes']==t and not game.state['inventory']


def test_activity_boundary_resume_and_no_premature_purchase(session):
    _,game,client=session
    game.state.update(canon_day=10,canon_time_minutes=10*1440+475,calendar_anchor_day=0)
    game.state['scheduled_events']=[{'title':'Meet the courier','location':'Winston','due_canon_day':10}]
    game.state['shops']=[{'name':'Stall','location':'Winston','inventory':[{'name':'Potion','price':2,'stock':1}]}]
    q=quote(client,catalog(game.state,'Winston')[0]['id']);assert q['interruption']['after_minutes']==5
    r=commit(client,q);assert r['interrupted']
    assert game.state['adventures']['pending_activity']['remaining_minutes']==5 and not game.state['inventory']
    game.state['shops'][0]['inventory'][0]['price']=3
    resumed=quote(client,'activity:resume');assert resumed['minutes']==5 and resumed['spec']['cost']==3
    commit(client,resumed)
    assert len(game.state['inventory'])==1 and not game.state['adventures'].get('pending_activity')
    assert game.state['canon_time_minutes']==10*1440+485


def test_people_exclude_dead_contacts_and_nonparty_travel():
    s=state();s['npc_memories']={'Mira':{'status':'dead','last_known_location':'Winston'},'Ren':{'last_known_location':'Winston'}}
    s['contacts']={'Mira':{'status':'active','location':'Winston'}}
    s['companions']=[{'name':'Ren','location':'Winston','status':'active'}]
    assert {p['name'] for p in available_people(s,'Winston')}=={'Ren'}
    assert {p['name'] for p in companions_here(s,'Winston')}=={'Ren'}


def test_journey_options_real_edges_and_pace():
    s=state();graph=build_travel_graph(s);destination=graph['edges']['Winston'][0]['to']
    choices=route_options(s,destination)['routes'];assert choices
    assert len({tuple(r['route']) for r in choices})==len(choices)
    fast=choices[0];slow=route_options(s,destination,'cautious')['routes'][0]
    assert slow['minutes']>fast['minutes'] and slow['exposure']<=fast['exposure']
    for r in choices:
        assert sum(e['minutes'] for e in r['steps'])==r['minutes']
        for e in r['steps']:assert any(original['to']==e['to'] for original in graph['edges'][e['origin']])


def test_sea_and_tower_access_are_not_fabricated():
    s=state('One Piece');s['location']='Foosha Village'
    ocean=next(r for r in route_options(s,'Shells Town')['routes'] if r['requirements'])
    assert not ocean['available']
    s['inventory']=[{'name':'Small seaworthy boat','seaworthy':True}]
    assert route_options(s,'Shells Town')['routes'][0]['available']
    s=state('Solo Max-Level Newbie');s['location']='Floor 1';s['tower_floor']=1
    assert not route_options(s,'Floor 3')['routes'][0]['available']


def test_journey_commits_only_reached_waypoints_and_moves_companion(session):
    _,game,client=session;graph=build_travel_graph(game.state);destination=graph['edges']['Winston'][0]['to']
    game.state['companions']=[{'name':'Ren','location':'Winston','status':'active'}]
    game.state['location_details']={n['name']:{'danger_level':0} for n in graph['nodes']}
    qroute=route_options(game.state,destination,companion='Ren')['routes'][0]
    assert qroute['available']
    t=game.state['canon_time_minutes'];q=quote(client,'journey:start',destination=destination,route_id=qroute['id'],preparation='normal',companion='Ren')
    result=commit(client,q)
    assert game.state['location']==destination and game.state['canon_time_minutes']==t+qroute['minutes']
    assert game.state['companions'][0]['location']==destination
    assert destination in game.state['discovered_locations']
    assert not game.state['adventures'].get('journey')


@pytest.mark.parametrize('world',list(WORLD_DATA))
@pytest.mark.parametrize('kind',['retrieval','protection','escape'])
def test_objective_boards_support_all_worlds_without_refresh_progress(session,world,kind):
    _,game,_=session;game.state=state(world);game.state['location']=_map_nodes(world)[0]['name']
    b,g=mission(game,kind);start=copy.deepcopy(g);rnd=game.state['combat']['round']
    for _ in range(5):board_view(game.state)
    assert g==start and game.state['combat']['round']==rnd
    assert g['target']!=g['exit'] or kind!='retrieval'
    assert all(0<=x<b['width'] for x in g['target'])


@pytest.mark.parametrize('kind',['retrieval','escape'])
def test_kill_all_cannot_replace_objective_and_actual_goal_commits_once(session,kind):
    _,game,client=session;b,g=mission(game,kind)
    for u in b['units']:
        if u['side']=='enemy':u.update(hp=0,defeated=True)
    assert outcome(game.state,b,'victory') is None
    player=next(u for u in b['units'] if u.get('player'))
    if kind=='retrieval':
        player['x'],player['y']=g['target'];command(game,'objective')
        assert g['carried_by']=='player'
    player['x'],player['y']=g['exit'];player['action_used']=False
    command(game,'defend')
    assert not game.state['combat']['active'] and game.state['combat']['outcome']=='objective_complete'
    assert len(game.state['adventures']['aftermath'])==1
    balance=copy.deepcopy(game.state['currency']);combat_finished(game,'objective_complete')
    assert game.state['currency']==balance and len(game.state['adventures']['aftermath'])==1
    assert game.state['quest_archive'][0]['status']=='Completed'
    entry=game.state['adventures']['aftermath'][0]
    assert client.get('/api/adventures/aftermath?story_id='+entry['story_id']).status_code==200
    game.save();game.load(Path(game.savepath()).stem)
    assert game.state['adventures']['aftermath'][0]['story_id']==entry['story_id']


def test_beacon_damage_shield_rounds_and_loss(session):
    _,game,_=session;b,g=mission(game,'protection');enemy=next(u for u in b['units'] if u['side']=='enemy')
    b['obstacles']=[];g['target']=[5,5];enemy.update(x=5,y=6,movement_left=0,movement_max=0)
    before=g['target_hp'];assert npc_action(game,b,enemy);plain=before-g['target_hp'];assert plain>0
    g['shield_round']=game.state['combat']['round'];before=g['target_hp'];npc_action(game,b,enemy)
    assert before-g['target_hp']<plain
    game.state['combat']['round']=g['started_round']+3;assert outcome(game.state,b,None) is None
    game.state['combat']['round']+=1;assert outcome(game.state,b,None)=='objective_complete'
    g['target_hp']=0;assert outcome(game.state,b,None)=='objective_failed'


def test_carrier_drop_and_distance_validation(session):
    _,game,_=session;b,g=mission(game,'retrieval')
    with pytest.raises(ValueError,match='Move next'):command(game,'objective')
    b=game.state['combat']['tactical'];g=game.state['combat']['adventure_objective'];p=next(u for u in b['units'] if u.get('player'))
    g['carried_by']='player';p.update(hp=0,defeated=True)
    outcome(game.state,b,None)
    assert g['carried_by'] is None and g['target']==[p['x'],p['y']]


def test_failed_objective_awards_no_reward_and_journey_has_no_phantom_mission(session):
    _,game,_=session;b,g=mission(game,'protection');before=copy.deepcopy(game.state['currency'])
    game.end_combat('objective_failed')
    assert game.state['currency']==before and not game.state['adventures']['aftermath'][0]['success']
    game.state['combat']={};game.state['adventures']={'journey':{'id':'road','destination':'Bairan'}}
    start_encounter(game,journey=game.state['adventures']['journey'])
    combat_finished(game,'fled')
    assert game.state['adventures']['journey']['encounter_resolved']


def test_narrator_cannot_complete_local_objective_or_rewrite_mission(session):
    _,game,_=session;b,g=mission(game)
    apply_guarded_patch(game.state,{'combat':{'active':False},'quests':[],'adventures':{'resolved':{'fake':{}}}})
    assert game.state['combat']['active'] and game.state['quests'][0]['adventure_id']
    assert not game.state['adventures'].get('resolved')
    with pytest.raises(ValueError,match='tactical objective'):game.run_time_skip(1,'days',[],'normal',{})


def test_canon_reference_unmasked_but_not_npc_knowledge(session):
    _,game,client=session
    game.state.update(world='Naruto',canon_day=-7,canon_time_minutes=-7*1440+480)
    game.settings['show_canon_spoilers']=False
    before=copy.deepcopy(game.state.get('npc_knowledge',{}))
    data=client.get('/api/panels').get_json()
    assert data['canon_reference_visible']
    assert any(e['day']>100 and 'Masked' not in e['title'] for e in data['canon_dependencies']['events'])
    assert game.state.get('npc_knowledge',{})==before


def test_rest_and_preparation_do_not_farm_passive_xp(session):
    _,game,client=session
    before={k:copy.deepcopy(game.state[k]) for k in ('xp','level','stats')}
    for action in ('rest:60','prepare','rest:480'):
        local(client,action)
    assert {k:game.state[k] for k in before}==before


def test_monthly_assessment_budget_uses_actual_leap_month(session):
    _,game,_=session
    game.state.update(world='Custom World',canon_day=0,canon_time_minutes=480,
                      calendar_epoch='2024-01-31',calendar_anchor_day=0)
    assert game.time_budget(1,'months',['Rest'])['available_minutes']==29*1440


def test_all_three_adventure_aftermaths_apply_real_benefits(session):
    from living_adventures import _finish, TEMPLATES
    _,game,client=session
    route_before=route_options(game.state,'Reinhardt')['routes'][0]['minutes']
    for i,t in enumerate(TEMPLATES):
        row={**t,'id':'durable-'+str(i),'origin':'Winston','contact':'Lysa','status':'active'}
        game.state.setdefault('adventures',{})['active']=row
        _finish(game,row,'Negotiated agreement')
    assert len(game.state['adventures']['aftermath'])==3
    assert game.state['location_details']['Winston']['adventure_shelter']
    assert route_options(game.state,'Reinhardt')['routes'][0]['minutes']<=route_before
    game.state['hp']=20;local(client,'rest:60')
    assert game.state['hp']==35
    local(client,'prepare')
    assert game.state['adventures']['preparation']['expires']==game.state['canon_time_minutes']+3*1440


def test_appointment_pauses_journey_and_resume_preserves_distance(session):
    _,game,client=session
    game.state['canon_time_minutes']=10*1440+7*60+50
    game.state['scheduled_events']=[{'title':'Local meeting','due_canon_day':10,'location':'Winston'}]
    route=next(r for r in route_options(game.state,'Reinhardt','cautious')['routes'] if r['available'])
    total=route['minutes'];start=game.state['canon_time_minutes']
    result=local(client,'journey:start',destination='Reinhardt',route_id=route['id'],preparation='cautious')
    assert result['interrupted'] and game.state['canon_time_minutes']==start+10
    assert game.state['adventures']['journey']['remaining_minutes']==total-10
    assert game.state['location']=='Winston'
    result=local(client,'journey:resume')
    assert game.state['location']=='Reinhardt'
    assert game.state['canon_time_minutes']==start+total
    assert not game.state['adventures'].get('journey')


def test_active_objective_survives_actual_save_reload(session):
    _,game,client=session;b,g=mission(game)
    for u in b['units']:
        if u['side']=='enemy':u.update(hp=0,defeated=True)
    game.ensure_combat_numbers();game.autosave()
    game.save();game.load(Path(game.savepath()).stem)
    assert game.state['combat']['active']
    assert game.state['combat']['adventure_objective']['kind']=='retrieval'
