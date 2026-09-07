"""Offline regressions for committed outcomes, recovery and AI retry boundaries."""
import copy
import io
import json
from pathlib import Path
import sys
import urllib.error
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from ai_budget import AIBudgetError, consume_retry, reserve, turn_budget
from ai_client import AI, AIHTTPError, AIResponseError
from game import GameSession
from narrative_state import record_npc_death
from request_receipts import completed, status
from turn_feedback import build_turn_receipt
from turn_recovery import guard
from worlds import BASE_STATE, abilities_for


def state(world='Overgeared'):
    s = copy.deepcopy(BASE_STATE)
    s.update(name='Ari', campaign_id='qa-campaign', world=world, location='Winston' if world == 'Overgeared' else 'Konohagakure',
             turn=5, canon_day=10, canon_time_minutes=14880, opening_complete=True,
             stats={k: 20 for k in abilities_for(world)}, hp=80, hp_max=100, level=2, xp=90, xp_next=100,
             currency={'name': 'Gold', 'amount': 10}, quests=[], quest_archive=[], inventory=[], equipment={}, skills={}, titles=[])
    return s


@pytest.fixture
def session(tmp_path, monkeypatch):
    import app
    game = GameSession(save_dir=tmp_path/'saves', settings_path=tmp_path/'settings.json')
    game.state = state(); game.campaign_active = True
    monkeypatch.setattr(app, 'game', game)
    monkeypatch.setattr(app, '_single_game', game)
    monkeypatch.setattr(app, '_start_due_lore_refresh_once', lambda: None)
    return app, game, app.app.test_client()


def test_receipt_is_net_record_not_reward_calculation():
    before = state(); after = copy.deepcopy(before)
    after.update(turn=6, canon_time_minutes=15000, hp=70, level=3, xp=15, inventory=[{'name':'Potion','quantity':2}])
    after['quests'] = [{'name':'Deliver letter', 'status':'Completed'}]
    after['skills'] = {'Shield Bash': {'rank': 1}}
    snapshot = copy.deepcopy(after)
    result = build_turn_receipt(before, after, 'time_resolve', 'one')
    assert after == snapshot
    assert result['elapsed_minutes'] == 120
    assert any(row['kind'] == 'xp_rollover' for row in result['changes'])
    assert not any(row['kind'] == 'xp' for row in result['changes'])
    assert any(row['label'] == 'Potion' and row['after'] == 2 for row in result['changes'])
    assert build_turn_receipt(before, after, 'time_resolve', 'one') == result


def test_receipt_conceals_hidden_class_and_skills():
    before = state(); after = copy.deepcopy(before)
    after['class_profile'] = {'name':'Secret King', 'true_name':'Secret King', 'signature_skill':'Secret Strike',
                              'discovery':{'concealed':True,'progress':0,'public_name':'Unidentified Class'}}
    after['skills'] = {'Secret Strike': {'rank': 1}}
    rendered = json.dumps(build_turn_receipt(before, after, 'time_resolve'))
    assert 'Secret King' not in rendered and 'Secret Strike' not in rendered


def test_narrative_world_does_not_invent_xp():
    before = state('Naruto'); after = copy.deepcopy(before)
    after.update(xp=200, turn=6)
    assert not any(c['kind'] in {'xp','level','xp_rollover'} for c in build_turn_receipt(before, after, 'time_resolve')['changes'])
    assert build_turn_receipt(before, before, 'time_resolve') is None


def test_fractional_currency_and_completed_quest_archive():
    before = state(); after = copy.deepcopy(before)
    before['currency'].update(amount_minor=101, minor_per_major=10000)
    after['currency'].update(amount_minor=102, minor_per_major=10000)
    before['quests'] = [{'name':'Letter', 'status':'Active'}]
    after['quest_archive'] = [{'name':'Letter','status':'Completed'}]
    receipt = build_turn_receipt(before, after, 'time_resolve')
    assert {'kind':'currency','label':'Gold','before':'0.0101','after':'0.0102'} in receipt['changes']
    assert any(c['kind']=='quest' and c['after']=='Completed' for c in receipt['changes'])


