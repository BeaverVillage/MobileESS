import math
import unittest

from pfr.slow_fast import (
    FastControl,
    FastLayerLimits,
    FastLayerState,
    GridScreenResult,
    SlowDiscretePlan,
    SlowFastArchitecture,
    SlowFastContractError,
    execute_fast_recourse,
)


def safe_screen(control, state):
    return GridScreenResult(True, "PASS_LINEAR_SCREEN", 0.97, 1.03, 0.82)


class SlowFastTests(unittest.TestCase):
    def setUp(self):
        self.arch = SlowFastArchitecture()
        self.plan = SlowDiscretePlan(
            plan_id="slow-1",
            valid_from_issue=10,
            mess_destination={"m1": "bus2"},
            mess_native_route_rank={"m1": 2},
            job_idc_placement={"j1": "idc1"},
            checkpoint_migration={"j1": None},
            gpu_gang_allocation={"j1": ("g0", "g1")},
            job_start_issue={"j1": 10},
            coarse_charging_kw={"m1": (20.0, 0.0)},
        )
        self.state = FastLayerState(10, {"m1": 0.5}, {"j1": 2.0})
        self.limits = FastLayerLimits(
            step_minutes=5,
            mess_energy_capacity_kwh={"m1": 100.0},
            mess_charge_limit_kw={"m1": 50.0},
            mess_discharge_limit_kw={"m1": 50.0},
            mess_pcs_kva={"m1": 50.0},
            mess_soc_min={"m1": 0.1},
            mess_soc_max={"m1": 0.9},
            job_gpu_count={"j1": 2},
            site_throughput_limit={"idc1": 1.0},
        )
        self.nominal = FastControl(
            mess_charge_kw={"m1": 0.0},
            mess_discharge_kw={"m1": 30.0},
            mess_q_kvar={"m1": 45.0},
            job_compute_rate_fraction={"j1": 0.5},
            site_throughput_fraction={"idc1": 0.8},
        )

    def run_step(self, screen=safe_screen):
        return execute_fast_recourse(
            architecture=self.arch,
            slow_plan=self.plan,
            state=self.state,
            nominal=self.nominal,
            limits=self.limits,
            grid_screen=screen,
        )

    def test_horizon_and_replanning_are_separated(self):
        self.arch.validate()
        with self.assertRaises(SlowFastContractError):
            SlowFastArchitecture(replanning_interval_minutes=5).validate()

    def test_local_repair_is_rejected(self):
        with self.assertRaises(SlowFastContractError):
            SlowFastArchitecture(local_repair_enabled=True).validate()

    def test_fast_step_preserves_slow_binary_fingerprint(self):
        result = self.run_step()
        self.assertTrue(result.binary_state_unchanged)
        self.assertEqual(result.slow_plan_fingerprint_before, result.slow_plan_fingerprint_after)

    def test_compute_work_uses_gpu_fraction_and_step_duration(self):
        result = self.run_step()
        self.assertAlmostEqual(result.next_state.remaining_work_gpu_hours["j1"], 2.0 - 2 * 0.5 / 12)

    def test_soc_update_and_pcs_projection(self):
        result = self.run_step()
        expected = 0.5 - (30.0 / 0.95) / 12.0 / 100.0
        self.assertAlmostEqual(result.next_state.mess_soc["m1"], expected)
        p = result.control.mess_discharge_kw["m1"] - result.control.mess_charge_kw["m1"]
        q = result.control.mess_q_kvar["m1"]
        self.assertLessEqual(math.hypot(p, q), 50.0 + 1e-12)

    def test_grid_screen_rejection_is_fail_closed(self):
        bad = lambda control, state: GridScreenResult(False, "THERMAL_RISK", 0.96, 1.04, 1.02)
        result = self.run_step(bad)
        self.assertFalse(result.accepted_by_screen)
        self.assertEqual(result.status, "FAIL_CLOSED_GRID_SCREEN")

    def test_screen_cannot_claim_pass_outside_hard_limits(self):
        lying = lambda control, state: GridScreenResult(True, "PASS", 0.94, 1.03, 0.8)
        with self.assertRaises(SlowFastContractError):
            self.run_step(lying)


if __name__ == "__main__":
    unittest.main()
