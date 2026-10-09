"""Meaningful LV audit contracts; no AC/Native optimization in these tests."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from ieee8500_v42 import lv_sensitivity as lv


class LVSensitivityTests(unittest.TestCase):
    def test_source_path_includes_original_reactor_without_inventory_record(self):
        reactors=SimpleNamespace(AllNames=lambda:['HVMV_Sub_HSB'],Name=lambda name:None)
        element=SimpleNamespace(BusNames=lambda:['sourcebus.1.2.3','hv.1.2.3'],Enabled=lambda:True)
        engine=SimpleNamespace(d=SimpleNamespace(Reactors=reactors,CktElement=element),
            inventory=dict(lines=[dict(element='Line.primary',buses=['mv.1.2.3','pcc.1.2.3'],enabled=True)],
                transformers=[dict(element='Transformer.source',buses=['hv.1.2.3','mv.1.2.3'],enabled=True)]))
        path=lv.original_paths(engine)['pcc']
        self.assertEqual(path,{'reactor.hvmv_sub_hsb','transformer.source','line.primary'})

    def test_affine_interval_requires_repair_when_base_overloaded(self):
        lo,hi,ok=lv.linear_interval([1.1],[-.1],[0],[1],5)
        self.assertTrue(ok)
        self.assertAlmostEqual(lo,1.)
        self.assertEqual(hi,5.)

    def test_conflicting_bounds_fail_even_if_hardware_has_margin(self):
        self.assertEqual(lv.linear_interval([1.1,1.1],[.1,-.1],[0,0],[1,1],5),(0.,0.,False))

    def test_constant_infeasible_axis_is_not_ignored(self):
        self.assertEqual(lv.linear_interval([1.1],[0],[0],[1],5),(0.,0.,False))

    def test_small_signal_global_check_retains_baseline_and_new_violations(self):
        base=dict(line_rho=np.array([1.2,.9]),node_voltage_pu=np.array([1.06,1.0]),
            transformer_current_rho=np.array([.8]),transformer_winding_nameplate_kva_rho=np.array([.8]))
        endpoint={k:v.copy() for k,v in base.items()}
        endpoint['line_rho'][1]=1.01;endpoint['node_voltage_pu'][1]=1.051
        r=lv.global_check(endpoint,base,np.array([True,True]))
        self.assertEqual(r['line_overload_cells'],2)
        self.assertEqual(r['new_line_overload_cells'],1)
        self.assertEqual(r['voltage_violation_cells'],2)
        self.assertEqual(r['new_voltage_violation_cells'],1)

    def test_preregisters_complete_original_population_and_unqualified_status(self):
        old=lv.FOLDER
        with tempfile.TemporaryDirectory() as folder:
            lv.FOLDER=Path(folder)
            try:
                p,rows=lv.freeze_policy()
                self.assertEqual(len(rows),1177)
                self.assertEqual(p['planned_endpoint_AC_solves'],18832)
                self.assertEqual(p['slots'],[0,9,48,75])
                self.assertEqual(p['background_scale'],.552)
                self.assertEqual(len(p['line_set']),20)
                self.assertFalse(p['B1_B2_B3_results_used'])
                self.assertFalse(p['production_certificate'])
                self.assertEqual(p['physical_status'],'SIMULATION_DESIGN_NOT_FIELD')
                p2,_=lv.freeze_policy()
                self.assertEqual(p,p2)
            finally:lv.FOLDER=old


if __name__=='__main__':unittest.main()
