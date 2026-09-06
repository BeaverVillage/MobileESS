"""Report frozen results and read-only terminal/reference diagnostics."""
import io
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from .audit import ROOT, OUT, REF, BASE, S2, HOLDS, sha, git, write
from .experiment import get, load_panel, U_HOURS, PREFIX
from .contracts import FIELDS, slots, metrics, hybrid


def prepare_reports():
    a=get('DEV_CAL_RESULTS');b=get('EXPOSED_RESULTS');sel=get('METHOD_SELECTION')
    assert sel['selected'] is None, 'This closeout is for the observed frozen NONE result'
    body=a['body_metrics']+b['body_metrics'];tail=a['tail_metrics']+b['tail_metrics'];comb=a['results']+b['results']
    pd.DataFrame(body).to_csv(OUT/'V40S3_BODY_METRICS.csv',index=False)
    pd.DataFrame(tail).to_csv(OUT/'V40S3_TAIL_CLASSIFICATION_METRICS.csv',index=False)
    gate_rows=[]
    for r in comb:
        z=r['replay'] or {}
        gate_rows.append(dict(u_hours=r['u_hours'],body=r['body'],classifier=r['classifier'],policy=r['policy'],role=r['role'],
          **{k+'_gate':v for k,v in r['gates'].items()},tail_N=r['tail']['tail_N'],tail_recall=r['tail']['recall'],GPU_tail_recall=r['tail']['GPU_recall'],
          ECE=r['tail']['ECE'],mass_capture=r['tail']['mass_capture'],flagged_fraction=r['tail']['flagged_fraction'],
          GPU_mass_ratio=z.get('GPU_mass_ratio'),overreservation_ratio=z.get('overreservation_ratio')))
    pd.DataFrame(gate_rows).to_csv(OUT/'V40S3_EXACT_GATE_TABLE.csv',index=False)
    for name,c in [('BASELINE','B0'),('LIGHTGBM','B1'),('XGBOOST','B2'),('EXTRA_BASELINE','B3')]:
        write('BODY_'+name+'_REPORT',dict(candidate=c,status='REFERENCE_ONLY' if c=='B0' else 'EVALUATED_NOT_SELECTED',
          prediction_features='existing frozen reference' if c=='B0' else ['submit_hour','weekday'] if c!='B3' else [],
          metrics=[r for r in body if r['candidate']==c],raw_crossings=a['crossings']+b['crossings'],
          body_filter='Oracle actual T<=u, not inference-time classification',winner=False,
          baseline_identity_caveat='B0 is frozen current recipe C0_F3 before April / K0 April; not identical to unserialized production Apr01 final state. Exact live-Apr01 ledger subset separately audited.'))
    for name,c in [('BASELINE','C0'),('LOGISTIC','C1'),('LIGHTGBM','C2'),('XGBOOST','C3')]:
        write('TAIL_'+name+'_REPORT',dict(candidate=c,status='EVALUATED_NOT_SELECTED',features=[] if c=='C0' else ['submit_hour','weekday'],
          metrics=[r for r in tail if r['classifier']==c],eta_source='CALIBRATION_ONLY',winner=False,
          support='u24 CAL tail N=43 <100: no eta; exposed u12 tail N=62 and u24 N=19 insufficient for mandatory recall gate'))
    for policy in ('R0','R1'):
        write('ROBUST_POLICY_'+policy+'_REPORT',dict(policy=policy,status='DIAGNOSTIC_ONLY_NOT_SELECTED',
          meaning='frozen current-recipe duration + flexibility protected' if policy=='R0' else 'existing requested-walltime scheduling comparator; not exact completion or guaranteed hard bound',
          results=[r for r in comb if r['policy']==policy],selected_result=None))
    write('HYBRID_RUNTIME_METRICS',dict(status='NO_SELECTED_HYBRID',selected=None,full_denominator=True,
       denominator_unit='PENDING job-issue rows; repeated daily decisions retained',candidate_results=comb,
       strict_current_production_comparison='UNAVAILABLE for full issue panel; current-recipe reference comparison only. One existing current ledger subset separately audited.',
       no_reselection=True))
    write('GPU_WEIGHTED_UNDERPREDICTION_REPORT',dict(definition='sum requested_GPU * max(actual runtime - duration,0)',
       actual_allocated_GPU_claim=False,selected_reduction=None,
       records=[dict(u_hours=r['u_hours'],body=r['body'],classifier=r['classifier'],policy=r['policy'],role=r['role'],
         GPU_underprediction_sec=(r['replay'] or {}).get('GPU_underprediction_sec'),
         delta_vs_current_recipe=(r['replay'] or {}).get('GPU_mass_delta_vs_current'),
         delta_vs_RW=(r['replay'] or {}).get('GPU_mass_delta_vs_RW'),mass_capture=r['tail']['mass_capture']) for r in comb]))
    write('OVERRESERVATION_REPORT',dict(definition='sum requested_GPU * max(duration-actual runtime,0)/3600',
       preregistered_max_ratio=2.,selected_delta=None,records=[dict(u_hours=r['u_hours'],body=r['body'],classifier=r['classifier'],policy=r['policy'],role=r['role'],
          overreservation_GPU_hours=(r['replay'] or {}).get('overreservation_GPU_hours'),P95_sec=(r['replay'] or {}).get('overreservation_P95_sec'),
          ratio=(r['replay'] or {}).get('overreservation_ratio')) for r in comb]))
    # Exact current-production Apr01 schedule already committed at LIVE BASE.
    # Do not invent scheduled starts from actual future starts. It is a partial
    # matched current ledger, not coverage of every issue in the ML panel.
    path='dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-04-01/V37_R4A_JOB_LEDGER.parquet'
    data=git('show',f'{BASE}:{path}',binary=True)
    ledger=pd.read_parquet(io.BytesIO(data),columns=['job_id','state_at_issue','submit_time','RSP_duration_seconds','RSP_duration_slots',
      'RSP_scheduled_start','RSP_scheduled_completion','requested_gpus','requested_walltime_seconds','snapshot_operating_day'])
    assert ledger.snapshot_operating_day.eq('2025-04-01').all()
    issue=pd.Timestamp('2025-03-31T08:00Z')
    assert pd.to_datetime(ledger.submit_time,utc=True).le(issue).all()
    panel=load_panel();d=panel[panel.issue_time.eq(issue)].copy()
    d=d.merge(ledger[ledger.state_at_issue.eq('PENDING')],on='job_id',validate='one_to_one',suffixes=('','_live'))
    terminal=[];live_replays=[]
    for h in U_HOURS:
        pred=pd.read_parquet(OUT/f'V40S3_PREDICTIONS_u{h}_DEVELOPMENT.parquet')
        z=d.merge(pred,on='job_issue_uid',validate='one_to_one',suffixes=('','_pred'))
        if not len(z):
            continue
        for classifier in ('C0','C1','C2','C3'):
            eta=next(r['eta'] for r in get('ETA_SELECTION')['rows'] if r['u_hours']==h and r['classifier']==classifier)
            if eta is None:continue
            flag=z[classifier+'_p_tail'].to_numpy()>=eta
            for body_name in ('B1','B2','B3'):
                for policy in ('R0','R1'):
                    sec=hybrid(z[body_name+'_Q90'],flag,z.RSP_duration_seconds,z.requested_walltime_seconds,policy,state='PENDING')
                    duration=slots(sec)
                    # Existing schedule slots are relative to D1 issue in this
                    # materializer: source code/contract checked, no +24 shift.
                    old_end=z.RSP_scheduled_completion.to_numpy();new_end=z.RSP_scheduled_start.to_numpy()+duration
                    assert np.array_equal(old_end,z.RSP_scheduled_start+z.RSP_duration_slots)
                    old_done=old_end<=120;new_done=new_end<=120
                    record=dict(u_hours=h,body=body_name,classifier=classifier,policy=policy,N=len(z),
                         changed_duration_N=int((duration!=z.RSP_duration_slots).sum()),
                         remain_complete=int((old_done & new_done).sum()),become_cross_boundary=int((old_done & ~new_done).sum()),
                         remain_cross_boundary=int((~old_done & ~new_done).sum()),cross_to_complete=int((~old_done & new_done).sum()),
                         future_integration_terminal_risk='HIGH' if ((old_done!=new_done).sum()/len(z)>.05) else 'REVIEW_REQUIRED')
                    terminal.append(record)
                    live_replays.append(dict(u_hours=h,body=body_name,classifier=classifier,policy=policy,
                         candidate=metrics(z.runtime_seconds,duration*900,z.num_gpus_req),
                         exact_live_RSP=metrics(z.runtime_seconds,z.RSP_duration_slots*900,z.num_gpus_req),
                         RW=metrics(z.runtime_seconds,slots(z.requested_walltime_seconds)*900,z.num_gpus_req)))
    write('TERMINAL_CLASS_IMPACT_AUDIT',dict(status='READ_ONLY_PARTIAL_MATCHED_LEDGER_AUDIT' if len(d) else 'NO_MATCHING_FROZEN_SCHEDULE_AUTHORITY',H=120,selected_change_count=None,
       source=f'git:{BASE}:{path}',source_SHA256=sha(data),operating_day='2025-04-01',issue_time=issue.isoformat(),
       matched_N=len(d),panel_issue_N=int(panel.issue_time.eq(issue).sum()),counts=terminal,
       scheduled_start_held_fixed=True,actual_start_used_as_scheduled_start=False,terminal_decisions_modified=0,
       risk_rule='Descriptive HIGH if >5% matched rows change class; not a model-selection gate; no automatic integration',
       limitation='Only existing Apr01 ledger was available at live head for preMay. Its issue has no accepted panel rows after stage label cutoff. Zero matched rows does not mean zero terminal transitions. Transition counts are unavailable; no actual start substituted.'))
    write('EXACT_CURRENT_RSP_MATCHED_REFERENCE',dict(status='READ_ONLY_POST_SELECTION_DIAGNOSTIC',selection_use=False,
       source=f'git:{BASE}:{path}',SHA256=sha(data),matched_N=len(d),
       exact_duration_difference_vs_current_recipe_max_sec=float(np.max(np.abs(d.RSP_duration_seconds-d.reference_safe_sec))) if len(d) else None,
       results=live_replays,unchanged_existing_reference=True))
    write('EXISTING_MIGRATION_TOUCH_AUDIT',dict(status='READ_ONLY_SCOPE_AUDIT',selected_migration_touch_count=None,
       candidate_inherited_migration_touch_count=None,reason='No joined inherited migration witness on the PENDING issue panel or Apr01 duration ledger. Do not fabricate zero from missing witness.',
       current_code='dayahead/v40g/domain.py: migration materialization/audit requires RUNNING; dayahead/v40a/coordination.py freezes A1 RUNNING',
       RUNNING_rows_redesigned=0,new_migration_witnesses=0,migration_changed='NO',migration_solve_calls=0))
    write('RUNTIME_ADAPTER_PROPOSAL',dict(status='PROPOSAL_ONLY_NO_SELECTED_EXPORT',candidate_fields=list(FIELDS),
       records=[],semantics=dict(runtime_class='BODY or TAIL_RISK',tail_flag='probability>=CAL eta',
       runtime_body_q50_sec='positive finite',runtime_body_q90_sec='positive finite >=Q50',tail_threshold_sec='one preregistered physical u',
       robust_tail_policy='NONE for BODY, R0 or R1 for TAIL_RISK',candidate_duration_sec='BODY Q90 or existing R0/R1 duration',
       flexibility_protected='tail flag only; no migration/site/electrical decision'),
       production_integration='NO',future_integration_entrypoints=[
          'dayahead/v37/aidc_materializer.py:_jobs_and_ledger (PENDING duration admission only)',
          'dayahead/v40a/initial.py:build_initial (PENDING metadata/eligible_standby admission only)'],
       optimizer_solver_files_requiring_changes=[],
       future_note='These are proposed local consumer entrypoints, not implemented changes. Solvers, RUNNING, A1, MF, WAN and terminal semantics remain protected.'))
    scope=get('SCOPE_CONTRACT');scope.update(new_fit_count=70,new_prediction_count=210,
          fit_count_definition='35 primary tree/logistic fits +35 independent repeats; 5 empirical body and5 base-rate estimates separately',
          prediction_count_definition='model API calls:70 training repeat checks +105 DEV/CAL predictions +35 exposed evaluation predictions; constant-array outputs excluded',
          scientific_classification=sel['classification'])
    write('SCOPE_CONTRACT',scope)
    write('MAY_FIREWALL',dict(canonical_timezone='fixed AEST UTC+10',local_cutoff='2025-05-01T00:00:00+10:00',UTC_cutoff='2025-04-30T14:00:00Z',
       MAY_PATH_OR_CODE_DISCOVERY_READS='NONZERO; initial repository inventory, sparse setup status, targeted source literals',
       MAY_METADATA_ONLY_READS='NONZERO_PATH_INDEX_METADATA; exact initial operation count not instrumented',
       MAY_RUNTIME_OR_STATUS_ROW_READS=0,MAY_ACTUAL_OUTCOME_READS=0,MAY_MODEL_BUILDING_READS=0,MAY_TRAINING_READS=0,
       MAY_CALIBRATION_READS=0,MAY_THRESHOLD_SELECTION_READS=0,MAY_ETA_SELECTION_READS=0,MAY_MODEL_SELECTION_READS=0,MAY_HYBRID_SELECTION_READS=0,
       May_total_read_count_zero_claim=False,shadow='SEALED',shadow_runtime_rows_read=0,
       row_source_allowlist=['pre-Apr24 PREPARED_ROWS and S2 label ledger','V40I preMay March rolling predictions',
                             'live PR27 Apr01 JOB_LEDGER planning columns','locally derived V40S3 issue/prediction panels'],
       generated_future_duration_is_not_actual_outcome=True,
       timestamp_row_checks='All source submit/start/end <Apr24UTC, stricter than canonical preMay; 0 rejected in already prefiltered source. Raw April partitions not reopened.',
       maximum_accepted_actual_timestamp=get('POPULATION_AUDIT')['max_accepted_timestamp'],
       claimed_counter_scope='V40S3 task scientific reads; historical revisions retain their own disclosures'))
    base_entries=git('ls-tree','-r',BASE).splitlines()
    # All pre-existing tracked paths are protected, including nonmaterialized
    # sparse paths. Compare Git blob identities, not May payload content.
    current=git('ls-tree','-r','HEAD').splitlines()
    baseline_map={s.split('\t',1)[1]:s.split('\t',1)[0] for s in base_entries}
    current_map={s.split('\t',1)[1]:s.split('\t',1)[0] for s in current}
    assert all(current_map.get(p)==v for p,v in baseline_map.items())
    allowed=('dayahead/v40s3/',PREFIX)
    changed=git('diff','--name-only',BASE).splitlines()
    assert all(p.startswith(allowed) for p in changed)
    code=[p for p in baseline_map if p.startswith(('dayahead/v40a/','dayahead/v40g/','dayahead/v38/','dayahead/v39e/','dayahead/v37r3/')) and p.endswith('.py')]
    code += ['dayahead/v35r3/algorithm.py','dayahead/tools/run_v35r3e_r1_beam.py',
             'dayahead/v17_ac_restoration_runner.py','dayahead/v37/runner.py']
    write('PROTECTED_SCOPE_DIFF',dict(status='PASS',base=BASE,all_preexisting_tracked_paths_verified=len(baseline_map),
       changed_outside_allowed_prefixes=[],allowed_prefixes=allowed,
       protected_source_Git_blobs={p:baseline_map[p] for p in code},
       exact_future_local_consumer_files=['dayahead/v37/aidc_materializer.py','dayahead/v40a/initial.py'],
       future_solver_modification_files=[],source_changes_migration=0,source_changes_WAN=0,source_changes_terminal=0,
       production_tree_modified=False,V40S2_merged=False))
    ledger=get('READ_LEDGER');ledger['entries'].append(dict(path=f'git:{BASE}:{path}',SHA256=sha(data),purpose='Apr01 existing planning duration/start ledger; no actual outcome; post-selection terminal/reference diagnostic'))
    ledger['entries'].append(dict(path=str(REF/'dayahead/artifacts/v40q_regime_conditioned_tail/clean_execution_01/PREPARED_ROWS.parquet'),
           SHA256=get('POPULATION_AUDIT')['source_SHA256'],purpose='Amended normative PENDING reconstruction; strict two-clock predictors; full row timestamps checked before acceptance'))
    ledger['entries']=list({json.dumps(r,sort_keys=True):r for r in ledger['entries']}.values())
    write('READ_LEDGER',ledger)
    write('FAILURE_DECOMPOSITION',dict(classification=sel['classification'],winner=None,causal_feature_authority='PASS_STRICT_CLOCK_ONLY',
       membership_authority='PASS_NORMATIVE_RECONSTRUCTION',
       cause='Current proven clock features do not yield an eligible selective body/tail method across DEV/CAL. This is not a failure to reconstruct PENDING membership.',
       DEV_CAL_eligible=0,selection_frozen_before_exposed=True,
       calibration_ECE_le_005_by_classifier={c:[r['u_hours'] for r in tail if r['role']=='CALIBRATION' and r['body']=='B3' and r['classifier']==c and r['ECE']<=.05] for c in ['C0','C1','C2','C3']},
       important_distinction='Recall/capture can reach100% by flagging every job. That fails preregistered nontrivial-flagging gate and may leave R0 unchanged or inflate R1 reservation.',
       all_gates='V40S3_EXACT_GATE_TABLE.csv',retuning_count=0))
    print('REPORTS_READY',len(body),len(tail),'terminal matched',len(d))


if __name__=='__main__':prepare_reports()
