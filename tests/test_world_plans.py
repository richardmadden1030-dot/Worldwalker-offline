import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from world_plans import advance, context
from living_world import advance as living_advance
from simulation_integrity import build_travel_graph


class WorldPlanTests(unittest.TestCase):
    def state(self):
        return {'world':'Naruto','name':'Ren','turn':1,'location':'Konohagakure',
                'npc_memories':{'Konan':{}},'skills':{},'standing_intents':[]}
    def create(self,**patch):
        return {'op':'create','id':'clinic','actor':'Konan','goal':'Clinic expansion','location':'Amegakure',
                'evidence':'Konan accepted the supplied clinic project.','known_to_player':True,
                'delivery':{'source':'Konan','channel':'report'},
                'stages':[{'minutes':1440,'routine':True,'summary':'Konan has organized the clinic staff.'},
                          {'minutes':1440,'routine':False,'summary':'The neighboring district has accepted the clinic.'}],**patch}
    def start(self,**patch):
        s=self.state(); advance(s,10000,[self.create(**patch)]); return s
    def test_creation_does_not_retroactively_spend_time(self):
        s=self.start(); self.assertEqual(s['world_plans']['clinic']['stage'],0)
    def test_staged_work_survives_save_and_stops_before_contested_result(self):
        s=self.start(); s=json.loads(json.dumps(s)); s['turn']=2
        events=advance(s,100000)
        self.assertEqual(s['world_plans']['clinic']['status'],'awaiting_resolution')
        self.assertEqual(s['world_plans']['clinic']['stage'],1)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['narrative'],'Konan has organized the clinic staff.')
        self.assertNotIn('political_regions',s)
    def test_retry_cannot_double_progress_or_repeat_report(self):
        s=self.start(); s['turn']=2
        advance(s,720); advance(s,720)
        self.assertEqual(s['world_plans']['clinic']['elapsed_minutes'],720)
        s['turn']=3; self.assertEqual(len(advance(s,720)),1)
        self.assertEqual(advance(s,720),[])
    def test_hidden_plan_progresses_without_leaking_report(self):
        s=self.start(known_to_player=False); s['turn']=2
        self.assertEqual(advance(s,1440),[])
        self.assertEqual(s['world_plans']['clinic']['stage'],1)
        s['turn']=3
        self.assertEqual(len(advance(s,0,[{'op':'reveal','id':'clinic','delivery':{'source':'Konan','channel':'message'}}])),1)
    def test_unknown_actor_and_unsupported_goal_do_not_seed(self):
        s=self.state(); advance(s,1440,[self.create(actor='Invented Stranger'),self.create(evidence='')])
        self.assertEqual(s['world_plans'],{})
    def test_cancelled_order_stops_associated_work(self):
        s=self.start(standing_intent_id='order'); s['standing_intents']=[{'id':'order','status':'cancelled'}]; s['turn']=2
        self.assertEqual(advance(s,10000),[])
        self.assertEqual(s['world_plans']['clinic']['stage'],0)
    def test_incapacitated_actor_does_not_keep_working(self):
        s=self.start(); s['npc_memories']['Konan']['status']='dead'; s['turn']=2
        advance(s,10000); self.assertEqual(s['world_plans']['clinic']['stage'],0)
    def test_prerequisite_prevents_progress(self):
        s=self.start(stages=[{'minutes':60,'routine':True,'summary':'The clinic opens.','requires':['supplies']}]); s['turn']=2
        advance(s,10000); self.assertEqual(s['world_plans']['clinic']['elapsed_minutes'],0)
    def test_explicit_resolution_and_persistent_benefit(self):
        s=self.start(); s['turn']=2; advance(s,3000); s['turn']=3
        update={'op':'resolve','id':'clinic','success':True,'evidence':'The district agreed.',
                'report':'The clinic now serves the neighboring district.',
                'benefit':{'kind':'narrative','description':'Local residents have dependable medical care.'}}
        self.assertEqual(len(advance(s,1440,[update])),1)
        self.assertEqual(s['world_plans']['clinic']['status'],'completed')
        s['turn']=4; advance(s,90000)
        self.assertTrue(s['world_benefits']['clinic']['active'])
        advance(s,0,[{'op':'revoke_benefit','id':'clinic','reason':'The clinic was evacuated after a recorded flood.'}])
        self.assertFalse(s['world_benefits']['clinic']['active'])
    def test_safer_route_is_local_and_nonstacking(self):
        s=self.state(); base=build_travel_graph(s)
        a=base['nodes'][0]['name']; edge=base['edges'][a][0]; b=edge['to']
        benefit={'kind':'safer_route','origin':a,'destination':b,'factor':.75,'active':True}
        s['world_benefits']={'one':benefit,'two':copy.deepcopy(benefit)}
        new=next(e for e in build_travel_graph(s)['edges'][a] if e['to']==b)
        self.assertEqual(new['minutes'],round(edge['minutes']*.75))
    def test_existing_living_world_hook_and_context_are_safe(self):
        s=self.state(); living_advance(s,[],0,[],[self.create()]); prior=copy.deepcopy(s)
        self.assertIn('clinic',s['world_plans']); self.assertTrue(context(s)['plans'])
        self.assertEqual(s,prior)
    def test_real_gm_context_and_public_state_boundaries(self):
        from game import GameSession
        from worlds import BASE_STATE
        from state_guard import migrate_state
        game=GameSession(); game.state=copy.deepcopy(BASE_STATE); game.state.update(self.start(known_to_player=False))
        for history in [[],[{'turn':1,'outcome':'A quiet day.'}]]:
            game.state['campaign_canon']=history
            compiled=game.trimmed_state_for_ai('Continue our ongoing work')
            self.assertIn('world_plan_context',compiled)
            self.assertNotIn('world_plans',compiled)
        self.assertNotIn('world_plans',game.public_state())
        self.assertNotIn('world_plan_context',game.trimmed_state_for_ai('Hello Konan','chat'))
        migrated=migrate_state(json.loads(json.dumps(game.state)))
        # Migration API may include a repair report alongside the state.
        restored=migrated[0] if isinstance(migrated,tuple) else migrated
        self.assertIn('clinic',restored['world_plans'])
    def test_reports_are_capped_and_pending_not_discarded(self):
        s=self.state()
        advance(s,0,[self.create(id=str(i),stages=[{'minutes':60,'routine':True,'summary':f'Clinic {i} is staffed.'}]) for i in range(4)])
        s['turn']=2; self.assertEqual(len(advance(s,60)),2)
        s['turn']=3; self.assertEqual(len(advance(s,60)),2)
        s['turn']=4; self.assertEqual(advance(s,60),[])

if __name__=='__main__':unittest.main()
