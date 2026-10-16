"""Barrier and exact-scope solver policy regression; no optimizer calls."""
import pytest
import subprocess
from v44 import barrier,cap300
from v44.common import record,atomic,digest,read


def mock_campaign_run(root,permit,*,resume=False):
    assert resume is False
    atomic(root/'requests/case.json',dict(case_root=str(root/'case')))
    return subprocess.Popen(['python','-u','-m','v44.campaign','--worker',str(root/'requests/case.json')])


@pytest.mark.parametrize('day,stage,arm,robust,gap',[
    ('2025-05-01','M1','B2',False,.03),('2025-05-02','M1','B2',True,.03),
    ('2025-05-02','M2','B3',False,.005),('2025-05-02','M1','B3',False,.005),
    ('2025-05-02','A1','B1',False,.005),('2025-05-03','M1','B2',False,.03)])
def test_root_remains_barrier_and_only_b2_joint_gap_changes(day,stage,arm,robust,gap):
    original=dict(Method=2,MIPGap=.005,FeasibilityTol=1e-9,OptimalityTol=1e-9,
        IntFeasTol=1e-8,Threads=1,NumericFocus=3)
    expected=dict(original,MIPGap=gap)
    if robust:expected.update(BarHomogeneous=1,CrossoverBasis=1)
    assert barrier.parameters(original,day,stage,arm)==expected
    assert 'BarHomogeneous' not in original


def test_scoped_stage_uses_barrier_and_restores_original(tmp_path,monkeypatch):
    from v44.frozen.v43_mess.library import load
    from v44 import worker,budget
    engine=load()['m_engine'];source=record(engine.__file__)
    original=dict(engine.APPROVED_JOINT_PARAMETERS);solve=budget.StageBudget.solve
    def stage(request,aidc):return dict(engine.APPROVED_JOINT_PARAMETERS)
    monkeypatch.setattr(worker,'m_stage',stage)
    value=cap300.validate();value.update(numerical_overlay=barrier.overlay(),numerical_policy_sha=digest(barrier.overlay()))
    path=tmp_path/'permit.json';atomic(path,value)
    with barrier.install(path):
        result=worker.m_stage(dict(day='2025-05-02',arm='B2',stage='M1',case_root=str(tmp_path/'case')),None)
        assert result==dict(original,Method=2,MIPGap=.03,BarHomogeneous=1,CrossoverBasis=1)
        assert budget.StageBudget.solve is solve
    assert engine.APPROVED_JOINT_PARAMETERS==original and record(engine.__file__)==source
    assert read(tmp_path/'case/M1.NUMERICAL_POLICY.json')['fresh_M_stage'] is True


def test_dual_simplex_permit_cannot_authorize_barrier(tmp_path):
    from v44 import numeric
    value=cap300.validate();value.update(numerical_overlay=numeric.overlay(),numerical_policy_sha=digest(numeric.overlay()))
    path=tmp_path/'permit.json';atomic(path,value)
    with pytest.raises(PermissionError):barrier.validate(path)


def test_dispatch_uses_barrier_worker_and_fresh_campaign(tmp_path,monkeypatch):
    from v44 import campaign
    value=cap300.validate();value.update(numerical_overlay=barrier.overlay(),numerical_policy_sha=digest(barrier.overlay()))
    path=tmp_path/'permit.json';atomic(path,value)
    monkeypatch.setattr(campaign,'run',mock_campaign_run)
    commands=[]
    monkeypatch.setattr(subprocess,'Popen',lambda command,**kwargs:commands.append(command) or 'launched')
    assert barrier.coordinator_run(tmp_path/'new_campaign',path)=='launched'
    assert commands[0][3]=='v44.barrier'
    assert commands[0][-2:]==['--permit',str(path)]
    request=read(tmp_path/'new_campaign/requests/case.json')
    assert request['numerical_policy_sha']==digest(barrier.overlay())
    assert request['Joint_call_cap_seconds']==300.
    assert 'resume_of' not in request and 'resume_parent' not in request
