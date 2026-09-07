import copy
import json
import unittest

from relationship_life import available, candidates, prepare, resolve, route


def state():
    return {'name': 'Ren', 'world': 'Naruto', 'turn': 8, 'location': 'Konoha',
            'npc_memories': {'Konan': {'role': 'Medic', 'attitude': 'Friendly',
                'chain': [{'event': 'You helped Konan staff the clinic.', 'turn': 3}]}},
            'contacts': {'Konan': {'can_contact': True}}, 'stats': {'Taijutsu': 100},
            'relationships': {'Konan': 30}}


def response(s, **patch):
    return {'relationship_followups': [{'id': candidates(s)[0]['id'], 'actor': 'Konan',
        'disposition': 'send', 'message': 'Thank you for helping at the clinic. Would you like to join us for tea?',
        'reason': 'Shared clinic work; she has time to send a letter.',
        'delivery': {'channel': 'message', 'basis': 'Established courier route; a week has passed.'}, **patch}]}


class RelationshipLifeTests(unittest.TestCase):
    def test_old_save_candidates_read_only(self):
        s=state(); before=copy.deepcopy(s)
        self.assertEqual(candidates(s)[0]['actor'], 'Konan')
        self.assertEqual(s,before)

    def test_goal_alone_does_not_create_message(self):
        s=state(); s['npc_memories']['Konan']={'goal':'Conquer the world','recurring':True}
        self.assertEqual(candidates(s), [])
        from living_world import advance
        self.assertEqual(advance(s,[],1440)['incoming_chats'], [])

    def test_send_changes_only_followup_bookkeeping(self):
        s=state(); before=copy.deepcopy(s)
        messages=resolve(before,s,response(before))
        self.assertEqual(len(messages),1)
        self.assertIn('tea',messages[0]['message'])
        s.pop('relationship_life'); self.assertEqual(s,before)

    def test_retries_and_reload_do_not_repeat(self):
        s=state(); before=copy.deepcopy(s); data=response(before)
        resolve(before,s,data)
        self.assertEqual(resolve(before,s,data),[])
        s=json.loads(json.dumps(s)); s['turn']=100
        self.assertEqual(candidates(s),[])

    def test_cooldown_then_new_experience(self):
        s=state(); resolve(copy.deepcopy(s),s,response(s))
        s['npc_memories']['Konan']['chain'].append({'event':'You kept your promise to Konan.', 'turn':8})
        s['turn']=10;self.assertEqual(candidates(s),[])
        s['turn']=11;self.assertEqual(len(candidates(s)),1)

    def test_all_death_representations_and_incapacitation_block(self):
        for fields in ({'alive':False},{'deceased':True},{'status':'Dead'}, {'status':'missing'}, {'status':'imprisoned'}):
            for where in ('npc_memories','contacts'):
                with self.subTest(fields=fields,where=where):
                    s=state();s[where]['Konan'].update(fields)
                    self.assertFalse(available(s,'Konan'));self.assertEqual(candidates(s),[])

    def test_roster_death_vetoes_stale_memory(self):
        s=state();s['organizations']={'Akatsuki':{'members':{'Konan':{'status':'dead'}}}}
        self.assertFalse(available(s,'Konan'))

    def test_actor_dying_this_turn_cannot_send(self):
        before=state();s=copy.deepcopy(before);s['npc_memories']['Konan']['alive']=False
        self.assertEqual(resolve(before,s,response(before)),[])

    def test_unreachable_and_wrong_delivery_block(self):
        s=state();before=copy.deepcopy(s);s['contacts']['Konan']['can_contact']=False
        self.assertEqual(candidates(s),[])
        self.assertEqual(resolve(before,s,response(before)),[])
        s=state();self.assertEqual(resolve(copy.deepcopy(s),s,response(s,delivery={'channel':'in_person','basis':'She walks over.'})),[])

    def test_in_person_requires_current_scene(self):
        s=state();s['contacts']['Konan']['can_contact']=False
        s['scene_state']={'location':'Konoha','present':[{'name':'Konan'}]}
        self.assertEqual(route(s,'Konan'),'in_person')
        s['scene_state']['location']='Elsewhere';self.assertEqual(route(s,'Konan'),'')

    def test_unrecognized_id_actor_and_empty_delivery_rejected(self):
        for patch in ({'id':'fabricated'},{'actor':'Orochimaru'},{'message':''},{'delivery':{}},{'reason':''}):
            s=state();self.assertEqual(resolve(copy.deepcopy(s),s,response(s,**patch)),[])
            self.assertNotIn('relationship_life',s)

    def test_defer_preserves_opportunity_close_retires_it(self):
        s=state();before=copy.deepcopy(s)
        self.assertEqual(resolve(before,s,response(before,disposition='defer')),[])
        self.assertEqual(s,before)
        resolve(before,s,response(before,disposition='close'));s['turn']=30
        self.assertEqual(candidates(s),[])

    def test_no_second_message_same_sender(self):
        s=state();data=response(s);data['incoming_chats']=[{'sender':'Konan','message':'Already writing.'}]
        self.assertEqual(resolve(copy.deepcopy(s),s,data),[])
        self.assertNotIn('relationship_life',s)

    def test_combat_and_dead_player_have_no_social_prompt(self):
        for patch in ({'combat':{'active':True}},{'alive':False}):
            s=state();s.update(patch);self.assertEqual(candidates(s),[])

    def test_current_turn_memory_waits(self):
        s=state();s['npc_memories']['Konan']['chain'][0]['turn']=8
        self.assertEqual(candidates(s),[])

    def test_nemesis_not_automatically_hostile_or_scaled(self):
        s=state();s['npc_memories']['Konan']['nemesis']=True
        s['npc_memories']['Konan']['stats']={'Ninjutsu':40}
        before=copy.deepcopy(s);option=candidates(s)[0]
        self.assertTrue(option['nemesis']);self.assertEqual(s,before)
        packet={};prepare(s,packet)
        self.assertIn('Never match their stats',packet['relationship_guidance'])

    def test_chat_has_guidance_without_second_conversation_schema(self):
        packet={'thread':'Konan','task':'npc_chat','schema':{}}
        prepare(state(),packet)
        self.assertIn('relationship_guidance',packet)
        self.assertNotIn('relationship_followups',packet['schema'])

    def test_candidates_bounded_and_fair(self):
        s=state()
        for i in range(30):
            name=f'Person {i}';s['npc_memories'][name]=copy.deepcopy(s['npc_memories']['Konan']);s['contacts'][name]={'can_contact':True}
        self.assertEqual(len(candidates(s)),4)

    def test_malformed_optional_records_safe(self):
        s=state();s.update(relationship_life='old text',message_delivery_state='old text',organizations=['bad'])
        s['npc_memories']['Bad']='text';s['npc_memories']['Empty']={'chain':[None,{},[]]}
        self.assertEqual(len(candidates(s)),1)

    def test_no_stat_or_world_specific_assumptions(self):
        from worlds import WORLD_DATA
        for world in WORLD_DATA:
            s=state();s['world']=world;before=copy.deepcopy(s)
            self.assertEqual(len(resolve(before,s,response(s))),1)
            self.assertEqual(s['stats'],before['stats'])

    def test_real_time_skip_delivers_into_existing_chat(self):
        from game import GameSession
        from worlds import BASE_STATE
        game=GameSession();game.state=copy.deepcopy(BASE_STATE);game.state.update(state())
        game.autosave=lambda *a,**k:None
        data=response(game.state);data.update(narrative='A quiet week passes.',state_patch={})
        game.apply_time_skip(data,7,'days')
        messages=game.state['chat_threads']['Konan']
        self.assertTrue(any('tea' in r['text'] for r in messages))
        self.assertTrue(any(r['metadata'].get('relationship_followup') for r in messages))

    def test_chain_reason_dedup(self):
        from continuity import update_continuity
        s=state();before=copy.deepcopy(s)
        s['npc_memories']['Konan']['chain_event']='You helped Konan staff the clinic!'
        update_continuity(before,s)
        self.assertEqual(len(s['npc_memories']['Konan']['chain']),1)

    def test_real_normal_turn_delivers_followup(self):
        from game import GameSession
        from worlds import BASE_STATE
        game=GameSession();game.state=copy.deepcopy(BASE_STATE);game.state.update(state())
        game.autosave=lambda *a,**k:None
        data=response(game.state);data.update(narrative='You finish a quiet patrol.',state_patch={})
        game.apply_resolution(data,pending_action='Finish the patrol')
        self.assertTrue(any('tea' in r['text'] for r in game.state['chat_threads']['Konan']))

    def test_chat_memory_includes_specific_experiences(self):
        from gm_consistency import prepare_request
        s=state();packet=prepare_request(s,{'task':'npc_chat','thread':'Konan','player_message':'How is the clinic?','schema':{}})
        self.assertIn('clinic',json.dumps(packet))
        self.assertNotIn('relationship_candidates',packet)

    def test_reactive_messages_do_not_leak_on_keyword_overlap(self):
        from simulation_enhancements import reactive_communication
        s=state();s['npc_memories']['Konan']['goal']='Improve clinic medicine'
        events=[{'title':'Secret clinic medicine', 'narrative':'You secretly find forbidden medical notes.', 'importance':60}]
        self.assertEqual(reactive_communication(s,events,1440),[])

    def test_raw_bookkeeping_patch_is_blocked(self):
        from state_guard import APP_OWNED
        self.assertIn('relationship_life',APP_OWNED)
