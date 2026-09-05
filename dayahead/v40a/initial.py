"""A0 reuses the accepted causal RSP scheduler and V39E placement logic."""
from __future__ import annotations
from types import FunctionType
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from .invariants import digest, H, BEGIN
from .context import file_sha
from .feedback import pcc_from_jobs


def build_initial(repo, day, context):
    materialization_started=time.perf_counter()
    from dayahead.v39e import initial_state as initial
    from dayahead.v39e import full_spatial as spatial
    from dayahead.v39a.spatial import production_activity
    root=Path(repo)/'dayahead/artifacts/v37_r4a_per_day_aidc/days'/day
    ledger=pd.read_parquet(root/'V37_R4A_JOB_LEDGER.parquet')
    snapshot=pd.read_parquet(root/'V37_R4A_D1_SNAPSHOT.parquet')
    rw=pd.read_parquet(root/'V37_R4A_RW_SCHEDULE.parquet')
    rsp=pd.read_parquet(root/'V37_R4A_RSP_SCHEDULE.parquet')
    if ledger.job_id.astype(str).duplicated().any():raise ValueError('DUPLICATE_LEDGER_JOB_UID')
    ledger=ledger.copy();ledger['job_uid']=ledger.job_id.astype(str)
    snap=snapshot.assign(job_uid=snapshot.id.astype(str)).set_index('job_uid')
    if not set(ledger.job_uid).issubset(snap.index):raise ValueError('MISSING_CAUSAL_SNAPSHOT_JOB')
    issue=pd.Timestamp(day,tz='Etc/GMT-10')-pd.Timedelta(hours=6)
    if not (pd.to_datetime(snap.loc[ledger.job_uid].submit_time,utc=True)<=issue.tz_convert('UTC')).all():raise ValueError('FUTURE_JOB_READ')
    sites=tuple(context.capacity.aidc_ids)
    def voltage_constraints(model,active,capacity,*args):
        controls={}
        for t in range(96):
            for s in sites:
                cap=int(capacity.site_capacity[s]);vals=context.tables[s][t]
                g=model.addVar(vtype=GRB.INTEGER,lb=0,ub=cap);p=model.addVar(lb=float(vals.min()),ub=float(vals.max()))
                model.addConstr(g==active[t,s]);model.addGenConstrPWL(g,p,list(range(cap+1)),vals.tolist());controls[t,s]=p
        for t,c in enumerate(context.coefficients):
            for n,v in enumerate(c.voltage_constant):
                expression=float(v)+gp.quicksum(float(c.voltage_matrix[i,n])*controls[t,s] for i,s in enumerate(sites))
                model.addRange(expression,(.95-1e-7)**2,(1.05+1e-7)**2)
    def cloned(fn):
        namespace=dict(fn.__globals__);namespace['_add_frozen_planning_voltage_constraints']=voltage_constraints
        return FunctionType(fn.__code__,namespace,argdefs=fn.__defaults__,closure=fn.__closure__)
    base_materialization_seconds=time.perf_counter()-materialization_started
    initial_fn=cloned(initial.build_rw_anchored_initial_state);initial_fn.__kwdefaults__=initial.build_rw_anchored_initial_state.__kwdefaults__
    running=[(str(r.job_id),int(r.requested_gpus)) for r in rw.itertuples(index=False) if r.state_at_issue=='RUNNING']
    state=initial_fn(running,production_activity(rw),context.capacity,name=f'V40A_RW_INITIAL_{day}',planning_repo=Path(repo),operating_day=day)
    if state['status']!='PASS':raise RuntimeError('A0_RW_INITIAL_AUTHORITY_INFEASIBLE:'+str(state))
    plan_fn=cloned(spatial.plan_fixed_temporal_schedule);plan_fn.__kwdefaults__=spatial.plan_fixed_temporal_schedule.__kwdefaults__
    plan=plan_fn(production_activity(rsp),context.capacity,state['initial_state'],name=f'V40A_A0_{day}',allow_running_migration=False,planning_repo=Path(repo),operating_day=day)
    if plan['status']!='OPTIMAL':raise RuntimeError('A0_REQUIRES_TERMINAL_SAFE_ESCALATION_AUTHORITY:'+str(plan))
    assignments={str(r['job_uid']):r for r in plan['assignments']}
    sched=rsp.assign(job_uid=rsp.job_id.astype(str)).set_index('job_uid')
    jobs=[]
    for r in ledger.itertuples(index=False):
        uid=r.job_uid;q=sched.loc[uid];start=int(q.scheduled_start_slot);end=int(q.scheduled_end_slot)
        a=assignments.get(uid);site=a['destination_AIDC'] if a else state['initial_state'].get(uid,'UNASSIGNED')
        eligible=(str(r.state_at_issue)=='PENDING' and str(r.qos)=='standby' and str(r.duration_authority)=='SAFE_CAUSAL_RUNTIME_PENDING'
                  and int(r.RSP_duration_slots)>0 and pd.notna(r.RW_scheduled_completion) and int(r.RSP_scheduled_start)<=int(r.RW_scheduled_completion)-int(r.RSP_duration_slots))
        jobs.append({'job_uid':uid,'state_at_issue':str(r.state_at_issue),'qos':str(r.qos),'requested_GPU':int(r.requested_gpus),
                     'safe_duration_slots':int(r.RSP_duration_slots),'safe_duration_seconds':float(r.RSP_duration_seconds),
                     'start_slot':start,'end_slot':end,'AIDC_site':site,'Rack_label':a['logical_Rack_compatibility_label'] if a else None,
                     'migration_selected':False,'migration_destination':None,'initial_AIDC':state['initial_state'].get(uid),
                     'terminal_class':'IN_DAY_COMPLETE' if end<=H else 'CROSS_BOUNDARY' if start<H else 'POST_H_ONLY',
                     'post_H_site':site if end>H else None,'eligible_standby':bool(eligible),
                     'RSP_start_slot':int(r.RSP_scheduled_start),'RW_completion_slot':int(r.RW_scheduled_completion),
                     'duration_authority':str(r.duration_authority),'source_snapshot_sha256':file_sha(root/'V37_R4A_D1_SNAPSHOT.parquet'),
                     'operating_day':day})
    pcc,occ=pcc_from_jobs(jobs,context)
    return {'jobs':jobs,'PCC':pcc,'GPU':occ,'initial_state':state,'placement':plan,'A0_SHA':digest(jobs),
            'source_SHAs':{str(p):file_sha(p) for p in root.iterdir() if p.is_file()},'AIDC_solver_calls':2,
            'RSP_base_materialization_seconds':base_materialization_seconds,
            'RSP_scheduler_rerun':False,'RSP_source':'EXISTING_CAUSAL_MATERIALIZED_SCHEDULE'}
