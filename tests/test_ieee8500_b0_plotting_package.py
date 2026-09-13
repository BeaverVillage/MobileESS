"""Negative checks for the read-only plotting contract; no scientific execution."""

import json
import unittest

from tools.validate_ieee8500_b0_plotting import (
    DEFAULT_PACKAGE, MANIFEST, load_tables, validate_package, validate_tables,
)


class PlottingPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = load_tables(DEFAULT_PACKAGE)
        cls.manifest = json.loads((DEFAULT_PACKAGE / MANIFEST).read_text(encoding="utf-8"))

    def changed_row(self, table, index, **changes):
        tables = dict(self.tables)
        tables[table] = list(tables[table])
        tables[table][index] = dict(tables[table][index], **changes)
        return tables

    def test_sealed_package(self):
        self.assertEqual(validate_package(DEFAULT_PACKAGE)["status"], "PASS")

    def test_inactive_zero_is_rejected(self):
        index = next(i for i, r in enumerate(self.tables["plotting"]) if r["loading_status"] == "INACTIVE_TIE")
        tables = self.changed_row("plotting", index, rho_line_max="0")
        with self.assertRaisesRegex(ValueError, "Inactive tie"):
            validate_tables(tables, self.manifest)

    def test_missing_phase_is_rejected(self):
        tables = dict(self.tables, phases=self.tables["phases"][1:])
        with self.assertRaisesRegex(ValueError, "Active phase loading coverage"):
            validate_tables(tables, self.manifest)

    def test_wrong_representative_is_rejected(self):
        tables = self.changed_row("lines", 0, rho_line_max="999")
        with self.assertRaisesRegex(ValueError, "Phase-to-LINE maximum"):
            validate_tables(tables, self.manifest)

    def test_interval_end_is_not_critical_start(self):
        tables = self.changed_row("critical", 0, critical_timestamp="2025-05-21T08:00:00+10:00")
        with self.assertRaisesRegex(ValueError, "interval-start"):
            validate_tables(tables, self.manifest)

    def test_b3_values_are_rejected(self):
        tables = dict(self.tables, b3=[{"policy": "B3", "rho_line_max": "0.5"}])
        with self.assertRaisesRegex(ValueError, "B3 template"):
            validate_tables(tables, self.manifest)


if __name__ == "__main__":
    unittest.main()
