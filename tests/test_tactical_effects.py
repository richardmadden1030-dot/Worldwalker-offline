"""The shared effect compiler preserves authored identity across worlds."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from tactical_effects import compile_tactical_effect,named_applications


class TacticalEffectTests(unittest.TestCase):
    def test_healing_is_not_converted_to_an_attack(self):
        row=compile_tactical_effect('Bleach','Merciful Thread',{'description':'Repairs wounds and heals one ally.'})
        self.assertEqual(row['effect_type'],'heal');self.assertEqual(row['tactical']['effect'],'heal')

    def test_illusion_becomes_control_not_a_power_bonus(self):
        row=compile_tactical_effect('Bleach','False Moon',{'description':'An illusion misdirects one enemy.'})
        self.assertEqual(row['effect_type'],'control');self.assertNotIn('combat_boosts',row)

    def test_barrier_and_close_attack_receive_different_geometry(self):
        barrier=compile_tactical_effect('Jujutsu Kaisen','Quiet Ward',{'description':'A barrier shields the user.'})
        slash=compile_tactical_effect('One Piece','Tide Slash',{'description':'A sword slash strikes one opponent.'})
        self.assertEqual(barrier['tactical']['shape'],'self');self.assertEqual(barrier['effect_type'],'shield')
        self.assertEqual(slash['tactical']['range'],1)

    def test_ambiguous_power_is_visible_but_disabled(self):
        row=compile_tactical_effect('Hunter x Hunter','Blue Principle',{'description':'Expresses the user’s unique principle.'})
        self.assertIn('tactical_disabled',row);self.assertNotIn('tactical',row)

    def test_authored_geometry_wins_and_is_validated(self):
        row=compile_tactical_effect('Custom World','Hook',{'tactical':{'shape':'line','length':4,'effect':'movement'}})
        self.assertEqual(row['tactical']['length'],4)
        bad=compile_tactical_effect('Custom World','Broken',{'tactical':{'shape':'sphere','effect':'damage'}})
        self.assertIn('tactical_disabled',bad)

    def test_named_applications_keep_names_and_parent_requirements(self):
        rows=named_applications('Kuroshio',[{'name':'Undertow Bind','description':'Restrains one target.'}],requires_form='Shikai — Kuroshio')
        self.assertEqual(rows['Undertow Bind']['requires_form'],'Shikai — Kuroshio')


if __name__=='__main__':unittest.main()
