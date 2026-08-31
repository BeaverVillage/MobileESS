from __future__ import annotations

import hashlib
import json
import math
import unittest
from pathlib import Path

from dayahead.v20_integration import validate_forecast_bundle
from dayahead.v21_integration import select_production_forecast_authority


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v21_pre_science_integration"
V19 = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
V20 = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class V21PreScienceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.selection = read(OUT / "V21_SELECTED_PRODUCTION_FORECAST_AUTHORITY.json")
        cls.bundle_artifact = read(OUT / "V21_SELECTED_FORECAST_BUNDLE.json")
        cls.validation = read(OUT / "V21_SELECTED_FORECAST_BUNDLE_VALIDATION.json")
        cls.scheduler = read(OUT / "V21_SELECTED_FORECAST_SCHEDULER_ADAPTER.json")
        cls.power = read(OUT / "V21_SELECTED_FORECAST_JOB_TO_POWER_BRIDGE.json")
        cls.site = read(OUT / "V21_ENGINEERING_SITE_ALLOCATION.json")
        cls.facility = read(OUT / "V21_PROVISIONAL_FACILITY_CONSERVATION.json")
        cls.preflight = read(OUT / "V21_G1_G17_PRE_SCIENCE_PREFLIGHT.json")
        cls.ready = read(OUT / "V21_READY_FLAGS.json")

    def test_01_production_selection_reproduces_v19(self) -> None:
        actual = select_production_forecast_authority(
            read(V19 / "V19_READY_FLAGS.json"),
            read(V19 / "V19_PROPOSED_MODEL_ACCEPTANCE_TEST.json"),
            read(V19 / "V19_MODEL_COMPARISON.json"),
        )
        self.assertEqual(actual["selected_model_id"], "B3_LIGHTGBM_QUANTILE")
        self.assertEqual(self.selection["selected_model_id"], actual["selected_model_id"])
        self.assertEqual(self.selection["facility_metric_reads"], 0)
        self.assertEqual(self.selection["grid_metric_reads"], 0)

    def test_02_forecast_bundle_schema_and_count(self) -> None:
        self.assertEqual(self.bundle_artifact["schema"], "FORECAST_BUNDLE_V1")
        self.assertEqual(len(self.bundle_artifact["bundles"]), 7)
        for bundle in self.bundle_artifact["bundles"]:
            self.assertEqual(validate_forecast_bundle(bundle)["status"], "PASS")

    def test_03_all_scenario_mass_identities(self) -> None:
        self.assertEqual(self.validation["status"], "PASS")
        self.assertLessEqual(self.validation["maximum_mass_identity_error_GPU_h"], 1e-8)
        self.assertEqual(self.validation["negative_mass_count"], 0)
        for bundle in self.bundle_artifact["bundles"]:
            for daily, matrix in (
                ("daily_mean_GPU_h", "slot_tier_mean_GPU_h"),
                ("daily_Q50_GPU_h", "slot_tier_Q50_GPU_h"),
                ("daily_Q90_GPU_h", "slot_tier_Q90_GPU_h"),
            ):
                total = sum(sum(row) for row in bundle[matrix])
                self.assertLessEqual(abs(total - bundle[daily]), 1e-8)
                self.assertTrue(all(value >= 0 for row in bundle[matrix] for value in row))

    def test_04_causality_and_scale_firewall(self) -> None:
        self.assertEqual(self.bundle_artifact["April_target_reads"], 0)
        self.assertEqual(self.bundle_artifact["observed_outcome_reads"], 0)
        for bundle in self.bundle_artifact["bundles"]:
            certificate = bundle["causality_certificate"]
            self.assertTrue(certificate["passed"])
            self.assertEqual(certificate["April_target_reads"], 0)
            self.assertEqual(bundle["facility_scale_multiplier_count"], 0)
            self.assertEqual(bundle["beta_AIDC_application_count"], 0)

    def test_05_serialized_model_hashes(self) -> None:
        authority = read(OUT / "V21_B3_PRODUCTION_MODEL_AUTHORITY.json")
        self.assertEqual(sha256(ROOT / authority["Q50_model_path"]), authority["Q50_model_SHA256"])
        self.assertEqual(sha256(ROOT / authority["Q90_model_path"]), authority["Q90_model_SHA256"])
        self.assertEqual(authority["April_target_reads"], 0)
        self.assertEqual(authority["result_based_retuning"], 0)

    def test_06_training_only_distribution_profiles(self) -> None:
        adapter = read(OUT / "V21_TRAINING_ONLY_DISTRIBUTION_ADAPTER.json")
        self.assertEqual(adapter["April_target_reads"], 0)
        self.assertTrue(all(abs(value - 1.0) <= 1e-12 for value in adapter["profile_sum_checks"]["slot_tier"]))
        for row in adapter["profile_sum_checks"]["tier_latency"]:
            self.assertTrue(all(abs(value - 1.0) <= 1e-12 for value in row))

    def test_07_scheduler_conservation_deadline_capacity(self) -> None:
        self.assertLessEqual(self.scheduler["maximum_work_conservation_error_GPU_h"], 1e-8)
        self.assertLessEqual(self.scheduler["terminal_backlog_GPU_h"], 1e-8)
        self.assertLessEqual(self.scheduler["maximum_deadline_shortfall_GPU_h"], 1e-8)
        self.assertLessEqual(self.scheduler["maximum_capacity_violation_GPU_h_per_slot"], 1e-8)
        self.assertEqual(self.scheduler["hidden_shedding_GPU_h"], 0.0)

    def test_08_power_boundary_is_lower_bound_without_multiplier(self) -> None:
        self.assertEqual(self.power["partial_authority"], "GPU_BOARD_LOWER_BOUND")
        self.assertIsNone(self.power["partial_CPU_increment_kW"])
        self.assertEqual(self.power["hidden_multiplier_count"], 0)
        self.assertEqual(self.power["GPU_h_direct_to_instantaneous_kW_calls"], 0)

    def test_09_engineering_site_allocation_is_not_final(self) -> None:
        self.assertEqual(self.site["authority_class"], "ENGINEERING_GPU_ALLOCATION_ONLY")
        self.assertFalse(self.site["FINAL_MELBOURNE_SITE_CAPACITY_AUTHORITY"])
        self.assertLessEqual(self.site["maximum_site_system_identity_error_kW"], 1e-8)
        self.assertEqual(self.site["facility_scale_multiplier_count"], 0)
        self.assertEqual(self.site["power_weight_equals_GPU_weight_assumption_count"], 0)

    def test_10_facility_conservation_no_clipping_and_pue_once(self) -> None:
        self.assertLessEqual(self.facility["maximum_facility_conservation_error_kW"], 1e-8)
        self.assertLessEqual(self.facility["maximum_flexible_minus_total_kW"], 1e-8)
        self.assertEqual(self.facility["negative_residual_count"], 0)
        self.assertEqual(self.facility["negative_clipping_calls"], 0)
        self.assertEqual(self.facility["PUE"], 1.30)
        self.assertEqual(self.facility["PUE_application_count"], 1)
        self.assertIsNone(self.facility["FINAL_FACILITY_FLEXIBILITY_SHARE"])

    def test_11_g1_g17_exact_scope_and_fail_closed_blockers(self) -> None:
        self.assertEqual(len(self.preflight["gates"]), 17)
        self.assertFalse(self.preflight["passed"])
        self.assertEqual(
            self.preflight["failed_gates"],
            [
                "G13_PCC_transformer_interface",
                "G15_site_scale_authority",
                "G16_locked_test_authority",
            ],
        )
        self.assertFalse(self.preflight["synthetic_all_pass_fixture_used_for_readiness"])

    def test_12_previous_authority_preservation(self) -> None:
        self.assertEqual(self.preflight["preservation"]["status"], "PASS")
        self.assertEqual(self.preflight["preservation"]["files_checked"], 500)
        self.assertEqual(self.preflight["preservation"]["failures"], [])

    def test_13_scale_boundary_firewalls(self) -> None:
        scale = read(V20 / "V20A_FINAL_SCALE_REVIEW.json")
        firewall = scale["firewall"]
        self.assertFalse(scale["SITE_SCALE_AUTHORITY_READY"])
        self.assertIsNone(scale["final_realworld_numerator_MW"])
        self.assertEqual(firewall["mixed_boundary_silent_aggregation_count"], 0)
        self.assertEqual(firewall["MVA_to_MW_unsupported_conversion_count"], 0)
        self.assertEqual(firewall["unknown_to_zero_count"], 0)

    def test_14_d1_partial_and_locked_test_classifications(self) -> None:
        self.assertEqual(read(V20 / "V20B_D1_STATE_FINAL_REVIEW.json")["classification"], "B3_ONLY_NONCAUSAL_ORACLE_SUPPORTED")
        self.assertEqual(read(V20 / "V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json")["classification"], "C3_GPU_BOARD_LOWER_BOUND_REMAINS_ONLY")
        self.assertEqual(read(V20 / "V20E_LOCKED_TEST_FINAL_REVIEW.json")["classification"], "E3_NO_UNTOUCHED_PERIOD_AVAILABLE")

    def test_15_final_science_firewall(self) -> None:
        self.assertEqual(self.preflight["science_call_namespace"], "FINAL_GRID_SCIENCE_CASES")
        for key in (
            "B0_calls", "B1_calls", "B2_calls", "B3_calls", "OpenDSS_calls", "AC_science_calls"
        ):
            self.assertEqual(self.preflight[key], 0, key)
        self.assertEqual(self.preflight["grid_solver_calls"], 0)
        self.assertEqual(self.preflight["B3_ML_production_fit_calls"], 1)

    def test_16_ready_flags_are_fail_closed(self) -> None:
        self.assertTrue(self.ready["ML_AUTHORITY_READY"])
        self.assertTrue(self.ready["MODEL_AGNOSTIC_INTEGRATION_READY"])
        self.assertFalse(self.ready["SITE_SCALE_AUTHORITY_READY"])
        self.assertFalse(self.ready["LOCKED_TEST_AUTHORITY_READY"])
        self.assertFalse(self.ready["PRE_SCIENCE_PREFLIGHT_READY"])
        self.assertFalse(self.ready["FINAL_GRID_SCIENCE_READY"])
        self.assertFalse(self.ready["FINAL_GRID_SCIENCE_AUTHORIZED"])

    def test_17_artifact_manifest_hashes(self) -> None:
        manifest = read(OUT / "V21_ARTIFACT_SHA256_MANIFEST.json")
        self.assertTrue(manifest["self_hash_excluded"])
        for record in manifest["artifacts"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(sha256(path), record["sha256"], record["path"])


if __name__ == "__main__":
    unittest.main()
