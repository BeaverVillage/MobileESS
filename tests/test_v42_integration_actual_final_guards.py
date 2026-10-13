"""Latest DD00 scope, private metadata and mutable-case execution boundaries."""
import json

import numpy as np
import pytest

from v42_integration.actual import JobEventController, JobRequest, PRIVATE_REALIZATION_FIELDS
from v42_integration.coordinator import run_arm, _require_actual_gate
from v42_integration.fixture_validation import build_fixture
from v42_integration.qos import TrainingStatistics, QoSWindowProvider
from v42_final.workload import ForecastBook


class NoSolveBudget:
    def remaining(self):return 0.
    def used(self):return 0.


@pytest.mark.parametrize('private_key',sorted(PRIVATE_REALIZATION_FIELDS))
def test_private_aliases_rejected_before_registration_and_cc4(private_key):
    stats=TrainingStatistics.from_records([],source_sha='FINAL_GUARD_EMPTY_TRAIN')
    qos=QoSWindowProvider(stats,case_sha='case',provider_sha='provider')
    forecast=ForecastBook(tuple([1.]*24),tuple([2.]*24),0)
    controller=JobEventController({'A':1},arm='B0',qos_window_provider=qos,forecast=forecast)
    request=JobRequest('job',0,1,('A',),900,'A',dict(origin_unknown=True,
        representation_starts_seconds=(0,900),migration_capability={private_key:123}))
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        controller.submit(request,0)
    assert not controller.requests and not controller.ledger.jobs
    assert not controller.pending and not qos.receipts and not forecast.submissions


def test_hard_contract_completion_deadline_is_public_metadata():
    stats=TrainingStatistics.from_records([],source_sha='FINAL_GUARD_EMPTY_TRAIN')
    qos=QoSWindowProvider(stats,case_sha='case',provider_sha='provider')
    controller=JobEventController({'A':1},arm='B0',qos_window_provider=qos)
    controller.submit(JobRequest('job',0,1,('A',),900,'A',dict(
        completion_deadline_seconds=1800,representation_starts_seconds=(0,900))),0)
    assert controller.metadata['job']['completion_deadline_seconds']==1800


def test_case_single_use_prevents_cross_arm_future_observation_reuse_and_fixture_trace_axis(tmp_path):
    case=build_fixture(tmp_path/'INPUT')
    result=run_arm('B0',case,NoSolveBudget(),tmp_path/'B0')
    assert result['actual']['receipt']['completed_jobs']==3
    with np.load(tmp_path/'B0/ACTUAL_OCCUPANCY_POWER_TRACE.npz') as z:
        assert len(z['timestamps_start_epoch_seconds'])==z['GPU'].shape[0]==6
        assert z['GPU'].shape==z['IT_kw'].shape==z['PCC_P_kw'].shape==z['PCC_Q_kvar'].shape
    with pytest.raises(ValueError,match='ALREADY_CONSUMED'):
        run_arm('B2',case,NoSolveBudget(),tmp_path/'B2')
    assert not (tmp_path/'B2').exists()


def test_real_actual_requires_verified_dd00_queue_sites_and_exact_horizon(tmp_path):
    case=build_fixture(tmp_path/'INPUT')
    case.evidence_kind='REAL_DATA'
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):
        run_arm('B0',case,NoSolveBudget(),tmp_path/'NO_GATE')
    assert not case._consumed and not (tmp_path/'NO_GATE').exists()
    case.actual_gate=dict(status='DDAY_INITIAL_STATE_AUTHORIZED',initial_queue_verified=True,
                          active_running_site_authority=True,full96_actual_authorized=True,
                          common_initial_state_sha='fixture_verified_boundary',
                          Arm_initial_state_SHA={arm:'fixture_verified_boundary' for arm in ('B0','B1','B2','B3')})
    case.actual_arguments.update(begin=-21600,end=86400)
    with pytest.raises(ValueError,match='EXACT_96_SLOT_SCOPE'):_require_actual_gate(case,0)
    case.actual_arguments.update(begin=0,end=86400)
    _require_actual_gate(case,0)
    case.actual_gate['initial_queue_verified']=False
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):_require_actual_gate(case,0)


def test_planning_only_freezes_and_reloads_policy_without_unknown_registration_or_actual(tmp_path):
    case=build_fixture(tmp_path/'INPUT')
    case.evidence_kind='REAL_DATA'
    case.actual_gate=dict(status='INITIAL_QUEUE_UNVERIFIED',initial_queue_verified=False,
                          active_running_site_authority=False)
    original_uids=set(case.qos_provider.receipts)
    result=run_arm('B0',case,NoSolveBudget(),tmp_path/'PLAN_ONLY',planning_only=True)
    assert result['actual'] is None and result['planning_only']
    assert set(case.qos_provider.receipts)==original_uids and 'unknown-observed' not in original_uids
    receipt=json.loads((tmp_path/'PLAN_ONLY/RELOAD_CONSUMPTION_RECEIPT.json').read_text())
    assert receipt['status']=='RELOADED_PLANNING_ONLY_ACTUAL_NOT_RUN'
    assert receipt['runtimeQueries']==0
    assert (tmp_path/'PLAN_ONLY/UNKNOWN_CONTROL_POLICY.json').exists()
    assert (tmp_path/'PLAN_ONLY/PLANNING_FREEZE.json').exists()
    assert not (tmp_path/'PLAN_ONLY/ACTUAL_RESULT.json').exists()
    assert not result['freeze']['Actual_execution_authorized']
