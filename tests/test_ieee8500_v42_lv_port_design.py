"""Conservative dock envelope and actual original split-phase PCC readback."""
import unittest
import tempfile
import math
from pathlib import Path
from ieee8500_v42.lv_port_design import command_check,available_seconds,DESIGN
from ieee8500_v42.ac import IEEE8500AC


class LVPortSimulationDesign(unittest.TestCase):
    def test_continuous_port_and_actual_voltage_current(self):
        r=command_check(5,3,114,-114)
        self.assertTrue(r['interface_envelope_PASS'])
        self.assertAlmostEqual(r['hot1_amps'],math.sqrt(34)*1000/228)
        self.assertEqual(r['hot1_amps'],r['hot2_amps'])
        self.assertEqual(r['implied_inverter_neutral_current_A'],0)
        self.assertFalse(command_check(5,3,105,-105)['interface_envelope_PASS'])
        self.assertFalse(command_check(450,0,120,-120)['interface_envelope_PASS'])
        self.assertFalse(command_check(5,3.1,120,-120)['interface_envelope_PASS'])

    def test_original_delay_and_partial_slot_energy(self):
        self.assertEqual(available_seconds(0,0),300)
        self.assertEqual(available_seconds(0,300),0)
        self.assertEqual(available_seconds(900,0),900)
        self.assertEqual(available_seconds(900,600),600)
        # Mean first-slot energy availability never authorizes higher power.
        self.assertAlmostEqual(5*available_seconds(0,0)/3600,5/12)

    def test_real_240V_single_port_injection_and_source_ratings(self):
        with tempfile.TemporaryDirectory() as temp:
            e=IEEE8500AC(output_dir=Path(temp));counts=dict(e.inventory['counts'])
            e.add_pcc('dock','sx2748781a','LV_SPLIT_240')
            for p,q in ((1,0),(-1,0),(0,1),(0,-1),(5,3)):
                s=e.solve(pcc_demand={'dock':(-p,-q)})
                actual=s['pcc_actual']['dock']
                self.assertAlmostEqual(actual['p_kw'],-p,places=7)
                self.assertAlmostEqual(actual['q_kvar'],-q,places=7)
                self.assertEqual(actual['node_order'],[1,2])
                self.assertAlmostEqual(actual['currents_A'][0],actual['currents_A'][1],places=9)
                self.assertEqual(e.d.Transformers.Count(),counts['transformers'])
                self.assertEqual(e.d.Lines.Count(),counts['lines'])
                self.assertTrue(s['summary']['converged'] and s['summary']['control_actions_done'])
                self.assertGreater(s['summary']['node_voltage_violations_095_105'],0)
            self.assertTrue(e.verify_source_unchanged())

    def test_declared_simulation_and_production_scopes(self):
        self.assertEqual(DESIGN['new_feeder_transformer_count'],0)
        self.assertFalse(DESIGN['production_eligible'])
        self.assertFalse(DESIGN['independent_LV_leg_modes_authorized_for_this_design'])
        self.assertLess(DESIGN['study_DC_discharge_A_at_5kw_eta090_40V'],DESIGN['source_battery_discharge_current_A'])
        self.assertLess(DESIGN['study_DC_charge_A_at_5kw_eta090_40V'],DESIGN['source_battery_charge_current_A'])


if __name__=='__main__':unittest.main()
