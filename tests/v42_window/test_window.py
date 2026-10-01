from types import SimpleNamespace
import gurobipy as gp
import numpy as np
import pytest
from v42_window.common import arcs_for
from v42_window.grid import add_window
from v42_window.reachability import paired_paths
from v42_native.mess import RouteArc

@pytest.mark.parametrize('t1,t2',[(0,3),(1,2),(1,3),(2,3)])
def test_exact_pair_support_matches_all_complete_paths(t1,t2):
    from v42_m1_sparse.equivalence import route_patterns
    sites=('A','B');H=4;r=(RouteArc('trip','A','B',1,2,3,.1,'a'*64),)
    paths,arcs=route_patterns(sites,H,r,{'M':'A'});expected=set()
    for path in paths:
        states=[]
        for t in [t1,t2]:
            a=next(arcs[k] for k in path['M'] if arcs[k][1]<=t<arcs[k][3]);states.append(a[0] if a[-1] is None else 'TRANSIT')
        expected.add(tuple(states))
    actual=paired_paths(arcs,sites,'A',t1,t2,[*sites,'TRANSIT'],H)
    assert set(actual)==expected
    for (a,b),(_,path) in actual.items():
        loc='A';time=0
        for k in path:
            x=arcs[k];assert x[:2]==(loc,time);loc,time=x[2:4]
        assert time==H

def test_seven_slot_window_drops_outside_grid_but_keeps_inside_voltage():
    from v42_m1_sparse.equivalence import fixture
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage
    *_,base=fixture('all_stay');coeff=[]
    for t in range(8):
        c=SimpleNamespace(**vars(base[t%4]));c.slot=t;c.voltage_matrix=np.zeros_like(c.voltage_matrix);c.voltage_constant=np.ones_like(c.voltage_constant)
        coeff.append(c)
    authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
    coeff[0].voltage_constant[:]=1.1
    def solve(window):
        m=gp.Model();m.Params.OutputFlag=0;rho=add_window(m,coeff,[[0.]*7 for _ in coeff],authority,'M1-F3',[],[],window);m.setObjective(rho);m.optimize();status=m.Status;m.dispose();return status
    assert solve(range(1,8))==gp.GRB.OPTIMAL
    assert solve(range(8))==gp.GRB.INFEASIBLE
    coeff[3].voltage_constant[:]=1.1
    assert solve(range(1,8))==gp.GRB.INFEASIBLE

def test_window_retains_original_transformer_authority():
    from v42_m1_sparse.equivalence import fixture
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage
    *_,coeff=fixture('all_stay');coeff[2].transformer_ratings=[None,.1]
    m=gp.Model();m.Params.OutputFlag=0
    authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
    rho=add_window(m,coeff,[[0.]*7 for _ in coeff],authority,'M1-F3',[],[],[1,2,3]);m.setObjective(rho);m.optimize()
    assert m.Status==gp.GRB.INFEASIBLE;m.dispose()

def test_real_census_contains_all_seven_voltage_line_and_transformer_slots():
    from v42_window.common import OUT,read
    if not (OUT/'W7_MATRIX_CENSUS.json').exists():pytest.skip('real template not built')
    f=read(OUT/'W7_MATRIX_CENSUS.json')['rows_by_family']
    assert f['voltage_lower']==f['voltage_upper']==7*386
    assert f['line_thermal_face']==7*4208
    assert f['transformer_current']==7*48 and f['transformer_kVA']==7*1920

def test_certificate_box_does_not_modify_solver_domains():
    from v42_window.common import OUT,read
    if not (OUT/'W7_IMPLIED_AUXILIARY_BOUND_PROOF.json').exists():pytest.skip('real template not built')
    p=read(OUT/'W7_IMPLIED_AUXILIARY_BOUND_PROOF.json')
    assert p['PASS'] and not p['solver_bounds_changed'] and p['original_row_bindings_retained']
