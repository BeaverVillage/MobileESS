from __future__ import annotations

import unittest

from pfr.workload_uncertainty import WorkloadResidual, calibrate_daily_joint_workload


class WorkloadUncertaintyTests(unittest.TestCase):
    def test_daily_joint_calibration_and_new_spatial_projection(self):
        rows = (
            WorkloadResidual("2024-01-01", 120.0, 100.0, 200.0),
            WorkloadResidual("2024-01-01", 140.0, 100.0, 200.0),
            WorkloadResidual("2024-01-02", 110.0, 100.0, 200.0),
        )
        result = calibrate_daily_joint_workload(
            rows,
            target_coverage=0.5,
            spatial_weights={"IDC01": 0.25, "IDC02": 0.75},
            incremental_it_kw_per_gpu={"IDC01": 0.5, "IDC02": 0.5},
        )
        self.assertEqual(result.day_block_count, 2)
        self.assertEqual(result.global_gpu_reserve, 40.0)
        self.assertEqual(result.idc_gpu_reserve["IDC01"], 10.0)
        self.assertEqual(result.idc_incremental_it_reserve_kw["IDC02"], 15.0)


if __name__ == "__main__":
    unittest.main()
