import numpy as np
import gurobipy as gp
import pytest
from v42_epigraph.common import arcs_for,state_indices,reachable_arcs
from v42_epigraph.oracle import finite_bound_certificate,add_slot_lines
from v42_native.mess import RouteArc

def test_transit_includes_departure_and_excludes_connection():
    r=RouteArc('a','A','B',1,2,3,.1,'a'*64);arcs=arcs_for(('A','B'),(r,),4)
    k=8
    assert k not in state_indices(arcs,0)['TRANSIT']
    assert k in state_indices(arcs,1)['TRANSIT']
    assert k in state_indices(arcs,2)['TRANSIT']
    assert k not in state_indices(arcs,3)['TRANSIT']
    assert state_indices(arcs,3)['B']==[7]

def test_reachability_uses_route_authority_and_initial_state():
    r=RouteArc('a','A','B',1,2,3,.1,'a'*64)
    reached=reachable_arcs(('A','B'),{'M':'A'},(r,),4)['M']
    assert 8 in reached and 7 in reached
    assert not ({4,5,6}&reached)

@pytest.mark.parametrize('pi',[np.array([0.]),np.array([.3]),np.array([100.]),np.array([-2.])])
def test_lagrangian_certificate_remains_lower_bound_with_inexact_duals(pi):
    m=gp.Model();m.Params.OutputFlag=0;x=m.addVar(lb=-4,ub=5);m.addConstr(x>=2);m.setObjective(x);m.optimize()
    bound,certificate,projected=finite_bound_certificate(m,pi)
    assert bound<=2. and certificate['roundoff_upper_bound']>=0
    assert projected[0]>=0;m.dispose()

def test_oracle_line_faces_are_original_affine_rows():
    from v42_m1_sparse.equivalence import fixture
    from v42_native.grid import GridAuthority,add_grid
    from v42_native.voltage import Stage
    _,_,_,_,_,coeff=fixture('multiple_movement_choices');c=coeff[0]
    authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
    old=gp.Model();new=gp.Model();old.Params.OutputFlag=new.Params.OutputFlag=0
    x1=old.addVars(len(c.control_names),lb=-10,ub=10);x2=new.addVars(len(c.control_names),lb=-10,ub=10)
    add_grid(old,[c],[[x1[i] for i in x1]],authority);rho=new.addVar(lb=0,ub=1);add_slot_lines(new,c,[x2[i] for i in x2],rho)
    old.update();new.update()
    ro=[r for r in old.getConstrs() if r.ConstrName=='line_thermal_face'];rn=new.getConstrs()
    assert len(ro)==len(rn)==16
    for a,b in zip(ro,rn):
        ea=old.getRow(a);eb=new.getRow(b)
        # Axis order, not auxiliary names, identifies the same controls and rho.
        aa={ea.getVar(i).index:ea.getCoeff(i) for i in range(ea.size())};bb={eb.getVar(i).index:eb.getCoeff(i) for i in range(eb.size())}
        assert aa.keys()==bb.keys()
        assert all(abs(aa[k]-bb[k])<1e-12 for k in aa)
        assert abs(a.RHS-b.RHS)<1e-12
    old.dispose();new.dispose()

def test_pair_marginals_force_unique_integer_cell():
    m=gp.Model();m.Params.OutputFlag=0;w=m.addVars(3,2,lb=0)
    for a in range(3):m.addConstr(gp.quicksum(w[a,b] for b in range(2))==int(a==1))
    for b in range(2):m.addConstr(gp.quicksum(w[a,b] for a in range(3))==int(b==0))
    m.setObjective(gp.quicksum((a+b+.5)*w[a,b] for a,b in w));m.optimize()
    assert w[1,0].X==1. and sum(abs(v.X) for k,v in w.items() if k!=(1,0))==0
    m.dispose()

def test_preregistered_oracle_does_not_inherit_strengthening_rows():
    from pathlib import Path
    from v42_epigraph.common import OUT,read
    if not (OUT/'O1_TEMPLATE_41.json').exists():pytest.skip('real template not built')
    r=read(OUT/'O1_TEMPLATE_41.json')
    assert r['full_horizon_native'] and not r['S1_S2_S3_carried'] and r['binaries']==0
