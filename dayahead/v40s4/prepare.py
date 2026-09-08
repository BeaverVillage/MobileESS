"""Identity, proxy binding and preregistration before any S4 model fit."""
import re
import subprocess
import importlib.metadata
from .common import *


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'models').exists()
    (OUT/'.gitattributes').write_text('* -text whitespace=cr-at-eol\n')
    request=Path('C:/Users/kjw39/.codex/attachments/1be1854a-b59f-4c53-a637-622bcf9b3589/pasted-text.txt')
    (OUT/'USER_REQUEST.txt').write_bytes(request.read_bytes())
    assert git('rev-parse','HEAD')==BASE and git('rev-parse','bfeb9c3')==BASE
    assert subprocess.run(['git','merge-base','--is-ancestor',S3SCIENCE,BASE],cwd=ROOT).returncode==0
    receipt=get('FINAL_COMMIT_RECEIPT',True);selection=get('METHOD_SELECTION',True)
    assert receipt['scientific_commit']==S3SCIENCE
    assert receipt['classification']=='V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT' and selection['selected'] is None
    assert receipt['holds']['optimizer_integration']=='NO'
    checks={}
    paths=git('ls-tree','-r','--name-only',BASE,'dayahead/v40s3','dayahead/artifacts/v40s3_body_tail_runtime_risk').splitlines()
    for p in paths:
        actual=(ROOT/p).read_bytes();assert actual==git('show',f'{BASE}:{p}',binary=True),p
        assert actual==(S3ROOT/p).read_bytes(),p
        checks[p]=sha(actual)
    required=get('ARTIFACT_MANIFEST',True)['required'];assert len(required)==44
    assert all((S3OUT/p).exists() for p in required)
    live=json.loads(subprocess.check_output(['C:/Program Files/GitHub CLI/gh.exe','pr','view','27','--repo','BeaverVillage/MobileESS','--json','headRefOid,headRefName,baseRefOid,baseRefName,updatedAt,url']))
    ancestry={x:subprocess.run(['git','merge-base','--is-ancestor',x,BASE],cwd=ROOT).returncode==0 for x in [receipt['starting_live_PR27_head'],S3SCIENCE,live['headRefOid']]}
    write('GIT_LINEAGE_AUDIT',dict(timestamp=now(),S3_starting_PR27_head=receipt['starting_live_PR27_head'],S3_scientific_commit=S3SCIENCE,S3_receipt=BASE,live_PR27_metadata_only=live,
          is_ancestor_of_S4_base=ancestry,live_merge_base=git('merge-base',BASE,live['headRefOid']),live_merged=False,S4_branch=git('branch','--show-current')))
    write('START_STATE',dict(timestamp=now(),branch=git('branch','--show-current'),worktree=str(ROOT),starting_HEAD=BASE,live_PR27_used_for='METADATA_ONLY',
          allowed_paths=['dayahead/v40s4/**','dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/**','tests/dayahead/test_v40s4_*.py']))
    write('S3_REFERENCE_FREEZE',dict(status='PASS',scientific_commit=S3SCIENCE,receipt_commit=BASE,classification=receipt['classification'],selected=None,
           required_artifacts=44,verified_file_SHA256=checks,verified_files=len(checks),retrained=False,classification_changed=False))
    tree=git('ls-tree','-r',BASE).splitlines()
    write('PROTECTED_SCOPE_START',dict(base=BASE,all_existing_Git_entries={r.split('\t')[1]:r.split('\t')[0] for r in tree},S3_SHA256=checks,
          protection='All inherited files protected, including5352 tracked paths; sparse paths checked by Git blob identity without payload scientific reads'))
    assumption=dict(assumption_id=ASSUMPTION,REQUEST_STATE_ROLE='ASSUMPTION_BASED_SCHEDULER_VISIBLE_PROXY',HISTORICAL_D1_SNAPSHOT_PROVENANCE='UNVERIFIED',
         ORIGINAL_SUBMISSION_VALUE_PROVENANCE='UNVERIFIED',OPERATIONAL_AVAILABILITY_ASSUMPTION='FROZEN',
         definition='Recorded public Kestrel request fields proxy currently effective PENDING request state at D-1 18:00 fixed AEST. This is an assumption, not verified snapshot equality or request immutability.',
         POST_ISSUE_REQUEST_MODIFICATION_HISTORY='UNOBSERVED',POST_ISSUE_REQUEST_MODIFICATION_MODEL='OUT_OF_SCOPE',
         observed_modification_frequency=None,paper_label='ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL')
    write('REQUEST_STATE_PROXY_ASSUMPTION',assumption)
    (OUT/'V40S4_ASSUMPTION_BOUNDARY.md').write_text('# D1_SCHEDULER_REQUEST_STATE_PROXY_V1\n\nRecorded request fields are assumption-based scheduler-visible proxies. '
       'Historical D-1 snapshot and original submission provenance remain UNVERIFIED. No claim of immutable requests, observed modification frequency0, or causal snapshot ground truth. '
       'S3 strict provenance result remains valid. Start/end establish normative membership and labels only. Requested walltime is predictive metadata, never a guaranteed runtime bound.\n',encoding='utf-8')
    assert sha(SOURCE.read_bytes())==SOURCE_SHA,'SOURCE_MISMATCH_STOP'
    f=pd.read_parquet(SOURCE,columns=['job_id','submit_time','start_time','end_time','runtime_seconds',*FEATURES])
    for c in ['submit_time','start_time','end_time']:
        f[c]=pd.to_datetime(f[c],utc=True)
        assert f[c].notna().all() and f[c].lt(pd.Timestamp('2025-04-24T00:00Z')).all()
    assert len(f)==73504 and not f.job_id.duplicated().any()
    np.testing.assert_array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    assert f.runtime_seconds.eq(0).sum()==1212 and f.runtime_seconds.gt(0).sum()==72292
    parent=pd.read_parquet(S3OUT/'V40S3_PENDING_ISSUE_PANEL.parquet')
    assert sha((S3OUT/'V40S3_PENDING_ISSUE_PANEL.parquet').read_bytes())==get('POPULATION_AUDIT',True)['panel_SHA256']
    # Independent membership/split rebuild, preserving every job-issue identity.
    parts=[]
    for role,(lo,hi) in BOUNDS.items():
        for issue in pd.date_range(pd.Timestamp(lo),pd.Timestamp(hi),freq='D',inclusive='left'):
            m=f.runtime_seconds.gt(0)&f.submit_time.le(issue)&(f.start_time.isna()|f.start_time.gt(issue))&f.end_time.gt(issue)&f.end_time.lt(pd.Timestamp(hi))
            d=f[m].copy();d['issue_time']=issue;d['role']=role;d['job_issue_uid']=d.job_id.astype(str)+'@'+issue.isoformat();d['issue_day']=issue.strftime('%Y-%m-%d');parts.append(d)
    rebuilt=pd.concat(parts,ignore_index=True)
    assert len(rebuilt)==10883 and rebuilt.job_id.nunique()==7603
    fields=['job_id','submit_time','start_time','end_time','runtime_seconds','issue_time','role','issue_day',*CLOCK,'requested_seconds','num_gpus_req']
    pd.testing.assert_frame_equal(rebuilt.set_index('job_issue_uid')[fields].sort_index(),parent.set_index('job_issue_uid')[fields].sort_index())
    # Preserve S3 row order and frozen reference seconds exactly.
    extra=[c for c in FEATURES if c not in parent.columns]
    p=parent.merge(f[['job_id',*extra]],on='job_id',how='left',validate='many_to_one')
    assert p.job_issue_uid.tolist()==parent.job_issue_uid.tolist()
    for c in FEATURES:
        pd.testing.assert_series_equal(p.set_index('job_issue_uid')[c].sort_index(),rebuilt.set_index('job_issue_uid')[c].sort_index())
    p.to_parquet(OUT/'V40S4_PENDING_ISSUE_PANEL.parquet',index=False)
    counts={r:dict(N=len(d),unique_jobs=int(d.job_id.nunique()),ID_SHA256=ids(d),max_label_end=d.end_time.max().isoformat()) for r,d in p.groupby('role')}
    assert {r:v['N'] for r,v in counts.items()}=={'TRAIN':1190,'DEVELOPMENT':4346,'CALIBRATION':2634,'EXPOSED_EVALUATION':2713}
    write('POPULATION_AUDIT',dict(status='PASS',original_N=73504,positive_N=72292,zero_N=1212,negative_N=0,duplicates=0,missing_start_end=0,job_issue_N=len(p),unique_jobs=int(p.job_id.nunique()),
          source=str(SOURCE),source_SHA256=SOURCE_SHA,parent_panel_SHA256=sha((S3OUT/'V40S3_PENDING_ISSUE_PANEL.parquet').read_bytes()),panel_SHA256=sha((OUT/'V40S4_PENDING_ISSUE_PANEL.parquet').read_bytes()),
          exact_independent_S3_rebuild=True,blocks=counts,source_limitation='Previously exposed positive terminal-service complete cases, not full cluster backlog; unresolved censoring and raw rowgroup exclusion bias unchanged.'))
    write('RUNTIME_LABEL_CONTRACT',dict(target='end-start seconds exactly',original_N=73504,positive_N=72292,zero_N=1212,zero_rule='Retained original identity audit, excluded uniformly; no epsilon imputation',
          state_reconstruction='Normative PENDING submit<=issue, start missing or>issue, end>issue; RUNNING submit<=issue,start<=issue,end>issue',
          start_end_predictor_use=False,terminal_success_status='UNAVAILABLE; not COMPLETED-only',current_membership_authority='UNCHANGED_NORMATIVE_S3'))
    write('TEMPORAL_SPLIT_CONTRACT',dict(parent_contract=get('TEMPORAL_SPLIT_CONTRACT',True),exact_blocks=BOUNDS,block_counts=counts,
          axis='issue_time; strict end<stage cutoff; no random split',S3_contract_SHA256=sha((S3OUT/'V40S3_TEMPORAL_SPLIT_CONTRACT.json').read_bytes())))
    mapping=dict(wallclock_req='requested_seconds',gpus_requested='num_gpus_req',nodes_req='num_nodes_req',processors_req='num_cores_req',memory_req='requested_memory_mib',partition='partition',qos='qos',submit_hour='submit_hour',weekday='submit_dow')
    map_path=SOURCE.parents[2]/'v40k_central_runtime/V40K_FEATURE_TARGET_EQUIVALENCE.json'
    # SOURCE.parents[2] is the artifacts directory.
    eq=json.loads(map_path.read_text(encoding='utf-8'));assert eq['status']=='PASS'
    write('PROXY_FEATURE_INVENTORY',dict(status='PASS',mapping=mapping,source_fields_present={c:c in f for c in FEATURES},
          units=dict(requested_seconds='seconds',num_gpus_req='requested GPU count',num_nodes_req='requested node count',num_cores_req='requested processor/core count',requested_memory_mib='MiB, pinned Slurm normalization'),
          prior_exact_mapping_evidence=dict(path=str(map_path),SHA256=sha(map_path.read_bytes()),evidence=eq),
          optional_hardware='NOT_AVAILABLE as separate explicit request hardware field; derived hardware excluded, partition remains allowed request queue field',
          excluded=['user','account','job_name','application identity','hardware derivative','standby derivative','support counts'],primary_identifier_use='NO'))
    train=p[p.role=='TRAIN']
    pre={t:Preprocess(t).fit(train) for t in ('P','PW')}
    write('PROXY_FEATURE_PREPROCESSING_CONTRACT',dict(rule='Valid continuous: log1p after TRAIN median imputation plus missing indicator; categorical train-only one-hot vocabulary with UNKNOWN; clock raw hour/weekday; no target encoding',
          invalid_rule='nonfinite invalid; wall/GPU/nodes/cores<=0 invalid; memory<0 invalid; fractional GPU/node/core counts invalid; memory0 retained',
          missing_category_rule='NA or trimmed empty/nan/none/unknown -> __UNKNOWN__; unseen -> __UNKNOWN__',
          logistic='Same transformed columns as trees; no post-outcome scaling search; max_iter1000',descriptors={t:v.descriptor() for t,v in pre.items()},fit_role='TRAIN_ONLY'))
    missing=[]
    for scope,df in [('SOURCE_ALL',f),('PENDING_PANEL',p),*[(r,p[p.role==r]) for r in BOUNDS]]:
        for c in FEATURES:
            raw=df[c];v=numeric_valid(raw,c) if c in NUM else raw
            record=dict(scope=scope,feature=c,N=len(df),nonmissing_fraction=float(raw.notna().mean()),unique_values=int(raw.nunique(dropna=True)),missing_N=int(raw.isna().sum()))
            if c in NUM:record.update(invalid_N=int((raw.notna()&v.isna()).sum()),zero_N=int(pd.to_numeric(raw,errors='coerce').eq(0).sum()),impossible_N=int((raw.notna()&v.isna()).sum()))
            elif c in CAT:record.update(invalid_N=0,zero_N=int(raw.astype(str).eq('0').sum()),impossible_N=None,unseen_N=int((~clean_category(raw).isin(pre['P'].vocab[c])).sum()),unseen_values=sorted(set(clean_category(raw))-set(pre['P'].vocab[c])))
            else:record.update(invalid_N=0,zero_N=int(raw.eq(0).sum()),impossible_N=0)
            missing.append(record)
    write('PROXY_FEATURE_MISSINGNESS_AUDIT',dict(rows=missing,metadata_only_by_exposed_split=True,runtime_outcomes_used_to_choose_features=False))
    write('PROXY_FEATURE_CONTRACT',dict(assumption_id=ASSUMPTION,tracks={'C':{'role':'STRICT_PROVENANCE_REFERENCE','features':CLOCK,'retrain':False},
          'P':{'role':'ASSUMPTION_BASED_OPERATIONAL_PROXY','features':FEATURES},'PW':{'role':'WALLTIME_DEPENDENCE_SENSITIVITY','features':selected_features('PW')}},
          requested_GPU_dual_role='Predictor in both P and P-W, independently frozen evaluation weight in all tracks; recorded request, not measured allocation',
          forbidden_predictors=['job_id','job_issue_uid','user','account','job_name','start_time','end_time','runtime_seconds','K0','reference_safe_sec','support counts'],
          walltime='Predictive covariate; new model quantiles never clipped to walltime',proxy_values_frozen_at_issue_by_assumption=True))
    # Descriptive ratio, all positive valid source rows and panel stages separately.
    relationship=[]
    for scope,df in [('SOURCE_POSITIVE',f[f.runtime_seconds>0]),('PENDING_PANEL',p),*[(r,p[p.role==r]) for r in BOUNDS]]:
        valid=df[df.runtime_seconds.gt(0)&numeric_valid(df.requested_seconds,'requested_seconds').notna()].copy()
        groups=[('OVERALL',valid)]
        bucket=pd.cut(valid.requested_seconds/3600,[0,4,6,8,12,24,48,np.inf],right=True).astype(str)
        groups += [('walltime_'+k,d) for k,d in valid.groupby(bucket,observed=True)]
        groups += [('GPU_'+str(k),d) for k,d in valid.groupby('num_gpus_req')]
        groups += [('partition='+str(k[0])+'|qos='+str(k[1]),d) for k,d in valid.groupby(['partition','qos'],dropna=False) if len(d)>=100]
        for key,d in groups:
            ratio=d.runtime_seconds/d.requested_seconds
            relationship.append(dict(scope=scope,group=key,N=len(d),median=float(ratio.median()),P90=float(ratio.quantile(.9)),P95=float(ratio.quantile(.95)),P99=float(ratio.quantile(.99)),actual_gt_request_N=int((ratio>1).sum()),actual_gt_request_fraction=float((ratio>1).mean())))
    write('REQUEST_RUNTIME_RELATIONSHIP',dict(interpretation='Descriptive ratio only; requested walltime is NOT a hard bound',rows=relationship))
    write('TRACK_C_REFERENCE',dict(role='STRICT_PROVENANCE_REFERENCE',classification=receipt['classification'],selected=None,retrained=False,
          features=CLOCK,S3_receipt=BASE,source_predictions='Immutable V40S3_PREDICTIONS_u*_{role}.parquet',source_results=['V40S3_DEV_CAL_RESULTS.json','V40S3_EXPOSED_RESULTS.json'],
          raw_S3_eta_rule='CAL recall/GPU recall90% only, with separate80% flag/ECE gates; do not relabel as S4 eta protocol',
          raw_S3_gate_results_preserved=True,comparison_rule='Matched same-u/body/classifier metrics; S3 R1 is S4 R2, S4 R1 is new threshold floor'))
    write('UNTOUCHED_HOLDOUT_AUDIT',dict(TRUE_CONFIRMATORY_AVAILABLE='NO',shadow='SEALED',shadow_rows_read=0,exposed_evaluation='Previously exposed; not independent confirmation'))
    write('MAY_FIREWALL',dict(canonical_timezone='fixed AEST UTC+10',local_cutoff='2025-05-01T00:00:00+10:00',UTC_cutoff='2025-04-30T14:00:00Z',stricter_source_boundary='2025-04-24T00:00:00Z',
          MAY_PATH_OR_CODE_DISCOVERY_READS='NONZERO_GIT_PATH_INVENTORY_ONLY; no May source-code payload investigation',MAY_METADATA_ONLY_READS='NONZERO_GIT_INDEX_BLOB_INVENTORY_ONLY',MAY_RUNTIME_OR_STATUS_ROW_READS=0,MAY_ACTUAL_OUTCOME_READS=0,
          MAY_FEATURE_FITTING_READS=0,MAY_TRAINING_READS=0,MAY_CALIBRATION_READS=0,MAY_THRESHOLD_SELECTION_READS=0,MAY_ETA_SELECTION_READS=0,MAY_MODEL_SELECTION_READS=0,MAY_PROXY_SENSITIVITY_READS=0,
          shadow='SEALED',shadow_rows_read=0,May_total_read_count_zero_claim=False,
          row_inputs=[dict(path=str(SOURCE),SHA256=SOURCE_SHA,scope='Already pre-Apr24 verified source'),dict(path=str(S3OUT/'V40S3_PENDING_ISSUE_PANEL.parquet'),SHA256=sha((S3OUT/'V40S3_PENDING_ISSUE_PANEL.parquet').read_bytes()),scope='Immutable parent panel')]))
    versions={n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','xgboost','lightgbm']}
    write('PREREGISTRATION',dict(timestamp=now(),new_fits_before_commit=0,new_predictions_before_commit=0,assumption=assumption,
          feature_contract=get('PROXY_FEATURE_CONTRACT'),preprocessing=get('PROXY_FEATURE_PREPROCESSING_CONTRACT'),population=get('POPULATION_AUDIT'),splits=BOUNDS,threshold_hours=U,
          tracks=['C','P','PW'],C_retrain=False,body_registry={'B0':'Immutable current recipe comparator only, no selection','B1':{'library':'LightGBM','quantiles':[.5,.9],'params':LGB},'B2':{'library':'XGBoost','objective':'reg:quantileerror','quantiles':[.5,.9],'params':XGB},'B3':'TRAIN body empirical linear quantiles'},
          classifier_registry={'C0':'TRAIN tail base rate','C1':{'library':'sklearn LogisticRegression','C':1,'solver':'lbfgs','max_iter':1000,'random_state':SEED},'C2':{'library':'LightGBM','objective':'binary','params':LGB},'C3':{'library':'XGBoost','objective':'binary:logistic','eval_metric':'logloss','params':XGB}},
          body_train='TRAIN rows T<=u; transformed with unsupervised full TRAIN map; no additional quantile calibration, as S3',
          output_rule='Sort raw Q50/Q90 pair, clip only numerical nonpositive to1s; never cap to walltime. Report raw crossings. ceil(seconds/900) once for scheduler metrics.',
          eta_rule='Per track/u/body/classifier CAL only; largest unique probability or endpoint satisfying recall>=.90, requested-GPU recall>=.90, g*positive body-Q90 miss capture>=.80, selectivity. CAL N>=100 and tailN>=100; no qualifying eta =>NONE.',
          selectivity='flagged<=.60; if true tail prevalence>.60 use min(.80,prevalence+.20). CAL uses CAL prevalence; each evaluation metric applies its own prevalence rule without retuning eta.',
          body_gates={'overall_min':.9,'overall_max':.95,'GPU_min':.9,'major_day_min':.88,'major_day_GPU_min':.88,'support_N':100,'upper_warning':.975},
          tail_gates={'recall':.9,'GPU_recall':.9,'mass_capture':.8,'support_N':100,'tail_N':100,'ECE':'Diagnostic only; S4 specification does not carry S3 ECE<=.05 gate into eta or eligibility.'},
          ECE_definition='10 equal-width bins [0,.1)...[.9,1], N-weighted absolute bin observed-predicted difference',
          robust={'R0':'current recipe reference_safe_sec','R1':'max(reference_safe_sec,u_seconds)','R2':'recorded requested_seconds, not hard bound'},
          hybrid_gates={'overall_min':.9,'GPU_min':.9,'GPU_underprediction_ratio_strict_max':1.,'overreservation_ratio_max':3.,'major_day_N':100,'major_day_overall_min':.85,'major_day_GPU_min':.85,'major_day_overreservation_ratio_max':3.},
          zero_reference_rule='If reference mass or reserve0, candidate must also be0; no smoothing. Strict improvement still impossible for zero total reference miss.',
          selection='Require every gate on both DEV and CAL. Per track freeze best eligible by pooled overreservation, pooled oracle body Q50 MAE, B3/B1/B2 simplicity, C0/C1/C2/C3, larger u, R0/R1/R2. Freeze overall best across per-track winners by same criteria (PW beforeP only final tie). No refit/reselection after freeze.',
          exposed='After committed selection, evaluate frozen candidates as diagnostics and frozen per-track/global winners as promotion tests; no winner rescue after global selected failure.',
          importance='All tree models: aggregate gain by original feature; DEVELOPMENT-only3-repeat raw-feature permutation, seed4003+i; body oracle pinball at native alpha, classifier Brier; no redesign.',
          walltime_dependence='Matched P-PW comparisons per u/body/classifier/role; separately assess frozen per-track winners. P-only success strong walltime dependence; both or PW-only success beyond-walltime information; neither insufficient.',
          perturbation='Post-selection only S0,wallclock*.9,wallclock*1.1; no refit or eta change. Evaluate frozen global winner; if NONE use preregistered diagnostic anchor P/u4/B1/C2/R1 (and PW identical anchor) without claiming selection. Perturb predictor walltime and R2 walltime fallback together if selected policyR2; current RSP and actual labels fixed. Not an observed modification model.',
          bootstrap='Only if frozen global winner passes all exposed gates:5000 paired issue-day block bootstrap of GPU underprediction improvement vs current reference; seed4003; otherwise NOT_EXECUTED_SAFETY_FAIL',
          classification='Binding failure first; no DEV+CAL body-safe pair =>PROXY_BODY_RUNTIME_INSUFFICIENT; body exists but no tail/selectivity-safe pair =>PROXY_TAIL_DETECTION_FAIL; otherwise no eligible or exposed failed global method =>PROXY_HYBRID_RUNTIME_SAFETY_FAIL; frozen global all-pass =>REQUEST_STATE_PROXY_RUNTIME_PREVALIDATED.',
          compute=dict(device='CPU',threads=1,seed=SEED,versions=versions,independent_same_seed_repeat='All new fitted model objects, compare predictions on TRAIN+DEV+CAL before selection; never choose better repeat',extra_package_path='C:/codex_mobileess_workspace/v40s3_runtime_packages'),
          optimizer_integration='NO',holds=HOLDS,May_scientific_reads=0,shadow='SEALED'))
    print('S4_PREREG_READY',counts,'features',FEATURES,flush=True)


if __name__=='__main__':main()
