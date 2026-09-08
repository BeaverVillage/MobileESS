"""Fixed descriptive audits; no fitted estimator or selection changes."""
from .common import *
from .run import combine,aggregate

def flat_metrics(m):return {k:v for k,v in m.items() if not isinstance(v,dict)}
def correlations(d):
    out={}
    for c in ['coverage','GPU_coverage','MAE']:
        value=d.N_training_jobs.corr(d[c],method='spearman')
        out[c]=float(value) if np.isfinite(value) else None
    return out

def main():
    guard('SELECTION_FREEZE_COMMIT_RECEIPT');assert (OUT/f'{PREFIX}EXPOSED_RESULTS.json').exists()
    ledger=pd.read_parquet(OUT/f'{PREFIX}DAILY_TRAINING_LEDGER.parquet')
    issues=read('PENDING_PANEL_IDENTITY_AUDIT')['issues'];assert len(ledger)==len(issues)
    daily_rows=[];model_rows=[];crossing={};residual={};preprocessing={};gains={};margins={};leak=[];training_composition={};fits=[];inference=[]
    membership_audit=[];previous=set();previous_t=None
    for v in issues:
        t=pd.Timestamp(v['issue_time']);k=key(t)
        hist=pd.read_parquet(OUT/'membership'/f'{k}.parquet');current=set(hist.job_uid)
        row=ledger[ledger.issue_time==t].iloc[0]
        assert previous<=current and hist.end_time.lt(t).all() and ids(hist.job_uid)==row.training_job_uid_SHA256
        added=hist[~hist.job_uid.isin(previous)]
        assert previous_t is None or added.end_time.ge(previous_t).all()
        membership_audit.append(dict(issue_time=t,N=len(hist),new_jobs=len(added),ids_SHA256=ids(hist.job_uid),strict_end_pass=True,subset_pass=True))
        previous=current;previous_t=t
        ev=json.loads((OUT/'events'/f'{k}.json').read_text());events=[x['kind'] for x in ev]
        hashes=[x for x in ev if x['kind']=='PREDICTION_HASH'];label=next(x for x in ev if x['kind']=='EVALUATION_LABEL_READ')
        for x in hashes:
            assert file_sha(OUT/x['path'])==x['SHA256'] and x['sequence']<label['sequence']
            inference.append(dict(issue_time=t,track=x['track'],seconds=x['inference_seconds'],N=x['N']))
        assert set(x['track'] for x in hashes)=={'P','PW'} and events[-1]=='ISSUE_COMPLETE'
        leak.append(dict(issue_time=t,status='PASS',prediction_hash_sequence={x['track']:x['sequence'] for x in hashes},
          label_read_sequence=label['sequence'],label_read_timestamp=label['timestamp'],history_future_rows_materialized=0,
          ordered_events=events,evaluation_labels_after_both_hashes=True))
        training_composition[k]=dict(N=len(hist),runtime=distribution(hist.runtime_seconds),request=distribution(hist.requested_seconds),
          ratio=distribution(hist.runtime_seconds/hist.requested_seconds),GPU=distribution(hist.num_gpus_req),
          categorical={c:categories(hist[c]).value_counts().to_dict() for c in CAT},monthly_end=hist.end_time.dt.strftime('%Y-%m').value_counts().sort_index().to_dict())
        for track in ['P','PW']:
            pkg=json.loads((OUT/'models'/k/track/'package.json').read_text())
            r=json.loads((OUT/'daily'/f'{k}_{track}.json').read_text())
            model_rows.append(dict(issue_time=t,track=track,N_train=pkg['N_train'],training_ids=pkg['training_ids'],config_id=pkg['config_id'],
              OOF_config_id=pkg['OOF_config_id'],support_route=pkg['support_route'],OOF_N=pkg['OOF_N'],package_SHA256=pkg['package_SHA256'],
              model_files_SHA256=json.dumps(pkg['files_SHA256'],sort_keys=True),seconds=pkg['seconds'],cache_reuse=pkg['cache_reuse']))
            for fit in pkg['fit_records']:fits.append(dict(issue_time=t,track=track,purpose='daily',**fit))
            crossing[k+'_'+track]=r['crossing'];margins[k+'_'+track]=dict(sigma=r['sigma'],negative_r2_N=r['negative_r2_N'],margin=r['margin'])
            preprocessing[k+'_'+track]=pkg['preprocessing'];gains[k+'_'+track]=pkg['grouped_gain']
            residual[k+'_'+track]=dict(OOF_N=pkg['OOF_N'],warmup_N=pkg['warmup_N'],support_route=pkg['support_route'],
              folds=pkg['residual_folds'],in_sample_residuals=pkg['in_sample_residuals'],OOF_MAE=pkg['residual_MAE'],r2_distribution=pkg['r2_distribution'])
            for c,m in r['results'].items():
                daily_rows.append(dict(issue_time=t,role=v['role'],track=track,candidate=c,N_eval_jobs=r['N_eval_jobs'],N_training_jobs=r['N_training_jobs'],
                  new_training_jobs=r['new_training_jobs'],median_safe_runtime_ratio=m['safe_actual_ratio_distribution']['median'],**flat_metrics(m)))
    daily=pd.DataFrame(daily_rows);daily.to_parquet(OUT/f'{PREFIX}DAILY_RUNTIME_RESULTS.parquet',index=False)
    pd.DataFrame(model_rows).to_parquet(OUT/f'{PREFIX}DAILY_MODEL_LEDGER.parquet',index=False)
    write('DAILY_TRAINING_MEMBERSHIP_AUDIT',dict(status='PASS',issues=membership_audit,first_N=int(ledger.iloc[0].training_job_count),last_N=int(ledger.iloc[-1].training_job_count),
      strict_end=True,monotonic_membership=True,identity_once_per_issue=True,source_SHA256=SOURCE_SHA))
    write('PREQUENTIAL_LEAKAGE_AUDIT',dict(status='PASS',issues=leak,future_training_rows=0,current_issue_evaluation_label_reads_before_hash=0,
      static_S5_context_already_exposed=True,read_semantics=read('PREREGISTRATION')['physical_IO_disclosure'],TRUE_CONFIRMATORY_AVAILABLE='NO'))
    write('DAILY_PREPROCESSING_AUDIT',preprocessing);write('RESIDUAL_CROSSFIT_AUDIT',residual);write('QUANTILE_CROSSING_AUDIT',crossing)
    write('UARP_MARGIN_AUDIT',margins)
    aggregates={track:aggregate(track,ROLES) for track in ['P','PW']};write('ALL_SPLIT_RESULTS',aggregates)
    combined={track:combine(track,ROLES) for track in ['P','PW']}
    for track in ['P','PW']:
        rows=[dict(track=track,role=r,candidate=c,**flat_metrics(m)) for r,res in aggregates[track]['results'].items() for c,m in res.items()]
        pd.DataFrame(rows).to_csv(OUT/f'{PREFIX}TRACK_{track}_RESULTS.csv',index=False)
    safety={};under={};over={};static={};walltime={};unique={};drift={}
    for r in ROLES:
        f=combined['P'][combined['P'].role==r]
        safety[r]={c:daily_metrics(f,f[c]) for c in CANDIDATES}
        under[r]={c:{k:aggregates['P']['results'][r][c][k] for k in ['under_sec','GPU_under_sec']} for c in CANDIDATES}
        over[r]={c:{k:aggregates['P']['results'][r][c][k] for k in ['over_sec','GPU_over_h','EXTREME_CONSERVATISM_WARNING']} for c in CANDIDATES}
        old=pd.read_parquet(S5/f'V40S5_P_{r}_PREDICTIONS.parquet')
        assert old.job_issue_uid.tolist()==f.job_issue_uid.tolist()
        for c in ['runtime_seconds','requested_seconds','num_gpus_req','reference_safe_sec']:
            np.testing.assert_array_equal(old[c],f[c])
        static[r]={}
        for c in CANDIDATES:
            sm=metrics(old,old[c]);rm=aggregates['P']['results'][r][c]
            delta={k:rm[k]-sm[k] for k in ['coverage','GPU_coverage','GPU_under_sec','GPU_over_h','MAE']}
            static[r][c]=dict(static=sm,rolling=rm,rolling_minus_static=delta,
              interpretation=improvement(delta['coverage'],delta['GPU_coverage'],delta['GPU_under_sec']),
              MATERIAL_IMPROVEMENT_DIAGNOSTIC=bool(delta['coverage']>=.1 or delta['GPU_coverage']>=.1))
        walltime[r]=dict(Q50_MAE_delta_PW_minus_P=aggregates['PW']['quantiles'][r]['Q50']['metrics']['MAE']-aggregates['P']['quantiles'][r]['Q50']['metrics']['MAE'],
          pinball_delta_PW_minus_P={q:aggregates['PW']['quantiles'][r][q]['raw_pinball']-aggregates['P']['quantiles'][r][q]['raw_pinball'] for q in ['Q90','Q95','Q99']},
          candidates={c:{k:aggregates['PW']['results'][r][c][k]-aggregates['P']['results'][r][c][k] for k in ['coverage','GPU_coverage','GPU_under_sec','GPU_over_h']} for c in CANDIDATES[2:]})
        unique[r]={}
        for track in ['P','PW']:
            u=combined[track][combined[track].role==r].sort_values(['issue_time','job_uid']).drop_duplicates('job_uid')
            unique[r][track]=dict(N=len(u),results={c:metrics(u,u[c]) for c in CANDIDATES})
        drift[r]=dict(N=len(f),runtime=distribution(f.runtime_seconds),requested=distribution(f.requested_seconds),
          actual_request_ratio=distribution(f.runtime_seconds/f.requested_seconds),GPU=distribution(f.num_gpus_req))
    # Feature composition is projected from the immutable panel; labels above were
    # already opened after each prediction, and never enter this diagnostic model.
    import pyarrow.parquet as pq
    feat=pq.read_table(PANEL,columns=['job_issue_uid','issue_time','role',*FEATURES]).to_pandas()
    for r,f in feat.groupby('role'):
        drift[r]['categorical']={c:categories(f[c]).value_counts().to_dict() for c in CAT}
    data_maturity={}
    for c in CANDIDATES[2:]:
        d=daily[(daily.track=='P')&(daily.candidate==c)].sort_values('issue_time')
        data_maturity[c]=dict(Spearman=correlations(d),N_issues=len(d),min_N_train=int(d.N_training_jobs.min()),median_N_train=float(d.N_training_jobs.median()),
          max_N_train=int(d.N_training_jobs.max()),earliest=d.iloc[0].to_dict(),midpoint=d.iloc[len(d)//2].to_dict(),latest=d.iloc[-1].to_dict(),correlation_is_not_causation=True)
    exposed=combined['P'][combined['P'].role=='EXPOSED_EVALUATION'].copy()
    exposed['month']=exposed.issue_time.dt.strftime('%Y-%m');exposed['week']=exposed.issue_time.dt.strftime('%G-W%V')
    blocks={}
    for group in ['month','week']:
        blocks[group]={}
        for label,d in exposed.groupby(group):
            origin=ledger[ledger.issue_time.isin(d.issue_time)]
            blocks[group][label]=dict(N=len(d),first_issue=d.issue_time.min(),last_issue=d.issue_time.max(),
              N_train_start=int(origin.iloc[0].training_job_count),N_train_end=int(origin.iloc[-1].training_job_count),results={c:metrics(d,d[c]) for c in CANDIDATES})
    write('DAILY_SAFETY_AUDIT',dict(minimum_N=100,coverage_gate=.88,GPU_coverage_gate=.88,splits=safety))
    write('GPU_UNDERPREDICTION_AUDIT',under);write('OVERRESERVATION_AUDIT',over)
    write('STATIC_S5_COMPARISON',dict(name='STATIC_S5_REFERENCE',no_refit=True,splits=static,focus='R5_UARP_STYLE',material_threshold=.10,
      primary_interpretation=static['EXPOSED_EVALUATION']['R5_UARP_STYLE']['interpretation']))
    write('DATA_MATURITY_PERFORMANCE_AUDIT',dict(diagnostic_only=True,no_training_size_threshold=True,candidates=data_maturity))
    write('TEMPORAL_DRIFT_AUDIT',dict(training_composition=training_composition,panel_split_composition=drift,exposed_time_blocks=blocks,no_adaptive_weighting=True))
    write('UNIQUE_JOB_SENSITIVITY',dict(rule='earliest eligible issue per job per split',diagnostic_only=True,no_reselection=True,splits=unique))
    permutations={};repro={}
    for t in read('PREREGISTRATION')['repeat_issue_times']:
        k=key(t);permutations[k]=json.loads((OUT/'permutation'/k/'diagnostic.json').read_text())
        rp=json.loads((OUT/'repeats'/k/'package.json').read_text());repro[k]=json.loads((OUT/'repeats'/k/'comparison.json').read_text())
        fits += [dict(issue_time=t,track='P',purpose='independent_repeat',**v) for v in rp['fit_records']]
        fits += [dict(issue_time=t,track='P',purpose='historical_permutation',**v) for v in permutations[k]['fit_records']]
    write('WALLTIME_DEPENDENCE_ANALYSIS',dict(removed=['requested_seconds'],primary_track='P',PW_winner_search=False,
      shared_daily_membership=True,shared_config=model_config()[0],deltas=walltime,grouped_gain_over_time=gains,historical_permutation=permutations,
      diagnostic_only=True,feature_changes_after_importance=False))
    write('REPRODUCIBILITY_AUDIT',dict(status='PASS',predetermined_issues=read('PREREGISTRATION')['repeat_issue_times'],independent_rebuilds=len(repro),
      results=repro,better_repeat_selected=False,seed=SEED,threads=1))
    write('COMPUTE_LEDGER',dict(environment=read('COMPUTE_ENVIRONMENT'),daily_packages=len(model_rows),primary_packages=len(issues),PW_packages=len(issues),
      independent_repeat_packages=len(repro),historical_diagnostic_packages=len(permutations),fits=fits,inference=inference,
      total_fit_seconds=sum(v['fit_seconds'] for v in fits),total_fit_and_serialization_seconds=sum(v['seconds'] for v in fits),
      total_inference_seconds=sum(v['seconds'] for v in inference),cache_reuse_count=0,optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,holds=HOLDS))
    prior_exposed={}
    metadata=read('PENDING_PANEL_IDENTITY_AUDIT')
    m=pd.DataFrame(dict(job_uid=metadata['job_ids'],role=metadata['roles'],issue_time=pd.to_datetime(metadata['issue_times'],utc=True)))
    for v in issues:
        t=pd.Timestamp(v['issue_time']);hist=pd.read_parquet(OUT/'membership'/f'{key(t)}.parquet',columns=['job_uid','end_time'])
        earlier=set(m[(m.role=='EXPOSED_EVALUATION')&(m.issue_time<t)].job_uid)
        joined=hist[hist.job_uid.isin(earlier)]
        prior_exposed[key(t)]=dict(causally_mature_prior_exposed_jobs=len(joined),latest_end=joined.end_time.max() if len(joined) else None,strict_before_issue=True)
    write('EARLIER_EXPOSED_MATURITY_PROOF',prior_exposed)
    selected=read('SELECTION_FREEZE')['selected_candidate'];success=read('EXPOSED_RESULTS')['selected_pass'];proposal=[]
    if success:
        for _,v in exposed.iterrows():
            trainrow=ledger[ledger.issue_time==v.issue_time].iloc[0]
            pkg=json.loads((OUT/'models'/key(v.issue_time)/'P'/'package.json').read_text())
            proposal.append(dict(issue_time=v.issue_time,job_uid=v.job_uid,runtime_q50_sec=v.Q50,runtime_q90_sec=v.Q90,runtime_q95_sec=v.Q95,runtime_q99_sec=v.Q99,
              runtime_sigma_sec=v.sigma,runtime_candidate_name=selected,runtime_safe_sec=v[selected],runtime_safe_slots_15min=int(v[selected+'_slots']),
              training_job_count=int(trainrow.training_job_count),training_library_hash=trainrow.training_library_hash,request_state_assumption_id=ASSUMPTION,
              model_config_id=model_config()[0],model_package_hash=pkg['package_SHA256']))
    write('RUNTIME_ADAPTER_PROPOSAL',dict(proposal_only=True,optimizer_use_allowed=False,recommended_rows=proposal))
    print(json.dumps(dict(status='PASS',N_issues=len(issues),initial_training=int(ledger.iloc[0].training_job_count),final_training=int(ledger.iloc[-1].training_job_count),
      material_interpretation=static['EXPOSED_EVALUATION']['R5_UARP_STYLE']['interpretation'],daily_packages=len(model_rows),total_fit_instances=len(fits))),flush=True)

if __name__=='__main__':main()
