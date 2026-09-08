import time
import pytest
import numpy as np
import gurobipy as gp
from v41r4_loop_budget import LoopBudget,LoopBoundedLex,ContinuousSweep,OriginalBudget,OriginalBoundedLex,engine


def test_continuous_clock_counts_all_loop_work_once():
    now=[0.];b=LoopBudget(1800,lambda:now[0])
    now[0]=3600;b.charge(3600,'PREPARATION');assert b.used==0
    b.start_loop()
    for label in ('CANDIDATE','RANKING','ELECTRICAL','SOLVER','VALIDATION','PERSISTENCE','LOOP_OVERHEAD'):
        now[0]+=10;b.charge(10,label)
    assert b.used==70 and b.remaining==1730
    now[0]+=1730;assert b.used==1800 and b.remaining==0
    b.stop_loop();now[0]+=300;assert b.elapsed==1800


@pytest.mark.parametrize('priority',range(5))
def test_full_sweeps_and_floors_never_stop_early(priority):
    s=ContinuousSweep(priority,0)
    for n in range(30):
        s.observe(s.family_deadline+.001,False)
        assert s.reason is None
    assert s.normal_completed>=3
    if priority<4:assert s.diversification_completed>=3
    s.observe(s.family_deadline+.001,True);assert not s.reason
    from v41r4_loop_budget import _optimize
    assert _optimize.__globals__['objective_floor'](priority,[0]*5,production_verified=True) is None
    s.finish(1800,'POLICY_DAY_HARD_CAP_REACHED');assert s.reason=='SEARCH_LOOP_WALL_CLOCK_LIMIT'


def fixture(tmp_path,budget):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4
    x=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]');y=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,1]')
    m.addConstr(x+y==1);m.setObjective(x+2*y);m.update()
    e=engine(m,np.array([1.,0.]),tmp_path,budget,allocation=[1],metadata={0:dict(candidate_count=2,members=['fixture'])})
    return m,e


def test_real_gurobi_loop_uses_full_wall_time_and_restores_model(tmp_path,monkeypatch):
    from dayahead.v41 import physics_ranking
    monkeypatch.setattr(physics_ranking,'reorder',lambda e,o,a:(o,a));monkeypatch.setattr(physics_ranking,'record_acceptance',lambda *a:None)
    b=LoopBudget(.8);m,e=fixture(tmp_path,b)
    assert isinstance(e,LoopBoundedLex)
    original=e._choose
    def slow_ranking(priority):time.sleep(.01);return original(priority)
    monkeypatch.setattr(e,'_choose',slow_ranking)
    before=m.getA().toarray().copy();started=time.perf_counter();r=e.optimize('P1');wall=time.perf_counter()-started
    assert b.used==.8 and b.elapsed>=.8 and wall>=.8 and wall<3
    assert r['termination_reason']=='SEARCH_LOOP_WALL_CLOCK_LIMIT' and r['neighborhoods_solved']>1
    assert sum(c['solver_runtime_seconds'] for c in r['solver_calls'])<b.used
    np.testing.assert_array_equal(m.getA().toarray(),before);np.testing.assert_array_equal(e.values,[1.,0.])
    assert m.NumVars==2 and m.NumConstrs==1
    m.dispose()


def test_no_solver_call_after_deadline_and_original_rows_retained(tmp_path):
    now=[0.];b=LoopBudget(1,lambda:now[0]);m,e=fixture(tmp_path,b)
    e.search_spec=dict(priority=0,incumbent=1.,rhs=1.-1e-8)
    b.start_loop();now[0]=2
    values,data=e._solve(.1,'P1:F_AND_O')
    assert data['termination']=='WALL_CLOCK_EXPIRED_BEFORE_SOLVER_ENTRY'
    assert data['solver_runtime_seconds']==0 and m.NumConstrs==1
    np.testing.assert_array_equal(values,[1.,0.]);m.dispose()


def test_lex_stage_allocations_and_mess_engine_unchanged(tmp_path):
    from types import SimpleNamespace
    m=gp.Model();m.Params.OutputFlag=0;x=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]');m.setObjective(x);m.update()
    e=LoopBoundedLex(m,[0.],tmp_path/'aidc',LoopBudget(1800),context=SimpleNamespace())
    np.testing.assert_array_equal(e.deadlines,[900,1380,1560,1680,1800])
    b=OriginalBudget(1800);b.charge(123,'MODEL_BUILD');assert b.used==123
    original=engine(m,[0.],tmp_path/'mess',b);assert type(original) is OriginalBoundedLex
    m.dispose()


def test_both_aidc_dispatches_use_loop_budget_and_cold_seed():
    from pathlib import Path
    s=Path('v41r4_loop_runtime.py').read_text()
    assert 'ctx.v41_policy_budget=LoopBudget(1800.)' in s and 'bounded_solver.PolicyBudget=LoopBudget' in s
    recovery=s[s.index('def recovery('):s.index('def install_reports(')]
    assert 'previous_B1_reuse=False' in recovery and 'PREVIOUS_RUN' not in recovery


def test_late_validated_proposal_cannot_replace_deadline_incumbent(tmp_path,monkeypatch):
    from dayahead.v41 import physics_ranking
    monkeypatch.setattr(physics_ranking,'reorder',lambda e,o,a:(o,a));monkeypatch.setattr(physics_ranking,'record_acceptance',lambda *a:None)
    b=LoopBudget(.3);m,e=fixture(tmp_path,b);e.values=np.array([0.,1.])
    def slow_validation():time.sleep(.4);return dict(status='PASS')
    e.validator=slow_validation;r=e.optimize('P1')
    assert b.used==.3 and e.rejected_proposals>=1
    np.testing.assert_array_equal(e.values,[0.,1.]);assert not e.accepted_improvements
    m.dispose()


def test_all_five_stages_share_one_continuous_full_budget(tmp_path,monkeypatch):
    from dayahead.v41 import physics_ranking
    monkeypatch.setattr(physics_ranking,'reorder',lambda e,o,a:(o,a));monkeypatch.setattr(physics_ranking,'record_acceptance',lambda *a:None)
    b=LoopBudget(1.5);m,e=fixture(tmp_path,b)
    e.expressions=[m.getObjective()]*5;e.deadlines=np.array([.5,.8,1.,1.2,1.5])
    for i in range(5):e.optimize(f'P{i+1}')
    assert b.used==1.5 and len(b.stages)==5
    assert all(s['neighborhoods_solved']>0 for s in b.stages)
    assert all('CONVERGENCE' not in s['termination_reason'] for s in b.stages)
    m.dispose()


if __name__=='__main__':
    from fast_prepare import ROOT
    out=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4/audit/regression';out.mkdir(parents=True,exist_ok=True)
    raise SystemExit(pytest.main([__file__,'-q','--junitxml='+str(out/'LOOP_WALL_TESTS.xml'),
        '--basetemp='+str(ROOT/'frozen_artifacts/loop_wall_test'),'-o','cache_dir='+str(ROOT/'logs/v41r4_may/loop_wall_v4/pytest_cache')]))
