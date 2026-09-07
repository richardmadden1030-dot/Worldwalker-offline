import unittest
from organizations import ensure_organizations, roster_view, group_id


class V364MembershipTruthTests(unittest.TestCase):
    def yahiko_state(self):
        gid = group_id('Akatsuki')
        return {
            'world':'Naruto','name':'Yahiko','campaign_id':'yahiko-old-save','canon_day':100,'turn':80,'location':'Amegakure',
            'organizations':{gid:{'id':gid,'name':'Akatsuki','leader':'Yahiko','members':{
                'Yahiko':{'name':'Yahiko','position':'Founder and Leader','status':'active'},
                'Akatsuki':{'name':'Akatsuki','status':'active'},
                'Amegakure':{'name':'Amegakure','status':'active'},
                'Nagato':{'name':'Nagato','status':'active'},'Konan':{'name':'Konan','status':'active'},'Kagari':{'name':'Kagari','status':'active'},
            }}},
            'faction_rosters':{'Akatsuki':['Yahiko','Akatsuki','Amegakure','Kagari','Nagato','Konan']},
            'location_details':{'Amegakure':{'controlling_faction':'Akatsuki'}},
            'npc_memories':{
                'Nagato':{'role':'Co-founder','organization':'Akatsuki','last_known_location':'Amegakure'},
                'Konan':{'role':'Co-founder','organization':'Akatsuki','last_known_location':'Amegakure'},
                'Kagari':{'role':'Recruiter','organization':'Akatsuki','last_known_location':'Amegakure'},
                'Sasori':{'role':'Operative','last_known_location':'Amegakure'},
                'Hidan':{'role':'Operative','last_known_location':'Amegakure'},
                'Kisame Hoshigaki':{'role':'Operative','last_known_location':'Amegakure'},
                'Orochimaru':{'role':'Research partner','last_known_location':'Amegakure'},
                'Kakuzu':{'role':'Mercenary','last_known_location':'Amegakure'},
                # Deliberately polluted relationship-like records from the bug.
                'Amegakure':{'relationship':80}, 'Akatsuki':{'relationship':90},
            },
            'campaign_canon':[
                {'turn':67,'fact':'Sasori joined the Akatsuki as a confirmed inner-circle member.'},
                {'turn':67,'fact':'Kagari joined the Akatsuki and oversees recruitment.'},
                {'turn':72,'fact':'Hidan was added to the Akatsuki inner circle.'},
                {'turn':75,'fact':'Kisame Hoshigaki became a recognized inner-circle Akatsuki operative under the Kisame Compact.'},
                {'turn':78,'fact':'Orochimaru remains an independent research partner rather than a formal Akatsuki member.'},
                {'turn':79,'fact':'Kakuzu has not accepted the Akatsuki offer.'},
            ],
        }

    def test_yahiko_old_save_repairs_to_seven_real_members(self):
        state = self.yahiko_state(); ensure_organizations(state, legacy_mode=True)
        group = next(g for g in roster_view(state)['groups'] if g['name'] == 'Akatsuki')
        names = {row['name'] for row in group['members'] if row['status'] in {'active','away','missing'}}
        self.assertEqual(names, {'Yahiko','Nagato','Konan','Sasori','Kagari','Hidan','Kisame Hoshigaki'})
        self.assertNotIn('Akatsuki', names); self.assertNotIn('Amegakure', names)
        self.assertNotIn('Orochimaru', names); self.assertNotIn('Kakuzu', names)


if __name__ == '__main__':
    unittest.main()