def test_request_replays_once_and_survives_real_save_load(session):
    app, game, client = session; calls=[]
    def award():
        calls.append(1); game.state['hp'] -= 1; game.state['turn'] += 1
        game.append('The training is complete.')
        return {'status':'resolved','state':game.public_state(),'story':game.story_log[-1:]}
    payload={'request_id':'qa-once','orders':['Train']}
    first=app.atomic_game_call('time_resolve',payload,award)
    assert len([r for r in game.story_log if r['tag']=='receipt']) == 1
    again=app.atomic_game_call('time_resolve',payload,award)
    assert len(calls)==1 and again['replayed_request']
    assert again['story']==first['story']
    saved=game.save(); game.load(Path(game.savepath()).stem)
    replay=client.get('/api/action/status?request_id=qa-once&route=time_resolve').get_json()
    assert replay['status']=='completed' and replay['result']['replayed_request']
    assert len(calls)==1
    assert '_request_receipts' not in game.public_state()
    assert '_request_receipts' not in game.trimmed_state_for_ai()


def test_unknown_or_mismatched_request_is_not_blindly_replayed(session):
    app, game, client=session
    payload={'request_id':'one','orders':['Train']}
    app.atomic_game_call('time_resolve', payload, lambda:{'status':'resolved','state':game.public_state(),'story':[]})
    with pytest.raises(ValueError, match='different action'):
        app.atomic_game_call('time_resolve', {**payload,'orders':['Fight']}, lambda:pytest.fail('must not run'))
    game.state['campaign_id']='other'
    with pytest.raises(ValueError, match='another campaign'):
        completed(game,'one')
    assert status(game,'missing','time_resolve')['status']=='unknown'


def test_error_rolls_back_and_does_not_make_receipt(session):
    app, game, client=session
    def fail():
        game.state['hp']=1;game.append('Do not keep this!');raise ValueError('bad result')
    with pytest.raises(ValueError):app.atomic_game_call('time_resolve',{'request_id':'broken'},fail)
    assert game.state['hp']==80 and not game.story_log
    assert status(game,'broken','time_resolve')['status']=='failed'
    game._inflight_request={'id':'other'}
    assert status(game,'broken','time_resolve')['status']=='in_progress'


@pytest.mark.parametrize('result',[
    {'status':'lethal_confirm_required','check':{'lethal_risk':'high'}},
    {'status':'power_goal_confirm_required','warning':'Confirm training'},
    {'status':'manual_roll_required','check':{'major_event':True},'check_id':'roll'},
])
def test_confirmation_is_not_a_completed_turn_summary(session,result):
    app, game, client=session
    returned=app.atomic_game_call('time_resolve',{'request_id':'confirm'},lambda:copy.deepcopy(result))
    assert not game.story_log and returned['_recovery_guard']==guard(game.state)
    assert completed(game,'confirm')['status']==result['status']


def test_combat_routes_preserve_request_ids(session,monkeypatch):
    app, game, client=session;game.state['combat']={'active':True}
    calls=[]
    monkeypatch.setattr(game, 'combat_active', lambda: True)
    def resolve(*args,**kwargs):
        calls.append(1);game.state['hp']-=1
        return {'status':'resolved','state':game.public_state(),'story':[]}
    monkeypatch.setattr(game,'resolve_combat_round',resolve)
    body={'request_id':'combat-once','action':'attack'}
    assert client.post('/api/combat/action',json=body).status_code==200
    assert client.get('/api/action/status?request_id=combat-once&route=combat_action').get_json()['status']=='completed'
    assert client.post('/api/combat/action',json=body).get_json()['replayed_request']
    assert len(calls)==1
    monkeypatch.setattr(game,'narrate_combat',resolve)
    body={'request_id':'narrate-once'}
    assert client.post('/api/combat/narrate',json=body).status_code==200
    assert client.post('/api/combat/narrate',json=body).get_json()['replayed_request']
    assert len(calls)==2


def test_post_assessment_guard_is_the_one_used_for_advance(session, monkeypatch):
    app,game,client=session
    monkeypatch.setattr(game,'ai_ready',lambda:True)
    response=client.post('/api/time/assess',json={'amount':1,'unit':'moment','orders':['Practice my stance'],'intensity':'normal'})
    data=response.get_json();assert response.status_code==200, data
    assert data['_recovery_guard']==guard(game.state)
    body={'request_id':'assessed','expected_guard':data['_recovery_guard'],'orders':data['orders']}
    result=app.atomic_game_call('time_resolve',body,lambda:{'status':'resolved','state':game.public_state(),'story':[]})
    assert result['state']['_recovery_guard']==guard(game.state)


