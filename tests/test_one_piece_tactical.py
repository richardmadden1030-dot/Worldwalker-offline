"""One Piece tactical rules use isolated saves and no AI calls."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_naruto_tactical import fresh
from tactical_combat import ensure_board,board_view,submit_tactical_action,paths
from one_piece_tactics import CATALOG,compile_skill,saved_skill_details,capabilities
from one_piece_power_catalog import DEVIL_FRUITS,CANON_TECHNIQUES,TACTICAL_PRESETS,HAKI_APPLICATIONS,FIGHTING_STYLES

def game(fruit=None,haki=None,skills=None):
    g=fresh(skills or {});g.state['world']='One Piece';g.state['stats']={'Strength':100,'Agility':100,'Endurance':100,'Instinct':100,'Willpower':100}
    g.state['special']={'Devil Fruit Profile':fruit or {},'Haki Profile':haki or {}}
    g.state['combat']['tactical']=None;g.ensure_combat_numbers();b=ensure_board(g.state);b['obstacles']=[]
    b['units'][0].update(x=2,y=2);b['units'][1].update(x=3,y=2)
    return g

def send(g,action='attack',**fields):
    b=g.state['combat']['tactical'];return submit_tactical_action(g,{'action':action,'revision':b['revision'],'request_id':str(b['revision'])+action+str(fields),**fields})

class OnePieceTacticalTests(unittest.TestCase):
    def test_fruit_profile_applications_and_zoan_forms(self):
        fruit={'name':'Cat-Cat Fruit','type':'Zoan','abilities':['Claw Shift — a focused slashing attack','Predator Field — controls a prepared local area'],'awakening_status':'Unawakened'}
        details=saved_skill_details(game(fruit).state)
        self.assertIn('Claw Shift',details);self.assertIn('Hybrid Form',details);self.assertNotIn('Cat-Cat Fruit Awakening',details)
        self.assertEqual(compile_skill('Hybrid Form',details['Hybrid Form'])['tactical']['effect'],'transform')

    def test_unrelated_unknown_fruit_power_is_not_invented(self):
        d=compile_skill('Reality Rewrite',{'description':'Does something unprecedented','category':'devil fruit'})
        self.assertIn('tactical_disabled',d)

    def test_haki_profiles_compile_and_capabilities_require_awakened_record(self):
        haki={'Observation':{'mastery':20,'applications':['Presence sensing']},'Armament':{'mastery':10,'applications':['Hardening']},'Conqueror':{'mastery':0,'applications':[]}}
        g=game(haki=haki,skills={'Observation Haki':{'description':'Presence sensing'},'Armament Haki':{'description':'Hardening'}})
        self.assertEqual(set(capabilities(g.state)),{'observation-haki','armament-haki'})
        self.assertEqual(compile_skill('Conqueror Haki',{'description':'Intimidation burst'})['tactical']['shape'],'burst')

    def test_legacy_haki_save_is_migrated_into_visible_tactical_options(self):
        g=game();g.state['special']={'Haki':{'Observation':18,'Armament':'Awakened','Conqueror':'Unawakened'}}
        self.assertEqual(set(capabilities(g.state)),{'observation-haki','armament-haki'})
        details=saved_skill_details(g.state)
        self.assertIn('Observation Haki',details);self.assertIn('Armament Haki',details);self.assertNotIn('Conqueror Haki',details)

    def test_logia_requires_haki_seastone_or_counter(self):
        g=game();enemy=g.state['combat']['tactical']['units'][1];enemy['capabilities']=['logia']
        send(g,x=3,y=2);self.assertEqual(enemy['hp'],300);self.assertTrue(g.state['combat']['log'][-1]['targets'][0]['immune'])
        g=game(haki={'Armament':{'mastery':10,'applications':['Hardening']}});enemy=g.state['combat']['tactical']['units'][1];enemy['capabilities']=['logia']
        send(g,x=3,y=2);self.assertLess(enemy['hp'],300)

    def test_seastone_or_submersion_suppresses_power_without_spending(self):
        g=game(skills={'Flame Shot':{'description':'Fire projectile','category':'devil fruit','fruit_name':'Flame-Flame Fruit'}});p=g.state['combat']['tactical']['units'][0];p['statuses']=[{'kind':'seastone','rounds_left':2}]
        before=copy.deepcopy(g.state)
        with self.assertRaises(ValueError):send(g,ability='Flame Shot',x=3,y=2)
        self.assertEqual(g.state,before)

    def test_seastone_does_not_disable_unrelated_physical_technique(self):
        g=game(skills={'Sword Slash':{'description':'A practiced sword attack','category':'swordsmanship'}});p=g.state['combat']['tactical']['units'][0];p['statuses']=[{'kind':'seastone','rounds_left':2}]
        send(g,ability='Sword Slash',x=3,y=2)
        self.assertLess(g.state['combat']['tactical']['units'][1]['hp'],300)

    def test_flight_and_geppo_cross_but_do_not_land_on_obstacles(self):
        g=game();b=g.state['combat']['tactical'];b['obstacles']=[{'x':2,'y':3,'kind':'mast'}];p=b['units'][0];p['capabilities']=['flight']
        route=paths(b,(2,2),3,p['id']);self.assertIn((2,4),route);self.assertNotIn((2,3),route)

    def test_one_piece_board_is_world_specific_and_keeps_enemy_strength(self):
        g=game();view=board_view(g.state)
        self.assertTrue(view['one_piece_rules']);self.assertFalse(view['naruto_rules']);self.assertIn('skill_profiles',view)
        old=view['units'][1]['power'];g.state['stats']={k:9999 for k in g.state['stats']};self.assertEqual(board_view(g.state)['units'][1]['power'],old)

    def test_zoan_transform_is_free_and_updates_portrait_context(self):
        fruit={'name':'Ox-Ox Fruit','type':'Zoan','abilities':['Horn Strike — attack'],'awakening_status':'Unawakened'}
        g=game(fruit);send(g,'transform',ability='Hybrid Form')
        p=g.state['combat']['tactical']['units'][0];self.assertFalse(p['action_used']);self.assertTrue(g.state['portrait_identity']['active_form']['name'])

    def test_room_shambles_swaps_actual_board_positions(self):
        g=game(skills={'Room: Shambles':{'description':'Swap positions inside Room','category':'devil fruit','fruit_name':'Op-Op Fruit'}})
        p,e=g.state['combat']['tactical']['units'][:2];before=(p['x'],p['y'],e['x'],e['y'])
        send(g,ability='Room: Shambles',x=e['x'],y=e['y'])
        self.assertEqual((p['x'],p['y'],e['x'],e['y']),(before[2],before[3],before[0],before[1]))

    def test_every_curated_move_has_explicit_tactical_geometry_and_visual(self):
        for move in CATALOG.values():
            self.assertIn(move['tactical']['shape'],{'single','arc','line','burst','cone','self'})
            self.assertTrue(move.get('visual_effect',{}).get('asset'))

    def test_canon_registry_covers_major_fruits_haki_styles_and_named_techniques(self):
        self.assertGreaterEqual(len(DEVIL_FRUITS),90)
        self.assertGreaterEqual(len(CANON_TECHNIQUES),250)
        self.assertEqual(set(HAKI_APPLICATIONS),{'Observation Haki','Armament Haki',"Conqueror's Haki"})
        self.assertIn('Rokushiki',FIGHTING_STYLES);self.assertIn('Three Sword Style',FIGHTING_STYLES)
        self.assertEqual(compile_skill('Internal Destruction',{})['armor_piercing'],True)
        self.assertEqual(compile_skill('Future Sight',{})['tactical']['effect'],'buff')

    def test_every_canon_technique_is_locally_preset_without_ai_generation(self):
        valid_effects={'damage','heal','shield','control','debuff','buff','cleanse','transform','summon','movement','field','detect'}
        valid_shapes={'single','self','line','cone','arc','burst','ring','cross'}
        self.assertEqual(set(TACTICAL_PRESETS),set(CANON_TECHNIQUES))
        for name,preset in TACTICAL_PRESETS.items():
            self.assertIn(preset['effect_type'],valid_effects,name)
            self.assertIn(preset['tactical']['shape'],valid_shapes,name)
            self.assertTrue(preset['visual_effect'].get('family'),name)
            self.assertGreaterEqual(preset['resource_cost'],0,name)

    def test_successful_conquerors_overwhelm_emits_victory_cinematic_only_on_success(self):
        g=game(haki={'Conqueror':{'mastery':90,'applications':['Dominating Burst']}})
        g.state['combat']['tactical_enabled']=False
        g._combat_check=lambda *args,**kwargs:{'roll':1,'difficulty':1,'success':True}
        result=g.resolve_combat_round('overwhelm',ability_name='Conqueror Haki')
        self.assertEqual(result['log_tail'][0]['cinematic'],'conquerors_haki')
        self.assertEqual(result['log_tail'][0]['visual_outcome'],'victory')

        g=game(haki={'Conqueror':{'mastery':90,'applications':['Dominating Burst']}})
        g.state['combat']['tactical_enabled']=False
        g._combat_check=lambda *args,**kwargs:{'roll':100,'difficulty':1,'total':0,'success':False}
        result=g.resolve_combat_round('overwhelm',ability_name='Conqueror Haki')
        self.assertEqual(result['log_tail'][0]['visual_outcome'],'resisted')

if __name__=='__main__':unittest.main()
