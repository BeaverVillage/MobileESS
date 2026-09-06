"""Audited read-only V40S3 Phase A and fail-closed preregistration.

Execute with python -B -m dayahead.v40s3.audit. No old revision imports,
training, prediction, optimizer, raw archive or shadow reads are performed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import importlib.metadata
import numpy as np
import pandas as pd
from .contracts import Q, U_HOURS, FIELDS, metrics, baseline_safe, body_tail

ROOT = Path(__file__).resolve().parents[2]
REF = Path('C:/codex_mobileess_workspace/MobileESS_v40s2_survival_occupancy_ml')
OUT = ROOT/'dayahead/artifacts/v40s3_body_tail_runtime_risk'
BASE = 'a2a21c904535125c66668a294f91d73a66f5d4a7'
S2 = '00dadb1fcc5cab91c7b13e653bd629f68d538d61'
REQUEST = Path('C:/Users/kjw39/.codex/attachments/3ac2e98a-1d28-4207-9c06-426ed6fa2761/pasted-text.txt')
CUTOFF = pd.Timestamp('2025-04-30T14:00:00Z')
SHADOW = pd.Timestamp('2025-04-24T00:00:00Z')
CLASS = 'V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT'
READS = []
HOLDS = dict(production_q_seconds=Q, PF=.95, Q_control='NO', electrical_regeneration='HOLD',
             B0_B1_B2_B3='NO', FULL_MAY='NO', optimizer_integration='NO',
             RUNNING_migration_change='NO', A1_migration_change='NO', terminal_contract_change='NO')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, cwd=ROOT, binary=False):
    x = subprocess.check_output(['git', *args], cwd=cwd)
    return x if binary else x.decode('utf-8').strip()


def write(name, value):
    (OUT/f'V40S3_{name}.json').write_text(json.dumps(value, indent=2, ensure_ascii=False,
                   allow_nan=False, default=lambda x: x.item() if hasattr(x, 'item') else str(x))+'\n', encoding='utf-8')


def read(path, purpose):
    path = Path(path)
    # Explicit allowed roots, with all row payloads individually admitted below.
    if not any(path.is_relative_to(p) for p in (ROOT, REF)):
        raise ValueError('UNREGISTERED_SOURCE')
    data = path.read_bytes()
    READS.append(dict(path=str(path), SHA256=sha(data), purpose=purpose))
    return data


def jread(path, purpose='existing pre-May evidence'):
    return json.loads(read(path, purpose))


def frame(path, columns):
    # Only these three already authority-audited, pre-Apr24 row files are allowed.
    allowed = {'PREPARED_ROWS.parquet', 'V40S2_LABEL_AVAILABILITY_LEDGER.parquet',
               'V40I_PREMAY_VALIDATION_RECOMPUTED_ROWS.parquet'}
    if Path(path).name not in allowed:
        raise ValueError('ROW_SOURCE_NOT_ALLOWLISTED')
    read(path, 'pre-Apr24 row payload; timestamp validation follows')
    f = pd.read_parquet(path, columns=columns)
    for c in ('submit_time', 'start_time', 'end_time'):
        f[c] = pd.to_datetime(f[c], utc=True)
        if f[c].isna().any() or not (f[c] < SHADOW).all() or not (f[c] < CUTOFF).all():
            raise ValueError('ROW_TIMESTAMP_FIREWALL')
    return f


def identity(ids):
    return sha(('\n'.join(sorted(map(str, ids)))+'\n').encode())


def execute():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'.gitattributes').write_text('* -text whitespace=cr-at-eol\n')
    (OUT/'USER_REQUEST.txt').write_bytes(REQUEST.read_bytes())
    now = datetime.now(timezone.utc).isoformat()
    assert git('rev-parse', 'HEAD') == BASE
    assert git('branch', '--show-current') == 'codex/v40s3-body-tail-runtime-risk'
    gh = 'C:/Program Files/GitHub CLI/gh.exe'
    live = json.loads(subprocess.check_output([gh, 'pr', 'view', '27', '--repo', 'BeaverVillage/MobileESS',
        '--json', 'number,url,state,headRefOid,headRefName,baseRefOid,baseRefName,updatedAt'], cwd=ROOT))
    assert live['headRefOid'] == BASE
    tree = git('ls-tree', '-r', BASE).splitlines()
    current = [x for x in tree if '\tdayahead/artifacts/v40j_runtime_redesign/' in x]
    ancestry = {x: subprocess.run(['git', 'merge-base', '--is-ancestor', x, BASE], cwd=ROOT).returncode == 0
                for x in ['8ff3dc608d91cbd76c750713167d675297365f0d']}
    write('CURRENT_PR27_HEAD_AUDIT', dict(timestamp=now, live=live, resolved_HEAD=BASE,
          historical_SHA_is_ancestor=ancestry, V40J_artifact_tree=current,
          complete_base_tree_SHA256=sha(('\n'.join(tree)+'\n').encode()),
          V40S2_merge_base=git('merge-base', BASE, S2), V40S2_merged=False))
    write('START_STATE', dict(timestamp=now, branch=git('branch','--show-current'), worktree=str(ROOT),
          starting_HEAD=BASE, live_resolved_before_scientific_work=True, separate_worktree=True,
          setup_note='New --no-checkout worktree initially had empty index. A status command exposed staged-D path metadata; git read-tree -mu HEAD populated the index. Clean tracked status verified before edits. No deletion or production mutation.',
          permitted_prefixes=['dayahead/v40s3/', 'dayahead/artifacts/v40s3_body_tail_runtime_risk/']))
    receipt_path=REF/'dayahead/artifacts/v40s2_survival_occupancy_ml/V40S2_FINAL_COMMIT_RECEIPT.json'
    receipt=jread(receipt_path, 'read-only S2 commit receipt verification')
    verified={}
    for p, expected in receipt['committed_file_SHA256'].items():
        actual=sha(read(REF/p, 'S2 reference hash verification only'))
        committed=sha(git('show', f'{S2}:{p}', cwd=REF, binary=True))
        assert actual == expected == committed, p
        verified[p]=actual
    assert read(receipt_path, 'S2 receipt byte verification') == git('show', f'{S2}:{receipt_path.relative_to(REF).as_posix()}', cwd=REF, binary=True)
    write('V40S2_REFERENCE_FREEZE', dict(status='PASS', scientific_commit=receipt['scientific_commit'],
          full_receipt_commit=git('rev-parse','00dadb1',cwd=REF), file_count=len(verified),
          verified_SHA256=verified, merged=False, reference_modified=False, classification=receipt['classification']))
    evidence={}
    for revision, directory in [('K','v40k_central_runtime'),('L','v40l_conditional_tail'),
          ('N','v40n_shift_aware_tail'),('Q','v40q_regime_conditioned_tail'),('S2','v40s2_survival_occupancy_ml')]:
        path=REF/'dayahead/artifacts'/directory/f'V40{revision}_FINAL_REVIEW.md'
        data=read(path, 'prior pre-May scientific review; no new evaluation')
        evidence[revision]=dict(path=str(path), SHA256=sha(data))
    authority_root=REF/'dayahead/artifacts/v40s_direct_runtime_q90'
    old_state=jread(authority_root/'V40S_HISTORICAL_JOB_STATE_AUTHORITY_AUDIT.json')
    old_features=jread(authority_root/'V40S_CAUSAL_REDUCED_FEATURE_SET_AUDIT.json')
    old_decision=jread(authority_root/'V40S_AUTHORITY_RECOVERY_DECISION.json')
    evidence['S']=dict(prior_state_audit=old_state, prior_features=old_features, prior_decision=old_decision)
    baseline=jread(ROOT/'dayahead/artifacts/v40j_runtime_redesign/V40J_CURRENT_RUNTIME_BASELINE.json')
    evidence['J']=baseline
    evidence['I']=jread(ROOT/'dayahead/artifacts/v40i_authority_electrical_closure/pending_runtime_forensic/V40I_PREMAY_PENDING_RUNTIME_VALIDATION.json')
    code_paths=['dayahead/v37/aidc_materializer.py','dayahead/ml/safe_flex/state_reconstruction.py',
                'dayahead/v40a/initial.py','dayahead/v39e/initial_state.py','dayahead/v40a/coordination.py',
                'dayahead/v40a/invariants.py','dayahead/v40g/domain.py']
    code={p:git('show',f'{BASE}:{p}',binary=True) for p in code_paths}
    for p, b in code.items():
        READS.append(dict(path=f'git:{BASE}:{p}', SHA256=sha(b), purpose='current production code authority; no execution'))
    mat=code[code_paths[0]].decode()
    assert 'alive = end.isna() | end.gt(cutoff)' in mat
    assert 'safe_total = min(requested, max(point + Q_SELECTED_SECONDS, float(SLOT_SECONDS)))' in mat
    assert 'not an exact historical scheduler snapshot' in code[code_paths[1]].decode()
    scope=dict(PENDING_RUNTIME_REDESIGN='YES', RUNNING_RUNTIME_REDESIGN='NO', RUNNING_MIGRATION_CHANGE='NO',
               A1_RUNNING_CHANGE='NO', PRODUCTION_INTEGRATION='NO', RUNNING_redesign_count=0,
               architecture='D-1 18:00 fixed AEST; one-shot; 900s x 96; A0 > M1_ROUTE_PQ > A1_FEEDBACK > MF_FIXED_ROUTE_PQ > JOINT_FREEZE > FRESH > optional fixed-discrete P/Q restoration',
               extra_coordination_rounds=0, event_trigger_added=0, local_repair_added=0, rolling_MPC_added=0,
               new_fit_count=0, new_prediction_count=0, optimizer_calls=0, Gurobi_calls=0, Fresh_OpenDSS_calls=0,
               holds=HOLDS)
    write('SCOPE_CONTRACT',scope)
    feature_rows=[]
    for feature in ['submit_hour','weekday','requested_seconds','num_gpus_req','num_nodes_req','num_cores_req',
                    'requested_memory_mib','partition','qos','hardware','standby','account','user',
                    'exact_count','structural_count','s_wall','d_wall','nearest_ratio']:
        clock=feature in ('submit_hour','weekday')
        feature_rows.append(dict(feature=feature, source='recorded submit_time UTC' if clock else 'retrospective final accounting request or derivative',
          available_at='recorded submission episode' if clock else 'NOT_PROVEN',
          historical_provenance='V40S feature census and V40S2 exact clock reconstruction' if clock else 'request version / edit ledger absent',
          original_submit_time_authority='episode timestamp only; first-submit/attempt linkage unverified' if clock else 'NOT_PROVEN',
          current_D1_authority='clock derivable if job independently observed PENDING; membership unproven' if clock else 'current code consumes scheduler-visible representation; archived at-time value unproven',
          admission_decision='CLOCK_ONLY_CONDITIONAL; NO_PENDINGS_AUTHORIZED' if clock else 'REJECTED_CAUSAL_MODEL',
          evaluation_use='historical requested GPU weights and subgroups only; not measured allocations'))
    write('FEATURE_AUTHORITY_AUDIT', dict(status='FAIL', features=feature_rows,
          current_code_SHA256={p:sha(b) for p,b in code.items()},
          historical_PENDING_count=None, original_request_ledger='NOT_RECOVERED_IN_AUDITED_SOURCES',
          independent_D1_PENDING_snapshot='NOT_RECOVERED_IN_AUDITED_SOURCES',
          causal_training_population='UNAVAILABLE',
          finding='Current snapshot_at_issue derives alive and PENDING from final start/end; dropping timestamps afterwards does not establish historical capture. Prior scoped source census remains applicable; no fresh raw archive recovery program run.',
          inference_limit='No claim that no authority can exist anywhere. Clock-only is not itself declared noncausal; missing PENDING selection authority independently blocks this task.'))
    write('CAUSAL_FEATURE_CONTRACT', dict(status='FAIL', conditionally_causal_features=['submit_hour','weekday'],
          admitted_model_features=[], admitted_PENDING_rows=0, observed_PENDING_count=None,
          forbidden=['future start/end','runtime label','final status','unproven original requests','unproven support derivatives'],
          training_and_support_rule='end_time strictly before historical fit or prediction/support time; no V40S3 fit/support calculation executed',
          proxy_track=False, reason='Independent D-1 PENDING membership and required resource feature provenance unavailable'))
    source=REF/'dayahead/artifacts/v40q_regime_conditioned_tail/clean_execution_01/PREPARED_ROWS.parquet'
    assert sha(read(source,'S2 cohort source hash precheck')) == 'fed0270c4e90362bc97b3583d92bfc6e00d6083297ee502b098e08896e086df9'
    cols=['job_id','submit_time','start_time','end_time','runtime_seconds','num_gpus_req','requested_seconds','retrospective_final_status','submit_hour','submit_dow']
    f=frame(source, cols)
    ledger=frame(REF/'dayahead/artifacts/v40s2_survival_occupancy_ml/V40S2_LABEL_AVAILABILITY_LEDGER.parquet',
                 ['job_id','submit_time','start_time','end_time','runtime_seconds','model_eligible'])
    assert len(f)==len(ledger)==73504 and not f.job_id.duplicated().any()
    a=f.set_index('job_id').sort_index();b=ledger.set_index('job_id').sort_index()
    pd.testing.assert_frame_equal(a[['submit_time','start_time','end_time','runtime_seconds']],b[['submit_time','start_time','end_time','runtime_seconds']])
    assert np.array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    assert np.array_equal(a.runtime_seconds.gt(0), b.model_eligible)
    assert np.array_equal(f.submit_hour, f.submit_time.dt.hour)
    assert np.array_equal(f.submit_dow, f.submit_time.dt.dayofweek)
    pos=f[f.runtime_seconds>0].copy()
    assert len(pos)==72292 and int(f.runtime_seconds.eq(0).sum())==1212
    pop=dict(original_N=len(f), positive_service_N=len(pos), zero_N=int(f.runtime_seconds.eq(0).sum()),
             negative_N=int(f.runtime_seconds.lt(0).sum()), missing_timestamp_N=0, duplicate_job_id_N=0,
             exact_end_minus_start=True, exact_S2_identity=True, all_ID_SHA256=identity(f.job_id),
             positive_ID_SHA256=identity(pos.job_id), terminal_status_counts=f.retrospective_final_status.value_counts(dropna=False).to_dict(),
             PENDING_N=None, PENDING_N_reason='Historical independently observed D1 membership unavailable; 0 admitted is not 0 pending jobs.',
             original_population='pre-Apr24 terminal-event complete cases; not successful COMPLETED-only and not PENDING-at-issue',
             max_accepted_timestamp=max(f[c].max() for c in ['submit_time','start_time','end_time']).isoformat(),
             current_runtime_prediction_identity='S2 K0/T7 NOT used as current RSP comparator')
    write('POPULATION_AUDIT',pop)
    write('RUNTIME_LABEL_CONTRACT',dict(target='T=end_time-start_time in seconds', zero_rule='retain in audit; exclude consistently from positive-service diagnostics; no epsilon imputation',
             status_rule='service terminal event, not guaranteed successful COMPLETED', S2_identity=pop,
             censoring_authority='INSUFFICIENT; do not fabricate right-censored rows',
             truncation='Source requires terminal events; incomplete long jobs may be missing. No all-submitted-job generalization.'))
    # Phase A uses only March TRAIN/development. April identity was checked above,
    # but no April threshold metric is computed. These retrospective rows are NOT
    # promoted to a causal PENDING population.
    train=pos[(pos.submit_time>=pd.Timestamp('2025-03-14T00:00Z')) &
              (pos.submit_time<pd.Timestamp('2025-03-22T00:00Z')) &
              (pos.end_time<pd.Timestamp('2025-03-22T00:00Z'))]
    ipath=ROOT/'dayahead/artifacts/v40i_authority_electrical_closure/pending_runtime_forensic/V40I_PREMAY_VALIDATION_RECOMPUTED_ROWS.parquet'
    old=frame(ipath,['job_id','submit_time','start_time','end_time','runtime_seconds','actual_runtime_seconds',
                    'point_runtime_seconds','safe_runtime_seconds','effective_runtime_seconds','requested_seconds','num_gpus_req','split_time'])
    assert len(old)==87824 and not old.job_id.duplicated().any()
    assert np.array_equal(old.runtime_seconds,(old.end_time-old.start_time).dt.total_seconds())
    np.testing.assert_array_equal(old.safe_runtime_seconds,baseline_safe(old.point_runtime_seconds,old.requested_seconds))
    np.testing.assert_array_equal(old.effective_runtime_seconds,np.ceil(old.safe_runtime_seconds/900).clip(1)*900)
    split=pd.to_datetime(old.split_time,utc=True)
    assert (split<SHADOW).all()
    dev=old[(old.runtime_seconds>0)&old.num_gpus_req.gt(0)&np.isfinite(old.num_gpus_req)&
            old.submit_time.ge(pd.Timestamp('2025-03-22T00:00Z'))&old.submit_time.lt(pd.Timestamp('2025-04-01T00:00Z'))&
            old.end_time.lt(pd.Timestamp('2025-04-01T00:00Z'))].copy()
    assert not set(train.job_id)&set(dev.job_id)
    dev['day']=dev.submit_time.dt.strftime('%Y-%m-%d')
    splits=dict(timezone='UTC blocked half-open submission intervals',
       TRAIN=dict(interval=['2025-03-14T00:00Z','2025-03-22T00:00Z'], end_known_before='2025-03-22T00:00Z', N=len(train), ID_SHA256=identity(train.job_id), role='reference TRAIN percentile only; no fit'),
       DEVELOPMENT=dict(interval=['2025-03-22T00:00Z','2025-04-01T00:00Z'], end_known_before='2025-04-01T00:00Z', N=len(dev), ID_SHA256=identity(dev.job_id), actual_min_submit=dev.submit_time.min().isoformat(), actual_max_submit=dev.submit_time.max().isoformat(), role='existing March rolling reference predictions, positive GPU rows only'),
       CALIBRATION=dict(interval=['2025-04-01T00:00Z','2025-04-08T00:00Z'], execution='BLOCKED; no eta/q fit'),
       EXPOSED_EVALUATION=dict(interval=['2025-04-08T00:00Z','2025-04-24T00:00Z'], execution='BLOCKED; identity audit only; no candidate scoring'),
       SHADOW=dict(interval=['2025-04-24T00:00Z','2025-05-01T00:00Z'], status='SEALED'),
       strict_timestamp_cutoff='2025-05-01T00:00:00+10:00 fixed AEST = 2025-04-30T14:00:00Z',
       no_random_split=True, baseline_q_caveat='Existing q used March24-31 calibration outcomes; reused only as frozen CURRENT formula descriptive comparator. Not causal out-of-sample Q90 calibration evidence.',
       baseline_state_caveat='Archived rolling predictions share current recipe and formula, but are not exact frozen Apr01 final model state predictions. No new predictions/refit attempted.')
    write('TEMPORAL_SPLIT_CONTRACT',splits)
    write('UNTOUCHED_HOLDOUT_AUDIT',dict(TRUE_CONFIRMATORY_AVAILABLE='NO', shadow='SEALED', shadow_rows_read=0,
          April_exposed='K/L/N/Q/S/S2 prior exposure; cannot rename as untouched', maximum_positive_claim='PREVALIDATED'))
    records=[]; body_metrics=[]
    T=dev.runtime_seconds.to_numpy(); P=dev.safe_runtime_seconds.to_numpy(); G=dev.num_gpus_req.to_numpy()
    E=np.maximum(T-P,0); M=G*E
    totals=metrics(T,P,G)
    for h in U_HOURS:
        body, tail=body_tail(T,h*3600)
        m=metrics(T[body],P[body],G[body])
        rec=dict(u_hours=h,u_sec=h*3600,TRAIN_N=len(train),TRAIN_percentile=float(train.runtime_seconds.le(h*3600).mean()*100),
                 DEVELOPMENT_N=len(dev), tail_N=int(tail.sum()), body_N=int(body.sum()), tail_prevalence=float(tail.mean()),
                 tail_requested_GPU_fraction=float(G[tail].sum()/G.sum()), tail_runtime_hours_fraction=float(T[tail].sum()/T.sum()),
                 tail_positive_error_mass_fraction=float(E[tail].sum()/E.sum()),
                 tail_GPU_positive_error_mass_fraction=float(M[tail].sum()/M.sum()),
                 body_reference_safe_coverage=m['coverage'], body_reference_GPU_coverage=m['GPU_coverage'],
                 body_reference_safe_MAE_sec=m['MAE_sec'],body_reference_safe_WAPE=m['WAPE'],
                 body_reference_underprediction_rate=m['underprediction_rate'],body_GPU_underprediction_sec=m['GPU_underprediction_sec'],
                 body_point_MAE_sec=float(np.abs(T[body]-dev.point_runtime_seconds.to_numpy()[body]).mean()),
                 body_point_WAPE=float(np.abs(T[body]-dev.point_runtime_seconds.to_numpy()[body]).sum()/T[body].sum()))
        for pct in (1,5,10):
            n=int(np.ceil(len(T)*pct/100))
            for label,mass in [('positive',E),('GPU_positive',M)]:
                ix=np.argsort(-mass,kind='stable')[:n]
                rec[f'worst_{pct}pct_{label}_mass_fraction']=float(mass[ix].sum()/mass.sum())
                rec[f'tail_share_within_worst_{pct}pct_{label}_mass']=float(mass[ix][tail[ix]].sum()/mass[ix].sum())
        records.append(rec)
        for group,mask in [('OVERALL',body),*[(d,body & dev.day.eq(d).to_numpy()) for d in sorted(dev.day.unique())],
                           ('GPU_1',body&(G==1)),('GPU_2_4',body&(G>=2)&(G<=4)),('GPU_5_PLUS',body&(G>=5))]:
            if mask.any():
                bm=metrics(T[mask],P[mask],G[mask])
                gate=.9 if group=='OVERALL' or group.startswith('GPU_') else .88
                bm.update(u_hours=h, subgroup=group, candidate='B0_ARCHIVED_ROLLING_REFERENCE',
                          gate_threshold=gate, coverage_gate='INSUFFICIENT_SUPPORT' if bm['N']<100 else 'PASS' if bm['coverage']>=gate else 'FAIL',
                          GPU_coverage_gate='INSUFFICIENT_SUPPORT' if bm['N']<100 else 'PASS' if bm['GPU_coverage']>=gate else 'FAIL',
                          upper_warning=bm['coverage']>.975, interpretation='ORACLE_MEMBERSHIP_RETROSPECTIVE_DIAGNOSTIC_ONLY')
                body_metrics.append(bm)
    ranges=[]
    for lo,hi in [(0,4),(4,6),(6,8),(8,12),(12,24),(24,float('inf'))]:
        m=(T>lo*3600)&(T<=hi*3600)
        if m.any():
            ranges.append(dict(range_hours=f'({lo},{hi}]', N=int(m.sum()),GPU_underprediction_sec=float(M[m].sum()),
                          GPU_mass_fraction=float(M[m].sum()/M.sum()),positive_mass_fraction=float(E[m].sum()/E.sum()),
                          residual_SD_sec=float(np.std(T[m]-P[m])),residual_variance_sec2=float(np.var(T[m]-P[m]))))
    pd.DataFrame(records).to_csv(OUT/'V40S3_THRESHOLD_FORENSIC.csv',index=False)
    pd.DataFrame(body_metrics).to_csv(OUT/'V40S3_BODY_METRICS.csv',index=False)
    write('THRESHOLD_FORENSIC',dict(status='READ_ONLY_DESCRIPTIVE', population=splits['DEVELOPMENT'],
          baseline_caveats=[splits['baseline_q_caveat'],splits['baseline_state_caveat']],
          actual_membership_is_oracle=True, thresholds=records, runtime_ranges=ranges,
          total_reference_metrics=totals, zero_runtime_rows_in_reference=int(old.runtime_seconds.eq(0).sum()),
          missing_GPU_rows_in_reference=int(old.num_gpus_req.isna().sum()), missing_GPU_imputed=False))
    write('BODY_PREDICTABILITY_REPORT',dict(status='NOT_ESTABLISHED_FOR_CAUSAL_PENDING',
          reason='Oracle body coverage on archived rolling complete-case development cannot establish causal D1 PENDING predictability. Authority gate fails first.',
          intrinsic_body_failure_claimed=False, thresholds=records, by_temporal_block_and_GPU_band=body_metrics,
          upper_control='coverage >97.5% is OVERCONSERVATIVE_BODY_WARNING, not calibrated Q90',
          body_vs_tail_membership='T<=u diagnostic only; no inference-time membership generated'))
    library={}
    for name in ['numpy','pandas','pyarrow','xgboost','lightgbm','scikit-learn','pytest']:
        try: library[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: library[name]='NOT_INSTALLED; no install required for authority stop'
    registry=dict(body={'B0':'current frozen RSP reference; archived rolling comparator only',
                       'B1':'causal LightGBM Q50/Q90', 'B2':'causal XGBoost Q50/Q90',
                       'B3':'unconditional empirical TRAIN body Q50/Q90; simple quantile analogue of existing S2 KM baseline'},
                  tail={'C0':'TRAIN base rate', 'C1':'logistic on authorized clock features',
                        'C2':'causal LightGBM', 'C3':'causal XGBoost'})
    prereg=dict(timestamp=datetime.now(timezone.utc).isoformat(), phase='AUTHORITY_STOP_BEFORE_FIT',
       phase_A_exposed_before_freeze=True, phase_A_authorized_by_user=True,
       new_fit_before_commit=0,new_prediction_before_commit=0,candidate_ranking_observed=False,
       classification_if_authority_fails=CLASS, authority_gate='FAIL',
       exact_population=pop, feature_contract='V40S3_CAUSAL_FEATURE_CONTRACT.json',
       threshold_hours=U_HOURS, model_registry=registry, model_execution='ALL NEW MODELS BLOCKED; this preregistration does not authorize later fitting',
       registry_hyperparameters='NOT_ACTIVATED_AUTHORITY_STOP; any later fit requires new revision with fully frozen hyperparameters and new authority',
       calibration='C0 no additional calibration reserved for new body candidates; no automatic old global q',
       eta_rule='CALIBRATION only: largest observed probability or endpoint eta meeting recall>=.90 and GPU recall>=.90; 95% sensitivity; N>=100 and tail N>=100. Equality flags tail.',
       robust_policies=dict(R0='current RSP duration only + flexibility_protected', R1='existing requested-walltime comparator only; NOT a hard bound'),
       metrics=['coverage','GPU coverage','MAE','WAPE','log-MAE','completion-slot error','positive residual mean/P95/max',
                'ROC-AUC','PR-AUC','Brier','ECE','recall','precision','specificity','FNR','GPU recall/FNR','danger mass capture','overreservation'],
       gates=dict(causal_authority='MANDATORY PASS',body_N_min=100,body_coverage_min=.9,body_GPU_coverage_min=.9,
                  temporal_body_coverage_min=.88,body_upper_warning=.975,tail_recall_min=.9,tail_GPU_recall_min=.9,
                  mass_capture_min=.8,ECE_max=.05,
                  hybrid='NOT_EXECUTABLE_AUTHORITY_STOP; no permissive numeric overreservation or near-all-flag threshold invented after outcomes'),
       splits=splits, selection_hierarchy=['causal authority','body safety','tail recall','GPU underprediction','overreservation','largest body region','simplicity'],
       selected_u=None,selected_eta=None,shadow='SEALED',May_scientific_reads=0,holds=HOLDS,
       compute=dict(libraries=library,device='CPU',threads=1,seed=4003,determinism='pure deterministic diagnostics; no model fit',training_seconds=0))
    write('PREREGISTRATION',prereg)
    summary=dict(classification=CLASS,prior_evidence=evidence,
       distinct_populations='K/L/N/Q/S2 cohorts, temporal splits and terminal filtering differ; no pooled historical metric',
       prior_findings=dict(K='No point winner; conditional COMPLETED standby bias remains; not central-normal everywhere',
        L='T7 aggregate coverage passed but mandatory strong-support standby N=4; 324 miss jobs, top 1/5/10% miss jobs explain 22.625/50.932/66.374% mass',
        N='A2 shifted standby coverage 32.948%; broad temporal failure, no winner',
        Q='Residual calibration did not repair A2 structural OOS / negative shift failures',
        S='No original request-version or independent historical state authority; clock alone survives',
        S2='Clock-only survival safety failed; proxy advantage is retrospective and not causal authority'),
       question_answers=dict(long_positive_error='See threshold fractions; positive error mass is distinct from long-job count',
        dangerous_runtime_ranges=ranges,body_region='Descriptive short-body reference safety exists where reported; calibration/reconstruction limits prevent deployable claim',
        variance_increase='Fixed-bin residual SD/variance reported; no data-selected changepoint or causal claim',
        dangerous_mass_above_u=records))
    write('EXISTING_RUNTIME_EVIDENCE_AUDIT',summary)
    (OUT/'V40S3_EXISTING_RUNTIME_EVIDENCE_AUDIT.md').write_text(
       '# V40S3 기존 증거 재사용\n\nCurrent PR baseline은 V40J/V35R3D-R1이다. T7/S2 survival을 current RSP로 대체하지 않았다. '
       'March rolling prediction과 현재 formula의 일치를 확인했지만 Apr01 final model-state 동일성은 주장하지 않는다. '
       '기존 q를 선택했던 calibration 표본 재사용이며 독립 Q90 검증이 아니다.\n\n'
       'K의 조건부 point bias, L의 N=4 support 부족, N/Q의 시간·구조별 실패, S의 historical feature/state authority 부족, '
       'S2의 causal-clock survival safety 실패를 그대로 보존했다. April 결과는 새 u/eta 선택에 사용하지 않았다.\n\n'
       '요청한 다섯 duration threshold별 위험 집중과 runtime 구간별 분산은 THRESHOLD_FORENSIC에 있다. '
       '긴 작업이라는 사실과 GPU 양의 과소예측 질량은 별도로 집계한다. body oracle은 실제 runtime을 사용한 진단이며 분류기가 아니다. '
       'D1 PENDING authority 부족으로 새 fit을 실행하지 않는다.\n',encoding='utf-8')
    write('READ_LEDGER',dict(entries=READS,manual_discovery_note='Initial repository path inventories/status metadata and targeted code reads occurred before this ledger. May-related paths/code literals were exposed; no May row payload was opened.'))
    print(json.dumps(dict(status='AUDIT_AND_PREREG_READY',classifiation=CLASS,train_N=len(train),dev_N=len(dev),
                         thresholds=records),default=str))


if __name__=='__main__':
    execute()
