"""Source-specific normalization tests; no planning or private service replay."""
from copy import deepcopy
from pathlib import Path
from dataclasses import replace
import json

import pytest

from v42_integration.followup_contract import (
    build_approved_dday_observed_state, require_initial_state_alignment,
)
from v42_integration.unified_contract import file_sha
from v42_integration.actual import JobRequest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/v42_common_am_qos_integration/V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'


@pytest.fixture(scope='module')
def approved():
    raw=json.loads(SOURCE.read_text(encoding='utf8'))
    record=dict(path=str(SOURCE),sha256=file_sha(SOURCE),bytes=SOURCE.stat().st_size)
    state=build_approved_dday_observed_state(record,
        initial_state_sha=raw['common_initial_state_sha'],begin_seconds=raw['begin_epoch_seconds'])
    def request(row):
        return JobRequest(uid=row['uid'],gpu=row['gpu'],submit=row['submit_seconds'],
            q50=row['q50'],compatible=tuple(row['compatible_sites']),source_site=row['site'],
            metadata=dict(episode_id=row['episode_id'],
                elapsed_compute_seconds=row['elapsed_compute_seconds'],
                dday_initialization_seconds=raw['begin_epoch_seconds']))
    args=dict(begin=raw['begin_epoch_seconds'],
        running=[(request(row),row['site'],row['observed_start_seconds']) for row in raw['running']],
        requests=[request(row) for row in raw['pending']])
    return raw,state,args,dict(initial_state_sha=raw['common_initial_state_sha'])


def alter_request(driver,population,**changes):
    if population=='running':
        request,site,start=driver['running'][0]
        driver['running'][0]=(replace(request,**changes),site,start)
    else:
        driver['requests'][0]=replace(driver['requests'][0],**changes)


def test_SOURCE_SEMANTIC_AND_FILE_SHA_DISTINCT(approved):
    raw,state,args,identity=approved
    assert state['source_record']['sha256']!=identity['initial_state_sha']
    joined=require_initial_state_alignment(state,args,identity,evidence_scope='REAL_DATA')
    assert joined['status']=='PASS' and joined['Running_UIDs']==324 and joined['Pending_UIDs']==1300
    assert state['MODEL_ASSUMPTION'] and not state['KESTREL_OBSERVED_SITE']


def test_approved_projection_rejects_semantic_sha_transcription(approved):
    raw,state,args,identity=approved
    wrong='5df25289619221a8ed1f7ee86b453d1495b15f0ff8f9e6dbe3075b3fb67c573'
    with pytest.raises(ValueError,match='SEMANTIC_OR_CLOCK_DRIFT'):
        build_approved_dday_observed_state(state['source_record'],
            initial_state_sha=wrong,begin_seconds=args['begin'])


def test_initial_pending_gpu_and_episode_are_checked(approved):
    raw,state,args,identity=approved
    bad=deepcopy(args);alter_request(bad,'pending',gpu=bad['requests'][0].gpu+1)
    with pytest.raises(ValueError,match='PENDING_CONTRACT_DRIFT'):
        require_initial_state_alignment(state,bad,identity,evidence_scope='REAL_DATA')
    bad=deepcopy(args);bad['requests'][0].metadata['episode_id']='wrong'
    with pytest.raises(ValueError,match='INITIAL_EPISODE_DRIFT'):
        require_initial_state_alignment(state,bad,identity,evidence_scope='REAL_DATA')


def test_normalized_initial_row_cannot_change_the_approved_site(approved):
    raw,state,args,identity=approved
    bad=deepcopy(state);driver=deepcopy(args)
    bad['running'][0]['site']='AIDC12' if bad['running'][0]['site']!='AIDC12' else 'AIDC01'
    request,_,start=driver['running'][0]
    driver['running'][0]=(request,bad['running'][0]['site'],start)
    with pytest.raises(ValueError,match='SOURCE_ROW_DRIFT:running'):
        require_initial_state_alignment(bad,driver,identity,evidence_scope='REAL_DATA')


def test_normalized_initial_cannot_claim_kestrel_site_observation(approved):
    raw,state,args,identity=approved
    bad=deepcopy(state);bad['KESTREL_OBSERVED_SITE']=True
    with pytest.raises(ValueError,match='SOURCE_AUTHORITY_DRIFT:KESTREL_OBSERVED_SITE'):
        require_initial_state_alignment(bad,args,identity,evidence_scope='REAL_DATA')


