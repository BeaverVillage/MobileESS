"""Independent tiny native Pi/ObjBound convention confirmation, not M1."""
from .common import *
from .fixtures import run,master
from .certificate import global_dual
from fractions import Fraction as F
import numpy as np
import gurobipy as gp

def native(case,full):
    model=gp.Model('bounded_dual_fixture');model.Params.OutputFlag=0
    for k,v in dict(Threads=1,Method=2,Crossover=1,FeasibilityTol=EPS,OptimalityTol=EPS,IntFeasTol=EPS).items():model.setParam(k,v)
    rho=model.addVar(lb=0,ub=10,obj=1);y=model.addVar(lb=-gp.GRB.INFINITY if case.get('free') else 0,ub=gp.GRB.INFINITY if case.get('free') else 0)
    ls=[[model.addVar(lb=0) for _ in (range(2) if full else range(1))] for m in range(2)]
    expr=rho-gp.quicksum(case['demands'][m][j]*ls[m][j] for m in range(2) for j in range(len(ls[m])))
    sense=case.get('sense','>')
    row=model.addConstr(expr>=0 if sense=='>' else -expr<=0 if sense=='<' else expr==0)
    extra=model.addConstr(-rho<=0);binding=model.addConstr(y-(.5*rho if case.get('free') else 0)==0)
    conv=[model.addConstr(gp.quicksum(v)==1) for v in ls];model.optimize();assert model.Status==2
    pi=np.array([row.Pi,extra.Pi,binding.Pi]);alpha=np.array([c.Pi for c in conv])
    exact=master(case,[[0,1],[0,1]] if full else [[0],[0]])
    assert abs(model.ObjVal-float(exact['value']))<=EPS
    A=np.array([[1 if sense!='<' else -1,0],[-1,0],[-.5 if case.get('free') else 0,1]],float)
    from scipy.sparse import csr_matrix
    d=dict(sense=np.array([sense,'<','=']),objective=np.array([1.,0.]),rhs=np.zeros(3),constant=np.array(0.))
    lo=np.array([0.,-5. if case.get('free') else 0.]);hi=np.array([10.,5. if case.get('free') else 0.])
    value,proof=global_dual(csr_matrix(A),d,pi,lo,hi)
    pricing=[]
    for m in range(2):
        vals=[-sum(F(float(pi[i]))*q for i,q in enumerate(v))-F(float(alpha[m])) for v in exact['cols'][m]]
        p=gp.Model('full_tiny_pricing');p.Params.OutputFlag=0
        for k,v in dict(Threads=1,MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=EPS,OptimalityTol=EPS,IntFeasTol=EPS).items():p.setParam(k,v)
        choose=p.addVar(vtype='B',obj=float(vals[1]-vals[0]));p.ObjCon=float(vals[0]);p.optimize()
        assert p.Status==2 and abs(p.ObjVal-float(min(vals)))<=EPS and p.ObjBound<=float(min(vals))+EPS
        pricing.append(dict(status=p.Status,ObjVal=p.ObjVal,ObjBound=p.ObjBound,ObjBoundC=p.ObjBoundC,exact_full_enumerated_optimum=str(min(vals)),objective_constant_included=True,model_fingerprint=p.Fingerprint));p.dispose()
    L=value+sum(F(float(a))+min(F(0),F(p['ObjBound'])-F(EPS)) for a,p in zip(alpha,pricing))
    fullvalue=master(case,[[0,1],[0,1]])['value'];assert L<=fullvalue+F(EPS) and fullvalue<=F(model.ObjVal)+F(EPS)
    result=dict(PASS=True,case=case['name'],full=full,Pi=pi.tolist(),alpha=alpha.tolist(),global_box_dual=proof,pricing=pricing,L_corr=float(L),z_RMP=model.ObjVal,z_full=float(fullvalue),manual_RC_solver_RC_max=float(max(abs(v.RC-float(-sum(F(float(pi[i]))*q for i,q in enumerate(exact['cols'][m][j]))-F(float(alpha[m])))) for m in range(2) for j,v in enumerate(ls[m]))))
    assert result['manual_RC_solver_RC_max']<=EPS;model.dispose();return result
def audit():
    gate('native_bounded_fixture');verify_freeze();results=[]
    for case in [dict(name='greater_equal',demands=[[4,1],[2,1]]),dict(name='less_equal',demands=[[4,1],[2,1]],sense='<'),dict(name='equality_free_global',demands=[[4,1],[2,1]],sense='=',free=True)]:
        for full in (False,True):results.append(native(case,full))
    write('DW_DUAL_SIGN_AND_BOUND_PROOF.json',dict(PASS=True,native_cases=results,solver_version=list(gp.gurobi.version()),Threads=1,optimization_scope='Six bounded fixture LPs and twelve tiny binary pricing models; no full scientific model optimization.',
      actual_Pi_convention='min: <= Pi<=0, >= Pi>=0, equality/convexity unrestricted',global_z_bounds_and_free_equality_verified=True,manual_RC_equals_solver_RC=True,ObjBound_minimization_and_ObjCon_verified=True,
      exact_enumeration_proof_SHA=sha(OUT/'DW_CORRECTED_BOUND_BOUNDED_FIXTURES.json'),scientific_heavy_budget_charged=0))
    print('NATIVE_DUAL_AND_BESTBD_FIXTURES_PASS',flush=True)
if __name__=='__main__':audit()
