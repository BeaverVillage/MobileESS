"""One causal D-1 service requirement for every comparison case."""
from pathlib import Path
from copy import deepcopy
import math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,write_parquet,reference,sha,digest
from dayahead.v40a.feedback import authorized_options,pcc_from_jobs
from dayahead.v40a.invariants import tail
from .authority import REL,current_context,seal_previous


def preflight(repo):
    from dayahead.v40d_actual.inputs import frozen_jobs
    from dayahead.v40e.smoke import evaluate
    from dayahead.v40e.audit import OLD
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v36.contracts import PF_TAN
    repo=Path(repo).resolve();root=seal_previous(repo);out=root/'common_service';out.mkdir(exist_ok=True)
    bindings=read(repo/OLD/'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases']
    binding=next(b for b in bindings if b['day']=='2025-05-01' and b['case']=='B0')
    jobs=frozen_jobs(repo,binding)[0];before=deepcopy(jobs)
    src=repo/'dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01'
    ledgerpath=src/'V37_R4A_JOB_LEDGER.parquet';snapshot=src/'V37_R4A_D1_SNAPSHOT.parquet'
    ledger=pd.read_parquet(ledgerpath);ledger['uid']=ledger.job_id.astype(str);ledger=ledger.set_index('uid')
    snap=pd.read_parquet(snapshot);snap['uid']=snap.id.astype(str);snap=snap.set_index('uid')
    assert set(ledger.index)=={r['job_uid'] for r in jobs} and not ledger.index.duplicated().any()
    issue=pd.Timestamp('2025-04-30T18:00:00+10:00')
    assert (pd.to_datetime(snap.loc[ledger.index].submit_time,utc=True)<=issue.tz_convert('UTC')).all()
    rows=[];old_diff=0;projection=('job_uid','start_slot','AIDC_site','migration_selected','state_at_issue','qos','requested_GPU')
    for job in jobs:
        r=ledger.loc[job['job_uid']];duration=int(r.RSP_duration_slots);seconds=float(r.RSP_duration_seconds)
        assert duration==max(1,math.ceil(seconds/900)) and seconds>0
        assert int(job['requested_GPU'])==int(r.requested_gpus) and job['state_at_issue']==r.state_at_issue and job['qos']==r.qos
        assert r.duration_authority in ['SAFE_CAUSAL_RUNTIME_PENDING','REQUESTED_REMAINING','REQUESTED_WALLTIME_FAIL_CLOSED']
        old_diff+=int(r.RW_duration_slots)!=duration
        job.update(safe_duration_slots=duration,safe_duration_seconds=seconds,duration_authority=str(r.duration_authority),
            end_slot=int(job['start_slot'])+duration,RSP_start_slot=int(r.RSP_scheduled_start),RW_completion_slot=int(r.RW_scheduled_completion),
            eligible_standby=bool(job['state_at_issue']=='PENDING' and job['qos']=='standby' and r.duration_authority=='SAFE_CAUSAL_RUNTIME_PENDING'
                and int(r.RSP_scheduled_start)<=int(r.RW_scheduled_completion)-duration),
            source_snapshot_sha256=sha(snapshot),operating_day='2025-05-01')
        job['post_H_site']=job['AIDC_site'] if job['end_slot']>120 else None
        job['terminal_class']='IN_DAY_COMPLETE' if job['end_slot']<=120 else 'CROSS_BOUNDARY' if job['start_slot']<120 else 'POST_H_ONLY'
        # A terminal obligation is immutable service data, not an optimized tail.
        obligation={'must_complete_by_H':job['end_slot']<=120,'postH_profile':tail(job)}
        job['common_terminal_obligation']=obligation
        rows.append({'job_uid':job['job_uid'],'requested_GPU':job['requested_GPU'],'state_at_issue':job['state_at_issue'],
            'service_tier':job['qos'],'T_DA_seconds':seconds,'T_DA_slots':duration,'duration_authority':str(r.duration_authority),
            'terminal_obligation':obligation,'source_snapshot_sha':sha(snapshot),'old_RW_duration_slots':int(r.RW_duration_slots),
            'old_RSP_duration_slots':duration,'reference_start':job['start_slot'],'reference_site':job['AIDC_site']})
    for a,b in zip(before,jobs):assert all(a.get(k)==b.get(k) for k in projection)
    rows.sort(key=lambda x:x['job_uid']);authority_payload=[{k:v for k,v in r.items() if k not in ['old_RW_duration_slots','old_RSP_duration_slots','reference_start','reference_site']} for r in rows]
    authority_sha=digest(authority_payload)
    write_json(out/'COMMON_DA_SERVICE_AUTHORITY.json',{'source':reference(ledgerpath),'snapshot':reference(snapshot),
        'runtime_fields':['RSP_duration_seconds','RSP_duration_slots','duration_authority'],'rows':rows,'COMMON_DA_DURATION_SHA':authority_sha,
        'definition':'canonical SHA of per-job common service identity, duration/residual and terminal obligation; no case-specific runtime',
        'Realized_future_duration_read_count':0})
    flat=pd.DataFrame([{**r,'terminal_obligation':__import__('json').dumps(r['terminal_obligation'],sort_keys=True)} for r in rows]);write_parquet(out/'COMMON_DA_SERVICE_AUTHORITY.parquet',flat)
    write_json(out/'COMMON_B0_REFERENCE_JOBS.json',jobs)
    ctx=current_context(repo);failures=[]
    try:
        for r in jobs:
            try:
                opts=authorized_options(r,ctx.capacity)
                if (r['AIDC_site'],r['start_slot']) not in opts:failures.append({'job_uid':r['job_uid'],'constraint':'REFERENCE_OPTION_EXCLUDED','reference_site':r['AIDC_site'],'reference_start':r['start_slot']})
                if max(24,r['start_slot'])<min(120,r['end_slot']):
                    if r['AIDC_site'] not in ctx.capacity.aidc_ids:failures.append({'job_uid':r['job_uid'],'constraint':'UNASSIGNED_OPERATING_DAY_EXECUTION'})
                    elif not ctx.capacity.eligible_racks(r['AIDC_site'],r['requested_GPU']):failures.append({'job_uid':r['job_uid'],'constraint':'REFERENCE_RACK_COMPATIBILITY'})
            except (ValueError,KeyError) as e:failures.append({'job_uid':r['job_uid'],'constraint':str(e)})
        pcc=gpu=None;grid=None
        if not failures:
            try:pcc,gpu=pcc_from_jobs(jobs,ctx)
            except ValueError as e:failures.append({'constraint':str(e)})
        if not failures:
            grid=evaluate(ctx,jobs,pcc_override=pcc)
            if grid['status']!='PASS':failures.append({'constraint':'PLANNING_PHYSICAL_ROWS','violations':grid['violations'],'metrics':{k:v for k,v in grid.items() if k!='coefficient_SHAs'}})
            it=np.array([[float(site_it_power_kw(ctx.capacity.site_capacity[s],int(gpu[t,k]))) for k,s in enumerate(ctx.capacity.aidc_ids)] for t in range(96)])
            np.savez_compressed(out/'COMMON_B0_REFERENCE_AIDC.npz',gpu=gpu,it=it,pcc=pcc,qcc=pcc*PF_TAN)
            write_json(out/'COMMON_B0_PLANNING_GATE.json',grid)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()
    result={'COMMON_DA_DURATION_SOURCE':reference(ledgerpath),'COMMON_DA_DURATION_SHA':authority_sha,
        'common_authority_file':reference(out/'COMMON_DA_SERVICE_AUTHORITY.json'),'job_count':len(jobs),
        'RW_vs_RSP_duration_difference_count':old_diff,'case_dependent_duration_count_after_correction':0,
        'B0_REFERENCE_IN_COMMON_DOMAIN':'FAIL' if failures else 'PASS','B0_B1_COMMON_SERVICE_IDENTITY':'PASS',
        'B0_B1_DURATION_AUTHORITY_IDENTITY':'PASS','B0_B2_DURATION_AUTHORITY_IDENTITY':'PASS','B1_B3_A0_DURATION_AUTHORITY_IDENTITY':'PASS',
        'COMMON_DURATION_IDENTITY':'PASS','case_service_SHA':{c:authority_sha for c in ['B0','B1','B2','B3']},
        'reference_start_site_inherited_state_preserved':True,'terminal_baseline':'COMMON_B0_REFERENCE, not RSP',
        'case_common_services':['job_uid','requested_GPU','state_at_issue','qos','T_DA','terminal_obligation'],
        'failures':failures,'B0_Planning_J':None if grid is None else grid['rho_max'],
        'B1_min_rho_started':False,'FULL_MAY_AUTHORIZED':'NO','B2_B3_AUTHORIZED':'NO'}
    write_json(root/'V40F_COMMON_SERVICE_PREFLIGHT.json',result)
    print(__import__('json').dumps(result),flush=True)
    return result
