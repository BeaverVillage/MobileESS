"""Exhaustive tiny physical fixtures; independent of the large cut builder."""
from .common import *
from scipy.optimize import linprog,OptimizeWarning
import itertools,warnings

def problem(path,modes,relaxed=False):
    # 4 slots, two sites, one 2-slot travel arc. The other route travels
    # in the last 2 slots. Initial=terminal=2, SOC in [1.5,3], travel=1.
    # Original route/mode/power/SOC/PQ/PCS/grid physics; rational toy units.
    n=23;E=np.arange(5);C=np.arange(5,9);D=np.arange(9,13);Q=np.arange(13,17);rho=17;f=18;M=np.arange(19,23)
    obj=np.zeros(n);obj[rho]=1.;eq=[];eb=[];ub=[];rhs=[]
    def row(terms,b,kind='<'):
        r=np.zeros(n)
        for j,v in terms.items():r[j]+=v
        (eq if kind=='=' else ub).append(r);(eb if kind=='=' else rhs).append(b)
    for t in range(4):
        travel={f:1.} if t==0 else {f:-1.} if t==2 else {}
        row({E[t+1]:1,E[t]:-1,C[t]:-1,D[t]:1,**travel},-1. if t==2 else 0.,'=')
        # connected capacity: 1-f early, f late.
        flowcoeff=1. if t<2 else -1.;capacity=1. if t<2 else 0.
        row({C[t]:1,f:flowcoeff},capacity);row({D[t]:1,f:flowcoeff},capacity)
        row({C[t]:1,M[t]:-1},0);row({D[t]:1,M[t]:1},1)
        row({Q[t]:1,f:flowcoeff},capacity);row({Q[t]:-1,f:flowcoeff},capacity)
        for p,q in itertools.product((-1.,1.),repeat=2):row({D[t]:p,C[t]:-p,Q[t]:q,f:flowcoeff},capacity)
        for p,q in itertools.product((-1.,1.),repeat=2):row({D[t]:p,C[t]:-p,Q[t]:q*.5,rho:-1},0.)
    bounds=[(2.,2.)]+[(1.5,3.)]*3+[(2.,2.)]+[(0.,1.)]*8+[(-1.,1.)]*4+[(0.,2.)]+([(0.,1.)] if relaxed else [(path,path)])+([(0.,1.)]*4 if relaxed else [(v,v) for v in modes])
    return obj,np.array(ub),np.array(rhs),np.array(eq),np.array(eb),bounds

def compressed(problem):
    c,A,b,E,r,bounds=problem;n=len(c);keep=np.arange(5,n);R=np.zeros((n,len(keep)));off=np.zeros(n);R[keep,np.arange(len(keep))]=1.;off[:5]=2.
    # Exact temporal substitution, independently constructed from the toy
    # energy equation, retaining route/mode and no SOC discretization.
    for t in range(1,5):
        for s in range(t):R[t,5+s-5]+=1;R[t,9+s-5]-=1
        if t>=1:R[t,18-5]-=1
        if t>=3:R[t,18-5]+=1;off[t]-=1
    u=A@R;v=b-A@off;more=[];mb=[]
    for t in range(1,4):more.extend([R[t],-R[t]]);mb.extend([3.-off[t],off[t]-1.5])
    eq=R[4:5];er=np.array([2.-off[4]])
    return (c@R,np.vstack([u,more]),np.r_[v,mb],eq,er,[bounds[j] for j in keep]),R,off

