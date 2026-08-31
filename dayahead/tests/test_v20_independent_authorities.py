from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from dayahead.tools.build_v20d_integration_preflight import forecast_fixture, scale_fixture
from dayahead.v20_integration import (
    ContractError, allocate_to_sites, facility_bridge, schedule_jobs_edf,
    select_forecast_model, tier_GPU_h_to_IT_kWh, validate_forecast_bundle,
    validate_scale_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"


class TestV20Integration(unittest.TestCase):
    def test_forecast_mass_identity(self):
        self.assertEqual(validate_forecast_bundle(forecast_fixture())["status"], "PASS")

    def test_negative_mass_fails(self):
        bundle = forecast_fixture(); bundle["slot_tier_mean_GPU_h"][0][0] = -1
        with self.assertRaises(ContractError):
            validate_forecast_bundle(bundle)

    def test_training_only_fallback(self):
        selected = select_forecast_model({"PROPOSED_MODEL_ACCEPTED": False},
            {"accepted_baselines": [{"model_id": "slow", "training_only_daily_WAPE": .5},
                                    {"model_id": "best", "training_only_daily_WAPE": .2}]})
        self.assertEqual(selected["model_id"], "best")
        self.assertEqual(selected["selection_basis"], "TRAINING_ONLY_BLOCKED_CV")

    def test_scheduler_conservation_capacity_deadline(self):
        result = schedule_jobs_edf([{"job_id": "x", "GPU_h": 1, "release_slot": 0,
                                     "deadline_slot": 4, "max_GPU_h_per_slot": .5}], [.5] * 96)
        self.assertEqual(result["terminal_backlog_GPU_h"], 0)
        self.assertEqual(result["work_conservation_error"], 0)
        self.assertEqual(result["max_capacity_violation_GPU_h"], 0)
        self.assertEqual(result["hidden_shedding_GPU_h"], 0)

    def test_power_and_site_identity(self):
        power = tier_GPU_h_to_IT_kWh(forecast_fixture()["slot_tier_mean_GPU_h"])
        self.assertEqual(power["hidden_multiplier_count"], 0)
        alloc = allocate_to_sites(power["slot_IT_kWh"], [1 / 12] * 12, "FIXTURE")
        self.assertLessEqual(alloc["site_system_identity_error"], 1e-8)
        self.assertEqual(alloc["facility_scale_multiplier_count"], 0)

    def test_facility_conservation_and_pue_once(self):
        locked = [[10.] * 96 for _ in range(12)]; flex = [[1.] * 96 for _ in range(12)]
        bridge = facility_bridge(locked, flex, flex)
        self.assertEqual(bridge["P_IT_REF_kW"][0][0], 11.)
        self.assertEqual(bridge["P_PCC_REF_kW"][0][0], 14.3)
        self.assertEqual(bridge["PUE_application_count"], 1)

    def test_null_scale_is_preserved(self):
        result = validate_scale_bundle(scale_fixture(False))
        self.assertFalse(result["final_power_weight_complete"])
        with self.assertRaises(ContractError):
            validate_scale_bundle(scale_fixture(False), require_final=True)


class TestV20Artifacts(unittest.TestCase):
    def load(self, name):
        return json.loads((OUT / name).read_text(encoding="utf-8"))

    def test_scale_firewalls(self):
        p = self.load("V20A_CAPACITY_BOUNDARY_HARMONIZATION.json")
        self.assertEqual(p["mixed_boundary_silent_aggregation_count"], 0)
        self.assertEqual(p["MVA_to_MW_unsupported_conversion_count"], 0)
        self.assertEqual(p["unknown_to_zero_count"], 0)

    def test_D1_and_power_firewalls(self):
        b = self.load("V20B_D1_STATE_FINAL_REVIEW.json")
        c = self.load("V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json")
        self.assertEqual(b["future_actual_feature_injection_count"], 0)
        self.assertEqual(b["classification"], "B3_ONLY_NONCAUSAL_ORACLE_SUPPORTED")
        self.assertEqual(c["firewall"]["arbitrary_host_multiplier"], 0)
        self.assertEqual(c["firewall"]["partial_CPU_double_count"], 0)

    def test_fixture_all_gates(self):
        p = self.load("V20D_FINAL_INTEGRATION_PREFLIGHT_TEST.json")
        self.assertTrue(p["deterministic_fixture"]["passed"])
        self.assertTrue(all(v == "PASS" for v in p["deterministic_fixture"]["gates"].values()))
        self.assertEqual(p["grid_solver_calls"], 0)

    def test_preservation_manifest(self):
        manifest = self.load("V20_PRECHANGE_MANIFEST.json")
        for record in manifest["preserved_files"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_locked_test_not_falsely_sealed(self):
        p = self.load("V20E_LOCKED_TEST_FINAL_REVIEW.json")
        self.assertEqual(p["classification"], "E3_NO_UNTOUCHED_PERIOD_AVAILABLE")
        self.assertFalse(p["sealed"])
        self.assertEqual(p["already_observed_period_falsely_labeled_unseen_count"], 0)
        self.assertFalse((OUT / "V20E_NEW_LOCKED_TEST_PERIOD_FREEZE.json").exists())

    def test_master_firewall_and_ready_logic(self):
        p = self.load("V20_MASTER_AUTHORITY_STATUS.json")
        counters = p["firewall_counters"]
        self.assertEqual(counters["B0_B1_B2_B3_calls"], 0)
        self.assertEqual(counters["OpenDSS_calls"], 0)
        self.assertEqual(counters["grid_science_calls"], 0)
        self.assertTrue(p["ready_flags"]["MODEL_AGNOSTIC_INTEGRATION_READY"])
        self.assertFalse(p["ready_flags"]["PRE_ML_INTEGRATION_READY"])
        self.assertEqual(p["ready_flags"]["FINAL_SCIENCE_READY"], "PENDING_V19_MODEL_AUTHORITY")

    def test_protected_v19_path_not_changed(self):
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "77a86e3ded8087ea0109ccfca631bd2396ecd9fe", "--"],
            cwd=ROOT, text=True).splitlines()
        self.assertFalse(any(name.replace("\\", "/").startswith("dayahead/ml/c_mass_tpp/") for name in changed))


if __name__ == "__main__":
    unittest.main()
