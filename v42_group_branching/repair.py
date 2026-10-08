"""Saved-data equality multiplier repair; every operation has optimize=0."""
from .common import *
from v42_physics_redesign.exact_cut import construct
from v42_b2_root_validation.certificate import verify_certificate,tests

def repair_multiplier(A,d,pi,stationarity=None):
    family=np.array([str(n).split('[')[0] for n in d['names']])
    rowfamily=np.array([str(n).split('[')[0] for n in d['row_names']])
    target=np.flatnonzero(np.isin(family,['injection_P','injection_Q']))
    binding=np.flatnonzero(np.isin(rowfamily,['injection_P_binding','injection_Q_binding']))
    C=A.tocsc();rowset=set(map(int,binding));targetset=set(map(int,target));records=[];used=set();out=pi.copy()
    residual=d['objective']-A.T@pi if stationarity is None else stationarity
    for j in target:
        entries=range(C.indptr[j],C.indptr[j+1])
        match=[k for k in entries if int(C.indices[k]) in rowset]
        assert len(match)==1,('NOT_UNIQUE_BINDING',int(j))
        k=match[0];i=int(C.indices[k]);a=float(C.data[k]);assert d['sense'][i]=='=' and abs(a)==1 and i not in used
        row=A.getrow(i);other=set(row.indices).intersection(targetset)-{j};assert not other
        used.add(i);delta=float(residual[j]/a);out[i]+=delta
        records.append(dict(column=int(j),variable=str(d['names'][j]),row=i,row_name=str(d['row_names'][i]),
            pivot_coefficient=a,row_nnz=row.nnz,original_rhs=float(d['rhs'][i]),
            original_multiplier=float(pi[i]),stationarity_before=float(residual[j]),
            correction=delta,repaired_multiplier=float(out[i])))
    assert len(used)==len(binding)==len(target)
    wrong=((d['sense']=='<')&(out>0))|((d['sense']=='>')&(out<0));assert not wrong.any()
    return out,records,target

def main():
    prior.forbid_optimize();start=time.perf_counter();source=identity()
    A,d,T,augmented,full=model_inputs()
    with np.load(SOURCE187/'B2_ROOT_RAW.npz') as f:raw={k:f[k].copy() for k in f.files}
    with np.load(SOURCE187/'artifacts/B2_EXACT_LB_NEW_SIGN_CONE.npz') as f:
        projected=f['pi'].copy();residual=f['stationarity'].copy()
    bad=((full['sense']=='<')&(raw['pi']>0))|((full['sense']=='>')&(raw['pi']<0))
    assert int(bad.sum())==20566 and np.where(bad,0.,raw['pi']).tobytes()==projected.tobytes()
    repaired,records,target=repair_multiplier(augmented,full,projected,residual)
    save(WORK/'artifacts/SAVED_B2_EQUALITY_REPAIRED_MULTIPLIER.npz',pi=repaired,raw_pi=raw['pi'],
        sign_cone_pi=projected,repaired_rows=np.array([r['row'] for r in records]),target_columns=target)
    table(REPORTS/'INJECTION_BINDING_REPAIR_ROWS.csv',records)
    proof=construct(augmented,full,np.array([],dtype=int),repaired,WORK/'artifacts/SAVED_B2_REPAIRED_BOUND')
    assert proof['PASS'];independent=verify_certificate(augmented,full,proof)
    with np.load(proof['npz_path']) as f:newres=f['stationarity'].copy()
    native=read(SOURCE187/'B2_ROOT_NATIVE_RESULT.json')['ObjVal'];bound=independent['certified_LB']
    loss=native-bound;gate=independent['PASS'] and abs(loss)<=1e-4
    fixture=tests();assert fixture['PASS']
    result=dict(PASS=True,certification_pilot_gate_PASS=gate,gate_absolute_native_minus_certified_max=1e-4,
        classification='DUAL_CERTIFICATION_READY' if gate else 'DUAL_CERTIFICATION_BLOCKED',
        native_calls=0,source_HEAD=BASE187,raw_multiplier_preserved=True,raw_bad_sign_count=int(bad.sum()),
        raw_sign_cone_certificate='REJECTED',original_projected_LB=.5659508784310822,
        new_multiplier_separately_saved=True,repair_only_original_equalities=True,unique_unit_pivots=len(records),
        exact_all_variable_finite_bound_support=306040,producer=proof,independent=independent,
        native_LP_objective=native,repaired_exact_LB=bound,native_minus_certificate=loss,
        all_target_residual_max_before=float(abs(residual[target]).max()),all_target_residual_max_after=float(abs(newres[target]).max()),
        diagnostic_native_primal_not_an_exact_upper_bound=True,objective_unchanged=True,full_original_integer_domain_valid=True,
        analytic_checker_tests=fixture,wall_seconds=time.perf_counter()-start,
        branch_applicability='Same original binding equalities and finite-box proof; only selected binary bounds become [0,0] or [1,1]. Child domain checker must independently validate the one bound substitution.')
    write(REPORTS/'DUAL_CERTIFICATION_REPAIR_AUDIT.json',result)
    print('SAVED_B2_REPAIR',json.dumps(clean(result),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
