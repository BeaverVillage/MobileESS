from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import torch

from dayahead.ml.racq_flex.allocation import QuarterHourAllocator
from dayahead.ml.racq_flex.bundle import validate_bundle
from dayahead.ml.racq_flex.counts import HurdleCountHead, hurdle_count_nll
from dayahead.ml.racq_flex.payload import BulkTailPayloadHead, bulk_tail_nll
from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_kW
from dayahead.ml.racq_flex.queue_layer import FluidEDF, exact_scheduler
from dayahead.ml.racq_flex.recurrence_audit import recurrence_gate
from dayahead.ml.racq_flex.sampling import coherent_summaries


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class V23MTests(unittest.TestCase):
    def test_preservation_manifest_all_unchanged(self) -> None:
        manifest = load("V23M_PRECHANGE_PRESERVATION_MANIFEST.json")
        failures = []
        for records in manifest["protected_groups"].values():
            for record in records:
                path = ROOT / record["path"]
                if not path.is_file() or sha256(path) != record["sha256"]:
                    failures.append(record["path"])
        self.assertEqual(failures, [])

    def test_prior_artifact_deletion_count_zero(self) -> None:
        manifest = load("V23M_PRECHANGE_PRESERVATION_MANIFEST.json")
        self.assertGreater(manifest["protected_total_files"], 0)

    def test_feature_firewall(self) -> None:
        audit = load("V23M_FEATURE_FIREWALL_AUDIT.json")
        self.assertEqual(audit["status"], "PASS")
        for key in (
            "D_day_actual_feature_reads", "future_start_feature_reads", "future_end_feature_reads",
            "future_queue_wait_feature_reads", "future_completion_feature_reads", "future_job_id_injection_count",
        ):
            self.assertEqual(audit[key], 0)

    def test_cutoff_and_same_day_grouping(self) -> None:
        contract = load("V23M_CAUSAL_CUTOFF_AUGMENTATION_CONTRACT.json")
        self.assertEqual(contract["primary_cutoff_hour_AEST"], 18)
        self.assertEqual(contract["same_day_cross_fold_leakage_count"], 0)

    def test_recurrence_gate_failed_without_override(self) -> None:
        audit = load("V23M_RECURRENCE_SIGNAL_AUDIT.json")
        lift = load("V23M_RECURRENCE_PREDICTIVE_LIFT.json")
        decision = recurrence_gate(
            audit["median_fold_recurring_GPU_h_share"],
            lift["median_fold_relative_improvement"],
            tuple(lift["seven_day_block_bootstrap"]["CI95"]),
            load("V23M_ACCOUNT_HASH_STABILITY_AUDIT.json")["status"] == "PASS",
        )
        self.assertFalse(decision)
        self.assertFalse(audit["RACQ_RECURRENCE_GATE_PASS"])

    def test_count_distribution_finite(self) -> None:
        state = torch.randn(8, 16)
        parameters = HurdleCountHead(16)(state)
        loss = hurdle_count_nll(torch.arange(8.0).reshape(8, 1).expand(8, 2), parameters)
        self.assertTrue(torch.isfinite(loss))

    def test_payload_distribution_finite_and_shape_bounded(self) -> None:
        parameters = BulkTailPayloadHead(16)(torch.randn(8, 16))
        self.assertTrue(torch.all(parameters["tail_shape"].abs() <= 0.8))
        loss = bulk_tail_nll(torch.rand(8, 2) * 10 + 0.1, parameters, torch.tensor(5.0))
        self.assertTrue(torch.isfinite(loss))

    def test_allocation_exact_mass(self) -> None:
        allocator = QuarterHourAllocator(8)
        state = torch.randn(4, 8)
        hourly = torch.rand(4, 24, 6, 5, dtype=torch.float32)
        slots = allocator(state, hourly)
        self.assertLess(float((slots.sum((1,2,3))-hourly.sum((1,2,3))).abs().max()), 1e-4)

    def test_coherent_quantile_scenarios(self) -> None:
        samples = torch.rand(128, 96, 6, 5, dtype=torch.float64)
        summary = coherent_summaries(samples)
        self.assertAlmostEqual(float(summary["mean_tensor_GPU_h"].sum()), float(summary["mean_total_GPU_h"]), places=9)
        self.assertAlmostEqual(float(summary["Q50_CONDITIONED_COHERENT_SCENARIO_GPU_h"].sum()), float(summary["Q50_total_GPU_h"]), places=9)
        self.assertAlmostEqual(float(summary["Q90_CONDITIONED_COHERENT_SCENARIO_GPU_h"].sum()), float(summary["Q90_total_GPU_h"]), places=9)

    def test_queue_work_conservation_and_capacity(self) -> None:
        arrivals = torch.zeros(2, 96, 6, 5)
        arrivals[:, 0, :, :] = 10
        result = FluidEDF()(arrivals)
        self.assertLess(float(result["work_conservation_error_GPU_h"].max()), 1e-5)
        self.assertLessEqual(float(result["service_GPU_h"].sum((2,3)).max()), 132.0 + 1e-5)
        exact = exact_scheduler(arrivals[0].numpy())
        self.assertLessEqual(exact["work_conservation_abs_error_GPU_h"], 1e-8)
        self.assertEqual(exact["hidden_shedding_GPU_h"], 0.0)

    def test_power_nonnegative_and_IT_boundary(self) -> None:
        power = service_to_IT_power_kW(torch.rand(2, 96, 6, 5))
        self.assertTrue(torch.all(power >= 0))
        audit = load("V23M_POWER_BRIDGE_PREFLIGHT.json")
        self.assertEqual(audit["power_boundary"], "IT_SIDE")
        self.assertFalse(audit["PUE_in_ML_loss"])

    def test_benchmark_reproduction(self) -> None:
        self.assertEqual(load("V23M_PRIOR_BENCHMARK_REPRODUCTION.json")["status"], "PASS")

    def test_no_result_tuning_or_grid_science(self) -> None:
        policy = load("V23M_TRAINING_POLICY_FREEZE.json")
        self.assertEqual(policy["result_based_retuning"], 0)
        self.assertEqual(policy["grid_objective_reads_for_selection"], 0)
        freeze = load("V23M_MODEL_SELECTION_PRE_APRIL_FREEZE.json")
        self.assertFalse(freeze["grid_science_authorized"])

    def test_April_read_after_freeze_only(self) -> None:
        diagnostic = load("V23M_APRIL_POSTFREEZE_DIAGNOSTIC.json")
        self.assertEqual(diagnostic["April_target_reads_before_freeze"], 0)
        self.assertEqual(diagnostic["April_target_reads_after_freeze"], 1)
        self.assertEqual(diagnostic["April_reads_for_model_selection_or_tuning"], 0)
        self.assertEqual(diagnostic["retraining_after_April_read"], 0)

    def test_forecast_bundle_v2(self) -> None:
        bundle = load("V23M_FORECAST_BUNDLE_V2.json")
        self.assertEqual(validate_bundle(bundle), [])
        self.assertTrue(bundle["mean_and_Q50_distinct"])
        self.assertEqual(bundle["GPU_h_facility_scale_multiplication_calls"], 0)

    def test_scale_firewall_and_envelope_no_clip(self) -> None:
        diagnostic = load("V23M_SCALE_DEPENDENT_DIAGNOSTIC.json")
        self.assertEqual(diagnostic["facility_scale_multiplication_on_GPU_h"], 0)
        self.assertEqual(diagnostic["clipping_calls"], 0)
        self.assertIsNone(diagnostic["FINAL_FACILITY_FLEXIBILITY_SHARE"])

    def test_science_firewall(self) -> None:
        manifest = load("V23M_PRECHANGE_PRESERVATION_MANIFEST.json")
        counters = manifest["firewall_counters_at_start"]
        self.assertEqual(counters["B0_B1_B2_B3_science_calls"], 0)
        self.assertEqual(counters["OpenDSS_calls"], 0)
        self.assertEqual(counters["grid_science_calls"], 0)


if __name__ == "__main__":
    unittest.main()
