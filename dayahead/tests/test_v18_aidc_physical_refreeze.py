import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
OLD_MANIFEST = ROOT / "dayahead" / "artifacts" / "melbourne_aidc_april2025_scale" / "MELBOURNE_AIDC_APRIL2025_PRECHANGE_MANIFEST.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestV18PhysicalRefreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = json.loads((OUT / "V18_KESTREL_NATIVE_FLEXIBILITY_SHARE.json").read_text(encoding="utf-8"))
        cls.d1 = json.loads((OUT / "V18_D1_KNOWN_RUNNING_QUEUE_AUDIT.json").read_text(encoding="utf-8"))
        cls.power = json.loads((OUT / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json").read_text(encoding="utf-8"))
        cls.facility = json.loads((OUT / "V18_AIDC_WHOLE_FACILITY_IT_DECOMPOSITION_VALIDATION.json").read_text(encoding="utf-8"))
        cls.ready = json.loads((OUT / "V18_AIDC_REFREEZE_READY_FOR_SCIENCE_RUN.json").read_text(encoding="utf-8"))

    def test_v17_369_preserved(self):
        old = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(old["preserved_files"]), 369)
        for entry in old["preserved_files"]:
            self.assertEqual(sha(ROOT / entry["path"]), entry["sha256"], entry["path"])

    def test_key_forensic_preserved(self):
        pre = json.loads((OUT / "V18_AIDC_REFREEZE_PRECHANGE_MANIFEST.json").read_text(encoding="utf-8"))
        for entry in pre["key_authorities"]:
            self.assertEqual(sha(ROOT / entry["path"]), entry["sha256"], entry["path"])

    def test_native_reproduces_frozen_magnitudes(self):
        self.assertAlmostEqual(self.native["energies"]["all_executed_H100_GPU_hours"], 1660799.8058333318, places=5)
        self.assertAlmostEqual(self.native["energies"]["semantic_flexible_GPU_hours"], 610761.1522222199, places=5)
        self.assertEqual(self.native["counts"]["semantic_flexible_jobs"], 85671)

    def test_native_capacity_failure_is_exposed_without_clipping(self):
        self.assertGreater(self.native["capacity_violation_slot_count"], 0)
        self.assertEqual(self.native["flex_exceeds_total_slot_count"], 0)
        self.assertEqual(self.native["posthoc_clipping_calls"], 0)
        self.assertGreater(self.native["peak_total_active_GPU"], self.native["C_K_GPU_equivalent"])
        self.assertFalse(self.native["virtual_planning_capacity_selected"])

    def test_d1_categories_fail_closed_no_future_features(self):
        self.assertIsNone(self.d1["known_running_GPU_h"])
        self.assertIsNone(self.d1["known_queued_GPU_h"])
        self.assertEqual(self.d1["status"], "GATE_B_QUEUE_AUTHORITY_MISSING")
        self.assertTrue(all(v == 0 for v in self.d1["causality_counters"].values()))

    def test_power_boundary_and_no_partial_cpu_double_count(self):
        self.assertEqual(self.power["gate_C_status"], "PASS_HYBRID_AUTHORITY")
        self.assertIsNone(self.power["partialnode"]["CPU_package_increment"])
        self.assertEqual(self.power["PUE_application"], "after IT-side component sum exactly once")
        self.assertFalse(self.power["raw_reproduction"]["partial_node_CPU_package_authorized"])
        self.assertEqual(self.power["raw_reproduction"]["authority_reproduction_failures"], [])

    def test_facility_not_falsely_passed_or_clipped(self):
        self.assertEqual(self.facility["gate_D_status"], "NOT_EVALUATED")
        self.assertIsNone(self.facility["conservation_error_max_kW"])
        self.assertEqual(self.facility["negative_residual_clipping_count"], 0)

    def test_anti_tuning_and_no_science_run(self):
        review = json.loads((OUT / "V18_AIDC_REFREEZE_ROOT_CAUSE_CORRECTION_REVIEW.json").read_text(encoding="utf-8"))
        self.assertTrue(all(v == 0 for v in review["firewall_counters"].values()))
        self.assertFalse(self.ready["READY_FOR_NEW_SCIENCE_RUN"])
        self.assertEqual(self.ready["classification"], "E. REFREEZE_FAILED_PHYSICAL_COHERENCE")
        self.assertEqual(self.ready["scientific_solver_calls"], 0)
        self.assertEqual(self.ready["OpenDSS_calls"], 0)


if __name__ == "__main__":
    unittest.main()