@pytest.mark.parametrize('status_code',[400,401,403,404,422])
def test_permanent_ai_errors_do_not_retry(status_code):
    ai=AI(provider='cloud',key='test');calls=[]
    def fail(*args):calls.append(1);raise AIHTTPError(status_code,'Rejected')
    with patch.object(ai,'_responses_request',fail), pytest.raises(RuntimeError):ai.request('JSON',{})
    assert len(calls)==1


def test_quota_and_ordinary_rate_limit_do_not_hammer_provider():
    for detail in ['insufficient_quota','Too many requests']:
        ai=AI(provider='cloud',key='test');calls=[]
        def fail(*args):calls.append(1);raise AIHTTPError(429,detail)
        with patch.object(ai,'_responses_request',fail), pytest.raises(RuntimeError):ai.request('JSON',{})
        assert len(calls)==1


@pytest.mark.parametrize('first_error',[AIHTTPError(503,'temporary'), AIResponseError('malformed')])
def test_recoverable_ai_errors_retry_only_once(first_error):
    ai=AI(provider='cloud',key='test')
    with patch.object(ai,'_responses_request',side_effect=[first_error,{'narrative':'Done'}]) as send,patch('ai_client.time.sleep'):
        assert ai.request('JSON',{})['narrative']=='Done'
        assert send.call_count==2


def test_budget_is_shared_by_roles_not_reset_by_each_request():
    with turn_budget(.02,1):
        reserve(.011)
        with turn_budget(100,5):
            with pytest.raises(AIBudgetError):reserve(.01)
        consume_retry()
        with pytest.raises(AIBudgetError):consume_retry()
    with turn_budget(.02,1) as budget:
        reserve(.01);assert budget.reserved==.01
    with turn_budget(.02,1),pytest.raises(AIBudgetError):reserve(None)


def test_budget_refusal_sends_no_request():
    ai=AI(provider='cloud',key='test',model='gpt-4o')
    with turn_budget(.000001,2),patch('urllib.request.urlopen') as send,pytest.raises(AIBudgetError):
        ai.request('Return JSON.',{},max_output_tokens=1000)
    assert send.call_count==0


def test_ai_unknown_runtime_error_not_treated_as_bad_json():
    ai=AI(provider='cloud',key='test')
    with patch.object(ai,'_responses_request',side_effect=RuntimeError('application defect')) as send,pytest.raises(RuntimeError):ai.request('JSON',{})
    assert send.call_count==1


def test_npc_alias_and_shared_identity_resolve_without_rewriting_roster():
    s=state();s['contacts']={'Captain Mira':{'aliases':['Mira'],'canon_id':'mira'}}
    s['npc_memories']={'Mira':{'canon_id':'mira'}}
    s['companions']=[{'name':'Captain Mira','canon_id':'mira'}]
    s['organizations']={'Guard':{'members':{'Mira':{'canon_id':'mira','rank':'Captain'}}}}
    assert record_npc_death(s,'Mira','Confirmed battle result')
    assert s['contacts']['Captain Mira']['alive'] is False
    member=s['organizations']['Guard']['members']['Mira']
    assert member['rank']=='Captain' and member['membership_status']=='dead'
    assert member['person_id']==s['contacts']['Captain Mira']['person_id']


def test_ambiguous_alias_never_updates_two_people():
    s=state();s['contacts']={'Mira':{'aliases':['Captain']},'Rina':{'aliases':['Captain']}}
    before=copy.deepcopy(s)
    assert record_npc_death(s,'Captain','A rumor') is False
    assert s==before


def test_conflicting_same_name_identities_are_not_merged():
    s=state();s['contacts']={'Mira':{'person_id':'one'}};s['npc_memories']={'Mira':{'person_id':'two'}}
    before=copy.deepcopy(s)
    assert not record_npc_death(s,'Mira','Unclear') and s==before


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_invalid_cost_setting_has_no_partial_write(session,value):
    _,game,_=session;before=copy.deepcopy(game.settings)
    with pytest.raises(ValueError):game.update_settings({'music_volume':.1,'max_ai_cost_per_turn_usd':value})
    assert game.settings==before
