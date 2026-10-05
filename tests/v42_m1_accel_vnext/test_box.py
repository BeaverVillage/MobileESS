import numpy as np
import gurobipy as gp
from types import SimpleNamespace
from v42_m1_accel_vnext.box import initial_box,install,update

def test_box_is_exact_dual_constraint():
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    x=m.addVar(obj=2.);row=m.addConstr(x>=1.)
    state=initial_box(np.array([2.]),np.array([1.]),[0])
    install(SimpleNamespace(model=m,coupling=[row]),state);m.optimize()
    assert abs(m.ObjVal-2.)<1e-10
    assert abs(row.Pi-state['center'][0])<=state['width'][0]+1e-10
    m.dispose()

def test_true_dual_inside_frozen_box():
    t=np.array([-5.,0.,8.]);p=np.array([1.,0.,7.]);s=initial_box(t,p,[0,2])
    assert np.all(abs(t-s['center'])<=s['width'])
    assert update(s,t,1.,.999)['serious_steps']==1
    assert update(s,t,1.,1.)['null_steps']==1
    assert np.all(update(s,t,1.,1.)['width']==s['width']*.5)
