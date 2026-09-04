"""Focused preservation, boundary, coverage and arithmetic tests for V22S."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_melbourne_12site_scale"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class V22SAuthorityTests(unittest.TestCase):
    def test_required_artifacts_exist(self):
        required = {
            "V22S_PRECHANGE_PRESERVATION_MANIFEST.json",
            "V22S_12SITE_SOURCE_REGISTRY.json", "V22S_12SITE_CAPACITY_EVIDENCE.csv",
            "V22S_SITE_IDENTITY_AUTHORITY.json", "V22S_SOURCE_CONFLICT_REGISTRY.json",
            "V22S_CAPACITY_BOUNDARY_TAXONOMY.json", "V22S_CAPACITY_VS_OPERATING_LOAD_CONTRACT.json",
            "V22S_SITE_LOW_CENTRAL_HIGH_INTERVALS.csv", "V22S_STRICT_COMMON_BOUNDARY_SETS.json",
            "V22S_HOST_MAPPING_AUTHORITY.json", "V22S_MATCHED_HOST_DENOMINATORS.json",
            "V22S_IEEE123_DENOMINATOR_AUTHORITY.json", "V22S_STRICT_AUTHORITY_SCALE.json",
            "V22S_EQUIVALENT_12SITE_SCALE_CONTRACT.json", "V22S_EQUIVALENT_12SITE_SCALE_RESULTS.json",
            "V22S_SITE_POWER_WEIGHTS.json", "V22S_SITE_GPU_WEIGHT_AUTHORITY.json",
            "V22S_PCC_INTERFACE_ENGINEERING_CONTRACT.json", "V22S_PCC_INTERFACE_RESULTS.csv",
            "V22S_FINAL_SCALE_REVIEW.md", "V22S_FINAL_SCALE_REVIEW.json",
            "V22S_READY_FLAGS.json", "README.md",
        }
        self.assertFalse(required - {p.name for p in OUT.iterdir()})

    def test_preservation_manifest_matches_all_protected_files(self):
        manifest = load("V22S_PRECHANGE_PRESERVATION_MANIFEST.json")
        self.assertGreaterEqual(manifest["protected_file_count"], 599)
        for record in manifest["protected_files"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(record["sha256"], sha256(path), record["path"])

    def test_ml_code_changed_files_zero(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "7cbefc4519abfd97080f55e37fce15dc156210a7", "--", "dayahead/ml"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual("", changed)

    def test_twelve_sites_and_minimum_source_classes(self):
        identity = load("V22S_SITE_IDENTITY_AUTHORITY.json")
        self.assertEqual(12, len(identity["sites"]))
        self.assertEqual({f"AIDC{i:02d}" for i in range(1, 13)}, {s["site_id"] for s in identity["sites"]})
        for sid, audit in identity["source_class_search_audit"].items():
            self.assertGreaterEqual(audit["class_count"], 3, sid)
            self.assertTrue(audit["minimum_three_satisfied"], sid)

    def test_every_numerical_evidence_has_source_and_april_field(self):
        with (OUT / "V22S_12SITE_CAPACITY_EVIDENCE.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertGreater(len(rows), 20)
        for row in rows:
            self.assertTrue(row["reported_value"])
            self.assertTrue(row["source_url"].startswith("http"))
            self.assertTrue(row["April_2025_applicable"])

    def test_boundaries_and_no_silent_conversion(self):
        allowed = set(load("V22S_CAPACITY_BOUNDARY_TAXONOMY.json")["allowed_values"])
        registry = load("V22S_12SITE_SOURCE_REGISTRY.json")
        for source in registry["sources"]:
            self.assertIn(source["reported_boundary"], allowed)
        contract = load("V22S_CAPACITY_VS_OPERATING_LOAD_CONTRACT.json")
        self.assertEqual(0, contract["capacity_equals_load_relabel_count"])
        self.assertEqual(0, contract["unknown_to_zero_count"])
        self.assertEqual([], contract["operating_load_authority_available_sites"])

    def test_future_capacity_not_backcast_and_mid_build_excluded(self):
        review = load("V22S_FINAL_SCALE_REVIEW.json")
        self.assertEqual(0, review["firewall"]["future_capacity_backcast"])
        sets = load("V22S_STRICT_COMMON_BOUNDARY_SETS.json")
        self.assertEqual(42.0, sets["SET_C_OPERATING_OR_BUILT_MW"]["sites"]["AIDC05"])
        self.assertEqual(13.5, sets["SET_C_OPERATING_OR_BUILT_MW"]["sites"]["AIDC06"])

    def test_matched_coverage_and_unique_hosts(self):
        matched = load("V22S_MATCHED_HOST_DENOMINATORS.json")
        self.assertTrue(matched["unique_host_rule"])
        self.assertTrue(matched["coverage_tests"]["numerator_site_set_equals_denominator_site_set"])
        self.assertEqual(0, matched["coverage_tests"]["four_site_twelve_host_mismatch_count"])
        self.assertEqual(0, matched["coverage_tests"]["overlapping_DPTS_aggregate_count"])
        for key, case in matched["sets"].items():
            if case.get("site_subset"):
                self.assertEqual(len(case["site_subset"]), len(set(case["matched_host_subset"])), key)

    def test_ieee_demand_and_capacity_denominators_separate(self):
        ieee = load("V22S_IEEE123_DENOMINATOR_AUTHORITY.json")
        self.assertAlmostEqual(2.3154691360756456, ieee["LOAD_TO_LOAD"]["IEEE123_background_peak_demand_MW"])
        self.assertEqual(5.0, ieee["CAPACITY_TO_CAPACITY"]["IEEE123_substation_transformer_MVA"])
        self.assertEqual(0, ieee["demand_capacity_mixing_count"])

    def test_strict_arithmetic_reproducible(self):
        strict = load("V22S_STRICT_AUTHORITY_SCALE.json")
        self.assertIsNone(strict["STRICT_LOAD_EQUIVALENT_MW"])
        self.assertEqual(4, len(strict["strict_capacity_candidates"]))
        for case in strict["strict_capacity_candidates"]:
            rho = case["numerator_MW"] / case["denominator_MW"]
            self.assertAlmostEqual(rho, case["rho"], places=14)
            for pf_text, value in case["IEEE123_equivalent_active_MW_by_capacity_PF"].items():
                self.assertAlmostEqual(rho * 5.0 * float(pf_text), value, places=14)

    def test_weight_interval_and_numeric_scenario(self):
        weights = load("V22S_SITE_POWER_WEIGHTS.json")
        self.assertIsNone(weights["SITE_CAPACITY_WEIGHT"]["low"])
        self.assertIsNone(weights["SITE_CAPACITY_WEIGHT"]["primary"])
        high = weights["SITE_CAPACITY_WEIGHT"]["high_bound_corner"]
        self.assertEqual(12, len(high))
        self.assertTrue(all(value >= 0 for value in high.values()))
        self.assertAlmostEqual(1.0, math.fsum(high.values()), places=15)
        self.assertEqual(0, weights["null_converted_to_zero_count"])

    def test_pcc_interfaces_exceed_required_design_apparent_power(self):
        with (OUT / "V22S_PCC_INTERFACE_RESULTS.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        numeric = [r for r in rows if r["S_required_MVA"]]
        self.assertTrue(numeric)
        for row in numeric:
            self.assertGreaterEqual(float(row["standard_rating_MVA"]), float(row["S_required_MVA"]))
            self.assertEqual("True", row["rating_exceeds_required"])
            self.assertEqual("", row["REAL_DNSP_INTERFACE_MVA"])

    def test_science_firewall(self):
        firewall = load("V22S_FINAL_SCALE_REVIEW.json")["firewall"]
        for key in [
            "ML_retraining", "forecast_edits", "GPU_h_scale_calls", "B0_calls",
            "B1_calls", "B2_calls", "B3_calls", "OpenDSS_calls", "grid_science_calls",
            "unsupported_MVA_to_MW", "generator_to_IT", "UPS_to_IT",
            "server_count_to_MW", "capacity_to_actual_load", "grid_result_based_tuning",
        ]:
            self.assertEqual(0, firewall[key], key)


if __name__ == "__main__":
    unittest.main()
