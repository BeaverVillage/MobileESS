"""Post-freeze independent-review guard and reporting-only ratio uncertainty.

Does not alter registered source, any choice, predictions, thresholds or metrics.
"""
from study import *

def finite_selection_guard(table):
    required=['coverage','GPU_coverage','long_under','overreserved_GPUh','requested_overreserved_GPUh']
    need(np.isfinite(table[required].to_numpy(float)).all(),'NONFINITE_SELECTION_METRIC')
    need(set(table.role)==set(ROLES),'SELECTION_ROLE_MISSING')

def main():
    verify_sources();table=pd.read_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')
    finite_selection_guard(table)
    choice,_=choose(table);need(choice==read(ROOT/'FINAL_SELECTION_FREEZE.json')['selected_by_state'],'SELECTION_NOT_REPRODUCED')
    bad=table.copy();bad.loc[bad.index[0],'long_under']=np.nan
    try:finite_selection_guard(bad)
    except AssertionError:pass
    else:raise AssertionError('FINITE_GUARD_TEST_FAILED')
    f=pd.read_parquet(ROOT/'BOUND_PREDICTIONS.parquet');rows=[]
    comparisons=pd.read_csv(ROOT/'MATCHED_COMPARISONS.csv')
    for r in comparisons.itertuples():
        group=f[f.role.eq(r.role)&f.state.eq(r.state)]
        a=group[group.arm.eq(r.candidate)];b=group[group.arm.eq(r.reference)]
        need(set(a.job_issue_id)==set(b.job_issue_id),'RATIO_PAIRS')
        va=np.array([daily_values(g) for _,g in a.groupby('issue_time',sort=True)])
        vb=np.array([daily_values(g) for _,g in b.groupby('issue_time',sort=True)])
        need(va.shape==vb.shape,'DAILY_PAIR_SHAPE')
        n=len(va)
        def reduction(indices):
            numerator=va[indices,6].sum();denominator=vb[indices,6].sum()
            return 1-numerator/denominator if denominator>0 else np.nan
        for block in [1,7]:
            rng=np.random.default_rng(SEED);samples=[]
            for _ in range(DRAW):
                starts=rng.integers(n,size=int(np.ceil(n/block)))
                idx=((starts[:,None]+np.arange(block))%n).ravel()[:n]
                samples.append(reduction(idx))
            samples=np.array(samples);need(np.isfinite(samples).all(),'ZERO_REFERENCE_SLOTS_IN_BOOTSTRAP')
            lo,hi=np.quantile(samples,[.025,.975])
            rows.append(dict(role=r.role,state=r.state,candidate=r.candidate,reference=r.reference,
                metric='missed_slots_reduction',estimate=reduction(np.arange(n)),CI95_low=lo,CI95_high=hi,
                block_days=block,draws=DRAW,N_days=n,N_pairs=len(a),nonfinite_draws=0))
    pd.DataFrame(rows).to_csv(ROOT/'MISSED_SLOT_REDUCTION_UNCERTAINTY.csv',index=False)
    save('REVIEW_ADDENDUM_VALIDATION.json',dict(time=now(),PASS=True,all_selection_metrics_finite=True,
        frozen_choice_reproduced=True,synthetic_NaN_rejected=True,all_ratio_bootstrap_draws_finite=True,
        ratio_recomputed_per_draw=True,registered_code_unchanged=True,selection_changed=False,
        source_sha256=sha(ROOT/'review_addendum.py'),
        scope='post-freeze audit/reporting only; no candidate, metric definition, feature, threshold, or prediction changed'))
    print('REVIEW_ADDENDUM PASS',flush=True)

if __name__=='__main__':main()