def test_initial_source_and_driver_cannot_duplicate_or_resubmit_uid(approved):
    raw,state,args,identity=approved
    bad=deepcopy(state);bad['pending'].append(bad['pending'][0])
    with pytest.raises(ValueError,match='DUPLICATE_BOUNDARY_UID'):
        require_initial_state_alignment(bad,args,identity,evidence_scope='REAL_DATA')
    driver=deepcopy(args);driver['requests'].append(driver['requests'][0])
    with pytest.raises(ValueError,match='DUPLICATE_OR_RESUBMITTED_UID'):
        require_initial_state_alignment(state,driver,identity,evidence_scope='REAL_DATA')
    driver=deepcopy(args);driver['requests'].append(driver['running'][0][0])
    with pytest.raises(ValueError,match='DUPLICATE_OR_RESUBMITTED_UID'):
        require_initial_state_alignment(state,driver,identity,evidence_scope='REAL_DATA')


@pytest.mark.parametrize('population',['running','pending'])
def test_initial_public_service_and_site_compatibility_cannot_drift(approved,population):
    raw,state,args,identity=approved
    driver=deepcopy(args)
    request=driver['running'][0][0] if population=='running' else driver['requests'][0]
    alter_request(driver,population,q50=request.q50+900)
    with pytest.raises(ValueError,match='INITIAL_Q50_DRIFT'):
        require_initial_state_alignment(state,driver,identity,evidence_scope='REAL_DATA')
    driver=deepcopy(args)
    request=driver['running'][0][0] if population=='running' else driver['requests'][0]
    alter_request(driver,population,compatible=('AIDC01',))
    with pytest.raises(ValueError,match='INITIAL_COMPATIBILITY_DRIFT'):
        require_initial_state_alignment(state,driver,identity,evidence_scope='REAL_DATA')


def test_running_submit_cannot_change_while_copying_original_episode_id(approved):
    raw,state,args,identity=approved
    driver=deepcopy(args);alter_request(driver,'running',submit=driver['running'][0][0].submit+1)
    with pytest.raises(ValueError,match='INITIAL_SUBMIT_DRIFT'):
        require_initial_state_alignment(state,driver,identity,evidence_scope='REAL_DATA')


@pytest.fixture(scope='module')
def continuation(approved):
    from v42_integration.may01_boundary_reconciliation import (
        file_record,build_running_continuation_certificate,
    )
    from v42_integration.known_commands import compile_known_commands
    a_path=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/A1/A_RESULT.json')
    native=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    a=json.loads(a_path.read_text(encoding='utf8'))
    raw,state,args,identity=approved
    issue=1746000000.
    commands=compile_known_commands(a['selected_jobs'],slot_zero_seconds=issue)
    proof=build_running_continuation_certificate(file_record(a_path),file_record(native),
        state['source_record'],issue_seconds=issue,commands=commands,
        expected_semantic_sha=identity['initial_state_sha'])
    state=deepcopy(state);state['running_continuation_certificate']=proof
    identity=dict(identity,stage_case_sha=a['case_sha'])
    return commands,state,args,identity


def test_running_continuation_coordinate_does_not_retime_pending_or_pass_full_prefix(continuation):
    from v42_integration.followup_contract import validate_known_boundary
    from v42_integration.unified_contract import digest
    commands,state,args,identity=continuation
    before=digest(commands)
    result=validate_known_boundary(commands,state,begin_seconds=args['begin'],continuation_identity=identity)
    assert len(result['verified_issue_running_continuation_UIDs'])==103
    assert len(result['past_commands_without_observed_execution_UIDs'])==886
    assert len(result['observed_execution_command_mismatch_UIDs'])==151
    assert result['status']=='NOT_CERTIFIED' and not result['commands_retimed']
    assert digest(commands)==before


def test_running_continuation_requires_explicit_case_and_exact_source_revalidation(continuation):
    from v42_integration.followup_contract import validate_known_boundary
    commands,state,args,identity=continuation
    with pytest.raises(ValueError,match='CONTINUATION_EXPLICIT_STAGE_INITIAL_BINDING_REQUIRED'):
        validate_known_boundary(commands,state,begin_seconds=args['begin'])
    wrong=dict(identity,stage_case_sha='0'*64)
    with pytest.raises(ValueError,match='CERTIFICATE_BINDING_DRIFT'):
        validate_known_boundary(commands,state,begin_seconds=args['begin'],continuation_identity=wrong)
    bad=deepcopy(state);bad['running_continuation_certificate']['rows'][0]['gpu']+=1
    with pytest.raises(ValueError,match='CERTIFICATE_BINDING_DRIFT'):
        validate_known_boundary(commands,bad,begin_seconds=args['begin'],continuation_identity=identity)
