"""The diagnostic permit preserves Actual limits and cannot authorize production."""
from pathlib import Path
import pytest
from v42_pr134_b1.common import atomic,digest,record,sha
from v42_common_campaign import VERSION
from v42_vmax1048 import POLICY,ATTEMPT,DAY,MANIFEST
from v42_vmax1048 import authority


@pytest.fixture
def diagnostic(tmp_path,monkeypatch):
    monkeypatch.setattr(authority,'ROOT',tmp_path)
    code=tmp_path/'v42_code.py';code.write_text('original=True\n',encoding='utf8')
    sources={'v42_code.py':sha(code)}
    evidence=tmp_path/'original.json';atomic(evidence,dict(unchanged=True))
    receipt=record(evidence)
    manifest=dict(schema='V42_VMAX1048_DIAGNOSTIC_MANIFEST_V1',run_id='diagnostic',
        code_root=str(tmp_path),execution_sources=sources,execution_SHA=digest(sources),
        algorithm_version=VERSION,planning_policy=POLICY,planning_voltage_min_pu=.95,
        planning_voltage_max_pu=1.048,planning_voltage_max_squared_pu=1.098304,
        actual_voltage_min_pu=.95,actual_voltage_max_pu=1.05,native_M_limit_seconds=1800,
        Threads=1,P2_calls=0,diagnostic_only=True,all31_policy_conversion_approved=False,
        A1_A2_policy_changed=False,input_folder=str(tmp_path/'inputs'),input_receipts=[receipt],
        original_May01_result=receipt,original_control_audit_verdict=receipt,
        permitted_existing_canary_manifest=receipt,source_qualification=receipt)
    path=tmp_path/MANIFEST;atomic(path,manifest)
    attempt=tmp_path/'dates/B2'/DAY/'attempts'/ATTEMPT
    request=dict(root=str(tmp_path),manifest=str(path),manifest_SHA=sha(path),
        source_SHA=manifest['execution_SHA'],run_id='diagnostic',arm='B2',day=DAY,
        attempt_id=ATTEMPT,worker_slot=3,canary=True,planning_policy=POLICY,
        algorithm_version=VERSION,planning_voltage_max_pu=1.048,actual_voltage_max_pu=1.05,
        native_budget_seconds=1800,wall_budget_seconds=None,Threads=1,P2_calls=0,
        input_folder=manifest['input_folder'],result=str(attempt/'RESULT.json'),
        progress=str(attempt/'progress.json'),output=str(attempt/'output'))
    return path,manifest,request,code,evidence


def test_actual_voltage_limit_cannot_be_replaced_by_planning_margin(diagnostic):
    path,manifest,request,_,_=diagnostic
    authority.verify_request(request)
    manifest['actual_voltage_max_pu']=1.048;atomic(path,manifest)
    with pytest.raises(PermissionError,match='POLICY_DRIFT'):authority.verify_manifest(path)


def test_squared_voltage_direct_pu_binding_is_rejected(diagnostic):
    path,manifest,_,_,_=diagnostic
    manifest['planning_voltage_max_squared_pu']=1.048;atomic(path,manifest)
    with pytest.raises(PermissionError,match='POLICY_DRIFT'):authority.verify_manifest(path)


def test_diagnostic_result_cannot_authorize_31day_conversion(diagnostic):
    path,manifest,_,_,_=diagnostic
    manifest['all31_policy_conversion_approved']=True;atomic(path,manifest)
    with pytest.raises(PermissionError,match='POLICY_DRIFT'):authority.verify_manifest(path)


def test_execution_or_frozen_evidence_mutation_blocks_native_admission(diagnostic):
    path,_,request,code,evidence=diagnostic
    evidence.write_text('altered',encoding='utf8')
    with pytest.raises(PermissionError,match='FILE_SHA_DRIFT'):authority.verify_request(request)
    code.write_text('changed=True',encoding='utf8')
    with pytest.raises(PermissionError,match='SOURCE_BYTES_DRIFT'):authority.verify_manifest(path)


def test_request_cannot_escape_attempt_or_change_day_budget(diagnostic):
    _,_,request,_,_=diagnostic
    for changes in ({'day':'2025-05-02'},{'native_budget_seconds':1801},
            {'result':str(Path(request['root'])/'another.json')},{'Threads':2}):
        wrong=dict(request,**changes)
        with pytest.raises(PermissionError):authority.verify_request(wrong)
