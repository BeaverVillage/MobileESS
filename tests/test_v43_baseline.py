from functools import partial

import pytest

from test_v43_actual_port import stats
from test_v43_corrective import request
from v42_capacity.actual import Environment
from v43_actual.vendor.actual import run_actual
from v43_actual.vendor.policy import digest
from v43_actual.vendor.qos import QoSWindowProvider
from v43_corrective.reference import CorrectedReferenceScheduler
from v43_baseline.worker import BaselineController


def replay(*,service=2700.):
    caps={'A':1,'B':1}
    qos=QoSWindowProvider(stats(),case_sha=digest('BASELINE_FIXTURE'),provider_sha=digest('PROVIDER'))
    ref=CorrectedReferenceScheduler(caps,reference_sha='NAMED_BASELINE_REFERENCE')
    rows=[request('FIRST',0.,site='A',q50=900.,origin_unknown=False),request('SECOND',900.,site='A')]
    return run_actual(caps,rows,Environment({'FIRST':service,'SECOND':300.}),arm='B0',
        qos_window_provider=qos,reference=ref,begin=0.,end=4500.,frozen_policy=None,
        controller_class=partial(BaselineController,rack_limits={'A':[1],'B':[1]}))


def test_original_fcfs_waits_for_observed_overrun_release_without_alternative_site():
    out=replay();rows={r['job_uid']:r for r in out['queue_ledger']}
    assert rows['FIRST']['admitted_time']==0.
    assert rows['SECOND']['admitted_time']==2700.
    assert rows['SECOND']['site']=='A'
    assert all(r['policy_action']=='START' and r['intentional_delay_seconds']==0 for r in rows.values())
    assert not out['migration_receipts'] and not out['rule_consumption_receipt']
    assert out['receipt']['optimizer_calls']==0 and out['receipt']['capacity_violations']==0
    assert out['receipt']['future_duration_controller_reads']==0
    assert out['receipt']['future_completion_controller_reads']==0


def test_observed_shorter_service_changes_actual_occupancy_not_planning_copy():
    late=replay(service=2700.);early=replay(service=300.)
    late_rows={r['job_uid']:r for r in late['queue_ledger']}
    early_rows={r['job_uid']:r for r in early['queue_ledger']}
    assert late_rows['SECOND']['admitted_time']==2700.
    assert early_rows['SECOND']['admitted_time']==900.
    assert late['occupancy_GPU'].sum()!=early['occupancy_GPU'].sum()


def test_baseline_rejects_any_attached_control_policy():
    with pytest.raises(ValueError,match='GRID_BLIND_BASELINE_NO_CONTROL_POLICY_REQUIRED'):
        BaselineController({'A':1},arm='B0',qos_window_provider=None,frozen_policy=object(),rack_limits={'A':[1]})
