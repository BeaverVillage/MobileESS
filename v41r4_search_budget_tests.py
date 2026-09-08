import json
import pytest
import numpy as np
import gurobipy as gp
from v41r4_search_budget import SearchBudget,SearchSweep,SearchBoundedLex,OriginalBudget,engine
from dayahead.v41r1.early_stop import FAMILIES


def test_non_search_work_cannot_exhaust_search_allowance():
    b=SearchBudget(1800)
    for name in ('PREPARATION','MODEL_BUILD','VALIDATE_AND_PERSIST','REPORTING','SUPERVISOR'):
        b.charge(3600,name)
    assert b.used==0 and b.remaining==1800
    b.charge_solver(12.5,'P1:F_AND_O',wall_call_seconds=12.7)
    assert b.used==12.5 and b.remaining==1787.5
    assert sum(c['seconds'] for c in b.calls)==12.5
    assert len(b.excluded_calls)==5
    with pytest.raises(AssertionError):b.charge(1,'P1:F_AND_O')


@pytest.mark.parametrize('priority',range(5))
@pytest.mark.parametrize('improve_late',[False,True])
def test_last_improvement_requires_a_new_complete_predefined_sweep(priority,improve_late):
    s=SearchSweep(priority,0)
    used=0.
    if improve_late:
        for _ in FAMILIES[:-1]:
            used=s.family_deadline+1e-6;s.observe(used,False)
        assert not s.reason
    used+=.1;s.observe(used,True)
    assert s.completed_no_improvement_sweeps_since_last_material==0 and not s.reason
    seen=[]
    for _ in FAMILIES:
        seen.append(s.family);used=s.family_deadline+1e-6;s.observe(used,False)
    assert set(seen)==set(FAMILIES)
    assert s.completed_no_improvement_sweeps_since_last_material==1
    assert s.reason=='LOCAL_STAGNATION_COMPLETE_NO_IMPROVEMENT_SWEEP'
    assert s.diversification_started==0


@pytest.mark.parametrize('priority',range(5))
def test_time_limit_after_recent_improvement_is_uncertified(priority):
    s=SearchSweep(priority,0)
    s.observe(s.family_deadline+.1,False)
    s.observe(s.family_deadline+.2,True)
    s.observe(s.last_material_search_seconds+.01,False)
    s.finish(s.last_material_search_seconds+.02,'STAGE_SOFT_GUARD_REACHED')
    assert s.reason=='TIME_LIMIT_UNCERTIFIED'
    assert not s.metrics()['stagnation_sweep_requirement_satisfied']
    assert not s.metrics()['global_convergence_certified']


def test_real_solver_runtime_ledger_and_model_restoration(tmp_path,monkeypatch):
    from dayahead.v41 import physics_ranking
    monkeypatch.setattr(physics_ranking,'reorder',lambda e,o,a:(o,a))
    monkeypatch.setattr(physics_ranking,'record_acceptance',lambda *args:None)
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4
    x=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]')
    y=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,1]')
    m.addConstr(x+y==1);m.setObjective(x+2*y);m.update()
    b=SearchBudget(.3);b.charge(100000,'MODEL_BUILD')
    e=SearchBoundedLex(m,np.array([1.,0.]),tmp_path,b,allocation=[1],
        metadata={0:dict(candidate_count=2,members=['fixture'])})
    before=(m.NumVars,m.NumConstrs,m.getA().toarray().copy())
    e.search_spec=dict(priority=0,incumbent=1.,absolute_improvement=1e-8,rhs=1.-1e-8,independent_noise_tolerance=1e-9)
    values,data=e._solve(.1,'P1:F_AND_O')
    assert b.used>=0 and b.used==data['solver_runtime_seconds']==sum(c['solver_runtime_seconds'] for c in b.calls)
    assert b.used < 1. and b.excluded_calls
    assert m.NumVars==before[0] and m.NumConstrs==before[1]
    np.testing.assert_array_equal(m.getA().toarray(),before[2])
    np.testing.assert_array_equal(e.values,[1.,0.])
    assert len(b.calls)==1 and b.report()['actual_search_seconds']==b.used
    np.testing.assert_array_equal(values,[1.,0.])
    m.dispose()


def test_original_mess_budget_still_charges_wall_work():
    b=OriginalBudget(1800);b.charge(123,'MODEL_BUILD')
    assert b.used==123 and b.remaining==1677


def test_p1_soft_allocation_cannot_end_an_unfinished_sweep(tmp_path):
    from types import SimpleNamespace
    m=gp.Model();m.Params.OutputFlag=0
    x=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]');m.setObjective(x);m.update()
    e=SearchBoundedLex(m,np.array([0.]),tmp_path,SearchBudget(1800),context=SimpleNamespace())
    assert e.nominal_stage_deadlines[0]==900
    np.testing.assert_array_equal(e.deadlines,np.full(5,1800.))
    m.dispose()


if __name__=='__main__':
    from fast_prepare import ROOT
    root=ROOT/'frozen_artifacts/v41r4_may/search_time_v3/audit/regression'
    root.mkdir(parents=True,exist_ok=True)
    raise SystemExit(pytest.main([__file__,'-q','--junitxml='+str(root/'SEARCH_BUDGET_TESTS.xml'),
        '--basetemp='+str(root/'fixtures'),'-o','cache_dir='+str(ROOT/'logs/v41r4_may/search_time_v3/pytest_cache')]))
