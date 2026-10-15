import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import server


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.row = dict(current_stage='A1', current_phase='NATIVE_BINDINGS')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_actual_dw_progress_supersedes_stale_callback(self):
        self.write('LIVE_PROGRESS.json', dict(progress=dict(phase='NATIVE_BINDINGS')))
        self.write('A1/DW/NATIVE0_PREPARATION_PROGRESS.json', dict(phase='COMPLETE_SOURCE_PRICING_ROSTER', classes=50, required_classes=1555))
        value = server.phase_for(self.root, self.row, None, True)
        self.assertEqual(value['label'], '전체 Pricing 블록 준비')
        self.assertEqual(value['completed'], 50)

    def test_running_native_supersedes_native0_snapshot(self):
        self.write('A1/DW/NATIVE0_PREPARATION_PROGRESS.json', dict(phase='ORIGINAL_REFERENCE_ASSEMBLY',Native_calls=0))
        value = server.phase_for(self.root, self.row, dict(label='RELEASE_P1:A1:DW:PHASE_I'), True)
        self.assertEqual(value['label'], 'DW Phase I 최적화')

    def test_completed_build_does_not_show_old_binding(self):
        value = server.phase_for(self.root, self.row, None, True)
        self.assertEqual(value['code'], 'DW_PREPARATION_PENDING')

    def test_different_case_lower_bound_rejected(self):
        self.write('A1/DW/DW_RESULT.json', dict(case_sha='old', LB_certified=True, full_domain_pricing_complete=True, Global_LB=.6))
        self.assertIsNone(server.certified_bounds(self.root,'A1',dict(stage_case_sha='new'))['LB'])

    def test_incomplete_pricing_rejected(self):
        self.write('A1/DW/DW_RESULT.json', dict(case_sha='new', LB_certified=True, full_domain_pricing_complete=False, Global_LB=.6))
        self.assertIsNone(server.certified_bounds(self.root,'A1',dict(stage_case_sha='new'))['LB'])

    def test_matching_certified_bounds(self):
        self.write('A1/DW/DW_RESULT.json', dict(case_sha='new', LB_certified=True, full_domain_pricing_complete=True, Global_LB=.6))
        self.write('A1/P1_ONLY_RESULT.json', dict(case_sha='new', FULL_feasible=True, objective=.8))
        self.assertAlmostEqual(server.certified_bounds(self.root,'A1',dict(stage_case_sha='new'))['gap_percent'],25.)

    def test_historical_b0_is_explicitly_historical_and_sha_checked(self):
        outcome=self.write('old/ARM_OUTCOME.json',dict(status='FULL_PASS',actual=dict(result=dict(executed_actual_slots=96)),fresh=dict(result=dict(executed_slots=96))))
        raw=outcome.read_bytes()
        self.write('PRESERVED_B0_BASELINE.json',dict(baseline_preserved=True,outcome=dict(path=str(outcome),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
        value=server.preserved_b0(self.root)
        self.assertEqual(value['actual_slots'],96)
        self.assertFalse(value['current_release_recertified'])
        outcome.write_text('{"status":"FULL_PASS"}')
        self.assertEqual(server.preserved_b0(self.root)['status'],'EVIDENCE_MISMATCH')

    def test_preserved_old_execution_is_stopped(self):
        value=server.state()
        b1=next(a for a in value['arms'] if a['arm']=='B1')
        self.assertEqual(b1['stage_budget']['cap'],5400.)
        self.assertEqual(value['historical_B0']['fresh_slots'],96)
        self.assertFalse(value['historical_B0']['current_release_recertified'])
        self.assertEqual(value['archived_native_seconds'],1965.3929998874664)
        self.assertFalse(b1['process']['alive'])
        self.assertEqual(b1['raw_arm_status'],'INTERRUPTED_BY_USER')


if __name__=='__main__':
    unittest.main()
