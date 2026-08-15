import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from period_selection import (
    AXIS_STEPS_2024,
    AXIS_STEPS_2025,
    BURN_IN_STEPS,
    FORBIDDEN_FEATURE_TOKENS,
    STEPS_PER_WEEK,
)
from period_selection.candidate_weeks import generate_candidate_weeks
from period_selection.constrained_kmedoids import (
    build_distance_context,
    select_representative_weeks,
)
from period_selection.feature_builder import (
    FEATURE_COLUMNS,
    assert_raw_gate,
    fixed_aest_axis,
    fixed_aest_axis_2025,
    validate_feature_table,
)
from period_selection.freeze_manifest import verify_checksums, write_checksums
from period_selection.stress_periods import select_stress_periods


def synthetic_features() -> pd.DataFrame:
    axis = fixed_aest_axis_2025()
    t = np.arange(AXIS_STEPS_2025, dtype=float)
    day = np.sin(2 * np.pi * t / 288.0)
    year = np.sin(2 * np.pi * t / AXIS_STEPS_2025)
    data = {"timestamp_aest": axis}
    for index, name in enumerate(FEATURE_COLUMNS, start=1):
        data[name] = index + day * (0.1 + index / 100.0) + year * (0.2 + index / 100.0)
    return pd.DataFrame(data)[["timestamp_aest", *FEATURE_COLUMNS]]


class RepresentativePeriodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = synthetic_features()
        cls.config = json.loads(
            Path("period_selection/config/rep_week_config.example.json").read_text(encoding="utf-8")
        )
        cls.candidates = generate_candidate_weeks(cls.features)
        cls.ordered, cls.context = build_distance_context(cls.features, cls.candidates, cls.config)

    def test_exact_fixed_aest_axis_no_dst(self):
        axis = fixed_aest_axis_2025()
        self.assertEqual(len(axis), AXIS_STEPS_2025)
        self.assertFalse(axis.has_duplicates)
        self.assertEqual(axis[0].isoformat(), "2025-01-01T00:00:00+10:00")
        self.assertEqual(axis[-1].isoformat(), "2025-12-31T23:55:00+10:00")
        self.assertEqual({x.utcoffset().total_seconds() for x in axis[::288]}, {36_000.0})
        self.assertTrue((np.diff(axis.as_unit("ns").asi8) == 5 * 60 * 1_000_000_000).all())
        validate_feature_table(self.features)

    def test_2024_leap_year_fixed_axis(self):
        axis = fixed_aest_axis(2024)
        self.assertEqual(len(axis), AXIS_STEPS_2024)
        self.assertEqual(axis[0].isoformat(), "2024-01-01T00:00:00+10:00")
        self.assertEqual(axis[-1].isoformat(), "2024-12-31T23:55:00+10:00")
        self.assertEqual({x.utcoffset().total_seconds() for x in axis[::288]}, {36_000.0})

    def test_candidate_week_and_burn_in_lengths(self):
        self.assertTrue((self.candidates["week_steps"] == STEPS_PER_WEEK).all())
        self.assertTrue((self.candidates["burn_in_steps"] == BURN_IN_STEPS).all())
        self.assertTrue(
            ((self.candidates["end_index_exclusive"] - self.candidates["start_index"]) == STEPS_PER_WEEK).all()
        )
        self.assertTrue(
            ((self.candidates["start_index"] - self.candidates["burn_in_start_index"]) == BURN_IN_STEPS).all()
        )

    def test_seasonal_quotas_for_all_k(self):
        for k, quota in ((4, 1), (8, 2), (12, 3)):
            result = select_representative_weeks(self.ordered, self.context, k, self.config)
            self.assertEqual(len(result), k)
            self.assertEqual(result.groupby("season").size().to_dict(), {
                "summer": quota, "autumn": quota, "winter": quota, "spring": quota,
            })
            self.assertAlmostEqual(result["cluster_weight"].sum(), 1.0)

    def test_deterministic_rerun_identity(self):
        first = select_representative_weeks(self.ordered, self.context, 8, self.config)
        second = select_representative_weeks(self.ordered, self.context, 8, self.config)
        pd.testing.assert_frame_equal(first, second, check_exact=True)

    def test_input_order_invariance(self):
        shuffled = self.candidates.sample(frac=1.0, random_state=71).reset_index(drop=True)
        ordered, context = build_distance_context(self.features, shuffled, self.config)
        expected = select_representative_weeks(self.ordered, self.context, 12, self.config)
        actual = select_representative_weeks(ordered, context, 12, self.config)
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)

    def test_no_controller_or_e5c_features(self):
        lowered = " ".join(FEATURE_COLUMNS).lower()
        self.assertFalse(any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS))
        self.assertNotIn("selected_route", lowered)
        self.assertNotIn("realized", lowered)

    def test_fail_closed_missing_raw_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                assert_raw_gate(
                    root / "missing-raw-audit.json",
                    root / "missing-pv-audit.json",
                    root,
                )

    def test_2025_distance_uses_locked_2024_scales(self):
        calibration = self.features.copy()
        application = self.features.copy()
        application[FEATURE_COLUMNS] = application[FEATURE_COLUMNS] * 3.0 + 7.0
        candidates = generate_candidate_weeks(application)
        _, locked = build_distance_context(calibration, self.candidates, self.config)
        _, applied = build_distance_context(application, candidates, self.config, locked_2024_context=locked)
        self.assertEqual(applied.centers, locked.centers)
        self.assertEqual(applied.scales, locked.scales)
        self.assertEqual(applied.weekly_summary_centers, locked.weekly_summary_centers)

    def test_checksum_verification_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.txt"
            artifact.write_text("immutable\n", encoding="utf-8")
            checksum = root / "CHECKSUMS.sha256"
            write_checksums([artifact], checksum)
            self.assertTrue(verify_checksums(checksum))
            artifact.write_text("tampered\n", encoding="utf-8")
            self.assertFalse(verify_checksums(checksum))

    def test_stress_periods_are_48h_nonoverlapping_and_unweighted(self):
        result = select_stress_periods(self.features)
        self.assertEqual(len(result), 4)
        self.assertTrue((result["steps"] == BURN_IN_STEPS).all())
        self.assertTrue((result["annual_weight"] == 0.0).all())
        intervals = sorted(zip(result.start_index, result.end_index_exclusive))
        self.assertTrue(all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])))

    def test_versioned_paper_result_matches_selected_periods(self):
        result = json.loads(
            Path("science/REPRESENTATIVE_PERIOD_RESULT_20260815.json").read_text(encoding="utf-8")
        )
        self.assertEqual(self.config["status"], "FROZEN_PRE_CONTROLLER_EXOGENOUS_ONLY")
        selected = pd.read_csv("period_selection/output/REP_WEEK_SELECTION_2025_K12.csv")
        stress = pd.read_csv("period_selection/output/STRESS_PERIOD_CANDIDATES_2025.csv")
        self.assertEqual(result["status"], "FROZEN_PRE_CONTROLLER_EXOGENOUS_ONLY")
        self.assertFalse(result["information_boundary"]["controller_outputs_used"])
        self.assertEqual(
            selected["candidate_id"].tolist(),
            result["application_result_2025"]["selected_candidate_ids"],
        )
        self.assertEqual(selected.groupby("season").size().to_dict(), {
            "summer": 3, "autumn": 3, "winter": 3, "spring": 3,
        })
        self.assertAlmostEqual(selected["cluster_weight"].sum(), 1.0)
        self.assertTrue(
            ((selected["start_index"] - selected["burn_in_start_index"]) == BURN_IN_STEPS).all()
        )
        self.assertEqual(len(stress), 4)
        self.assertTrue((stress["annual_weight"] == 0.0).all())


if __name__ == "__main__":
    unittest.main()
