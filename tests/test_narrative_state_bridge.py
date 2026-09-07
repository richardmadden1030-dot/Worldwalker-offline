import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from campaign_reliability import reconcile_narrated_consequences


def state():
    return dict(name='Ren',world='Naruto',turn=50,location='Konoha',skills={},inventory=[],titles=[],conditions=[],
                quests=[],npc_memories={'Kaito':{'status':'alive','location':'Konoha'}},companions=[])


def reconcile(s, **claim):
    return reconcile_narrated_consequences(copy.deepcopy(s),s,{'consequence_manifest':[claim]})


class NarrativeStateBridgeTests(unittest.TestCase):
    def test_discovery_does_not_teleport_player(self):
        s=state(); reconcile(s,kind='location',target='Old Watchtower',change='discovered',evidence='A scout marks it on your map.')
        self.assertEqual(s['location'],'Konoha')
        self.assertIn('Old Watchtower',s['discovered_locations'])

    def test_skill_names_do_not_duplicate_by_case(self):
        s=state(); s['skills']['Fireball']={'effect':'Fire projectile'}
        reconcile(s,kind='skill',target='fireball',change='gained',details={'effect':'Fire projectile'},evidence='You learned Fireball.')
        self.assertEqual(len(s['skills']),1)

    def test_npc_skill_does_not_go_to_player(self):
        s=state(); reconcile(s,kind='skill',target='Fireball',subject='Kaito',change='gained',details={'effect':'Fire projectile'},evidence='Kaito learned Fireball.')
        self.assertNotIn('Fireball',s['skills'])

    def test_uncertain_death_does_not_kill_player(self):
        s=state(); reconcile(s,kind='death',target='Ren',change='suspected',evidence='A distant rumor says Ren died.')
        self.assertNotEqual(s.get('alive'),False)

    def test_explicit_npc_death_reaches_memory(self):
        s=state(); s['companions']=[{'name':'Kaito','status':'alive'}]
        reconcile(s,kind='death',subject='Kaito',target='Kaito',change='died',evidence='Kaito died in the battle.')
        self.assertEqual(s['npc_memories']['Kaito']['status'],'dead')
        self.assertEqual(s['companions'][0]['status'],'dead')

    def test_quest_evidence_does_not_override_in_progress(self):
        s=state(); s['quests']=[{'name':'Repair Bridge','status':'Active'}]
        reconcile(s,kind='quest',target='Repair Bridge',change='in_progress',evidence='The repairs are not completed.')
        self.assertEqual(s['quests'][0]['status'],'Active')

    def test_destroyed_equipped_item_does_not_remain_equipped(self):
        s=state(); s['inventory']=[{'name':'Iron Sword'}];s['equipment']={'Weapon':'Iron Sword'}
        reconcile(s,kind='item',target='Iron Sword',change='destroyed',evidence='The Iron Sword broke beyond repair.')
        self.assertNotIn('Iron Sword',str(s['equipment']))

    def test_safe_gain_and_completion_still_work(self):
        s=state();s['quests']=[{'name':'Deliver Letter','status':'Active'}]
        reconcile(s,kind='skill',target='Fireball',change='gained',details={'effect':'Fire projectile'},evidence='You learned Fireball.')
        reconcile(s,kind='quest',target='Deliver Letter',change='completed',evidence='The letter reached its recipient.')
        self.assertIn('Fireball',s['skills']);self.assertEqual(s['quests'][0]['status'],'Completed')

    def test_sharingan_gain_syncs_special_panel(self):
        from world_progression import normalize_world_progression
        s=state();before=copy.deepcopy(s)
        reconcile(s,kind='skill',target='Sharingan',change='gained',details={'effect':'A transplanted Sharingan grants visual perception.'},evidence='You gained a Sharingan.')
        normalize_world_progression(s,before)
        self.assertIn('Sharingan',str(s['special']['Dōjutsu Profile']))

    def test_old_save_review_is_read_only_and_skips_later_loss(self):
        from campaign_review import review_candidates
        s=state();s['campaign_canon']=[{'turn':1,'outcome':'You learned **Fireball**.'},{'turn':2,'outcome':'You forgot Fireball.'}]
        before=copy.deepcopy(s)
        self.assertFalse(review_candidates(s));self.assertEqual(s,before)

    def test_missing_mechanics_reaches_existing_review(self):
        from campaign_review import review_candidates
        s=state();reconcile(s,kind='skill',target='Fireball',change='gained',evidence='You learned Fireball.')
        suggestions=review_candidates(s)
        self.assertEqual(suggestions[0]['target'],'Fireball');self.assertNotIn('Fireball',s['skills'])

    def test_confirmed_death_preserves_historical_roster(self):
        s=state();s['organizations']={'squad':{'members':{'Kaito':{'status':'active','position':'Medic'}}}}
        reconcile(s,kind='death',target='Kaito',change='died',evidence='Kaito died in battle.')
        member=s['organizations']['squad']['members']['Kaito']
        self.assertEqual(member['status'],'dead');self.assertEqual(member['position'],'Medic')

    def test_explicit_old_save_correction_and_case_safe_skill(self):
        from simulation_integrity import apply_player_correction
        s=state();s['skills']['Fireball']={'effect':'Fire projectile'}
        apply_player_correction(s,'skill','fireball','A sweeping fire projectile.')
        self.assertEqual(len(s['skills']),1)
        apply_player_correction(s,'npc_status','Kaito','dead','Confirmed by the battle result.')
        self.assertFalse(s['npc_memories']['Kaito']['alive'])

    def test_tactical_receipt_syncs_named_death_once(self):
        from tactical_combat import record_outcome
        class Game:
            def __init__(self): self.state=state();self.lines=[]
            def append(self,*args): self.lines.append(args)
        game=Game();game.state['combat']={'casualties':[{'name':'Kaito','side':'enemy','outcome':'killed'}]}
        board={'units':[{'name':'Kaito','side':'enemy','hp':0,'alive':False}]}
        record_outcome(game,board,'victory');record_outcome(game,board,'victory')
        self.assertFalse(game.state['npc_memories']['Kaito']['alive'])
        self.assertEqual(len(game.state['tactical_battle_results']),1)
        self.assertFalse(game.state.get('information_packets'))

    def test_new_records_survive_save_round_trip_all_worlds(self):
        import json
        from worlds import WORLD_DATA
        for world in WORLD_DATA:
            with self.subTest(world=world):
                s=state();s['world']=world
                reconcile(s,kind='skill',target='Test technique',change='gained',details={'effect':'A test-only ranged attack.'},evidence='You learned Test technique.')
                loaded=json.loads(json.dumps(s))
                reconcile(loaded,kind='skill',target='test technique',change='gained',details={'effect':'A test-only ranged attack.'},evidence='You learned Test technique.')
                self.assertEqual(len(loaded['skills']),1)

    def test_real_skip_syncs_new_skill_without_teleport(self):
        from game import GameSession
        from worlds import BASE_STATE
        game=GameSession();game.state=copy.deepcopy(BASE_STATE)
        game.state.update(state());game.autosave=lambda *a,**k:None
        game.apply_time_skip({'narrative':'You gain a Sharingan. A scout reports a watchtower.', 'state_patch':{},
            'consequence_manifest':[{'kind':'skill','target':'Sharingan','change':'gained','details':{'effect':'A transplanted eye improves perception.'}},
                                    {'kind':'location','target':'Old Watchtower','change':'discovered'}]},1,'days')
        self.assertEqual(game.state['location'],'Konoha')
        self.assertIn('Sharingan',str(game.state['special']['Dōjutsu Profile']))

    def test_npc_death_http_preview_and_stale_guard(self):
        import app as api
        from unittest.mock import patch
        from game import GameSession
        from worlds import BASE_STATE
        game=GameSession();game.state=copy.deepcopy(BASE_STATE);game.state.update(state())
        game.campaign_active=True;game.autosave=lambda *a,**k:None
        payload={'type':'npc_status','target':'Kaito','value':'dead','explanation':'Confirmed battle casualty.'}
        with patch.object(api,'game',game):
            client=api.app.test_client();before=copy.deepcopy(game.state)
            preview=client.post('/api/campaign/correct/preview',json=payload)
            self.assertEqual(preview.status_code,200)
            self.assertEqual(game.state,before)
            self.assertTrue(any(row['field']=='npc_memories.Kaito' for row in preview.json['changes']))
            self.assertEqual(client.post('/api/campaign/correct',json=payload).status_code,409)
            payload['preview_token']=preview.json['preview_token']
            game.state['npc_memories']['Kaito']['status']='missing'
            self.assertEqual(client.post('/api/campaign/correct',json=payload).status_code,409)
            payload.pop('preview_token')
            payload['preview_token']=client.post('/api/campaign/correct/preview',json=payload).json['preview_token']
            self.assertEqual(client.post('/api/campaign/correct',json=payload).status_code,200)
            self.assertFalse(game.state['npc_memories']['Kaito']['alive'])

    def test_correction_preview_preserves_object_details(self):
        import subprocess
        js=(Path(__file__).resolve().parents[1]/'frontend/js/app.js').read_text(encoding='utf-8')
        fn=js[js.index('function correctionReadable('):js.index('function compactReadable(')]
        script=fn+"if(!correctionReadable({status:'dead',alive:false}).includes('dead'))throw Error('Hidden status');if(correctionReadable(0)!=='0')throw Error('Lost zero');"
        subprocess.run(['node','-e',script],check=True,capture_output=True)
