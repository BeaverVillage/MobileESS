"""Target identities and distributions before fitting any forecasting family."""
from .common import *

def distribution(y):
    y=np.asarray(y,float); mean=y.mean(); std=y.std(ddof=1)
    return {'N':len(y),'mean':mean,'median':np.median(y),'std':std,
        **dict(zip(['P75','P90','P95','P99','maximum'],np.quantile(y,[.75,.9,.95,.99,1]))),
        'zero_fraction':np.mean(y==0),'positive_fraction':np.mean(y>0),
        'coefficient_of_variation':std/mean if mean>0 else None,
        'skewness':float(pd.Series(y).skew()) if len(y)>2 and std>0 else None}

def main():
    assert git('rev-parse','HEAD')==BASE
    assert not (OUT/'fits').exists(), 'PHASE0_MUST_PRECEDE_FIT'
    prior=external(R51/'V40R5R1_FINAL_COMMIT_RECEIPT.json')
    lineage=[R4REC,R5SCI,R5REC,prior['scientific_commit'],BASE]
    for a,b in zip(lineage,lineage[1:]): git('merge-base','--is-ancestor',a,b)
    assert git('log','-1','--format=%H','--','dayahead/artifacts/v40r5r1_zero_inflation_gate_correction/V40R5R1_FINAL_COMMIT_RECEIPT.json')==BASE
    original=ROOT.parent/'MobileESS_v40r5r1_zero_inflation_gate_correction'
    assert git('rev-parse','HEAD',cwd=original)==BASE and git('status','--porcelain',cwd=original)==''
    dump('START_STATE',{'base':BASE,'branch':git('branch','--show-current'),'worktree':ROOT,'time_UTC':utc(),
        'parent_R5R1_closed_clean':True,'R5R1_classification':prior['classification']})
    dump('GIT_LINEAGE_AUDIT',{'lineage':lineage,'independently_verified_Git_ancestry':True,
        'R5R1_receipt_resolved_from_file_history':BASE,'R5_preregistration':'9e77df9e3d607c2b1ef3ee9a6f18fe21b653634e',
        'R5_CAL_freeze':'2917efa8a3b56b2bc0b897574009eb96df3cd526'})
    dump('PROTECTED_SCOPE_START',snapshot())
    r5reg=external(R5/'V40R5_PREREGISTRATION.json')
    target_path=R5/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet'
    expected=r5reg['frozen_hashes'][target_path.relative_to(ROOT).as_posix()]
    actual=sha(target_path)
    if actual!=expected:
        dump('R5_TARGET_AUTHORITY_FREEZE',{'classification':'V40R6_TARGET_AUTHORITY_MISMATCH','expected':expected,'actual':actual})
        raise RuntimeError('V40R6_TARGET_AUTHORITY_MISMATCH')
    for name in ['data.npz','feature_availability.npz','seasonal_maturity_proof.parquet','inputs/V40R3_LABEL_MATURITY_LEDGER.parquet']:
        p=R5/name; assert sha(p)==r5reg['frozen_hashes'][p.relative_to(ROOT).as_posix()]
    atom=pd.read_parquet(target_path); a=np.load(R5/'data.npz')
    ledger=pd.read_parquet(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    y=atom.DeltaW15_GPUh.to_numpy().reshape(349,96)
    np.testing.assert_array_equal(y.ravel(),a['y'])
    assert len(atom)==33504 and len(ledger)==349
    assert np.array_equal(ledger.operating_day.to_numpy(),a['days'])
    parent=np.load(R5/'inputs/causal_dataset.npz')['target']
    error=float(np.max(np.abs(y.reshape(349,48,2).sum(2)-parent)))
    assert error<=1e-7 and abs(y.sum()-external(R5/'V40R5_15MIN_TARGET_CONTRACT.json')['total_GPUh'])<=1e-7
    dump('R5_TARGET_AUTHORITY_FREEZE',{'SHA256':actual,'expected_R5_preregistered_SHA256':expected,'match':True,
        'native_intervals':y.size,'days':349,'total_GPUh':y.sum(),'adjacent_pair_R4_max_error_GPUh':error,
        'R4_authority':'R5 frozen inputs/causal_dataset.npz:target','unit':'GPUh','label_modifications':False})
    split=external(R5/'V40R5_TEMPORAL_SPLIT_CONTRACT.json'); dump('TEMPORAL_SPLIT_CONTRACT',split)
    caldays=ledger.loc[ledger.role=='CALIBRATION','operating_day'].tolist(); mid=(len(caldays)+1)//2
    fitdays=caldays[:mid]; selectdays=caldays[mid:]
    subsplit={'rule':'Chronological calendar days; first ceil(N/2) then remainder; retain original stage maturity eligibility',
        'CAL_calendar_days':caldays,'CAL_FIT_days':fitdays,'CAL_SELECT_days':selectdays,
        'CAL_FIT_eligible_days':ledger.loc[ledger.operating_day.isin(fitdays)&ledger.stage_maturity_eligible,'operating_day'].tolist(),
        'CAL_SELECT_eligible_days':ledger.loc[ledger.operating_day.isin(selectdays)&ledger.stage_maturity_eligible,'operating_day'].tolist(),
        'no_day_split':True,'CAL_FIT_use':'uncertainty calibration only','CAL_SELECT_use':'candidate selection only',
        'maturity_cutoff':'Original R5 stage cutoff retained; offline historical split calibration, not a rolling live calibration claim'}
    dump('CAL_SUBSPLIT_CONTRACT',subsplit)
    frames=[]
    for di,row in ledger.iterrows():
        for h,slots in HORIZONS.items():
            count=97-slots
            values=np.lib.stride_tricks.sliding_window_view(y[di],slots).sum(axis=1)
            role=row.role
            if role=='CALIBRATION': role='CAL_FIT' if row.operating_day in fitdays else 'CAL_SELECT'
            frames.append(pd.DataFrame({'day':row.operating_day,'day_index':di,'issue_time':row.forecast_origin,
                'window_start_slot':np.arange(count),'window_end_slot_exclusive':np.arange(count)+slots,
                'horizon':h,'horizon_slots':slots,'horizon_hours':slots/4,'target_GPUh':values,
                'role':row.role,'analysis_role':role,'stage_maturity_eligible':row.stage_maturity_eligible,
                'target_available_at':row.target_label_available_at,'weekday':pd.Timestamp(row.operating_day).weekday()}))
    f=pd.concat(frames,ignore_index=True); f['row_id']=np.arange(len(f))
    assert len(f)==83760 and (f.groupby('day').size()==240).all()
    assert (f.window_end_slot_exclusive<=96).all()
    residual=np.array([abs(r.target_GPUh-y[r.day_index,r.window_start_slot:r.window_end_slot_exclusive].sum()) for r in f.itertuples()])
    assert residual.max()<=1e-7
    daily_error=np.max(np.abs(f.loc[f.horizon=='H24','target_GPUh'].to_numpy()-y.sum(1)))
    f.to_parquet(OUT/'V40R6_CUMULATIVE_TARGET.parquet',index=False)
    dump('CUMULATIVE_TARGET_AUDIT',{'total_rows':len(f),'days':349,'windows_per_day':240,
        'per_horizon_per_day':{h:97-s for h,s in HORIZONS.items()},'horizon_counts':f.groupby('horizon').size().to_dict(),
        'within_day_only':True,'native_atomic_target_unchanged':True,'sum_of_rolling_windows_is_not_distinct_work_mass':True})
    dump('CUMULATIVE_TARGET_IDENTITY_AUDIT',{'every_row_checked':len(f),'maximum_error_GPUh':residual.max(),
        'mean_error_GPUh':residual.mean(),'H24_daily_sum_max_error_GPUh':daily_error,'tolerance_GPUh':1e-7,
        'artificial_floating_correction':False,'PASS':True})
    dist={}; zero={}
    for h in HORIZONS:
        hf=f[f.horizon==h]
        roles={r:distribution(hf.loc[(hf.role==r)&hf.stage_maturity_eligible,'target_GPUh']) for r in split['roles']}
        months={m:distribution(g.target_GPUh) for m,g in hf.groupby(hf.day.str[:7])}
        sub={r:distribution(hf.loc[(hf.analysis_role==r)&hf.stage_maturity_eligible,'target_GPUh']) for r in ['CAL_FIT','CAL_SELECT']}
        dist[h]={'all_authority_rows':distribution(hf.target_GPUh),'mature_roles':roles,'monthly_all_authority_rows':months,'CAL_subblocks':sub}
        zero[h]={'all':dist[h]['all_authority_rows']['zero_fraction'],
            'mature_roles':{r:v['zero_fraction'] for r,v in roles.items()},'monthly':{m:v['zero_fraction'] for m,v in months.items()}}
    dump('HORIZON_DISTRIBUTION_AUDIT',{'before_fit':True,'time_UTC':utc(),'scope':'All frozen historical target authority, including exposed distributions, as explicitly requested; no forecast comparison',
        'by_horizon':dist})
    dump('ZERO_INFLATION_AUDIT',{'before_fit':True,'by_horizon':zero})
    feasibility={}
    for h in HORIZONS:
        feasibility[h]={}
        for role in ['TRAIN','DEVELOPMENT','CAL_FIT','CAL_SELECT','EXPOSED_EVALUATION']:
            yy=f.loc[(f.horizon==h)&f.stage_maturity_eligible&(f.analysis_role==role),'target_GPUh'].to_numpy()
            n=int((yy>0).sum()); low=(9*n+9)//10; high=39*n//40
            feasibility[h][role]={'positive_N':n,'zero_fraction':np.mean(yy==0),'positive_bounds':[.9,.975],
                'covered_integer_min':low,'covered_integer_max':high,'empirical_coverage_grid_feasible':n>0 and low<=high,
                'overall_upper_gate':None,'zero_inflation_structural_contradiction':False}
    dump('EVALUATION_GATE_FEASIBILITY_AUDIT',{'before_fit':True,'overall_coverage':'DIAGNOSTIC_ONLY',
        'no_zero_inflation_upper_gate_contradiction':True,'integer_grid_checked':True,'horizons':feasibility})
    features(f,a)
    dump('MAY_FIREWALL',{'May_scientific_reads':0,'Apr24_30_shadow_scientific_reads':0,'shadow_status':'SEALED',
        'metadata_path_index_discovery':'NONZERO: user request, Git worktree/index and inherited provenance',
        'scientific_sources':'Only frozen R5 data.npz, target, seasonal feature/maturity arrays and label ledger through Feb 2025',
        'R4_initial_sparse_checkout':'Inherited R4 files briefly materialized by Git worktree creation; removed by scoped sparse checkout; no scientific row queries',
        'hashing':'Inherited authority byte hashes and Git metadata; not parsed as May/shadow scientific rows',
        'new_external_sources':0,'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'Fresh_calls':0,
        'no_system_wide_access_monitor_claim':True,'holds':HOLDS})
    print(json.dumps(clean({'rows':len(f),'identity_error':residual.max(),'R4_pair_error':error,
        'CAL_calendar_split':[len(fitdays),len(selectdays)],'CAL_eligible_split':[len(subsplit['CAL_FIT_eligible_days']),len(subsplit['CAL_SELECT_eligible_days'])],
        'distributions':{h:dist[h]['all_authority_rows'] for h in HORIZONS}}),indent=2),flush=True)

def features(f,a):
    source_rows=f.day_index.to_numpy()*96+f.window_start_slot.to_numpy()
    inherited=a['X'][source_rows]; origin=ns(f.issue_time)
    av=np.load(R5/'feature_availability.npz')['available_ns'][source_rows]
    assert (av<=origin[:,None]).all()
    values=[inherited,f[['window_start_slot','horizon_hours']].to_numpy(dtype=np.float32)]
    names=list(a['feature_names'])+['window_start_slot','horizon_hours']
    proof=pd.DataFrame({'row_id':f.row_id,'issue_time_ns':origin,'inherited_source_row':source_rows,
        'inherited_latest_availability_ns':av.max(1),'inherited_available_by_issue':(av<=origin[:,None]).all(1),
        'deterministic_context_available_at_issue':True})
    rawproof=pd.read_parquet(R5/'seasonal_maturity_proof.parquet')
    lagvalues=[]; lagmasks=[]
    for col,lag in enumerate([7,14,21,28]):
        src=rawproof[rawproof.lag_days==lag].reset_index(drop=True)
        mature=a['seasonal_mask'][:,col].copy() & (src.parent_available_ns.to_numpy()<a['origin_ns'])
        sw=a['seasonal_w'][:,col].reshape(349,96); sm=mature.reshape(349,96)
        available=src.parent_available_ns.to_numpy().reshape(349,96)
        v=np.zeros(len(f)); valid=np.zeros(len(f),bool); at=np.zeros(len(f),np.int64)
        for r in f.itertuples():
            sl=slice(r.window_start_slot,r.window_end_slot_exclusive)
            valid[r.Index]=sm[r.day_index,sl].all()
            at[r.Index]=available[r.day_index,sl].max()
            if valid[r.Index]: v[r.Index]=sw[r.day_index,sl].sum()
        assert (at[valid]<origin[valid]).all()
        values.append(np.column_stack([v,valid]).astype(np.float32)); names += [f'cumulative_lag_{lag}d_GPUh',f'cumulative_lag_{lag}d_mature']
        proof[f'lag_{lag}d_latest_raw_availability_ns']=at
        proof[f'lag_{lag}d_complete_mature']=valid
        proof[f'lag_{lag}d_published_GPUh']=v
        lagvalues.append(v); lagmasks.append(valid)
    X=np.concatenate(values,axis=1).astype(np.float32)
    assert np.isfinite(X).all()
    np.savez_compressed(OUT/'features.npz',X=X,feature_names=np.array(names,dtype='U90'),
        lag_values=np.stack(lagvalues,1),lag_mature=np.stack(lagmasks,1),source_rows=source_rows)
    proof.to_parquet(OUT/'V40R6_FEATURE_MATURITY_PROOF.parquet',index=False)
    contract={'feature_names':names,'feature_count':len(names),'inherited_R5_features':61,
        'inherited_alignment':'Exact R5 vector at cumulative window start; no averages of future features',
        'additional_context':['window_start_slot','horizon_hours'],'cumulative_lags_days':[7,14,21,28],
        'lag_rule':'Sum exact R5 historical seasonal15 GPUh only when every member bin is mature and latest raw availability < current issue time',
        'unavailable_lag':'0 with mature=0; not an observed zero or missing-GPU replacement',
        'strict_derived_maturity':True,'inherited_availability_rule':'R5 available_at <= issue retained; deterministic computations at issue allowed',
        'future_realized_features':[],'burst_classifier_outputs':[],'external_inputs_added':[],
        'data_SHA256':sha(R5/'data.npz'),'R5_contract_SHA256':sha(R5/'V40R5_15MIN_FEATURE_MATRIX_CONTRACT.json'),
        'features_SHA256':sha(OUT/'features.npz'),'maturity_proof_SHA256':sha(OUT/'V40R6_FEATURE_MATURITY_PROOF.parquet'),
        'source_authority_limit':external(R5/'V40R5_FEATURE_AUTHORITY_AUDIT.json')['source_authority_limit']}
    dump('FEATURE_CONTRACT',contract)
    dump('FEATURE_AUTHORITY_AUDIT',{'PASS':True,**contract,'rows':len(f),'derived_usable_by_lag':dict(zip([7,14,21,28],[int(m.sum()) for m in lagmasks])),
        'raw_proof_source_SHA256':sha(R5/'seasonal_maturity_proof.parquet'),'R5_availability_SHA256':sha(R5/'feature_availability.npz')})

if __name__=='__main__': main()
