import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from world_atlas import base_atlas, political_atlas, inside
from systems import map_snapshot
from worlds import WORLD_DATA
from atlas_context import VILLAGE_COUNTRIES


class WorldAtlasTests(unittest.TestCase):
    def snapshot(self,world='Naruto',**extra):
        state={'world':world,'location':WORLD_DATA[world]['map'][0][0],**extra}
        return map_snapshot(state,WORLD_DATA[world]['map'],world)

    def test_land_always_has_one_owner_and_stable_ids(self):
        for world in WORLD_DATA:
            a=self.snapshot(world)['atlas']
            with self.subTest(world=world):
                self.assertTrue(a['cells'])
                self.assertEqual(len(a['cells']),len({c['id'] for c in a['cells']}))
                self.assertTrue(all(c['owner'] and c['owner'] not in {'Unknown','Unclaimed'} for c in a['cells']))
                # Dense interior sampling proves that coverage is not limited
                # to a radius around whichever starting town was selected.
                for x in range(1,100,3):
                    for y in range(1,100,3):
                        if any(inside(x,y,l['polygon']) for l in a['land']):
                            self.assertLess(min((c['x']-x)**2+(c['y']-y)**2 for c in a['cells']),2)

    def test_presets_do_not_depend_on_start(self):
        for world in WORLD_DATA:
            if world in {'Bleach','Solo Max-Level Newbie'}:continue
            a=self.snapshot(world)['atlas']
            b=self.snapshot(world,location=WORLD_DATA[world]['map'][-1][0])['atlas']
            self.assertEqual(a['revision'],b['revision'],world)

    def test_naruto_places_have_the_right_polity(self):
        nodes={n['name']:n for n in self.snapshot()['nodes']}
        for name in ['Konohagakure','Sunagakure','Kirigakure','Kumogakure','Iwagakure','Amegakure','Kusagakure','Takigakure']:
            self.assertEqual(nodes[name]['controller'],VILLAGE_COUNTRIES[name])
            self.assertEqual(nodes[name]['local_authority'],name)

    def test_country_transfer_updates_markers_and_every_district_tile(self):
        before=self.snapshot()['atlas']
        after=self.snapshot(location_details={'Land of Fire':{'controlling_faction':'Player Alliance'}})
        self.assertNotEqual(before['revision'],after['atlas']['revision'])
        self.assertTrue(all(c['owner']=='Player Alliance' for c in after['atlas']['cells'] if c['district']=='Land of Fire'))
        self.assertEqual(next(n for n in after['nodes'] if n['name']=='Konohagakure')['controller'],'Player Alliance')

    def test_claim_starts_one_tile_and_grows_exactly(self):
        claim={'name':'My Holding','anchor':'Konohagakure','controller':'My Clan','player_founded':True}
        for count in [1,7,40]:
            claim['hex_count']=count
            a=self.snapshot(political_regions=[claim])['atlas']
            claimed=[c for c in a['cells'] if c['owner']=='My Clan']
            self.assertEqual(len(claimed),count)
            self.assertEqual(len({c['land'] for c in claimed}),1)

    def test_unanchored_claim_does_not_follow_player(self):
        a=self.snapshot(political_regions=[{'name':'Lost Castle','controller':'Player'}])['atlas']
        self.assertEqual(a['revision'],self.snapshot()['atlas']['revision'])
        self.assertTrue(a['warnings'])

    def test_realm_claim_stays_in_its_realm(self):
        a=self.snapshot('Bleach',political_regions=[{'name':'Royal Claim','realm':'Royal Realm','x':50,'y':44,'controller':'Player','player_founded':True}])
        for b in a['boards']:
            self.assertEqual(any(c['owner']=='Player' for c in b['atlas']['cells']),b['name']=='Royal Realm')

    def test_solo_only_returns_current_floor(self):
        a=self.snapshot('Solo Max-Level Newbie',location='Floor 12')
        self.assertEqual([n['name'] for n in a['nodes']],['Floor 12'])
        self.assertNotIn('boards',a)
        self.assertIn('Floor 12',a['atlas']['id'])

    def test_snapshot_does_not_mutate_old_save(self):
        state={'world':'Naruto','location':'Konohagakure','political_regions':[{'name':'Holding','controller':'Clan','anchor':'Konohagakure','hex_count':1}]}
        prior=copy.deepcopy(state)
        map_snapshot(state,WORLD_DATA['Naruto']['map'],'Naruto')
        self.assertEqual(state,prior)

    def test_no_geography_leaks_between_worlds(self):
        for world in WORLD_DATA:
            a=self.snapshot(world)['atlas']
            if world!='Naruto':self.assertNotIn('Konohagakure',{c['owner'] for c in a['cells']})

    def test_hxh_mitene_and_overgeared_continents(self):
        nodes={n['name']:n for n in self.snapshot('Hunter x Hunter')['nodes']}
        self.assertGreater(nodes['NGL']['y'],nodes['Yorbian Continent']['y'])
        self.assertLess(nodes['NGL']['x'],nodes['East Gorteau']['x'])
        nodes={n['name']:n for n in self.snapshot('Overgeared')['nodes']}
        self.assertGreater(nodes['Pangea']['x'],nodes['Valhalla']['x'])

    def test_jjk_school_is_not_a_country(self):
        a=self.snapshot('Jujutsu Kaisen')['atlas']
        self.assertEqual({c['owner'] for c in a['cells']},{'Japan'})

if __name__=='__main__':unittest.main()
