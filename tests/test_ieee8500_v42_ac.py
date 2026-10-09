"""Real OpenDSS checks of original source and conductor-level AC contracts."""
import math
import unittest
from pathlib import Path

import numpy as np
import opendssdirect as odd

from ieee8500_v42.ac import IEEE8500AC


class OriginalACContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = IEEE8500AC()
        cls.original = cls.engine.solve()

    def test_original_regression_against_independent_raw_compile(self):
        d = odd.NewContext()
        d.Basic.AllowChangeDir(False)
        d.Basic.AllowForms(False)
        d.Text.Command(f'compile "{self.engine.source_dir / "Master-unbal.dss"}"')
        d.Text.Command('set maxiterations=100 maxcontroliter=100 tolerance=1e-9 mode=snapshot controlmode=static')
        d.Solution.Solve()
        self.assertTrue(d.Solution.Converged())
        self.assertTrue(d.Solution.ControlActionsDone())
        np.testing.assert_allclose(d.Circuit.AllBusMagPu(), [r['voltage_pu'] for r in self.original['buses']], atol=2e-8, rtol=0)
        np.testing.assert_allclose(d.Circuit.TotalPower(), -np.array([self.original['summary']['source_kw'], self.original['summary']['source_kvar']]), atol=2e-4, rtol=0)
        self.assertEqual(self.engine.inventory['counts'], {'buses':4876,'nodes':8531,'lines':3703,'transformers':1190,'loads':2354,'regcontrols':12,'capacitors':10,'capcontrols':9})
        self.assertTrue(self.engine.verify_source_unchanged())

    def test_original_triplex_hots_and_winding_ratings(self):
        ct = next(r for r in self.engine.inventory['transformers'] if r['element']=='Transformer.t21396254a')
        self.assertEqual(ct['xfmrcode'], 'ct15')
        self.assertEqual(ct['node_order'], [1,0,1,0,0,2])
        self.assertAlmostEqual(ct['windings'][1]['normal_line_amps']/ct['windings'][0]['normal_line_amps'],60)
        self.assertEqual(ct['windings'][0]['kva_nameplate'], 15)
        self.assertEqual(ct['normal_hkva'], 16.5)
        self.assertGreater(self.original['summary']['transformer_nameplate_kva_rho_max'], self.original['summary']['transformer_kva_rho_max'])
        self.assertTrue(all(r['ncond']==2 for r in self.engine.inventory['lines'] if r['group']=='Triplex'))

    def test_bulk_arrays_equal_full_all_conductor_audit(self):
        a = self.engine
        r = a.solve()
        arrays = a.measurement_arrays()
        np.testing.assert_allclose(arrays['line_amps'], [v['amps'] for v in r['lines']], atol=1e-10)
        np.testing.assert_allclose(arrays['transformer_current_rho'], [v['current_rho'] for v in r['transformers']], atol=1e-10)
        np.testing.assert_allclose(arrays['node_voltage_pu'], [v['voltage_pu'] for v in r['buses']], atol=1e-12)
        self.assertAlmostEqual(max(arrays['line_rho'][a.objective_line_mask]), r['summary']['rho_max'],12)
        self.assertAlmostEqual(max(arrays['line_rho']), r['summary']['rho_max_all_terminals'],12)
        self.assertFalse(a.inventory['objective_contract']['unreachable_enabled_lines'])

    def test_split_phase_negative_demand_is_equal_opposite_injection(self):
        a = IEEE8500AC()
        line = next(r for r in a.inventory['lines'] if r['element']=='Line.tpx21459660c0')
        bus = line['buses'][1].split('.')[0]
        a.add_pcc('LV_TEST',bus,mode='LV_SPLIT_240')
        base = a.solve()
        inj = a.solve(pcc_demand={'LV_TEST':(-1,-.25)},control_mode='fixed',fixed_state=base['control_state'])
        pcc = inj['pcc_actual']['LV_TEST']
        self.assertAlmostEqual(pcc['p_kw'],-1,8)
        self.assertAlmostEqual(pcc['q_kvar'],-.25,8)
        self.assertEqual(pcc['node_order'],[1,2])
        self.assertAlmostEqual(pcc['currents_A'][0],pcc['currents_A'][1],10)
        self.assertTrue(200 < pcc['v_ll_V'] < 260)
        self.assertLess(inj['summary']['rho_max'],base['summary']['rho_max'])
        self.assertEqual(inj['control_state'],base['control_state'])
        self.assertLess(abs(inj['summary']['balance_residual_kw']),1e-4)
        self.assertLess(abs(inj['summary']['balance_residual_kvar']),1e-4)
        a.d.Circuit.SetActiveElement(a.pccs['LV_TEST']['element'])
        current=np.asarray(a.d.CktElement.Currents())
        np.testing.assert_allclose(current[:2]+current[2:],0,atol=1e-12)

    def test_independent_auto_controls_repeat_without_planning_tap_copy(self):
        a = IEEE8500AC()
        a.add_pcc('MV_TEST','l3234149')
        initial = a.control_state()
        r1 = a.solve(pcc_demand={'MV_TEST':(100,30)})
        a.solve(pcc_demand={'MV_TEST':(500,150)},reset_controls=False,snapshot=False)
        r2 = a.solve(pcc_demand={'MV_TEST':(100,30)},reset_controls=True)
        self.assertNotEqual(r1['control_state'],initial)
        self.assertEqual(r1['control_state'],r2['control_state'])
        self.assertAlmostEqual(r1['summary']['rho_max'],r2['summary']['rho_max'],7)
        self.assertTrue(r2['summary']['converged'])
        self.assertTrue(r2['summary']['control_actions_done'])
        self.assertEqual(r2['summary']['control_queue_size'],0)
        self.assertEqual(a.inventory['counts']['transformers'],a.d.Transformers.Count())
        self.assertTrue(a.verify_source_unchanged())

    def test_single_leg_120_models_and_implied_neutral_are_audited(self):
        a=IEEE8500AC()
        a.add_pcc('LEG1','sx2748781a',mode='LV_LEG1_120')
        a.add_pcc('LEG2','sx2748781a',mode='LV_LEG2_120')
        base=a.solve()
        for name,expected_nodes in [('LEG1',[1,0]),('LEG2',[2,0])]:
            r=a.solve(pcc_demand={name:(-1,-.25)},control_mode='fixed',fixed_state=base['control_state'])
            p=r['pcc_actual'][name]
            self.assertEqual(p['node_order'],expected_nodes)
            self.assertAlmostEqual(p['p_kw'],-1,8)
            self.assertAlmostEqual(p['q_kvar'],-.25,8)
            self.assertTrue(100<p['connection_voltage_V']<130)
            self.assertEqual(r['control_state'],base['control_state'])
            self.assertLess(abs(r['summary']['balance_residual_kw']),1e-4)
            line=[x for x in r['lines'] if x['element']=='Line.tpx21382813a0' and x['terminal']==1]
            neutral=-sum(complex(x['i_real_A'],x['i_imag_A']) for x in line)
            self.assertAlmostEqual(abs(neutral),line[0]['implied_neutral_amps'],10)
            self.assertIsNone(line[0]['implied_neutral_rating_A'])
            arr=a.measurement_arrays()
            idx=next(i for i,x in enumerate(a.triplex_terminal_axes) if x['element']=='Line.tpx21382813a0' and x['terminal']==1)
            self.assertAlmostEqual(abs(neutral),arr['triplex_implied_neutral_amps'][idx],10)
            self.assertFalse(r['summary']['triplex_neutral_ampacity_known'])
        self.assertEqual(a.d.Transformers.Count(),1190)
        self.assertEqual(a.d.Circuit.NumBuses(),4876)

    def test_local_split_injection_linear_response_predicts_separate_ac_point(self):
        a=IEEE8500AC()
        line=next(r for r in a.inventory['lines'] if r['element']=='Line.tpx21459660c0')
        a.add_pcc('SENS',line['buses'][1],mode='LV_SPLIT_240')
        base=a.solve()
        response=a.local_injection_sensitivity('SENS',delta_kw=.1,delta_kvar=.1,mode='fixed',base_snapshot=base)
        idx=next(i for i,r in enumerate(a.line_axes) if r['element']==line['element'] and r['terminal']==1 and r['node']==1)
        derivative=response['derivatives']['P']['line_amps'][idx]
        self.assertLess(derivative,-1)
        actual=a.solve(pcc_demand={'SENS':(-.5,0)},control_mode='fixed',fixed_state=base['control_state'])
        predicted=base['lines'][idx]['amps']+.5*derivative
        self.assertLess(abs(actual['lines'][idx]['amps']-predicted),.01)
        for axis in ('P','Q'):
            for endpoint in ('minus_injection','plus_injection'):
                q=response['endpoints'][axis][endpoint]
                self.assertTrue(q['converged'])
                self.assertEqual(q['control_state'],base['control_state'])


if __name__=='__main__':
    unittest.main()
