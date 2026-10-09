"""Source-conservation regressions for installation versus workload changes."""
import unittest
import numpy as np
import pandas as pd

from ieee8500_v42_high.facility import DATA, OLD, REPORT, load_inputs, load_recomputed_inputs, integer_installation
from ieee8500_v42_aemo.common import read


class FacilityConservationTest(unittest.TestCase):
    def test_source_C0_power_and_service_identity(self):
        for source in ('PLANNING', 'ACTUAL'):
            candidate = load_inputs('C0', source)
            with np.load(OLD / f'derived/{source}_INPUTS.npz', allow_pickle=False) as original:
                for key in ('total_gpu', 'capacities', 'demand_mw', 'pv_mw', 'gross_factor', 'pv_factor'):
                    np.testing.assert_array_equal(candidate[key], original[key])
                for key in ('IT_kw', 'PCC_P_kw', 'PCC_Q_kvar'):
                    np.testing.assert_allclose(candidate[key], original[key], atol=1e-10, rtol=0)

    def test_installation_expansion_preserves_all_served_work(self):
        for source in ('PLANNING', 'ACTUAL'):
            baseline = load_inputs('C0', source)
            for tag in ('C1', 'C2'):
                candidate = load_inputs(tag, source)
                np.testing.assert_array_equal(candidate['total_gpu'], baseline['total_gpu'])
                np.testing.assert_array_equal(candidate['workload_IT_kw'], baseline['workload_IT_kw'])
                np.testing.assert_allclose(candidate['IT_kw'] - baseline['IT_kw'],
                    candidate['installed_idle_IT_kw'] - baseline['installed_idle_IT_kw'], atol=1e-12, rtol=0)
                self.assertTrue((candidate['PCC_P_kw'] >= baseline['PCC_P_kw'] - 1e-10).all())
                if source == 'PLANNING':
                    np.testing.assert_array_equal(candidate['eligible_gpu'], baseline['eligible_gpu'])
                    np.testing.assert_array_equal(candidate['known_gpu'], baseline['known_gpu'])
                    np.testing.assert_array_equal(candidate['cc4_gpu'], baseline['cc4_gpu'])

    def test_exact_1170_GPU_is_not_homogeneous_four_GPU_server_build(self):
        original = load_inputs('C0', 'PLANNING')['capacities']
        self.assertEqual(int(integer_installation(original, 'C1').sum()), 1170)
        self.assertEqual(int(integer_installation(original, 'C2').sum()), 1560)
        audit = pd.read_csv(REPORT / 'AIDC_FACILITY_CAPACITY_AUDIT.csv')
        failures = audit[audit.homogeneous_four_GPU_build_status.eq('FAIL_EXACT_4GPU_PACKING')]
        self.assertEqual(list(failures.capacity_case), ['C1'])
        self.assertEqual(list(failures.aidc_id), ['AIDC05'])
        self.assertEqual(list(failures.proposed_installed_GPU), [150])
        self.assertTrue((audit.physical_facility_nameplates == 'UNVERIFIED').all())

    def test_capability_masks_cannot_be_claimed_as_dispatch(self):
        receipt = read(REPORT / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json')
        self.assertEqual(receipt['current_B0_vs_Native_site_mismatches'], 1290)
        self.assertEqual(receipt['admitted_B0_outside_original_WINDOW_count'], 1024)
        self.assertEqual(receipt['nonzero_AIDC_full96_control_schedule'], 'FAIL_NOT_CERTIFIED')
        self.assertFalse(receipt['research_WAIT_proxy_is_SLA'])
        self.assertEqual(receipt['controls_with_claimed_certified_reduction_kw'], 0.)
        for tag in ('C0', 'C1', 'C2'):
            array = load_inputs(tag, 'PLANNING')
            self.assertGreater(array['source_mask_P_upper_bound_kw'].max(), 0.)
            self.assertEqual(float(array['certified_reducible_P_kw'].sum()), 0.)

    def test_actual_known_and_postissue_arrivals_exactly_reconstruct_total(self):
        for tag in ('C0', 'C1', 'C2'):
            array = load_inputs(tag, 'ACTUAL')
            np.testing.assert_allclose(array['known_at_issue_gpu'] + array['post_issue_arrival_gpu'],
                                       array['total_gpu'], atol=1e-9, rtol=0)
        receipt = read(REPORT / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json')
        self.assertEqual(receipt['Actual_known_at_issue_UID_count'], 1649)
        self.assertEqual(receipt['Actual_post_issue_arrival_UID_count'], 849)
        self.assertEqual(receipt['Actual_terminal_unadmitted_jobs'], 76)

    def test_capacity_replay_preserves_jobs_while_recomputing_occupancy(self):
        original = pd.read_csv(DATA / 'recomputed/C0_JOB_SERVICE_AUDIT.csv').set_index('job_uid')
        for tag in ('C1', 'C2'):
            changed = pd.read_csv(DATA / f'recomputed/{tag}_JOB_SERVICE_AUDIT.csv').set_index('job_uid')
            self.assertEqual(set(original.index), set(changed.index))
            for field in ('submit_time', 'GPU_gang', 'unchanged_nominal_remaining_seconds',
                          'unchanged_service_slots', 'exact_nominal_required_GPUh', 'runtime_authority'):
                pd.testing.assert_series_equal(original[field], changed[field])
            candidate = load_recomputed_inputs(tag, 'PLANNING')
            self.assertFalse(np.array_equal(candidate['total_gpu'], load_inputs(tag, 'PLANNING')['total_gpu']))
            np.testing.assert_array_equal(candidate['demand_mw'], load_inputs('C0', 'PLANNING')['demand_mw'])
            np.testing.assert_array_equal(candidate['pv_mw'], load_inputs('C0', 'PLANNING')['pv_mw'])

    def test_actual_required_compute_and_release_reservations_are_distinct(self):
        required = None
        for tag in ('C0', 'C1', 'C2'):
            audit = read(DATA / f'recomputed/{tag}_ACTUAL_QUEUE_RECEIPT.json')
            total = audit['immutable_total_full_realized_GPUh']
            if required is None:
                required = total
            self.assertEqual(total, required)
            self.assertAlmostEqual(audit['already_executed_before_issue_GPUh'] + audit['prefix_executed_GPUh']
                + audit['executed_Dday_GPUh'] + audit['required_service_remaining_after96_GPUh'], total, places=7)
            self.assertAlmostEqual(audit['executed_Dday_GPUh'] + audit['release_rounding_reserved_Dday_GPUh'],
                                   audit['physical_occupied_Dday_GPUh'], places=7)
            self.assertGreater(audit['release_rounding_reserved_Dday_GPUh'], 0.)


if __name__ == '__main__':
    unittest.main()
