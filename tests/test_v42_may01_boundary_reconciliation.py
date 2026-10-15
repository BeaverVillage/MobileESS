from copy import deepcopy
import json
from pathlib import Path
import pytest

from v42_integration.dday_initialization import _episode
from v42_integration.known_commands import compile_known_commands
from v42_integration.may01_boundary_reconciliation import (
    approved_initialization_audit,build_running_continuation_certificate,checked_json,
    compare_known_boundary,file_record,validate_running_continuation_certificate)
from v42_integration.policy import digest

ROOT=Path(r'D:\v42_integration_validation_20261013\DDAY_V5_B3_FINAL_ATTEMPT01')
INITIAL=Path(r'D:\v42_common_am_qos_integration_20261013\docs\v42_common_am_qos_integration\V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
NATIVE=Path(r'D:\v42_may_joint_repair_campaign_20261013\raw\2025-05-01\NATIVE_INPUT_TEMPLATE_B1.json')
SHA='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'


@pytest.fixture(scope='module')
def original():
    if not all(p.exists() for p in (INITIAL,NATIVE,ROOT/'B3/A1/A_RESULT.json')):
        pytest.skip('Exact original PR223 source artifacts unavailable; no fixture promotion.')
    a=file_record(ROOT/'B3/A1/A_RESULT.json');n=file_record(NATIVE);i=file_record(INITIAL)
    result=checked_json(a);commands=compile_known_commands(result['selected_jobs'],slot_zero_seconds=1746000000.)
    proof=build_running_continuation_certificate(a,n,i,issue_seconds=1746000000.,commands=commands,expected_semantic_sha=SHA)
    return a,n,i,result,commands,proof


def validate(original,proof=None,commands=None,stage=None):
    a,n,i,result,original_commands,original_proof=original
    return validate_running_continuation_certificate(proof or original_proof,commands=commands or original_commands,
        stage_case_sha=stage or result['case_sha'],initial_semantic_sha=SHA,begin_seconds=1746021600.)


def test_original_semantic_sha_and_raw_file_sha_are_distinct_valid_receipts(original):
    state,audit=approved_initialization_audit(original[2],expected_semantic_sha=SHA)
    assert audit['status']=='PASS' and audit['semantic_sha']!=audit['raw_file_sha']
    assert state['counts']['running']==324 and state['counts']['running_GPU']==472
    assert state['counts']['pending']==1300 and len(state['historical_completed'])==178
    assert state['PR129_reused_jobs']==20 and state['PR125_fallback_jobs']==153


def test_original_103_issue_running_are_continuations_not_restarted_jobs(original):
    rows=validate(original);proof=original[-1]
    assert len(rows)==103 and proof['eligible_GPU']==133 and proof['observed_continuation_prefix_GPUh']==798
    assert all(r['historical_episode_start_seconds']<r['native_start_epoch_seconds'] for r in rows.values())
    assert all(r['running_GPU_retained'] and not r['physical_job_restarted'] for r in rows.values())
    assert not proof['Pending_execution_certified'] and not proof['full_issue_to_Dday_schedule_prefix_certified']


def test_resealed_forged_continuation_row_is_rejected_by_exact_source_rebuild(original):
    forged=deepcopy(original[-1]);forged['rows'][0]['current_site']='FORGED'
    forged['certificate_sha']=digest({k:v for k,v in forged.items() if k!='certificate_sha'})
    with pytest.raises(ValueError,match='SOURCE_RUNNING_CONTINUATION_REVALIDATION_DRIFT'):validate(original,proof=forged)


def test_retimed_command_and_different_stage_cannot_use_original_certificate(original):
    changed=deepcopy(original[-2]);changed[next(iter(changed))]['start_seconds']+=900
    with pytest.raises(ValueError,match='BINDING_DRIFT'):validate(original,commands=changed)
    with pytest.raises(ValueError,match='BINDING_DRIFT'):validate(original,stage='a'*64)


def test_self_sealed_unrelated_native_copy_is_not_approved_boundary_source(original,tmp_path):
    unrelated=tmp_path/'UNRELATED_NATIVE.json'
    native=checked_json(original[1]);native['role']='UNRELATED_SELF_SEALED_SOURCE'
    unrelated.write_text(json.dumps(native),encoding='utf-8')
    with pytest.raises(ValueError,match='NATIVE_NOT_IN_APPROVED_INITIAL_SOURCE_RECEIPTS'):
        build_running_continuation_certificate(original[0],file_record(unrelated),original[2],
            issue_seconds=1746000000.,commands=original[-2],expected_semantic_sha=SHA)


def test_false_full_point_replay_cannot_issue_continuation_authority(original,tmp_path):
    invalid=checked_json(original[0]);invalid['FULL_point_replay']['PASS']=False
    path=tmp_path/'INVALID_A.json';path.write_text(json.dumps(invalid),encoding='utf-8')
    with pytest.raises(ValueError,match='FULL_POINT_REPLAY_REQUIRED'):
        build_running_continuation_certificate(file_record(path),original[1],original[2],
            issue_seconds=1746000000.,commands=original[-2],expected_semantic_sha=SHA)


def named_fixture():
    def source(uid,state='PENDING',gpu=1,q50=4500,elapsed=0):
        return dict(job_uid=uid,state=state,known_at_issue=True,issue_time='1970-01-01T00:00:00+00:00',
            submit_time='1969-12-31T23:00:00+00:00',GPU_gang=gpu,V10_Q50_total_seconds=q50,
            elapsed_seconds=elapsed,nominal_remaining_seconds=max(0,q50-elapsed),
            service_slots=max(0,(q50-elapsed+899)//900),current_site_if_running='A' if state=='RUNNING' else None)
    sources=[source('continuation','RUNNING',2,4500,900),source('observed_start'),
        source('past_finished'),source('past_active'),source('expired','RUNNING',3,900,1800),source('future')]
    def running(uid,site,start,gpu,q50):
        return dict(uid=uid,episode_id=_episode(uid,-3600),site=site,observed_start_seconds=start,
            elapsed_compute_seconds=1800-start,gpu=gpu,q50=q50)
    state=dict(begin_epoch_seconds=1800,common_initial_state_sha='a'*64,
        running=[running('continuation','A',-900,2,4500),running('observed_start','B',900,1,4500),
            running('expired','A',-1800,3,900)],pending=[dict(uid=uid,episode_id=_episode(uid,-3600),site='A')
            for uid in ('past_finished','past_active','future')],historical_completed=[])
    def option(start,end):return dict(start=start,initial_site='A',checkpoint=-1,segments=[['A',start,end]])
    selected=dict(continuation=option(0,4),observed_start=option(0,5),past_finished=option(0,1),
        past_active=option(1,5),future=option(2,7))
    return dict(known_population=sources),dict(selected_jobs=selected,case_sha='b'*64),state


def test_named_fixture_multiple_causes_prefix_quantity_and_no_private_runtime_read():
    native,a,state=named_fixture();rows,summary=compare_known_boundary(native,a,state,issue_seconds=0)
    by_uid={r['uid']:r for r in rows}
    assert by_uid['continuation']['continuation_certified'] and by_uid['continuation']['first_possible_divergence_seconds'] is None
    assert by_uid['observed_start']['mismatch_types']==['ISSUE_PENDING_SOURCE_STARTED_AFTER_OPTIMIZED','DISTINCT_APPROVED_DDAY_SITE_MODEL']
    assert by_uid['past_finished']['primary_classification']=='PENDING_PRE_DDAY_COMMAND_NOMINAL_FINISHED'
    assert by_uid['past_active']['primary_classification']=='PENDING_PRE_DDAY_COMMAND_NOMINAL_ACTIVE'
    assert by_uid['past_active']['planned_prefix_reserved_GPUh']==.25
    assert by_uid['continuation']['planned_prefix_reserved_GPUh']==1
    assert by_uid['expired']['primary_classification']=='ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD'
    assert by_uid['expired']['Dday_remaining_nominal_seconds']==0 and by_uid['expired']['gpu']==3
    assert all(r['actual_remaining_runtime_seconds'] is None for r in rows)
    assert summary['Native_calls']==0 and not summary['optimized_schedule_full_prefix_replayed']


def test_nonlegal_prefix_axis_fails_closed():
    native,a,state=named_fixture();state['begin_epoch_seconds']=1801
    with pytest.raises(ValueError,match='LEGAL_SLOT_AXIS'):compare_known_boundary(native,a,state,issue_seconds=0)
