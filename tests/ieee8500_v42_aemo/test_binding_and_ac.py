import unittest
import numpy as np
import pandas as pd
import opendssdirect as odd
from ieee8500_v42_aemo.common import *
from ieee8500_v42_aemo.data_binding import STARTS,ENDS,axis_equal,temporal_factors
from ieee8500_v42_aemo.engine import StudyEngine,target_vreg


class BindingTests(unittest.TestCase):
    def test_wrong_interval_axis_rejected(self):
        with self.assertRaises(AssertionError):axis_equal(ENDS,STARTS)

    def test_duplicate_axis_rejected(self):
        bad=list(STARTS);bad[-1]=bad[-2]
        with self.assertRaises(AssertionError):axis_equal(bad,STARTS)

    def test_timezone_shift_rejected(self):
        with self.assertRaises(AssertionError):axis_equal(STARTS.tz_localize(None).tz_localize('UTC'),STARTS)

    def test_forecast_issue_cutoff(self):
        f=read(DATA/'sources/AEMO_FORECAST.json');cutoff=pd.Timestamp(f['cutoff_fixed_aest'])
        self.assertLessEqual(pd.Timestamp(f['demand_issue']),cutoff)
        self.assertLessEqual(pd.Timestamp(f['pv_issue']),cutoff)
        self.assertFalse(read(ROOT/'ieee8500_v42/data/v42_inputs/PLANNING_INPUT_BUNDLE.json')['future_actual_arrival_IDs_present'])

    def test_raw5minute_integral_correction(self):
        doc=read(REPORT/'ACTUAL_EXOGENOUS_AUDIT.json')
        self.assertAlmostEqual(doc['raw_demand_energy_MWh'],doc['new_demand_energy_MWh'],places=8)
        self.assertGreater(abs(doc['old_minus_energy_preserved_MWh']),14)
        raw=rows(DATA/'sources/ACTUAL_SELECTED_DEMAND_5MIN.csv')
        values=np.array([float(r['TOTALDEMAND']) for r in raw]).reshape(96,3).mean(1)
        with np.load(DATA/'derived/ACTUAL_INPUTS.npz') as z:
            np.testing.assert_allclose(values,z['demand_mw'],rtol=0,atol=1e-10)

    def test_frozen_normalization_and_same_pv_capacity(self):
        for source in ('PLANNING','ACTUAL'):
            with np.load(DATA/'derived'/f'{source}_INPUTS.npz') as z:
                p,q=temporal_factors(z['demand_mw'],z['pv_mw'],.11852937486188635)
                np.testing.assert_allclose(p,z['gross_factor'],rtol=0,atol=1e-15)
                np.testing.assert_allclose(q,z['pv_factor'],rtol=0,atol=1e-15)
        self.assertTrue(all(r['planning_actual_same_capacity']=='True' for r in rows(REPORT/'PV_PCC_CAPACITY_AUDIT.csv')))

    def test_actual_gpu_not_forecast_pq_replay(self):
        with np.load(DATA/'derived/PLANNING_INPUTS.npz') as p,np.load(DATA/'derived/ACTUAL_INPUTS.npz') as a:
            self.assertGreater(float(abs(a['PCC_P_kw']-p['PCC_P_kw']).max()),1)
            self.assertTrue((a['total_gpu']<=a['capacities'][None,:]+1e-9).all())
        q=read(REPORT/'ACTUAL_Kestrel_QUEUE_AUDIT.json')
        self.assertEqual(q['raw_requested_UIDs_verified'],2498)
        self.assertEqual(q['future_duration_controller_reads'],0)

    def test_unsupported_causality_remains_unverified(self):
        p=read(REPORT/'PLANNING_INPUT_FREEZE.json')
        self.assertEqual(p['actual_values_read_by_planning_binding'],0)
        self.assertEqual(p['GFS_publication_available_before_cutoff'],'UNVERIFIED')
        self.assertEqual(p['normalization']['empirical_reference_available_at_D1'],'UNVERIFIED')


class ElectricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.e=StudyEngine('unit_fixture','P3',True)

    def test_original_identity_control_ratings_and_pv_wiring(self):
        e=self.e;self.assertTrue(e.verify_parameters()['PASS'])
        for r,name in zip(e.load_records,e.pv_names):
            e.d.Generators.Name(name)
            self.assertEqual(e.d.CktElement.BusNames(),r['buses'])
            self.assertEqual(e.d.Generators.Phases(),1)
            self.assertAlmostEqual(e.d.Generators.kV(),r['kv'])
        self.assertEqual(e.d.RegControls.Count(),12);self.assertEqual(e.d.CapControls.Count(),9)

    def test_static_fixed_global_multiplier_shape_semantics(self):
        d=odd.NewContext();d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False)
        d.Text.Command('new circuit.status_fixture basekv=12.47 pu=1 phases=3 bus1=src')
        d.Text.Command('new Loadshape.trace npts=4 interval=1 mult=[0.2,0.4,0.6,0.8]')
        d.Text.Command('new Load.fixed bus1=src phases=3 kv=12.47 kw=90 pf=1 status=fixed daily=trace')
        d.Text.Command('new Load.variable bus1=src phases=3 kv=12.47 kw=90 pf=1 status=variable daily=trace')
        d.Text.Command('set mode=snapshot loadmult=2');d.Solution.Solve()
        for name,expected in [('fixed',90),('variable',180)]:
            d.Loads.Name(name);self.assertAlmostEqual(sum(d.CktElement.Powers()[0::2]),expected,places=3)
        d.Text.Command('set mode=daily number=1 stepsize=1h hour=0 loadmult=2');d.Solution.Solve()
        d.Loads.Name('fixed');self.assertAlmostEqual(sum(d.CktElement.Powers()[0::2]),90,places=3)
        d.Loads.Name('variable');self.assertLess(sum(d.CktElement.Powers()[0::2]),180)

    def test_fixed_customers_unmodified_on_different_dayslots(self):
        e=self.e
        with np.load(DATA/'derived/PLANNING_INPUTS.npz') as z:
            for t in (0,48,92):
                e.apply_inputs(t,z['gross_factor'][t],z['pv_factor'][t],z['PCC_P_kw'][t],z['PCC_Q_kvar'][t])
                np.testing.assert_array_equal(e.expected_p[e.fixed],e.base_p[e.fixed]*BG_SCALE)
                for r in e.load_records:
                    if r['status']=='fixed':
                        e.d.Loads.Name(r['name']);self.assertEqual(e.d.Properties.Value('Status').lower(),'fixed')

    def test_capbank0_override_not_105pu_guard(self):
        r=next(r for r in rows(REPORT/'emergency/CAPBANK0_PHASE_MONITOR_AUDIT.csv')
               if r['case']=='BASE' and r['source']=='PLANNING' and r['Capacitor']=='capbank0a')
        self.assertEqual(r['states'],'[1]')
        self.assertGreater(float(r['monitor_pu']),1.05)
        self.assertLess(float(r['actual_monitor_V']),float(r['Vmax_V']))
        self.assertGreater(float(r['Vmax_pu']),1.075)
        self.assertEqual(float(r['PTRatio']),1)
        self.assertEqual(float(r['DelayOff_s']),80)

    def test_capbank0_fixed_tap_causal_voltage_relief(self):
        rr=rows(REPORT/'emergency/FIXED_TAP_CAUSAL_COUNTERFACTUALS.csv')
        for source in ('PLANNING','ACTUAL'):
            base=next(r for r in rr if r['source']==source and r['case']=='BASE')
            off=next(r for r in rr if r['source']==source and r['case']=='CAP0A_OFF')
            self.assertLess(float(off['r42246_phase1_pu']),float(base['r42246_phase1_pu']))
            self.assertEqual(off['taps_fixed'],'True');self.assertEqual(off['automatic_policy'],'False')

    def test_emergency_overlay_historical_scope(self):
        self.assertEqual(target_vreg('P3','vreg3_a'),125)
        self.assertEqual(target_vreg('P4','vreg3_b'),123.5)
        self.assertEqual(target_vreg('P4','vreg4_b'),125)
        self.assertEqual(target_vreg('P5','vreg4_b'),123.5)

    def test_strict_voltage_rejects_small_actual_exceedance(self):
        rejected=read(REPORT/'ac/QUALIFIED_B0_ACTUAL/RECEIPT.json')
        self.assertGreater(rejected['Vmax'],1.05)
        self.assertLess(rejected['Vmax']-1.05,.00002)
        self.assertFalse(rejected['hard_constraints_PASS'])
        self.assertTrue(read(REPORT/'emergency/VALIDATION_ESCALATION.json')['rejected_on_Actual_hard_constraints'])

    def test_final_independent_actual_auto_and_unchanged_pv(self):
        for source in ('PLANNING','ACTUAL'):
            r=read(REPORT/'ac'/('FINAL_B0_'+source)/'RECEIPT.json')
            self.assertTrue(r['hard_constraints_PASS']);self.assertTrue(r['PV_connected'])
            self.assertEqual(r['voltage_violation_cells'],0)
            fresh=read(REPORT/('FINAL_'+source+'_FRESH_VERIFICATION.json'))
            self.assertEqual(max(fresh['maximum_absolute_errors'].values()),0)
        self.assertNotEqual(read(REPORT/'ac/FINAL_B0_PLANNING/CONTROL_STATES.json'),
                            read(REPORT/'ac/FINAL_B0_ACTUAL/CONTROL_STATES.json'))


if __name__=='__main__':unittest.main()
