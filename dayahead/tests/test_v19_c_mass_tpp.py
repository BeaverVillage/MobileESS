from __future__ import annotations

import hashlib
import json
import math
import unittest
from pathlib import Path

import numpy as np
import torch

from dayahead.ml.c_mass_tpp.data import ROOT, causality_audit
from dayahead.ml.c_mass_tpp.facility_bridge import reference_it_power
from dayahead.ml.c_mass_tpp.model import CMASSTPP, CMASSTPPConfig
from dayahead.ml.c_mass_tpp.power_bridge import PUE, packets_to_power


OUT = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class V19StructuralUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(20260901)
        self.model = CMASSTPP(CMASSTPPConfig(k_max=257))
        self.output = self.model.forward_one(
            torch.randn(32, 9), torch.linspace(0, 167, 32), torch.randn(18), True
        )

    def test_causality_feature_reads_zero(self) -> None:
        audit = causality_audit()
        for key, value in audit.items():
            if key.endswith("feature_reads"):
                self.assertEqual(value, 0, key)

    def test_mean_q50_q90_mass_identity(self) -> None:
        for scenario in ("mean", "q50", "q90"):
            error = abs(
                float(self.output[f"event_mass_{scenario}"].sum())
                - float(self.output[scenario][0])
            )
            self.assertLessEqual(error, 1e-10, scenario)

    def test_zero_mass_day_safe(self) -> None:
        from dayahead.ml.c_mass_tpp.set_decoder import hard_mass_reconciliation

        mass, _ = hard_mass_reconciliation(
            torch.tensor([0.0]), torch.randn(1, 17), torch.randn(1, 17)
        )
        self.assertEqual(float(mass.sum()), 0.0)
        self.assertTrue(torch.all(mass == 0))

    def test_numerics_and_quantiles(self) -> None:
        for key in ("mean", "q50", "q90", "event_mass_mean"):
            value = self.output[key]
            self.assertFalse(bool(torch.isnan(value).any()), key)
            self.assertFalse(bool(torch.isinf(value).any()), key)
            self.assertTrue(bool((value >= 0).all()), key)
        self.assertGreaterEqual(float(self.output["q90"][0]), float(self.output["q50"][0]))

    def test_tier_power_and_pue_once(self) -> None:
        arrival = np.asarray([0.0, 1.0])
        tier = np.zeros((2, 6))
        tier[0, 0] = 1.0
        tier[1, 5] = 1.0
        mass = np.asarray([2.0, 3.0])
        result = packets_to_power(arrival, tier, mass)
        self.assertAlmostEqual(float(np.asarray(result["tier_mass_GPU_h"]).sum()), 5.0, 12)
        self.assertAlmostEqual(result["PCC_energy_kWh"], PUE * result["IT_energy_kWh"], 12)
        self.assertEqual(result["PUE_application_count"], 1)
        self.assertEqual(result["partial_CPU_double_count"], 0)

    def test_facility_zero_flex_residual_nonnegative(self) -> None:
        total, _ = reference_it_power("2025-04-02")
        residual = total - np.zeros_like(total)
        self.assertGreaterEqual(float(residual.min()), 0.0)
        self.assertLessEqual(float(np.max(np.abs(total - residual))), 1e-12)


