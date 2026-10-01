"""Exact grid extension checks with unrestricted signed injections."""
import numpy as np
import pytest
import gurobipy as gp
from v42_m1_sparse.grid import add_compressed,response,map_bindings
from v42_native.grid import add_grid,GridAuthority
from v42_native.voltage import Stage

@pytest.mark.parametrize('case',['PR105_overvoltage','one_movement','multiple_MESS_same_site','near_PCS_boundary','SOC_limited'])
def test_bounded_projection(case):
    from v42_m1_sparse.equivalence import compare_case
    old=compare_case(case,'M1-F0');new=compare_case(case,'M1-FCRA')
    assert len(old)==len(new)
    for a,b in zip(old,new):
        assert a['route']==b['route'] and a['feasible']==b['feasible']
        if a['feasible']:assert np.allclose(a['scores'],b['scores'],rtol=0,atol=1e-5)

def test_signed_auxiliaries_and_start_mapping_are_equalities_only():
    m=gp.Model();m.Params.OutputFlag=0
    try:
        p=m.addVar(lb=-10,ub=10,name='p');q=m.addVar(lb=-10,ub=10,name='q');bindings=[]
        a=response(m,'response_test[0]',2*p-3*q+4,bindings);m.update()
        values={'p':-2.,'q':3.};map_bindings(bindings,values)
        assert values[a.VarName]==-9 and np.isneginf(a.LB) and np.isposinf(a.UB)
        assert p.LB==-10 and p.UB==10 and q.LB==-10 and q.UB==10
        assert m.NumConstrs==1 and m.getConstrs()[0].Sense=='='
    finally:m.dispose()

def test_one_use_current_and_unprofitable_constant_faces_are_unfactored():
    from v42_m1_sparse.equivalence import fixture
    _,_,_,_,_,coeff=fixture('transformer_kVA_binding')
    m=gp.Model();m.Params.OutputFlag=0;bindings=[];cost=[]
    try:
        controls=[[0.]+[m.addVar(lb=-10,ub=10) for _ in range(6)] for c in coeff]
        authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
        add_compressed(m,coeff,controls,authority,'M1-FCRA',bindings,cost);m.update()
        assert all(r['new_occurrences']<r['old_occurrences'] for r in cost if r['selected'])
        assert not any(r['selected'] for r in cost if r['family']=='transformer_current')
        assert not any(r['selected'] for r in cost if r['family']=='transformer_kVA')
    finally:m.dispose()

@pytest.mark.parametrize('root_seconds,complete,expected',[(60.,True,False),(301.,True,True),(600.,False,True)])
def test_optional_four_thread_gate_uses_actual_root_lp_not_cut_wall(root_seconds,complete,expected):
    from v42_m1_sparse.thread_policy import extra_allowed
    p={'root':{'seconds':root_seconds,'LP_complete':complete,'status':'objective 0.3' if complete else 'time limit'},'status':9,'root_processing_wall_seconds':600.}
    assert extra_allowed(p)==expected

def test_zero_intervention_has_exact_optimum_certificate_without_hiding_unknown_bound():
    from v42_m1_sparse.quality import certified_gap
    from v42_two.contract import relative_gap
    assert certified_gap(0.,0.)==0.
    assert certified_gap(0.,None) is None
    assert certified_gap(0.,-.1) is None
    assert certified_gap(.6696147314213984,.28011314354280115)==relative_gap(.6696147314213984,.28011314354280115)
