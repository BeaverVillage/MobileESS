"""Exercise archived policy functions without importing or running the campaign."""
import ast
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).parent / 'perf1_overlay/burst_resource_dispatcher.py'


class ResourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.live = []
        self.pending = {('2025-05-26', p) for p in ('B0', 'B1', 'B2')}
        self.pending |= {('2025-05-27', p) for p in ('B0', 'B1')}
        self.campaign = SimpleNamespace(
            read=lambda p: json.loads(p.read_text(encoding='utf-8')),
            atomic=self.write, sha=lambda p: 'mock-sha',
            scan_workers=lambda: self.live,
            POLICIES=('B0', 'B1', 'B2', 'B3'),
            da_pass=lambda d, p: (d, p) in self.pending,
            actual_done=lambda d, p: False,
        )
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.ns = dict(campaign=self.campaign, OUT=self.out, time=time,
                       __file__=str(SOURCE), base_atomic=self.write)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), self.ns)
        self.write(self.out / 'RESOURCE_BURST_AUTHORITY.json', dict(
            dispatcher_adapter_SHA='mock-sha', unchanged_performance_freeze_SHA='mock-sha'))

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.ns['apply_policy']({'all_days': ['2025-05-26', '2025-05-27']})

    def test_occupied_DA_backlog_returns_to_four(self):
        self.live = [dict(day=d, cmd=['mission_cut_worker.py'])
                     for d in ('2025-05-26', '2025-05-27')]
        self.assertEqual(self.apply()['total'], 4)
        state = self.campaign.read(self.out / 'RESOURCE_BURST_STATE.json')
        self.assertEqual(state['pending_eligible_Actual'], 5)
        self.assertEqual(state['dispatchable_pending_Actual'], 0)
        self.assertEqual(state['pending_on_occupied_days'], 5)
        self.assertEqual(state['mode'], 'NORMAL_4')
        self.assertTrue((self.out / 'RESOURCE_BURST_RESTORED.json').exists())

    def test_runnable_backlog_retains_burst(self):
        self.live = [dict(day='2025-05-26', cmd=['mission_cut_worker.py'])]
        self.assertEqual(self.apply()['total'], 10)

    def test_running_actual_must_drain(self):
        self.pending.clear()
        self.live = [dict(day='2025-05-26', cmd=['performance_worker.py'])]
        self.assertEqual(self.apply()['mode'], 'ACTUAL_BURST_8')

    def test_normal_mode_stays_normal_after_new_DA(self):
        self.pending.clear()
        self.assertEqual(self.apply()['mode'], 'NORMAL_4')
        self.pending.add(('2025-05-27', 'B3'))
        self.assertEqual(self.apply()['total'], 4)

    def test_normal_order_does_not_prioritize_later_actual(self):
        self.write(self.out / 'RESOURCE_BURST_STATE.json', {'mode': 'NORMAL_4'})
        self.ns['base_choose'] = lambda days, *args: (days[0], 'DA' if days[0].endswith('26') else 'ACTUAL')
        choose = self.ns['choose_with_pipeline']
        self.assertEqual(choose(['2025-05-27', '2025-05-26'], set(), set(), set()), ('2025-05-26', 'DA'))
        self.assertEqual(choose(['2025-05-26', '2025-05-27'], {'2025-05-26'}, set(), set()), ('2025-05-27', 'ACTUAL'))

    def test_status_reports_normal_priority(self):
        self.write(self.out / 'RESOURCE_BURST_STATE.json', {'mode': 'NORMAL_4'})
        path = self.out / 'status.json'
        self.ns['atomic_with_policy'](path, {'Actual_priority': True})
        state = self.campaign.read(path)
        self.assertFalse(state['Actual_priority'])
        self.assertEqual(state['resource_mode'], 'NORMAL_4')


if __name__ == '__main__':
    unittest.main(verbosity=2)
