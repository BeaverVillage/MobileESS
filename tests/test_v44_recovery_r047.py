import copy
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from v44_recovery_r047 import operations as op


class B0ParallelTests(unittest.TestCase):
    def test_reject_b2_from_parallel_slot(self):
        with self.assertRaises(PermissionError),op.b0_slot(op.core.week.DAYS[0],'B2',1,root=op.CAMPAIGN,lease={}):pass

    def test_reject_second_slot(self):
        with self.assertRaises(PermissionError),op.b0_slot(op.core.week.DAYS[0],'B0',2,root=op.CAMPAIGN,lease={}):pass

    def test_reject_wrong_day(self):
        with self.assertRaises(PermissionError),op.b0_slot('2025-05-07','B0',1,root=op.CAMPAIGN,lease={}):pass

    def test_unknown_legacy_resource_rejected(self):
        with patch('v44.execution.assert_current',return_value={'request':{}}),patch.object(op,'request_authority'),self.assertRaises(PermissionError),op.shared_resources('D:/unknown.lock'):pass

    def fixture(self):
        old=[dict(day=d,arm=a,status='PASS' if a in ('B1','B3') else 'BASELINE_QUEUED') for d in op.core.week.DAYS for a in op.core.week.ARMS]
        aux=[dict(day=d,arm='B0',status='PASS',result={'path':d}) for d in op.core.week.DAYS]
        return dict(jobs=old,lease={}),dict(jobs=aux,workers=[])

    def merge(self,state,aux):
        with patch.object(op,'alive',return_value=False),patch.object(op,'verify'),patch.object(op,'read',side_effect=lambda p:dict(day=p,arm='B0',PASS=True,finished_UTC='done')):
            return op.merge_aux(state,aux)

    def test_merge_all_seven_without_changing_main_or_b2(self):
        state,aux=self.fixture();before=copy.deepcopy(state)
        merged=self.merge(state,aux)
        self.assertEqual(sum(j['status']=='PASS' for j in merged['jobs']),21)
        self.assertEqual([j for j in merged['jobs'] if j['arm']!='B0'],[j for j in before['jobs'] if j['arm']!='B0'])

    def test_merge_live_parent_rejected(self):
        state,aux=self.fixture()
        with patch.object(op,'alive',return_value=True),self.assertRaises(PermissionError):op.merge_aux(state,aux)

    def test_merge_live_worker_rejected(self):
        state,aux=self.fixture();aux['workers']=[{'pid':1}]
        with patch.object(op,'alive',return_value=False),self.assertRaises(PermissionError):op.merge_aux(state,aux)

    def test_merge_unfinished_main_rejected(self):
        state,aux=self.fixture();state['jobs'][1]['status']='ACTUAL_RUNNING'
        with self.assertRaises(PermissionError):self.merge(state,aux)

    def test_merge_duplicate_dispatch_rejected(self):
        state,aux=self.fixture();state['jobs'][0]['status']='BASELINE_RUNNING'
        with self.assertRaises(PermissionError):self.merge(state,aux)

    def test_merge_false_pass_rejected(self):
        state,aux=self.fixture()
        with patch.object(op,'alive',return_value=False),patch.object(op,'verify'),patch.object(op,'read',return_value=dict(day=op.core.week.DAYS[0],arm='B0',PASS=False,finished_UTC='done')),self.assertRaises(PermissionError):op.merge_aux(state,aux)

    def test_merge_missing_or_duplicate_day_rejected(self):
        for change in ('missing','duplicate'):
            state,aux=self.fixture()
            if change=='missing':aux['jobs'].pop()
            else:aux['jobs'][-1]=aux['jobs'][0]
            with self.assertRaises(PermissionError):self.merge(state,aux)

    def test_b0_uses_original_full_case(self):
        import inspect
        source=inspect.getsource(op.worker)
        self.assertIn('return inherited.base.worker(r)',source)
        self.assertNotIn("patch.object(science,'actual'",source)

if __name__=='__main__':unittest.main()
