"""Regression guards for customer conservation and real split-phase injection."""
import copy
import unittest
import numpy as np
from ieee8500_v42.ac import _complex
from ieee8500_v42_balanced.common import *
from ieee8500_v42_balanced.audit import pair_customers
from ieee8500_v42_balanced.engine import BalancedEngine
from ieee8500_v42_aemo.sensitivity import port_audit


class BalancedRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=read(REPORT/'BALANCED_CUSTOMER_RECORDS.json');cls.u=read(REPORT/'UNBALANCED_CUSTOMER_RECORDS.json')
        cls.e=BalancedEngine('TEST_REGRESSION')

    def test_exact_customer_nominal_conservation(self):
        result=pair_customers(self.b,self.u)
        self.assertEqual(len(result),1177)
        self.assertLess(abs(sum(r['balanced_P_kw'] for r in result)-10773.17),1e-8)
        self.assertEqual(sum(r['status']=='fixed' for r in result),24)

    def test_reject_customer_power_loss(self):
        records=copy.deepcopy(self.b);records[0]['kw']+=.001
        with self.assertRaises(AssertionError):pair_customers(records,self.u)

    def test_reject_customer_id_or_missing_leg(self):
        records=copy.deepcopy(self.u);records[0]['name']='wrong_customera'
        with self.assertRaises(AssertionError):pair_customers(self.b,records)

    def test_reject_fixed_status_change(self):
        records=copy.deepcopy(self.u);records[0]['status']='fixed'
        with self.assertRaises(AssertionError):pair_customers(self.b,records)

    def test_original_axes_and_ratings(self):
        old=read(OLD/'ac/FINAL_B0_PLANNING/AC_AXES.json')
        self.assertEqual(self.e.line_axes,old['lines']);self.assertEqual(self.e.transformer_axes,old['transformers'])
        self.assertEqual(self.e.node_axes,old['nodes'])
        self.assertEqual(self.e.d.Lines.Count(),3703);self.assertEqual(self.e.d.Transformers.Count(),1190)
        self.assertTrue(self.e.verify_parameters()['PASS'])

    def test_p5_overlay_exact_identity(self):
        self.assertEqual(sha(REPORT/'overlays/P5.dss'),sha(OLD/'overlays/P5.dss'))
        self.assertEqual(sha(MAPPING),MAPPING_SHA)

    def test_same_pv_hot_installation_and_capacity(self):
        ratio=float(read(DATA/'historical/SCREENING_RULE_PR62.json')['PV_ratio'])
        self.assertEqual(self.e.pv_records,self.u)
        np.testing.assert_array_equal(self.e.pv_capacity,np.array([r['kw'] for r in self.u])*ratio)
        self.assertEqual(self.e.d.Generators.Count(),2354)

    def test_real_lv_hot_currents_and_rating(self):
        e=self.e;data=dict(np.load(DATA/'derived/PLANNING_INPUTS.npz'));t=48
        e.apply_inputs(t,data['gross_factor'][t],data['pv_factor'][t],data['PCC_P_kw'][t],data['PCC_Q_kvar'][t])
        state=read(REPORT/'ac/BALANCED_PLANNING/CONTROL_STATES.json')[t]
        e.settle('fixed',state);actual,pv,error,balance=e.load_measurements()
        self.assertLess(np.abs(e.last_legs-np.column_stack((e.expected_p,e.expected_q))[:,None,:]/2).max(),1e-5)
        self.assertLess(np.abs(balance).max(),1e-5)
        changes=dict(e.base_pcc);changes['STA01']=(-5.,3.)
        e.set_pcc(changes);a=e.settle('auto',state)
        audit=port_audit(e,['STA01'])[0];self.assertTrue(audit['port_limits_PASS'])
        self.assertAlmostEqual(audit['actual_P_kw'],-5.,places=5);self.assertAlmostEqual(audit['actual_Q_kvar'],3.,places=5)
        e.d.Circuit.SetActiveElement(e.pccs['STA01']['element']);current=_complex(e.d.CktElement.Currents())
        self.assertLess(abs(current[0]+current[1]),1e-9)
        self.assertLess(max(abs(current)),27)
        self.assertEqual(e.d.CktElement.NodeOrder(),[1,2])
        e.set_pcc(e.base_pcc)

    def test_fresh_and_independent_full_axes_verifier(self):
        self.assertTrue(read(REPORT/'BALANCED_B0_FRESH_RECEIPT.json')['PASS'])
        verify=read(REPORT/'INDEPENDENT_VERIFICATION.json');self.assertTrue(verify['PASS'])
        self.assertEqual(len(verify['cases']),4)
        for r in verify['cases']:self.assertEqual(r['all_full_axis_violations'],0)
        self.assertEqual(verify['geometry']['axes'],552)

    def test_no_final_case_or_production_claim(self):
        decision=read(REPORT/'SINGLE_CASE_DECISION.json')
        self.assertFalse(decision['final_main_paper_case_selected']);self.assertFalse(decision['Production_eligible'])
        self.assertFalse(decision['final_operating_configuration_frozen']);self.assertEqual(decision['Native_calls'],0)


if __name__=='__main__':unittest.main()
