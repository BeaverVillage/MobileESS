"""One controlled two-window generalization after observed substitution."""
from common import *

def main():
    import gurobipy as gp
    substitution=read(OUT/'SUBSTITUTION_EFFECT_AUDIT.json')
    assert substitution['substitution_observed'] and substitution['valid_LB_change']<.001
    selected=max((r for r in substitution['new_point_mode_location_defects'] if r['MESS']!='MESS04'),key=lambda r:r['mode_location_PQ_defect']);assert selected['MESS']=='MESS03'
    labels=['MESS04_69_72','MESS03_69_72'];A,d,_=load();n=A.shape[1];extra=0;matrices=[];datasets=[];authorities=[]
    for label in labels:
        h=read(OUT/(label+'_HULL_AUTHORITY.json'));assert read(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))['PASS']
        B=sparse.load_npz(OUT/(label+'_EF_MATRIX.npz')).tocoo()
        assert sha(OUT/(label+'_EF_MATRIX.npz'))==h['matrix_SHA256']
        with np.load(OUT/(label+'_EF_DATA.npz')) as z:f={k:z[k] for k in ('lower','upper','rhs','sense')}
        B.col=np.where(B.col>=n,B.col+extra,B.col)
        matrices.append(B);datasets.append(f);authorities.append(h);extra+=len(f['lower'])
    lifted=[sparse.csr_matrix((B.data,(B.row,B.col)),shape=(B.shape[0],n+extra)) for B in matrices]
    M=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],extra))],format='csr')]+lifted,format='csr')
    e=dict(lower=np.concatenate([d['lower']]+[f['lower'] for f in datasets]),upper=np.concatenate([d['upper']]+[f['upper'] for f in datasets]),objective=np.r_[d['objective'],np.zeros(extra)],constant=d['constant'],rhs=np.concatenate([d['rhs']]+[f['rhs'] for f in datasets]),sense=np.concatenate([d['sense']]+[f['sense'] for f in datasets]))
    scope=dict(UTC=stamp(),single_generalization_only=True,blocks=labels,block_count=2,maximum_allowed_blocks=4,selection_from_new_point=selected,selection_point_SHA256=sha(OUT/'SINGLE_WINDOW_STRENGTHENED_LP_PRIMAL.npz'),new_point_raw_replay_failed=True,substitution_is_observation_of_approximate_native_point=True,original_MESS04_hull_retained=True,all_original_rows_preserved=True,authorities=authorities,
        correctness_issue='Single-window native OPTIMAL barrier capture fails strict replay: augmented max0.01889765, original max2.3786e-5. Enable crossover once for this new two-block LP to obtain a basis and improve numerical feasibility; no tolerance relaxation or parameter sweep.',only_algorithm_setting_change_from_PR167_pure_LP='Crossover 0 -> 1',scientific_physics_unchanged=True)
    write('MULTIWINDOW_HULL_AUTHORITY.json',scope)
    m=gp.Model('MULTIWINDOW_HULL');m.Params.OutputFlag=0
    v=m.addMVar(M.shape[1],lb=e['lower'],ub=e['upper'],obj=e['objective'],vtype='C');v[:n].VarName=d['names'].tolist();m.ObjCon=float(e['constant']);m.addMConstr(M,v,e['sense'],e['rhs'])
    settings=dict(Method=2,Threads=1,Crossover=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,TimeLimit=gp.GRB.INFINITY)
    for k,val in settings.items():m.setParam(k,val)
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/'MULTIWINDOW_STRENGTHENED_LP.log');m.update()
    assert m.NumBinVars==0 and m.NumNZs==M.nnz
    once('MULTIWINDOW_STRENGTHENED_LP',settings,scope);snapshot('MULTIWINDOW_CONCURRENCY.json');print('MULTIWINDOW_START',M.shape,M.nnz,flush=True);m.optimize()
    receipt=dict(Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),settings=settings,rows=M.shape[0],cols=M.shape[1],nnz=M.nnz,optimize_calls=1)
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/'MULTIWINDOW_STRENGTHENED_LP_PRIMAL.npz',x=x)
        receipt.update(ObjVal=float(m.ObjVal),native_ObjBound=float(m.ObjBound),barrier_iterations=int(m.BarIterCount),simplex_iterations=float(m.IterCount),primal_saved_before_validation=True)
        write('MULTIWINDOW_STRENGTHENED_LP.json',dict(receipt,postprocessing_pending=True))
        pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'));slack=np.asarray(m.getAttr('Slack'));np.savez_compressed(OUT/'MULTIWINDOW_STRENGTHENED_LP_DUAL_RC_SLACK.npz',dual=pi,reduced_cost=rc,slack=slack)
        cert=exact_bounded_lagrangian(M,e,pi)[0];valid=max(LB,cert['lower_bound']);receipt.update(raw_augmented_replay=replay(M,e,x),original_C3A_replay=replay(A,d,x[:n]),exact_certificate=cert,new_valid_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED,material=valid-LB>=.001,native_ObjVal_not_promoted_to_LB=True,postprocessing_pending=False)
    else:receipt.update(new_valid_LB=LB,delta_LB=0.,material=False,no_primal_available=True)
    write('MULTIWINDOW_STRENGTHENED_LP.json',receipt);m.dispose();print('MULTIWINDOW_DONE',receipt,flush=True)

if __name__=='__main__':main()
