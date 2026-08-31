from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18r2_aidc_forecast_magnitude_refreeze"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class TestV18R2AIDCForecastMagnitudeRefreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pre = load("V18R2_PRECHANGE_PRESERVATION_MANIFEST.json")
        cls.lineage = load("V18R2_WF_FORECAST_LINEAGE_AUDIT.json")
        cls.target = load("V18R2_FLEXIBLE_ARRIVAL_TARGET_CONTRACT.json")
        cls.distribution = load("V18R2_FLEXIBLE_ARRIVAL_TRAINING_DISTRIBUTION.json")
        cls.q50 = load("V18R2_SLOTWISE_Q50_AGGREGATION_AUDIT.json")
        cls.comparison = load("V18R2_FORECAST_CANDIDATE_COMPARISON.json")
        cls.freeze = load("V18R2_FORECAST_MODEL_SELECTION_FREEZE.json")
        cls.april = load("V18R2_APRIL_DIAGNOSTIC_FORECAST.json")
        cls.tier = load("V18R2_POWER_TIER_FORECAST_VALIDATION.json")
        cls.scheduler = load("V18R2_REFERENCE_SCHEDULER_PREFLIGHT.json")
        cls.facility = load("V18R2_FACILITY_DECOMPOSITION_VALIDATION.json")
        cls.share = load("V18R2_FACILITY_FLEXIBILITY_SHARE.json")
        cls.ready = load("V18R2_READY_FLAGS.json")

    def test_required_21_artifacts_exist(self):
        required = {
            "V18R2_PRECHANGE_PRESERVATION_MANIFEST.json",
            "V18R2_WF_FORECAST_LINEAGE_AUDIT.json",
            "V18R2_FORECAST_MAGNITUDE_ROOT_CAUSE.json",
            "V18R2_FLEXIBLE_ARRIVAL_TARGET_CONTRACT.json",
            "V18R2_FLEXIBLE_ARRIVAL_TRAINING_DISTRIBUTION.json",
            "V18R2_SLOTWISE_Q50_AGGREGATION_AUDIT.json",
            "V18R2_FORECAST_CANDIDATE_COMPARISON.json",
            "V18R2_FORECAST_MODEL_SELECTION_FREEZE.json",
            "V18R2_CAPACITY_NORMALIZED_FORECAST_CONTRACT.json",
            "V18R2_FLEXIBLE_WORKLOAD_MODEL_TRAINING_REPORT.json",
            "V18R2_BLOCKED_CV_RESULTS.json",
            "V18R2_APRIL_DIAGNOSTIC_FORECAST.json",
            "V18R2_FORECAST_MAGNITUDE_WATERFALL.csv",
            "V18R2_POWER_TIER_FORECAST_VALIDATION.json",
            "V18R2_REFERENCE_SCHEDULER_PREFLIGHT.json",
            "V18R2_FACILITY_DECOMPOSITION_VALIDATION.json",
            "V18R2_FACILITY_FLEXIBILITY_SHARE.json",
            "V18R2_FORECAST_REFREEZE_FINAL_REVIEW.json",
            "V18R2_FORECAST_REFREEZE_FINAL_REVIEW.md",
            "V18R2_READY_FLAGS.json",
            "README.md",
        }
        self.assertEqual({path.name for path in OUT.iterdir() if path.is_file()}, required)

    def test_v17_v18_v18r1_byte_preservation(self):
        self.assertEqual(self.pre["counts"], {"v17_candidate": 369, "v17_forensic": 8, "v18": 17, "v18r1": 20})
        for entries in self.pre["preservation_groups"].values():
            for entry in entries:
                self.assertEqual(sha256(ROOT / entry["path"]), entry["sha256"], entry["path"])

    def test_old_1244_lineage_is_arithmetically_reproduced(self):
        reproduction = self.lineage["reproduction"]
        self.assertAlmostEqual(reproduction["Q50_before_beta_7day_GPU_h"] * 0.25, reproduction["after_beta_7day_GPU_h"], places=10)
        self.assertLess(reproduction["arithmetic_reproduction_abs_error_GPU_h"], 1e-9)
        self.assertLess(reproduction["scheduler_identity_abs_error_GPU_h"], 1e-9)

    def test_units_and_mass_identities(self):
        self.assertEqual(self.lineage["factor_audit"]["GPU_vs_node_factor_4"], "NOT_APPLIED_TO_OLD_WORKLOAD; TARGET_ALREADY_GPU_HOUR")
        self.assertEqual(self.lineage["factor_audit"]["slot_hours_0_25"], "NOT_APPLIED_TO_WORKLOAD; USED_ONCE_FOR_CAPACITY_AND_POWER_RATE")
        self.assertLess(self.target["daily_slot_mass_identity_max_abs_GPU_h"], 1e-8)
        self.assertLess(self.target["daily_tier_mass_identity_max_abs_GPU_h"], 1e-8)
        self.assertLess(self.tier["mass_identity_abs_error_GPU_h"], 1e-8)

    def test_q50_aggregation_bias_and_training_only_selection(self):
        self.assertTrue(self.q50["zero_inflated"])
        self.assertEqual(self.q50["H6_verdict"], "CONTRIBUTOR")
        self.assertLess(self.q50["CV_slotwise_Q50_aggregate_mass_ratio"], self.q50["CV_daily_Q50_aggregate_mass_ratio"])
        self.assertEqual(self.comparison["selected"], "CANDIDATE_B")
        self.assertLess(self.comparison["combined"]["CANDIDATE_B"]["daily_WAPE"], self.comparison["combined"]["OLD_V17_WF_LINEAGE_EQUIVALENT"]["daily_WAPE"])
        self.assertEqual(self.comparison["April_reads_for_selection"], 0)

    def test_causality_and_april_freeze_firewall(self):
        counters = self.freeze["causality_counters_at_freeze"]
        self.assertTrue(all(value == 0 for value in counters.values()))
        self.assertEqual(self.april["label"], "OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST")
        self.assertEqual(self.april["April_target_reads_before_model_freeze"], 0)
        self.assertEqual(self.april["April_reads_for_retraining_or_model_selection"], 0)

    def test_nonnegative_quantiles_and_no_posthoc_multiplier(self):
        self.assertEqual(self.comparison["combined"]["CANDIDATE_B"]["negative_prediction_count"], 0)
        self.assertEqual(self.comparison["combined"]["CANDIDATE_B"]["quantile_crossing_count"], 0)
        self.assertEqual(self.freeze["anti_tuning"]["posthoc_workload_multiplier"], 0)
        self.assertEqual(self.freeze["anti_tuning"]["C_MODEL_mutations"], 0)

    def test_reference_scheduler_has_no_shedding(self):
        self.assertTrue(self.scheduler["feasible"])
        self.assertLess(self.scheduler["maximum_work_conservation_error_GPU_h"], 1e-8)
        self.assertEqual(self.scheduler["maximum_deadline_shortfall_GPU_h"], 0)
        self.assertEqual(self.scheduler["terminal_backlog_GPU_h"], 0)
        self.assertEqual(self.scheduler["hidden_shedding_GPU_h"], 0)

    def test_exact_facility_decomposition_and_pue_once(self):
        self.assertEqual(self.facility["gate"], "PASS_EXACT_TWO_COMPONENT_DECOMPOSITION")
        self.assertEqual(self.facility["negative_locked_residual_count"], 0)
        self.assertLess(self.facility["maximum_conservation_error_kW"], 1e-9)
        self.assertEqual(self.facility["PUE_application_count"], 1)
        self.assertEqual(self.facility["negative_residual_clipping_calls"], 0)

    def test_anti_tuning_science_firewall_and_ready_flags(self):
        firewalls = self.ready["firewall_counters"]
        self.assertTrue(all(value == 0 for value in firewalls.values()))
        self.assertTrue(self.ready["FORECAST_REFREEZE_READY"])
        self.assertTrue(self.ready["FACILITY_COMPOSITION_READY"])
        self.assertFalse(self.ready["NEW_LOCKED_SCIENCE_RUN_READY"])
        self.assertFalse(self.share["literature_calibration"])


if __name__ == "__main__":
    unittest.main()
