from types import SimpleNamespace
from pathlib import Path
import inspect
import numpy as np
import pytest
from scipy import sparse
import v44_recovery_r026f1
from v44.common import atomic,read,record,digest
from v44_recovery_r026f1 import strict_recovery as r


def test_nonvoltage_replay_keeps_thermal_bounds_and_integrality(monkeypatch):
    from v42_m1_research import check_ub
    monkeypatch.setattr(check_ub,'physical_replay',lambda case,x:dict(PASS=True))
    d=dict(row_names=np.array(['voltage_lower[0]','line_thermal_face[0]']),rhs=np.array([.95,1.]),
        sense=np.array(['>','<']),lower=np.array([0.]),upper=np.array([1.]),types=np.array(['B']),objective=np.zeros(1),constant=0.)
    case=SimpleNamespace(original_A=sparse.csr_matrix([[1.],[1.]]),original_d=d)
    assert r.nonvoltage_replay(case,np.array([0.]))['PASS']
    assert not r.nonvoltage_replay(case,np.array([.5]))['PASS']
    assert not r.nonvoltage_replay(case,np.array([2.]))['PASS']
    d['rhs'][1]=-.1
    assert not r.nonvoltage_replay(case,np.array([0.]))['PASS']


def signed_result(tmp_path):
    plan=dict(P_kW=[0]);plan['plan_sha']=digest(plan)
    atomic(tmp_path/'nonvoltage.json',dict(PASS=True));atomic(tmp_path/'voltage.json',dict(PASS=False))
    handoff=dict(PASS=True,day='2025-05-02',arm='B3',source_sha='source',MESS_plan_sha=plan['plan_sha'],nonvoltage_PASS=True,
        Actual_Fresh_original_strict_voltage_required=True,nonvoltage_receipt=record(tmp_path/'nonvoltage.json'),
        evidence=[record(tmp_path/'voltage.json'),record(tmp_path/'nonvoltage.json')])
    atomic(tmp_path/'handoff.json',handoff)
    return dict(day='2025-05-02',arm='B3',source_sha='source',MESS_plan=plan,FULL_feasible=False,
        global_gap_certified=False,actual_voltage_diagnostic_handoff=record(tmp_path/'handoff.json'))


def test_explicit_diagnostic_admission_is_independent_of_m2_voltage_PASS(tmp_path):
    result=signed_result(tmp_path);r.require_actual(result,'B3')
    assert result['FULL_feasible'] is False
    result['MESS_plan']['P_kW']=[1]
    with pytest.raises(PermissionError,match='PLAN_SHA'):r.require_actual(result,'B3')


@pytest.mark.parametrize('change',[dict(FULL_feasible=True),dict(global_gap_certified=True),dict(source_sha='changed'),dict(arm='B1')])
def test_diagnostic_cannot_forge_full_gap_source_or_arm(tmp_path,change):
    result=signed_result(tmp_path);result.update(change)
    with pytest.raises((ValueError,PermissionError)):r.require_actual(result,'B3')


def test_diagnostic_rejects_tampered_nonvoltage_receipt(tmp_path):
    result=signed_result(tmp_path);atomic(tmp_path/'nonvoltage.json',dict(PASS=False))
    with pytest.raises(Exception):r.require_actual(result,'B3')


def test_original_corrective_driver_only_changes_mess_admission():
    import v43_corrective.compare as original
    routed=r.diagnostic_driver(original.run)
    source=inspect.getsource(routed)
    assert '_r026f1_require_actual(result,arm)' in source
    assert 'fresh=oracle.full_fresh_probe(rows)' in source
    assert inspect.getsource(original.run).count('FROZEN_ARM_FULL_MESS_REQUIRED')==1


def test_m2_no_full_solution_uses_validated_operating_plan_then_actual(tmp_path,monkeypatch):
    from v44 import worker,runtime,checkpoints
    root=tmp_path/'M2';root.mkdir();request=dict(stage='M2',arm='B3',day='2025-05-02',root=str(root),
        case_root=str(tmp_path),source_sha='source')
    plan=dict(P_kW=[0]);plan['plan_sha']=digest(plan)
    monkeypatch.setattr(runtime,'build',lambda *a,**kw:SimpleNamespace(case_sha='case'))
    def stage(current,aidc):
        runtime.build(aidc,current)
        return dict(PASS=False,FULL_feasible=False,M_stage_execution_PASS=True,implementation_errors=[],allow_downstream=False,
            status='NO_FULL_FEASIBLE_INCUMBENT',arm='B3',day=current['day'],source_sha='source',MESS_plan=None)
    monkeypatch.setattr(worker,'m_stage',stage)
    monkeypatch.setattr(checkpoints,'seal_stage',lambda *a:None)
    monkeypatch.setattr(r,'parent_operating_point',lambda *a:(plan,dict(PASS=True)))
    monkeypatch.setattr(r,'voltage_report',lambda *a:dict(PASS=False,strict_PASS=False))
    with r.install():result=worker.m_stage(request,{})
    assert result['allow_downstream'] is True and result['PASS'] is False and result['FULL_feasible'] is False
    assert result['M2_voltage_recovery_failure_is_case_failure'] is False
    assert read(root/'M2_STRICT_VOLTAGE_RECOVERY.json')['PASS'] is False
    r.require_actual(result,'B3')


def test_m2_nonvoltage_failure_still_blocks_actual(tmp_path,monkeypatch):
    from v44 import worker,runtime,checkpoints
    root=tmp_path/'M2';root.mkdir();request=dict(stage='M2',arm='B3',day='2025-05-02',root=str(root),source_sha='source')
    monkeypatch.setattr(runtime,'build',lambda *a,**kw:SimpleNamespace(case_sha='case'))
    def stage(current,aidc):
        runtime.build(aidc,current)
        return dict(status='NO_FULL',M_stage_execution_PASS=True,implementation_errors=[],allow_downstream=False)
    monkeypatch.setattr(worker,'m_stage',stage)
    def rejected(*a):raise ValueError('R026F1_M1_PLAN_FAILS_CURRENT_A2_NONVOLTAGE_CONSTRAINTS')
    monkeypatch.setattr(r,'parent_operating_point',rejected)
    with r.install(),pytest.raises(ValueError,match='NONVOLTAGE'):worker.m_stage(request,{})
