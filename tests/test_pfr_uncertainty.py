from __future__ import annotations

import unittest

from pfr.uncertainty import (
    MobilityResidualObservation,
    UncertaintyContractError,
    UncertaintyUniverse,
    empirical_coverage,
    finite_sample_upper_quantile,
    fit_joint_mobility_calibration,
)


class JointMobilityUncertaintyTests(unittest.TestCase):
    def observation(self, block: str, eta_score: float, energy_score: float):
        return MobilityResidualObservation(
            block_id=block,
            eta_actual_seconds=100.0 + eta_score * 10.0,
            eta_predicted_seconds=100.0,
            eta_scale_seconds=10.0,
            energy_actual_kwh=20.0 + energy_score * 2.0,
            energy_predicted_kwh=20.0,
            energy_scale_kwh=2.0,
            source_year=2024,
        )

    def test_joint_score_is_maximum_normalized_residual(self):
        observation = self.observation("2024-01-01|OD001", 1.5, 2.0)
        self.assertAlmostEqual(observation.joint_score, 2.0)

    def test_finite_sample_rank(self):
        quantile, rank = finite_sample_upper_quantile(range(96), alpha=0.05)
        self.assertEqual(rank, 93)
        self.assertEqual(quantile, 92.0)

    def test_calibration_aggregates_within_independent_block(self):
        observations = (
            self.observation("A", 1.0, 0.5),
            self.observation("A", 2.0, 0.5),
            self.observation("B", 0.1, 1.0),
        )
        calibration = fit_joint_mobility_calibration(
            observations, alpha=0.5, source_identities=("ETA", "ENERGY")
        )
        self.assertEqual(calibration.calibration_block_count, 2)
        self.assertEqual(calibration.joint_quantile, 2.0)

    def test_safe_bound_uses_one_joint_quantile(self):
        calibration = fit_joint_mobility_calibration(
            (self.observation("A", 2.0, 1.0),),
            alpha=0.5,
            source_identities=("ETA", "ENERGY"),
        )
        bound = calibration.safe_bound(
            eta_prediction_seconds=100.0,
            eta_scale_seconds=10.0,
            energy_prediction_kwh=20.0,
            energy_scale_kwh=2.0,
        )
        self.assertEqual(bound.eta_safe_seconds, 120.0)
        self.assertEqual(bound.energy_safe_kwh, 24.0)

    def test_2025_labels_are_rejected(self):
        observation = self.observation("bad", 1.0, 1.0)
        with self.assertRaises(UncertaintyContractError):
            MobilityResidualObservation(
                **{**observation.__dict__, "source_year": 2025}
            ).validate()

    def test_empirical_coverage(self):
        self.assertEqual(empirical_coverage((1.0, 2.0, 3.0), quantile=2.0), 2 / 3)

    def test_uncertainty_components_remain_separate(self):
        universe = UncertaintyUniverse(
            mobility={"joint_quantile": 2.0},
            workload={"arrival_burst": 1.0},
            grid={"load_error": 0.1},
        )
        product = universe.as_product_contract()
        self.assertEqual(set(product), {"U_mob", "U_work", "U_grid"})


if __name__ == "__main__":
    unittest.main()
