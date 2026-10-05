import numpy as np
import gurobipy as gp
import pytest
from v42_integrated.matrix import arrays,audit
from v42_m1_accel_vnext.labels import solve

@pytest.mark.parametrize('travel,terminal,reactive',[(0.,1.,0.),(.3,.8,.4),(.7,.5,-.2)])
def test_continuous_SOC_mode_and_route_hybrid(travel,terminal,reactive):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    for p in ('FeasibilityTol','OptimalityTol','IntFeasTol'):m.setParam(p,1e-8)
    route=m.addVar(vtype='B',name='route');mode=m.addVars(2,vtype='B',name='mode')
    e=m.addVars(3,lb=0,ub=2,name='SOC');c=m.addVars(2,ub=1,name='Pch');v=m.addVars(2,ub=1,name='Pdis');q=m.addVars(2,lb=-1,ub=1,name='Q')
    m.addConstr(e[0]==1);m.addConstr(e[2]==terminal)
    for t in range(2):
        m.addConstr(c[t]<=mode[t]);m.addConstr(v[t]<=1-mode[t])
        m.addConstr(e[t+1]==e[t]+.9*c[t]-v[t]/.9-(travel*route if t==0 else 0))
        m.addConstr(c[t]+v[t]<=(1-route if t==0 else 1))
        m.addConstr(q[t]+v[t]-c[t]<=1);m.addConstr(-q[t]+v[t]-c[t]<=1)
    m.setObjective(-v[0]-2*v[1]+.4*c[0]+.6*c[1]+reactive*q[0]-.1*route)
    m.update();A,d=arrays(m);m.optimize();reference=m.ObjVal
    def valid(x):return audit(A,d,x,integral=True,tolerance=1e-8)['PASS'] and np.array_equal(x[d['types']!='C'],np.rint(x[d['types']!='C']))
    result,x=solve(A,d,seconds=10,validator=valid)
    assert result['optimum'] is not None,result
    assert abs(result['optimum']-reference)<=1e-8
    assert valid(x) and abs(float(d['objective']@x)-reference)<=1e-8
    assert result['exact_domain_cover'] and not result['SOC_discretization']
    m.dispose()