class V19ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = OUT / "V19_READY_FLAGS.json"
        if not required.is_file():
            raise unittest.SkipTest("full V19 artifacts not generated yet")
        cls.ready = json.loads(required.read_text(encoding="utf-8"))
        cls.reproduction = json.loads(
            (OUT / "V19_EVENT_DATASET_REPRODUCTION.json").read_text(encoding="utf-8")
        )
        cls.april = json.loads(
            (OUT / "V19_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text(encoding="utf-8")
        )

    def test_exact_required_artifact_set(self) -> None:
        expected = {
            "V19_PRECHANGE_PRESERVATION_MANIFEST.json",
            "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT.json",
            "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT.md",
            "V19_NEAREST_PRIOR_WORK_MATRIX.csv",
            "V19_EVENT_DATASET_CONTRACT.json",
            "V19_EVENT_DATASET_REPRODUCTION.json",
            "V19_EVENT_ENCODER_PRETRAINING_CONTRACT.json",
            "V19_EVENT_ENCODER_PRETRAINING_REPORT.json",
            "V19_C_MASS_TPP_ARCHITECTURE_CONTRACT.json",
            "V19_BLOCKED_CV_SPLIT_CONTRACT.json",
            "V19_BASELINE_IMPLEMENTATION_AUDIT.json",
            "V19_BASELINE_BLOCKED_CV_RESULTS.csv",
            "V19_C_MASS_TPP_BLOCKED_CV_RESULTS.csv",
            "V19_MODEL_COMPARISON.json",
            "V19_PROPOSED_MODEL_ACCEPTANCE_TEST.json",
            "V19_ABLATION_RESULTS.csv",
            "V19_MODEL_SELECTION_PRE_APRIL_FREEZE.json",
            "V19_APRIL_POSTFREEZE_DIAGNOSTIC.json",
            "V19_EVENT_FORECAST_DIAGNOSTIC.csv",
            "V19_POWER_FORECAST_DIAGNOSTIC.csv",
            "V19_REFERENCE_SCHEDULER_PREFLIGHT.json",
            "V19_FACILITY_DECOMPOSITION_VALIDATION.json",
            "V19_FACILITY_FLEXIBILITY_DIAGNOSTIC.json",
            "V19_FINAL_REVIEW.json",
            "V19_FINAL_REVIEW.md",
            "V19_READY_FLAGS.json",
            "README.md",
        }
        actual = {path.name for path in OUT.iterdir() if path.is_file()}
        self.assertEqual(actual, expected)

    def test_kmax_has_no_truncation(self) -> None:
        self.assertEqual(self.reproduction["K_max_training_observed"], 10012)
        self.assertIn("no target-event truncation", self.reproduction["KMAX_resolution"])

    def test_target_mass_views_preserve_daily_master(self) -> None:
        for key in (
            "daily_master_mass_identity_max_abs_error_GPU_h",
            "daily_slot_mass_identity_max_abs_error_GPU_h",
            "daily_tier_mass_identity_max_abs_error_GPU_h",
        ):
            self.assertLessEqual(self.reproduction[key], 1e-8, key)

    def test_cuda_execution_device_only(self) -> None:
        report = json.loads(
            (OUT / "V19_EVENT_ENCODER_PRETRAINING_REPORT.json").read_text(encoding="utf-8")
        )
        correction = report["execution_correction"]
        self.assertEqual(correction["EXECUTION_DEVICE_CHANGE_ONLY"], "CPU_TO_CUDA")
        self.assertEqual(correction["RESULT_BASED_RETUNING"], 0)
        self.assertFalse(correction["final_table_mixes_CPU_and_CUDA_deep_folds"])
        self.assertTrue(report["runs"])
        self.assertTrue(all(run["execution_device"] == "cuda:0" for run in report["runs"]))
        self.assertTrue(all(run["peak_VRAM_bytes"] > 0 for run in report["runs"]))

    def test_april_firewall(self) -> None:
        self.assertEqual(self.april["April_target_reads_before_freeze"], 0)
        self.assertEqual(self.april["April_reads_for_model_selection_or_tuning"], 0)

    def test_science_and_anti_tuning_firewall(self) -> None:
        counters = self.ready["firewall_counters"]
        for key in (
            "literature_target_reads",
            "grid_objective_reads_for_model_selection",
            "result_based_workload_multiplier_calls",
            "beta_AIDC_scaling_calls",
            "facility_scale_calls_on_GPU_h",
            "B0_B1_B2_B3_science_calls",
            "OpenDSS_calls",
        ):
            self.assertEqual(counters[key], 0, key)

    def test_prior_artifacts_preserved(self) -> None:
        manifest = json.loads(
            (OUT / "V19_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8")
        )
        for records in manifest["preservation_groups"].values():
            for record in records:
                self.assertEqual(sha256(ROOT / record["path"]), record["sha256"])

    def test_facility_scale_is_not_final_authority(self) -> None:
        self.assertIsNone(self.ready["FINAL_FACILITY_FLEXIBILITY_SHARE"])
        self.assertIn("PROVISIONAL", self.ready["FACILITY_FORECAST_INTEGRATION_AUTHORITY"])


if __name__ == "__main__":
    unittest.main()
