"""Native0 Table V integration tests; no May performance is inferred."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import numpy as np
import pytest

from test_v42_integration_actual import request,qos
from v42_capacity.actual import Environment
from v42_integration.actual import run_actual
from v42_integration.qos import CausalReferenceScheduler
from v42_integration.tablev_actual import (TableVReferenceController,project_public_initial,
    _require_mess,run_tablev_actual)


def execute(arm):
    jobs=[request('first',gpu=1,q50=900,compatible=('A',)),
        request('second',submit=1,gpu=1,q50=900,compatible=('A',))]
    return run_actual({'A':1},jobs,Environment({'first':450,'second':450}),arm=arm,
        qos_window_provider=qos(),end=2700,controller_class=TableVReferenceController)


def test_b0_b2_have_identical_reference_aidc_trace_without_grid_veto():
    b0,b2=execute('B0'),execute('B2')
    np.testing.assert_array_equal(b0['occupancy_GPU'],b2['occupancy_GPU'])
    assert b0['job_event_ledger']==b2['job_event_ledger']
    assert b0['queue_ledger']==b2['queue_ledger']
    for result in (b0,b2):
        assert result['carryout']['controller']['tablev_state']['sensitivity_reads']==0
        assert not result['carryout']['controller']['tablev_state']['electrical_admission_veto_added']


def test_reference_uses_observed_completion_immediately_without_changing_dispatch_grid():
    result=execute('B0')
    assert result['occupancy_GPU'][0,0]==.5
    jobs=result['carryout']['controller']['episode_jobs']
    assert jobs['first']['completion_observed_time']==450
    assert jobs['first']['release_control_time']==450
    starts={r['job_uid']:r['admitted_time'] for r in result['queue_ledger']}
    assert starts=={'first':0,'second':900}


@pytest.mark.parametrize('arm',['B1','B3'])
def test_reference_controller_cannot_silently_relabel_flexible_arm(arm):
    with pytest.raises(ValueError,match='GRID_BLIND_REFERENCE'):
        TableVReferenceController({'A':1},arm=arm,qos_window_provider=qos())


def projection_fixture():
    raw_request=request('K',source_site=None,origin_unknown=True,episode_id='episode',elapsed_compute_seconds=0,
        can_prestart_place=False,protected=None,batch_eligible=None)
    raw=dict(uid='K',site=None,submit_seconds=0,gpu=1,q50=900,compatible_sites=['A','B'],
        episode_id='episode',elapsed_compute_seconds=0,origin_unknown=True,metadata=deepcopy(raw_request.metadata))
    state=dict(begin_epoch_seconds=0,common_initial_state_sha='initial',running=[],pending=[raw])
    future=request('U',submit=900,can_prestart_place=False)
    opaque=object();provider=SimpleNamespace(provider_sha='provider')
    reference=CausalReferenceScheduler({'A':1,'B':1},reference_sha='reference')
    reference.submit(raw_request,event_seconds=0)
    args=dict(begin=0,requests=[raw_request,future],running=[],environment=opaque)
    return args,state,reference,provider,raw_request,future


def test_initial_1624_projection_pattern_keeps_private_environment_and_source_flags():
    args,state,reference,provider,raw,future=projection_fixture();before=deepcopy(raw.metadata)
    result=project_public_initial(args,state,reference=reference,provider=provider)
    assert result['environment'] is args['environment'] and result['requests'][1] is future
    projected=result['requests'][0]
    assert projected.metadata['origin_unknown'] is False and projected.metadata['cc4_eligible'] is False
    assert projected.metadata['can_prestart_place'] is False and raw.metadata==before
    assert projected.source_site is None


@pytest.mark.parametrize('field,value',[('gpu',2),('q50',1800),('submit',1),('compatible',('B',))])
def test_initial_projection_refuses_request_service_or_source_drift(field,value):
    args,state,reference,provider,raw,_=projection_fixture()
    args['requests'][0]=replace(raw,**{field:value})
    with pytest.raises(ValueError,match='PUBLIC_REQUEST_DRIFT'):
        project_public_initial(args,state,reference=reference,provider=provider)


def test_reference_cannot_consume_saved_or_current_mess_on_plan():
    with pytest.raises(ValueError,match='MESS_OFF_REJECTS_ON_PLAN'):
        _require_mess({},'B0',{'mess':{'plan_sha':'old'}},None)


def test_truth_preparation_stays_below_official_contract_gate(tmp_path,monkeypatch):
    from v42_integration import tablev_actual
    monkeypatch.setattr(tablev_actual,'prepare_reference_inputs',lambda *a,**k:pytest.fail('private bank read'))
    with pytest.raises(ValueError,match='SETTLED_AC_CONTRACT'):
        run_tablev_actual(context={},arm='B0',reference_result={},reference_acceptance={},output=tmp_path/'new',gate={})
    assert not (tmp_path/'new').exists()


def test_actual_source_freeze_calls_original_two_argument_verifier_and_retains_exact_code(tmp_path):
    from v42_integration.tablev_actual import _source_freeze
    from v42_integration.coordinator import verify_sources
    from v42_integration.m_engine import file_record
    original=file_record(__import__('v42_integration.tablev_actual',fromlist=['']).__file__)
    freeze=_source_freeze({'manifest':{'source_freeze':{'files':[]}}},{'sources':[original]},tmp_path)
    verify_sources(freeze,[])
    saved=next(r for r in freeze['files'] if r['path'].endswith('tablev_actual.py'))
    assert saved['sha256']==original['sha256'] and saved['bytes']==original['bytes']
    assert Path(saved['path']).parent.name=='EXECUTED_SOURCE'
