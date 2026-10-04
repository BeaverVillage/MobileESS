"""Independent read-only audits of the newly executed native campaign."""
import json
import os
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np

from v42_campaign.authority import file_sha
from v42_b0_production.authority import ROOT, read


@unittest.skipUnless(os.environ.get('B0_AUDIT_RUN_ROOT'), 'Requires completed new production artifacts')
class CompletedCampaign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['B0_AUDIT_RUN_ROOT']).resolve()
        cls.authority = read(cls.root / 'AUTHORITY.json')
        cls.state = read(cls.root / 'CAMPAIGN_STATE.json')
        cls.checker = read(ROOT / 'docs/v42_transformer_normalamps_contract/SOURCE_COMPILED_NORMALAMPS_AUTHORITY.json')

    def receipt(self, day, stage):
        row = self.state['stages'][f'B0/{day}/{stage}']
        self.assertEqual(row['status'], 'PASS')
        path = self.root / row['receipt_path']
        self.assertEqual(file_sha(path), row['receipt_sha'])
        return read(path)['payload']

    def test_all_new_dates_outputs_and_scope(self):
        self.assertEqual(self.authority['days'], [f'2025-05-{d:02d}' for d in range(1, 32)])
        self.assertEqual(len(self.state['stages']), 155)
        for sid, row in self.state['stages'].items():
            self.assertTrue(sid.startswith('B0/'))
            self.assertIn(row['status'], ('PASS', 'FAIL', 'INTERRUPTED', 'BLOCKED'))
            if row['status'] == 'PASS':
                payload = self.receipt(row['day'], row['stage'])
                self.assertEqual(payload['run_id'], self.authority['run_id'])
                self.assertFalse(payload['synthetic_only'])
                for entry in payload['output_files']:
                    path = Path(entry['path']).resolve()
                    self.assertTrue(path.is_relative_to(self.root))
                    self.assertEqual(file_sha(path), entry['sha256'])
        for key in ('optimizer', 'Gurobi_optimize', 'B1', 'B2', 'B3', 'M1', 'Branch_and_Price'):
            self.assertEqual(self.state['production_calls'][key], 0)

    def test_all_planning_freezes_precede_any_actual(self):
        frozen = max(datetime.fromisoformat(self.state['stages'][f'B0/{d}/PLANNING_FREEZE']['timestamps']['PASS'])
                     for d in self.authority['days'])
        starts = [datetime.fromisoformat(t['timestamp']) for t in self.state['transitions']
                  if t['new'] == 'RUNNING' and t['id'].endswith('/ACTUAL')]
        self.assertTrue(starts)
        self.assertLess(frozen, min(starts))

    def test_raw_fresh_current_voltage_and_actual_PQ(self):
        self.assertEqual(self.checker['transformer_current_authority_sha256'], self.authority['checker_SHA'])
        limits = {r['branch_phase']: r['NormalAmps'] for r in self.checker['rows'] + self.checker['lines']}
        for day in self.authority['days']:
            fresh = self.receipt(day, 'FRESH_AC')
            actual = self.receipt(day, 'ACTUAL')
            with np.load(Path(fresh['folder']) / 'V_ACTUAL_AC.npz') as raw, np.load(Path(actual['folder']) / 'ACTUAL_PHYSICAL.npz') as physical:
                names = list(map(str, raw['branch_names']))
                tx = np.array([n.startswith('transformer.') for n in names])
                ratio = raw['current_A'] / np.array([limits[n] for n in names])
                np.testing.assert_array_equal(raw['current_pu'], ratio)
                np.testing.assert_array_equal(raw['PCC_P_kw'], physical['PCC_P_kw'])
                np.testing.assert_array_equal(raw['PCC_Q_kvar'], physical['PCC_Q_kvar'])
                self.assertEqual(int(raw['converged'].sum()), 96)
                self.assertTrue(np.all(raw['capacitor_states'] == 1))
                measured = dict(voltage_violations=int(((raw['V_ACTUAL_AC'] < .95) | (raw['V_ACTUAL_AC'] > 1.05)).sum()),
                    line_current_violations=int((ratio[:, ~tx] > 1).sum()),
                    transformer_current_violations=int((ratio[:, tx] > 1).sum()),
                    transformer_kVA_violations=int((raw['transformer_kVA_pu'] > 1).sum()))
                for key, value in measured.items():
                    self.assertEqual(fresh['metrics'][key], value)
                self.assertEqual(fresh['metrics']['maximum_transformer_current_pu'], float(ratio[:, tx].max()))
                self.assertEqual(fresh['metrics']['maximum_line_current_pu'], float(ratio[:, ~tx].max()))

    def test_native_requests_threads_no_forbidden_calls(self):
        results = [read(p) for p in self.root.rglob('RESULT.json') if read(p)['status'] == 'COMPUTED']
        self.assertEqual(sum(r.get('stage') == 'B0_PLANNING' for r in results), 31)
        self.assertEqual(sum(r.get('stage') == 'ACTUAL' for r in results), 31)
        self.assertEqual(sum(r.get('stage') == 'FRESH_AC' for r in results), 31)
        for result in results:
            self.assertEqual(result['status'], 'COMPUTED')
            self.assertEqual(result['arm'], 'B0')
            self.assertEqual(result['GUROBI_THREADS'], 1)
            for key in ('Gurobi_optimize_calls', 'M1_calls', 'B1_calls', 'B2_calls', 'B3_calls', 'Branch_and_Price_calls'):
                self.assertEqual(result[key], 0)
            self.assertTrue(all(m['Threads'] == 1 for m in result['Gurobi_models_parameter_readback']))
        for path in self.root.rglob('REQUEST.json'):
            request = read(path)
            self.assertEqual(request['arm'], 'B0')
            self.assertEqual(request['run_id'], self.authority['run_id'])
            self.assertIn(request['stage'], ('B0_PLANNING', 'ACTUAL', 'FRESH_AC', 'TRUTH_PREPARATION'))


if __name__ == '__main__':
    unittest.main()
