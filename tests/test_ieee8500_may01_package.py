"""Reject realistic publication errors even if a CSV hash is refreshed."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'verify_results', ROOT/'tools/ieee8500_may01/verify_results.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PACKAGE = ROOT/'science/ieee8500_may01_mess6_20260914/paper_csv'


class PackageIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name)/'package'
        shutil.copytree(PACKAGE, self.package)

    def mutate(self, filename, change, refresh_hash=True):
        path = self.package/filename
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        if refresh_hash:
            manifest_path = self.package/'MANIFEST.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['outputs'][filename]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    def test_committed_snapshot(self):
        self.assertEqual(MODULE.verify(self.package)['status'], 'PASS')

    def test_modified_cell_without_updated_hash(self):
        self.mutate('POLICY_RESULT_SUMMARY.csv', lambda rows: rows[3].update(planning_rho_max='0.1'), False)
        with self.assertRaisesRegex(ValueError, 'Hash mismatch'):
            MODULE.verify(self.package)

    def test_b3_own_peak_cannot_replace_same_time(self):
        self.mutate('HEATMAP_B0_B3_SAME_TIME.csv', lambda rows: rows[0].update(time='2025-05-01T18:30:00'))
        with self.assertRaisesRegex(ValueError, 'Mixed heatmap timestamps'):
            MODULE.verify(self.package)

    def test_ac_pass_cannot_hide_energy_floor_failure(self):
        self.mutate('B3_OPERATING_ENERGY_EXCEPTION.csv', lambda rows: rows[0].update(operating_floor_feasible='true'))
        with self.assertRaisesRegex(ValueError, 'Energy exception hidden'):
            MODULE.verify(self.package)

    def test_component_sum_cannot_become_end_to_end_runtime(self):
        self.mutate('RUNTIME_TERMINATION.csv', lambda rows: rows[3].update(runtime_s=rows[3]['recorded_component_sum_s']))
        with self.assertRaisesRegex(ValueError, 'Invented end-to-end runtime'):
            MODULE.verify(self.package)


if __name__ == '__main__':
    unittest.main()
