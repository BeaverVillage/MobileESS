"""One preregistered local-branching primal-quality search, never full B&B."""
from common import *

def main():
    import gurobipy as gp
    from v42_redundancy.model import build
    A,d,reference=load();start=reference
    improved=OUT/'UB_FIXED_DISCRETE_VALID_POINT.npz'
    if improved.exists():
        with np.load(improved) as z:start=z['x'].copy()
    b=np.flatnonzero(d['types']=='B');free=[]
    for j in b:
        name=str(d['names'][j]);t=int(name.rsplit(',',1)[-1][:-1])
        if 64<=t<=84:free.append(int(j))
    free=np.array(free,dtype=int);fixed=np.setdiff1d(b,free)
    f=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
    f['lower'][fixed]=reference[fixed];f['upper'][fixed]=reference[fixed]
    weights=np.where(reference[free]>.5,-1.,1.);rhs=24-int((reference[free]>.5).sum())
    row=sparse.csr_matrix((weights,(np.zeros(len(free),int),free)),shape=(1,A.shape[1]))
    B=sparse.vstack([A,row],format='csr')
    e=dict(f,rhs=np.r_[d['rhs'],rhs],sense=np.concatenate([d['sense'],['<']]),row_names=np.concatenate([d['row_names'],['PRIMAL_NEIGHBORHOOD_HAMMING24']]))
    definition=dict(UTC=stamp(),definition='Original all-integer C3A, all units node/mode slots64..84 free, all other B fixed to incumbent; local branching Hamming distance <=24 over free original binaries',free_count=len(free),fixed_count=len(fixed),radius=24,LP_guidance='PR167 active thermal slots66..95 and MESS04 69..72; permit departure/return around event without selecting a presumed causal unit',free_names=d['names'][free].tolist(),original_integer_set_restricted_only_for_primal_search=True,bound_not_global=True,preregistered_before_model_optimize=True)
    write('UB_LOCAL_NEIGHBORHOOD_DEFINITION.json',definition)
    m=build(B,e);m.setAttr('Start',m.getVars(),start.tolist())
    settings=dict(Threads=1,TimeLimit=300,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0)
    for k,v in settings.items():m.setParam(k,v)
    m.Params.LogFile=str(OUT/'UB_LOCAL_NEIGHBORHOOD.log');m.Params.OutputFlag=1;m.Params.LogToConsole=0
    once('UB_LOCAL_NEIGHBORHOOD',settings,definition)
    print('PRIMAL_NEIGHBORHOOD_START',len(free),flush=True);m.optimize()
    point=None;raw=None;phy=None;valid=UB
    if m.SolCount:
        point=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/'UB_LOCAL_NEIGHBORHOOD_POINT.npz',x=point)
        raw=replay(A,d,point,True);phy=physical_reader().check(point,A,d)
        if raw['PASS'] and phy['PASS']:valid=min(UB,float(d['objective']@point))
    text=(OUT/'UB_LOCAL_NEIGHBORHOOD.log').read_text(encoding='utf-8',errors='replace')
    report=dict(Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),NodeCount=float(m.NodeCount),SolCount=int(m.SolCount),ObjVal=float(m.ObjVal) if m.SolCount else None,native_neighborhood_ObjBound=float(m.ObjBound),neighborhood_bound_not_global=True,settings=settings,definition_SHA256=sha(OUT/'UB_LOCAL_NEIGHBORHOOD_DEFINITION.json'),start_supplied=True,start_accepted='Loaded user MIP start' in text,raw_point_saved_before_validation=True,original_all_integer_replay=raw,physical_replay=phy,baseline_UB=UB,new_valid_UB=valid,delta_UB=UB-valid,optimality_of_global_integer_problem_not_claimed=True,no_full_global_B_and_B=True)
    write('UB_LOCAL_NEIGHBORHOOD_RESULT.json',report);m.dispose();print('PRIMAL_NEIGHBORHOOD_DONE',valid,UB-valid,flush=True)

if __name__=='__main__':main()
