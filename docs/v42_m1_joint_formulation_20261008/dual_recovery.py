"""Joint equality-block stationarity repair. Sparse arithmetic, zero optimize."""
from common import *
from scipy.sparse.linalg import lsmr
def run():
    gp,original_optimize=forbid_optimize()
    try:
        A,d,_=load();objective_identity(A,d);families=np.array([info(n)[0] for n in d['names']])
        equalities=np.flatnonzero((d['sense']=='=')&np.isin(d['row_names'],['injection_P_binding','injection_Q_binding','response_line_P_binding','response_line_Q_binding','response_line_correction_binding','response_transformer_P_binding','response_transformer_Q_binding','energy_balance']))
        block=A[equalities].tocsc();cols=np.flatnonzero(np.diff(block.indptr));B=block[:,cols].T.tocsr()
        width=d['upper'][cols]-d['lower'][cols];weight=np.maximum(width,1.)
        weighted=sparse.diags(weight)@B;scale=np.sqrt(np.asarray(weighted.power(2).sum(axis=0)).ravel());scale[scale==0]=1
        normalized=weighted@sparse.diags(1/scale);events=[]
        for node_id in [0,20,52]:
            folder=ARCHIVE/'external_production/external_nodes'/f'{node_id:04d}';receipt=read(folder/'RESULT.json');assert receipt['native_status']==2 and receipt['LP_status']=='OPTIMAL'
            with np.load(folder/'LP_POINT_PROOF.npz') as z:pi=z['Pi'].copy();x=z['x'].copy();native_rc=z['RC'].copy()
            e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
            for j,v in receipt['fixings']:e['lower'][j]=e['upper'][j]=v
            before,_,r,_=hc.exact_bounded_lagrangian(A,e,pi)
            interior=(x-e['lower']>1e-7)&(e['upper']-x>1e-7)
            desired=native_rc.copy();desired[interior]=0
            target=weight*(r[cols]-desired[cols]);t0=time.perf_counter();solution=lsmr(normalized,target,atol=1e-13,btol=1e-13,maxiter=2000)
            candidate=pi.copy();candidate[equalities]+=solution[0]/scale
            assert np.array_equal(candidate[d['sense']!='='],pi[d['sense']!='='])
            after,_,rr,_=hc.exact_bounded_lagrangian(A,e,candidate)
            # Second independent original-array arithmetic evaluation from saved bytes.
            path=OUT/f'DUAL_RECOVERY_NODE_{node_id:04d}.npz';save_vector(path,Pi=candidate)
            with np.load(path) as z:independent,_,_,_=hc.exact_bounded_lagrangian(A,e,z['Pi'])
            assert independent['exact_rational']==after['exact_rational']
            event=dict(node_id=node_id,global_domain=node_id==0,child_bound_is_not_global=node_id!=0,fixings=receipt['fixings'],source_receipt_SHA256=sha(folder/'RESULT.json'),source_vector_SHA256=sha(folder/'LP_POINT_PROOF.npz'),corrected_vector_SHA256=sha(path),native_LP_objective=receipt['LP_objective'],before=before,after=after,improvement=float(F(after['exact_rational'])-F(before['exact_rational'])),inherited_global_LB=LB,recovered_exceeds_inherited_global_LB=float(F(after['exact_rational']))>LB,LSMR=dict(stop_code=solution[1],iterations=solution[2],residual_norm=solution[3],normal_residual_norm=solution[4],condition_estimate=solution[6],wall_seconds=time.perf_counter()-t0),interior_stationarity_target_zero=True,bound_variables_target_archived_reduced_cost=True,corrected_equality_rows=len(equalities),joint_columns=len(cols),PCS_inequality_multipliers_unchanged=True,changed_original_matrix_objective_bounds=False,independent_exact_certificate_PASS=True)
            events.append(event);atomic(OUT/f'DUAL_RECOVERY_NODE_{node_id:04d}.json',event)
            print('DUAL_RECOVERY',node_id,float(F(before['exact_rational'])),float(F(after['exact_rational'])),solution[2],flush=True)
        root=events[0];global_LB=max(F.from_float(LB),F(root['after']['exact_rational']))
        atomic(OUT/'DUAL_RECOVERY_RESULT.json',dict(PASS=True,optimize_calls=0,method='Joint weighted sparse least-squares equality multiplier correction, not an LP/MIP solve',events=events,valid_global_LB=float(global_LB),valid_global_LB_exact=str(global_LB),UB=UB,gap=float((F.from_float(UB)-global_LB)/F.from_float(UB)),genuine_relaxation_strengthening=False,old_OPEN_tree_restarted=False))
    finally:gp.Model.optimize=original_optimize
if __name__=='__main__':run()
