"""Phase 0 audit and preregistration. Does not import or fit estimators."""
import platform
import sys
import importlib.metadata
from .common import *

def main():
    assert git('rev-parse','HEAD')==BASE
    assert not (OUT/'models').exists()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'.gitattributes').write_text('* -text\n')
    request=Path('C:/Users/kjw39/.codex/attachments/fb540a25-08c3-4ddf-a051-2ae51ee52e0c/pasted-text.txt')
    (OUT/'USER_REQUEST.txt').write_bytes(request.read_bytes())
    r4=json.loads((S4/'V40S4_FINAL_COMMIT_RECEIPT.json').read_text())
    r3=json.loads((S3/'V40S3_FINAL_COMMIT_RECEIPT.json').read_text())
    decision=json.loads((S4/'V40S4_FINAL_DECISION.json').read_text())
    assert git('rev-parse',SCI4)==SCI4 and git('rev-parse',BASE)==BASE
    assert git('log','-1','--format=%H',BASE,'--',str((S4/'V40S4_FINAL_COMMIT_RECEIPT.json').relative_to(ROOT)).replace('\\','/'))==BASE
    assert ancestor(SCI3,REC3) and ancestor(REC3,SCI4) and ancestor(SCI4,BASE)
    assert r4['scientific_commit']==SCI4 and r4['S3_scientific_commit']==SCI3 and r4['S3_receipt_base']==REC3
    assert r4['final_classification']==decision['classification']=='V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT'
    assert r4['selected'] is None and decision['selected'] is None and decision['optimizer_integration']=='NO'
    assert r4['git_status_after_scientific_commit']=='CLEAN' and git('status','--porcelain',cwd=S4ROOT)==''
    assert git('rev-parse','HEAD',cwd=S4ROOT)==BASE
    assert r3['scientific_commit']==SCI3
    assert git('diff','--name-only',SCI4,BASE).splitlines()==['dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_FINAL_COMMIT_RECEIPT.json']
    verified={}
    for p,h in r4['owned_files_SHA256'].items():
        assert file_sha(ROOT/p)==h and file_sha(S4ROOT/p)==h,p
        assert sha(git('show',f'{BASE}:{p}',binary=True))==h,p
        verified[p]=h
    s3paths=git('ls-tree','-r','--name-only',BASE,'dayahead/v40s3','dayahead/artifacts/v40s3_body_tail_runtime_risk').splitlines()
    for p in s3paths:
        assert git('rev-parse',f'{REC3}:{p}')==git('rev-parse',f'{BASE}:{p}')
        assert (ROOT/p).read_bytes()==(S4ROOT/p).read_bytes()
    inventory=tree(BASE)
    write('START_STATE',dict(timestamp=now(),branch=git('branch','--show-current'),worktree=str(ROOT),base=BASE,
      isolated=True,S4_worktree_clean=True,allowed_scope=['dayahead/v40s5/**','dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/**','tests/dayahead/test_v40s5_*.py']))
    write('GIT_LINEAGE_AUDIT',dict(status='PASS',S4_scientific=SCI4,S4_receipt=BASE,S3_scientific=SCI3,S3_receipt=REC3,
      all_ancestry_checks=True,S4_receipt_only_commit=True,S4_receipt_resolved=BASE,S4_worktree_clean=True,
      inherited_entries=len(inventory),S4_owned_verified=len(verified),S3_preserved=len(s3paths)))
    write('S4_REFERENCE_FREEZE',dict(classification=decision['classification'],selected_track='NONE',selected_u='NONE',selected_body='NONE',
      selected_classifier='NONE',selected_eta='NONE',selected_robust_policy='NONE',optimizer_integration='NO',
      owned_SHA256=verified,receipt_SHA256=file_sha(S4/'V40S4_FINAL_COMMIT_RECEIPT.json'),S4_retrained=False,
      interpretation='Request-state proxy metadata did not make S4 selective architecture operationally safe; preserved as evidence.'))
    write('PROTECTED_SCOPE_START',dict(base=BASE,entries=inventory,entry_count=len(inventory),S4_verified=verified,S3_preserved_paths=s3paths))

    assert file_sha(SOURCE)==SOURCE_SHA
    source=pd.read_parquet(SOURCE,columns=['job_id','submit_time','start_time','end_time','runtime_seconds',*FEATURES])
    source['source_row_identity']=[SOURCE_SHA+':row:'+str(i) for i in range(len(source))]
    source['job_uid']=source.job_id.astype(str)
    for c in ['submit_time','start_time','end_time']:
        source[c]=pd.to_datetime(source[c],utc=True)
        assert source[c].notna().all() and source[c].lt(pd.Timestamp('2025-04-24T00:00Z')).all()
    assert not source.job_uid.duplicated().any()
    np.testing.assert_array_equal(source.runtime_seconds,(source.end_time-source.start_time).dt.total_seconds())
    valid=np.isfinite(source.runtime_seconds)&source.runtime_seconds.gt(0)
    mature=source.end_time.lt(CUTOFF)
    # S4 CLOCK fields are reused exactly. No actual time enters FEATURES.
    complete=source[CLOCK].notna().all(axis=1)
    lib=source[valid&mature&complete].sort_values(['end_time','job_uid'],kind='mergesort').reset_index(drop=True)
    assert len(lib)>0 and lib.end_time.lt(CUTOFF).all()
    lib.to_parquet(OUT/'V40S5_HISTORICAL_TRAINING_LIBRARY.parquet',index=False)
    proof=lib[['job_uid','submit_time','start_time','end_time','source_row_identity']].copy()
    proof['runtime_sec']=lib.runtime_seconds;proof['model_fit_cutoff']=CUTOFF
    proof['label_available_before_cutoff']=proof.end_time<CUTOFF
    proof.to_parquet(OUT/'V40S5_TRAINING_LABEL_AVAILABILITY_PROOF.parquet',index=False)
    fit,tune,boundary=temporal_split(lib)
    write('HISTORICAL_INTERNAL_SPLIT',dict(order=['end_time','job_uid'],fraction=.8,boundary=boundary,
      timestamp_block_to='HIST_TUNE',HIST_FIT_N=len(fit),HIST_TUNE_N=len(tune),HIST_FIT_ids=ids(fit.job_uid),HIST_TUNE_ids=ids(tune.job_uid),
      max_fit_end=fit.end_time.max(),min_tune_end=tune.end_time.min(),overlap=0))
    fdist={c:distribution(lib[c]) for c in NUM+['runtime_seconds']}
    fdist['actual_request_ratio']=distribution(lib.runtime_seconds/lib.requested_seconds)
    missing={c:dict(raw_missing=int(lib[c].isna().sum()),invalid_or_missing=int(numeric(lib[c],c).isna().sum()) if c in NUM else int(categories(lib[c]).eq('__UNKNOWN__').sum()) if c in CAT else int(lib[c].isna().sum())) for c in FEATURES}
    write('FEATURE_MISSINGNESS_AUDIT',dict(historical_N=len(lib),features=missing,feature_complete_means='All required fields constructible; numeric missing uses historical median+indicator; categorical missing UNKNOWN. CLOCK must exist.',
      complete_raw_valid_N=int(pd.DataFrame({c:numeric(lib[c],c).notna() for c in NUM}).all(axis=1).sum())))
    write('HISTORICAL_TRAINING_LIBRARY_AUDIT',dict(status='PASS',source_path=str(SOURCE),source_SHA256=SOURCE_SHA,
      source_rows=len(source),source_unique_jobs=source.job_uid.nunique(),positive_runtime_jobs=int(valid.sum()),zero_runtime_jobs=int(source.runtime_seconds.eq(0).sum()),
      negative_runtime_jobs=int(source.runtime_seconds.lt(0).sum()),nonfinite_runtime_jobs=int((~np.isfinite(source.runtime_seconds)).sum()),
      A_jobs_end_before_cutoff=int(mature.sum()),B_jobs_end_at_or_after_cutoff=int((~mature).sum()),
      C_feature_constructible_positive_mature_jobs=len(lib),D_exact_unique_training_jobs=lib.job_uid.nunique(),model_fit_cutoff=CUTOFF,
      library_SHA256=file_sha(OUT/'V40S5_HISTORICAL_TRAINING_LIBRARY.parquet'),
      earliest_submit=lib.submit_time.min(),latest_submit=lib.submit_time.max(),earliest_start=lib.start_time.min(),latest_end=lib.end_time.max(),
      distributions=fdist,categorical_frequencies={c:lib[c].value_counts(dropna=False).to_dict() for c in CAT},
      monthly_end_counts=lib.end_time.dt.strftime('%Y-%m').value_counts().sort_index().to_dict(),
      monthly_submit_counts=lib.submit_time.dt.strftime('%Y-%m').value_counts().sort_index().to_dict(),
      actual_gt_request_N=int((lib.runtime_seconds>lib.requested_seconds).sum()),actual_gt_request_fraction=float((lib.runtime_seconds>lib.requested_seconds).mean()),
      TRAINING_LIBRARY_FULL_BACKLOG_AUTHORITY='NO',TRAINING_LIBRARY_COMPLETE_CASE_SELECTION_LIMITATION='YES',
      source_warning='Existing exposed terminal-service complete-case source; not full cluster backlog. Zero durations audited then excluded uniformly. No terminal-success filter added.',
      source_payload_scope='Phase 0 reads authorized pre-Apr24 source label columns for counts, runtime identity and maturity audit; post-cutoff rows never enter fit or tuning.'))
    assert file_sha(S4/'V40S4_PENDING_ISSUE_PANEL.parquet')==PANEL_SHA
    panel_ids=pd.read_parquet(S4/'V40S4_PENDING_ISSUE_PANEL.parquet',columns=['job_id','job_issue_uid','issue_time','role'])
    expected=json.loads((S4/'V40S4_POPULATION_AUDIT.json').read_text())
    pchecks={}
    for role,d in panel_ids.groupby('role'):
        assert len(d)==EXPECTED[role] and ids(d.job_issue_uid)==expected['blocks'][role]['ID_SHA256']
        pchecks[role]=dict(N=len(d),unique_jobs=d.job_id.nunique(),ID_SHA256=ids(d.job_issue_uid))
    assert not set(lib.job_uid)&set(panel_ids.job_id.astype(str))
    write('PANEL_IDENTITY_AUDIT',dict(status='PASS',panel_SHA256=PANEL_SHA,exact_S4_file=True,blocks=pchecks,training_job_overlap=0,
      phase0_columns=['job_id','job_issue_uid','issue_time','role'],panel_outcome_scoring_before_freeze=False))
    (OUT/'V40S5_TRAINING_VS_EVALUATION_CONTRACT.md').write_text(
      'Historical fitting uses unique jobs with end < 2025-03-14T08:00:00Z, positive finite end-start, and constructible Track P proxy features. '
      'It is independent of PENDING membership. The immutable S4 panel is used for scheduler-facing job-issue evaluation only. '
      'Its TRAIN block is diagnostic, never model fitting. DEV+CAL select the candidate; EXPOSED is scored only after a committed freeze and is exposed historical evidence, not untouched confirmation. '
      'Primary denominator is job-issue. Earliest issue per job in each split is a secondary diagnostic with no reselection.\n',encoding='utf-8')
    feature=dict(assumption_id=ASSUMPTION,P=FEATURES,PW=fields('PW'),HISTORICAL_D1_SNAPSHOT_PROVENANCE='UNVERIFIED',
      ORIGINAL_SUBMISSION_VALUE_PROVENANCE='UNVERIFIED',REQUEST_MODIFICATION_HISTORY='UNOBSERVED',paper_label='ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL',
      excluded=['job_uid','job_id','user ID','account ID','username','job name','application identity','start_time','end_time','runtime_seconds','terminal status','K0','reference_safe_sec','future scheduler state','migration information','future electrical result'],
      mapping=json.loads((S4/'V40S4_PROXY_FEATURE_INVENTORY.json').read_text())['mapping'],GPU_weight='Recorded num_gpus_req, frozen separately from predictions')
    write('FEATURE_CONTRACT',feature)
    pre=dict(log1p=NUM,categorical=CAT,clock=CLOCK,numeric_missing='historical fit-subset median + explicit indicator',
      categorical_encoding='one-hot; UNKNOWN always represented',unseen='__UNKNOWN__',missing_categorical='__UNKNOWN__',target_encoding=False,
      fit_scope='HIST_FIT for tuning, strictly preceding historical subset for each OOF fold, whole mature library for final models',
      final_P=Preprocess('P').fit(lib).descriptor(),final_PW=Preprocess('PW').fit(lib).descriptor())
    write('PREPROCESSING_CONTRACT',pre)
    folds=[dict(fold=k,fit_N=len(a),valid_N=len(b),fit_ids=ids(a.job_uid),valid_ids=ids(b.job_uid),max_fit_end=a.end_time.max(),min_valid_end=b.end_time.min(),max_valid_end=b.end_time.max()) for k,a,b in temporal_folds(lib)]
    prereg=dict(timestamp=now(),name='V40S5_UNCERTAINTY_AWARE_DIRECT_RUNTIME',base=BASE,source_SHA256=SOURCE_SHA,panel_SHA256=PANEL_SHA,
      user_request_SHA256=file_sha(OUT/'USER_REQUEST.txt'),all_user_sections_binding=True,
      eligibility='end < cutoff AND positive finite end-start AND proxy feature constructible AND same source contract',cutoff=CUTOFF,
      feature_contract=feature,preprocessing=pre,historical_split=read('HISTORICAL_INTERNAL_SPLIT'),configs=CONFIGS,fixed_parameters=FIXED,
      model_family='LightGBM only',quantiles=QUANTILES,target='runtime_seconds in seconds; no target transform',
      tuning_score='Mean raw quantile pinball / HIST_TUNE mean actual runtime; shared configuration',
      tuning_tie_break=['Q99 pinball','raw crossing fraction','L0 then L1 then L2'],
      quantile_repair='Fixed physical lower bound max(raw,0), then cumulative maximum Q50,Q90,Q95,Q99; record both raw negatives and crossings. No upper cap.',
      residual=dict(folds=folds,OOF_Q50_config='L0',OOF_config_reason='Auxiliary median fixed before tuning so HIST_TUNE labels cannot affect any OOF prediction through hyperparameter selection.',
        final_residual_config='shared selected configuration',target='(runtime-Q50_OOF)^2',sigma='sqrt(max(predicted_r2,0))',
        warmup='First chronological sixth has no OOF label; excluded from residual model only',
        diagnostic_residual='One auxiliary instance on HIST_FIT OOF only; HIST_TUNE OOF squared errors for held-out permutation. No candidate search.'),
      UARP=dict(name='U1_PUBLISHED_STYLE_ADAPTIVE_RUNTIME',alpha=.20,beta=.50,formula='Q99+max(.20*Q99,.50*sigma)',walltime_cap=False),
      candidates=CANDIDATES,new_eligible=CANDIDATES[2:],selection_roles=ROLES[1:3],safety=dict(coverage=.90,GPU_coverage=.90,major_day_N=100,major_day_coverage=.88,major_day_GPU_coverage=.88,GPU_under='strictly less than RSP'),
      efficiency='GPU_over_h strictly less than requested walltime separately on DEV and CAL',
      selection_hierarchy=['CAL GPU_over_h','CAL GPU_under_sec','DEV+CAL GPU_over_h','DEV+CAL corresponding raw quantile pinball (Q99 for UARP)','Q90,Q95,Q99,UARP'],
      exposed='Committed selected candidate must pass all same gates; no refit or reselection after exposure',
      PW='Exactly one feature removal with shared config, same OOF fixed L0, quantiles and formula, after primary freeze and before exposed; if NONE all four fixed formulas diagnostic only, selected remains NONE',
      reproducibility='One independent P pipeline rebuild before exposed, same seed; compare all Qs,sigma and all candidate safe outputs; never choose better repeat',
      permutation='3 deterministic permutations per source feature; raw pinball on HIST_TUNE for HIST_FIT quantile models; MSE for auxiliary HIST_FIT residual; diagnostic only',
      shift='Training-decile edges for continuous predictors, unique edges, infinities outer; PSI probabilities floored at 1e-6; diagnostic only',
      slots='ceil(seconds/900) once for actual and candidate; no 96-slot truncation',unique_job='earliest issue per job per split; diagnostic only',
      firewalls=dict(shadow='SEALED',May_scientific_rows=0,optimizer=0,Gurobi=0,OpenDSS=0,Fresh=0),holds=HOLDS,
      failure='CURRENT_RSP_REMAINS_OPERATIONAL; DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA',
      paper=dict(authors='Jiheon Choi; Sangyoon Oh',title='UARP: uncertainty-aware runtime prediction for preventing scheduler termination under Wallclock constraints in HPC',
        year=2026,doi='10.1007/s11227-026-08422-8',url='https://link.springer.com/article/10.1007/s11227-026-08422-8',verified='Section 4.3 equation 2 and alpha=.2,beta=.5; section 4.4 Q99+margin',
        scope='Formula adaptation; not reproduction of paper datasets or scheduler results; chronological OOF is this experiment leakage control.'))
    write('PREREGISTRATION',prereg)
    write('MAY_FIREWALL',dict(shadow='SEALED',shadow_scientific_rows=0,May_runtime_rows=0,May_outcomes=0,May_training=0,May_calibration=0,May_selection=0,May_sensitivity=0,
      metadata_discovery='Nonzero Git path/index/blob-identity inventory, including earlier broad filename inventory; no sealed source scientific payload reads',
      total_metadata_reads_zero_claim=False,source_payload='Only hash-verified pre-Apr24 PREPARED_ROWS and S4 panel, role-filtered before exposure'))
    write('COMPUTE_LEDGER',dict(timestamp=now(),Python=sys.version,executable=sys.executable,CPU=platform.processor(),device='CPU',threads=1,seed=SEED,
      libraries={p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','lightgbm','pyarrow']},fits=[],inference=[],optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,holds=HOLDS))
    print(json.dumps(dict(source_N=len(source),positive=int(valid.sum()),mature_all=int(mature.sum()),training_N=len(lib),fit_N=len(fit),tune_N=len(tune),inherited_entries=len(inventory),S4_owned=len(verified),S3_preserved=len(s3paths),missingness=missing),indent=2))

if __name__=='__main__': main()
