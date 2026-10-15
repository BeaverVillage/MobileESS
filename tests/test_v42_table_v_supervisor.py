"""Native0 supervisor regression: no production solver entry points."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import vector_sha
from v42_integration.table_v_control import stop_request, require_running, CampaignStopped
from v42_integration.table_v_status import classify_a_result, failed_stage_status
from v42_integration.table_v_reuse import discover_a1_attempts


def test_user_stop_is_durable_idempotent_and_prevents_new_arm(tmp_path):
    from v42_integration.table_v_run import run_arm
    first=stop_request(tmp_path,reason='USER_STOP')
    assert stop_request(tmp_path,reason='SECOND_REQUEST')==first
    with pytest.raises(CampaignStopped):require_running(tmp_path)
    with pytest.raises(CampaignStopped):run_arm('B2',tmp_path)
    assert not (tmp_path/'B2').exists()


@pytest.mark.parametrize('native,expected',[(3,'INFEASIBLE_REPORTED_CURRENT_MATRIX'),
    (9,'TIME_LIMIT_NO_FEASIBLE'),(11,'INTERRUPTED_NO_FEASIBLE')])
def test_original_native_failure_is_not_collapsed(native,expected):
    result=dict(Native_call=dict(status=native),FULL_feasible=False,bound=.61,gap=None)
    assert classify_a_result(result)==expected
    assert failed_stage_status({'A1':{'result':result}},'A1')==expected
    assert result['gap'] is None


def test_milp_zero_gap_is_not_dw_global_certificate():
    result=dict(FULL_feasible=True,FULL_point_replay={'PASS':True},objective=.6,bound=.6,gap=0.)
    assert classify_a_result(result)=='FULL_FEASIBLE_OPTIMALITY_UNPROVEN'
    result.update(AIDC_Global_LB=.599,AIDC_Global_UB=.6,
                  DW=dict(LB_certified=True,full_domain_pricing_complete=True))
    assert classify_a_result(result)=='P1_GLOBAL_GAP_TARGET_MET'
    result['DW']['full_domain_pricing_complete']=False
    assert classify_a_result(result)=='FULL_FEASIBLE_OPTIMALITY_UNPROVEN'


def test_phase_one_and_pricing_failures_are_separate():
    assert classify_a_result(None)=='NOT_RUN'
    assert classify_a_result({'DW':{'phase_I_status':'NOT_CERTIFIED'}})=='DW_PHASE_I_NOT_CERTIFIED'
    assert classify_a_result({'DW':{'phase_I_status':'PHI_ZERO_CERTIFIED'}})=='DW_PRICING_INCOMPLETE'


def test_valid_weak_negative_lower_bound_is_certified_with_unmet_gap():
    result=dict(FULL_feasible=True,FULL_point_replay={'PASS':True},AIDC_Global_LB=-.01,AIDC_Global_UB=.6,
        DW=dict(LB_certified=True,full_domain_pricing_complete=True))
    assert classify_a_result(result)=='DW_GLOBAL_LB_CERTIFIED'


def candidate(root,name,context,*,native_seconds=1.):
    folder=root/'B1'/name/'A1' if name else root/'B1/A1'
    folder.mkdir(parents=True)
    point=np.array([1.,0.])
    binding=dict(matrix_sha='matrix',domain_sha='domain-includes-objective',objective_sense=1,rows=2,columns=2)
    full=dict(PASS=True,point_sha256=vector_sha(point))
    call=dict(solver='GUROBI',Native_Runtime=native_seconds,status=2,native_binding=binding,
        stage_context=dict(arm='B1',stage='A1',stage_case_sha='stage',source_sha='source'))
    result=dict(arm='B1',stage='A1',case_sha='stage',FULL_feasible=True,FULL_point_replay=full,
        source_identity=context['manifest']['identity'],D0_input_sha='input',native_binding=binding,
        domain_scope='ORIGINAL_SOURCE_AUTHORIZED_E1_FLEX30_FULL_DOMAIN',Native_call=call)
    acceptance=dict(schema='RELEASE_P1_ONLY_STAGE_ACCEPTANCE_V1',status='FULL_PASS',stage='A1',arm='B1',
        source_identity=context['manifest']['identity'],source_sha='source',result_sha=digest(result),
        P2_calls=0,P2_optimized=False,evidence_scope='REAL_PRODUCTION',native_binding=binding,
        point_sha256=vector_sha(point))
    acceptance['acceptance_sha']=digest(acceptance)
    (folder/'P1_ONLY_RESULT.json').write_text(json.dumps(result))
    (folder/'P1_ONLY_ACCEPTANCE.json').write_text(json.dumps(acceptance))
    np.savez_compressed(folder/'P1_ONLY_POINT.npz',point=point)
    return folder,call


def test_latest_verified_attempt_found_even_when_latest_pointer_failed(tmp_path):
    ctx=dict(manifest=dict(identity={'science_sha':'E1','case_sha':'D0'},source_sha='source'),input_audit={'a_input_sha':'input'})
    old,call=candidate(tmp_path,'',ctx)
    newest,call2=candidate(tmp_path,'ATTEMPT02',ctx,native_seconds=2.)
    (tmp_path/'PLANNING_NATIVE_LEDGER.json').write_text(json.dumps({'calls':[call,call2]}))
    (tmp_path/'B1/LATEST_ATTEMPT.json').write_text(json.dumps({'path':'ATTEMPT03'}))
    assert discover_a1_attempts(tmp_path,ctx)==(newest.resolve(),old.resolve())
    np.savez_compressed(newest/'P1_ONLY_POINT.npz',point=np.array([0.,1.]))
    assert discover_a1_attempts(tmp_path,ctx)==(old.resolve(),)
    (tmp_path/'PLANNING_NATIVE_LEDGER.json').write_text(json.dumps({'calls':[]}))
    assert discover_a1_attempts(tmp_path,ctx)==()


def test_prepare_does_not_invent_approval_or_touch_output(tmp_path):
    from v42_integration.table_v_run import prepare
    output=tmp_path/'unapproved'
    with pytest.raises(PermissionError,match='AUTHORIZATION_DOCUMENTS'):
        prepare(output)
    assert not output.exists()
