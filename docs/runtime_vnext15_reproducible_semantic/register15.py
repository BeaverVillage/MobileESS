from common15 import *
sys.path.insert(0,str(V13));import common13
def main():
    assert not (ROOT/'PREREGISTRATION.json').exists()
    for n in ['SEMANTIC_ADAPTER_PARITY_AUDIT.json','RUNTIME_SEMANTIC_CAUSALITY_AUDIT.json','CC4_SEMANTIC_CAUSALITY_AUDIT.json']:
        assert read(ROOT/n)['PASS']
    field=pd.read_csv(ROOT/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv').drop_duplicates('field')
    assert set(field.loc[field.allowed_for_historical_semantics,'field'])=={'user','submit_line'}
    assert field[field.field.isin(['name','submit_line','script'])].opaque_7hex_fraction.gt(.95).all()
    old={r['path']:r for r in read(V13/'LOCAL_EVIDENCE_MANIFEST.json')['files']}
    inputs=[]
    for p in [V13/'.local/CURRENT_STATE_FEATURES.parquet']+[V13/'.local'/f'fold{i}'/('EXPANDING_S4'+suffix) for i in range(1,6) for suffix in ['.json','.parquet','_quantiles.npz']]:
        assert sha(p)==old[str(p)]['sha256'],str(p);inputs.append(rec(p))
    membership={};support=pd.read_csv(V13/'TEMPORAL_FOLD_SUPPORT.csv')
    for i in range(1,6):
        for role in ['TRAIN','CAL','VALID']:
            p=V9/'.local'/f'fold{i}'/(role+'.parquet');f=pd.read_parquet(p,columns=['job_id'])
            digest=common13.ids(f);expected=support[support.fold.eq(i)&support.role.eq(role)].iloc[0]
            assert digest==expected.membership and len(f)==expected.N
            membership[f'{i}_{role}']=dict(N=len(f),membership=digest,file=rec(p))
    write('RUNTIME_INPUT_RECEIPT.json',dict(time=now(),memberships=membership,state_and_R0=inputs,
        semantic_projection=rec(LOCAL/'GPU_SUBMISSION_METADATA.parquet'),all_roles_unchanged=True))
    protocol=read(V13/'EXPERIMENT_PROTOCOL.json')
    code=[REPO/'v42'/n for n in ['semantic_adapter.py','semantic_state.py','runtime_provider_contract.py','policy.py','contracts.py']]+[ROOT/'runtime15.py']
    registration=dict(time=now(),before_new_validation_metrics=True,
        allowed_fields=read(ROOT/'SEMANTIC_FIELD_WHITELIST.json'),field_audit=rec(ROOT/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv'),
        authority=rec(ROOT/'SUBMISSION_SEMANTIC_AUTHORITY.json'),
        Runtime=dict(arms=dict(R0='Exact frozen V13 EXPANDING_S4 C0 reuse',R1='R0 + SEM_RECURRENCE_V1',R2='R0 + SEM_COOCCUR32_V1 + SEM_RECURRENCE_V1',R3='NOT_APPLICABLE'),
            folds=rec(V13/'TEMPORAL_FOLD_CONTRACT.json'),memberships=membership,learner=protocol['learner'],gates=protocol['gates'],ranking=protocol['ranking'],
            calibration='Frozen primary C0; no calibration family search',
            material_benefit='(min-fold increase >= .05 OR gt4h increase >= .05) AND Q90 pinball relative increase <= .05',
            ablation='No broad ablation unless material benefit; R2-R1 is the planned incremental contrast',
            semantic_fit='Each fold TRAIN only, no CAL/VALID frequencies or targets'),
        CC4=dict(user_frozen_C0='T0/B0 hourly submitted GPUh LightGBM; unchanged target/resolution/family',
            arms=dict(C0='Exact A0/B0 frozen prediction reuse',C1='C0 + past semantic state',C2='C1 + TRAIN-only KMeans8 composition',C3='NOT_RUN_OPTIONAL_NOT_PREREGISTERED'),
            parameters=dict(num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,deterministic=True,force_col_wise=True,random_state=20260924,verbosity=-1),
            quantiles=[.5,.9],transformation='log1p label, expm1 prediction, nonnegative, Q90>=Q50; no cap',
            fits='Exact daily expanding non-PURGE matured TRAIN membership and half-life30 weights inherited from T0/B0',
            semantic_fit='One SVD32 and KMeans8 on GPU submission records in frozen TRAIN target dates with submit before first DEVELOPMENT issue; no label input. Reuse transformer unchanged thereafter.',
            state='Strict submit<issue; 1/6/24/72h 32D centroid,count,dispersion,recurrence. Scalar L2 changes1h-24h,6h-72h. C2 K8 count/fraction/entropy1/6/24h plus fraction change1h-24h. Unavailable account/script-family fractions omitted, not fabricated.',
            periods='Existing ledger roles only, pre-April target days and matured labels before 2025-04-01 UTC; no April/May payload decoding. OOS_EXTENSION original eligible=False preserved and reported separately.',
            selection='DEVELOPMENT raw nominal .88..92 preferred, then Q90 pinball, calibration error, requirement ratio, arm. No test reselection.',
            calibration='Existing signed per-slot finite-rank residual, ceil(.9*(n+1)), min20 past mature DEV/CAL days; frozen mature CAL offset before first EXPOSED_EVALUATION; Q90>=Q50 and 0, no cap',
            support_gate='Against C0 in pre-April EXPOSED_EVALUATION and OOS_EXTENSION: paired raw pinball 95% CI upper<0 for both 1/7-day block bootstraps; Q50 WAPE noninferior; raw and calibrated requirement ratio noninferior; calibrated coverage .88..92; burst coverage noninferior. Failure keeps C0, no automatic operational promotion.',
            bootstrap=dict(draws=2000,blocks=[1,7],seed=20260928),burst='Frozen TRAIN positive T0 Q95, no VALID threshold tuning',
            operational_scope='Inherited logical event-time and request-version limitations remain; feature support is separate from operational model authorization'),
        privacy='Raw future strings ephemeral, repr redacted; persisted only namespace-separated pseudonyms/numeric features; no optimizer strings.',
        implementation_sha256={p.relative_to(REPO).as_posix():sha(p) for p in code},
        CC4_implementation_freeze='Bind separate CC4 execution code before any C1/C2 training; algorithm above cannot change based on Runtime results.',
        execution_order=['field audit','adapter','parity/causality fixtures','registration','Runtime R1/R2 sequential','CC4 C1/C2 sequential phase','freeze/report'],
        prohibited=['private RADDiT recovery','distributed RADDiT vectors','large LLM','April selection','May payload','optimizer/physics changes','OpenDSS'],
        synthetic_unit_fits='One toy SVD and KMeans used for pretraining contract tests only, separately recorded')
    write('PREREGISTRATION.json',registration)
    write('PREREGISTRATION_HASH.json',dict(time=now(),sha256=sha(ROOT/'PREREGISTRATION.json'),new_historical_model_fits_before_freeze=0))
    print('REGISTERED',sha(ROOT/'PREREGISTRATION.json'),flush=True)
if __name__=='__main__':main()
