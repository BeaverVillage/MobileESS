"""Exactly one membership feasibility LP and one single-window global LP."""
from common import *
import argparse,time

def main(membership=False):
    import gurobipy as gp
    label='MESS04_69_72';h=read(OUT/(label+'_HULL_AUTHORITY.json'))
    assert read(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))['PASS']
    assert sha(OUT/(label+'_EF_MATRIX.npz'))==h['matrix_SHA256']
    assert sha(OUT/(label+'_EF_DATA.npz'))==h['data_SHA256']
    A,d,start=load();n=A.shape[1]
    B=sparse.load_npz(OUT/(label+'_EF_MATRIX.npz')).tocsr()
    with np.load(OUT/(label+'_EF_DATA.npz')) as z:f={k:z[k] for k in z.files if k!='blocks'}
    with np.load(HISTORY/'PURE_LP_POINT.npz') as z:xref=z['x']
    stage='MESS04_69_72_MEMBERSHIP' if membership else 'SINGLE_WINDOW_STRENGTHENED_LP'
    e=dict(lower=np.r_[xref if membership else d['lower'],f['lower']],upper=np.r_[xref if membership else d['upper'],f['upper']],objective=np.r_[np.zeros(n) if membership else d['objective'],np.zeros(len(f['lower']))],constant=float(d['constant']))
    if membership:M=B;e.update(rhs=f['rhs'],sense=f['sense'])
    else:
        M=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],len(f['lower'])))],format='csr'),B],format='csr')
        e.update(rhs=np.r_[d['rhs'],f['rhs']],sense=np.concatenate([d['sense'],f['sense']]))
    m=gp.Model(stage);m.Params.OutputFlag=0
    variables=m.addMVar(M.shape[1],lb=e['lower'],ub=e['upper'],vtype='C',obj=e['objective']);variables[:n].VarName=d['names'].tolist();m.ObjCon=e['constant']
    constraints=m.addMConstr(M,variables,e['sense'],e['rhs'])
    if not membership:constraints[:A.shape[0]].ConstrName=d['row_names'].tolist()
    settings=dict(Method=2,Threads=1,Crossover=0,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,TimeLimit=gp.GRB.INFINITY)
    for k,v in settings.items():m.setParam(k,v)
    m.Params.LogFile=str(OUT/(stage+'.log'));m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.update()
    assert m.NumBinVars==0 and m.NumIntVars==0 and m.NumNZs==M.nnz and m.NumConstrs==M.shape[0]
    once(stage,settings,dict(only_MESS04_69_72_hull=True,membership_only_no_original_grid_rows=membership,rows=M.shape[0],cols=M.shape[1],nnz=M.nnz,independent_hull_verified=True,no_original_rows_deleted=not membership))
    snapshot(stage+'_CONCURRENCY.json')
    print(stage+'_START',M.shape,M.nnz,flush=True);m.optimize()
    result=dict(Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),settings=settings,rows=M.shape[0],cols=M.shape[1],nnz=M.nnz,membership=membership,optimize_calls=1,original_integer_set_preserved=not membership,original_rows_deleted=0 if not membership else None)
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/(stage+'_PRIMAL.npz'),x=x)
        pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'));slack=np.asarray(m.getAttr('Slack'))
        np.savez_compressed(OUT/(stage+'_DUAL_RC_SLACK.npz'),dual=pi,reduced_cost=rc,slack=slack)
        result.update(ObjVal=float(m.ObjVal),native_ObjBound=float(m.ObjBound),raw_augmented_replay=replay(M,e,x),primal_saved_before_validation=True,all_duals_RC_slacks_saved=True,barrier_iterations=int(m.BarIterCount))
        if not membership:
            result.update(original_C3A_replay=replay(A,d,x[:n]),baseline_LB=LB,approximate_primal_objective_not_certified_LB=True)
            cert,_,_,_=exact_bounded_lagrangian(M,e,pi);valid=max(LB,cert['lower_bound'])
            write('SINGLE_WINDOW_VALID_LB_CERTIFICATE.json',dict(exact_certificate=cert,baseline_LB=LB,new_valid_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED,native_ObjBound_observed=float(m.ObjBound),native_ObjBound_not_substituted_for_independent_certificate=True,all_original_integer_projections_have_exact_EF_extensions=True,independent_hull_verification_SHA256=sha(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))))
            result.update(new_valid_LB=valid,delta_LB=valid-LB,material=valid-LB>=.001)
    write(stage+'.json',result);m.dispose();print(stage+'_DONE',result,flush=True)

if __name__=='__main__':main('--membership' in sys.argv)