def temporal_rows(problem):
    # Independent analytic instance of the four endpoint disjunctions;
    # the large temporal.build implementation is NOT called by this test.
    c,A,b,E,r,bounds=problem;rows=[];rhs=[]
    for dep,arr,selected_offset,selected_sign in [(0,2,0.,1.),(2,4,1.,-1.)]:
        ld,ud=bounds[dep];la,ua=bounds[arr];cost=1.;U=max(0,ua-ld+cost);L=min(0,la-ud+cost);lo=max(0,la+cost-ld);up=max(0,ua-ud+cost)
        for ed,ea,slope,br in [(-1,1,U,U-cost),(1,-1,-L,cost-L),(-1,0,lo,-ld),(0,1,up,ua)]:
            row=np.zeros(len(c));row[dep]=ed;row[arr]=ea;row[18]=slope*selected_sign;rows.append(row);rhs.append(br-slope*selected_offset)
    return (c,np.vstack([A,rows]),np.r_[b,rhs],E,r,bounds)

def solve(p):
    c,A,b,E,r,bounds=p
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',OptimizeWarning)
        return linprog(c,A_ub=A,b_ub=b,A_eq=E,b_eq=r,bounds=bounds,method='highs',options={'threads':1,'primal_feasibility_tolerance':1e-8,'dual_feasibility_tolerance':1e-8})

def main():
    prior.forbid_optimize();results=[];calls=0;start=time.perf_counter()
    for path in (0.,1.):
        for modes in itertools.product((0.,1.),repeat=4):
            original=problem(path,modes);orig=solve(original);calls+=1
            h2,R,off=compressed(original);reduced=solve(h2);calls+=1
            aug=solve(temporal_rows(original));calls+=1
            assert orig.status==reduced.status==aug.status
            passed=True
            if orig.success:
                rebuilt=off+R@reduced.x;passed=abs(orig.fun-reduced.fun)<=1e-8 and abs(orig.fun-aug.fun)<=1e-8 and np.max(abs(original[3]@rebuilt-original[4]))<=1e-8 and np.max(original[1]@rebuilt-original[2])<=1e-8
                assert passed
            results.append(dict(path=path,mode_word=''.join(str(int(v)) for v in modes),status=orig.status,original_objective=float(orig.fun) if orig.success else None,H2_objective=float(reduced.fun) if reduced.success else None,B2_objective=float(aug.fun) if aug.success else None,PASS=passed))
    fractional=problem(0.,(0.,)*4,True);lp=solve(fractional);h2,R,off=compressed(fractional);lp2=solve(h2);tight=solve(temporal_rows(fractional));calls+=3
    assert lp.success and lp2.success and tight.success and abs(lp.fun-.25)<=1e-8 and abs(tight.fun-.5)<=1e-8 and abs(lp.fun-lp2.fun)<=1e-8
    # Mutation: remove travel physics from the original energy system.
    mutated=list(fractional);er=mutated[3].copy();er[:,18]=0.;mutated[3]=er;mutated[4]=np.zeros(4);wrong=solve(tuple(mutated));calls+=1;assert wrong.success and wrong.fun<lp.fun
    report=dict(PASS=True,integer_assignments=len(results),feasible=sum(v['status']==0 for v in results),infeasible=sum(v['status']==2 for v in results),enumerated_cases=results,original_to_H1='identity',original_to_H2='drop reconstructed SOC coordinates',H2_to_original='exact cumulative energy substitution with all original SOC bounds and terminal equality',original_and_B2_integer_optimum=min(v['original_objective'] for v in results if v['status']==0),fractional_original_LB=lp.fun,fractional_H2_LB=lp2.fun,fractional_B2_LB=tight.fun,positive_fractional_strengthening=True,mutated_travel_identity_rejected=True,native_fullscale_Gurobi_calls=0,tiny_HiGHS_calls=calls,controller_wall_seconds=time.perf_counter()-start,full_C3A_equivalence_not_inferred_from_toy=True,fixture_horizon=4,actual_large_coverage='independent full96-slot CSR proof')
    write(REPORTS/'BOUNDED_EXACT_FIXTURE_VERIFICATION.json',report);print('BOUNDED_FIXTURE_PASS',json.dumps(clean({k:v for k,v in report.items() if k!='enumerated_cases'})),flush=True)

if __name__=='__main__':main()
