import math
import unittest
from fractions import Fraction

from ieee8500_v42_high.mv_design import REPORT, read, csv_rows, transformer_overlay_commands
from ieee8500_v42_high.mv_relocation import interval_constraints


class MVDesignTests(unittest.TestCase):
    def test_original_DSS_all31_and_real_node_availability(self):
        receipt=read(REPORT/'MV_ORIGINAL_SOURCE_PRESERVATION.json')
        self.assertEqual(receipt['before_sha256'],receipt['after_sha256'])
        self.assertEqual(len(receipt['before_sha256']),31)
        rows=csv_rows(REPORT/'MV_STA_ELIGIBILITY_AUDIT.csv')
        self.assertEqual(len(rows),12)
        self.assertTrue(all(r['same_proxy_M1_M2_M3_eligibility']=='FAIL_MISSING_PRIMARY_PHASES' for r in rows))
        self.assertTrue(all(len(r['fresh_original_proxy_nodes'].split(','))==1 for r in rows))

    def test_missing_original_phases_do_not_become_virtual_ABC(self):
        for nodes in ([1],[2],[3],[1,2],[1,3],[2,3],[]):
            with self.assertRaises(ValueError): transformer_overlay_commands('STA01','real_original_bus',nodes)

    def test_exact_slope_interval_preserves_strict_ties(self):
        self.assertEqual(interval_constraints([(Fraction(1),Fraction(-1),'lower'),
                                               (Fraction(-1),Fraction(2),'upper')])[:2],(Fraction(1),Fraction(2)))
        self.assertFalse(interval_constraints([(Fraction(1),Fraction(-1),'lower'),
                                              (Fraction(-1),Fraction(1),'upper')])[-1])
        self.assertFalse(interval_constraints([(Fraction(0),Fraction(0),'coincident')])[-1])

    def test_exact_rotation_domain_certificate_all606_each_STA(self):
        result=read(REPORT/'MV_RELOCATION_ORIENTATION_RESULT.json')
        self.assertTrue(result['complete_all_allowed_rotation_domain_infeasibility'])
        self.assertFalse(result['feasible'])
        allowed=[r for r in result['semicircle_results'] if r['AA132_orientation_feasible']]
        self.assertEqual(len(allowed),1)
        self.assertEqual(allowed[0]['cos_sign'],-1)
        self.assertLess(allowed[0]['theta_lower_degrees'],allowed[0]['theta_upper_degrees'])
        self.assertEqual({s for s,n in allowed[0]['per_STA_candidate_count_any_angle'].items() if n==0},
                         {'STA01','STA02','STA05','STA06','STA07','STA10'})
        rows=csv_rows(REPORT/'MV_RELOCATION_ALLANGLE_CANDIDATE_INTERVALS.csv')
        self.assertEqual(len(rows),12*606)
        self.assertEqual(len({r['candidate_bus'] for r in rows}),606)
        for site in ('STA01','STA02','STA05','STA06','STA07','STA10'):
            subset=[r for r in rows if r['STA']==site]
            self.assertEqual(len(subset),606)
            self.assertTrue(all(r['fixed_AIDC_compatible_at_any_allowed_rotation']=='False' for r in subset))

    def test_ratings_PQ_circle_and_vehicle_not_upscaled(self):
        rows=csv_rows(REPORT/'MESS_PORT_TRANSFORMER_RATINGS.csv')
        self.assertEqual([r['interface'] for r in rows],['L0','M1','M2','M3'])
        for r in rows:
            self.assertEqual(float(r['vehicle_Pmax_kw']),450)
            self.assertEqual(float(r['vehicle_Smax_kva']),600)
            self.assertLessEqual(math.hypot(float(r['port_P_import_export_limit_kw']),
                                           float(r['abs_Q_at_Pmax_kvar'])),float(r['port_S_limit_kva'])+1e-8)
            if r['interface']!='L0':
                self.assertEqual(int(r['same_proxy_eligible_ports']),0)
                self.assertEqual(int(r['separate_relocation_candidate_ports']),0)

    def test_three_phase_component_PQ_and_voltage_dependent_current(self):
        receipt=read(REPORT/'MV_COMPONENT_REGRESSION.json')
        self.assertEqual(receipt['case_count'],12)
        self.assertTrue(receipt['single_phase_fake_ABC_rejected'])
        self.assertFalse(receipt['IEEE8500_case_MV_eligibility_PASS'])
        self.assertTrue(all(r['three_phase_total_readback_error']<1e-5 for r in receipt['cases']))
        # Rated apparent power alone is insufficient below nominal voltage.
        self.assertFalse(receipt['all_unit_endpoints_port_current_PASS'])
        self.assertTrue(any(not r['all_port_phase_current_limits_pass'] for r in receipt['cases']))

    def test_no_unqualified_hardware_Production_PASS(self):
        design=read(REPORT/'ENGINEERING_MV_DESIGN.json')
        self.assertEqual(design['status'],'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED')
        self.assertFalse(design['final_production_configuration_frozen'])
        self.assertEqual(design['new_dedicated_transformer_count_relocation_candidate'],0)
        self.assertTrue(design['safety_gates']['short_circuit'].startswith('UNVERIFIED'))

    def test_joint_reselection_is_a_separate_24_MV_geometry_witness(self):
        result=read(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT.json')
        self.assertTrue(result['geometric_feasible'])
        self.assertTrue(result['AIDC_fixed_bus_constraint_released'])
        self.assertEqual(result['distinct_buses'],24)
        self.assertEqual(result['pair_passes'],276)
        self.assertEqual(result['axis_passes'],552)
        self.assertFalse(result['electrical_and_equipment_dispatch_96slot_PASS'])
        rows=csv_rows(REPORT/'JOINT_MV_HOST_SOURCE_AUDIT.csv')
        self.assertEqual(len(rows),24)
        self.assertTrue(all(r['fresh_original_nodes']=='1,2,3' for r in rows))
        self.assertTrue(all(abs(float(r['fresh_kv_base_LL'])-12.47)<1e-10 for r in rows))
        proof=read(REPORT/'JOINT_MV_TRAFFIC_ETA_AUDIT.json')
        self.assertEqual(proof['traffic_files_before_sha256'],proof['traffic_files_after_sha256'])
        self.assertFalse(proof['physical_installed_site_PASS'])


if __name__=='__main__':unittest.main()
