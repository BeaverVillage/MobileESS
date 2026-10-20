from contextlib import contextmanager
from fractions import Fraction
from types import SimpleNamespace
import inspect
import numpy as np
import scipy.sparse as sp
import pytest
from v44_recovery_r025.phase_stability import StableNative,policy,observe,stabilized_phase,_solve,PRIMARY,REPAIR
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective


def snapshot():
    return LinearSnapshot(sp.csr_matrix([[1.,1.]]),np.zeros(2),np.full(2,3.),np.array(['>']),np.ones(1),np.full(2,'C'),(Objective('Phi',((1,Fraction(1)),),0),)).require()


class Model:
    def __init__(self):
        self.NumIntVars=0;self.NumVars=2;self.Params=SimpleNamespace(FeasibilityTol=1e-6,OptimalityTol=1e-6,IntFeasTol=1e-5,MIPGap=.005,Seed=0,Threads=1,Method=2);self.attrs={}
    def setParam(self,k,v):setattr(self.Params,k,v)
    def setAttr(self,k,vars_,v):self.attrs[k]=v
    def getVars(self):return [0,1]
    def getAttr(self,k):return dict(Status=2,ConstrVio=0,BoundVio=0,DualVio=0,ComplVio=0,Kappa=100)[k]


@pytest.mark.parametrize('repair',[False,True])
def test_robust_policy_changes_algorithm_and_preserves_all_tolerances(tmp_path,repair):
    model=Model();old=vars(model.Params).copy();apply=policy(lambda m,p,g:dict(Method=2))
    seed=dict(X=np.array([0.,1.]))
    token=_solve.set(dict(folder=tmp_path,component='PHASE_I',repair=repair,seed=seed))
    try:result=apply(model,{},None)
    finally:_solve.reset(token)
    expected=REPAIR if repair else PRIMARY
    assert all(getattr(model.Params,k)==v for k,v in expected.items())
    for k in ['FeasibilityTol','OptimalityTol','IntFeasTol','MIPGap','Seed','Threads']:assert getattr(model.Params,k)==old[k]
    assert model.attrs['PStart']==[0.,1.] and result['R025_numerical_stability']


def test_no_numerical_scope_does_not_change_original_native_parameters():
    model=Model();apply=policy(lambda *a:dict(Method=2));assert apply(model,{},None)=={'Method':2}
    assert vars(model.Params).get('NumericFocus') is None


def test_numerical_quality_is_observed_without_any_extra_native_call(tmp_path):
    calls=[];context=dict(folder=tmp_path)
    token=_solve.set(context)
    try:assert observe(lambda model:calls.append(1) or 'done')(Model())=='done'
    finally:_solve.reset(token)
    assert calls==[1] and context['quality']['DualVio']==0


def test_worse_optimal_status_is_rejected_then_repaired_with_both_calls_charged(tmp_path):
    calls=[]
    class Native:
        used=0
        def remaining(self):return 5400-self.used
        def solve(self,snapshot,folder,component):
            context=_solve.get();calls.append(context['repair']);self.used+=1
            x=np.array([0.,2.]) if not context['repair'] else np.array([1.,0.])
            return dict(status=2,objective=x[1],native_seconds=1),dict(X=x,Pi=np.zeros(1),RC=np.array([0.,1.]))
    original=Native();facade=StableNative(original);s=snapshot();facade.admit_prior(s,np.array([0.,1.]))
    rec,raw=facade.solve(s,tmp_path,'PHASE_I')
    assert calls==[False,True] and original.used==2 and rec['native_seconds']==2
    assert raw['X'].tolist()==[1.,0.] and rec['numerical_attempts']==2


def test_both_bad_solutions_fail_closed_without_using_the_old_point_as_a_solver_result(tmp_path):
    class Native:
        def remaining(self):return 5400
        def solve(self,*args):return dict(status=2,native_seconds=1),dict(X=np.array([0.,2.]),Pi=np.zeros(1),RC=np.array([0.,1.]))
    facade=StableNative(Native());s=snapshot();facade.admit_prior(s,np.array([0.,1.]))
    with pytest.raises(ValueError,match='DOMINANCE_NOT_VERIFIED'):facade.solve(s,tmp_path,'PHASE_I')
    assert facade.seed['X'].tolist()==[0.,1.]


def test_prior_point_cannot_cross_an_input_matrix_change(tmp_path):
    from dataclasses import replace
    facade=StableNative(None);s=snapshot();facade.admit_prior(s,np.array([0.,1.]))
    with pytest.raises(ValueError,match='SNAPSHOT_IDENTITY_DRIFT'):facade.solve(replace(s,rhs=np.array([2.])),tmp_path,'PHASE_I')


def test_phase_body_preserved_except_admission_of_already_checked_prior_point():
    from v42_a_stage_canary import phase
    function=stabilized_phase(phase.run,dict(vars(phase)))
    assert inspect.getsource(function).replace('        native.admit_prior(fullnew.snapshot,included_point)\n','')==inspect.getsource(phase.run)


def test_explicit_user_restart_admitted_even_after_attempt003():
    from pathlib import Path
    from v44_recovery_r025.operations import needs_retry
    root=Path('D:/root/2025-05-02/B3/attempt003')
    assert needs_retry(root,dict(error='USER_REQUESTED_FRESH_A2_NUMERICAL_STABILITY_RESTART'))


def test_may02_b3_a2_keeps_its_running_revision_even_with_fresh_flag(monkeypatch):
    from v44 import worker
    from v44_recovery_r025 import phase_rebuild
    entered=[]
    @contextmanager
    def scope(request):entered.append(request['stage']);yield
    monkeypatch.setattr(phase_rebuild,'stage_scope',scope);monkeypatch.setattr(worker,'a_stage',lambda request,**kw:True)
    with phase_rebuild.install():assert worker.a_stage(dict(day='2025-05-02',arm='B3',stage='A2',fresh_a2_parent='original'))
    assert entered==['A2']
