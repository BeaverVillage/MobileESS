import unittest
from pathlib import Path
import tempfile
import zipfile

from pfr.power import H100UtilizationPowerCurve, PowerCurveContractError
from pfr.tools.build_h100_utilization_power import build


class H100PowerCurveTests(unittest.TestCase):
    def setUp(self):
        self.curve = H100UtilizationPowerCurve(
            (0.0, 0.5, 1.0), (0.1, 0.4, 0.7), "a" * 64, ("b" * 64,)
        )

    def test_piecewise_linear_interpolation(self):
        self.assertAlmostEqual(self.curve.per_gpu_power_kw(0.25), 0.25)
        self.assertAlmostEqual(self.curve.per_gpu_power_kw(0.75), 0.55)

    def test_gang_power_preserves_all_or_nothing_gpu_count(self):
        self.assertAlmostEqual(self.curve.gang_power_kw(8, 1.0), 5.6)

    def test_curve_must_be_monotone(self):
        with self.assertRaises(PowerCurveContractError):
            H100UtilizationPowerCurve((0.0, 1.0), (0.5, 0.4), "a" * 64, ("b" * 64,)).validate()

    def test_rate_domain_is_closed_unit_interval(self):
        with self.assertRaises(PowerCurveContractError):
            self.curve.per_gpu_power_kw(1.01)

    def test_throughput_claim_is_explicitly_prohibited(self):
        with self.assertRaises(PowerCurveContractError):
            H100UtilizationPowerCurve(
                (0.0, 1.0), (0.1, 0.7), "a" * 64, ("b" * 64,), "MEASURED_TOKEN_THROUGHPUT"
            ).validate()

    def test_duplicate_content_paths_are_not_double_weighted(self):
        fields = [
            *(f"gpu{i}_utilization_percent" for i in range(8)),
            *(f"gpu{i}_power_W" for i in range(8)),
        ]
        rows = [
            ",".join([str(util)] * 8 + [str(100 + util)] * 8)
            for util in (0, 25, 50, 75, 100)
        ]
        payload = (",".join(fields) + "\n" + "\n".join(rows) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("root/H100/a.csv", payload)
                archive.writestr("root/H100/duplicate-a.csv", payload)
            result = build(source)
        self.assertEqual(result["h100_path_member_count"], 2)
        self.assertEqual(result["h100_unique_content_member_count"], 1)
        self.assertEqual(result["duplicate_path_member_count"], 1)
        self.assertEqual(result["measured_row_count"], 5)


if __name__ == "__main__":
    unittest.main()
