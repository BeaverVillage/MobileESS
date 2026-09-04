"""Focused scientific-firewall and coherence tests for V24M FASER-Flex."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.faser_flex.bundle import validate_forecast_bundle_v3
from dayahead.ml.faser_flex.distribution import mixture_samples
from dayahead.ml.faser_flex.gp_models import nearest_psd_correlation
from dayahead.ml.faser_flex.shape import coherent_tensor


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestV24M(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.target = load("V24M_FACTORIZED_TARGET_CONTRACT.json")
        cls.feature = load("V24M_FEATURE_FIREWALL_AUDIT.json")
        cls.analog = load("V24M_ANALOG_LIBRARY_AUDIT.json")
        cls.acceptance = load("V24M_FASER_ACCEPTANCE_TEST.json")
        cls.freeze = load("V24M_MODEL_SELECTION_PRE_APRIL_FREEZE.json")
        cls.april = load("V24M_APRIL_POSTFREEZE_DIAGNOSTIC.json")
        cls.bundle = load("V24M_FORECAST_BUNDLE_V3.json")
        cls.scale = load("V24M_SCALE_DEPENDENT_DIAGNOSTIC.json")

    def test_factor_identity(self) -> None:
        self.assertLessEqual(self.target["max_identity_error_GPU_h"], 1e-9)

    def test_wallclock_conversion_once(self) -> None:
        self.assertIn("TO_SECONDS_TO_HOURS", self.target["source"]["wallclock_conversion_contract"])

    def test_factor_supports_and_no_clipping(self) -> None:
        frame = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
        self.assertTrue((frame.R_ALL_GPU_h_requested >= 0).all())
        self.assertTrue(frame.PI_F.between(0, 1).all())
        self.assertEqual(self.target["target_clipping_calls"], 0)

    def test_undefined_kappa_not_zero(self) -> None:
        frame = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
        self.assertTrue(frame.loc[~frame.KAPPA_DEFINED.astype(bool), "KAPPA_F"].isna().all())

    def test_zero_flex_convention(self) -> None:
        self.assertEqual(self.target["zero_day_convention"], "PI_F=0,H_F=0,KAPPA_DEFINED=false,KAPPA_F=null")

    def test_feature_future_reads_zero(self) -> None:
        for key, value in self.feature.items():
            if key.endswith("feature_reads"):
                self.assertEqual(value, 0, key)

    def test_past_only_analogs(self) -> None:
        self.assertEqual(self.analog["future_analog_count"], 0)
        self.assertEqual(self.analog["self_neighbor_count"], 0)

    def test_analog_weights(self) -> None:
        provenance = load("V24M_ANALOG_PROVENANCE_OOF.json")["records"]
        for row in provenance:
            weights = np.asarray(row["weights"], float)
            self.assertGreaterEqual(weights.min(), 0)
            self.assertAlmostEqual(float(weights.sum()), 1.0, places=12)

    def test_signature_dimensions(self) -> None:
        audit = load("V24M_SIGNATURE_REPRESENTATION_AUDIT.json")
        self.assertEqual(audit["candidates"]["SIG-A"]["dimension"], 90)
        self.assertEqual(audit["candidates"]["SIG-B"]["dimension"], 819)

    def test_psd_projection(self) -> None:
        matrix, _ = nearest_psd_correlation(np.array([[1, 1.2], [1.2, 1.0]]))
        self.assertGreaterEqual(float(np.linalg.eigvalsh(matrix).min()), -1e-10)

    def test_coherent_tensor(self) -> None:
        tensor = coherent_tensor(12345.6789, np.ones((96, 6, 5)) / (96 * 6 * 5))
        self.assertLessEqual(abs(float(tensor.sum()) - 12345.6789), 1e-9)
        self.assertGreaterEqual(float(tensor.min()), 0)

    def test_joint_sample_identity(self) -> None:
        gp = {"R_ALL": np.ones((2, 4))*10, "PI_F": np.ones((2, 4))*.2, "KAPPA_F": np.ones((2, 4))*.5, "H_F": np.ones((2, 4))}
        mixed = mixture_samples(gp, gp, np.array([0.2, 0.8]), 1)
        self.assertTrue(np.allclose(mixed["H_F"], mixed["R_ALL"]*mixed["PI_F"]*mixed["KAPPA_F"]))

    def test_acceptance_negative_preserved(self) -> None:
        self.assertFalse(self.acceptance["FASER_PROPOSED_MODEL_ACCEPTED"])
        self.assertEqual(self.acceptance["classification"], "V24M_FASER_NOVELTY_PASS_PERFORMANCE_FAIL")

    def test_no_april_before_freeze(self) -> None:
        self.assertEqual(self.freeze["April_target_reads_before_freeze"], 0)
        self.assertTrue(self.april["freeze_verified_before_April_read"])

    def test_no_april_fit_rows(self) -> None:
        self.assertEqual(self.april["April_reads_for_model_selection_or_tuning"], 0)

    def test_bundle(self) -> None:
        self.assertEqual(validate_forecast_bundle_v3(self.bundle), [])

    def test_mean_not_q50(self) -> None:
        self.assertTrue(self.bundle["mean_and_Q50_distinct"])

    def test_no_gpu_h_scale(self) -> None:
        self.assertEqual(self.bundle["GPU_h_facility_scale_multiplication_calls"], 0)
        self.assertEqual(self.scale["GPU_h_scale_calls"], 0)

    def test_scale_is_diagnostic(self) -> None:
        self.assertEqual(self.scale["label"], "SCALE_DEPENDENT_DIAGNOSTIC_ONLY")
        self.assertIsNone(self.scale["FINAL_FACILITY_FLEXIBILITY_SHARE"])

    def test_protected_hashes_unchanged(self) -> None:
        manifest = load("V24M_PRECHANGE_PRESERVATION_MANIFEST.json")
        for records in manifest["protected_groups"].values():
            for record in records:
                self.assertEqual(sha256(ROOT / record["path"]), record["sha256"], record["path"])

    def test_science_firewall(self) -> None:
        final = load("V24M_FINAL_REVIEW.json")
        firewall = final["firewall"]
        self.assertEqual(firewall["GPU_h_scale_calls"], 0)
        self.assertEqual(firewall["B0_B1_B2_B3_final_science_calls"], 0)
        self.assertEqual(firewall["OpenDSS_calls"], 0)
        self.assertEqual(firewall["grid_science_calls"], 0)


if __name__ == "__main__":
    unittest.main()
