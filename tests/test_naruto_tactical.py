"""Local-only Naruto battle regressions. No live saves or paid AI calls."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from game import GameSession
from worlds import BASE_STATE, abilities_for
from naruto_tactics import compile_skill, MOVES, require_narrative_available
from tactical_combat import (ensure_board, submit_naruto_action, combat_profile,
    footprint_cells, ability_footprint, connected, _npc_activation)


def fresh(skills=None):
    game=GameSession.__new__(GameSession)
    game.campaign_active=True;game.busy=False
    game.story_log=[]
    game.state=copy.deepcopy(BASE_STATE)
    game.state.update(world='Naruto',name='Test Shinobi',campaign_id='isolated-fixture',turn=1,
                      stats={k:100 for k in abilities_for('Naruto')},hp=300,hp_max=300,
                      resource=300,resource_max=300,skills=skills or {},companions=[],npc_memories={})
    game.state['combat']={'active':True,'tactical_enabled':True,'enemy':{
        'name':'Test Chunin','power':100,'hp':300,'hp_max':300,'power_reason':'Established test fixture'}}
    game.saved=[]
    game.autosave=lambda *a,**kw:game.saved.append(copy.deepcopy(game.state))
    game.clear_danger_scenario=lambda:None
    game._combat_check=lambda *a,**kw:{'success':True,'margin':20,'breakthrough':False,'total':70,'difficulty':50}
    game.ensure_combat_numbers();board=ensure_board(game.state)
    board['obstacles']=[]
    board['units'][0].update(x=2,y=2)
    board['units'][1].update(x=3,y=2)
    return game


def send(game,action='attack',**fields):
    board=game.state['combat']['tactical']
    return submit_naruto_action(game,{'action':action,'revision':board['revision'],
                                    'request_id':str(board['revision'])+'-'+action,**fields})


class NarutoTacticalTests(unittest.TestCase):
    def test_single_player_controls_every_present_combat_ally(self):
        from tactical_combat import board_view
        g=fresh();g.state['companions']=[{'name':'Konan','role':'Ranged support','combat_support':True,
            'stats':{'Taijutsu':60,'Ninjutsu':110,'Genjutsu':50,'Chakra Control':100,'Willpower':90,'Intellect':90},
            'skills':{'Paper Spear':{'description':'A paper projectile pierces one enemy.','effect_type':'damage'}}}]
        g.state['npc_memories']={'Konan':{'last_known_location':g.state.get('location','Unknown')}}
        g.state['npc_continuity']={};g.state['combat']['tactical']=None
        board=ensure_board(g.state);ally=next(u for u in board['units'] if u.get('player_controlled'))
        self.assertEqual(ally['name'],'Konan');self.assertIn('Paper Spear',ally['skills'])
        send(g,'end')
        self.assertEqual(board['active_id'],ally['id'])
        self.assertFalse(any(row.get('name')=='Konan' and row.get('action')=='attack' for row in g.state['combat']['log']))
        view=board_view(g.state);self.assertIn('Paper Spear',view['skill_profiles'])

    def test_controlled_ally_uses_own_position_stats_and_ability(self):
        g=fresh();g.state['companions']=[{'name':'Konan','combat_support':True,
            'stats':{'Taijutsu':60,'Ninjutsu':110,'Genjutsu':50,'Chakra Control':100,'Willpower':90,'Intellect':90},
            'skills':{'Paper Spear':{'description':'A paper projectile pierces one enemy.','effect_type':'damage'}}}]
        g.state['npc_memories']={'Konan':{'last_known_location':g.state.get('location','Unknown')}}
        g.state['npc_continuity']={};g.state['combat']['tactical']=None
        board=ensure_board(g.state);ally=next(u for u in board['units'] if u.get('player_controlled'));enemy=next(u for u in board['units'] if u['side']=='enemy')
        ally.update(x=2,y=2);enemy.update(x=4,y=2);send(g,'end')
        before=enemy['hp'];send(g,ability='Paper Spear',x=4,y=2)
        self.assertLess(enemy['hp'],before);self.assertEqual(g.state['combat']['log'][-1]['unit_id'],ally['id'])

    def test_each_controlled_ally_receives_its_own_speed_bonus_choice(self):
        g=fresh();g.state['companions']=[{'name':'Fast Ally','combat_support':True,
            'stats':{'Taijutsu':80,'Ninjutsu':80,'Genjutsu':30,'Chakra Control':80,'Willpower':80,'Intellect':50},
            'skills':{'Quick Strike':{'description':'A close strike attacks one enemy.'}}}]
        g.state['npc_memories']={'Fast Ally':{'last_known_location':g.state.get('location','Unknown')}}
        g.state['npc_continuity']={};g.state['combat']['tactical']=None
        board=ensure_board(g.state);ally=next(u for u in board['units'] if u.get('player_controlled'));enemy=next(u for u in board['units'] if u['side']=='enemy')
        # Avoid spending the main character's own speed bonus in this fixture.
        board['units'][0]['speed']=board['units'][0]['base_speed']=enemy['speed'];ally['speed']=ally['base_speed']=enemy['speed']+30
        send(g,'end');self.assertEqual(board['active_id'],ally['id'])
        send(g,'end');self.assertEqual(board['active_id'],ally['id']);self.assertTrue(board['bonus_activation'])

    def test_original_visuals_reference_real_exported_assets(self):
        runtime=(Path(__file__).resolve().parents[1]/'frontend/tactical/unity-battle-fx.js').read_text(encoding='utf-8')
        for element in ('Fire','Water','Wind','Lightning','Earth'):
            detail=compile_skill(element+' Sweeping Kick',{'description':'Sweeps three squares'})
            self.assertIn("'"+detail['visual_effect']['asset']+"'",runtime)
            self.assertEqual(detail['visual_effect']['delivery'],'area')

    def test_lan_browser_request_ids_do_not_require_random_uuid(self):
        runtime=(Path(__file__).resolve().parents[1]/'frontend/tactical/campaign.js').read_text(encoding='utf-8')
        self.assertIn('function requestId()',runtime)
        self.assertIn('request_id:requestId()',runtime)
        self.assertNotIn('request_id:crypto.randomUUID()',runtime)
        self.assertIn("fetchJSON('/api/auth/session')",runtime)
        self.assertIn("worldwalker_friend_auth_token",runtime)

    def test_clone_retains_portrait_when_host_reverts(self):
        g=fresh({'Shadow Clone Technique':{'description':'A real clone'}})
        send(g,ability='Shadow Clone Technique',x=2,y=4)
        clone=next(u for u in g.state['combat']['tactical']['units'] if u.get('clone'))
        self.assertTrue(clone['portrait_url']);portrait=clone['portrait_url']
        send(g,'revert')
        self.assertEqual(clone['portrait_url'],portrait)

    def test_special_profile_form_can_cast_without_rewriting_skills(self):
        from naruto_tactics import skill_options
        g=fresh();g.state['special']['Dōjutsu']={'name':'Sharingan','combat_boosts':{'speed_pct':.2}}
        self.assertIn('Sharingan',skill_options(g))
        send(g,'transform',ability='Sharingan')
        self.assertFalse(g.state['combat']['tactical']['units'][0]['action_used'])
        self.assertNotIn('Sharingan',g.state['skills'])

    def test_missing_boosts_and_locked_future_forms_remain_unavailable(self):
        from naruto_tactics import skill_options
        g=fresh();g.state['special']['Dōjutsu']={'name':'Sharingan'}
        g.state['special']['Jinchūriki Profile']={'forms':[{'name':'Future Mode','unlocked':False,'combat_boosts':{'power_pct':2}}]}
        options=skill_options(g)
        self.assertIn('tactical_disabled',options['Sharingan']);self.assertNotIn('Future Mode',options)

    def test_room_json_reconnect_retry_and_next_owner(self):
        from naruto_tactical_room import initialize,submit,snapshot
        g=fresh();people=[{'user_id':'host','character':g.state},{'user_id':'guest','character':copy.deepcopy(g.state)}]
        board=initialize(g,people,'host',100)
        command={'action':'defend','request_id':'retry-on-reconnect','revision':board['revision']}
        submit(g,'host',command,now=101)
        g.state=json.loads(json.dumps(g.state))
        before=copy.deepcopy(g.state);submit(g,'host',command,now=102)
        self.assertEqual(g.state,before)
        submit(g,'host',{'action':'end','revision':g.state['combat']['tactical']['revision'],'request_id':'next'},now=103)
        self.assertTrue(snapshot(g,'guest')['is_turn']);self.assertFalse(snapshot(g,'host')['is_turn'])

    def test_room_guest_can_finish_encounter_and_preserve_host_resource(self):
        from naruto_tactical_room import initialize,submit
        g=fresh();people=[{'user_id':'host','character':g.state},{'user_id':'guest','character':copy.deepcopy(g.state)}]
        board=initialize(g,people,'host',100);board['active_id']='pc:guest'
        actor=next(u for u in board['units'] if u['id']=='pc:guest');actor.update(x=3,y=3)
        board['units'][1].update(x=4,y=3,hp=1)
        submit(g,'guest',{'action':'attack','x':4,'y':3,'request_id':'finish','revision':board['revision']},now=101)
        self.assertFalse(g.state['combat']['active']);self.assertEqual(g.state['resource'],300)

    def test_event_animation_origin_is_caster_not_host(self):
        from naruto_tactical_actions import cast
        g=fresh();board=g.state['combat']['tactical'];enemy=board['units'][1]
        cast(g,board,{'ability':'Rasengan','x':2,'y':2},enemy,compile_skill('Rasengan',{}))
        self.assertEqual(g.state['combat']['log'][-1]['origin'],{'x':3,'y':2})

    def test_normal_state_always_routes_supported_combat_to_tactical(self):
        import app as api
        from unittest.mock import Mock
        g=fresh();g.public_state=Mock(side_effect=lambda:copy.deepcopy(g.state))
        with patch.object(api,'game',g),api.app.test_request_context('/api/state'):
            self.assertIn('_tactical_battle_url',api.request_public_state())
            g.state['combat']['active']=False
            self.assertNotIn('_tactical_battle_url',api.request_public_state())
            g.state.update(world='Bleach');g.state['combat']['active']=True
            self.assertIn('_tactical_battle_url',api.request_public_state())
            g.state['world']='Naruto'
            with patch.dict('os.environ',{'WORLDWALKER_NARUTO_TACTICAL':'0'}):
                self.assertIn('_tactical_battle_url',api.request_public_state())

    def test_room_completion_publishes_once(self):
        from naruto_tactical_room import initialize,persist_members
        from unittest.mock import Mock
        g=fresh();people=[{'user_id':'host','character':g.state},{'user_id':'guest','character':copy.deepcopy(g.state)}]
        initialize(g,people,'host');store=Mock()
        g.state['combat'].update(active=False,outcome='victory')
        persist_members(g,store,'room',people);persist_members(g,store,'room',people)
        self.assertEqual(store.complete.call_count,1)

    def test_learned_catalog_skills_survive_legacy_selector_filter(self):
        from tactical_combat import board_view
        g=fresh({'Rasengan':{'description':'Rotating chakra'},'Sage Mode':{'effect_type':'transform'}})
        self.assertIn('Rasengan',board_view(g.state)['skill_profiles'])

    def test_room_clone_is_not_another_human_turn(self):
        from naruto_tactical_room import initialize
        g=fresh({'Shadow Clone Technique':{'description':'A real clone'}})
        initialize(g,[{'user_id':'host','character':g.state},{'user_id':'guest','character':copy.deepcopy(g.state)}],'host',now=0)
        self.assertEqual(g.state['combat']['tactical']['deadline'],600)
        send(g,ability='Shadow Clone Technique',x=2,y=4)
        clone=next(u for u in g.state['combat']['tactical']['units'] if u.get('clone'))
        self.assertFalse(clone['human']);self.assertIsNone(clone['owner_id'])

    def test_catalog_and_contact_range(self):
        self.assertEqual(len(MOVES),69)
        g=fresh();b=g.state['combat']['tactical'];p=b['units'][0]
        d=compile_skill('Rasengan',{'description':'Rotating chakra'})
        spec=ability_footprint('Rasengan',d)
        self.assertEqual(footprint_cells(b,p,spec,(4,2)),[])
        self.assertEqual(footprint_cells(b,p,spec,(3,2)),[(3,2)])

    def test_bandit_does_not_scale_to_player(self):
        g=fresh();raw={'name':'Random bandit','power':1500,'speed':1500,'defense':1500,'hp':3000,'hp_max':3000}
        a=combat_profile(g.state,raw)
        g.state['stats']={k:2000 for k in g.state['stats']}
        b=combat_profile(g.state,raw)
        self.assertEqual(a['power'],b['power']);self.assertLess(a['power'],100)
        self.assertLess(a['speed'],100);self.assertLess(a['defense'],100)

    def test_described_sweep_and_unknown_complex_skill(self):
        self.assertEqual(compile_skill('Sweeping Fire Kick',{'description':'Sweeps three squares'})['tactical']['width'],3)
        self.assertIn('tactical_disabled',compile_skill('Reality Fold',{'description':'Creates an alternate dimension'}))

    def test_rollback_invalid_range(self):
        g=fresh({'Rasengan':{'description':'Rotating chakra'}})
        before=copy.deepcopy(g.state)
        with self.assertRaises(ValueError):send(g,ability='Rasengan',x=7,y=7)
        self.assertEqual(before,g.state)

    def test_duplicate_after_json_reload(self):
        g=fresh({'Rasengan':{'description':'Rotating chakra'}})
        payload={'action':'attack','ability':'Rasengan','x':3,'y':2,'revision':0,'request_id':'cast-one'}
        submit_naruto_action(g,payload); resource=g.state['resource']
        g.state=json.loads(json.dumps(g.state))
        result=submit_naruto_action(g,payload)
        self.assertTrue(result['replayed_request']);self.assertEqual(g.state['resource'],resource)
        with self.assertRaises(ValueError):submit_naruto_action(g,{**payload,'x':4})

    def test_stale_request_rejected(self):
        g=fresh();send(g,'move',x=2,y=3)
        with self.assertRaises(ValueError):submit_naruto_action(g,{'action':'attack','revision':0,'request_id':'stale'})

    def test_clone_splits_remaining_chakra(self):
        g=fresh({'Shadow Clone Technique':{'description':'Creates a real shadow clone'}})
        send(g,ability='Shadow Clone Technique',x=2,y=4)
        b=g.state['combat']['tactical'];clone=next(u for u in b['units'] if u.get('clone'))
        self.assertEqual(clone['resource']+g.state['resource'],280)
        self.assertEqual(clone['hp'],1);self.assertTrue(b['units'][0]['action_used'])
        self.assertEqual((clone['x'],clone['y']),(2,4))
        event=g.state['combat']['log'][-1]
        self.assertEqual(event['affected_tiles'],[[2,4]])
        self.assertEqual(event['visual']['asset'],'clone-barrage')
        self.assertEqual(event['visual']['delivery'],'target')

    def test_clone_invalid_targets_do_not_spend_or_spawn(self):
        for x,y in [(2,2),(3,2),(7,7),(-1,2),(2,3)]:
            with self.subTest(target=(x,y)):
                g=fresh({'Shadow Clone Technique':{'description':'Creates a real shadow clone'}})
                g.state['combat']['tactical']['obstacles']=[{'x':2,'y':3,'kind':'tree'}]
                before=copy.deepcopy(g.state)
                with self.assertRaises(ValueError):send(g,ability='Shadow Clone Technique',x=x,y=y)
                self.assertEqual(g.state,before)

    def test_teleport_requires_saved_mark(self):
        g=fresh({'Flying Thunder God':{'description':'Teleports to an established seal'}})
        with self.assertRaises(ValueError):send(g,ability='Flying Thunder God',x=6,y=6)
        g.state['combat']['tactical']['teleport_marks']=[{'owner_id':'player','x':6,'y':6}]
        send(g,ability='Flying Thunder God',x=6,y=6)
        self.assertEqual(g.state['combat']['tactical']['units'][0]['x'],6)

    def test_form_free_and_no_stack_revert(self):
        g=fresh({'Test Sage Mode':{'description':'Established sage transformation','effect_type':'transform',
                                  'combat_boosts':{'speed_pct':1,'power_pct':2},'resource_cost':10}})
        send(g,ability='Test Sage Mode');b=g.state['combat']['tactical']
        self.assertFalse(b['units'][0]['action_used']);self.assertEqual(b['units'][0]['speed'],200)
        self.assertEqual(g.state['portrait_identity']['active_form']['name'],'Test Sage Mode')
        with self.assertRaises(ValueError):send(g,ability='Test Sage Mode')
        send(g,'revert');self.assertEqual(g.state['combat']['tactical']['units'][0]['speed'],100)
        self.assertFalse(g.state['portrait_identity']['active_form'])

    def test_missing_boost_not_generic_transform(self):
        g=fresh({'Sage Mode':{'effect_type':'transform','description':'A transformation'}})
        with self.assertRaises(ValueError):send(g,ability='Sage Mode')

    def test_narrative_and_legacy_bypass_blocked(self):
        g=fresh()
        with self.assertRaises(ValueError):require_narrative_available(g.state)
        with self.assertRaises(ValueError):g.resolve_combat_round('attack')
        g.state['combat']['active']=False
        require_narrative_available(g.state)

    def test_paralysis_blocks_movement_and_cast(self):
        g=fresh();g.state['combat']['player_statuses']=[{'name':'Paralyzed','blocks_action':True,'rounds_left':1}]
        for action,fields in [('move',{'x':2,'y':3}),('attack',{'x':3,'y':2})]:
            with self.assertRaises(ValueError):send(g,action,**fields)

    def test_kai_only_cleans_genjutsu(self):
        g=fresh({'Kai':{'description':'Genjutsu release'}})
        g.state['combat']['player_statuses']=[{'name':'Illusion','kind':'genjutsu','rounds_left':2},
                                             {'name':'Poison','kind':'poison','rounds_left':2}]
        send(g,ability='Kai')
        self.assertEqual([s['kind'] for s in g.state['combat']['player_statuses']],['poison'])

    def test_kirin_requires_conditions(self):
        g=fresh({'Kirin':{'description':'Natural lightning'}})
        g.state['tactical_capabilities']=['lightning-nature']
        with self.assertRaisesRegex(ValueError,'stormclouds'):send(g,ability='Kirin',x=3,y=2)

    def test_outcome_persisted_and_deduplicated(self):
        g=fresh();g.state['combat']['tactical']['units'][1]['hp']=1
        send(g,x=3,y=2)
        self.assertFalse(g.state['combat']['active'])
        self.assertEqual(g.saved[-1]['tactical_battle_results'][0]['casualties'][0]['outcome'],'killed')
        self.assertEqual(len(g.state['tactical_battle_results']),1)

    def test_sparing_is_not_killing(self):
        g=fresh();g.state['combat']['spare_enemy']=True;g.state['combat']['tactical']['units'][1]['hp']=2
        send(g,x=3,y=2)
        self.assertEqual(g.state['tactical_battle_results'][0]['casualties'][0]['outcome'],'subdued')

    def test_disabled_default_other_world(self):
        g=fresh();g.state['world']='Bleach'
        with self.assertRaises(ValueError):send(g)

    def test_every_curated_move_resolves_with_established_requirements(self):
        for move in MOVES:
            with self.subTest(move=move['name']):
                g=fresh({move['name']:{'description':move['description']}})
                b=g.state['combat']['tactical'];p,e=b['units'][:2];c=move['combat'];req=c.get('requires',{})
                g.state['tactical_capabilities']=req.get('capabilities',[])
                b['conditions']=req.get('environment',[])
                if req.get('targetStatusSource'):
                    e['statuses']=[{'name':'Restrained','kind':'restrained','source_id':'player',
                                    'technique_id':req['targetStatusSource'],'rounds_left':2}]
                for i in range(req.get('alliedClones',0)):
                    clone=copy.deepcopy(p);clone.update(id=f'clone{i}',player=False,clone=True,summoner_id='player',x=0,y=i)
                    b['units'].append(clone)
                if c.get('heal'):
                    p['hp']=g.state['hp']=100;aim=(2,2)
                elif c.get('target')=='self' or c.get('shape')=='self':aim=(2,2)
                else:aim=(3,2)
                result=send(g,ability=move['name'],x=aim[0],y=aim[1],facing='east')
                self.assertEqual(g.state['resource'],300-c['cost'])
                self.assertTrue(result['combat']['tactical']['units'][0]['action_used'])

    def test_bonus_is_a_fresh_choice(self):
        g=fresh();g.state['stats']={k:200 for k in g.state['stats']}
        send(g,'defend');send(g,'end')
        b=g.state['combat']['tactical']
        self.assertTrue(b['bonus_activation']);self.assertFalse(b['units'][0]['action_used'])

    def test_connected_boards_across_seeds(self):
        from tactical_combat import make_board
        g=fresh()
        for turn in range(40):
            g.state['turn']=turn
            self.assertTrue(connected(make_board(g.state,copy.deepcopy(g.state['combat']['tactical']['units']))))

    def test_enemy_canonical_cast_uses_own_resource(self):
        g=fresh();b=g.state['combat']['tactical'];e=b['units'][1]
        e['abilities']=[{'name':'Rasengan',**compile_skill('Rasengan',{'description':'Rotating chakra'})}]
        e['resource']=100
        _npc_activation(g,b,e)
        self.assertEqual(e['resource'],82)
        self.assertEqual(g.state['resource'],300)

    def test_enemy_paralysis_survives_into_player_turn(self):
        g=fresh();b=g.state['combat']['tactical'];e=b['units'][1]
        e['abilities']=[{'name':'Recorded restraint','effect_type':'control','status_effect':'Paralyzed',
                         'duration_rounds':1,'resource_cost':0,
                         'tactical':{'shape':'single','range':5,'effect':'control'}}]
        send(g,'end')
        self.assertTrue(g.state['combat']['player_statuses'])
        with self.assertRaises(ValueError):send(g,'move',x=2,y=3)

    def test_no_real_saves_created(self):
        g=fresh();send(g,'defend')
        self.assertTrue(g.saved)

    def test_all_curated_footprints_are_bounded_in_every_direction(self):
        b={'width':8,'height':8}
        for move in MOVES:
            for facing in ('north','east','south','west'):
                for origin in ({'x':3,'y':3},{'x':0,'y':0}):
                    with self.subTest(name=move['name'],facing=facing,origin=origin):
                        spec=ability_footprint(move['name'],compile_skill(move['name'],{}),8)
                        actual=footprint_cells(b,origin,spec,(4,3),facing)
                        self.assertTrue(all(0<=x<8 and 0<=y<8 for x,y in actual))

    def test_state_migration_preserves_positions_and_spent_action(self):
        from state_guard import migrate_state
        g=fresh();send(g,'move',x=2,y=3);send(g,'defend')
        before=copy.deepcopy(g.state['combat']['tactical'])
        migrate_state(g.state)
        after=ensure_board(g.state)
        self.assertEqual(before['units'][0]['x'],after['units'][0]['x'])
        self.assertEqual(before['units'][0]['y'],after['units'][0]['y'])
        self.assertEqual(before['units'][0]['movement_left'],after['units'][0]['movement_left'])
        self.assertTrue(after['units'][0]['action_used'])

    def test_local_endpoint_cannot_be_disabled_after_shipping(self):
        import app as api
        with patch.dict('os.environ',{'WORLDWALKER_NARUTO_TACTICAL':'0'}),api.app.test_request_context('/api/combat/tactical'):
            response,status=api.api_naruto_tactical()
            self.assertEqual(status,400)
            self.assertNotIn('disabled', response.get_json()['error'].lower())

    def test_local_endpoint_rejects_multiplayer_instead_of_mutating_host(self):
        import app as api
        from flask import g as context
        with patch.dict('os.environ',{'WORLDWALKER_NARUTO_TACTICAL':'1'}),api.app.test_request_context('/api/combat/tactical'):
            context.worldwalker_room={'id':'test-room'}
            _,status=api.api_naruto_tactical()
            self.assertEqual(status,409)

    def test_local_endpoint_read_is_detached(self):
        import app as api
        game=fresh()
        with patch.object(api,'game',game),patch.dict('os.environ',{'WORLDWALKER_NARUTO_TACTICAL':'1'}),api.app.test_request_context('/api/combat/tactical'):
            response=api.api_naruto_tactical()
            data=response.get_json();self.assertTrue(data['enabled'])
            self.assertIn('skill_profiles',data['board']);self.assertFalse(game.busy)

    def test_room_ownership_and_ten_minute_pass(self):
        from naruto_tactical_room import initialize,submit,tick
        g=fresh();guest=copy.deepcopy(g.state);guest.update(name='Second Shinobi')
        people=[{'user_id':'host','character':g.state,'connected':True},{'user_id':'guest','character':guest,'connected':True}]
        b=initialize(g,people,'host',100)
        with self.assertRaises(ValueError):submit(g,'guest',{'action':'defend','revision':b['revision'],'request_id':'wrong'},now=101)
        self.assertFalse(tick(g,people,699));self.assertTrue(tick(g,people,700))
        self.assertEqual(b['active_id'],'pc:guest')
        people[1]['connected']=False;self.assertTrue(tick(g,people,701))
        self.assertEqual(b['active_id'],'player')

    def test_guest_cannot_spend_hosts_chakra(self):
        from naruto_tactical_room import initialize,submit
        g=fresh();guest=copy.deepcopy(g.state);guest.update(name='Second Shinobi',skills={'Rasengan':{'description':'Rotating chakra'}})
        people=[{'user_id':'host','character':g.state},{'user_id':'guest','character':guest}]
        b=initialize(g,people,'host',100);b['active_id']='pc:guest'
        u=next(u for u in b['units'] if u.get('owner_id')=='guest');u.update(x=3,y=3)
        b['units'][1].update(x=4,y=3)
        submit(g,'guest',{'action':'attack','ability':'Rasengan','x':4,'y':3,'revision':b['revision'],'request_id':'guest-hit'},now=101)
        self.assertEqual(g.state['resource'],300);self.assertEqual(u['resource'],282)


if __name__=='__main__':unittest.main()
