from __future__ import annotations

import unittest

from pfr.factorized_uncertainty import (
    FactorizedUncertaintyError,
    FactorizedUncertaintySet,
    NormalizedResidualObservation,
    fit_component_calibration,
)


def row(family: str, block: str, score: float, year: int = 2024):
    return NormalizedResidualObservation(family, block, score, 0.0, 1.0, year)


class FactorizedUncertaintyTests(unittest.TestCase):
    def test_component_uses_independent_block_maximum(self):
        calibration = fit_component_calibration(
            (row("workload", "A", 1.0), row("workload", "A", 2.0), row("workload", "B", 0.5)),
            family="workload",
            target_coverage=0.5,
            frozen_scale_authority="PREDECLARED_GPU_HEADROOM",
        )
        self.assertEqual(calibration.block_count, 2)
        self.assertEqual(calibration.normalized_quantile, 2.0)

    def test_2025_calibration_is_rejected(self):
        with self.assertRaises(FactorizedUncertaintyError):
            fit_component_calibration(
                (row("grid", "bad", 1.0, 2025),),
                family="grid",
                target_coverage=0.95,
                frozen_scale_authority="PREDECLARED_GRID_SCALE",
            )

    def test_factorized_mapping_keeps_components_separate(self):
        workload = fit_component_calibration(
            (row("workload", "A", 1.0),),
            family="workload",
            target_coverage=0.5,
            frozen_scale_authority="WORK",
        )
        grid = fit_component_calibration(
            (row("grid", "A", 1.0),),
            family="grid",
            target_coverage=0.5,
            frozen_scale_authority="GRID",
        )
        mapping = FactorizedUncertaintySet(2.0, workload, grid).as_mapping()
        self.assertEqual(set(mapping), {"factorization", "U_mob", "U_work", "U_grid"})


if __name__ == "__main__":
    unittest.main()
