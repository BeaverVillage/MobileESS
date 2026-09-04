"""Focused T1--T25 checks for the V22S-R1 arithmetic authority."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"


def read_json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def read_csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class V22SR1AuthorityTests(unittest.TestCase):
    def test_T01_case_name_and_non_census_label(self) -> None:
        data = read_json("V22SR1_SCALING_METHOD_FREEZE.json")
        self.assertEqual(data["case_name"], "MELBOURNE_INFORMED_EQUIVALENT_12SITE_OPERATING_LOAD_CASE")
        self.assertEqual(data["prohibited_interpretation"], "ACTUAL_METERED_MELBOURNE_APRIL_2025_LOAD_CENSUS")

    def test_T02_all_twelve_sites_have_preregistered_values(self) -> None:
        rows = read_csv("V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv")
        self.assertEqual([row["site_id"] for row in rows], [f"AIDC{i:02d}" for i in range(1, 13)])
        self.assertTrue(all(float(row["primary_IT_equivalent_capacity_MW"]) > 0 for row in rows))

    def test_T03_capacity_total_exact(self) -> None:
        rows = read_csv("V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv")
        self.assertAlmostEqual(math.fsum(float(row["primary_IT_equivalent_capacity_MW"]) for row in rows), 202.750769230769, places=9)

    def test_T04_conversion_arithmetic(self) -> None:
        data = read_json("V22SR1_CAPACITY_CONVERSION_AUDIT.json")
        self.assertAlmostEqual(data["AIDC04"]["IT_equivalent_MW"], 2.5 * 0.98 / 1.30, places=14)
        self.assertAlmostEqual(data["AIDC09"]["IT_equivalent_MW"], (4.175 - 1.125) / 1.30, places=14)

    def test_T05_utilisation_authority_exact(self) -> None:
        data = read_json("V22SR1_LOAD_UTILISATION_AUTHORITY.json")
        self.assertEqual(data["primary"]["value"], 0.46)
        self.assertEqual(data["low"]["value"], 0.435)
        self.assertAlmostEqual(data["high"]["value"], 93 / 189.1, places=15)

    def test_T06_shape_source_is_seven_frozen_files(self) -> None:
        data = read_json("V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json")
        self.assertEqual(len(data["source_files"]), 7)
        self.assertEqual(data["slot_count"], 672)
        self.assertTrue(all(len(record["sha256"]) == 64 for record in data["source_files"]))

    def test_T07_shape_factor_reproducible(self) -> None:
        data = read_json("V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json")
        self.assertAlmostEqual(data["k_shape_mean_over_max"], 0.8451687396540487, places=15)

    def test_T08_legacy_absolute_magnitude_discarded(self) -> None:
        data = read_json("V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json")
        self.assertEqual(data["absolute_legacy_magnitude_status"], "DISCARDED_NOT_SCALE_AUTHORITY")
        self.assertEqual(data["debug_results_read_for_scale_selection"], 0)

    def test_T09_profile_means_preserve_site_targets(self) -> None:
        profile = read_csv("V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv")
        capacities = {row["site_id"]: float(row["primary_IT_equivalent_capacity_MW"]) for row in read_csv("V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv")}
        self.assertEqual(len(profile), 672)
        for sid, capacity in capacities.items():
            mean = math.fsum(float(row[f"{sid}_IT_equivalent_MW"]) for row in profile) / len(profile)
            self.assertAlmostEqual(mean, capacity * 0.46, places=11)

    def test_T10_pue_applied_once(self) -> None:
        review = read_json("V22SR1_FINAL_REVIEW.json")
        self.assertAlmostEqual(review["primary_operating_PCC_peak_MW"], review["primary_operating_IT_peak_MW"] * 1.30, places=12)
        self.assertEqual(review["firewall_counters"]["PUE_application_count"], 1)
        self.assertEqual(review["firewall_counters"]["double_PUE_count"], 0)

    def test_T11_dpts_counted_once_without_lvn_tna(self) -> None:
        data = read_json("V22SR1_HOST_DOUBLE_COUNT_AUDIT.json")
        self.assertEqual(data["DPTS_count"], 1)
        self.assertEqual(data["LVN_count"], 0)
        self.assertEqual(data["TNA_count"], 0)

    def test_T12_unique_host_total_exact(self) -> None:
        data = read_json("V22SR1_MATCHED_UNIQUE_HOST_2025_AUTHORITY.json")
        self.assertAlmostEqual(data["nine_non_DPTS_hosts_total_MW"], 351.394, places=12)
        self.assertAlmostEqual(data["DPTS_2025_forecast_MW"], 276.752, places=12)
        self.assertAlmostEqual(data["total_MW"], 628.146, places=12)

    def test_T13_host_coverage_is_exactly_twelve_sites(self) -> None:
        data = read_json("V22SR1_HOST_DOUBLE_COUNT_AUDIT.json")
        self.assertEqual(data["site_coverage"], [f"AIDC{i:02d}" for i in range(1, 13)])
        self.assertTrue(data["coverage_complete_12_of_12"])
        self.assertEqual(data["duplicate_site_count"], 0)

    def test_T14_load_to_load_boundary_match(self) -> None:
        data = read_json("V22SR1_PRIMARY_MELBOURNE_PENETRATION.json")
        self.assertEqual(data["boundary_match"], "LOAD_TO_LOAD_EQUIVALENT")
        self.assertEqual(data["numerator"]["site_coverage"], data["denominator"]["site_coverage"])

    def test_T15_rho_arithmetic(self) -> None:
        data = read_json("V22SR1_PRIMARY_MELBOURNE_PENETRATION.json")
        self.assertAlmostEqual(data["rho"], data["numerator"]["value_MW"] / data["denominator"]["value_MW"], places=15)

    def test_T16_ieee_background_denominator_exact(self) -> None:
        data = read_json("V22SR1_FINAL_IEEE123_AIDC_SCALE.json")
        self.assertAlmostEqual(data["IEEE123_background_peak_MW"], 2.3154691360756456, places=15)

    def test_T17_final_ieee_scale_arithmetic(self) -> None:
        data = read_json("V22SR1_FINAL_IEEE123_AIDC_SCALE.json")
        expected = data["real_equivalent_rho"] * data["IEEE123_background_peak_MW"]
        self.assertAlmostEqual(data["final_aggregate_AIDC_PCC_peak_MW"], expected, places=15)
        self.assertLess(abs(data["final_aggregate_AIDC_PCC_peak_MW"] - 0.529), 0.001)

    def test_T18_site_weights_nonnegative_and_sum_one(self) -> None:
        rows = read_csv("V22SR1_PRIMARY_SITE_WEIGHTS.csv")
        weights = [float(row["capacity_weight"]) for row in rows]
        self.assertTrue(all(weight >= 0 for weight in weights))
        self.assertAlmostEqual(math.fsum(weights), 1.0, places=15)

    def test_T19_site_pcc_sum_equals_system_total(self) -> None:
        rows = read_csv("V22SR1_SITE_PCC_PEAKS.csv")
        total = math.fsum(float(row["IEEE123_equivalent_PCC_peak_MW"]) for row in rows)
        expected = read_json("V22SR1_FINAL_IEEE123_AIDC_SCALE.json")["final_aggregate_AIDC_PCC_peak_MW"]
        self.assertAlmostEqual(total, expected, places=15)

    def test_T20_utilisation_sensitivity_is_monotonic(self) -> None:
        cases = read_json("V22SR1_UTILISATION_SENSITIVITY.json")["cases"]
        values = [case["IEEE123_AIDC_PCC_peak_MW"] for case in cases]
        self.assertLess(values[0], values[1])
        self.assertLess(values[1], values[2])
        self.assertAlmostEqual(values[1], 0.5288087919579649, places=14)

    def test_T21_capacity_envelope_has_open_me5_lower(self) -> None:
        data = read_json("V22SR1_CAPACITY_EVIDENCE_ENVELOPE.json")
        self.assertIsNone(data["site_variants"]["AIDC09"]["low"])
        self.assertEqual(data["site_variants"]["AIDC09"]["lower_bound"], "OPEN_POSITIVE_NOT_NUMERIC")
        self.assertLess(data["extended_joint_engineering_scale_MW"]["low_open_exclusive"], data["extended_joint_engineering_scale_MW"]["primary"])
        self.assertGreater(data["extended_joint_engineering_scale_MW"]["high_inclusive"], data["extended_joint_engineering_scale_MW"]["primary"])

    def test_T22_interface_ratings_exceed_required_design(self) -> None:
        rows = read_csv("V22SR1_PCC_INTERFACE_SIZING.csv")
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertGreaterEqual(float(row["rounded_standard_interface_MVA"]) + 1e-12, float(row["S_required_MVA"]))
            self.assertEqual(row["authority"], "IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE")

    def test_T23_source_reverification_has_all_critical_authorities(self) -> None:
        data = read_json("V22SR1_SOURCE_REVERIFICATION.json")
        ids = {record["source_id"] for record in data["targeted_reverification"]}
        required = {"S_FUJITSU_OFFICIAL_REACCESS", "S_NEXTDC_1H25_REACCESS", "S_CDC_INFRATIL_2025_REACCESS", "S_ME5_EQX_REACCESS", "S_MEL11_DLR_HISTORICAL_2020", "S_STACK_OPEN_REACCESS", "S_DPTS_TCPR_REACCESS", "S_IEEE_UTILISATION_REACCESS"}
        self.assertTrue(required.issubset(ids))
        self.assertEqual(data["downloaded_source_count"], 0)

    def test_T24_science_and_relabelling_firewall_zero(self) -> None:
        review = read_json("V22SR1_FINAL_REVIEW.json")
        self.assertEqual(review["firewall_counters"]["PUE_application_count"], 1)
        self.assertTrue(all(value == 0 for key, value in review["firewall_counters"].items() if key != "PUE_application_count"))
        conversions = read_json("V22SR1_CAPACITY_CONVERSION_AUDIT.json")["counters"]
        self.assertTrue(all(value == 0 for value in conversions.values()))
        ready = read_json("V22SR1_READY_FLAGS.json")
        self.assertTrue(ready["SCALING_FREEZE_READY"])
        self.assertFalse(ready["FINAL_GRID_SCIENCE_AUTHORIZED"])

    def test_T25_all_prechange_protected_hashes_unchanged(self) -> None:
        manifest = read_json("V22SR1_PRECHANGE_MANIFEST.json")
        self.assertGreaterEqual(manifest["protected_file_count"], 500)
        for record in manifest["protected_files"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(sha256(path), record["sha256"], record["path"])


if __name__ == "__main__":
    unittest.main()
