"""Numerical overlay boundaries; no optimizer calls."""
from pathlib import Path
import pytest
from v44 import numeric, cap300
from v44.common import atomic, read, record, digest


@pytest.mark.parametrize('day,stage,method',[
    ('2025-05-01','M1',2),('2025-05-02','M1',1),('2025-05-02','M2',1),
    ('2025-05-02','A1',2),('2025-05-03','M1',2)])
def test_only_may02_joint_method_changes(day,stage,method):
    original=dict(Method=2,Threads=1,FeasibilityTol=1e-9,OptimalityTol=1e-9,
        IntFeasTol=1e-8,NumericFocus=3,ScaleFlag=2,MIPGap=.005)
    before=dict(original)
    selected=numeric.parameters(original,day,stage)
    assert selected.pop('Method') == method
    assert selected == {k:v for k,v in before.items() if k!='Method'}
    assert original == before


def test_permit_rejects_numerical_or_source_drift(tmp_path):
    value=cap300.validate()
    value.update(numerical_overlay=numeric.overlay(),numerical_policy_sha=digest(numeric.overlay()))
    path=tmp_path/'permit.json'
    atomic(path,value)
    assert numeric.validate(path)['numerical_policy_sha'] == value['numerical_policy_sha']
    value['numerical_overlay']['parameter_changes']['FeasibilityTol']=1e-5
    value['numerical_policy_sha']=digest(value['numerical_overlay'])
    atomic(path,value)
    with pytest.raises(PermissionError):numeric.validate(path)


def test_scope_restores_parameters_and_frozen_sources(tmp_path):
    from v44.frozen.v43_mess.library import load
    from v44 import worker
    engine=load()['m_engine']
    frozen=record(engine.__file__)
    original=dict(engine.APPROVED_JOINT_PARAMETERS)
    stage=worker.m_stage
    value=cap300.validate()
    value.update(numerical_overlay=numeric.overlay(),numerical_policy_sha=digest(numeric.overlay()))
    path=tmp_path/'permit.json';atomic(path,value)
    with numeric.install(path):
        assert worker.m_stage is not stage
        assert engine.APPROVED_JOINT_PARAMETERS == original
        assert record(engine.__file__) == frozen
    assert worker.m_stage is stage
    assert engine.APPROVED_JOINT_PARAMETERS == original
    assert record(engine.__file__) == frozen


@pytest.mark.parametrize('day,method',[('2025-05-01',2),('2025-05-02',1)])
def test_real_stage_wrapper_records_only_scoped_solver_change(tmp_path,monkeypatch,day,method):
    from v44.frozen.v43_mess.library import load
    from v44 import worker, budget
    engine=load()['m_engine']
    original=dict(engine.APPROVED_JOINT_PARAMETERS)
    solve=budget.StageBudget.solve
    def fake_stage(request,aidc):
        assert 'resume_parent' not in request
        return dict(engine.APPROVED_JOINT_PARAMETERS)
    monkeypatch.setattr(worker,'m_stage',fake_stage)
    value=cap300.validate()
    value.update(numerical_overlay=numeric.overlay(),numerical_policy_sha=digest(numeric.overlay()))
    path=tmp_path/'permit.json';atomic(path,value)
    request=dict(day=day,stage='M1',case_root=str(tmp_path/'case'))
    with numeric.install(path):
        result=worker.m_stage(request,None)
        assert result['Method']==method
        assert budget.StageBudget.solve is solve
    result.pop('Method')
    assert result=={k:v for k,v in original.items() if k!='Method'}
    receipt=read(tmp_path/'case/M1.NUMERICAL_POLICY.json')
    assert receipt['fresh_M_stage'] is True
    assert receipt['effective_Joint_parameters']['Method']==method
