"""Current production loader and immutable per-case reuse certificates."""
import numpy as np
import pandas as pd
from .common import *

def validate_case_files(day,case,checkpoint,case_root):
    from dayahead.v36.storage import CASE_FILES,CRITICAL_COLUMNS,PRIMARY_KEYS
    payload=read(checkpoint)
    if case=='B3':raise ValueError('OLD_B3_REUSE_FORBIDDEN')
    if payload.get('status')!='PASS' or payload.get('date')!=day or payload.get('case')!=case:raise ValueError('CASE_IDENTITY_OR_COMPLETION')
    if {i['relative_path'] for i in payload['files']}!=set(CASE_FILES):raise ValueError('INCOMPLETE_CASE_CERTIFICATE')
    for item in payload['files']:
        path=case_root/item['relative_path']
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:raise ValueError('HISTORICAL_FILE_DRIFT')
        if path.suffix in ('.parquet','.csv'):
            frame=pd.read_parquet(path) if path.suffix=='.parquet' else pd.read_csv(path)
            # V39E's accepted producer intentionally emits its per-day ledger
            # and AIDC_id/PCC schema, not the older April V36 schema aliases.
            # These fields come from current campaign_adapter.build_day and
            # aidc_materializer.materialize_day; no historical bytes are edited.
            production_columns={
              'AIDC_SCHEDULER_LEDGER.parquet':['job_id','requested_GPUs','RSP_duration_slots','RW_scheduled_start','RW_scheduled_completion','RSP_scheduled_start','RSP_scheduled_completion','source_snapshot_sha256'],
              'IDC_FACILITY_96.parquet':['slot','AIDC_id','IT_power_kW','PCC_P_kW','PCC_Q_kvar','operating_day'],
              'SOLVER_RUNS.parquet':['solver_type','case','vehicle','beam_state','status','WorkLimit','incumbent','best_bound','gap','wallclock','threads']}
            missing=set(production_columns.get(path.name,CRITICAL_COLUMNS.get(path.name,())))-set(frame.columns)
            # Empty MESS/OFF and solver tables retain the inherited schema.
            if missing and len(frame):raise ValueError('SCHEMA_MISSING:'+path.name+':'+str(missing))
            keys={'IDC_FACILITY_96.parquet':['slot','AIDC_id'],
                  'SOLVER_RUNS.parquet':['case','vehicle','beam_state']}.get(path.name,PRIMARY_KEYS.get(path.name))
            if keys and all(k in frame for k in keys) and frame.duplicated(keys).any():raise ValueError('DUPLICATE_KEYS')
    result=payload['result'];fresh=result['Fresh'];planning=result['Planning']
    if fresh['day']!=day or fresh['case']!=case:raise ValueError('FRESH_IDENTITY')
    if fresh['convergence_count']!=96 or fresh['physical_violation'] or not planning['pass']:raise ValueError('PHYSICAL_GATE')
    gates=read(case_root/'summary/PHYSICAL_GATES.json')
    if gates['Fresh_solve_coverage']!='96/96':raise ValueError('FRESH_COVERAGE')
    for namespace in ('Planning','Fresh'):
        if any(gates[namespace][key]!=0 for key in ('voltage_violation_count','current_violation_count','transformer_violation_count')):raise ValueError('PHYSICAL_VIOLATION')
    objective=read(case_root/'summary/OBJECTIVE.json')
    if objective['date']!=day or objective['case']!=case or objective['primary_objective_J']!=result['objective']:raise ValueError('PLANNING_BINDING')
    inputs=read(case_root/'inputs/INPUT_AUTHORITY.json')
    if inputs['date']!=day or inputs['case']!=case:raise ValueError('INPUT_IDENTITY')
    for item in inputs['immutable_references'].values():
        if item.get('sha256') and (not Path(item['path']).is_file() or sha(Path(item['path']))!=item['sha256']):raise ValueError('INPUT_SHA_DRIFT:'+str(item))
    return payload

def load_historical(day,case):
    if case=='B3':raise ValueError('OLD_B3_REUSE_FORBIDDEN')
    from dayahead.v39e.campaign_adapter import configure_v37_runner,build_day,freeze_path
    from dayahead.v39d.actual import validate_actual_fixed_replay
    runner=configure_v37_runner()
    aidc=build_day(REPO,day,'B0' if case=='B2' else case)
    fingerprint=runner.case_execution_fingerprint(REPO,day,case,aidc)
    result=runner._valid_case_checkpoint(OLD,day,case,fingerprint)
    if result is None:raise ValueError('CURRENT_LOADER_REJECTS_OLD_RESULT')
    cp=runner._checkpoint_path(OLD,day,case);case_root=runner._case_root(OLD,day,case)
    payload=validate_case_files(day,case,cp,case_root)
    freeze=read(freeze_path(REPO,day,case))
    if validate_actual_fixed_replay(freeze,freeze['DA_decision_SHA256'])['status']!='PASS':raise ValueError('DA_REPLAY')
    return {'status':'PASS','day':day,'case':case,'CURRENT_LOADER_ACCEPTS_OLD_RESULT':'YES',
       'historical_checkpoint':str(cp),'historical_checkpoint_SHA':sha(cp),'historical_case_root':str(case_root),
       'files':payload['files'],'current_execution_fingerprint':fingerprint,'DA_file_SHA':sha(freeze_path(REPO,day,case)),
       'DA_decision_SHA':freeze['DA_decision_SHA256'],'Fresh_schedule_SHA':result['Fresh']['schedule_sha256'],
       'current_loader_source_SHA':sha(REPO/'dayahead/v37/runner.py'),
       'new_reuse_loader_source_SHA':sha(Path(__file__)),'terminal_authority_binding':'COMPLETE_ACCEPTED_DA_FREEZE_AND_CURRENT_V39K_MANIFEST',
       'stale_authority_check':'EXACT_CURRENT_FINGERPRINT; historical V39H provenance is permitted only via current V39K authority',
       'old_result_modified':False}

def build_matrix(certificates,approved):
    rows=[]
    for day in DAYS:
        for case in CASES:
            key=f'{day}:{case}';cert=certificates.get(key)
            reuse=case!='B3' and approved.get(case,False) and cert and cert.get('status')=='PASS'
            rows.append({'day':day,'case':case,'status':'REUSE_CERTIFIED' if reuse else 'RUN_REQUIRED',
                 'certificate':str(ROOT/'reuse_certificates'/f'{day}_{case}.json') if reuse else None,
                 'B3_method':'BOUNDED_ITERATIVE_AIDC_MESS_CO_OPTIMIZATION' if case=='B3' else None})
    return rows

def write_matrix(rows):
    write(ROOT/'V40B_MAY_EXECUTION_MATRIX.json',{'rows':rows,'total':124})
    pd.DataFrame(rows).to_csv(ROOT/'V40B_MAY_EXECUTION_MATRIX.csv',index=False)
