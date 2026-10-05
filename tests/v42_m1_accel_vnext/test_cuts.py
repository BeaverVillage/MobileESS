import gurobipy as gp
import numpy as np
from v42_m1_accel_vnext.cuts import eliminate_duals

def objective(integer,cuts):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    x=m.addVars(2,vtype='B' if integer else 'C',ub=1);mode=m.addVar(vtype='B' if integer else 'C',ub=1)
    c=m.addVars(2,ub=1);d=m.addVars(2,ub=1)
    m.addConstr(x[0]+x[1]==1)
    for i in range(2):
        m.addConstr(c[i]<=x[i]);m.addConstr(d[i]<=x[i]);m.addConstr(c[i]<=mode);m.addConstr(d[i]<=1-mode)
    m.addConstr(c.sum()==d.sum()) # fixed terminal SOC
    if cuts:m.addConstr(c.sum()<=mode);m.addConstr(d.sum()<=1-mode)
    m.setObjective(-c.sum());m.optimize();value=m.ObjVal;m.dispose();return value

def test_integer_preserved_and_arc_LP_strengthened():
    assert objective(True,False)==objective(True,True)==0
    assert abs(objective(False,False)+1)<1e-10
    assert abs(objective(False,True)+.5)<1e-10

def test_cut_dual_elimination_is_exact_and_nonnegative():
    assert eliminate_duals(np.array([-2.,-.5]),np.array([-1.,0.]))==2
