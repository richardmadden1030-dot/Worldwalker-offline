import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from systems import map_snapshot
from worlds import WORLD_DATA, MAJOR_CHARACTER_STARTS
from starting_holdings import initialize_starting_holdings
from atlas_context import baseline_day, gm_map_context


class AtlasContextTests(unittest.TestCase):
    def test_gm_receives_compact_starting_history(self):
        import json
        context=gm_map_context({'world':'Reincarnated as a Slime','atlas_start_day':0})
        text=json.dumps(context)
        self.assertIn('Tempest',text)
        self.assertNotIn('cells',context)
        self.assertLess(len(text),3000)

    def snapshot(self,world='Naruto',**patch):
        state={'world':world,'location':WORLD_DATA[world]['map'][0][0],**patch}
        return map_snapshot(state,WORLD_DATA[world]['map'],world)

    def test_canon_starts_do_not_automatically_own_land(self):
        for world,starts in MAJOR_CHARACTER_STARTS.items():
            for start in starts:
                state={'world':world,**copy.deepcopy(start)}
                self.assertEqual(initialize_starting_holdings(state),[],start['name'])

    def test_tempest_not_created_by_elapsed_days(self):
        for day in (0,100,900):
            snapshot=self.snapshot('Reincarnated as a Slime',calendar_anchor_day=0,canon_day=day)
            self.assertNotIn('Jura Tempest Federation',{c['owner'] for c in snapshot['atlas']['cells']})
            self.assertNotIn('Tempest',{n['name'] for n in snapshot['nodes']})

    def test_late_start_and_recorded_foundation(self):
        late=self.snapshot('Reincarnated as a Slime',calendar_anchor_day=179)
        self.assertIn('Jura Tempest Federation',{c['owner'] for c in late['atlas']['cells']})
        own=self.snapshot('Reincarnated as a Slime',calendar_anchor_day=0,political_regions=[
            {'name':'Tempest','anchor':'Tempest','controller':'My Federation','hex_count':7}])
        self.assertEqual(sum(c['owner']=='My Federation' for c in own['atlas']['cells']),7)
        self.assertIn('Tempest',{n['name'] for n in own['nodes']})

    def test_village_capture_not_country_annexation(self):
        a=self.snapshot(location_details={'Konohagakure':{'controlling_faction':'Rebels'}})
        captured=[c for c in a['atlas']['cells'] if c['owner']=='Rebels']
        self.assertTrue(captured)
        self.assertLess(len(captured),15)
        self.assertIn('Land of Fire',{c['owner'] for c in a['atlas']['cells']})

    def test_country_claim_and_estate_creation(self):
        for background,count in [('I am the ruler of Land of Fire.',None),('I own a small estate in Konoha.',1),('I am Hokage of Konoha.',7)]:
            state={'world':'Naruto','name':'Ren','background':background}
            self.assertTrue(initialize_starting_holdings(state))
            a=map_snapshot(state,WORLD_DATA['Naruto']['map'],'Naruto')
            claim=state['political_regions'][0]
            if count is not None:
                self.assertEqual(sum(c.get('claim')==claim['name'] for c in a['atlas']['cells']),count)
            else:
                self.assertTrue(all(c.get('claim')=='Land of Fire' for c in a['atlas']['cells'] if c['district']=='Land of Fire'))

    def test_ambitions_and_past_tense_do_not_grant_land(self):
        for text in ['I want to become ruler of Land of Fire.','I was the ruler of Land of Fire.','I am not the ruler of Land of Fire.','I am the ruler of Land of Fire in my dreams.']:
            self.assertFalse(initialize_starting_holdings({'world':'Naruto','background':text}))

    def test_early_naruto_does_not_place_sound(self):
        a=self.snapshot(calendar_anchor_day=-4900)
        self.assertNotIn('Otogakure',{n['name'] for n in a['nodes']})
        self.assertIn('Land of Rice Fields',{c['owner'] for c in a['atlas']['cells']})

    def test_one_piece_occupation_sovereignty_and_protection(self):
        a=self.snapshot('One Piece',calendar_anchor_day=-7)
        nodes={n['name']:n for n in a['nodes']}
        self.assertEqual(nodes['Dressrosa']['controller'],'Donquixote Pirates')
        self.assertEqual(nodes['Dressrosa']['sovereignty'],'Dressrosa Kingdom')
        self.assertEqual(nodes['Fishman Island']['protection'],'Whitebeard Pirates')
        later=self.snapshot('One Piece',calendar_anchor_day=732)
        self.assertEqual(next(n for n in later['nodes'] if n['name']=='Fishman Island')['protection'],'Big Mom Pirates')

    def test_campaign_changes_override_era(self):
        state={'calendar_anchor_day':732,'location_details':{'Dressrosa':{'controlling_faction':'Player Crew','protection':'None'}}}
        a=self.snapshot('One Piece',**state)
        node=next(n for n in a['nodes'] if n['name']=='Dressrosa')
        self.assertEqual(node['controller'],'Player Crew')
        self.assertEqual(node['local_authority'],'Player Crew')
        self.assertEqual(node['protection'],'None')

    def test_jjk_city_does_not_annex_japan(self):
        a=self.snapshot('Jujutsu Kaisen',location_details={'Tokyo':{'controlling_faction':'Rebels'}})
        self.assertIn('Japan',{c['owner'] for c in a['atlas']['cells']})

    def test_old_save_without_anchor_does_not_guess_from_current_day(self):
        self.assertEqual(baseline_day({'turn':500,'canon_day':10000},'Naruto')[0],-7)

    def test_readonly_and_world_isolation(self):
        for world in WORLD_DATA:
            state={'world':world,'calendar_anchor_day':0,'location':WORLD_DATA[world]['map'][0][0]}
            prior=copy.deepcopy(state)
            a=map_snapshot(state,WORLD_DATA[world]['map'],world)
            self.assertEqual(state,prior)
            self.assertTrue(all(c['owner'] for c in a['atlas']['cells']))

if __name__=='__main__': unittest.main()
