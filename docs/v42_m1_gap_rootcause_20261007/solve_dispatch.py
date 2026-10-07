"""One continuous reoptimization with the entire incumbent trajectory fixed."""
from common import *
import time

def main():
    import gurobipy as gp
    from v42_redundancy.model import build
    A,d,start=load()
    fixed=(d['types']!='C')|np.char.startswith(d['names'],'route_flow[')
    f=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy(),types=np.full(len(start),'C'))
    f['lower'][fixed]=start[fixed];f['upper'][fixed]=start[fixed]
    assert np.array_equal(start[d['types']!='C'],np.rint(start[d['types']!='C']))
    settings=dict(Method=2,Threads=1,Crossover=0,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,TimeLimit=gp.GRB.INFINITY)
    m=build(A,f)
    for k,v in settings.items():m.setParam(k,v)
    m.Params.LogFile=str(OUT/'UB_FIXED_DISCRETE_REOPT.log');m.Params.LogToConsole=0;m.Params.OutputFlag=1
    once('UB_FIXED_DISCRETE_REOPT',settings,dict(fixed_columns=int(fixed.sum()),fixed_names_SHA256=hashlib.sha256('\n'.join(d['names'][fixed]).encode()).hexdigest(),all_incumbent_mobility_flows_and_node_modes_fixed=True,restricted_LB_not_global=True))
    print('FIXED_DISPATCH_START',int(fixed.sum()),flush=True);m.optimize()
    x=np.asarray(m.getAttr('X'));pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'));slack=np.asarray(m.getAttr('Slack'))
    np.savez_compressed(OUT/'UB_FIXED_DISCRETE_REOPT_POINT.npz',x=x,dual=pi,reduced_cost=rc,slack=slack,fixed_mask=fixed)
    raw=replay(A,d,x,True);p=physical_reader()
    # Preserve raw capture. Optional interpolation of two fixed-trajectory
    # dispatches supplies a new candidate only if original strict replay passes.
    trials=[];accepted=None;physical=None
    for k in range(21):
        weight=2.**(-k);candidate=x.copy() if k==0 else start+weight*(x-start)
        r=replay(A,d,candidate,True)
        if r['PASS']:
            phy=p.check(candidate,A,d)
            if phy['PASS']:
                accepted=candidate;physical=phy;trials.append(dict(weight=weight,raw=r,physical_PASS=True));break
        trials.append(dict(weight=weight,raw=r,physical_PASS=False))
    new_ub=UB
    if accepted is not None and float(d['objective']@accepted)<UB:
        new_ub=float(d['objective']@accepted);np.savez_compressed(OUT/'UB_FIXED_DISCRETE_VALID_POINT.npz',x=accepted)
    cert,_,_,_=exact_bounded_lagrangian(A,f,pi)
    report=dict(Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),ObjVal=float(m.ObjVal),native_ObjBound=float(m.ObjBound),settings=settings,raw_point=raw,raw_point_saved_before_validation=True,all_duals_RC_slacks_saved=True,
        fixed_trajectory_lower_bound=cert,that_bound_is_not_global=True,baseline_UB=UB,new_valid_UB=new_ub,delta_UB=UB-new_ub,physical_replay=physical,interpolation_trials=trials,
        every_original_integer_and_mobility_coordinate_fixed=True,no_original_physics_changed=True,continuous_dispatch_optimality_gap_if_valid=new_ub-cert['lower_bound'],integer_optimum_not_claimed=True)
    write('UB_FIXED_DISCRETE_REOPT.json',report);m.dispose();print('FIXED_DISPATCH_DONE',new_ub,'improvement',UB-new_ub,'raw',raw['PASS'],flush=True)

if __name__=='__main__':main()
