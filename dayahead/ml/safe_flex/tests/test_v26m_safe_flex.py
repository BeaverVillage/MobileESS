from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.safe_flex.bundle import validate_bundle
from dayahead.ml.safe_flex.conformal_set import calibrate_inner_set
from dayahead.ml.safe_flex.scenario import compose_mass_scenarios
from dayahead.ml.safe_flex.service_set import cumulative_bounds, project_service_set
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


class V26MStructuralTests(unittest.TestCase):
    def test_cutoff_exact_fixed_aest(self) -> None:
        self.assertEqual(cutoff_for_day("2025-03-31").isoformat(), "2025-03-30T18:00:00+10:00")

    def test_cumulative_lower_never_exceeds_release_upper_for_same_mass(self) -> None:
        arrivals = np.zeros((96, 6, 5)); arrivals[0, 0, 0] = 2.0
        lower, upper = cumulative_bounds(arrivals)
        self.assertTrue(np.all(lower <= upper + 1e-12))

    def test_service_projector_mass_and_capacity(self) -> None:
        arrivals = np.zeros((96, 6, 5)); arrivals[0, 0, 4] = 10.0
        result = project_service_set(arrivals, 2.0)
        self.assertEqual(result.status, "FEASIBLE")
        self.assertLess(result.mass_identity_error_GPU_h, 1e-12)
        self.assertLessEqual(result.reference_service_GPU_h.sum(axis=(1, 2)).max(), 2.0)
        self.assertEqual(result.hidden_shedding_GPU_h, 0.0)

    def test_source_infeasible_is_not_clipped(self) -> None:
        arrivals = np.zeros((96, 6, 5)); arrivals[0, 0, 0] = 100.0
        result = project_service_set(arrivals, 1.0)
        self.assertNotEqual(result.status, "FEASIBLE")
        self.assertAlmostEqual(arrivals.sum(), result.reference_service_GPU_h.sum() + result.terminal_backlog_GPU_h.sum())

    def test_scenario_reproducible_nonnegative_and_mass_exact(self) -> None:
        shape = np.full((96, 6, 5), 1 / (96 * 6 * 5))
        a = compose_mass_scenarios(10, 20, shape, 32, 20260901)
        b = compose_mass_scenarios(10, 20, shape, 32, 20260901)
        self.assertTrue(np.array_equal(a, b)); self.assertTrue(np.all(a >= 0))
        self.assertTrue(np.allclose(a.sum(axis=(1,2,3)), a[:,0,0,0] / shape[0,0,0]))

    def test_conformal_directions(self) -> None:
        lower = np.zeros((96, 6, 5)); upper = np.ones_like(lower); scale = np.ones_like(lower)
        calibrated_lower, calibrated_upper = calibrate_inner_set(lower, upper, 0.2, scale)
        self.assertTrue(np.all(calibrated_lower >= lower)); self.assertTrue(np.all(calibrated_upper <= upper))


class V26MArtifactTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads((OUT / name).read_text(encoding="utf-8"))

    def test_state_reconstruction_firewall(self) -> None:
        state = self.load("V26M_STATE_RECONSTRUCTION_CONTRACT.json")
        self.assertEqual(state["future_timestamp_value_reads"], 0); self.assertEqual(state["exact_squeue_claims"], 0)

    def test_capacity_and_power_firewall(self) -> None:
        capacity = self.load("V26M_CAPACITY_NORMALIZATION_CONTRACT.json")
        self.assertEqual(capacity["fixed_528_used_in_training"], 0); self.assertEqual(capacity["facility_MW_scale_calls"], 0)
        power = self.load("V26M_POWER_MAPPING_CONTRACT.json")
        self.assertEqual(power["PUE_calls"], 0); self.assertEqual(power["beta_AIDC_calls"], 0)

    def test_april_freeze_and_no_post_open_fit(self) -> None:
        freeze = OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
        expected = (OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").read_text().strip()
        self.assertEqual(hashlib.sha256(freeze.read_bytes()).hexdigest(), expected)
        april = self.load("V26M_APRIL_POSTFREEZE_DIAGNOSTIC.json")
        self.assertEqual(april["fit_calls_after_open"], 0); self.assertEqual(april["calibration_calls_after_open"], 0); self.assertEqual(april["selection_calls_after_open"], 0)

    def test_oracle_and_acceptance_are_not_silently_promoted(self) -> None:
        gate = self.load("V26M_COMMITTED_STATE_VALUE_GATE.json")
        acceptance = self.load("V26M_ACCEPTANCE_TEST.json")
        self.assertTrue(gate["COMMITTED_STATE_VALUE_READY"])
        self.assertFalse(acceptance["SAFE_FLEX_PROPOSED_MODEL_ACCEPTED"])
        self.assertEqual(acceptance["classification"], "V26M_SAFE_CALIBRATION_FAIL")

    def test_bundle_it_side_and_rejected(self) -> None:
        bundle = self.load("V26M_SAFE_FORECAST_BUNDLE_V5.json")
        validation = validate_bundle(bundle["records"][0])
        self.assertEqual(validation["PUE_decision_fields"], 0); self.assertEqual(validation["facility_scale_decision_fields"], 0)
        self.assertEqual(bundle["bundle_status"], "NOT_ISSUED_FOR_PRODUCTION")

    def test_raw_source_hash_unchanged(self) -> None:
        manifest = self.load("V26M_PRECHANGE_PRESERVATION_MANIFEST.json")
        record = manifest["raw_sources"][0]
        source = Path(record["path"])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(digest, record["sha256"])

    def test_no_grid_science_or_facility_scale(self) -> None:
        manifest = self.load("V26M_PRECHANGE_PRESERVATION_MANIFEST.json")
        counters = manifest["firewall_counters"]
        self.assertEqual(counters["OpenDSS_calls"], 0); self.assertEqual(counters["B0_B3_final_grid_science_calls"], 0)
        self.assertEqual(counters["grid_objective_reads"], 0); self.assertEqual(counters["facility_MW_scale_calls"], 0)

    def test_oof_universe_and_arithmetic(self) -> None:
        raw = pd.read_csv(OUT / "V26M_RAW_ENVELOPE_RESULTS.csv")
        self.assertEqual(raw.groupby("model").size().nunique(), 1); self.assertEqual(raw.groupby("model").size().iloc[0], 151)
        oracle = pd.read_csv(OUT / "V26M_ORACLE_CEILING_RESULTS.csv")
        self.assertTrue(np.allclose(oracle.hidden_shedding_GPU_h, 0.0))


if __name__ == "__main__":
    unittest.main()
