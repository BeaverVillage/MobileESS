"""Read-only parent verification and complete policy freeze before any R1 fit."""
import sys
import platform
import importlib.metadata
import pyarrow.parquet as pq
from .common import *
from .data import history

def main():
    assert git('rev-parse','HEAD')==BASE and not (OUT/'models').exists()
    assert git('rev-parse','HEAD',cwd=S5ROOT)==BASE and git('status','--porcelain',cwd=S5ROOT)==''
    assert git('log','-1','--format=%H',BASE,'--','dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/V40S5_FINAL_COMMIT_RECEIPT.json')==BASE
    r=s5('FINAL_COMMIT_RECEIPT');decision=s5('FINAL_DECISION')
    assert r['scientific_commit']==S5SCIENCE and ancestor(S5SCIENCE,BASE)
    assert r['classification']==decision['classification']=='V40S5_DIRECT_RUNTIME_SAFETY_FAIL'
    assert r['selected_model'] is None and decision['selected_model'] is None
    assert all(decision[c]=='NO' for c in ['CURRENT_RSP_REPLACED','optimizer_integration','production_ready'])
    assert all((S5/p).exists() for p in r['required_artifacts'])
    checks={}
    for p,h in r['owned_SHA256'].items():
        assert file_sha(ROOT/p)==file_sha(S5ROOT/p)==h,p
        assert sha(git('show',f'{S5SCIENCE}:{p}',binary=True))==h,p
        checks[p]=h
    assert git('diff','--name-only',S5SCIENCE,BASE).splitlines()==['dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/V40S5_FINAL_COMMIT_RECEIPT.json']
    previous_verify=subprocess.check_output([sys.executable,'-B','-m','dayahead.v40s5.closeout','verify'],cwd=S5ROOT)
    verified=json.loads(previous_verify);assert verified['status']=='PASS' and verified['receipt_commit']==BASE
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'.gitattributes').write_text('* -text\n')
    request=Path('C:/Users/kjw39/.codex/attachments/265b5a5f-42bc-405e-9743-1bd12a9fd233/pasted-text.txt')
    (OUT/'USER_REQUEST.txt').write_bytes(request.read_bytes())
    initial=s5('HISTORICAL_TRAINING_LIBRARY_AUDIT');split=s5('HISTORICAL_INTERNAL_SPLIT')
    review=(S5/'V40S5_FINAL_REVIEW.md').read_text(encoding='utf-8')
    assert str(initial['D_exact_unique_training_jobs']) in review and '8시간' in review
    write('START_STATE',dict(timestamp=now(),working_name='V40S5R1_ROLLING_ORIGIN_UNCERTAINTY_RUNTIME',branch=git('branch','--show-current'),
      worktree=str(ROOT),base=BASE,parent_fully_closed=True,parent_verification=verified,optimizer_integration='NO'))
    write('GIT_LINEAGE_AUDIT',dict(status='PASS',S5_scientific=S5SCIENCE,S5_receipt=BASE,S4_scientific=r['S4_scientific'],S4_receipt=r['S4_base'],
      S3_scientific=r['S3_scientific'],S3_receipt=r['S3_receipt'],all_ancestry_verified=all(ancestor(a,b) for a,b in [
        (r['S3_scientific'],r['S3_receipt']),(r['S3_receipt'],r['S4_scientific']),(r['S4_scientific'],r['S4_base']),(r['S4_base'],S5SCIENCE),(S5SCIENCE,BASE)])))
    write('S5_REFERENCE_FREEZE',dict(classification=decision['classification'],selected_model=None,CURRENT_RSP_REPLACED='NO',optimizer_integration='NO',production_ready='NO',
      historical_positive_jobs=initial['D_exact_unique_training_jobs'],HIST_FIT=split['HIST_FIT_N'],HIST_TUNE=split['HIST_TUNE_N'],
      initial_library_limitation=initial,model_config=s5('HYPERPARAMETER_FREEZE'),verified_SHA256=checks,S5_owned_scientific_files=len(checks),
      receipt_SHA256=file_sha(S5/'V40S5_FINAL_COMMIT_RECEIPT.json'),static_models_refitted=False,source_warning=initial['source_warning']))
    inventory=tree(BASE)
    write('PROTECTED_SCOPE_START',dict(base=BASE,entries=inventory,entry_count=len(inventory),parent_owned_SHA256=checks,
      allowed=['dayahead/v40s5r1/**','dayahead/artifacts/v40s5r1_rolling_origin_runtime/**','tests/dayahead/test_v40s5r1_*.py']))
    assert file_sha(PANEL)==PANEL_SHA and file_sha(SOURCE)==SOURCE_SHA
    f=pq.read_table(PANEL,columns=['job_id','job_issue_uid','issue_time','role']).to_pandas()
    assert len(f)==sum(EXPECTED.values()) and f.job_id.nunique()==7603 and not f.job_issue_uid.duplicated().any()
    assert f.groupby('role').size().to_dict()==EXPECTED
    assert f.issue_time.dt.hour.eq(8).all() and f.issue_time.dt.minute.eq(0).all() and f.issue_time.dt.second.eq(0).all()
    checks_panel={}
    for role,d in f.groupby('role'):
        old=pq.read_table(S5/f'V40S5_P_{role}_PREDICTIONS.parquet',columns=['job_issue_uid']).to_pandas()
        assert d.job_issue_uid.tolist()==old.job_issue_uid.tolist()
        checks_panel[role]=dict(N=len(d),unique_jobs=d.job_id.nunique(),ordered_ids_SHA256=ordered_ids(d.job_issue_uid),ids_SHA256=ids(d.job_issue_uid))
    issues=[]
    for t,d in f.groupby('issue_time',sort=True):
        assert d.role.nunique()==1
        issues.append(dict(issue_time=t.isoformat(),role=d.role.iloc[0],N=len(d),ids_SHA256=ids(d.job_issue_uid),ordered_ids_SHA256=ordered_ids(d.job_issue_uid)))
    write('PENDING_PANEL_IDENTITY_AUDIT',dict(status='PASS',source_path=str(PANEL),panel_SHA256=PANEL_SHA,total_job_issue=len(f),unique_jobs=f.job_id.nunique(),
      blocks=checks_panel,issues=issues,unique_issue_times=len(issues),ordered_job_issue_ids=f.job_issue_uid.tolist(),
      job_ids=f.job_id.tolist(),roles=f.role.tolist(),issue_times=f.issue_time.map(lambda t:t.isoformat()).tolist(),
      timezone='fixed AEST UTC+10, D-1 18:00 = 08:00 UTC',missing_calendar_days='No artificial issues created; use exact nonempty stored issue timestamps',
      initial_read_columns=['job_id','job_issue_uid','issue_time','role'],initial_evaluation_label_columns=[]))
    first=pd.Timestamp(issues[0]['issue_time']);hist=history(first,log=False)
    old=pd.read_parquet(S5/'V40S5_HISTORICAL_TRAINING_LIBRARY.parquet')
    assert ids(hist.job_uid)==ids(old.job_uid) and len(hist)==initial['D_exact_unique_training_jobs']
    pd.testing.assert_frame_equal(hist.set_index('job_uid')[['submit_time',*LABELS,*FEATURES]].sort_index(),old.set_index('job_uid')[['submit_time',*LABELS,*FEATURES]].sort_index())
    rtimes=[]
    for role in ROLES:rtimes.append(next(v['issue_time'] for v in issues if v['role']==role))
    rtimes.append([v['issue_time'] for v in issues if v['role']=='EXPOSED_EVALUATION'][-1])
    config,params=model_config();oldpr=s5('PREREGISTRATION');feature=s5('FEATURE_CONTRACT')
    assert feature['P']==FEATURES and feature['assumption_id']==ASSUMPTION
    prereg=dict(timestamp=now(),working_name='V40S5R1_ROLLING_ORIGIN_UNCERTAINTY_RUNTIME',base=BASE,S5_scientific=S5SCIENCE,
      source_SHA256=SOURCE_SHA,panel_SHA256=PANEL_SHA,user_request_SHA256=file_sha(OUT/'USER_REQUEST.txt'),all_user_sections_binding=True,
      initial_N=len(hist),issue_count=len(issues),issue_times=[v['issue_time'] for v in issues],
      exact_S5_config_id=config,exact_S5_config=params,fixed_parameters=FIXED,quantiles=QUANTILES,target='raw runtime_seconds=end-start; no target transform',
      hyperparameter_tuning=False,feature_contract=feature,preprocessing=s5('PREPROCESSING_CONTRACT'),
      preprocessing_change='Same transformations; fit each origin on all mature history; each OOF map fitted only before its validation timestamp',
      membership='Unique same-source jobs with strict end_time < stored issue_time; runtime>0 finite; CLOCK available; numeric missing imputed exactly as S5',
      training_policy='EXPANDING_ALL_CAUSALLY_MATURE_HISTORY',one_primary_package_per_unique_issue=True,cache_reuse='NO',
      quantile_repair=oldpr['quantile_repair'],
      residual=dict(method='Exact S5 chronological expanding OOF squared residuals',OOF_Q50_config=oldpr['residual']['OOF_Q50_config'],
        OOF_config_reason=oldpr['residual']['OOF_config_reason'],final_config=config,support_rule={'N>=250':5,'100<=N<250':3,'N<100':'INSUFFICIENT_SUPPORT_STOP'},
        fold_boundaries='N/(folds+1) row-count boundaries sorted end_time,job_uid; entire boundary timestamp belongs to validation; no equal timestamp split',
        insufficient_distinct_boundary_timestamps='STOP; do not silently change folds',warmup='First chronological block excluded from residual targets',
        sigma='sqrt(max(predicted_r2,0))'),UARP=dict(formula='Q99+max(.20*Q99,.50*sigma)',coefficients=[.2,.5],walltime_cap=False),
      candidates=CANDIDATES,static_reference='Immutable S5 predictions, same row/order, no refit; payload comparisons after prediction hashes',
      sensitivity='Exactly one P-W using identical daily membership and policies; both tracks hash before any current issue label read; PW never selected',
      sequence=['HISTORICAL_READ strict predicate','FIT_P','PREDICT_P','HASH_P','FIT_PW','PREDICT_PW','HASH_PW','optional predetermined historical repeat/diagnostic','READ_CURRENT_LABELS','SCORE','ADVANCE'],
      evaluation_label_firewall='No current issue start/end/runtime materialized until both saved prediction files are hashed and verified',
      physical_IO_disclosure='Arrow may scan encoded pages to evaluate end_time predicate. Future source rows never materialized as scientific training rows. Hashing bytes is identity verification, not row-level outcome scoring.',
      prior_exposure='S5 historical outcomes and prior conversation already exposed; unread-before-hash is an enforced S5R1 execution/dataflow rule, not a claim of untouched data.',
      prequential='Earlier evaluation outcomes may enter a later issue training library only after their end < that later issue; no global future residual pool',
      selection_roles=['DEVELOPMENT','CALIBRATION'],safety=oldpr['safety'],efficiency=oldpr['efficiency'],
      selection_hierarchy=['all DEV safety','all CAL safety','DEV+CAL efficiency','min CAL GPU_over_h','CAL GPU_under_sec','DEV+CAL GPU_over_h','Q90,Q95,Q99,UARP simplicity'],
      exposed='Same daily policy continues after committed candidate freeze; no feature/config/coefficient/candidate changes; TRUE_CONFIRMATORY_AVAILABLE=NO',
      primary_denominator='JOB-ISSUE',unique_job='Earliest issue per job per reporting split, diagnostic only',metrics='Exact S5 metrics and 15min ceil(seconds/900) once, no 96-slot truncation',
      daily_diagnostics=['N_train','new jobs','coverage','GPU coverage','GPU under','GPU over','MAE','median safe/actual'],
      maturity=dict(earliest_midpoint_latest='Chronological indices 0,floor(N_issues/2),N_issues-1',correlations='Spearman unweighted daily N_train vs coverage,GPU coverage,MAE for all observed issues; descriptive only; no size threshold selection'),
      temporal=dict(distributions=['runtime','requested_seconds','actual/request','GPU request','partition','qos'],training_composition='per issue',exposed_blocks=['calendar month','ISO calendar week'],adaptive_weighting=False),
      material_improvement=dict(rule='coverage delta>=.10 OR GPU coverage delta>=.10 vs same static S5 candidate',diagnostic_only=True,
        primary_diagnostic_focus='R5_UARP_STYLE fixed before outcomes',categories=['ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME','ROLLING_UPDATE_SMALL_EFFECT','ROLLING_UPDATE_NO_GENERALIZATION_RECOVERY','ROLLING_UPDATE_DEGRADES_RUNTIME'],
        degradation='both coverage deltas<0 AND GPU_under delta>0',no_recovery='both coverage deltas<=0 without degradation; positive subthreshold effect is SMALL_EFFECT'),
      walltime_importance=dict(gain='Grouped source feature gain every daily final quantile/residual model',periodic_issue_times=rtimes,
        permutation='Exact S5 historical temporal 80/20 split, frozen L2 diagnostic instances; 3 seeded walltime permutations; no tuning or feature change'),
      repeat_issue_times=rtimes,repeat='One full independent P package rebuild at each predeclared origin before current labels; same seed; compare Q50,Q90,Q95,Q99,sigma,UARP; never select repeat',
      firewalls=dict(shadow='SEALED',shadow_scientific_rows=0,May_scientific_rows=0,optimizer=0,Gurobi=0,OpenDSS=0,Fresh=0),holds=HOLDS,
      stop_rule='On fail: CURRENT_RSP_REMAINS_OPERATIONAL; FURTHER_RUNTIME_MODEL_WORK=DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA; no next runtime experiment',
      paper=oldpr['paper'])
    write('PREREGISTRATION',prereg)
    write('MAY_FIREWALL',dict(shadow='SEALED',shadow_scientific_rows=0,May_runtime_rows=0,May_outcomes=0,May_feature_fitting=0,May_training=0,May_selection=0,May_calibration=0,May_sensitivity=0,
      metadata_discovery='Nonzero Git path/index/blob identity inventory and schema metadata; no sealed scientific rows read',total_metadata_reads_zero_claim=False,
      source='Same SHA-verified pre-Apr24 source as S5',exposed_semantics='EXPOSED PREQUENTIAL HISTORICAL EVIDENCE',TRUE_CONFIRMATORY_AVAILABLE='NO'))
    write('COMPUTE_ENVIRONMENT',dict(Python=sys.version,executable=sys.executable,CPU=platform.processor(),device='CPU',threads=1,seed=SEED,
      libraries={p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','lightgbm','pyarrow','scipy']}))
    print(json.dumps(dict(status='PASS',base=BASE,initial_training_N=len(hist),HIST_FIT=split['HIST_FIT_N'],HIST_TUNE=split['HIST_TUNE_N'],
      issue_count=len(issues),config=config,OOF_config=prereg['residual']['OOF_Q50_config'],repeat_dates=rtimes,base_entries=len(inventory))),flush=True)

if __name__=='__main__':main()
