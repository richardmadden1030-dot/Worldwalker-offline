import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from campaign_review import review_candidates
from simulation_integrity import travel_route, travel_plan_for_actions, apply_player_correction
from politics import normalize_political_state
from systems import map_snapshot
from worlds import WORLD_DATA


class MapReliabilityTests(unittest.TestCase):
    def test_malformed_narrative_hex_count_does_not_block_load(self):
        state=self.state(); state['political_regions'][0]['hex_count']='a small estate'
        normalize_political_state(state)
        self.assertEqual(state['political_regions'][0]['hex_count'],1)

    def state(self):
        return {'world':'Naruto','name':'Ren','location':'Konohagakure','turn':5,'skills':{},
                'political_regions':[{'id':'holding','name':'Ren Estate','anchor':'Konohagakure',
                                      'controller':'Ren','hex_count':7,'player_founded':True}]}

    def atlas(self,state):
        return map_snapshot(state,WORLD_DATA['Naruto']['map'],'Naruto')['atlas']

    def test_lost_holding_does_not_reappear_after_normalization_and_reload(self):
        state=self.state()
        state['political_regions'][0]['status']='lost'
        normalize_political_state(state)
        loaded=json.loads(json.dumps(state))
        self.assertFalse(any(c['owner']=='Ren' for c in self.atlas(loaded)['cells']))

    def test_transfer_not_reverted_by_unchanged_old_location_detail(self):
        before=self.state()
        before['location_details']={'Konohagakure':{'controlling_faction':'Ren'}}
        state=copy.deepcopy(before)
        state['political_regions'][0]['controller']='New Clan'
        normalize_political_state(state,before)
        self.assertEqual(state['political_regions'][0]['controller'],'New Clan')

    def test_no_substring_capture_from_nearby_location(self):
        state=self.state()
        state['political_regions'][0]['anchor']='Konohagakure Outskirts'
        state['location_details']={'Konohagakure':{'controlling_faction':'Other'}}
        normalize_political_state(state)
        self.assertEqual(state['political_regions'][0]['controller'],'Ren')

    def test_empty_and_ambiguous_routes_fail_closed(self):
        for name in ['', 'Land of']:
            self.assertFalse(travel_route(self.state(),name)['reachable'])

    def test_sub_location_prefers_longest_landmark(self):
        state={'world':'Bleach','location':'Urahara Training Grounds, lower room'}
        self.assertEqual(travel_route(state,'Karakura Town')['origin'],'Urahara Training Grounds')

    def test_queued_travel_legs_chain(self):
        plans=travel_plan_for_actions(self.state(),['Travel to Sunagakure','Travel to Amegakure'])
        self.assertEqual(plans[1]['origin'],'Sunagakure')
        self.assertEqual(plans[1]['minutes'],travel_route(self.state(),'Amegakure',origin='Sunagakure')['minutes'])

    def test_review_is_readonly_deduplicated_and_not_npc_or_plan(self):
        state=self.state()
        state['campaign_canon']=[{'outcome':x} for x in ['You learned Water Prison.','You learned Water Prison.',
                                'Kakashi learned Chidori.','You will learn Rasengan.','You could have awakened Sharingan.',
                                'You conquered Amegakure.']]
        old=copy.deepcopy(state)
        rows=review_candidates(state)
        self.assertEqual({r['target'] for r in rows},{'Water Prison','Amegakure'})
        self.assertEqual(len(rows),2)
        self.assertEqual(state,old)

    def test_exact_holding_correction_preserves_extent_after_reload(self):
        state=self.state()
        apply_player_correction(state,'territory','Ren Estate','New Clan')
        loaded=json.loads(json.dumps(state))
        normalize_political_state(loaded)
        self.assertEqual(sum(c['owner']=='New Clan' for c in self.atlas(loaded)['cells']),7)
        self.assertEqual(loaded['turn'],5)

    def test_unknown_territory_rejected_without_writing(self):
        state=self.state(); prior=copy.deepcopy(state)
        with self.assertRaises(ValueError):apply_player_correction(state,'territory','Imaginary Continent','Ren')
        self.assertEqual(state,prior)

    def test_village_correction_does_not_annex_country(self):
        state=self.state(); state['political_regions']=[]
        apply_player_correction(state,'territory','Konohagakure','Ren')
        cells=self.atlas(state)['cells']
        self.assertTrue(any(c['owner']=='Land of Fire' for c in cells))
        self.assertLess(sum(c['owner']=='Ren' for c in cells),25)

    def test_http_review_and_stale_preview_are_nonmutating(self):
        import app as module
        from worlds import BASE_STATE
        old,active=module.game.state,module.game.campaign_active
        try:
            state=copy.deepcopy(BASE_STATE); state.update(self.state())
            module.game.state=state; module.game.campaign_active=True
            client=module.app.test_client(); prior=copy.deepcopy(state)
            self.assertEqual(client.get('/api/campaign/review').status_code,200)
            payload={'type':'territory','target':'Ren Estate','value':'New Clan'}
            preview=client.post('/api/campaign/correct/preview',json=payload)
            self.assertEqual(preview.status_code,200)
            self.assertEqual(module.game.state,prior)
            self.assertEqual(client.post('/api/campaign/correct',json=payload).status_code,409)
            module.game.state['political_regions'][0]['controller']='Third Clan'
            payload['preview_token']=preview.get_json()['preview_token']
            self.assertEqual(client.post('/api/campaign/correct',json=payload).status_code,409)
            self.assertEqual(module.game.state['political_regions'][0]['controller'],'Third Clan')
        finally:
            module.game.state=old; module.game.campaign_active=active

if __name__=='__main__':unittest.main()
