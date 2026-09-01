import csv
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
CAND = ROOT / "dayahead" / "artifacts" / "v17_candidate"
MANIFEST = ROOT / "dayahead" / "artifacts" / "melbourne_aidc_april2025_scale" / "MELBOURNE_AIDC_APRIL2025_PRECHANGE_MANIFEST.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestV17FlexibilityFunnelForensic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((OUT / "V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1.json").read_text(encoding="utf-8"))
        cls.cf = json.loads((OUT / "V17_AIDC_FLEXIBILITY_COUNTERFACTUAL_DIAGNOSTIC_V1.json").read_text(encoding="utf-8"))

    def test_preservation_manifest_all_unchanged(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entries = manifest.get("files", manifest.get("preserved_files", []))
        self.assertEqual(len(entries), 369)
        for e in entries:
            p = ROOT / e["path"]
            self.assertEqual(sha256(p), e["sha256"], e["path"])

    def test_three_key_v4r1_files_byte_identical(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entries = {Path(e["path"]).name: e["sha256"] for e in manifest.get("files", manifest.get("preserved_files", []))}
        for name in ["V17_AIDC_POWER_V4R1_FINAL_REVIEW.json", "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json", "V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON.json"]:
            p = next(CAND.rglob(name))
            self.assertEqual(sha256(p), entries[name])

    def test_firewall_counters_zero(self):
        self.assertTrue(all(v == 0 for v in self.data["firewall_counters"].values()))

    def test_coverage_reproduced(self):
        s0, s1 = self.data["funnel"]["S0"], self.data["funnel"]["S1"]
        self.assertAlmostEqual(s1["GPU_hours"] / s0["GPU_hours"], 0.9209445408280355, places=14)
        self.assertAlmostEqual(s1["jobs"] / s0["jobs"], 0.9673635185768813, places=14)

    def test_units_and_pue_once(self):
        s4, s5 = self.data["funnel"]["S4"], self.data["funnel"]["S5"]
        self.assertAlmostEqual(s4["flexible_PCC_kWh"], 1.30 * s4["flexible_IT_kWh"], places=9)
        self.assertAlmostEqual(s5["total_PCC_kWh"], 1.30 * s5["total_IT_kWh"], places=8)
        self.assertAlmostEqual(s5["eta_flex_energy_IT"], s5["eta_flex_energy_PCC"], places=14)

    def test_same_dates_slots_sites_and_sums(self):
        daily = self.data["daily"]
        self.assertEqual(set(daily), {"2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"})
        self.assertAlmostEqual(sum(v["total_IT_kWh"] for v in daily.values()), self.data["funnel"]["S5"]["total_IT_kWh"], places=7)
        self.assertAlmostEqual(sum(v["flexible_IT_kWh"] for v in daily.values()), self.data["funnel"]["S4"]["flexible_IT_kWh"], places=9)
        with (OUT / "V17_AIDC_FACILITY_FLEXIBLE_SHARE_V1.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for pair in ["B1-B0", "B3-B2"]:
            system = next(r for r in rows if r["date"] == "ALL_7_DAYS" and r["aidc_id"] == "SYSTEM" and r["optimized_case"] == pair)
            sites = [r for r in rows if r["date"] == "ALL_7_DAYS" and r["aidc_id"].startswith("AIDC") and r["optimized_case"] == pair]
            self.assertEqual(len(sites), 12)
            self.assertAlmostEqual(sum(float(r["total_it_kwh"]) for r in sites), float(system["total_it_kwh"]), places=7)

    def test_shift_conservation(self):
        for v in self.data["funnel"]["S6"].values():
            self.assertAlmostEqual(v["positive_shifted_pcc_kwh"], v["negative_shifted_pcc_kwh_magnitude"], places=7)
            self.assertAlmostEqual(v["net_shifted_pcc_kwh"], 0.0, places=7)
            self.assertAlmostEqual(v["absolute_shifted_pcc_kwh"], 2 * v["shifted_pcc_kwh"], places=7)

    def test_counterfactuals_non_authority_and_null_not_zero(self):
        self.assertEqual(self.cf["diagnostic_class"], "NON_AUTHORITY_DIAGNOSTIC")
        self.assertIsNone(self.cf["C3_BACKLOG_INCLUSION_UPPER_BOUND"]["flexible_IT_kWh"])
        self.assertIsNone(self.cf["C4_HOST_POWER_INCLUSION"]["flexible_IT_kWh"])

    def test_beta_diagnostic_preserves_share(self):
        self.assertAlmostEqual(self.cf["C0_CURRENT"]["facility_flexible_share"], self.cf["C1_BETA_1_EQUIVALENT_ARITHMETIC"]["facility_flexible_share"], places=15)


if __name__ == "__main__":
    unittest.main()
