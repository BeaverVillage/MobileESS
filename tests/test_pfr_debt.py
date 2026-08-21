import unittest

from pfr.debt import (
    DebtAblation,
    DebtContractError,
    DebtState,
    EnergyReachability,
    RecoveryStep,
    evaluate_recovery,
    update_dual_debt,
)


REACHABLE = EnergyReachability(10, 9, 8, 7, 6, 5)


class DualDebtTests(unittest.TestCase):
    def test_compute_debt_is_unserved_gpu_hours(self):
        state = update_dual_debt(
            DebtState(), compute_reference_gpu_hours=4, compute_executed_gpu_hours=1.5,
            energy_support_kwh=0, energy_repay_kwh=0, energy_reachability=REACHABLE,
        )
        self.assertEqual(state.compute_debt_gpu_hours, 2.5)

    def test_compute_over_service_clears_but_never_makes_negative_debt(self):
        state = update_dual_debt(
            DebtState(1, 0), compute_reference_gpu_hours=1, compute_executed_gpu_hours=3,
            energy_support_kwh=0, energy_repay_kwh=0, energy_reachability=REACHABLE,
        )
        self.assertEqual(state.compute_debt_gpu_hours, 0)

    def test_energy_repayment_is_limited_by_all_reachability_components(self):
        self.assertEqual(REACHABLE.reachable_kwh, 5)
        with self.assertRaises(DebtContractError):
            update_dual_debt(
                DebtState(0, 10), compute_reference_gpu_hours=0, compute_executed_gpu_hours=0,
                energy_support_kwh=0, energy_repay_kwh=5.1, energy_reachability=REACHABLE,
            )

    def test_energy_debt_update(self):
        state = update_dual_debt(
            DebtState(0, 3), compute_reference_gpu_hours=0, compute_executed_gpu_hours=0,
            energy_support_kwh=2, energy_repay_kwh=4, energy_reachability=REACHABLE,
        )
        self.assertEqual(state.energy_debt_kwh, 1)

    def test_recovery_window_metrics(self):
        steps = (
            RecoveryStep(0, 1, 0, 1, REACHABLE, 110, 0, 0.55),
            RecoveryStep(0, 1, 0, 1, REACHABLE, 105, 0, 0.60),
        )
        metrics = evaluate_recovery(
            initial=DebtState(2, 2), steps=steps, ablation=DebtAblation.A_DEBT1,
            step_minutes=5, baseline_power_kw=100, recovery_peak_limit_kw=115,
            epsilon_compute_gpu_hours=0, epsilon_energy_kwh=0,
        )
        self.assertTrue(metrics.recovery_window_passed)
        self.assertEqual(metrics.debt_clearance_duration_minutes, 10)
        self.assertEqual(metrics.rebound_peak_kw, 10)
        self.assertAlmostEqual(metrics.rebound_energy_area_kwh, 15 / 12)

    def test_peak_limit_is_a_hard_recovery_gate(self):
        metrics = evaluate_recovery(
            initial=DebtState(),
            steps=(RecoveryStep(0, 0, 0, 0, REACHABLE, 121, 0, 0.5),),
            ablation=DebtAblation.A_DEBT0, step_minutes=5, baseline_power_kw=100,
            recovery_peak_limit_kw=120, epsilon_compute_gpu_hours=0, epsilon_energy_kwh=0,
        )
        self.assertFalse(metrics.recovery_window_passed)

    def test_ablation_identity_is_explicit(self):
        self.assertFalse(DebtAblation.A_DEBT0.debt_aware_recovery)
        self.assertTrue(DebtAblation.A_DEBT1.debt_aware_recovery)


if __name__ == "__main__":
    unittest.main()
