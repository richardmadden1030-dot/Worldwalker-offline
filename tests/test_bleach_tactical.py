"""Bleach tactical rules run locally and only expose recorded powers."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_naruto_tactical import fresh
from tactical_combat import ensure_board,board_view,submit_tactical_action
from bleach_tactics import compile_skill,saved_skill_details,capabilities


def game(skills=None,special=None):
    g=fresh(skills or {})
    g.state['world']='Bleach'
    g.state['stats']={'Zanjutsu':100,'Hakuda':90,'Hoho':110,'Kido':120,'Reiatsu Control':130,'Willpower':100}
    g.state['special']=special or {'Spiritual Nature':'Soul Reaper','Zanpakuto':'Unnamed Asauchi',
        'Zanpakuto Profile':{'stage':'Sealed','name':'Unknown'},'Shikai':'Unachieved','Bankai':'Unachieved'}
    g.state['combat']['tactical']=None;g.ensure_combat_numbers();board=ensure_board(g.state);board['obstacles']=[]
    board['units'][0].update(x=2,y=2);board['units'][1].update(x=3,y=2)
    return g


def send(g,action='attack',**fields):
    board=g.state['combat']['tactical']
    return submit_tactical_action(g,{'action':action,'revision':board['revision'],
        'request_id':str(board['revision'])+'-'+action+str(fields),**fields})


class BleachTacticalTests(unittest.TestCase):
    def test_http_endpoint_resolves_bleach_kido(self):
        import app as api
        g=game({'Hadō #4: Byakurai':{'description':'White lightning bolt'}})
        payload={'action':'attack','revision':0,'request_id':'bleach-http-1',
                 'ability':'Hadō #4: Byakurai','x':3,'y':2,'facing':'east'}
        with (patch.object(api,'game',g),patch.object(api,'atomic_game_call',lambda route,body,callback:callback()),
              patch.dict('os.environ',{'WORLDWALKER_NARUTO_TACTICAL':'1'}),
              api.app.test_request_context('/api/combat/tactical',method='POST',json=payload)):
            response=api.api_naruto_tactical();data=response.get_json()
        self.assertEqual(response.status_code,200)
        self.assertEqual(data['combat']['log'][-1]['ability'],'Hadō #4: Byakurai')
        self.assertLess(data['resource'],300)

    def test_legacy_finalizer_respects_tactical_casualties(self):
        g=game();combat=g.state['combat']
        combat['casualties']=[{'name':'Training Hollow','side':'enemy','outcome':'subdued'}]
        combat['spare_enemy']=False
        g.end_combat('victory')
        self.assertFalse(combat['enemy_died'])

    def test_canon_hado_and_bakudo_get_distinct_effects(self):
        byakurai=compile_skill('Hadō #4: Byakurai',{})
        rikujokoro=compile_skill('Bakudō #61: Rikujōkōrō',{})
        danku=compile_skill('Bakudō #81: Dankū',{})
        self.assertEqual(byakurai['tactical']['effect'],'damage')
        self.assertEqual(rikujokoro['tactical']['effect'],'control')
        self.assertEqual(danku['tactical']['effect'],'shield')

    def test_informational_kido_is_not_faked_as_an_attack(self):
        spell=compile_skill('Bakudō #77: Tenteikūra',{})
        self.assertIn('tactical_disabled',spell)

    def test_campaign_original_numbered_kido_is_supported_and_persistent(self):
        spell=compile_skill('Hadō #47: Ember Loom',{'description':'A learned campaign formula.'})
        self.assertEqual(spell['category'],'kido')
        self.assertEqual(spell['tactical']['effect'],'damage')

    def test_unachieved_releases_are_not_exposed(self):
        g=game()
        details=saved_skill_details(g.state)
        self.assertFalse(any('Shikai' in name or 'Bankai' in name for name in details))
        self.assertNotIn('shikai',capabilities(g.state))

    def test_release_profile_synchronizes_into_combat_options(self):
        special={'Spiritual Nature':'Soul Reaper','Zanpakuto':'Kuroshio',
            'Zanpakuto Profile':{'stage':'Bankai','name':'Kuroshio','shikai_name':'Kuroshio',
                'shikai_effect':'Commands a black tide.','bankai_name':'Bankai — Kuroshio Kaimetsu',
                'bankai_effect':'The tide becomes a crushing domain.'},
            'Shikai':'Achieved — Kuroshio','Bankai':'Bankai — Kuroshio Kaimetsu'}
        g=game(special=special);details=saved_skill_details(g.state)
        self.assertIn('Shikai — Kuroshio',details);self.assertIn('Bankai — Kuroshio Kaimetsu',details)
        self.assertEqual(set(capabilities(g.state)),{'zanpakuto','shikai','bankai'})

    def test_shikai_is_a_free_form_change_and_updates_portrait(self):
        special={'Zanpakuto':'Kuroshio','Zanpakuto Profile':{'name':'Kuroshio','shikai_name':'Kuroshio',
                 'shikai_effect':'A black tide binds one target.'},
                 'Shikai':'Achieved — Kuroshio','Bankai':'Unachieved'}
        g=game(special=special);send(g,'transform',ability='Shikai — Kuroshio')
        player=g.state['combat']['tactical']['units'][0]
        self.assertFalse(player['action_used']);self.assertEqual(g.state['portrait_identity']['active_form']['name'],'Shikai — Kuroshio')

    def test_release_application_requires_its_active_form(self):
        special={'Zanpakuto':'Kuroshio','Zanpakuto Profile':{'name':'Kuroshio','shikai_name':'Kuroshio',
                 'shikai_applications':[{'name':'Undertow Bind','description':'Restrains one target.'}]},
                 'Shikai':'Achieved — Kuroshio','Bankai':'Unachieved'}
        g=game(special=special)
        before=copy.deepcopy(g.state)
        with self.assertRaisesRegex(ValueError,'Activate Shikai'):
            send(g,ability='Undertow Bind',x=3,y=2)
        self.assertEqual(g.state,before)
        send(g,'transform',ability='Shikai — Kuroshio')
        # End the free transformation activation's remaining action with the application.
        send(g,ability='Undertow Bind',x=3,y=2)
        enemy=g.state['combat']['tactical']['units'][1]
        self.assertTrue(any(row.get('blocks_action') for row in enemy['statuses']))

    def test_kido_cast_spends_reiryoku_and_affects_target(self):
        g=game({'Hadō #4: Byakurai':{'description':'White lightning bolt'}})
        before=g.state['resource'];enemy=g.state['combat']['tactical']['units'][1]
        send(g,ability='Hadō #4: Byakurai',x=3,y=2)
        self.assertLess(g.state['resource'],before);self.assertLess(enemy['hp'],300)

    def test_board_uses_bleach_rules_without_rescaling_enemy(self):
        g=game();view=board_view(g.state)
        self.assertTrue(view['bleach_rules']);self.assertFalse(view['naruto_rules']);self.assertFalse(view['one_piece_rules'])
        old=view['units'][1]['power'];g.state['stats']={k:9999 for k in g.state['stats']}
        self.assertEqual(board_view(g.state)['units'][1]['power'],old)

    def test_unknown_ability_remains_disabled(self):
        self.assertIn('tactical_disabled',compile_skill('Impossible Mirror Kingdom',{'description':'Unknown effect'}))


if __name__=='__main__':unittest.main()
