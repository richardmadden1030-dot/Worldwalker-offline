import copy, pathlib, sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BACKEND=ROOT/'backend'
if str(BACKEND) not in sys.path:sys.path.insert(0,str(BACKEND))
from game import GameSession
from offline_mode import catalog, opening, resolve_action
from worlds import WORLD_DATA, abilities_for

def make_game(tmp_path,world):
    g=GameSession(save_dir=tmp_path/world.replace(' ','_'),settings_path=tmp_path/'settings.json')
    g.settings['offline_mode']=True
    stats={name:30 for name in abilities_for(world)}
    g.new_campaign('Offline Tester',world,'Adventurer','A prepared local with a reason to explore.','', '', 'Wanderer','Balanced',stats)
    g.campaign_active=True
    def fail(*a,**k):raise AssertionError('Offline Mode attempted an AI request')
    g.ai.request=fail;g.ai_bg.request=fail;g.ai_major.request=fail
    return g

@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_every_world_opens_and_has_real_local_choices(tmp_path,world):
    g=make_game(tmp_path,world);result=opening(g);c=catalog(g)
    assert result['generated_locally'] is True
    assert c['offline_mode'] is True and c['actions']
    ids=[a['id'] for a in c['actions']]
    assert any(i.startswith('rest:') for i in ids)
    assert any(i.startswith(('train:','path:')) for i in ids)
    assert any(a['category']=='missions' for a in c['actions']),world

@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_rest_and_training_use_existing_worldwalker_resolution(tmp_path,world):
    g=make_game(tmp_path,world);opening(g);c=catalog(g)
    before=copy.deepcopy(g.state);rest=next(a for a in c['actions'] if a['id'].startswith('rest:'))
    out=resolve_action(g,rest);assert out.get('generated_locally') is True
    assert g.state['canon_time_minutes']>before['canon_time_minutes']
    c=catalog(g);train=next(a for a in c['actions'] if a['id'].startswith('train:'))
    before_resource=g.state['resource'];out=resolve_action(g,train)
    assert out.get('state') and g.state['resource']<=before_resource

@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_offline_catalog_categorizes_364_system_extensions_when_available(tmp_path,world):
    g=make_game(tmp_path,world);opening(g);c=catalog(g)
    for row in c['actions']:
        category=row.get('original_category') if row.get('category')=='recommended' else row.get('category')
        if row['id'].startswith('path:'):assert category=='training'
        if row['id'].startswith(('property:','craft:')):assert category=='property'
        if row['id'].startswith('expedition:'):assert category=='missions'
        if row['id'].startswith(('conflict:','reputation:')):assert category=='world'

def test_social_farming_is_bounded_and_returned_state_is_current(tmp_path):
    g=make_game(tmp_path,'Naruto');opening(g);place=g.state['location'];name='Local Friend'
    g.state.setdefault('npc_memories',{})[name]={'status':'active','last_known_location':place,'public_goal':'Prepare for tomorrow’s patrol.'}
    c=catalog(g);row=next(a for a in c['actions'] if a['id']==f'offline:social:spend:{name}')
    for _ in range(4):out=resolve_action(g,row)
    assert g.state['relationships'][name]['score']<=2
    assert out['state']['relationships'][name]['score']==g.state['relationships'][name]['score']

def test_active_combat_blocks_time_advancing_offline_actions(tmp_path):
    g=make_game(tmp_path,'Naruto');opening(g)
    g.state['combat']={'active':True,'enemy':{'name':'Test','hp':10,'hp_max':10,'power':10}}
    c=catalog(g)
    assert not any(a['id'].startswith(('rest:','train:','mission:','offline:travel:','offline:social:')) for a in c['actions'])
    assert any(a['id']=='offline:navigate:combat' for a in c['actions'])
    with pytest.raises(ValueError):resolve_action(g,{'id':'rest:60'})

def test_frontend_offline_layer_hides_freeform_and_service_worker_caches_it():
    js=(ROOT/'frontend/js/offline-mode.js').read_text();html=(ROOT/'frontend/index.html').read_text();sw=(ROOT/'frontend/sw.js').read_text()
    assert 'composer.hidden=true' in js and 'time.hidden=true' in js
    assert '.action-deck-side' in js
    assert '/js/offline-mode.js' in html and '/js/offline-mode.js' in sw
