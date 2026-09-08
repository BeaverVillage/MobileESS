import json
import numpy as np
import gurobipy as gp
import pytest
from dayahead.v41r1.bounded_solver import BoundedLex,PolicyBudget
from dayahead.v41r1.early_stop import IMPROVEMENT_EPS,IMPROVEMENT_NOISE
from dayahead.v41r1.feasible_seed import row_audit

@pytest.fixture(autouse=True)
def synthetic_model_ordering(monkeypatch):
    """These fixtures have no feeder; exercise acceptance with their fixed order.

    Production ranking remains mandatory and is checked by the separate cached
    feeder ranking regression. Do not install a production fallback here.
    """
    from dayahead.v41 import physics_ranking
    def ordered(engine, groups, anchors):
        assert engine.context is None
        return groups, anchors
    monkeypatch.setattr(physics_ranking, 'reorder', ordered)
    monkeypatch.setattr(physics_ranking, 'record_acceptance', lambda *args: None)

def engine(tmp_path,delta=.0987654321):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    x=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]')
    rho=m.addVar(lb=.5,ub=.5,name='rho');p2=1604.-delta*x
    m.setObjective(p2);m.update()
    e=BoundedLex(m,[0,.5],tmp_path,PolicyBudget(1),allocation=[1],objective_expressions=[rho,p2])
    return m,e,x

def test_small_p2_gain_recovered_without_percentage_gap_or_optimality_proof(tmp_path):
    m,e,x=engine(tmp_path)
    try:
        r=e.optimize('P2')
        assert e.values[x.index]==1 and e.vector()[1]<1604.-IMPROVEMENT_EPS[1]
        assert all(c['SolutionLimit']==1 and c['constant_objective']==0 and not c['percentage_gap_on_P1_P5'] for c in r['solver_calls'])
        assert m.Params.MIPGap not in (0,.03) and not r['exact_optimum_certified']
        assert not any(c.ConstrName.startswith('FO_TEMPORARY') for c in m.getConstrs())
        assert row_audit(m,e.values)['status']=='PASS'
    finally:m.dispose()

def test_improvement_infeasible_does_not_invalidate_original_incumbent(tmp_path):
    m,e,x=engine(tmp_path,delta=0)
    try:
        r=e.optimize('P2');assert e.vector()==[.5,1604.]
        assert r['feasibility']['status']=='PASS'
        assert all(c['solution_count']==0 for c in r['solver_calls'])
    finally:m.dispose()

def test_semantic_rejection_keeps_incumbent_and_continues(tmp_path):
    m,e,x=engine(tmp_path)
    try:
        calls=[]
        def validate():
            calls.append(1)
            return dict(status='FAIL') if len(calls)==1 else dict(status='PASS')
        e.validator=validate;r=e.optimize('P2')
        assert e.rejected_proposals>=1 and len(e.history)>1 and e.values[x.index]==1
        assert e.history[0]['candidate_rejection'] and not e.history[0]['accepted']
    finally:m.dispose()

def test_equal_full_vector_and_noise_do_not_satisfy_improvement_search(tmp_path):
    m,e,x=engine(tmp_path,delta=1e-10)
    try:
        e.optimize('P2');assert e.values[x.index]==0
        assert IMPROVEMENT_NOISE[1]>1e-10
        assert IMPROVEMENT_EPS[1]<.0988/1000
    finally:m.dispose()

def test_coupled_pair_accepted_as_one_move_without_neutral_intermediate(tmp_path):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    a=m.addVar(vtype=gp.GRB.BINARY,name='choice[0,0]');b=m.addVar(vtype=gp.GRB.BINARY,name='choice[1,0]')
    m.addConstr(a==b,name='FULL_DESTINATION_CAPACITY_EXCHANGE')
    rho=1-.001*a;m.setObjective(rho);m.update()
    e=BoundedLex(m,[0,0],tmp_path,PolicyBudget(1),allocation=[1],objective_expressions=[rho])
    try:
        e.optimize('P1');assert e.values.tolist()==[1,1]
        assert len(e.accepted_improvements)==1
    finally:m.dispose()

def test_p2_cannot_give_back_an_incidental_p1_gain_inside_old_stage_cap(tmp_path):
    # Reproduces actual May-04 iteration 77: B improved P1 while solving P2;
    # C then improves P2 but gives back part of B's P1 gain. The old stage
    # cap from A permits C, while lexicographic incumbent acceptance forbids it.
    m=gp.Model();m.Params.OutputFlag=0;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    a,b,c=[m.addVar(vtype=gp.GRB.BINARY,name=f'choice[0,{k}]') for k in range(3)]
    m.addConstr(a+b+c==1)
    p1=.6*a+.5*b+.55*c;p2=1604*a+1603*b+1602*c
    m.addConstr(p1<=.6,name='OLDER_P1_STAGE_LOCK');m.setObjective(p2);m.update()
    e=BoundedLex(m,[1,0,0],tmp_path,PolicyBudget(2),allocation=[1],objective_expressions=[p1,p2])
    original=e._solve;calls=[]
    def first_B_then_C_available(seconds,label):
        if not calls:c.UB=0
        try:return original(seconds,label)
        finally:c.UB=1;calls.append(1)
    e._solve=first_B_then_C_available
    try:
        e.optimize('P2')
        assert e.values.tolist()==[0,1,0] and len(calls)>1
        assert len(e.accepted_improvements)==1
        assert not any(x.ConstrName.startswith('FO_TEMPORARY') for x in m.getConstrs())
    finally:m.dispose()
