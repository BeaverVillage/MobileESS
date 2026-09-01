import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestV18R1AIDCPhysicalCoherenceRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = load("V18R1_PRECHANGE_PRESERVATION_MANIFEST.json")
        cls.schema = load("V18R1_KESTREL_GPU_ACCOUNTING_SCHEMA_AUDIT.json")
        cls.feasibility = load("V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json")
        cls.timeline = load("V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.json")
        cls.native = load("V18R1_KESTREL_NATIVE_FLEXIBILITY_RECOMPUTED.json")
        cls.d1 = load("V18R1_D1_MAIN_CAUSAL_SCOPE_CONTRACT.json")
        cls.oracle = load("V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE.json")
        cls.tier = load("V18R1_FLEX_WORK_POWER_TIER_VALIDATION.json")
        cls.power = load("V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION.json")
        cls.facility = load("V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_VALIDATION.json")
        cls.share = load("V18R1_FACILITY_FLEXIBILITY_SHARE.json")
        cls.ready = load("V18R1_READY_FLAGS.json")

    def test_required_artifacts_exist(self):
        required = {
            "V18R1_PRECHANGE_PRESERVATION_MANIFEST.json",
            "V18R1_KESTREL_GPU_ACCOUNTING_SCHEMA_AUDIT.json",
            "V18R1_KESTREL_NODE_POPULATION_FORENSIC.csv",
            "V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.json",
            "V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json",
            "V18R1_KESTREL_PHYSICAL_ALLOCATION_VIOLATIONS.csv",
            "V18R1_KESTREL_NATIVE_FLEXIBILITY_RECOMPUTED.json",
            "V18R1_D1_MAIN_CAUSAL_SCOPE_CONTRACT.json",
            "V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE.json",
            "V18R1_FLEX_WORK_POWER_TIER_CONTRACT.json",
            "V18R1_FLEX_WORK_POWER_TIER_VALIDATION.json",
            "V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION.json",
            "V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_CONTRACT.json",
            "V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_VALIDATION.json",
            "V18R1_FACILITY_FLEXIBILITY_SHARE.json",
            "V18R1_STRUCTURAL_REFREEZE_FINAL_REVIEW.json",
            "V18R1_STRUCTURAL_REFREEZE_FINAL_REVIEW.md",
            "V18R1_READY_FLAGS.json",
            "README.md",
        }
        self.assertEqual({path.name for path in OUT.iterdir() if path.is_file()}, required)

    def test_v17_369_v17_forensic_and_v18_are_byte_preserved(self):
        self.assertEqual(self.pre["v17_preserved_file_count"], 369)
        self.assertEqual(self.pre["v18_preserved_file_count"], 17)
        for group in ("v17_preserved_files", "v17_forensic_files", "v18_preserved_files"):
            for entry in self.pre[group]:
                self.assertEqual(sha256(ROOT / entry["path"]), entry["sha256"], entry["path"])

    def test_accounting_semantics_and_duplicate_guards(self):
        self.assertIsNone(self.schema["series_semantics"]["G_ALLOCATED_OBS"])
        self.assertEqual(self.schema["risk_audit"]["A1_duplicate_rows"]["duplicate_id_rows"], 0)
        self.assertEqual(self.schema["risk_audit"]["A2_job_step_double_count"]["step_like_id_count"], 0)
        array_audit = self.schema["risk_audit"]["A4_array_parent_child_double_count"]
        self.assertEqual(array_audit["executing_parent_plus_child_collision_groups"], 0)
        self.assertEqual(array_audit["nonexecuting_parent_summary_groups"], 31)
        self.assertEqual(self.schema["risk_audit"]["A7_nodelist_parsing_duplicate"]["rows_with_duplicate_node_identity"], 0)
        self.assertEqual(self.schema["risk_audit"]["A10_requested_vs_allocated_confusion"]["verdict"], "CONTRIBUTOR")

    def test_physical_repair_is_explicit_and_unclipped(self):
        self.assertEqual(self.feasibility["raw_static_528_exceed_slot_count"], 902)
        self.assertGreater(self.feasibility["raw_infeasible_event_interval_count"], 0)
        self.assertGreater(len(self.feasibility["raw_conflict_job_ids"]), 0)
        self.assertEqual(
            self.feasibility["raw_exact_feasible_15min_slot_count"]
            + self.feasibility["raw_exact_infeasible_15min_slot_count"],
            self.feasibility["raw_exact_active_15min_slot_count"],
        )
        self.assertEqual(self.feasibility["repaired_true_infeasible_slot_count"], 0)
        self.assertLessEqual(self.feasibility["repaired_max_exact_requested_GPU_on_any_node"], 4)
        self.assertEqual(self.feasibility["repaired_ambiguous_feasibility"]["ambiguous_infeasible_event_interval_count"], 0)
        self.assertEqual(self.feasibility["posthoc_clipping_calls"], 0)
        self.assertEqual(self.feasibility["capacity_promotion_q99_5_u85_calls"], 0)

    def test_node_population_and_timeline_semantics(self):
        self.assertEqual(self.timeline["raw_nodelist_observation"]["distinct_nodes_entire_training"], 156)
        self.assertEqual(self.timeline["raw_nodelist_observation"]["monthly"]["2024-10"]["distinct_H100_nodelist_nodes"], 132)
        self.assertEqual(self.timeline["timeline_status"], "TIME_VARYING_INSTALLED_CAPACITY_NOT_FULLY_IDENTIFIED")
        self.assertTrue(self.timeline["gate_A3"].startswith("PARTIAL"))

    def test_native_share_recomputed_without_facility_claim(self):
        self.assertAlmostEqual(self.native["raw_before_conflict_repair"]["eta_F_GPU_energy"], 0.3677512184653483, places=10)
        self.assertGreater(self.native["repaired_authority"]["eta_F_GPU_energy"], 0)
        self.assertFalse(self.native["facility_power_share_claim"])

    def test_main_d1_is_forecast_only_and_leakage_free(self):
        self.assertEqual(self.d1["MAIN_D1_CONTROL_SCOPE"], "FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY")
        self.assertEqual(self.d1["KNOWN_QUEUE_EXTENSION_STATUS"], "UNAVAILABLE")
        self.assertTrue(all(value == 0 for value in self.d1["causality_counters"].values()))
        self.assertEqual(self.oracle["label"], "NON_CAUSAL_RETROSPECTIVE_DIAGNOSTIC")
        self.assertGreater(self.oracle["totals"]["queued_oracle_GPU_h"], 0)
        for path in (ROOT / "dayahead").glob("*.py"):
            self.assertNotIn("V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE", path.read_text(encoding="utf-8", errors="ignore"))

    def test_tier_work_mass_and_units(self):
        self.assertLessEqual(self.tier["sum_tier_work_minus_total_max_abs_GPU_h"], 1e-7)
        self.assertEqual(self.tier["negative_tier_mass_count"], 0)
        self.assertEqual(self.tier["partial_node_CPU_double_count"], 0)
        self.assertEqual(set(self.tier["forecast_7day_tier_GPU_h"]), {"FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL"})
        self.assertTrue(self.tier["gate_C2"].startswith("PASS"))

    def test_hybrid_power_boundary_revalidated(self):
        self.assertEqual(self.power["gate_C"], "PASS_HYBRID_AUTHORITY")
        self.assertEqual(self.power["raw_authority_reproduction_failures"], [])
        self.assertIsNone(self.power["partialnode"]["CPU_package_increment"])
        self.assertEqual(self.power["arbitrary_multiplier_calls"], 0)

    def test_exact_two_component_facility_decomposition(self):
        self.assertGreaterEqual(self.facility["minimum_locked_residual_IT_kW"], 0)
        self.assertLessEqual(self.facility["maximum_conservation_error_kW"], 1e-9)
        self.assertLessEqual(self.facility["site_sum_max_abs_error_kW"], 1e-9)
        self.assertEqual(self.facility["negative_locked_residual_count"], 0)
        self.assertEqual(self.facility["PUE_application_count"], 1)
        self.assertEqual(self.facility["negative_residual_clipping_calls"], 0)
        self.assertAlmostEqual(self.facility["aggregate_total_minus_day_sum_kWh"], 0.0, places=10)
        self.assertAlmostEqual(self.facility["aggregate_flexible_minus_day_sum_kWh"], 0.0, places=10)

    def test_facility_share_is_not_literature_calibrated(self):
        self.assertGreater(self.share["eta_F_FACILITY_ENERGY"], 0)
        self.assertFalse(self.share["literature_calibration"])

    def test_firewall_and_ready_flags(self):
        self.assertTrue(all(value == 0 for value in self.ready["firewall_counters"].values()))
        self.assertTrue(self.ready["STRUCTURAL_REFREEZE_READY"])
        self.assertFalse(self.ready["NEW_LOCKED_SCIENCE_RUN_READY"])
        self.assertEqual(self.ready["RESULT_CLASSIFICATION"], "B. V18R1_PASS_CAPACITY_TIMELINE_PARTIAL")


if __name__ == "__main__":
    unittest.main()
