"""Mandatory smoothing full-enumeration CG proof; no stabilized-dual certificate."""
from .common import *
def proof(intervals,cancel):
    import gurobipy as gp
    from fractions import Fraction as F
    # Every feasible discrete trajectory of two bounded finite-domain blocks.
    domains=[[(F(0),F(3)),(F(1),F(1)),(F(2),F(0))],[(F(0),F(2)),(F(1),F(1,2)),(F(2),F(0))]]
    def solve(pool):
        model=gp.Model();model.Params.OutputFlag=0;model.Params.Threads=1;model.Params.Method=1;model.Params.FeasibilityTol=EPS;model.Params.OptimalityTol=EPS;model.Params.IntFeasTol=EPS;model.Params.TimeLimit=5
        variables=[[model.addVar(lb=0,obj=float(domains[m][j][1])) for j in ix] for m,ix in enumerate(pool)]
        conv=[model.addConstr(gp.quicksum(vs)==1) for vs in variables]
        coupling=model.addConstr(gp.quicksum(float(domains[m][j][0])*v for m,ix in enumerate(pool) for j,v in zip(ix,variables[m]))<=2)
        def control(native,where):
            if cancel.is_set() or STOP.exists():native.terminate()
        a=time.perf_counter();model.optimize(control);b=time.perf_counter();intervals.append((a,b));assert model.Status==2
        result=(float(model.ObjVal),F(float(coupling.Pi)),[F(float(c.Pi)) for c in conv]);model.dispose();return result
    full,_,_=solve([list(range(3)),list(range(3))]);runs=[]
    for stabilized in (False,True):
        pool=[[0],[0]];smooth=None;smooth_alpha=None;previous=None;weight=.30;steps=[]
        for k in range(12):
            obj,pi,alpha=solve(pool)
            if smooth is None:smooth=pi;smooth_alpha=alpha.copy()
            else:
                smooth=F(weight)*pi+(1-F(weight))*smooth;smooth_alpha=[F(weight)*a+(1-F(weight))*b for a,b in zip(alpha,smooth_alpha)]
            search=smooth if stabilized else pi;search_alpha=smooth_alpha if stabilized else alpha;added=[]
            for m,domain in enumerate(domains):
                rank=min(range(3),key=lambda j:domain[j][1]-search*domain[j][0]-search_alpha[m])
                if domain[rank][1]-pi*domain[rank][0]-alpha[m]<0 and rank not in pool[m]:pool[m].append(rank);added.append((m,rank))
            # Exact recovery always prices the ENTIRE domain under true pi.
            beta=[min(c-pi*a-alpha[m] for a,c in domain) for m,domain in enumerate(domains)]
            for m,domain in enumerate(domains):
                if beta[m]<0:
                    j=min(range(3),key=lambda j:domain[j][1]-pi*domain[j][0]-alpha[m])
                    if j not in pool[m]:pool[m].append(j);added.append((m,j))
            steps.append(dict(objective=obj,true_pi=str(pi),search_pi=str(search),exact_beta=list(map(str,beta)),added=added,certificate_dual='TRUE_UNSTABILIZED_RMP'))
            if previous is not None:weight=next_smoothing_weight(weight,float(abs(pi-previous)/max(F(1e-12),abs(previous))))
            previous=pi
            if all(v>=0 for v in beta):break
        assert all(v>=0 for v in beta) and abs(obj-full)<=EPS
        runs.append(dict(stabilized_discovery=stabilized,objective=obj,steps=steps,full_enumerated_domain_sizes=[3,3],no_stabilized_certificate=True))
    return dict(PASS=True,full_enumeration_optimum=full,runs=runs,same_optimum=True,native_intervals_charged=True,finite_bounded_fixture=True)
