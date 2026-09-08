"""Boundary and fail-closed coverage regressions for the review validator."""
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from validate_bundle import DAYS, day_pass, select, validate


class ScreenEvidenceTests(unittest.TestCase):
    def test_frozen_bundle(self):
        self.assertEqual(validate(Path(__file__).parent)["selected_alpha_BG"], 1.15)

    def test_hash_drift_is_rejected(self):
        original = Path.read_bytes
        def changed(path):
            data = original(path)
            return data + b" " if path.name == "DAILY_RESULTS.json" else data
        with patch.object(Path, "read_bytes", changed):
            with self.assertRaisesRegex(ValueError, "file hash mismatch"):
                validate(Path(__file__).parent)

    def test_voltage_inclusive_and_thermal_strict(self):
        slots = [[1, .95, 1.05, .9, .9, .9] for _ in range(96)]
        self.assertTrue(day_pass(slots))
        for col in (3, 4, 5):
            trial = [s[:] for s in slots]
            trial[0][col] = 1.0
            self.assertFalse(day_pass(trial))
        for col, value in ((1, math.nextafter(.95, -math.inf)), (2, math.nextafter(1.05, math.inf))):
            trial = [s[:] for s in slots]
            trial[0][col] = value
            self.assertFalse(day_pass(trial))
        slots[0][0] = 0
        self.assertFalse(day_pass(slots))

    def test_coverage_fails_closed(self):
        rows = [{"day": d, "alpha_BG": a, "PASS": True} for a in (1.2, 1.15, 1.1) for d in DAYS]
        with self.assertRaises(ValueError):
            select(rows[:-1], (1.2, 1.15, 1.1))
        with self.assertRaises(ValueError):
            select(rows + [rows[0]], (1.2, 1.15, 1.1))
        with self.assertRaises(ValueError):
            day_pass([[1, 1, 1, .5, .5, .5]] * 95)

    def test_largest_eligible_and_no_fallback_outside_candidates(self):
        rows = [{"day": d, "alpha_BG": a, "PASS": a != 1.2} for a in (1.2, 1.15, 1.1) for d in DAYS]
        self.assertEqual(select(rows, (1.1, 1.2, 1.15)), 1.15)
        for row in rows:
            row["PASS"] = False
        self.assertIsNone(select(rows, (1.2, 1.15, 1.1)))


if __name__ == "__main__":
    unittest.main()
