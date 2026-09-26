"""Offline integrity and cross-scope checks; never import production launchers."""
import ast
import csv
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'science/ieee8500_paper_scale_only_final'


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


class FinalCampaignEvidence(unittest.TestCase):
    def test_copied_sources_match_manifest_and_parse(self):
        inventory = read('SOURCE_INVENTORY.json')
        self.assertEqual(inventory['archived_snapshot_files_verified'], 262)
        for item in inventory['files']:
            with self.subTest(path=item['path']):
                path = ROOT / item['path']
                payload = path.read_bytes()
                self.assertEqual(len(payload), item['bytes'])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), item['sha256'])
                if path.suffix == '.py':
                    ast.parse(payload.decode('utf-8-sig'), filename=item['path'])

    def test_final_scales_and_paper_regression_scopes(self):
        report = read('evidence/FINAL_CAMPAIGN_RESULT.json')
        for key, value in {'BG_SCALE': .552, 'AIDC_ABSOLUTE_SCALE': 2.4,
                           'MESS_SCALE': 2., 'PAPER_PCC_CONFIG_USED': True,
                           'RESITING_USED': False, 'FEEDER_MODIFIED': False,
                           'AIDC_DOUBLE_SCALING': False,
                           'B2_SEARCH_DOMAIN_CHANGED': False}.items():
            self.assertEqual(report[key], value)
        parity = read('evidence/paper_authority/ACTUAL_PIPELINE_PARITY_FREEZE.json')
        self.assertEqual(parity['status'], 'FROZEN_PASS')
        self.assertTrue(parity['independent_scopes'])
        self.assertAlmostEqual(parity['DA_exact_rho'], .8543958835735742, places=12)
        self.assertAlmostEqual(parity['Actual_exact_rho'], .8537462147791017, places=12)

    def test_final_ac_and_export_scopes_agree(self):
        report = read('evidence/FINAL_CAMPAIGN_RESULT.json')
        by = {r['policy']: r for r in report['results']}
        for policy, row in by.items():
            folder = {'B0': 'DA_exact', 'B1': 'final_exact',
                      'B2': 'independent_clean_exact', 'B3': 'final_exact'}[policy]
            for name, metric in [(folder, 'DA_exact_rho'), ('Fresh', 'Fresh_rho')]:
                ac = read(f'evidence/{policy}/{name}/AC_VALIDATION.json')
                self.assertEqual(ac['status'], 'PASS')
                self.assertEqual(len(ac['slots']), 96)
                self.assertTrue(all(s['converged'] and s['controls_settled'] and s['feasible'] for s in ac['slots']))
                self.assertEqual(row[metric], ac['metrics']['max_phase_line_loading_pu'])
            actual = read(f'evidence/Actual/{policy}/COMPLETE.json')
            self.assertTrue(actual['AC_feasible'])
            self.assertEqual(actual['summary']['converged_slots'], 96)
            self.assertEqual(actual['summary']['controls_settled_slots'], 96)
            self.assertEqual(row['Actual_rho'], actual['summary']['max_phase_line_loading_pu'])
            inner = f'Actual/{policy}' if policy == 'B0' else f'Actual/{policy}/{policy}'
            replay = read(f'evidence/{inner}/CONTINUOUS_VERIFICATION.json')
            self.assertEqual(replay['status'], 'PASS')
            self.assertTrue(replay['taps_identical'])
            self.assertTrue(all(v == 0 for v in replay['max_errors'].values()))
        for scope, pairs in report['reductions'].items():
            for pair, value in pairs.items():
                left, right = pair.split('_minus_')
                self.assertAlmostEqual(by[left][scope] - by[right][scope], value, places=14)
        with (ROOT / 'paper_csv/10_EXPORT_VALIDATION.csv').open(encoding='utf-8-sig') as stream:
            for row in csv.DictReader(stream):
                self.assertEqual(float(row['array_max']), by[row['policy']]['Actual_rho'])
                self.assertEqual(float(row['abs_error']), 0.)
        review = read('evidence/FINAL_REVIEW_20260923.json')
        b2 = next(r for r in review['results'] if r['policy'] == 'B2')
        self.assertIn('not full B2', b2['runtime_scope'])
        self.assertGreater(b2['calendar_start_to_DA_complete_seconds'], b2['runtime_seconds'])

    def test_paper_termination_and_full_separation(self):
        authority = read('evidence/PAPER_SOLVER_TERMINATION_AUTHORITY.json')
        self.assertEqual(authority['effective_parameters']['MIPGap'], .001)
        self.assertEqual(authority['effective_parameters']['TimeLimit'], 600.)
        self.assertEqual(authority['WORK_LIMIT_TIERS'], [60., 180., 300.])
        self.assertTrue(authority['original_quality_guard_unchanged'])
        certificates = sorted((ROOT / 'evidence').glob('*/active_grid/call_*/FULL_SEPARATION_CLOSURE.json'))
        self.assertEqual(len(certificates), 44)
        for path in certificates:
            c = json.loads(path.read_text())
            self.assertEqual(c['status'], 'PASS')
            self.assertEqual(c['checked_rows'], 31945536)
            self.assertLessEqual(c['maximum_violation'], c['tolerance'])
            self.assertTrue(c['no_active_row_cap'] and c['no_route_pruning'])
            self.assertEqual(c['termination_authority'], 'PAPER_SOLVER_TERMINATION')

    def test_external_archive_checksum_and_size(self):
        path = next((ROOT / 'archive').glob('*_VERIFICATION.json'))
        verification = json.loads(path.read_text())
        checksum = next((ROOT / 'archive').glob('*.sha256')).read_text().split()[0]
        self.assertEqual(verification['status'], 'PASS')
        self.assertEqual(checksum, verification['archive_sha256'])
        self.assertEqual(verification['archive_bytes'], 18532150287)
        self.assertEqual(verification['source_file_count'], 32243)
        self.assertTrue(verification['all_member_sha256_match'])
        self.assertFalse(read('archive/LOCATION.json')['archive_committed'])


if __name__ == '__main__':
    unittest.main()
