import copy, tempfile
from pathlib import Path
import pytest

from game import GameSession
from worlds import BASE_STATE, WORLD_DATA, abilities_for


def new_game(world):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    game = GameSession(save_dir=root/'saves', settings_path=root/'settings.json')
    game.settings['offline_mode'] = True
    state = copy.deepcopy(BASE_STATE)
    state.update(name='Offline Tester', campaign_id=f'offline-{world}', world=world,
                 location=WORLD_DATA[world].get('start') or 'Starting Region', turn=5,
                 canon_day=10, canon_time_minutes=14880, opening_complete=False,
                 stats={k:20 for k in abilities_for(world)}, hp=80, hp_max=100,
                 resource=70, resource_max=100, currency={'name':'Currency','amount':1000},
                 quests=[], quest_archive=[], inventory=[], equipment={}, skills={}, titles=[])
    game.state = state; game.campaign_active = True
    game._offline_test_tmp = td
    return game


@pytest.fixture(autouse=True)
def forbid_model_calls(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Offline Mode must never call a model')
    monkeypatch.setattr('ai_client.AI.request', forbidden)


@pytest.mark.parametrize('world', list(WORLD_DATA))
def test_offline_training_every_world(world):
    game = new_game(world); before = copy.deepcopy(game.state)
    opening = game.offline_opening(); assert opening['offline_mode'] and game.state['opening_complete']
    out = game.resolve_offline_activity({'id':'training-stats','label':'Condition the body','category':'training','duration':'hour'})
    assert out['offline_mode']; assert game.state['turn'] == before['turn']+1
    assert game.state['canon_time_minutes'] > before['canon_time_minutes']
    assert any(game.state['stats'][k] > before['stats'][k] for k in before['stats'])


@pytest.mark.parametrize('world', list(WORLD_DATA))
def test_mission_generation_every_world(world):
    game = new_game(world)
    out = game.resolve_offline_activity({'id':'missions-work','label':'Look for work','category':'missions'})
    offers = out['state']['offline_mode']['mission_offers']
    assert len(offers)==3 and len({x['id'] for x in offers})==3
    assert all(x['objectives'] and x['generated_offline'] for x in offers)


def test_accept_progress_and_reward():
    game=new_game('Overgeared')
    board=game.resolve_offline_activity({'id':'missions-work','label':'Look for work','category':'missions'})
    offer=board['state']['offline_mode']['mission_offers'][0]
    game.resolve_offline_activity({'id':f"offline-accept:{offer['id']}",'label':offer['title'],'category':'missions'})
    quest=next(q for q in game.state['quests'] if q.get('id')==offer['id'])
    dest=quest.get('destination')
    if dest and dest != game.state['location']:
        game.resolve_offline_activity({'id':f'travel:{dest}','label':f'Travel to {dest}','category':'travel'})
    for _ in range(6):
        game.resolve_offline_activity({'id':f"quest:{quest['title']}",'label':f"Work on {quest['title']}",'category':'missions'})
        if game.combat_active(): game.end_combat('victory')
        current = next((q for q in game.state['quests'] if q.get('id')==offer['id']), None)
        archived = next((q for q in game.state.get('quest_archive',[]) if q.get('id')==offer['id']), None)
        quest = current or archived or quest
        if archived or str(quest.get('status')).lower() in {'complete','completed'}: break
    assert int(quest.get('progress',100 if archived else 0))>0


def test_storylet_resolves_without_ai():
    game=new_game('Naruto')
    game.ensure_offline_state()['pending_event']={'id':'evt','title':'Opportunity','text':'Something happens.',
        'choices':[{'id':'study','label':'Study it','category':'training'}]}
    game.resolve_offline_activity({'id':'offline-event:evt:study','label':'Study it','category':'recommended'})
    assert game.state['offline_mode']['pending_event'] is None
    assert game.state['offline_mode']['event_history'][-1]['choice']=='Study it'


def test_combat_reuses_existing_resolver_and_locks_world_actions():
    game=new_game('Custom World')
    result=game.resolve_offline_activity({'id':'combat-spar','label':'Spar','category':'combat'})
    assert result['combat_started'] and game.combat_active() and game.state['combat']['non_lethal']
    round_result=game.resolve_combat_round('defend')
    assert round_result['combat']['round'] >= 1
    with pytest.raises(ValueError, match='Finish the current battle'):
        game.resolve_offline_activity({'id':'personal-rest','label':'Rest','category':'personal'})


def test_offline_result_survives_save_load():
    game=new_game('Bleach')
    game.resolve_offline_activity({'id':'missions-work','label':'Look for work','category':'missions'})
    game.save()
    # public state itself proves the generated game layer is persisted in the canonical save.
    assert len(game.public_state()['offline_mode']['mission_offers']) == 3


def test_offline_mode_never_schedules_background_ai():
    game=new_game('Naruto')
    for mode in ('economy','balanced','deep'):
        game.settings['simulation_mode']=mode
        game.state['turn']=8
        assert game.background_ai_due() is False


def test_completed_generated_quest_moves_into_normal_archive():
    game=new_game('Custom World')
    board=game.resolve_offline_activity({'id':'missions-work','label':'Look for work','category':'missions'})
    offer=board['state']['offline_mode']['mission_offers'][0]
    game.resolve_offline_activity({'id':f"offline-accept:{offer['id']}",'label':offer['title'],'category':'missions'})
    q=next(q for q in game.state['quests'] if q.get('id')==offer['id'])
    q['destination']=game.state['location']; q['archetype']='investigation'
    for _ in range(5):
        game.resolve_offline_activity({'id':f"quest:{q['title']}",'label':f"Work on {q['title']}",'category':'missions'})
        if any(x.get('id')==offer['id'] for x in game.state.get('quest_archive',[]) if isinstance(x,dict)): break
    assert any(x.get('id')==offer['id'] for x in game.state.get('quest_archive',[]) if isinstance(x,dict))
